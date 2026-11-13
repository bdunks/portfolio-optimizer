from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from query_test_support import count_selects
from sqlalchemy import select

from app.broker.fake import FakeBroker
from app.db.models import (
    Account,
    BrokerTransaction,
    CurrentTaxLot,
    PolicyRevision,
    Security,
    SecurityExposure,
    SyncState,
)
from app.domain.allocation import (
    AllocationPolicy,
    AllocationSleeve,
    AllowedSecurity,
    SecurityIdentity,
    SecurityOverride,
    SleeveAssignment,
    resolve_cash,
    resolve_holding,
)
from app.domain.financial_inputs import FinancialInputs, financial_inputs_from_provenance
from app.domain.portfolio_accounting import evaluate_portfolio
from app.domain.trade_dates import (
    DEMO_PROPOSED_TRADE_DATE,
    classify_holding_period,
    current_eastern_trade_date,
    resolve_proposed_trade_date,
)
from app.main import create_app
from app.schemas import BrokerSnapshot
from app.services.financial_input_loader import load_financial_inputs


def _allocation_policy() -> AllocationPolicy:
    return AllocationPolicy(
        sleeves=(
            AllocationSleeve("us_equities", None, True, direct_index_container=True),
            AllocationSleeve("direct_indexing", "us_equities", True, direct_index_sleeve=True),
            AllocationSleeve("international", None, True),
            AllocationSleeve("disabled", "us_equities", False),
            AllocationSleeve("cash", None, True, cash_sleeve=True),
        ),
        allowed_securities=(
            AllowedSecurity("ABC", "international", None, 0, True),
            AllowedSecurity("OVR", "international", None, 0, True),
        ),
        overrides=(SecurityOverride("OVR", "us_equities", "direct_indexing"),),
    )


def test_allocation_resolver_precedence_defaults_and_invalid_destinations() -> None:
    policy = _allocation_policy()
    assert resolve_holding(policy, SecurityIdentity("OVR", "ETF")).assignment == SleeveAssignment(
        "us_equities", "direct_indexing"
    )
    assert resolve_holding(policy, SecurityIdentity("ABC", "ETF")).assignment == SleeveAssignment(
        "international"
    )
    assert resolve_holding(policy, SecurityIdentity("XYZ", "EQUITY")).assignment == SleeveAssignment(
        "us_equities", "direct_indexing"
    )
    assert resolve_holding(policy, SecurityIdentity("VB", "ETF", True)).assignment == SleeveAssignment(
        "us_equities", "direct_indexing"
    )
    assert resolve_holding(policy, SecurityIdentity("VXF", "ETF", True)).assignment == SleeveAssignment(
        "us_equities", "direct_indexing"
    )
    assert resolve_holding(policy, SecurityIdentity("OTHER", "ETF")).reason == "no_policy_assignment"
    assert resolve_cash(policy).assignment == SleeveAssignment("cash")

    invalid_override = AllocationPolicy(
        policy.sleeves,
        policy.allowed_securities,
        (SecurityOverride("OVR", "disabled", None),),
    )
    assert resolve_holding(invalid_override, SecurityIdentity("OVR", "ETF")).reason == (
        "assignment_target_missing_disabled_or_invalid_ancestry"
    )

    ambiguous = AllocationPolicy(
        policy.sleeves,
        (
            AllowedSecurity("AMB", "us_equities", None, 0, True),
            AllowedSecurity("AMB", "international", None, 0, True),
        ),
        (),
    )
    assert resolve_holding(ambiguous, SecurityIdentity("AMB", "ETF")).reason == (
        "ambiguous_allowed_security_destination"
    )


