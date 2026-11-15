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

from app.domain.financial_inputs import FinancialInputs
from app.domain.portfolio_accounting import ConsolidatedLeg
from app.optimizer.core import OptimizerRequest, OptimizerResult, optimize_worker
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


def _assess(records: list[dict[str, Any]], field: str, target: float) -> bool | None:
    values = [
        row[field]
        for row in records
        if row.get("accepted") is True
        and not row.get("error")
        and isinstance(row.get(field), (int, float))
    ]
    p95 = percentile(values, 0.95)
    return p95 < target if p95 is not None else None


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


def _measured_worker(request: OptimizerRequest, deadline: float) -> tuple[OptimizerResult, int | None]:
    """Return optimizer payload and child-process peak RSS in bytes where supported."""
    result = optimize_worker(request, deadline)
    try:
        import resource

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Linux reports KiB; macOS reports bytes.
        peak_bytes = peak if sys.platform == "darwin" else peak * 1024
    except ImportError, AttributeError, OSError:
        peak_bytes = None
    return result, peak_bytes


def _fixture_dimensions(inputs: FinancialInputs) -> dict[str, Any]:
    settings = dict(inputs.policy.settings.values)
    return {
        "held_position_count": len(inputs.positions),
        "security_count": len(inputs.securities),
        "lot_count": len(inputs.lots),
        "available_lot_count": sum(lot.available_shares > 0 for lot in inputs.lots),
        "controlled_restrictions": {
            key: settings.get(key)
            for key in (
                "max_sell_tickers_per_batch",
                "max_sell_lots_per_batch",
                "max_total_orders_per_batch",
            )
        },
    }


def _path_coverage(
    scenario: str, accepted: bool, legs: tuple[ConsolidatedLeg, ...]
) -> dict[str, bool | str | None]:
    sells = [leg for leg in legs if leg.side == "SELL"]
    buys = [leg for leg in legs if leg.side == "BUY"]
    dependent_whole_share_buy = any(
        buy.shares == buy.shares.to_integral_value()
        and any(sell.leg_id in buy.depends_on_leg_ids for sell in sells)
        for buy in buys
    )
    coverage: dict[str, bool | str | None] = {
        "path_covered": False,
        "explicit_failure": None,
        "sell_present": bool(sells),
        "dependent_whole_share_buy_present": dependent_whole_share_buy,
        "required_recent_loss_lots_present": None,
    }
    if scenario == "baseline":
        coverage["path_covered"] = accepted
        if not accepted:
            coverage["explicit_failure"] = "baseline_not_accepted"
        return coverage
    if scenario == "recent_loss":
        sold = {lot.broker_lot_id: lot.shares for sell in sells for lot in sell.selected_lots}
        coverage["required_recent_loss_lots_present"] = (
            sold.get("EQ000-LOT-001") == 1 and sold.get("EQ000-LOT-002", 0) > 0
        )
    if not accepted:
        coverage["explicit_failure"] = "result_not_accepted"
    elif not sells:
        coverage["explicit_failure"] = "accepted_result_has_no_sell"
    elif not coverage["dependent_whole_share_buy_present"]:
        coverage["explicit_failure"] = "accepted_result_has_no_dependent_whole_share_buy"
    elif coverage["required_recent_loss_lots_present"] is False:
        coverage["explicit_failure"] = "required_recent_loss_lot_clearance_missing"
    else:
        coverage["path_covered"] = True
    return coverage


async def run_trial(
    seed: int, supervisor: ProcessSupervisor, scenario: str = "baseline"
) -> dict[str, Any]:
    started = time.perf_counter()
    row: dict[str, Any] = {
        "seed": seed,
        "scenario": scenario,
        "status": "failed",
        "accepted": False,
    }
    try:
        inputs = build_optimizer_benchmark_inputs(seed, scenario=scenario)
        row.update(_fixture_dimensions(inputs))
        request = OptimizerRequest(inputs)
        worker_result = await supervisor.run(
            request, _measured_worker, timeout_seconds=10.0, validation_reserve_seconds=2.0
        )
        returned_at = time.perf_counter()
        result, peak_bytes = worker_result.value
        validation_started = time.perf_counter()
        validation = validate_candidate(
            inputs, result.legs, deadline=worker_result.overall_deadline
        )
        validation_seconds = time.perf_counter() - validation_started
        metadata = result.metadata
        repair_validate_rank_seconds = metadata.repair_validate_rank_seconds
        warning_counts: Counter[str] = Counter()
        warning_samples: defaultdict[str, list[str]] = defaultdict(list)
        for warning in (*metadata.warnings, *validation.warnings):
            code = warning.split(":", 1)[0]
            warning_counts[code] += 1
            if len(warning_samples[code]) < 3:
                warning_samples[code].append(warning)
        status = result.status
        row.update(
            {
                "independently_validated": True,
                "status": status,
                "accepted": bool(
                    status == "ready"
                    and validation.accepted
                    and time.monotonic() < worker_result.overall_deadline
                ),
                "reasons": list(validation.reasons),
                "warnings": [
                    {"code": code, "count": count, "samples": warning_samples[code]}
                    for code, count in sorted(warning_counts.items())
                ],
                "leg_count": len(result.legs),
                "sell_lot_count": sum(
                    len(leg.selected_lots) for leg in result.legs if leg.side == "SELL"
                ),
                "buy_order_count": sum(leg.side == "BUY" for leg in result.legs),
                "screening_seconds": metadata.screening_seconds,
                "continuous_solve_including_model_construction_seconds": metadata.solve_seconds,
                "repair_validate_rank_seconds": repair_validate_rank_seconds,
                "repair_all_validation_rank_seconds": (
                    repair_validate_rank_seconds + validation_seconds
                    if repair_validate_rank_seconds is not None
                    else None
                ),
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
            }
        )
        row["path_coverage"] = _path_coverage(scenario, row["accepted"], result.legs)
    except Exception as error:  # noqa: BLE001 — persist per-trial failures instead of aborting the run.
        row["path_coverage"] = {
            "path_covered": False,
            "explicit_failure": "trial_error",
            "error": str(error),
        }
        row.update({"error_type": type(error).__name__, "error": str(error)})
    row.setdefault("total_with_validation_seconds", time.perf_counter() - started)
    return row


