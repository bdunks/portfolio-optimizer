from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal, localcontext

import pytest

from app.domain.allocation import (
    AllocationPolicy,
    AllocationSleeve,
    AllowedSecurity,
    SecurityIdentity,
    SecurityOverride,
    SleeveAssignment,
)
from app.domain.financial_inputs import (
    AccountInput,
    FinancialInputs,
    LotInput,
    PolicyInput,
    PolicySettings,
    PositionInput,
    SecurityInput,
)
from app.domain.portfolio_accounting import (
    BasketValidationError,
    ConsolidatedLeg,
    LotAllocation,
    evaluate_portfolio,
)

_NOW = datetime(2026, 11, 5, 12, tzinfo=UTC)


def _inputs(*, transition_destination: bool = True, cash_reserve: Decimal = Decimal(0)) -> FinancialInputs:
    policy = AllocationPolicy(
        sleeves=(
            AllocationSleeve(
                "us",
                None,
                True,
                direct_index_container=True,
                target_pct=Decimal(60),
                drift_band_pp=Decimal(5),
            ),
            AllocationSleeve(
                "legacy",
                "us",
                True,
                direct_index_sleeve=True,
                target_pct=Decimal(50),
                drift_band_pp=Decimal(5),
            ),
            AllocationSleeve(
                "destination",
                "us",
                True,
                transition_destination=transition_destination,
                target_pct=Decimal(25),
                drift_band_pp=Decimal(5),
            ),
            AllocationSleeve(
                "destination_nested",
                "destination",
                True,
                target_pct=Decimal(100),
                drift_band_pp=Decimal(5),
            ),
            AllocationSleeve("other_us", "us", True, target_pct=Decimal(25), drift_band_pp=Decimal(5)),
            AllocationSleeve("international", None, True, target_pct=Decimal(30), drift_band_pp=Decimal(5)),
            AllocationSleeve("cash", None, True, cash_sleeve=True, target_pct=Decimal(10), drift_band_pp=Decimal(2)),
        ),
        allowed_securities=(
            AllowedSecurity("NEWBUY", "us", "destination", 0, True),
            AllowedSecurity("NEWETF", "us", "destination", 0, True),
            AllowedSecurity("BROAD", "us", "other_us", 0, True),
            AllowedSecurity("INTL", "international", None, 0, True),
        ),
        overrides=(SecurityOverride("NEST", "destination", "destination_nested"),),
    )
    policy_input = PolicyInput(
        "policy",
        policy,
        PolicySettings.from_mapping({"cash_reserve_usd": cash_reserve}),
    )
    positions = (
        PositionInput("AAPL", "EQUITY", False, Decimal(10), 1, _NOW, Decimal(1000), SleeveAssignment("us", "legacy")),
        PositionInput("NEWETF", "ETF", False, Decimal(3), 1, _NOW, Decimal(300), SleeveAssignment("us", "destination")),
        PositionInput("BROAD", "ETF", False, Decimal(2), 1, _NOW, Decimal(200), SleeveAssignment("us", "other_us")),
        PositionInput(
            "NEST",
            "EQUITY",
            False,
            Decimal(1),
            1,
            _NOW,
            Decimal(40),
            SleeveAssignment("destination", "destination_nested"),
        ),
        PositionInput("INTL", "ETF", False, Decimal(3), 1, _NOW, Decimal(300), SleeveAssignment("international")),
    )
    lots = (
        LotInput(
            "AAPL", "AAPL-short", date(2026, 10, 1), Decimal(4), Decimal(4), Decimal(50), None,
            "FAKE", _NOW, False, (), 1,
        ),
        LotInput(
            "AAPL", "AAPL-long", date(2024, 1, 1), Decimal(6), Decimal(6), Decimal(80), None,
            "FAKE", _NOW, False, (), 1,
        ),
    )
    identities = (
        SecurityIdentity("AAPL", "EQUITY"),
        SecurityIdentity("NEWETF", "ETF"),
        SecurityIdentity("BROAD", "ETF"),
        SecurityIdentity("NEST", "EQUITY"),
        SecurityIdentity("INTL", "ETF"),
        SecurityIdentity("NEWBUY", "ETF"),
    )
    return FinancialInputs(
        account=AccountInput(
            1,
            "fingerprint",
            "Test account",
            "BROKERAGE",
            None,
            "FAKE",
            _NOW,
            Decimal(100),
            Decimal(100),
        ),
        source_generation=1,
        proposed_trade_date=date(2026, 11, 5),
        policy=policy_input,
        securities=tuple(SecurityInput(identity) for identity in identities),
        positions=positions,
        lots=lots,
        quotes=(),
        transactions=(),
    )


