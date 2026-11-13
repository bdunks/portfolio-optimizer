from __future__ import annotations

import asyncio
import multiprocessing
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from decimal import Decimal
from multiprocessing.synchronize import Event
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    Account,
    ActivityEvent,
    Base,
    OptimizerRun,
    PolicyRevision,
    RecommendationGroup,
    RecommendationGroupLeg,
    RecommendationLeg,
    RecommendationSelectedLot,
    Security,
)
from app.db.session import create_database_engine
from app.domain.financial_inputs import PolicySettings
from app.domain.portfolio_accounting import ConsolidatedLeg, LotAllocation
from app.optimizer.runtime import WorkerCapacityError, WorkerResult, WorkerTimeoutError
from app.optimizer.validation import CandidateValidation, validate_candidate
from app.schemas import (
    OptimizerLotReviewIntentInput,
    OptimizerSelectionInput,
    RecommendationAnnotationInput,
)
from app.services import optimizer_service
from app.services.errors import AppError
from tests.optimizer_benchmark_fixture import build_optimizer_benchmark_inputs


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


@dataclass(frozen=True)
class ServiceLot:
    ticker: str
    broker_lot_id: str
    available_shares: Decimal = Decimal(1)
    acquired_date: date = date(2025, 1, 1)
    adjusted_unit_basis_usd: Decimal = Decimal(10)


@dataclass(frozen=True)
class ServiceInputs:
    lots: tuple[ServiceLot, ...]

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

def _owner_validation_hang(started: Event, *, deadline: float) -> str:
    started.set()
    while True:
        time.sleep(0.01)


def _owner_validation_sleep(started: Event, seconds: float, value: str, *, deadline: float) -> str:
    started.set()
    time.sleep(seconds)
    return value


def _owner_validation_echo(value: str, *, deadline: float) -> str:
    return value


async def _wait_for_owner_validation(
    executor: optimizer_service.BoundedValidationExecutor, started: Event
) -> int:
    loop = asyncio.get_running_loop()
    wait_until = loop.time() + 8
    while not started.is_set():
        if loop.time() >= wait_until:
            raise AssertionError("owner validation child did not start")
        await asyncio.sleep(0.01)
    for handle in executor._supervisor._active.values():
        if handle.process.pid is not None:
            return handle.process.pid
    raise AssertionError("owner validation child exited before its pid was captured")


def _assert_process_reaped(pid: int) -> None:
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


@pytest.mark.asyncio
async def test_bounded_validation_executor_kills_timeout_reaps_and_releases_capacity() -> None:
    context = multiprocessing.get_context("spawn")
    started = context.Event()
    executor = optimizer_service.BoundedValidationExecutor(max_workers=1)
    pulse_stop = asyncio.Event()
    pulse_count = 0

    async def event_loop_pulse() -> None:
        nonlocal pulse_count
        while not pulse_stop.is_set():
            pulse_count += 1
            await asyncio.sleep(0.01)

    pulse_task = asyncio.create_task(event_loop_pulse())
    deadline = time.monotonic() + 1.5
    run_started = time.monotonic()
    validation_task = asyncio.create_task(
        executor.run(_owner_validation_hang, started, deadline=deadline)
    )
    try:
        child_pid = await _wait_for_owner_validation(executor, started)
        with pytest.raises(WorkerTimeoutError):
            await validation_task
        assert time.monotonic() - run_started < 2.5
        assert pulse_count > 20
        assert executor._supervisor.active_workers == 0
        _assert_process_reaped(child_pid)
        reclaimed = await executor.run(
            _owner_validation_echo, "capacity-reclaimed", deadline=time.monotonic() + 3
        )
        assert reclaimed == "capacity-reclaimed"
    finally:
        pulse_stop.set()
        await asyncio.gather(pulse_task, return_exceptions=True)
        if not validation_task.done():
            validation_task.cancel()
        await asyncio.gather(validation_task, return_exceptions=True)
        await executor.aclose()


