"""Bounded, killable process execution for optimizer computations.

Inputs passed to :meth:`ProcessSupervisor.run` must be immutable snapshots and
pickleable. Worker callables must be importable top-level functions. Workers
return candidate data only; the request owner remains responsible for all
independent validation and publication.
"""

from __future__ import annotations

import asyncio
import math
import multiprocessing
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess
from typing import TypeVar

DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_VALIDATION_RESERVE_SECONDS = 2.0

InputT = TypeVar("InputT")
ResultT = TypeVar("ResultT")


class WorkerCapacityError(RuntimeError):
    """Raised immediately when all worker slots are occupied."""


class WorkerTimeoutError(TimeoutError):
    """Raised when the worker misses its computation deadline."""


class WorkerExecutionError(RuntimeError):
    """Raised when the child callable fails or cannot return a result."""


@dataclass(frozen=True, slots=True)
class WorkerResult[T]:
    """Untrusted child output and the deadlines needed by parent validation."""

    value: T
    computation_deadline: float
    overall_deadline: float


def remaining_seconds(deadline: float) -> float:
    """Return nonnegative time remaining against an absolute ``time.monotonic`` deadline."""

    return max(0.0, deadline - time.monotonic())


def _child_entry[InputT, ResultT](
    connection: Connection,
    worker: Callable[[InputT, float], ResultT],
    worker_input: InputT,
    deadline: float,
) -> None:
    try:
        try:
            value = worker(worker_input, deadline)
            message: tuple[str, object] = ("ok", value)
        except Exception as error:  # noqa: BLE001 - serialize child failures to parent
            message = ("error", f"{type(error).__name__}: {error}")
        try:
            connection.send(message)
        except Exception as error:  # noqa: BLE001 - report serialization failures
            # A non-pickleable return value still exits cleanly and is reported.
            with suppress(Exception):
                connection.send(("error", f"Worker result could not be serialized: {error}"))
    finally:
        connection.close()


@dataclass(slots=True)
class _WorkerHandle:
    process: BaseProcess
    parent_connection: Connection
    child_connection: Connection
    setup_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    startup_task: asyncio.Task[None] | None = None
    receiver_task: asyncio.Task[object] | None = None
    cleanup_task: asyncio.Task[None] | None = None