def test_default_equity_and_vb_vxf_routing_uses_only_direct_legacy_child() -> None:
    policy = AllocationPolicy(
        sleeves=(
            AllocationSleeve("us_equities", None, True, direct_index_container=True),
            AllocationSleeve("legacy", "us_equities", True, direct_index_sleeve=True),
            AllocationSleeve("nested_legacy", "legacy", True, direct_index_sleeve=True),
        ),
        allowed_securities=(),
        overrides=(),
    )

    for security in (
        SecurityIdentity("XYZ", "EQUITY"),
        SecurityIdentity("VB", "ETF", True),
        SecurityIdentity("VXF", "ETF", True),
    ):
        assert resolve_holding(policy, security).assignment == SleeveAssignment(
            "us_equities", "legacy"
        )


def test_trade_date_defaults_timezone_anniversary_and_leap_day() -> None:
    assert resolve_proposed_trade_date(None, demo=True) == DEMO_PROPOSED_TRADE_DATE == date(2026, 11, 5)
    assert resolve_proposed_trade_date(date(2024, 2, 29), demo=True) == date(2024, 2, 29)
    assert current_eastern_trade_date(datetime(2026, 11, 6, 0, 30, tzinfo=UTC)) == date(2026, 11, 5)
    assert current_eastern_trade_date(datetime(2026, 11, 7, 17, tzinfo=UTC)) == date(2026, 11, 7)
    assert resolve_proposed_trade_date(None, demo=False, now=datetime(2026, 11, 6, 0, 30, tzinfo=UTC)) == date(
        2026, 11, 5
    )
    assert classify_holding_period(date(2025, 11, 5), date(2026, 11, 5)) == "ST"
    assert classify_holding_period(date(2025, 11, 5), date(2026, 11, 6)) == "LT"
    assert classify_holding_period(date(2024, 2, 29), date(2025, 2, 28)) == "ST"
    assert classify_holding_period(date(2024, 2, 29), date(2025, 3, 1)) == "LT"
    with pytest.raises(ValueError, match="timezone-aware"):
        current_eastern_trade_date(datetime(2026, 11, 5, 12))


def _large_snapshot() -> BrokerSnapshot:
    template = FakeBroker.demo_snapshot()
    account_as_of = template.as_of
    positions = []
    lots = []
    quotes = []
    for index in range(460):
        ticker = f"STK{index:03d}"
        positions.append(
            {
                "ticker": ticker,
                "asset_type": "EQUITY",
                "shares": "10",
                "market_value_usd": "1000",
            }
        )
        lot_count = 6 if index < 200 else 5
        quantities = [Decimal(1)] * 5 + [Decimal(5)] if lot_count == 6 else [Decimal(2)] * 5
        for lot_index, shares in enumerate(quantities):
            lots.append(
                {
                    "ticker": ticker,
                    "broker_lot_id": f"{ticker}-LOT-{lot_index:02d}",
                    "acquired_date": date(2020, 1, 1),
                    "shares": str(shares),
                    "available_shares": str(shares),
                    "adjusted_unit_basis_usd": "50",
                    "source": "DEMO",
                    "as_of": account_as_of,
                    "quality_flags": [],
                }
            )
        quotes.append(
            {
                "ticker": ticker,
                "bid_usd": "99.99",
                "ask_usd": "100.01",
                "last_usd": "100",
                "source": "DEMO",
                "as_of": account_as_of,
                "quality": "good",
            }
        )
    vti_quote = next(row.model_dump() for row in template.quotes if row.ticker == "VTI")
    quotes.append(vti_quote)
    snapshot_data = template.model_dump()
    snapshot_data.update(
        {
            "positions": positions,
            "lots": lots,
            "quotes": quotes,
            "transactions": [],
        }
    )
    return BrokerSnapshot.model_validate(snapshot_data)



