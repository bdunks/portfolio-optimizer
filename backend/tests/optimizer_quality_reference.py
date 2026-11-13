"""Exact bounded basket enumeration for tiny offline quality-reference cases.

This module deliberately uses enumeration, never the production screen/solver/repair search. Each
canonical basket is passed to the owner validator for feasibility and its exact Decimal score. The
result is exact only over the explicitly supplied finite universe and only when ``complete`` is true.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal
from time import monotonic
from typing import Literal

from app.domain.financial_inputs import FinancialInputs, LotInput
from app.domain.portfolio_accounting import ConsolidatedLeg, LotAllocation
from app.optimizer.validation import CandidateValidation, read_objective_policy, validate_candidate

StopReason = Literal["exhausted", "max_assignments", "deadline"]


@dataclass(frozen=True, slots=True)
class SellLotBound:
    """Include zero through ``max_shares`` whole shares of one named broker lot."""

    ticker: str
    broker_lot_id: str
    max_shares: int


@dataclass(frozen=True, slots=True)
class BuyTickerBound:
    """Include zero through ``max_shares`` whole shares of one named ticker."""

    ticker: str
    max_shares: int


@dataclass(frozen=True, slots=True)
class CandidateUniverse:
    """Caller-supplied finite dimensions; no ticker, quantity, or policy defaults are added."""

    sells: tuple[SellLotBound, ...] = ()
    buys: tuple[BuyTickerBound, ...] = ()


@dataclass(frozen=True, slots=True)
class ReferenceCandidate:
    legs: tuple[ConsolidatedLeg, ...]
    validation: CandidateValidation
    validation_completed: bool

    @property
    def feasible(self) -> bool:
        return (
            self.validation_completed
            and self.validation.accepted
            and self.validation.objective_value is not None
        )


@dataclass(frozen=True, slots=True)
class SmallCaseSearchResult:
    """Bounded search evidence; ``best_observed`` is not an optimum unless ``complete`` is true."""

    complete: bool
    stop_reason: StopReason
    theoretical_assignment_count: int
    assignments_examined: int
    canonical_baskets_examined: int
    feasible_basket_count: int
    max_assignments: int
    time_limit_seconds: float
    elapsed_seconds: float
    incumbent: ReferenceCandidate
    candidates: tuple[ReferenceCandidate, ...]
    best_observed: ReferenceCandidate | None

    @property
    def exact_optimum(self) -> ReferenceCandidate | None:
        """Return a proven finite-universe optimum, never a best-known result after cutoff."""
        return self.best_observed if self.complete else None


def _validate_universe(
    inputs: FinancialInputs, universe: CandidateUniverse
) -> tuple[tuple[SellLotBound, ...], tuple[BuyTickerBound, ...]]:
    lots: dict[str, LotInput] = {lot.broker_lot_id: lot for lot in inputs.lots}
    positions = {position.ticker.upper(): position for position in inputs.positions}
    sells: list[SellLotBound] = []
    seen_lots: set[str] = set()
    maximum_by_ticker: dict[str, Decimal] = {}
    for bound in universe.sells:
        ticker = bound.ticker.strip().upper()
        if not ticker or not bound.broker_lot_id or bound.broker_lot_id in seen_lots:
            raise ValueError("sell bounds need a ticker and unique broker lot IDs")
        _require_quote_mark(inputs, ticker)
        if isinstance(bound.max_shares, bool) or not isinstance(bound.max_shares, int):
            raise TypeError("sell bounds must use integer whole-share maxima")
        if bound.max_shares <= 0:
            raise ValueError("sell bounds must allow at least one whole share")
        lot = lots.get(bound.broker_lot_id)
        if lot is None or lot.ticker.upper() != ticker:
            raise ValueError(f"sell bound does not identify a frozen lot for {ticker}")
        if not lot.available_shares.is_finite() or lot.available_shares < 0:
            raise ValueError(f"sell bound has invalid available shares for {bound.broker_lot_id}")
        available_whole_shares = int(lot.available_shares.to_integral_value(rounding=ROUND_FLOOR))
        if bound.max_shares > available_whole_shares:
            raise ValueError(f"sell bound exceeds whole available shares for {bound.broker_lot_id}")
        if ticker not in positions:
            raise ValueError(f"sell bound has no frozen position for {ticker}")
        seen_lots.add(bound.broker_lot_id)
        maximum_by_ticker[ticker] = maximum_by_ticker.get(ticker, Decimal(0)) + Decimal(
            bound.max_shares
        )
        sells.append(SellLotBound(ticker, bound.broker_lot_id, bound.max_shares))
    for ticker, maximum in maximum_by_ticker.items():
        if maximum > positions[ticker].shares:
            raise ValueError(f"combined sell bounds exceed frozen position shares for {ticker}")

    buys: list[BuyTickerBound] = []
    seen_buy_tickers: set[str] = set()
    for bound in universe.buys:
        ticker = bound.ticker.strip().upper()
        if not ticker:
            raise ValueError("buy bounds need a ticker")
        _require_quote_mark(inputs, ticker)
        if isinstance(bound.max_shares, bool) or not isinstance(bound.max_shares, int):
            raise TypeError("buy bounds must use integer whole-share maxima")
        if bound.max_shares <= 0:
            raise ValueError("buy bounds must allow at least one whole share")
        if ticker in seen_buy_tickers:
            raise ValueError(f"buy bounds repeat ticker {ticker}")
        seen_buy_tickers.add(ticker)
        buys.append(BuyTickerBound(ticker, bound.max_shares))
    return (
        tuple(sorted(sells, key=lambda row: (row.ticker, row.broker_lot_id))),
        tuple(sorted(buys, key=lambda row: row.ticker)),
    )


def _quote_mark(inputs: FinancialInputs, ticker: str) -> Decimal | None:
    quote = inputs.quote_for(ticker)
    if quote is None:
        return None
    if quote.bid_usd is not None and quote.ask_usd is not None:
        if quote.bid_usd > 0 and quote.ask_usd > 0 and quote.bid_usd <= quote.ask_usd:
            return (quote.bid_usd + quote.ask_usd) / Decimal(2)
    elif quote.last_usd is not None and quote.last_usd > 0:
        return quote.last_usd
    elif quote.bid_usd is not None and quote.bid_usd > 0:
        return quote.bid_usd
    elif quote.ask_usd is not None and quote.ask_usd > 0:
        return quote.ask_usd
    return None


def _require_quote_mark(inputs: FinancialInputs, ticker: str) -> Decimal:
    quote_mark = _quote_mark(inputs, ticker)
    if quote_mark is None:
        raise ValueError(f"candidate bound has no usable frozen quote for {ticker}")
    return quote_mark


def _canonical_key(legs: tuple[ConsolidatedLeg, ...]) -> tuple[object, ...]:
    return tuple(
        (
            leg.side,
            leg.ticker,
            leg.shares,
            leg.estimated_unit_price_usd,
            tuple(
                (allocation.broker_lot_id, allocation.shares) for allocation in leg.selected_lots
            ),
            leg.depends_on_leg_ids,
            leg.sequence,
        )
        for leg in legs
    )


def _build_legs(
    inputs: FinancialInputs,
    sells: tuple[SellLotBound, ...],
    buys: tuple[BuyTickerBound, ...],
    quantities: tuple[int, ...],
    spread_bps: Decimal,
) -> tuple[ConsolidatedLeg, ...]:
    sell_quantities = quantities[: len(sells)]
    buy_quantities = quantities[len(sells) :]
    allocations_by_ticker: dict[str, list[LotAllocation]] = {}
    for bound, quantity in zip(sells, sell_quantities, strict=True):
        if quantity:
            allocations_by_ticker.setdefault(bound.ticker, []).append(
                LotAllocation(bound.broker_lot_id, Decimal(quantity))
            )

    sell_tickers = sorted(allocations_by_ticker)
    sell_ids = tuple(f"sell:{ticker}" for ticker in sell_tickers)
    legs: list[ConsolidatedLeg] = []
    half_spread = spread_bps / Decimal(10000)
    for sequence, ticker in enumerate(sell_tickers):
        allocations = tuple(
            sorted(allocations_by_ticker[ticker], key=lambda allocation: allocation.broker_lot_id)
        )
        quote_mark = _require_quote_mark(inputs, ticker)
        price = quote_mark * (Decimal(1) - half_spread)
        legs.append(
            ConsolidatedLeg(
                leg_id=f"sell:{ticker}",
                side="SELL",
                ticker=ticker,
                shares=sum((allocation.shares for allocation in allocations), Decimal(0)),
                estimated_unit_price_usd=price,
                selected_lots=allocations,
                sequence=sequence,
                group_ids=(f"sale:{ticker}",),
            )
        )

    for index, (bound, quantity) in enumerate(zip(buys, buy_quantities, strict=True)):
        if not quantity:
            continue
        quote_mark = _require_quote_mark(inputs, bound.ticker)
        price = quote_mark * (Decimal(1) + half_spread)
        legs.append(
            ConsolidatedLeg(
                leg_id=f"buy:{bound.ticker}",
                side="BUY",
                ticker=bound.ticker,
                shares=Decimal(quantity),
                estimated_unit_price_usd=price,
                depends_on_leg_ids=sell_ids,
                sequence=len(sell_tickers) + index,
                group_ids=(f"buy:{bound.ticker}",),
            )
        )
    return tuple(legs)


def _assignment_vectors(maxima: tuple[int, ...]) -> Iterator[tuple[int, ...]]:
    """Yield the Cartesian space in stable mixed-radix order using O(dimensions) memory."""
    digits = [0] * len(maxima)
    while True:
        yield tuple(digits)
        for index in range(len(digits) - 1, -1, -1):
            if digits[index] < maxima[index]:
                digits[index] += 1
                break
            digits[index] = 0
        else:
            return


def enumerate_small_case(
    inputs: FinancialInputs,
    universe: CandidateUniverse,
    *,
    max_assignments: int,
    time_limit_seconds: float,
    incumbent_legs: tuple[ConsolidatedLeg, ...] = (),
) -> SmallCaseSearchResult:
    """Enumerate a bounded explicit whole-share universe and owner-validate every basket.

    ``max_assignments`` bounds candidate storage and work; ``time_limit_seconds`` is a shared
    deadline for the incumbent check and enumeration. If either stops the traversal, ``complete``
    is false and ``exact_optimum`` intentionally returns ``None``.
    """
    if isinstance(max_assignments, bool) or not isinstance(max_assignments, int):
        raise TypeError("max_assignments must be an integer")
    if max_assignments < 1:
        raise ValueError("max_assignments must be positive")
    if isinstance(time_limit_seconds, bool):
        raise TypeError("time_limit_seconds must be a number")
    if not math.isfinite(time_limit_seconds) or time_limit_seconds <= 0:
        raise ValueError("time_limit_seconds must be finite and positive")
    sells, buys = _validate_universe(inputs, universe)
    maxima = tuple(bound.max_shares for bound in (*sells, *buys))
    theoretical_count = math.prod(maximum + 1 for maximum in maxima)
    started = monotonic()
    deadline = started + time_limit_seconds

    objective_policy, _ = read_objective_policy(inputs)
    spread_bps = (
        objective_policy.estimated_spread_bps if objective_policy is not None else Decimal(0)
    )
    incumbent_validation = validate_candidate(inputs, incumbent_legs, deadline=deadline)
    incumbent_completed = (
        "validation_deadline_exceeded" not in incumbent_validation.reasons
        and monotonic() < deadline
    )
    incumbent = ReferenceCandidate(tuple(incumbent_legs), incumbent_validation, incumbent_completed)

    candidates: list[ReferenceCandidate] = []
    feasible_count = 0
    best_observed: ReferenceCandidate | None = None
    best_score: Decimal | None = None
    seen: set[tuple[object, ...]] = set()
    assignments_examined = 0
    stop_reason: StopReason = "exhausted"
    if not incumbent_completed or monotonic() >= deadline:
        stop_reason = "deadline"
    else:
        for quantities in _assignment_vectors(maxima):
            if monotonic() >= deadline:
                stop_reason = "deadline"
                break
            if assignments_examined >= max_assignments:
                stop_reason = "max_assignments"
                break
            assignments_examined += 1
            legs = _build_legs(inputs, sells, buys, quantities, spread_bps)
            key = _canonical_key(legs)
            if key in seen:
                continue
            seen.add(key)
            validation = validate_candidate(inputs, legs, deadline=deadline)
            completed = (
                "validation_deadline_exceeded" not in validation.reasons and monotonic() < deadline
            )
            candidate = ReferenceCandidate(legs, validation, completed)
            candidates.append(candidate)
            if candidate.feasible:
                feasible_count += 1
                score = validation.objective_value
                if score is not None and (best_score is None or score < best_score):
                    best_observed = candidate
                    best_score = score
            if not completed:
                stop_reason = "deadline"
                break
        else:
            stop_reason = "exhausted"
        if stop_reason == "exhausted" and assignments_examined < theoretical_count:
            stop_reason = "max_assignments"

    if stop_reason == "exhausted" and monotonic() >= deadline:
        stop_reason = "deadline"
    complete = stop_reason == "exhausted" and assignments_examined == theoretical_count
    return SmallCaseSearchResult(
        complete=complete,
        stop_reason=stop_reason,
        theoretical_assignment_count=theoretical_count,
        assignments_examined=assignments_examined,
        canonical_baskets_examined=len(candidates),
        feasible_basket_count=feasible_count,
        max_assignments=max_assignments,
        time_limit_seconds=time_limit_seconds,
        elapsed_seconds=monotonic() - started,
        incumbent=incumbent,
        candidates=tuple(candidates),
        best_observed=best_observed,
    )
