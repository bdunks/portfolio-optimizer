"""Seeded, bounded whole-share reference search for representative optimizer review.

This is a best-known heuristic, not an exact optimizer. It builds baskets independently of production
search and rechecks each with the owner's exact Decimal validator. The shared validator is not
independent proof of financial semantics; no finite-domain/global optimum or live-probability claim is
made. Synthetic case frequency is not an estimate of live accounts or markets.
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal
from time import monotonic
from typing import Literal

from app.domain.decimal_math import exact_difference, exact_product, exact_sum
from app.domain.financial_inputs import FinancialInputs, PositionInput, QuoteInput, SecurityInput
from app.domain.portfolio_accounting import ConsolidatedLeg, LotAllocation
from app.optimizer.validation import (
    CandidateValidation,
    ObjectivePolicy,
    read_objective_policy,
    validate_candidate,
)

StopReason = Literal["candidate_budget", "deadline", "pool_unavailable", "generation_budget"]
_MODES = ("coupled", "multi_lot_sell", "local", "sell_only", "buy_only", "random")


@dataclass(frozen=True, slots=True)
class CandidateAssessment:
    """Compact validation result; full portfolio evaluations are never retained."""

    legs: tuple[ConsolidatedLeg, ...]
    validation_completed: bool
    accepted: bool
    reasons: tuple[str, ...]
    objective_value: Decimal | None
    estimated_tax_benefit_usd: Decimal | None
    estimated_trading_cost_usd: Decimal | None
    proposed_cash_usd: Decimal | None

    @property
    def feasible(self) -> bool:
        return self.validation_completed and self.accepted and self.objective_value is not None


@dataclass(frozen=True, slots=True)
class CandidateTrace:
    """One bounded candidate example per generation mode, not a full candidate log."""

    ordinal: int
    source: str
    legs: tuple[ConsolidatedLeg, ...]
    validation_completed: bool
    feasible: bool
    objective_value: Decimal | None
    estimated_trading_cost_usd: Decimal | None
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RepresentativeSearchResult:
    seed: int
    input_checksum: str | None
    input_checksum_source: str
    candidate_budget: int
    time_budget_seconds: float
    elapsed_seconds: float
    candidate_proposal_count: int
    validation_attempt_count: int
    unique_candidate_count: int
    feasible_candidate_count: int
    generation_step_count: int
    generation_mode_attempts: tuple[tuple[str, int], ...]
    stop_reason: StopReason
    search_complete: bool
    global_optimality_proven: bool
    pool_complete: bool
    pool_scan_count: int
    sell_lot_option_count: int
    sell_ticker_count: int
    buy_ticker_option_count: int
    fractional_only_lots_skipped: int
    other_ineligible_lots_skipped: int
    batch_limits: tuple[tuple[str, int | None], ...]
    quantity_domain: str
    incumbent_assessment: CandidateAssessment
    no_trade_assessment: CandidateAssessment
    best_known: CandidateAssessment | None
    candidate_trace: tuple[CandidateTrace, ...]
    metadata_within_time_budget: bool


@dataclass(frozen=True, slots=True)
class _SellOption:
    ticker: str
    lot_id: str
    max_shares: int
    price: Decimal


@dataclass(frozen=True, slots=True)
class _BuyOption:
    ticker: str
    max_shares: int
    price: Decimal


@dataclass(frozen=True, slots=True)
class _Pool:
    sells: tuple[_SellOption, ...]
    buys: tuple[_BuyOption, ...]
    sells_by_key: dict[tuple[str, str], _SellOption]
    sells_by_ticker: dict[str, tuple[_SellOption, ...]]
    buys_by_ticker: dict[str, _BuyOption]
    position_caps: dict[str, int]
    max_sell_tickers: int | None
    max_sell_lots: int | None
    max_total_orders: int | None
    settled_buying_power: Decimal
    scan_count: int
    fractional_lots_skipped: int
    other_lots_skipped: int
    complete: bool
    quantity_domain: str


@dataclass(frozen=True, slots=True)
class _PoolBuild:
    pool: _Pool
    objective_policy: ObjectivePolicy | None
    deadline_hit: bool


class _DeadlineExpired(Exception):
    """Internal fast exit from a bounded phase."""


def _check_deadline(deadline: float) -> None:
    if monotonic() >= deadline:
        raise _DeadlineExpired


def _setting_int(inputs: FinancialInputs, key: str) -> int | None:
    value = inputs.policy.settings.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def _whole_floor(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_FLOOR))


def _quote_mark(quote: QuoteInput, inputs: FinancialInputs, ticker: str) -> Decimal | None:
    if (
        quote.ticker != ticker
        or quote.quality.lower() != "good"
        or quote.sync_generation != inputs.source_generation
        or quote.as_of > inputs.account.as_of
    ):
        return None
    if quote.bid_usd is not None and quote.ask_usd is not None:
        if quote.bid_usd > 0 and quote.ask_usd > 0 and quote.bid_usd <= quote.ask_usd:
            return (quote.bid_usd + quote.ask_usd) / Decimal(2)
        return None
    for value in (quote.last_usd, quote.bid_usd, quote.ask_usd):
        if value is not None and value > 0:
            return value
    return None


def _blank_pool(
    limits: tuple[int | None, int | None, int | None] = (None, None, None),
    *,
    scan_count: int = 0,
    fractional_count: int = 0,
    other_count: int = 0,
    complete: bool = False,
) -> _Pool:
    return _Pool(
        (),
        (),
        {},
        {},
        {},
        {},
        *limits,
        Decimal(0),
        scan_count,
        fractional_count,
        other_count,
        complete,
        "incomplete or unavailable",
    )


def _build_pool(inputs: FinancialInputs, deadline: float) -> _PoolBuild:
    """Bound pool discovery by the same deadline used for generation and validation."""
    objective_policy, _ = read_objective_policy(inputs)
    limits = (
        _setting_int(inputs, "max_sell_tickers_per_batch"),
        _setting_int(inputs, "max_sell_lots_per_batch"),
        _setting_int(inputs, "max_total_orders_per_batch"),
    )
    if objective_policy is None:
        return _PoolBuild(_blank_pool(limits), None, False)

    scan_count = fractional_count = ineligible_count = 0
    try:
        positions: dict[str, PositionInput] = {}
        for row in inputs.positions:
            _check_deadline(deadline)
            scan_count += 1
            positions.setdefault(row.ticker.upper(), row)

        quotes: dict[str, QuoteInput] = {}
        for row in inputs.quotes:
            _check_deadline(deadline)
            scan_count += 1
            quotes.setdefault(row.ticker.upper(), row)

        securities: dict[str, SecurityInput] = {}
        for row in inputs.securities:
            _check_deadline(deadline)
            scan_count += 1
            securities.setdefault(row.identity.ticker.upper(), row)

        position_caps: dict[str, int] = {}
        portfolio_values = [inputs.account.cash_usd]
        for ticker, row in positions.items():
            _check_deadline(deadline)
            try:
                valid = (
                    row.ticker == ticker
                    and row.sync_generation == inputs.source_generation
                    and row.as_of <= inputs.account.as_of
                    and row.shares.is_finite()
                    and row.shares > 0
                )
            except AttributeError, TypeError, ValueError:
                valid = False
            position_caps[ticker] = _whole_floor(row.shares) if valid else 0
            portfolio_values.append(row.market_value_usd)

        spread = objective_policy.estimated_spread_bps / Decimal(10000)
        sells: list[_SellOption] = []
        remaining_caps = dict(position_caps)
        for lot in inputs.lots:
            _check_deadline(deadline)
            scan_count += 1
            ticker = lot.ticker.upper()
            available = lot.available_shares
            valid = (
                lot.ticker == ticker
                and lot.sync_generation == inputs.source_generation
                and lot.as_of <= inputs.account.as_of
                and available.is_finite()
                and available > 0
            )
            if valid and _whole_floor(available) == 0:
                fractional_count += 1
                continue
            quote, security = quotes.get(ticker), securities.get(ticker)
            if (
                not valid
                or ticker not in positions
                or remaining_caps.get(ticker, 0) <= 0
                or quote is None
                or security is None
                or security.identity.ticker != ticker
                or security.tradable is not True
            ):
                ineligible_count += 1
                continue
            mark = _quote_mark(quote, inputs, ticker)
            quantity = min(_whole_floor(available), remaining_caps[ticker])
            price = exact_product(mark, Decimal(1) - spread) if mark is not None else Decimal(0)
            if quantity <= 0 or price <= 0:
                ineligible_count += 1
                continue
            sells.append(_SellOption(ticker, lot.broker_lot_id, quantity, price))
            remaining_caps[ticker] -= quantity

        allowed_tickers: list[str] = []
        seen_allowed: set[str] = set()
        for allowed in inputs.policy.allocation.allowed_securities:
            _check_deadline(deadline)
            scan_count += 1
            ticker = allowed.ticker.strip().upper()
            if allowed.enabled and ticker and ticker not in seen_allowed:
                seen_allowed.add(ticker)
                allowed_tickers.append(ticker)

        turnover_pct = inputs.policy.settings.get("max_batch_turnover_pct")
        settled = inputs.account.settled_buying_power_usd
        buy_capacity: Decimal | None = None
        if (
            isinstance(turnover_pct, Decimal)
            and turnover_pct.is_finite()
            and Decimal(0) <= turnover_pct <= Decimal(100)
            and settled.is_finite()
            and settled >= 0
            and all(value.is_finite() for value in portfolio_values)
        ):
            portfolio_value = exact_sum(portfolio_values)
            if portfolio_value > 0:
                buy_capacity = exact_sum(
                    (
                        settled,
                        exact_product(portfolio_value, turnover_pct / Decimal(100)),
                    )
                )

        prefer_etfs = inputs.policy.settings.get("prefer_etf_buys") is True
        buys: list[_BuyOption] = []
        for ticker in allowed_tickers:
            _check_deadline(deadline)
            quote, security = quotes.get(ticker), securities.get(ticker)
            if (
                quote is None
                or security is None
                or security.identity.ticker != ticker
                or security.tradable is not True
                or (
                    prefer_etfs
                    and security.identity.asset_type.upper() not in {"ETF", "MUTUAL_FUND"}
                )
                or buy_capacity is None
            ):
                continue
            mark = _quote_mark(quote, inputs, ticker)
            price = exact_product(mark, Decimal(1) + spread) if mark is not None else Decimal(0)
            shares = _whole_floor(buy_capacity / price) if price > 0 else 0
            if shares > 0:
                buys.append(_BuyOption(ticker, shares, price))

        sell_groups: dict[str, list[_SellOption]] = {}
        for option in sells:
            _check_deadline(deadline)
            sell_groups.setdefault(option.ticker, []).append(option)
        groups = {ticker: tuple(rows) for ticker, rows in sell_groups.items()}
        pool = _Pool(
            tuple(sells),
            tuple(buys),
            {(row.ticker, row.lot_id): row for row in sells},
            groups,
            {row.ticker: row for row in buys},
            position_caps,
            *limits,
            settled,
            scan_count,
            fractional_count,
            ineligible_count,
            True,
            "SELL: whole shares from 1 through each frozen lot's available/position capacity; "
            "BUY: whole shares from 1 through settled buying power plus the turnover ceiling",
        )
        return _PoolBuild(pool, objective_policy, False)
    except _DeadlineExpired:
        return _PoolBuild(
            _blank_pool(
                limits,
                scan_count=scan_count,
                fractional_count=fractional_count,
                other_count=ineligible_count,
            ),
            objective_policy,
            True,
        )


def _canonical_key(legs: tuple[ConsolidatedLeg, ...], deadline: float) -> tuple[object, ...]:
    rows = []
    for leg in legs:
        _check_deadline(deadline)
        allocations = []
        for lot in leg.selected_lots:
            _check_deadline(deadline)
            allocations.append((lot.broker_lot_id, lot.shares))
        rows.append(
            (
                leg.leg_id,
                leg.side,
                leg.ticker,
                leg.shares,
                leg.estimated_unit_price_usd,
                tuple(allocations),
                leg.depends_on_leg_ids,
                leg.sequence,
                leg.group_ids,
            )
        )
    return tuple(rows)


def _candidate_legs(
    pool: _Pool,
    policy: ObjectivePolicy,
    sells: dict[tuple[str, str], int],
    buys: dict[str, int],
    deadline: float,
) -> tuple[ConsolidatedLeg, ...] | None:
    if pool.max_sell_tickers is None or pool.max_sell_lots is None or pool.max_total_orders is None:
        return None
    by_ticker: dict[str, list[tuple[_SellOption, int]]] = {}
    totals: dict[str, int] = {}
    for key, quantity in sells.items():
        _check_deadline(deadline)
        option = pool.sells_by_key.get(key)
        if (
            option is None
            or isinstance(quantity, bool)
            or not isinstance(quantity, int)
            or quantity <= 0
            or quantity > option.max_shares
        ):
            return None
        by_ticker.setdefault(option.ticker, []).append((option, quantity))
        totals[option.ticker] = totals.get(option.ticker, 0) + quantity
    for ticker, quantity in totals.items():
        _check_deadline(deadline)
        if quantity > pool.position_caps.get(ticker, 0):
            return None
    if len(by_ticker) > pool.max_sell_tickers or len(sells) > pool.max_sell_lots:
        return None

    normalized_buys: dict[str, tuple[_BuyOption, int]] = {}
    for ticker, quantity in buys.items():
        _check_deadline(deadline)
        option = pool.buys_by_ticker.get(ticker)
        if (
            option is None
            or isinstance(quantity, bool)
            or not isinstance(quantity, int)
            or quantity <= 0
            or quantity > option.max_shares
            or ticker in by_ticker
        ):
            return None
        normalized_buys[ticker] = (option, quantity)
    if len(by_ticker) + len(normalized_buys) > pool.max_total_orders or not (
        by_ticker or normalized_buys
    ):
        return None

    sales: list[tuple[Decimal, str, tuple[tuple[_SellOption, int], ...]]] = []
    for ticker, actions in by_ticker.items():
        _check_deadline(deadline)
        ordered = tuple(sorted(actions, key=lambda row: row[0].lot_id))
        gross = exact_sum(exact_product(Decimal(qty), option.price) for option, qty in ordered)
        sales.append((exact_difference(gross, policy.estimated_fee_per_order_usd), ticker, ordered))
    sales.sort(key=lambda row: (-row[0], row[1]))
    sell_ids = tuple(f"sell:{ticker}" for _, ticker, _ in sales)
    legs: list[ConsolidatedLeg] = []
    for index, (_, ticker, actions) in enumerate(sales):
        _check_deadline(deadline)
        legs.append(
            ConsolidatedLeg(
                f"sell:{ticker}",
                "SELL",
                ticker,
                exact_sum(Decimal(qty) for _, qty in actions),
                actions[0][0].price,
                tuple(LotAllocation(option.lot_id, Decimal(qty)) for option, qty in actions),
                sequence=index,
                group_ids=(f"sale:{ticker}",),
            )
        )
    for index, (ticker, (option, quantity)) in enumerate(sorted(normalized_buys.items())):
        _check_deadline(deadline)
        legs.append(
            ConsolidatedLeg(
                f"buy:{ticker}",
                "BUY",
                ticker,
                Decimal(quantity),
                option.price,
                depends_on_leg_ids=sell_ids,
                sequence=len(sales) + index,
                group_ids=(f"buy:{ticker}",),
            )
        )
    return tuple(legs)


def _draw_sells(
    pool: _Pool, rng: random.Random, deadline: float, *, one_ticker: bool = False
) -> dict[tuple[str, str], int] | None:
    tickers = []
    for ticker in pool.sells_by_ticker:
        _check_deadline(deadline)
        tickers.append(ticker)
    if not tickers or pool.max_sell_tickers is None or pool.max_sell_lots is None:
        return None
    ticker_cap = min(pool.max_sell_tickers, pool.max_sell_lots, len(tickers))
    if pool.max_total_orders is not None:
        ticker_cap = min(ticker_cap, pool.max_total_orders)
    if ticker_cap < 1:
        return None
    count = 1 if one_ticker else rng.randint(1, ticker_cap)
    chosen_tickers = rng.sample(tickers, count)
    options = {}
    for ticker in chosen_tickers:
        _check_deadline(deadline)
        options[ticker] = pool.sells_by_ticker[ticker]
    available_lots = 0
    for rows in options.values():
        _check_deadline(deadline)
        available_lots += len(rows)
    lot_cap = min(pool.max_sell_lots, available_lots)
    if lot_cap < count:
        return None
    lot_count = rng.randint(count, lot_cap)
    chosen = []
    for rows in options.values():
        _check_deadline(deadline)
        chosen.append(rng.choice(rows))
    while len(chosen) < lot_count:
        remaining = []
        for rows in options.values():
            for row in rows:
                _check_deadline(deadline)
                if row not in chosen:
                    remaining.append(row)
        if not remaining:
            break
        chosen.append(rng.choice(remaining))
    actions: dict[tuple[str, str], int] = {}
    totals: dict[str, int] = {}
    for option in chosen:
        _check_deadline(deadline)
        cap = min(
            option.max_shares, pool.position_caps[option.ticker] - totals.get(option.ticker, 0)
        )
        if cap > 0:
            actions[(option.ticker, option.lot_id)] = rng.randint(1, cap)
            totals[option.ticker] = (
                totals.get(option.ticker, 0) + actions[(option.ticker, option.lot_id)]
            )
    return actions or None


def _draw_buys(
    pool: _Pool, rng: random.Random, deadline: float, excluded: set[str] | None = None
) -> dict[str, int] | None:
    if pool.max_total_orders is None:
        return None
    excluded_tickers = excluded or set()
    available = []
    for row in pool.buys:
        _check_deadline(deadline)
        if row.ticker not in excluded_tickers:
            available.append(row)
    count = min(pool.max_total_orders, len(available))
    if not count:
        return None
    selected = rng.sample(available, rng.randint(1, count))
    actions = {}
    for row in selected:
        _check_deadline(deadline)
        actions[row.ticker] = rng.randint(1, row.max_shares)
    return actions


def _random_basket(
    mode: str, pool: _Pool, policy: ObjectivePolicy, rng: random.Random, deadline: float
) -> tuple[ConsolidatedLeg, ...] | None:
    if mode == "coupled":
        if pool.max_total_orders is None or pool.max_total_orders < 2:
            return None
        sells = _draw_sells(pool, rng, deadline, one_ticker=True)
        if not sells:
            return None
        ticker = next(iter(sells))[0]
        options = []
        for row in pool.buys:
            _check_deadline(deadline)
            if row.ticker != ticker:
                options.append(row)
        if not options:
            return None
        buy = rng.choice(options)
        gross = Decimal(0)
        for key, quantity in sells.items():
            _check_deadline(deadline)
            gross = exact_sum(
                (gross, exact_product(Decimal(quantity), pool.sells_by_key[key].price))
            )
        fees = exact_product(policy.estimated_fee_per_order_usd, Decimal(2))
        funds = exact_difference(exact_sum((pool.settled_buying_power, gross)), fees)
        shares = min(buy.max_shares, _whole_floor(funds / buy.price)) if funds > 0 else 0
        return (
            _candidate_legs(pool, policy, sells, {buy.ticker: shares}, deadline) if shares else None
        )
    if mode == "sell_only":
        return _candidate_legs(pool, policy, _draw_sells(pool, rng, deadline) or {}, {}, deadline)
    if mode == "buy_only":
        return _candidate_legs(pool, policy, {}, _draw_buys(pool, rng, deadline) or {}, deadline)
    if mode == "random":
        return _random_basket(
            rng.choice(("coupled", "sell_only", "buy_only")), pool, policy, rng, deadline
        )
    return None


def _multi_lot_candidate(
    pool: _Pool, policy: ObjectivePolicy, deadline: float
) -> tuple[ConsolidatedLeg, ...] | None:
    for ticker, options in pool.sells_by_ticker.items():
        _check_deadline(deadline)
        selected = options[: min(len(options), pool.max_sell_lots or 0)]
        if len(selected) > 1:
            actions = {(ticker, option.lot_id): 1 for option in selected}
            return _candidate_legs(pool, policy, actions, {}, deadline)
    return None


def _incumbent_actions(
    legs: tuple[ConsolidatedLeg, ...], pool: _Pool, deadline: float
) -> tuple[dict[tuple[str, str], int], dict[str, int]] | None:
    sells: dict[tuple[str, str], int] = {}
    buys: dict[str, int] = {}
    for leg in legs:
        _check_deadline(deadline)
        if (
            not leg.shares.is_finite()
            or leg.shares <= 0
            or leg.shares != leg.shares.to_integral_value()
        ):
            return None
        if leg.side == "SELL":
            allocated = Decimal(0)
            if not leg.selected_lots or leg.depends_on_leg_ids:
                return None
            for lot in leg.selected_lots:
                _check_deadline(deadline)
                key = (leg.ticker.upper(), lot.broker_lot_id)
                option = pool.sells_by_key.get(key)
                if (
                    option is None
                    or key in sells
                    or not lot.shares.is_finite()
                    or lot.shares <= 0
                    or lot.shares != lot.shares.to_integral_value()
                    or lot.shares > option.max_shares
                ):
                    return None
                sells[key] = int(lot.shares)
                allocated += lot.shares
            if allocated != leg.shares:
                return None
        elif leg.side == "BUY":
            ticker = leg.ticker.upper()
            option = pool.buys_by_ticker.get(ticker)
            if (
                option is None
                or ticker in buys
                or leg.selected_lots
                or leg.shares > option.max_shares
            ):
                return None
            buys[ticker] = int(leg.shares)
        else:
            return None
    return sells, buys


def _local_neighbors(
    legs: tuple[ConsolidatedLeg, ...], pool: _Pool, policy: ObjectivePolicy, deadline: float
) -> Iterator[tuple[ConsolidatedLeg, ...]]:
    actions = _incumbent_actions(legs, pool, deadline)
    if actions is None:
        return
    base_sells, base_buys = actions
    for key, quantity in base_sells.items():
        _check_deadline(deadline)
        option = pool.sells_by_key[key]
        for changed_quantity in (quantity - 1, quantity + 1):
            if 0 < changed_quantity <= option.max_shares:
                changed = dict(base_sells)
                changed[key] = changed_quantity
                candidate = _candidate_legs(pool, policy, changed, dict(base_buys), deadline)
                if candidate is not None:
                    yield candidate
        if quantity == 1:
            changed = dict(base_sells)
            del changed[key]
            candidate = _candidate_legs(pool, policy, changed, dict(base_buys), deadline)
            if candidate is not None:
                yield candidate
    for ticker, quantity in base_buys.items():
        _check_deadline(deadline)
        option = pool.buys_by_ticker[ticker]
        for changed_quantity in (quantity - 1, quantity + 1):
            if 0 < changed_quantity <= option.max_shares:
                changed = dict(base_buys)
                changed[ticker] = changed_quantity
                candidate = _candidate_legs(pool, policy, dict(base_sells), changed, deadline)
                if candidate is not None:
                    yield candidate
        if quantity == 1:
            changed = dict(base_buys)
            del changed[ticker]
            candidate = _candidate_legs(pool, policy, dict(base_sells), changed, deadline)
            if candidate is not None:
                yield candidate
    existing_sells = set(base_sells)
    for option in pool.sells:
        _check_deadline(deadline)
        key = (option.ticker, option.lot_id)
        if key not in existing_sells:
            candidate = _candidate_legs(
                pool, policy, {**base_sells, key: 1}, dict(base_buys), deadline
            )
            if candidate is not None:
                yield candidate
    for option in pool.buys:
        _check_deadline(deadline)
        if option.ticker not in base_buys:
            candidate = _candidate_legs(
                pool, policy, dict(base_sells), {**base_buys, option.ticker: 1}, deadline
            )
            if candidate is not None:
                yield candidate


def _assess(
    legs: tuple[ConsolidatedLeg, ...], validation: CandidateValidation, deadline: float
) -> CandidateAssessment:
    completed = "validation_deadline_exceeded" not in validation.reasons and monotonic() < deadline
    reasons = validation.reasons
    if not completed and "validation_deadline_exceeded" not in reasons:
        reasons = (*reasons, "validation_deadline_exceeded")
    accepted = completed and validation.accepted and validation.objective_value is not None
    evaluation = validation.evaluation
    return CandidateAssessment(
        legs,
        completed,
        accepted,
        reasons[:12],
        validation.objective_value if accepted else None,
        validation.estimated_tax_benefit_usd if completed else None,
        validation.estimated_trading_cost_usd if completed else None,
        evaluation.proposed.cash_usd if completed and evaluation is not None else None,
    )


def _unrun(legs: tuple[ConsolidatedLeg, ...], reason: str) -> CandidateAssessment:
    return CandidateAssessment(legs, False, False, (reason,), None, None, None, None)


def search_representative_best_known(
    inputs: FinancialInputs,
    incumbent_legs: tuple[ConsolidatedLeg, ...],
    *,
    seed: int,
    max_candidate_count: int,
    time_limit_seconds: float,
) -> RepresentativeSearchResult:
    """Search a seeded, finite candidate stream; never claim exhaustion or an optimum.

    The exact incumbent and no-trade basket consume candidate budget and are owner-revalidated before
    pool exploration. An incumbent is not clipped to the generated pool and remains eligible if pool
    generation hits its time limit. Duplicate generated candidates consume proposals, not validations.
    """
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError("seed must be an integer")
    if isinstance(max_candidate_count, bool) or not isinstance(max_candidate_count, int):
        raise TypeError("max_candidate_count must be an integer")
    if max_candidate_count < 1:
        raise ValueError("max_candidate_count must be positive")
    if isinstance(time_limit_seconds, bool) or not isinstance(time_limit_seconds, (int, float)):
        raise TypeError("time_limit_seconds must be a number")
    if not math.isfinite(time_limit_seconds) or time_limit_seconds <= 0:
        raise ValueError("time_limit_seconds must be finite and positive")
    if not isinstance(incumbent_legs, tuple):
        raise TypeError("incumbent_legs must be a tuple of canonical legs")
    if incumbent_legs and max_candidate_count < 2:
        raise ValueError("max_candidate_count must allow both incumbent and no-trade validation")

    started = monotonic()
    deadline = started + float(time_limit_seconds)
    checksum = (
        inputs.source_checksum
        if isinstance(inputs.source_checksum, str) and inputs.source_checksum
        else None
    )
    checksum_source = "frozen_source_checksum" if checksum is not None else "unavailable"
    proposals = validations = unique = feasible_count = steps = 0
    mode_counts = dict.fromkeys(_MODES, 0)
    seen: set[tuple[object, ...]] = set()
    traces: dict[str, CandidateTrace] = {}
    best: CandidateAssessment | None = None
    best_score: Decimal | None = None

    def consider(legs: tuple[ConsolidatedLeg, ...], source: str) -> CandidateAssessment | None:
        nonlocal proposals, validations, unique, feasible_count, best, best_score
        if proposals >= max_candidate_count:
            return None
        proposals += 1
        try:
            key = _canonical_key(legs, deadline)
        except _DeadlineExpired:
            assessment = _unrun(legs, "validation_deadline_exceeded")
            traces.setdefault(
                source,
                CandidateTrace(
                    proposals, source, legs, False, False, None, None, assessment.reasons
                ),
            )
            return assessment
        if key in seen:
            return None
        seen.add(key)
        unique += 1
        if monotonic() >= deadline:
            assessment = _unrun(legs, "validation_deadline_exceeded")
        else:
            validations += 1
            assessment = _assess(
                legs, validate_candidate(inputs, legs, deadline=deadline), deadline
            )
        if assessment.feasible:
            feasible_count += 1
            score = assessment.objective_value
            if score is not None and (best_score is None or score < best_score):
                best, best_score = assessment, score
        old_trace = traces.get(source)
        if old_trace is None or (assessment.feasible and not old_trace.feasible):
            traces[source] = CandidateTrace(
                proposals,
                source,
                legs,
                assessment.validation_completed,
                assessment.feasible,
                assessment.objective_value,
                assessment.estimated_trading_cost_usd,
                assessment.reasons[:5],
            )
        return assessment

    incumbent = consider(incumbent_legs, "production_incumbent")
    if incumbent is None:
        incumbent = _unrun(incumbent_legs, "candidate_budget_exhausted")
    if not incumbent_legs:
        no_trade = incumbent
    elif proposals < max_candidate_count:
        no_trade = consider((), "no_trade") or _unrun((), "candidate_budget_exhausted")
    else:
        no_trade = _unrun((), "candidate_budget_exhausted")

    built = _PoolBuild(_blank_pool(), None, False)
    if monotonic() < deadline and proposals < max_candidate_count:
        built = _build_pool(inputs, deadline)
    pool = built.pool
    if monotonic() >= deadline or built.deadline_hit:
        stop: StopReason = "deadline"
    elif proposals >= max_candidate_count:
        stop = "candidate_budget"
    elif built.objective_policy is None or not pool.complete or not (pool.sells or pool.buys):
        stop = "pool_unavailable"
    else:
        rng = random.Random(seed)
        local = iter(_local_neighbors(incumbent_legs, pool, built.objective_policy, deadline))
        stop = "generation_budget"
        mode_index = 0
        while proposals < max_candidate_count and steps < max_candidate_count:
            if monotonic() >= deadline:
                stop = "deadline"
                break
            mode = _MODES[mode_index % len(_MODES)]
            mode_index += 1
            steps += 1
            mode_counts[mode] += 1
            try:
                if mode == "coupled":
                    legs = _random_basket(mode, pool, built.objective_policy, rng, deadline)
                elif mode == "multi_lot_sell":
                    legs = _multi_lot_candidate(pool, built.objective_policy, deadline)
                elif mode == "local":
                    legs = next(local, None)
                else:
                    legs = _random_basket(mode, pool, built.objective_policy, rng, deadline)
            except _DeadlineExpired:
                stop = "deadline"
                break
            if legs is not None:
                if monotonic() >= deadline:
                    stop = "deadline"
                    break
                consider(legs, mode)
        else:
            if proposals >= max_candidate_count:
                stop = "candidate_budget"

    if monotonic() >= deadline:
        stop = "deadline"
    metadata_within_budget = monotonic() < deadline
    if not metadata_within_budget:
        stop = "deadline"
    return RepresentativeSearchResult(
        seed=seed,
        input_checksum=checksum,
        input_checksum_source=checksum_source,
        candidate_budget=max_candidate_count,
        time_budget_seconds=float(time_limit_seconds),
        elapsed_seconds=monotonic() - started,
        candidate_proposal_count=proposals,
        validation_attempt_count=validations,
        unique_candidate_count=unique,
        feasible_candidate_count=feasible_count,
        generation_step_count=steps,
        generation_mode_attempts=tuple((mode, mode_counts[mode]) for mode in _MODES),
        stop_reason=stop,
        search_complete=False,
        global_optimality_proven=False,
        pool_complete=pool.complete,
        pool_scan_count=pool.scan_count,
        sell_lot_option_count=len(pool.sells),
        sell_ticker_count=len(pool.sells_by_ticker),
        buy_ticker_option_count=len(pool.buys),
        fractional_only_lots_skipped=pool.fractional_lots_skipped,
        other_ineligible_lots_skipped=pool.other_lots_skipped,
        batch_limits=(
            ("max_sell_tickers_per_batch", pool.max_sell_tickers),
            ("max_sell_lots_per_batch", pool.max_sell_lots),
            ("max_total_orders_per_batch", pool.max_total_orders),
        ),
        quantity_domain=pool.quantity_domain,
        incumbent_assessment=incumbent,
        no_trade_assessment=no_trade,
        best_known=best,
        candidate_trace=tuple(traces.values()),
        metadata_within_time_budget=metadata_within_budget,
    )
