from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from app.domain.financial_inputs import FinancialInputs, TransactionInput


@dataclass(frozen=True, slots=True)
class ProposedLotSale:
    ticker: str
    broker_lot_id: str
    shares: Decimal
    realized_pl_usd: Decimal
    trade_group_id: str
    sale_date: date


@dataclass(frozen=True, slots=True)
class ProposedBuy:
    ticker: str
    shares: Decimal
    trade_group_id: str
    buy_date: date


@dataclass(frozen=True, slots=True)
class WashSaleAssessment:
    ticker: str
    broker_lot_id: str
    trade_group_id: str
    eligible: bool
    reasons: tuple[str, ...]
    conflicting_transaction_keys: tuple[str, ...]
    no_buy_through: date | None
    next_eligible_purchase_date: date | None


@dataclass(frozen=True, slots=True)
class BuyWashSaleAssessment:
    ticker: str
    trade_group_id: str
    eligible: bool
    reasons: tuple[str, ...]
    conflicting_transaction_keys: tuple[str, ...]
    no_buy_through: date | None
    next_eligible_purchase_date: date | None


def _has_required_history(inputs: FinancialInputs, sale_date: date) -> bool:
    metadata = inputs.source_metadata
    required_start = sale_date - timedelta(days=30)
    return (
        metadata.transaction_history_complete is True
        and metadata.transaction_history_start_date is not None
        and metadata.transaction_history_start_date <= required_start
        and metadata.transaction_history_end_date is not None
        and metadata.transaction_history_end_date >= sale_date
    )


def _is_recent_buy(transaction: TransactionInput, ticker: str, sale_date: date) -> bool:
    return (
        transaction.ticker.upper() == ticker
        and transaction.is_acquisition
        and sale_date - timedelta(days=30) <= transaction.trade_date <= sale_date
    )


def _recent_lot_issues(
    inputs: FinancialInputs,
    sale: ProposedLotSale,
    group_sales: Sequence[ProposedLotSale],
    recent_buys: Sequence[TransactionInput],
) -> tuple[set[str], set[str]]:
    reasons: set[str] = set()
    transaction_keys: set[str] = set()
    lots_by_id = {
        lot.broker_lot_id: lot for lot in inputs.lots if lot.ticker.upper() == sale.ticker.upper()
    }
    buys_by_lot: dict[str, list[TransactionInput]] = defaultdict(list)
    for transaction in recent_buys:
        if transaction.broker_lot_id is None:
            reasons.add("unattributed_recent_acquisition")
            transaction_keys.add(transaction.broker_transaction_key)
        else:
            buys_by_lot[transaction.broker_lot_id].append(transaction)

    recent_lot_ids = set(buys_by_lot)
    for lot in inputs.lots:
        if (
            lot.ticker.upper() == sale.ticker.upper()
            and sale.sale_date - timedelta(days=30) <= lot.acquired_date <= sale.sale_date
        ):
            recent_lot_ids.add(lot.broker_lot_id)

    group_sold_by_lot: dict[str, Decimal] = defaultdict(Decimal)
    for group_sale in group_sales:
        if group_sale.ticker.upper() == sale.ticker.upper():
            group_sold_by_lot[group_sale.broker_lot_id] += group_sale.shares

    for lot_id in recent_lot_ids:
        acquisitions = buys_by_lot.get(lot_id, [])
        lot = lots_by_id.get(lot_id)
        if lot is None:
            reasons.add("recent_acquisition_not_fully_disposed")
            transaction_keys.update(
                transaction.broker_transaction_key for transaction in acquisitions
            )
            continue

        acquired_shares = sum((transaction.shares for transaction in acquisitions), Decimal(0))
        if acquisitions and acquired_shares != lot.shares:
            reasons.add("recent_acquisition_quantity_mismatch")
            transaction_keys.update(
                transaction.broker_transaction_key for transaction in acquisitions
            )
            continue
        if (
            group_sold_by_lot.get(lot_id, Decimal(0)) != lot.shares
            or lot.available_shares != lot.shares
        ):
            reasons.add("recent_acquisition_not_fully_disposed")
            transaction_keys.update(
                transaction.broker_transaction_key for transaction in acquisitions
            )

    return reasons, transaction_keys


def _validate_action_dates(
    inputs: FinancialInputs,
    proposed_sales: Sequence[ProposedLotSale],
    proposed_buys: Sequence[ProposedBuy],
) -> None:
    if any(sale.sale_date != inputs.proposed_trade_date for sale in proposed_sales) or any(
        buy.buy_date != inputs.proposed_trade_date for buy in proposed_buys
    ):
        raise ValueError("wash-sale action date must match frozen proposed trade date")


