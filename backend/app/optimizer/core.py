"""Two-pass, deadline-bounded top-K tax-lot optimizer worker.

This module proposes canonical legs only. The caller must validate the returned basket independently
through :func:`app.optimizer.validation.validate_candidate` before storing or displaying it as feasible.
"""

from __future__ import annotations

import math
import time
from collections import defaultdict
from dataclasses import dataclass, replace
from decimal import ROUND_FLOOR, Decimal
from importlib.metadata import PackageNotFoundError, version
from typing import Any

import cvxpy as cp

from app.domain.allocation import AllocationSleeve, assignment_path, resolve_cash, resolve_holding
from app.domain.decimal_math import exact_product, exact_sum
from app.domain.exposure import aggregate_lookthrough_exposure
from app.domain.financial_inputs import FinancialInputs, LotInput, PositionInput, QuoteInput
from app.domain.portfolio_accounting import (
    BasketValidationError,
    ConsolidatedLeg,
    LotAllocation,
    PortfolioEvaluation,
    evaluate_portfolio,
)
from app.domain.tax import (
    TaxAffineRegion,
    TaxProfile,
    enumerate_tax_regions,
    evaluate_tax,
    tax_value,
)
from app.domain.trade_dates import classify_holding_period
from app.domain.wash import ProposedBuy, ProposedLotSale, assess_proposed_buys, assess_wash_sales
from app.optimizer.validation import (
    CandidateValidation,
    ObjectivePolicy,
    read_objective_policy,
    validate_candidate,
)

_ZERO = Decimal(0)
_ONE = Decimal(1)
_HUNDRED = Decimal(100)
_BASIS_POINTS = Decimal(10000)
_INTEGER_SEARCH_INCOMPLETE = "whole_share_search_incomplete_continuous_relaxation_rounded_down"
OPTIMIZER_IMPLEMENTATION_VERSION = "t-0045-core-v1"


@dataclass(frozen=True, slots=True)
class OptimizerRequest:
    inputs: FinancialInputs
    sell_lot_ids: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class TradeGroupPriority:
    group_id: str
    rank: int
    priority_score: Decimal | None
    objective_components: tuple[tuple[str, Decimal], ...]
    rationale: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OptimizerMetadata:
    input_generation: int
    source_checksum: str | None
    status: str
    solver: str | None
    solver_statuses: tuple[str, ...]
    elapsed_seconds: float
    screening_seconds: float
    solve_seconds: float
    tax_regions_considered: int
    tax_regions_solved: int
    tax_region_search_complete: bool
    integer_search_complete: bool
    screened_lot_count: int
    selected_lot_ids: tuple[str, ...]
    candidate_types: tuple[str, ...]
    objective_value: Decimal | None
    baseline_objective_value: Decimal | None
    estimated_tax_benefit_usd: Decimal | None
    estimated_trading_cost_usd: Decimal | None
    exposure_coverage_complete: bool | None
    rounding_attempts: int
    warnings: tuple[str, ...]
    implementation_version: str = OPTIMIZER_IMPLEMENTATION_VERSION
    solver_versions: tuple[tuple[str, str], ...] = ()
    trade_group_priorities: tuple[TradeGroupPriority, ...] = ()
    repair_validate_rank_seconds: float = 0.0


@dataclass(frozen=True, slots=True)
class OptimizerResult:
    status: str
    legs: tuple[ConsolidatedLeg, ...]
    metadata: OptimizerMetadata


@dataclass(frozen=True, slots=True)
class _SaleCandidate:
    lot: LotInput
    maximum_shares: Decimal
    mark_price: Decimal
    execution_price: Decimal
    gain_per_share: Decimal
    term: str
    categories: tuple[str, ...]
    rank: Decimal


@dataclass(frozen=True, slots=True)
class _BuyCandidate:
    ticker: str
    maximum_shares: Decimal
    mark_price: Decimal
    execution_price: Decimal
    assignment_path: tuple[str, ...]
    priority: int
    replacement_set_id: str


@dataclass(frozen=True, slots=True)
class _Screen:
    baseline: PortfolioEvaluation
    sales: tuple[_SaleCandidate, ...]
    buys: tuple[_BuyCandidate, ...]
    warnings: tuple[str, ...]
    candidate_types: tuple[str, ...]
    screened_lot_count: int

    sector_model: _SectorModel | None = None


@dataclass(frozen=True, slots=True)
class _SectorModel:
    bands: tuple[tuple[str, Decimal, Decimal], ...]
    invested_usd: Decimal
    current_values: tuple[tuple[str, Decimal], ...]
    ticker_weights: tuple[tuple[str, tuple[tuple[str, Decimal], ...]], ...] = ()


@dataclass(frozen=True, slots=True)
class _RegionSolve:
    region: TaxAffineRegion | None
    problem: cp.Problem
    sell_variables: tuple[cp.Variable, ...]
    buy_variables: tuple[cp.Variable, ...]
    solver: str
    status: str


def _setting_decimal(
    inputs: FinancialInputs, key: str, default: Decimal | None = None
) -> Decimal | None:
    value = inputs.policy.settings.get(key, default)
    if value is None:
        return None
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"invalid decimal policy setting: {key}")
    return value


def _setting_int(inputs: FinancialInputs, key: str) -> int | None:
    value = inputs.policy.settings.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _build_sector_model(
    inputs: FinancialInputs, current_positions: tuple[Any, ...]
) -> tuple[_SectorModel | None, tuple[str, ...]]:
    raw_bands = inputs.policy.sector_bands
    if not raw_bands:
        if inputs.policy.status.strip().upper() == "ACTIVE":
            return None, ("configuration_required:sector_bands",)
        return None, ()

    bands: list[tuple[str, Decimal, Decimal]] = []
    seen: set[str] = set()
    for band in raw_bands:
        key = band.sector_key.strip()
        target = band.target_weight_pct
        tolerance = band.band_pct
        if (
            not key
            or key in seen
            or not target.is_finite()
            or not tolerance.is_finite()
            or target < _ZERO
            or target > _HUNDRED
            or tolerance < _ZERO
            or tolerance > _HUNDRED
        ):
            return None, ("invalid_sector_band_policy",)
        seen.add(key)
        bands.append((key, target / _HUNDRED, tolerance / _HUNDRED))
    if exact_sum(band.target_weight_pct for band in raw_bands) != _HUNDRED:
        return None, ("invalid_sector_band_target_sum",)

    try:
        exposure = aggregate_lookthrough_exposure(inputs, dimension="sector")
    except ArithmeticError, TypeError, ValueError:
        return None, ("sector_exposure_incomplete_or_unknown",)
    if exposure.coverage.complete is not True:
        return None, ("sector_exposure_incomplete_or_unknown",)
    current_values = {
        row.exposure_key: row.value_usd for row in exposure.values if row.dimension == "sector"
    }
    invested_usd = exact_sum(row.market_value_usd for row in current_positions)
    if exact_sum(current_values.values()) != invested_usd:
        return None, ("sector_exposure_not_fully_allocated",)
    if any(key not in seen and value > _ZERO for key, value in current_values.items()):
        return None, ("sector_exposure_not_configured",)
    return (
        _SectorModel(
            tuple(bands),
            invested_usd,
            tuple(sorted(current_values.items())),
        ),
        (),
    )


def _unit_sector_weights(
    inputs: FinancialInputs, ticker: str
) -> tuple[tuple[str, Decimal], ...] | None:
    ticker_key = ticker.upper()
    unit_inputs = replace(
        inputs,
        positions=tuple(row for row in inputs.positions if row.ticker.upper() != ticker_key),
    )
    try:
        exposure = aggregate_lookthrough_exposure(
            unit_inputs, tickers=(ticker_key,), dimension="sector"
        )
    except ArithmeticError, TypeError, ValueError:
        return None
    if exposure.coverage.complete is not True:
        return None
    weights = tuple(
        sorted(
            (row.exposure_key, row.value_usd)
            for row in exposure.values
            if row.dimension == "sector" and row.value_usd != _ZERO
        )
    )
    if exact_sum(value for _, value in weights) != _ONE:
        return None
    return weights


def _whole_floor(value: Decimal) -> Decimal:
    return value.to_integral_value(rounding=ROUND_FLOOR)


