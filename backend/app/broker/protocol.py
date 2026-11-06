from __future__ import annotations

from typing import Protocol

from app.schemas import BrokerSnapshot


class ReadOnlyBroker(Protocol):
    """Read-only source for a complete single-account snapshot; no order methods exist."""

    mode: str

    def fetch_snapshot(self) -> BrokerSnapshot: ...