@pytest.mark.asyncio
async def test_bounded_validation_executor_rejects_and_cleans_up_active_jobs() -> None:
    context = multiprocessing.get_context("spawn")
    executor = optimizer_service.BoundedValidationExecutor(max_workers=1)
    started = context.Event()
    running = asyncio.create_task(
        executor.run(_owner_validation_hang, started, deadline=time.monotonic() + 10)
    )
    child_pid = await _wait_for_owner_validation(executor, started)
    try:
        rejection_started = time.monotonic()
        with pytest.raises(WorkerCapacityError):
            await executor.run(
                _owner_validation_echo, "must-not-queue", deadline=time.monotonic() + 3
            )
        assert time.monotonic() - rejection_started < 0.2

        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running
        assert executor._supervisor.active_workers == 0
        _assert_process_reaped(child_pid)
        reclaimed = await executor.run(
            _owner_validation_echo, "cancel-released", deadline=time.monotonic() + 3
        )
        assert reclaimed == "cancel-released"

        closing_started = context.Event()
        closing = asyncio.create_task(
            executor.run(
                _owner_validation_hang,
                closing_started,
                deadline=time.monotonic() + 10,
            )
        )
        closing_pid = await _wait_for_owner_validation(executor, closing_started)
        await executor.aclose()
        closing_result = await asyncio.gather(closing, return_exceptions=True)
        assert isinstance(closing_result[0], BaseException)
        assert executor._supervisor.active_workers == 0
        _assert_process_reaped(closing_pid)
    finally:
        if not running.done():
            running.cancel()
        await asyncio.gather(running, return_exceptions=True)
        await executor.aclose()


@pytest.mark.asyncio
async def test_bounded_validation_executor_keeps_original_absolute_deadline() -> None:
    context = multiprocessing.get_context("spawn")
    started = context.Event()
    executor = optimizer_service.BoundedValidationExecutor(max_workers=1)
    deadline = time.monotonic() + 2.5
    await asyncio.sleep(1)
    run_started = time.monotonic()
    validation_task = asyncio.create_task(
        executor.run(
            _owner_validation_sleep,
            started,
            4,
            "too-late",
            deadline=deadline,
        )
    )
    try:
        child_pid = await _wait_for_owner_validation(executor, started)
        with pytest.raises(WorkerTimeoutError):
            await validation_task
        assert time.monotonic() - run_started < 2.2
        _assert_process_reaped(child_pid)
    finally:
        if not validation_task.done():
            validation_task.cancel()
        await asyncio.gather(validation_task, return_exceptions=True)
        await executor.aclose()


@pytest.mark.asyncio
async def test_bounded_validation_executor_returns_real_candidate_validation() -> None:
    inputs = build_optimizer_benchmark_inputs(seed=17)
    executor = optimizer_service.BoundedValidationExecutor(max_workers=1)
    try:
        validation = await executor.run(
            validate_candidate,
            inputs,
            (),
            deadline=time.monotonic() + 10,
        )
        assert isinstance(validation, CandidateValidation)
        assert validation.accepted
        assert validation.evaluation is not None
    finally:
        await executor.aclose()



_RUN_ID = "service-run"
_GROUP_ID = "service-group"
_POLICY_ID = "service-policy"
_SUBSET_RUN_ID = "subset-service-run"
_SUBSET_POLICY_ID = "subset-service-policy"
_GROUP_A_ID = "subset-group-a"
_GROUP_B_ID = "subset-group-b"


@dataclass(frozen=True)
class PublicationCandidate:
    marker: str
    legs: tuple[object, ...] = ()



def _sell_legs_for_ids(inputs: object, broker_lot_ids: tuple[str, ...]) -> tuple[ConsolidatedLeg, ...]:
    lots_by_id = {lot.broker_lot_id: lot for lot in getattr(inputs, "lots", ())}
    grouped: dict[str, list[str]] = {}
    for broker_lot_id in broker_lot_ids:
        assert broker_lot_id in lots_by_id
        grouped.setdefault(lots_by_id[broker_lot_id].ticker, []).append(broker_lot_id)
    legs = []
    for sequence, (ticker, lot_ids) in enumerate(sorted(grouped.items()), start=1):
        allocations = tuple(LotAllocation(lot_id, Decimal(1)) for lot_id in lot_ids)
        legs.append(
            ConsolidatedLeg(
                leg_id=f"sell-{ticker.lower()}-{sequence}",
                side="SELL",
                ticker=ticker,
                shares=Decimal(len(allocations)),
                estimated_unit_price_usd=Decimal(10),
                selected_lots=allocations,
                sequence=sequence,
                group_ids=(f"sale:{ticker.upper()}",),
            )
        )
    return tuple(legs)

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


