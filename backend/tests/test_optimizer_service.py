from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    Account,
    Base,
    OptimizerRun,
    PolicyRevision,
    RecommendationGroup,
    RecommendationLeg,
    Security,
)
from app.db.session import create_database_engine
from app.domain.financial_inputs import PolicySettings
from app.optimizer.runtime import WorkerResult, WorkerTimeoutError
from app.schemas import RecommendationAnnotationInput
from app.services import optimizer_service
from app.services.errors import AppError


@dataclass(frozen=True)
class Request:
    inputs: object
    sell_lot_ids: tuple[str, ...] | None

@dataclass(frozen=True)
class Metadata:
    input_generation: int = 1
    source_checksum: str = "checksum"

@dataclass(frozen=True)
class Candidate:
    legs: tuple[object, ...]
    status: str = "ready"
    metadata: Metadata = Metadata()


@dataclass(frozen=True)
class Validation:
    accepted: bool
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class Policy:
    settings: PolicySettings


@dataclass(frozen=True)
class Inputs:
    policy: Policy
    source_generation: int = 1
    source_checksum: str = "checksum"

class FakeSupervisor:
    def __init__(self, value: object, *, deadline: float | None = None) -> None:
        self.value = value
        self.deadline = deadline
        self.request: object | None = None

    async def run(self, request: object, worker: Callable[..., object]) -> WorkerResult[object]:
        self.request = request
        deadline = self.deadline if self.deadline is not None else time.monotonic() + 2
        value = worker(request, deadline - 1)
        assert value is self.value
        return WorkerResult(value, deadline - 1, deadline)


def _batch_inputs() -> Inputs:
    return Inputs(
        Policy(
            PolicySettings.from_mapping(
                {
                    "max_sell_tickers_per_batch": 5,
                    "max_sell_lots_per_batch": 8,
                    "max_total_orders_per_batch": 6,
                    "max_batch_turnover_pct": "5.0",
                    "min_buy_order_notional_usd": "500.00",
                    "cash_reserve_usd": "25.00",
                }
            )
        )
    )


def test_batch_overrides_are_immutable_tightenings() -> None:
    inputs = _batch_inputs()
    request = type("RunInput", (), {"max_sell_tickers_per_batch": 3, "max_sell_lots_per_batch": None, "max_total_orders_per_batch": 4})()

    limited, settings = optimizer_service.apply_run_batch_limits(inputs, request)

    assert settings["max_sell_tickers_per_batch"] == 3
    assert settings["max_sell_lots_per_batch"] == 8
    assert settings["max_total_orders_per_batch"] == 4
    assert limited.policy.settings.get("max_sell_tickers_per_batch") == 3
    assert inputs.policy.settings.get("max_sell_tickers_per_batch") == 5
    assert settings["cash_reserve_usd"] == "25.00"


def test_batch_override_cannot_widen_active_policy() -> None:
    inputs = _batch_inputs()
    request = type("RunInput", (), {"max_sell_tickers_per_batch": 6})()

    with pytest.raises(AppError, match="tighten but cannot widen") as error:
        optimizer_service.apply_run_batch_limits(inputs, request)

    assert error.value.code == "batch_override_exceeds_policy"


@pytest.mark.asyncio
async def test_run_validated_candidate_passes_explicit_lot_subset_to_core(monkeypatch: pytest.MonkeyPatch) -> None:
    candidate = Candidate((object(),))
    supervisor = FakeSupervisor(candidate)
    seen: dict[str, object] = {}

    def worker(request: Request, deadline: float) -> Candidate:
        assert deadline > time.monotonic()
        return candidate

    def validator(inputs: object, legs: tuple[object, ...], *, deadline: float) -> Validation:
        seen.update(inputs=inputs, legs=legs, deadline=deadline)
        return Validation(True)

    monkeypatch.setattr(
        optimizer_service,
        "_core_contract",
        lambda: (Request, worker, validator),
    )
    inputs = _batch_inputs()
    lots = ("LOT-1", "LOT-2")

    result = await optimizer_service.run_validated_candidate(inputs, supervisor, sell_lot_ids=lots)  # type: ignore[arg-type]

    assert isinstance(supervisor.request, Request)
    assert supervisor.request.inputs is inputs
    assert supervisor.request.sell_lot_ids == lots
    assert result.candidate is candidate
    assert result.validation.accepted is True
    assert seen["legs"] == candidate.legs


