from __future__ import annotations

import time
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    Account,
    Base,
    OptimizerRun,
    PolicyRevision,
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
from tests.test_optimizer_core import _shared_funding_case


def _service_outcome(
    inputs: object,
    legs: tuple[object, ...],
    *,
    core_group_id: str | None,
    status: str = "ready",
) -> optimizer_service.ValidatedOptimizerCandidate:
    priority_rows = (
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