def _create_sqlite_subset_optimizer_run(
    tmp_path: Path,
) -> tuple[Engine, Callable[[], Session]]:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'optimizer-subset-service.db'}")
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    initial_lots = {
        "sale:AAA": ("LOT-A1", "LOT-A2"),
        "sale:BBB": ("LOT-B1",),
    }
    with session_factory.begin() as session:
        session.add(
            PolicyRevision(
                id=_SUBSET_POLICY_ID,
                revision_number=1,
                status="ACTIVE",
                created_at=now,
            )
        )
        session.flush()
        session.add(
            Account(
                id=1,
                broker_account_id_key="subset-fake-account",
                display_name="Subset test account",
                cash_usd=Decimal(0),
                settled_buying_power_usd=Decimal(0),
                as_of=now,
            )
        )
        session.add_all(
            [
                Security(id=1, ticker="AAA", asset_type="EQUITY"),
                Security(id=2, ticker="BBB", asset_type="EQUITY"),
            ]
        )
        session.flush()
        session.add(
            OptimizerRun(
                id=_SUBSET_RUN_ID,
                policy_revision_id=_SUBSET_POLICY_ID,
                source_generation=1,
                as_of=now,
                proposed_trade_date=date(2026, 11, 13),
                solver_version="test",
                status="COMPLETE",
                batch_settings={
                    "max_sell_tickers_per_batch": 2,
                    "max_sell_lots_per_batch": 3,
                    "max_total_orders_per_batch": 3,
                },
                metrics={
                    "basket_revision": 4,
                    "basket_marker": "initial",
                    "selection_universe": {key: list(value) for key, value in initial_lots.items()},
                },
                warnings=[],
                input_fingerprint="service-fingerprint",
                frozen_input_bundle={"mode": "real_optimizer"},
            )
        )
        session.flush()
        for rank, (core_group_id, group_id, ticker, security_id) in enumerate(
            (
                ("sale:AAA", _GROUP_A_ID, "AAA", 1),
                ("sale:BBB", _GROUP_B_ID, "BBB", 2),
            ),
            start=1,
        ):
            session.add(
                RecommendationGroup(
                    id=group_id,
                    run_id=_SUBSET_RUN_ID,
                    rank=rank,
                    group_type="optimizer_trade",
                    rationale=f"Test sale for {ticker}",
                    impact={
                        "core_group_id": core_group_id,
                        "candidate_sell_lot_ids": list(initial_lots[core_group_id]),
                    },
                    dependencies=[],
                    selected=True,
                    rejected=False,
                )
            )
            leg_id = f"initial-leg-{ticker.lower()}"
            lot_ids = initial_lots[core_group_id]
            session.add(
                RecommendationLeg(
                    id=leg_id,
                    group_id=group_id,
                    account_id=1,
                    security_id=security_id,
                    side="SELL",
                    shares=Decimal(len(lot_ids)),
                    estimated_unit_price_usd=Decimal(10),
                    net_st_realized_usd=Decimal(0),
                    net_lt_realized_usd=Decimal(0),
                    sequence=rank,
                    details={"core_group_ids": [core_group_id]},
                )
            )
            session.flush()
            session.add(RecommendationGroupLeg(group_id=group_id, leg_id=leg_id))
            for lot_id in lot_ids:
                session.add(
                    RecommendationSelectedLot(
                        leg_id=leg_id,
                        broker_lot_id=lot_id,
                        shares=Decimal(1),
                        acquired_date=date(2025, 1, 1),
                        adjusted_basis_usd=Decimal(10),
                        st_lt_term="LT",
                        realized_pl_usd=Decimal(0),
                        selected=True,
                    )
                )
    return engine, session_factory