def _sell(*, shares: str = "3", allocations: tuple[tuple[str, str], ...] = (("AAPL-short", "2"), ("AAPL-long", "1")), sequence: int = 0) -> ConsolidatedLeg:
    return ConsolidatedLeg(
        leg_id="sell-aapl",
        side="SELL",
        ticker="AAPL",
        shares=Decimal(shares),
        estimated_unit_price_usd=Decimal(110),
        selected_lots=tuple(LotAllocation(lot_id, Decimal(quantity)) for lot_id, quantity in allocations),
        sequence=sequence,
    )


def test_empty_basket_is_current_state_and_nested_destination_progress_uses_all_assigned_assets() -> None:
    result = evaluate_portfolio(_inputs())

    assert result.current == result.proposed
    assert result.current.portfolio_total_usd == Decimal(1940)
    current_values = dict(result.current.sleeve_values_usd)
    assert current_values["us"] == Decimal(1540)
    assert current_values["destination"] == Decimal(340)
    assert current_values["destination_nested"] == Decimal(40)
    assert current_values["cash"] == Decimal(100)
    assert result.transition is not None
    assert result.transition.destination_sleeve_key == "destination"
    assert result.transition.current.etf_progress_pct == Decimal("22.08")

    targets = {row.sleeve_key: row for row in result.allocation.target.sleeves}
    assert targets["us"].target_whole_portfolio_pct == Decimal(60)
    assert targets["destination"].target_whole_portfolio_pct == Decimal(15)
    assert targets["destination_nested"].target_whole_portfolio_pct == Decimal(15)


def test_consolidated_lots_funding_cash_and_proposed_transition_are_recomputed_exactly() -> None:
    sale = _sell()
    buy = ConsolidatedLeg(
        leg_id="buy-new",
        side="BUY",
        ticker="NEWBUY",
        shares=Decimal(2),
        estimated_unit_price_usd=Decimal(100),
        depends_on_leg_ids=(sale.leg_id,),
        sequence=1,
    )

    result = evaluate_portfolio(_inputs(), (sale, buy))

    assert result.current.portfolio_total_usd == Decimal(1940)
    assert result.sell_proceeds_usd == Decimal(330)
    assert result.proposed.cash_usd == Decimal(230)
    assert result.proposed.portfolio_total_usd == Decimal(1970)
    proposed_positions = {row.ticker: row for row in result.proposed.positions}
    assert proposed_positions["AAPL"].shares == Decimal(7)
    assert proposed_positions["AAPL"].market_value_usd == Decimal(700)
    assert proposed_positions["NEWBUY"].shares == Decimal(2)
    assert proposed_positions["NEWBUY"].assignment == SleeveAssignment("us", "destination")
    proposed_values = dict(result.proposed.sleeve_values_usd)
    assert proposed_values["us"] == Decimal(1440)
    assert proposed_values["destination"] == Decimal(540)
    assert result.transition is not None
    assert result.transition.current.etf_progress_pct == Decimal("22.08")
    assert result.transition.proposed_basket.etf_progress_pct == Decimal("37.50")
    assert result.realized_st_usd == Decimal(120)
    assert result.realized_lt_usd == Decimal(30)
    assert result.position_count_before == 5
    assert result.position_count_after == 6
    assert result.lot_count_before == result.lot_count_after == 2
    assert result.selected_lots_count == 2
    assert {row.broker_lot_id: row.shares for row in result.proposed.lots}["AAPL-short"] == Decimal(2)


