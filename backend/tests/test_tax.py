from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.financial_inputs import PolicySettings
from app.domain.tax import (
    TaxProfile,
    enumerate_tax_regions,
    evaluate_tax,
    matching_tax_regions,
    tax_value,
)


def dec(value: str) -> Decimal:
    return Decimal(value)


def profile(
    *,
    st_rate: str = "0.40",
    lt_rate: str = "0.15",
    deduction: str = "3000",
    retained: str = "3000",
    discount: str = "0.50",
    **kwargs: Decimal,
) -> TaxProfile:
    return TaxProfile(
        short_term_tax_rate=dec(st_rate),
        long_term_tax_rate=dec(lt_rate),
        ordinary_income_deduction_limit_usd=dec(deduction),
        target_retained_net_loss_usd=dec(retained),
        carryforward_loss_discount_factor=dec(discount),
        **kwargs,
    )


def test_exact_irs_sign_and_cross_netting_cases() -> None:
    assumptions = profile(deduction="1000", retained="4000")

    assert tax_value(assumptions, dec("100"), dec("50")) == dec("47.50")
    assert tax_value(assumptions, dec("100"), dec("-40")) == dec("24.00")
    assert tax_value(assumptions, dec("-30"), dec("100")) == dec("10.50")
    assert tax_value(assumptions, dec("-500"), dec("-500")) == dec("-400.00")
    assert tax_value(assumptions, dec("-1250"), dec("-1250")) == dec("-512.5000")
    assert tax_value(assumptions, dec("-2500"), dec("-2500")) == dec("-625.000")
    assert tax_value(assumptions, dec("-5000"), dec("-5000")) == dec("-625.000")


def test_exact_tax_boundaries_and_zero_or_equal_limits() -> None:
    profiles = (
        profile(deduction="0", retained="0"),
        profile(deduction="0", retained="3000"),
        profile(deduction="3000", retained="0"),
        profile(deduction="2500", retained="2500"),
        profile(deduction="3000", retained="6000"),
        profile(deduction="6000", retained="3000"),
    )
    for assumptions in profiles:
        regions = enumerate_tax_regions(assumptions)
        assert regions is not None
        for loss in {
            dec("0"),
            assumptions.ordinary_income_deduction_limit_usd,
            assumptions.target_retained_net_loss_usd,
        }:
            for magnitude in (max(dec("0"), loss - dec("1")), loss, loss + dec("1")):
                point = (magnitude.copy_negate() / 2, magnitude.copy_negate() / 2)
                matching = matching_tax_regions(regions, *point)
                assert matching
                assert all(
                    region.value(*point) == tax_value(assumptions, *point) for region in matching
                )

        # The four sign quadrants and cross-netting lines meet at/around the net-zero boundary.
        for point in (
            (dec("0"), dec("0")),
            (dec("100"), dec("-100")),
            (dec("-100"), dec("100")),
            (dec("-100"), dec("-1")),
            (dec("100"), dec("1")),
        ):
            matching = matching_tax_regions(regions, *point)
            assert matching
            assert all(
                region.value(*point) == tax_value(assumptions, *point) for region in matching
            )


def test_tax_profile_baseline_carryforwards_and_incremental_benefit() -> None:
    assumptions = profile(
        deduction="50",
        retained="100",
        st_loss_carryforward_usd=dec("500"),
        lt_loss_carryforward_usd=dec("100"),
        ytd_realized_st_usd=dec("1000"),
        ytd_realized_lt_usd=dec("-200"),
    )
    result = evaluate_tax(assumptions, dec("-300"), dec("0"))

    assert assumptions.baseline_st_net_usd == dec("500")
    assert assumptions.baseline_lt_net_usd == dec("-300")
    assert result.post_trade_st_net_usd == dec("200")
    assert result.post_trade_lt_net_usd == dec("-300")
    assert result.realized_st_usd == dec("-300")
    assert result.realized_lt_usd == dec("0")
    assert result.baseline_tax_usd == dec("80.00")
    assert result.post_trade_tax_usd == dec("-23.7500")
    assert result.incremental_tax_cost_usd == dec("-103.7500")
    assert result.estimated_tax_benefit_usd == dec("103.7500")
    assert result.status == "tax_profile_complete"


def test_incomplete_rates_keep_realized_results_and_null_tax_estimates() -> None:
    assumptions = TaxProfile(
        short_term_tax_rate=dec("0.40"),
        long_term_tax_rate=None,
        ytd_realized_st_usd=dec("200"),
        st_loss_carryforward_usd=dec("50"),
    )
    result = evaluate_tax(assumptions, dec("-75"), dec("125"))

    assert result.realized_st_usd == dec("-75")
    assert result.realized_lt_usd == dec("125")
    assert result.baseline_st_net_usd == dec("150")
    assert result.post_trade_st_net_usd == dec("75")
    assert result.post_trade_lt_net_usd == dec("125")
    assert result.baseline_tax_usd is None
    assert result.post_trade_tax_usd is None
    assert result.incremental_tax_cost_usd is None
    assert result.estimated_tax_benefit_usd is None
    assert result.status == "tax_profile_incomplete"
    assert tax_value(assumptions, dec("1"), dec("1")) is None
    assert enumerate_tax_regions(assumptions) is None