def _mark_price(quote: QuoteInput) -> Decimal | None:
    if quote.bid_usd is not None and quote.ask_usd is not None:
        if quote.bid_usd <= 0 or quote.ask_usd <= 0 or quote.bid_usd > quote.ask_usd:
            return None
        return (quote.bid_usd + quote.ask_usd) / Decimal(2)
    if quote.last_usd is not None and quote.last_usd > 0:
        return quote.last_usd
    if quote.bid_usd is not None and quote.bid_usd > 0:
        return quote.bid_usd
    if quote.ask_usd is not None and quote.ask_usd > 0:
        return quote.ask_usd
    return None


def _quote_is_current(inputs: FinancialInputs, quote: QuoteInput | None) -> bool:
    return (
        quote is not None
        and quote.quality.lower() == "good"
        and quote.sync_generation == inputs.source_generation
        and quote.as_of <= inputs.account.as_of
        and _mark_price(quote) is not None
    )


def _execution_prices(mark: Decimal, spread_bps: Decimal) -> tuple[Decimal, Decimal]:
    half_spread = spread_bps / _BASIS_POINTS
    sell_price = mark * (_ONE - half_spread)
    buy_price = mark * (_ONE + half_spread)
    return sell_price, buy_price


def _asset_flags(asset_type: str) -> tuple[bool, bool, bool]:
    normalized = asset_type.upper()
    is_equity = normalized == "EQUITY"
    is_muni = "MUNI" in normalized or "MUNICIPAL" in normalized
    is_etf = not is_equity and not is_muni and ("ETF" in normalized or "MUTUAL_FUND" in normalized)
    return is_equity, is_etf, is_muni


def _validate_target_sums(inputs: FinancialInputs) -> tuple[str, ...]:
    sleeves = tuple(row for row in inputs.policy.allocation.sleeves if row.enabled)
    children: dict[str | None, list[AllocationSleeve]] = defaultdict(list)
    for row in sleeves:
        children[row.parent_key].append(row)
    errors: list[str] = []
    for parent_key, siblings in children.items():
        total = exact_sum(row.target_pct or _ZERO for row in siblings)
        if total != _HUNDRED:
            label = "top_level" if parent_key is None else parent_key
            errors.append(f"allocation_target_sum_not_100:{label}")
    return tuple(errors)


def _configured_limits(
    inputs: FinancialInputs,
) -> tuple[int, int, int, Decimal, Decimal, Decimal] | None:
    sell_ticker_limit = _setting_int(inputs, "max_sell_tickers_per_batch")
    sell_lot_limit = _setting_int(inputs, "max_sell_lots_per_batch")
    order_limit = _setting_int(inputs, "max_total_orders_per_batch")
    turnover_pct = _setting_decimal(inputs, "max_batch_turnover_pct")
    buy_minimum = _setting_decimal(inputs, "min_buy_order_notional_usd")
    cash_reserve = _setting_decimal(inputs, "cash_reserve_usd", _ZERO)
    if (
        sell_ticker_limit is None
        or sell_lot_limit is None
        or order_limit is None
        or turnover_pct is None
        or buy_minimum is None
        or cash_reserve is None
        or sell_ticker_limit <= 0
        or sell_lot_limit <= 0
        or order_limit <= 0
        or not _ZERO <= turnover_pct <= _HUNDRED
        or buy_minimum < 0
        or cash_reserve < 0
    ):
        return None
    return sell_ticker_limit, sell_lot_limit, order_limit, turnover_pct, buy_minimum, cash_reserve


def _enabled_allowed(inputs: FinancialInputs) -> dict[str, tuple[int, str]]:
    result: dict[str, tuple[int, str]] = {}
    for row in inputs.policy.allocation.allowed_securities:
        if not row.enabled:
            continue
        ticker = row.ticker.upper()
        candidate = (row.priority, row.replacement_set_id)
        if ticker not in result or candidate[0] < result[ticker][0]:
            result[ticker] = candidate
    return result


def _current_overweight_rank(
    inputs: FinancialInputs,
    baseline: PortfolioEvaluation,
    position: PositionInput,
    sale_notional: Decimal,
) -> Decimal:
    if position.assignment is None:
        return _ZERO
    path = assignment_path(
        inputs.policy.allocation, position.assignment.sleeve_key, position.assignment.sub_sleeve_key
    )
    if path is None:
        return _ZERO
    target_rows = {row.sleeve_key: row for row in baseline.allocation.target.sleeves}
    values = dict(baseline.current.sleeve_values_usd)
    bonus: list[Decimal] = []
    total = baseline.current.portfolio_total_usd
    for key in path:
        target_row = target_rows.get(key)
        sleeve = next((item for item in inputs.policy.allocation.sleeves if item.key == key), None)
        if target_row is None or sleeve is None:
            continue
        target = target_row.target_whole_portfolio_pct
        band = sleeve.drift_band_pp or _ZERO
        if sleeve.parent_key is not None:
            parent = target_rows.get(sleeve.parent_key)
            band = band * (parent.target_whole_portfolio_pct if parent else _ZERO) / _HUNDRED
        current_pct = values.get(key, _ZERO) * _HUNDRED / total if total else _ZERO
        excess = max(_ZERO, current_pct - target - band)
        if excess:
            bonus.append(
                min(excess, sale_notional * _HUNDRED / total if total else _ZERO) / _HUNDRED
            )
    return exact_sum(bonus)


