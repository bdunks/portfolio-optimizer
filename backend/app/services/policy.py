from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    CurrentPosition,
    PolicyAllowedSecurity,
    PolicyRevision,
    PolicySectorBand,
    PolicySecurityOverride,
    PolicySleeve,
    Security,
)
from app.domain.allocation import (
    SecurityIdentity,
    resolve_holding,
    resolve_transition_destination,
)
from app.domain.decimal_math import exact_sum
from app.schemas import PolicyDraftInput, PolicySettingsInput, SleeveInput
from app.services.errors import AppError
from app.services.financial_input_loader import load_allocation_policy

ONE_HUNDRED = Decimal(100)


def _sleeves_by_key(session: Session, revision_id: str) -> dict[str, PolicySleeve]:
    return {
        sleeve.sleeve_key: sleeve
        for sleeve in session.scalars(
            select(PolicySleeve).where(PolicySleeve.policy_revision_id == revision_id)
        ).all()
    }


def _security_by_ticker(session: Session, ticker: str) -> Security | None:
    return session.scalar(select(Security).where(Security.ticker == ticker.upper()))


def _target_parts(
    target: str,
    sleeves: dict[str, PolicySleeve],
) -> tuple[str, str | None] | None:
    sleeve = sleeves.get(target)
    if sleeve is None or not sleeve.enabled:
        return None
    if sleeve.parent_sleeve_key:
        return sleeve.parent_sleeve_key, sleeve.sleeve_key
    return sleeve.sleeve_key, None


