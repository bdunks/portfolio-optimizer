from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.engine import Engine

from app.broker.fake import FakeBroker
from app.db.models import Account, PolicyRevision, SyncState
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


def _count_selects[T](engine: Engine, action: Callable[[], T]) -> tuple[T, int]:
    statements: list[str] = []

    def count(_conn: object, _cursor: object, statement: str, _parameters: object, _context: object, _many: bool) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", count)
    try:
        result = action()
    finally:
        event.remove(engine, "before_cursor_execute", count)
    return result, len(statements)

def test_460_security_2500_lot_loads_are_bulk_and_round_trip_immutable_inputs(tmp_path: Path) -> None:
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'bulk-inputs.sqlite3'}",
        broker=FakeBroker(_large_snapshot()),
        seed_demo_data=True,
    )
    with TestClient(app, base_url="http://localhost") as client:
        response, portfolio_selects = _count_selects(app.state.engine, lambda: client.get("/api/v1/portfolio"))
        assert response.status_code == 200, response.text
        assert response.json()["position_count"] == 460
        assert portfolio_selects == 9

        lot_page, lot_selects = _count_selects(
            app.state.engine,
            lambda: client.get("/api/v1/lots?limit=500"),
        )
        assert lot_page.status_code == 200, lot_page.text
        assert lot_page.json()["total"] == 2500
        assert len(lot_page.json()["items"]) == 500
        assert lot_selects == 8
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

        inputs, full_input_selects = _count_selects(app.state.engine, load_inputs)
        assert len(inputs.positions) == 460
        assert len(inputs.lots) == 2500
        assert full_input_selects == 11
        restored = financial_inputs_from_provenance(
            inputs.to_provenance(), proposed_trade_date=DEMO_PROPOSED_TRADE_DATE
        )
        assert restored == inputs
        frozen_sleeves = inputs.to_provenance()["policy"]["sleeves"]
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
        legacy_bundle["schema"] = "demo-run-input-v1"
        legacy_bundle.pop("proposed_trade_date")
        legacy_bundle.pop("securities")
        legacy_lots = legacy_bundle["lots"]
        assert isinstance(legacy_lots, list)
        for legacy_lot in legacy_lots:
            assert isinstance(legacy_lot, dict)
            legacy_lot.pop("sync_generation")
        legacy_restored = financial_inputs_from_provenance(
            legacy_bundle, proposed_trade_date=DEMO_PROPOSED_TRADE_DATE
        )
        assert len(legacy_restored.lots) == 2500
        assert {lot.sync_generation for lot in legacy_restored.lots} == {inputs.source_generation}
        assert all("sync_generation" not in legacy_lot for legacy_lot in legacy_lots)
        assert all(not sleeve.transition_destination for sleeve in legacy_restored.policy.allocation.sleeves)
        current_bundle_missing_lot_generation = inputs.to_provenance()
        current_bundle_missing_lot_generation["lots"][0].pop("sync_generation")
        with pytest.raises(TypeError, match="frozen lot has no sync_generation"):
            financial_inputs_from_provenance(
                current_bundle_missing_lot_generation,
                proposed_trade_date=DEMO_PROPOSED_TRADE_DATE,
            )
