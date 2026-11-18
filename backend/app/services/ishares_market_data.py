"""Bounded, injected iShares holdings adapter for observed ITOT CSV responses."""

from __future__ import annotations

import csv
import io
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Protocol

import httpx

from app.domain.decimal_math import exact_product, exact_sum
from app.schemas import ExposureInput

ITOT_URL = "https://www.ishares.com/us/products/239724/ishares-core-s-p-total-u-s-stock-market-etf/latest-holdings.csv"
_REQUIRED = {"Ticker", "Name", "Sector", "Asset Class", "Weight (%)", "Location", "Exchange"}
_FOOTER_START = "The content contained herein is owned or licensed by BlackRock"


class IsharesMarketDataError(ValueError):
    """The configured iShares request or response cannot be used safely."""


@dataclass(frozen=True, slots=True)
class IsharesFundConfig:
    ticker: str
    url: str

    def __post_init__(self) -> None:
        if not self.ticker.strip() or not self.url.strip():
            raise ValueError("iShares ticker and URL must be configured")


@dataclass(frozen=True, slots=True)
class IsharesHolding:
    ticker: str
    name: str
    sector: str
    asset_class: str
    location: str
    exchange: str
    weight: Decimal


@dataclass(frozen=True, slots=True)
class IsharesDimensionCoverage:
    dimension: str
    observed_holdings: int
    eligible_holdings: int
    covered_weight: Decimal
    total_weight: Decimal
    shortfall: Decimal
    complete: bool


@dataclass(frozen=True, slots=True)
class IsharesExposureResult:
    exposures: tuple[ExposureInput, ...]
    holdings: tuple[IsharesHolding, ...]
    fund_ticker: str
    source_url: str
    as_of_date: date
    fetched_at: datetime
    reported_weight_total: Decimal
    coverage: tuple[IsharesDimensionCoverage, ...]


class _Response(Protocol):
    content: bytes

    def raise_for_status(self) -> None: ...


class _HttpClient(Protocol):
    def get(self, url: str, *, timeout: float) -> _Response: ...


def _parse_weight(value: str, context: str) -> Decimal:
    try:
        weight = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise IsharesMarketDataError(f"{context} has invalid Weight (%)") from exc
    exponent = weight.as_tuple().exponent
    if not weight.is_finite() or not isinstance(exponent, int) or not -1000 <= exponent <= 1000:
        raise IsharesMarketDataError(f"{context} has non-finite or unbounded Weight (%)")
    if weight < 0:
        raise IsharesMarketDataError(f"{context} has negative Weight (%)")
    return exact_product(weight, Decimal("0.01"))


def _date_from_preamble(text: str) -> date:
    matches = re.findall(
        r'^Fund Holdings as of,"([A-Za-z]{3} \d{1,2}, \d{4})"\s*$', text, re.MULTILINE
    )
    if len(matches) != 1:
        raise IsharesMarketDataError("iShares Fund Holdings as of date is missing or ambiguous")
    try:
        return datetime.strptime(matches[0], "%b %d, %Y").date()
    except ValueError as exc:
        raise IsharesMarketDataError("iShares Fund Holdings as of date is invalid") from exc


def _parse_csv(text: str) -> tuple[date, tuple[IsharesHolding, ...], Decimal]:
    as_of = _date_from_preamble(text)
    lines = text.splitlines(keepends=True)
    header_index = next(
        (
            index
            for index, line in enumerate(lines)
            if _REQUIRED.issubset(next(csv.reader([line]), []))
        ),
        None,
    )
    if header_index is None:
        raise IsharesMarketDataError("iShares holdings CSV header is missing")
    try:
        header = next(csv.reader([lines[header_index]]))
    except (csv.Error, StopIteration) as exc:
        raise IsharesMarketDataError("iShares holdings CSV header is malformed") from exc
    if len(header) != len(set(header)) or not _REQUIRED.issubset(header):
        raise IsharesMarketDataError("iShares holdings CSV header lacks required columns")

    reader = csv.reader(io.StringIO("".join(lines[header_index + 1 :])))
    rows: list[IsharesHolding] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    footer_seen = False
    for row_number, fields in enumerate(reader, start=header_index + 2):
        if not fields or (len(fields) == 1 and not fields[0].strip()):
            continue
        if footer_seen:
            raise IsharesMarketDataError("unexpected nonblank record after iShares legal footer")
        if len(fields) == 1 and fields[0].startswith(_FOOTER_START):
            footer_seen = True
            continue
        if len(fields) != len(header):
            raise IsharesMarketDataError(
                f"iShares row {row_number} has {len(fields)} columns; expected {len(header)}"
            )
        record = dict(zip(header, fields, strict=True))
        ticker = record["Ticker"].strip()
        name = record["Name"].strip()
        sector = record["Sector"].strip()
        asset_class = record["Asset Class"].strip()
        location = record["Location"].strip()
        exchange = record["Exchange"].strip()
        if not all(
            (ticker, name, sector, asset_class, location, exchange, record["Weight (%)"].strip())
        ):
            raise IsharesMarketDataError(f"iShares row {row_number} is a partial holding")
        weight = _parse_weight(record["Weight (%)"].strip(), f"iShares row {row_number}")
        identity = (
            ticker.upper(),
            name.upper(),
            asset_class.upper(),
            location.upper(),
            exchange.upper(),
        )
        if identity in seen:
            raise IsharesMarketDataError(f"duplicate iShares listing at row {row_number}")
        seen.add(identity)
        rows.append(IsharesHolding(ticker, name, sector, asset_class, location, exchange, weight))
    if not rows:
        raise IsharesMarketDataError("iShares holdings CSV contains no positions")
    total = exact_sum(row.weight for row in rows)
    return as_of, tuple(rows), total