def test_460_security_2500_lot_loads_are_bulk_and_round_trip_immutable_inputs(tmp_path: Path) -> None:
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'bulk-inputs.sqlite3'}",
        broker=FakeBroker(_large_snapshot()),
        seed_demo_data=True,
    )
    with TestClient(app, base_url="http://localhost") as client:
        response, portfolio_selects = count_selects(app.state.engine, lambda: client.get("/api/v1/portfolio"))
        assert response.status_code == 200, response.text
        assert response.json()["position_count"] == 460
        assert portfolio_selects == 11

        lot_page, lot_selects = count_selects(
            app.state.engine,
            lambda: client.get("/api/v1/lots?limit=500"),
        )
        assert lot_page.status_code == 200, lot_page.text
        assert lot_page.json()["total"] == 2500
        assert len(lot_page.json()["items"]) == 500
        assert lot_selects == 9

        assert lot_page.json()["source_generation"] == 1

        outside_loaded_page = client.get("/api/v1/lots?search=stk459-lot-04&limit=1")
        assert outside_loaded_page.status_code == 200, outside_loaded_page.text
        assert outside_loaded_page.json()["total"] == 1
        assert outside_loaded_page.json()["items"][0]["broker_lot_id"] == "STK459-LOT-04"
        assert outside_loaded_page.json()["source_generation"] == 1

        tied_first = client.get(
            "/api/v1/lots?search=LOT-05&sort_by=remaining_shares&sort_direction=desc&limit=2"
        ).json()
        tied_second = client.get(
            "/api/v1/lots?search=LOT-05&sort_by=remaining_shares&sort_direction=desc&offset=2&limit=2"
        ).json()
        assert tied_first["total"] == tied_second["total"] == 200
        assert [row["broker_lot_id"] for row in tied_first["items"]] == [
            "STK000-LOT-05",
            "STK001-LOT-05",
        ]
        assert [row["broker_lot_id"] for row in tied_second["items"]] == [
            "STK002-LOT-05",
            "STK003-LOT-05",
        ]
        empty_page = client.get("/api/v1/lots?search=no-such-lot&offset=4&limit=2").json()
        assert empty_page["items"] == []
        assert empty_page["total"] == 0
        assert empty_page["offset"] == 4
        assert empty_page["limit"] == 2

        with app.state.session_factory.begin() as session:
            close_lots = [
                session.scalar(select(CurrentTaxLot).where(CurrentTaxLot.broker_lot_id == broker_lot_id))
                for broker_lot_id in ("STK000-LOT-00", "STK000-LOT-01")
            ]
            assert all(lot is not None for lot in close_lots)
            first_lot, second_lot = close_lots
            assert first_lot is not None
            assert second_lot is not None
            first_lot.available_shares = Decimal("0.9999999999999999999999999999")
            second_lot.available_shares = Decimal(1)
            for broker_lot_id in ("STK000-LOT-02", "STK000-LOT-03", "STK000-LOT-04", "STK000-LOT-05"):
                lot = session.scalar(select(CurrentTaxLot).where(CurrentTaxLot.broker_lot_id == broker_lot_id))
                assert lot is not None
                lot.available_shares = Decimal(0)
        exact_numeric_page = client.get(
            "/api/v1/lots?search=STK000-LOT-0&sort_by=available_shares&sort_direction=desc&limit=2"
        ).json()
        assert [row["broker_lot_id"] for row in exact_numeric_page["items"]] == [
            "STK000-LOT-01",
            "STK000-LOT-00",
        ]
        assert exact_numeric_page["items"][0]["available_shares"] == "1"
        assert exact_numeric_page["items"][1]["available_shares"] == "0.9999999999999999999999999999"
        with app.state.session_factory.begin() as session:
            state = session.get(SyncState, 1)
            vti = session.scalar(select(Security).where(Security.ticker == "VTI"))
            assert state is not None
            assert vti is not None
            stk000 = session.scalar(select(Security).where(Security.ticker == "STK000"))
            assert stk000 is not None
            state.complete = True
            state.coverage = {
                **state.coverage,
                "transactions": True,
                "transaction_history_start_date": "2026-10-01",
                "transaction_history_end_date": DEMO_PROPOSED_TRADE_DATE.isoformat(),
                "lookthrough": True,
            }
            session.add(
                SecurityExposure(
                    security_id=vti.id,
                    dimension="security",
                    exposure_key="AAPL",
                    weight=Decimal("0.25"),
                    provider="vanguard",
                    as_of_date=date(2026, 11, 4),
                )
            )
            session.add(
                BrokerTransaction(
                    broker_transaction_key="TEST-EXECUTED-LOSS",
                    account_id=1,
                    security_id=stk000.id,
                    transaction_kind="SELL",
                    transaction_time=datetime(2026, 11, 4, 20, tzinfo=UTC),
                    trade_date=date(2026, 11, 4),
                    shares=Decimal(1),
                    amount_usd=Decimal(0),
                    realized_pl_usd=Decimal(-5),
                    is_acquisition=False,
                    broker_lot_id=None,
                    source="DEMO",
                )
            )

        def load_inputs() -> FinancialInputs:
            with app.state.session_factory() as session:
                account = session.get(Account, 1)
                state = session.get(SyncState, 1)
                policy = session.scalar(select(PolicyRevision).where(PolicyRevision.status == "ACTIVE"))
                assert account is not None
                assert state is not None
                assert policy is not None
                return load_financial_inputs(
                    session, account, state, policy, DEMO_PROPOSED_TRADE_DATE
                )


        def load_without_transactions() -> FinancialInputs:
            with app.state.session_factory() as session:
                account = session.get(Account, 1)
                state = session.get(SyncState, 1)
                policy = session.scalar(select(PolicyRevision).where(PolicyRevision.status == "ACTIVE"))
                assert account is not None
                assert state is not None
                assert policy is not None
                return load_financial_inputs(
                    session,
                    account,
                    state,
                    policy,
                    DEMO_PROPOSED_TRADE_DATE,
                    include_transactions=False,
                )
        inputs, full_input_selects = count_selects(app.state.engine, load_inputs)
        without_transactions = load_without_transactions()
        assert without_transactions.transactions == ()
        assert without_transactions.source_metadata.transaction_history_complete is False
        assert without_transactions.source_metadata.transaction_history_start_date == date(2026, 10, 1)
        assert len(inputs.positions) == 460
        assert len(inputs.lots) == 2500
        assert full_input_selects == 13
        assert inputs.exposures[0].ticker == "VTI"
        assert inputs.exposures[0].weight == Decimal("0.25")
        assert len(inputs.transactions) == 1
        assert inputs.transactions[0].realized_pl_usd == Decimal(-5)
        assert inputs.source_metadata.transaction_history_complete is True
        assert inputs.source_metadata.transaction_history_start_date == date(2026, 10, 1)
        assert inputs.source_metadata.transaction_history_end_date == DEMO_PROPOSED_TRADE_DATE
        assert inputs.source_metadata.lookthrough_complete is True
        resolved, resolver_selects = count_selects(
            app.state.engine,
            lambda: [
                resolve_holding(inputs.policy.allocation, security.identity)
                for security in inputs.securities
            ],
        )
        assert len(resolved) == len(inputs.securities)
        assert resolver_selects == 0
        accounting, accounting_selects = count_selects(
            app.state.engine, lambda: evaluate_portfolio(inputs)
        )
        assert accounting_selects == 0
        assert accounting.current == accounting.proposed
        restored = financial_inputs_from_provenance(
            inputs.to_provenance(), proposed_trade_date=DEMO_PROPOSED_TRADE_DATE
        )
        assert restored == inputs
        malformed_sector_bundle = inputs.to_provenance()
        malformed_sector_policy = malformed_sector_bundle["policy"]
        assert isinstance(malformed_sector_policy, dict)
        malformed_sector_bands = malformed_sector_policy["sector_bands"]
        assert isinstance(malformed_sector_bands, list)
        assert isinstance(malformed_sector_bands[0], dict)
        malformed_sector_bands[0]["target_weight_pct"] = "NaN"
        with pytest.raises(ValueError, match="frozen sector band policy data is invalid"):
            financial_inputs_from_provenance(
                malformed_sector_bundle,
                proposed_trade_date=DEMO_PROPOSED_TRADE_DATE,
            )
        frozen_sleeves = inputs.to_provenance()["policy"]["sleeves"]
        frozen_settings = inputs.to_provenance()["policy"]["settings"]
        assert isinstance(frozen_settings, dict)
        assert Decimal(frozen_settings["objective_band_weight"]) == Decimal("1.0")
        assert Decimal(frozen_settings["estimated_spread_bps"]) == Decimal("5.0")
        assert Decimal(frozen_settings["estimated_fee_per_order_usd"]) == Decimal("1.00")
        restored_settings = dict(restored.policy.settings.values)
        assert restored_settings["objective_band_weight"] == Decimal("1.0")
        assert isinstance(frozen_sleeves, list)
        assert any(row.get("is_transition_destination") is True for row in frozen_sleeves if isinstance(row, dict))
        assert isinstance(restored.account.cash_usd, Decimal)
        assert isinstance(restored.positions[0].as_of, datetime)
        assert isinstance(restored.lots[0].acquired_date, date)
        legacy_bundle = inputs.to_provenance()
        legacy_policy = legacy_bundle["policy"]
        assert isinstance(legacy_policy, dict)
        legacy_sleeves = legacy_policy["sleeves"]
        assert isinstance(legacy_sleeves, list)
        for row in legacy_sleeves:
            assert isinstance(row, dict)
            row.pop("is_transition_destination", None)
        legacy_bundle.pop("exposures")
        legacy_bundle.pop("source_metadata")
        legacy_bundle["schema"] = "demo-run-input-v1"
        legacy_bundle.pop("proposed_trade_date")
        legacy_bundle.pop("securities")
        legacy_lots = legacy_bundle["lots"]
        assert isinstance(legacy_lots, list)
        for legacy_lot in legacy_lots:
            assert isinstance(legacy_lot, dict)
            legacy_lot.pop("sync_generation")
        legacy_transactions = legacy_bundle["transactions"]
        assert isinstance(legacy_transactions, list)
        for legacy_transaction in legacy_transactions:
            assert isinstance(legacy_transaction, dict)
            legacy_transaction.pop("realized_pl_usd", None)
        legacy_restored = financial_inputs_from_provenance(
            legacy_bundle, proposed_trade_date=DEMO_PROPOSED_TRADE_DATE
        )
        assert len(legacy_restored.lots) == 2500
        assert {lot.sync_generation for lot in legacy_restored.lots} == {inputs.source_generation}
        assert all("sync_generation" not in legacy_lot for legacy_lot in legacy_lots)
        assert legacy_restored.exposures == ()
        assert legacy_restored.source_metadata.transaction_history_complete is None
        assert legacy_restored.source_metadata.lookthrough_complete is None
        assert all(not sleeve.transition_destination for sleeve in legacy_restored.policy.allocation.sleeves)
        current_bundle_missing_lot_generation = inputs.to_provenance()
        current_bundle_missing_lot_generation["lots"][0].pop("sync_generation")
        with pytest.raises(TypeError, match="frozen lot has no sync_generation"):
            financial_inputs_from_provenance(
                current_bundle_missing_lot_generation,
                proposed_trade_date=DEMO_PROPOSED_TRADE_DATE,
            )

        malformed_exposure_bundle = inputs.to_provenance()
        exposure_rows = malformed_exposure_bundle["exposures"]
        assert isinstance(exposure_rows, list)
        exposure_rows.append(None)
        with pytest.raises(TypeError, match="frozen exposure data is malformed"):
            financial_inputs_from_provenance(
                malformed_exposure_bundle,
                proposed_trade_date=DEMO_PROPOSED_TRADE_DATE,
            )
