"""Bounded, injected iShares holdings adapter for observed ITOT CSV responses."""

from __future__ import annotations

import csv
import io
import re
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from decimal import ROUND_FLOOR, Decimal, InvalidOperation, localcontext
from typing import Protocol

import httpx

from app.domain.decimal_math import exact_sum
from app.schemas import ExposureInput

ITOT_URL = "https://www.ishares.com/us/products/239724/ishares-core-s-p-total-u-s-stock-market-etf/latest-holdings.csv"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
_WEIGHT_PLACES = 24
_REQUIRED = {"Ticker", "Name", "Sector", "Asset Class", "Market Value", "Location", "Exchange"}
_ALLOWED_ASSET_CLASSES = {
    "Equity",
    "Cash",
    "Cash Collateral and Margins",
    "Money Market",
    "Futures",
}
_FOOTER_START = "The content contained herein is owned or licensed by BlackRock"


class IsharesMarketDataError(ValueError):
    """The configured iShares request or response cannot be used safely."""


@dataclass(frozen=True, slots=True)
class IsharesFundConfig:
    ticker: str
    url: str

    def __post_init__(self) -> None:
        if self.ticker != "ITOT" or self.url != ITOT_URL:
            raise IsharesMarketDataError("only the verified ITOT fund and §5 URL are supported")


@dataclass(frozen=True, slots=True)
class IsharesHolding:
    ticker: str
    name: str
    sector: str
    asset_class: str
    location: str
    exchange: str
    market_value: Decimal
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
    total_equity_market_value: Decimal
    coverage: tuple[IsharesDimensionCoverage, ...]


class _Response(Protocol):
    headers: httpx.Headers
    request: httpx.Request
    history: list[httpx.Response]

    def raise_for_status(self) -> None: ...

    def iter_bytes(self) -> Iterator[bytes]: ...


class _StreamContext(Protocol):
    def __enter__(self) -> _Response: ...
    def __exit__(self, *args: object) -> None: ...


class _HttpClient(Protocol):
    def stream(
        self,
        method: str,
        url: str,
        *,
        timeout: float,
        headers: dict[str, str],
        follow_redirects: bool,
    ) -> _StreamContext: ...


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