async def run_benchmark(trials: int, seed: int, scenario: str = "baseline") -> dict[str, Any]:
    supervisor = ProcessSupervisor(max_workers=1)
    records: list[dict[str, Any]] = []
    try:
        for index in range(trials):
            records.append(await run_trial(seed + index, supervisor, scenario=scenario))
    finally:
        await supervisor.aclose()
    timing_fields = (
        "screening_seconds",
        "continuous_solve_including_model_construction_seconds",
        "worker_elapsed_seconds",
        "supervisor_wall_seconds",
        "independent_validation_seconds",
        "total_with_validation_seconds",
        "repair_validate_rank_seconds",
        "repair_all_validation_rank_seconds",
    )
    summaries = {
        name: {
            "p50_seconds": percentile(
                [row[name] for row in records if isinstance(row.get(name), (int, float))], 0.50
            ),
            "p95_seconds": percentile(
                [row[name] for row in records if isinstance(row.get(name), (int, float))], 0.95
            ),
        }
        for name in timing_fields
    }
    valid = [row["accepted"] for row in records]
    return {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "benchmark": "synthetic single-account optimizer; actual ProcessSupervisor spawn worker plus owner validation",
        "scenario": scenario,
        "fixture": {
            "held_positions": records[0].get("held_position_count") if records else None,
            "securities": records[0].get("security_count") if records else None,
            "lots": records[0].get("lot_count") if records else None,
            "available_lots": records[0].get("available_lot_count") if records else None,
            "controlled_restrictions": records[0].get("controlled_restrictions")
            if records
            else None,
            "seed_start": seed,
            "trial_count": trials,
            "seed_variants_change_basis_data": True,
            "description": "Synthetic one-account taxable portfolio; scenario restrictions and available-lot counts (available_shares > 0) are disclosed per trial; actual optimizer eligibility counts are not measured. No broker, database, or network access.",
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
            "git_commit": subprocess.run(  # noqa: ASYNC221
                ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
            ).stdout.strip(),
            "memory_note": "Per-trial child_peak_rss_bytes uses getrusage(RUSAGE_SELF); includes native allocations and process baseline, not exact incremental allocations. Null where unsupported.",
        },
        "targets": {
            "screening_p95_seconds": 1.0,
            "continuous_solve_p95_seconds": 3.0,
            "round_repair_validate_rank_p95_seconds": 2.0,
            "complete_p95_seconds": 10.0,
            "timing_labels": {
                "continuous_solve_including_model_construction_seconds": "Includes model construction; no production instrumentation split.",
                "total_with_validation_seconds": "Includes fixture construction and setup; no setup time excluded.",
            },
            "phase2_target_note": "Combined repair plus core validation/ranking plus independent Decimal validation is assessed against 2s; original components remain available.",
        },
        "validation": {
            "status_semantics": "Only ready results independently validated as accepted before the overall deadline count as feasible; errors and no-trade outcomes remain explicit.",
        },
        "timings": summaries,
        "outcomes": {
            "accepted_count": sum(valid),
            "rejected_count": len(valid) - sum(valid),
            "independently_validated_count": sum(
                bool(row.get("independently_validated")) for row in records
            ),
            "feasible_nonempty_count": sum(
                row["accepted"] and row["leg_count"] > 0 for row in records
            ),
            "results": records,
        },
        "target_assessment": {
            "assessment_population": "successful independently accepted trials only; failed/error rows are retained and do not count as passes",
            "screening_under_1s": _assess(records, "screening_seconds", 1.0),
            "continuous_solve_including_model_construction_under_3s": _assess(
                records, "continuous_solve_including_model_construction_seconds", 3.0
            ),
            "complete_under_10s": _assess(records, "total_with_validation_seconds", 10.0),
            "repair_all_validation_rank_under_2s": _assess(
                records, "repair_all_validation_rank_seconds", 2.0
            ),
            "benchmark_acceptance": False,
            "integer_search_status": "incomplete or gap unavailable; not a full integer-optimality claim",
            "unmeasured_deferred": [
                "Missing candidate and constraint counts.",
                "Continuous-solve model-construction split.",
                "Persistence and response overhead.",
                "Process-tree memory.",
                "Fine-grained profiling and live-data performance.",
            ],
            "acceptance_blockers": [
                "Integer search incomplete or optimality gap unavailable; recommendations are not represented as globally integer-optimal.",
                f"{sum(bool(row.get('error')) for row in records)} trial(s) failed; see retained per-trial errors.",
                "Measurements are synthetic and incomplete; benchmark_acceptance remains false.",
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
    parser.add_argument(
        "--scenario",
        choices=("baseline", "replacement_buy", "recent_loss"),
        default="baseline",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    if args.trials < 1:
        parser.error("--trials must be positive")
    report = asyncio.run(run_benchmark(args.trials, args.seed, scenario=args.scenario))
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