def fetch_ishares_exposures(
    config: IsharesFundConfig,
    client: _HttpClient | httpx.Client,
    *,
    clock: Callable[[], datetime],
    timeout: float = 10.0,
) -> IsharesExposureResult:
    """Fetch exactly one configured URL using injected HTTP and UTC clock dependencies."""
    try:
        response = client.get(config.url, timeout=timeout)
        response.raise_for_status()
        text = response.content.decode("utf-8-sig", errors="strict")
    except Exception as exc:
        raise IsharesMarketDataError("iShares request failed or response was not UTF-8") from exc
    try:
        as_of_date, holdings, reported_total = _parse_csv(text)
    except (csv.Error, UnicodeError) as exc:
        raise IsharesMarketDataError("iShares holdings CSV is malformed") from exc
    fetched_at = clock()
    offset = fetched_at.utcoffset()
    if fetched_at.tzinfo is None or offset is None or offset.total_seconds() != 0:
        raise IsharesMarketDataError("iShares fetch clock must return an aware UTC datetime")
    fetched_at = fetched_at.astimezone(UTC)

    equities = [row for row in holdings if row.asset_class.casefold() == "equity"]
    equity_ticker_counts = Counter(
        row.ticker.strip().upper()
        for row in equities
        if row.location.casefold() == "united states" and row.ticker.strip() not in {"-", "—"}
    )
    exposures_by_key: dict[tuple[str, str], list[Decimal]] = {}
    for row in equities:
        ticker = row.ticker.strip().upper()
        if (
            row.location.casefold() == "united states"
            and ticker not in {"-", "—"}
            and equity_ticker_counts[ticker] == 1
            and re.fullmatch(r"[A-Z][A-Z0-9.]{0,9}", ticker)
        ):
            exposures_by_key.setdefault(("security", ticker), []).append(row.weight)
        if row.sector not in {"-", "—"}:
            exposures_by_key.setdefault(("sector", row.sector), []).append(row.weight)
        if row.location not in {"-", "—"}:
            exposures_by_key.setdefault(("country", row.location), []).append(row.weight)

    exposures = tuple(
        ExposureInput(
            ticker=config.ticker,
            dimension=dimension,
            exposure_key=key,
            weight=exact_sum(weights),
            provider="ishares",
            as_of_date=as_of_date,
        )
        for (dimension, key), weights in sorted(exposures_by_key.items())
    )
    dimension_names = ("security", "sector", "country")

    def covered(row: IsharesHolding, dimension: str) -> bool:
        if dimension == "security":
            ticker = row.ticker.strip().upper()
            return (
                row.location.casefold() == "united states"
                and ticker not in {"-", "—"}
                and equity_ticker_counts[ticker] == 1
                and re.fullmatch(r"[A-Z][A-Z0-9.]{0,9}", ticker) is not None
            )
        return (
            row.sector not in {"-", "—"}
            if dimension == "sector"
            else row.location not in {"-", "—"}
        )

    coverage = tuple(
        IsharesDimensionCoverage(
            dimension=dimension,
            observed_holdings=sum(covered(row, dimension) for row in equities),
            eligible_holdings=len(equities),
            covered_weight=exact_sum(row.weight for row in equities if covered(row, dimension)),
            total_weight=exact_sum(row.weight for row in equities),
            shortfall=exact_sum(row.weight for row in equities)
            - exact_sum(row.weight for row in equities if covered(row, dimension)),
            complete=all(covered(row, dimension) for row in equities),
        )
        for dimension in dimension_names
    )
    return IsharesExposureResult(
        exposures=exposures,
        holdings=holdings,
        fund_ticker=config.ticker.upper(),
        source_url=config.url,
        as_of_date=as_of_date,
        fetched_at=fetched_at,
        reported_weight_total=reported_total,
        coverage=coverage,
    )