@pytest.mark.asyncio
async def test_run_validated_candidate_does_not_publish_rejected_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    candidate = Candidate((), status="no_trade")
    inputs = _batch_inputs()
    supervisor = FakeSupervisor(candidate)

    monkeypatch.setattr(
        optimizer_service,
        "_core_contract",
        lambda: (Request, lambda request, deadline: candidate, lambda *args, **kwargs: Validation(False, ("cash_shortfall",))),
    )

    with pytest.raises(AppError) as error:
        await optimizer_service.run_validated_candidate(inputs, supervisor)  # type: ignore[arg-type]

    assert error.value.code == "optimizer_candidate_rejected"
    assert error.value.details == {"reasons": ["cash_shortfall"], "basket_unchanged": True}


@pytest.mark.asyncio
async def test_run_validated_candidate_rejects_late_owner_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    candidate = Candidate((), status="no_trade")
    inputs = _batch_inputs()
    supervisor = FakeSupervisor(candidate, deadline=time.monotonic() - 1)
    monkeypatch.setattr(
        optimizer_service,
        "_core_contract",
        lambda: (Request, lambda request, deadline: candidate, lambda *args, **kwargs: Validation(True)),
    )

    with pytest.raises(WorkerTimeoutError):
        await optimizer_service.run_validated_candidate(inputs, supervisor)  # type: ignore[arg-type]


_RUN_ID = "service-run"
_GROUP_ID = "service-group"
_POLICY_ID = "service-policy"


@dataclass(frozen=True)
class PublicationCandidate:
    marker: str


def _create_sqlite_optimizer_run(
    tmp_path: Path, *, selected: bool
) -> tuple[Engine, Callable[[], Session]]:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'optimizer-service.db'}")
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    with session_factory.begin() as session:
        session.add(
            PolicyRevision(
                id=_POLICY_ID,
                revision_number=1,
                status="ACTIVE",
                created_at=now,
            )
        )
        session.flush()
        session.add(
            Account(
                id=1,
                broker_account_id_key="fake-account",
                display_name="Test account",
                cash_usd=Decimal(0),
                settled_buying_power_usd=Decimal(0),
                as_of=now,
            )
        )
        session.add(Security(id=1, ticker="ABC", asset_type="EQUITY"))
        session.flush()
        session.add(
            OptimizerRun(
                id=_RUN_ID,
                policy_revision_id=_POLICY_ID,
                source_generation=1,
                as_of=now,
                proposed_trade_date=date(2026, 11, 13),
                solver_version="test",
                status="COMPLETE",
                batch_settings={
                    "max_sell_tickers_per_batch": 1,
                    "max_sell_lots_per_batch": 1,
                    "max_total_orders_per_batch": 1,
                },
                metrics={"basket_revision": 0, "basket_marker": "initial"},
                warnings=[],
                input_fingerprint="service-fingerprint",
                frozen_input_bundle={"mode": "real_optimizer"},
            )
        )
        session.flush()
        session.add(
            RecommendationGroup(
                id=_GROUP_ID,
                run_id=_RUN_ID,
                rank=1,
                group_type="optimizer_trade",
                rationale="Test trade group",
                impact={"core_group_id": "sale:ABC", "candidate_sell_lot_ids": ["LOT-1"]},
                dependencies=[],
                selected=selected,
                rejected=False,
                note="initial note",
            )
        )
    return engine, session_factory


def _patch_real_run_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    prepared = optimizer_service.PreparedOptimizerRun(
        inputs=object(),
        batch_settings={
            "max_sell_tickers_per_batch": 1,
            "max_sell_lots_per_batch": 1,
            "max_total_orders_per_batch": 1,
        },
        frozen_input_bundle={"mode": "real_optimizer"},
        input_fingerprint="service-fingerprint",
        policy_revision_id=_POLICY_ID,
        source_generation=1,
        as_of=datetime(2026, 11, 13, tzinfo=UTC),
        proposed_trade_date=date(2026, 11, 13),
    )

    def prepare(
        _session: Session,
        _request: object,
        *,
        proposed_trade_date: date | None = None,
        batch_limits: object | None = None,
    ) -> optimizer_service.PreparedOptimizerRun:
        del proposed_trade_date, batch_limits
        return prepared

    def assert_current(
        _session: Session,
        _prepared: optimizer_service.PreparedOptimizerRun,
        *,
        deadline: float | None = None,
    ) -> None:
        del deadline

    monkeypatch.setattr(optimizer_service, "prepare_optimizer_run", prepare)
    monkeypatch.setattr(optimizer_service, "assert_optimizer_run_current", assert_current)


