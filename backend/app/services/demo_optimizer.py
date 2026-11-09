from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Account,
    ActivityEvent,
    BrokerTransaction,
    CurrentPosition,
    CurrentQuote,
    CurrentTaxLot,
    OptimizerRun,
    PolicyAllowedSecurity,
    PolicyRevision,
    PolicySecurityOverride,
    PolicySleeve,
    RecommendationGroup,
    RecommendationGroupLeg,
    RecommendationLeg,
    RecommendationSelectedLot,
    Security,
    SyncState,
)
from app.domain.decimal_math import (
    exact_percent_product,
    exact_product,
    exact_sum,
    whole_share_floor,
)
from app.domain.financial_inputs import (
    FinancialInputs,
    LotInput,
    financial_inputs_from_provenance,
)
from app.domain.portfolio_accounting import (
    BasketValidationError,
    ConsolidatedLeg,
    LotAllocation,
    evaluate_portfolio,
)
from app.domain.trade_dates import resolve_proposed_trade_date
from app.schemas import (
    FrozenRunDisplayContextResponse,
    OptimizerLotReviewIntentInput,
    OptimizerRunInput,
    OptimizerSelectionInput,
)
from app.services.demo_candidates import _candidate_groups, _datetime_iso, _decimal
from app.services.errors import AppError
from app.services.financial_input_loader import load_financial_inputs
from app.services.policy import validate_policy_revision
from app.services.portfolio_presentation import present_portfolio_evaluation

DEMO_WARNING = "real_optimizer_unavailable"
DEMO_WASH_WARNING = "wash_sale_validation_deferred_demo"
DEMO_RISK_WARNING = "risk_tracking_validation_not_run_demo"


