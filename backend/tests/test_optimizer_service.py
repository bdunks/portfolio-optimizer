from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

import pytest

from app.domain.financial_inputs import PolicySettings
from app.optimizer.runtime import WorkerResult, WorkerTimeoutError
from app.services import optimizer_service
from app.services.errors import AppError


@dataclass(frozen=True)
class Request:
    inputs: object
    sell_lot_ids: tuple[str, ...] | None


@dataclass(frozen=True)
class Candidate:
    legs: tuple[object, ...]


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
    inputs = object()
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
    candidate = Candidate(())
    supervisor = FakeSupervisor(candidate)

    monkeypatch.setattr(
        optimizer_service,
        "_core_contract",
        lambda: (Request, lambda request, deadline: candidate, lambda *args, **kwargs: Validation(False, ("cash_shortfall",))),
    )

    with pytest.raises(AppError) as error:
        await optimizer_service.run_validated_candidate(object(), supervisor)  # type: ignore[arg-type]

    assert error.value.code == "optimizer_candidate_rejected"
    assert error.value.details == {"reasons": ["cash_shortfall"], "basket_unchanged": True}


@pytest.mark.asyncio
async def test_run_validated_candidate_rejects_late_owner_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    candidate = Candidate(())
    supervisor = FakeSupervisor(candidate, deadline=time.monotonic() - 1)
    monkeypatch.setattr(
        optimizer_service,
        "_core_contract",
        lambda: (Request, lambda request, deadline: candidate, lambda *args, **kwargs: Validation(True)),
    )

    with pytest.raises(WorkerTimeoutError):
        await optimizer_service.run_validated_candidate(object(), supervisor)  # type: ignore[arg-type]
