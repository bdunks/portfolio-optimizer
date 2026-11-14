from __future__ import annotations

import time
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    Account,
    Base,
    OptimizerRun,
    PolicyRevision,
    RecommendationGroup,
    Security,
)
from app.db.session import create_database_engine
from app.optimizer.core import _cohere_trade_group_legs, _group_priorities
from app.optimizer.validation import validate_candidate
from app.schemas import (
    OptimizerLotReviewIntentInput,
    OptimizerSelectionInput,
    RecommendationAnnotationInput,
)
from app.services import optimizer_service
from app.services.errors import AppError
from tests.test_optimizer_core import _shared_funding_case


def _service_outcome(
    inputs: object,
    legs: tuple[object, ...],
    *,
    core_group_id: str | None,
    status: str = "ready",
    trade_group_priorities: tuple[object, ...] | None = None,
) -> optimizer_service.ValidatedOptimizerCandidate:
    priority_rows = trade_group_priorities or (
        (
            SimpleNamespace(
                group_id=core_group_id,
                rank=1,
                priority_score=Decimal(1),
                rationale=("coherent component",),
            ),
        )
        if core_group_id is not None
        else ()
    )
    metadata = SimpleNamespace(
        input_generation=inputs.source_generation,
        source_checksum=inputs.source_checksum,
        solver="test-solver",
        implementation_version="service-lifecycle-test",
        solver_versions={},
        solver_statuses=(),
        elapsed_seconds=0.01,
        screening_seconds=0.005,
        solve_seconds=0.005,
        tax_regions_considered=1,
        tax_regions_solved=1,
        tax_region_search_complete=True,
        integer_search_complete=True,
        screened_lot_count=len(inputs.lots),
        selected_lot_ids=tuple(
            allocation.broker_lot_id
            for leg in legs
            if getattr(leg, "side", None) == "SELL"
            for allocation in getattr(leg, "selected_lots", ())
        ),
        candidate_types=(),
        exposure_coverage_complete=True,
        rounding_attempts=0,
        warnings=(),
        trade_group_priorities=priority_rows,
    )
    candidate = SimpleNamespace(legs=legs, status=status, metadata=metadata)
    validation = validate_candidate(inputs, legs)
    assert validation.accepted, validation.reasons
    return optimizer_service.ValidatedOptimizerCandidate(
        candidate, validation, time.monotonic() + 60, status
    )



def _outcome_with_real_priorities(
    inputs: object,
    baseline: object,
    screen: object,
    legs: tuple[object, ...],
    *,
    core_group_id: str | None = None,
) -> tuple[optimizer_service.ValidatedOptimizerCandidate, tuple[object, ...]]:
    priorities, warnings = _group_priorities(
        inputs, screen, baseline, legs, time.monotonic() + 5
    )
    assert warnings == ()
    outcome = _service_outcome(
        inputs,
        legs,
        core_group_id=core_group_id,
        trade_group_priorities=priorities,
    )
    return outcome, priorities


