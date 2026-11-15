from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from app.schemas import BrokerSnapshot


class FakeBroker:
    """Deterministic, offline-only broker source. It has no HTTP or order transport."""

    mode = "fake"

    def __init__(self, snapshot: BrokerSnapshot | dict[str, Any] | None = None) -> None:
        self._snapshot = snapshot if snapshot is not None else self.demo_snapshot()
        self.fetch_count = 0
        self.fetch_error: Exception | None = None

    def fetch_snapshot(self) -> BrokerSnapshot:
        self.fetch_count += 1
        if self.fetch_error is not None:
            raise self.fetch_error
        return BrokerSnapshot.model_validate(
            self._snapshot.model_dump()
            if isinstance(self._snapshot, BrokerSnapshot)
            else self._snapshot
        )

    @staticmethod
    def demo_snapshot() -> BrokerSnapshot:
        as_of = datetime(2026, 11, 5, 20, 0, tzinfo=UTC)
        return BrokerSnapshot.model_validate(
            {
                "account_id_key": "DEMO-ONLY-ACCOUNT",
                "display_name": "DEMO — Hypothetical Account",
                "account_type": "BROKERAGE",
                "tax_treatment": "TAXABLE",
                "source": "DEMO",
                "as_of": as_of,
                "cash_usd": "850.00",
                "settled_buying_power_usd": "850.00",
                "coverage": {
                    "positions": True,
                    "lots": True,
                    "transactions": True,
                    "balances": True,
                    "quotes": True,
                    "lookthrough": False,
                },
                "positions": [
                    {
                        "ticker": "AAPL",
                        "asset_type": "EQUITY",
                        "shares": "10",
                        "market_value_usd": "1800.00",
                    },
                    {
                        "ticker": "VB",
                        "asset_type": "ETF",
                        "is_completion_etf": True,
                        "shares": "2",
                        "market_value_usd": "400.00",
                    },
                ],
                "lots": [
                    {
                        "ticker": "AAPL",
                        "broker_lot_id": "DEMO-AAPL-LOT-1",
                        "acquired_date": date(2025, 1, 10),
                        "shares": "10",
                        "available_shares": "10",
                        "adjusted_unit_basis_usd": "150.000000000000000001",
                        "source": "DEMO",
                        "as_of": as_of,
                        "quality_flags": [],
                    },
                    {
                        "ticker": "VB",
                        "broker_lot_id": "DEMO-VB-LOT-1",
                        "acquired_date": date(2025, 6, 3),
                        "shares": "2",
                        "available_shares": "2",
                        "adjusted_unit_basis_usd": "220.00",
                        "source": "DEMO",
                        "as_of": as_of,
                        "quality_flags": [],
                    },
                ],
                "quotes": [
                    {
                        "ticker": "AAPL",
                        "bid_usd": "179.99",
                        "ask_usd": "180.01",
                        "last_usd": "180.00",
                        "source": "DEMO",
                        "as_of": as_of,
                    },
                    {
                        "ticker": "VTI",
                        "bid_usd": "199.99",
                        "ask_usd": "200.01",
                        "last_usd": "200.00",
                        "source": "DEMO",
                        "as_of": as_of,
                    },
                    {
                        "ticker": "VB",
                        "bid_usd": "199.99",
                        "ask_usd": "200.01",
                        "last_usd": "200.00",
                        "source": "DEMO",
                        "as_of": as_of,
                    },
                ],
                "transactions": [
                    {
                        "broker_transaction_key": "DEMO-TXN-AAPL-1",
                        "ticker": "AAPL",
                        "transaction_kind": "BUY",
                        "transaction_time": datetime(2025, 1, 10, 15, 0, tzinfo=UTC),
                        "trade_date": date(2025, 1, 10),
                        "shares": "10",
                        "amount_usd": "1500.00000000000000001",
                        "is_acquisition": True,
                        "broker_lot_id": "DEMO-AAPL-LOT-1",
                        "source": "DEMO",
                    }
                ],
            }
        )
