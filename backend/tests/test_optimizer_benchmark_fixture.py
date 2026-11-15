from __future__ import annotations

import time
from datetime import timedelta
from decimal import Decimal

import pytest

from app.domain.exposure import aggregate_lookthrough_exposure
from app.domain.portfolio_accounting import evaluate_portfolio
from app.optimizer.core import OptimizerRequest, _build_sector_model, optimize_worker
from app.optimizer.validation import validate_candidate
from tests.optimizer_benchmark_fixture import build_optimizer_benchmark_inputs


def test_optimizer_benchmark_sector_fixture_is_complete_and_assessable() -> None:
    inputs = build_optimizer_benchmark_inputs(seed=17)
    sector_keys = {"technology", "healthcare", "other"}
    assert sum(
        (band.target_weight_pct for band in inputs.policy.sector_bands), start=Decimal(0)
    ) == Decimal(100)
    assert {band.sector_key for band in inputs.policy.sector_bands} == sector_keys
    assert all(band.band_pct == Decimal(8) for band in inputs.policy.sector_bands)

    held_and_candidate_tickers = {position.ticker for position in inputs.positions} | {
        "VTI",
        "VXUS",
    }
    for ticker in sorted(held_and_candidate_tickers):
        exposure = aggregate_lookthrough_exposure(inputs, tickers=(ticker,), dimension="sector")
        assert exposure.coverage.complete is True, ticker
        assert {row.exposure_key for row in exposure.values} <= sector_keys
        expected_value = next(
            (
                position.market_value_usd
                for position in inputs.positions
                if position.ticker == ticker
            ),
            Decimal(1),
        )
        assert (
            sum((row.value_usd for row in exposure.values), start=Decimal(0)) == expected_value
        ), ticker

    sector_model, reasons = _build_sector_model(inputs, inputs.positions)
    assert reasons == ()
    assert sector_model is not None


def test_optimizer_benchmark_fixture_is_deterministic_complete_and_full_sized() -> None:
    first = build_optimizer_benchmark_inputs(seed=17)
    second = build_optimizer_benchmark_inputs(seed=17)

    assert len(first.positions) == 460
    assert len(first.lots) == 2500
    assert len(first.quotes) == 462
    assert first.to_provenance() == second.to_provenance()
    variant = build_optimizer_benchmark_inputs(seed=18)
    assert first.to_provenance() != variant.to_provenance()
    assert first.source_checksum != variant.source_checksum
    assert first.source_metadata.transaction_history_complete is True
    assert first.source_metadata.lookthrough_complete is True
    assert {row.ticker for row in first.exposures} == {
        position.ticker for position in first.positions
    } | {"VB", "VXF", "VTI", "VXUS"}

    for ticker in {row.ticker for row in first.exposures}:
        for dimension in {row.dimension for row in first.exposures if row.ticker == ticker}:
            assert sum(
                (
                    row.weight
                    for row in first.exposures
                    if row.ticker == ticker and row.dimension == dimension
                ),
                start=Decimal(0),
            ) == Decimal(1)
    assert first.policy.settings.get("max_sell_tickers_per_batch") == 10
    assert first.policy.settings.get("max_sell_lots_per_batch") == 20
    assert first.policy.settings.get("max_total_orders_per_batch") == 12
    assert any(lot.shares == Decimal("0.01") for lot in first.lots)
    basis_comparisons: list[bool] = []
    for lot in first.lots:
        quote = first.quote_for(lot.ticker)
        assert quote is not None
        assert quote.last_usd is not None
        basis_comparisons.append(lot.adjusted_unit_basis_usd > quote.last_usd)
    assert any(basis_comparisons)
    assert any(not comparison for comparison in basis_comparisons)
    assert evaluate_portfolio(first).current.portfolio_total_usd > 1_000_000


