"""Bounded, killable process execution for optimizer computations.

Inputs passed to :meth:`ProcessSupervisor.run` must be immutable snapshots and
pickleable. Worker callables must be importable top-level functions. Workers
return candidate data only; the request owner remains responsible for all
independent validation and publication.
"""

from __future__ import annotations

import asyncio
import multiprocessing
import pickle
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
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


class ProcessSupervisor:
    """Run a bounded number of computations in independently killable processes."""

    def __init__(self, max_workers: int = 2) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be at least 1")
        self._max_workers = max_workers
        self._active: set[BaseProcess] = set()
        self._closed = False

    @property
    def active_workers(self) -> int:
        """Number of currently supervised child processes."""

        return len(self._active)

    async def run(
        self,
        worker_input: InputT,
        worker: Callable[[InputT, float], ResultT],
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        validation_reserve_seconds: float = DEFAULT_VALIDATION_RESERVE_SECONDS,
    ) -> WorkerResult[ResultT]:
        """Run one worker, reserving parent time for validation before the overall deadline.

        Raises ``WorkerCapacityError`` without queueing, ``WorkerTimeoutError``
        on overrun, or ``WorkerExecutionError`` on child failure.
        """

        if self._closed:
            raise RuntimeError("ProcessSupervisor is closed")
        if timeout_seconds <= 0 or validation_reserve_seconds < 0:
            raise ValueError("timeout must be positive and validation reserve nonnegative")
        if validation_reserve_seconds >= timeout_seconds:
            raise ValueError("validation reserve must be less than timeout")
        if len(self._active) >= self._max_workers:
            raise WorkerCapacityError("optimizer worker capacity is full")
        try:
            pickle.dumps((worker_input, worker))
        except (pickle.PickleError, TypeError, AttributeError) as error:
            raise TypeError("worker input and callable must be pickleable") from error

        overall_deadline = time.monotonic() + timeout_seconds
        computation_deadline = overall_deadline - validation_reserve_seconds
        context = multiprocessing.get_context("spawn")
        parent_connection, child_connection = context.Pipe(duplex=False)
        process = context.Process(
            target=_child_entry,
            args=(child_connection, worker, worker_input, computation_deadline),
            daemon=True,
        )
        self._active.add(process)
        try:
            process.start()
            child_connection.close()
            while remaining_seconds(computation_deadline) > 0:
                if parent_connection.poll():
                    try:
                        status, payload = parent_connection.recv()
                    except EOFError as error:
                        raise WorkerExecutionError("worker exited without a result") from error
                    if status != "ok":
                        raise WorkerExecutionError(str(payload))
                    return WorkerResult(payload, computation_deadline, overall_deadline)
                if not process.is_alive():
                    if parent_connection.poll():
                        continue
                    raise WorkerExecutionError(
                        f"worker exited without a result (exit code {process.exitcode})"
                    )
                await asyncio.sleep(min(0.01, remaining_seconds(computation_deadline)))
            raise WorkerTimeoutError("optimizer computation deadline exceeded")
        finally:
            parent_connection.close()
            child_connection.close()
            await asyncio.to_thread(self._stop_and_reap, process, True)
            self._active.discard(process)

    async def aclose(self) -> None:
        """Stop and reap any active workers and prevent subsequent submissions."""

        self._closed = True
        processes = tuple(self._active)
        for process in processes:
            await asyncio.to_thread(self._stop_and_reap, process, False)
            self._active.discard(process)

    @staticmethod
    def _stop_and_reap(process: BaseProcess, close: bool) -> None:
        if process.pid is None:
            return
        if process.is_alive():
            process.terminate()
        process.join(timeout=0.25)
        if process.is_alive():
            process.kill()
            process.join(timeout=0.25)
        else:
            process.join()
        if close:
            process.close()
