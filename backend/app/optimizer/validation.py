"""Independent, Decimal-based owner validation for optimizer worker baskets.

The optimizer never supplies account totals, realized gains, wash-sale results, or objective values
trusted by this module. Every value is recomputed from the frozen FinancialInputs and canonical legs.
"""
from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.domain.decimal_math import exact_difference, exact_product, exact_sum, percentage
from app.domain.exposure import ExposureCoverage, aggregate_lookthrough_exposure
from app.domain.financial_inputs import FinancialInputs
from app.domain.portfolio_accounting import (
    BasketValidationError,
    ConsolidatedLeg,
    PortfolioEvaluation,
    evaluate_portfolio,
)
from app.domain.tax import TaxEvaluation, TaxProfile, evaluate_tax
from app.domain.wash import ProposedBuy, ProposedLotSale, WashSaleAssessment, assess_wash_sales

_ZERO = Decimal(0)
_HUNDRED = Decimal(100)
_OBJECTIVE_WEIGHT_KEYS = (
    "objective_band_weight",
    "objective_allocation_weight",
    "objective_tax_weight",
    "objective_trading_cost_weight",
    "objective_turnover_weight",
    "objective_cleanup_weight",
)
_REQUIRED_DECIMAL_KEYS = (*_OBJECTIVE_WEIGHT_KEYS, "estimated_spread_bps", "estimated_fee_per_order_usd")


@dataclass(frozen=True, slots=True)
class ObjectivePolicy:
    weights: tuple[tuple[str, Decimal], ...]
    estimated_spread_bps: Decimal
    estimated_fee_per_order_usd: Decimal

    def weight(self, name: str) -> Decimal:
        return dict(self.weights)[name]


@dataclass(frozen=True, slots=True)
class CandidateValidation:
    accepted: bool
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    evaluation: PortfolioEvaluation | None
    tax: TaxEvaluation | None
    wash_assessments: tuple[WashSaleAssessment, ...]
    exposure_coverage: ExposureCoverage | None
    objective_value: Decimal | None
    estimated_tax_benefit_usd: Decimal | None
    estimated_trading_cost_usd: Decimal | None
    buy_wash_assessments: tuple[object, ...] = ()
    objective_components: tuple[tuple[str, Decimal], ...] = ()


def read_objective_policy(inputs: FinancialInputs) -> tuple[ObjectivePolicy | None, tuple[str, ...]]:
    """Read required objective/cost settings as exact Decimals, without adding policy defaults."""
    settings = inputs.policy.settings
    accessor = getattr(settings, "decimal", None)
    if not callable(accessor):
        accessor = getattr(settings, "get", None)
    if not callable(accessor):
        return None, ("configuration_required:typed_policy_settings_accessor",)
    values: dict[str, Decimal] = {}
    missing: list[str] = []
    invalid: list[str] = []
    for key in _REQUIRED_DECIMAL_KEYS:
        try:
            value = accessor(key)
        except (KeyError, TypeError, ValueError, AttributeError):
            value = None
        if value is None:
            missing.append(key)
        elif not isinstance(value, Decimal) or not value.is_finite() or value < 0:
            invalid.append(key)
        else:
            values[key] = value
    if missing or invalid:
        reasons = (
            *(f"configuration_required:{key}" for key in missing),
            *(f"invalid_configuration:{key}" for key in invalid),
        )
        return None, reasons
    weight_sum = exact_sum(values[key] for key in _OBJECTIVE_WEIGHT_KEYS)
    if weight_sum <= 0:
        return None, ("configuration_required:positive_objective_weight_sum",)
    normalized = tuple((key, values[key] / weight_sum) for key in _OBJECTIVE_WEIGHT_KEYS)
    return ObjectivePolicy(normalized, values["estimated_spread_bps"], values["estimated_fee_per_order_usd"]), ()


def _setting_decimal(inputs: FinancialInputs, key: str, default: Decimal | None = None) -> Decimal | None:
    value = inputs.policy.settings.get(key, default)
    if value is None:
        return None
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"invalid decimal policy setting: {key}")
    return value