def test_high_precision_partial_sale_cash_and_nested_rollup_match_independent_expected_values() -> None:
    base = _inputs()
    inputs = replace(
        base,
        account=replace(
            base.account,
            cash_usd=Decimal("100.000000000000000000000000009"),
            settled_buying_power_usd=Decimal("100.000000000000000000000000009"),
        ),
        positions=tuple(
            replace(
                position,
                market_value_usd=Decimal("1000.000000000000000000000000007"),
                assignment=SleeveAssignment("destination", "destination_nested"),
            )
            if position.ticker == "AAPL"
            else position
            for position in base.positions
        ),
    )
    sale = ConsolidatedLeg(
        "sell-aapl",
        "SELL",
        "AAPL",
        Decimal("1.25"),
        Decimal("110.00000000000000000000000003"),
        (LotAllocation("AAPL-short", Decimal("1.25")),),
    )
    buy = ConsolidatedLeg(
        "buy-new",
        "BUY",
        "NEWBUY",
        Decimal(1),
        Decimal("100.00000000000000000000000001"),
        depends_on_leg_ids=(sale.leg_id,),
        sequence=1,
    )

    with localcontext() as context:
        context.prec = 3
        result = evaluate_portfolio(inputs, (sale, buy))

    assert result.sell_proceeds_usd == Decimal("137.5000000000000000000000000375")
    assert result.current.portfolio_total_usd == Decimal("1940.000000000000000000000000016")
    assert result.proposed.cash_usd == Decimal("137.5000000000000000000000000365")
    assert result.proposed.portfolio_total_usd == Decimal("1952.500000000000000000000000052625")
    assert result.current.portfolio_total_usd - Decimal(1940) == Decimal("0.000000000000000000000000016")
    assert result.proposed.portfolio_total_usd - Decimal("1952.5") == Decimal("0.000000000000000000000000052625")

    current_values = dict(result.current.sleeve_values_usd)
    proposed_values = dict(result.proposed.sleeve_values_usd)
    assert current_values["us"] == Decimal("1540.000000000000000000000000007")
    assert current_values["destination"] == Decimal("1340.000000000000000000000000007")
    assert current_values["destination_nested"] == Decimal("1040.000000000000000000000000007")
    assert proposed_values["us"] == Decimal("1515.000000000000000000000000016125")
    assert proposed_values["destination"] == Decimal("1315.000000000000000000000000016125")
    assert proposed_values["destination_nested"] == Decimal("915.000000000000000000000000006125")
    proposed_positions = {row.ticker: row for row in result.proposed.positions}
    assert proposed_positions["AAPL"].shares == Decimal("8.75")
    assert proposed_positions["AAPL"].market_value_usd == Decimal("875.000000000000000000000000006125")
    proposed_lots = {row.broker_lot_id: row for row in result.proposed.lots}
    assert proposed_lots["AAPL-short"].shares == Decimal("2.75")


def test_full_position_exit_closes_lots_and_preserves_exact_account_value() -> None:
    sale = ConsolidatedLeg(
        leg_id="sell-aapl",
        side="SELL",
        ticker="AAPL",
        shares=Decimal(10),
        estimated_unit_price_usd=Decimal(100),
        selected_lots=(LotAllocation("AAPL-short", Decimal(4)), LotAllocation("AAPL-long", Decimal(6))),
    )

    result = evaluate_portfolio(_inputs(), (sale,))

    assert result.proposed.portfolio_total_usd == result.current.portfolio_total_usd == Decimal(1940)
    assert result.proposed.cash_usd == Decimal(1100)
    assert "AAPL" not in {row.ticker for row in result.proposed.positions}
    assert result.position_count_before == 5
    assert result.position_count_after == 4
    assert result.lot_count_before == 2
    assert result.lot_count_after == 0
    assert all(row.position_exited for row in result.position_effects if row.ticker == "AAPL")
    assert all(row.lot_closed for row in result.lot_effects)


def test_unconfigured_destination_stays_unavailable_even_with_etfs_in_us_siblings() -> None:
    result = evaluate_portfolio(_inputs(transition_destination=False))

    assert result.transition is not None
    assert result.transition.destination_sleeve_key is None
    assert result.transition.current.etf_progress_pct is None
    assert result.transition.proposed_basket.etf_progress_pct is None


def test_unassigned_current_state_is_explicitly_display_only() -> None:
    inputs = _inputs()
    no_policy = PolicyInput(
        "no-policy", AllocationPolicy((), (), ()), PolicySettings.from_mapping({})
    )
    display_inputs = replace(
        inputs,
        policy=no_policy,
        positions=tuple(replace(position, assignment=None) for position in inputs.positions),
    )

    evaluation = evaluate_portfolio(display_inputs, allow_unassigned_current_positions=True)
    assert evaluation.current.portfolio_total_usd == Decimal(1940)
    assert evaluation.current.sleeve_values_usd == ()
    assert all(position.assignment is None for position in evaluation.current.positions)
    assert evaluation.transition is None

    with pytest.raises(BasketValidationError, match="no policy sleeve assignment") as strict_error:
        evaluate_portfolio(display_inputs)
    assert strict_error.value.code == "unassigned_holding"
    with pytest.raises(BasketValidationError, match="only for an empty-basket display") as proposal_error:
        evaluate_portfolio(display_inputs, (_sell(),), allow_unassigned_current_positions=True)
    assert proposal_error.value.code == "unassigned_current_only"


