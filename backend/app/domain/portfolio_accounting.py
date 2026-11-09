"""Pure, independently recomputed account and sleeve effects for a consolidated basket.

The input is the frozen account/policy state plus canonical run-level legs. No solver totals,
web framework, persistence, or broker state are accepted by this module.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Literal, cast

from app.domain.allocation import (
    AllocationPolicy,
    SleeveAssignment,
    accumulate_sleeve_value,
    assignment_path,
    resolve_cash,
    resolve_holding,
    transition_progress,
)
from app.domain.decimal_math import (
    exact_difference,
    exact_percent_product,
    exact_product,
    exact_sum,
    percentage,
)
from app.domain.financial_inputs import FinancialInputs, LotInput, PositionInput
from app.domain.trade_dates import classify_holding_period

LegSide = Literal["BUY", "SELL"]


@dataclass(frozen=True, slots=True)
class LotAllocation:
    broker_lot_id: str
    shares: Decimal


@dataclass(frozen=True, slots=True)
class ConsolidatedLeg:
    """One executable ticker leg; SELL lots and BUY funding dependencies are explicit."""

    leg_id: str
    side: LegSide
    ticker: str
    shares: Decimal
    estimated_unit_price_usd: Decimal
    selected_lots: tuple[LotAllocation, ...] = ()
    depends_on_leg_ids: tuple[str, ...] = ()
    sequence: int = 0
    group_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PositionBalance:
    ticker: str
    asset_type: str
    shares: Decimal
    market_value_usd: Decimal
    assignment: SleeveAssignment | None


@dataclass(frozen=True, slots=True)
class LotBalance:
    ticker: str
    broker_lot_id: str
    shares: Decimal
    available_shares: Decimal


@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    cash_usd: Decimal
    portfolio_total_usd: Decimal
    positions: tuple[PositionBalance, ...]
    lots: tuple[LotBalance, ...]
    sleeve_values_usd: tuple[tuple[str, Decimal], ...]
    sleeve_weights_pct: tuple[tuple[str, Decimal], ...]


@dataclass(frozen=True, slots=True)
class PositionEffect:
    ticker: str
    shares_before: Decimal
    shares_after: Decimal
    market_value_before_usd: Decimal
    market_value_after_usd: Decimal
    position_exited: bool


@dataclass(frozen=True, slots=True)
class LotEffect:
    ticker: str
    broker_lot_id: str
    shares_before: Decimal
    shares_sold: Decimal
    shares_after: Decimal
    available_shares_before: Decimal
    available_shares_after: Decimal
    realized_pl_usd: Decimal
    term: Literal["ST", "LT"]
    lot_closed: bool


@dataclass(frozen=True, slots=True)
class SleeveTarget:
    sleeve_key: str
    target_within_parent_pct: Decimal
    target_whole_portfolio_pct: Decimal


@dataclass(frozen=True, slots=True)
class AllocationTarget:
    top_level_sleeve_weights_pct: tuple[tuple[str, Decimal], ...]
    sleeves: tuple[SleeveTarget, ...]


@dataclass(frozen=True, slots=True)
class AllocationEvaluation:
    current: AccountSnapshot
    proposed: AccountSnapshot
    target: AllocationTarget


@dataclass(frozen=True, slots=True)
class TransitionChild:
    value_usd: Decimal
    within_us_sleeve_pct: Decimal
    whole_portfolio_pct: Decimal


@dataclass(frozen=True, slots=True)
class TransitionSnapshot:
    us_sleeve_value_usd: Decimal
    us_sleeve_whole_portfolio_pct: Decimal
    etf_progress_pct: Decimal | None
    children: tuple[tuple[str, TransitionChild], ...]


@dataclass(frozen=True, slots=True)
class TransitionTargetChild:
    within_us_sleeve_pct: Decimal
    whole_portfolio_pct: Decimal


@dataclass(frozen=True, slots=True)
class TransitionTarget:
    us_sleeve_whole_portfolio_pct: Decimal
    children: tuple[tuple[str, TransitionTargetChild], ...]


@dataclass(frozen=True, slots=True)
class TransitionEvaluation:
    sleeve_key: str
    destination_sleeve_key: str | None
    current: TransitionSnapshot
    proposed_basket: TransitionSnapshot
    target: TransitionTarget


@dataclass(frozen=True, slots=True)
class PortfolioEvaluation:
    """Current and independently calculated proposed portfolio plus auditable deltas."""

    current: AccountSnapshot
    proposed: AccountSnapshot
    allocation: AllocationEvaluation
    transition: TransitionEvaluation | None
    position_effects: tuple[PositionEffect, ...]
    lot_effects: tuple[LotEffect, ...]
    position_count_before: int
    position_count_after: int
    lot_count_before: int
    lot_count_after: int
    selected_lots_count: int
    sell_proceeds_usd: Decimal
    realized_st_usd: Decimal
    realized_lt_usd: Decimal


class BasketValidationError(ValueError):
    """A structurally inconsistent or independently infeasible proposed basket."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _invalid(code: str, message: str) -> BasketValidationError:
    return BasketValidationError(code, message)


