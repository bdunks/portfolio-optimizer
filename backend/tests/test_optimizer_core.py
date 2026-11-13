from __future__ import annotations

import time
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

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
    PolicySettings,
    PositionInput,
    QuoteInput,
    SecurityInput,
)
from app.domain.portfolio_accounting import LotAllocation
from app.optimizer.core import OptimizerRequest, optimize_worker, resolve_subset
from app.optimizer.validation import validate_candidate

TRADE_DATE = date(2026, 11, 13)
NOW = datetime(2026, 11, 13, 16, 0, tzinfo=UTC)


def _inputs(*, objective_settings: bool = True) -> FinancialInputs:
    settings: dict[str, Decimal | bool | int] = {
        "short_term_tax_rate": Decimal("0.30"),
        "long_term_tax_rate": Decimal("0.15"),
        "gain_budget_usd": Decimal(0),
        "max_incremental_tax_cost_usd": Decimal(0),
        "st_gain_limit_usd": Decimal(0),
        "lt_gain_limit_usd": Decimal(0),
        "max_batch_turnover_pct": Decimal(100),
        "min_buy_order_notional_usd": Decimal(100),
        "cash_reserve_usd": Decimal(0),
        "max_sell_tickers_per_batch": 1,
        "max_sell_lots_per_batch": 2,
        "max_total_orders_per_batch": 2,
        "prefer_etf_buys": True,
        "allow_gain_sales": False,
        "permit_etf_harvest": False,
        "permit_muni_exit": False,
    }
    if objective_settings:
        settings.update(
            {
                "objective_band_weight": Decimal(0),
                "objective_allocation_weight": Decimal(0),
                "objective_tax_weight": Decimal(1),
                "objective_trading_cost_weight": Decimal(0),
                "objective_turnover_weight": Decimal(0),
                "objective_cleanup_weight": Decimal(0),
                "estimated_spread_bps": Decimal(0),
                "estimated_fee_per_order_usd": Decimal(0),
            }
        )
    allocation = AllocationPolicy(
        sleeves=(
            AllocationSleeve("equity", None, True, target_pct=Decimal(90), drift_band_pp=Decimal(10)),
            AllocationSleeve("cash", None, True, cash_sleeve=True, target_pct=Decimal(10), drift_band_pp=Decimal(10)),
        ),
        allowed_securities=(AllowedSecurity("NEWETF", "equity", None, 0, True, "replacement"),),
        overrides=(),
    )
    return FinancialInputs(
        account=AccountInput(1, "test-account", "Test", "BROKERAGE", None, "TEST", NOW, Decimal(0), Decimal(0)),
        source_generation=1,
        proposed_trade_date=TRADE_DATE,
        policy=PolicyInput("test-policy", allocation, PolicySettings(tuple(sorted(settings.items())))),
        securities=(
            SecurityInput(SecurityIdentity("AAPL", "EQUITY")),
            SecurityInput(SecurityIdentity("NEWETF", "ETF")),
        ),
        positions=(
            PositionInput("AAPL", "EQUITY", False, Decimal(10), 1, NOW, Decimal(1000), SleeveAssignment("equity")),
        ),
        lots=(
            LotInput(
                "AAPL",
                "loss-lot",
                TRADE_DATE - timedelta(days=100),
                Decimal(10),
                Decimal(10),
                Decimal(110),
                None,
                "TEST",
                NOW,
                False,
                (),
                1,
            ),
        ),
        quotes=(
            QuoteInput("AAPL", Decimal(100), Decimal(100), None, "TEST", NOW, "good", 1),
            QuoteInput("NEWETF", Decimal(100), Decimal(100), None, "TEST", NOW, "good", 1),
        ),
        transactions=(),
        source_checksum="test-checksum",
        exposures=(LookThroughExposureInput("NEWETF", "security", "US_MARKET", Decimal(1), "TEST", TRADE_DATE),),
        source_metadata=InputSourceMetadata(
            sync_complete=True,
            transaction_history_complete=True,
            transaction_history_start_date=TRADE_DATE - timedelta(days=30),
            transaction_history_end_date=TRADE_DATE,
            lookthrough_complete=True,
        ),
    )