def _setting_int(inputs: FinancialInputs, key: str) -> int | None:
    value = inputs.policy.settings.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _target_rows(inputs: FinancialInputs, evaluation: PortfolioEvaluation) -> tuple[tuple[str, Decimal, Decimal], ...]:
    sleeves = {row.key: row for row in inputs.policy.allocation.sleeves if row.enabled}
    targets: list[tuple[str, Decimal, Decimal]] = []
    for row in evaluation.allocation.target.sleeves:
        sleeve = sleeves[row.sleeve_key]
        band = sleeve.drift_band_pp or _ZERO
        if sleeve.parent_key is not None:
            parent_target = next(
                (item.target_whole_portfolio_pct for item in evaluation.allocation.target.sleeves if item.sleeve_key == sleeve.parent_key),
                _ZERO,
            )
            band = exact_product(band, parent_target) / _HUNDRED
        target = row.target_whole_portfolio_pct

        targets.append((row.sleeve_key, target, band))
    return tuple(targets)


def _distance_sum(
    inputs: FinancialInputs,
    evaluation: PortfolioEvaluation,
) -> tuple[Decimal, Decimal, tuple[str, ...]]:
    targets = _target_rows(inputs, evaluation)
    current_values = dict(evaluation.current.sleeve_values_usd)
    proposed_values = dict(evaluation.proposed.sleeve_values_usd)
    total_before = evaluation.current.portfolio_total_usd
    total_after = evaluation.proposed.portfolio_total_usd
    if total_before <= 0 or total_after <= 0:
        return _ZERO, _ZERO, ("invalid_portfolio_total",)
    allocation_distance: list[Decimal] = []
    band_distance: list[Decimal] = []
    errors: list[str] = []
    for key, target, band in targets:
        current = percentage(current_values.get(key, _ZERO), total_before)
        proposed = percentage(proposed_values.get(key, _ZERO), total_after)
        current_distance = abs(current - target)
        proposed_distance = abs(proposed - target)
        allocation_distance.append(proposed_distance / _HUNDRED)
        band_distance.append(max(_ZERO, proposed_distance - band) / _HUNDRED)
        allowed_distance = max(current_distance, band)
        if proposed_distance > allowed_distance:
            errors.append(f"sleeve_drift_worsened:{key}")
    return exact_sum(allocation_distance), exact_sum(band_distance), tuple(errors)