def _screen(
    request: OptimizerRequest,
    config: ObjectivePolicy,
    deadline: float,
) -> tuple[_Screen | None, tuple[str, ...]]:
    inputs = request.inputs
    if time.monotonic() >= deadline:
        return None, ("deadline_exceeded_during_screen",)
    if inputs.source_metadata.sync_complete is not True:
        return None, ("source_sync_incomplete",)
    try:
        baseline = evaluate_portfolio(inputs, ())
    except BasketValidationError as error:
        return None, (f"current_portfolio_invalid:{error.code}",)
    warnings: list[str] = []
    position_by_ticker = {row.ticker.upper(): row for row in inputs.positions}
    security_by_ticker = {row.identity.ticker.upper(): row for row in inputs.securities}
    quote_by_ticker = {row.ticker.upper(): row for row in inputs.quotes}
    inputs_profile = TaxProfile.from_policy_settings(inputs.policy.settings)
    gain_sales_allowed = inputs.policy.settings.get("allow_gain_sales", False) is True
    etf_harvest_allowed = inputs.policy.settings.get("permit_etf_harvest", False) is True
    muni_exit_allowed = inputs.policy.settings.get("permit_muni_exit", False) is True
    preferred_etfs = inputs.policy.settings.get("prefer_etf_buys", False) is True
    total = baseline.current.portfolio_total_usd
    target_errors = _validate_target_sums(inputs)
    if target_errors:
        return None, target_errors
    sector_model, sector_errors = _build_sector_model(inputs, baseline.current.positions)
    if sector_errors:
        return None, sector_errors
    sector_weights_by_ticker: dict[str, tuple[tuple[str, Decimal], ...]] = {}

    candidates: list[_SaleCandidate] = []
    candidate_types: set[str] = set()
    seen_lots = 0
    for lot in inputs.lots:
        if time.monotonic() >= deadline:
            warnings.append("deadline_during_screening")
            break
        seen_lots += 1
        ticker = lot.ticker.upper()
        position = position_by_ticker.get(ticker)
        security = security_by_ticker.get(ticker)
        quote = quote_by_ticker.get(ticker)
        if position is None or security is None or quote is None:
            continue
        if not _quote_is_current(inputs, quote) or not security.tradable:
            continue
        if (
            position.sync_generation != inputs.source_generation
            or position.as_of > inputs.account.as_of
            or lot.sync_generation != inputs.source_generation
            or lot.as_of > inputs.account.as_of
        ):
            warnings.append(f"stale_position_or_lot:{ticker}:{lot.broker_lot_id}")
            continue
        whole_available = _whole_floor(lot.available_shares)
        if whole_available <= 0:
            if lot.available_shares > 0:
                warnings.append(f"fractional_remainder_not_executable:{lot.broker_lot_id}")
            continue
        if lot.available_shares != whole_available:
            warnings.append(f"fractional_remainder_not_executable:{lot.broker_lot_id}")
            if lot.fractional_cleanup_unsupported:
                warnings.append(f"fractional_cleanup_unsupported:{lot.broker_lot_id}")
        mark = _mark_price(quote)
        if mark is None:
            continue
        sell_price, _ = _execution_prices(mark, config.estimated_spread_bps)
        if sell_price <= 0:
            continue
        gain_per_share = sell_price - lot.adjusted_unit_basis_usd
        is_equity, is_etf, is_muni = _asset_flags(security.identity.asset_type)
        sale_notional = sell_price * whole_available
        band_bonus = _current_overweight_rank(inputs, baseline, position, sale_notional)
        categories: list[str] = []
        if gain_per_share < 0:
            if is_equity:
                categories.append("stock_tlh")
            elif is_etf and etf_harvest_allowed:
                categories.append("etf_tlh")
            elif is_muni and muni_exit_allowed:
                categories.append("municipal_exit")
        if gain_sales_allowed:
            if is_muni and muni_exit_allowed:
                categories.append("municipal_exit")
            elif is_equity:
                categories.append("gain_aware_stock_cleanup")
            elif is_etf:
                categories.append("allowed_etf_swap_exit")
        if band_bonus > 0 and (gain_per_share <= 0 or gain_sales_allowed):
            categories.append("allocation_exit")
        if not categories:
            continue

        if gain_per_share > 0 and not inputs_profile.tax_rates_complete:
            warnings.append(f"gain_candidate_blocked_incomplete_tax_rates:{lot.broker_lot_id}")
            continue
        if lot.fractional_cleanup_unsupported and lot.available_shares < 1:
            continue
        quantity_gain = gain_per_share * whole_available
        term = classify_holding_period(lot.acquired_date, inputs.proposed_trade_date)
        st_gain = quantity_gain if term == "ST" else _ZERO
        lt_gain = quantity_gain if term == "LT" else _ZERO
        tax_eval = evaluate_tax(inputs_profile, st_gain, lt_gain)
        tax_benefit = tax_eval.estimated_tax_benefit_usd or _ZERO
        cost = (
            sale_notional * config.estimated_spread_bps / _BASIS_POINTS
            + config.estimated_fee_per_order_usd
        )
        cleanup_fraction = Decimal(1) / Decimal(max(1, len(inputs.lots)))
        rank = exact_sum(
            (
                config.weight("objective_tax_weight") * tax_benefit / total if total else _ZERO,
                config.weight("objective_band_weight") * band_bonus,
                config.weight("objective_allocation_weight") * band_bonus,
                config.weight("objective_cleanup_weight") * cleanup_fraction,
                -(
                    config.weight("objective_trading_cost_weight") * cost / total
                    if total
                    else _ZERO
                ),
                -(
                    config.weight("objective_turnover_weight") * sale_notional / total
                    if total
                    else _ZERO
                ),
            )
        )
        candidates.append(
            _SaleCandidate(
                lot,
                whole_available,
                mark,
                sell_price,
                gain_per_share,
                "ST" if inputs_profile.tax_rates_complete and st_gain != 0 else "LT",
                tuple(categories),
                rank,
            )
        )
        candidate_types.update(categories)

    candidates_by_ticker: dict[str, list[_SaleCandidate]] = defaultdict(list)
    for candidate in candidates:
        candidates_by_ticker[candidate.lot.ticker.upper()].append(candidate)
    wash_blocked: set[str] = set()
    requested_lots = set(request.sell_lot_ids) if request.sell_lot_ids is not None else None
    for ticker, ticker_candidates in candidates_by_ticker.items():
        if time.monotonic() >= deadline:
            return None, ("deadline_during_sell_wash_screening",)
        possible_group = tuple(
            candidate
            for candidate in ticker_candidates
            if requested_lots is None or candidate.lot.broker_lot_id in requested_lots
        )
        proposed_sales = tuple(
            ProposedLotSale(
                ticker,
                candidate.lot.broker_lot_id,
                candidate.maximum_shares,
                candidate.gain_per_share * candidate.maximum_shares,
                f"sale:{ticker}",
                inputs.proposed_trade_date,
            )
            for candidate in possible_group
        )
        assessments = assess_wash_sales(inputs, proposed_sales)
        for assessment in assessments:
            if not assessment.eligible:
                wash_blocked.add(assessment.broker_lot_id)
                warnings.extend(
                    f"sell_wash_sale_ineligible:{ticker}:{assessment.broker_lot_id}:{reason}"
                    for reason in assessment.reasons
                )
    if wash_blocked:
        candidates = [
            candidate for candidate in candidates if candidate.lot.broker_lot_id not in wash_blocked
        ]
    limits = _configured_limits(inputs)
    if limits is None:
        return None, ("configuration_required:batch_limits_and_cash_policy",)
    sell_ticker_limit, sell_lot_limit, order_limit, turnover_pct, buy_minimum, _cash_reserve = (
        limits
    )
    sell_order_capacity = min(sell_ticker_limit, order_limit)
    if config.estimated_spread_bps >= _BASIS_POINTS:
        return None, ("invalid_configuration:estimated_spread_bps_must_be_less_than_10000",)
    candidates.sort(key=lambda row: (-row.rank, row.lot.ticker.upper(), row.lot.broker_lot_id))
    if request.sell_lot_ids is not None:
        requested = set(request.sell_lot_ids)
        matched = {candidate.lot.broker_lot_id for candidate in candidates}
        unknown = requested - {lot.broker_lot_id for lot in inputs.lots}
        ineligible = requested - matched
        if unknown:
            return None, tuple(f"unknown_selected_lot:{lot_id}" for lot_id in sorted(unknown))
        if ineligible:
            return None, tuple(
                f"selected_lot_not_eligible:{lot_id}" for lot_id in sorted(ineligible)
            )
        candidates = [
            candidate for candidate in candidates if candidate.lot.broker_lot_id in requested
        ]
        if len(candidates) > sell_lot_limit:
            return None, ("selected_subset_exceeds_max_sell_lots_per_batch",)
        if len({candidate.lot.ticker.upper() for candidate in candidates}) > sell_order_capacity:
            return None, ("selected_subset_exceeds_max_sell_tickers_per_batch",)
    selected_sales: list[_SaleCandidate] = []
    selected_tickers: set[str] = set()
    for candidate in candidates:
        ticker = candidate.lot.ticker.upper()
        if len(selected_sales) >= sell_lot_limit:
            break
        if ticker not in selected_tickers and len(selected_tickers) >= sell_order_capacity:
            continue
        selected_sales.append(candidate)
        selected_tickers.add(ticker)

    enabled_allowed = _enabled_allowed(inputs)
    buy_candidates: list[_BuyCandidate] = []
    exposure_buy_cache: dict[str, bool] = {}
    for ticker, (priority, replacement_set) in sorted(
        enabled_allowed.items(), key=lambda item: (item[1][0], item[0])
    ):
        if time.monotonic() >= deadline:
            warnings.append("deadline_during_buy_screening")
            break
        security = security_by_ticker.get(ticker)
        quote = quote_by_ticker.get(ticker)
        if security is None or not security.tradable or not _quote_is_current(inputs, quote):
            continue
        assert quote is not None
        is_equity, is_etf, is_muni = _asset_flags(security.identity.asset_type)
        if preferred_etfs and not (is_etf or security.identity.is_completion_etf):
            continue
        if is_muni:
            continue
        resolution = resolve_holding(inputs.policy.allocation, security.identity)
        if resolution.assignment is None:
            continue
        path = assignment_path(
            inputs.policy.allocation,
            resolution.assignment.sleeve_key,
            resolution.assignment.sub_sleeve_key,
        )
        if path is None:
            continue
        mark = _mark_price(quote)
        if mark is None:
            continue
        _, buy_price = _execution_prices(mark, config.estimated_spread_bps)
        if buy_price <= 0 or buy_price < 0:
            continue
        if not is_equity:
            try:
                candidate_exposure = aggregate_lookthrough_exposure(inputs, tickers=(ticker,))
                exposure_ok = candidate_exposure.coverage.complete is True and bool(
                    candidate_exposure.values
                )
            except ValueError, TypeError, ArithmeticError:
                exposure_ok = False
            exposure_buy_cache[ticker] = exposure_ok
            if not exposure_ok:
                warnings.append(f"buy_exposure_incomplete:{ticker}")
                continue
        if total <= 0:
            continue
        if sector_model is not None:
            sector_weights = _unit_sector_weights(inputs, ticker)
            if sector_weights is None:
                warnings.append(f"buy_sector_exposure_incomplete:{ticker}")
                continue
            configured_sectors = {key for key, _, _ in sector_model.bands}
            if any(
                key not in configured_sectors and value > _ZERO for key, value in sector_weights
            ):
                warnings.append(f"buy_sector_exposure_not_configured:{ticker}")
                continue
            sector_weights_by_ticker[ticker] = sector_weights
        max_turnover_usd = total * turnover_pct / _HUNDRED
        max_shares = _whole_floor(max_turnover_usd / buy_price)
        if max_shares <= 0 or buy_price * max_shares < buy_minimum:
            continue
        buy_wash_assessments = assess_proposed_buys(
            inputs,
            (ProposedBuy(ticker, _ONE, f"screen-buy:{ticker}", inputs.proposed_trade_date),),
        )
        if time.monotonic() >= deadline:
            warnings.append("deadline_during_buy_screening")
            break
        if not all(assessment.eligible for assessment in buy_wash_assessments):
            warnings.extend(
                f"buy_wash_sale_ineligible:{ticker}:{reason}"
                for assessment in buy_wash_assessments
                for reason in assessment.reasons
            )
            continue
        buy_candidates.append(
            _BuyCandidate(ticker, max_shares, mark, buy_price, path, priority, replacement_set)
        )
    # A replacement BUY must be distinct from every source ticker in this basket.
    buy_candidates = [
        candidate for candidate in buy_candidates if candidate.ticker not in selected_tickers
    ]
    available_buy_slots = max(0, order_limit - len(selected_tickers))
    buy_candidates = buy_candidates[:available_buy_slots]
    if sector_model is not None:
        for ticker in sorted(selected_tickers):
            if ticker not in sector_weights_by_ticker:
                sector_weights = _unit_sector_weights(inputs, ticker)
                if sector_weights is None:
                    return None, (f"sector_exposure_incomplete:{ticker}",)
                configured_sectors = {key for key, _, _ in sector_model.bands}
                if any(
                    key not in configured_sectors and value > _ZERO for key, value in sector_weights
                ):
                    return None, (f"sector_exposure_not_configured:{ticker}",)
                sector_weights_by_ticker[ticker] = sector_weights
        active_buy_tickers = {candidate.ticker for candidate in buy_candidates}
        sector_model = replace(
            sector_model,
            ticker_weights=tuple(
                sorted(
                    (ticker, sector_weights_by_ticker[ticker])
                    for ticker in selected_tickers | active_buy_tickers
                )
            ),
        )
    warnings.append(_INTEGER_SEARCH_INCOMPLETE)
    screen = _Screen(
        baseline,
        tuple(selected_sales),
        tuple(buy_candidates),
        tuple(dict.fromkeys(warnings)),
        tuple(sorted(candidate_types)),
        seen_lots,
        sector_model,
    )
    return screen, ()


