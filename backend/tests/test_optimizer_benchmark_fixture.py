from __future__ import annotations

from decimal import Decimal

from app.domain.exposure import aggregate_lookthrough_exposure
from app.domain.portfolio_accounting import evaluate_portfolio
from app.optimizer.core import _build_sector_model
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
    assert any(
        lot.adjusted_unit_basis_usd > first.quote_for(lot.ticker).last_usd for lot in first.lots
    )
    assert any(
        lot.adjusted_unit_basis_usd < first.quote_for(lot.ticker).last_usd for lot in first.lots
    )
    assert evaluate_portfolio(first).current.portfolio_total_usd > 1_000_000
