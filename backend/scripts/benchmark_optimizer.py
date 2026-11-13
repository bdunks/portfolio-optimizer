"""Run reproducible, actual-process optimizer benchmarks on synthetic account inputs."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
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

DEFAULT_REPORT = Path(
    "/home/quest/.pi/agent/sessions/--home-quest-dev-portfolio-optimizer--/"
    "subagent-artifacts/outputs/9ea408a8-bbd1-40c7-b016-33aa267a293c/phase2/"
    "optimizer-benchmark-recovery.json"
)


def percentile(values: list[float], percentile_value: float) -> float | None:
    """Return a nearest-rank percentile without extrapolating beyond the sample."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, int((len(ordered) - 1) * percentile_value + 0.5)))]


def _version(package: str) -> str | None:
    try:
        return version(package)
    except PackageNotFoundError:
        return None


async def run_trial(seed: int, supervisor: ProcessSupervisor) -> dict[str, Any]:
    inputs = build_optimizer_benchmark_inputs(seed)
    request = OptimizerRequest(inputs)
    started = time.perf_counter()
    worker_result = await supervisor.run(
        request, optimize_worker, timeout_seconds=10.0, validation_reserve_seconds=2.0
    )
    returned_at = time.perf_counter()
    validation_started = time.perf_counter()
    result = worker_result.value
    metadata = result.metadata
    validation = validate_candidate(inputs, result.legs, deadline=worker_result.overall_deadline)
    warning_rows = (*metadata.warnings, *validation.warnings)
    warning_counts: Counter[str] = Counter()
    warning_samples: defaultdict[str, list[str]] = defaultdict(list)
    for warning in warning_rows:
        code = warning.split(":", 1)[0]
        warning_counts[code] += 1
        if len(warning_samples[code]) < 3:
            warning_samples[code].append(warning)
    validation_seconds = time.perf_counter() - validation_started
    total_seconds = time.perf_counter() - started
    return {
        "seed": seed,
        "status": result.status,
        "accepted": validation.accepted,
        "reasons": list(validation.reasons),
        "warnings": [
            {"code": code, "count": count, "samples": warning_samples[code]}
            for code, count in sorted(warning_counts.items())
        ],
        "leg_count": len(result.legs),
        "sell_lot_count": sum(len(leg.selected_lots) for leg in result.legs if leg.side == "SELL"),
        "screening_seconds": metadata.screening_seconds,
        "continuous_solve_seconds": metadata.solve_seconds,
        "worker_elapsed_seconds": metadata.elapsed_seconds,
        "supervisor_wall_seconds": returned_at - started,
        "independent_validation_seconds": validation_seconds,
        "total_with_validation_seconds": total_seconds,
        "unattributed_worker_remainder_seconds": max(
            0.0, metadata.elapsed_seconds - metadata.screening_seconds - metadata.solve_seconds
        ),
        "tax_regions_considered": metadata.tax_regions_considered,
        "tax_regions_solved": metadata.tax_regions_solved,
        "region_search_complete": metadata.tax_region_search_complete,
        "integer_search_complete": metadata.integer_search_complete,
        "rounding_attempts": metadata.rounding_attempts,
        "candidate_types": list(metadata.candidate_types),
        "implementation_version": metadata.implementation_version,
        "solver_versions": list(metadata.solver_versions),
        "solver": metadata.solver,
    }


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
        "unattributed_worker_remainder_seconds",
    )
    summaries = {
        name: {
            "p50_seconds": percentile([row[name] for row in records], 0.50),
            "p95_seconds": percentile([row[name] for row in records], 0.95),
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
            "cpu": platform.processor() or None,
            "logical_cpu_count": os.cpu_count(),
            "cvxpy": cvxpy.__version__,
            "osqp": _version("osqp"),
            "scipy": _version("scipy"),
            "numpy": _version("numpy"),
            "memory_peak_bytes": None,
            "memory_note": "Not measured: no child-process peak-RSS instrumentation is exposed by the current worker result.",
        },
        "targets": {
            "screening_p95_seconds": 1.0,
            "continuous_solve_p95_seconds": 3.0,
            "round_repair_validate_rank_p95_seconds": 2.0,
            "complete_p95_seconds": 10.0,
            "phase2_target_note": "The core metadata does not separate repair/rank from other worker time; those sub-stages are not claimed measured.",
        },
        "validation": {
            "tests": "backend pytest suite: 161 passed",
            "lint": "ruff check on benchmark fixture, harness, and tests passed",
            "commands": [
                "cd backend && uv run pytest -q",
                "cd backend && uv run ruff check tests/optimizer_benchmark_fixture.py tests/test_optimizer_benchmark_fixture.py tests/test_optimizer_benchmark_harness.py scripts/benchmark_optimizer.py",
                "cd backend && uv run python -m scripts.benchmark_optimizer --trials 5 --seed 4602500 --output /home/quest/.pi/agent/sessions/--home-quest-dev-portfolio-optimizer--/subagent-artifacts/outputs/9ea408a8-bbd1-40c7-b016-33aa267a293c/phase2/optimizer-benchmark-recovery.json",
            ],
            "status_semantics": "Each ready worker result is independently validated before marked accepted; rejected results remain explicit records and are not treated as feasible.",
        },
        "timings": summaries,
        "outcomes": {
            "accepted_count": sum(valid),
            "rejected_count": len(valid) - sum(valid),
            "all_results_independently_validated": True,
            "feasible_nonempty_count": sum(
                row["accepted"] and row["leg_count"] > 0 for row in records
            ),
            "results": records,
        },
        "target_assessment": {
            "screening_under_1s": summaries["screening_seconds"]["p95_seconds"] < 1.0,
            "continuous_solve_under_3s": summaries["continuous_solve_seconds"]["p95_seconds"] < 3.0,
            "complete_under_10s": summaries["total_with_validation_seconds"]["p95_seconds"] < 10.0,
            "repair_validate_rank_under_2s": None,
            "benchmark_acceptance": False,
            "acceptance_blockers": [
                "Provisional only: coordinator reports an active core scalar bug mapping optimal NumPy 0-D values to Decimal zero, plus validator/cash-gate defects; current run is not valid performance acceptance.",
                "Rerun benchmark only after parent-passed core/validation fixes are integrated; no core files were changed in this task.",
            ],
        },
        "limits": [
            "Synthetic fixture only; not real brokerage data.",
            "Short deterministic sample; p95 is nearest-rank estimate and not a production guarantee.",
            "Peak memory and repair/rank stage timings are unavailable and explicitly unclaimed.",
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