def _cp_float(value: Decimal) -> float:
    return float(value)


def _model_region(
    request: OptimizerRequest,
    screen: _Screen,
    config: ObjectivePolicy,
    limits: tuple[int, int, int, Decimal, Decimal, Decimal],
    profile: TaxProfile,
    region: TaxAffineRegion | None,
) -> tuple[cp.Problem, tuple[cp.Variable, ...], tuple[cp.Variable, ...]]:
    inputs = request.inputs
    baseline = screen.baseline
    sell_vars = tuple(
        cp.Variable(nonneg=True, name=f"sell_{index}") for index in range(len(screen.sales))
    )
    buy_vars = tuple(
        cp.Variable(nonneg=True, name=f"buy_{index}") for index in range(len(screen.buys))
    )
    constraints: list[Any] = []
    for variable, candidate in zip(sell_vars, screen.sales, strict=True):
        constraints.append(variable <= _cp_float(candidate.maximum_shares))
    if request.sell_lot_ids:
        required_lots = set(request.sell_lot_ids)
        for variable, candidate in zip(sell_vars, screen.sales, strict=True):
            if candidate.lot.broker_lot_id in required_lots:
                constraints.append(variable >= _ONE)
    for variable, candidate in zip(buy_vars, screen.buys, strict=True):
        constraints.append(variable <= _cp_float(candidate.maximum_shares))

    sell_by_ticker: dict[str, list[tuple[int, _SaleCandidate]]] = defaultdict(list)
    for index, candidate in enumerate(screen.sales):
        sell_by_ticker[candidate.lot.ticker.upper()].append((index, candidate))
    current_positions = {row.ticker.upper(): row for row in inputs.positions}
    sleeve_deltas: dict[str, Any] = defaultdict(lambda: cp.Constant(0.0))
    cash_path: tuple[str, ...] = ()
    cash_resolution = resolve_cash(inputs.policy.allocation)
    if cash_resolution.assignment is not None:
        resolved_path = assignment_path(
            inputs.policy.allocation,
            cash_resolution.assignment.sleeve_key,
            cash_resolution.assignment.sub_sleeve_key,
        )
        cash_path = resolved_path or ()
    sell_proceeds: Any = cp.Constant(0.0)
    sell_turnover: Any = cp.Constant(0.0)
    buy_spend: Any = cp.Constant(0.0)
    buy_turnover: Any = cp.Constant(0.0)
    realized_st: Any = cp.Constant(0.0)
    realized_lt: Any = cp.Constant(0.0)
    gross_st_gain: Any = cp.Constant(0.0)
    gross_lt_gain: Any = cp.Constant(0.0)
    lot_cleanup: Any = cp.Constant(0.0)
    position_cleanup: Any = cp.Constant(0.0)

    for ticker, rows in sell_by_ticker.items():
        position = current_positions[ticker]
        if position.assignment is None:
            continue
        path = (
            assignment_path(
                inputs.policy.allocation,
                position.assignment.sleeve_key,
                position.assignment.sub_sleeve_key,
            )
            or ()
        )
        position_value_per_share = position.market_value_usd / position.shares
        total_ticker_shares: Any = cp.Constant(0.0)
        for index, candidate in rows:
            variable = sell_vars[index]
            total_ticker_shares += variable
            sell_proceeds += _cp_float(candidate.execution_price) * variable
            sell_turnover += _cp_float(candidate.execution_price) * variable
            for key in path:
                sleeve_deltas[key] -= _cp_float(position_value_per_share) * variable
            gain = candidate.gain_per_share
            if candidate.term == "ST":
                realized_st += _cp_float(gain) * variable
                if gain > 0:
                    gross_st_gain += _cp_float(gain) * variable
            else:
                realized_lt += _cp_float(gain) * variable
                if gain > 0:
                    gross_lt_gain += _cp_float(gain) * variable
            lot_cleanup += variable / max(_cp_float(candidate.maximum_shares), 1.0)
        for key in cash_path:
            sleeve_deltas[key] += sum(
                _cp_float(candidate.execution_price) * sell_vars[index] for index, candidate in rows
            )
        position_cleanup += total_ticker_shares / max(_cp_float(position.shares), 1.0)

    for index, candidate in enumerate(screen.buys):
        variable = buy_vars[index]
        amount = _cp_float(candidate.execution_price) * variable
        buy_spend += amount
        buy_turnover += amount
        for key in candidate.assignment_path:
            sleeve_deltas[key] += amount
        for key in cash_path:
            sleeve_deltas[key] -= amount

    sector_model = screen.sector_model
    if sector_model is not None:
        sector_values = dict(sector_model.current_values)
        ticker_weights = dict(sector_model.ticker_weights)
        sector_deltas: dict[str, Any] = defaultdict(lambda: cp.Constant(0.0))
        invested_delta: Any = cp.Constant(0.0)
        for ticker, rows in sell_by_ticker.items():
            position = current_positions[ticker]
            value_per_share = position.market_value_usd / position.shares
            shares = sum(sell_vars[index] for index, _ in rows)
            invested_delta -= _cp_float(value_per_share) * shares
            for sector_key, weight in ticker_weights[ticker]:
                sector_deltas[sector_key] -= _cp_float(value_per_share * weight) * shares
        for candidate, variable in zip(screen.buys, buy_vars, strict=True):
            invested_delta += _cp_float(candidate.execution_price) * variable
            for sector_key, weight in ticker_weights[candidate.ticker]:
                sector_deltas[sector_key] += (
                    _cp_float(candidate.execution_price * weight) * variable
                )
        proposed_invested = _cp_float(sector_model.invested_usd) + invested_delta
        constraints.append(proposed_invested >= 0)
        for sector_key, target, tolerance in sector_model.bands:
            current_sector_value = sector_values.get(sector_key, _ZERO)
            current_weight = (
                current_sector_value / sector_model.invested_usd
                if sector_model.invested_usd > _ZERO
                else _ZERO
            )
            lower_bound = min(current_weight, target - tolerance)
            upper_bound = max(current_weight, target + tolerance)
            proposed_sector_value = _cp_float(current_sector_value) + sector_deltas[sector_key]
            constraints.append(proposed_sector_value >= _cp_float(lower_bound) * proposed_invested)
            constraints.append(proposed_sector_value <= _cp_float(upper_bound) * proposed_invested)

    sale_fee_proxy: Any = cp.Constant(0.0)
    for rows in sell_by_ticker.values():
        max_shares = exact_sum(candidate.maximum_shares for _, candidate in rows)
        sale_fee_proxy += (
            _cp_float(config.estimated_fee_per_order_usd)
            * sum(sell_vars[index] for index, _ in rows)
            / max(_cp_float(max_shares), 1.0)
        )
    buy_fee_proxy: Any = cp.Constant(0.0)
    for variable, candidate in zip(buy_vars, screen.buys, strict=True):
        buy_fee_proxy += (
            _cp_float(config.estimated_fee_per_order_usd)
            * variable
            / max(_cp_float(candidate.maximum_shares), 1.0)
        )
    fee_proxy = sale_fee_proxy + buy_fee_proxy

    _, _, _, turnover_pct, _, cash_reserve = limits
    total = baseline.current.portfolio_total_usd
    constraints.append(sell_turnover + buy_turnover <= _cp_float(total * turnover_pct / _HUNDRED))
    constraints.append(
        _cp_float(inputs.account.cash_usd) + sell_proceeds - buy_spend - fee_proxy
        >= _cp_float(cash_reserve)
    )
    constraints.append(
        _cp_float(inputs.account.settled_buying_power_usd) + sell_proceeds - buy_spend - fee_proxy
        >= 0
    )

    gain_budget = _setting_decimal(inputs, "gain_budget_usd")
    st_gain_limit = _setting_decimal(inputs, "st_gain_limit_usd")
    lt_gain_limit = _setting_decimal(inputs, "lt_gain_limit_usd")
    if gain_budget is not None:
        constraints.append(gross_st_gain + gross_lt_gain <= _cp_float(gain_budget))
    if st_gain_limit is not None:
        constraints.append(gross_st_gain <= _cp_float(st_gain_limit))
    if lt_gain_limit is not None:
        constraints.append(gross_lt_gain <= _cp_float(lt_gain_limit))

    incremental_tax: Any = cp.Constant(0.0)
    if region is not None:
        post_st = _cp_float(profile.baseline_st_net_usd) + realized_st
        post_lt = _cp_float(profile.baseline_lt_net_usd) + realized_lt
        for half_plane in region.inequalities:
            constraints.append(
                _cp_float(half_plane.short_term_coefficient) * post_st
                + _cp_float(half_plane.long_term_coefficient) * post_lt
                <= _cp_float(half_plane.upper_bound_usd)
            )
        baseline_tax = tax_value(profile, profile.baseline_st_net_usd, profile.baseline_lt_net_usd)
        assert baseline_tax is not None
        incremental_tax = (
            _cp_float(region.short_term_coefficient) * post_st
            + _cp_float(region.long_term_coefficient) * post_lt
            + _cp_float(region.constant_usd)
            - _cp_float(baseline_tax)
        )
        max_tax = _setting_decimal(inputs, "max_incremental_tax_cost_usd")
        if max_tax is not None:
            constraints.append(incremental_tax <= _cp_float(max_tax))
    else:
        max_tax = _setting_decimal(inputs, "max_incremental_tax_cost_usd")
        if max_tax is not None and (screen.sales or screen.buys):
            # Without complete rates the configured tax-cost cap cannot be independently proven.
            constraints.extend(variable == 0 for variable in (*sell_vars, *buy_vars))

    sleeve_by_key = {row.key: row for row in inputs.policy.allocation.sleeves if row.enabled}
    target_by_key = {row.sleeve_key: row for row in baseline.allocation.target.sleeves}
    current_values = dict(baseline.current.sleeve_values_usd)
    post_values = {
        key: _cp_float(current_values.get(key, _ZERO)) + sleeve_deltas[key] for key in target_by_key
    }
    post_weights = {key: post_values[key] * _cp_float(_HUNDRED / total) for key in target_by_key}
    allocation_terms: list[Any] = []
    band_terms: list[Any] = []
    for key, target_row in target_by_key.items():
        current_value = current_values.get(key, _ZERO)
        post_value = post_values[key]
        post_weight = post_weights[key]
        sleeve = sleeve_by_key[key]
        band = sleeve.drift_band_pp or _ZERO
        if sleeve.parent_key is None:
            target = target_row.target_whole_portfolio_pct
            current_weight = current_value * _HUNDRED / total if total else _ZERO
            deviation = post_weight - _cp_float(target)
            allocation_terms.append(cp.square(deviation / _cp_float(_HUNDRED)))
            band_terms.append(cp.pos(cp.abs(deviation) - _cp_float(band)) / _cp_float(_HUNDRED))
            lower_bound = min(current_weight, target - band)
            upper_bound = max(current_weight, target + band)
            constraints.append(post_weight >= _cp_float(lower_bound))
            constraints.append(post_weight <= _cp_float(upper_bound))
            continue

        parent_row = target_by_key[sleeve.parent_key]
        parent_current_value = current_values.get(sleeve.parent_key, _ZERO)
        parent_post_value = post_values[sleeve.parent_key]
        target_ratio = target_row.target_within_parent_pct
        current_ratio = (
            current_value * _HUNDRED / parent_current_value if parent_current_value > 0 else _ZERO
        )
        lower_ratio = min(current_ratio, target_ratio - band)
        upper_ratio = max(current_ratio, target_ratio + band)
        constraints.append(post_value >= _cp_float(lower_ratio / _HUNDRED) * parent_post_value)
        constraints.append(post_value <= _cp_float(upper_ratio / _HUNDRED) * parent_post_value)

        parent_target_weight = parent_row.target_whole_portfolio_pct
        parent_scale = parent_target_weight if parent_target_weight > 0 else _HUNDRED
        ratio_deviation = (
            post_weight - _cp_float(target_ratio / _HUNDRED) * post_weights[sleeve.parent_key]
        )
        # The cross-multiplied convex surrogate equals the exact parent-relative drift
        # when the parent is at its target weight; the Decimal owner score uses the exact ratio.
        allocation_terms.append(cp.square(ratio_deviation / _cp_float(parent_scale)))
        band_terms.append(
            cp.pos(
                cp.abs(ratio_deviation)
                - _cp_float(band / _HUNDRED) * post_weights[sleeve.parent_key]
            )
            / _cp_float(parent_scale)
        )

    spread_cost: Any = cp.Constant(0.0)
    for index, candidate in enumerate(screen.sales):
        spread_cost += (
            _cp_float(candidate.mark_price * config.estimated_spread_bps / _BASIS_POINTS)
            * sell_vars[index]
        )
    for candidate, variable in zip(screen.buys, buy_vars, strict=True):
        spread_cost += (
            _cp_float(candidate.mark_price * config.estimated_spread_bps / _BASIS_POINTS) * variable
        )
    trading_cost_proxy = spread_cost + fee_proxy
    turnover_expr = sell_turnover + buy_turnover
    cleanup_denominator = max(1, baseline.lot_count_before + baseline.position_count_before)
    cleanup_reward = (lot_cleanup + position_cleanup) / cleanup_denominator
    objective = cp.Minimize(
        _cp_float(config.weight("objective_band_weight")) * sum(band_terms)
        + _cp_float(config.weight("objective_allocation_weight")) * sum(allocation_terms)
        + _cp_float(config.weight("objective_tax_weight")) * incremental_tax / _cp_float(total)
        + _cp_float(config.weight("objective_trading_cost_weight"))
        * trading_cost_proxy
        / _cp_float(total)
        + _cp_float(config.weight("objective_turnover_weight")) * turnover_expr / _cp_float(total)
        - _cp_float(config.weight("objective_cleanup_weight")) * cleanup_reward
    )
    problem = cp.Problem(objective, constraints)
    return problem, sell_vars, buy_vars