def test_optimizer_benchmark_scenarios_are_deterministic_full_sized_and_explicit() -> None:
    baseline = build_optimizer_benchmark_inputs(seed=17)
    explicit_baseline = build_optimizer_benchmark_inputs(seed=17, scenario="baseline")
    assert baseline.to_provenance() == explicit_baseline.to_provenance()

    for scenario in ("baseline", "replacement_buy", "recent_loss"):
        first = build_optimizer_benchmark_inputs(seed=17, scenario=scenario)
        second = build_optimizer_benchmark_inputs(seed=17, scenario=scenario)
        held_tickers = {position.ticker for position in first.positions}
        assert len(first.positions) == len(held_tickers) == 460
        assert len(first.securities) == 462
        assert len(first.securities) - len(held_tickers) == 2
        assert len(first.lots) == 2500
        assert len(first.quotes) == 462
        assert {exposure.dimension for exposure in first.exposures} == {
            "sector",
            "benchmark",
            "security",
        }
        assert first.to_provenance() == second.to_provenance()
        assert first.source_metadata.lookthrough_complete is True


def test_recent_loss_scenario_links_recent_acquisition_to_lot_and_old_loss() -> None:
    inputs = build_optimizer_benchmark_inputs(seed=17, scenario="recent_loss")
    recent_lot = next(lot for lot in inputs.lots if lot.broker_lot_id == "EQ000-LOT-001")
    old_loss_lot = next(lot for lot in inputs.lots if lot.broker_lot_id == "EQ000-LOT-002")
    recent_buy = next(
        transaction
        for transaction in inputs.transactions
        if transaction.broker_transaction_key == "SCENARIO-RECENT-EQ000"
    )
    recent_start = inputs.proposed_trade_date - timedelta(days=30)

    assert recent_lot.ticker == "EQ000"
    assert old_loss_lot.ticker == "EQ000"
    assert recent_buy.ticker == "EQ000"
    assert recent_lot.acquired_date == recent_buy.trade_date
    assert recent_start <= recent_buy.trade_date <= inputs.proposed_trade_date
    assert recent_buy.is_acquisition is True
    assert recent_buy.broker_lot_id == recent_lot.broker_lot_id
    assert old_loss_lot.acquired_date < recent_start
    quote = inputs.quote_for("EQ000")
    assert quote is not None
    assert quote.last_usd is not None
    assert old_loss_lot.adjusted_unit_basis_usd > quote.last_usd


@pytest.mark.parametrize("scenario", ["replacement_buy", "recent_loss"])
def test_optimizer_benchmark_scenario_emits_independently_accepted_dependent_buy(
    scenario: str,
) -> None:
    inputs = build_optimizer_benchmark_inputs(seed=17, scenario=scenario)
    result = optimize_worker(OptimizerRequest(inputs), time.monotonic() + 10.0)

    assert result.status == "ready", (result.metadata.warnings, result.legs)
    sells = [leg for leg in result.legs if leg.side == "SELL"]
    buys = [leg for leg in result.legs if leg.side == "BUY"]
    assert len(sells) == len(buys) == 1
    assert sells[0].ticker == "EQ000"
    assert buys[0].ticker == "VTI"
    assert buys[0].depends_on_leg_ids == (sells[0].leg_id,)
    assert buys[0].shares > 0
    assert all(leg.shares == leg.shares.to_integral_value() for leg in result.legs)

    sold_lots = {
        allocation.broker_lot_id: allocation.shares for allocation in sells[0].selected_lots
    }
    expected_sold_lot_ids = {"EQ000-LOT-002"}
    if scenario == "recent_loss":
        expected_sold_lot_ids.add("EQ000-LOT-001")
    assert set(sold_lots) == expected_sold_lot_ids

    source_lot = next(lot for lot in inputs.lots if lot.broker_lot_id == "EQ000-LOT-002")
    source_sold_shares = sold_lots["EQ000-LOT-002"]
    assert source_lot.available_shares == Decimal(20)
    assert Decimal(0) < source_sold_shares <= source_lot.available_shares
    assert source_sold_shares == source_sold_shares.to_integral_value()
    if scenario == "recent_loss":
        assert sold_lots["EQ000-LOT-001"] == Decimal(1)

    validation = validate_candidate(inputs, result.legs)
    assert validation.accepted, validation.reasons
    assert validation.evaluation is not None