def _fingerprint(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()



def _active_policy(session: Session) -> PolicyRevision:
    policy = session.scalar(select(PolicyRevision).where(PolicyRevision.status == "ACTIVE"))
    if policy is None:
        raise AppError("active_policy_required", "An active policy is required to create demo recommendations", status_code=409)
    errors = validate_policy_revision(session, policy)
    if errors:
        raise AppError(
            "policy_invalid",
            "The active policy is invalid; no recommendations were created",
            status_code=422,
            details=errors,
        )
    return policy


def _frozen_input(
    session: Session,
    account: Account,
    sync_state: SyncState,
    policy: PolicyRevision,
    proposed_trade_date: date,
) -> FinancialInputs:
    if not sync_state.complete or sync_state.current_generation < 1:
        raise AppError("current_state_unavailable", "A complete current portfolio sync is required", status_code=409)
    required = ("positions", "lots", "transactions", "balances", "quotes")
    missing = [key for key in required if not sync_state.coverage.get(key, False)]
    if missing:
        raise AppError(
            "current_state_incomplete",
            "Current portfolio data is incomplete; no demo recommendations were created",
            status_code=422,
            details={"incomplete_sections": missing},
        )
    if (
        not account.cash_usd.is_finite()
        or not account.settled_buying_power_usd.is_finite()
        or account.cash_usd < 0
        or account.settled_buying_power_usd < 0
    ):
        raise AppError("invalid_current_balance", "Current account balances must be finite and nonnegative", status_code=422)

    inputs = load_financial_inputs(session, account, sync_state, policy, proposed_trade_date)
    quotes_by_ticker = {quote.ticker: quote for quote in inputs.quotes}
    positions_by_ticker = {position.ticker: position for position in inputs.positions}
    lots_by_ticker: dict[str, list[LotInput]] = {}
    for position in inputs.positions:
        quote = quotes_by_ticker.get(position.ticker)
        if position.sync_generation != sync_state.current_generation:
            raise AppError("current_state_inconsistent", "Current position data is inconsistent", status_code=409)
        if position.shares <= 0 or position.market_value_usd < 0:
            raise AppError("invalid_position", "Current positions require positive shares and nonnegative value", status_code=422)
        if quote is None or quote.sync_generation != sync_state.current_generation or quote.last_usd is None:
            raise AppError(
                "quote_unavailable",
                "Every held position requires a quote from the current complete sync",
                status_code=422,
                details={"ticker": position.ticker},
            )
        if quote.quality.lower() != "good" or quote.last_usd <= 0:
            raise AppError(
                "quote_unavailable",
                "A current position has a stale or unusable quote",
                status_code=422,
                details={"ticker": position.ticker, "quality": quote.quality},
            )
    for lot in inputs.lots:
        if lot.sync_generation != sync_state.current_generation:
            raise AppError("current_state_inconsistent", "Current tax-lot data is inconsistent", status_code=409)
        if lot.shares <= 0 or lot.available_shares < 0 or lot.available_shares > lot.shares:
            raise AppError(
                "invalid_lot_quantity",
                "Current tax-lot quantities are invalid; no demo recommendations were created",
                status_code=422,
                details={"broker_lot_id": lot.broker_lot_id},
            )
        if lot.adjusted_unit_basis_usd < 0:
            raise AppError("invalid_lot_basis", "Adjusted lot basis cannot be negative", status_code=422)
        lots_by_ticker.setdefault(lot.ticker, []).append(lot)
    if set(lots_by_ticker) != set(positions_by_ticker) or any(
        exact_sum(lot.shares for lot in lots_by_ticker[ticker]) != position.shares
        for ticker, position in positions_by_ticker.items()
    ):
        raise AppError(
            "incomplete_lots",
            "Current tax lots do not exactly cover all positions; no demo recommendations were created",
            status_code=422,
        )

    provenance = inputs.to_provenance()
    provenance.pop("source_checksum", None)
    source_checksum = _fingerprint(provenance)
    return replace(inputs, source_checksum=source_checksum)






def _add_demo_group(session: Session, run: OptimizerRun, rank: int, data: dict[str, object]) -> RecommendationGroup:
    ticker = str(data["ticker"])
    source_price = _decimal(data["source_price"])
    source_quote = data["source_quote"]
    replacement = data["replacement"]
    assert isinstance(source_quote, dict)
    assert isinstance(replacement, dict)
    replacement_ticker = str(replacement["ticker"])
    replacement_price = _decimal(replacement["price"])
    group_id = str(uuid4())
    sell_leg_id = str(uuid4())
    buy_leg_id = str(uuid4())
    lots = data["sell_lots"]
    assert isinstance(lots, list)
    shares = exact_sum(_decimal(lot["proposed_shares"]) for lot in lots)
    # Recalculation below fills realized tax fields from the shared accounting result.
    group = RecommendationGroup(
        id=group_id,
        run_id=run.id,
        rank=rank,
        group_type="demo_loss_harvest",
        sleeve_key=str(data["sleeve_key"]),
        rationale=(
            f"DEMO only: sell loss lots in {ticker} and resize a configured {replacement_ticker} buy. "
            "This is not optimizer-validated or actionable."
        ),
        estimated_benefit_usd=None,
        impact={"demo": True, "wash_status": "not_validated_demo"},
        dependencies=[],
        selected=True,
        rejected=False,
    )
    session.add(group)
    session.add(
        RecommendationLeg(
            id=sell_leg_id,
            group_id=group_id,
            account_id=1,
            security_id=_security_id(session, ticker),
            side="SELL",
            shares=shares,
            estimated_unit_price_usd=source_price,
            net_st_realized_usd=Decimal(0),
            net_lt_realized_usd=Decimal(0),
            sequence=1,
            details={
                "quote_as_of": source_quote["as_of"],
                "quote_source": source_quote["source"],
                "sleeve_key": data["sleeve_key"],
                "sub_sleeve_key": data["sub_sleeve_key"],
                "original_shares": str(shares),
            },
        )
    )
    session.add(
        RecommendationLeg(
            id=buy_leg_id,
            group_id=group_id,
            account_id=1,
            security_id=_security_id(session, replacement_ticker),
            side="BUY",
            shares=Decimal(0),
            estimated_unit_price_usd=replacement_price,
            net_st_realized_usd=Decimal(0),
            net_lt_realized_usd=Decimal(0),
            sequence=2,
            details={
                "sleeve_key": replacement["sleeve_key"],
                "sub_sleeve_key": replacement["sub_sleeve_key"],
                "depends_on_leg_id": sell_leg_id,
                "quote_as_of": replacement["quote"]["as_of"],
                "quote_source": replacement["quote"]["source"],
                "min_buy_order_notional_usd": str(replacement.get("min_buy_order_notional_usd", "0")),
            },
        )
    )
    for lot in lots:
        proposed_shares = _decimal(lot["proposed_shares"])
        acquired = lot["acquired_date"]
        if not isinstance(acquired, date):
            acquired = date.fromisoformat(str(acquired))
        # Recalculation replaces these placeholders with date-classified lot effects.
        term = "ST"
        realized = Decimal(0)
        session.add(
            RecommendationSelectedLot(
                leg_id=sell_leg_id,
                broker_lot_id=str(lot["broker_lot_id"]),
                shares=proposed_shares,
                acquired_date=acquired,
                adjusted_basis_usd=_decimal(lot["adjusted_unit_basis_usd"]),
                st_lt_term=term,
                realized_pl_usd=realized,
                selected=True,
            )
        )
    return group


def _consolidate_replacement_legs(session: Session, run: OptimizerRun) -> None:
    groups = session.scalars(
        select(RecommendationGroup).where(RecommendationGroup.run_id == run.id).order_by(RecommendationGroup.rank)
    ).all()
    buys_by_security: dict[int, list[RecommendationLeg]] = {}
    for group in groups:
        legs = session.scalars(
            select(RecommendationLeg).where(RecommendationLeg.group_id == group.id).order_by(RecommendationLeg.sequence)
        ).all()
        for leg in legs:
            if session.get(RecommendationGroupLeg, (group.id, leg.id)) is None:
                session.add(RecommendationGroupLeg(group_id=group.id, leg_id=leg.id))
            if leg.side == "BUY":
                buys_by_security.setdefault(leg.security_id, []).append(leg)
    session.flush()
    for buy_legs in buys_by_security.values():
        canonical = buy_legs[0]
        linked_groups = list(dict.fromkeys(leg.group_id for leg in buy_legs))
        funding_sells = session.scalars(
            select(RecommendationLeg).where(
                RecommendationLeg.group_id.in_(linked_groups), RecommendationLeg.side == "SELL"
            ).order_by(RecommendationLeg.sequence, RecommendationLeg.id)
        ).all()
        details = dict(canonical.details)
        details.pop("depends_on_leg_id", None)
        details["depends_on_leg_ids"] = [leg.id for leg in funding_sells]
        canonical.details = details
        canonical.shares = exact_sum(leg.shares for leg in buy_legs)
        for group_id in linked_groups:
            if session.get(RecommendationGroupLeg, (group_id, canonical.id)) is None:
                session.add(RecommendationGroupLeg(group_id=group_id, leg_id=canonical.id))
        for duplicate in buy_legs[1:]:
            session.query(RecommendationGroupLeg).filter_by(leg_id=duplicate.id).delete(synchronize_session=False)
            session.delete(duplicate)


def _security_id(session: Session, ticker: str) -> int:
    security = session.scalar(select(Security).where(Security.ticker == ticker))
    if security is None:
        raise AppError("candidate_security_unavailable", "Configured ETF candidate is not in the current catalog", status_code=422)
    return security.id


def create_demo_run(
    session: Session,
    request: OptimizerRunInput,
    *,
    broker_mode: str,
    correlation_id: str,
) -> OptimizerRun:
    if request.mode == "real_optimizer":
        raise AppError(
            DEMO_WARNING,
            "The real optimizer is not implemented; no optimizer run was attempted",
            status_code=503,
            details={"mode": "real_optimizer", "available": False, "actionable": False},
        )
    if broker_mode.lower() != "fake":
        raise AppError(
            "demo_mode_unavailable",
            "Recommendations-only demo mode requires the deterministic FakeBroker",
            status_code=503,
            details={"broker_mode": broker_mode, "actionable": False},
        )
    account = session.get(Account, 1)
    sync_state = session.get(SyncState, 1)
    if account is None or sync_state is None or account.source.upper() not in {"DEMO", "FAKE"}:
        raise AppError("demo_account_required", "A seeded FakeBroker demo account is required", status_code=409)
    policy = _active_policy(session)
    proposed_trade_date = resolve_proposed_trade_date(request.proposed_trade_date, demo=True)
    inputs = _frozen_input(session, account, sync_state, policy, proposed_trade_date)
    configured = {
        "max_sell_tickers_per_batch": policy.max_sell_tickers_per_batch,
        "max_sell_lots_per_batch": policy.max_sell_lots_per_batch,
        "max_total_orders_per_batch": policy.max_total_orders_per_batch,
    }
    requested = request.model_dump(exclude={"mode", "proposed_trade_date"}, exclude_none=True)
    for key, value in requested.items():
        if value > configured[key]:
            raise AppError(
                "batch_override_exceeds_policy",
                "Per-run batch overrides may tighten but cannot widen the active policy",
                status_code=422,
                details={"setting": key, "policy_limit": configured[key]},
            )
        configured[key] = value
    batch_settings: dict[str, object] = {
        **configured,
        "max_batch_turnover_pct": str(policy.max_batch_turnover_pct),
        "min_buy_order_notional_usd": str(policy.min_buy_order_notional_usd),
        "cash_reserve_usd": str(policy.cash_reserve_usd),
    }
    bundle = inputs.to_provenance()
    bundle["batch_settings"] = batch_settings
    fingerprint = _fingerprint(bundle)
    bundle["input_fingerprint"] = fingerprint
    run = OptimizerRun(
        id=str(uuid4()),
        policy_revision_id=policy.id,
        source_generation=sync_state.current_generation,
        as_of=inputs.account.as_of,
        proposed_trade_date=proposed_trade_date,
        solver_version="DEMO",
        status="COMPLETE",
        batch_settings=batch_settings,
        metrics={},
        warnings=[DEMO_WARNING, DEMO_WASH_WARNING, DEMO_RISK_WARNING],
        input_fingerprint=fingerprint,
        frozen_input_bundle=bundle,
    )
    session.add(run)
    session.flush()
    candidates = _candidate_groups(inputs, batch_settings)
    for rank, candidate in enumerate(candidates, start=1):
        _add_demo_group(session, run, rank, candidate)
    session.flush()
    _consolidate_replacement_legs(session, run)
    session.flush()
    groups = session.scalars(
        select(RecommendationGroup).where(RecommendationGroup.run_id == run.id).order_by(RecommendationGroup.rank)
    ).all()
    selected_lots = {
        group.id: [
            row.broker_lot_id
            for row in _group_lot_rows(session, group.id)
        ]
        for group in groups
    }
    _recalculate_selection(session, run, {group.id for group in groups}, selected_lots)
    _add_activity(
        session,
        correlation_id,
        "optimizer_run",
        {"run_id": run.id, "policy_revision_id": policy.id, "source_generation": run.source_generation, "demo": True},
    )
    return run


def _group_lot_rows(session: Session, group_id: str) -> list[RecommendationSelectedLot]:
    sell_leg = session.scalar(
        select(RecommendationLeg).where(
            RecommendationLeg.group_id == group_id,
            RecommendationLeg.side == "SELL",
        )
    )
    if sell_leg is None:
        return []
    return session.scalars(
        select(RecommendationSelectedLot)
        .where(RecommendationSelectedLot.leg_id == sell_leg.id)
        .order_by(RecommendationSelectedLot.broker_lot_id)
    ).all()

def _group_legs(session: Session, group_id: str) -> list[RecommendationLeg]:
    return session.scalars(
        select(RecommendationLeg)
        .join(RecommendationGroupLeg, RecommendationGroupLeg.leg_id == RecommendationLeg.id)
        .where(RecommendationGroupLeg.group_id == group_id)
        .order_by(RecommendationLeg.sequence, RecommendationLeg.id)
    ).all()



def _check_run_current(session: Session, run: OptimizerRun) -> None:
    state = session.get(SyncState, 1)
    active = session.scalar(select(PolicyRevision).where(PolicyRevision.status == "ACTIVE"))
    if state is None or not state.complete or state.current_generation != run.source_generation:
        raise AppError(
            "stale_run_source",
            "The saved run is stale after a portfolio sync; create a new demo run before changing its selection",
            status_code=409,
            details={"run_source_generation": run.source_generation, "current_generation": state.current_generation if state else None},
        )
    if active is None or active.id != run.policy_revision_id:
        raise AppError(
            "stale_run_policy",
            "The saved run uses a superseded policy; create a new demo run before changing its selection",
            status_code=409,
            details={"run_policy_revision_id": run.policy_revision_id, "active_policy_revision_id": active.id if active else None},
        )
    bundle = run.frozen_input_bundle
    fingerprint_payload = {key: value for key, value in bundle.items() if key != "input_fingerprint"}
    if (
        not run.input_fingerprint
        or bundle.get("input_fingerprint") != run.input_fingerprint
        or _fingerprint(fingerprint_payload) != run.input_fingerprint
    ):
        raise AppError("run_provenance_invalid", "Saved demo run provenance is incomplete or changed", status_code=409)
    if run.proposed_trade_date is None:
        raise AppError("run_trade_date_missing", "Saved run trade-date provenance is missing", status_code=409)
    try:
        frozen_inputs = financial_inputs_from_provenance(
            bundle, proposed_trade_date=run.proposed_trade_date
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise AppError("run_provenance_invalid", "Saved run financial inputs cannot be reconstructed", status_code=409) from exc

    account = session.get(Account, 1)
    frozen_account = frozen_inputs.account
    if (
        account is None
        or account.source != frozen_account.source
        or account.cash_usd != frozen_account.cash_usd
        or account.settled_buying_power_usd != frozen_account.settled_buying_power_usd
        or account.as_of != frozen_account.as_of
        or _fingerprint(account.broker_account_id_key) != frozen_account.account_key_fingerprint
    ):
        raise AppError("stale_run_account", "Current account values changed; create a new demo run", status_code=409)

    securities = {row.id: row for row in session.scalars(select(Security)).all()}
    frozen_positions = {row.ticker: row for row in frozen_inputs.positions}
    current_positions = session.scalars(
        select(CurrentPosition).where(CurrentPosition.account_id == account.id)
    ).all()
    live_positions = {
        securities[row.security_id].ticker: row
        for row in current_positions
        if row.security_id in securities
    }
    if set(live_positions) != set(frozen_positions):
        raise AppError("stale_run_positions", "Current positions changed; create a new demo run", status_code=409)
    frozen_quotes = {row.ticker: row for row in frozen_inputs.quotes}

    def quote_matches(ticker: str, security_id: int) -> bool:
        frozen_quote = frozen_quotes.get(ticker)
        live_quote = session.scalar(select(CurrentQuote).where(CurrentQuote.security_id == security_id))
        return bool(
            frozen_quote is not None
            and live_quote is not None
            and live_quote.sync_generation == run.source_generation
            and live_quote.quality.lower() == "good"
            and live_quote.bid_usd == frozen_quote.bid_usd
            and live_quote.ask_usd == frozen_quote.ask_usd
            and live_quote.last_usd == frozen_quote.last_usd
            and live_quote.source == frozen_quote.source
            and live_quote.quality == frozen_quote.quality
            and live_quote.as_of == frozen_quote.as_of
        )

    for ticker, frozen in frozen_positions.items():
        position = live_positions[ticker]
        security = securities[position.security_id]
        if (
            position.sync_generation != run.source_generation
            or position.shares != frozen.shares
            or position.market_value_usd != frozen.market_value_usd
            or position.as_of != frozen.as_of
            or security.asset_type != frozen.asset_type
            or security.is_completion_etf != frozen.is_completion_etf
            or not quote_matches(ticker, security.id)
        ):
            raise AppError(
                "stale_run_positions",
                "Current holdings or quotes changed; create a new demo run",
                status_code=409,
                details={"ticker": ticker},
            )

    for group in session.scalars(select(RecommendationGroup).where(RecommendationGroup.run_id == run.id)).all():
        for leg in session.scalars(select(RecommendationLeg).where(RecommendationLeg.group_id == group.id)).all():
            security = session.get(Security, leg.security_id)
            if security is None or not quote_matches(security.ticker, security.id):
                raise AppError(
                    "stale_run_quote",
                    "A recommendation quote changed or is no longer current; create a new demo run",
                    status_code=409,
                    details={"ticker": security.ticker if security else None},
                )

    frozen_lots = {row.broker_lot_id: row for row in frozen_inputs.lots}
    for group in session.scalars(select(RecommendationGroup).where(RecommendationGroup.run_id == run.id)).all():
        for row in _group_lot_rows(session, group.id):
            live = session.scalar(
                select(CurrentTaxLot).where(
                    CurrentTaxLot.account_id == account.id,
                    CurrentTaxLot.broker_lot_id == row.broker_lot_id,
                )
            )
            frozen = frozen_lots.get(row.broker_lot_id)
            security = securities.get(live.security_id) if live is not None else None
            if (
                live is None
                or frozen is None
                or security is None
                or live.sync_generation != run.source_generation
                or live.shares != frozen.shares
                or live.available_shares != frozen.available_shares
                or live.adjusted_unit_basis_usd != frozen.adjusted_unit_basis_usd
                or live.broker_wash_adjustment_usd != frozen.broker_wash_adjustment_usd
                or live.source != frozen.source
                or live.as_of != frozen.as_of
                or live.fractional_cleanup_unsupported != frozen.fractional_cleanup_unsupported
                or tuple(live.quality_flags) != frozen.quality_flags
                or live.acquired_date != frozen.acquired_date
                or security.ticker != frozen.ticker
                or live.available_shares < row.shares
            ):
                raise AppError(
                    "stale_run_lot",
                    "A proposed sell lot is unavailable or has changed; create a new demo run",
                    status_code=409,
                    details={"broker_lot_id": row.broker_lot_id},
                )

def _recalculate_selection(
    session: Session,
    run: OptimizerRun,
    selected_group_ids: set[str],
    selected_lots_by_group: dict[str, list[str]],
) -> None:
    bundle = run.frozen_input_bundle
    if run.proposed_trade_date is None:
        raise AppError("run_trade_date_missing", "Saved run has no proposed trade-date provenance", status_code=409)
    try:
        inputs = financial_inputs_from_provenance(bundle, proposed_trade_date=run.proposed_trade_date)
    except (KeyError, TypeError, ValueError) as exc:
        raise AppError("run_provenance_invalid", "Saved run financial inputs cannot be reconstructed", status_code=409) from exc
    groups = session.scalars(
        select(RecommendationGroup).where(RecommendationGroup.run_id == run.id).order_by(RecommendationGroup.rank)
    ).all()
    known_group_ids = {group.id for group in groups}
    if selected_group_ids - known_group_ids:
        raise AppError(
            "invalid_group_selection",
            "Selection contains a group that does not belong to this run",
            status_code=422,
            details={"unknown_group_ids": sorted(selected_group_ids - known_group_ids)},
        )
    if set(selected_lots_by_group) - selected_group_ids:
        raise AppError(
            "invalid_lot_selection",
            "Sell-lot selections may only be supplied for selected groups",
            status_code=422,
            details={"unselected_group_ids": sorted(set(selected_lots_by_group) - selected_group_ids)},
        )

    actions: list[dict[str, object]] = []
    buy_pools: dict[str, dict[str, object]] = {}

    selected_tickers: set[str] = set()
    for group in groups:
        legs = _group_legs(session, group.id)
        sell_leg = next((leg for leg in legs if leg.side == "SELL"), None)
        buy_leg = next((leg for leg in legs if leg.side == "BUY"), None)
        if sell_leg is None or buy_leg is None:
            raise AppError("invalid_demo_group", "A demo trade group is missing a dependent trade leg", status_code=409)
        lot_rows = _group_lot_rows(session, group.id)
        member_ids = {row.broker_lot_id for row in lot_rows}
        requested_ids = (
            set(selected_lots_by_group.get(group.id, member_ids)) if group.id in selected_group_ids else set()
        )
        if group.id in selected_group_ids and not requested_ids:
            raise AppError(
                "empty_selected_group",
                "A selected trade group must retain at least one sell lot",
                status_code=422,
                details={"group_id": group.id},
            )
        if requested_ids - member_ids:
            raise AppError(
                "invalid_lot_selection",
                "Selection contains a sell lot that was not attributed to this group",
                status_code=422,
                details={"group_id": group.id, "unknown_broker_lot_ids": sorted(requested_ids - member_ids)},
            )
        if group.rejected and group.id in selected_group_ids:
            raise AppError("rejected_group_selection", "A rejected group cannot be selected", status_code=422)

        source_security = session.get(Security, sell_leg.security_id)
        target_security = session.get(Security, buy_leg.security_id)
        if source_security is None or target_security is None:
            raise AppError("stale_run_security", "A saved recommendation security is unavailable", status_code=409)
        source_price = sell_leg.estimated_unit_price_usd
        selected_rows = [row for row in lot_rows if row.broker_lot_id in requested_ids]
        proceeds = Decimal(0)
        shares_sold = Decimal(0)
        for row in selected_rows:
            proceeds = exact_sum((proceeds, exact_product(source_price, row.shares)))
            shares_sold = exact_sum((shares_sold, row.shares))
        selected = group.id in selected_group_ids
        group.selected = selected
        for row in lot_rows:
            row.selected = selected and row.broker_lot_id in requested_ids
        if selected:
            selected_tickers.add(source_security.ticker)

            pool = buy_pools.setdefault(
                buy_leg.id,
                {"leg": buy_leg, "proceeds": Decimal(0), "sell_leg_ids": [], "group_ids": []},
            )
            pool["proceeds"] = exact_sum((pool["proceeds"], proceeds))  # type: ignore[arg-type]
            pool["sell_leg_ids"].append(sell_leg.id)  # type: ignore[union-attr]
            pool["group_ids"].append(group.id)  # type: ignore[union-attr]

        sell_leg.shares = shares_sold if selected else Decimal(0)
        sell_leg.net_st_realized_usd = Decimal(0)
        sell_leg.net_lt_realized_usd = Decimal(0)
        actions.append(
            {
                "group": group,
                "sell_leg": sell_leg,
                "buy_leg": buy_leg,
                "source_ticker": source_security.ticker,
                "source_asset_type": source_security.asset_type,
                "target_ticker": target_security.ticker,
                "target_asset_type": target_security.asset_type,
                "source_sleeve_key": sell_leg.details.get("sleeve_key"),
                "source_sub_sleeve_key": sell_leg.details.get("sub_sleeve_key"),
                "target_sleeve_key": buy_leg.details.get("sleeve_key"),
                "target_sub_sleeve_key": buy_leg.details.get("sub_sleeve_key"),
                "shares_sold": shares_sold if selected else Decimal(0),
                "proceeds": proceeds if selected else Decimal(0),
                "buy_shares": Decimal(0),
                "buy_cost": Decimal(0),
                "apply_buy": False,
                "realized_st": Decimal(0),
                "realized_lt": Decimal(0),
                "selected": selected,
                "selected_rows": selected_rows if selected else [],
            }
        )

    all_buy_legs = session.scalars(
        select(RecommendationLeg)
        .join(RecommendationGroupLeg, RecommendationGroupLeg.leg_id == RecommendationLeg.id)
        .join(RecommendationGroup, RecommendationGroupLeg.group_id == RecommendationGroup.id)
        .where(RecommendationGroup.run_id == run.id, RecommendationLeg.side == "BUY")
        .distinct()
    ).all()
    minimum = _decimal(run.batch_settings.get("min_buy_order_notional_usd", "0"))

    for buy_leg in all_buy_legs:
        pool = buy_pools.get(buy_leg.id)
        if pool is None:
            buy_leg.shares = Decimal(0)
            details = dict(buy_leg.details)
            details["depends_on_leg_ids"] = []
            buy_leg.details = details
            continue
        proceeds = _decimal(pool["proceeds"])
        buy_shares = whole_share_floor(proceeds, buy_leg.estimated_unit_price_usd)
        buy_cost = exact_product(buy_shares, buy_leg.estimated_unit_price_usd)
        group_ids = pool["group_ids"]
        if buy_shares <= 0:
            raise AppError(
                "selected_basket_infeasible",
                "Selected sell lots cannot fund at least one whole replacement ETF share",
                status_code=422,
                details={"group_ids": group_ids},
            )
        if buy_cost < minimum:
            raise AppError(
                "selected_basket_infeasible",
                "The pooled replacement BUY is below the active minimum buy notional",
                status_code=422,
                details={"group_ids": group_ids, "minimum_buy_order_notional_usd": str(minimum)},
            )
        buy_leg.shares = buy_shares
        details = dict(buy_leg.details)
        details.pop("depends_on_leg_id", None)
        details["depends_on_leg_ids"] = list(dict.fromkeys(str(item) for item in pool["sell_leg_ids"]))
        buy_leg.details = details

        first_group = group_ids[0]
        for action in actions:
            if action["selected"] and action["buy_leg"].id == buy_leg.id:
                action["buy_shares"] = buy_shares
                action["buy_cost"] = buy_cost
                action["apply_buy"] = action["group"].id == first_group

    settings = inputs.policy.settings
    batch = run.batch_settings
    max_tickers = int(batch["max_sell_tickers_per_batch"])
    max_lots = int(batch["max_sell_lots_per_batch"])
    max_orders = int(batch["max_total_orders_per_batch"])
    max_turnover = _decimal(settings.get("max_batch_turnover_pct", Decimal(0)))

    consolidated_legs: list[ConsolidatedLeg] = []
    for action in actions:
        if not action["selected"]:
            continue
        sell_leg = action["sell_leg"]
        selected_rows = action["selected_rows"]
        assert isinstance(sell_leg, RecommendationLeg)
        assert isinstance(selected_rows, list)
        consolidated_legs.append(
            ConsolidatedLeg(
                leg_id=sell_leg.id,
                side="SELL",
                ticker=str(action["source_ticker"]),
                shares=_decimal(action["shares_sold"]),
                estimated_unit_price_usd=sell_leg.estimated_unit_price_usd,
                selected_lots=tuple(LotAllocation(row.broker_lot_id, row.shares) for row in selected_rows),
                sequence=sell_leg.sequence,
                group_ids=(str(action["group"].id),),
            )
        )
    for buy_leg in all_buy_legs:
        pool = buy_pools.get(buy_leg.id)
        if pool is None or buy_leg.shares <= 0:
            continue
        buy_security = session.get(Security, buy_leg.security_id)
        if buy_security is None:
            raise AppError("stale_run_security", "A saved replacement security is unavailable", status_code=409)
        consolidated_legs.append(
            ConsolidatedLeg(
                leg_id=buy_leg.id,
                side="BUY",
                ticker=buy_security.ticker,
                shares=buy_leg.shares,
                estimated_unit_price_usd=buy_leg.estimated_unit_price_usd,
                depends_on_leg_ids=tuple(dict.fromkeys(str(item) for item in pool["sell_leg_ids"])),
                sequence=buy_leg.sequence,
                group_ids=tuple(dict.fromkeys(str(item) for item in pool["group_ids"])),
            )
        )
    try:
        evaluation = evaluate_portfolio(inputs, consolidated_legs)
    except BasketValidationError as exc:
        raise AppError(
            "selected_basket_infeasible",
            exc.message,
            status_code=422,
            details={"reason": exc.code},
        ) from exc

    lot_effects = {effect.broker_lot_id: effect for effect in evaluation.lot_effects}
    total_st = evaluation.realized_st_usd
    total_lt = evaluation.realized_lt_usd
    for action in actions:
        if not action["selected"]:
            continue
        sell_leg = action["sell_leg"]
        selected_rows = action["selected_rows"]
        effects_for_group = [lot_effects[row.broker_lot_id] for row in selected_rows]
        realized_st = exact_sum(effect.realized_pl_usd for effect in effects_for_group if effect.term == "ST")
        realized_lt = exact_sum(effect.realized_pl_usd for effect in effects_for_group if effect.term == "LT")
        action["realized_st"] = realized_st
        action["realized_lt"] = realized_lt
        sell_leg.net_st_realized_usd = realized_st
        sell_leg.net_lt_realized_usd = realized_lt
        for row in selected_rows:
            effect = lot_effects[row.broker_lot_id]
            row.st_lt_term = effect.term
            row.realized_pl_usd = effect.realized_pl_usd

    selected_lot_count = evaluation.selected_lots_count
    cash = inputs.account.cash_usd
    cash_after = evaluation.proposed.cash_usd
    actual_orders = len(consolidated_legs)
    turnover_limit = exact_percent_product(evaluation.current.portfolio_total_usd, max_turnover)
    if len(selected_tickers) > max_tickers or selected_lot_count > max_lots or actual_orders > max_orders:
        raise AppError(
            "selected_basket_infeasible",
            "Selected basket exceeds an active small-batch order limit",
            status_code=422,
            details={"sell_tickers": len(selected_tickers), "sell_lots": selected_lot_count, "orders": actual_orders},
        )
    if evaluation.sell_proceeds_usd > turnover_limit:
        raise AppError(
            "selected_basket_infeasible",
            "Selected basket exceeds the configured demo turnover limit",
            status_code=422,
            details={"sell_proceeds_usd": str(evaluation.sell_proceeds_usd), "turnover_limit_usd": str(turnover_limit)},
        )

    effects = present_portfolio_evaluation(
        evaluation, transition_label="DEMO only; values include the full account and cash"
    )

    for action in actions:
        group = action["group"]
        group.impact = {
            "demo": True,
            "wash_status": "not_validated_demo",
            "selected_sell_lots_count": sum(row.selected for row in _group_lot_rows(session, group.id)),
            "sell_proceeds_usd": str(action["proceeds"]),
            "realized_st_usd": str(action["realized_st"]),
            "realized_lt_usd": str(action["realized_lt"]),
            "replacement_buy_shares": str(action["buy_shares"]),
            "replacement_buy_cost_usd": str(action["buy_cost"]),
            "cash_after_usd": str(cash_after),
            "portfolio_effects": effects,
            "risk_tracking_score": None,
        }
    tax_status = (
        "tax_profile_incomplete"
        if settings.get("short_term_tax_rate") is None or settings.get("long_term_tax_rate") is None
        else "optimizer_unavailable"
    )
    warnings = [DEMO_WARNING, DEMO_WASH_WARNING, DEMO_RISK_WARNING]
    if tax_status == "tax_profile_incomplete":
        warnings.append(tax_status)
    run.warnings = warnings
    run.metrics = {
        "estimated_realized_st_usd": str(total_st),
        "estimated_realized_lt_usd": str(total_lt),
        "estimated_tax_benefit_usd": None,
        "estimated_tax_benefit_status": tax_status,
        "lots_sold_count": selected_lot_count,
        "positions_exited_count": sum(effect.position_exited for effect in evaluation.position_effects),
        "orders_count": actual_orders,
        "cash_before_usd": str(cash),
        "cash_after_usd": str(cash_after),
        "portfolio_effects": effects,
        "no_trade_reason": "No demo candidates met the configured batch and funding limits" if not actions or not selected_group_ids else None,
        "constraints_satisfied": None,
    }



def apply_selection(
    session: Session,
    run_id: str,
    request: OptimizerSelectionInput,
    *,
    correlation_id: str,
) -> OptimizerRun:
    run = session.get(OptimizerRun, run_id)
    if run is None:
        raise AppError("run_not_found", "Optimizer run was not found", status_code=404)
    _check_run_current(session, run)
    selected = set(request.selected_group_ids)
    _recalculate_selection(session, run, selected, request.selected_sell_lots)
    _add_activity(
        session,
        correlation_id,
        "recommendation_selection",
        {"run_id": run.id, "selected_group_ids": sorted(selected)},
    )
    return run



def _lot_intent_error(exc: AppError) -> AppError:
    details = dict(exc.details) if isinstance(exc.details, dict) else {"reason": exc.details}
    details["basket_unchanged"] = True
    return AppError(exc.code, exc.message, status_code=exc.status_code, details=details)


def apply_lot_review_intent(
    session: Session,
    run_id: str,
    request: OptimizerLotReviewIntentInput,
    *,
    correlation_id: str,
) -> OptimizerRun:
    """Replace the confirmed DEMO basket from exact, generation-bound broker-lot intent."""
    run = session.get(OptimizerRun, run_id)
    if run is None:
        raise AppError("run_not_found", "Optimizer run was not found", status_code=404)
    if request.source_generation != run.source_generation:
        raise AppError(
            "stale_lot_review_intent",
            "The requested lots belong to a different source generation; refresh the lot query and review again",
            status_code=409,
            details={
                "requested_source_generation": request.source_generation,
                "run_source_generation": run.source_generation,
                "basket_unchanged": True,
            },
        )
    if run.solver_version != "DEMO":
        raise AppError(
            "lot_review_intent_unsupported",
            "Lot-review intent is supported only for saved deterministic DEMO recommendations",
            status_code=503,
            details={"solver_version": run.solver_version, "basket_unchanged": True},
        )
    try:
        _check_run_current(session, run)
    except AppError as exc:
        raise _lot_intent_error(exc) from exc

    requested_ids = request.broker_lot_ids
    current_lots = {}
    if requested_ids:
        current_lots = {
            lot.broker_lot_id: lot
            for lot in session.scalars(
                select(CurrentTaxLot).where(
                    CurrentTaxLot.account_id == 1,
                    CurrentTaxLot.broker_lot_id.in_(requested_ids),
                )
            ).all()
        }
    candidate_groups_by_lot: dict[str, set[str]] = {}
    candidate_rows = session.execute(
        select(RecommendationSelectedLot.broker_lot_id, RecommendationGroup.id)
        .join(RecommendationLeg, RecommendationLeg.id == RecommendationSelectedLot.leg_id)
        .join(RecommendationGroupLeg, RecommendationGroupLeg.leg_id == RecommendationLeg.id)
        .join(RecommendationGroup, RecommendationGroup.id == RecommendationGroupLeg.group_id)
        .where(RecommendationGroup.run_id == run.id, RecommendationLeg.side == "SELL")
    ).all()
    for broker_lot_id, group_id in candidate_rows:
        candidate_groups_by_lot.setdefault(broker_lot_id, set()).add(group_id)

    rejected_lots: list[dict[str, str]] = []
    selected_lots_by_group: dict[str, list[str]] = {}
    for broker_lot_id in requested_ids:
        if broker_lot_id not in current_lots:
            rejected_lots.append({"broker_lot_id": broker_lot_id, "reason": "missing_current_lot"})
            continue
        group_ids = candidate_groups_by_lot.get(broker_lot_id, set())
        if not group_ids:
            rejected_lots.append({"broker_lot_id": broker_lot_id, "reason": "outside_saved_demo_candidates"})
            continue
        if len(group_ids) != 1:
            rejected_lots.append({"broker_lot_id": broker_lot_id, "reason": "ambiguous_saved_demo_candidate"})
            continue
        group_id = next(iter(group_ids))
        selected_lots_by_group.setdefault(group_id, []).append(broker_lot_id)
    if rejected_lots:
        raise AppError(
            "lot_review_intent_rejected",
            "Every requested lot must exist and belong to exactly one saved DEMO candidate; no basket changes were applied",
            status_code=422,
            details={"rejected_lots": rejected_lots, "basket_unchanged": True},
        )

    selected_group_ids = set(selected_lots_by_group)
    try:
        _recalculate_selection(session, run, selected_group_ids, selected_lots_by_group)
    except AppError as exc:
        raise _lot_intent_error(exc) from exc
    _add_activity(
        session,
        correlation_id,
        "recommendation_lot_review_intent",
        {
            "run_id": run.id,
            "source_generation": request.source_generation,
            "broker_lot_ids": requested_ids,
            "selected_group_ids": sorted(selected_group_ids),
        },
    )
    return run

def annotate_group(
    session: Session,
    run_id: str,
    group_id: str,
    payload: object,
    *,
    correlation_id: str,
) -> OptimizerRun:
    from app.schemas import RecommendationAnnotationInput

    run = session.get(OptimizerRun, run_id)
    if run is None:
        raise AppError("run_not_found", "Optimizer run was not found", status_code=404)
    _check_run_current(session, run)
    group = session.scalar(
        select(RecommendationGroup).where(
            RecommendationGroup.id == group_id,
            RecommendationGroup.run_id == run_id,
        )
    )
    if group is None:
        raise AppError("recommendation_group_not_found", "Recommendation group was not found", status_code=404)
    if not isinstance(payload, RecommendationAnnotationInput):
        raise AppError("invalid_annotation", "Recommendation annotation is invalid", status_code=422)
    fields_set = payload.model_fields_set
    if "note" in fields_set:
        group.note = payload.note
    if payload.rejected is True:
        group.rejected = True
        group.selected = False
        if "rejection_reason" in fields_set:
            group.rejection_reason = payload.rejection_reason
        for row in _group_lot_rows(session, group.id):
            row.selected = False
    elif payload.rejected is False:
        group.rejected = False
        group.rejection_reason = None
    if payload.rejected:
        active_groups = [
            row
            for row in session.scalars(
                select(RecommendationGroup).where(RecommendationGroup.run_id == run.id)
            ).all()
            if row.selected and not row.rejected
        ]
        lot_map = {
            row.id: [lot.broker_lot_id for lot in _group_lot_rows(session, row.id) if lot.selected]
            for row in active_groups
        }
        _recalculate_selection(session, run, {row.id for row in active_groups}, lot_map)
    _add_activity(
        session,
        correlation_id,
        "recommendation_annotation",
        {"run_id": run.id, "group_id": group.id, "rejected": group.rejected},
    )
    return run


def _add_activity(session: Session, correlation_id: str, event_type: str, details: dict[str, object]) -> None:
    session.add(
        ActivityEvent(
            id=str(uuid4()),
            created_at=datetime.now(UTC),
            event_type=event_type,
            status="complete",
            correlation_id=correlation_id,
            details=details,
        )
    )


def _presentation_portfolio_effects(value: object) -> object:
    """Mark progress unavailable for persisted effects predating explicit destinations."""
    if not isinstance(value, dict):
        return value
    transition = value.get("us_transition")
    if not isinstance(transition, dict) or "transition_destination_sleeve_key" in transition:
        return value

    presented_transition = dict(transition)
    presented_transition["transition_destination_sleeve_key"] = None
    for key in ("current", "proposed_basket"):
        snapshot = transition.get(key)
        if isinstance(snapshot, dict):
            presented_snapshot = dict(snapshot)
            presented_snapshot["etf_progress_pct"] = None
            presented_transition[key] = presented_snapshot
    presented = dict(value)
    presented["us_transition"] = presented_transition
    return presented


def _presentation_group_impact(value: object) -> object:
    if not isinstance(value, dict):
        return value
    effects = value.get("portfolio_effects")
    presented_effects = _presentation_portfolio_effects(effects)
    if presented_effects is effects:
        return value
    presented = dict(value)
    presented["portfolio_effects"] = presented_effects
    return presented

_RUN_DISPLAY_POLICY_SETTINGS = (
    "short_term_tax_rate",
    "long_term_tax_rate",
    "st_loss_carryforward_usd",
    "lt_loss_carryforward_usd",
    "ytd_realized_st_usd",
    "ytd_realized_lt_usd",
    "ytd_source",
    "ytd_as_of",
    "target_retained_net_loss_usd",
    "ordinary_income_deduction_limit_usd",
    "carryforward_loss_discount_factor",
    "gain_budget_usd",
    "max_incremental_tax_cost_usd",
    "st_gain_limit_usd",
    "lt_gain_limit_usd",
    "budget_period",
    "max_sell_tickers_per_batch",
    "max_sell_lots_per_batch",
    "max_total_orders_per_batch",
    "max_batch_turnover_pct",
    "min_buy_order_notional_usd",
    "cash_reserve_usd",
    "prefer_etf_buys",
    "allow_gain_sales",
    "permit_etf_harvest",
    "permit_muni_exit",
)

_RUN_DISPLAY_SLEEVE_FIELDS = (
    "sleeve_key",
    "display_name",
    "sort_order",
    "parent_sleeve_key",
    "target_pct",
    "drift_band_pp",
    "enabled",
    "is_direct_index_container",
    "is_direct_index_sleeve",
    "is_transition_destination",
    "is_cash_sleeve",
)
_RUN_DISPLAY_ALLOWED_FIELDS = (
    "ticker",
    "sleeve_key",
    "sub_sleeve_key",
    "replacement_set_id",
    "priority",
    "enabled",
    "exposure_suitability",
)
_RUN_DISPLAY_OVERRIDE_FIELDS = ("ticker", "sleeve_key", "sub_sleeve_key")


def _run_context_datetime(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    return parsed.isoformat().replace("+00:00", "Z")


def _frozen_run_display_context(run: OptimizerRun) -> dict[str, object] | None:
    policy = run.frozen_input_bundle.get("policy")
    if not isinstance(policy, dict) or policy.get("id") != run.policy_revision_id:
        return None
    settings = policy.get("settings")
    sleeves = policy.get("sleeves")
    allowed_securities = policy.get("allowed_securities")
    overrides = policy.get("overrides")
    revision_number = policy.get("revision_number")
    if (
        not isinstance(settings, dict)
        or not isinstance(sleeves, list)
        or not isinstance(allowed_securities, list)
        or not isinstance(overrides, list)
        or not isinstance(revision_number, int)
        or isinstance(revision_number, bool)
    ):
        return None
    if any(not isinstance(row, dict) or not set(_RUN_DISPLAY_SLEEVE_FIELDS) <= row.keys() for row in sleeves):
        return None
    if any(not isinstance(row, dict) or not set(_RUN_DISPLAY_ALLOWED_FIELDS) <= row.keys() for row in allowed_securities):
        return None
    if any(not isinstance(row, dict) or not set(_RUN_DISPLAY_OVERRIDE_FIELDS) <= row.keys() for row in overrides):
        return None
    raw_created_at = policy.get("created_at")
    raw_activated_at = policy.get("activated_at")
    if (raw_created_at is not None and not isinstance(raw_created_at, str)) or (
        raw_activated_at is not None and not isinstance(raw_activated_at, str)
    ):
        return None
    try:
        created_at = _run_context_datetime(raw_created_at)
        activated_at = _run_context_datetime(raw_activated_at)
    except (TypeError, ValueError):
        return None
    context = {
        "available": True,
        "source": "frozen_input_bundle",
        "policy_revision_id": run.policy_revision_id,
        "revision_number": revision_number,
        "created_at": created_at,
        "activated_at": activated_at,
        "sleeves": [{key: row[key] for key in _RUN_DISPLAY_SLEEVE_FIELDS} for row in sleeves],
        "settings": settings,
        "allowed_securities": [{key: row[key] for key in _RUN_DISPLAY_ALLOWED_FIELDS} for row in allowed_securities],
        "overrides": [{key: row[key] for key in _RUN_DISPLAY_OVERRIDE_FIELDS} for row in overrides],
        "unavailable_reason": None,
    }
    try:
        FrozenRunDisplayContextResponse.model_validate(context)
    except ValidationError:
        return None
    return context


def _policy_revision_run_display_context(session: Session, run: OptimizerRun) -> dict[str, object] | None:
    revision = session.get(PolicyRevision, run.policy_revision_id)
    if revision is None:
        return None
    sleeves = session.scalars(
        select(PolicySleeve)
        .where(PolicySleeve.policy_revision_id == revision.id)
        .order_by(PolicySleeve.sort_order, PolicySleeve.sleeve_key)
    ).all()
    allowed_securities = session.scalars(
        select(PolicyAllowedSecurity)
        .where(PolicyAllowedSecurity.policy_revision_id == revision.id)
        .order_by(
            PolicyAllowedSecurity.sleeve_key,
            PolicyAllowedSecurity.replacement_set_id,
            PolicyAllowedSecurity.priority,
            PolicyAllowedSecurity.ticker,
        )
    ).all()
    overrides = session.execute(
        select(PolicySecurityOverride, Security.ticker)
        .join(Security, Security.id == PolicySecurityOverride.security_id)
        .where(PolicySecurityOverride.policy_revision_id == revision.id)
        .order_by(Security.ticker)
    ).all()
    settings: dict[str, object] = {}
    for key in _RUN_DISPLAY_POLICY_SETTINGS:
        value = getattr(revision, key)
        settings[key] = value.isoformat() if isinstance(value, date) else str(value) if isinstance(value, Decimal) else value
    return {
        "available": True,
        "source": "policy_revision",
        "policy_revision_id": revision.id,
        "revision_number": revision.revision_number,
        "created_at": _run_context_datetime(revision.created_at),
        "activated_at": _run_context_datetime(revision.activated_at),
        "sleeves": [
            {
                "sleeve_key": row.sleeve_key,
                "display_name": row.display_name,
                "sort_order": row.sort_order,
                "parent_sleeve_key": row.parent_sleeve_key,
                "target_pct": str(row.target_pct),
                "drift_band_pp": str(row.drift_band_pp),
                "enabled": row.enabled,
                "is_direct_index_container": row.is_direct_index_container,
                "is_direct_index_sleeve": row.is_direct_index_sleeve,
                "is_transition_destination": row.is_transition_destination,
                "is_cash_sleeve": row.is_cash_sleeve,
            }
            for row in sleeves
        ],
        "settings": settings,
        "allowed_securities": [
            {
                "ticker": row.ticker,
                "sleeve_key": row.sleeve_key,
                "sub_sleeve_key": row.sub_sleeve_key,
                "replacement_set_id": row.replacement_set_id,
                "priority": row.priority,
                "enabled": row.enabled,
                "exposure_suitability": row.exposure_suitability,
            }
            for row in allowed_securities
        ],
        "overrides": [
            {"ticker": ticker, "sleeve_key": row.sleeve_key, "sub_sleeve_key": row.sub_sleeve_key}
            for row, ticker in overrides
        ],
        "unavailable_reason": None,
    }


def _run_display_context(run: OptimizerRun, session: Session | None) -> dict[str, object]:
    context = _frozen_run_display_context(run)
    if context is None and session is not None:
        context = _policy_revision_run_display_context(session, run)
    if context is not None:
        return context
    return {
        "available": False,
        "source": None,
        "policy_revision_id": run.policy_revision_id,
        "revision_number": None,
        "created_at": None,
        "activated_at": None,
        "sleeves": None,
        "settings": None,
        "allowed_securities": None,
        "overrides": None,
        "unavailable_reason": "Frozen policy display provenance is unavailable",
    }



def run_summary(run: OptimizerRun, *, session: Session | None = None) -> dict[str, object]:
    metrics = run.metrics
    bundle = run.frozen_input_bundle
    policy = bundle.get("policy")
    settings = policy.get("settings", {}) if isinstance(policy, dict) else {}
    display_context = _run_display_context(run, session)
    display_settings = display_context["settings"] if isinstance(display_context.get("settings"), dict) else settings
    tax_status = metrics.get("estimated_tax_benefit_status", "tax_profile_incomplete")
    return {
        "run_id": run.id,
        "status": "demo",
        "mode": "recommendations_only",
        "policy_revision_id": run.policy_revision_id,
        "source_generation": run.source_generation,
        "as_of": run.as_of,
        "proposed_trade_date": run.proposed_trade_date,
        "solver_version": "DEMO",
        "demo": True,
        "actionable": False,
        "input_fingerprint": run.input_fingerprint,
        "source_checksum": bundle.get("source_checksum"),
        "batch_settings": run.batch_settings,
        "estimated_realized_st_usd": metrics.get("estimated_realized_st_usd", "0"),
        "estimated_realized_lt_usd": metrics.get("estimated_realized_lt_usd", "0"),
        "estimated_tax_benefit_usd": None,
        "estimated_tax_benefit_status": tax_status,
        "lots_sold_count": metrics.get("lots_sold_count", 0),
        "positions_exited_count": metrics.get("positions_exited_count", 0),
        "orders_count": metrics.get("orders_count", 0),
        "cash_before_usd": metrics.get("cash_before_usd"),
        "cash_after_usd": metrics.get("cash_after_usd"),
        "portfolio_effects": _presentation_portfolio_effects(metrics.get("portfolio_effects")),
        "constraints_satisfied": None,
        "no_trade_reason": metrics.get("no_trade_reason"),
        "warnings": list(run.warnings),
        "tax_profile_configured": display_settings.get("short_term_tax_rate") is not None
        and display_settings.get("long_term_tax_rate") is not None,
        "frozen_display_context": display_context,
    }


def _leg_dict(
    leg: RecommendationLeg,
    ticker: str | None,
    group_ids: list[str],
    selected_lot_rows: list[RecommendationSelectedLot],
) -> dict[str, object]:
    """Adapt preloaded canonical-leg data to the response without performing I/O."""
    details = dict(leg.details)
    if isinstance(details.get("depends_on_leg_ids"), list):
        dependencies = list(details["depends_on_leg_ids"])
    elif details.get("depends_on_leg_id"):
        dependencies = [details["depends_on_leg_id"]]
    else:
        dependencies = []
    selected_lots = (
        [
            {
                "broker_lot_id": row.broker_lot_id,
                "shares": str(row.shares),
                "acquired_date": row.acquired_date.isoformat(),
                "adjusted_basis_usd": str(row.adjusted_basis_usd),
                "st_lt": row.st_lt_term,
                "realized_pl_usd": str(row.realized_pl_usd),
                "selected": row.selected,
            }
            for row in selected_lot_rows
        ]
        if leg.side == "SELL"
        else []
    )
    return {
        "leg_id": leg.id,
        "side": leg.side,
        "ticker": ticker,
        "shares": str(leg.shares),
        "estimated_unit_price_usd": str(leg.estimated_unit_price_usd),
        "estimated_notional_usd": str(exact_product(leg.shares, leg.estimated_unit_price_usd)),
        "net_st_realized_usd": str(leg.net_st_realized_usd),
        "net_lt_realized_usd": str(leg.net_lt_realized_usd),
        "sequence": leg.sequence,
        "dependencies": dependencies,
        "selected": leg.shares > 0,
        "group_ids": group_ids,
        "selected_lots": selected_lots,
        "details": details,
    }


def _group_dict(group: RecommendationGroup, leg_ids: list[str]) -> dict[str, object]:
    return {
        "group_id": group.id,
        "rank": group.rank,
        "group_type": group.group_type,
        "sleeve_key": group.sleeve_key,
        "rationale": group.rationale,
        "estimated_benefit_usd": None,
        "impact": _presentation_group_impact(group.impact),
        "dependencies": group.dependencies,
        "selected": group.selected,
        "rejected": group.rejected,
        "note": group.note,
        "rejection_reason": group.rejection_reason,
        "leg_ids": leg_ids,
        "warnings": [DEMO_WARNING, DEMO_WASH_WARNING, DEMO_RISK_WARNING],
    }


def run_recommendations(session: Session, run: OptimizerRun) -> dict[str, object]:
    groups = session.scalars(
        select(RecommendationGroup)
        .where(RecommendationGroup.run_id == run.id)
        .order_by(RecommendationGroup.rank)
    ).all()
    if not groups:
        return {**run_summary(run, session=session), "groups": [], "consolidated_legs": []}

    group_ids = [group.id for group in groups]
    group_rank = {group.id: group.rank for group in groups}
    memberships = session.scalars(
        select(RecommendationGroupLeg).where(RecommendationGroupLeg.group_id.in_(group_ids))
    ).all()
    group_leg_ids: dict[str, list[str]] = {group.id: [] for group in groups}
    leg_group_ids: dict[str, list[str]] = {}
    for membership in memberships:
        group_leg_ids[membership.group_id].append(membership.leg_id)
        leg_group_ids.setdefault(membership.leg_id, []).append(membership.group_id)

    legs = (
        session.scalars(
            select(RecommendationLeg)
            .join(RecommendationGroupLeg, RecommendationGroupLeg.leg_id == RecommendationLeg.id)
            .join(RecommendationGroup, RecommendationGroup.id == RecommendationGroupLeg.group_id)
            .where(RecommendationGroup.run_id == run.id)
            .distinct()
        )
        .unique()
        .all()
    )
    legs_by_id = {leg.id: leg for leg in legs}
    for linked_group_ids in leg_group_ids.values():
        linked_group_ids.sort(key=lambda group_id: (group_rank.get(group_id, 0), group_id))
    for linked_leg_ids in group_leg_ids.values():
        linked_leg_ids.sort(key=lambda leg_id: (legs_by_id[leg_id].sequence, leg_id))

    security_ids = sorted({leg.security_id for leg in legs})
    securities = session.scalars(select(Security).where(Security.id.in_(security_ids))).all()
    tickers_by_security_id = {security.id: security.ticker for security in securities}
    sell_leg_ids = [leg.id for leg in legs if leg.side == "SELL"]
    selected_lot_rows = (
        session.scalars(
            select(RecommendationSelectedLot)
            .where(RecommendationSelectedLot.leg_id.in_(sell_leg_ids))
            .order_by(RecommendationSelectedLot.leg_id, RecommendationSelectedLot.broker_lot_id)
        ).all()
        if sell_leg_ids
        else []
    )
    selected_lots_by_leg: dict[str, list[RecommendationSelectedLot]] = {}
    for row in selected_lot_rows:
        selected_lots_by_leg.setdefault(row.leg_id, []).append(row)

    legs.sort(
        key=lambda leg: (
            leg.side == "BUY",
            min((group_rank[group_id] for group_id in leg_group_ids.get(leg.id, [])), default=0),
            leg.sequence,
            leg.id,
        )
    )
    serialized_legs = [
        _leg_dict(
            leg,
            tickers_by_security_id.get(leg.security_id),
            leg_group_ids.get(leg.id, []),
            selected_lots_by_leg.get(leg.id, []),
        )
        for leg in legs
    ]
    return {
        **run_summary(run, session=session),
        "groups": [_group_dict(group, group_leg_ids[group.id]) for group in groups],
        "consolidated_legs": serialized_legs,
    }


def get_run(session: Session, run_id: str) -> OptimizerRun:
    run = session.get(OptimizerRun, run_id)
    if run is None:
        raise AppError("run_not_found", "Optimizer run was not found", status_code=404)
    return run


def export_run(session: Session, run: OptimizerRun, file_format: str) -> tuple[str, str]:
    response = run_recommendations(session, run)
    metadata = {
        key: response[key]
        for key in (
            "run_id",
            "policy_revision_id",
            "source_generation",
            "as_of",
            "proposed_trade_date",
            "solver_version",
            "demo",
            "actionable",
            "input_fingerprint",
            "source_checksum",
            "warnings",
            "frozen_display_context",
        )
    }
    if file_format == "json":
        return "application/json", json.dumps({"metadata": metadata, "run": response}, default=str, sort_keys=True)
    if file_format != "csv":
        raise AppError("invalid_export_format", "Export format must be json or csv", status_code=422)
    output = io.StringIO(newline="")
    fields = [
        "run_id",
        "record_type",
        "policy_revision_id",
        "source_generation",
        "as_of",
        "proposed_trade_date",
        "solver_version",
        "demo",
        "input_fingerprint",
        "source_checksum",
        "orders_count",
        "lots_sold_count",
        "positions_exited_count",
        "estimated_realized_st_usd",
        "estimated_realized_lt_usd",
        "cash_before_usd",
        "cash_after_usd",
        "portfolio_effects_json",
        "frozen_display_context_json",
        "actionable",
        "group_id",
        "group_ids",
        "rank",
        "selected",
        "rejected",
        "note",
        "leg_id",
        "side",
        "ticker",
        "shares",
        "estimated_notional_usd",
        "dependencies",
        "estimated_unit_price_usd",
        "broker_lot_id",
        "lot_shares",
        "lot_selected",
        "acquired_date",
        "adjusted_basis_usd",
        "st_lt",
        "realized_pl_usd",
        "net_st_realized_usd",
        "net_lt_realized_usd",
        "estimated_tax_benefit_usd",
        "estimated_tax_benefit_status",
        "warnings",
    ]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    writer.writerow(
        {
            **{key: metadata.get(key) for key in fields if key in metadata},
            "record_type": "metadata",
            "warnings": ";".join(metadata["warnings"]),
            "estimated_tax_benefit_status": response["estimated_tax_benefit_status"],
            "orders_count": response["orders_count"],
            "lots_sold_count": response["lots_sold_count"],
            "positions_exited_count": response["positions_exited_count"],
            "estimated_realized_st_usd": response["estimated_realized_st_usd"],
            "estimated_realized_lt_usd": response["estimated_realized_lt_usd"],
            "estimated_tax_benefit_usd": response["estimated_tax_benefit_usd"],
            "cash_before_usd": response["cash_before_usd"],
            "cash_after_usd": response["cash_after_usd"],
            "frozen_display_context_json": json.dumps(
                response["frozen_display_context"], sort_keys=True, separators=(",", ":"), default=str
            ),
            "portfolio_effects_json": json.dumps(
                response["portfolio_effects"], sort_keys=True, separators=(",", ":"), default=str
            ),
        }
    )
    groups_by_id = {group["group_id"]: group for group in response["groups"]}
    for leg in response["consolidated_legs"]:
        linked_groups = [groups_by_id[group_id] for group_id in leg["group_ids"]]
        lot_rows = leg["selected_lots"] if leg["side"] == "SELL" else [None]
        for lot in lot_rows:
            writer.writerow(
                {
                    **{key: metadata.get(key) for key in fields if key in metadata},
                    "estimated_tax_benefit_usd": "",
                    "estimated_tax_benefit_status": response["estimated_tax_benefit_status"],
                    "group_id": ";".join(leg["group_ids"]),
                    "group_ids": json.dumps(leg["group_ids"], separators=(",", ":")),
                    "rank": ";".join(str(group["rank"]) for group in linked_groups),
                    "selected": leg["selected"],
                    "rejected": any(group["rejected"] for group in linked_groups) if leg["side"] == "SELL" else "",
                    "note": ";".join(group["note"] or "" for group in linked_groups),
                    "leg_id": leg["leg_id"],
                    "side": leg["side"],
                    "ticker": leg["ticker"],
                    "shares": leg["shares"],
                    "estimated_notional_usd": leg["estimated_notional_usd"],
                    "dependencies": json.dumps(leg["dependencies"], separators=(",", ":")),
                    "estimated_unit_price_usd": leg["estimated_unit_price_usd"],
                    "broker_lot_id": lot["broker_lot_id"] if lot else "",
                    "lot_shares": lot["shares"] if lot else "",
                    "lot_selected": lot["selected"] if lot else "",
                    "acquired_date": lot["acquired_date"] if lot else "",
                    "adjusted_basis_usd": lot["adjusted_basis_usd"] if lot else "",
                    "st_lt": lot["st_lt"] if lot else "",
                    "realized_pl_usd": lot["realized_pl_usd"] if lot else "",
                    "net_st_realized_usd": leg["net_st_realized_usd"],
                    "net_lt_realized_usd": leg["net_lt_realized_usd"],
                    "warnings": ";".join(dict.fromkeys(warning for group in linked_groups for warning in group["warnings"])),
                }
            )
    return "text/csv; charset=utf-8", output.getvalue()


def wash_sales(session: Session) -> dict[str, object]:
    account = session.get(Account, 1)
    if account is None:
        raise AppError("demo_account_required", "A synced single-account demo is required", status_code=409)
    transactions = session.scalars(
        select(BrokerTransaction)
        .where(BrokerTransaction.account_id == account.id)
        .order_by(BrokerTransaction.trade_date.desc(), BrokerTransaction.transaction_time.desc())
    ).all()
    history: list[dict[str, object]] = []
    securities = {row.id: row for row in session.scalars(select(Security)).all()}
    acquisitions = []
    for transaction in transactions:
        security = securities.get(transaction.security_id)
        row = {
            "broker_transaction_key": transaction.broker_transaction_key,
            "ticker": security.ticker if security else None,
            "transaction_kind": transaction.transaction_kind,
            "trade_date": transaction.trade_date.isoformat(),
            "transaction_time": _datetime_iso(transaction.transaction_time),
            "shares": str(transaction.shares),
            "source": transaction.source,
            "is_acquisition": transaction.is_acquisition,
        }
        history.append(row)
        if transaction.is_acquisition and transaction.transaction_kind == "BUY":
            acquisitions.append({**row, "lookback_window_end_date": (transaction.trade_date + timedelta(days=30)).isoformat()})

    proposed: list[dict[str, object]] = []
    state = session.get(SyncState, 1)
    active = session.scalar(select(PolicyRevision).where(PolicyRevision.status == "ACTIVE"))
    if state is not None and state.complete and active is not None:
        latest_run = None
        run_events = session.scalars(
            select(ActivityEvent)
            .where(ActivityEvent.event_type == "optimizer_run")
            .order_by(ActivityEvent.created_at.desc())
        ).all()
        for event in run_events:
            candidate = session.get(OptimizerRun, event.details.get("run_id"))
            if (
                candidate is not None
                and candidate.source_generation == state.current_generation
                and candidate.policy_revision_id == active.id
            ):
                latest_run = candidate
                break
        if latest_run is not None:
            groups = session.scalars(
                select(RecommendationGroup).where(
                    RecommendationGroup.run_id == latest_run.id,
                    RecommendationGroup.selected.is_(True),
                )
            ).all()
            for group in groups:
                sell_legs = session.scalars(
                    select(RecommendationLeg).where(
                        RecommendationLeg.group_id == group.id,
                        RecommendationLeg.side == "SELL",
                    )
                ).all()
                for leg in sell_legs:
                    if exact_sum((leg.net_st_realized_usd, leg.net_lt_realized_usd)) >= 0:
                        continue
                    security = session.get(Security, leg.security_id)
                    if security is None:
                        continue
                    loss_date = latest_run.proposed_trade_date
                    if loss_date is None:
                        continue
                    proposed.append(
                        {
                            "run_id": latest_run.id,
                            "ticker": security.ticker,
                            "trigger": "proposed_demo_loss_sale",
                            "loss_sale_date": loss_date.isoformat(),
                            "source": "DEMO recommendation; not an executed trade",
                            "next_eligible_purchase_date": (loss_date + timedelta(days=31)).isoformat(),
                            "validation": "not_live_validated",
                        }
                    )
    return {
        "demo": True,
        "source": account.source,
        "history": history,
        "acquisitions": acquisitions,
        "current_restrictions": [],
        "proposed_restrictions": proposed,
        "warnings": [
            "DEMO single-account transaction history only; not E*TRADE-derived live validation",
            "historical realized-loss lot attribution is unavailable, so current restrictions are not inferred",
            "full 30-day basket wash-sale validation is deferred to Phase 2",
        ],
    }
