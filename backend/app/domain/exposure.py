from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from app.domain.decimal_math import exact_sum
from app.domain.financial_inputs import FinancialInputs, LookThroughExposureInput, PositionInput

EXPOSURE_CACHE_MAX_AGE_DAYS = 95
_SECURITY_DIMENSIONS = frozenset({"security", "ticker", "constituent", "constituent_ticker"})
_PROVIDER_ORDER = {"vanguard": 0, "ishares": 1, "manual_csv": 2}


@dataclass(frozen=True, slots=True)
class ExposureValue:
    dimension: str
    exposure_key: str
    value_usd: Decimal


@dataclass(frozen=True, slots=True)
class ExposureSourceFreshness:
    provider: str
    as_of_date: date


@dataclass(frozen=True, slots=True)
class ExposureCoverage:
    complete: bool | None
    as_of_date: date | None
    missing_tickers: tuple[str, ...]
    stale_tickers: tuple[str, ...]
    conflicting_tickers: tuple[str, ...]
    invalid_tickers: tuple[str, ...]
    duplicate_rows_removed: int
    sources: tuple[ExposureSourceFreshness, ...]


@dataclass(frozen=True, slots=True)
class ExposureAggregate:
    values: tuple[ExposureValue, ...]
    coverage: ExposureCoverage


@dataclass(frozen=True, slots=True)
class ExposureOverlap:
    dimension: str
    overlap_pct: Decimal | None
    reason: str | None


def _normalise_dimension(dimension: str) -> str:
    normalized = dimension.strip().lower()
    return "security" if normalized in _SECURITY_DIMENSIONS else normalized


def _normalise_key(dimension: str, key: str) -> str:
    return key.strip().upper() if _normalise_dimension(dimension) == "security" else key.strip()


def _selected_rows(
    exposures: Sequence[LookThroughExposureInput],
) -> tuple[dict[tuple[str, str, str], LookThroughExposureInput], set[str], int]:
    grouped: dict[tuple[str, str, str], list[LookThroughExposureInput]] = defaultdict(list)
    for row in exposures:
        key = (
            row.ticker.upper(),
            _normalise_dimension(row.dimension),
            _normalise_key(row.dimension, row.exposure_key),
        )
        grouped[key].append(row)

    selected: dict[tuple[str, str, str], LookThroughExposureInput] = {}
    conflicts: set[str] = set()
    duplicates_removed = 0
    for key, rows in grouped.items():
        newest_date = max(row.as_of_date for row in rows)
        newest = [row for row in rows if row.as_of_date == newest_date]
        if len({row.weight for row in newest}) > 1:
            conflicts.add(key[0])
        winner = max(newest, key=lambda row: (_PROVIDER_ORDER.get(row.provider, -1), row.provider))
        selected[key] = winner
        duplicates_removed += len(rows) - 1
    return selected, conflicts, duplicates_removed