def _install_objective_accessor(monkeypatch: pytest.MonkeyPatch) -> None:
    def decimal_value(settings: PolicySettings, key: str) -> Decimal | None:
        value = settings.get(key)
        return value if isinstance(value, Decimal) else None

    monkeypatch.setattr(PolicySettings, "decimal", decimal_value, raising=False)



def test_worker_requires_persisted_objective_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_objective_accessor(monkeypatch)
    result = optimize_worker(OptimizerRequest(_inputs(objective_settings=False)), time.monotonic() + 1)

    assert result.status == "configuration_required"
    assert "configuration_required:objective_band_weight" in result.metadata.warnings
    assert result.legs == ()



def test_no_trade_preserves_baseline_objective(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_objective_accessor(monkeypatch)
    inputs = _inputs()
    inputs = replace(inputs, lots=(replace(inputs.lots[0], adjusted_unit_basis_usd=Decimal(100)),))

    result = optimize_worker(OptimizerRequest(inputs), time.monotonic() + 10)

    assert result.status == "no_trade"
    assert result.legs == ()
    assert result.metadata.objective_value == result.metadata.baseline_objective_value


def test_unfunded_cash_reserve_is_infeasible(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_objective_accessor(monkeypatch)
    inputs = _inputs()
    settings = tuple(
        (key, Decimal(1) if key == "cash_reserve_usd" else value)
        for key, value in inputs.policy.settings.values
    )
    inputs = replace(inputs, policy=replace(inputs.policy, settings=PolicySettings(settings)))

    result = optimize_worker(OptimizerRequest(inputs), time.monotonic() + 10)

    assert result.status == "infeasible"
    assert result.legs == ()
    assert "cash_reserve_breached_after_fees" in result.metadata.warnings
def test_joint_loss_harvest_is_independently_validated_and_prioritized(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_objective_accessor(monkeypatch)
    inputs = _inputs()
    request = OptimizerRequest(inputs)

    result = optimize_worker(request, time.monotonic() + 10)

    assert result.status == "ready"
    sells = [leg for leg in result.legs if leg.side == "SELL"]
    buys = [leg for leg in result.legs if leg.side == "BUY"]
    assert len(buys) == 1
    assert buys[0].depends_on_leg_ids == (sells[0].leg_id,)
    assert buys[0].shares * buys[0].estimated_unit_price_usd >= Decimal(100)
    assert len(sells) == 1
    assert sells[0].ticker == "AAPL"
    assert sells[0].selected_lots
    assert {allocation.broker_lot_id for allocation in sells[0].selected_lots} == {"loss-lot"}
    assert all(leg.shares == leg.shares.to_integral_value() for leg in result.legs)

    validation = validate_candidate(inputs, result.legs)
    assert validation.accepted
    assert validation.estimated_tax_benefit_usd is not None
    assert result.metadata.tax_region_search_complete
    assert not result.metadata.integer_search_complete
    assert result.metadata.solver_versions
    assert result.metadata.implementation_version
    assert len(result.metadata.trade_group_priorities) == 1
    priority = result.metadata.trade_group_priorities[0]
    assert priority.group_id == "sale:AAPL"
    assert priority.rank == 1
    assert priority.priority_score is not None
    assert dict(priority.objective_components)["objective_tax_weight"] > 0
    assert any("Configured candidate types: stock_tlh" in line for line in priority.rationale)

    tampered_sell = replace(sells[0], selected_lots=(LotAllocation("unknown-lot", sells[0].shares),))
    tampered = tuple(tampered_sell if leg.side == "SELL" else leg for leg in result.legs)
    assert not validate_candidate(inputs, tampered).accepted

    subset = resolve_subset(request, ("loss-lot",), time.monotonic() + 10)
    assert subset.status == "ready"
    assert subset.metadata.selected_lot_ids == ("loss-lot",)


def test_expired_deadline_returns_no_legs(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_objective_accessor(monkeypatch)
    result = optimize_worker(OptimizerRequest(_inputs()), time.monotonic() - 1)

    assert result.status == "deadline_exceeded"
    assert result.legs == ()
    assert "computation_deadline_exceeded" in result.metadata.warnings
