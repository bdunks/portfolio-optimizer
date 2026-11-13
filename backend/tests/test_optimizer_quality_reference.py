from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from optimizer_quality_reference import (
    BuyTickerBound,
    CandidateUniverse,
    SellLotBound,
    enumerate_small_case,
)

from app.domain.allocation import (
    AllocationPolicy,
    AllocationSleeve,
    AllowedSecurity,
    SecurityIdentity,
    SleeveAssignment,
)
from app.domain.financial_inputs import (
    AccountInput,
    FinancialInputs,
    InputSourceMetadata,
    LookThroughExposureInput,
    LotInput,
    PolicyInput,
    PolicySectorBandInput,
    PolicySettings,
    PositionInput,
    QuoteInput,
    SecurityInput,
)

TRADE_DATE = date(2026, 11, 13)
AS_OF = datetime(2026, 11, 13, 16, tzinfo=UTC)


def _inputs(*, cash: Decimal = Decimal(100), cash_reserve: Decimal = Decimal(0)) -> FinancialInputs:
    settings: dict[str, object] = {
        "short_term_tax_rate": Decimal("0.30"),
        "long_term_tax_rate": Decimal("0.15"),
        "st_loss_carryforward_usd": Decimal(0),
        "lt_loss_carryforward_usd": Decimal(0),
        "gain_budget_usd": Decimal(100),
        "max_incremental_tax_cost_usd": Decimal(100),
        "st_gain_limit_usd": Decimal(100),
        "lt_gain_limit_usd": Decimal(100),
        "max_batch_turnover_pct": Decimal(100),
        "min_buy_order_notional_usd": Decimal(0),
        "cash_reserve_usd": cash_reserve,
        "max_sell_tickers_per_batch": 1,
        "max_sell_lots_per_batch": 2,
        "max_total_orders_per_batch": 2,
        "prefer_etf_buys": True,
        "allow_gain_sales": False,
        "permit_etf_harvest": False,
        "permit_muni_exit": False,
        "objective_band_weight": Decimal(0),
        "objective_allocation_weight": Decimal(0),
        "objective_tax_weight": Decimal(0),
        "objective_trading_cost_weight": Decimal(0),
        "objective_turnover_weight": Decimal(0),
        "objective_cleanup_weight": Decimal(1),
        "estimated_spread_bps": Decimal(0),
        "estimated_fee_per_order_usd": Decimal(3),
    }
    allocation = AllocationPolicy(
        sleeves=(
            AllocationSleeve(
                "equity", None, True, target_pct=Decimal(90), drift_band_pp=Decimal(100)
            ),
            AllocationSleeve(
                "cash",
                None,
                True,
                cash_sleeve=True,
                target_pct=Decimal(10),
                drift_band_pp=Decimal(100),
            ),
        ),
        allowed_securities=(
            AllowedSecurity("AAA", "equity", None, 0, True, "replacement"),
            AllowedSecurity("BBB", "equity", None, 1, True, "replacement"),
        ),
        overrides=(),
    )
    return FinancialInputs(
        account=AccountInput(
            1,
            "synthetic-quality-account",
            "Synthetic quality fixture",
            "BROKERAGE",
            None,
            "SYNTHETIC_TEST",
            AS_OF,
            cash,
            cash,
        ),
        source_generation=1,
        proposed_trade_date=TRADE_DATE,
        policy=PolicyInput(
            "synthetic-quality-policy",
            allocation,
            PolicySettings.from_mapping(settings),
            status="ACTIVE",
            sector_bands=(PolicySectorBandInput("technology", Decimal(100), Decimal(100)),),
        ),
        securities=(
            SecurityInput(SecurityIdentity("AAA", "EQUITY"), security_id=1),
            SecurityInput(SecurityIdentity("BBB", "ETF"), security_id=2),
        ),
        positions=(
            PositionInput(
                "AAA",
                "EQUITY",
                False,
                Decimal(2),
                1,
                AS_OF,
                Decimal(20),
                SleeveAssignment("equity"),
            ),
        ),
        lots=(
            LotInput(
                "AAA",
                "aaa-lot-1",
                TRADE_DATE - timedelta(days=400),
                Decimal(1),
                Decimal(1),
                Decimal(10),
                None,
                "SYNTHETIC_TEST",
                AS_OF,
                False,
                (),
                1,
            ),
            LotInput(
                "AAA",
                "aaa-lot-2",
                TRADE_DATE - timedelta(days=400),
                Decimal(1),
                Decimal(1),
                Decimal(10),
                None,
                "SYNTHETIC_TEST",
                AS_OF,
                False,
                (),
                1,
            ),
        ),
        quotes=(
            QuoteInput("AAA", Decimal(10), Decimal(10), None, "SYNTHETIC_TEST", AS_OF, "good", 1),
            QuoteInput("BBB", Decimal(5), Decimal(5), None, "SYNTHETIC_TEST", AS_OF, "good", 1),
        ),
        transactions=(),
        source_checksum="synthetic-quality-fixture-v1",
        exposures=(
            LookThroughExposureInput(
                "AAA", "sector", "technology", Decimal(1), "manual_csv", TRADE_DATE
            ),
            LookThroughExposureInput(
                "BBB", "sector", "technology", Decimal(1), "manual_csv", TRADE_DATE
            ),
            LookThroughExposureInput(
                "BBB", "security", "US_MARKET", Decimal(1), "manual_csv", TRADE_DATE
            ),
        ),
        source_metadata=InputSourceMetadata(
            sync_complete=True,
            transaction_history_complete=True,
            transaction_history_start_date=TRADE_DATE - timedelta(days=30),
            transaction_history_end_date=TRADE_DATE,
            lookthrough_complete=True,
        ),
    )


