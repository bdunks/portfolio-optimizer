"""Injected Vanguard holdings adapter for typed look-through exposures.

The configured request is kept separate from parsing so tests can replay captured
provider responses without constructing a network client.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import MAX_EMAX, MIN_EMIN, Decimal, InvalidOperation, localcontext
from typing import Literal, Protocol

import httpx

from app.domain.decimal_math import exact_product, exact_sum
from app.schemas import ExposureInput


class VanguardMarketDataError(ValueError):
    """The configured Vanguard request or response cannot be used safely."""


@dataclass(frozen=True, slots=True)
class VanguardFundConfig:
    ticker: str
    fund_id: str
    url: str

    def __post_init__(self) -> None:
        if not self.ticker.strip() or not self.fund_id.strip() or not self.url.strip():
            raise ValueError("Vanguard ticker, fund ID, and URL must be configured")


@dataclass(frozen=True, slots=True)
class VanguardConstituentIdentifier:
    """One source listing, including rows whose reported weight is unavailable."""

    section: Literal["equity", "fixedIncome"]
    holding_name: str | None
    ticker: str | None
    cusip: str | None
    sedol: str | None
    country: str | None
    industry: str | None
    weight: Decimal | None


@dataclass(frozen=True, slots=True)
class VanguardDimensionCoverage:
    dimension: str
    observed_constituents: int
    total_constituents: int
    covered_weight: Decimal
    unavailable_weight_count: int
    complete: bool


@dataclass(frozen=True, slots=True)
class VanguardExposureResult:
    exposures: tuple[ExposureInput, ...]
    identifiers: tuple[VanguardConstituentIdentifier, ...]
    fund_ticker: str
    fund_id: str
    source_url: str
    as_of_date: date
    reported_weight_total: Decimal
    coverage: tuple[VanguardDimensionCoverage, ...]


class _Response(Protocol):
    content: bytes

    def raise_for_status(self) -> None: ...


class _HttpClient(Protocol):
    def get(self, url: str, *, timeout: float) -> _Response: ...


def _parse_percentage(value: object, *, context: str) -> Decimal | None:
    if value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise VanguardMarketDataError(f"{context} must be a JSON number or blank")
    try:
        percentage = Decimal(value) if not isinstance(value, Decimal) else value
    except (InvalidOperation, ValueError) as exc:
        raise VanguardMarketDataError(f"{context} must be a JSON number or blank") from exc
    exponent = percentage.as_tuple().exponent
    if not percentage.is_finite() or not isinstance(exponent, int) or not -1000 <= exponent <= 1000:
        raise VanguardMarketDataError(f"{context} must have a bounded decimal exponent")
    if percentage < 0 or percentage > 100:
        raise VanguardMarketDataError(f"{context} must be finite and between 0 and 100")
    with localcontext() as arithmetic_context:
        arithmetic_context.Emin = MIN_EMIN
        arithmetic_context.Emax = MAX_EMAX
        return exact_product(percentage, Decimal("0.01"))


def _exact_adapter_sum(values: list[Decimal]) -> Decimal:
    with localcontext() as arithmetic_context:
        arithmetic_context.Emin = MIN_EMIN
        arithmetic_context.Emax = MAX_EMAX
        return exact_sum(values)


def _source_text(row: dict[str, object], key: str, *, context: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise VanguardMarketDataError(f"{context}.{key} must be a string when present")
    return value


def _normalised_identifier(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    return value.strip().upper()


def _listing_identity(
    item: VanguardConstituentIdentifier,
) -> tuple[str, str, str, str] | None:
    cusip = _normalised_identifier(item.cusip)
    sedol = _normalised_identifier(item.sedol)
    ticker = _normalised_identifier(item.ticker) or ""
    if cusip is not None:
        return (item.section, "cusip", cusip, sedol or "")
    if sedol is not None:
        return (item.section, "sedol", sedol, ticker)
    return None


def fetch_vanguard_exposures(
    config: VanguardFundConfig,
    client: _HttpClient | httpx.Client,
    *,
    timeout: float = 10.0,
) -> VanguardExposureResult:
    """Fetch one configured fund using the supplied client; no transport is constructed here."""
    try:
        response = client.get(config.url, timeout=timeout)
        response.raise_for_status()
        payload = json.loads(response.content, parse_float=Decimal, parse_int=Decimal)
    except Exception as exc:
        raise VanguardMarketDataError("Vanguard request failed or returned invalid JSON") from exc

    if not isinstance(payload, dict):
        raise VanguardMarketDataError("Vanguard response must be a JSON object")
    date_value = payload.get("latestEffectiveDate")
    if not isinstance(date_value, str) or not date_value:
        raise VanguardMarketDataError("Vanguard latestEffectiveDate must be an ISO date")
    try:
        as_of_date = date.fromisoformat(date_value)
        if as_of_date.isoformat() != date_value:
            raise ValueError("latestEffectiveDate is not canonical YYYY-MM-DD")
    except ValueError as exc:
        raise VanguardMarketDataError("Vanguard latestEffectiveDate must be an ISO date") from exc

    date_section = payload.get(date_value)
    if not isinstance(date_section, dict):
        raise VanguardMarketDataError("Vanguard effective-date section must be an object")
    source_arrays: dict[Literal["equity", "fixedIncome"], list[object]] = {}
    for section in ("equity", "fixedIncome"):
        rows = date_section.get(section)
        if not isinstance(rows, list):
            raise VanguardMarketDataError(f"Vanguard {section} direct holdings must be an array")
        source_arrays[section] = rows

    identifiers: list[VanguardConstituentIdentifier] = []
    for section, rows in source_arrays.items():
        for index, value in enumerate(rows):
            context = f"{date_value}.{section}[{index}]"
            if not isinstance(value, dict):
                raise VanguardMarketDataError(f"{context} must be an object")
            if "percentOfFunds" not in value:
                raise VanguardMarketDataError(f"{context}.percentOfFunds is required")
            weight = _parse_percentage(value["percentOfFunds"], context=f"{context}.percentOfFunds")
            identifiers.append(
                VanguardConstituentIdentifier(
                    section=section,
                    holding_name=_source_text(value, "holdingName", context=context),
                    ticker=_source_text(value, "ticker", context=context),
                    cusip=_source_text(value, "cusip", context=context),
                    sedol=_source_text(value, "sedol", context=context),
                    country=_source_text(value, "country", context=context)
                    if section == "equity"
                    else None,
                    industry=_source_text(value, "sector", context=context)
                    if section == "equity"
                    else None,
                    weight=weight,
                )
            )

    seen_listings: set[tuple[str, str, str, str]] = set()
    for item in identifiers:
        identity = _listing_identity(item)
        if identity is not None:
            if identity in seen_listings:
                raise VanguardMarketDataError(
                    f"Duplicate Vanguard listing identity in {item.section} holdings"
                )
            seen_listings.add(identity)

    reported_weight_total = _exact_adapter_sum(
        [item.weight for item in identifiers if item.weight is not None]
    )
    if reported_weight_total > Decimal(1):
        raise VanguardMarketDataError("Vanguard direct holding weights exceed 100 percent")

    ticker_counts: dict[str, int] = {}
    bond_cusip_counts: dict[str, int] = {}
    for item in identifiers:
        ticker = _normalised_identifier(item.ticker)
        if ticker is not None:
            ticker_counts[ticker] = ticker_counts.get(ticker, 0) + 1
        if item.section == "fixedIncome":
            cusip = _normalised_identifier(item.cusip)
            if cusip is not None:
                bond_cusip_counts[cusip] = bond_cusip_counts.get(cusip, 0) + 1

    dimension_rows: dict[str, list[tuple[str, Decimal]]] = {
        dimension: []
        for dimension in ("security", "cusip", "industry", "country", "sector", "size")
    }
    for item in identifiers:
        if item.weight is None:
            continue
        ticker = _normalised_identifier(item.ticker)
        cusip = _normalised_identifier(item.cusip)
        if (
            item.section == "equity"
            and item.country is not None
            and item.country.strip().upper() == "US"
            and ticker is not None
            and ticker_counts[ticker] == 1
        ):
            dimension_rows["security"].append((ticker, item.weight))
        if item.section == "fixedIncome" and cusip is not None and bond_cusip_counts[cusip] == 1:
            dimension_rows["cusip"].append((cusip, item.weight))
        if item.section == "equity":
            if item.industry is not None and item.industry.strip():
                dimension_rows["industry"].append((item.industry.strip(), item.weight))
            if item.country is not None and item.country.strip():
                dimension_rows["country"].append((item.country.strip(), item.weight))

    grouped_weights: dict[tuple[str, str], list[Decimal]] = {}
    observed = dict.fromkeys(dimension_rows, 0)
    covered_weights: dict[str, list[Decimal]] = {dimension: [] for dimension in dimension_rows}
    for dimension, rows in dimension_rows.items():
        for exposure_key, weight in rows:
            grouped_weights.setdefault((dimension, exposure_key), []).append(weight)
            observed[dimension] += 1
            covered_weights[dimension].append(weight)

    exposures = tuple(
        ExposureInput(
            ticker=config.ticker,
            dimension=dimension,
            exposure_key=exposure_key,
            weight=_exact_adapter_sum(weights),
            provider="vanguard",
            as_of_date=as_of_date,
        )
        for (dimension, exposure_key), weights in sorted(grouped_weights.items())
    )
    total_constituents = len(identifiers)
    unavailable_weight_count = sum(item.weight is None for item in identifiers)
    coverage = tuple(
        VanguardDimensionCoverage(
            dimension=dimension,
            observed_constituents=observed[dimension],
            total_constituents=total_constituents,
            covered_weight=_exact_adapter_sum(covered_weights[dimension]),
            unavailable_weight_count=unavailable_weight_count,
            complete=(
                total_constituents > 0
                and reported_weight_total == Decimal(1)
                and unavailable_weight_count == 0
                and observed[dimension] == total_constituents
                and _exact_adapter_sum(covered_weights[dimension]) == Decimal(1)
            ),
        )
        for dimension in dimension_rows
    )
    return VanguardExposureResult(
        exposures=exposures,
        identifiers=tuple(identifiers),
        fund_ticker=config.ticker.upper(),
        fund_id=config.fund_id,
        source_url=config.url,
        as_of_date=as_of_date,
        reported_weight_total=reported_weight_total,
        coverage=coverage,
    )
