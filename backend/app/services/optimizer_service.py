"""Owner-side production optimizer orchestration, validation, and persistence.

The child process never writes database state. Candidate legs are published only
when the independent request-owner validator and the source-currentness checks
both pass within the ProcessSupervisor's shared deadline.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4, uuid5

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.db.models import (
    Account,
    ActivityEvent,
    OptimizerRun,
    RecommendationGroup,
    RecommendationGroupLeg,
    RecommendationLeg,
    RecommendationSelectedLot,
    Security,
    SyncState,
)
from app.domain.allocation import resolve_holding
from app.domain.decimal_math import exact_difference, exact_product, exact_sum
from app.domain.financial_inputs import FinancialInputs, PolicySettings
from app.domain.portfolio_accounting import ConsolidatedLeg
from app.domain.trade_dates import classify_holding_period, resolve_proposed_trade_date
from app.optimizer.runtime import (
    DEFAULT_TIMEOUT_SECONDS,
    ProcessSupervisor,
    WorkerCapacityError,
    WorkerResult,
    WorkerTimeoutError,
)
from app.schemas import (
    OptimizerLotReviewIntentInput,
    OptimizerRunInput,
    OptimizerSelectionInput,
    RecommendationAnnotationInput,
)
from app.services.demo_optimizer import _active_policy, _frozen_input, _run_display_context
from app.services.errors import AppError

_BATCH_LIMIT_KEYS = (
    "max_sell_tickers_per_batch",
    "max_sell_lots_per_batch",
    "max_total_orders_per_batch",
)


@dataclass(frozen=True, slots=True)
class ValidatedOptimizerCandidate:
    candidate: object
    validation: object | None
    overall_deadline: float
    status: str


@dataclass(frozen=True, slots=True)
class PreparedOptimizerRun:
    inputs: FinancialInputs
    batch_settings: dict[str, object]
    frozen_input_bundle: dict[str, object]
    input_fingerprint: str
    policy_revision_id: str
    source_generation: int
    as_of: datetime
    proposed_trade_date: date


@dataclass(frozen=True, slots=True)
class _RunState:
    run_id: str
    input_fingerprint: str
    source_generation: int
    basket_revision: int
    prepared: PreparedOptimizerRun
    group_rows: tuple[dict[str, Any], ...]
    selection_universe: dict[str, list[str]]


@dataclass(frozen=True, slots=True)
class _OwnerValidationInput:
    validator: Callable[..., object]
    args: tuple[object, ...]
    original_deadline: float


def _owner_validation_worker(worker_input: _OwnerValidationInput, deadline: float) -> object:
    """Run pure owner validation in a child that the supervisor can terminate."""
    validation_deadline = min(worker_input.original_deadline, deadline)
    return worker_input.validator(*worker_input.args, deadline=validation_deadline)


class BoundedValidationExecutor:
    """Run pure owner validation with bounded, killable, non-queued capacity."""

    def __init__(self, max_workers: int = 2) -> None:
        self._supervisor = ProcessSupervisor(max_workers=max_workers)

    async def run(self, validator: Callable[..., object], *args: object, deadline: float) -> object:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise WorkerTimeoutError("optimizer owner validation missed the shared deadline")
        worker_input = _OwnerValidationInput(validator, args, deadline)
        result: WorkerResult[object] = await self._supervisor.run(
            worker_input,
            _owner_validation_worker,
            timeout_seconds=min(remaining, DEFAULT_TIMEOUT_SECONDS),
            validation_reserve_seconds=0,
        )
        if time.monotonic() >= deadline:
            raise WorkerTimeoutError("optimizer owner validation missed the shared deadline")
        return result.value

    async def aclose(self) -> None:
        await self._supervisor.aclose()


def _fingerprint_bundle(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


def apply_run_batch_limits(
    inputs: FinancialInputs, request: object
) -> tuple[FinancialInputs, dict[str, object]]:
    """Apply request limits as an immutable policy tightening for this saved run."""
    settings = inputs.policy.settings
    configured: dict[str, int] = {}
    for key in _BATCH_LIMIT_KEYS:
        value = settings.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise AppError(
                "optimizer_configuration_required",
                f"A positive {key} policy limit is required before optimization",
                status_code=409,
                details={"setting": key},
            )
        configured[key] = value

    effective = dict(configured)
    for key in _BATCH_LIMIT_KEYS:
        requested = request.get(key) if isinstance(request, Mapping) else getattr(request, key, None)
        if requested is None:
            continue
        if not isinstance(requested, int) or isinstance(requested, bool) or requested <= 0:
            raise AppError(
                "invalid_batch_override",
                "Per-run batch overrides must be positive integers",
                status_code=422,
                details={"setting": key},
            )
        if requested > configured[key]:
            raise AppError(
                "batch_override_exceeds_policy",
                "Per-run batch overrides may tighten but cannot widen the active policy",
                status_code=422,
                details={"setting": key, "policy_limit": configured[key]},
            )
        effective[key] = requested

    setting_values = settings.to_provenance()
    setting_values.update(effective)
    limited_policy = replace(inputs.policy, settings=PolicySettings.from_mapping(setting_values))
    limited_inputs = replace(inputs, policy=limited_policy)
    batch_settings: dict[str, object] = {
        **effective,
        "max_batch_turnover_pct": str(settings.get("max_batch_turnover_pct")),
        "min_buy_order_notional_usd": str(settings.get("min_buy_order_notional_usd")),
        "cash_reserve_usd": str(settings.get("cash_reserve_usd")),
    }
    return limited_inputs, batch_settings


def prepare_optimizer_run(
    session: Session,
    request: OptimizerRunInput,
    *,
    proposed_trade_date: date | None = None,
    batch_limits: Mapping[str, object] | None = None,
) -> PreparedOptimizerRun:
    """Freeze current account/policy inputs and non-widening limits for one real run."""
    account = session.get(Account, 1)
    if account is None:
        raise AppError("account_not_found", "The managed brokerage account was not found", status_code=409)
    sync_state = session.get(SyncState, 1)
    if sync_state is None:
        raise AppError("current_state_unavailable", "A complete current portfolio sync is required", status_code=409)
    policy = _active_policy(session)
    trade_date = proposed_trade_date or resolve_proposed_trade_date(request.proposed_trade_date, demo=False)
    source_inputs = _frozen_input(session, account, sync_state, policy, trade_date)
    optimizer_inputs, effective_batch = apply_run_batch_limits(
        source_inputs, batch_limits if batch_limits is not None else request
    )
    bundle = optimizer_inputs.to_provenance()
    bundle["batch_settings"] = effective_batch
    bundle["mode"] = "real_optimizer"
    fingerprint = _fingerprint_bundle(bundle)
    bundle["input_fingerprint"] = fingerprint
    return PreparedOptimizerRun(
        inputs=optimizer_inputs,
        batch_settings=effective_batch,
        frozen_input_bundle=bundle,
        input_fingerprint=fingerprint,
        policy_revision_id=policy.id,
        source_generation=sync_state.current_generation,
        as_of=optimizer_inputs.account.as_of,
        proposed_trade_date=trade_date,
    )


def assert_optimizer_run_current(
    session: Session,
    prepared: PreparedOptimizerRun,
    *,
    deadline: float | None = None,
) -> None:
    """Re-read policy and portfolio state immediately before atomic publication."""
    limits = {key: prepared.batch_settings[key] for key in _BATCH_LIMIT_KEYS}
    request = OptimizerRunInput(
        mode="real_optimizer",
        proposed_trade_date=prepared.proposed_trade_date,
        **limits,
    )
    current = prepare_optimizer_run(
        session,
        request,
        proposed_trade_date=prepared.proposed_trade_date,
        batch_limits=prepared.batch_settings,
    )
    if (
        current.input_fingerprint != prepared.input_fingerprint
        or current.policy_revision_id != prepared.policy_revision_id
        or current.source_generation != prepared.source_generation
    ):
        raise AppError(
            "stale_optimizer_input",
            "Portfolio inputs or active policy changed while recommendations were being computed",
            status_code=409,
            details={"basket_unchanged": True},
        )
    if deadline is not None and time.monotonic() >= deadline:
        raise WorkerTimeoutError("optimizer publication missed the shared deadline")


def _core_contract() -> tuple[type[Any], Any, Any]:
    """Load worker and validator lazily so deterministic DEMO does not require the core."""
    core = importlib.import_module("app.optimizer.core")
    validation_module = importlib.import_module("app.optimizer.validation")
    return core.OptimizerRequest, core.optimize_worker, validation_module.validate_candidate


class CandidateRejectedError(AppError):
    """A candidate rejected by the solver-free owner validation."""


async def run_validated_candidate(
    inputs: FinancialInputs,
    supervisor: ProcessSupervisor,
    *,
    sell_lot_ids: tuple[str, ...] | None = None,
    validation_executor: BoundedValidationExecutor | None = None,
) -> ValidatedOptimizerCandidate:
    """Run one bounded pass and independently validate ready/no-trade candidates."""
    try:
        request_type, worker, validator = _core_contract()
    except (ImportError, AttributeError) as exc:
        raise AppError(
            "optimizer_core_unavailable",
            "The production optimizer core is not available; no recommendation run was created",
            status_code=503,
            details={"basket_unchanged": True},
        ) from exc

    request = request_type(inputs=inputs, sell_lot_ids=sell_lot_ids)
    worker_result: WorkerResult[object] = await supervisor.run(request, worker)
    candidate = worker_result.value
    candidate_legs = getattr(candidate, "legs", None)
    metadata = getattr(candidate, "metadata", None)
    status = getattr(candidate, "status", None) or getattr(metadata, "status", None)
    if not isinstance(candidate_legs, tuple) or status not in {
        "ready",
        "no_trade",
        "infeasible",
        "configuration_required",
        "deadline_exceeded",
        "search_incomplete",
    }:
        raise AppError(
            "optimizer_core_contract_error",
            "The optimizer worker returned a malformed candidate; no recommendation run was created",
            status_code=502,
            details={"basket_unchanged": True},
        )
    if (status == "ready" and not candidate_legs) or (status != "ready" and candidate_legs):
        raise AppError(
            "optimizer_core_contract_error",
            "The optimizer worker returned legs inconsistent with its terminal status",
            status_code=502,
            details={"basket_unchanged": True},
        )
    if (
        getattr(metadata, "input_generation", None) != inputs.source_generation
        or getattr(metadata, "source_checksum", None) != inputs.source_checksum
    ):
        raise AppError(
            "optimizer_core_provenance_mismatch",
            "The optimizer result does not match the frozen source inputs",
            status_code=502,
            details={"basket_unchanged": True},
        )

    validation: object | None = None
    if status in {"ready", "no_trade"}:
        if validation_executor is None:
            validation = validator(inputs, candidate_legs, deadline=worker_result.overall_deadline)
        else:
            validation = await validation_executor.run(
                validator, inputs, candidate_legs, deadline=worker_result.overall_deadline
            )
        if getattr(validation, "accepted", False) is not True:
            reasons = getattr(validation, "reasons", ())
            raise CandidateRejectedError(
                "optimizer_candidate_rejected",
                "The optimizer candidate failed independent owner validation; no recommendation run was created",
                status_code=422,
                details={
                    "reasons": list(reasons) if isinstance(reasons, tuple | list) else [],
                    "basket_unchanged": True,
                },
            )
    if time.monotonic() >= worker_result.overall_deadline:
        raise WorkerTimeoutError("optimizer validation missed the shared deadline")
    return ValidatedOptimizerCandidate(candidate, validation, worker_result.overall_deadline, status)


def _app_error_for_worker_error(
    exc: Exception, *, basket_unchanged: bool, run_id: str | None = None
) -> AppError:
    details: dict[str, object] = {"basket_unchanged": basket_unchanged}
    if run_id is not None:
        details["run_id"] = run_id
    if isinstance(exc, WorkerCapacityError):
        return AppError(
            "optimizer_capacity_exceeded",
            "All production optimizer worker or validation slots are occupied; retry shortly",
            status_code=503,
            details={"basket_unchanged": basket_unchanged},
        )
    if isinstance(exc, WorkerTimeoutError):
        return AppError(
            "optimizer_timeout",
            "The production optimizer did not finish and validate within its shared deadline",
            status_code=504,
            details=details,
        )
    raise exc


def _decimal_string(value: object | None) -> str | None:
    return str(value) if isinstance(value, Decimal) else None


def _jsonable(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_jsonable(item) for item in value]
    if isinstance(value, bool | int | float | str) or value is None:
        return value
    return str(value)


def _account_snapshot_payload(snapshot: object) -> dict[str, object]:
    return {
        "total_portfolio_usd": str(object.__getattribute__(snapshot, "portfolio_total_usd")),
        "sleeve_weights_pct": {key: str(value) for key, value in object.__getattribute__(snapshot, "sleeve_weights_pct")},
    }


def _transition_snapshot_payload(snapshot: object) -> dict[str, object]:
    return {
        "us_sleeve_value_usd": str(snapshot.us_sleeve_value_usd),
        "us_sleeve_whole_portfolio_pct": str(snapshot.us_sleeve_whole_portfolio_pct),
        "etf_progress_pct": _decimal_string(snapshot.etf_progress_pct),
        "children": {
            key: {
                "value_usd": str(child.value_usd),
                "within_us_sleeve_pct": str(child.within_us_sleeve_pct),
                "whole_portfolio_pct": str(child.whole_portfolio_pct),
            }
            for key, child in snapshot.children
        },
    }


def _portfolio_effects_payload(evaluation: object | None, inputs: FinancialInputs) -> dict[str, object] | None:
    if evaluation is None:
        return None
    allocation = evaluation.allocation
    target = {key: str(value) for key, value in allocation.target.top_level_sleeve_weights_pct}
    transition = evaluation.transition
    us_transition: dict[str, object] | None = None
    if transition is not None:
        sleeve = next((row for row in inputs.policy.allocation.sleeves if row.key == transition.sleeve_key), None)
        us_transition = {
            "sleeve_key": transition.sleeve_key,
            "transition_destination_sleeve_key": transition.destination_sleeve_key,
            "label": sleeve.display_name if sleeve else transition.sleeve_key,
            "current": _transition_snapshot_payload(transition.current),
            "proposed_basket": _transition_snapshot_payload(transition.proposed_basket),
            "target": {
                "us_sleeve_whole_portfolio_pct": str(transition.target.us_sleeve_whole_portfolio_pct),
                "children": {
                    key: {
                        "within_us_sleeve_pct": str(child.within_us_sleeve_pct),
                        "whole_portfolio_pct": str(child.whole_portfolio_pct),
                    }
                    for key, child in transition.target.children
                },
            },
        }
    return {
        "allocation": {
            "current": _account_snapshot_payload(allocation.current),
            "proposed": _account_snapshot_payload(allocation.proposed),
            "target": {"sleeve_weights_pct": target},
        },
        "us_transition": us_transition,
    }


def _tax_assessment_payload(validation: object | None) -> dict[str, object] | None:
    tax = getattr(validation, "tax", None) if validation is not None else None
    if tax is None:
        return None
    names = (
        "realized_st_usd",
        "realized_lt_usd",
        "baseline_st_net_usd",
        "baseline_lt_net_usd",
        "post_trade_st_net_usd",
        "post_trade_lt_net_usd",
        "baseline_tax_usd",
        "post_trade_tax_usd",
        "estimated_tax_benefit_usd",
    )
    return {name: _jsonable(object.__getattribute__(tax, name)) for name in names}


def _wash_assessment_payload(validation: object | None) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    if validation is None:
        return [], []
    sale_rows: list[dict[str, object]] = []
    for assessment in getattr(validation, "wash_assessments", ()):
        sale_rows.append(
            {
                "ticker": assessment.ticker,
                "broker_lot_id": assessment.broker_lot_id,
                "trade_group_id": assessment.trade_group_id,
                "eligible": assessment.eligible,
                "reasons": list(assessment.reasons),
                "conflicting_transaction_keys": list(assessment.conflicting_transaction_keys),
                "no_buy_through": assessment.no_buy_through.isoformat() if assessment.no_buy_through else None,
                "next_eligible_purchase_date": (
                    assessment.next_eligible_purchase_date.isoformat()
                    if assessment.next_eligible_purchase_date
                    else None
                ),
            }
        )
    buy_rows: list[dict[str, object]] = []
    for assessment in getattr(validation, "buy_wash_assessments", ()):
        buy_rows.append(
            {
                "ticker": getattr(assessment, "ticker", None),
                "trade_group_id": getattr(assessment, "trade_group_id", None),
                "eligible": getattr(assessment, "eligible", None),
                "reasons": list(getattr(assessment, "reasons", ())),
                "conflicting_transaction_keys": list(getattr(assessment, "conflicting_transaction_keys", ())),
            }
        )
    return sale_rows, buy_rows


def _exposure_coverage_payload(validation: object | None) -> dict[str, object] | None:
    coverage = getattr(validation, "exposure_coverage", None) if validation is not None else None
    if coverage is None:
        return None
    return {
        "complete": coverage.complete,
        "as_of_date": coverage.as_of_date.isoformat() if coverage.as_of_date else None,
        "missing_tickers": list(coverage.missing_tickers),
        "stale_tickers": list(coverage.stale_tickers),
        "conflicting_tickers": list(coverage.conflicting_tickers),
        "invalid_tickers": list(coverage.invalid_tickers),
        "duplicate_rows_removed": coverage.duplicate_rows_removed,
        "sources": [{"provider": source.provider, "as_of_date": source.as_of_date.isoformat()} for source in coverage.sources],
    }


def _search_evidence(metadata: object) -> dict[str, object]:
    """Expose incomplete-search diagnostics without presenting infeasibility as proven."""
    return {
        "search_state": "incomplete",
        "feasibility_proven": False,
        "tax_regions_considered": getattr(metadata, "tax_regions_considered", 0),
        "tax_regions_solved": getattr(metadata, "tax_regions_solved", 0),
        "tax_region_search_complete": getattr(metadata, "tax_region_search_complete", False),
        "integer_search_complete": getattr(metadata, "integer_search_complete", False),
        "solver_statuses": list(getattr(metadata, "solver_statuses", ())),
    }


def _optimizer_metrics(prepared: PreparedOptimizerRun, result: ValidatedOptimizerCandidate) -> dict[str, object]:
    candidate = result.candidate
    metadata = candidate.metadata
    validation = result.validation
    evaluation = getattr(validation, "evaluation", None) if validation is not None else None
    sale_wash, buy_wash = _wash_assessment_payload(validation)
    portfolio = _portfolio_effects_payload(evaluation, prepared.inputs)
    tax = _tax_assessment_payload(validation)
    warnings = list(metadata.warnings)
    if result.status == "search_incomplete":
        warnings.append("search_incomplete_no_feasibility_claim")
    priorities = []
    for priority in getattr(metadata, "trade_group_priorities", ()):
        priorities.append(
            {
                "core_group_id": priority.group_id,
                "rank": priority.rank,
                "priority_score": _jsonable(priority.priority_score),
                "rationale": list(priority.rationale),
            }
        )
    metrics: dict[str, object] = {
        "engine": "production_optimizer",
        "optimizer_status": result.status,
        "solver": metadata.solver,
        "implementation_version": metadata.implementation_version,
        "solver_versions": dict(metadata.solver_versions),
        "solver_statuses": list(metadata.solver_statuses),
        "elapsed_seconds": metadata.elapsed_seconds,
        "screening_seconds": metadata.screening_seconds,
        "solve_seconds": metadata.solve_seconds,
        "tax_regions_considered": metadata.tax_regions_considered,
        "tax_regions_solved": metadata.tax_regions_solved,
        "tax_region_search_complete": metadata.tax_region_search_complete,
        "integer_search_complete": metadata.integer_search_complete,
        "screened_lot_count": metadata.screened_lot_count,
        "selected_lot_ids": list(metadata.selected_lot_ids),
        "candidate_types": list(metadata.candidate_types),
        "objective_value": _jsonable(getattr(validation, "objective_value", None)),
        "baseline_objective_value": None,
        "estimated_tax_benefit_usd": _jsonable(
            getattr(validation, "estimated_tax_benefit_usd", None)
        ),
        "estimated_trading_cost_usd": _jsonable(
            getattr(validation, "estimated_trading_cost_usd", None)
        ),
        "objective_components": {
            key: str(value) for key, value in getattr(validation, "objective_components", ())
        },
        "exposure_coverage_complete": metadata.exposure_coverage_complete,
        "rounding_attempts": metadata.rounding_attempts,
        "warnings": warnings,
        "trade_group_priorities": priorities,
        "tax_assessment": tax,
        "sale_wash_assessments": sale_wash,
        "buy_wash_assessments": buy_wash,
        "exposure_coverage": _exposure_coverage_payload(validation),
        "portfolio_effects": portfolio,
        "cash_before_usd": str(prepared.inputs.account.cash_usd),
        "cash_after_usd": str(evaluation.proposed.cash_usd) if evaluation is not None else None,
        "estimated_realized_st_usd": str(evaluation.realized_st_usd) if evaluation is not None else "0",
        "estimated_realized_lt_usd": str(evaluation.realized_lt_usd) if evaluation is not None else "0",
        "lots_sold_count": evaluation.selected_lots_count if evaluation is not None else 0,
        "positions_exited_count": (
            sum(1 for effect in evaluation.position_effects if effect.position_exited) if evaluation is not None else 0
        ),
        "orders_count": len(candidate.legs),
        "constraints_satisfied": getattr(validation, "accepted", None),
        "tax_profile_configured": bool(tax and tax.get("baseline_tax_usd") is not None),
        "no_trade_reason": (
            {"code": "no_trade", "message": "The optimizer returned no trades for the frozen inputs."}
            if result.status == "no_trade"
            else None
        ),
        "selection_universe": {},
        "group_annotations": {},
        "basket_revision": 0,
    }
    if result.status == "search_incomplete":
        metrics["search_evidence"] = _search_evidence(metadata)
    return metrics


def _unique_strings(values: object) -> list[str]:
    if not isinstance(values, list | tuple):
        return []
    return list(dict.fromkeys(str(value) for value in values if isinstance(value, str) and value))


def _core_group_ids(legs: Sequence[ConsolidatedLeg]) -> list[str]:
    # A review opportunity must be backed by a published leg. Priority-only IDs
    # are diagnostics, not independently selectable groups.
    groups = {group_id for leg in legs for group_id in leg.group_ids if group_id}
    for leg in legs:
        if not leg.group_ids:
            groups.add(f"{leg.side.lower()}:{leg.ticker.upper()}")
    return sorted(groups)

def _priority_map(metadata: object) -> dict[str, object]:
    return {str(row.group_id): row for row in getattr(metadata, "trade_group_priorities", ())}


def _stable_id(run_id: str, prefix: str, value: str) -> str:
    return str(uuid5(UUID(run_id), f"{prefix}:{value}"))


def _add_activity(session: Session, event_type: str, correlation_id: str, details: dict[str, object]) -> None:
    session.add(
        ActivityEvent(
            id=str(uuid4()),
            created_at=datetime.now().astimezone(),
            event_type=event_type,
            status="complete",
            correlation_id=correlation_id,
            details=details,
        )
    )


def _fresh_run(session: Session, run_id: str) -> OptimizerRun:
    run = session.scalar(
        select(OptimizerRun)
        .where(OptimizerRun.id == run_id)
        .execution_options(populate_existing=True)
    )
    if run is None:
        raise AppError("run_not_found", "Optimizer run was not found", status_code=404)
    return run


def _existing_group_state(
    session: Session, run: OptimizerRun
) -> tuple[dict[str, list[str]], dict[str, dict[str, object]], dict[str, list[str]]]:
    groups = session.scalars(
        select(RecommendationGroup)
        .where(RecommendationGroup.run_id == run.id)
        .order_by(RecommendationGroup.rank)
        .execution_options(populate_existing=True)
    ).all()
    universe: dict[str, list[str]] = {}
    annotations: dict[str, dict[str, object]] = {}
    selected_lots_by_core: dict[str, list[str]] = {}
    existing_universe = run.metrics.get("selection_universe", {}) if isinstance(run.metrics, dict) else {}
    if isinstance(existing_universe, dict):
        universe = {str(key): _unique_strings(value) for key, value in existing_universe.items()}
    for group in groups:
        impact = group.impact if isinstance(group.impact, dict) else {}
        core_id = str(impact.get("core_group_id") or group.id)
        lots = _unique_strings(impact.get("candidate_sell_lot_ids"))
        group_leg_ids = session.scalars(
            select(RecommendationGroupLeg.leg_id).where(RecommendationGroupLeg.group_id == group.id)
        ).all()
        current_selected_lots: list[str] = []
        if group_leg_ids:
            current_selected_lots = list(
                session.scalars(
                    select(RecommendationSelectedLot.broker_lot_id)
                    .join(RecommendationLeg, RecommendationLeg.id == RecommendationSelectedLot.leg_id)
                    .where(
                        RecommendationLeg.id.in_(group_leg_ids),
                        RecommendationLeg.side == "SELL",
                        RecommendationSelectedLot.selected.is_(True),
                    )
                    .order_by(RecommendationLeg.sequence, RecommendationSelectedLot.id)
                ).all()
            )
            lots.extend(current_selected_lots)
        if lots:
            universe[core_id] = list(dict.fromkeys((*universe.get(core_id, ()), *lots)))
        if current_selected_lots:
            selected_lots_by_core.setdefault(core_id, []).extend(current_selected_lots)
        annotations[core_id] = {
            "selected": bool(group.selected),
            "rejected": bool(group.rejected),
            "note": group.note,
            "rejection_reason": group.rejection_reason,
            "rank": group.rank,
            "group_type": group.group_type,
            "sleeve_key": group.sleeve_key,
            "rationale": group.rationale,
            "impact": impact,
            "dependencies": list(group.dependencies or []),
        }
    selected_lots_by_core = {
        core_id: list(dict.fromkeys(lot_ids)) for core_id, lot_ids in selected_lots_by_core.items()
    }
    return universe, annotations, selected_lots_by_core


def _clear_run_recommendations(session: Session, run: OptimizerRun) -> None:
    group_ids = session.scalars(select(RecommendationGroup.id).where(RecommendationGroup.run_id == run.id)).all()
    if not group_ids:
        return
    leg_ids = session.scalars(
        select(RecommendationLeg.id).where(RecommendationLeg.group_id.in_(group_ids))
    ).all()
    if leg_ids:
        session.execute(delete(RecommendationSelectedLot).where(RecommendationSelectedLot.leg_id.in_(leg_ids)))
        session.execute(delete(RecommendationGroupLeg).where(RecommendationGroupLeg.leg_id.in_(leg_ids)))
        session.execute(delete(RecommendationLeg).where(RecommendationLeg.id.in_(leg_ids)))
    session.execute(delete(RecommendationGroupLeg).where(RecommendationGroupLeg.group_id.in_(group_ids)))
    session.execute(delete(RecommendationGroup).where(RecommendationGroup.id.in_(group_ids)))


def _persist_candidate(
    session: Session,
    run: OptimizerRun,
    prepared: PreparedOptimizerRun,
    outcome: ValidatedOptimizerCandidate,
    *,
    selected_groups: Mapping[str, bool] | None = None,
    annotation_overrides: Mapping[str, Mapping[str, object]] | None = None,
    expected_universe: Mapping[str, list[str]] | None = None,
) -> None:
    candidate = outcome.candidate
    metadata = candidate.metadata
    legs: tuple[ConsolidatedLeg, ...] = candidate.legs
    old_universe, old_annotations, _old_selected_lots = _existing_group_state(session, run)
    universe = {key: list(value) for key, value in old_universe.items()}
    for key, value in (expected_universe or {}).items():
        universe[key] = list(dict.fromkeys((*universe.get(key, ()), *value)))

    old_groups = session.scalars(
        select(RecommendationGroup)
        .where(RecommendationGroup.run_id == run.id)
        .order_by(RecommendationGroup.rank, RecommendationGroup.id)
    ).all()
    old_groups_by_core: dict[str, list[RecommendationGroup]] = {}
    for old_group in old_groups:
        impact = old_group.impact if isinstance(old_group.impact, dict) else {}
        old_core_id = str(impact.get("core_group_id") or old_group.id)
        old_groups_by_core.setdefault(old_core_id, []).append(old_group)

    active_group_ids = _core_group_ids(legs)
    lots_by_id = {lot.broker_lot_id: lot for lot in prepared.inputs.lots}
    sell_lots_by_core: dict[str, list[str]] = {core_id: [] for core_id in active_group_ids}
    for leg in legs:
        core_ids = list(leg.group_ids) or [f"{leg.side.lower()}:{leg.ticker.upper()}"]
        if leg.side == "SELL":
            for core_id in core_ids:
                sell_lots_by_core.setdefault(core_id, []).extend(
                    allocation.broker_lot_id for allocation in leg.selected_lots
                )

    group_priorities = _priority_map(metadata)
    alias_keys = set(universe) | set(old_annotations)
    sources_by_core: dict[str, set[str]] = {core_id: {core_id} for core_id in active_group_ids}
    assigned_aliases: set[str] = set()
    if outcome.status != "search_incomplete":
        for alias in sorted(alias_keys):
            alias_lots = set(universe.get(alias, ()))
            matches = [
                (core_id, len(alias_lots.intersection(lot_ids)))
                for core_id, lot_ids in sell_lots_by_core.items()
                if alias_lots.intersection(lot_ids)
            ]
            if not matches:
                continue
            owner_core = min(
                matches,
                key=lambda item: (
                    -item[1],
                    item[0] != alias,
                    getattr(group_priorities.get(item[0]), "rank", 10**6),
                    item[0],
                ),
            )[0]
            sources_by_core.setdefault(owner_core, {owner_core}).add(alias)
            assigned_aliases.add(alias)

    group_ids = (
        []
        if outcome.status == "search_incomplete"
        else sorted(
            set(active_group_ids) | (alias_keys - assigned_aliases),
            key=lambda key: (getattr(group_priorities.get(key), "rank", 10**6), key),
        )
    )
    sources_by_group = {
        core_id: sources_by_core.get(core_id, {core_id})
        for core_id in group_ids
    }

    current_lot_owner: dict[str, str] = {}
    for core_id, lot_ids in sell_lots_by_core.items():
        for lot_id in lot_ids:
            previous_owner = current_lot_owner.setdefault(lot_id, core_id)
            if previous_owner != core_id:
                raise AppError(
                    "optimizer_core_contract_error",
                    "Optimizer output assigns a SELL lot to multiple trade groups",
                    status_code=502,
                )

    ordered_group_ids = sorted(
        group_ids,
        key=lambda key: (getattr(group_priorities.get(key), "rank", 10**6), key),
    )
    candidate_universe: dict[str, list[str]] = {}
    for core_id in group_ids:
        source_keys = sorted(sources_by_group[core_id], key=lambda key: (key != core_id, key))
        candidate_universe[core_id] = list(
            dict.fromkeys(
                lot_id
                for source in source_keys
                for lot_id in universe.get(source, ())
            )
        )
        candidate_universe[core_id] = list(
            dict.fromkeys((*candidate_universe[core_id], *sell_lots_by_core.get(core_id, ())))
        )

    # Review universes are ownership boundaries too: current SELL lots belong to
    # their emitted component, and omitted historical lots may be restored only
    # through one selectable opportunity.
    universe = {core_id: [] for core_id in group_ids}
    claimed_lots: set[str] = set()
    for core_id in ordered_group_ids:
        for lot_id in sell_lots_by_core.get(core_id, ()):
            if lot_id not in claimed_lots:
                universe[core_id].append(lot_id)
                claimed_lots.add(lot_id)
    for core_id in ordered_group_ids:
        for lot_id in candidate_universe[core_id]:
            if current_lot_owner.get(lot_id, core_id) != core_id or lot_id in claimed_lots:
                continue
            universe[core_id].append(lot_id)
            claimed_lots.add(lot_id)

    next_rank = 1
    rank_for_group: dict[str, int] = {}
    for core_group_id in group_ids:
        priority = group_priorities.get(core_group_id)
        proposed_rank = getattr(priority, "rank", None)
        if isinstance(proposed_rank, int) and proposed_rank > 0 and proposed_rank not in rank_for_group.values():
            rank_for_group[core_group_id] = proposed_rank
        else:
            while next_rank in rank_for_group.values():
                next_rank += 1
            rank_for_group[core_group_id] = next_rank
            next_rank += 1

    if (outcome.status == "ready" and not legs) or (outcome.status != "ready" and legs):
        raise AppError("optimizer_core_contract_error", "Optimizer legs are inconsistent with result status", status_code=502)
    if outcome.status in {"ready", "no_trade"} and outcome.validation is None:
        raise AppError("optimizer_core_contract_error", "Validated optimizer output is missing owner validation", status_code=502)

    prior_metrics = run.metrics if isinstance(run.metrics, dict) else {}
    basket_revision = int(prior_metrics.get("basket_revision", 0))
    metrics = _optimizer_metrics(prepared, outcome)
    metrics["basket_revision"] = basket_revision + 1
    metrics["selection_universe"] = universe
    annotations: dict[str, dict[str, object]] = {}
    for core_group_id in group_ids:
        source_keys = sorted(
            sources_by_group[core_group_id],
            key=lambda key: (
                key != core_group_id,
                old_groups_by_core.get(key, [None])[0].rank
                if old_groups_by_core.get(key)
                else 10**6,
                key,
            ),
        )
        state: dict[str, object] = {}
        source_notes: list[str] = []
        rejection_reasons: list[str] = []
        for source in source_keys:
            previous = old_annotations.get(source, {})
            state.update(previous)
            note = previous.get("note")
            rejection_reason = previous.get("rejection_reason")
            if isinstance(note, str) and note:
                source_notes.append(note)
            if isinstance(rejection_reason, str) and rejection_reason:
                rejection_reasons.append(rejection_reason)
        if source_notes:
            state["note"] = " / ".join(dict.fromkeys(source_notes))
        if rejection_reasons:
            state["rejection_reason"] = " / ".join(dict.fromkeys(rejection_reasons))
        if selected_groups is not None:
            selected_values = [selected_groups[key] for key in source_keys if key in selected_groups]
            state["selected"] = any(selected_values) if selected_values else core_group_id in active_group_ids
        else:
            state.setdefault("selected", core_group_id in active_group_ids)
        state["rejected"] = any(
            bool(old_annotations.get(source, {}).get("rejected")) for source in source_keys
        )
        if state["rejected"]:
            state["selected"] = False
        state.setdefault("note", None)
        state.setdefault("rejection_reason", None)
        annotations[core_group_id] = state
    for source, values in (annotation_overrides or {}).items():
        target = source if source in annotations else next(
            (core_id for core_id, sources in sources_by_group.items() if source in sources),
            source,
        )
        annotations.setdefault(target, {}).update(values)
    invalid_active_owners = sorted(
        core_group_id
        for core_group_id in active_group_ids
        if not annotations.get(core_group_id, {}).get("selected")
        or annotations.get(core_group_id, {}).get("rejected")
    )
    if invalid_active_owners:
        raise AppError(
            "optimizer_review_ownership_conflict",
            "Active optimizer legs cannot be reconciled to selected, non-rejected review opportunities",
            status_code=409,
            details={
                "core_group_ids": invalid_active_owners,
                "basket_unchanged": True,
            },
        )
    metrics["group_annotations"] = annotations
    persisted_group_ids: dict[str, str] = {}
    inherited_group_ids: dict[str, str] = {}
    claimed_group_ids: set[str] = set()
    reserved_group_ids = {old_group.id for old_group in old_groups}
    for core_group_id in sorted(group_ids):
        previous_groups = [
            old_group
            for source in sources_by_group[core_group_id]
            for old_group in old_groups_by_core.get(source, ())
        ]
        previous_groups.sort(
            key=lambda old_group: (
                str((old_group.impact or {}).get("core_group_id") or old_group.id) != core_group_id,
                old_group.rank,
                old_group.id,
            )
        )
        prior_group = next(
            (old_group for old_group in previous_groups if old_group.id not in claimed_group_ids),
            None,
        )
        if prior_group is not None:
            inherited_group_ids[core_group_id] = prior_group.id
            claimed_group_ids.add(prior_group.id)

    for core_group_id in group_ids:
        group_id = inherited_group_ids.get(core_group_id)
        if group_id is None:
            group_id = _stable_id(run.id, "group", core_group_id)
            collision_index = 0
            while group_id in reserved_group_ids or group_id in claimed_group_ids:
                collision_index += 1
                group_id = _stable_id(
                    run.id,
                    "group",
                    f"{core_group_id}:replacement:{collision_index}",
                )
            claimed_group_ids.add(group_id)
        persisted_group_ids[core_group_id] = group_id

    run.policy_revision_id = prepared.policy_revision_id
    run.source_generation = prepared.source_generation
    run.as_of = prepared.as_of
    run.proposed_trade_date = prepared.proposed_trade_date
    run.solver_version = str(getattr(metadata, "implementation_version", "unknown"))[:64]
    run.input_fingerprint = prepared.input_fingerprint
    run.frozen_input_bundle = prepared.frozen_input_bundle
    run.batch_settings = prepared.batch_settings
    run.metrics = metrics
    run_warnings = [str(w) for w in getattr(metadata, "warnings", ())]
    if outcome.status == "search_incomplete":
        run_warnings.append("search_incomplete_no_feasibility_claim")
    run.warnings = list(dict.fromkeys(run_warnings))
    status_map = {
        "ready": "COMPLETE",
        "no_trade": "COMPLETE",
        "infeasible": "INFEASIBLE",
        "deadline_exceeded": "TIMEOUT",
        "configuration_required": "FAILED",
        "search_incomplete": "FAILED",
    }
    run.status = status_map[outcome.status]

    _clear_run_recommendations(session, run)
    groups_by_core: dict[str, RecommendationGroup] = {}
    for core_group_id in group_ids:
        priority = group_priorities.get(core_group_id)
        group_legs = [leg for leg in legs if core_group_id in leg.group_ids]
        group_sells = [leg for leg in group_legs if leg.side == "SELL"]
        group_buys = [leg for leg in group_legs if leg.side == "BUY"]
        selected_lots = [
            (leg, allocation, lots_by_id.get(allocation.broker_lot_id))
            for leg in group_sells
            for allocation in leg.selected_lots
        ]
        proceeds = exact_sum(exact_product(leg.estimated_unit_price_usd, leg.shares) for leg in group_sells)
        realized_st = Decimal(0)
        realized_lt = Decimal(0)
        for leg, allocation, lot in selected_lots:
            if lot is None:
                raise AppError("optimizer_core_contract_error", "Optimizer selected a lot outside frozen inputs", status_code=502)
            realized = exact_product(exact_difference(leg.estimated_unit_price_usd, lot.adjusted_unit_basis_usd), allocation.shares)
            term = classify_holding_period(lot.acquired_date, prepared.proposed_trade_date)
            if term == "ST":
                realized_st += realized
            else:
                realized_lt += realized
        exclusive_buys = [leg for leg in group_buys if len(leg.group_ids) == 1]
        buy_is_fully_attributed = len(exclusive_buys) == len(group_buys)
        rationale = tuple(getattr(priority, "rationale", ())) if priority is not None else ()
        state = annotations.get(core_group_id, {})
        previous_impact = state.get("impact", {}) if isinstance(state.get("impact"), dict) else {}
        wash_status = "validated" if group_sells and outcome.validation is not None else "not_applicable"
        impact: dict[str, object] = {
            "demo": False,
            "wash_status": wash_status,
            "selected_sell_lots_count": len(selected_lots),
            "sell_proceeds_usd": str(proceeds),
            "realized_st_usd": str(realized_st),
            "realized_lt_usd": str(realized_lt),
            "replacement_buy_shares": str(exact_sum(leg.shares for leg in exclusive_buys)) if buy_is_fully_attributed else None,
            "replacement_buy_cost_usd": (
                str(exact_sum(exact_product(leg.shares, leg.estimated_unit_price_usd) for leg in exclusive_buys))
                if buy_is_fully_attributed
                else None
            ),
            "cash_after_usd": str(metrics["cash_after_usd"]) if len(active_group_ids) == 1 else None,
            "portfolio_effects": metrics["portfolio_effects"] if len(active_group_ids) == 1 else None,
            "risk_tracking_score": None,
            "core_group_id": core_group_id,
            "candidate_sell_lot_ids": universe.get(core_group_id, []),
            "warnings": ["Shared replacement-buy effects are not attributed to one trade group."]
            if any(len(leg.group_ids) > 1 for leg in group_buys)
            else [],
            "impact_attribution": "Shared replacement buys are not attributed to any one trade group."
            if any(len(leg.group_ids) > 1 for leg in group_buys)
            else "",
        }
        if not group_sells and isinstance(previous_impact, dict):
            impact["sell_proceeds_usd"] = "0"
            impact["realized_st_usd"] = "0"
            impact["realized_lt_usd"] = "0"
        sleeve_key: str | None = None
        for leg in group_sells:
            security = prepared.inputs.security_for(leg.ticker)
            if security is not None:
                resolution = resolve_holding(prepared.inputs.policy.allocation, security.identity)
                if resolution.assignment is not None:
                    sleeve_key = resolution.assignment.sleeve_key
                    break
        group_id = persisted_group_ids[core_group_id]
        rationale_text = " ".join(rationale).strip() or "Production optimizer recommendation; see the saved solver diagnostics."
        group = RecommendationGroup(
            id=group_id,
            run_id=run.id,
            rank=rank_for_group[core_group_id],
            group_type="optimizer_trade",
            sleeve_key=sleeve_key,
            rationale=rationale_text,
            estimated_benefit_usd=None,
            impact=impact,
            dependencies=[],
            selected=bool(state.get("selected", core_group_id in active_group_ids)),
            rejected=bool(state.get("rejected", False)),
            note=state.get("note") if isinstance(state.get("note"), str) else None,
            rejection_reason=state.get("rejection_reason") if isinstance(state.get("rejection_reason"), str) else None,
        )
        session.add(group)
        groups_by_core[core_group_id] = group

    # Membership rows are inserted without ORM relationships, so persist their groups first.
    session.flush()
    leg_ids = {str(leg.leg_id): _stable_id(run.id, "leg", str(leg.leg_id)) for leg in legs}
    seen_leg_keys: set[tuple[str, str]] = set()
    for leg in legs:
        key = (leg.side, leg.ticker.upper())
        if key in seen_leg_keys:
            raise AppError("optimizer_core_contract_error", "Optimizer output contains duplicate ticker legs", status_code=502)
        seen_leg_keys.add(key)
        core_groups = list(leg.group_ids) or [f"buy:{leg.ticker.upper()}"]
        if any(core_group not in groups_by_core for core_group in core_groups):
            raise AppError("optimizer_core_contract_error", "Optimizer leg references an unknown trade group", status_code=502)
        security_input = prepared.inputs.security_for(leg.ticker)
        security_id = security_input.security_id if security_input is not None else None
        if security_id is None:
            security_id = session.scalar(select(Security.id).where(Security.ticker == leg.ticker.upper()))
        if security_id is None:
            raise AppError("optimizer_core_contract_error", "Optimizer leg references an unknown security", status_code=502)
        persistent_id = leg_ids[str(leg.leg_id)]
        persistent_dependencies = [leg_ids[item] for item in leg.depends_on_leg_ids if item in leg_ids]
        if len(persistent_dependencies) != len(leg.depends_on_leg_ids):
            raise AppError("optimizer_core_contract_error", "Optimizer leg references an unknown dependency", status_code=502)
        st_realized = Decimal(0)
        lt_realized = Decimal(0)
        lot_rows: list[tuple[object, object, Decimal, str]] = []
        for allocation in leg.selected_lots:
            lot = lots_by_id.get(allocation.broker_lot_id)
            if lot is None or allocation.shares <= 0:
                raise AppError("optimizer_core_contract_error", "Optimizer lot attribution is invalid", status_code=502)
            term = classify_holding_period(lot.acquired_date, prepared.proposed_trade_date)
            realized = exact_product(exact_difference(leg.estimated_unit_price_usd, lot.adjusted_unit_basis_usd), allocation.shares)
            if term == "ST":
                st_realized += realized
            else:
                lt_realized += realized
            lot_rows.append((allocation, lot, realized, term))
        primary_group = min(core_groups, key=lambda group_id: rank_for_group[group_id])
        persisted_leg = RecommendationLeg(
            id=persistent_id,
            group_id=groups_by_core[primary_group].id,
            account_id=prepared.inputs.account.local_account_id,
            security_id=security_id,
            side=leg.side,
            shares=leg.shares,
            estimated_unit_price_usd=leg.estimated_unit_price_usd,
            net_st_realized_usd=st_realized,
            net_lt_realized_usd=lt_realized,
            sequence=leg.sequence,
            details={
                "core_leg_id": leg.leg_id,
                "group_ids": [groups_by_core[group_id].id for group_id in core_groups],
                "depends_on_leg_ids": persistent_dependencies,
                "core_group_ids": core_groups,
            },
        )
        session.add(persisted_leg)
        # RecommendationGroupLeg has no ORM relationship; flush its parent before the FK row.
        session.flush()
        for core_group in core_groups:
            session.add(RecommendationGroupLeg(group_id=groups_by_core[core_group].id, leg_id=persistent_id))
        for allocation, lot, realized, term in lot_rows:
            session.add(
                RecommendationSelectedLot(
                    leg_id=persistent_id,
                    broker_lot_id=allocation.broker_lot_id,
                    shares=allocation.shares,
                    acquired_date=lot.acquired_date,
                    adjusted_basis_usd=lot.adjusted_unit_basis_usd,
                    st_lt_term=term,
                    realized_pl_usd=realized,
                    selected=True,
                )
            )
    for group in groups_by_core.values():
        group.dependencies = sorted(
            {
                dependency
                for leg in legs
                if group.id in [groups_by_core[core_group].id for core_group in (leg.group_ids or [f"buy:{leg.ticker.upper()}"])]
                for dependency in (leg_ids[item] for item in leg.depends_on_leg_ids if item in leg_ids)
            }
        )


def _new_run(prepared: PreparedOptimizerRun) -> OptimizerRun:
    return OptimizerRun(
        id=str(uuid4()),
        policy_revision_id=prepared.policy_revision_id,
        source_generation=prepared.source_generation,
        as_of=prepared.as_of,
        proposed_trade_date=prepared.proposed_trade_date,
        solver_version=None,
        status="CREATED",
        batch_settings=prepared.batch_settings,
        metrics={},
        warnings=[],
        input_fingerprint=prepared.input_fingerprint,
        frozen_input_bundle=prepared.frozen_input_bundle,
    )


def _persist_initial_timeout(
    session: Session, prepared: PreparedOptimizerRun, *, correlation_id: str
) -> str:
    """Save a truthful timeout run without publishing partial recommendations."""
    with session.begin():
        run = _new_run(prepared)
        run.status = "TIMEOUT"
        run.metrics = {
            "engine": "production_optimizer",
            "optimizer_status": "deadline_exceeded",
            "timeout_message": "The production optimizer did not finish and validate within its shared deadline",
            "basket_revision": 0,
            "selection_universe": {},
            "group_annotations": {},
            "estimated_realized_st_usd": "0",
            "estimated_realized_lt_usd": "0",
            "lots_sold_count": 0,
            "positions_exited_count": 0,
            "orders_count": 0,
            "warnings": ["optimizer_timeout"],
        }
        run.warnings = ["optimizer_timeout"]
        session.add(run)
        _add_activity(
            session,
            "production_optimizer_run",
            correlation_id,
            {"run_id": run.id, "status": "deadline_exceeded", "input_fingerprint": prepared.input_fingerprint},
        )
    return run.id


async def create_production_run(
    session: Session,
    request: OptimizerRunInput,
    supervisor: ProcessSupervisor,
    validation_executor: BoundedValidationExecutor,
    *,
    correlation_id: str,
) -> OptimizerRun:
    with session.begin():
        prepared = prepare_optimizer_run(session, request)
    try:
        outcome = await run_validated_candidate(
            prepared.inputs,
            supervisor,
            validation_executor=validation_executor,
        )
        with session.begin():
            assert_optimizer_run_current(session, prepared, deadline=outcome.overall_deadline)
            run = _new_run(prepared)
            session.add(run)
            session.flush()
            _persist_candidate(session, run, prepared, outcome)
            _add_activity(
                session,
                "production_optimizer_run",
                correlation_id,
                {"run_id": run.id, "status": outcome.status, "input_fingerprint": prepared.input_fingerprint},
            )
    except WorkerCapacityError as exc:
        raise _app_error_for_worker_error(exc, basket_unchanged=True) from exc
    except WorkerTimeoutError as exc:
        timeout_run_id = _persist_initial_timeout(session, prepared, correlation_id=correlation_id)
        raise _app_error_for_worker_error(
            exc, basket_unchanged=True, run_id=timeout_run_id
        ) from exc
    return run

def _run_state(
    session: Session, run_id: str
) -> tuple[OptimizerRun, _RunState, dict[str, dict[str, object]]]:
    run = _fresh_run(session, run_id)
    if run.solver_version == "DEMO" or run.frozen_input_bundle.get("mode") != "real_optimizer":
        raise AppError(
            "real_optimizer_operation_required",
            "This operation is not available for deterministic DEMO recommendations",
            status_code=409,
            details={"basket_unchanged": True},
        )
    if run.status not in {"COMPLETE", "INFEASIBLE"}:
        raise AppError("optimizer_run_not_editable", "Only completed optimizer runs can be reviewed", status_code=409)
    raw_settings = run.batch_settings if isinstance(run.batch_settings, dict) else {}
    limits = {key: raw_settings.get(key) for key in _BATCH_LIMIT_KEYS}
    request = OptimizerRunInput(
        mode="real_optimizer",
        proposed_trade_date=run.proposed_trade_date,
        **limits,
    )
    prepared = prepare_optimizer_run(
        session,
        request,
        proposed_trade_date=run.proposed_trade_date,
        batch_limits=raw_settings,
    )
    if prepared.input_fingerprint != run.input_fingerprint or prepared.source_generation != run.source_generation:
        raise AppError(
            "stale_optimizer_input",
            "The saved optimizer run no longer matches current account or policy inputs",
            status_code=409,
            details={"basket_unchanged": True},
        )
    universe, annotations, current_selected_lots = _existing_group_state(session, run)
    metrics = run.metrics if isinstance(run.metrics, dict) else {}
    state = _RunState(
        run_id=run.id,
        input_fingerprint=run.input_fingerprint or "",
        source_generation=run.source_generation,
        basket_revision=int(metrics.get("basket_revision", 0)),
        prepared=prepared,
        group_rows=tuple(
            {
                "id": row.id,
                "core_group_id": str((row.impact or {}).get("core_group_id") or row.id),
                "rank": row.rank,
                "selected": row.selected,
                "rejected": row.rejected,
                "note": row.note,
                "rejection_reason": row.rejection_reason,
                "candidate_sell_lot_ids": list(universe.get(str((row.impact or {}).get("core_group_id") or row.id), [])),
                "selected_sell_lot_ids": list(current_selected_lots.get(str((row.impact or {}).get("core_group_id") or row.id), [])),
                "impact": row.impact,
            }
            for row in session.scalars(
                select(RecommendationGroup)
                .where(RecommendationGroup.run_id == run.id)
                .order_by(RecommendationGroup.rank)
                .execution_options(populate_existing=True)
            ).all()
        ),
        selection_universe=universe,
    )
    return run, state, annotations


def _assert_same_run_state(session: Session, state: _RunState) -> None:
    revision = func.coalesce(func.json_extract(OptimizerRun.metrics, "$.basket_revision"), 0)
    result = session.execute(
        update(OptimizerRun)
        .where(
            OptimizerRun.id == state.run_id,
            OptimizerRun.input_fingerprint == state.input_fingerprint,
            OptimizerRun.source_generation == state.source_generation,
            revision == state.basket_revision,
        )
        .values(input_fingerprint=OptimizerRun.input_fingerprint)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise AppError(
            "stale_optimizer_basket",
            "The saved recommendation basket changed while the requested subset was being recomputed",
            status_code=409,
            details={"basket_unchanged": True},
        )


def _selection_payload_lots(
    state: _RunState, request: OptimizerSelectionInput
) -> tuple[tuple[str, ...], dict[str, bool]]:
    by_public_id = {str(row["id"]): row for row in state.group_rows}
    unknown_groups = set(request.selected_group_ids) - set(by_public_id)
    unknown_groups.update(set(request.selected_sell_lots) - set(by_public_id))
    if unknown_groups:
        raise AppError("unknown_recommendation_group", "The selection contains an unknown trade group", status_code=422,
                       details={"unknown_group_ids": sorted(unknown_groups), "basket_unchanged": True})
    unselected_groups = set(request.selected_sell_lots) - set(request.selected_group_ids)
    if unselected_groups:
        raise AppError(
            "invalid_group_lot_selection",
            "Sell-lot selections may only be supplied for selected trade groups",
            status_code=422,
            details={"unselected_group_ids": sorted(unselected_groups), "basket_unchanged": True},
        )
    selected_core_ids: set[str] = set()
    requested_lots: list[str] = []
    seen_lots: set[str] = set()
    for public_id in request.selected_group_ids:
        row = by_public_id[public_id]
        core_id = str(row["core_group_id"])
        if row["rejected"]:
            raise AppError("rejected_recommendation_group", "A rejected trade group cannot be selected", status_code=409,
                           details={"group_id": public_id, "basket_unchanged": True})
        allowed = set(state.selection_universe.get(core_id, ()))
        if public_id in request.selected_sell_lots:
            lot_ids = request.selected_sell_lots[public_id]
        elif row["selected"]:
            lot_ids = _unique_strings(row.get("selected_sell_lot_ids"))
        else:
            lot_ids = list(allowed)
        invalid = set(lot_ids) - allowed
        if invalid:
            raise AppError("invalid_group_lot_selection", "Selected broker lots do not belong to this saved trade group", status_code=422,
                           details={"group_id": public_id, "unknown_lot_ids": sorted(invalid), "basket_unchanged": True})
        if not allowed or not lot_ids:
            raise AppError("group_has_no_sell_lots", "A real optimizer trade group must identify exact SELL lots before re-solving", status_code=422,
                           details={"group_id": public_id, "basket_unchanged": True})
        selected_core_ids.add(core_id)
        for lot_id in lot_ids:
            if lot_id in seen_lots:
                raise AppError("duplicate_selected_lot", "A broker lot may be selected only once", status_code=422,
                               details={"broker_lot_id": lot_id, "basket_unchanged": True})
            seen_lots.add(lot_id)
            requested_lots.append(lot_id)
    selected = {str(row["core_group_id"]): str(row["core_group_id"]) in selected_core_ids for row in state.group_rows}
    return tuple(requested_lots), selected


def _validate_intent_lots(state: _RunState, request: OptimizerLotReviewIntentInput) -> tuple[str, ...]:
    if request.source_generation != state.source_generation:
        raise AppError(
            "stale_lot_review_intent",
            "The requested broker lots belong to a different source generation",
            status_code=409,
            details={"requested_source_generation": request.source_generation, "run_source_generation": state.source_generation,
                     "basket_unchanged": True},
        )
    by_id = {lot.broker_lot_id: lot for lot in state.prepared.inputs.lots}
    missing = [lot_id for lot_id in request.broker_lot_ids if lot_id not in by_id]
    unavailable = [
        lot_id for lot_id in request.broker_lot_ids
        if lot_id in by_id and by_id[lot_id].available_shares <= 0
    ]
    if missing or unavailable:
        raise AppError(
            "lot_review_intent_rejected",
            "Every requested lot must exist in the frozen current portfolio; no basket changes were applied",
            status_code=422,
            details={"missing_lot_ids": missing, "unavailable_lot_ids": unavailable, "basket_unchanged": True},
        )
    rejected_groups_by_lot: dict[str, set[str]] = {}
    rejected_core_ids: set[str] = set()
    for row in state.group_rows:
        if row["rejected"]:
            core_id = str(row["core_group_id"])
            rejected_core_ids.add(core_id)
            for lot_id in state.selection_universe.get(core_id, ()):
                rejected_groups_by_lot.setdefault(lot_id, set()).add(str(row["id"]))
    rejected_lots = [
        lot_id
        for lot_id in request.broker_lot_ids
        if lot_id in rejected_groups_by_lot
        or f"sale:{by_id[lot_id].ticker.upper()}" in rejected_core_ids
    ]
    if rejected_lots:
        rejected_group_ids = sorted(
            {
                group_id
                for lot_id in rejected_lots
                for group_id in rejected_groups_by_lot.get(lot_id, ())
            }
            | {
                str(row["id"])
                for lot_id in rejected_lots
                for row in state.group_rows
                if row["rejected"]
                and f"sale:{by_id[lot_id].ticker.upper()}" == str(row["core_group_id"])
            }
        )
        raise AppError(
            "rejected_recommendation_group",
            "A lot from a rejected trade group cannot be selected until the group is restored",
            status_code=409,
            details={"group_ids": rejected_group_ids, "broker_lot_ids": rejected_lots, "basket_unchanged": True},
        )
    return tuple(request.broker_lot_ids)


def _positive_whole_shares(value: object) -> bool:
    return isinstance(value, Decimal) and value.is_finite() and value > 0 and value == value.to_integral_value()


def _sell_lot_intent_errors(
    prepared: PreparedOptimizerRun,
    outcome: ValidatedOptimizerCandidate,
    selected_lot_ids: tuple[str, ...],
) -> dict[str, object] | None:
    expected_ids = list(selected_lot_ids)
    expected = set(expected_ids)
    frozen_lots: dict[str, object] = {}
    for lot in getattr(prepared.inputs, "lots", ()):
        lot_id = getattr(lot, "broker_lot_id", None)
        if isinstance(lot_id, str):
            frozen_lots[lot_id] = lot
    frozen_lot_ids = set(frozen_lots)
    actual_ids: list[str] = []
    errors: set[str] = set()
    if len(expected_ids) != len(expected):
        errors.add("duplicate_requested_lot_ids")
    if expected and outcome.status != "ready":
        errors.add("nonempty_intent_requires_ready_result")
    legs = getattr(outcome.candidate, "legs", ())
    if not isinstance(legs, tuple):
        errors.add("malformed_candidate_legs")
        legs = ()
    for leg in legs:
        side = getattr(leg, "side", None)
        allocations = getattr(leg, "selected_lots", ())
        if side == "BUY":
            if allocations:
                errors.add("buy_leg_has_sell_lot_attribution")
            continue
        if side != "SELL":
            errors.add("invalid_trade_leg_side")
            continue
        leg_shares = getattr(leg, "shares", None)
        if not _positive_whole_shares(leg_shares):
            errors.add("sell_quantity_not_positive_whole_shares")
        if not isinstance(allocations, tuple) or not allocations:
            errors.add("sell_leg_missing_lot_attribution")
            continue
        allocated_shares = Decimal(0)
        for allocation in allocations:
            broker_lot_id = getattr(allocation, "broker_lot_id", None)
            quantity = getattr(allocation, "shares", None)
            if not isinstance(broker_lot_id, str) or not broker_lot_id:
                errors.add("sell_lot_id_missing")
            else:
                actual_ids.append(broker_lot_id)
                if broker_lot_id not in frozen_lot_ids:
                    errors.add("sell_lot_id_outside_frozen_inputs")
                else:
                    frozen_ticker = getattr(frozen_lots[broker_lot_id], "ticker", None)
                    leg_ticker = getattr(leg, "ticker", None)
                    if (
                        not isinstance(frozen_ticker, str)
                        or not isinstance(leg_ticker, str)
                        or frozen_ticker.upper() != leg_ticker.upper()
                    ):
                        errors.add("sell_lot_ticker_mismatch")
            if not _positive_whole_shares(quantity):
                errors.add("sell_lot_quantity_not_positive_whole_shares")
            else:
                allocated_shares += quantity
                if isinstance(broker_lot_id, str) and broker_lot_id in frozen_lots:
                    available_shares = getattr(frozen_lots[broker_lot_id], "available_shares", None)
                    if (
                        not isinstance(available_shares, Decimal)
                        or not available_shares.is_finite()
                        or quantity > available_shares
                    ):
                        errors.add("sell_lot_quantity_exceeds_frozen_available_shares")
        if _positive_whole_shares(leg_shares) and allocated_shares != leg_shares:
            errors.add("sell_quantity_does_not_match_lot_attributions")
    if set(actual_ids) != expected or len(actual_ids) != len(expected):
        errors.add("sell_lot_ids_do_not_match_intent")
    if not errors:
        return None
    return {
        "intent_errors": sorted(errors),
        "expected_sell_lot_ids": expected_ids,
        "actual_sell_lot_ids": actual_ids,
    }


async def _recompute_real_basket(
    session: Session,
    run_id: str,
    state: _RunState,
    selected_lot_ids: tuple[str, ...],
    selected_groups: Mapping[str, bool],
    supervisor: ProcessSupervisor,
    validation_executor: BoundedValidationExecutor,
    *,
    correlation_id: str,
    event_type: str,
    event_details: dict[str, object],
    annotation_overrides: Mapping[str, Mapping[str, object]] | None = None,
    expected_universe: Mapping[str, list[str]] | None = None,
) -> OptimizerRun:
    try:
        outcome = await run_validated_candidate(
            state.prepared.inputs,
            supervisor,
            sell_lot_ids=selected_lot_ids,
            validation_executor=validation_executor,
        )
    except (WorkerCapacityError, WorkerTimeoutError) as exc:
        raise _app_error_for_worker_error(exc, basket_unchanged=True) from exc
    if outcome.status not in {"ready", "no_trade"}:
        candidate_metadata = getattr(outcome.candidate, "metadata", None)
        warnings = list(getattr(candidate_metadata, "warnings", ()))
        if outcome.status == "search_incomplete":
            warnings.append("search_incomplete_no_feasibility_claim")
        details: dict[str, object] = {
            "optimizer_status": outcome.status,
            "warnings": warnings,
            "basket_unchanged": True,
        }
        if outcome.status == "search_incomplete":
            details["search_evidence"] = _search_evidence(candidate_metadata)
        raise AppError(
            "optimizer_subset_rejected",
            "The requested subset could not produce an independently validated recommendation; the saved basket is unchanged",
            status_code=422 if outcome.status != "deadline_exceeded" else 504,
            details=details,
        )
    intent_errors = _sell_lot_intent_errors(state.prepared, outcome, selected_lot_ids)
    if intent_errors is not None:
        raise AppError(
            "optimizer_subset_rejected",
            "The optimizer result did not exactly satisfy the requested SELL-lot intent; the saved basket is unchanged",
            status_code=422,
            details={
                "optimizer_status": outcome.status,
                **intent_errors,
                "basket_unchanged": True,
            },
        )
    with session.begin():
        run = _fresh_run(session, run_id)
        _assert_same_run_state(session, state)
        try:
            assert_optimizer_run_current(session, state.prepared, deadline=outcome.overall_deadline)
        except WorkerTimeoutError as exc:
            raise _app_error_for_worker_error(exc, basket_unchanged=True) from exc
        _persist_candidate(
            session,
            run,
            state.prepared,
            outcome,
            selected_groups=selected_groups,
            annotation_overrides=annotation_overrides,
            expected_universe=expected_universe,
        )
        details = {"run_id": run.id, "selected_sell_lot_ids": list(selected_lot_ids), **event_details}
        _add_activity(session, event_type, correlation_id, details)
    return run


async def apply_real_selection(
    session: Session,
    run_id: str,
    request: OptimizerSelectionInput,
    supervisor: ProcessSupervisor,
    validation_executor: BoundedValidationExecutor,
    *,
    correlation_id: str,
) -> OptimizerRun:
    with session.begin():
        _run, state, _annotations = _run_state(session, run_id)
        selected_lots, selected_groups = _selection_payload_lots(state, request)
    return await _recompute_real_basket(
        session,
        run_id,
        state,
        selected_lots,
        selected_groups,
        supervisor,
        validation_executor,
        correlation_id=correlation_id,
        event_type="production_recommendation_selection",
        event_details={"selected_group_ids": list(request.selected_group_ids)},
    )


async def apply_real_lot_review_intent(
    session: Session,
    run_id: str,
    request: OptimizerLotReviewIntentInput,
    supervisor: ProcessSupervisor,
    validation_executor: BoundedValidationExecutor,
    *,
    correlation_id: str,
) -> OptimizerRun:
    with session.begin():
        _run, state, _annotations = _run_state(session, run_id)
        selected_lots = _validate_intent_lots(state, request)
        selected_groups: dict[str, bool] = dict.fromkeys(state.selection_universe, False)
        for lot_id in selected_lots:
            lot = next(lot for lot in state.prepared.inputs.lots if lot.broker_lot_id == lot_id)
            fallback = f"sale:{lot.ticker.upper()}"
            selected_groups[fallback] = True
        intent_universe: dict[str, list[str]] = {}
        for lot_id in selected_lots:
            lot = next(lot for lot in state.prepared.inputs.lots if lot.broker_lot_id == lot_id)
            intent_universe.setdefault(f"sale:{lot.ticker.upper()}", []).append(lot_id)
    return await _recompute_real_basket(
        session,
        run_id,
        state,
        selected_lots,
        selected_groups,
        supervisor,
        validation_executor,
        correlation_id=correlation_id,
        event_type="production_lot_review_intent",
        event_details={"source_generation": request.source_generation},
        expected_universe=intent_universe,
    )


async def annotate_real_group(
    session: Session,
    run_id: str,
    group_id: str,
    request: RecommendationAnnotationInput,
    supervisor: ProcessSupervisor,
    validation_executor: BoundedValidationExecutor,
    *,
    correlation_id: str,
) -> OptimizerRun:
    with session.begin():
        run, state, annotations = _run_state(session, run_id)
        target = next((row for row in state.group_rows if row["id"] == group_id), None)
        if target is None:
            raise AppError("recommendation_group_not_found", "Recommendation group was not found", status_code=404)
        core_id = str(target["core_group_id"])
        current = annotations.get(core_id, {})
        current_selected = bool(current.get("selected", False))
        changes_rejection = request.rejected is not None and (
            request.rejected != bool(current.get("rejected", False))
            or (request.rejected and current_selected)
        )
        should_resolve = changes_rejection and request.rejected is True and current_selected
        if not should_resolve:
            assert_optimizer_run_current(session, state.prepared)
            _assert_same_run_state(session, state)
            group = session.scalar(
                select(RecommendationGroup)
                .where(RecommendationGroup.id == group_id)
                .execution_options(populate_existing=True)
            )
            if group is None:
                raise AppError("recommendation_group_not_found", "Recommendation group was not found", status_code=404)
            if changes_rejection:
                metrics = dict(run.metrics) if isinstance(run.metrics, dict) else {}
                metrics["basket_revision"] = state.basket_revision + 1
                run.metrics = metrics
            if "note" in request.model_fields_set:
                group.note = request.note
            if request.rejected is not None:
                group.rejected = request.rejected
                if request.rejected:
                    group.selected = False
                    if "rejection_reason" in request.model_fields_set:
                        group.rejection_reason = request.rejection_reason
                else:
                    group.rejection_reason = None
            _add_activity(
                session,
                "production_recommendation_annotation",
                correlation_id,
                {"run_id": run_id, "group_id": group_id, "rejected": request.rejected},
            )
            return run
        note_value = request.note if "note" in request.model_fields_set else current.get("note")
        rejection_reason = request.rejection_reason if "rejection_reason" in request.model_fields_set else None
        selected_groups = {
            str(row["core_group_id"]): bool(row["selected"]) and str(row["core_group_id"]) != core_id
            for row in state.group_rows
        }
        selected_lots = tuple(
            lot_id
            for row in state.group_rows
            if str(row["core_group_id"]) != core_id and row["selected"] and not row["rejected"]
            for lot_id in _unique_strings(row.get("selected_sell_lot_ids"))
        )
        overrides = {
            core_id: {
                "selected": False,
                "rejected": True,
                "note": note_value,
                "rejection_reason": rejection_reason,
            }
        }
    return await _recompute_real_basket(
        session,
        run_id,
        state,
        selected_lots,
        selected_groups,
        supervisor,
        validation_executor,
        correlation_id=correlation_id,
        event_type="production_recommendation_rejection",
        event_details={"group_id": group_id, "rejected": True},
        annotation_overrides=overrides,
    )


def _group_warnings(group: RecommendationGroup) -> list[str]:
    return _unique_strings(group.impact.get("warnings") if isinstance(group.impact, dict) else None)


def real_run_summary(run: OptimizerRun, session: Session) -> dict[str, object]:
    metrics = run.metrics if isinstance(run.metrics, dict) else {}
    estimated_tax = metrics.get("estimated_tax_benefit_usd")
    tax_status = "optimizer_unavailable"
    if metrics.get("tax_profile_configured"):
        tax_status = "available"
    elif metrics.get("tax_assessment") is not None:
        tax_status = "tax_profile_incomplete"
    optimizer_status = str(metrics.get("optimizer_status", "failed"))
    status = {
        "ready": "complete",
        "no_trade": "complete",
        "infeasible": "infeasible",
        "deadline_exceeded": "timeout",
        "configuration_required": "failed",
        "search_incomplete": "failed",
    }.get(optimizer_status, run.status.lower())
    return {
        "run_id": run.id,
        "status": status,
        "mode": "real_optimizer",
        "policy_revision_id": run.policy_revision_id,
        "source_generation": run.source_generation,
        "as_of": run.as_of,
        "solver_version": run.solver_version or "unknown",
        "proposed_trade_date": run.proposed_trade_date,
        "demo": False,
        "actionable": False,
        "input_fingerprint": run.input_fingerprint,
        "source_checksum": run.frozen_input_bundle.get("source_checksum"),
        "batch_settings": run.batch_settings or {},
        "estimated_realized_st_usd": str(metrics.get("estimated_realized_st_usd", "0")),
        "estimated_realized_lt_usd": str(metrics.get("estimated_realized_lt_usd", "0")),
        "estimated_tax_benefit_usd": str(estimated_tax) if estimated_tax is not None else None,
        "estimated_tax_benefit_status": tax_status,
        "lots_sold_count": int(metrics.get("lots_sold_count", 0)),
        "positions_exited_count": int(metrics.get("positions_exited_count", 0)),
        "orders_count": int(metrics.get("orders_count", 0)),
        "cash_before_usd": metrics.get("cash_before_usd"),
        "cash_after_usd": metrics.get("cash_after_usd"),
        "portfolio_effects": metrics.get("portfolio_effects"),
        "constraints_satisfied": metrics.get("constraints_satisfied"),
        "no_trade_reason": metrics.get("no_trade_reason"),
        "warnings": list(run.warnings or []),
        "tax_profile_configured": bool(metrics.get("tax_profile_configured", False)),
        "optimizer_metrics": metrics,
        "frozen_display_context": _run_display_context(run, session),
    }


def real_run_recommendations(session: Session, run: OptimizerRun) -> dict[str, object]:
    response = real_run_summary(run, session)
    groups = session.scalars(
        select(RecommendationGroup).where(RecommendationGroup.run_id == run.id).order_by(RecommendationGroup.rank)
    ).all()
    group_ids = [group.id for group in groups]
    group_leg_rows = session.execute(
        select(RecommendationGroupLeg.group_id, RecommendationGroupLeg.leg_id).where(
            RecommendationGroupLeg.group_id.in_(group_ids)
        )
    ).all() if group_ids else []
    leg_ids_by_group: dict[str, list[str]] = {group_id: [] for group_id in group_ids}
    for group_id, leg_id in group_leg_rows:
        leg_ids_by_group.setdefault(group_id, []).append(leg_id)
    group_responses = []
    for group in groups:
        group_responses.append(
            {
                "group_id": group.id,
                "rank": group.rank,
                "group_type": group.group_type,
                "sleeve_key": group.sleeve_key,
                "rationale": group.rationale,
                "estimated_benefit_usd": None,
                "impact": {
                    key: group.impact.get(key)
                    for key in (
                        "demo",
                        "wash_status",
                        "selected_sell_lots_count",
                        "sell_proceeds_usd",
                        "realized_st_usd",
                        "realized_lt_usd",
                        "replacement_buy_shares",
                        "replacement_buy_cost_usd",
                        "cash_after_usd",
                        "portfolio_effects",
                        "risk_tracking_score",
                    )
                },
                "dependencies": list(group.dependencies or []),
                "selected": group.selected,
                "rejected": group.rejected,
                "note": group.note,
                "rejection_reason": group.rejection_reason,
                "leg_ids": leg_ids_by_group.get(group.id, []),
                "warnings": _group_warnings(group),
            }
        )
    legs = session.scalars(
        select(RecommendationLeg)
        .join(RecommendationGroup, RecommendationGroup.id == RecommendationLeg.group_id)
        .where(RecommendationGroup.run_id == run.id)
        .order_by(RecommendationLeg.sequence, RecommendationLeg.side, RecommendationLeg.id)
    ).all()
    leg_responses = []
    for leg in legs:
        details = leg.details if isinstance(leg.details, dict) else {}
        selected_lots = session.scalars(
            select(RecommendationSelectedLot)
            .where(RecommendationSelectedLot.leg_id == leg.id)
            .order_by(RecommendationSelectedLot.broker_lot_id)
        ).all()
        leg_responses.append(
            {
                "leg_id": leg.id,
                "side": leg.side,
                "ticker": session.get(Security, leg.security_id).ticker,
                "shares": str(leg.shares),
                "estimated_unit_price_usd": str(leg.estimated_unit_price_usd),
                "estimated_notional_usd": str(exact_product(leg.shares, leg.estimated_unit_price_usd)),
                "net_st_realized_usd": str(leg.net_st_realized_usd),
                "net_lt_realized_usd": str(leg.net_lt_realized_usd),
                "selected": True,
                "group_ids": list(details.get("group_ids", [])),
                "sequence": leg.sequence,
                "dependencies": list(details.get("depends_on_leg_ids", [])),
                "selected_lots": [
                    {
                        "broker_lot_id": row.broker_lot_id,
                        "shares": str(row.shares),
                        "acquired_date": row.acquired_date,
                        "adjusted_basis_usd": str(row.adjusted_basis_usd),
                        "st_lt": row.st_lt_term,
                        "realized_pl_usd": str(row.realized_pl_usd),
                        "selected": row.selected,
                    }
                    for row in selected_lots
                ],
                "details": details,
            }
        )
    response["groups"] = group_responses
    response["consolidated_legs"] = leg_responses
    return response


def real_run_export_response(session: Session, run: OptimizerRun) -> dict[str, object]:
    return real_run_recommendations(session, run)