def _solve_problem(
    problem: cp.Problem,
    deadline: float,
    regions_remaining: int,
) -> tuple[str | None, str]:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return None, "deadline_exceeded"
    native_limit = max(0.001, min(remaining, remaining / max(1, regions_remaining)))
    try:
        problem.solve(
            solver=cp.OSQP,
            verbose=False,
            warm_start=False,
            max_iter=20000,
            eps_abs=1e-7,
            eps_rel=1e-7,
            time_limit=native_limit,
        )
        status = problem.status
        if status in {cp.OPTIMAL, cp.OPTIMAL_INACCURATE, cp.INFEASIBLE}:
            return "OSQP", status
    except cp.error.SolverError, ValueError, TypeError:
        status = "osqp_error"
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return None, "deadline_exceeded_after_osqp"
    try:
        problem.solve(solver=cp.CLARABEL, verbose=False, time_limit=remaining)
        return "CLARABEL", problem.status
    except cp.error.SolverError, ValueError, TypeError:
        return None, "solver_error"


def _canonical_legs(
    screen: _Screen,
    sell_values: tuple[Decimal, ...],
    buy_values: tuple[Decimal, ...],
) -> tuple[ConsolidatedLeg, ...]:
    allocations: dict[str, list[LotAllocation]] = defaultdict(list)
    prices: dict[str, Decimal] = {}
    for candidate, shares in zip(screen.sales, sell_values, strict=True):
        if shares <= 0:
            continue
        ticker = candidate.lot.ticker.upper()
        allocations[ticker].append(LotAllocation(candidate.lot.broker_lot_id, shares))
        prices[ticker] = candidate.execution_price
    sells: list[ConsolidatedLeg] = []
    for ticker in sorted(allocations):
        lot_allocations = tuple(sorted(allocations[ticker], key=lambda item: item.broker_lot_id))
        shares = exact_sum(row.shares for row in lot_allocations)
        sells.append(
            ConsolidatedLeg(
                leg_id=f"sell:{ticker}",
                side="SELL",
                ticker=ticker,
                shares=shares,
                estimated_unit_price_usd=prices[ticker],
                selected_lots=lot_allocations,
                sequence=0,
                group_ids=(f"sale:{ticker}",),
            )
        )
    sale_groups = tuple(leg.group_ids[0] for leg in sells)
    dependencies = tuple(leg.leg_id for leg in sells)
    buys: list[ConsolidatedLeg] = []
    for candidate, shares in zip(screen.buys, buy_values, strict=True):
        if shares <= 0:
            continue
        buys.append(
            ConsolidatedLeg(
                leg_id=f"buy:{candidate.ticker}",
                side="BUY",
                ticker=candidate.ticker,
                shares=shares,
                estimated_unit_price_usd=candidate.execution_price,
                depends_on_leg_ids=dependencies,
                sequence=1,
                group_ids=sale_groups or (f"buy:{candidate.ticker}",),
            )
        )
    return (*sells, *buys)