def _seed_real_writer_run(
    tmp_path: Path,
    inputs: object,
    outcome: optimizer_service.ValidatedOptimizerCandidate,
    *,
    expected_universe: dict[str, list[str]],
) -> tuple[object, object, optimizer_service.PreparedOptimizerRun, str]:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'real-review-writer.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1

    now = datetime.now(UTC)
    run_id = "f7c9888c-4a72-4fc1-8e6b-37d6da832809"
    policy_id = "af5a2ec8-2f79-485b-8cde-40a7692e934d"
    prepared = optimizer_service.PreparedOptimizerRun(
        inputs=inputs,
        batch_settings={
            "max_sell_tickers_per_batch": 2,
            "max_sell_lots_per_batch": 2,
            "max_total_orders_per_batch": 3,
        },
        frozen_input_bundle={"mode": "real_optimizer"},
        input_fingerprint="real-review-writer-fingerprint",
        policy_revision_id=policy_id,
        source_generation=inputs.source_generation,
        as_of=inputs.account.as_of,
        proposed_trade_date=inputs.proposed_trade_date,
    )
    with session_factory.begin() as session:
        session.add(
            PolicyRevision(
                id=policy_id,
                revision_number=1,
                status="ACTIVE",
                created_at=now,
            )
        )
        session.flush()
        session.add(
            Account(
                id=inputs.account.local_account_id,
                broker_account_id_key="real-review-test-account",
                display_name="Real review test account",
                cash_usd=inputs.account.cash_usd,
                settled_buying_power_usd=inputs.account.settled_buying_power_usd,
                as_of=inputs.account.as_of,
            )
        )

        for security_id, security in enumerate(inputs.securities, start=1):
            ticker = security.identity.ticker

            session.add(
                Security(
                    id=security_id,
                    ticker=ticker,
                    asset_type=security.identity.asset_type,
                )
            )
        session.flush()
        run = OptimizerRun(
            id=run_id,
            policy_revision_id=policy_id,
            source_generation=inputs.source_generation,
            as_of=inputs.account.as_of,
            proposed_trade_date=inputs.proposed_trade_date,
            solver_version="real-writer-test",
            status="COMPLETE",
            batch_settings=prepared.batch_settings,
            metrics={"basket_revision": 0},
            warnings=[],
            input_fingerprint=prepared.input_fingerprint,
            frozen_input_bundle=prepared.frozen_input_bundle,
        )
        session.add(run)
        session.flush()
        optimizer_service._persist_candidate(
            session,
            run,
            prepared,
            outcome,
            expected_universe=expected_universe,
        )
    return engine, session_factory, prepared, run_id


def _patch_real_review_solver(
    monkeypatch: pytest.MonkeyPatch,
    prepared: optimizer_service.PreparedOptimizerRun,
    outcomes: dict[frozenset[str], optimizer_service.ValidatedOptimizerCandidate],
) -> None:
    def prepared_again(
        _session: object,
        _request: object,
        *,
        proposed_trade_date: date | None = None,
        batch_limits: object | None = None,
    ) -> optimizer_service.PreparedOptimizerRun:
        del proposed_trade_date, batch_limits
        return prepared

    def current_again(
        _session: object,
        _prepared: optimizer_service.PreparedOptimizerRun,
        *,
        deadline: float | None = None,
    ) -> None:
        del deadline

    async def solve_subset(
        _inputs: object,
        _supervisor: object,
        *,
        sell_lot_ids: tuple[str, ...] | None = None,
        validation_executor: object = None,
    ) -> optimizer_service.ValidatedOptimizerCandidate:
        del validation_executor
        return outcomes[frozenset(sell_lot_ids or ())]

    monkeypatch.setattr(optimizer_service, "prepare_optimizer_run", prepared_again)
    monkeypatch.setattr(optimizer_service, "assert_optimizer_run_current", current_again)
    monkeypatch.setattr(optimizer_service, "run_validated_candidate", solve_subset)


def _inputs_with_disjoint_aapl_lot(
    inputs: object, screen: object
) -> tuple[object, object, object, object]:
    original_lot = next(lot for lot in inputs.lots if lot.broker_lot_id == "loss-lot")
    loss_lot = replace(original_lot, shares=Decimal(9), available_shares=Decimal(9))
    extra_lot = replace(
        original_lot,
        broker_lot_id="aapl-extra-lot",
        shares=Decimal(1),
        available_shares=Decimal(1),
    )
    updated_inputs = replace(
        inputs,
        lots=(
            *(loss_lot if lot.broker_lot_id == "loss-lot" else lot for lot in inputs.lots),
            extra_lot,
        ),
    )
    updated_baseline = validate_candidate(updated_inputs, ())
    assert updated_baseline.accepted
    assert updated_baseline.evaluation is not None
    original_sale = next(row for row in screen.sales if row.lot.broker_lot_id == "loss-lot")
    updated_sales = (
        *(
            replace(row, lot=loss_lot, maximum_shares=Decimal(9))
            if row.lot.broker_lot_id == "loss-lot"
            else row
            for row in screen.sales
        ),
        replace(original_sale, lot=extra_lot, maximum_shares=Decimal(1)),
    )
    updated_screen = replace(
        screen,
        baseline=updated_baseline.evaluation,
        sales=updated_sales,
        screened_lot_count=len(updated_sales),
    )
    return updated_inputs, updated_baseline, updated_screen, extra_lot

