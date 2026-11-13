from __future__ import annotations

import asyncio
import struct
import time
from dataclasses import dataclass
from multiprocessing.connection import Connection
from threading import Event, Lock
from typing import Any, cast

import pytest

from app.optimizer import runtime
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


@dataclass(frozen=True)
class DelayedInput(Input):
    def __reduce__(self) -> tuple[object, tuple[int]]:
        time.sleep(0.6)
        return Input, (self.value,)


def restore_after_delay(delay: float, value: int) -> int:
    time.sleep(delay)
    return value


class DelayedDecode:
    def __reduce__(self) -> tuple[object, tuple[float, int]]:
        return restore_after_delay, (2.3, 42)


def delayed_decode_worker(worker_input: Input, deadline: float) -> DelayedDecode:
    return DelayedDecode()


def partial_frame_entry(
    connection: Connection, worker: object, worker_input: object, deadline: float
) -> None:
    cast(Any, connection)._send(struct.pack("!i", 100) + b"partial")
    while True:
        time.sleep(0.02)


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


@pytest.mark.asyncio
async def test_partial_frame_and_hung_child_timeout_without_blocking_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runtime, "_child_entry", partial_frame_entry)
    supervisor = ProcessSupervisor(max_workers=1)
    ticks = 0

    async def heartbeat() -> None:
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0.01)

    heartbeat_task = asyncio.create_task(heartbeat())
    with pytest.raises(WorkerTimeoutError):
        await supervisor.run(
            Input(1), successful_worker, timeout_seconds=1.5, validation_reserve_seconds=0.2
        )
    heartbeat_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await heartbeat_task
    assert ticks > 10
    assert supervisor.active_workers == 0
    await supervisor.aclose()


@pytest.mark.asyncio
async def test_slow_input_preparation_consumes_computation_budget() -> None:
    supervisor = ProcessSupervisor(max_workers=1)
    ticks = 0

    async def heartbeat() -> None:
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0.01)

    heartbeat_task = asyncio.create_task(heartbeat())
    with pytest.raises(WorkerTimeoutError):
        await supervisor.run(
            DelayedInput(1), successful_worker, timeout_seconds=0.4, validation_reserve_seconds=0.1
        )
    heartbeat_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await heartbeat_task
    assert ticks > 5
    assert supervisor.active_workers == 0
    await supervisor.aclose()


@pytest.mark.asyncio
async def test_late_result_decode_is_rejected_and_reader_is_reaped() -> None:
    supervisor = ProcessSupervisor(max_workers=1)
    with pytest.raises(WorkerTimeoutError):
        await supervisor.run(
            Input(1), delayed_decode_worker, timeout_seconds=2.5, validation_reserve_seconds=0.2
        )
    assert supervisor.active_workers == 0
    await supervisor.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("reserve", [float("nan"), float("inf"), -0.1, 10.0])
async def test_validation_reserve_must_be_finite_nonnegative_and_less_than_timeout(
    reserve: float,
) -> None:
    supervisor = ProcessSupervisor()
    with pytest.raises(ValueError, match="validation reserve"):
        await supervisor.run(Input(1), successful_worker, validation_reserve_seconds=reserve)
    assert supervisor.active_workers == 0
    await supervisor.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), 10.01])
async def test_timeout_must_be_finite_and_at_most_ten_seconds(timeout: float) -> None:
    supervisor = ProcessSupervisor()
    with pytest.raises(ValueError, match="timeout"):
        await supervisor.run(Input(1), successful_worker, timeout_seconds=timeout)
    assert supervisor.active_workers == 0
    await supervisor.aclose()


@pytest.mark.asyncio
async def test_repeated_cancellation_waits_for_one_cleanup_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supervisor = ProcessSupervisor(max_workers=1)
    cleanup_started = Event()
    release_cleanup = Event()
    calls = 0
    calls_lock = Lock()
    original = ProcessSupervisor._stop_and_reap

    def gated_reap(process: object) -> None:
        nonlocal calls
        with calls_lock:
            calls += 1
        cleanup_started.set()
        release_cleanup.wait(timeout=3)
        original(process)  # type: ignore[arg-type]

    monkeypatch.setattr(ProcessSupervisor, "_stop_and_reap", staticmethod(gated_reap))
    running = asyncio.create_task(
        supervisor.run(Input(1), hanging_worker, timeout_seconds=5, validation_reserve_seconds=0.1)
    )
    for _ in range(200):
        if supervisor.active_workers:
            break
        await asyncio.sleep(0.005)
    running.cancel()
    assert await asyncio.to_thread(cleanup_started.wait, 3)
    running.cancel()
    closing = asyncio.create_task(supervisor.aclose())
    await asyncio.sleep(0.02)
    assert supervisor.active_workers == 1
    release_cleanup.set()
    with pytest.raises(asyncio.CancelledError):
        await running
    await closing
    assert calls == 1
    assert supervisor.active_workers == 0