def _decimal_solution(value: object, maximum: Decimal, minimum: Decimal = _ZERO) -> Decimal:
    if value is None:
        return _ZERO
    shape = getattr(value, "shape", None)
    if shape is not None and shape != ():
        return _ZERO
    item = getattr(value, "item", None)
    if callable(item):
        try:
            value = item()
        except TypeError, ValueError:
            return _ZERO
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return _ZERO
    try:
        numeric = float(value)
    except OverflowError, TypeError, ValueError:
        return _ZERO
    if not math.isfinite(numeric) or numeric <= 0:
        return _ZERO
    try:
        raw = min(Decimal(str(value)), maximum)
    except ArithmeticError, TypeError, ValueError:
        return _ZERO
    if raw > _ZERO and minimum > _ZERO and maximum >= minimum:
        raw = max(raw, minimum)
    return _whole_floor(raw)


def _scaled_legs(legs: tuple[ConsolidatedLeg, ...], factor: Decimal) -> tuple[ConsolidatedLeg, ...]:
    scaled: list[ConsolidatedLeg] = []
    for leg in legs:
        if leg.side == "SELL":
            allocations = tuple(
                LotAllocation(row.broker_lot_id, _whole_floor(row.shares * factor))
                for row in leg.selected_lots
            )
            allocations = tuple(row for row in allocations if row.shares > 0)
            shares = exact_sum(row.shares for row in allocations)
            if not allocations:
                continue
            scaled.append(
                ConsolidatedLeg(
                    leg.leg_id,
                    leg.side,
                    leg.ticker,
                    shares,
                    leg.estimated_unit_price_usd,
                    allocations,
                    (),
                    leg.sequence,
                    leg.group_ids,
                )
            )
        else:
            shares = _whole_floor(leg.shares * factor)
            if shares <= 0:
                continue
            scaled.append(
                ConsolidatedLeg(
                    leg.leg_id,
                    leg.side,
                    leg.ticker,
                    shares,
                    leg.estimated_unit_price_usd,
                    (),
                    tuple(item.leg_id for item in scaled if item.side == "SELL"),
                    1,
                    leg.group_ids,
                )
            )
    return tuple(scaled)


def _repair_and_validate(
    inputs: FinancialInputs,
    legs: tuple[ConsolidatedLeg, ...],
    deadline: float,
) -> tuple[tuple[ConsolidatedLeg, ...] | None, CandidateValidation | None, int]:
    attempts = 0
    factors = (Decimal(1), Decimal("0.75"), Decimal("0.5"), Decimal("0.25"))
    for factor in factors:
        if time.monotonic() >= deadline:
            return None, None, attempts
        attempts += 1
        candidate = legs if factor == 1 else _scaled_legs(legs, factor)
        # A sub-minimum BUY is never emitted; try the independently validated sale-only remainder.
        minimum_buy = _setting_decimal(inputs, "min_buy_order_notional_usd", _ZERO) or _ZERO
        filtered = tuple(
            leg
            for leg in candidate
            if leg.side != "BUY"
            or exact_product(leg.shares, leg.estimated_unit_price_usd) >= minimum_buy
        )
        sell_ids = tuple(leg.leg_id for leg in filtered if leg.side == "SELL")
        filtered = tuple(
            ConsolidatedLeg(
                leg.leg_id,
                leg.side,
                leg.ticker,
                leg.shares,
                leg.estimated_unit_price_usd,
                leg.selected_lots,
                sell_ids if leg.side == "BUY" else (),
                1 if leg.side == "BUY" else 0,
                leg.group_ids,
            )
            for leg in filtered
        )
        validation = validate_candidate(inputs, filtered, deadline)
        if validation.accepted:
            return filtered, validation, attempts
    return None, None, attempts


def _package_versions() -> tuple[tuple[str, str], ...]:
    packages = ("cvxpy", "osqp", "clarabel")
    versions: list[tuple[str, str]] = []
    for package in packages:
        try:
            installed_version = version(package)
        except PackageNotFoundError:
            installed_version = "not-installed"
        versions.append((package, installed_version))
    return tuple(versions)


def _metadata(
    inputs: FinancialInputs,
    status: str,
    solver: str | None,
    solver_statuses: tuple[str, ...],
    started: float,
    screen_started: float,
    solve_started: float,
    regions_considered: int,
    regions_solved: int,
    region_complete: bool,
    screened_lots: int,
    selected_ids: tuple[str, ...],
    candidate_types: tuple[str, ...],
    objective: Decimal | None,
    baseline_objective: Decimal | None,
    tax_benefit: Decimal | None,
    trading_cost: Decimal | None,
    exposure_complete: bool | None,
    rounding_attempts: int,
    warnings: tuple[str, ...],
    group_priorities: tuple[TradeGroupPriority, ...] = (),
    solve_seconds: float = 0.0,
    repair_validate_rank_seconds: float = 0.0,
) -> OptimizerMetadata:
    return OptimizerMetadata(
        input_generation=inputs.source_generation,
        source_checksum=inputs.source_checksum,
        status=status,
        solver=solver,
        solver_statuses=solver_statuses,
        elapsed_seconds=max(0.0, time.monotonic() - started),
        screening_seconds=max(0.0, solve_started - screen_started),
        solve_seconds=max(0.0, solve_seconds),
        tax_regions_considered=regions_considered,
        tax_regions_solved=regions_solved,
        tax_region_search_complete=region_complete,
        integer_search_complete=False,
        screened_lot_count=screened_lots,
        selected_lot_ids=selected_ids,
        candidate_types=candidate_types,
        objective_value=objective,
        baseline_objective_value=baseline_objective,
        estimated_tax_benefit_usd=tax_benefit,
        estimated_trading_cost_usd=trading_cost,
        exposure_coverage_complete=exposure_complete,
        rounding_attempts=rounding_attempts,
        warnings=tuple(dict.fromkeys((*warnings, _INTEGER_SEARCH_INCOMPLETE))),
        implementation_version=OPTIMIZER_IMPLEMENTATION_VERSION,
        solver_versions=_package_versions(),
        trade_group_priorities=group_priorities,
        repair_validate_rank_seconds=max(0.0, repair_validate_rank_seconds),
    )