def create_policy_draft(session: Session, payload: PolicyDraftInput) -> PolicyRevision:
    active = session.scalar(
        select(PolicyRevision)
        .where(PolicyRevision.status == "ACTIVE")
        .order_by(PolicyRevision.revision_number.desc())
    )
    source_id = payload.source_revision_id or (active.id if active else None)
    source = session.get(PolicyRevision, source_id) if source_id else None
    if payload.source_revision_id and source is None:
        raise AppError(
            "policy_revision_not_found", "Source policy revision was not found", status_code=404
        )

    incoming_sleeves = {s.sleeve_key: s for s in payload.sleeves}
    if len(incoming_sleeves) != len(payload.sleeves):
        raise AppError("duplicate_sleeve", "Sleeve keys must be unique", status_code=422)
    if any(s.parent_sleeve_key == s.sleeve_key for s in payload.sleeves):
        raise AppError("invalid_sleeve_tree", "A sleeve cannot be its own parent", status_code=422)
    for sleeve in payload.sleeves:
        if sleeve.parent_sleeve_key and sleeve.parent_sleeve_key not in incoming_sleeves:
            raise AppError(
                "invalid_sleeve_tree",
                "Every nested sleeve must reference a sleeve in this draft",
                status_code=422,
                details={"sleeve_key": sleeve.sleeve_key},
            )

    ordered_sleeves: list[SleeveInput] = []
    pending_sleeves = list(payload.sleeves)
    inserted_keys: set[str] = set()
    while pending_sleeves:
        ready = [
            sleeve
            for sleeve in pending_sleeves
            if sleeve.parent_sleeve_key is None or sleeve.parent_sleeve_key in inserted_keys
        ]
        if not ready:
            raise AppError(
                "invalid_sleeve_tree", "Sleeve hierarchy cannot contain a cycle", status_code=422
            )
        ordered_sleeves.extend(ready)
        inserted_keys.update(sleeve.sleeve_key for sleeve in ready)
        pending_sleeves = [sleeve for sleeve in pending_sleeves if sleeve not in ready]

    allowed_keys = [(item.ticker, item.replacement_set_id) for item in payload.allowed_securities]
    if len(set(allowed_keys)) != len(allowed_keys):
        raise AppError(
            "duplicate_allowed_security",
            "ETF candidate entries must be unique within each set",
            status_code=422,
        )
    override_tickers = [item.ticker for item in payload.overrides]
    if len(set(override_tickers)) != len(override_tickers):
        raise AppError(
            "duplicate_override", "Each security can have at most one override", status_code=422
        )
    enabled_targets = {s.sleeve_key for s in payload.sleeves if s.enabled}
    for source_key, target_key in payload.reassignments.items():
        if not source_key or target_key not in enabled_targets:
            raise AppError(
                "invalid_reassignment",
                "Reassignment targets must name an enabled draft sleeve",
                status_code=422,
                details={"source_sleeve_key": source_key, "target_sleeve_key": target_key},
            )
    sector_keys = [item.sector_key for item in payload.sector_bands]
    if len(set(sector_keys)) != len(sector_keys):
        raise AppError("duplicate_sector_band", "Sector keys must be unique", status_code=422)
    if any(not item.sector_key.strip() for item in payload.sector_bands) or any(
        not item.target_weight_pct.is_finite()
        or not item.band_pct.is_finite()
        or not Decimal(0) <= item.target_weight_pct <= ONE_HUNDRED
        or not Decimal(0) <= item.band_pct <= ONE_HUNDRED
        for item in payload.sector_bands
    ):
        raise AppError(
            "invalid_sector_band",
            "Sector targets and bands must be finite values from 0 to 100",
            status_code=422,
        )

    # Cache current holdings and their source-policy resolution to enforce explicit reassignment.
    positions = session.scalars(select(CurrentPosition).order_by(CurrentPosition.id)).all()
    securities = {security.id: security for security in session.scalars(select(Security)).all()}
    resolved_sources: dict[str, tuple[str, str | None]] = {}
    if source is not None:
        source_allocation = load_allocation_policy(session, source.id)
        for position in positions:
            security = securities.get(position.security_id)
            if security is None:
                continue
            old_resolution = resolve_holding(
                source_allocation,
                SecurityIdentity(security.ticker, security.asset_type, security.is_completion_etf),
            )
            if old_resolution.assignment is not None:
                resolved_sources[security.ticker] = (
                    old_resolution.assignment.sleeve_key,
                    old_resolution.assignment.sub_sleeve_key,
                )
    revision_number = (session.scalar(select(func.max(PolicyRevision.revision_number))) or 0) + 1
    revision_id = str(uuid4())
    revision = PolicyRevision(
        id=revision_id,
        revision_number=revision_number,
        status="DRAFT",
        created_at=datetime.now(UTC),
        **payload.settings.model_dump(),
    )
    session.add(revision)
    session.flush()
    for item in payload.sector_bands:
        session.add(
            PolicySectorBand(
                policy_revision_id=revision_id,
                sector_key=item.sector_key,
                target_weight_pct=item.target_weight_pct,
                band_pct=item.band_pct,
            )
        )

    for item in ordered_sleeves:
        session.add(
            PolicySleeve(
                policy_revision_id=revision_id,
                sleeve_key=item.sleeve_key,
                display_name=item.display_name,
                sort_order=item.sort_order,
                parent_sleeve_key=item.parent_sleeve_key,
                target_pct=item.target_pct,
                drift_band_pp=item.drift_band_pp,
                is_direct_index_container=item.is_direct_index_container,
                is_direct_index_sleeve=item.is_direct_index_sleeve,
                is_transition_destination=item.is_transition_destination,
                is_cash_sleeve=item.is_cash_sleeve,
                enabled=item.enabled,
            )
        )

        session.flush()
    session.flush()
    draft_sleeves = _sleeves_by_key(session, revision_id)

    for item in payload.allowed_securities:
        if item.sleeve_key not in enabled_targets or (
            item.sub_sleeve_key and item.sub_sleeve_key not in enabled_targets
        ):
            raise AppError(
                "invalid_allowed_security",
                "Allowed ETFs must reference enabled draft sleeves",
                status_code=422,
                details={"ticker": item.ticker},
            )

        if (
            item.sub_sleeve_key
            and incoming_sleeves[item.sub_sleeve_key].parent_sleeve_key != item.sleeve_key
        ):
            raise AppError(
                "invalid_allowed_security",
                "An ETF sub-sleeve must be a direct child of its assigned sleeve",
                status_code=422,
                details={"ticker": item.ticker},
            )
        security = _security_by_ticker(session, item.ticker)
        if security is None:
            security = Security(
                ticker=item.ticker, asset_type="ETF", is_completion_etf=item.ticker in {"VB", "VXF"}
            )
            session.add(security)
            session.flush()
        elif security.asset_type != "ETF":
            raise AppError(
                "invalid_allowed_security",
                "Allowed replacement candidates must be ETFs",
                status_code=422,
                details={"ticker": item.ticker},
            )
        session.add(
            PolicyAllowedSecurity(
                policy_revision_id=revision_id,
                sleeve_key=item.sleeve_key,
                sub_sleeve_key=item.sub_sleeve_key,
                ticker=item.ticker,
                replacement_set_id=item.replacement_set_id,
                priority=item.priority,
                enabled=item.enabled,
                exposure_suitability=item.exposure_suitability,
            )
        )

    for item in payload.overrides:
        target_key = item.sub_sleeve_key or item.sleeve_key
        if item.sleeve_key not in enabled_targets or target_key not in enabled_targets:
            raise AppError(
                "invalid_override",
                "Overrides must reference enabled draft sleeves",
                status_code=422,
                details={"ticker": item.ticker},
            )

        if (
            item.sub_sleeve_key
            and incoming_sleeves[item.sub_sleeve_key].parent_sleeve_key != item.sleeve_key
        ):
            raise AppError(
                "invalid_override",
                "An override sub-sleeve must be a direct child of its assigned sleeve",
                status_code=422,
                details={"ticker": item.ticker},
            )
        security = _security_by_ticker(session, item.ticker)
        if security is None:
            raise AppError(
                "unknown_override_security",
                "An override must reference a security already known to the managed portfolio",
                status_code=422,
                details={"ticker": item.ticker},
            )
        session.add(
            PolicySecurityOverride(
                policy_revision_id=revision_id,
                security_id=security.id,
                sleeve_key=item.sleeve_key,
                sub_sleeve_key=item.sub_sleeve_key,
            )
        )

    # A removed or disabled holding assignment must have a visible, explicit destination.
    reassigned_overrides = {item.ticker: item for item in payload.overrides}
    for ticker, (old_parent, old_child) in resolved_sources.items():
        old_key = old_child or old_parent
        old_sleeve = incoming_sleeves.get(old_key)
        if old_sleeve is not None and old_sleeve.enabled:
            continue
        target_key = payload.reassignments.get(old_key) or payload.reassignments.get(old_parent)
        explicit = reassigned_overrides.get(ticker)
        if target_key is None and explicit is None:
            raise AppError(
                "reassignment_required",
                "Deleting or disabling a sleeve with held assets requires reassignment",
                status_code=422,
                details={"ticker": ticker, "source_sleeve_key": old_key},
            )
        if explicit is not None:
            continue
        target = _target_parts(target_key or "", draft_sleeves)
        if target is None:
            raise AppError(
                "invalid_reassignment",
                "Reassignment target is missing or disabled",
                status_code=422,
                details={"ticker": ticker, "target_sleeve_key": target_key},
            )
        security = _security_by_ticker(session, ticker)
        if security is not None:
            session.add(
                PolicySecurityOverride(
                    policy_revision_id=revision_id,
                    security_id=security.id,
                    sleeve_key=target[0],
                    sub_sleeve_key=target[1],
                )
            )

    session.flush()
    return revision