def _universe() -> CandidateUniverse:
    return CandidateUniverse(
        sells=(
            SellLotBound("AAA", "aaa-lot-1", 1),
            SellLotBound("AAA", "aaa-lot-2", 1),
        ),
        buys=(BuyTickerBound("BBB", 2),),
    )


def test_tiny_exact_reference_enumerates_no_trade_and_consolidated_multilot_optimum() -> None:
    result = enumerate_small_case(_inputs(), _universe(), max_assignments=12, time_limit_seconds=10)

    assert result.complete
    assert result.stop_reason == "exhausted"
    assert result.theoretical_assignment_count == result.assignments_examined == 12
    assert result.canonical_baskets_examined == 12
    assert result.feasible_basket_count > 0
    assert result.incumbent.feasible

    no_trade = next(candidate for candidate in result.candidates if not candidate.legs)
    assert no_trade.feasible
    assert no_trade.validation.objective_value == Decimal(0)

    optimum = result.exact_optimum
    assert optimum is not None
    assert optimum.validation.objective_value == Decimal(-1)
    assert len(optimum.legs) == 1
    sell = optimum.legs[0]
    assert sell.side == "SELL"
    assert sell.ticker == "AAA"
    assert sell.shares == Decimal(2)
    assert tuple(lot.broker_lot_id for lot in sell.selected_lots) == ("aaa-lot-1", "aaa-lot-2")
    assert optimum.validation.estimated_trading_cost_usd == Decimal(3)
    assert optimum.validation.evaluation is not None
    assert optimum.validation.evaluation.proposed.cash_usd == Decimal(117)
    assert result.exact_optimum is optimum


