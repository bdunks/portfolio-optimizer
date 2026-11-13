from __future__ import annotations

from decimal import Decimal

from app.domain.portfolio_accounting import evaluate_portfolio
from tests.optimizer_benchmark_fixture import build_optimizer_benchmark_inputs


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
    assert {row.ticker for row in first.exposures} == {"VB", "VXF", "VTI", "VXUS"}
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
