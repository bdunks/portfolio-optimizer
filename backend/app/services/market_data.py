"""Isolated, injected Vanguard JSON adapter for typed look-through exposures.

The supported synthetic v1 wire contract is documented in
``backend/tests/fixtures/vanguard/v1/CONTRACT.md``. It is not a claim about a live
Vanguard endpoint response.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Protocol

import httpx

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
    ticker: str | None
    cusip: str | None


@dataclass(frozen=True, slots=True)
class VanguardDimensionCoverage:
    dimension: str
    observed_constituents: int
    total_constituents: int
    complete: bool


@dataclass(frozen=True, slots=True)
class VanguardExposureResult:
    exposures: tuple[ExposureInput, ...]
    identifiers: tuple[VanguardConstituentIdentifier, ...]
    fund_ticker: str
    fund_id: str
    source_url: str
    as_of_date: date
    coverage: tuple[VanguardDimensionCoverage, ...]


class _Response(Protocol):
    content: bytes

    def raise_for_status(self) -> None: ...


class _HttpClient(Protocol):
    def get(self, url: str, *, timeout: float) -> _Response: ...


def _parse_percentage(value: object, *, context: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise VanguardMarketDataError(f"{context} must be a decimal percentage")
    try:
        percentage = Decimal(value) if not isinstance(value, Decimal) else value
    except (InvalidOperation, ValueError) as exc:
        raise VanguardMarketDataError(f"{context} must be a decimal percentage") from exc
    if not percentage.is_finite() or percentage < 0 or percentage > 100:
        raise VanguardMarketDataError(f"{context} must be finite and between 0 and 100")
    return percentage / Decimal(100)


def _required_string(value: object, *, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise VanguardMarketDataError(f"{context} must be a non-empty string")
    return value.strip()


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

    if not isinstance(payload, dict) or set(payload) != {
        "schema_version",
        "fund",
        "as_of_date",
        "holdings",
    }:
        raise VanguardMarketDataError("Vanguard response does not match the v1 contract")
    if payload["schema_version"] != "vanguard.holdings.v1":
        raise VanguardMarketDataError("Unsupported Vanguard response schema version")

    fund = payload["fund"]
    if not isinstance(fund, dict) or set(fund) != {"ticker", "id"}:
        raise VanguardMarketDataError("Vanguard fund metadata does not match the v1 contract")
    if fund["ticker"] != config.ticker or str(fund["id"]) != config.fund_id:
        raise VanguardMarketDataError("Vanguard response fund does not match configured fund")

    try:
        as_of_date = date.fromisoformat(
            _required_string(payload["as_of_date"], context="as_of_date")
        )
    except ValueError as exc:
        raise VanguardMarketDataError("Vanguard as_of_date must be an ISO date") from exc

    holdings = payload["holdings"]
    if not isinstance(holdings, list):
        raise VanguardMarketDataError("Vanguard holdings must be a list")

    exposures: list[ExposureInput] = []
    identifiers: list[VanguardConstituentIdentifier] = []
    ticker_ids: set[str] = set()
    cusip_ids: set[str] = set()
    observed = {"security": 0, "sector": 0, "size": 0}

    for index, holding in enumerate(holdings):
        context = f"holdings[{index}]"
        if not isinstance(holding, dict) or set(holding) - {
            "ticker",
            "cusip",
            "weight_pct",
            "sector",
            "size",
        }:
            raise VanguardMarketDataError(f"{context} does not match the v1 contract")
        ticker_value = holding.get("ticker")
        cusip_value = holding.get("cusip")
        ticker = (
            _required_string(ticker_value, context=f"{context}.ticker")
            if ticker_value is not None
            else None
        )
        cusip = (
            _required_string(cusip_value, context=f"{context}.cusip")
            if cusip_value is not None
            else None
        )
        if ticker is None and cusip is None:
            raise VanguardMarketDataError(f"{context} requires a ticker or CUSIP identifier")
        if ticker is not None:
            normalized_ticker = ticker.upper()
            if normalized_ticker in ticker_ids:
                raise VanguardMarketDataError(
                    f"Duplicate Vanguard ticker identifier: {normalized_ticker}"
                )
            ticker_ids.add(normalized_ticker)
            ticker = normalized_ticker
        if cusip is not None:
            normalized_cusip = cusip.upper()
            if normalized_cusip in cusip_ids:
                raise VanguardMarketDataError(
                    f"Duplicate Vanguard CUSIP identifier: {normalized_cusip}"
                )
            cusip_ids.add(normalized_cusip)
            cusip = normalized_cusip

        weight = _parse_percentage(holding.get("weight_pct"), context=f"{context}.weight_pct")
        identifiers.append(VanguardConstituentIdentifier(ticker=ticker, cusip=cusip))
        if ticker is not None:
            observed["security"] += 1
            exposures.append(
                ExposureInput(
                    ticker=config.ticker,
                    dimension="security",
                    exposure_key=ticker,
                    weight=weight,
                    provider="vanguard",
                    as_of_date=as_of_date,
                )
            )
        for dimension in ("sector", "size"):
            label_value = holding.get(dimension)
            if label_value is None:
                continue
            label = _required_string(label_value, context=f"{context}.{dimension}")
            observed[dimension] += 1
            exposures.append(
                ExposureInput(
                    ticker=config.ticker,
                    dimension=dimension,
                    exposure_key=label,
                    weight=weight,
                    provider="vanguard",
                    as_of_date=as_of_date,
                )
            )

    total = len(holdings)
    coverage = tuple(
        VanguardDimensionCoverage(
            dimension=dimension,
            observed_constituents=observed[dimension],
            total_constituents=total,
            complete=total > 0 and observed[dimension] == total,
        )
        for dimension in ("security", "sector", "size")
    )
    return VanguardExposureResult(
        exposures=tuple(exposures),
        identifiers=tuple(identifiers),
        fund_ticker=config.ticker.upper(),
        fund_id=config.fund_id,
        source_url=config.url,
        as_of_date=as_of_date,
        coverage=coverage,
    )