def aggregate_lookthrough_exposure(
    inputs: FinancialInputs, *, tickers: Sequence[str] | None = None
) -> ExposureAggregate:
    """Aggregate current dollar exposure by economic dimension using only cached rows.

    Direct equities are represented at security level. ETFs, including VB and VXF, are
    expanded using their cached security-level look-through rows. A ticker selector can
    build a unit-notional benchmark aggregate for an ETF not currently held.
    """
    positions_by_ticker = {position.ticker.upper(): position for position in inputs.positions}
    if tickers is None:
        selected_positions = tuple(inputs.positions)
        unit_notional_tickers: set[str] = set()
    else:
        normalized_tickers = tuple(dict.fromkeys(ticker.upper() for ticker in tickers))
        selected_position_rows: list[PositionInput] = []
        unit_notional_tickers = set()
        for ticker in normalized_tickers:
            position = positions_by_ticker.get(ticker)
            if position is not None:
                selected_position_rows.append(position)
                continue
            security = inputs.security_for(ticker)
            selected_position_rows.append(
                PositionInput(
                    ticker=ticker,
                    asset_type=security.identity.asset_type if security is not None else "ETF",
                    is_completion_etf=(
                        security.identity.is_completion_etf
                        if security is not None
                        else ticker in {"VB", "VXF"}
                    ),
                    shares=Decimal(1),
                    sync_generation=inputs.source_generation,
                    as_of=inputs.account.as_of,
                    market_value_usd=Decimal(1),
                    assignment=None,
                )
            )
            unit_notional_tickers.add(ticker)
        selected_positions = tuple(selected_position_rows)

    relevant_tickers = {position.ticker.upper() for position in selected_positions}
    relevant_exposures = tuple(
        row for row in inputs.exposures if row.ticker.upper() in relevant_tickers
    )
    selected_rows, conflicting_tickers, duplicates_removed = _selected_rows(relevant_exposures)
    values: dict[tuple[str, str], list[Decimal]] = defaultdict(list)
    missing_tickers: set[str] = set()
    stale_tickers: set[str] = set()
    invalid_tickers: set[str] = set()
    evaluation_date = inputs.proposed_trade_date
    stale_before = evaluation_date - timedelta(days=EXPOSURE_CACHE_MAX_AGE_DAYS)

    lookthrough_required = False
    for position in selected_positions:
        ticker = position.ticker.upper()
        security = inputs.security_for(ticker)
        asset_type = security.identity.asset_type if security is not None else position.asset_type
        if asset_type != "EQUITY":
            lookthrough_required = True
        market_value = Decimal(1) if ticker in unit_notional_tickers else position.market_value_usd
        if asset_type == "EQUITY":
            values[("security", ticker)].append(market_value)
            continue

        ticker_rows = [
            row for (row_ticker, _, _), row in selected_rows.items() if row_ticker == ticker
        ]
        if not ticker_rows:
            missing_tickers.add(ticker)
            continue
        if any(
            row.as_of_date < stale_before or row.as_of_date > evaluation_date for row in ticker_rows
        ):
            stale_tickers.add(ticker)
        for row in ticker_rows:
            if not row.weight.is_finite() or row.weight < 0 or row.weight > 1:
                invalid_tickers.add(ticker)
                continue
            dimension = _normalise_dimension(row.dimension)
            exposure_key = _normalise_key(row.dimension, row.exposure_key)
            values[(dimension, exposure_key)].append(market_value * row.weight)

    as_of_date = max((row.as_of_date for row in selected_rows.values()), default=None)
    source_dates: dict[str, date] = {}
    for row in relevant_exposures:
        source_dates[row.provider] = max(
            source_dates.get(row.provider, row.as_of_date), row.as_of_date
        )
    failures = missing_tickers | stale_tickers | conflicting_tickers | invalid_tickers
    if failures:
        complete: bool | None = False
    elif not lookthrough_required:
        complete = True
    else:
        complete = inputs.source_metadata.lookthrough_complete

    coverage = ExposureCoverage(
        complete=complete,
        as_of_date=as_of_date,
        missing_tickers=tuple(sorted(missing_tickers)),
        stale_tickers=tuple(sorted(stale_tickers)),
        conflicting_tickers=tuple(sorted(conflicting_tickers)),
        invalid_tickers=tuple(sorted(invalid_tickers)),
        duplicate_rows_removed=duplicates_removed,
        sources=tuple(
            ExposureSourceFreshness(provider, source_dates[provider])
            for provider in sorted(source_dates)
        ),
    )
    return ExposureAggregate(
        values=tuple(
            ExposureValue(dimension, exposure_key, exact_sum(amounts))
            for (dimension, exposure_key), amounts in sorted(values.items())
        ),
        coverage=coverage,
    )


def exposure_overlap(
    left: ExposureAggregate, right: ExposureAggregate, *, dimension: str = "security"
) -> ExposureOverlap:
    """Return shared normalized weight for one exposure dimension; never infer tracking error."""
    normalized_dimension = _normalise_dimension(dimension)
    if left.coverage.complete is not True or right.coverage.complete is not True:
        return ExposureOverlap(
            normalized_dimension, None, "incomplete_or_unknown_exposure_coverage"
        )

    left_values = {
        row.exposure_key: row.value_usd
        for row in left.values
        if _normalise_dimension(row.dimension) == normalized_dimension
    }
    right_values = {
        row.exposure_key: row.value_usd
        for row in right.values
        if _normalise_dimension(row.dimension) == normalized_dimension
    }
    left_total = exact_sum(left_values.values())
    right_total = exact_sum(right_values.values())
    if left_total <= 0 or right_total <= 0:
        return ExposureOverlap(normalized_dimension, None, "exposure_dimension_unavailable")

    shared = exact_sum(
        min(
            left_values.get(key, Decimal(0)) / left_total,
            right_values.get(key, Decimal(0)) / right_total,
        )
        for key in left_values.keys() | right_values.keys()
    )
    return ExposureOverlap(normalized_dimension, shared * Decimal(100), None)