def _proportional_amount(total: Decimal, part: Decimal, whole: Decimal) -> Decimal:
    if part == 0 or total == 0:
        return Decimal(0)
    if part == whole:
        return total
    precision = max(
        80,
        len(total.as_tuple().digits) + len(part.as_tuple().digits) + len(whole.as_tuple().digits) + 16,
    )
    with localcontext() as context:
        context.prec = precision
        return exact_product(total, part) / whole


def _normalized_legs(legs: Sequence[ConsolidatedLeg]) -> tuple[ConsolidatedLeg, ...]:
    if len({leg.leg_id for leg in legs}) != len(legs) or any(not leg.leg_id for leg in legs):
        raise _invalid("duplicate_or_empty_leg_id", "Consolidated leg IDs must be nonempty and unique")
    by_id = {leg.leg_id: leg for leg in legs}
    seen_tickers: set[tuple[str, str]] = set()
    sides_by_ticker: dict[str, set[str]] = {}
    for leg in legs:
        ticker = leg.ticker.strip().upper()
        if not ticker or leg.side not in ("BUY", "SELL"):
            raise _invalid("invalid_leg", "Every consolidated leg needs a ticker and BUY or SELL side")
        if not leg.shares.is_finite() or leg.shares <= 0:
            raise _invalid("invalid_leg_shares", f"{leg.leg_id} shares must be positive and finite")
        if not leg.estimated_unit_price_usd.is_finite() or leg.estimated_unit_price_usd <= 0:
            raise _invalid("invalid_leg_price", f"{leg.leg_id} unit price must be positive and finite")
        if leg.sequence < 0:
            raise _invalid("invalid_leg_sequence", f"{leg.leg_id} sequence cannot be negative")
        side_ticker = (leg.side, ticker)
        if side_ticker in seen_tickers:
            raise _invalid("unconsolidated_ticker_legs", f"{leg.side} legs for {ticker} must be consolidated")
        seen_tickers.add(side_ticker)
        sides_by_ticker.setdefault(ticker, set()).add(leg.side)
        if len(set(leg.group_ids)) != len(leg.group_ids):
            raise _invalid("duplicate_leg_group", f"{leg.leg_id} group references must be unique")
        if leg.side == "BUY":
            if leg.selected_lots:
                raise _invalid("buy_has_lot_allocations", f"BUY leg {leg.leg_id} cannot allocate broker lots")
            if leg.shares != leg.shares.to_integral_value():
                raise _invalid("fractional_buy_shares", f"BUY leg {leg.leg_id} must use whole shares")
        elif leg.depends_on_leg_ids:
            raise _invalid("sell_has_funding_dependencies", f"SELL leg {leg.leg_id} cannot depend on funding legs")
        if len({allocation.broker_lot_id for allocation in leg.selected_lots}) != len(leg.selected_lots):
            raise _invalid("duplicate_lot_allocation", f"SELL leg {leg.leg_id} repeats a broker lot ID")
        if len(set(leg.depends_on_leg_ids)) != len(leg.depends_on_leg_ids):
            raise _invalid("duplicate_funding_dependency", f"BUY leg {leg.leg_id} repeats a dependency")

    for ticker, sides in sides_by_ticker.items():
        if len(sides) > 1:
            raise _invalid("buy_sell_same_ticker", f"A basket cannot both buy and sell {ticker}")

    for leg in legs:
        if leg.side != "BUY":
            continue
        for dependency_id in leg.depends_on_leg_ids:
            dependency = by_id.get(dependency_id)
            if dependency is None or dependency.side != "SELL":
                raise _invalid(
                    "invalid_funding_dependency",
                    f"BUY leg {leg.leg_id} must depend only on included SELL leg IDs",
                )
            if dependency.sequence >= leg.sequence:
                raise _invalid(
                    "funding_dependency_not_prior",
                    f"Funding SELL {dependency_id} must precede BUY leg {leg.leg_id}",
                )
    return tuple(legs)