@pytest.mark.asyncio
async def test_real_writer_reconciles_coherent_component_identity_through_review_lifecycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs, baseline, screen, original_legs = _shared_funding_case()
    priorities, warnings = _group_priorities(
        inputs, screen, baseline, original_legs, time.monotonic() + 5
    )
    assert warnings == ()
    assert len(priorities) == 1
    canonical_legs = _cohere_trade_group_legs(original_legs)
    canonical_core_id = priorities[0].group_id
    full_outcome = _service_outcome(inputs, canonical_legs, core_group_id=canonical_core_id)
    msft_sell = next(leg for leg in canonical_legs if leg.side == "SELL" and leg.ticker == "MSFT")
    shared_buy = next(leg for leg in canonical_legs if leg.side == "BUY")
    narrowed_legs = (
        replace(msft_sell, sequence=1, group_ids=("sale:MSFT",)),
        replace(
            shared_buy,
            shares=Decimal(1),
            sequence=2,
            depends_on_leg_ids=(msft_sell.leg_id,),
            group_ids=("sale:MSFT",),
        ),
    )
    narrowed_outcome = _service_outcome(inputs, narrowed_legs, core_group_id="sale:MSFT")
    no_trade_outcome = _service_outcome(inputs, (), core_group_id=None, status="no_trade")

    engine = create_database_engine(f"sqlite:///{tmp_path / 'real-coherent-writer.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1

    now = datetime.now(UTC)
    run_id = "f7c9888c-4a72-4fc1-8e6b-37d6da832809"
    policy_id = "af5a2ec8-2f79-485b-8cde-40a7692e934d"
    prepared = optimizer_service.PreparedOptimizerRun(
        inputs=inputs,
        batch_settings={
            "max_sell_tickers_per_batch": 2,
            "max_sell_lots_per_batch": 2,
            "max_total_orders_per_batch": 3,
        },
        frozen_input_bundle={"mode": "real_optimizer"},
        input_fingerprint="real-coherent-writer-fingerprint",
        policy_revision_id=policy_id,
        source_generation=inputs.source_generation,
        as_of=inputs.account.as_of,
        proposed_trade_date=inputs.proposed_trade_date,
    )
    with session_factory.begin() as session:
        session.add(
            PolicyRevision(
                id=policy_id,
                revision_number=1,
                status="ACTIVE",
                created_at=now,
            )
        )
        session.flush()
        session.add(
            Account(
                id=inputs.account.local_account_id,
                broker_account_id_key="real-coherent-test-account",
                display_name="Real coherent test account",
                cash_usd=inputs.account.cash_usd,
                settled_buying_power_usd=inputs.account.settled_buying_power_usd,
                as_of=inputs.account.as_of,
            )
        )
        session.add_all(
            [
                Security(id=1, ticker="AAPL", asset_type="EQUITY"),
                Security(id=2, ticker="MSFT", asset_type="EQUITY"),
                Security(id=3, ticker="NEWETF", asset_type="ETF"),
            ]
        )
        session.flush()
        run = OptimizerRun(
            id=run_id,
            policy_revision_id=policy_id,
            source_generation=inputs.source_generation,
            as_of=inputs.account.as_of,
            proposed_trade_date=inputs.proposed_trade_date,
            solver_version="real-writer-test",
            status="COMPLETE",
            batch_settings=prepared.batch_settings,
            metrics={"basket_revision": 0},
            warnings=[],
            input_fingerprint=prepared.input_fingerprint,
            frozen_input_bundle=prepared.frozen_input_bundle,
        )
        session.add(run)
        session.flush()
        optimizer_service._persist_candidate(
            session,
            run,
            prepared,
            full_outcome,
            expected_universe={
                "sale:AAPL": ["loss-lot"],
                "sale:MSFT": ["msft-loss-lot"],
            },
        )

    def prepared_again(
        _session: object,
        _request: object,
        *,
        proposed_trade_date: date | None = None,
        batch_limits: object | None = None,
    ) -> optimizer_service.PreparedOptimizerRun:
        del proposed_trade_date, batch_limits
        return prepared

    def current_again(
        _session: object,
        _prepared: optimizer_service.PreparedOptimizerRun,
        *,
        deadline: float | None = None,
    ) -> None:
        del deadline

    async def solve_subset(
        _inputs: object,
        _supervisor: object,
        *,
        sell_lot_ids: tuple[str, ...] | None = None,
        validation_executor: object = None,
    ) -> optimizer_service.ValidatedOptimizerCandidate:
        del validation_executor
        selected_lots = set(sell_lot_ids or ())
        if not selected_lots:
            return no_trade_outcome
        if selected_lots == {"msft-loss-lot"}:
            return narrowed_outcome
        assert selected_lots == {"loss-lot", "msft-loss-lot"}
        return full_outcome

    monkeypatch.setattr(optimizer_service, "prepare_optimizer_run", prepared_again)
    monkeypatch.setattr(optimizer_service, "assert_optimizer_run_current", current_again)
    monkeypatch.setattr(optimizer_service, "run_validated_candidate", solve_subset)

    def assert_readback(
        *,
        core_group_id: str,
        selected: bool,
        rejected: bool = False,
        expected_tickers: set[str],
        expected_lots: set[str],
        expected_note: str | None = None,
    ) -> str:
        with session_factory() as session:
            run = session.get(OptimizerRun, run_id)
            assert run is not None
            result = optimizer_service.real_run_recommendations(session, run)
            summary = optimizer_service.real_run_summary(run, session)
            groups = result["groups"]
            legs = result["consolidated_legs"]
            assert isinstance(groups, list)
            assert len(groups) == 1
            assert isinstance(legs, list)
            group = groups[0]
            assert isinstance(group, dict)
            assert group["selected"] is selected
            assert group["rejected"] is rejected
            assert group["note"] == expected_note
            assert result["optimizer_metrics"]["selection_universe"].keys() == {core_group_id}
            assert set(result["optimizer_metrics"]["selection_universe"][core_group_id]) == {
                "loss-lot",
                "msft-loss-lot",
            }
            assert len(result["optimizer_metrics"]["trade_group_priorities"]) == (
                1 if expected_tickers else 0
            )
            assert (
                summary["optimizer_metrics"]["selection_universe"]
                == result["optimizer_metrics"]["selection_universe"]
            )
            assert {leg["ticker"] for leg in legs} == expected_tickers
            assert all(leg["group_ids"] == [group["group_id"]] for leg in legs)
            assert {
                lot["broker_lot_id"] for leg in legs for lot in leg["selected_lots"]
            } == expected_lots
            if "NEWETF" in expected_tickers:
                buy = next(leg for leg in legs if leg["side"] == "BUY")
                sells = {leg["leg_id"] for leg in legs if leg["side"] == "SELL"}
                assert set(buy["dependencies"]) == sells
                assert set(group["dependencies"]) == sells
                sell_legs = [leg for leg in legs if leg["side"] == "SELL"]
                expected_buy_shares = Decimal(1 if "AAPL" not in expected_tickers else 2)
                buy_notional = Decimal(buy["estimated_notional_usd"])
                sell_proceeds = sum(
                    (Decimal(leg["estimated_notional_usd"]) for leg in sell_legs), Decimal(0)
                )
                assert Decimal(buy["shares"]) == expected_buy_shares
                assert buy_notional == sell_proceeds
                assert all(
                    Decimal(leg["shares"])
                    == sum((Decimal(lot["shares"]) for lot in leg["selected_lots"]), Decimal(0))
                    for leg in sell_legs
                )
                impact = group["impact"]
                assert isinstance(impact, dict)
                assert Decimal(impact["sell_proceeds_usd"]) == sell_proceeds
                assert Decimal(impact["replacement_buy_cost_usd"]) == buy_notional
            return str(group["group_id"])

    # Initial production publication must merge the ticker-level lot intent aliases.
    initial_group_id = assert_readback(
        core_group_id=canonical_core_id,
        selected=True,
        expected_tickers={"AAPL", "MSFT", "NEWETF"},
        expected_lots={"loss-lot", "msft-loss-lot"},
    )

    with session_factory() as session:
        await optimizer_service.annotate_real_group(
            session,
            run_id,
            initial_group_id,
            RecommendationAnnotationInput(note="reviewed coherent opportunity"),
            object(),
            None,
            correlation_id="coherent-note",
        )
    assert assert_readback(
        core_group_id=canonical_core_id,
        selected=True,
        expected_tickers={"AAPL", "MSFT", "NEWETF"},
        expected_lots={"loss-lot", "msft-loss-lot"},
        expected_note="reviewed coherent opportunity",
    ) == initial_group_id

    with session_factory() as session:
        await optimizer_service.apply_real_lot_review_intent(
            session,
            run_id,
            OptimizerLotReviewIntentInput(
                source_generation=inputs.source_generation,
                broker_lot_ids=["msft-loss-lot"],
            ),
            object(),
            None,
            correlation_id="narrow-to-msft",
        )
    narrowed_group_id = assert_readback(
        core_group_id="sale:MSFT",
        selected=True,
        expected_tickers={"MSFT", "NEWETF"},
        expected_lots={"msft-loss-lot"},
        expected_note="reviewed coherent opportunity",
    )
    assert narrowed_group_id == initial_group_id

    with session_factory() as session:
        await optimizer_service.apply_real_selection(
            session,
            run_id,
            OptimizerSelectionInput(selected_group_ids=[]),
            object(),
            None,
            correlation_id="deselect-coherent-group",
        )
    assert assert_readback(
        core_group_id="sale:MSFT",
        selected=False,
        expected_tickers=set(),
        expected_lots=set(),
        expected_note="reviewed coherent opportunity",
    ) == initial_group_id

    with session_factory() as session:
        await optimizer_service.apply_real_selection(
            session,
            run_id,
            OptimizerSelectionInput(selected_group_ids=[initial_group_id]),
            object(),
            None,
            correlation_id="reselect-and-restore-omitted-lots",
        )
    assert assert_readback(
        core_group_id=canonical_core_id,
        selected=True,
        expected_tickers={"AAPL", "MSFT", "NEWETF"},
        expected_lots={"loss-lot", "msft-loss-lot"},
        expected_note="reviewed coherent opportunity",
    ) == initial_group_id

    with session_factory() as session:
        await optimizer_service.annotate_real_group(
            session,
            run_id,
            initial_group_id,
            RecommendationAnnotationInput(rejected=True, rejection_reason="reviewed"),
            object(),
            None,
            correlation_id="reject-coherent-group",
        )
    assert assert_readback(
        core_group_id=canonical_core_id,
        selected=False,
        rejected=True,
        expected_tickers=set(),
        expected_lots=set(),
        expected_note="reviewed coherent opportunity",
    ) == initial_group_id

    with session_factory() as session:
        await optimizer_service.annotate_real_group(
            session,
            run_id,
            initial_group_id,
            RecommendationAnnotationInput(rejected=False),
            object(),
            None,
            correlation_id="restore-rejected-group",
        )
    assert assert_readback(
        core_group_id=canonical_core_id,
        selected=False,
        rejected=False,
        expected_tickers=set(),
        expected_lots=set(),
        expected_note="reviewed coherent opportunity",
    ) == initial_group_id

    with session_factory() as session:
        await optimizer_service.apply_real_lot_review_intent(
            session,
            run_id,
            OptimizerLotReviewIntentInput(
                source_generation=inputs.source_generation,
                broker_lot_ids=["loss-lot", "msft-loss-lot"],
            ),
            object(),
            None,
            correlation_id="restore-all-coherent-lots",
        )
    assert assert_readback(
        core_group_id=canonical_core_id,
        selected=True,
        expected_tickers={"AAPL", "MSFT", "NEWETF"},
        expected_lots={"loss-lot", "msft-loss-lot"},
        expected_note="reviewed coherent opportunity",
    ) == initial_group_id
    engine.dispose()


@pytest.mark.asyncio
async def test_real_writer_fails_closed_when_rejected_disjoint_lot_alias_owns_active_sell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs, baseline, screen, original_legs = _shared_funding_case()
    inputs, baseline, screen, _extra_lot = _inputs_with_disjoint_aapl_lot(inputs, screen)
    canonical_legs = _cohere_trade_group_legs(original_legs)
    no_trade_outcome = _service_outcome(inputs, (), core_group_id=None, status="no_trade")

    msft_sell = next(leg for leg in canonical_legs if leg.side == "SELL" and leg.ticker == "MSFT")
    aapl_sell = next(leg for leg in canonical_legs if leg.side == "SELL" and leg.ticker == "AAPL")
    shared_buy = next(leg for leg in canonical_legs if leg.side == "BUY")
    msft_only_legs = (
        replace(msft_sell, sequence=1, group_ids=("sale:MSFT",)),
        replace(
            shared_buy,
            shares=Decimal(1),
            sequence=2,
            depends_on_leg_ids=(msft_sell.leg_id,),
            group_ids=("sale:MSFT",),
        ),
    )
    msft_only_outcome, _ = _outcome_with_real_priorities(
        inputs, baseline, screen, msft_only_legs
    )
    extra_sell = replace(
        aapl_sell,
        leg_id="sell:AAPL-extra",
        shares=Decimal(1),
        selected_lots=(replace(aapl_sell.selected_lots[0], broker_lot_id="aapl-extra-lot"),),
        sequence=1,
        group_ids=("sale:AAPL",),
    )
    extra_buy = replace(
        shared_buy,
        shares=Decimal(1),
        sequence=2,
        depends_on_leg_ids=(extra_sell.leg_id,),
        group_ids=("sale:AAPL",),
    )
    extra_outcome, _ = _outcome_with_real_priorities(
        inputs, baseline, screen, (extra_sell, extra_buy)
    )
    split_legs = (
        replace(aapl_sell, sequence=1, group_ids=("sale:AAPL",)),
        replace(msft_sell, sequence=2, group_ids=("sale:MSFT",)),
    )
    split_outcome, split_priorities = _outcome_with_real_priorities(
        inputs, baseline, screen, split_legs
    )
    assert [row.group_id for row in split_priorities] == ["sale:AAPL", "sale:MSFT"]

    engine, session_factory, prepared, run_id = _seed_real_writer_run(
        tmp_path,
        inputs,
        msft_only_outcome,
        expected_universe={
            "sale:MSFT": ["loss-lot", "msft-loss-lot"],
        },
    )
    _patch_real_review_solver(
        monkeypatch,
        prepared,
        {
            frozenset(): no_trade_outcome,
            frozenset({"msft-loss-lot"}): msft_only_outcome,
            frozenset({"aapl-extra-lot"}): extra_outcome,
            frozenset({"loss-lot", "msft-loss-lot"}): split_outcome,
        },
    )
    with session_factory() as session:
        run = session.get(OptimizerRun, run_id)
        assert run is not None
        initial = optimizer_service.real_run_recommendations(session, run)
        initial_groups = initial["groups"]
        assert isinstance(initial_groups, list)
        assert len(initial_groups) == 1
        original_public_id = initial_groups[0]["group_id"]

    with session_factory() as session:
        await optimizer_service.annotate_real_group(
            session,
            run_id,
            str(original_public_id),
            RecommendationAnnotationInput(note="original selected opportunity"),
            object(),
            None,
            correlation_id="owner-note",
        )
    with session_factory() as session:
        await optimizer_service.apply_real_lot_review_intent(
            session,
            run_id,
            OptimizerLotReviewIntentInput(
                source_generation=inputs.source_generation,
                broker_lot_ids=["aapl-extra-lot"],
            ),
            object(),
            None,
            correlation_id="create-disjoint-aapl-opportunity",
        )

    with session_factory() as session:
        groups = session.scalars(
            select(RecommendationGroup).where(RecommendationGroup.run_id == run_id)
        ).all()
        disjoint_group = next(
            group
            for group in groups
            if isinstance(group.impact, dict)
            and group.impact.get("core_group_id") == "sale:AAPL"
        )
        disjoint_public_id = disjoint_group.id
        assert disjoint_group.selected is True
        assert disjoint_group.rejected is False
    with session_factory() as session:
        await optimizer_service.annotate_real_group(
            session,
            run_id,
            disjoint_public_id,
            RecommendationAnnotationInput(rejected=True, rejection_reason="extra lot excluded"),
            object(),
            None,
            correlation_id="reject-disjoint-aapl-opportunity",
        )
    with session_factory() as session:
        run = session.get(OptimizerRun, run_id)
        assert run is not None
        before = optimizer_service.real_run_recommendations(session, run)
        assert before["consolidated_legs"] == []
        assert run.metrics["basket_revision"] > 0

    with pytest.raises(AppError) as ownership_error, session_factory() as session:
        await optimizer_service.apply_real_selection(
            session,
            run_id,
            OptimizerSelectionInput(
                selected_group_ids=[str(original_public_id)],
                selected_sell_lots={
                    str(original_public_id): ["loss-lot", "msft-loss-lot"]
                },
            ),
            object(),
            None,
            correlation_id="restore-original-lots-as-independent-sales",
        )
    ownership_conflict = True
    assert ownership_error.value.code == "optimizer_review_ownership_conflict"

    with session_factory() as session:
        run = session.get(OptimizerRun, run_id)
        assert run is not None
        result = optimizer_service.real_run_recommendations(session, run)
        groups = {group["group_id"]: group for group in result["groups"]}
        legs = result["consolidated_legs"]
        assert isinstance(legs, list)
        group_by_id = groups
        for leg in legs:
            if leg["side"] == "SELL":
                owners = [group_by_id[group_id] for group_id in leg["group_ids"]]
                assert all(owner["selected"] and not owner["rejected"] for owner in owners)
        assert any(
            group["group_id"] == disjoint_public_id and group["rejected"]
            for group in groups.values()
        )
        if ownership_conflict:
            assert legs == []
            assert run.metrics["basket_revision"] == before["optimizer_metrics"]["basket_revision"]
    engine.dispose()


@pytest.mark.parametrize(
    ("aapl_shares", "msft_shares", "expected_first_group"),
    [(1, 2, "sale:MSFT"), (2, 1, "sale:AAPL")],
)
@pytest.mark.asyncio
async def test_real_writer_reserves_inherited_group_id_before_split_fallbacks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    aapl_shares: int,
    msft_shares: int,
    expected_first_group: str,
) -> None:
    inputs, baseline, screen, original_legs = _shared_funding_case()
    canonical_legs = _cohere_trade_group_legs(original_legs)
    full_outcome, full_priorities = _outcome_with_real_priorities(
        inputs, baseline, screen, canonical_legs
    )
    assert len(full_priorities) == 1
    assert full_priorities[0].group_id == "sale:AAPL"
    no_trade_outcome = _service_outcome(inputs, (), core_group_id=None, status="no_trade")
    msft_sell = next(leg for leg in canonical_legs if leg.side == "SELL" and leg.ticker == "MSFT")
    shared_buy = next(leg for leg in canonical_legs if leg.side == "BUY")
    msft_only_legs = (
        replace(msft_sell, sequence=1, group_ids=("sale:MSFT",)),
        replace(
            shared_buy,
            shares=Decimal(1),
            sequence=2,
            depends_on_leg_ids=(msft_sell.leg_id,),
            group_ids=("sale:MSFT",),
        ),
    )
    msft_only_outcome, _ = _outcome_with_real_priorities(
        inputs, baseline, screen, msft_only_legs
    )
    aapl_sell = next(leg for leg in canonical_legs if leg.side == "SELL" and leg.ticker == "AAPL")
    split_legs = (
        replace(
            aapl_sell,
            shares=Decimal(aapl_shares),
            selected_lots=(replace(aapl_sell.selected_lots[0], shares=Decimal(aapl_shares)),),
            sequence=1,
            group_ids=("sale:AAPL",),
        ),
        replace(
            msft_sell,
            shares=Decimal(msft_shares),
            selected_lots=(replace(msft_sell.selected_lots[0], shares=Decimal(msft_shares)),),
            sequence=2,
            group_ids=("sale:MSFT",),
        ),
    )
    split_outcome, split_priorities = _outcome_with_real_priorities(
        inputs, baseline, screen, split_legs
    )
    assert split_priorities[0].group_id == expected_first_group
    engine, session_factory, prepared, run_id = _seed_real_writer_run(
        tmp_path,
        inputs,
        full_outcome,
        expected_universe={
            "sale:AAPL": ["loss-lot"],
            "sale:MSFT": ["msft-loss-lot"],
        },
    )
    _patch_real_review_solver(
        monkeypatch,
        prepared,
        {
            frozenset(): no_trade_outcome,
            frozenset({"msft-loss-lot"}): msft_only_outcome,
            frozenset({"loss-lot", "msft-loss-lot"}): split_outcome,
        },
    )
    with session_factory() as session:
        run = session.get(OptimizerRun, run_id)
        assert run is not None
        initial = optimizer_service.real_run_recommendations(session, run)
        initial_groups = initial["groups"]
        assert isinstance(initial_groups, list)
        assert len(initial_groups) == 1
        inherited_public_id = initial_groups[0]["group_id"]
    with session_factory() as session:
        await optimizer_service.apply_real_lot_review_intent(
            session,
            run_id,
            OptimizerLotReviewIntentInput(
                source_generation=inputs.source_generation,
                broker_lot_ids=["msft-loss-lot"],
            ),
            object(),
            None,
            correlation_id="recanonicalize-to-msft",
        )
    with session_factory() as session:
        run = session.get(OptimizerRun, run_id)
        assert run is not None
        narrowed = optimizer_service.real_run_recommendations(session, run)
        narrowed_groups = narrowed["groups"]
        assert isinstance(narrowed_groups, list)
        assert len(narrowed_groups) == 1
        assert narrowed_groups[0]["group_id"] == inherited_public_id
    with session_factory() as session:
        await optimizer_service.apply_real_lot_review_intent(
            session,
            run_id,
            OptimizerLotReviewIntentInput(
                source_generation=inputs.source_generation,
                broker_lot_ids=["loss-lot", "msft-loss-lot"],
            ),
            object(),
            None,
            correlation_id="restore-independent-sale-components",
        )
    with session_factory() as session:
        groups = session.scalars(
            select(RecommendationGroup).where(RecommendationGroup.run_id == run_id)
        ).all()
        by_core = {
            group.impact["core_group_id"]: group
            for group in groups
            if isinstance(group.impact, dict)
        }
        assert by_core["sale:MSFT"].id == inherited_public_id
        assert by_core["sale:AAPL"].id != inherited_public_id
        assert len({group.id for group in groups}) == len(groups)
        run = session.get(OptimizerRun, run_id)
        assert run is not None
        readback = optimizer_service.real_run_recommendations(session, run)
        readback_groups = {group["group_id"]: group for group in readback["groups"]}
        assert readback_groups[inherited_public_id]["note"] is None
    engine.dispose()
