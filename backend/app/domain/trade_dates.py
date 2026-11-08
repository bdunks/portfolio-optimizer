from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

EASTERN_TIME = ZoneInfo("America/New_York")
DEMO_PROPOSED_TRADE_DATE = date(2026, 11, 5)


def current_eastern_trade_date(now: datetime | None = None) -> date:
    """Return today's America/New_York calendar date without weekend/holiday adjustment."""
    instant = now if now is not None else datetime.now(EASTERN_TIME)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return instant.astimezone(EASTERN_TIME).date()


def resolve_proposed_trade_date(
    explicit_date: date | None, *, demo: bool, now: datetime | None = None
) -> date:
    """Use an explicit date when supplied, otherwise apply the mode's approved default."""
    if explicit_date is not None:
        return explicit_date
    return DEMO_PROPOSED_TRADE_DATE if demo else current_eastern_trade_date(now)


def classify_holding_period(acquired_date: date, proposed_trade_date: date) -> str:
    """Classify ST through the one-year anniversary; LT starts the following calendar day."""
    try:
        anniversary = acquired_date.replace(year=acquired_date.year + 1)
    except ValueError:
        # A February 29 acquisition reaches its first anniversary on February 28.
        anniversary = acquired_date.replace(year=acquired_date.year + 1, day=28)
    return "LT" if proposed_trade_date > anniversary else "ST"
