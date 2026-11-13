"""Run reproducible, actual-process optimizer benchmarks on synthetic account inputs."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import platform
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import cvxpy

from app.optimizer.core import OptimizerRequest, optimize_worker
from app.optimizer.runtime import ProcessSupervisor
from app.optimizer.validation import validate_candidate
from tests.optimizer_benchmark_fixture import build_optimizer_benchmark_inputs

DEFAULT_REPORT = Path("benchmark-results/optimizer-benchmark.json")


def percentile(values: list[float], percentile_value: float) -> float | None:
    """Return a nearest-rank percentile without extrapolating beyond the sample."""
    if not values:
        return None
    ordered = sorted(values)
    if not 0 < percentile_value <= 1:
        raise ValueError("percentile must be in (0, 1]")
    return ordered[math.ceil(len(ordered) * percentile_value) - 1]


def _version(package: str) -> str | None:
    try:
        return version(package)
    except PackageNotFoundError:
        return None
def _cpu_model() -> str | None:
    processor = platform.processor()
    if processor:
        return processor
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.lower().startswith(("model name", "hardware")):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return None




def _measured_worker(request: OptimizerRequest, deadline: float) -> tuple[Any, int | None]:
    """Return optimizer payload and child-process peak RSS in bytes where supported."""
    result = optimize_worker(request, deadline)
    try:
        import resource

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Linux reports KiB; macOS reports bytes.
        peak_bytes = int(peak if sys.platform == "darwin" else peak * 1024)
    except (ImportError, AttributeError, OSError):
        peak_bytes = None
    return result, peak_bytes


async def run_trial(seed: int, supervisor: ProcessSupervisor) -> dict[str, Any]:
    started = time.perf_counter()
    row: dict[str, Any] = {"seed": seed, "status": "failed", "accepted": False}
    try:
        inputs = build_optimizer_benchmark_inputs(seed)
        request = OptimizerRequest(inputs)
        worker_result = await supervisor.run(
            request, _measured_worker, timeout_seconds=10.0, validation_reserve_seconds=2.0
        )
        returned_at = time.perf_counter()
        result, peak_bytes = worker_result.value
        validation_started = time.perf_counter()
        validation = validate_candidate(inputs, result.legs, deadline=worker_result.overall_deadline)
        validation_seconds = time.perf_counter() - validation_started
        metadata = result.metadata
        warning_counts: Counter[str] = Counter()
        warning_samples: defaultdict[str, list[str]] = defaultdict(list)
        for warning in (*metadata.warnings, *validation.warnings):
            code = warning.split(":", 1)[0]
            warning_counts[code] += 1
            if len(warning_samples[code]) < 3:
                warning_samples[code].append(warning)
        status = result.status
        row.update({
            "independently_validated": True,
            "status": status,
            "accepted": bool(status == "ready" and validation.accepted and time.monotonic() < worker_result.overall_deadline),
            "reasons": list(validation.reasons),
            "warnings": [
                {"code": code, "count": count, "samples": warning_samples[code]}
                for code, count in sorted(warning_counts.items())
            ],
            "leg_count": len(result.legs),
            "sell_lot_count": sum(len(leg.selected_lots) for leg in result.legs if leg.side == "SELL"),
            "buy_order_count": sum(leg.side == "BUY" for leg in result.legs),
            "screening_seconds": metadata.screening_seconds,
            "continuous_solve_seconds": metadata.solve_seconds if getattr(metadata, "repair_validate_rank_seconds", None) is not None else None,
            "core_reported_solve_seconds": metadata.solve_seconds,
            "repair_validate_rank_seconds": getattr(metadata, "repair_validate_rank_seconds", None),
            "worker_elapsed_seconds": metadata.elapsed_seconds,
            "supervisor_wall_seconds": returned_at - started,
            "independent_validation_seconds": validation_seconds,
            "total_with_validation_seconds": time.perf_counter() - started,
            "child_peak_rss_bytes": peak_bytes,
            "tax_regions_considered": metadata.tax_regions_considered,
            "tax_regions_solved": metadata.tax_regions_solved,
            "region_search_complete": metadata.tax_region_search_complete,
            "integer_search_complete": metadata.integer_search_complete,
            "rounding_attempts": metadata.rounding_attempts,
            "candidate_types": list(metadata.candidate_types),
            "implementation_version": metadata.implementation_version,
            "solver_versions": list(metadata.solver_versions),
            "solver": metadata.solver,
        })
    except Exception as error:  # noqa: BLE001 — persist per-trial failures instead of aborting the run.
        row.update({"error_type": type(error).__name__, "error": str(error)})
    row.setdefault("total_with_validation_seconds", time.perf_counter() - started)
    return row


async def run_benchmark(trials: int, seed: int) -> dict[str, Any]:
    supervisor = ProcessSupervisor(max_workers=1)
    records: list[dict[str, Any]] = []
    try:
        for index in range(trials):
            records.append(await run_trial(seed + index, supervisor))
    finally:
        await supervisor.aclose()
    timing_fields = (
        "screening_seconds",
        "continuous_solve_seconds",
        "worker_elapsed_seconds",
        "supervisor_wall_seconds",
        "independent_validation_seconds",
        "total_with_validation_seconds",
        "repair_validate_rank_seconds",
    )
    summaries = {
        name: {
            "p50_seconds": percentile([row[name] for row in records if isinstance(row.get(name), (int, float))], 0.50),
            "p95_seconds": percentile([row[name] for row in records if isinstance(row.get(name), (int, float))], 0.95),
        }
        for name in timing_fields
    }
    valid = [row["accepted"] for row in records]
    return {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "benchmark": "synthetic single-account optimizer; actual ProcessSupervisor spawn worker plus owner validation",
        "fixture": {
            "securities": 460,
            "lots": 2500,
            "seed_start": seed,
            "trial_count": trials,
            "seed_variants_change_basis_data": True,
            "description": "Synthetic one-account taxable portfolio with cash, nested policy targets, full tax/YTD/carryforward settings, 8 explicit objective/cost settings, mixed gain/loss and tiny cleanup lots, complete look-through and transaction-history provenance; no broker, database, or network access.",
        },
        "environment": {
            "platform": platform.platform(),
            "os": os.name,
            "python": sys.version,
            "cpu": _cpu_model(),
            "logical_cpu_count": os.cpu_count(),
            "cvxpy": cvxpy.__version__,
            "osqp": _version("osqp"),
            "scipy": _version("scipy"),
            "numpy": _version("numpy"),
            "git_commit": subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip(),  # noqa: ASYNC221
            "memory_note": "Per-trial child_peak_rss_bytes uses getrusage(RUSAGE_SELF); includes native allocations and process baseline, not exact incremental allocations. Null where unsupported.",
        },
        "targets": {
            "screening_p95_seconds": 1.0,
            "continuous_solve_p95_seconds": 3.0,
            "round_repair_validate_rank_p95_seconds": 2.0,
            "complete_p95_seconds": 10.0,
            "phase2_target_note": "Repair/validation/rank is reported only when core metadata exposes the dedicated stage; missing data is null.",
        },
        "validation": {
            "status_semantics": "Only ready results independently validated as accepted before the overall deadline count as feasible; errors and no-trade outcomes remain explicit.",
        },
        "timings": summaries,
        "outcomes": {
            "accepted_count": sum(valid),
            "rejected_count": len(valid) - sum(valid),
            "independently_validated_count": sum(bool(row.get("independently_validated")) for row in records),
            "feasible_nonempty_count": sum(
                row["accepted"] and row["leg_count"] > 0 for row in records
            ),
            "results": records,
        },
        "target_assessment": {
            "screening_under_1s": summaries["screening_seconds"]["p95_seconds"] is not None and summaries["screening_seconds"]["p95_seconds"] < 1.0,
            "continuous_solve_under_3s": summaries["continuous_solve_seconds"]["p95_seconds"] is not None and summaries["continuous_solve_seconds"]["p95_seconds"] < 3.0,
            "complete_under_10s": summaries["total_with_validation_seconds"]["p95_seconds"] is not None and summaries["total_with_validation_seconds"]["p95_seconds"] < 10.0,
            "repair_validate_rank_under_2s": (summaries["repair_validate_rank_seconds"]["p95_seconds"] < 2.0 if summaries["repair_validate_rank_seconds"]["p95_seconds"] is not None else None),
            "benchmark_acceptance": False,
            "acceptance_blockers": [
                "Integer search incomplete for one or more trials; recommendations may be rounded relaxation candidates." if any(row.get("integer_search_complete") is False for row in records) else "",
                f"{len([row for row in records if row.get('error')])} trial(s) failed; see per-trial errors." if any(row.get("error") for row in records) else "Core correctness has not been verified as fixed; do not treat provisional timings as performance acceptance.",
                "Continuous solve and repair/validation/rank stage are unmeasured until core emits dedicated stage metadata." if summaries["repair_validate_rank_seconds"]["p95_seconds"] is None else "",
            ],
        },
        "limits": [
            "Synthetic fixture only; not real brokerage data.",
            "Short deterministic sample; p95 is nearest-rank estimate and not a production guarantee.",
            "Peak RSS includes worker process baseline and native allocations, not exact incremental allocations.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument("--seed", type=int, default=4602500)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    if args.trials < 1:
        parser.error("--trials must be positive")
    report = asyncio.run(run_benchmark(args.trials, args.seed))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "accepted": report["outcomes"]["accepted_count"],
                "trials": args.trials,
                "timings": report["timings"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
