from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import pytest

from app.optimizer.runtime import (
    ProcessSupervisor,
    WorkerCapacityError,
    WorkerExecutionError,
    WorkerTimeoutError,
    remaining_seconds,
)


@dataclass(frozen=True)
class Input:
    value: int


def successful_worker(worker_input: Input, deadline: float) -> tuple[int, bool]:
    return worker_input.value, deadline > time.monotonic()


def hanging_worker(worker_input: Input, deadline: float) -> int:
    while True:
        time.sleep(0.02)


def failing_worker(worker_input: Input, deadline: float) -> int:
    raise ValueError("expected worker failure")


@pytest.mark.asyncio
async def test_worker_returns_value_and_shared_deadline() -> None:
    supervisor = ProcessSupervisor(max_workers=1)
    result = await supervisor.run(
        Input(7), successful_worker, timeout_seconds=2, validation_reserve_seconds=0.2
    )
    assert result.value == (7, True)
    assert result.overall_deadline > result.computation_deadline
    assert remaining_seconds(result.overall_deadline) > 0
    assert supervisor.active_workers == 0
    await supervisor.aclose()


@pytest.mark.asyncio
async def test_hangs_timeout_reap_capacity_and_repeated_timeouts() -> None:
    supervisor = ProcessSupervisor(max_workers=1)
    for _ in range(2):
        with pytest.raises(WorkerTimeoutError):
            await supervisor.run(
                Input(1), hanging_worker, timeout_seconds=0.25, validation_reserve_seconds=0.05
            )
        assert supervisor.active_workers == 0
        result = await supervisor.run(
            Input(2), successful_worker, timeout_seconds=2, validation_reserve_seconds=0.2
        )
        assert result.value[0] == 2
    await supervisor.aclose()


@pytest.mark.asyncio
async def test_worker_error_is_returned_to_parent() -> None:
    supervisor = ProcessSupervisor(max_workers=1)
    with pytest.raises(WorkerExecutionError, match="ValueError: expected worker failure"):
        await supervisor.run(
            Input(1), failing_worker, timeout_seconds=2, validation_reserve_seconds=0.2
        )
    assert supervisor.active_workers == 0
    await supervisor.aclose()


@pytest.mark.asyncio
async def test_capacity_rejects_without_queueing_and_releases_after_completion() -> None:
    supervisor = ProcessSupervisor(max_workers=1)
    running = asyncio.create_task(
        supervisor.run(Input(1), hanging_worker, timeout_seconds=2, validation_reserve_seconds=0.1)
    )
    for _ in range(100):
        if supervisor.active_workers:
            break
        await asyncio.sleep(0.005)
    with pytest.raises(WorkerCapacityError):
        await supervisor.run(Input(2), successful_worker)
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    assert supervisor.active_workers == 0
    result = await supervisor.run(
        Input(3), successful_worker, timeout_seconds=2, validation_reserve_seconds=0.2
    )
    assert result.value[0] == 3
    await supervisor.aclose()


@pytest.mark.asyncio
async def test_explicit_cleanup_stops_active_worker_and_closes_supervisor() -> None:
    supervisor = ProcessSupervisor(max_workers=1)
    running = asyncio.create_task(
        supervisor.run(Input(1), hanging_worker, timeout_seconds=2, validation_reserve_seconds=0.1)
    )
    for _ in range(100):
        if supervisor.active_workers:
            break
        await asyncio.sleep(0.005)
    await supervisor.aclose()
    with pytest.raises((asyncio.CancelledError, WorkerExecutionError, WorkerTimeoutError)):
        await running
    assert supervisor.active_workers == 0
    with pytest.raises(RuntimeError, match="closed"):
        await supervisor.run(Input(1), successful_worker)
