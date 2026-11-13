from __future__ import annotations

import asyncio

from app.optimizer.runtime import WorkerTimeoutError
from scripts.benchmark_optimizer import percentile, run_trial


def test_percentile_is_nearest_rank_for_small_samples() -> None:
    assert percentile([3.0, 1.0, 2.0], 0.50) == 2.0
    assert percentile([3.0, 1.0, 2.0], 0.95) == 3.0
    assert percentile([], 0.95) is None
    assert percentile([1.0, 2.0, 3.0, 4.0], 0.50) == 2.0
    assert percentile([1.0, 2.0, 3.0, 4.0, 5.0], 0.60) == 3.0


def test_trial_timeout_is_recorded_instead_of_aborting_benchmark() -> None:
    class TimedOutSupervisor:
        async def run(self, *args: object, **kwargs: object) -> None:
            raise WorkerTimeoutError("optimizer computation deadline exceeded")

    row = asyncio.run(run_trial(19, TimedOutSupervisor()))  # type: ignore[arg-type]
    assert row["status"] == "failed"
    assert row["error_type"] == "WorkerTimeoutError"
    assert row["error"] == "optimizer computation deadline exceeded"
    assert row["accepted"] is False