def _cash_and_limits(
    inputs: FinancialInputs,
    legs: Sequence[ConsolidatedLeg],
    evaluation: PortfolioEvaluation,
    config: ObjectivePolicy,
) -> tuple[list[str], Decimal, Decimal]:
    reasons: list[str] = []
    sells = tuple(leg for leg in legs if leg.side == "SELL")
    buys = tuple(leg for leg in legs if leg.side == "BUY")
    max_tickers = _setting_int(inputs, "max_sell_tickers_per_batch")
    max_lots = _setting_int(inputs, "max_sell_lots_per_batch")
    max_orders = _setting_int(inputs, "max_total_orders_per_batch")
    if max_tickers is None or max_tickers <= 0:
        reasons.append("configuration_required:max_sell_tickers_per_batch")
    if max_lots is None or max_lots <= 0:
        reasons.append("configuration_required:max_sell_lots_per_batch")
    if max_orders is None or max_orders <= 0:
        reasons.append("configuration_required:max_total_orders_per_batch")
    if max_tickers is not None and len(sells) > max_tickers:
        reasons.append("max_sell_tickers_exceeded")
    sell_lot_count = sum(len(leg.selected_lots) for leg in sells)
    if max_lots is not None and sell_lot_count > max_lots:
        reasons.append("max_sell_lots_exceeded")
    if max_orders is not None and len(legs) > max_orders:
        reasons.append("max_total_orders_exceeded")

    fee_total = exact_product(config.estimated_fee_per_order_usd, Decimal(len(legs)))
    net_cash = exact_difference(evaluation.proposed.cash_usd, fee_total)
    cash_reserve = _setting_decimal(inputs, "cash_reserve_usd", _ZERO)
    if cash_reserve is None or cash_reserve < 0:
        reasons.append("invalid_cash_reserve")
    elif net_cash < cash_reserve:
        reasons.append("cash_reserve_breached_after_fees")

    settled_available = inputs.account.settled_buying_power_usd
    order_by_sequence = sorted(legs, key=lambda leg: (leg.sequence, leg.leg_id))
    for leg in order_by_sequence:
        notional = exact_product(leg.shares, leg.estimated_unit_price_usd)
        settled_available = exact_difference(settled_available, config.estimated_fee_per_order_usd)
        if leg.side == "SELL":
            settled_available = exact_sum((settled_available, notional))
        else:
            settled_available = exact_difference(settled_available, notional)
        if settled_available < 0:
            reasons.append(f"settled_buying_power_exceeded:{leg.ticker}")
            break

    turnover = exact_sum(exact_product(leg.shares, leg.estimated_unit_price_usd) for leg in legs)
    turnover_pct = _setting_decimal(inputs, "max_batch_turnover_pct")
    if turnover_pct is None or turnover_pct < 0 or turnover_pct > _HUNDRED:
        reasons.append("invalid_max_batch_turnover_pct")
    elif evaluation.current.portfolio_total_usd <= 0 or turnover > exact_product(
        evaluation.current.portfolio_total_usd, turnover_pct / _HUNDRED
    ):
        reasons.append("max_batch_turnover_exceeded")

    minimum_buy = _setting_decimal(inputs, "min_buy_order_notional_usd", _ZERO)
    if minimum_buy is None or minimum_buy < 0:
        reasons.append("invalid_min_buy_order_notional_usd")
    else:
        for leg in buys:
            if exact_product(leg.shares, leg.estimated_unit_price_usd) < minimum_buy:
                reasons.append(f"buy_order_below_minimum:{leg.ticker}")

    allowed = {
        row.ticker.upper()
        for row in inputs.policy.allocation.allowed_securities
        if row.enabled
    }
    prefer_etfs = inputs.policy.settings.get("prefer_etf_buys", False) is True
    for leg in buys:
        if leg.ticker.upper() not in allowed:
            reasons.append(f"buy_not_in_enabled_allowed_securities:{leg.ticker}")
        security = inputs.security_for(leg.ticker)
        if prefer_etfs and security is not None and security.identity.asset_type.upper() not in {"ETF", "MUTUAL_FUND"}:
            reasons.append(f"buy_not_preferred_etf:{leg.ticker}")

    positive_st: list[Decimal] = []
    positive_lt: list[Decimal] = []
    for effect in evaluation.lot_effects:
        if effect.realized_pl_usd > 0:
            (positive_st if effect.term == "ST" else positive_lt).append(effect.realized_pl_usd)
    gross_st = exact_sum(positive_st)
    gross_lt = exact_sum(positive_lt)
    gross_gain = exact_sum((gross_st, gross_lt))
    for key, actual in (("gain_budget_usd", gross_gain), ("st_gain_limit_usd", gross_st), ("lt_gain_limit_usd", gross_lt)):
        limit = _setting_decimal(inputs, key)
        if limit is not None and (limit < 0 or actual > limit):
            reasons.append(f"{key}_exceeded")

    tax_profile = TaxProfile.from_policy_settings(inputs.policy.settings)
    tax = evaluate_tax(tax_profile, evaluation.realized_st_usd, evaluation.realized_lt_usd)
    max_tax = _setting_decimal(inputs, "max_incremental_tax_cost_usd")
    if tax.incremental_tax_cost_usd is None:
        if max_tax is not None and legs:
            reasons.append("tax_cost_unverifiable_with_incomplete_rates")
        if gross_gain > 0:
            reasons.append("positive_gain_unverifiable_with_incomplete_rates")
    elif max_tax is not None and tax.incremental_tax_cost_usd > max_tax:
        reasons.append("max_incremental_tax_cost_exceeded")

    return reasons, turnover, fee_total


def _wash_validation(
    inputs: FinancialInputs,
    legs: Sequence[ConsolidatedLeg],
    evaluation: PortfolioEvaluation,
) -> tuple[list[str], tuple[WashSaleAssessment, ...], tuple[object, ...]]:
    sales: list[ProposedLotSale] = []
    group_by_lot = {
        allocation.broker_lot_id: (leg, allocation)
        for leg in legs
        if leg.side == "SELL"
        for allocation in leg.selected_lots
    }
    for effect in evaluation.lot_effects:
        leg, allocation = group_by_lot[effect.broker_lot_id]
        sales.append(
            ProposedLotSale(
                ticker=effect.ticker,
                broker_lot_id=effect.broker_lot_id,
                shares=allocation.shares,
                realized_pl_usd=effect.realized_pl_usd,
                trade_group_id=(leg.group_ids[0] if leg.group_ids else f"sale:{effect.ticker}"),
                sale_date=inputs.proposed_trade_date,
            )
        )
    buys = tuple(
        ProposedBuy(
            ticker=leg.ticker,
            shares=leg.shares,
            trade_group_id=(leg.group_ids[0] if leg.group_ids else f"buy:{leg.ticker}"),
            buy_date=inputs.proposed_trade_date,
        )
        for leg in legs
        if leg.side == "BUY"
    )
    sale_assessments = assess_wash_sales(inputs, tuple(sales), buys)
    reasons = [
        f"wash_sale_ineligible:{assessment.ticker}:{assessment.broker_lot_id}:{reason}"
        for assessment in sale_assessments
        if not assessment.eligible
        for reason in assessment.reasons
    ]
    buy_assessments: tuple[object, ...] = ()
    if buys:
        # The supplemental domain API is deliberately required; never infer historical realized
        # losses from transaction proceeds or silently accept an unchecked buy-only basket.
        from app.domain import wash as wash_module

        assess_buys = getattr(wash_module, "assess_proposed_buys", None)
        if not callable(assess_buys):
            reasons.append("buy_wash_validation_unavailable")
        else:
            buy_assessments = tuple(assess_buys(inputs, buys, tuple(sales)))
            for assessment in buy_assessments:
                if getattr(assessment, "eligible", False) is not True:
                    ticker = getattr(assessment, "ticker", "unknown")
                    assessment_reasons = getattr(assessment, "reasons", ())
                    if assessment_reasons:
                        reasons.extend(f"buy_wash_sale_ineligible:{ticker}:{reason}" for reason in assessment_reasons)
                    else:
                        reasons.append(f"buy_wash_sale_ineligible:{ticker}")
    return reasons, sale_assessments, buy_assessments


