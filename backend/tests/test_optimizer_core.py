from __future__ import annotations

import time
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import cast

import cvxpy as cp
import numpy as np
import pytest

import app.domain.wash as wash_module
import app.optimizer.core as core_module
import app.optimizer.validation as validation_module
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
    TransactionInput,
)
from app.domain.portfolio_accounting import ConsolidatedLeg, LotAllocation
from app.domain.tax import TaxAffineRegion, TaxProfile
from app.domain.wash import (
    ProposedBuy,
    ProposedLotSale,
    WashAssessmentDeadlineError,
    WashSaleAssessment,
)
from app.optimizer.core import (
    OptimizerRequest,
    TradeGroupPriority,
    _decimal_solution,
    _Screen,
    optimize_worker,
    resolve_subset,
)
from app.optimizer.validation import (
    CandidateValidation,
    ObjectivePolicy,
    read_objective_policy,
    validate_candidate,
)

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
            AllocationSleeve(
                "equity", None, True, target_pct=Decimal(90), drift_band_pp=Decimal(10)
            ),
            AllocationSleeve(
                "cash",
                None,
                True,
                cash_sleeve=True,
                target_pct=Decimal(10),
                drift_band_pp=Decimal(10),
            ),
        ),
        allowed_securities=(AllowedSecurity("NEWETF", "equity", None, 0, True, "replacement"),),
        overrides=(),
    )
    return FinancialInputs(
        account=AccountInput(
            1, "test-account", "Test", "BROKERAGE", None, "TEST", NOW, Decimal(0), Decimal(0)
        ),
        source_generation=1,
        proposed_trade_date=TRADE_DATE,
        policy=PolicyInput(
            "test-policy",
            allocation,
            PolicySettings(tuple(sorted(settings.items()))),
            status="ACTIVE",
            sector_bands=(PolicySectorBandInput("TEST", Decimal(100), Decimal(100)),),
        ),
        securities=(
            SecurityInput(SecurityIdentity("AAPL", "EQUITY")),
            SecurityInput(SecurityIdentity("NEWETF", "ETF")),
        ),
        positions=(
            PositionInput(
                "AAPL",
                "EQUITY",
                False,
                Decimal(10),
                1,
                NOW,
                Decimal(1000),
                SleeveAssignment("equity"),
            ),
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
        exposures=(
            LookThroughExposureInput(
                "NEWETF", "security", "US_MARKET", Decimal(1), "TEST", TRADE_DATE
            ),
            LookThroughExposureInput("AAPL", "sector", "TEST", Decimal(1), "TEST", TRADE_DATE),
            LookThroughExposureInput("NEWETF", "sector", "TEST", Decimal(1), "TEST", TRADE_DATE),
        ),
        source_metadata=InputSourceMetadata(
            sync_complete=True,
            transaction_history_complete=True,
            transaction_history_start_date=TRADE_DATE - timedelta(days=30),
            transaction_history_end_date=TRADE_DATE,
            lookthrough_complete=True,
        ),
    )


def _shared_funding_case() -> tuple[
    FinancialInputs,
    CandidateValidation,
    core_module._Screen,
    tuple[ConsolidatedLeg, ...],
]:
    inputs = _inputs()
    settings = dict(inputs.policy.settings.values)
    settings["max_sell_tickers_per_batch"] = 2
    settings["max_total_orders_per_batch"] = 3
    inputs = replace(
        inputs,
        policy=replace(
            inputs.policy,
            settings=PolicySettings(tuple(sorted(settings.items()))),
        ),
    )
    msft = SecurityInput(SecurityIdentity("MSFT", "EQUITY"))
    msft_position = PositionInput(
        "MSFT", "EQUITY", False, Decimal(10), 1, NOW, Decimal(1000), SleeveAssignment("equity")
    )
    msft_lot = LotInput(
        "MSFT",
        "msft-loss-lot",
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
    )
    inputs = replace(
        inputs,
        securities=(*inputs.securities, msft),
        positions=(*inputs.positions, msft_position),
        lots=(*inputs.lots, msft_lot),
        quotes=(
            *inputs.quotes,
            QuoteInput("MSFT", Decimal(100), Decimal(100), None, "TEST", NOW, "good", 1),
        ),
        exposures=(
            *inputs.exposures,
            LookThroughExposureInput("MSFT", "sector", "TEST", Decimal(1), "TEST", TRADE_DATE),
        ),
    )
    baseline = validate_candidate(inputs, ())
    assert baseline.accepted, baseline.reasons
    assert baseline.evaluation is not None
    sale_candidates = tuple(
        core_module._SaleCandidate(
            lot,
            Decimal(10),
            Decimal(100),
            Decimal(100),
            Decimal(-10),
            "LT",
            ("stock_tlh",),
            Decimal(1),
        )
        for lot in inputs.lots
    )
    screen = core_module._Screen(
        baseline.evaluation, sale_candidates, (), (), ("stock_tlh",), len(sale_candidates)
    )
    legs = (
        ConsolidatedLeg(
            "sell:AAPL",
            "SELL",
            "AAPL",
            Decimal(1),
            Decimal(100),
            (LotAllocation("loss-lot", Decimal(1)),),
            (),
            0,
            ("sale:AAPL",),
        ),
        ConsolidatedLeg(
            "sell:MSFT",
            "SELL",
            "MSFT",
            Decimal(1),
            Decimal(100),
            (LotAllocation("msft-loss-lot", Decimal(1)),),
            (),
            0,
            ("sale:MSFT",),
        ),
        ConsolidatedLeg(
            "buy:NEWETF",
            "BUY",
            "NEWETF",
            Decimal(2),
            Decimal(100),
            (),
            ("sell:AAPL", "sell:MSFT"),
            1,
            ("sale:AAPL", "sale:MSFT"),
        ),
    )
    return inputs, baseline, screen, legs


def _buy_only_components_case() -> tuple[
    FinancialInputs, CandidateValidation, core_module._Screen, tuple[ConsolidatedLeg, ...]
]:
    inputs = _inputs()
    other_etf = SecurityInput(SecurityIdentity("OTHERETF", "ETF"))
    allocation = replace(
        inputs.policy.allocation,
        allowed_securities=(
            *inputs.policy.allocation.allowed_securities,
            AllowedSecurity("OTHERETF", "equity", None, 0, True, "replacement"),
        ),
    )
    inputs = replace(
        inputs,
        account=replace(
            inputs.account, cash_usd=Decimal(500), settled_buying_power_usd=Decimal(500)
        ),
        policy=replace(inputs.policy, allocation=allocation),
        securities=(*inputs.securities, other_etf),
        quotes=(
            *inputs.quotes,
            QuoteInput("OTHERETF", Decimal(100), Decimal(100), None, "TEST", NOW, "good", 1),
        ),
        exposures=(
            *inputs.exposures,
            LookThroughExposureInput(
                "OTHERETF", "security", "US_MARKET", Decimal(1), "TEST", TRADE_DATE
            ),
            LookThroughExposureInput("OTHERETF", "sector", "TEST", Decimal(1), "TEST", TRADE_DATE),
        ),
    )
    baseline = validate_candidate(inputs, ())
    assert baseline.accepted, baseline.reasons
    assert baseline.evaluation is not None
    screen = core_module._Screen(baseline.evaluation, (), (), (), (), 0)
    legs = (
        ConsolidatedLeg(
            "buy:NEWETF", "BUY", "NEWETF", Decimal(1), Decimal(100), group_ids=("buy:NEWETF",)
        ),
        ConsolidatedLeg(
            "buy:OTHERETF", "BUY", "OTHERETF", Decimal(1), Decimal(100), group_ids=("buy:OTHERETF",)
        ),
    )
    return inputs, baseline, screen, legs


def _drift_test_inputs(
    equity_value: int, cash_value: int, *, nested: bool = False
) -> FinancialInputs:
    inputs = _inputs()
    shares = Decimal(equity_value) / Decimal(50)
    sleeve_rows = (
        (
            AllocationSleeve(
                "equity", None, True, target_pct=Decimal(50), drift_band_pp=Decimal(50)
            ),
            AllocationSleeve(
                "cash",
                None,
                True,
                cash_sleeve=True,
                target_pct=Decimal(50),
                drift_band_pp=Decimal(50),
            ),
            AllocationSleeve(
                "child-one", "equity", True, target_pct=Decimal(50), drift_band_pp=Decimal(10)
            ),
            AllocationSleeve(
                "child-two", "equity", True, target_pct=Decimal(50), drift_band_pp=Decimal(10)
            ),
        )
        if nested
        else (
            AllocationSleeve(
                "equity", None, True, target_pct=Decimal(50), drift_band_pp=Decimal(5)
            ),
            AllocationSleeve(
                "cash",
                None,
                True,
                cash_sleeve=True,
                target_pct=Decimal(50),
                drift_band_pp=Decimal(5),
            ),
        )
    )
    allocation = replace(inputs.policy.allocation, sleeves=sleeve_rows)
    first_position_shares = shares / Decimal(2) if nested else shares
    first_position = replace(
        inputs.positions[0],
        shares=first_position_shares,
        market_value_usd=Decimal(equity_value) / Decimal(2) if nested else Decimal(equity_value),
        assignment=SleeveAssignment("equity", "child-one" if nested else None),
    )
    positions = (first_position,)
    lots = (
        replace(
            inputs.lots[0],
            shares=first_position_shares,
            available_shares=first_position_shares,
            adjusted_unit_basis_usd=Decimal(55),
        ),
    )
    if nested:
        positions = (
            *positions,
            PositionInput(
                "NEWETF",
                "ETF",
                False,
                first_position_shares,
                1,
                NOW,
                Decimal(equity_value) / Decimal(2),
                SleeveAssignment("equity", "child-two"),
            ),
        )
    return replace(
        inputs,
        account=replace(
            inputs.account,
            cash_usd=Decimal(cash_value),
            settled_buying_power_usd=Decimal(cash_value),
        ),
        policy=replace(inputs.policy, allocation=allocation),
        positions=positions,
        lots=lots,
        quotes=tuple(
            replace(quote, bid_usd=Decimal(50), ask_usd=Decimal(50)) for quote in inputs.quotes
        ),
    )


def _install_objective_accessor(monkeypatch: pytest.MonkeyPatch) -> None:
    def decimal_value(settings: PolicySettings, key: str) -> Decimal | None:
        value = settings.get(key)
        return value if isinstance(value, Decimal) else None

    monkeypatch.setattr(PolicySettings, "decimal", decimal_value, raising=False)


def test_worker_requires_persisted_objective_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_objective_accessor(monkeypatch)
    result = optimize_worker(
        OptimizerRequest(_inputs(objective_settings=False)), time.monotonic() + 1
    )

    assert result.status == "configuration_required"
    assert "configuration_required:objective_band_weight" in result.metadata.warnings
    assert result.legs == ()


def test_policy_settings_get_provides_typed_objective_decimals() -> None:
    config, reasons = read_objective_policy(_inputs())

    assert config is not None
    assert reasons == ()
    assert config.weight("objective_tax_weight") == Decimal(1)
    assert config.estimated_spread_bps == Decimal(0)


def test_owner_applies_order_fee_once_to_tax_and_cash(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_objective_accessor(monkeypatch)
    inputs = _inputs()
    settings = dict(inputs.policy.settings.values)
    settings["estimated_fee_per_order_usd"] = Decimal(2)
    settings["cash_reserve_usd"] = Decimal(97)
    inputs = replace(
        inputs,
        lots=(replace(inputs.lots[0], adjusted_unit_basis_usd=Decimal(99)),),
        policy=replace(
            inputs.policy,
            settings=PolicySettings(tuple(sorted(settings.items()))),
        ),
    )
    sale = ConsolidatedLeg(
        "sell:AAPL",
        "SELL",
        "AAPL",
        Decimal(1),
        Decimal(100),
        (LotAllocation("loss-lot", Decimal(1)),),
        (),
        0,
        ("sale:AAPL",),
    )

    result = validate_candidate(inputs, (sale,))

    assert result.accepted, result.reasons
    assert result.evaluation is not None
    assert result.evaluation.realized_st_usd == Decimal(-1)
    assert result.evaluation.proposed.cash_usd == Decimal(98)
    assert result.evaluation.proposed.portfolio_total_usd == Decimal(998)
    assert result.estimated_trading_cost_usd == Decimal(2)

    wash_inputs = replace(
        inputs,
        transactions=(
            TransactionInput(
                "recent-aapl-buy",
                "AAPL",
                "BUY",
                NOW - timedelta(days=10),
                TRADE_DATE - timedelta(days=10),
                Decimal(1),
                Decimal(100),
                True,
                "untracked-recent-lot",
                "TEST",
            ),
        ),
    )
    wash_result = validate_candidate(wash_inputs, (sale,))

    assert not wash_result.accepted
    assert any(
        reason.startswith("wash_sale_ineligible:AAPL:loss-lot:") for reason in wash_result.reasons
    )


def test_worker_uses_order_fee_to_find_fee_flipped_loss_with_zero_gain_caps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_objective_accessor(monkeypatch)
    inputs = _inputs()
    settings = dict(inputs.policy.settings.values)
    settings["estimated_fee_per_order_usd"] = Decimal(2)
    assert settings["allow_gain_sales"] is False
    assert (
        settings["gain_budget_usd"]
        == settings["st_gain_limit_usd"]
        == settings["lt_gain_limit_usd"]
        == 0
    )
    allocation = replace(
        inputs.policy.allocation,
        sleeves=(
            replace(
                inputs.policy.allocation.sleeves[0],
                target_pct=Decimal(0),
                drift_band_pp=Decimal(100),
            ),
            replace(
                inputs.policy.allocation.sleeves[1],
                target_pct=Decimal(100),
                drift_band_pp=Decimal(100),
            ),
        ),
    )
    inputs = replace(
        inputs,
        positions=(replace(inputs.positions[0], shares=Decimal(1), market_value_usd=Decimal(100)),),
        lots=(
            replace(
                inputs.lots[0],
                shares=Decimal(1),
                available_shares=Decimal(1),
                adjusted_unit_basis_usd=Decimal(99),
            ),
        ),
        policy=replace(
            inputs.policy,
            allocation=allocation,
            settings=PolicySettings(tuple(sorted(settings.items()))),
        ),
    )

    result = optimize_worker(
        OptimizerRequest(inputs, sell_lot_ids=("loss-lot",)), time.monotonic() + 10
    )

    assert result.status == "ready", (result.metadata.warnings, result.metadata.solver_statuses)
    sells = [leg for leg in result.legs if leg.side == "SELL"]
    assert len(sells) == 1
    assert sells[0].shares == Decimal(1)
    validation = validate_candidate(inputs, result.legs)
    assert validation.accepted, validation.reasons
    assert validation.evaluation is not None
    assert validation.evaluation.realized_st_usd == Decimal(-1)
    assert "stock_tlh" in result.metadata.candidate_types
    assert any(
        warning.startswith("fixed_order_fee_tax_proxy:") for warning in result.metadata.warnings
    )


def test_consolidated_multi_lot_sell_allocates_one_fee_across_tax_terms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_objective_accessor(monkeypatch)
    inputs = _inputs()
    settings = dict(inputs.policy.settings.values)
    settings.update(
        {
            "estimated_fee_per_order_usd": Decimal(2),
            "gain_budget_usd": Decimal(2),
            "st_gain_limit_usd": Decimal(1),
            "lt_gain_limit_usd": Decimal(1),
            "max_incremental_tax_cost_usd": Decimal(1),
            "allow_gain_sales": True,
        }
    )
    allocation = replace(
        inputs.policy.allocation,
        sleeves=(
            replace(
                inputs.policy.allocation.sleeves[0],
                target_pct=Decimal(0),
                drift_band_pp=Decimal(100),
            ),
            replace(
                inputs.policy.allocation.sleeves[1],
                target_pct=Decimal(100),
                drift_band_pp=Decimal(100),
            ),
        ),
    )
    short_lot = replace(
        inputs.lots[0],
        shares=Decimal(1),
        available_shares=Decimal(1),
        adjusted_unit_basis_usd=Decimal(98),
    )
    long_lot = replace(
        short_lot,
        broker_lot_id="long-lot",
        acquired_date=TRADE_DATE - timedelta(days=400),
    )
    inputs = replace(
        inputs,
        positions=(replace(inputs.positions[0], shares=Decimal(2), market_value_usd=Decimal(200)),),
        lots=(short_lot, long_lot),
        policy=replace(
            inputs.policy,
            allocation=allocation,
            settings=PolicySettings(tuple(sorted(settings.items()))),
        ),
    )
    sale = ConsolidatedLeg(
        "sell:AAPL",
        "SELL",
        "AAPL",
        Decimal(2),
        Decimal(100),
        (LotAllocation("loss-lot", Decimal(1)), LotAllocation("long-lot", Decimal(1))),
        (),
        0,
        ("sale:AAPL",),
    )

    result = validate_candidate(inputs, (sale,))

    assert result.accepted, result.reasons
    assert result.evaluation is not None
    assert result.evaluation.realized_st_usd == Decimal(1)
    assert result.evaluation.realized_lt_usd == Decimal(1)
    assert result.evaluation.proposed.cash_usd == Decimal(198)
    assert result.evaluation.proposed.portfolio_total_usd == Decimal(198)
    assert result.estimated_trading_cost_usd == Decimal(2)


@pytest.mark.parametrize(
    ("equity_value", "cash_value", "side", "shares", "accepted"),
    [
        (700, 300, "SELL", 5, True),
        (700, 300, "SELL", 6, False),
        (300, 700, "BUY", 5, True),
        (300, 700, "BUY", 6, False),
    ],
)
def test_validator_enforces_asymmetric_sleeve_bounds_and_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    equity_value: int,
    cash_value: int,
    side: str,
    shares: int,
    accepted: bool,
) -> None:
    _install_objective_accessor(monkeypatch)
    inputs = _drift_test_inputs(equity_value, cash_value)
    leg = (
        ConsolidatedLeg(
            "sell:AAPL",
            "SELL",
            "AAPL",
            Decimal(shares),
            Decimal(50),
            (LotAllocation("loss-lot", Decimal(shares)),),
            (),
            0,
            ("sale:AAPL",),
        )
        if side == "SELL"
        else ConsolidatedLeg(
            "buy:NEWETF", "BUY", "NEWETF", Decimal(shares), Decimal(50), (), (), 1, ("buy:NEWETF",)
        )
    )

    validation = validate_candidate(inputs, (leg,))

    assert validation.accepted is accepted
    if not accepted:
        assert "sleeve_drift_worsened:equity" in validation.reasons


@pytest.mark.parametrize(("shares", "accepted"), [(2, True), (3, False)])
def test_validator_scales_nested_band_to_actual_parent_ratio(
    monkeypatch: pytest.MonkeyPatch, shares: int, accepted: bool
) -> None:
    _install_objective_accessor(monkeypatch)
    inputs = _drift_test_inputs(700, 300, nested=True)
    leg = ConsolidatedLeg(
        "sell:AAPL",
        "SELL",
        "AAPL",
        Decimal(shares),
        Decimal(50),
        (LotAllocation("loss-lot", Decimal(shares)),),
        (),
        0,
        ("sale:AAPL",),
    )

    validation = validate_candidate(inputs, (leg,))

    assert validation.accepted is accepted
    if not accepted:
        assert "sleeve_drift_worsened:child-one" in validation.reasons


@pytest.mark.parametrize(
    ("case", "expected_reason"),
    [
        ("untradable", "security_not_tradable:AAPL"),
        ("bad_quote", "frozen_quote_stale_or_unusable:AAPL"),
        ("future_quote", "frozen_quote_stale_or_unusable:AAPL"),
        ("wrong_quote_generation", "frozen_quote_stale_or_unusable:AAPL"),
        ("execution_price", "execution_price_not_frozen_quote_derivation:AAPL"),
        ("unknown_sync", "source_sync_incomplete_or_unknown"),
        ("stale_position", "frozen_position_stale:AAPL"),
        ("stale_lot", "frozen_lot_stale:AAPL:loss-lot"),
    ],
)
def test_owner_rechecks_frozen_tradability_and_quote_provenance(
    monkeypatch: pytest.MonkeyPatch, case: str, expected_reason: str
) -> None:
    _install_objective_accessor(monkeypatch)
    inputs = _drift_test_inputs(700, 300)
    leg = ConsolidatedLeg(
        "sell:AAPL",
        "SELL",
        "AAPL",
        Decimal(1),
        Decimal(50),
        (LotAllocation("loss-lot", Decimal(1)),),
        (),
        0,
        ("sale:AAPL",),
    )
    if case == "untradable":
        inputs = replace(
            inputs,
            securities=tuple(
                replace(row, tradable=False) if row.identity.ticker == "AAPL" else row
                for row in inputs.securities
            ),
        )
    elif case in {"bad_quote", "future_quote", "wrong_quote_generation"}:
        inputs = replace(
            inputs,
            quotes=tuple(
                replace(
                    row,
                    quality="bad" if case == "bad_quote" and row.ticker == "AAPL" else row.quality,
                    as_of=NOW + timedelta(seconds=1)
                    if case == "future_quote" and row.ticker == "AAPL"
                    else row.as_of,
                    sync_generation=0
                    if case == "wrong_quote_generation" and row.ticker == "AAPL"
                    else row.sync_generation,
                )
                if row.ticker == "AAPL"
                else row
                for row in inputs.quotes
            ),
        )
    elif case == "execution_price":
        leg = replace(leg, estimated_unit_price_usd=Decimal("50.01"))
    elif case == "unknown_sync":
        inputs = replace(
            inputs, source_metadata=replace(inputs.source_metadata, sync_complete=None)
        )
    elif case == "stale_position":
        inputs = replace(
            inputs,
            positions=tuple(
                replace(row, sync_generation=0) if row.ticker == "AAPL" else row
                for row in inputs.positions
            ),
        )
    elif case == "stale_lot":
        inputs = replace(inputs, lots=(replace(inputs.lots[0], sync_generation=0),))

    validation = validate_candidate(inputs, (leg,))

    assert not validation.accepted
    assert expected_reason in validation.reasons


@pytest.mark.parametrize("solver", ["OSQP", "CLARABEL"])
def test_decimal_solution_converts_positive_cvxpy_scalar(solver: str) -> None:
    variable = cp.Variable()
    problem = cp.Problem(cp.Minimize(cp.square(variable - 2)), [variable >= 1.5])
    problem.solve(solver=solver)

    assert problem.status == cp.OPTIMAL
    assert np.asarray(variable.value).shape == ()
    assert _decimal_solution(variable.value, Decimal(3)) == Decimal(2)


@pytest.mark.parametrize(
    ("value", "maximum", "expected"),
    [
        (np.array(2.75), Decimal(3), Decimal(2)),
        (np.array(8.0), Decimal(3), Decimal(3)),
        (np.array(float("nan")), Decimal(3), Decimal(0)),
        (np.array(-1.0), Decimal(3), Decimal(0)),
        (None, Decimal(3), Decimal(0)),
        (np.array([2.0]), Decimal(3), Decimal(0)),
        (np.array([[2.0]]), Decimal(3), Decimal(0)),
    ],
)
def test_decimal_solution_rejects_invalid_or_nonscalar_values(
    value: object, maximum: Decimal, expected: Decimal
) -> None:
    assert _decimal_solution(value, maximum) == expected


def test_validation_rejects_deadline_exceeded_during_wash(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [0.0]
    deadline = 5.0

    def delayed_wash(
        *_args: object, **_kwargs: object
    ) -> tuple[list[str], tuple[object, ...], tuple[object, ...]]:
        clock[0] = deadline
        return [], (), ()

    monkeypatch.setattr(validation_module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(validation_module, "_wash_validation", delayed_wash)
    _install_objective_accessor(monkeypatch)

    validation = validate_candidate(_inputs(), (), deadline)

    assert not validation.accepted
    assert "validation_deadline_exceeded" in validation.reasons
    assert validation.objective_value is None


def test_validation_catches_wash_owner_deadline_and_rejects_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_objective_accessor(monkeypatch)
    deadline = time.monotonic() + 10
    forwarded_deadlines: list[float | None] = []

    def expired_assessment(
        _inputs: FinancialInputs,
        proposed_sales: tuple[ProposedLotSale, ...],
        proposed_buys: tuple[ProposedBuy, ...] = (),
        *,
        deadline: float | None = None,
    ) -> tuple[WashSaleAssessment, ...]:
        assert proposed_sales == ()
        assert proposed_buys == ()
        forwarded_deadlines.append(deadline)
        raise WashAssessmentDeadlineError("wash-sale assessment deadline exceeded")

    monkeypatch.setattr(validation_module, "assess_wash_sales", expired_assessment)
    validation = validate_candidate(_inputs(), (), deadline)

    assert not validation.accepted
    assert validation.reasons == ("validation_deadline_exceeded",)
    assert validation.wash_assessments == ()
    assert forwarded_deadlines == [deadline]


def test_worker_owner_rechecks_deadline_after_group_priorities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [0.0]
    deadline = 5.0
    fake_time = SimpleNamespace(monotonic=lambda: clock[0])
    monkeypatch.setattr(core_module, "time", fake_time)
    monkeypatch.setattr(validation_module, "time", fake_time)

    monkeypatch.setattr(wash_module, "time", fake_time)
    _install_objective_accessor(monkeypatch)

    def expire_after_ranking(*_args: object) -> tuple[tuple[object, ...], tuple[str, ...]]:
        clock[0] = deadline
        return (), ()

    monkeypatch.setattr(core_module, "_group_priorities", expire_after_ranking)

    result = optimize_worker(OptimizerRequest(_inputs()), deadline)

    assert result.status == "deadline_exceeded"
    assert result.legs == ()
    assert "computation_deadline_exceeded" in result.metadata.warnings


def test_worker_metadata_separates_solve_and_repair_rank_timings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [0.0]
    fake_time = SimpleNamespace(monotonic=lambda: clock[0])
    monkeypatch.setattr(core_module, "time", fake_time)
    monkeypatch.setattr(validation_module, "time", fake_time)

    monkeypatch.setattr(wash_module, "time", fake_time)
    _install_objective_accessor(monkeypatch)
    calls = {"model": 0, "solve": 0, "repair": 0, "rank": 0}
    original_model = core_module._model_region
    original_solve = core_module._solve_problem
    original_repair = core_module._repair_and_validate
    original_rank = core_module._group_priorities

    def timed_model(
        request: OptimizerRequest,
        screen: _Screen,
        config: ObjectivePolicy,
        limits: tuple[int, int, int, Decimal, Decimal, Decimal],
        profile: TaxProfile,
        region: TaxAffineRegion | None,
    ) -> tuple[cp.Problem, tuple[cp.Variable, ...], tuple[cp.Variable, ...]]:
        result = original_model(request, screen, config, limits, profile, region)
        calls["model"] += 1
        clock[0] += 2
        return result

    def timed_solve(
        problem: cp.Problem, deadline: float, regions_remaining: int
    ) -> tuple[str | None, str]:
        result = original_solve(problem, deadline, regions_remaining)
        calls["solve"] += 1
        clock[0] += 3
        return result

    def timed_repair(
        inputs: FinancialInputs,
        legs: tuple[ConsolidatedLeg, ...],
        deadline: float,
        mandatory_clearance_shares: tuple[tuple[str, Decimal], ...] = (),
    ) -> tuple[tuple[ConsolidatedLeg, ...] | None, CandidateValidation | None, int]:
        result = original_repair(inputs, legs, deadline, mandatory_clearance_shares)
        calls["repair"] += 1
        clock[0] += 4
        return result

    def timed_rank(
        inputs: FinancialInputs,
        screen: _Screen,
        baseline: CandidateValidation,
        legs: tuple[ConsolidatedLeg, ...],
        deadline: float,
    ) -> tuple[tuple[TradeGroupPriority, ...], tuple[str, ...]]:
        result = original_rank(inputs, screen, baseline, legs, deadline)
        calls["rank"] += 1
        clock[0] += 5
        return result

    monkeypatch.setattr(core_module, "_model_region", timed_model)
    monkeypatch.setattr(core_module, "_solve_problem", timed_solve)
    monkeypatch.setattr(core_module, "_repair_and_validate", timed_repair)
    monkeypatch.setattr(core_module, "_group_priorities", timed_rank)

    result = optimize_worker(OptimizerRequest(_inputs()), 100.0)

    assert result.status == "ready"
    assert calls["model"] == calls["solve"] > 0
    assert calls["repair"] > 0
    assert calls["rank"] == 1
    assert result.metadata.solve_seconds == float(5 * calls["solve"])
    assert result.metadata.repair_validate_rank_seconds == float(4 * calls["repair"] + 5)
    assert result.metadata.elapsed_seconds == (
        result.metadata.solve_seconds + result.metadata.repair_validate_rank_seconds
    )


def test_no_trade_preserves_baseline_objective(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_objective_accessor(monkeypatch)
    inputs = _inputs()
    inputs = replace(inputs, lots=(replace(inputs.lots[0], adjusted_unit_basis_usd=Decimal(100)),))

    result = optimize_worker(OptimizerRequest(inputs), time.monotonic() + 10)

    assert result.status == "no_trade"
    assert result.legs == ()
    assert result.metadata.objective_value == result.metadata.baseline_objective_value


def test_worker_can_sell_to_repair_unfunded_cash_reserve(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_objective_accessor(monkeypatch)
    inputs = _inputs()
    inputs = replace(inputs, lots=(replace(inputs.lots[0], adjusted_unit_basis_usd=Decimal(10)),))
    overrides: dict[str, Decimal | bool] = {
        key: Decimal(100)
        for key in (
            "cash_reserve_usd",
            "gain_budget_usd",
            "max_incremental_tax_cost_usd",
            "st_gain_limit_usd",
            "lt_gain_limit_usd",
        )
    }
    overrides["allow_gain_sales"] = True
    settings = tuple(
        (key, overrides.get(key, value)) for key, value in inputs.policy.settings.values
    )
    inputs = replace(inputs, policy=replace(inputs.policy, settings=PolicySettings(settings)))

    result = optimize_worker(OptimizerRequest(inputs), time.monotonic() + 10)

    assert result.status == "ready"
    assert result.legs
    assert any(leg.side == "SELL" for leg in result.legs)
    validation = validate_candidate(inputs, result.legs)
    assert validation.accepted
    assert validation.evaluation is not None
    assert validation.evaluation.proposed.cash_usd >= Decimal(100)
    assert result.metadata.objective_value is not None
    assert result.metadata.baseline_objective_value is not None
    assert result.metadata.objective_value > result.metadata.baseline_objective_value


def test_worker_never_publishes_no_trade_when_reserve_is_unmet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_objective_accessor(monkeypatch)
    inputs = _inputs()
    inputs = replace(inputs, lots=(replace(inputs.lots[0], adjusted_unit_basis_usd=Decimal(100)),))
    settings = tuple(
        (key, Decimal(1) if key == "cash_reserve_usd" else value)
        for key, value in inputs.policy.settings.values
    )
    inputs = replace(inputs, policy=replace(inputs.policy, settings=PolicySettings(settings)))

    result = optimize_worker(OptimizerRequest(inputs), time.monotonic() + 10)

    assert result.status == "infeasible"
    assert result.legs == ()
    assert "cash_reserve_breached_after_fees" in result.metadata.warnings

    assert result.metadata.tax_region_search_complete
    assert result.metadata.solver_statuses
    assert all(status.endswith(f":{cp.INFEASIBLE}") for status in result.metadata.solver_statuses)


def test_connected_sell_groups_and_shared_buy_emit_one_exactly_scored_opportunity() -> None:
    inputs, baseline, screen, legs = _shared_funding_case()
    deadline = time.monotonic() + 5
    exact_validation = validate_candidate(inputs, legs, deadline)
    assert exact_validation.accepted, exact_validation.reasons
    assert exact_validation.objective_components

    priorities, warnings = core_module._group_priorities(inputs, screen, baseline, legs, deadline)
    assert warnings == ()
    assert len(priorities) == 1
    priority = priorities[0]
    assert priority.group_id == "sale:AAPL"
    assert priority.rank == 1
    assert priority.priority_score == sum(
        (
            dict(baseline.objective_components)[key]
            - dict(exact_validation.objective_components)[key]
            for key, _ in baseline.objective_components
        ),
        Decimal(0),
    )
    assert any(
        "Original member group IDs: sale:AAPL, sale:MSFT." in item for item in priority.rationale
    )
    assert any(
        "Funding and replacement BUYs included: NEWETF." in item for item in priority.rationale
    )

    coherent = core_module._cohere_trade_group_legs(legs)
    assert tuple(leg.group_ids for leg in coherent) == (("sale:AAPL",),) * 3
    assert coherent[2].depends_on_leg_ids == ("sell:AAPL", "sell:MSFT")
    assert tuple(leg.selected_lots for leg in coherent[:2]) == tuple(
        leg.selected_lots for leg in legs[:2]
    )
    assert tuple(leg.shares for leg in coherent) == tuple(leg.shares for leg in legs)
    assert tuple(leg.estimated_unit_price_usd for leg in coherent) == tuple(
        leg.estimated_unit_price_usd for leg in legs
    )
    assert len({row.priority_score for row in priorities}) == 1


def test_independent_buy_only_components_keep_deterministic_separate_ranks() -> None:
    inputs, baseline, screen, legs = _buy_only_components_case()
    deadline = time.monotonic() + 5
    forward, forward_warnings = core_module._group_priorities(
        inputs, screen, baseline, legs, deadline
    )
    reverse, reverse_warnings = core_module._group_priorities(
        inputs, screen, baseline, tuple(reversed(legs)), deadline
    )

    assert forward_warnings == reverse_warnings == ()
    assert len(forward) == len(reverse) == 2
    assert [(item.group_id, item.rank, item.priority_score) for item in forward] == [
        (item.group_id, item.rank, item.priority_score) for item in reverse
    ]
    assert {item.group_id for item in forward} == {"buy:NEWETF", "buy:OTHERETF"}
    assert {item.group_id for item in forward} == {
        leg.group_ids[0] for leg in core_module._cohere_trade_group_legs(legs)
    }
    assert all(item.priority_score is not None for item in forward)


def test_joint_loss_harvest_is_independently_validated_and_prioritized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    assert all(leg.group_ids == (priority.group_id,) for leg in result.legs)
    assert priority.priority_score is not None
    assert dict(priority.objective_components)["objective_tax_weight"] > 0
    assert any(
        "Funding and replacement BUYs included: NEWETF." in line for line in priority.rationale
    )
    assert any("Configured candidate types: stock_tlh" in line for line in priority.rationale)

    tampered_sell = replace(
        sells[0], selected_lots=(LotAllocation("unknown-lot", sells[0].shares),)
    )
    tampered = tuple(tampered_sell if leg.side == "SELL" else leg for leg in result.legs)
    assert not validate_candidate(inputs, tampered).accepted

    subset = resolve_subset(request, ("loss-lot",), time.monotonic() + 10)
    assert subset.status == "ready"
    assert subset.metadata.selected_lot_ids == ("loss-lot",)
    assert len(subset.metadata.trade_group_priorities) == 1
    assert all(
        leg.group_ids == (subset.metadata.trade_group_priorities[0].group_id,)
        for leg in subset.legs
    )
    assert {
        allocation.broker_lot_id
        for leg in subset.legs
        if leg.side == "SELL"
        for allocation in leg.selected_lots
    } == {"loss-lot"}


def test_subset_requires_a_positive_whole_share_for_each_selected_lot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_objective_accessor(monkeypatch)
    inputs = _inputs()
    inputs = replace(
        inputs,
        lots=(replace(inputs.lots[0], available_shares=Decimal(1)),),
    )

    result = resolve_subset(OptimizerRequest(inputs), ("loss-lot",), time.monotonic() + 10)

    assert result.status == "ready", (result.metadata.warnings, result.metadata.solver_statuses)
    sells = [leg for leg in result.legs if leg.side == "SELL"]
    assert len(sells) == 1
    assert sells[0].shares == Decimal(1)
    assert sells[0].selected_lots == (LotAllocation("loss-lot", Decimal(1)),)


def test_subset_rejects_repair_that_drops_a_requested_lot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_objective_accessor(monkeypatch)
    inputs = _inputs()
    empty_validation = validate_candidate(inputs, ())

    def drop_selected_lot(
        _inputs: FinancialInputs,
        _legs: tuple[ConsolidatedLeg, ...],
        _deadline: float,
        _mandatory_clearance_shares: tuple[tuple[str, Decimal], ...] = (),
    ) -> tuple[tuple[ConsolidatedLeg, ...] | None, CandidateValidation | None, int]:
        return (), empty_validation, 0

    monkeypatch.setattr(core_module, "_repair_and_validate", drop_selected_lot)
    result = optimize_worker(OptimizerRequest(inputs, ("loss-lot",)), time.monotonic() + 10)

    assert result.status != "ready"
    assert result.legs == ()
    assert "selected_lot_set_mismatch" in result.metadata.solver_statuses


def test_worker_fills_buy_slot_after_filtering_wash_blocked_priority_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_objective_accessor(monkeypatch)
    inputs = _inputs()
    settings = tuple(
        (key, Decimal(1) if key == "objective_allocation_weight" else value)
        for key, value in inputs.policy.settings.values
    )
    allocation = replace(
        inputs.policy.allocation,
        allowed_securities=(
            AllowedSecurity("NEWETF", "equity", None, 0, True, "replacement"),
            AllowedSecurity("ALTETF", "equity", None, 1, True, "replacement"),
        ),
    )
    blocked_loss = TransactionInput(
        "executed-loss",
        "NEWETF",
        "SELL",
        NOW - timedelta(days=10),
        TRADE_DATE - timedelta(days=10),
        Decimal(1),
        Decimal(100),
        False,
        None,
        "TEST",
        Decimal(-10),
    )
    inputs = replace(
        inputs,
        policy=replace(inputs.policy, allocation=allocation, settings=PolicySettings(settings)),
        securities=(*inputs.securities, SecurityInput(SecurityIdentity("ALTETF", "ETF"))),
        quotes=(
            *inputs.quotes,
            QuoteInput("ALTETF", Decimal(100), Decimal(100), None, "TEST", NOW, "good", 1),
        ),
        transactions=(blocked_loss,),
        exposures=(
            *inputs.exposures,
            LookThroughExposureInput(
                "ALTETF", "security", "US_MARKET", Decimal(1), "TEST", TRADE_DATE
            ),
            LookThroughExposureInput("ALTETF", "sector", "TEST", Decimal(1), "TEST", TRADE_DATE),
        ),
    )

    result = optimize_worker(OptimizerRequest(inputs), time.monotonic() + 10)

    assert result.status == "ready"
    assert any(leg.side == "BUY" and leg.ticker == "ALTETF" for leg in result.legs)
    assert not any(leg.side == "BUY" and leg.ticker == "NEWETF" for leg in result.legs)
    assert any(
        "buy_wash_sale_ineligible:NEWETF:executed_loss_restriction" in warning
        for warning in result.metadata.warnings
    )
    assert validate_candidate(inputs, result.legs).accepted


def _add_msft_loss_candidate(inputs: FinancialInputs) -> FinancialInputs:
    return replace(
        inputs,
        securities=(*inputs.securities, SecurityInput(SecurityIdentity("MSFT", "EQUITY"))),
        positions=(
            *inputs.positions,
            PositionInput(
                "MSFT",
                "EQUITY",
                False,
                Decimal(10),
                1,
                NOW,
                Decimal(1000),
                SleeveAssignment("equity"),
            ),
        ),
        lots=(
            *inputs.lots,
            LotInput(
                "MSFT",
                "msft-loss-lot",
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
            *inputs.quotes,
            QuoteInput("MSFT", Decimal(100), Decimal(100), None, "TEST", NOW, "good", 1),
        ),
        exposures=(
            *inputs.exposures,
            LookThroughExposureInput("MSFT", "sector", "TEST", Decimal(1), "TEST", TRADE_DATE),
        ),
    )


def _strict_equity_order_budget_inputs(inputs: FinancialInputs) -> FinancialInputs:
    settings = tuple(
        (key, 2 if key in {"max_sell_tickers_per_batch", "max_total_orders_per_batch"} else value)
        for key, value in inputs.policy.settings.values
    )
    equity, cash = inputs.policy.allocation.sleeves
    allocation = replace(
        inputs.policy.allocation,
        sleeves=(
            replace(equity, target_pct=Decimal(100), drift_band_pp=Decimal(0)),
            replace(cash, target_pct=Decimal(0), drift_band_pp=Decimal(0)),
        ),
    )
    return replace(
        inputs,
        policy=replace(
            inputs.policy,
            allocation=allocation,
            settings=PolicySettings(settings),
        ),
    )


def _small_cash_funding_inputs() -> FinancialInputs:
    inputs = _strict_equity_order_budget_inputs(_add_msft_loss_candidate(_inputs()))
    positions = tuple(
        replace(row, shares=Decimal(25), market_value_usd=Decimal(500)) for row in inputs.positions
    )
    lots = tuple(
        replace(
            row,
            shares=Decimal(1),
            available_shares=Decimal(1),
            adjusted_unit_basis_usd=Decimal(40),
        )
        for row in inputs.lots
    )
    quotes = tuple(
        replace(row, bid_usd=Decimal(20), ask_usd=Decimal(20))
        if row.ticker in {"AAPL", "MSFT"}
        else row
        for row in inputs.quotes
    )
    settings = tuple(
        (
            key,
            Decimal(10)
            if key == "objective_cleanup_weight"
            else Decimal(1)
            if key == "objective_allocation_weight"
            else Decimal(0)
            if key == "objective_tax_weight"
            else value,
        )
        for key, value in inputs.policy.settings.values
    )
    return replace(
        inputs,
        account=replace(
            inputs.account,
            cash_usd=Decimal(100),
            settled_buying_power_usd=Decimal(100),
        ),
        policy=replace(inputs.policy, settings=PolicySettings(settings)),
        positions=positions,
        lots=lots,
        quotes=quotes,
    )


def test_total_order_cap_keeps_feasible_single_sell(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_objective_accessor(monkeypatch)
    inputs = _add_msft_loss_candidate(_inputs())
    settings = tuple(
        (
            key,
            2
            if key == "max_sell_tickers_per_batch"
            else 1
            if key == "max_total_orders_per_batch"
            else value,
        )
        for key, value in inputs.policy.settings.values
    )
    inputs = replace(inputs, policy=replace(inputs.policy, settings=PolicySettings(settings)))

    result = optimize_worker(OptimizerRequest(inputs), time.monotonic() + 10)

    sells = [leg for leg in result.legs if leg.side == "SELL"]
    assert result.status == "ready"
    assert len(sells) == 1
    assert len({leg.ticker for leg in sells}) == 1
    assert len(result.legs) <= 1
    assert validate_candidate(inputs, result.legs).accepted


def test_total_order_budget_keeps_fundable_replacement_ahead_of_unrelated_priority_buy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_objective_accessor(monkeypatch)
    inputs = _strict_equity_order_budget_inputs(_add_msft_loss_candidate(_inputs()))
    unrelated = SecurityInput(SecurityIdentity("OTHERETF", "ETF"))
    allocation = replace(
        inputs.policy.allocation,
        sleeves=(
            *inputs.policy.allocation.sleeves,
            AllocationSleeve(
                "unrelated", None, True, target_pct=Decimal(0), drift_band_pp=Decimal(0)
            ),
        ),
        allowed_securities=(
            AllowedSecurity("OTHERETF", "unrelated", None, 0, True, "unrelated"),
            AllowedSecurity("NEWETF", "equity", None, 1, True, "replacement"),
        ),
    )
    inputs = replace(
        inputs,
        policy=replace(inputs.policy, allocation=allocation),
        securities=(*inputs.securities, unrelated),
        quotes=(
            *inputs.quotes,
            QuoteInput("OTHERETF", Decimal(100), Decimal(100), None, "TEST", NOW, "good", 1),
        ),
        exposures=(
            *inputs.exposures,
            LookThroughExposureInput(
                "OTHERETF", "security", "US_MARKET", Decimal(1), "TEST", TRADE_DATE
            ),
            LookThroughExposureInput("OTHERETF", "sector", "TEST", Decimal(1), "TEST", TRADE_DATE),
        ),
    )

    result = optimize_worker(OptimizerRequest(inputs), time.monotonic() + 10)

    assert result.status == "ready"
    assert len(result.legs) == 2
    assert [leg.side for leg in result.legs].count("SELL") == 1
    assert [leg.side for leg in result.legs].count("BUY") == 1
    assert next(leg for leg in result.legs if leg.side == "BUY").ticker == "NEWETF"
    assert validate_candidate(inputs, result.legs).accepted


def test_order_budget_recognizes_replacement_in_sibling_child_of_violated_parent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_objective_accessor(monkeypatch)
    inputs = _add_msft_loss_candidate(_inputs())
    settings = tuple(
        (key, 2 if key == "max_sell_tickers_per_batch" else value)
        for key, value in inputs.policy.settings.values
    )
    allocation = replace(
        inputs.policy.allocation,
        sleeves=(
            AllocationSleeve("us", None, True, target_pct=Decimal(100), drift_band_pp=Decimal(0)),
            AllocationSleeve(
                "cash",
                None,
                True,
                cash_sleeve=True,
                target_pct=Decimal(0),
                drift_band_pp=Decimal(0),
            ),
            AllocationSleeve(
                "legacy", "us", True, target_pct=Decimal(50), drift_band_pp=Decimal(50)
            ),
            AllocationSleeve("etf", "us", True, target_pct=Decimal(50), drift_band_pp=Decimal(50)),
        ),
        allowed_securities=(AllowedSecurity("NEWETF", "us", "etf", 0, True, "replacement"),),
    )
    inputs = replace(
        inputs,
        positions=tuple(
            replace(row, assignment=SleeveAssignment("us", "legacy")) for row in inputs.positions
        ),
        policy=replace(
            inputs.policy,
            allocation=allocation,
            settings=PolicySettings(settings),
        ),
    )

    result = optimize_worker(OptimizerRequest(inputs), time.monotonic() + 10)

    assert result.status == "ready"
    assert len(result.legs) == 2
    assert [leg.side for leg in result.legs].count("SELL") == 1
    assert [leg.side for leg in result.legs].count("BUY") == 1
    assert next(leg for leg in result.legs if leg.side == "BUY").ticker == "NEWETF"
    assert validate_candidate(inputs, result.legs).accepted


def test_order_budget_funds_minimum_buy_with_existing_cash_and_small_loss_sale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_objective_accessor(monkeypatch)
    inputs = _small_cash_funding_inputs()

    result = optimize_worker(OptimizerRequest(inputs), time.monotonic() + 10)

    assert result.status == "ready", (
        result.metadata.warnings,
        result.metadata.solver_statuses,
        result.legs,
    )
    sells = [leg for leg in result.legs if leg.side == "SELL"]
    buys = [leg for leg in result.legs if leg.side == "BUY"]
    assert len(sells) == len(buys) == 1
    assert sells[0].shares == Decimal(1)
    assert sells[0].shares * sells[0].estimated_unit_price_usd == Decimal(20)
    assert buys[0].shares * buys[0].estimated_unit_price_usd >= Decimal(100)
    validation = validate_candidate(inputs, result.legs)
    assert validation.accepted, validation.reasons
    assert validation.evaluation is not None
    assert validation.evaluation.proposed.cash_usd == Decimal(20)


@pytest.mark.parametrize(
    ("cash_usd", "settled_buying_power_usd", "cash_reserve_usd", "fee_per_order_usd"),
    [
        (Decimal(0), Decimal(100), Decimal(0), Decimal(0)),
        (Decimal(100), Decimal(100), Decimal(30), Decimal(0)),
        (Decimal(100), Decimal(100), Decimal(0), Decimal(11)),
    ],
    ids=("unsettled-cash-is-not-available-cash", "preserve-cash-reserve", "include-order-fees"),
)
def test_screen_does_not_reserve_unfundable_buy_capacity(
    monkeypatch: pytest.MonkeyPatch,
    cash_usd: Decimal,
    settled_buying_power_usd: Decimal,
    cash_reserve_usd: Decimal,
    fee_per_order_usd: Decimal,
) -> None:
    _install_objective_accessor(monkeypatch)
    inputs = _small_cash_funding_inputs()
    settings = tuple(
        (
            key,
            cash_reserve_usd
            if key == "cash_reserve_usd"
            else fee_per_order_usd
            if key == "estimated_fee_per_order_usd"
            else value,
        )
        for key, value in inputs.policy.settings.values
    )
    inputs = replace(
        inputs,
        account=replace(
            inputs.account,
            cash_usd=cash_usd,
            settled_buying_power_usd=settled_buying_power_usd,
        ),
        policy=replace(inputs.policy, settings=PolicySettings(settings)),
    )
    config, config_errors = read_objective_policy(inputs)
    assert config is not None
    assert config_errors == ()

    screen, screen_errors = core_module._screen(
        OptimizerRequest(inputs), config, time.monotonic() + 10
    )

    assert screen_errors == ()
    assert screen is not None
    assert len(screen.sales) == 2
    assert screen.buys == ()


def test_ineligible_replacement_does_not_reserve_buy_capacity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_objective_accessor(monkeypatch)
    inputs = _small_cash_funding_inputs()
    blocked_loss = TransactionInput(
        "recent-loss",
        "NEWETF",
        "SELL",
        NOW - timedelta(days=10),
        TRADE_DATE - timedelta(days=10),
        Decimal(1),
        Decimal(100),
        False,
        None,
        "TEST",
        Decimal(-10),
    )
    inputs = replace(inputs, transactions=(blocked_loss,))
    config, config_errors = read_objective_policy(inputs)
    assert config is not None
    assert config_errors == ()

    screen, screen_errors = core_module._screen(
        OptimizerRequest(inputs), config, time.monotonic() + 10
    )

    assert screen_errors == ()
    assert screen is not None
    assert len(screen.sales) == 2
    assert screen.buys == ()
    assert any("buy_wash_sale_ineligible:NEWETF" in warning for warning in screen.warnings)


def test_total_order_budget_keeps_sale_only_candidates_when_buy_is_unneeded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_objective_accessor(monkeypatch)
    inputs = _add_msft_loss_candidate(_inputs())
    settings = tuple(
        (key, 2 if key == "max_sell_tickers_per_batch" else value)
        for key, value in inputs.policy.settings.values
    )
    inputs = replace(
        inputs,
        policy=replace(inputs.policy, settings=PolicySettings(settings)),
    )
    config, config_errors = read_objective_policy(inputs)
    assert config is not None
    assert config_errors == ()

    screen, screen_errors = core_module._screen(
        OptimizerRequest(inputs), config, time.monotonic() + 10
    )

    assert screen_errors == ()
    assert screen is not None
    assert {candidate.lot.ticker for candidate in screen.sales} == {"AAPL", "MSFT"}
    assert screen.buys == ()


def test_wash_clearance_bundle_is_atomic_under_lot_capacity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_objective_accessor(monkeypatch)
    inputs = _add_msft_loss_candidate(_inputs())
    recent_date = TRADE_DATE - timedelta(days=10)
    recent_lot = replace(
        inputs.lots[0],
        broker_lot_id="recent-aapl-clearance-lot",
        acquired_date=recent_date,
        shares=Decimal(1),
        available_shares=Decimal(1),
        adjusted_unit_basis_usd=Decimal(95),
    )
    base_settings = tuple(
        (
            key,
            True
            if key == "allow_gain_sales"
            else Decimal(100)
            if key
            in {
                "gain_budget_usd",
                "max_incremental_tax_cost_usd",
                "st_gain_limit_usd",
                "lt_gain_limit_usd",
            }
            else 2
            if key == "max_sell_tickers_per_batch"
            else value,
        )
        for key, value in inputs.policy.settings.values
    )
    inputs = replace(
        inputs,
        positions=(
            replace(inputs.positions[0], shares=Decimal(11), market_value_usd=Decimal(1100)),
            inputs.positions[1],
        ),
        lots=(*inputs.lots, recent_lot),
        transactions=(
            TransactionInput(
                "recent-aapl-buy",
                "AAPL",
                "BUY",
                NOW - timedelta(days=10),
                recent_date,
                Decimal(1),
                Decimal(95),
                True,
                "recent-aapl-clearance-lot",
                "TEST",
                None,
            ),
        ),
        policy=replace(inputs.policy, settings=PolicySettings(base_settings)),
    )

    clearance_sale = ConsolidatedLeg(
        "sell:AAPL",
        "SELL",
        "AAPL",
        Decimal(2),
        Decimal(100),
        (
            LotAllocation("loss-lot", Decimal(1)),
            LotAllocation("recent-aapl-clearance-lot", Decimal(1)),
        ),
        (),
        0,
        ("sale:AAPL",),
    )
    assert validate_candidate(inputs, (clearance_sale,)).accepted

    for lot_limit, expected_lots in (
        (1, {"msft-loss-lot"}),
        (2, {"loss-lot", "recent-aapl-clearance-lot"}),
    ):
        settings = tuple(
            (key, lot_limit if key == "max_sell_lots_per_batch" else value)
            for key, value in base_settings
        )
        case_inputs = replace(
            inputs,
            policy=replace(
                inputs.policy,
                settings=PolicySettings(settings),
            ),
        )
        config, config_errors = read_objective_policy(case_inputs)
        assert config is not None
        assert config_errors == ()
        screen, screen_errors = core_module._screen(
            OptimizerRequest(case_inputs), config, time.monotonic() + 10
        )

        assert screen_errors == ()
        assert screen is not None
        assert {candidate.lot.broker_lot_id for candidate in screen.sales} == expected_lots


def test_wash_blocked_sell_does_not_consume_sell_screen_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_objective_accessor(monkeypatch)
    inputs = _add_msft_loss_candidate(_inputs())
    recent_date = TRADE_DATE - timedelta(days=10)
    recent_lot = replace(
        inputs.lots[0],
        broker_lot_id="recent-aapl-lot",
        acquired_date=recent_date,
        shares=Decimal(1),
        available_shares=Decimal(1),
        adjusted_unit_basis_usd=Decimal(100),
    )
    inputs = replace(
        inputs,
        positions=(
            replace(inputs.positions[0], shares=Decimal(11), market_value_usd=Decimal(1100)),
            inputs.positions[1],
        ),
        lots=(*inputs.lots, recent_lot),
        transactions=(
            TransactionInput(
                "recent-aapl-buy",
                "AAPL",
                "BUY",
                NOW - timedelta(days=10),
                recent_date,
                Decimal(1),
                Decimal(100),
                True,
                "recent-aapl-lot",
                "TEST",
                None,
            ),
        ),
    )

    result = optimize_worker(OptimizerRequest(inputs), time.monotonic() + 10)

    assert result.status == "ready"
    assert {leg.ticker for leg in result.legs if leg.side == "SELL"} == {"MSFT"}
    assert any(
        warning.startswith("sell_wash_sale_ineligible:AAPL:loss-lot:")
        for warning in result.metadata.warnings
    )
    assert validate_candidate(inputs, result.legs).accepted


def test_allocation_objective_uses_squared_decimal_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_objective_accessor(monkeypatch)
    inputs = _drift_test_inputs(700, 300)
    settings = tuple(
        (
            key,
            Decimal(1)
            if key == "objective_allocation_weight"
            else Decimal(0)
            if key.startswith("objective_")
            else value,
        )
        for key, value in inputs.policy.settings.values
    )
    inputs = replace(inputs, policy=replace(inputs.policy, settings=PolicySettings(settings)))
    leg = ConsolidatedLeg(
        "sell:AAPL",
        "SELL",
        "AAPL",
        Decimal(1),
        Decimal(50),
        (LotAllocation(inputs.lots[0].broker_lot_id, Decimal(1)),),
        (),
        0,
        ("sale:AAPL",),
    )

    result = validate_candidate(inputs, (leg,))

    assert result.accepted
    assert dict(result.objective_components)["objective_allocation_weight"] == Decimal("0.045")


def test_buy_only_trade_group_is_ranked(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_objective_accessor(monkeypatch)
    inputs = _inputs()
    settings = tuple(
        (
            key,
            Decimal(1)
            if key == "objective_allocation_weight"
            else Decimal(0)
            if key.startswith("objective_")
            else value,
        )
        for key, value in inputs.policy.settings.values
    )
    inputs = replace(
        inputs,
        account=replace(
            inputs.account, cash_usd=Decimal(500), settled_buying_power_usd=Decimal(500)
        ),
        lots=(replace(inputs.lots[0], adjusted_unit_basis_usd=Decimal(100)),),
        policy=replace(inputs.policy, settings=PolicySettings(settings)),
    )

    result = optimize_worker(OptimizerRequest(inputs), time.monotonic() + 10)

    assert result.status == "ready"
    assert result.legs
    assert all(leg.side == "BUY" for leg in result.legs)
    assert len(result.metadata.trade_group_priorities) == 1
    assert result.metadata.trade_group_priorities[0].group_id == "buy:NEWETF"
    assert all(
        leg.group_ids == (result.metadata.trade_group_priorities[0].group_id,)
        for leg in result.legs
    )
    assert any(
        "Funding and replacement BUYs included" in line
        for line in result.metadata.trade_group_priorities[0].rationale
    )


def test_solver_fallback_preserves_downstream_deadline_reserve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [20.0]
    monkeypatch.setattr(core_module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    calls: list[tuple[str, float]] = []

    class FakeProblem:
        status = cp.INFEASIBLE_INACCURATE

        def solve(self, *, solver: str, **kwargs: object) -> None:
            calls.append((solver, cast(float, kwargs["time_limit"])))
            if solver == cp.OSQP:
                clock[0] += 4.0
            else:
                self.status = cp.OPTIMAL

    solver_name, status = core_module._solve_problem(
        cast(cp.Problem, FakeProblem()), 30.0, regions_remaining=1
    )

    assert calls == [(cp.OSQP, 9.0), (cp.CLARABEL, 5.0)]
    assert solver_name == cp.CLARABEL
    assert status == cp.OPTIMAL


def test_worker_rejects_ready_basket_when_metadata_work_exceeds_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = time.monotonic()
    clock = [started]
    deadline = started + 10.0
    monkeypatch.setattr(core_module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    _install_objective_accessor(monkeypatch)

    def delayed_versions() -> tuple[tuple[str, str], ...]:
        clock[0] = deadline + 0.1
        return (("cvxpy", "test"),)

    monkeypatch.setattr(core_module, "_package_versions", delayed_versions)
    result = optimize_worker(OptimizerRequest(_inputs()), deadline)

    assert result.status == "deadline_exceeded"
    assert result.legs == ()
    assert result.metadata.status == "deadline_exceeded"
    assert result.metadata.selected_lot_ids == ()
    assert result.metadata.objective_value is None
    assert result.metadata.elapsed_seconds >= clock[0] - started
    assert "computation_deadline_exceeded" in result.metadata.warnings


def test_infeasible_inaccurate_status_retries_with_clarabel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class FakeProblem:
        status = cp.INFEASIBLE_INACCURATE

        def solve(self, *, solver: str, **kwargs: object) -> None:
            calls.append(solver)
            if solver == cp.CLARABEL:
                self.status = cp.OPTIMAL

    solver_name, status = core_module._solve_problem(
        cast(cp.Problem, FakeProblem()), time.monotonic() + 5, regions_remaining=1
    )

    assert calls == [cp.OSQP, cp.CLARABEL]
    assert solver_name == cp.CLARABEL
    assert status == cp.OPTIMAL


def test_unproven_infeasible_status_remains_incomplete(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_objective_accessor(monkeypatch)

    def unproven_solve(
        problem: cp.Problem, deadline: float, regions_remaining: int
    ) -> tuple[str | None, str]:
        del problem, deadline, regions_remaining
        return None, cp.INFEASIBLE_INACCURATE

    monkeypatch.setattr(core_module, "_solve_problem", unproven_solve)

    result = optimize_worker(OptimizerRequest(_inputs()), time.monotonic() + 10)

    assert result.status == "search_incomplete"
    assert result.legs == ()
    assert not result.metadata.tax_region_search_complete
    assert any("infeasible_inaccurate" in status for status in result.metadata.solver_statuses)


def test_invalid_baseline_with_inaccurate_solvers_is_search_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_objective_accessor(monkeypatch)
    inputs = _inputs()
    inputs = replace(inputs, lots=(replace(inputs.lots[0], adjusted_unit_basis_usd=Decimal(10)),))
    overrides: dict[str, Decimal | bool] = {
        key: Decimal(100)
        for key in (
            "cash_reserve_usd",
            "gain_budget_usd",
            "max_incremental_tax_cost_usd",
            "st_gain_limit_usd",
            "lt_gain_limit_usd",
        )
    }
    overrides["allow_gain_sales"] = True
    settings = tuple(
        (key, overrides.get(key, value)) for key, value in inputs.policy.settings.values
    )
    inputs = replace(inputs, policy=replace(inputs.policy, settings=PolicySettings(settings)))

    def both_solvers_inaccurate(
        problem: cp.Problem, deadline: float, regions_remaining: int
    ) -> tuple[str | None, str]:
        del problem, deadline, regions_remaining
        return f"{cp.OSQP}+{cp.CLARABEL}", cp.INFEASIBLE_INACCURATE

    monkeypatch.setattr(core_module, "_solve_problem", both_solvers_inaccurate)

    result = optimize_worker(OptimizerRequest(inputs), time.monotonic() + 10)

    assert result.status == "search_incomplete"
    assert result.legs == ()
    assert not result.metadata.tax_region_search_complete
    assert all(
        "infeasible_inaccurate" in solver_status
        for solver_status in result.metadata.solver_statuses
    )


def test_expired_deadline_returns_no_legs(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_objective_accessor(monkeypatch)
    result = optimize_worker(OptimizerRequest(_inputs()), time.monotonic() - 1)

    assert result.status == "deadline_exceeded"
    assert result.legs == ()
    assert "computation_deadline_exceeded" in result.metadata.warnings


def _sector_constrained_inputs() -> FinancialInputs:
    inputs = _inputs()
    bands = (
        PolicySectorBandInput("Technology", Decimal(100), Decimal(0)),
        PolicySectorBandInput("Healthcare", Decimal(0), Decimal(0)),
    )
    exposures = (
        *(row for row in inputs.exposures if row.dimension != "sector"),
        LookThroughExposureInput("AAPL", "sector", "Technology", Decimal(1), "TEST", TRADE_DATE),
        LookThroughExposureInput("NEWETF", "sector", "Healthcare", Decimal(1), "TEST", TRADE_DATE),
    )
    return replace(
        inputs,
        policy=replace(inputs.policy, sector_bands=bands),
        exposures=exposures,
    )


def test_active_policy_requires_explicit_sector_bands() -> None:
    inputs = _inputs()
    inputs = replace(inputs, policy=replace(inputs.policy, sector_bands=()))

    result = validate_candidate(inputs, ())

    assert not result.accepted
    assert "configuration_required:sector_bands" in result.reasons


def test_optimizer_reports_missing_active_sector_bands_as_configuration_required() -> None:
    inputs = _inputs()
    inputs = replace(inputs, policy=replace(inputs.policy, sector_bands=()))

    result = optimize_worker(OptimizerRequest(inputs), time.monotonic() + 10)

    assert result.status == "configuration_required"
    assert result.legs == ()
    assert "configuration_required:sector_bands" in result.metadata.warnings


def test_validator_rejects_replacement_that_worsens_sector_bands() -> None:
    inputs = _sector_constrained_inputs()
    sell = ConsolidatedLeg(
        "sell:AAPL",
        "SELL",
        "AAPL",
        Decimal(1),
        Decimal(100),
        (LotAllocation("loss-lot", Decimal(1)),),
        (),
        0,
        ("sale:AAPL",),
    )
    buy = ConsolidatedLeg(
        "buy:NEWETF",
        "BUY",
        "NEWETF",
        Decimal(1),
        Decimal(100),
        (),
        ("sell:AAPL",),
        1,
        ("sale:AAPL",),
    )

    result = validate_candidate(inputs, (sell, buy))

    assert not result.accepted
    assert "sector_drift_worsened:Technology" in result.reasons
    assert "sector_drift_worsened:Healthcare" in result.reasons


def test_worker_does_not_select_sector_band_violating_replacement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_objective_accessor(monkeypatch)
    inputs = _sector_constrained_inputs()

    result = optimize_worker(OptimizerRequest(inputs), time.monotonic() + 10)

    assert result.status == "ready"
    assert not any(leg.side == "BUY" and leg.ticker == "NEWETF" for leg in result.legs)
    assert validate_candidate(inputs, result.legs).accepted


def _wash_clearance_inputs(
    *,
    recent_shares: Decimal = Decimal(1),
    recent_available_shares: Decimal | None = None,
    add_second_loss: bool = False,
    lot_limit: int = 2,
) -> FinancialInputs:
    inputs = _inputs()
    recent_date = TRADE_DATE - timedelta(days=10)
    recent_lot = replace(
        inputs.lots[0],
        broker_lot_id="recent-aapl-clearance-lot",
        acquired_date=recent_date,
        shares=recent_shares,
        available_shares=(
            recent_shares if recent_available_shares is None else recent_available_shares
        ),
        adjusted_unit_basis_usd=Decimal(95),
    )
    settings = dict(inputs.policy.settings.values)
    settings.update(
        {
            "allow_gain_sales": True,
            "gain_budget_usd": Decimal(100),
            "max_incremental_tax_cost_usd": Decimal(100),
            "st_gain_limit_usd": Decimal(100),
            "lt_gain_limit_usd": Decimal(100),
            "max_sell_lots_per_batch": lot_limit,
            "max_sell_tickers_per_batch": 1,
            "max_total_orders_per_batch": 2,
        }
    )
    extra_lots = (recent_lot,)
    extra_shares = recent_shares
    if add_second_loss:
        extra_lots = (
            *extra_lots,
            replace(
                inputs.lots[0],
                broker_lot_id="older-aapl-loss-b",
                shares=Decimal(1),
                available_shares=Decimal(1),
                adjusted_unit_basis_usd=Decimal(101),
            ),
        )
        extra_shares += Decimal(1)
    return replace(
        inputs,
        positions=(
            replace(
                inputs.positions[0],
                shares=Decimal(10) + extra_shares,
                market_value_usd=Decimal(1000) + extra_shares * Decimal(100),
            ),
        ),
        lots=(*inputs.lots, *extra_lots),
        transactions=(
            TransactionInput(
                "recent-aapl-buy",
                "AAPL",
                "BUY",
                NOW - timedelta(days=10),
                recent_date,
                recent_shares,
                Decimal(95),
                True,
                recent_lot.broker_lot_id,
                "TEST",
                None,
            ),
        ),
        policy=replace(
            inputs.policy,
            settings=PolicySettings(tuple(sorted(settings.items()))),
        ),
    )


def test_worker_sells_full_recent_wash_clearance_quantity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_objective_accessor(monkeypatch)
    inputs = _wash_clearance_inputs()

    result = optimize_worker(OptimizerRequest(inputs), time.monotonic() + 10)

    assert result.status == "ready"
    sold_lots = {
        allocation.broker_lot_id: allocation.shares
        for leg in result.legs
        if leg.side == "SELL"
        for allocation in leg.selected_lots
    }
    assert sold_lots["loss-lot"] > 0
    assert sold_lots["recent-aapl-clearance-lot"] == Decimal(1)
    assert validate_candidate(inputs, result.legs).accepted


def test_shared_wash_clearance_does_not_merge_independent_losses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_objective_accessor(monkeypatch)
    inputs = _wash_clearance_inputs(add_second_loss=True, lot_limit=2)
    config, config_errors = read_objective_policy(inputs)
    assert config is not None
    assert config_errors == ()

    screen, screen_errors = core_module._screen(
        OptimizerRequest(inputs), config, time.monotonic() + 10
    )

    assert screen_errors == ()
    assert screen is not None
    selected_ids = {candidate.lot.broker_lot_id for candidate in screen.sales}
    assert "recent-aapl-clearance-lot" in selected_ids
    assert len(selected_ids) == 2
    assert selected_ids & {"loss-lot", "older-aapl-loss-b"}


def test_recent_loss_clearance_over_batch_cap_skips_owner_assessment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_objective_accessor(monkeypatch)
    inputs = _wash_clearance_inputs(lot_limit=2)
    recent_date = TRADE_DATE - timedelta(days=10)
    recent_lots = tuple(
        replace(
            inputs.lots[0],
            broker_lot_id=f"recent-loss-{index}",
            acquired_date=recent_date,
            shares=Decimal(1),
            available_shares=Decimal(1),
            adjusted_unit_basis_usd=Decimal(101),
        )
        for index in range(2500)
    )
    transactions = tuple(
        replace(
            inputs.transactions[0],
            broker_transaction_key=f"recent-buy-{index}",
            broker_lot_id=lot.broker_lot_id,
            shares=Decimal(1),
        )
        for index, lot in enumerate(recent_lots)
    )
    inputs = replace(
        inputs,
        positions=(
            replace(inputs.positions[0], shares=Decimal(2500), market_value_usd=Decimal(250000)),
        ),
        lots=recent_lots,
        transactions=transactions,
    )
    owner_calls = 0

    def unexpected_owner_assessment(
        _inputs: FinancialInputs,
        proposed_sales: tuple[ProposedLotSale, ...],
        *,
        deadline: float | None = None,
    ) -> tuple[WashSaleAssessment, ...]:
        nonlocal owner_calls
        owner_calls += 1
        pytest.fail(
            f"over-cap clearance materialized {len(proposed_sales)} owner proposals; {deadline=}"
        )

    monkeypatch.setattr(core_module, "assess_wash_sales", unexpected_owner_assessment)
    config, config_errors = read_objective_policy(inputs)
    assert config is not None
    assert config_errors == ()

    screen, screen_errors = core_module._screen(
        OptimizerRequest(inputs), config, time.monotonic() + 60
    )

    assert screen_errors == ()
    assert screen is not None
    assert screen.sales == ()
    assert owner_calls == 0
    assert (
        sum("clearance_exceeds_max_sell_lots_per_batch" in warning for warning in screen.warnings)
        == 2500
    )


def test_wash_dependency_owner_assessment_call_count_is_bounded_for_2500_lots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_objective_accessor(monkeypatch)
    inputs = _wash_clearance_inputs()
    recent_lot = inputs.lots[-1]
    lots = tuple(
        replace(
            inputs.lots[0],
            broker_lot_id=f"loss-{index}",
            shares=Decimal(1),
            available_shares=Decimal(1),
            adjusted_unit_basis_usd=Decimal(101),
        )
        for index in range(2499)
    )
    inputs = replace(
        inputs,
        positions=(
            replace(
                inputs.positions[0],
                shares=Decimal(2500),
                market_value_usd=Decimal(250000),
            ),
        ),
        lots=(*lots, recent_lot),
    )
    calls: list[int] = []

    def counted_assessment(
        _inputs: FinancialInputs,
        proposed_sales: tuple[ProposedLotSale, ...],
        *,
        deadline: float | None = None,
    ) -> tuple[WashSaleAssessment, ...]:
        assert deadline is not None
        calls.append(len(proposed_sales))
        return tuple(
            WashSaleAssessment(
                sale.ticker,
                sale.broker_lot_id,
                sale.trade_group_id,
                True,
                (),
                (),
                None,
                None,
            )
            for sale in proposed_sales
        )

    monkeypatch.setattr(core_module, "assess_wash_sales", counted_assessment)
    config, config_errors = read_objective_policy(inputs)
    assert config is not None
    assert config_errors == ()

    screen, screen_errors = core_module._screen(
        OptimizerRequest(inputs), config, time.monotonic() + 10
    )

    assert screen_errors == ()
    assert screen is not None
    assert len(calls) == 1
    assert sum(calls) <= 2


def test_wash_dependency_checks_deadline_after_owner_assessment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_objective_accessor(monkeypatch)
    clock = [0.0]
    deadline = 5.0
    monkeypatch.setattr(core_module, "time", SimpleNamespace(monotonic=lambda: clock[0]))

    def expire_during_assessment(
        _inputs: FinancialInputs,
        proposed_sales: tuple[ProposedLotSale, ...],
        *,
        deadline: float | None = None,
    ) -> tuple[WashSaleAssessment, ...]:
        assert deadline is not None
        assert deadline == 5.0
        clock[0] = deadline
        return tuple(
            WashSaleAssessment(
                sale.ticker,
                sale.broker_lot_id,
                sale.trade_group_id,
                True,
                (),
                (),
                None,
                None,
            )
            for sale in proposed_sales
        )

    monkeypatch.setattr(core_module, "assess_wash_sales", expire_during_assessment)
    config, config_errors = read_objective_policy(_inputs())
    assert config is not None
    assert config_errors == ()

    screen, errors = core_module._screen(OptimizerRequest(_inputs()), config, deadline)

    assert screen is None
    assert any("deadline" in error for error in errors)


def test_wash_owner_deadline_exception_stops_screen_without_partial_assessment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_objective_accessor(monkeypatch)
    monkeypatch.setattr(core_module, "time", SimpleNamespace(monotonic=lambda: 0.0))

    def expired_assessment(
        _inputs: FinancialInputs,
        proposed_sales: tuple[ProposedLotSale, ...],
        *,
        deadline: float | None = None,
    ) -> tuple[WashSaleAssessment, ...]:
        assert proposed_sales
        assert deadline == 5.0
        raise WashAssessmentDeadlineError("wash-sale assessment deadline exceeded")

    monkeypatch.setattr(core_module, "assess_wash_sales", expired_assessment)
    config, config_errors = read_objective_policy(_inputs())
    assert config is not None
    assert config_errors == ()

    screen, errors = core_module._screen(OptimizerRequest(_inputs()), config, 5.0)

    assert screen is None
    assert errors == ("deadline_during_sell_wash_screening",)


def test_fractional_recent_lot_cannot_clear_an_older_loss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_objective_accessor(monkeypatch)
    inputs = _wash_clearance_inputs(recent_shares=Decimal("1.5"), lot_limit=2)
    config, config_errors = read_objective_policy(inputs)
    assert config is not None
    assert config_errors == ()

    screen, screen_errors = core_module._screen(
        OptimizerRequest(inputs), config, time.monotonic() + 10
    )

    assert screen_errors == ()
    assert screen is not None
    assert "loss-lot" not in {candidate.lot.broker_lot_id for candidate in screen.sales}