def _capture_real_run_state(session: Session) -> optimizer_service._RunState:
    with session.begin():
        _run, state, _annotations = optimizer_service._run_state(session, _RUN_ID)
    return state


def _persist_test_candidate(
    session: Session,
    run: OptimizerRun,
    _prepared: optimizer_service.PreparedOptimizerRun,
    outcome: optimizer_service.ValidatedOptimizerCandidate,
    *,
    selected_groups: object = None,
    annotation_overrides: object = None,
    expected_universe: object = None,
) -> None:
    del selected_groups, annotation_overrides, expected_universe
    marker = cast(PublicationCandidate, outcome.candidate).marker
    metrics = dict(run.metrics)
    metrics["basket_revision"] = int(metrics["basket_revision"]) + 1
    metrics["basket_marker"] = marker
    run.metrics = metrics
    session.add(
        RecommendationLeg(
            id=f"service-leg-{marker}",
            group_id=_GROUP_ID,
            account_id=1,
            security_id=1,
            side="SELL",
            shares=Decimal(1),
            estimated_unit_price_usd=Decimal(10),
            net_st_realized_usd=Decimal(0),
            net_lt_realized_usd=Decimal(0),
            sequence=1,
            details={"test_marker": marker},
        )
    )


def _get_run_rows(
    session_factory: Callable[[], Session],
) -> tuple[OptimizerRun, RecommendationGroup, int]:
    with session_factory() as session:
        run = session.scalar(select(OptimizerRun).where(OptimizerRun.id == _RUN_ID))
        group = session.scalar(
            select(RecommendationGroup).where(RecommendationGroup.id == _GROUP_ID)
        )
        leg_count = len(session.scalars(select(RecommendationLeg.id)).all())
        assert run is not None
        assert group is not None
        return run, group, leg_count