def _patch_real_run_dependencies(monkeypatch: pytest.MonkeyPatch, *, inputs: object | None = None) -> None:
    prepared_inputs = inputs if inputs is not None else ServiceInputs(
        (
            ServiceLot("ABC", "LOT-1"),
            ServiceLot("ABC", "LOT-OLDER"),
            ServiceLot("ABC", "LOT-NEWER"),
        )
    )
    prepared = optimizer_service.PreparedOptimizerRun(
        inputs=prepared_inputs,
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


def _capture_real_run_state(
    session: Session, run_id: str = _RUN_ID
) -> optimizer_service._RunState:
    with session.begin():
        _run, state, _annotations = optimizer_service._run_state(session, run_id)
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
    del selected_groups, expected_universe
    if isinstance(annotation_overrides, dict):
        group = session.scalar(
            select(RecommendationGroup)
            .where(RecommendationGroup.id == _GROUP_ID)
            .execution_options(populate_existing=True)
        )
        values = annotation_overrides.get("sale:ABC")
        note = values.get("note") if isinstance(values, dict) else None
        if group is not None and isinstance(note, str):
            group.note = note
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



def _persist_subset_candidate(
    session: Session,
    run: OptimizerRun,
    prepared: optimizer_service.PreparedOptimizerRun,
    outcome: optimizer_service.ValidatedOptimizerCandidate,
    *,
    selected_groups: object = None,
    annotation_overrides: object = None,
    expected_universe: object = None,
) -> None:
    metrics = dict(run.metrics)
    revision = int(metrics.get("basket_revision", 0)) + 1
    metrics["basket_revision"] = revision
    if isinstance(outcome.candidate, PublicationCandidate):
        metrics["basket_marker"] = outcome.candidate.marker
    universe = {
        str(core_id): list(lot_ids)
        for core_id, lot_ids in metrics.get("selection_universe", {}).items()
    }
    if isinstance(expected_universe, dict):
        for core_id, lot_ids in expected_universe.items():
            universe[core_id] = list(dict.fromkeys((*universe.get(core_id, ()), *lot_ids)))
    metrics["selection_universe"] = universe
    run.metrics = metrics

    groups = session.scalars(
        select(RecommendationGroup)
        .where(RecommendationGroup.run_id == run.id)
        .order_by(RecommendationGroup.rank)
        .execution_options(populate_existing=True)
    ).all()
    groups_by_core = {
        str(group.impact["core_group_id"]): group
        for group in groups
        if isinstance(group.impact, dict) and isinstance(group.impact.get("core_group_id"), str)
    }
    active_core_ids = {
        core_id for leg in outcome.candidate.legs for core_id in leg.group_ids
    }
    overrides = annotation_overrides if isinstance(annotation_overrides, dict) else {}
    for core_id, group in groups_by_core.items():
        impact = dict(group.impact)
        impact["candidate_sell_lot_ids"] = universe.get(core_id, [])
        group.impact = impact
        if isinstance(selected_groups, dict):
            group.selected = bool(selected_groups.get(core_id, core_id in active_core_ids))
        values = overrides.get(core_id)
        if isinstance(values, dict):
            for field in ("selected", "rejected", "note", "rejection_reason"):
                if field in values:
                    setattr(group, field, values[field])

    group_ids = [group.id for group in groups]
    leg_ids = session.scalars(
        select(RecommendationLeg.id).where(RecommendationLeg.group_id.in_(group_ids))
    ).all()
    if leg_ids:
        session.execute(delete(RecommendationSelectedLot).where(RecommendationSelectedLot.leg_id.in_(leg_ids)))
        session.execute(delete(RecommendationGroupLeg).where(RecommendationGroupLeg.leg_id.in_(leg_ids)))
        session.execute(delete(RecommendationLeg).where(RecommendationLeg.id.in_(leg_ids)))
    session.execute(delete(RecommendationGroupLeg).where(RecommendationGroupLeg.group_id.in_(group_ids)))

    lots_by_id = {lot.broker_lot_id: lot for lot in prepared.inputs.lots}
    for leg in outcome.candidate.legs:
        core_group_ids = list(leg.group_ids)
        primary_group = groups_by_core[core_group_ids[0]]
        security_id = session.scalar(select(Security.id).where(Security.ticker == leg.ticker.upper()))
        assert security_id is not None
        leg_id = f"subset-service-leg-{revision}-{leg.sequence}"
        session.add(
            RecommendationLeg(
                id=leg_id,
                group_id=primary_group.id,
                account_id=1,
                security_id=security_id,
                side=leg.side,
                shares=leg.shares,
                estimated_unit_price_usd=leg.estimated_unit_price_usd,
                net_st_realized_usd=Decimal(0),
                net_lt_realized_usd=Decimal(0),
                sequence=leg.sequence,
                details={"core_group_ids": core_group_ids},
            )
        )
        session.flush()
        for core_group_id in core_group_ids:
            session.add(RecommendationGroupLeg(group_id=groups_by_core[core_group_id].id, leg_id=leg_id))
        for allocation in leg.selected_lots:
            lot = lots_by_id[allocation.broker_lot_id]
            session.add(
                RecommendationSelectedLot(
                    leg_id=leg_id,
                    broker_lot_id=allocation.broker_lot_id,
                    shares=allocation.shares,
                    acquired_date=lot.acquired_date,
                    adjusted_basis_usd=lot.adjusted_unit_basis_usd,
                    st_lt_term="LT",
                    realized_pl_usd=Decimal(0),
                    selected=True,
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



def _subset_inputs() -> ServiceInputs:
    return ServiceInputs(
        (
            ServiceLot("AAA", "LOT-A1"),
            ServiceLot("AAA", "LOT-A2"),
            ServiceLot("BBB", "LOT-B1"),
        )
    )


def _subset_snapshot(session_factory: Callable[[], Session]) -> tuple[object, ...]:
    with session_factory() as session:
        run = session.scalar(select(OptimizerRun).where(OptimizerRun.id == _SUBSET_RUN_ID))
        assert run is not None
        groups = session.scalars(
            select(RecommendationGroup)
            .where(RecommendationGroup.run_id == _SUBSET_RUN_ID)
            .order_by(RecommendationGroup.rank)
        ).all()
        selected_lot_ids = tuple(
            session.scalars(
                select(RecommendationSelectedLot.broker_lot_id)
                .join(RecommendationLeg, RecommendationLeg.id == RecommendationSelectedLot.leg_id)
                .join(RecommendationGroupLeg, RecommendationGroupLeg.leg_id == RecommendationLeg.id)
                .join(RecommendationGroup, RecommendationGroup.id == RecommendationGroupLeg.group_id)
                .where(RecommendationGroup.run_id == _SUBSET_RUN_ID)
                .order_by(RecommendationSelectedLot.broker_lot_id)
            ).all()
        )
        legs = tuple(
            session.execute(
                select(RecommendationLeg.id, RecommendationLeg.side, RecommendationLeg.shares)
                .join(RecommendationGroup, RecommendationGroup.id == RecommendationLeg.group_id)
                .where(RecommendationGroup.run_id == _SUBSET_RUN_ID)
                .order_by(RecommendationLeg.id)
            ).all()
        )
        event_count = len(session.scalars(select(ActivityEvent.id)).all())
        return (
            int(run.metrics["basket_revision"]),
            tuple((group.id, group.selected, group.rejected) for group in groups),
            selected_lot_ids,
            legs,
            event_count,
        )

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
            PublicationCandidate(marker, _sell_legs_for_ids(_inputs, sell_lot_ids)), None, time.monotonic() + 60, "ready"
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
                annotation_overrides={"sale:ABC": {"note": "older stale annotation"}},
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
                annotation_overrides={"sale:ABC": {"note": "newer annotation"}},
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
        assert group.note == "newer annotation"
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
        del validation_executor
        assert sell_lot_ids is not None
        solve_started.set()
        await release_solve.wait()
        return optimizer_service.ValidatedOptimizerCandidate(
            PublicationCandidate("stale-solve", _sell_legs_for_ids(_inputs, sell_lot_ids)), None, time.monotonic() + 60, "ready"
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


@pytest.mark.asyncio
async def test_lot_intent_roundtrip_preserves_actual_selected_lots_and_rejected_groups(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = _subset_inputs()
    engine, session_factory = _create_sqlite_subset_optimizer_run(tmp_path)
    _patch_real_run_dependencies(monkeypatch, inputs=inputs)
    monkeypatch.setattr(optimizer_service, "_persist_candidate", _persist_subset_candidate)
    solve_lot_sets: list[tuple[str, ...]] = []

    async def fake_solve(
        _inputs: object,
        _supervisor: object,
        *,
        sell_lot_ids: tuple[str, ...] | None = None,
        validation_executor: object = None,
    ) -> optimizer_service.ValidatedOptimizerCandidate:
        del validation_executor
        assert sell_lot_ids is not None
        selected_lots = tuple(sell_lot_ids)
        solve_lot_sets.append(selected_lots)
        candidate = PublicationCandidate(
            f"solve-{len(solve_lot_sets)}", _sell_legs_for_ids(_inputs, selected_lots)
        )
        return optimizer_service.ValidatedOptimizerCandidate(
            candidate, Validation(True), time.monotonic() + 60, "ready"
        )

    monkeypatch.setattr(optimizer_service, "run_validated_candidate", fake_solve)
    supervisor = FakeSupervisor(None)
    initial_snapshot = _subset_snapshot(session_factory)
    assert initial_snapshot[2] == ("LOT-A1", "LOT-A2", "LOT-B1")

    with session_factory() as session:
        await optimizer_service.apply_real_lot_review_intent(
            session,
            _SUBSET_RUN_ID,
            OptimizerLotReviewIntentInput(source_generation=1, broker_lot_ids=["LOT-A1", "LOT-B1"]),
            supervisor,
            None,
            correlation_id="narrow-subset",
        )
    narrow_snapshot = _subset_snapshot(session_factory)
    assert solve_lot_sets == [("LOT-A1", "LOT-B1")]
    assert narrow_snapshot[0] == initial_snapshot[0] + 1
    assert narrow_snapshot[2] == ("LOT-A1", "LOT-B1")

    with session_factory() as session:
        await optimizer_service.annotate_real_group(
            session,
            _SUBSET_RUN_ID,
            _GROUP_B_ID,
            RecommendationAnnotationInput(rejected=True, rejection_reason="reviewed"),
            supervisor,
            None,
            correlation_id="reject-group-b",
        )
    rejected_snapshot = _subset_snapshot(session_factory)
    assert solve_lot_sets[-1] == ("LOT-A1",)
    assert rejected_snapshot[2] == ("LOT-A1",)
    assert rejected_snapshot[1] == ((_GROUP_A_ID, True, False), (_GROUP_B_ID, False, True))

    with session_factory() as session:
        await optimizer_service.apply_real_selection(
            session,
            _SUBSET_RUN_ID,
            OptimizerSelectionInput(selected_group_ids=[_GROUP_A_ID]),
            supervisor,
            None,
            correlation_id="implicit-current-selection",
        )
    implicit_snapshot = _subset_snapshot(session_factory)
    assert solve_lot_sets[-1] == ("LOT-A1",)
    assert implicit_snapshot[2] == ("LOT-A1",)

    solve_count_before_rejected_intent = len(solve_lot_sets)
    before_rejected_intent = _subset_snapshot(session_factory)
    with session_factory() as session, pytest.raises(AppError) as error:
        await optimizer_service.apply_real_lot_review_intent(
            session,
            _SUBSET_RUN_ID,
            OptimizerLotReviewIntentInput(source_generation=1, broker_lot_ids=["LOT-A1", "LOT-B1"]),
            supervisor,
            None,
            correlation_id="rejected-lot-intent",
        )
    assert error.value.code == "rejected_recommendation_group"
    assert error.value.details["basket_unchanged"] is True
    assert len(solve_lot_sets) == solve_count_before_rejected_intent
    assert _subset_snapshot(session_factory) == before_rejected_intent

    with session_factory() as session:
        await optimizer_service.annotate_real_group(
            session,
            _SUBSET_RUN_ID,
            _GROUP_B_ID,
            RecommendationAnnotationInput(rejected=False),
            supervisor,
            None,
            correlation_id="explicit-restore-group-b",
        )
    restored_snapshot = _subset_snapshot(session_factory)
    assert restored_snapshot[0] == before_rejected_intent[0] + 1
    assert restored_snapshot[1] == ((_GROUP_A_ID, True, False), (_GROUP_B_ID, False, False))
    assert restored_snapshot[2] == ("LOT-A1",)
    assert len(solve_lot_sets) == solve_count_before_rejected_intent

    with session_factory() as session:
        await optimizer_service.apply_real_lot_review_intent(
            session,
            _SUBSET_RUN_ID,
            OptimizerLotReviewIntentInput(source_generation=1, broker_lot_ids=["LOT-A1", "LOT-B1"]),
            supervisor,
            None,
            correlation_id="explicit-restored-lot-intent",
        )
    final_snapshot = _subset_snapshot(session_factory)
    assert solve_lot_sets[-1] == ("LOT-A1", "LOT-B1")
    assert final_snapshot[2] == ("LOT-A1", "LOT-B1")
    assert final_snapshot[1] == ((_GROUP_A_ID, True, False), (_GROUP_B_ID, True, False))
    engine.dispose()


@pytest.mark.parametrize(
    "worker_shape",
    ["missing_sell", "no_trade", "fractional_quantity", "foreign_lot", "exceeds_available", "wrong_ticker"],
)
@pytest.mark.asyncio
async def test_worker_subset_result_must_exactly_match_positive_whole_lot_intent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, worker_shape: str
) -> None:
    inputs = _subset_inputs()
    engine, session_factory = _create_sqlite_subset_optimizer_run(tmp_path)
    _patch_real_run_dependencies(monkeypatch, inputs=inputs)
    monkeypatch.setattr(optimizer_service, "_persist_candidate", _persist_subset_candidate)
    requested_lots = ("LOT-A1", "LOT-B1")
    solve_lot_sets: list[tuple[str, ...]] = []

    async def fake_solve(
        _inputs: object,
        _supervisor: object,
        *,
        sell_lot_ids: tuple[str, ...] | None = None,
        validation_executor: object = None,
    ) -> optimizer_service.ValidatedOptimizerCandidate:
        del validation_executor
        assert sell_lot_ids is not None
        solve_lot_sets.append(tuple(sell_lot_ids))
        candidate_status = "ready"
        if worker_shape == "no_trade":
            candidate = Candidate((), status="no_trade")
            candidate_status = "no_trade"
        elif worker_shape == "missing_sell":
            candidate = Candidate(_sell_legs_for_ids(_inputs, ("LOT-A1",)))
        else:
            normal_legs = _sell_legs_for_ids(_inputs, requested_lots)
            if worker_shape == "fractional_quantity":
                aaa = normal_legs[0]
                fractional_aaa = ConsolidatedLeg(
                    leg_id=aaa.leg_id,
                    side="SELL",
                    ticker=aaa.ticker,
                    shares=Decimal("0.5"),
                    estimated_unit_price_usd=aaa.estimated_unit_price_usd,
                    selected_lots=(LotAllocation("LOT-A1", Decimal("0.5")),),
                    sequence=aaa.sequence,
                    group_ids=aaa.group_ids,
                )
                candidate = Candidate((fractional_aaa, *normal_legs[1:]))
            else:
                bbb = normal_legs[1]
                if worker_shape == "foreign_lot":
                    candidate = Candidate(
                        (
                            normal_legs[0],
                            replace(bbb, selected_lots=(LotAllocation("LOT-FOREIGN", Decimal(1)),)),
                        )
                    )
                elif worker_shape == "exceeds_available":
                    candidate = Candidate(
                        (
                            normal_legs[0],
                            replace(
                                bbb,
                                shares=Decimal(2),
                                selected_lots=(LotAllocation("LOT-B1", Decimal(2)),),
                            ),
                        )
                    )
                else:
                    candidate = Candidate(
                        (
                            replace(normal_legs[0], selected_lots=(LotAllocation("LOT-B1", Decimal(1)),)),
                            replace(bbb, selected_lots=(LotAllocation("LOT-A1", Decimal(1)),)),
                        )
                    )
        return optimizer_service.ValidatedOptimizerCandidate(
            candidate, Validation(True), time.monotonic() + 60, candidate_status
        )

    monkeypatch.setattr(optimizer_service, "run_validated_candidate", fake_solve)
    before = _subset_snapshot(session_factory)
    with session_factory() as session, pytest.raises(AppError) as error:
        await optimizer_service.apply_real_lot_review_intent(
            session,
            _SUBSET_RUN_ID,
            OptimizerLotReviewIntentInput(source_generation=1, broker_lot_ids=list(requested_lots)),
            FakeSupervisor(None),
            None,
            correlation_id=f"invalid-worker-{worker_shape}",
        )

    assert error.value.code == "optimizer_subset_rejected"
    assert error.value.details["basket_unchanged"] is True
    assert error.value.details["expected_sell_lot_ids"] == list(requested_lots)
    assert solve_lot_sets == [requested_lots]
    if worker_shape == "fractional_quantity":
        assert "sell_quantity_not_positive_whole_shares" in error.value.details["intent_errors"]
        assert "sell_lot_quantity_not_positive_whole_shares" in error.value.details["intent_errors"]
    if worker_shape == "foreign_lot":
        assert "sell_lot_id_outside_frozen_inputs" in error.value.details["intent_errors"]
    if worker_shape == "exceeds_available":
        assert "sell_lot_quantity_exceeds_frozen_available_shares" in error.value.details["intent_errors"]
    if worker_shape == "wrong_ticker":
        assert "sell_lot_ticker_mismatch" in error.value.details["intent_errors"]
    assert _subset_snapshot(session_factory) == before
    engine.dispose()


@pytest.mark.parametrize("subset", [False, True])
def test_published_financial_metrics_use_owner_validation_and_survive_summary_readback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, subset: bool
) -> None:
    if subset:
        engine, session_factory = _create_sqlite_subset_optimizer_run(tmp_path)
        run_id = _SUBSET_RUN_ID
    else:
        engine, session_factory = _create_sqlite_optimizer_run(tmp_path, selected=True)
        run_id = _RUN_ID
    monkeypatch.setattr(
        optimizer_service, "_stable_id", lambda _run_id, prefix, value: f"{prefix}:{value}"
    )

    metadata = SimpleNamespace(
        solver="fake-solver",
        implementation_version="fake-worker",
        solver_versions={},
        solver_statuses=(),
        elapsed_seconds=0.1,
        screening_seconds=0.02,
        solve_seconds=0.03,
        tax_regions_considered=1,
        tax_regions_solved=1,
        tax_region_search_complete=True,
        integer_search_complete=True,
        screened_lot_count=0,
        selected_lot_ids=(),
        candidate_types=(),
        objective_value=Decimal(999999),
        baseline_objective_value=Decimal(888888),
        estimated_tax_benefit_usd=Decimal(777777),
        estimated_trading_cost_usd=Decimal(666666),
        trade_group_priorities=(
            SimpleNamespace(
                group_id="group-1",
                rank=1,
                priority_score=Decimal("4.56"),
                objective_components=(("worker_only", Decimal("999.99")),),
                rationale=("test rationale",),
            ),
        ),
        exposure_coverage_complete=True,
        rounding_attempts=0,
        warnings=(),
    )
    candidate = Candidate((), status="no_trade", metadata=metadata)  # type: ignore[arg-type]
    validation = SimpleNamespace(
        accepted=True,
        objective_value=Decimal("12.34"),
        objective_components=(("tax", Decimal("2.34")),),
        estimated_tax_benefit_usd=None,
        estimated_trading_cost_usd=Decimal("1.23"),
        evaluation=None,
        tax=None,
        wash_assessments=(),
        buy_wash_assessments=(),
        exposure_coverage=None,
    )
    prepared = optimizer_service.PreparedOptimizerRun(
        inputs=SimpleNamespace(
            lots=(), account=SimpleNamespace(cash_usd=Decimal("10.00"))
        ),  # type: ignore[arg-type]
        batch_settings={},
        frozen_input_bundle={"mode": "real_optimizer", "source_checksum": "test"},
        input_fingerprint="test-fingerprint",
        policy_revision_id=_SUBSET_POLICY_ID if subset else _POLICY_ID,
        source_generation=1,
        as_of=datetime(2026, 11, 13, tzinfo=UTC),
        proposed_trade_date=date(2026, 11, 13),
    )
    outcome = optimizer_service.ValidatedOptimizerCandidate(
        candidate, validation, time.monotonic() + 60, "no_trade"
    )

    with session_factory.begin() as session:
        run = session.get(OptimizerRun, run_id)
        assert run is not None
        optimizer_service._persist_candidate(session, run, prepared, outcome)

    with session_factory() as session:
        run = session.get(OptimizerRun, run_id)
        assert run is not None
        assert run.metrics["objective_value"] == "12.34"
        assert run.metrics["baseline_objective_value"] is None
        assert run.metrics["objective_components"] == {"tax": "2.34"}
        assert "objective_components" not in run.metrics["trade_group_priorities"][0]
        assert run.metrics["trade_group_priorities"][0] == {
            "core_group_id": "group-1",
            "rank": 1,
            "priority_score": "4.56",
            "rationale": ["test rationale"],
        }
        assert run.metrics["estimated_tax_benefit_usd"] is None
        assert run.metrics["estimated_trading_cost_usd"] == "1.23"
        summary = optimizer_service.real_run_summary(run, session)
        assert summary["estimated_tax_benefit_usd"] is None
        assert summary["optimizer_metrics"]["objective_value"] == "12.34"
        assert summary["optimizer_metrics"]["baseline_objective_value"] is None
        assert summary["optimizer_metrics"]["estimated_tax_benefit_usd"] is None
        assert summary["optimizer_metrics"]["estimated_trading_cost_usd"] == "1.23"
    engine.dispose()