def test_policy_settings_conversion_preserves_nullable_rates_and_configured_targets() -> None:
    settings = PolicySettings.from_mapping(
        {
            "short_term_tax_rate": "0.37",
            "long_term_tax_rate": None,
            "st_loss_carryforward_usd": "1200.25",
            "lt_loss_carryforward_usd": "300.50",
            "ytd_realized_st_usd": "-50",
            "ytd_realized_lt_usd": "750",
            "target_retained_net_loss_usd": "4500",
            "ordinary_income_deduction_limit_usd": "1500",
            "carryforward_loss_discount_factor": "0.25",
        }
    )
    assumptions = TaxProfile.from_policy_settings(settings)

    assert assumptions.short_term_tax_rate == dec("0.37")
    assert assumptions.long_term_tax_rate is None
    assert assumptions.st_loss_carryforward_usd == dec("1200.25")
    assert assumptions.lt_loss_carryforward_usd == dec("300.50")
    assert assumptions.ytd_realized_st_usd == dec("-50")
    assert assumptions.ytd_realized_lt_usd == dec("750")
    assert assumptions.target_retained_net_loss_usd == dec("4500")
    assert assumptions.ordinary_income_deduction_limit_usd == dec("1500")
    assert assumptions.carryforward_loss_discount_factor == dec("0.25")

    defaults = TaxProfile.from_policy_settings(PolicySettings.from_mapping({}))
    assert defaults.target_retained_net_loss_usd == dec("3000")
    assert defaults.ordinary_income_deduction_limit_usd == dec("3000")
    assert defaults.carryforward_loss_discount_factor == dec("0.50")
    assert defaults.st_loss_carryforward_usd == dec("0")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("short_term_tax_rate", dec("1.01"), "short_term_tax_rate must be between 0 and 1"),
        ("long_term_tax_rate", dec("-0.01"), "long_term_tax_rate must be between 0 and 1"),
        ("st_loss_carryforward_usd", dec("-1"), "loss carryforwards cannot be negative"),
        (
            "target_retained_net_loss_usd",
            dec("-1"),
            "target_retained_net_loss_usd cannot be negative",
        ),
        (
            "ordinary_income_deduction_limit_usd",
            dec("-1"),
            "ordinary_income_deduction_limit_usd cannot be negative",
        ),
        (
            "carryforward_loss_discount_factor",
            dec("1.01"),
            "carryforward_loss_discount_factor must be between 0 and 1",
        ),
    ],
)
def test_invalid_policy_profile_values_are_rejected(
    field: str, value: Decimal, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        TaxProfile(**{field: value})


def test_invalid_rate_order_and_nonfinite_values_are_rejected() -> None:
    with pytest.raises(ValueError, match="short_term_tax_rate must be at least"):
        TaxProfile(short_term_tax_rate=dec("0.10"), long_term_tax_rate=dec("0.20"))
    with pytest.raises(ValueError, match="must be finite"):
        TaxProfile(short_term_tax_rate=Decimal("NaN"))
    with pytest.raises(TypeError, match="must be a Decimal"):
        tax_value(profile(), 1.0, dec("0"))  # type: ignore[arg-type]


def test_affine_region_grid_covers_plane_and_matches_direct_decimal_value() -> None:
    assumptions = profile(deduction="125", retained="500")
    regions = enumerate_tax_regions(assumptions)
    assert regions is not None
    values = tuple(map(dec, ("-700", "-500", "-125", "-1", "0", "1", "125", "500", "700")))

    for short_term in values:
        for long_term in values:
            matching = matching_tax_regions(regions, short_term, long_term)
            assert matching, (short_term, long_term)
            expected = tax_value(assumptions, short_term, long_term)
            assert expected is not None
            assert all(region.value(short_term, long_term) == expected for region in matching)


@given(
    short_term=st.decimals(min_value=-100_000, max_value=100_000, places=2, allow_nan=False),
    long_term=st.decimals(min_value=-100_000, max_value=100_000, places=2, allow_nan=False),
)
def test_hypothesis_region_coverage_and_exact_formula_agreement(
    short_term: Decimal, long_term: Decimal
) -> None:
    assumptions = profile(deduction="101.25", retained="550.75")
    regions = enumerate_tax_regions(assumptions)
    assert regions is not None
    matching = matching_tax_regions(regions, short_term, long_term)
    assert matching
    expected = tax_value(assumptions, short_term, long_term)
    assert expected is not None
    assert all(region.value(short_term, long_term) == expected for region in matching)