def validate_policy_revision(session: Session, revision: PolicyRevision) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    sector_bands = session.scalars(
        select(PolicySectorBand).where(PolicySectorBand.policy_revision_id == revision.id)
    ).all()
    sector_keys = [row.sector_key for row in sector_bands]
    if len(set(sector_keys)) != len(sector_keys):
        errors.append({"code": "duplicate_sector_band", "message": "Sector keys must be unique"})
    if sector_bands:
        if any(
            not row.sector_key.strip()
            or not row.target_weight_pct.is_finite()
            or not row.band_pct.is_finite()
            or not Decimal(0) <= row.target_weight_pct <= ONE_HUNDRED
            or not Decimal(0) <= row.band_pct <= ONE_HUNDRED
            for row in sector_bands
        ):
            errors.append(
                {
                    "code": "invalid_sector_band",
                    "message": "Sector targets and bands must be finite values from 0 to 100",
                }
            )
        if exact_sum(row.target_weight_pct for row in sector_bands) != ONE_HUNDRED:
            errors.append(
                {
                    "code": "sector_target_sum",
                    "message": "Configured sector targets must sum exactly to 100% of invested security exposure",
                }
            )
    sleeves = session.scalars(
        select(PolicySleeve).where(PolicySleeve.policy_revision_id == revision.id)
    ).all()
    by_key = {s.sleeve_key: s for s in sleeves}
    enabled = [s for s in sleeves if s.enabled]
    top = [s for s in enabled if s.parent_sleeve_key is None]
    if not top:
        errors.append(
            {
                "code": "missing_top_level_sleeves",
                "message": "At least one enabled top-level sleeve is required",
            }
        )
    elif exact_sum(s.target_pct for s in top) != ONE_HUNDRED:
        errors.append(
            {
                "code": "top_level_target_sum",
                "message": "Enabled top-level targets must sum exactly to 100%",
            }
        )

    for parent in enabled:
        children = [s for s in enabled if s.parent_sleeve_key == parent.sleeve_key]
        if children and exact_sum(s.target_pct for s in children) != ONE_HUNDRED:
            errors.append(
                {
                    "code": "nested_target_sum",
                    "message": f"Enabled child targets of '{parent.sleeve_key}' must sum exactly to 100%",
                }
            )
    for sleeve in enabled:
        if sleeve.target_pct < 0 or sleeve.drift_band_pp < 0:
            errors.append(
                {
                    "code": "negative_sleeve_value",
                    "message": f"Sleeve '{sleeve.sleeve_key}' has a negative target or band",
                }
            )
        parent = by_key.get(sleeve.parent_sleeve_key or "")
        if sleeve.parent_sleeve_key and (parent is None or not parent.enabled):
            errors.append(
                {
                    "code": "disabled_parent",
                    "message": f"Enabled sleeve '{sleeve.sleeve_key}' has no enabled parent",
                }
            )

    try:
        st_rate = revision.short_term_tax_rate
        lt_rate = revision.long_term_tax_rate
        if st_rate is not None and (st_rate < 0 or st_rate > 1):
            errors.append(
                {
                    "code": "invalid_tax_rate",
                    "message": "Short-term tax rate must be between 0 and 1",
                }
            )
        if lt_rate is not None and (lt_rate < 0 or lt_rate > 1):
            errors.append(
                {
                    "code": "invalid_tax_rate",
                    "message": "Long-term tax rate must be between 0 and 1",
                }
            )
        if st_rate is not None and lt_rate is not None and st_rate < lt_rate:
            errors.append(
                {
                    "code": "invalid_tax_rate_order",
                    "message": "Short-term tax rate must be at least the long-term rate",
                }
            )
        retained = revision.target_retained_net_loss_usd
        deduction = revision.ordinary_income_deduction_limit_usd
        factor = revision.carryforward_loss_discount_factor
        turnover = revision.max_batch_turnover_pct
        buy_minimum = revision.min_buy_order_notional_usd
        cash_reserve = revision.cash_reserve_usd
        if min(retained, deduction, buy_minimum, cash_reserve) < 0:
            errors.append(
                {
                    "code": "invalid_nonnegative_setting",
                    "message": "Loss target, deduction, buy minimum, and cash reserve cannot be negative",
                }
            )
        if not Decimal(0) <= factor <= Decimal(1):
            errors.append(
                {
                    "code": "invalid_discount_factor",
                    "message": "Carryforward discount factor must be between 0 and 1",
                }
            )
        if not Decimal(0) <= turnover <= Decimal(100):
            errors.append(
                {
                    "code": "invalid_turnover",
                    "message": "Batch turnover percent must be between 0 and 100",
                }
            )
        for key in (
            "max_sell_tickers_per_batch",
            "max_sell_lots_per_batch",
            "max_total_orders_per_batch",
        ):
            if getattr(revision, key) <= 0:
                errors.append({"code": "invalid_batch_limit", "message": f"{key} must be positive"})
        has_ytd_values = revision.ytd_realized_st_usd != 0 or revision.ytd_realized_lt_usd != 0
        if (
            has_ytd_values or revision.ytd_source is not None or revision.ytd_as_of is not None
        ) and not (revision.ytd_source and revision.ytd_as_of):
            errors.append(
                {
                    "code": "incomplete_ytd_provenance",
                    "message": "YTD realized amounts require both a source and as-of date",
                }
            )
    except ArithmeticError, ValueError, TypeError:
        errors.append(
            {"code": "invalid_policy_settings", "message": "Policy settings are malformed"}
        )
    if sum(1 for s in enabled if s.is_direct_index_container) > 1:
        errors.append(
            {
                "code": "multiple_direct_index_containers",
                "message": "Only one enabled direct-indexing container is allowed",
            }
        )
    if sum(1 for s in enabled if s.is_cash_sleeve) > 1:
        errors.append(
            {"code": "multiple_cash_sleeves", "message": "Only one enabled cash sleeve is allowed"}
        )

    allocation = load_allocation_policy(session, revision.id)
    held_securities = session.execute(
        select(
            CurrentPosition.security_id,
            Security.ticker,
            Security.asset_type,
            Security.is_completion_etf,
        ).join(Security, Security.id == CurrentPosition.security_id)
    ).all()
    destination_resolution = resolve_transition_destination(allocation)
    if destination_resolution.reason is not None:
        destination_messages = {
            "multiple_transition_destinations": "Only one enabled transition destination sleeve is allowed",
            "transition_destination_requires_unique_direct_index_container": (
                "An enabled transition destination requires exactly one enabled direct-indexing container"
            ),
            "transition_destination_has_invalid_container_ancestry": (
                "The direct-indexing container must have valid enabled ancestry"
            ),
            "transition_destination_outside_direct_index_container": (
                "The transition destination must be a strict descendant of the direct-indexing container"
            ),
            "transition_destination_overlaps_direct_index_branch": (
                "The transition destination cannot overlap the legacy direct-indexing branch"
            ),
        }
        errors.append(
            {
                "code": destination_resolution.reason,
                "message": destination_messages[destination_resolution.reason],
            }
        )
    for _, ticker, asset_type, is_completion_etf in held_securities:
        resolution = resolve_holding(
            allocation,
            SecurityIdentity(ticker, asset_type, is_completion_etf),
        )
        if resolution.assignment is None:
            errors.append(
                {
                    "code": "unassigned_holding",
                    "message": f"Held security '{ticker}' has no enabled policy sleeve ({resolution.reason})",
                }
            )

    return errors


