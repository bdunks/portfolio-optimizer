from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest

from app.domain.financial_inputs import FinancialInputs
from app.optimizer.core import OptimizerRequest, OptimizerResult
from app.optimizer.runtime import ProcessSupervisor, WorkerResult, WorkerTimeoutError
from scripts.benchmark_optimizer import percentile, run_trial



def test_percentile_is_nearest_rank_for_small_samples() -> None:
    assert percentile([3.0, 1.0, 2.0], 0.50) == 2.0
    assert percentile([3.0, 1.0, 2.0], 0.95) == 3.0
    assert percentile([], 0.95) is None
    assert percentile([1.0, 2.0, 3.0, 4.0], 0.50) == 2.0
    assert percentile([1.0, 2.0, 3.0, 4.0, 5.0], 0.60) == 3.0

def test_trial_timeout_is_recorded_instead_of_aborting_benchmark(
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    async def timed_out_run(
        self: ProcessSupervisor,
        worker_input: OptimizerRequest,
        worker: Callable[[OptimizerRequest, float], tuple[OptimizerResult, int | None]],
        *,
        timeout_seconds: float = 10.0,
        validation_reserve_seconds: float = 2.0,
    ) -> WorkerResult[tuple[OptimizerResult, int | None]]:
        raise WorkerTimeoutError("optimizer computation deadline exceeded")

    monkeypatch.setattr(ProcessSupervisor, "run", timed_out_run)
    row = asyncio.run(run_trial(19, ProcessSupervisor()))
    assert row["status"] == "failed"
    assert row["error_type"] == "WorkerTimeoutError"
    assert row["error"] == "optimizer computation deadline exceeded"
    assert row["accepted"] is False

def test_trial_defaults_to_baseline_and_forwards_scenario(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import scripts.benchmark_optimizer as benchmark

    scenario_calls: list[str] = []
    original_build = benchmark.build_optimizer_benchmark_inputs

    def record_build(seed: int, scenario: str = "baseline") -> FinancialInputs:
        scenario_calls.append(scenario)
        return original_build(seed, scenario=scenario)

    async def timed_out_run(
        self: ProcessSupervisor,
        worker_input: OptimizerRequest,
        worker: Callable[[OptimizerRequest, float], tuple[OptimizerResult, int | None]],
        *,
        timeout_seconds: float = 10.0,
        validation_reserve_seconds: float = 2.0,
    ) -> WorkerResult[tuple[OptimizerResult, int | None]]:
        raise WorkerTimeoutError("optimizer computation deadline exceeded")

    monkeypatch.setattr(benchmark, "build_optimizer_benchmark_inputs", record_build)
    monkeypatch.setattr(ProcessSupervisor, "run", timed_out_run)
    default_row = asyncio.run(run_trial(1, ProcessSupervisor()))
    scenario_row = asyncio.run(run_trial(2, ProcessSupervisor(), scenario="recent_loss"))
    assert scenario_calls == ["baseline", "recent_loss"]
    assert default_row["scenario"] == "baseline"
    assert scenario_row["scenario"] == "recent_loss"
    assert scenario_row["held_position_count"] == 460
    assert scenario_row["security_count"] == 462
    assert scenario_row["available_lot_count"] > 0


def test_path_coverage_requires_sell_dependent_buy_and_exact_recent_clearance() -> None:
    from decimal import Decimal
    from types import SimpleNamespace

    from scripts.benchmark_optimizer import _assess, _path_coverage

    sell = SimpleNamespace(
        side="SELL",
        leg_id="sell-1",
        selected_lots=(
            SimpleNamespace(broker_lot_id="EQ000-LOT-001", shares=Decimal(1)),
            SimpleNamespace(broker_lot_id="EQ000-LOT-002", shares=Decimal(2)),
        ),
    )
    buy = SimpleNamespace(
        side="BUY",
        leg_id="buy-1",
        shares=Decimal(1),
        depends_on_leg_ids=("sell-1",),
        selected_lots=(),
    )
    covered = _path_coverage("recent_loss", True, (sell, buy))
    assert covered["path_covered"] is True
    sell_only = _path_coverage("replacement_buy", True, (sell,))
    assert sell_only["path_covered"] is False
    assert sell_only["explicit_failure"] == "accepted_result_has_no_dependent_whole_share_buy"
    assert _assess([{"accepted": False, "screening_seconds": 0.01}], "screening_seconds", 1) is None