class ProcessSupervisor:
    """Run a bounded number of computations in independently killable processes."""

    def __init__(self, max_workers: int = 2) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be at least 1")
        self._max_workers = max_workers
        self._active: dict[BaseProcess, _WorkerHandle] = {}
        self._closed = False

    @property
    def active_workers(self) -> int:
        """Number of jobs still holding a worker capacity slot."""

        return len(self._active)

    async def run(
        self,
        worker_input: InputT,
        worker: Callable[[InputT, float], ResultT],
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        validation_reserve_seconds: float = DEFAULT_VALIDATION_RESERVE_SECONDS,
    ) -> WorkerResult[ResultT]:
        """Run one worker and reserve time before the overall deadline for validation."""

        if self._closed:
            raise RuntimeError("ProcessSupervisor is closed")
        try:
            valid_timeout = (
                math.isfinite(timeout_seconds) and 0 < timeout_seconds <= DEFAULT_TIMEOUT_SECONDS
            )
            valid_reserve = (
                math.isfinite(validation_reserve_seconds) and validation_reserve_seconds >= 0
            )
        except TypeError as error:
            raise ValueError("timeout and validation reserve must be finite numbers") from error
        if not valid_timeout:
            raise ValueError(
                f"timeout must be finite and between 0 and {DEFAULT_TIMEOUT_SECONDS} seconds"
            )
        if not valid_reserve or validation_reserve_seconds >= timeout_seconds:
            raise ValueError(
                "validation reserve must be finite, nonnegative, and less than timeout"
            )
        if len(self._active) >= self._max_workers:
            raise WorkerCapacityError("optimizer worker capacity is full")

        # Start the budget before process setup/argument serialization. Startup and
        # connection decoding run off-loop but remain owned by this bounded job.
        overall_deadline = time.monotonic() + timeout_seconds
        computation_deadline = overall_deadline - validation_reserve_seconds
        context = multiprocessing.get_context("spawn")
        parent_connection, child_connection = context.Pipe(duplex=False)
        process = context.Process(
            target=_child_entry,
            args=(child_connection, worker, worker_input, computation_deadline),
            daemon=True,
        )
        handle = _WorkerHandle(process, parent_connection, child_connection)
        self._active[process] = handle
        try:
            async with handle.setup_lock:
                handle.startup_task = asyncio.create_task(asyncio.to_thread(process.start))
                await self._wait_task_until(handle.startup_task, computation_deadline)
                child_connection.close()

                # recv() may block on a partial frame or spend time reconstructing a
                # result. Its single reader is bounded by active job slots and owned
                # through cleanup; it never blocks the event loop.
                handle.receiver_task = asyncio.create_task(
                    asyncio.to_thread(parent_connection.recv)
                )
            try:
                message = await self._wait_task_until(handle.receiver_task, computation_deadline)
            except EOFError as error:
                raise WorkerExecutionError("worker exited without a result") from error
            if time.monotonic() >= computation_deadline:
                raise WorkerTimeoutError("optimizer computation deadline exceeded")
            if (
                not isinstance(message, tuple)
                or len(message) != 2
                or not isinstance(message[0], str)
            ):
                raise WorkerExecutionError("worker returned a malformed result")
            status, payload = message
            if status != "ok":
                raise WorkerExecutionError(str(payload))
            return WorkerResult(payload, computation_deadline, overall_deadline)
        finally:
            await self._await_cleanup(handle)

    async def aclose(self) -> None:
        """Stop new work and await the same per-job cleanup used by run()."""

        self._closed = True
        handles = tuple(self._active.values())
        await asyncio.gather(*(self._await_cleanup(handle) for handle in handles))

    async def _wait_task_until(self, task: asyncio.Task[ResultT], deadline: float) -> ResultT:
        remaining = remaining_seconds(deadline)
        if remaining <= 0:
            raise WorkerTimeoutError("optimizer computation deadline exceeded")
        done, _ = await asyncio.wait((task,), timeout=remaining)
        if not done:
            raise WorkerTimeoutError("optimizer computation deadline exceeded")
        return task.result()

    async def _await_cleanup(self, handle: _WorkerHandle) -> None:
        if handle.cleanup_task is None:
            handle.cleanup_task = asyncio.create_task(self._cleanup(handle))
        cleanup_task = handle.cleanup_task
        cancelled = False
        while not cleanup_task.done():
            try:
                await asyncio.shield(cleanup_task)
            except asyncio.CancelledError:
                cancelled = True
        cleanup_task.result()
        if cancelled:
            raise asyncio.CancelledError

    async def _cleanup(self, handle: _WorkerHandle) -> None:
        process = handle.process
        try:
            async with handle.setup_lock:
                if handle.startup_task is not None:
                    await asyncio.gather(handle.startup_task, return_exceptions=True)
                if process.pid is not None:
                    await asyncio.to_thread(self._stop_and_reap, process)
                if handle.receiver_task is not None:
                    await asyncio.gather(handle.receiver_task, return_exceptions=True)
        finally:
            try:
                handle.parent_connection.close()
                handle.child_connection.close()
            finally:
                try:
                    if process.pid is not None:
                        process.close()
                finally:
                    self._active.pop(process, None)

    @staticmethod
    def _stop_and_reap(process: BaseProcess) -> None:
        if process.pid is None:
            return
        if process.is_alive():
            process.terminate()
        process.join(timeout=0.25)
        if process.is_alive():
            process.kill()
            process.join()
        else:
            process.join()