def test_exact_reference_orders_sells_by_proceeds_for_intermediate_cash_feasibility() -> None:
    base = _inputs(cash=Decimal(0))
    settings: dict[str, object] = dict(base.policy.settings.values)
    settings.update({"max_sell_tickers_per_batch": 2, "max_total_orders_per_batch": 2})
    policy = replace(base.policy, settings=PolicySettings.from_mapping(settings))
    inputs = replace(
        base,
        policy=policy,
        positions=(
            base.positions[0],
            replace(
                base.positions[0],
                ticker="BBB",
                asset_type="ETF",
                market_value_usd=Decimal(10),
            ),
        ),
        lots=(
            replace(
                base.lots[0],
                broker_lot_id="aaa-lot",
                shares=Decimal(1),
                available_shares=Decimal(1),
                adjusted_unit_basis_usd=Decimal(1),
            ),
            replace(
                base.lots[1],
                ticker="BBB",
                broker_lot_id="bbb-lot",
                shares=Decimal(1),
                available_shares=Decimal(1),
                adjusted_unit_basis_usd=Decimal(10),
            ),
        ),
        quotes=(
            QuoteInput("AAA", Decimal(1), Decimal(1), None, "SYNTHETIC_TEST", AS_OF, "good", 1),
            QuoteInput("BBB", Decimal(10), Decimal(10), None, "SYNTHETIC_TEST", AS_OF, "good", 1),
        ),
    )
    universe = CandidateUniverse(
        sells=(
            SellLotBound("AAA", "aaa-lot", 1),
            SellLotBound("BBB", "bbb-lot", 1),
        )
    )

    result = enumerate_small_case(inputs, universe, max_assignments=4, time_limit_seconds=10)

    assert result.complete
    optimum = result.exact_optimum
    assert optimum is not None
    assert optimum.feasible
    assert tuple(leg.ticker for leg in optimum.legs) == ("BBB", "AAA")
    assert tuple(leg.sequence for leg in optimum.legs) == (0, 1)
    assert optimum.validation.evaluation is not None
    assert optimum.validation.evaluation.proposed.cash_usd == Decimal(5)
    assert optimum.validation.objective_value == Decimal("-0.5")


def test_assignment_limit_reports_only_best_observed_not_an_exact_optimum() -> None:
    result = enumerate_small_case(_inputs(), _universe(), max_assignments=1, time_limit_seconds=10)

    assert not result.complete
    assert result.stop_reason == "max_assignments"
    assert result.assignments_examined == 1
    assert result.theoretical_assignment_count == 12
    assert result.exact_optimum is None
    assert result.best_observed is not None
    assert result.best_observed.legs == ()


def test_infeasible_no_trade_incumbent_can_have_a_feasible_reference_basket() -> None:
    inputs = _inputs(cash=Decimal(0), cash_reserve=Decimal(15))
    universe = CandidateUniverse(
        sells=(
            SellLotBound("AAA", "aaa-lot-1", 1),
            SellLotBound("AAA", "aaa-lot-2", 1),
        )
    )
    result = enumerate_small_case(inputs, universe, max_assignments=4, time_limit_seconds=10)

    assert result.complete
    assert not result.incumbent.feasible
    assert "cash_reserve_breached_after_fees" in result.incumbent.validation.reasons
    optimum = result.exact_optimum
    assert optimum is not None
    assert optimum.feasible
    assert optimum.legs[0].shares == Decimal(2)
    assert optimum.validation.evaluation is not None
    assert optimum.validation.evaluation.proposed.cash_usd == Decimal(17)


def test_deadline_cutoff_is_never_reported_as_complete() -> None:
    result = enumerate_small_case(
        _inputs(), _universe(), max_assignments=12, time_limit_seconds=1e-300
    )

    assert not result.complete
    assert result.stop_reason == "deadline"
    assert result.assignments_examined == 0
    assert result.exact_optimum is None
    assert not result.incumbent.validation_completed


def test_universe_bounds_must_respect_the_frozen_lot() -> None:
    with pytest.raises(ValueError, match="exceeds whole available shares"):
        enumerate_small_case(
            _inputs(),
            CandidateUniverse(sells=(SellLotBound("AAA", "aaa-lot-1", 2),)),
            max_assignments=3,
            time_limit_seconds=10,
        )


def test_candidate_bounds_require_a_frozen_quote() -> None:
    inputs = replace(_inputs(), quotes=())
    universe = CandidateUniverse(buys=(BuyTickerBound("BBB", 1),))

    with pytest.raises(ValueError, match="no usable frozen quote for BBB"):
        enumerate_small_case(inputs, universe, max_assignments=2, time_limit_seconds=10)