def _group_priorities(
    inputs: FinancialInputs,
    screen: _Screen,
    baseline: CandidateValidation,
    legs: tuple[ConsolidatedLeg, ...],
    deadline: float,
) -> tuple[tuple[TradeGroupPriority, ...], tuple[str, ...]]:
    baseline_components = dict(baseline.objective_components)
    if not baseline_components:
        return (), ("trade_group_priority_components_unavailable",)
    candidates_by_lot = {row.lot.broker_lot_id: row for row in screen.sales}
    group_ids_by_leg = {
        leg.leg_id: leg.group_ids or (f"{leg.side.lower()}:{leg.ticker}",) for leg in legs
    }
    roots = {group_id: group_id for ids in group_ids_by_leg.values() for group_id in ids}

    def find(group_id: str) -> str:
        root = roots[group_id]
        while root != roots[root]:
            roots[root] = roots[roots[root]]
            root = roots[root]
        roots[group_id] = root
        return root

    def union(left: str, right: str) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            roots[right_root] = left_root

    leg_ids = {leg.leg_id: leg for leg in legs}
    for leg in legs:
        ids = group_ids_by_leg[leg.leg_id]
        for group_id in ids[1:]:
            union(ids[0], group_id)
        for dependency in leg.depends_on_leg_ids:
            parent = leg_ids.get(dependency)
            if parent is not None:
                for group_id in group_ids_by_leg[parent.leg_id]:
                    union(ids[0], group_id)
    groups_by_root: dict[str, set[str]] = defaultdict(set)
    for group_id in roots:
        groups_by_root[find(group_id)].add(group_id)
    legs_by_root: dict[str, list[ConsolidatedLeg]] = defaultdict(list)
    for leg in legs:
        legs_by_root[find(group_ids_by_leg[leg.leg_id][0])].append(leg)

    ranked: list[TradeGroupPriority] = []
    warnings: list[str] = []
    components = sorted(groups_by_root.items(), key=lambda item: tuple(sorted(item[1])))
    for root, group_ids in components:
        component_legs = tuple(legs_by_root[root])
        if time.monotonic() >= deadline:
            warnings.append("trade_group_priority_deadline_incomplete")
            score = None
            component_deltas: tuple[tuple[str, Decimal], ...] = ()
            rationale = ("Independent Decimal recomputation skipped at the shared deadline.",)
        else:
            validation = validate_candidate(inputs, component_legs, deadline)
            rationale_parts = [
                "Score is the independently Decimal-recomputed no-trade objective minus the connected trade group's objective.",
                f"Connected legs: {', '.join(leg.leg_id for leg in component_legs)}.",
            ]
            group_types = sorted(
                {
                    candidate_type
                    for leg in component_legs
                    if leg.side == "SELL"
                    for allocation in leg.selected_lots
                    for candidate in (candidates_by_lot.get(allocation.broker_lot_id),)
                    if candidate is not None
                    for candidate_type in candidate.categories
                }
            )
            if group_types:
                rationale_parts.append(f"Configured candidate types: {', '.join(group_types)}.")
            buy_tickers = sorted({leg.ticker for leg in component_legs if leg.side == "BUY"})
            if buy_tickers:
                rationale_parts.append(
                    f"Funding and replacement BUYs included: {', '.join(buy_tickers)}."
                )
            if not validation.accepted:
                rationale_parts.append(
                    "Connected-group score is diagnostic, not executable: "
                    + ", ".join(validation.reasons)
                    + "."
                )
            if validation.objective_components:
                group_components = dict(validation.objective_components)
                component_deltas = tuple(
                    (key, baseline_value - group_components.get(key, baseline_value))
                    for key, baseline_value in baseline.objective_components
                )
                score = exact_sum(value for _, value in component_deltas)
            else:
                component_deltas = ()
                score = None
                rationale_parts.extend(
                    f"Connected group validation: {reason}." for reason in validation.reasons
                )
            rationale = tuple(rationale_parts)
        for group_id in sorted(group_ids):
            ranked.append(TradeGroupPriority(group_id, 0, score, component_deltas, rationale))
    ranked.sort(
        key=lambda row: (row.priority_score is None, -(row.priority_score or _ZERO), row.group_id)
    )
    priorities = tuple(
        TradeGroupPriority(
            row.group_id, rank, row.priority_score, row.objective_components, row.rationale
        )
        for rank, row in enumerate(ranked, start=1)
    )
    return priorities, tuple(warnings)


