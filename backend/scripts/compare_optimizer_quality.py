"""Compare the real bounded optimizer against exact tiny synthetic reference cases.

This is provisional measurement tooling, not an acceptance benchmark. It performs no network,
broker, or database access and reports synthetic fixtures separately from production evidence.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import platform
import subprocess
import sys
import time
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import cvxpy

from app.domain.decimal_math import exact_sum
from app.domain.exposure import aggregate_lookthrough_exposure
from app.optimizer.core import OPTIMIZER_IMPLEMENTATION_VERSION, OptimizerRequest, optimize_worker
from app.optimizer.runtime import ProcessSupervisor
from app.optimizer.validation import CandidateValidation, validate_candidate
from tests.optimizer_quality_cases import (
    CASE_FAMILIES,
    SmallQualityCase,
    build_small_quality_case,
)
from tests.optimizer_quality_reference import (
    ReferenceCandidate,
    SmallCaseSearchResult,
    enumerate_small_case,
)

PROTOCOL_VERSION = "offline-optimizer-quality-protocol-v1"
HARNESS_VERSION = "offline-small-quality-comparison-v1"
DEFAULT_SEED = 20261113
DEFAULT_CASE_COUNT = len(CASE_FAMILIES)
DEFAULT_MAX_ASSIGNMENTS = 512
DEFAULT_REFERENCE_SECONDS = 2.0
DEFAULT_PRODUCTION_SECONDS = 10.0
DEFAULT_VALIDATION_RESERVE_SECONDS = 2.0


class CaseConfigurationError(ValueError):
    """Raised when a requested run exceeds the declared finite comparison bounds."""


def nearest_rank(values: list[Decimal], percentile: Decimal) -> Decimal | None:
    """Return the nearest-rank percentile without interpolating or extrapolating."""
    if not values:
        return None
    if not Decimal(0) < percentile <= Decimal(1):
        raise ValueError("percentile must be in (0, 1]")
    ordered = sorted(values)
    index = math.ceil(len(ordered) * float(percentile)) - 1
    return ordered[index]


def median(values: list[Decimal]) -> Decimal | None:
    """Return the exact median, averaging the two middle Decimal values when needed."""
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / Decimal(2)


def objective_gap_percent(
    objective_delta: Decimal | None, reference_objective: Decimal | None
) -> Decimal | None:
    """Return a signed objective-gap percentage only for positive reference objectives."""
    if objective_delta is None or reference_objective is None or reference_objective <= 0:
        return None
    return objective_delta / reference_objective * Decimal(100)


def _decimal(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _package_version(package: str) -> str | None:
    try:
        return version(package)
    except PackageNotFoundError:
        return None


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_value(*args: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            check=True,
            capture_output=True,
            text=True,
            cwd=_repo_root(),
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip() or None


def _leg_json(legs: tuple[Any, ...]) -> list[dict[str, Any]]:
    return [
        {
            "leg_id": leg.leg_id,
            "side": leg.side,
            "ticker": leg.ticker,
            "shares": str(leg.shares),
            "estimated_unit_price_usd": str(leg.estimated_unit_price_usd),
            "selected_lots": [
                {"broker_lot_id": lot.broker_lot_id, "shares": str(lot.shares)}
                for lot in leg.selected_lots
            ],
            "depends_on_leg_ids": list(leg.depends_on_leg_ids),
            "sequence": leg.sequence,
        }
        for leg in legs
    ]


def _validation_json(validation: CandidateValidation, completed: bool = True) -> dict[str, Any]:
    evaluation = validation.evaluation
    tax = validation.tax
    return {
        "completed": completed,
        "accepted": validation.accepted,
        "reasons": list(validation.reasons),
        "objective_value": _decimal(validation.objective_value),
        "estimated_tax_benefit_usd": _decimal(validation.estimated_tax_benefit_usd),
        "estimated_trading_cost_usd": _decimal(validation.estimated_trading_cost_usd),
        "incremental_tax_cost_usd": (
            _decimal(tax.incremental_tax_cost_usd) if tax is not None else None
        ),
        "realized_st_usd": _decimal(evaluation.realized_st_usd) if evaluation else None,
        "realized_lt_usd": _decimal(evaluation.realized_lt_usd) if evaluation else None,
    }


def _candidate_json(candidate: ReferenceCandidate | None) -> dict[str, Any] | None:
    if candidate is None:
        return None
    return {
        "legs": _leg_json(candidate.legs),
        "validation": _validation_json(candidate.validation, candidate.validation_completed),
        "feasible": candidate.feasible,
    }


def _bound_json(case: SmallQualityCase) -> dict[str, Any]:
    return {
        "sells": [
            {
                "ticker": bound.ticker,
                "broker_lot_id": bound.broker_lot_id,
                "max_whole_shares": bound.max_shares,
            }
            for bound in case.universe.sells
        ],
        "buys": [
            {"ticker": bound.ticker, "max_whole_shares": bound.max_shares}
            for bound in case.universe.buys
        ],
    }


def _production_domain_check(case: SmallQualityCase, legs: tuple[Any, ...]) -> dict[str, Any]:
    """Check actual worker legs against the declared finite quantity domain; never clip them."""
    sell_bounds = {
        (bound.ticker.upper(), bound.broker_lot_id): bound.max_shares
        for bound in case.universe.sells
    }
    sell_max_by_ticker: dict[str, int] = defaultdict(int)
    for (ticker, _lot_id), maximum in sell_bounds.items():
        sell_max_by_ticker[ticker] += maximum
    buy_bounds = {bound.ticker.upper(): bound.max_shares for bound in case.universe.buys}
    seen_sell_tickers: set[str] = set()
    seen_buy_tickers: set[str] = set()
    sell_totals: dict[str, Decimal] = defaultdict(Decimal)
    reasons: list[str] = []

    for leg in legs:
        ticker = leg.ticker.strip().upper()
        if not leg.shares.is_finite() or leg.shares <= 0:
            reasons.append(f"invalid_quantity:{leg.side}:{ticker}")
            continue
        if leg.shares != leg.shares.to_integral_value():
            reasons.append(f"fractional_quantity:{leg.side}:{ticker}")
            continue
        if leg.side == "SELL":
            if ticker in seen_sell_tickers:
                reasons.append(f"duplicate_sell_leg:{ticker}")
            seen_sell_tickers.add(ticker)
            if not leg.selected_lots:
                reasons.append(f"sell_without_lots:{ticker}")
            allocated = Decimal(0)
            seen_lots: set[str] = set()
            for allocation in leg.selected_lots:
                lot_id = allocation.broker_lot_id
                bound_maximum = sell_bounds.get((ticker, lot_id))
                if bound_maximum is None:
                    reasons.append(f"sell_lot_outside_universe:{ticker}:{lot_id}")
                    continue
                if lot_id in seen_lots:
                    reasons.append(f"duplicate_sell_lot:{ticker}:{lot_id}")
                seen_lots.add(lot_id)
                if (
                    not allocation.shares.is_finite()
                    or allocation.shares <= 0
                    or allocation.shares != allocation.shares.to_integral_value()
                ):
                    reasons.append(f"invalid_sell_lot_quantity:{ticker}:{lot_id}")
                elif allocation.shares > bound_maximum:
                    reasons.append(f"sell_lot_quantity_exceeds_bound:{ticker}:{lot_id}")
                allocated += allocation.shares
            if allocated != leg.shares:
                reasons.append(f"sell_leg_lot_total_mismatch:{ticker}")
            sell_totals[ticker] += leg.shares
        elif leg.side == "BUY":
            if ticker in seen_buy_tickers:
                reasons.append(f"duplicate_buy_leg:{ticker}")
            seen_buy_tickers.add(ticker)
            maximum = buy_bounds.get(ticker)
            if maximum is None:
                reasons.append(f"buy_ticker_outside_universe:{ticker}")
            elif leg.shares > maximum:
                reasons.append(f"buy_quantity_exceeds_bound:{ticker}")
        else:
            reasons.append(f"unsupported_side:{leg.side}:{ticker}")

    for ticker, shares in sell_totals.items():
        if shares > sell_max_by_ticker.get(ticker, 0):
            reasons.append(f"sell_ticker_quantity_exceeds_bound:{ticker}")
    return {"in_domain": not reasons, "reasons": reasons}




def _allocation_drift_for_inputs(
    inputs: Any, validation: CandidateValidation
) -> Decimal | None:
    evaluation = validation.evaluation
    if evaluation is None:
        return None
    sleeves = {row.key: row for row in inputs.policy.allocation.sleeves if row.enabled}
    values = dict(evaluation.proposed.sleeve_values_usd)
    total = evaluation.proposed.portfolio_total_usd
    drifts: list[Decimal] = []
    for target in evaluation.allocation.target.sleeves:
        row = sleeves[target.sleeve_key]
        if row.parent_key is None:
            denominator = total
            target_weight = target.target_whole_portfolio_pct
        else:
            denominator = values.get(row.parent_key, Decimal(0))
            target_weight = target.target_within_parent_pct
        if denominator <= 0:
            return None
        observed = values.get(row.key, Decimal(0)) / denominator * Decimal(100)
        drifts.append(abs(observed - target_weight))
    return max(drifts) if drifts else Decimal(0)


def _sector_drift_pp(inputs: Any, validation: CandidateValidation) -> Decimal | None:
    evaluation = validation.evaluation
    if evaluation is None:
        return None
    invested = exact_sum(row.market_value_usd for row in evaluation.proposed.positions)
    if invested <= 0:
        return None
    sector_values: dict[str, list[Decimal]] = defaultdict(list)
    for position in evaluation.proposed.positions:
        aggregate = aggregate_lookthrough_exposure(
            inputs, tickers=(position.ticker,), dimension="sector"
        )
        if aggregate.coverage.complete is not True:
            return None
        unit_total = exact_sum(row.value_usd for row in aggregate.values)
        if unit_total <= 0:
            return None
        for row in aggregate.values:
            sector_values[row.exposure_key].append(
                position.market_value_usd * row.value_usd / unit_total
            )
    values = {key: exact_sum(parts) for key, parts in sector_values.items()}
    drifts: list[Decimal] = []
    for band in inputs.policy.sector_bands:
        observed = values.get(band.sector_key, Decimal(0)) / invested * Decimal(100)
        drifts.append(abs(observed - band.target_weight_pct))
    return max(drifts) if drifts else None


def _economic_metrics(inputs: Any, validation: CandidateValidation) -> dict[str, Decimal | None]:
    tax = validation.tax
    return {
        "objective": validation.objective_value,
        "incremental_tax_cost_usd": tax.incremental_tax_cost_usd if tax else None,
        "estimated_tax_benefit_usd": validation.estimated_tax_benefit_usd,
        "estimated_trading_cost_usd": validation.estimated_trading_cost_usd,
        "allocation_max_target_drift_pp": _allocation_drift_for_inputs(inputs, validation),
        "sector_max_target_drift_pp": _sector_drift_pp(inputs, validation),
    }


def _metric_summary(rows: list[tuple[str, Decimal]]) -> dict[str, Any]:
    values = [value for _, value in rows]
    absolute = [abs(value) for value in values]
    return {
        "samples": len(values),
        "min_absolute_delta": _decimal(min(absolute)) if absolute else None,
        "median_absolute_delta": _decimal(median(absolute)),
        "p95_absolute_delta_nearest_rank": _decimal(nearest_rank(absolute, Decimal("0.95"))),
        "worst_absolute_delta": _decimal(max(absolute)) if absolute else None,
        "min_signed_delta": _decimal(min(values)) if values else None,
        "median_signed_delta": _decimal(median(values)),
        "nearest_rank_rule": "sorted absolute deltas; rank=ceil(n*0.95), one-indexed",
        "case_deltas": [{"case_id": case_id, "production_minus_reference": str(value)} for case_id, value in rows],
    }


def _reference_json(result: SmallCaseSearchResult) -> dict[str, Any]:
    optimum = result.exact_optimum
    return {
        "complete": result.complete,
        "stop_reason": result.stop_reason,
        "theoretical_assignment_count": result.theoretical_assignment_count,
        "assignments_examined": result.assignments_examined,
        "canonical_baskets_examined": result.canonical_baskets_examined,
        "feasible_basket_count": result.feasible_basket_count,
        "max_assignments": result.max_assignments,
        "time_limit_seconds": result.time_limit_seconds,
        "elapsed_seconds": result.elapsed_seconds,
        "incumbent": _candidate_json(result.incumbent),
        "best_observed": _candidate_json(result.best_observed),
        "exact_optimum": _candidate_json(optimum),
    }


def _production_json(
    case: SmallQualityCase,
    status: str,
    legs: tuple[Any, ...],
    validation: CandidateValidation | None,
    validation_completed: bool,
    wall_seconds: float,
    validation_seconds: float | None,
    error: Exception | None,
    metadata: Any | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    domain = _production_domain_check(case, legs)
    owner_valid = bool(validation and validation_completed and validation.accepted)
    output_candidate = status in {"ready", "no_trade"} and owner_valid
    in_domain_candidate = output_candidate and domain["in_domain"]
    production = {
        "status": status,
        "legs": _leg_json(legs),
        "independently_revalidated": validation_completed,
        "owner_validation": _validation_json(validation, validation_completed) if validation else None,
        "returned_legs_in_declared_domain": domain["in_domain"],
        "domain_exclusion_reasons": domain["reasons"],
        "owner_valid_candidate": owner_valid,
        "candidate_comparable_in_domain": in_domain_candidate,
        "supervisor_wall_seconds": wall_seconds,
        "independent_validation_seconds": validation_seconds,
        "reported_input_checksum": getattr(metadata, "source_checksum", None),
        "implementation_version": getattr(metadata, "implementation_version", None),
        "solver": getattr(metadata, "solver", None),
        "solver_versions": [list(row) for row in getattr(metadata, "solver_versions", ())],
        "metadata_warnings": list(getattr(metadata, "warnings", ())),
        "error_type": type(error).__name__ if error else None,
        "error": str(error) if error else None,
    }
    internal = {
        "domain": domain,
        "candidate": in_domain_candidate,
        "owner_validation": validation,
        "validation_completed": validation_completed,
    }
    return production, internal


async def _compare_case(
    case: SmallQualityCase,
    supervisor: ProcessSupervisor,
    *,
    max_assignments: int,
    reference_time_limit_seconds: float,
    production_timeout_seconds: float,
    validation_reserve_seconds: float,
) -> dict[str, Any]:
    production_started = time.perf_counter()
    production_status = "failed"
    production_legs: tuple[Any, ...] = ()
    production_validation: CandidateValidation | None = None
    validation_completed = False
    validation_seconds: float | None = None
    production_error: Exception | None = None
    metadata: Any | None = None
    process_elapsed = 0.0

    try:
        worker_result = await supervisor.run(
            OptimizerRequest(case.inputs),
            optimize_worker,
            timeout_seconds=production_timeout_seconds,
            validation_reserve_seconds=validation_reserve_seconds,
        )
        process_elapsed = time.perf_counter() - production_started
        result = worker_result.value
        production_status = result.status
        production_legs = tuple(result.legs)
        metadata = result.metadata
        validation_started = time.perf_counter()
        production_validation = validate_candidate(
            case.inputs, production_legs, deadline=worker_result.overall_deadline
        )
        validation_seconds = time.perf_counter() - validation_started
        validation_completed = (
            "validation_deadline_exceeded" not in production_validation.reasons
            and time.monotonic() < worker_result.overall_deadline
        )
        if not validation_completed:
            production_error = TimeoutError("owner revalidation did not complete before overall deadline")
    except Exception as error:  # noqa: BLE001 — preserve per-case production failures in the report.
        production_error = error
        process_elapsed = time.perf_counter() - production_started

    production, production_internal = _production_json(
        case,
        production_status,
        production_legs,
        production_validation,
        validation_completed,
        process_elapsed,
        validation_seconds,
        production_error,
        metadata,
    )

    reference_started = time.perf_counter()
    reference_result: SmallCaseSearchResult | None = None
    reference_error: Exception | None = None
    try:
        reference_result = enumerate_small_case(
            case.inputs,
            case.universe,
            max_assignments=max_assignments,
            time_limit_seconds=reference_time_limit_seconds,
        )
    except Exception as error:  # noqa: BLE001 — preserve per-case reference failures.
        reference_error = error
    reference_wall_seconds = time.perf_counter() - reference_started

    exact = bool(reference_result and reference_result.complete)
    reference_optimum = reference_result.exact_optimum if exact and reference_result else None
    reference_feasible_count = reference_result.feasible_basket_count if reference_result else 0
    reference_json = _reference_json(reference_result) if reference_result else {
        "complete": False,
        "stop_reason": "error",
        "error_type": type(reference_error).__name__ if reference_error else "unknown",
        "error": str(reference_error) if reference_error else "reference result unavailable",
        "elapsed_seconds": reference_wall_seconds,
        "theoretical_assignment_count": None,
        "assignments_examined": None,
        "canonical_baskets_examined": None,
        "feasible_basket_count": None,
        "exact_optimum": None,
    }
    optimum_validation = reference_optimum.validation if reference_optimum else None
    production_validation = production_internal["owner_validation"]
    denominator_eligible = bool(
        exact
        and production_internal["domain"]["in_domain"]
        and production.get("reported_input_checksum") in (None, case.inputs.source_checksum)
    )
    production_candidate = bool(denominator_eligible and production_internal["candidate"])
    missed_feasibility = bool(
        denominator_eligible and reference_feasible_count > 0 and not production_candidate
    )
    no_reference_feasible = bool(exact and reference_feasible_count == 0)
    missed_improvement: bool | None = None
    deltas: dict[str, str | None] = {}
    objective_gap_pct: Decimal | None = None
    if (
        denominator_eligible
        and reference_optimum is not None
        and production_candidate
        and production_validation is not None
        and optimum_validation is not None
    ):
        production_metrics = _economic_metrics(case.inputs, production_validation)
        reference_metrics = _economic_metrics(case.inputs, optimum_validation)
        for name, production_value in production_metrics.items():
            reference_value = reference_metrics[name]
            deltas[name] = (
                str(production_value - reference_value)
                if production_value is not None and reference_value is not None
                else None
            )
        prod_objective = production_metrics["objective"]
        ref_objective = reference_metrics["objective"]
        if isinstance(prod_objective, Decimal) and isinstance(ref_objective, Decimal):
            objective_delta = prod_objective - ref_objective
            objective_gap_pct = objective_gap_percent(objective_delta, ref_objective)
            missed_improvement = prod_objective > ref_objective

    return {
        "case_id": case.case_id,
        "fixture_version": case.fixture_version,
        "family": case.family,
        "seed": case.seed,
        "description": case.description,
        "input_checksum_sha256": case.inputs.source_checksum,
        "policy_revision_id": case.inputs.policy.revision_id,
        "source_generation": case.inputs.source_generation,
        "source_metadata_complete": {
            "sync": case.inputs.source_metadata.sync_complete,
            "transaction_history": case.inputs.source_metadata.transaction_history_complete,
            "lookthrough": case.inputs.source_metadata.lookthrough_complete,
        },
        "bounds": _bound_json(case),
        "reference": reference_json,
        "reference_wall_seconds": reference_wall_seconds,
        "production": production,
        "comparison": {
            "frozen_inputs_match": production.get("reported_input_checksum")
            in (None, case.inputs.source_checksum),
            "exact_small_case_denominator_eligible": denominator_eligible,
            "exclusion_reason": (
                None
                if denominator_eligible
                else "incomplete_or_failed_reference_or_production_outside_domain_or_input_mismatch"
            ),
            "missed_feasibility_case": missed_feasibility,
            "reference_has_no_feasible_basket": no_reference_feasible,
            "missed_improvement_case": missed_improvement,
            "deltas_production_minus_exact_reference": deltas,
            "objective_gap_percent": _decimal(objective_gap_pct),
            "objective_gap_percent_suppressed_nonpositive_reference": bool(
                reference_optimum
                and optimum_validation
                and optimum_validation.objective_value is not None
                and optimum_validation.objective_value <= 0
            ),
            "out_of_domain_production_candidate": not production_internal["domain"]["in_domain"],
            "reference_cutoff": bool(reference_result and not reference_result.complete),
            "reference_error": reference_error is not None,
        },
    }


def _empty_case_record(family: str, seed: int, error: Exception) -> dict[str, Any]:
    return {
        "case_id": f"{family}-seed-{seed}",
        "family": family,
        "seed": seed,
        "fixture_error": {"type": type(error).__name__, "message": str(error)},
        "reference": {"complete": False, "stop_reason": "fixture_error"},
        "production": {"status": "not_run"},
        "comparison": {
            "exact_small_case_denominator_eligible": False,
            "exclusion_reason": "fixture_error",
            "missed_feasibility_case": False,
            "reference_has_no_feasible_basket": False,
            "missed_improvement_case": None,
            "out_of_domain_production_candidate": False,
            "reference_cutoff": False,
            "reference_error": False,
        },
    }


def _build_summaries(cases: list[dict[str, Any]]) -> dict[str, Any]:
    complete = [row for row in cases if row.get("reference", {}).get("complete") is True]
    eligible = [
        row for row in cases
        if row.get("comparison", {}).get("exact_small_case_denominator_eligible") is True
    ]
    feasible_reference = [
        row for row in eligible
        if row.get("reference", {}).get("feasible_basket_count", 0) > 0
    ]
    missed_feasibility_count = sum(
        bool(row.get("comparison", {}).get("missed_feasibility_case"))
        for row in feasible_reference
    )
    improvement_rows = [
        row for row in eligible
        if row.get("comparison", {}).get("missed_improvement_case") is not None
    ]
    missed_improvement_count = sum(
        bool(row["comparison"]["missed_improvement_case"]) for row in improvement_rows
    )
    out_of_domain = [
        row for row in cases
        if row.get("comparison", {}).get("out_of_domain_production_candidate") is True
    ]
    cutoffs = [row for row in cases if row.get("comparison", {}).get("reference_cutoff") is True]
    no_feasible = [
        row for row in cases
        if row.get("comparison", {}).get("reference_has_no_feasible_basket") is True
    ]
    metric_keys = (
        "objective",
        "incremental_tax_cost_usd",
        "estimated_tax_benefit_usd",
        "estimated_trading_cost_usd",
        "allocation_max_target_drift_pp",
        "sector_max_target_drift_pp",
    )
    metric_summaries: dict[str, Any] = {}
    for key in metric_keys:
        delta_rows: list[tuple[str, Decimal]] = []
        for row in eligible:
            value = row.get("comparison", {}).get("deltas_production_minus_exact_reference", {}).get(key)
            if value is not None:
                delta_rows.append((row["case_id"], Decimal(value)))
        metric_summaries[key] = _metric_summary(delta_rows)
    return {
        "case_count": len(cases),
        "reference_complete_count": len(complete),
        "reference_cutoff_count": len(cutoffs),
        "reference_error_count": sum(
            bool(row.get("comparison", {}).get("reference_error")) for row in cases
        ),
        "exact_small_case_denominator_eligible_count": len(eligible),
        "out_of_domain_production_case_count": len(out_of_domain),
        "out_of_domain_case_ids": [row["case_id"] for row in out_of_domain],
        "reference_no_feasible_basket_count": len(no_feasible),
        "reference_no_feasible_case_ids": [row["case_id"] for row in no_feasible],
        "missed_feasibility": {
            "numerator": missed_feasibility_count,
            "denominator": len(feasible_reference),
            "synthetic_case_fraction_not_probability": (
                str(Decimal(missed_feasibility_count) / Decimal(len(feasible_reference)))
                if feasible_reference
                else None
            ),
            "eligible_case_ids": [row["case_id"] for row in feasible_reference],
        },
        "missed_improvement": {
            "numerator": missed_improvement_count,
            "denominator": len(improvement_rows),
            "synthetic_case_fraction_not_probability": (
                str(Decimal(missed_improvement_count) / Decimal(len(improvement_rows)))
                if improvement_rows
                else None
            ),
            "eligible_case_ids": [row["case_id"] for row in improvement_rows],
        },
        "metric_deltas": metric_summaries,
        "objective_percentage_suppression_count": sum(
            bool(row.get("comparison", {}).get("objective_gap_percent_suppressed_nonpositive_reference"))
            for row in eligible
        ),
        "objective_percentage_available_count": sum(
            row.get("comparison", {}).get("objective_gap_percent") is not None for row in eligible
        ),
        "missed_feasibility_not_mixed_with_missed_improvement": True,
        "p95_rule": "nearest rank: sorted absolute deltas, rank=ceil(n*0.95), one-indexed",
    }


def _validate_run_bounds(
    case_count: int,
    max_assignments: int,
    reference_time_limit_seconds: float,
    production_timeout_seconds: float,
    validation_reserve_seconds: float,
) -> None:
    if isinstance(case_count, bool) or not 1 <= case_count <= len(CASE_FAMILIES):
        raise CaseConfigurationError(f"case_count must be in [1, {len(CASE_FAMILIES)}]")
    if isinstance(max_assignments, bool) or max_assignments < 1:
        raise CaseConfigurationError("max_assignments must be a positive integer")
    if not math.isfinite(reference_time_limit_seconds) or not 0 < reference_time_limit_seconds <= 10:
        raise CaseConfigurationError("reference_time_limit_seconds must be finite and in (0, 10]")
    if not math.isfinite(production_timeout_seconds) or not 0 < production_timeout_seconds <= 10:
        raise CaseConfigurationError("production_timeout_seconds must be finite and in (0, 10]")
    if (
        not math.isfinite(validation_reserve_seconds)
        or validation_reserve_seconds < 0
        or validation_reserve_seconds >= production_timeout_seconds
    ):
        raise CaseConfigurationError(
            "validation_reserve_seconds must be finite, nonnegative, and less than production timeout"
        )


async def run_comparison(
    *,
    case_count: int = DEFAULT_CASE_COUNT,
    seed: int = DEFAULT_SEED,
    max_assignments: int = DEFAULT_MAX_ASSIGNMENTS,
    reference_time_limit_seconds: float = DEFAULT_REFERENCE_SECONDS,
    production_timeout_seconds: float = DEFAULT_PRODUCTION_SECONDS,
    validation_reserve_seconds: float = DEFAULT_VALIDATION_RESERVE_SECONDS,
) -> dict[str, Any]:
    """Run actual spawned optimizer workers and bounded reference enumerations per case."""
    _validate_run_bounds(
        case_count,
        max_assignments,
        reference_time_limit_seconds,
        production_timeout_seconds,
        validation_reserve_seconds,
    )
    supervisor = ProcessSupervisor(max_workers=1)
    records: list[dict[str, Any]] = []
    try:
        for index, family in enumerate(CASE_FAMILIES[:case_count]):
            case_seed = seed + index
            try:
                case = build_small_quality_case(family, case_seed)
            except Exception as error:  # noqa: BLE001 — fixture failure remains one case record.
                records.append(_empty_case_record(family, case_seed, error))
                continue
            try:
                records.append(
                    await _compare_case(
                        case,
                        supervisor,
                        max_assignments=max_assignments,
                        reference_time_limit_seconds=reference_time_limit_seconds,
                        production_timeout_seconds=production_timeout_seconds,
                        validation_reserve_seconds=validation_reserve_seconds,
                    )
                )
            except Exception as error:  # noqa: BLE001 — one case never aborts the full batch.
                records.append(_empty_case_record(family, case_seed, error))
    finally:
        await supervisor.aclose()

    root = _repo_root()
    reference_path = root / "tests" / "optimizer_quality_reference.py"
    validator_path = root / "app" / "optimizer" / "validation.py"
    core_path = root / "app" / "optimizer" / "core.py"
    reference_commit = _git_value("log", "-1", "--format=%H", "--", "backend/tests/optimizer_quality_reference.py")
    current_commit = _git_value("rev-parse", "HEAD")
    return {
        "schema": "offline-small-quality-comparison-v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "assessment_status": "PROVISIONAL_NOT_ACCEPTANCE",
        "acceptance_claim": False,
        "protocol_version": PROTOCOL_VERSION,
        "harness_version": HARNESS_VERSION,
        "run_bounds": {
            "case_count_requested": case_count,
            "case_count_run": len(records),
            "seed_start": seed,
            "reference_max_assignments": max_assignments,
            "reference_time_limit_seconds_per_case": reference_time_limit_seconds,
            "production_total_timeout_seconds": production_timeout_seconds,
            "production_owner_validation_reserve_seconds": validation_reserve_seconds,
            "production_process_supervisor_max_workers": 1,
        },
        "implementation_versions": {
            "production_core_version": OPTIMIZER_IMPLEMENTATION_VERSION,
            "production_core_source_sha256": _sha256(core_path),
            "owner_validator_source_sha256": _sha256(validator_path),
            "reference_source_sha256": _sha256(reference_path),
            "reference_file_last_commit": reference_commit,
            "repository_head_at_report_generation": current_commit,
            "reference_protocol_source": "docs/optimizer_quality_protocol.md",
            "reference_protocol_source_sha256": _sha256(root.parent / "docs" / "optimizer_quality_protocol.md"),
            "pending_reference_fix_commit_reported_by_parent": "98b6efe8",
            "known_reference_p1": {
                "status": "pending_fix_and_fresh_review",
                "finding": "Alphabetical SELL sequencing can miss executable bounded assignments when a fixed fee and zero cash make order sequence affect cash feasibility.",
                "example": "AAA $1 then ZZZ $10 with $3 fee can fail cash while ZZZ then AAA leaves $5; the oracle must enumerate/order these semantics correctly.",
                "report_interpretation": "All exact-reference comparisons remain provisional until the separate reference fix commit is present and freshly reviewed.",
            },
        },
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "cvxpy": cvxpy.__version__,
            "solver_packages": {
                package: _package_version(package) for package in ("osqp", "scipy", "numpy")
            },
        },
        "comparison_semantics": {
            "production_execution": "Actual app.optimizer.core.optimize_worker in a spawned ProcessSupervisor process; no mocked solver.",
            "production_deadline": "Same configured total timeout, with the declared owner-validation reserve and independent request-owner validate_candidate call before the overall deadline.",
            "reference": "Exhaustive assignments and canonical baskets only within explicit SELL/BUY bounds, max assignments, and reference time cap; exact optimum exists only when complete.",
            "owner_validation_shared": "Production and reference share validate_candidate; this is not independent proof of tax/accounting semantics.",
            "common_domain": "Production legs are checked against explicit lot/ticker quantities. Out-of-domain legs are never clipped and are excluded from exact denominators.",
            "no_trade": "The no-trade vector remains part of the finite reference domain and production no_trade counts only after owner acceptance.",
            "synthetic_frequency": "All case fractions describe these deterministic synthetic fixtures only; they are not user, market, or production probabilities.",
            "tax_benefit_sign": "Tax-benefit deltas are production minus reference; interpret sign according to the owner's benefit convention.",
            "positive_cost_sign": "Incremental tax-cost and estimated trading-cost deltas are production minus reference; positive cost deltas are worse.",
            "fixed_fee_proxy_limitation": "The convex search proxy allocates configured per-order fee proportionally across potential quantities; owner validation charges actual consolidated order fees. Any resulting gap is provisional.",
            "nested_allocation_limitation": "Nested-allocation cases remain provisional; the owner validator scores exact frozen targets, but this comparison does not establish search quality outside each enumerated universe.",
        },
        "summary": _build_summaries(records),
        "cases": records,
        "limitations": [
            "Small illustrative synthetic cases only; no captured brokerage data, and fixture frequencies are not live probabilities.",
            "The explicit finite candidate universe is not representative of the full trade space and can omit a better feasible basket.",
            "Reference completeness is conditional on assignment, canonicalization, owner-validation, and time caps; cutoff cases are reported separately.",
            "Owner validator is shared between production and reference; financial semantics require separate review.",
            "Known reference SELL-order sequencing P1 and provisional convex fee/nested allocation proxies prevent acceptance claims.",
            "Do not use the tiny fixtures to select acceptance thresholds or claim benchmark success.",
        ],
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-count", type=int, default=DEFAULT_CASE_COUNT)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--max-reference-assignments", type=int, default=DEFAULT_MAX_ASSIGNMENTS)
    parser.add_argument("--reference-time-limit-seconds", type=float, default=DEFAULT_REFERENCE_SECONDS)
    parser.add_argument("--production-timeout-seconds", type=float, default=DEFAULT_PRODUCTION_SECONDS)
    parser.add_argument("--validation-reserve-seconds", type=float, default=DEFAULT_VALIDATION_RESERVE_SECONDS)
    parser.add_argument("--output", type=Path, help="Optional JSON report destination; stdout when omitted.")
    args = parser.parse_args()
    try:
        _validate_run_bounds(
            args.case_count,
            args.max_reference_assignments,
            args.reference_time_limit_seconds,
            args.production_timeout_seconds,
            args.validation_reserve_seconds,
        )
    except (CaseConfigurationError, TypeError) as error:
        parser.error(str(error))
    return args


def main() -> None:
    args = _parse_args()
    report = asyncio.run(
        run_comparison(
            case_count=args.case_count,
            seed=args.seed,
            max_assignments=args.max_reference_assignments,
            reference_time_limit_seconds=args.reference_time_limit_seconds,
            production_timeout_seconds=args.production_timeout_seconds,
            validation_reserve_seconds=args.validation_reserve_seconds,
        )
    )
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output is None:
        print(rendered)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
        print(json.dumps({"output": str(args.output), "summary": report["summary"]}, indent=2))


if __name__ == "__main__":
    main()
