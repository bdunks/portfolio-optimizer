from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from app.domain.decimal_math import exact_difference, exact_product, exact_sum
from app.domain.financial_inputs import PolicySettings

_ZERO = Decimal(0)
_ONE = Decimal(1)
_DEFAULT_RETAINED_LOSS = Decimal(3000)
_DEFAULT_ORDINARY_DEDUCTION = Decimal(3000)
_DEFAULT_CARRYFORWARD_DISCOUNT = Decimal("0.50")


def _finite_decimal(value: object, name: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be a Decimal")
    if not value.is_finite():
        raise ValueError(f"{name} must be finite")
    return value


def _affine_value(
    st_coefficient: Decimal,
    lt_coefficient: Decimal,
    constant: Decimal,
    short_term_net_usd: Decimal,
    long_term_net_usd: Decimal,
) -> Decimal:
    return exact_sum(
        (
            exact_product(st_coefficient, short_term_net_usd),
            exact_product(lt_coefficient, long_term_net_usd),
            constant,
        )
    )


@dataclass(frozen=True, slots=True)
class TaxProfile:
    """Immutable, validated tax assumptions and pre-trade realized tax positions."""

    short_term_tax_rate: Decimal | None = None
    long_term_tax_rate: Decimal | None = None
    st_loss_carryforward_usd: Decimal = _ZERO
    lt_loss_carryforward_usd: Decimal = _ZERO
    ytd_realized_st_usd: Decimal = _ZERO
    ytd_realized_lt_usd: Decimal = _ZERO
    target_retained_net_loss_usd: Decimal = _DEFAULT_RETAINED_LOSS
    ordinary_income_deduction_limit_usd: Decimal = _DEFAULT_ORDINARY_DEDUCTION
    carryforward_loss_discount_factor: Decimal = _DEFAULT_CARRYFORWARD_DISCOUNT

    def __post_init__(self) -> None:
        for name in ("short_term_tax_rate", "long_term_tax_rate"):
            rate = getattr(self, name)
            if rate is not None:
                _finite_decimal(rate, name)
                if not _ZERO <= rate <= _ONE:
                    raise ValueError(f"{name} must be between 0 and 1")
        if (
            self.short_term_tax_rate is not None
            and self.long_term_tax_rate is not None
            and self.short_term_tax_rate < self.long_term_tax_rate
        ):
            raise ValueError("short_term_tax_rate must be at least long_term_tax_rate")

        for name in (
            "st_loss_carryforward_usd",
            "lt_loss_carryforward_usd",
            "ytd_realized_st_usd",
            "ytd_realized_lt_usd",
            "target_retained_net_loss_usd",
            "ordinary_income_deduction_limit_usd",
            "carryforward_loss_discount_factor",
        ):
            _finite_decimal(getattr(self, name), name)
        if self.st_loss_carryforward_usd < 0 or self.lt_loss_carryforward_usd < 0:
            raise ValueError("loss carryforwards cannot be negative")
        if self.target_retained_net_loss_usd < 0:
            raise ValueError("target_retained_net_loss_usd cannot be negative")
        if self.ordinary_income_deduction_limit_usd < 0:
            raise ValueError("ordinary_income_deduction_limit_usd cannot be negative")
        if not _ZERO <= self.carryforward_loss_discount_factor <= _ONE:
            raise ValueError("carryforward_loss_discount_factor must be between 0 and 1")

    @classmethod
    def from_policy_settings(cls, settings: PolicySettings) -> TaxProfile:
        """Build a tax profile from immutable policy settings, applying documented defaults."""
        values = dict(settings.values)

        def required_setting(name: str, default: Decimal) -> Decimal:
            if name not in values:
                return default
            return _finite_decimal(values[name], name)

        def optional_setting(name: str) -> Decimal | None:
            if name not in values or values[name] is None:
                return None
            return _finite_decimal(values[name], name)

        return cls(
            short_term_tax_rate=optional_setting("short_term_tax_rate"),
            long_term_tax_rate=optional_setting("long_term_tax_rate"),
            st_loss_carryforward_usd=required_setting("st_loss_carryforward_usd", _ZERO),
            lt_loss_carryforward_usd=required_setting("lt_loss_carryforward_usd", _ZERO),
            ytd_realized_st_usd=required_setting("ytd_realized_st_usd", _ZERO),
            ytd_realized_lt_usd=required_setting("ytd_realized_lt_usd", _ZERO),
            target_retained_net_loss_usd=required_setting(
                "target_retained_net_loss_usd", _DEFAULT_RETAINED_LOSS
            ),
            ordinary_income_deduction_limit_usd=required_setting(
                "ordinary_income_deduction_limit_usd", _DEFAULT_ORDINARY_DEDUCTION
            ),
            carryforward_loss_discount_factor=required_setting(
                "carryforward_loss_discount_factor", _DEFAULT_CARRYFORWARD_DISCOUNT
            ),
        )

    @property
    def tax_rates_complete(self) -> bool:
        return self.short_term_tax_rate is not None and self.long_term_tax_rate is not None

    @property
    def baseline_st_net_usd(self) -> Decimal:
        return exact_difference(self.ytd_realized_st_usd, self.st_loss_carryforward_usd)

    @property
    def baseline_lt_net_usd(self) -> Decimal:
        return exact_difference(self.ytd_realized_lt_usd, self.lt_loss_carryforward_usd)

    @property
    def carryforward_tax_rate(self) -> Decimal | None:
        if self.long_term_tax_rate is None:
            return None
        return exact_product(self.carryforward_loss_discount_factor, self.long_term_tax_rate)


@dataclass(frozen=True, slots=True)
class TaxEvaluation:
    """Exact realized deltas and, when rates are complete, their incremental tax value."""

    realized_st_usd: Decimal
    realized_lt_usd: Decimal
    baseline_st_net_usd: Decimal
    baseline_lt_net_usd: Decimal
    post_trade_st_net_usd: Decimal
    post_trade_lt_net_usd: Decimal
    baseline_tax_usd: Decimal | None
    post_trade_tax_usd: Decimal | None
    incremental_tax_cost_usd: Decimal | None
    estimated_tax_benefit_usd: Decimal | None
    status: Literal["tax_profile_complete", "tax_profile_incomplete"]


def tax_value(
    profile: TaxProfile,
    short_term_net_usd: Decimal,
    long_term_net_usd: Decimal,
) -> Decimal | None:
    """Return the exact configured T(S, L), or None when either marginal rate is absent."""
    short_term_net_usd = _finite_decimal(short_term_net_usd, "short_term_net_usd")
    long_term_net_usd = _finite_decimal(long_term_net_usd, "long_term_net_usd")
    if not profile.tax_rates_complete:
        return None

    st_rate = profile.short_term_tax_rate
    lt_rate = profile.long_term_tax_rate
    cf_rate = profile.carryforward_tax_rate
    assert st_rate is not None
    assert lt_rate is not None
    assert cf_rate is not None

    if short_term_net_usd >= 0 and long_term_net_usd >= 0:
        return exact_sum(
            (
                exact_product(st_rate, short_term_net_usd),
                exact_product(lt_rate, long_term_net_usd),
            )
        )

    net_capital = exact_sum((short_term_net_usd, long_term_net_usd))
    if net_capital >= 0:
        if short_term_net_usd > 0 and long_term_net_usd < 0:
            return exact_product(st_rate, net_capital)
        if long_term_net_usd > 0 and short_term_net_usd < 0:
            return exact_product(lt_rate, net_capital)
        # The only remaining net-gain boundary is a zero bucket, where both formulations agree.
        return exact_sum(
            (
                exact_product(st_rate, short_term_net_usd),
                exact_product(lt_rate, long_term_net_usd),
            )
        )

    net_loss = net_capital.copy_negate()
    ordinary_loss = min(net_loss, profile.ordinary_income_deduction_limit_usd)
    retained_loss = min(net_loss, profile.target_retained_net_loss_usd)
    carryforward_loss = max(_ZERO, exact_difference(retained_loss, ordinary_loss))
    tax_credit = exact_sum(
        (
            exact_product(st_rate, ordinary_loss),
            exact_product(cf_rate, carryforward_loss),
        )
    )
    return tax_credit.copy_negate()


def evaluate_tax(
    profile: TaxProfile,
    realized_st_usd: Decimal,
    realized_lt_usd: Decimal,
) -> TaxEvaluation:
    """Evaluate proposed realized deltas against the policy YTD/carryforward baseline."""
    realized_st_usd = _finite_decimal(realized_st_usd, "realized_st_usd")
    realized_lt_usd = _finite_decimal(realized_lt_usd, "realized_lt_usd")
    baseline_st = profile.baseline_st_net_usd
    baseline_lt = profile.baseline_lt_net_usd
    post_st = exact_sum((baseline_st, realized_st_usd))
    post_lt = exact_sum((baseline_lt, realized_lt_usd))
    baseline_tax = tax_value(profile, baseline_st, baseline_lt)
    post_tax = tax_value(profile, post_st, post_lt)
    incremental_cost = (
        exact_difference(post_tax, baseline_tax)
        if baseline_tax is not None and post_tax is not None
        else None
    )
    benefit = incremental_cost.copy_negate() if incremental_cost is not None else None
    return TaxEvaluation(
        realized_st_usd=realized_st_usd,
        realized_lt_usd=realized_lt_usd,
        baseline_st_net_usd=baseline_st,
        baseline_lt_net_usd=baseline_lt,
        post_trade_st_net_usd=post_st,
        post_trade_lt_net_usd=post_lt,
        baseline_tax_usd=baseline_tax,
        post_trade_tax_usd=post_tax,
        incremental_tax_cost_usd=incremental_cost,
        estimated_tax_benefit_usd=benefit,
        status="tax_profile_complete" if profile.tax_rates_complete else "tax_profile_incomplete",
    )


@dataclass(frozen=True, slots=True)
class LinearInequality:
    """A closed linear half-plane: a*S + b*L <= bound."""

    short_term_coefficient: Decimal
    long_term_coefficient: Decimal
    upper_bound_usd: Decimal

    def __post_init__(self) -> None:
        _finite_decimal(self.short_term_coefficient, "short_term_coefficient")
        _finite_decimal(self.long_term_coefficient, "long_term_coefficient")
        _finite_decimal(self.upper_bound_usd, "upper_bound_usd")

    def contains(self, short_term_net_usd: Decimal, long_term_net_usd: Decimal) -> bool:
        short_term_net_usd = _finite_decimal(short_term_net_usd, "short_term_net_usd")
        long_term_net_usd = _finite_decimal(long_term_net_usd, "long_term_net_usd")
        left = exact_sum(
            (
                exact_product(self.short_term_coefficient, short_term_net_usd),
                exact_product(self.long_term_coefficient, long_term_net_usd),
            )
        )
        return left <= self.upper_bound_usd


@dataclass(frozen=True, slots=True)
class TaxAffineRegion:
    """Closed region and affine T(S, L) coefficients, suitable for a convex subproblem."""

    name: str
    short_term_coefficient: Decimal
    long_term_coefficient: Decimal
    constant_usd: Decimal
    inequalities: tuple[LinearInequality, ...]

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("tax region name cannot be empty")
        _finite_decimal(self.short_term_coefficient, "short_term_coefficient")
        _finite_decimal(self.long_term_coefficient, "long_term_coefficient")
        _finite_decimal(self.constant_usd, "constant_usd")
        if not all(isinstance(item, LinearInequality) for item in self.inequalities):
            raise TypeError("tax region inequalities must be LinearInequality values")

    def value(self, short_term_net_usd: Decimal, long_term_net_usd: Decimal) -> Decimal:
        short_term_net_usd = _finite_decimal(short_term_net_usd, "short_term_net_usd")
        long_term_net_usd = _finite_decimal(long_term_net_usd, "long_term_net_usd")
        return _affine_value(
            self.short_term_coefficient,
            self.long_term_coefficient,
            self.constant_usd,
            short_term_net_usd,
            long_term_net_usd,
        )

    def contains(self, short_term_net_usd: Decimal, long_term_net_usd: Decimal) -> bool:
        short_term_net_usd = _finite_decimal(short_term_net_usd, "short_term_net_usd")
        long_term_net_usd = _finite_decimal(long_term_net_usd, "long_term_net_usd")
        return all(
            constraint.contains(short_term_net_usd, long_term_net_usd)
            for constraint in self.inequalities
        )


def _inequality(
    short_term_coefficient: Decimal,
    long_term_coefficient: Decimal,
    upper_bound_usd: Decimal,
) -> LinearInequality:
    return LinearInequality(short_term_coefficient, long_term_coefficient, upper_bound_usd)


def _loss_region_affine(
    profile: TaxProfile, lower_loss: Decimal, upper_loss: Decimal | None
) -> tuple[Decimal, Decimal]:
    """Return the shared S/L coefficient and constant on a loss-magnitude interval."""
    if upper_loss is None:
        sample = exact_sum((lower_loss, _ONE))
    else:
        sample = exact_product(exact_sum((lower_loss, upper_loss)), Decimal("0.5"))

    deduction = profile.ordinary_income_deduction_limit_usd
    retained = profile.target_retained_net_loss_usd
    ordinary_slope, ordinary_intercept = (1, _ZERO) if sample < deduction else (0, deduction)
    capped_slope, capped_intercept = (1, _ZERO) if sample < retained else (0, retained)
    carry_slope = capped_slope - ordinary_slope
    carry_intercept = exact_difference(capped_intercept, ordinary_intercept)
    carry_at_sample = exact_sum((exact_product(Decimal(carry_slope), sample), carry_intercept))
    if carry_at_sample <= 0:
        carry_slope, carry_intercept = 0, _ZERO

    st_rate = profile.short_term_tax_rate
    lt_rate = profile.long_term_tax_rate
    assert st_rate is not None
    assert lt_rate is not None
    cf_rate = profile.carryforward_tax_rate
    assert cf_rate is not None
    magnitude_slope = exact_sum(
        (
            exact_product(st_rate, Decimal(ordinary_slope)),
            exact_product(cf_rate, Decimal(carry_slope)),
        )
    )
    magnitude_intercept = exact_sum(
        (
            exact_product(st_rate, ordinary_intercept),
            exact_product(cf_rate, carry_intercept),
        )
    )
    # N = -(S+L); T = -tax_credit(N) = slope*(S+L) - intercept.
    return magnitude_slope, magnitude_intercept.copy_negate()


def enumerate_tax_regions(profile: TaxProfile) -> tuple[TaxAffineRegion, ...] | None:
    """Enumerate closed affine regions covering the (S, L) plane.

    Adjacent regions deliberately share boundary points. Their affine formulas agree there,
    including zero net gain/loss and ordinary-deduction/retained-loss breakpoints.
    """
    if not profile.tax_rates_complete:
        return None

    st_rate = profile.short_term_tax_rate
    lt_rate = profile.long_term_tax_rate
    assert st_rate is not None
    assert lt_rate is not None
    regions: list[TaxAffineRegion] = [
        TaxAffineRegion(
            "both_buckets_nonnegative",
            st_rate,
            lt_rate,
            _ZERO,
            (
                _inequality(_ONE.copy_negate(), _ZERO, _ZERO),
                _inequality(_ZERO, _ONE.copy_negate(), _ZERO),
            ),
        ),
        TaxAffineRegion(
            "short_term_gain_offsets_long_term_loss",
            st_rate,
            st_rate,
            _ZERO,
            (
                _inequality(_ONE.copy_negate(), _ZERO, _ZERO),
                _inequality(_ZERO, _ONE, _ZERO),
                _inequality(_ONE.copy_negate(), _ONE.copy_negate(), _ZERO),
            ),
        ),
        TaxAffineRegion(
            "long_term_gain_offsets_short_term_loss",
            lt_rate,
            lt_rate,
            _ZERO,
            (
                _inequality(_ONE, _ZERO, _ZERO),
                _inequality(_ZERO, _ONE.copy_negate(), _ZERO),
                _inequality(_ONE.copy_negate(), _ONE.copy_negate(), _ZERO),
            ),
        ),
    ]

    breakpoints = sorted(
        {
            value
            for value in (
                _ZERO,
                profile.ordinary_income_deduction_limit_usd,
                profile.target_retained_net_loss_usd,
            )
            if value >= 0
        }
    )
    for index, lower in enumerate(breakpoints):
        upper = breakpoints[index + 1] if index + 1 < len(breakpoints) else None
        slope, constant = _loss_region_affine(profile, lower, upper)
        constraints: list[LinearInequality] = [
            # N >= lower  <=>  S + L <= -lower.
            _inequality(_ONE, _ONE, lower.copy_negate())
        ]
        if upper is not None:
            # N <= upper  <=>  -(S + L) <= upper.
            constraints.append(_inequality(_ONE.copy_negate(), _ONE.copy_negate(), upper))
        regions.append(
            TaxAffineRegion(f"net_loss_{index}", slope, slope, constant, tuple(constraints))
        )
    return tuple(regions)


def matching_tax_regions(
    regions: Iterable[TaxAffineRegion],
    short_term_net_usd: Decimal,
    long_term_net_usd: Decimal,
) -> tuple[TaxAffineRegion, ...]:
    """Return every closed region containing the point (usually one, boundaries may overlap)."""
    short_term_net_usd = _finite_decimal(short_term_net_usd, "short_term_net_usd")
    long_term_net_usd = _finite_decimal(long_term_net_usd, "long_term_net_usd")
    return tuple(
        region for region in regions if region.contains(short_term_net_usd, long_term_net_usd)
    )