def _assignment_path(policy: AllocationPolicy, assignment: SleeveAssignment | None, ticker: str) -> tuple[str, ...]:
    if assignment is None:
        raise _invalid("unassigned_holding", f"Held security {ticker} has no policy sleeve assignment")
    path = assignment_path(policy, assignment.sleeve_key, assignment.sub_sleeve_key)
    if path is None:
        raise _invalid("invalid_holding_assignment", f"Held security {ticker} has invalid or disabled sleeve ancestry")
    return path


def _snapshot(
    policy: AllocationPolicy,
    positions: Mapping[str, PositionBalance],
    lots: Mapping[str, LotBalance],
    cash_usd: Decimal,
) -> AccountSnapshot:
    position_values = [position.market_value_usd for position in positions.values()]
    portfolio_total = exact_sum((*position_values, cash_usd))
    sleeve_values: dict[str, Decimal] = {}
    for position in positions.values():
        if position.assignment is not None:
            path = _assignment_path(policy, position.assignment, position.ticker)
            accumulate_sleeve_value(sleeve_values, path, position.market_value_usd)
    cash_resolution = resolve_cash(policy)
    if cash_resolution.assignment is not None:
        cash_path = assignment_path(
            policy, cash_resolution.assignment.sleeve_key, cash_resolution.assignment.sub_sleeve_key
        )
        if cash_path is None:
            raise _invalid("invalid_cash_assignment", "Configured cash sleeve has invalid or disabled ancestry")
        accumulate_sleeve_value(sleeve_values, cash_path, cash_usd)
    elif cash_resolution.reason not in ("cash_sleeve_not_configured",):
        raise _invalid("invalid_cash_assignment", "Configured cash sleeve is ambiguous or invalid")

    enabled = [sleeve for sleeve in policy.sleeves if sleeve.enabled]
    top_level = sorted(
        (sleeve for sleeve in enabled if sleeve.parent_key is None),
        key=lambda sleeve: (sleeve.sort_order, sleeve.key),
    )
    all_weights = tuple(
        (sleeve.key, percentage(sleeve_values.get(sleeve.key, Decimal(0)), portfolio_total))
        for sleeve in sorted(enabled, key=lambda item: (item.sort_order, item.key))
    )
    top_weights = tuple(
        (sleeve.key, percentage(sleeve_values.get(sleeve.key, Decimal(0)), portfolio_total))
        for sleeve in top_level
    )
    return AccountSnapshot(
        cash_usd=cash_usd,
        portfolio_total_usd=portfolio_total,
        positions=tuple(sorted(positions.values(), key=lambda item: item.ticker)),
        lots=tuple(sorted(lots.values(), key=lambda item: (item.ticker, item.broker_lot_id))),
        sleeve_values_usd=tuple(
            (sleeve.key, sleeve_values.get(sleeve.key, Decimal(0)))
            for sleeve in sorted(enabled, key=lambda item: (item.sort_order, item.key))
        ),
        sleeve_weights_pct=top_weights if top_weights else all_weights,
    )