def _exposure_validation(
    inputs: FinancialInputs,
    legs: Sequence[ConsolidatedLeg],
) -> tuple[list[str], ExposureCoverage | None]:
    needs_exposure = False
    for leg in legs:
        security = inputs.security_for(leg.ticker)
        if security is None or security.identity.asset_type.upper() != "EQUITY":
            needs_exposure = True
            break
    if not needs_exposure:
        return [], None
    try:
        aggregate = aggregate_lookthrough_exposure(inputs)
    except (ValueError, TypeError, ArithmeticError):
        return ["exposure_coverage_unavailable"], None
    coverage = aggregate.coverage
    reasons: list[str] = []
    if coverage.complete is not True:
        reasons.append("incomplete_or_unknown_exposure_coverage")
    # Require each newly purchased non-equity security to have its own usable unit-notional
    # look-through, not just a complete aggregate for the holdings that happen to be present.
    for leg in legs:
        if leg.side != "BUY":
            continue
        security = inputs.security_for(leg.ticker)
        if security is None or security.identity.asset_type.upper() == "EQUITY":
            continue
        try:
            candidate = aggregate_lookthrough_exposure(inputs, tickers=(leg.ticker,))
        except (ValueError, TypeError, ArithmeticError):
            reasons.append(f"buy_exposure_unavailable:{leg.ticker}")
            continue
        if candidate.coverage.complete is not True or not candidate.values:
            reasons.append(f"buy_exposure_incomplete:{leg.ticker}")
    return reasons, coverage


def _objective(
    inputs: FinancialInputs,
    evaluation: PortfolioEvaluation,
    tax: TaxEvaluation,
    turnover: Decimal,
    trading_cost: Decimal,
    config: ObjectivePolicy,
) -> tuple[Decimal, tuple[str, ...], tuple[tuple[str, Decimal], ...]]:
    allocation_drift, band_slack, drift_reasons = _distance_sum(inputs, evaluation)
    portfolio_value = evaluation.current.portfolio_total_usd
    if portfolio_value <= 0:
        return _ZERO, ("invalid_portfolio_total",), ()
    tax_cost = tax.incremental_tax_cost_usd or _ZERO
    cost_ratio = trading_cost / portfolio_value
    turnover_ratio = turnover / portfolio_value
    cleanup_count = (
        evaluation.position_count_before
        - evaluation.position_count_after
        + evaluation.lot_count_before
        - evaluation.lot_count_after
    )
    cleanup_denominator = max(1, evaluation.position_count_before + evaluation.lot_count_before)
    cleanup_reward = Decimal(cleanup_count) / Decimal(cleanup_denominator)
    components = (
        ("objective_band_weight", exact_product(config.weight("objective_band_weight"), band_slack)),
        ("objective_allocation_weight", exact_product(config.weight("objective_allocation_weight"), allocation_drift)),
        ("objective_tax_weight", exact_product(config.weight("objective_tax_weight"), tax_cost / portfolio_value)),
        ("objective_trading_cost_weight", exact_product(config.weight("objective_trading_cost_weight"), cost_ratio)),
        ("objective_turnover_weight", exact_product(config.weight("objective_turnover_weight"), turnover_ratio)),
        ("objective_cleanup_weight", exact_product(config.weight("objective_cleanup_weight"), cleanup_reward.copy_negate())),
    )
    return exact_sum(value for _, value in components), drift_reasons, components