@pytest.mark.asyncio
async def test_concurrent_subset_publication_cannot_overwrite_newer_basket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, session_factory = _create_sqlite_optimizer_run(tmp_path, selected=True)
    _patch_real_run_dependencies(monkeypatch)
    monkeypatch.setattr(optimizer_service, "_persist_candidate", _persist_test_candidate)
    both_solves_started = asyncio.Barrier(2)
    release_older = asyncio.Event()

    async def fake_solve(
        _inputs: object,
        _supervisor: optimizer_service.ProcessSupervisor,
        *,
        sell_lot_ids: tuple[str, ...] | None = None,
        validation_executor: optimizer_service.BoundedValidationExecutor | None = None,
    ) -> optimizer_service.ValidatedOptimizerCandidate:
        del validation_executor
        assert sell_lot_ids is not None
        marker = "newer" if sell_lot_ids == ("LOT-NEWER",) else "older"
        await both_solves_started.wait()
        if marker == "older":
            await release_older.wait()
        return optimizer_service.ValidatedOptimizerCandidate(
            PublicationCandidate(marker), None, time.monotonic() + 60, "ready"
        )

    monkeypatch.setattr(optimizer_service, "run_validated_candidate", fake_solve)
    older_session = session_factory()
    newer_session = session_factory()
    supervisor = optimizer_service.ProcessSupervisor()
    validation_executor = optimizer_service.BoundedValidationExecutor()
    try:
        older_state = _capture_real_run_state(older_session)
        newer_state = _capture_real_run_state(newer_session)
        older_task = asyncio.create_task(
            optimizer_service._recompute_real_basket(
                older_session,
                _RUN_ID,
                older_state,
                ("LOT-OLDER",),
                {"sale:ABC": True},
                supervisor,
                validation_executor,
                correlation_id="older-request",
                event_type="test_publication",
                event_details={},
            )
        )
        newer_task = asyncio.create_task(
            optimizer_service._recompute_real_basket(
                newer_session,
                _RUN_ID,
                newer_state,
                ("LOT-NEWER",),
                {"sale:ABC": True},
                supervisor,
                validation_executor,
                correlation_id="newer-request",
                event_type="test_publication",
                event_details={},
            )
        )
        await newer_task
        release_older.set()
        with pytest.raises(AppError) as error:
            await older_task

        assert error.value.code == "stale_optimizer_basket"
        assert error.value.details == {"basket_unchanged": True}
        run, group, leg_count = _get_run_rows(session_factory)
        assert run.metrics["basket_revision"] == 1
        assert run.metrics["basket_marker"] == "newer"
        assert group.note == "initial note"
        assert leg_count == 1
    finally:
        release_older.set()
        await validation_executor.aclose()
        older_session.close()
        newer_session.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_inflight_solve_is_invalidated_by_non_solving_rejection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, session_factory = _create_sqlite_optimizer_run(tmp_path, selected=False)
    _patch_real_run_dependencies(monkeypatch)
    monkeypatch.setattr(optimizer_service, "_persist_candidate", _persist_test_candidate)
    solve_started = asyncio.Event()
    release_solve = asyncio.Event()

    async def fake_solve(
        _inputs: object,
        _supervisor: optimizer_service.ProcessSupervisor,
        *,
        sell_lot_ids: tuple[str, ...] | None = None,
        validation_executor: optimizer_service.BoundedValidationExecutor | None = None,
    ) -> optimizer_service.ValidatedOptimizerCandidate:
        del sell_lot_ids, validation_executor
        solve_started.set()
        await release_solve.wait()
        return optimizer_service.ValidatedOptimizerCandidate(
            PublicationCandidate("stale-solve"), None, time.monotonic() + 60, "ready"
        )

    monkeypatch.setattr(optimizer_service, "run_validated_candidate", fake_solve)
    solve_session = session_factory()
    annotation_session = session_factory()
    solve_supervisor = optimizer_service.ProcessSupervisor()
    validation_executor = optimizer_service.BoundedValidationExecutor()
    try:
        captured_state = _capture_real_run_state(solve_session)
        solve_task = asyncio.create_task(
            optimizer_service._recompute_real_basket(
                solve_session,
                _RUN_ID,
                captured_state,
                ("LOT-1",),
                {"sale:ABC": False},
                solve_supervisor,
                validation_executor,
                correlation_id="inflight-solve",
                event_type="test_publication",
                event_details={},
            )
        )
        await solve_started.wait()
        with annotation_session:
            await optimizer_service.annotate_real_group(
                annotation_session,
                _RUN_ID,
                _GROUP_ID,
                RecommendationAnnotationInput(rejected=True, rejection_reason="reviewed"),
                solve_supervisor,
                validation_executor,
                correlation_id="rejection-update",
            )
        release_solve.set()
        with pytest.raises(AppError) as error:
            await solve_task

        assert error.value.code == "stale_optimizer_basket"
        run, group, leg_count = _get_run_rows(session_factory)
        assert run.metrics["basket_revision"] == 1
        assert run.metrics["basket_marker"] == "initial"
        assert group.rejected is True
        assert group.selected is False
        assert group.rejection_reason == "reviewed"
        assert leg_count == 0
    finally:
        release_solve.set()
        await validation_executor.aclose()
        solve_session.close()
        annotation_session.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_note_only_annotation_does_not_increment_basket_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, session_factory = _create_sqlite_optimizer_run(tmp_path, selected=False)
    _patch_real_run_dependencies(monkeypatch)
    session = session_factory()
    supervisor = optimizer_service.ProcessSupervisor()
    validation_executor = optimizer_service.BoundedValidationExecutor()
    try:
        with session:
            await optimizer_service.annotate_real_group(
                session,
                _RUN_ID,
                _GROUP_ID,
                RecommendationAnnotationInput(note="reviewed without changing eligibility"),
                supervisor,
                validation_executor,
                correlation_id="note-only",
            )
        run, group, leg_count = _get_run_rows(session_factory)
        assert run.metrics["basket_revision"] == 0
        assert group.note == "reviewed without changing eligibility"
        assert leg_count == 0
    finally:
        session.close()
        engine.dispose()
