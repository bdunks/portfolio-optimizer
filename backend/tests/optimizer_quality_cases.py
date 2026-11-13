"""Frozen, intentionally small synthetic cases for offline optimizer quality comparisons.

These fixtures are illustrative test data, not production policy defaults or live-account evidence.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
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
from tests.optimizer_quality_reference import BuyTickerBound, CandidateUniverse, SellLotBound

FIXTURE_VERSION = "offline-small-cases-v2"
TRADE_DATE = date(2026, 11, 13)
AS_OF = datetime(2026, 11, 13, 16, tzinfo=UTC)
CASE_FAMILIES = (
    "fee-consolidation",
    "reserve-repair",
    "loss-gain-offset",
    "tiny-replacement-buy",
    "nested-allocation",
    "sector-constraints",
)


@dataclass(frozen=True, slots=True)
class SmallQualityCase:
    case_id: str
    fixture_version: str
    seed: int
    family: str
    inputs: FinancialInputs
    universe: CandidateUniverse
    description: str


def _inputs_for_case(family: str, seed: int) -> FinancialInputs:
    rng = random.Random(seed)
    cent_jitter = Decimal(rng.randrange(-2, 3)) / Decimal(100)
    nested = family == "nested-allocation"
    cash = Decimal(0) if family == "reserve-repair" else Decimal(20)
    fee = Decimal(2) if family == "fee-consolidation" else Decimal("0.25")
    reserve = Decimal(15) if family == "reserve-repair" else Decimal(0)
    minimum_buy = Decimal(5) if family == "tiny-replacement-buy" else Decimal(0)
    allow_gain_sales = family == "loss-gain-offset"

    if nested:
        sleeves = (
            AllocationSleeve(
                "equity", None, True, target_pct=Decimal(70), drift_band_pp=Decimal(10)
            ),
            AllocationSleeve(
                "cash",
                None,
                True,
                cash_sleeve=True,
                target_pct=Decimal(30),
                drift_band_pp=Decimal(10),
            ),
            AllocationSleeve(
                "growth", "equity", True, target_pct=Decimal(50), drift_band_pp=Decimal(10)
            ),
            AllocationSleeve(
                "value", "equity", True, target_pct=Decimal(50), drift_band_pp=Decimal(10)
            ),
        )
    else:
        band = Decimal(5) if family == "sector-constraints" else Decimal(100)
        sleeves = (
            AllocationSleeve("equity", None, True, target_pct=Decimal(70), drift_band_pp=band),
            AllocationSleeve(
                "cash", None, True, cash_sleeve=True, target_pct=Decimal(30), drift_band_pp=band
            ),
        )

    allocation = AllocationPolicy(
        sleeves=sleeves,
        allowed_securities=(
            AllowedSecurity(
                "ETF_A", "equity", "growth" if nested else None, 0, True, "replacement"
            ),
            AllowedSecurity("ETF_B", "equity", "value" if nested else None, 1, True, "replacement"),
        ),
        overrides=(),
    )
    ytd_st = Decimal(0)
    ytd_lt = Decimal(0)
    if allow_gain_sales:
        ytd_st = Decimal(5)
        ytd_lt = Decimal(-3)

    settings = PolicySettings.from_mapping(
        {
            "short_term_tax_rate": Decimal("0.30"),
            "long_term_tax_rate": Decimal("0.15"),
            "st_loss_carryforward_usd": Decimal(0),
            "lt_loss_carryforward_usd": Decimal(0),
            "ytd_realized_st_usd": ytd_st,
            "ytd_realized_lt_usd": ytd_lt,
            "ytd_as_of": TRADE_DATE.isoformat(),
            "target_retained_net_loss_usd": Decimal(0),
            "ordinary_income_deduction_limit_usd": Decimal(3000),
            "carryforward_loss_discount_factor": Decimal("0.85"),
            "gain_budget_usd": Decimal(100),
            "max_incremental_tax_cost_usd": Decimal(100),
            "st_gain_limit_usd": Decimal(100),
            "lt_gain_limit_usd": Decimal(100),
            "max_batch_turnover_pct": Decimal(100),
            "min_buy_order_notional_usd": minimum_buy,
            "cash_reserve_usd": reserve,
            "max_sell_tickers_per_batch": 2,
            "max_sell_lots_per_batch": 3,
            "max_total_orders_per_batch": 3,
            "prefer_etf_buys": True,
            "allow_gain_sales": allow_gain_sales,
            "permit_etf_harvest": False,
            "permit_muni_exit": False,
            "objective_band_weight": Decimal("0.20"),
            "objective_allocation_weight": Decimal("0.25"),
            "objective_tax_weight": Decimal("0.25"),
            "objective_trading_cost_weight": Decimal("0.10"),
            "objective_turnover_weight": Decimal("0.05"),
            "objective_cleanup_weight": Decimal("0.15"),
            "estimated_spread_bps": Decimal(10),
            "estimated_fee_per_order_usd": fee,
        }
    )

    if family == "sector-constraints":
        sector_bands = (
            PolicySectorBandInput("technology", Decimal(65), Decimal(5)),
            PolicySectorBandInput("healthcare", Decimal(35), Decimal(5)),
        )
    else:
        sector_bands = (
            PolicySectorBandInput("technology", Decimal(50), Decimal(50)),
            PolicySectorBandInput("healthcare", Decimal(50), Decimal(50)),
        )

    policy = PolicyInput(
        revision_id=f"synthetic-{family}-policy-v1",
        allocation=allocation,
        settings=settings,
        revision_number=1,
        status="ACTIVE",
        sector_bands=sector_bands,
    )
    security_rows = (
        SecurityInput(SecurityIdentity("EQ1", "EQUITY"), security_id=1),
        SecurityInput(SecurityIdentity("EQ2", "EQUITY"), security_id=2),
        SecurityInput(SecurityIdentity("ETF_A", "ETF"), security_id=3),
        SecurityInput(SecurityIdentity("ETF_B", "ETF"), security_id=4),
    )
    positions = (
        PositionInput(
            "EQ1",
            "EQUITY",
            False,
            Decimal(2),
            1,
            AS_OF,
            Decimal(20),
            SleeveAssignment("equity", "growth" if nested else None),
        ),
        PositionInput(
            "EQ2",
            "EQUITY",
            False,
            Decimal(2),
            1,
            AS_OF,
            Decimal(20),
            SleeveAssignment("equity", "value" if nested else None),
        ),
    )
    basis_by_family = {
        "fee-consolidation": (Decimal(12), Decimal(12), Decimal(12)),
        "reserve-repair": (Decimal(12), Decimal(12), Decimal(12)),
        "loss-gain-offset": (Decimal(12), Decimal(8), Decimal(8)),
        "tiny-replacement-buy": (Decimal(12), Decimal(12), Decimal(12)),
        "nested-allocation": (Decimal(12), Decimal(12), Decimal(12)),
        "sector-constraints": (Decimal(12), Decimal(12), Decimal(12)),
    }
    bases = tuple(value + cent_jitter for value in basis_by_family[family])
    acquired_dates = (
        TRADE_DATE - timedelta(days=400),
        TRADE_DATE - timedelta(days=40 if family == "loss-gain-offset" else 420),
        TRADE_DATE - timedelta(days=500),
    )
    lots = (
        LotInput(
            "EQ1",
            "EQ1-L1",
            acquired_dates[0],
            Decimal(1),
            Decimal(1),
            bases[0],
            None,
            "SYNTHETIC_TEST",
            AS_OF,
            False,
            (),
            1,
        ),
        LotInput(
            "EQ1",
            "EQ1-L2",
            acquired_dates[1],
            Decimal(1),
            Decimal(1),
            bases[1],
            None,
            "SYNTHETIC_TEST",
            AS_OF,
            False,
            (),
            1,
        ),
        LotInput(
            "EQ2",
            "EQ2-L1",
            acquired_dates[2],
            Decimal(2),
            Decimal(2),
            bases[2],
            None,
            "SYNTHETIC_TEST",
            AS_OF,
            False,
            (),
            1,
        ),
    )
    quotes = (
        QuoteInput("EQ1", Decimal(10), Decimal(10), None, "SYNTHETIC_TEST", AS_OF, "good", 1),
        QuoteInput("EQ2", Decimal(10), Decimal(10), None, "SYNTHETIC_TEST", AS_OF, "good", 1),
        QuoteInput("ETF_A", Decimal(5), Decimal(5), None, "SYNTHETIC_TEST", AS_OF, "good", 1),
        QuoteInput("ETF_B", Decimal(10), Decimal(10), None, "SYNTHETIC_TEST", AS_OF, "good", 1),
    )
    if family == "sector-constraints":
        etf_a_sectors = (("technology", Decimal("0.80")), ("healthcare", Decimal("0.20")))
        etf_b_sectors = (("technology", Decimal("0.20")), ("healthcare", Decimal("0.80")))
    else:
        etf_a_sectors = (("technology", Decimal("0.80")), ("healthcare", Decimal("0.20")))
        etf_b_sectors = (("technology", Decimal("0.50")), ("healthcare", Decimal("0.50")))

    exposures: list[LookThroughExposureInput] = []
    for ticker, weights in (
        ("EQ1", (("technology", Decimal(1)),)),
        ("EQ2", (("healthcare", Decimal(1)),)),
        ("ETF_A", etf_a_sectors),
        ("ETF_B", etf_b_sectors),
    ):
        exposures.extend(
            LookThroughExposureInput(ticker, "sector", key, weight, "manual_csv", TRADE_DATE)
            for key, weight in weights
        )
    security_for_sector = {"technology": "EQ1", "healthcare": "EQ2"}
    for ticker, sector_weights in (("ETF_A", etf_a_sectors), ("ETF_B", etf_b_sectors)):
        security_weights = {
            security_for_sector[sector]: weight for sector, weight in sector_weights
        }
        exposures.extend(
            LookThroughExposureInput(ticker, "security", security, weight, "manual_csv", TRADE_DATE)
            for security, weight in security_weights.items()
        )
    transactions = ()
    if allow_gain_sales:
        prior_time = datetime(2026, 10, 1, 15, tzinfo=UTC)
        transactions = (
            TransactionInput(
                "history-eq2-realized-gain",
                "EQ2",
                "SELL",
                prior_time,
                date(2026, 10, 1),
                Decimal(1),
                Decimal(15),
                False,
                None,
                "SYNTHETIC_TEST",
                Decimal(5),
            ),
        )

    inputs = FinancialInputs(
        account=AccountInput(
            1,
            f"synthetic-quality-{family}",
            f"Synthetic {family} fixture",
            "BROKERAGE",
            "taxable",
            "SYNTHETIC_TEST",
            AS_OF,
            cash,
            cash,
        ),
        source_generation=1,
        proposed_trade_date=TRADE_DATE,
        policy=policy,
        securities=security_rows,
        positions=positions,
        lots=lots,
        quotes=quotes,
        transactions=transactions,
        source_checksum=None,
        exposures=tuple(exposures),
        source_metadata=InputSourceMetadata(
            sync_complete=True,
            sync_started_at=AS_OF,
            sync_completed_at=AS_OF,
            transaction_history_complete=True,
            transaction_history_start_date=TRADE_DATE - timedelta(days=500),
            transaction_history_end_date=TRADE_DATE,
            lookthrough_complete=True,
        ),
    )
    checksum = hashlib.sha256(
        json.dumps(inputs.to_provenance(), sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return replace(inputs, source_checksum=checksum)


def build_small_quality_case(family: str, seed: int) -> SmallQualityCase:
    """Build one registered family, isolating fixture failures to that case."""
    if family not in CASE_FAMILIES:
        raise ValueError(f"unknown small quality case family: {family}")
    inputs = _inputs_for_case(family, seed)
    universe = CandidateUniverse(
        sells=(
            SellLotBound("EQ1", "EQ1-L1", 1),
            SellLotBound("EQ1", "EQ1-L2", 1),
            SellLotBound("EQ2", "EQ2-L1", 1),
        ),
        buys=(BuyTickerBound("ETF_A", 1), BuyTickerBound("ETF_B", 2)),
    )
    return SmallQualityCase(
        case_id=f"{family}-seed-{seed}",
        fixture_version=FIXTURE_VERSION,
        seed=seed,
        family=family,
        inputs=inputs,
        universe=universe,
        description={
            "fee-consolidation": "Two named same-ticker lots plus another equity expose one-order fee and consolidation choices.",
            "reserve-repair": "An unfunded frozen cash reserve requires a small whole-share sale to restore feasibility.",
            "loss-gain-offset": "Short- and long-term gain/loss lots plus frozen YTD realized values exercise tax netting.",
            "tiny-replacement-buy": "A one-share $5 ETF candidate tests a small whole-share replacement purchase at the configured notional floor.",
            "nested-allocation": "Two child sleeves under an equity parent make nested allocation drift part of the comparison.",
            "sector-constraints": "Two-sector holdings and replacement ETFs exercise frozen sector look-through bands.",
        }[family],
    )


def build_small_quality_cases(seed: int = 20261113) -> tuple[SmallQualityCase, ...]:
    """Build all registered families with recorded, deterministic parameter-variant seeds."""
    return tuple(
        build_small_quality_case(family, seed + index) for index, family in enumerate(CASE_FAMILIES)
    )
