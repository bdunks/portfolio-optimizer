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
    dimension: str = "security"


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
    dimension: str,
    evaluation_date: date,
) -> tuple[dict[tuple[str, str, str], LookThroughExposureInput], set[str], int]:
    snapshots: dict[tuple[str, str], dict[tuple[str, date], list[LookThroughExposureInput]]] = (
        defaultdict(lambda: defaultdict(list))
    )
    for row in exposures:
        normalized_dimension = _normalise_dimension(row.dimension)
        if normalized_dimension != dimension:
            continue
        snapshots[(row.ticker.upper(), normalized_dimension)][
            (row.provider, row.as_of_date)
        ].append(row)

    selected: dict[tuple[str, str, str], LookThroughExposureInput] = {}
    conflicts: set[str] = set()
    duplicates_removed = 0
    stale_before = evaluation_date - timedelta(days=EXPOSURE_CACHE_MAX_AGE_DAYS)
    for (ticker, row_dimension), candidates in snapshots.items():
        valid = [
            (snapshot, rows)
            for snapshot, rows in candidates.items()
            if stale_before <= snapshot[1] <= evaluation_date
        ]
        available = valid or list(candidates.items())
        (provider, as_of_date), winning_rows = max(
            available,
            key=lambda item: (
                item[0][1],
                -_PROVIDER_ORDER.get(item[0][0], len(_PROVIDER_ORDER)),
                item[0][0],
            ),
        )
        del provider, as_of_date
        duplicates_removed += sum(len(rows) for rows in candidates.values()) - len(winning_rows)
        by_key: dict[str, list[LookThroughExposureInput]] = defaultdict(list)
        for row in winning_rows:
            by_key[_normalise_key(row.dimension, row.exposure_key)].append(row)
        for exposure_key, rows in by_key.items():
            if len({row.weight for row in rows}) > 1:
                conflicts.add(ticker)
            duplicates_removed += len(rows) - 1
            selected[(ticker, row_dimension, exposure_key)] = min(
                rows, key=lambda row: (str(row.weight), row.exposure_key)
            )
    return selected, conflicts, duplicates_removed


def aggregate_lookthrough_exposure(
    inputs: FinancialInputs,
    *,
    tickers: Sequence[str] | None = None,
    dimension: str = "security",
) -> ExposureAggregate:
    """Aggregate selected positions for one economic dimension using cached rows only.

    Direct equities are represented directly for the security dimension. Every other
    position/dimension pair requires an explicit cached row; a missing contributor makes
    coverage incomplete rather than silently normalizing the available subset. VB and VXF
    use their ordinary cached security-level look-through rows.
    """
    normalized_dimension = _normalise_dimension(dimension)
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
        row
        for row in inputs.exposures
        if row.ticker.upper() in relevant_tickers
        and _normalise_dimension(row.dimension) == normalized_dimension
    )
    selected_rows, conflicting_tickers, duplicates_removed = _selected_rows(
        relevant_exposures, normalized_dimension, inputs.proposed_trade_date
    )
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
        market_value = Decimal(1) if ticker in unit_notional_tickers else position.market_value_usd
        if asset_type == "EQUITY" and normalized_dimension == "security":
            values[("security", ticker)].append(market_value)
            continue

        lookthrough_required = True
        ticker_rows = [
            row
            for (row_ticker, row_dimension, _), row in selected_rows.items()
            if row_ticker == ticker and row_dimension == normalized_dimension
        ]
        if not ticker_rows:
            missing_tickers.add(ticker)
            continue
        if any(
            row.as_of_date < stale_before or row.as_of_date > evaluation_date for row in ticker_rows
        ):
            stale_tickers.add(ticker)
        ticker_weights: list[Decimal] = []
        for row in ticker_rows:
            if not row.weight.is_finite() or row.weight < 0 or row.weight > 1:
                invalid_tickers.add(ticker)
                continue
            ticker_weights.append(row.weight)
            exposure_key = _normalise_key(row.dimension, row.exposure_key)
            values[(normalized_dimension, exposure_key)].append(market_value * row.weight)
        if normalized_dimension == "sector" and exact_sum(ticker_weights) != Decimal(1):
            invalid_tickers.add(ticker)

    as_of_date = max((row.as_of_date for row in selected_rows.values()), default=None)
    source_dates: dict[str, date] = {}
    for row in selected_rows.values():
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
        dimension=normalized_dimension,
    )
    return ExposureAggregate(
        values=tuple(
            ExposureValue(value_dimension, exposure_key, exact_sum(amounts))
            for (value_dimension, exposure_key), amounts in sorted(values.items())
        ),
        coverage=coverage,
    )


def exposure_overlap(
    left: ExposureAggregate, right: ExposureAggregate, *, dimension: str = "security"
) -> ExposureOverlap:
    """Return shared normalized weight for one exposure dimension; never infer tracking error."""
    normalized_dimension = _normalise_dimension(dimension)
    if (
        left.coverage.dimension != normalized_dimension
        or right.coverage.dimension != normalized_dimension
    ):
        return ExposureOverlap(normalized_dimension, None, "requested_dimension_not_aggregated")
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