def _allocation_target(policy: AllocationPolicy) -> AllocationTarget:
    enabled = {sleeve.key: sleeve for sleeve in policy.sleeves if sleeve.enabled}
    for sleeve in enabled.values():
        if assignment_path(policy, sleeve.key) is None:
            raise _invalid("invalid_policy_tree", f"Enabled sleeve {sleeve.key} has missing, disabled, or cyclic ancestry")
    children: dict[str | None, list[str]] = {}
    for sleeve in enabled.values():
        children.setdefault(sleeve.parent_key, []).append(sleeve.key)
    for child_keys in children.values():
        child_keys.sort(key=lambda key: (enabled[key].sort_order, key))

    target_rows: dict[str, SleeveTarget] = {}
    pending = list(children.get(None, []))
    while pending:
        key = pending.pop(0)
        sleeve = enabled[key]
        target = sleeve.target_pct or Decimal(0)
        parent = enabled.get(sleeve.parent_key or "")
        if sleeve.parent_key is not None and parent is None:
            raise _invalid("invalid_policy_tree", f"Enabled sleeve {key} has a missing or disabled parent")
        whole_portfolio_target = (
            target
            if parent is None
            else exact_percent_product(target_rows[parent.key].target_whole_portfolio_pct, target)
        )
        target_rows[key] = SleeveTarget(key, target, whole_portfolio_target)
        pending.extend(children.get(key, []))

    top_targets = tuple(
        (key, target_rows[key].target_whole_portfolio_pct)
        for key in children.get(None, [])
    )
    ordered_targets = tuple(
        target_rows[key]
        for key in sorted(target_rows, key=lambda item: (enabled[item].sort_order, item))
    )
    return AllocationTarget(top_targets, ordered_targets)


def _transition_snapshot(
    policy: AllocationPolicy,
    state: AccountSnapshot,
    destination_key: str | None,
    progress_pct: Decimal | None,
) -> TransitionSnapshot:
    sleeves = {sleeve.key: sleeve for sleeve in policy.sleeves if sleeve.enabled}
    container = next(
        (sleeve for sleeve in sleeves.values() if sleeve.direct_index_container),
        None,
    )
    if container is None:
        raise _invalid("transition_container_missing", "Transition summary requires a direct-indexing container")
    values = dict(state.sleeve_values_usd)
    children = sorted(
        (sleeve for sleeve in sleeves.values() if sleeve.parent_key == container.key),
        key=lambda sleeve: (sleeve.sort_order, sleeve.key),
    )
    return TransitionSnapshot(
        us_sleeve_value_usd=values.get(container.key, Decimal(0)),
        us_sleeve_whole_portfolio_pct=percentage(
            values.get(container.key, Decimal(0)), state.portfolio_total_usd
        ),
        etf_progress_pct=progress_pct,
        children=tuple(
            (
                child.key,
                TransitionChild(
                    values.get(child.key, Decimal(0)),
                    percentage(values.get(child.key, Decimal(0)), values.get(container.key, Decimal(0))),
                    percentage(values.get(child.key, Decimal(0)), state.portfolio_total_usd),
                ),
            )
            for child in children
        ),
    )


def _transition_evaluation(
    policy: AllocationPolicy, current: AccountSnapshot, proposed: AccountSnapshot, target: AllocationTarget
) -> TransitionEvaluation | None:
    current_values = dict(current.sleeve_values_usd)
    proposed_values = dict(proposed.sleeve_values_usd)
    try:
        current_progress = transition_progress(policy, current_values)
        proposed_progress = transition_progress(policy, proposed_values)
    except ValueError as exc:
        reason = str(exc)
        raise _invalid(reason, f"Invalid transition-destination configuration: {reason}") from exc
    if current_progress.container_key is None:
        return None
    children_targets = {row.sleeve_key: row for row in target.sleeves}
    container = next(sleeve for sleeve in policy.sleeves if sleeve.key == current_progress.container_key)
    children = sorted(
        (
            sleeve
            for sleeve in policy.sleeves
            if sleeve.enabled and sleeve.parent_key == container.key
        ),
        key=lambda sleeve: (sleeve.sort_order, sleeve.key),
    )
    target_children = tuple(
        (
            child.key,
            TransitionTargetChild(
                child.target_pct or Decimal(0),
                children_targets[child.key].target_whole_portfolio_pct,
            ),
        )
        for child in children
    )
    return TransitionEvaluation(
        sleeve_key=container.key,
        destination_sleeve_key=current_progress.destination_sleeve_key,
        current=_transition_snapshot(
            policy, current, current_progress.destination_sleeve_key, current_progress.progress_pct
        ),
        proposed_basket=_transition_snapshot(
            policy, proposed, proposed_progress.destination_sleeve_key, proposed_progress.progress_pct
        ),
        target=TransitionTarget(
            children_targets[container.key].target_whole_portfolio_pct,
            target_children,
        ),
    )