@pytest.mark.parametrize(
    ("field", "expected_code"),
    [
        ("market_value_usd", "invalid_position"),
        ("cash_reserve_usd", "invalid_cash_reserve"),
        ("cash_usd", "invalid_account_balance"),
        ("settled_buying_power_usd", "invalid_account_balance"),
    ],
)
@pytest.mark.parametrize("amount", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_nonfinite_monetary_boundaries_raise_structured_errors(
    field: str, expected_code: str, amount: Decimal
) -> None:
    inputs = _inputs()
    if field == "market_value_usd":
        positions = (replace(inputs.positions[0], market_value_usd=amount), *inputs.positions[1:])
        inputs = replace(inputs, positions=positions)
    elif field == "cash_reserve_usd":
        inputs = _inputs(cash_reserve=amount)
    else:
        inputs = replace(inputs, account=replace(inputs.account, **{field: amount}))

    with pytest.raises(BasketValidationError) as error:
        evaluate_portfolio(inputs, allow_unassigned_current_positions=True)
    assert error.value.code == expected_code


@pytest.mark.parametrize("field", ["cash_usd", "settled_buying_power_usd"])
def test_negative_account_balances_are_rejected(field: str) -> None:
    inputs = _inputs()
    invalid_account = replace(inputs.account, **{field: Decimal(-1)})

    with pytest.raises(BasketValidationError) as error:
        evaluate_portfolio(replace(inputs, account=invalid_account))
    assert error.value.code == "invalid_account_balance"


def test_basket_structure_lots_dependencies_and_funding_are_independently_validated() -> None:
    inputs = _inputs()
    buy = ConsolidatedLeg(
        "buy-new", "BUY", "NEWBUY", Decimal(2), Decimal(100), depends_on_leg_ids=("missing",), sequence=1
    )
    with pytest.raises(BasketValidationError, match="SELL leg IDs") as unknown_dependency:
        evaluate_portfolio(inputs, (_sell(), buy))
    assert unknown_dependency.value.code == "invalid_funding_dependency"

    bad_total = _sell(shares="4", allocations=(("AAPL-short", "2"), ("AAPL-long", "1")))
    with pytest.raises(BasketValidationError) as mismatch:
        evaluate_portfolio(inputs, (bad_total,))
    assert mismatch.value.code == "sell_lot_total_mismatch"

    oversell = _sell(shares="5", allocations=(("AAPL-short", "5"),))
    with pytest.raises(BasketValidationError) as lot_limit:
        evaluate_portfolio(inputs, (oversell,))
    assert lot_limit.value.code == "lot_oversell"

    underfunded = ConsolidatedLeg("buy-new", "BUY", "NEWBUY", Decimal(2), Decimal(100))
    with pytest.raises(BasketValidationError) as cash_limit:
        evaluate_portfolio(inputs, (underfunded,))
    assert cash_limit.value.code == "insufficient_cash"

    duplicate_sales = (_sell(), ConsolidatedLeg("sell-again", "SELL", "AAPL", Decimal(1), Decimal(100), (LotAllocation("AAPL-short", Decimal(1)),)))
    with pytest.raises(BasketValidationError) as unconsolidated:
        evaluate_portfolio(inputs, duplicate_sales)
    assert unconsolidated.value.code == "unconsolidated_ticker_legs"


def test_funding_dependencies_must_precede_the_buy() -> None:
    sale = _sell(sequence=1)
    buy = ConsolidatedLeg(
        "buy-new", "BUY", "NEWBUY", Decimal(1), Decimal(100), depends_on_leg_ids=(sale.leg_id,), sequence=1
    )

    with pytest.raises(BasketValidationError) as failure:
        evaluate_portfolio(_inputs(), (sale, buy))
    assert failure.value.code == "funding_dependency_not_prior"
