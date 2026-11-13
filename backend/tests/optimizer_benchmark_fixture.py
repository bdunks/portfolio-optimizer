"""Deterministic, realistic-sized inputs for the optimizer benchmark harness."""

from __future__ import annotations

import hashlib
import random
from datetime import UTC, date, datetime
from decimal import Decimal

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

TRADE_DATE = date(2026, 11, 5)
AS_OF = datetime(2026, 11, 5, 15, tzinfo=UTC)


def build_optimizer_benchmark_inputs(seed: int = 4602500) -> FinancialInputs:
    """Build 460 risky securities and 2,500 current lots with complete provenance."""
    rng = random.Random(seed)
    stock_tickers = tuple(f"EQ{i:03d}" for i in range(458))
    tickers = (*stock_tickers, "VB", "VXF")
    prices = {ticker: Decimal(35 + (i * 17 % 265)) for i, ticker in enumerate(tickers)}
    policy = AllocationPolicy(
        sleeves=(
            AllocationSleeve(
                "us",
                None,
                True,
                display_name="US equities",
                target_pct=Decimal(60),
                drift_band_pp=Decimal(5),
            ),
            AllocationSleeve(
                "direct",
                "us",
                True,
                direct_index_container=True,
                display_name="Direct indexing",
                target_pct=Decimal(100),
                drift_band_pp=Decimal(10),
            ),
            AllocationSleeve(
                "growth",
                "direct",
                True,
                direct_index_sleeve=True,
                display_name="Growth",
                target_pct=Decimal(50),
                drift_band_pp=Decimal(8),
            ),
            AllocationSleeve(
                "value",
                "direct",
                True,
                direct_index_sleeve=True,
                display_name="Value",
                target_pct=Decimal(50),
                drift_band_pp=Decimal(8),
            ),
            AllocationSleeve(
                "intl",
                None,
                True,
                display_name="International",
                target_pct=Decimal(30),
                drift_band_pp=Decimal(5),
            ),
            AllocationSleeve(
                "cash",
                None,
                True,
                cash_sleeve=True,
                display_name="Cash",
                target_pct=Decimal(10),
                drift_band_pp=Decimal(2),
            ),
        ),
        allowed_securities=tuple(
            [AllowedSecurity("VTI", "us", "direct", i, True, "us_total") for i in range(1)]
            + [AllowedSecurity("VXUS", "intl", None, 0, True, "intl_total")]
        ),
        overrides=(),
    )
    settings = PolicySettings.from_mapping(
        {
            "short_term_tax_rate": "0.37",
            "long_term_tax_rate": "0.20",
            "st_loss_carryforward_usd": "1200",
            "lt_loss_carryforward_usd": "800",
            "ytd_realized_st_usd": "2400",
            "ytd_realized_lt_usd": "-900",
            "ytd_as_of": TRADE_DATE.isoformat(),
            "target_retained_net_loss_usd": "500",
            "ordinary_income_deduction_limit_usd": "3000",
            "carryforward_loss_discount_factor": "0.85",
            "gain_budget_usd": "1800",
            "max_incremental_tax_cost_usd": "600",
            "st_gain_limit_usd": "900",
            "lt_gain_limit_usd": "1600",
            "max_batch_turnover_pct": "0.08",
            "min_buy_order_notional_usd": "100",
            "cash_reserve_usd": "2500",
            "objective_band_weight": "1.0",
            "objective_allocation_weight": "0.7",
            "objective_tax_weight": "0.8",
            "objective_trading_cost_weight": "0.1",
            "objective_turnover_weight": "0.1",
            "objective_cleanup_weight": "0.3",
            "estimated_spread_bps": "3",
            "estimated_fee_per_order_usd": "0",
            "max_sell_tickers_per_batch": 10,
            "max_sell_lots_per_batch": 20,
            "max_total_orders_per_batch": 12,
            "prefer_etf_buys": True,
            "allow_gain_sales": True,
            "permit_etf_harvest": False,
            "permit_muni_exit": False,
        }
    )
    policy_input = PolicyInput(
        "benchmark-policy-r1",
        policy,
        settings,
        revision_number=1,
        status="active",
        sector_bands=(
            PolicySectorBandInput("technology", Decimal(34), Decimal(8)),
            PolicySectorBandInput("healthcare", Decimal(33), Decimal(8)),
            PolicySectorBandInput("other", Decimal(33), Decimal(8)),
        ),
    )
    securities = [
        SecurityInput(SecurityIdentity(ticker, "EQUITY"), i + 1)
        for i, ticker in enumerate(stock_tickers)
    ]
    securities.extend(
        (
            SecurityInput(SecurityIdentity("VB", "ETF", True), 459),
            SecurityInput(SecurityIdentity("VXF", "ETF", True), 460),
            SecurityInput(SecurityIdentity("VTI", "ETF"), 461),
            SecurityInput(SecurityIdentity("VXUS", "ETF"), 462),
        )
    )
    positions: list[PositionInput] = []
    lots: list[LotInput] = []
    transactions: list[TransactionInput] = []
    for index, ticker in enumerate(tickers):
        price = prices[ticker]
        assignment = SleeveAssignment("direct", "growth" if index % 2 == 0 else "value")
        position_shares = Decimal(2500) / price
        positions.append(
            PositionInput(
                ticker,
                "EQUITY" if index < len(stock_tickers) else "ETF",
                index >= len(stock_tickers),
                position_shares
                + (
                    position_shares / Decimal(2500 // len(tickers) + (index < 2500 % len(tickers)))
                    - Decimal("0.01")
                    if index % 13 == 0
                    else Decimal("1e-24")
                ),
                1,
                AS_OF,
                Decimal(2500),
                assignment,
            )
        )
        count = 2500 // len(tickers) + (index < 2500 % len(tickers))
        for lot_index in range(count):
            shares = position_shares / Decimal(count)
            # Deliberate ST/LT gains/losses, near-basis lots and tiny DRIP cleanup lots.
            basis_factor = (
                Decimal("1.30")
                if (index + lot_index) % 11 == 0
                else Decimal("0.72")
                if (index + lot_index) % 7 == 0
                else Decimal("0.99")
                if lot_index % 3 == 0
                else Decimal("1.06")
            )
            basis_factor *= Decimal(1000 + rng.randint(-5, 5)) / Decimal(1000)
            acquired = date(2026, 8, 1) if lot_index % 4 == 0 else date(2023, 3, 1)
            if lot_index == count - 1 and index % 13 == 0:
                shares = Decimal("0.01")
                basis_factor = Decimal("0.95")
            lot_id = f"{ticker}-LOT-{lot_index:03d}"
            lots.append(
                LotInput(
                    ticker,
                    lot_id,
                    acquired,
                    shares,
                    shares,
                    price * basis_factor,
                    None,
                    "FAKE",
                    AS_OF,
                    False,
                    (),
                    1,
                )
            )
            if index < 40 and lot_index == 0:
                transactions.append(
                    TransactionInput(
                        f"HIST-{ticker}",
                        ticker,
                        "BUY",
                        datetime(2026, 9, 1, tzinfo=UTC),
                        date(2026, 9, 1),
                        shares,
                        -(price * shares),
                        True,
                        lot_id,
                        "FAKE",
                    )
                )
    quotes = [
        QuoteInput(
            t,
            prices[t] - Decimal("0.05"),
            prices[t] + Decimal("0.05"),
            prices[t],
            "FAKE",
            AS_OF,
            "good",
            1,
        )
        for t in tickers
    ]
    quotes.extend(
        (
            QuoteInput(
                "VTI", Decimal(250), Decimal("250.1"), Decimal("250.05"), "FAKE", AS_OF, "good", 1
            ),
            QuoteInput(
                "VXUS", Decimal(70), Decimal("70.1"), Decimal("70.05"), "FAKE", AS_OF, "good", 1
            ),
        )
    )
    exposures_list = []
    for ticker in ("VB", "VXF", "VTI", "VXUS"):
        exposures_list.extend(
            LookThroughExposureInput(ticker, dimension, key, weight, "fixture-v1", TRADE_DATE)
            for dimension, key, weight in (
                ("sector", "technology", Decimal("0.25")),
                ("sector", "healthcare", Decimal("0.20")),
                ("sector", "other", Decimal("0.55")),
                ("benchmark", "US_TOTAL", Decimal("1.00")),
            )
        )
        if ticker == "VB":
            members = stock_tickers[-50:]
        elif ticker == "VXF":
            members = stock_tickers[200:300]
        elif ticker == "VTI":
            members = stock_tickers[:100]
        else:
            members = tuple(f"INTL{i:03d}" for i in range(100))
        member_weight = Decimal(1) / Decimal(len(members))
        exposures_list.extend(
            LookThroughExposureInput(
                ticker,
                "security",
                member,
                Decimal(1) - member_weight * (len(members) - 1)
                if index == len(members) - 1
                else member_weight,
                "fixture-v1",
                TRADE_DATE,
            )
            for index, member in enumerate(members)
        )
    sector_keys = ("technology", "healthcare", "other")
    exposures_list.extend(
        LookThroughExposureInput(
            ticker,
            "sector",
            sector_keys[index % len(sector_keys)],
            Decimal(1),
            "fixture-v1",
            TRADE_DATE,
        )
        for index, ticker in enumerate(stock_tickers)
    )
    exposures = tuple(exposures_list)
    fingerprint = ";".join(
        f"{lot.broker_lot_id}:{lot.adjusted_unit_basis_usd}:{lot.shares}" for lot in lots
    )
    return FinancialInputs(
        account=AccountInput(
            1,
            "benchmark-single-account",
            "Synthetic benchmark brokerage",
            "BROKERAGE",
            "taxable",
            "FAKE",
            AS_OF,
            Decimal(12000),
            Decimal(12000),
        ),
        source_generation=1,
        proposed_trade_date=TRADE_DATE,
        policy=policy_input,
        securities=tuple(securities),
        positions=tuple(positions),
        lots=tuple(lots),
        quotes=tuple(quotes),
        transactions=tuple(transactions),
        source_checksum=hashlib.sha256(fingerprint.encode()).hexdigest(),
        exposures=exposures,
        source_metadata=InputSourceMetadata(
            sync_complete=True,
            sync_started_at=AS_OF,
            sync_completed_at=AS_OF,
            transaction_history_complete=True,
            transaction_history_start_date=date(2025, 11, 5),
            transaction_history_end_date=TRADE_DATE,
            lookthrough_complete=True,
        ),
    )
