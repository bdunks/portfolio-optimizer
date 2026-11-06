from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_DOWN, Decimal
from uuid import uuid4

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
    PolicyRevision,
    RecommendationGroup,
    RecommendationGroupLeg,
    RecommendationLeg,
    RecommendationSelectedLot,
    Security,
    SyncState,
)
from app.domain.decimal_math import (
    exact_difference,
    exact_percent_product,
    exact_product,
    exact_sum,
    percentage,
    whole_share_floor,
)
from app.schemas import OptimizerRunInput, OptimizerSelectionInput
from app.services.errors import AppError
from app.services.policy import (
    accumulate_sleeve_value,
    policy_to_dict,
    resolve_holding,
    resolve_policy_assignment,
    sleeve_assignment_path,
    validate_policy_revision,
)

DEMO_WARNING = "real_optimizer_unavailable"
DEMO_WASH_WARNING = "wash_sale_validation_deferred_demo"
DEMO_RISK_WARNING = "risk_tracking_validation_not_run_demo"


def _decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _datetime_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _json_safe(value: object) -> object:
    if isinstance(value, datetime):
        return _datetime_iso(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _fingerprint(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _term(acquired: date, as_of: date) -> str:
    try:
        anniversary = acquired.replace(year=acquired.year + 1)
    except ValueError:
        anniversary = acquired.replace(year=acquired.year + 1, day=28)
    return "LT" if as_of > anniversary else "ST"


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
) -> dict[str, object]:
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

    if account.cash_usd < 0 or account.settled_buying_power_usd < 0:
        raise AppError("invalid_current_balance", "Current account balances cannot be negative", status_code=422)
    securities = {row.id: row for row in session.scalars(select(Security)).all()}
    quotes = {row.security_id: row for row in session.scalars(select(CurrentQuote)).all()}
    positions = session.scalars(
        select(CurrentPosition).where(CurrentPosition.account_id == account.id).order_by(CurrentPosition.security_id)
    ).all()
    lots = session.scalars(
        select(CurrentTaxLot).where(CurrentTaxLot.account_id == account.id).order_by(CurrentTaxLot.broker_lot_id)
    ).all()
    transactions = session.scalars(
        select(BrokerTransaction).where(BrokerTransaction.account_id == account.id).order_by(BrokerTransaction.trade_date)
    ).all()

    position_rows: list[dict[str, object]] = []
    for position in positions:
        security = securities.get(position.security_id)
        quote = quotes.get(position.security_id)
        if security is None or position.sync_generation != sync_state.current_generation:
            raise AppError("current_state_inconsistent", "Current position data is inconsistent", status_code=409)
        if position.shares <= 0 or position.market_value_usd < 0:
            raise AppError("invalid_position", "Current positions require positive shares and nonnegative value", status_code=422)
        if quote is None or quote.sync_generation != sync_state.current_generation or quote.last_usd is None:
            raise AppError(
                "quote_unavailable",
                "Every held position requires a quote from the current complete sync",
                status_code=422,
                details={"ticker": security.ticker},
            )
        if quote.quality.lower() != "good" or quote.last_usd <= 0:
            raise AppError(
                "quote_unavailable",
                "A current position has a stale or unusable quote",
                status_code=422,
                details={"ticker": security.ticker, "quality": quote.quality},
            )
        resolved = resolve_holding(session, policy.id, security)
        if resolved is None:
            raise AppError(
                "unassigned_holding",
                "Every current holding must resolve to an active policy sleeve",
                status_code=422,
                details={"ticker": security.ticker},
            )
        position_rows.append(
            {
                "ticker": security.ticker,
                "asset_type": security.asset_type,
                "is_completion_etf": security.is_completion_etf,
                "shares": str(position.shares),
                "sync_generation": position.sync_generation,
                "as_of": _datetime_iso(position.as_of),
                "market_value_usd": str(position.market_value_usd),
                "sleeve_key": resolved[0],
                "sub_sleeve_key": resolved[1],
            }
        )

    lot_shares_by_ticker: dict[str, list[Decimal]] = {}
    lot_rows: list[dict[str, object]] = []
    for lot in lots:
        security = securities.get(lot.security_id)
        if security is None or lot.sync_generation != sync_state.current_generation:
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
        lot_shares_by_ticker.setdefault(security.ticker, []).append(lot.shares)
        lot_rows.append(
            {
                "ticker": security.ticker,
                "broker_lot_id": lot.broker_lot_id,
                "acquired_date": lot.acquired_date.isoformat(),
                "shares": str(lot.shares),
                "available_shares": str(lot.available_shares),
                "adjusted_unit_basis_usd": str(lot.adjusted_unit_basis_usd),
                "broker_wash_adjustment_usd": str(lot.broker_wash_adjustment_usd)
                if lot.broker_wash_adjustment_usd is not None
                else None,
                "source": lot.source,
                "as_of": _datetime_iso(lot.as_of),
                "fractional_cleanup_unsupported": lot.fractional_cleanup_unsupported,
                "quality_flags": list(lot.quality_flags),
            }
        )
    position_shares_by_ticker = {row["ticker"]: _decimal(row["shares"]) for row in position_rows}
    if set(lot_shares_by_ticker) != set(position_shares_by_ticker) or any(
        exact_sum(lot_shares_by_ticker[ticker]) != shares
        for ticker, shares in position_shares_by_ticker.items()
    ):
        raise AppError(
            "incomplete_lots",
            "Current tax lots do not exactly cover all positions; no demo recommendations were created",
            status_code=422,
        )

    quote_rows: dict[str, dict[str, object]] = {}
    for security_id, quote in quotes.items():
        security = securities.get(security_id)
        if security is None:
            continue
        quote_rows[security.ticker] = {
            "bid_usd": str(quote.bid_usd) if quote.bid_usd is not None else None,
            "ask_usd": str(quote.ask_usd) if quote.ask_usd is not None else None,
            "last_usd": str(quote.last_usd) if quote.last_usd is not None else None,
            "source": quote.source,
            "as_of": _datetime_iso(quote.as_of),
            "quality": quote.quality,
            "sync_generation": quote.sync_generation,
        }

    transaction_rows: list[dict[str, object]] = []
    for transaction in transactions:
        security = securities.get(transaction.security_id)
        if security is None:
            continue
        transaction_rows.append(
            {
                "broker_transaction_key": transaction.broker_transaction_key,
                "ticker": security.ticker,
                "transaction_kind": transaction.transaction_kind,
                "transaction_time": _datetime_iso(transaction.transaction_time),
                "trade_date": transaction.trade_date.isoformat(),
                "shares": str(transaction.shares),
                "amount_usd": str(transaction.amount_usd),
                "is_acquisition": transaction.is_acquisition,
                "broker_lot_id": transaction.broker_lot_id,
                "source": transaction.source,
            }
        )

    account_bundle = {
        "local_account_id": account.id,
        "account_key_fingerprint": _fingerprint(account.broker_account_id_key),
        "display_name": account.display_name,
        "account_type": account.account_type,
        "tax_treatment": account.tax_treatment,
        "source": account.source,
        "as_of": _datetime_iso(account.as_of),
        "cash_usd": str(account.cash_usd),
        "settled_buying_power_usd": str(account.settled_buying_power_usd),
    }
    policy_bundle = _json_safe(policy_to_dict(session, policy))
    source_payload: dict[str, object] = {
        "schema": "demo-run-input-v1",
        "account": account_bundle,
        "source_generation": sync_state.current_generation,
        "positions": position_rows,
        "lots": lot_rows,
        "quotes": quote_rows,
        "policy": policy_bundle,
        "transactions": transaction_rows,
    }
    source_checksum = _fingerprint(source_payload)
    source_payload["source_checksum"] = source_checksum
    return source_payload


def _candidate_groups(bundle: dict[str, object], batch: dict[str, object]) -> list[dict[str, object]]:
    policy = bundle["policy"]
    assert isinstance(policy, dict)
    settings = policy["settings"]
    assert isinstance(settings, dict)
    quotes = bundle["quotes"]
    positions = bundle["positions"]
    lots = bundle["lots"]
    assert isinstance(quotes, dict)
    assert isinstance(positions, list)
    assert isinstance(lots, list)
    policy_rows = policy["allowed_securities"]
    assert isinstance(policy_rows, list)
    sleeve_rows = policy["sleeves"]
    assert isinstance(sleeve_rows, list)
    sleeves_by_key = {str(row["sleeve_key"]): row for row in sleeve_rows}
    portfolio_total = exact_sum(
        [_decimal(row["market_value_usd"]) for row in positions]  # type: ignore[index]
        + [_decimal(bundle["account"]["cash_usd"])]  # type: ignore[index]
    )
    max_sell_tickers = int(batch["max_sell_tickers_per_batch"])
    max_sell_lots = int(batch["max_sell_lots_per_batch"])
    max_total_orders = int(batch["max_total_orders_per_batch"])
    max_turnover = _decimal(settings["max_batch_turnover_pct"])
    minimum_buy = _decimal(settings["min_buy_order_notional_usd"])
    reserve = _decimal(settings["cash_reserve_usd"])
    cash = _decimal(bundle["account"]["cash_usd"])  # type: ignore[index]
    if cash < reserve:
        raise AppError("cash_reserve_unavailable", "Current cash is below the configured reserve", status_code=422)

    by_ticker = {str(row["ticker"]): row for row in positions}  # type: ignore[index]
    lots_by_ticker: dict[str, list[dict[str, object]]] = {}
    for row in lots:
        lots_by_ticker.setdefault(str(row["ticker"]), []).append(row)

    candidates: list[dict[str, object]] = []
    for ticker, position in by_ticker.items():
        source_quote = quotes.get(ticker)
        source_price_raw = source_quote.get("last_usd") if isinstance(source_quote, dict) else None
        if source_price_raw is None:
            continue
        source_price = _decimal(source_price_raw)
        source_lots: list[dict[str, object]] = []
        total_loss = Decimal(0)
        for lot in lots_by_ticker.get(ticker, []):
            if lot["quality_flags"]:
                continue
            available = _decimal(lot["available_shares"])
            whole_shares = available.to_integral_value(rounding=ROUND_DOWN)
            basis = _decimal(lot["adjusted_unit_basis_usd"])
            if whole_shares <= 0 or basis <= source_price:
                continue
            loss = exact_product(exact_difference(source_price, basis), whole_shares)
            if loss >= 0:
                continue
            source_lots.append({**lot, "proposed_shares": str(whole_shares)})
            total_loss = exact_sum((total_loss, loss))
        if not source_lots:
            continue

        sleeve_key = str(position["sleeve_key"])
        source_path = sleeve_assignment_path(
            sleeves_by_key,
            sleeve_key,
            str(position["sub_sleeve_key"])
            if position["sub_sleeve_key"] is not None
            else None,
        )
        source_scope = source_path[0] if source_path else sleeve_key
        allowed = sorted(
            (
                row
                for row in policy_rows
                if row["enabled"]
                and row["ticker"] != ticker
                and (
                    configured_path := sleeve_assignment_path(
                        sleeves_by_key,
                        str(row["sleeve_key"]),
                        str(row["sub_sleeve_key"]) if row["sub_sleeve_key"] is not None else None,
                    )
                )
                and configured_path[0] == source_scope
            ),
            key=lambda row: (int(row["priority"]), str(row["ticker"])),
        )
        replacement: dict[str, object] | None = None
        for row in allowed:
            quote = quotes.get(str(row["ticker"]))
            if (
                not isinstance(quote, dict)
                or quote.get("last_usd") is None
                or quote.get("quality") != "good"
                or int(quote.get("sync_generation", 0)) != int(bundle["source_generation"])
            ):
                continue
            replacement_assignment = resolve_policy_assignment(
                policy, str(row["ticker"]), asset_type="ETF"
            )
            if replacement_assignment is None:
                continue
            price = _decimal(quote["last_usd"])
            if price > 0:
                replacement = {
                    **row,
                    "sleeve_key": replacement_assignment[0],
                    "sub_sleeve_key": replacement_assignment[1],
                    "price": str(price),
                    "quote": quote,
                }
                break
        if replacement is None:
            continue

        proceeds = exact_sum(
            exact_product(source_price, _decimal(lot["proposed_shares"])) for lot in source_lots
        )
        if proceeds > exact_percent_product(portfolio_total, max_turnover):
            continue
        if len(source_lots) > max_sell_lots or max_sell_tickers < 1 or max_total_orders < 2:
            continue
        candidates.append(
            {
                "ticker": ticker,
                "asset_type": position["asset_type"],
                "source_price": str(source_price),
                "source_quote": source_quote,
                "sleeve_key": position["sleeve_key"],
                "sub_sleeve_key": position["sub_sleeve_key"],
                "sell_lots": source_lots,
                "replacement": replacement,
                "total_loss": str(total_loss),
                "proceeds": str(proceeds),
            }
        )

    candidates.sort(key=lambda row: (_decimal(row["total_loss"]).copy_abs().copy_negate(), str(row["ticker"])))
    result: list[dict[str, object]] = []
    used_lots = 0
    used_turnover = Decimal(0)
    turnover_limit = exact_percent_product(portfolio_total, max_turnover)
    for row in candidates:
        source_lots = row["sell_lots"]
        assert isinstance(source_lots, list)
        proposed = [*result, row]
        sell_tickers = {str(item["ticker"]) for item in proposed}
        if len(sell_tickers) > max_sell_tickers or used_lots + len(source_lots) > max_sell_lots:
            continue
        proceeds = _decimal(row["proceeds"])
        if exact_sum((used_turnover, proceeds)) > turnover_limit:
            continue
        proceeds_by_target: dict[str, Decimal] = {}
        target_prices: dict[str, Decimal] = {}
        for item in proposed:
            replacement = item["replacement"]
            assert isinstance(replacement, dict)
            target = str(replacement["ticker"])
            proceeds_by_target[target] = exact_sum((proceeds_by_target.get(target, Decimal(0)), _decimal(item["proceeds"])))
            target_prices[target] = _decimal(replacement["price"])
        buy_tickers = {
            target
            for target, pooled_proceeds in proceeds_by_target.items()
            if whole_share_floor(pooled_proceeds, target_prices[target]) > 0
        }
        if len(sell_tickers) + len(buy_tickers) > max_total_orders:
            continue
        result.append(row)
        used_lots += len(source_lots)
        used_turnover = exact_sum((used_turnover, proceeds))

    # The minimum is a BUY-order rule: apply it to the pooled order, never one group at a time.
    pooled: dict[str, tuple[Decimal, Decimal]] = {}
    for row in result:
        replacement = row["replacement"]
        assert isinstance(replacement, dict)
        target = str(replacement["ticker"])
        proceeds, price = pooled.get(target, (Decimal(0), _decimal(replacement["price"])))
        pooled[target] = (exact_sum((proceeds, _decimal(row["proceeds"]))), price)
    excluded = {
        target
        for target, (proceeds, price) in pooled.items()
        if whole_share_floor(proceeds, price) <= 0 or exact_product(whole_share_floor(proceeds, price), price) < minimum_buy
    }
    return [
        row
        for row in result
        if str(row["replacement"]["ticker"]) not in excluded  # type: ignore[index]
    ]



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
    realized_by_term = {"ST": Decimal(0), "LT": Decimal(0)}
    as_of = date.fromisoformat(str(run.as_of.date()))
    for lot in lots:
        term = _term(date.fromisoformat(str(lot["acquired_date"])), as_of)
        realized_by_term[term] = exact_sum(
            (
                realized_by_term[term],
                exact_product(
                    exact_difference(source_price, _decimal(lot["adjusted_unit_basis_usd"])),
                    _decimal(lot["proposed_shares"]),
                ),
            )
        )
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
            net_st_realized_usd=realized_by_term["ST"],
            net_lt_realized_usd=realized_by_term["LT"],
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
        acquired = date.fromisoformat(str(lot["acquired_date"]))
        term = _term(acquired, as_of)
        realized = exact_product(
            exact_difference(source_price, _decimal(lot["adjusted_unit_basis_usd"])), proposed_shares
        )
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
    bundle = _frozen_input(session, account, sync_state, policy)
    configured = {
        "max_sell_tickers_per_batch": policy.max_sell_tickers_per_batch,
        "max_sell_lots_per_batch": policy.max_sell_lots_per_batch,
        "max_total_orders_per_batch": policy.max_total_orders_per_batch,
    }
    requested = request.model_dump(exclude={"mode"}, exclude_none=True)
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
    bundle["batch_settings"] = batch_settings
    fingerprint = _fingerprint(bundle)
    bundle["input_fingerprint"] = fingerprint
    as_of = datetime.fromisoformat(str(bundle["account"]["as_of"]))  # type: ignore[index]
    run = OptimizerRun(
        id=str(uuid4()),
        policy_revision_id=policy.id,
        source_generation=sync_state.current_generation,
        as_of=as_of,
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
    candidates = _candidate_groups(bundle, batch_settings)
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

    frozen_account = bundle["account"]
    account = session.get(Account, 1)
    if (
        account is None
        or account.source != frozen_account["source"]
        or str(account.cash_usd) != frozen_account["cash_usd"]
        or str(account.settled_buying_power_usd) != frozen_account["settled_buying_power_usd"]
        or _datetime_iso(account.as_of) != frozen_account["as_of"]
        or _fingerprint(account.broker_account_id_key) != frozen_account["account_key_fingerprint"]
    ):
        raise AppError("stale_run_account", "Current account values changed; create a new demo run", status_code=409)

    securities = {row.id: row for row in session.scalars(select(Security)).all()}
    frozen_positions = {row["ticker"]: row for row in bundle["positions"]}
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

    def quote_matches(ticker: str, security_id: int) -> bool:
        frozen_quote = bundle.get("quotes", {}).get(ticker)
        live_quote = session.scalar(select(CurrentQuote).where(CurrentQuote.security_id == security_id))
        if not isinstance(frozen_quote, dict) or live_quote is None:
            return False
        return (
            live_quote.sync_generation == run.source_generation
            and live_quote.quality.lower() == "good"
            and (str(live_quote.bid_usd) if live_quote.bid_usd is not None else None)
            == frozen_quote.get("bid_usd")
            and (str(live_quote.ask_usd) if live_quote.ask_usd is not None else None)
            == frozen_quote.get("ask_usd")
            and (str(live_quote.last_usd) if live_quote.last_usd is not None else None)
            == frozen_quote.get("last_usd")
            and live_quote.source == frozen_quote.get("source")
            and live_quote.quality == frozen_quote.get("quality")
            and _datetime_iso(live_quote.as_of) == frozen_quote.get("as_of")
        )

    for ticker, frozen in frozen_positions.items():
        position = live_positions[ticker]
        security = securities[position.security_id]
        if (
            position.sync_generation != run.source_generation
            or str(position.shares) != frozen["shares"]
            or str(position.market_value_usd) != frozen["market_value_usd"]
            or _datetime_iso(position.as_of) != frozen["as_of"]
            or security.asset_type != frozen["asset_type"]
            or security.is_completion_etf != frozen["is_completion_etf"]
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

    frozen_lots = {row["broker_lot_id"]: row for row in bundle["lots"]}
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
                or live.shares != _decimal(frozen["shares"])
                or live.available_shares != _decimal(frozen["available_shares"])
                or live.adjusted_unit_basis_usd != _decimal(frozen["adjusted_unit_basis_usd"])
                or (
                    str(live.broker_wash_adjustment_usd) if live.broker_wash_adjustment_usd is not None else None
                ) != frozen["broker_wash_adjustment_usd"]
                or live.source != frozen["source"]
                or _datetime_iso(live.as_of) != frozen["as_of"]
                or live.fractional_cleanup_unsupported != frozen["fractional_cleanup_unsupported"]
                or live.quality_flags != frozen["quality_flags"]
                or live.acquired_date.isoformat() != frozen["acquired_date"]
                or security.ticker != frozen["ticker"]
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
    total_proceeds = Decimal(0)
    total_buy_cost = Decimal(0)
    total_st = Decimal(0)
    total_lt = Decimal(0)
    selected_lot_count = 0
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
        realized_st = Decimal(0)
        realized_lt = Decimal(0)
        shares_sold = Decimal(0)
        for row in selected_rows:
            proceeds = exact_sum((proceeds, exact_product(source_price, row.shares)))
            shares_sold = exact_sum((shares_sold, row.shares))
            if row.st_lt_term == "ST":
                realized_st = exact_sum((realized_st, row.realized_pl_usd))
            else:
                realized_lt = exact_sum((realized_lt, row.realized_pl_usd))

        selected = group.id in selected_group_ids
        group.selected = selected
        for row in lot_rows:
            row.selected = selected and row.broker_lot_id in requested_ids
        if selected:
            selected_tickers.add(source_security.ticker)
            selected_lot_count += len(selected_rows)
            total_proceeds = exact_sum((total_proceeds, proceeds))
            total_st = exact_sum((total_st, realized_st))
            total_lt = exact_sum((total_lt, realized_lt))
            pool = buy_pools.setdefault(
                buy_leg.id,
                {"leg": buy_leg, "proceeds": Decimal(0), "sell_leg_ids": [], "group_ids": []},
            )
            pool["proceeds"] = exact_sum((pool["proceeds"], proceeds))  # type: ignore[arg-type]
            pool["sell_leg_ids"].append(sell_leg.id)  # type: ignore[union-attr]
            pool["group_ids"].append(group.id)  # type: ignore[union-attr]

        sell_leg.shares = shares_sold if selected else Decimal(0)
        sell_leg.net_st_realized_usd = realized_st if selected else Decimal(0)
        sell_leg.net_lt_realized_usd = realized_lt if selected else Decimal(0)
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
                "realized_st": realized_st if selected else Decimal(0),
                "realized_lt": realized_lt if selected else Decimal(0),
                "selected": selected,
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
    active_buy_count = 0
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
        details["depends_on_leg_ids"] = list(pool["sell_leg_ids"])
        buy_leg.details = details
        total_buy_cost = exact_sum((total_buy_cost, buy_cost))
        active_buy_count += 1
        first_group = group_ids[0]
        for action in actions:
            if action["selected"] and action["buy_leg"].id == buy_leg.id:
                action["buy_shares"] = buy_shares
                action["buy_cost"] = buy_cost
                action["apply_buy"] = action["group"].id == first_group

    settings = bundle["policy"]["settings"]
    cash = _decimal(bundle["account"]["cash_usd"])
    cash_after = exact_sum((cash, total_proceeds, total_buy_cost.copy_negate()))
    reserve = _decimal(settings["cash_reserve_usd"])
    if cash_after < reserve:
        raise AppError("selected_basket_infeasible", "Selected basket would breach the configured cash reserve", status_code=422)
    batch = run.batch_settings
    max_tickers = int(batch["max_sell_tickers_per_batch"])
    max_lots = int(batch["max_sell_lots_per_batch"])
    max_orders = int(batch["max_total_orders_per_batch"])
    max_turnover = _decimal(settings["max_batch_turnover_pct"])
    portfolio_total = exact_sum(
        [_decimal(row["market_value_usd"]) for row in bundle["positions"]] + [cash]
    )
    turnover_limit = exact_percent_product(portfolio_total, max_turnover)
    actual_orders = len(selected_tickers) + active_buy_count
    if len(selected_tickers) > max_tickers or selected_lot_count > max_lots or actual_orders > max_orders:
        raise AppError(
            "selected_basket_infeasible",
            "Selected basket exceeds an active small-batch order limit",
            status_code=422,
            details={"sell_tickers": len(selected_tickers), "sell_lots": selected_lot_count, "orders": actual_orders},
        )
    if total_proceeds > turnover_limit:
        raise AppError(
            "selected_basket_infeasible",
            "Selected basket exceeds the configured demo turnover limit",
            status_code=422,
            details={"sell_proceeds_usd": str(total_proceeds), "turnover_limit_usd": str(turnover_limit)},
        )

    effects = _account_effects(bundle, actions)
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
        "positions_exited_count": _positions_exited(bundle, actions),
        "orders_count": actual_orders,
        "cash_before_usd": str(cash),
        "cash_after_usd": str(cash_after),
        "portfolio_effects": effects,
        "no_trade_reason": "No demo candidates met the configured batch and funding limits" if not actions or not selected_group_ids else None,
        "constraints_satisfied": None,
    }


def _positions_exited(bundle: dict[str, object], actions: list[dict[str, object]]) -> int:
    positions = {row["ticker"]: _decimal(row["shares"]) for row in bundle["positions"]}
    sold: dict[str, Decimal] = {}
    for action in actions:
        if action["selected"]:
            ticker = str(action["source_ticker"])
            sold[ticker] = exact_sum((sold.get(ticker, Decimal(0)), _decimal(action["shares_sold"])))
    return sum(1 for ticker, shares in sold.items() if shares >= positions.get(ticker, Decimal(0)))


def _account_effects(bundle: dict[str, object], actions: list[dict[str, object]]) -> dict[str, object]:
    policy = bundle["policy"]
    assert isinstance(policy, dict)
    sleeves = policy["sleeves"]
    assert isinstance(sleeves, list)
    sleeves_by_key = {
        str(row["sleeve_key"]): row
        for row in sleeves
        if row["enabled"]
    }
    top_sleeves = [row for row in sleeves_by_key.values() if row["parent_sleeve_key"] is None]
    child_sleeves = [row for row in sleeves_by_key.values() if row["parent_sleeve_key"] is not None]
    container = next((row for row in top_sleeves if row["is_direct_index_container"]), None)
    current_values: dict[str, Decimal] = {}
    for row in bundle["positions"]:
        path = sleeve_assignment_path(
            sleeves_by_key,
            str(row["sleeve_key"]),
            str(row["sub_sleeve_key"]) if row["sub_sleeve_key"] is not None else None,
        )
        accumulate_sleeve_value(current_values, path, _decimal(row["market_value_usd"]))

    cash = _decimal(bundle["account"]["cash_usd"])
    cash_sleeve = next((row for row in sleeves_by_key.values() if row["is_cash_sleeve"]), None)
    cash_path = (
        sleeve_assignment_path(sleeves_by_key, str(cash_sleeve["sleeve_key"]))
        if cash_sleeve is not None
        else ()
    )
    if cash_path:
        accumulate_sleeve_value(current_values, cash_path, cash)

    proposed_values = dict(current_values)
    direct_children = {
        str(child["sleeve_key"])
        for child in child_sleeves
        if container is not None
        and child["parent_sleeve_key"] == container["sleeve_key"]
        and child["is_direct_index_sleeve"]
    }

    def is_transition_etf(asset_type: object, path: tuple[str, ...]) -> bool:
        return bool(
            container is not None
            and asset_type == "ETF"
            and str(container["sleeve_key"]) in path
            and not direct_children.intersection(path)
        )

    current_etf_value = Decimal(0)
    for row in bundle["positions"]:
        path = sleeve_assignment_path(
            sleeves_by_key,
            str(row["sleeve_key"]),
            str(row["sub_sleeve_key"]) if row["sub_sleeve_key"] is not None else None,
        )
        if is_transition_etf(row["asset_type"], path):
            current_etf_value = exact_sum((current_etf_value, _decimal(row["market_value_usd"])))
    proposed_etf_value = current_etf_value

    total_sell = Decimal(0)
    total_buy = Decimal(0)
    for action in actions:
        if not action["selected"]:
            continue
        proceeds = _decimal(action["proceeds"])
        buy_cost = _decimal(action["buy_cost"]) if action["apply_buy"] else Decimal(0)
        source_path = sleeve_assignment_path(
            sleeves_by_key,
            str(action["source_sleeve_key"]),
            str(action["source_sub_sleeve_key"])
            if action["source_sub_sleeve_key"] is not None
            else None,
        )
        target_path = sleeve_assignment_path(
            sleeves_by_key,
            str(action["target_sleeve_key"]),
            str(action["target_sub_sleeve_key"])
            if action["target_sub_sleeve_key"] is not None
            else None,
        )
        accumulate_sleeve_value(proposed_values, source_path, proceeds.copy_negate())
        accumulate_sleeve_value(proposed_values, target_path, buy_cost)
        if is_transition_etf(action["source_asset_type"], source_path):
            proposed_etf_value = exact_difference(proposed_etf_value, proceeds)
        if is_transition_etf(action["target_asset_type"], target_path):
            proposed_etf_value = exact_sum((proposed_etf_value, buy_cost))
        total_sell = exact_sum((total_sell, proceeds))
        total_buy = exact_sum((total_buy, buy_cost))

    cash_after = exact_sum((cash, total_sell, total_buy.copy_negate()))
    if cash_path:
        accumulate_sleeve_value(proposed_values, cash_path, exact_difference(cash_after, cash))

    portfolio_total = exact_sum([_decimal(row["market_value_usd"]) for row in bundle["positions"]] + [cash])
    current_top = {
        row["sleeve_key"]: percentage(current_values.get(row["sleeve_key"], Decimal(0)), portfolio_total)
        for row in top_sleeves
    }
    proposed_top = {
        row["sleeve_key"]: percentage(proposed_values.get(row["sleeve_key"], Decimal(0)), portfolio_total)
        for row in top_sleeves
    }
    target_top = {row["sleeve_key"]: str(row["target_pct"]) for row in top_sleeves}
    allocation: dict[str, object] = {
        "current": {
            "total_portfolio_usd": str(portfolio_total),
            "sleeve_weights_pct": {key: str(value) for key, value in current_top.items()},
        },
        "proposed": {
            "total_portfolio_usd": str(portfolio_total),
            "sleeve_weights_pct": {key: str(value) for key, value in proposed_top.items()},
        },
        "target": {"sleeve_weights_pct": target_top},
    }
    transition = None
    if container is not None:
        children = [row for row in child_sleeves if row["parent_sleeve_key"] == container["sleeve_key"]]
        us_current = current_values.get(container["sleeve_key"], Decimal(0))
        us_proposed = proposed_values.get(container["sleeve_key"], Decimal(0))

        def child_values(values: dict[str, Decimal], total: Decimal) -> dict[str, dict[str, str]]:
            return {
                child["sleeve_key"]: {
                    "value_usd": str(values.get(child["sleeve_key"], Decimal(0))),
                    "within_us_sleeve_pct": str(
                        percentage(values.get(child["sleeve_key"], Decimal(0)), total)
                    ),
                    "whole_portfolio_pct": str(
                        percentage(values.get(child["sleeve_key"], Decimal(0)), portfolio_total)
                    ),
                }
                for child in children
            }

        target_children = {
            child["sleeve_key"]: {
                "within_us_sleeve_pct": str(child["target_pct"]),
                "whole_portfolio_pct": str(
                    exact_percent_product(_decimal(container["target_pct"]), _decimal(child["target_pct"]))
                ),
            }
            for child in children
        }
        transition = {
            "sleeve_key": container["sleeve_key"],
            "label": "DEMO only; values include the full account and cash",
            "current": {
                "us_sleeve_value_usd": str(us_current),
                "us_sleeve_whole_portfolio_pct": str(percentage(us_current, portfolio_total)),
                "etf_progress_pct": str(percentage(current_etf_value, us_current)),
                "children": child_values(current_values, us_current),
            },
            "proposed_basket": {
                "us_sleeve_value_usd": str(us_proposed),
                "us_sleeve_whole_portfolio_pct": str(percentage(us_proposed, portfolio_total)),
                "etf_progress_pct": str(percentage(proposed_etf_value, us_proposed)),
                "children": child_values(proposed_values, us_proposed),
            },
            "target": {
                "us_sleeve_whole_portfolio_pct": str(container["target_pct"]),
                "children": target_children,
            },
        }
    return {"allocation": allocation, "us_transition": transition}


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
    if payload.note is not None:
        group.note = payload.note
    if payload.rejected is not None:
        group.rejected = payload.rejected
        if payload.rejected:
            group.selected = False
            group.rejection_reason = payload.rejection_reason
            for row in _group_lot_rows(session, group.id):
                row.selected = False
        else:
            group.rejection_reason = None
    elif payload.rejection_reason is not None:
        raise AppError("invalid_annotation", "A rejection reason requires rejected=true", status_code=422)
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


def run_summary(run: OptimizerRun) -> dict[str, object]:
    metrics = run.metrics
    bundle = run.frozen_input_bundle
    settings = bundle.get("policy", {}).get("settings", {})
    tax_status = metrics.get("estimated_tax_benefit_status", "tax_profile_incomplete")
    return {
        "run_id": run.id,
        "status": "demo",
        "mode": "recommendations_only",
        "policy_revision_id": run.policy_revision_id,
        "source_generation": run.source_generation,
        "as_of": run.as_of,
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
        "portfolio_effects": metrics.get("portfolio_effects"),
        "constraints_satisfied": None,
        "no_trade_reason": metrics.get("no_trade_reason"),
        "warnings": list(run.warnings),
        "tax_profile_configured": settings.get("short_term_tax_rate") is not None
        and settings.get("long_term_tax_rate") is not None,
    }


def _leg_dict(session: Session, leg: RecommendationLeg) -> dict[str, object]:
    security = session.get(Security, leg.security_id)
    details = dict(leg.details)
    if isinstance(details.get("depends_on_leg_ids"), list):
        dependencies = list(details["depends_on_leg_ids"])
    elif details.get("depends_on_leg_id"):
        dependencies = [details["depends_on_leg_id"]]
    else:
        dependencies = []
    selected_lots = []
    if leg.side == "SELL":
        selected_lots = [
            {
                "broker_lot_id": row.broker_lot_id,
                "shares": str(row.shares),
                "acquired_date": row.acquired_date.isoformat(),
                "adjusted_basis_usd": str(row.adjusted_basis_usd),
                "st_lt": row.st_lt_term,
                "realized_pl_usd": str(row.realized_pl_usd),
                "selected": row.selected,
            }
            for row in session.scalars(
                select(RecommendationSelectedLot)
                .where(RecommendationSelectedLot.leg_id == leg.id)
                .order_by(RecommendationSelectedLot.broker_lot_id)
            ).all()
        ]
    group_ids = session.scalars(
        select(RecommendationGroupLeg.group_id)
        .join(RecommendationGroup, RecommendationGroup.id == RecommendationGroupLeg.group_id)
        .where(RecommendationGroupLeg.leg_id == leg.id)
        .order_by(RecommendationGroup.rank)
    ).all()
    return {
        "leg_id": leg.id,
        "side": leg.side,
        "ticker": security.ticker if security else None,
        "shares": str(leg.shares),
        "estimated_unit_price_usd": str(leg.estimated_unit_price_usd),
        "estimated_notional_usd": str(exact_product(leg.shares, leg.estimated_unit_price_usd)),
        "net_st_realized_usd": str(leg.net_st_realized_usd),
        "net_lt_realized_usd": str(leg.net_lt_realized_usd),
        "sequence": leg.sequence,
        "dependencies": dependencies,
        "selected": leg.shares > 0,
        "group_ids": list(group_ids),
        "selected_lots": selected_lots,
        "details": details,
    }


def _group_dict(session: Session, group: RecommendationGroup) -> dict[str, object]:
    return {
        "group_id": group.id,
        "rank": group.rank,
        "group_type": group.group_type,
        "sleeve_key": group.sleeve_key,
        "rationale": group.rationale,
        "estimated_benefit_usd": None,
        "impact": group.impact,
        "dependencies": group.dependencies,
        "selected": group.selected,
        "rejected": group.rejected,
        "note": group.note,
        "rejection_reason": group.rejection_reason,
        "leg_ids": [leg.id for leg in _group_legs(session, group.id)],
        "warnings": [DEMO_WARNING, DEMO_WASH_WARNING, DEMO_RISK_WARNING],
    }


def run_recommendations(session: Session, run: OptimizerRun) -> dict[str, object]:
    groups = session.scalars(
        select(RecommendationGroup).where(RecommendationGroup.run_id == run.id).order_by(RecommendationGroup.rank)
    ).all()
    group_rank = {group.id: group.rank for group in groups}
    legs = session.scalars(
        select(RecommendationLeg)
        .join(RecommendationGroupLeg, RecommendationGroupLeg.leg_id == RecommendationLeg.id)
        .join(RecommendationGroup, RecommendationGroup.id == RecommendationGroupLeg.group_id)
        .where(RecommendationGroup.run_id == run.id)
        .distinct()
    ).unique().all()
    legs.sort(
        key=lambda leg: (
            leg.side == "BUY",
            min((group_rank[group_id] for group_id in _leg_dict(session, leg)["group_ids"]), default=0),
            leg.sequence,
            leg.id,
        )
    )
    return {
        **run_summary(run),
        "groups": [_group_dict(session, group) for group in groups],
        "consolidated_legs": [_leg_dict(session, leg) for leg in legs],
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
            "solver_version",
            "demo",
            "actionable",
            "input_fingerprint",
            "source_checksum",
            "warnings",
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
        "solver_version",
        "demo",
        "input_fingerprint",
        "source_checksum",
        "actionable",
        "group_id",
        "rank",
        "selected",
        "rejected",
        "note",
        "leg_id",
        "side",
        "ticker",
        "shares",
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
                    "rank": ";".join(str(group["rank"]) for group in linked_groups),
                    "selected": leg["selected"],
                    "rejected": any(group["rejected"] for group in linked_groups) if leg["side"] == "SELL" else "",
                    "note": ";".join(group["note"] or "" for group in linked_groups),
                    "leg_id": leg["leg_id"],
                    "side": leg["side"],
                    "ticker": leg["ticker"],
                    "shares": leg["shares"],
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
                    loss_date = latest_run.as_of.date()
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
