"""Deterministic demo candidate generation; no persistence or portfolio accounting."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal
from typing import cast

from app.domain.allocation import assignment_path, resolve_holding
from app.domain.decimal_math import (
    exact_difference,
    exact_percent_product,
    exact_product,
    exact_sum,
    whole_share_floor,
)
from app.domain.financial_inputs import FinancialInputs, LotInput
from app.services.errors import AppError


def _batch_limit(batch: dict[str, object], name: str) -> int:
    value = batch.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AppError("invalid_batch_limit", f"Demo batch setting {name} must be a nonnegative integer", status_code=422)
    return value


def _decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _datetime_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _candidate_groups(inputs: FinancialInputs, batch: dict[str, object]) -> list[dict[str, object]]:
    policy = inputs.policy.allocation
    settings = inputs.policy.settings
    quotes = {row.ticker: row for row in inputs.quotes}
    positions = {row.ticker: row for row in inputs.positions}
    lots_by_ticker: dict[str, list[LotInput]] = {}
    for lot in inputs.lots:
        lots_by_ticker.setdefault(lot.ticker, []).append(lot)
    portfolio_total = exact_sum(
        [row.market_value_usd for row in inputs.positions] + [inputs.account.cash_usd]
    )
    max_sell_tickers = _batch_limit(batch, "max_sell_tickers_per_batch")
    max_sell_lots = _batch_limit(batch, "max_sell_lots_per_batch")
    max_total_orders = _batch_limit(batch, "max_total_orders_per_batch")
    max_turnover = _decimal(settings.get("max_batch_turnover_pct", Decimal(0)))
    minimum_buy = _decimal(settings.get("min_buy_order_notional_usd", Decimal(0)))
    reserve = _decimal(settings.get("cash_reserve_usd", Decimal(0)))
    cash = inputs.account.cash_usd
    if cash < reserve:
        raise AppError("cash_reserve_unavailable", "Current cash is below the configured reserve", status_code=422)

    candidates: list[dict[str, object]] = []
    for ticker, position in positions.items():
        assignment = position.assignment
        if assignment is None:
            continue
        source_quote = quotes.get(ticker)
        if source_quote is None or source_quote.last_usd is None:
            continue
        source_price = source_quote.last_usd
        source_lots: list[dict[str, object]] = []
        total_loss = Decimal(0)
        for lot in lots_by_ticker.get(ticker, []):
            if lot.quality_flags:
                continue
            whole_shares = lot.available_shares.to_integral_value(rounding=ROUND_DOWN)
            if whole_shares <= 0 or lot.adjusted_unit_basis_usd <= source_price:
                continue
            loss = exact_product(
                exact_difference(source_price, lot.adjusted_unit_basis_usd), whole_shares
            )
            if loss >= 0:
                continue
            source_lots.append(
                {
                    "ticker": lot.ticker,
                    "broker_lot_id": lot.broker_lot_id,
                    "acquired_date": lot.acquired_date,
                    "shares": str(lot.shares),
                    "available_shares": str(lot.available_shares),
                    "adjusted_unit_basis_usd": str(lot.adjusted_unit_basis_usd),
                    "quality_flags": list(lot.quality_flags),
                    "proposed_shares": str(whole_shares),
                }
            )
            total_loss = exact_sum((total_loss, loss))
        if not source_lots:
            continue

        source_path = assignment_path(
            policy, assignment.sleeve_key, assignment.sub_sleeve_key
        )
        if not source_path:
            continue
        source_scope = source_path[0]
        allowed = sorted(
            (
                row
                for row in policy.allowed_securities
                if row.enabled
                and row.ticker != ticker
                and (configured_path := assignment_path(policy, row.sleeve_key, row.sub_sleeve_key))
                and configured_path[0] == source_scope
            ),
            key=lambda row: (row.priority, row.ticker),
        )
        replacement: dict[str, object] | None = None
        for row in allowed:
            quote = quotes.get(row.ticker)
            security = inputs.security_for(row.ticker)
            if (
                quote is None
                or quote.last_usd is None
                or quote.quality != "good"
                or quote.sync_generation != inputs.source_generation
                or security is None
            ):
                continue
            replacement_resolution = resolve_holding(policy, security.identity)
            replacement_assignment = replacement_resolution.assignment
            if replacement_assignment is None:
                continue

            price = quote.last_usd
            if price > 0:
                replacement = {
                    "ticker": row.ticker,
                    "sleeve_key": replacement_assignment.sleeve_key,
                    "sub_sleeve_key": replacement_assignment.sub_sleeve_key,
                    "price": str(price),
                    "quote": {
                        "as_of": _datetime_iso(quote.as_of),
                        "source": quote.source,
                        "quality": quote.quality,
                        "sync_generation": quote.sync_generation,
                    },
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
                "asset_type": position.asset_type,
                "source_price": str(source_price),
                "source_quote": {
                    "as_of": _datetime_iso(source_quote.as_of),
                    "source": source_quote.source,
                },
                "sleeve_key": assignment.sleeve_key,
                "sub_sleeve_key": assignment.sub_sleeve_key,
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
        source_lots = cast(list[dict[str, object]], row["sell_lots"])
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
            replacement_item = item["replacement"]
            assert isinstance(replacement_item, dict)
            target = str(replacement_item["ticker"])
            proceeds_by_target[target] = exact_sum(
                (proceeds_by_target.get(target, Decimal(0)), _decimal(item["proceeds"]))
            )
            target_prices[target] = _decimal(replacement_item["price"])
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
        replacement_item = row["replacement"]
        assert isinstance(replacement_item, dict)
        target = str(replacement_item["ticker"])
        proceeds, price = pooled.get(target, (Decimal(0), _decimal(replacement_item["price"])))
        pooled[target] = (exact_sum((proceeds, _decimal(row["proceeds"]))), price)
    excluded = {
        target
        for target, (proceeds, price) in pooled.items()
        if whole_share_floor(proceeds, price) <= 0
        or exact_product(whole_share_floor(proceeds, price), price) < minimum_buy
    }
    return [
        row
        for row in result
        if str(row["replacement"]["ticker"]) not in excluded  # type: ignore[index]
    ]