def _trading_cost(
    config: ObjectivePolicy,
    legs: Sequence[ConsolidatedLeg],
    inputs: FinancialInputs,
) -> Decimal:
    spread_costs: list[Decimal] = []
    for leg in legs:
        quote = inputs.quote_for(leg.ticker)
        mark = None
        if quote is not None and quote.bid_usd is not None and quote.ask_usd is not None:
            mark = (quote.bid_usd + quote.ask_usd) / Decimal(2)
        elif quote is not None:
            mark = quote.last_usd
        if mark is None:
            mark = leg.estimated_unit_price_usd
        spread_costs.append(exact_product(exact_product(leg.shares, mark), config.estimated_spread_bps / Decimal(10000)))
    spread = exact_sum(spread_costs)
    fees = exact_product(config.estimated_fee_per_order_usd, Decimal(len(legs)))
    return exact_sum((spread, fees))


def validate_candidate(
    inputs: FinancialInputs,
    legs: Sequence[ConsolidatedLeg],
    deadline: float | None = None,
) -> CandidateValidation:
    """Recompute and validate a basket using only owner-frozen input and Decimal domain logic."""
    if deadline is not None and time.monotonic() >= deadline:
        return CandidateValidation(False, ("validation_deadline_exceeded",), (), None, None, (), None, None, None, None)
    config, config_errors = read_objective_policy(inputs)
    if config is None:
        return CandidateValidation(False, config_errors, (), None, None, (), None, None, None, None)
    errors: list[str] = []
    warnings: list[str] = []
    normalized_legs = tuple(legs)
    for leg in normalized_legs:
        if leg.shares != leg.shares.to_integral_value():
            errors.append(f"fractional_{leg.side.lower()}_shares:{leg.ticker}")
        if leg.side == "SELL":
            for allocation in leg.selected_lots:
                if allocation.shares != allocation.shares.to_integral_value():
                    errors.append(f"fractional_sell_lot_shares:{allocation.broker_lot_id}")
    if deadline is not None and time.monotonic() >= deadline:
        errors.append("validation_deadline_exceeded")
    if errors:
        return CandidateValidation(False, tuple(errors), tuple(warnings), None, None, (), None, None, None, None)
    try:
        evaluation = evaluate_portfolio(inputs, normalized_legs)
    except BasketValidationError as error:
        return CandidateValidation(False, (f"accounting:{error.code}",), tuple(warnings), None, None, (), None, None, None, None)

    if deadline is not None and time.monotonic() >= deadline:
        return CandidateValidation(False, ("validation_deadline_exceeded",), (), evaluation, None, (), None, None, None, None)
    limit_errors, turnover, _fee_total = _cash_and_limits(inputs, normalized_legs, evaluation, config)
    errors.extend(limit_errors)
    tax = evaluate_tax(
        TaxProfile.from_policy_settings(inputs.policy.settings),
        evaluation.realized_st_usd,
        evaluation.realized_lt_usd,
    )
    if deadline is not None and time.monotonic() >= deadline:
        errors.append("validation_deadline_exceeded")
    wash_errors, wash_assessments, buy_wash_assessments = _wash_validation(inputs, normalized_legs, evaluation)
    errors.extend(wash_errors)
    exposure_errors, exposure_coverage = _exposure_validation(inputs, normalized_legs)
    errors.extend(exposure_errors)
    trading_cost = _trading_cost(config, normalized_legs, inputs)
    objective_value, drift_errors, objective_components = _objective(inputs, evaluation, tax, turnover, trading_cost, config)
    errors.extend(drift_errors)
    if tax.estimated_tax_benefit_usd is None:
        warnings.append("tax_profile_incomplete_estimated_benefit_null")
    if exposure_coverage is not None:
        warnings.append("exposure_coverage_only_no_tracking_error_inferred")
    return CandidateValidation(
        accepted=not errors,
        reasons=tuple(dict.fromkeys(errors)),
        warnings=tuple(dict.fromkeys(warnings)),
        evaluation=evaluation,
        tax=tax,
        wash_assessments=wash_assessments,
        exposure_coverage=exposure_coverage,
        objective_value=objective_value,
        estimated_tax_benefit_usd=tax.estimated_tax_benefit_usd,
        estimated_trading_cost_usd=trading_cost,
        buy_wash_assessments=buy_wash_assessments,
        objective_components=objective_components,
    )