def evaluate_portfolio(
    inputs: FinancialInputs,
    proposed_legs: Sequence[ConsolidatedLeg] = (),
    *,
    allow_unassigned_current_positions: bool = False,
) -> PortfolioEvaluation:
    """Recompute current and proposed account effects from immutable inputs and unique legs.

    This is suitable for independent validation after solver rounding: it has no parameters for
    solver-reported totals, and every leg, sale allocation, cash movement, and sleeve value is
    recomputed from the frozen financial inputs.
    `allow_unassigned_current_positions` is only for empty-basket display; proposed baskets stay strict.
    """
    policy = inputs.policy.allocation
    legs = _normalized_legs(proposed_legs)
    if allow_unassigned_current_positions and legs:
        raise _invalid(
            "unassigned_current_only",
            "Unassigned current holdings may be omitted from sleeve totals only for an empty-basket display",
        )
    cash_usd = inputs.account.cash_usd
    settled_buying_power_usd = inputs.account.settled_buying_power_usd
    if (
        not cash_usd.is_finite()
        or not settled_buying_power_usd.is_finite()
        or cash_usd < 0
        or settled_buying_power_usd < 0
    ):
        raise _invalid("invalid_account_balance", "Account cash and settled buying power must be finite and nonnegative")
    positions_by_ticker: dict[str, PositionInput] = {}
    position_assignments: dict[str, SleeveAssignment | None] = {}
    for position in inputs.positions:
        ticker = position.ticker.strip().upper()
        if ticker in positions_by_ticker:
            raise _invalid("duplicate_position", f"Current position {ticker} appears more than once")
        if (
            not position.shares.is_finite()
            or position.shares <= 0
            or not position.market_value_usd.is_finite()
            or position.market_value_usd < 0
        ):
            raise _invalid("invalid_position", f"Current position {ticker} has invalid shares or market value")
        if position.assignment is None:
            if not allow_unassigned_current_positions:
                raise _invalid("unassigned_holding", f"Held security {ticker} has no policy sleeve assignment")
        else:
            _assignment_path(policy, position.assignment, ticker)
        positions_by_ticker[ticker] = position
        position_assignments[ticker] = position.assignment

    lots_by_id: dict[str, LotInput] = {}
    for lot in inputs.lots:
        if not lot.broker_lot_id or lot.broker_lot_id in lots_by_id:
            raise _invalid("duplicate_or_empty_lot_id", "Broker lot IDs must be nonempty and unique")
        if (
            not lot.shares.is_finite()
            or not lot.available_shares.is_finite()
            or lot.shares <= 0
            or lot.available_shares < 0
            or lot.available_shares > lot.shares
        ):
            raise _invalid("invalid_lot_balance", f"Broker lot {lot.broker_lot_id} has invalid share balances")
        lots_by_id[lot.broker_lot_id] = lot
    lot_shares_by_ticker: dict[str, Decimal] = {}
    for lot in lots_by_id.values():
        ticker = lot.ticker.strip().upper()
        position = positions_by_ticker.get(ticker)
        if position is None:
            raise _invalid("orphan_lot", f"Broker lot {lot.broker_lot_id} has no current {ticker} position")
        if not lot.adjusted_unit_basis_usd.is_finite() or lot.adjusted_unit_basis_usd < 0:
            raise _invalid("invalid_lot_basis", f"Broker lot {lot.broker_lot_id} has an invalid basis")
        lot_shares_by_ticker[ticker] = exact_sum((lot_shares_by_ticker.get(ticker, Decimal(0)), lot.shares))
    for ticker, lot_shares in lot_shares_by_ticker.items():
        if lot_shares > positions_by_ticker[ticker].shares:
            raise _invalid("lot_shares_exceed_position", f"Broker lots exceed current position shares for {ticker}")

    lot_allocations: dict[str, tuple[ConsolidatedLeg, LotAllocation]] = {}
    sold_by_ticker: dict[str, Decimal] = {}
    bought_assignment: dict[str, SleeveAssignment] = {}
    for leg in legs:
        ticker = leg.ticker.strip().upper()
        if leg.side == "SELL":
            position = positions_by_ticker.get(ticker)
            if position is None:
                raise _invalid("sell_without_position", f"SELL leg {leg.leg_id} has no current {ticker} position")
            if not leg.selected_lots:
                raise _invalid("sell_without_lots", f"SELL leg {leg.leg_id} requires explicit broker-lot allocations")
            lot_share_sum: list[Decimal] = []
            for allocation in leg.selected_lots:
                lot = lots_by_id.get(allocation.broker_lot_id)
                if lot is None or lot.ticker.strip().upper() != ticker:
                    raise _invalid(
                        "unknown_or_mismatched_lot",
                        f"SELL leg {leg.leg_id} references an unknown or different-ticker broker lot",
                    )
                if not allocation.shares.is_finite() or allocation.shares <= 0:
                    raise _invalid("invalid_lot_allocation", f"SELL leg {leg.leg_id} lot shares must be positive")
                if allocation.shares > lot.available_shares or allocation.shares > lot.shares:
                    raise _invalid(
                        "lot_oversell", f"SELL leg {leg.leg_id} exceeds available shares for {allocation.broker_lot_id}"
                    )
                if allocation.broker_lot_id in lot_allocations:
                    raise _invalid("duplicate_lot_allocation", f"Broker lot {allocation.broker_lot_id} is sold twice")
                lot_allocations[allocation.broker_lot_id] = (leg, allocation)
                lot_share_sum.append(allocation.shares)
            if exact_sum(lot_share_sum) != leg.shares:
                raise _invalid("sell_lot_total_mismatch", f"SELL leg {leg.leg_id} shares do not equal its lot allocations")
            sold_by_ticker[ticker] = leg.shares
            if leg.shares > position.shares:
                raise _invalid("position_oversell", f"SELL leg {leg.leg_id} exceeds current position shares")
        else:
            security = inputs.security_for(ticker)
            if security is None:
                raise _invalid("unknown_buy_security", f"BUY leg {leg.leg_id} references unknown security {ticker}")
            resolution = resolve_holding(policy, security.identity)
            if resolution.assignment is None:
                raise _invalid(
                    "unassigned_buy_security",
                    f"BUY security {ticker} has no valid policy assignment ({resolution.reason})",
                )
            existing = positions_by_ticker.get(ticker)
            if existing is not None and existing.assignment != resolution.assignment:
                raise _invalid("buy_assignment_mismatch", f"BUY security {ticker} differs from its current assignment")
            bought_assignment[ticker] = resolution.assignment

    cash_reserve_value = inputs.policy.settings.get("cash_reserve_usd", Decimal(0))
    if (
        not isinstance(cash_reserve_value, Decimal)
        or not cash_reserve_value.is_finite()
        or cash_reserve_value < 0
    ):
        raise _invalid("invalid_cash_reserve", "Configured cash reserve must be a nonnegative Decimal")
    cash = cash_usd

    leg_by_id = {leg.leg_id: leg for leg in legs}
    for leg in sorted(legs, key=lambda item: (item.sequence, item.leg_id)):
        notional = exact_product(leg.shares, leg.estimated_unit_price_usd)
        if leg.side == "SELL":
            cash = exact_sum((cash, notional))
        else:
            cash = exact_difference(cash, notional)
            if cash < cash_reserve_value:
                raise _invalid("insufficient_cash", f"BUY leg {leg.leg_id} breaches the configured cash reserve")
        for dependency_id in leg.depends_on_leg_ids:
            if leg_by_id[dependency_id].sequence >= leg.sequence:
                raise _invalid("funding_dependency_not_prior", f"Funding SELL {dependency_id} must precede {leg.leg_id}")

    current_positions = {
        ticker: PositionBalance(
            position.ticker,
            position.asset_type,
            position.shares,
            position.market_value_usd,
            position_assignments[ticker],
        )
        for ticker, position in positions_by_ticker.items()
    }
    current_lots = {
        lot_id: LotBalance(lot.ticker, lot_id, lot.shares, lot.available_shares)
        for lot_id, lot in lots_by_id.items()
    }
    proposed_positions = dict(current_positions)
    proposed_lots = dict(current_lots)
    position_effects: list[PositionEffect] = []
    lot_effects: list[LotEffect] = []
    realized_st: list[Decimal] = []
    realized_lt: list[Decimal] = []

    for ticker, shares_sold in sold_by_ticker.items():
        before = current_positions[ticker]
        shares_after = exact_difference(before.shares, shares_sold)
        value_reduction = _proportional_amount(before.market_value_usd, shares_sold, before.shares)
        value_after = exact_difference(before.market_value_usd, value_reduction)
        if value_after < 0:
            raise _invalid("negative_position_value", f"SELL leg leaves {ticker} with a negative market value")
        if shares_after == 0:
            proposed_positions.pop(ticker, None)
            value_after = Decimal(0)
        else:
            proposed_positions[ticker] = PositionBalance(
                before.ticker, before.asset_type, shares_after, value_after, before.assignment
            )
        position_effects.append(
            PositionEffect(ticker, before.shares, shares_after, before.market_value_usd, value_after, shares_after == 0)
        )

    for leg in legs:
        if leg.side != "BUY":
            continue
        ticker = leg.ticker.strip().upper()
        notional = exact_product(leg.shares, leg.estimated_unit_price_usd)
        before = proposed_positions.get(ticker)
        if before is None:
            security = inputs.security_for(ticker)
            assert security is not None
            proposed_positions[ticker] = PositionBalance(
                security.identity.ticker,
                security.identity.asset_type,
                leg.shares,
                notional,
                bought_assignment[ticker],
            )
        else:
            proposed_positions[ticker] = PositionBalance(
                before.ticker,
                before.asset_type,
                exact_sum((before.shares, leg.shares)),
                exact_sum((before.market_value_usd, notional)),
                before.assignment,
            )

    for lot_id, (leg, allocation) in lot_allocations.items():
        lot = lots_by_id[lot_id]
        shares_after = exact_difference(lot.shares, allocation.shares)
        available_after = exact_difference(lot.available_shares, allocation.shares)
        price_gain = exact_difference(leg.estimated_unit_price_usd, lot.adjusted_unit_basis_usd)
        realized = exact_product(price_gain, allocation.shares)
        term = cast(
            Literal["ST", "LT"], classify_holding_period(lot.acquired_date, inputs.proposed_trade_date)
        )
        (realized_st if term == "ST" else realized_lt).append(realized)
        if shares_after == 0:
            proposed_lots.pop(lot_id, None)
        else:
            proposed_lots[lot_id] = LotBalance(lot.ticker, lot_id, shares_after, available_after)
        lot_effects.append(
            LotEffect(
                lot.ticker,
                lot_id,
                lot.shares,
                allocation.shares,
                shares_after,
                lot.available_shares,
                available_after,
                realized,
                term,
                shares_after == 0,
            )
        )

    effect_tickers = {effect.ticker for effect in position_effects}
    for ticker, before in current_positions.items():
        after = proposed_positions.get(ticker)
        if after is not None and ticker not in effect_tickers and (
            before.shares != after.shares or before.market_value_usd != after.market_value_usd
        ):
            position_effects.append(
                PositionEffect(
                    ticker,
                    before.shares,
                    after.shares,
                    before.market_value_usd,
                    after.market_value_usd,
                    False,
                )
            )
    for ticker, after in proposed_positions.items():
        if ticker not in current_positions:
            position_effects.append(
                PositionEffect(ticker, Decimal(0), after.shares, Decimal(0), after.market_value_usd, False)
            )
    current = _snapshot(policy, current_positions, current_lots, cash_usd)
    proposed = _snapshot(policy, proposed_positions, proposed_lots, cash)
    target = _allocation_target(policy)
    transition = _transition_evaluation(policy, current, proposed, target)
    return PortfolioEvaluation(
        current=current,
        proposed=proposed,
        allocation=AllocationEvaluation(current, proposed, target),
        transition=transition,
        position_effects=tuple(sorted(position_effects, key=lambda item: item.ticker)),
        lot_effects=tuple(sorted(lot_effects, key=lambda item: (item.ticker, item.broker_lot_id))),
        position_count_before=len(current_positions),
        position_count_after=len(proposed_positions),
        lot_count_before=len(current_lots),
        lot_count_after=len(proposed_lots),
        selected_lots_count=len(lot_allocations),
        sell_proceeds_usd=exact_sum(
            exact_product(leg.estimated_unit_price_usd, leg.shares) for leg in legs if leg.side == "SELL"
        ),
        realized_st_usd=exact_sum(realized_st),
        realized_lt_usd=exact_sum(realized_lt),
    )