def optimize_worker(request: OptimizerRequest, computation_deadline: float) -> OptimizerResult:
    """Run Pass 1 screening and Pass 2 exact-tax-region convex relaxations before whole-share repair."""
    started = time.monotonic()
    inputs = request.inputs
    config, config_errors = read_objective_policy(inputs)
    if config is None:
        meta = _metadata(
            inputs,
            "configuration_required",
            None,
            (),
            started,
            started,
            time.monotonic(),
            0,
            0,
            False,
            0,
            (),
            (),
            None,
            None,
            None,
            None,
            None,
            0,
            config_errors,
        )
        return OptimizerResult("configuration_required", (), meta)
    if config.estimated_spread_bps >= _BASIS_POINTS:
        warnings = ("invalid_configuration:estimated_spread_bps_must_be_less_than_10000",)
        meta = _metadata(
            inputs,
            "configuration_required",
            None,
            (),
            started,
            started,
            time.monotonic(),
            0,
            0,
            False,
            0,
            (),
            (),
            None,
            None,
            None,
            None,
            None,
            0,
            warnings,
        )
        return OptimizerResult("configuration_required", (), meta)
    limits = _configured_limits(inputs)
    if limits is None:
        warnings = ("configuration_required:batch_limits_and_cash_policy",)
        meta = _metadata(
            inputs,
            "configuration_required",
            None,
            (),
            started,
            started,
            time.monotonic(),
            0,
            0,
            False,
            0,
            (),
            (),
            None,
            None,
            None,
            None,
            None,
            0,
            warnings,
        )
        return OptimizerResult("configuration_required", (), meta)
    target_errors = _validate_target_sums(inputs)
    if target_errors:
        meta = _metadata(
            inputs,
            "configuration_required",
            None,
            (),
            started,
            started,
            time.monotonic(),
            0,
            0,
            False,
            0,
            (),
            (),
            None,
            None,
            None,
            None,
            None,
            0,
            target_errors,
        )
        return OptimizerResult("configuration_required", (), meta)
    if time.monotonic() >= computation_deadline:
        meta = _metadata(
            inputs,
            "deadline_exceeded",
            None,
            (),
            started,
            started,
            time.monotonic(),
            0,
            0,
            False,
            0,
            (),
            (),
            None,
            None,
            None,
            None,
            None,
            0,
            ("computation_deadline_exceeded",),
        )
        return OptimizerResult("deadline_exceeded", (), meta)

    screen_started = time.monotonic()
    screen, screen_errors = _screen(request, config, computation_deadline)
    solve_started = time.monotonic()
    if screen is None:
        status = (
            "deadline_exceeded"
            if any("deadline" in error for error in screen_errors)
            else "infeasible"
        )
        meta = _metadata(
            inputs,
            status,
            None,
            (),
            started,
            screen_started,
            solve_started,
            0,
            0,
            False,
            0,
            (),
            (),
            None,
            None,
            None,
            None,
            None,
            0,
            screen_errors,
        )
        return OptimizerResult(status, (), meta)
    baseline_validation_started = time.monotonic()
    baseline_result = validate_candidate(inputs, (), computation_deadline)
    repair_validate_rank_seconds = max(0.0, time.monotonic() - baseline_validation_started)
    baseline_reserve_repairable = (
        not baseline_result.accepted
        and baseline_result.reasons == ("cash_reserve_breached_after_fees",)
        and baseline_result.evaluation is not None
    )
    if (
        not baseline_result.accepted and not baseline_reserve_repairable
    ) or baseline_result.objective_value is None:
        meta = _metadata(
            inputs,
            "configuration_required"
            if any("configuration_required" in reason for reason in baseline_result.reasons)
            else "infeasible",
            None,
            (),
            started,
            screen_started,
            solve_started,
            0,
            0,
            False,
            screen.screened_lot_count,
            (),
            screen.candidate_types,
            None,
            None,
            None,
            None,
            None,
            0,
            (*screen.warnings, *baseline_result.reasons),
            repair_validate_rank_seconds=repair_validate_rank_seconds,
        )
        return OptimizerResult(meta.status, (), meta)
    baseline_objective = baseline_result.objective_value
    profile = TaxProfile.from_policy_settings(inputs.policy.settings)
    if profile.tax_rates_complete:
        tax_regions = enumerate_tax_regions(profile) or ()
        region_list: tuple[TaxAffineRegion | None, ...] = tuple(tax_regions)
        region_search_needed = True
    else:
        region_list = (None,)
        region_search_needed = False
    solver_statuses: list[str] = []
    used_solvers: list[str] = []
    solved_regions = 0
    region_complete = True
    best_legs: tuple[ConsolidatedLeg, ...] = ()
    best_validation = baseline_result
    best_score = baseline_objective if baseline_result.accepted else None
    best_selected: tuple[str, ...] = ()
    rounding_attempts = 0
    solve_seconds = 0.0
    for index, region in enumerate(region_list):
        if time.monotonic() >= computation_deadline:
            region_complete = False
            solver_statuses.append("deadline_exceeded")
            break
        continuous_stage_started = time.monotonic()
        try:
            problem, sell_vars, buy_vars = _model_region(
                request, screen, config, limits, profile, region
            )
        except (ValueError, TypeError, ArithmeticError, cp.error.DCPError) as error:
            region_complete = False
            solver_statuses.append(f"model_error:{type(error).__name__}")
            solve_seconds += max(0.0, time.monotonic() - continuous_stage_started)
            continue
        solver, solver_status = _solve_problem(
            problem, computation_deadline, len(region_list) - index
        )
        solve_seconds += max(0.0, time.monotonic() - continuous_stage_started)
        solver_statuses.append(f"{solver or 'none'}:{solver_status}")
        if solver is None and "deadline" in solver_status:
            region_complete = False
            break
        if solver is not None:
            used_solvers.append(solver)
        if solver_status not in {cp.OPTIMAL, cp.OPTIMAL_INACCURATE}:
            if solver_status != cp.INFEASIBLE:
                region_complete = False
            else:
                solved_regions += 1
            continue
        solved_regions += 1
        repair_started = time.monotonic()
        sale_values = tuple(
            _decimal_solution(
                variable.value,
                candidate.maximum_shares,
                _ONE if candidate.lot.broker_lot_id in (request.sell_lot_ids or ()) else _ZERO,
            )
            for variable, candidate in zip(sell_vars, screen.sales, strict=True)
        )
        buy_values = tuple(
            _decimal_solution(variable.value, candidate.maximum_shares)
            for variable, candidate in zip(buy_vars, screen.buys, strict=True)
        )
        proposed = _canonical_legs(screen, sale_values, buy_values)
        repaired, validation, attempts = _repair_and_validate(
            inputs, proposed, computation_deadline
        )
        repair_validate_rank_seconds += max(0.0, time.monotonic() - repair_started)
        rounding_attempts += attempts
        if repaired is not None and request.sell_lot_ids is not None:
            actual_lot_ids = {
                allocation.broker_lot_id
                for leg in repaired
                if leg.side == "SELL"
                for allocation in leg.selected_lots
            }
            if actual_lot_ids != set(request.sell_lot_ids):
                repaired = None
                validation = None
                region_complete = False
                solver_statuses.append("selected_lot_set_mismatch")
        if (
            repaired is None
            or validation is None
            or not validation.accepted
            or validation.objective_value is None
        ):
            continue
        if best_score is None or validation.objective_value < best_score - Decimal("0.0000000001"):
            best_legs = repaired
            best_validation = validation
            best_score = validation.objective_value
            best_selected = tuple(
                sorted(
                    allocation.broker_lot_id
                    for leg in repaired
                    if leg.side == "SELL"
                    for allocation in leg.selected_lots
                )
            )

    warnings = list(screen.warnings)
    if not baseline_result.accepted:
        warnings.extend(baseline_result.reasons)
    if not profile.tax_rates_complete:
        warnings.append("tax_profile_incomplete_estimated_benefit_null")
    if not region_search_needed:
        warnings.append("tax_regions_not_enumerated_incomplete_rates")
    if not region_complete:
        warnings.append("tax_region_search_incomplete_deadline_or_solver")

    if not best_legs:
        observed_statuses = tuple(status.rsplit(":", 1)[-1] for status in solver_statuses)
        if time.monotonic() >= computation_deadline:
            status = "deadline_exceeded"
        elif not region_complete:
            status = "search_incomplete"
        elif observed_statuses and all(value == cp.INFEASIBLE for value in observed_statuses):
            status = "infeasible"
        elif baseline_result.accepted:
            status = "no_trade"
        else:
            status = "search_incomplete"
        meta = _metadata(
            inputs,
            status,
            "+".join(sorted(set(used_solvers))) or None,
            tuple(solver_statuses),
            started,
            screen_started,
            solve_started,
            len(region_list) if region_search_needed else 0,
            solved_regions,
            region_complete,
            screen.screened_lot_count,
            (),
            screen.candidate_types,
            baseline_objective,
            baseline_objective,
            None if not profile.tax_rates_complete else best_validation.estimated_tax_benefit_usd,
            best_validation.estimated_trading_cost_usd,
            best_validation.exposure_coverage.complete
            if best_validation.exposure_coverage
            else None,
            rounding_attempts,
            tuple(warnings),
            solve_seconds=solve_seconds,
            repair_validate_rank_seconds=repair_validate_rank_seconds,
        )
        return OptimizerResult(status, (), meta)
    group_priority_started = time.monotonic()
    group_priorities, group_priority_warnings = _group_priorities(
        inputs, screen, baseline_result, best_legs, computation_deadline
    )
    repair_validate_rank_seconds += max(0.0, time.monotonic() - group_priority_started)
    warnings.extend(group_priority_warnings)

    if time.monotonic() >= computation_deadline:
        warnings.append("computation_deadline_exceeded")
        meta = _metadata(
            inputs,
            "deadline_exceeded",
            "+".join(sorted(set(used_solvers))) or None,
            tuple(solver_statuses),
            started,
            screen_started,
            solve_started,
            len(region_list) if region_search_needed else 0,
            solved_regions,
            region_complete,
            screen.screened_lot_count,
            (),
            screen.candidate_types,
            None,
            baseline_objective,
            None,
            None,
            None,
            rounding_attempts,
            tuple(warnings),
            group_priorities,
            solve_seconds=solve_seconds,
            repair_validate_rank_seconds=repair_validate_rank_seconds,
        )
        return OptimizerResult("deadline_exceeded", (), meta)

    status = "ready"
    meta = _metadata(
        inputs,
        status,
        "+".join(sorted(set(used_solvers))) or None,
        tuple(solver_statuses),
        started,
        screen_started,
        solve_started,
        len(region_list) if region_search_needed else 0,
        solved_regions,
        region_complete,
        screen.screened_lot_count,
        best_selected,
        screen.candidate_types,
        best_validation.objective_value,
        baseline_objective,
        best_validation.estimated_tax_benefit_usd,
        best_validation.estimated_trading_cost_usd,
        best_validation.exposure_coverage.complete if best_validation.exposure_coverage else None,
        rounding_attempts,
        (*warnings, *best_validation.warnings),
        group_priorities,
        solve_seconds=solve_seconds,
        repair_validate_rank_seconds=repair_validate_rank_seconds,
    )
    return OptimizerResult(status, best_legs, meta)


def resolve_subset(
    request: OptimizerRequest,
    selected_sell_lot_ids: tuple[str, ...],
    deadline: float,
) -> OptimizerResult:
    """Fast Pass-2 re-solve restricted to the user-selected source lot IDs."""
    return optimize_worker(OptimizerRequest(request.inputs, tuple(selected_sell_lot_ids)), deadline)
