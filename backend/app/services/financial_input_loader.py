from __future__ import annotations

import hashlib
import json
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Account,
    BrokerTransaction,
    CurrentPosition,
    CurrentQuote,
    CurrentTaxLot,
    PolicyAllowedSecurity,
    PolicyRevision,
    PolicySecurityOverride,
    PolicySleeve,
    Security,
    SyncState,
)
from app.domain.allocation import (
    AllocationPolicy,
    AllocationSleeve,
    AllowedSecurity,
    SecurityIdentity,
    SecurityOverride,
    SleeveAssignment,
    resolve_holding,
)
from app.domain.financial_inputs import (
    AccountInput,
    FinancialInputs,
    LotInput,
    PolicyInput,
    PolicySettings,
    PositionInput,
    QuoteInput,
    SecurityInput,
    TransactionInput,
)
from app.schemas import PolicySettingsInput
from app.services.errors import AppError


def _fingerprint(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def load_allocation_policy(session: Session, revision_id: str) -> AllocationPolicy:
    """Load policy lookup tables in three bounded queries; do not resolve through the ORM."""
    sleeves = session.scalars(
        select(PolicySleeve)
        .where(PolicySleeve.policy_revision_id == revision_id)
        .order_by(PolicySleeve.sort_order, PolicySleeve.sleeve_key)
    ).all()
    allowed = session.scalars(
        select(PolicyAllowedSecurity)
        .where(PolicyAllowedSecurity.policy_revision_id == revision_id)
        .order_by(PolicyAllowedSecurity.ticker, PolicyAllowedSecurity.priority, PolicyAllowedSecurity.id)
    ).all()
    override_rows = session.execute(
        select(PolicySecurityOverride, Security.ticker)
        .join(Security, Security.id == PolicySecurityOverride.security_id)
        .where(PolicySecurityOverride.policy_revision_id == revision_id)
        .order_by(PolicySecurityOverride.security_id)
    ).all()
    return AllocationPolicy(
        sleeves=tuple(
            AllocationSleeve(
                key=row.sleeve_key,
                parent_key=row.parent_sleeve_key,
                enabled=row.enabled,
                direct_index_container=row.is_direct_index_container,
                direct_index_sleeve=row.is_direct_index_sleeve,
                cash_sleeve=row.is_cash_sleeve,
                display_name=row.display_name,
                sort_order=row.sort_order,
                target_pct=row.target_pct,
                drift_band_pp=row.drift_band_pp,
            )
            for row in sleeves
        ),
        allowed_securities=tuple(
            AllowedSecurity(
                ticker=row.ticker,
                sleeve_key=row.sleeve_key,
                sub_sleeve_key=row.sub_sleeve_key,
                priority=row.priority,
                enabled=row.enabled,
                replacement_set_id=row.replacement_set_id,
                exposure_suitability=row.exposure_suitability,
            )
            for row in allowed
        ),
        overrides=tuple(
            SecurityOverride(
                ticker=ticker,
                sleeve_key=row.sleeve_key,
                sub_sleeve_key=row.sub_sleeve_key,
            )
            for row, ticker in override_rows
        ),
    )


def load_policy_input(session: Session, revision: PolicyRevision) -> PolicyInput:
    allocation = load_allocation_policy(session, revision.id)
    settings = {
        field: getattr(revision, field)
        for field in PolicySettingsInput.model_fields
    }
    return PolicyInput(
        revision_id=revision.id,
        allocation=allocation,
        settings=PolicySettings.from_mapping(settings),
        revision_number=revision.revision_number,
        status=revision.status,
        created_at=revision.created_at,
        activated_at=revision.activated_at,
    )


def load_financial_inputs(
    session: Session,
    account: Account,
    sync_state: SyncState | None,
    revision: PolicyRevision | None,
    proposed_trade_date: date,
    *,
    include_tax_lots: bool = True,
    include_transactions: bool = True,
    require_resolved_assignments: bool = True,
) -> FinancialInputs:
    """Bulk-load current relational inputs once and map them to immutable domain values."""
    securities = session.scalars(select(Security).order_by(Security.ticker)).all()
    quotes = session.scalars(select(CurrentQuote).order_by(CurrentQuote.security_id)).all()
    positions = session.scalars(
        select(CurrentPosition)
        .where(CurrentPosition.account_id == account.id)
        .order_by(CurrentPosition.security_id)
    ).all()
    lots = (
        session.scalars(
            select(CurrentTaxLot)
            .where(CurrentTaxLot.account_id == account.id)
            .order_by(CurrentTaxLot.broker_lot_id)
        ).all()
        if include_tax_lots
        else []
    )
    transactions = (
        session.scalars(
            select(BrokerTransaction)
            .where(BrokerTransaction.account_id == account.id)
            .order_by(BrokerTransaction.trade_date, BrokerTransaction.transaction_time)
        ).all()
        if include_transactions
        else []
    )
    policy = (
        load_policy_input(session, revision)
        if revision is not None
        else PolicyInput("", AllocationPolicy((), (), ()), PolicySettings.from_mapping({}))
    )
    security_by_id = {row.id: row for row in securities}

    assignment_by_id: dict[int, SleeveAssignment | None] = {}
    for position in positions:
        security = security_by_id.get(position.security_id)
        if security is None:
            raise AppError("current_state_inconsistent", "A current position references an unknown security", status_code=409)
        resolution = (
            resolve_holding(
                policy.allocation,
                SecurityIdentity(security.ticker, security.asset_type, security.is_completion_etf),
            )
            if revision is not None
            else None
        )
        assignment = resolution.assignment if resolution is not None else None
        if assignment is None and require_resolved_assignments:
            raise AppError(
                "unassigned_holding",
                "Every current holding must resolve to an active policy sleeve",
                status_code=422,
                details={
                    "ticker": security.ticker,
                    "reason": resolution.reason if resolution is not None else "no_active_policy",
                },
            )
        assignment_by_id[security.id] = assignment
    quote_inputs = tuple(
        QuoteInput(
            ticker=security_by_id[row.security_id].ticker,
            bid_usd=row.bid_usd,
            ask_usd=row.ask_usd,
            last_usd=row.last_usd,
            source=row.source,
            as_of=row.as_of,
            quality=row.quality,
            sync_generation=row.sync_generation,
        )
        for row in quotes
        if row.security_id in security_by_id
    )
    position_inputs = tuple(
        PositionInput(
            ticker=security_by_id[row.security_id].ticker,
            asset_type=security_by_id[row.security_id].asset_type,
            is_completion_etf=security_by_id[row.security_id].is_completion_etf,
            shares=row.shares,
            sync_generation=row.sync_generation,
            as_of=row.as_of,
            market_value_usd=row.market_value_usd,
            assignment=assignment_by_id[row.security_id],
        )
        for row in positions
        if row.security_id in security_by_id
    )
    lot_inputs = tuple(
        LotInput(
            ticker=security_by_id[row.security_id].ticker,
            broker_lot_id=row.broker_lot_id,
            acquired_date=row.acquired_date,
            shares=row.shares,
            available_shares=row.available_shares,
            adjusted_unit_basis_usd=row.adjusted_unit_basis_usd,
            broker_wash_adjustment_usd=row.broker_wash_adjustment_usd,
            source=row.source,
            as_of=row.as_of,
            fractional_cleanup_unsupported=row.fractional_cleanup_unsupported,
            quality_flags=tuple(row.quality_flags),
            sync_generation=row.sync_generation,
        )
        for row in lots
        if row.security_id in security_by_id
    )
    transaction_inputs = tuple(
        TransactionInput(
            broker_transaction_key=row.broker_transaction_key,
            ticker=security_by_id[row.security_id].ticker,
            transaction_kind=row.transaction_kind,
            transaction_time=row.transaction_time,
            trade_date=row.trade_date,
            shares=row.shares,
            amount_usd=row.amount_usd,
            is_acquisition=row.is_acquisition,
            broker_lot_id=row.broker_lot_id,
            source=row.source,
        )
        for row in transactions
        if row.security_id in security_by_id
    )
    return FinancialInputs(
        account=AccountInput(
            local_account_id=account.id,
            account_key_fingerprint=_fingerprint(account.broker_account_id_key),
            display_name=account.display_name,
            account_type=account.account_type,
            tax_treatment=account.tax_treatment,
            source=account.source,
            as_of=account.as_of,
            cash_usd=account.cash_usd,
            settled_buying_power_usd=account.settled_buying_power_usd,
        ),
        source_generation=sync_state.current_generation if sync_state is not None else 0,
        proposed_trade_date=proposed_trade_date,
        policy=policy,
        securities=tuple(
            SecurityInput(SecurityIdentity(row.ticker, row.asset_type, row.is_completion_etf), row.id, row.tradable)
            for row in securities
        ),
        positions=position_inputs,
        lots=lot_inputs,
        quotes=quote_inputs,
        transactions=transaction_inputs,
    )