def assess_wash_sales(
    inputs: FinancialInputs,
    proposed_sales: Sequence[ProposedLotSale],
    proposed_buys: Sequence[ProposedBuy] = (),
) -> tuple[WashSaleAssessment, ...]:
    """Check same-security 30-day wash rules on exact proposed lot sales and basket buys.

    A recent acquisition is cleared only when its currently retained shares are fully
    available and sold in the same trade group as the loss sale. History must explicitly
    cover the complete lookback interval and the proposed trade date; unknown coverage fails closed.
    """
    _validate_action_dates(inputs, proposed_sales, proposed_buys)
    assessments: list[WashSaleAssessment] = []
    for sale in proposed_sales:
        ticker = sale.ticker.upper()
        if sale.realized_pl_usd >= 0:
            assessments.append(
                WashSaleAssessment(
                    ticker,
                    sale.broker_lot_id,
                    sale.trade_group_id,
                    True,
                    (),
                    (),
                    None,
                    None,
                )
            )
            continue

        reasons: set[str] = set()
        transaction_keys: set[str] = set()
        if not _has_required_history(inputs, sale.sale_date):
            reasons.add("incomplete_acquisition_history")
        else:
            recent_buys = tuple(
                transaction
                for transaction in inputs.transactions
                if _is_recent_buy(transaction, ticker, sale.sale_date)
            )
            same_group_sales = tuple(
                candidate
                for candidate in proposed_sales
                if candidate.trade_group_id == sale.trade_group_id
            )
            acquisition_reasons, acquisition_keys = _recent_lot_issues(
                inputs, sale, same_group_sales, recent_buys
            )
            reasons.update(acquisition_reasons)
            transaction_keys.update(acquisition_keys)

        no_buy_through = sale.sale_date + timedelta(days=30)
        next_eligible = no_buy_through + timedelta(days=1)
        if any(
            buy.ticker.upper() == ticker and sale.sale_date <= buy.buy_date <= no_buy_through
            for buy in proposed_buys
        ):
            reasons.add("proposed_same_security_buy")

        assessments.append(
            WashSaleAssessment(
                ticker=ticker,
                broker_lot_id=sale.broker_lot_id,
                trade_group_id=sale.trade_group_id,
                eligible=not reasons,
                reasons=tuple(sorted(reasons)),
                conflicting_transaction_keys=tuple(sorted(transaction_keys)),
                no_buy_through=no_buy_through,
                next_eligible_purchase_date=next_eligible,
            )
        )
    return tuple(assessments)


def assess_proposed_buys(
    inputs: FinancialInputs,
    proposed_buys: Sequence[ProposedBuy],
    proposed_sales: Sequence[ProposedLotSale] = (),
) -> tuple[BuyWashSaleAssessment, ...]:
    """Check buy eligibility against frozen executed losses and proposed loss sales.

    Transaction realized P/L must be explicitly attributed. A recent SELL with absent P/L,
    or transaction history that does not cover the required window, fails closed rather than
    treating unknown attribution as a gain.
    """
    _validate_action_dates(inputs, proposed_sales, proposed_buys)
    assessments: list[BuyWashSaleAssessment] = []
    for buy in proposed_buys:
        ticker = buy.ticker.upper()
        reasons: set[str] = set()
        transaction_keys: set[str] = set()
        no_buy_through: date | None = None
        if not _has_required_history(inputs, buy.buy_date):
            reasons.add("incomplete_executed_loss_history")

        lookback_start = buy.buy_date - timedelta(days=30)
        for transaction in inputs.transactions:
            if (
                transaction.ticker.upper() != ticker
                or transaction.transaction_kind.upper() != "SELL"
                or not lookback_start <= transaction.trade_date <= buy.buy_date
            ):
                continue
            if transaction.realized_pl_usd is None:
                reasons.add("executed_loss_attribution_unknown")
                transaction_keys.add(transaction.broker_transaction_key)
                restriction_end = transaction.trade_date + timedelta(days=30)
            elif transaction.realized_pl_usd < 0:
                reasons.add("executed_loss_restriction")
                transaction_keys.add(transaction.broker_transaction_key)
                restriction_end = transaction.trade_date + timedelta(days=30)
            elif transaction.broker_lot_id is None:
                # A consolidated order-level gain can conceal loss-making lots.
                reasons.add("executed_loss_attribution_unknown")
                transaction_keys.add(transaction.broker_transaction_key)
                restriction_end = transaction.trade_date + timedelta(days=30)
            else:
                continue
            no_buy_through = max(no_buy_through or restriction_end, restriction_end)

        proposed_loss_sales = tuple(
            sale
            for sale in proposed_sales
            if sale.ticker.upper() == ticker and sale.realized_pl_usd < 0
        )
        if proposed_loss_sales:
            reasons.add("proposed_loss_sale_restriction")
            no_buy_through = max(
                no_buy_through or buy.buy_date,
                max(sale.sale_date + timedelta(days=30) for sale in proposed_loss_sales),
            )

        next_eligible = no_buy_through + timedelta(days=1) if no_buy_through is not None else None
        assessments.append(
            BuyWashSaleAssessment(
                ticker=ticker,
                trade_group_id=buy.trade_group_id,
                eligible=not reasons,
                reasons=tuple(sorted(reasons)),
                conflicting_transaction_keys=tuple(sorted(transaction_keys)),
                no_buy_through=no_buy_through,
                next_eligible_purchase_date=next_eligible,
            )
        )
    return tuple(assessments)