def _market_value(value: str, context: str, asset_class: str) -> Decimal:
    raw = value.strip()
    try:
        if not re.fullmatch(r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?", raw):
            raise InvalidOperation
        amount = Decimal(raw.replace(",", ""))
    except (InvalidOperation, ValueError) as exc:
        raise IsharesMarketDataError(f"{context} has invalid Market Value") from exc
    exponent = amount.as_tuple().exponent
    if not amount.is_finite() or not isinstance(exponent, int) or not -1000 <= exponent <= 1000:
        raise IsharesMarketDataError(f"{context} has non-finite or unbounded Market Value")
    if asset_class.casefold() == "equity" and amount < 0:
        raise IsharesMarketDataError(f"{context} has negative equity Market Value")
    return amount


def _parse_csv(text: str) -> tuple[date, tuple[IsharesHolding, ...]]:
    lines = text.splitlines(keepends=True)
    header_index: int | None = None
    for index, line in enumerate(lines):
        try:
            candidate = next(csv.reader([line], strict=True))
        except csv.Error:
            continue
        if _REQUIRED.issubset(candidate):
            header_index = index
            break
    if header_index is None:
        raise IsharesMarketDataError("iShares holdings CSV header is missing")
    as_of = _date_from_preamble("".join(lines[:header_index]))
    try:
        header = next(csv.reader([lines[header_index]], strict=True))
    except (csv.Error, StopIteration) as exc:
        raise IsharesMarketDataError("iShares holdings CSV header is malformed") from exc
    if len(header) != len(set(header)) or not _REQUIRED.issubset(header):
        raise IsharesMarketDataError("iShares holdings CSV header lacks required columns")

    reader = csv.reader(io.StringIO("".join(lines[header_index + 1 :])), strict=True)
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
        ticker, name = record["Ticker"].strip(), record["Name"].strip()
        sector, asset_class = record["Sector"].strip(), record["Asset Class"].strip()
        location, exchange = record["Location"].strip(), record["Exchange"].strip()
        if not all((name, asset_class, exchange)):
            raise IsharesMarketDataError(f"iShares row {row_number} is a partial holding")
        if asset_class not in _ALLOWED_ASSET_CLASSES:
            raise IsharesMarketDataError(f"iShares row {row_number} has unknown Asset Class")
        market_value = _market_value(
            record["Market Value"], f"iShares row {row_number}", asset_class
        )
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
        rows.append(
            IsharesHolding(
                ticker, name, sector, asset_class, location, exchange, market_value, Decimal(0)
            )
        )
    if not rows:
        raise IsharesMarketDataError("iShares holdings CSV contains no positions")
    return as_of, tuple(rows)


def _normalized_weights(
    rows: tuple[IsharesHolding, ...], denominator: Decimal
) -> tuple[Decimal, ...]:
    eligible = [
        i
        for i, row in enumerate(rows)
        if row.asset_class.casefold() == "equity" and row.market_value > 0
    ]
    unit = Decimal(1).scaleb(-_WEIGHT_PLACES)
    with localcontext() as context:
        context.prec = 80
        values = [Decimal(0)] * len(rows)
        remainders: list[tuple[Decimal, int]] = []
        for index in eligible:
            quota = rows[index].market_value / denominator / unit
            floor = quota.to_integral_value(rounding=ROUND_FLOOR)
            values[index] = floor * unit
            remainders.append((quota - floor, index))
        remaining = int((Decimal(1) - exact_sum(values)) / unit)
        # Stable index tie-break keeps the largest-remainder allocation reproducible.
        for _, index in sorted(remainders, key=lambda item: (-item[0], item[1]))[:remaining]:
            values[index] += unit
    return tuple(values)


def fetch_ishares_exposures(
    config: IsharesFundConfig,
    client: _HttpClient | httpx.Client,
    *,
    clock: Callable[[], datetime],
    timeout: float = 10.0,
) -> IsharesExposureResult:
    """Fetch one bounded configured URL using injected HTTP and UTC clock dependencies."""
    try:
        content = bytearray()
        with client.stream(
            "GET",
            config.url,
            timeout=timeout,
            headers={"Accept-Encoding": "identity"},
            follow_redirects=False,
        ) as response:
            if str(response.request.url) != config.url or response.history:
                raise IsharesMarketDataError("iShares response request identity changed")
            response.raise_for_status()
            encoding = response.headers.get("content-encoding", "identity").strip().casefold()
            if encoding not in {"", "identity"}:
                raise IsharesMarketDataError("iShares response used unsupported content encoding")
            for chunk in response.iter_bytes():
                if len(chunk) > MAX_RESPONSE_BYTES - len(content):
                    raise IsharesMarketDataError("iShares response exceeds 8 MiB limit")
                content.extend(chunk)
        text = bytes(content).decode("utf-8-sig", errors="strict")
    except IsharesMarketDataError:
        raise
    except Exception as exc:
        raise IsharesMarketDataError("iShares request failed or response was not UTF-8") from exc
    try:
        as_of_date, parsed = _parse_csv(text)
    except (csv.Error, UnicodeError) as exc:
        raise IsharesMarketDataError("iShares holdings CSV is malformed") from exc
    equities = [row for row in parsed if row.asset_class.casefold() == "equity"]
    denominator = exact_sum(row.market_value for row in equities if row.market_value > 0)
    if denominator <= 0:
        raise IsharesMarketDataError("iShares holdings have no positive equity Market Value")
    weights = _normalized_weights(parsed, denominator)
    holdings = tuple(
        replace(row, weight=weight) for row, weight in zip(parsed, weights, strict=True)
    )
    fetched_at = clock()
    offset = fetched_at.utcoffset()
    if fetched_at.tzinfo is None or offset is None or offset.total_seconds() != 0:
        raise IsharesMarketDataError("iShares fetch clock must return an aware UTC datetime")
    fetched_at = fetched_at.astimezone(UTC)

    eligible = [
        row for row in holdings if row.asset_class.casefold() == "equity" and row.market_value > 0
    ]
    ticker_counts = Counter(
        row.ticker.strip().upper()
        for row in eligible
        if row.location.casefold() == "united states" and row.ticker.strip() not in {"-", "—"}
    )

    def usable_ticker(row: IsharesHolding) -> bool:
        ticker = row.ticker.strip().upper()
        return (
            row.location.casefold() == "united states"
            and ticker not in {"-", "—"}
            and ticker_counts[ticker] == 1
            and re.fullmatch(r"[A-Z][A-Z0-9.]{0,9}", ticker) is not None
        )

    dimensions: dict[tuple[str, str], list[Decimal]] = {}
    for row in eligible:
        if usable_ticker(row):
            dimensions.setdefault(("security", row.ticker.strip().upper()), []).append(row.weight)
        if row.sector not in {"", "-", "—"}:
            dimensions.setdefault(("sector", row.sector), []).append(row.weight)
        if row.location not in {"", "-", "—"}:
            dimensions.setdefault(("country", row.location), []).append(row.weight)
    exposures = tuple(
        ExposureInput(
            ticker=config.ticker,
            dimension=dimension,
            exposure_key=key,
            weight=exact_sum(weights),
            provider="ishares",
            as_of_date=as_of_date,
        )
        for (dimension, key), weights in sorted(dimensions.items())
    )
    coverage = tuple(
        IsharesDimensionCoverage(
            dimension=dimension,
            observed_holdings=sum(
                (
                    usable_ticker(row)
                    if dimension == "security"
                    else row.sector not in {"", "-", "—"}
                    if dimension == "sector"
                    else row.location not in {"", "-", "—"}
                )
                for row in eligible
            ),
            eligible_holdings=len(eligible),
            covered_weight=exact_sum(
                row.weight
                for row in eligible
                if (
                    usable_ticker(row)
                    if dimension == "security"
                    else row.sector not in {"", "-", "—"}
                    if dimension == "sector"
                    else row.location not in {"", "-", "—"}
                )
            ),
            total_weight=Decimal(1),
            shortfall=Decimal(1)
            - exact_sum(
                row.weight
                for row in eligible
                if (
                    usable_ticker(row)
                    if dimension == "security"
                    else row.sector not in {"", "-", "—"}
                    if dimension == "sector"
                    else row.location not in {"", "-", "—"}
                )
            ),
            complete=all(
                (
                    usable_ticker(row)
                    if dimension == "security"
                    else row.sector not in {"", "-", "—"}
                    if dimension == "sector"
                    else row.location not in {"", "-", "—"}
                )
                for row in eligible
            ),
        )
        for dimension in ("security", "sector", "country")
    )
    return IsharesExposureResult(
        exposures,
        holdings,
        config.ticker.upper(),
        config.url,
        as_of_date,
        fetched_at,
        denominator,
        coverage,
    )