def activate_policy(
    session: Session, revision_id: str
) -> tuple[PolicyRevision, list[dict[str, str]]]:
    revision = session.get(PolicyRevision, revision_id)
    if revision is None:
        raise AppError(
            "policy_revision_not_found", "Policy revision was not found", status_code=404
        )
    if revision.activated_at is not None or revision.status != "DRAFT":
        raise AppError(
            "policy_immutable",
            "Activated policy revisions cannot be changed or reactivated",
            status_code=409,
        )
    errors = validate_policy_revision(session, revision)
    if errors:
        return revision, errors
    now = datetime.now(UTC)
    for previous in session.scalars(
        select(PolicyRevision).where(PolicyRevision.status == "ACTIVE")
    ).all():
        previous.status = "SUPERSEDED"
    revision.status = "ACTIVE"
    revision.activated_at = now
    session.flush()
    return revision, []


def _policy_settings(revision: PolicyRevision) -> dict[str, object]:
    result: dict[str, object] = {}
    for name in PolicySettingsInput.model_fields:
        value = getattr(revision, name)
        if isinstance(value, Decimal):
            result[name] = str(value)
        elif isinstance(value, date):
            result[name] = value.isoformat()
        else:
            result[name] = value
    return result


def policy_to_dict(session: Session, revision: PolicyRevision) -> dict[str, object]:
    sleeves = session.scalars(
        select(PolicySleeve)
        .where(PolicySleeve.policy_revision_id == revision.id)
        .order_by(PolicySleeve.sort_order, PolicySleeve.sleeve_key)
    ).all()
    allowed = session.scalars(
        select(PolicyAllowedSecurity)
        .where(PolicyAllowedSecurity.policy_revision_id == revision.id)
        .order_by(PolicyAllowedSecurity.sleeve_key, PolicyAllowedSecurity.priority)
    ).all()
    overrides = session.execute(
        select(PolicySecurityOverride, Security.ticker)
        .join(Security, Security.id == PolicySecurityOverride.security_id)
        .where(PolicySecurityOverride.policy_revision_id == revision.id)
        .order_by(PolicySecurityOverride.security_id)
    ).all()
    sector_bands = session.scalars(
        select(PolicySectorBand)
        .where(PolicySectorBand.policy_revision_id == revision.id)
        .order_by(PolicySectorBand.sector_key)
    ).all()
    return {
        "id": revision.id,
        "revision_number": revision.revision_number,
        "status": revision.status,
        "created_at": revision.created_at,
        "activated_at": revision.activated_at,
        "settings": _policy_settings(revision),
        "sector_bands": [
            {
                "sector_key": row.sector_key,
                "target_weight_pct": str(row.target_weight_pct),
                "band_pct": str(row.band_pct),
            }
            for row in sector_bands
        ],
        "sleeves": [
            {
                "sleeve_key": s.sleeve_key,
                "display_name": s.display_name,
                "sort_order": s.sort_order,
                "parent_sleeve_key": s.parent_sleeve_key,
                "target_pct": str(s.target_pct),
                "drift_band_pp": str(s.drift_band_pp),
                "is_direct_index_container": s.is_direct_index_container,
                "is_direct_index_sleeve": s.is_direct_index_sleeve,
                "is_transition_destination": s.is_transition_destination,
                "is_cash_sleeve": s.is_cash_sleeve,
                "enabled": s.enabled,
            }
            for s in sleeves
        ],
        "allowed_securities": [
            {
                "ticker": a.ticker,
                "sleeve_key": a.sleeve_key,
                "sub_sleeve_key": a.sub_sleeve_key,
                "replacement_set_id": a.replacement_set_id,
                "priority": a.priority,
                "enabled": a.enabled,
                "exposure_suitability": a.exposure_suitability,
            }
            for a in allowed
        ],
        "overrides": [
            {
                "ticker": ticker,
                "sleeve_key": override.sleeve_key,
                "sub_sleeve_key": override.sub_sleeve_key,
            }
            for override, ticker in overrides
        ],
    }
