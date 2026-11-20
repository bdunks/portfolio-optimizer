"""Explicit, injected refresh and typed status for current ETF look-through exposure data.

This service publishes one configured source per ticker. Provider adapters and local CSV parsing
run before the SQLite write transaction; successful batches replace each ticker's rows and
coverage metadata atomically. Provider-universe completeness is never inferred.
"""

from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal, cast

import httpx
from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    ExposureCacheState,
    ExposureDimensionCoverage,
    Security,
    SecurityExposure,
)
from app.domain.decimal_math import exact_sum
from app.domain.exposure import (
    EXPOSURE_CACHE_MAX_AGE_DAYS,
    _normalise_dimension,
    _normalise_key,
)
from app.schemas import ExposureInput
from app.services.errors import AppError
from app.services.ishares_market_data import (
    IsharesFundConfig,
    IsharesMarketDataError,
    fetch_ishares_exposures,
)
from app.services.market_data import (
    VanguardFundConfig,
    VanguardMarketDataError,
    fetch_vanguard_exposures,
)

MAX_LOCAL_CSV_BYTES = 8 * 1024 * 1024
_PROVIDER_VALUES = ("vanguard", "ishares", "manual_csv")
_SECURITY_DIMENSIONS = frozenset({"security", "ticker", "constituent", "constituent_ticker"})
_LOCAL_HEADER = ("ticker", "as_of_date", "dimension", "exposure_key", "weight")
_LOCAL_TICKER = re.compile(r"[A-Z0-9][A-Z0-9.-]{0,31}\Z")
_LOCAL_DIMENSION = re.compile(r"[a-z][a-z0-9_]{0,31}\Z")
_LOCAL_WEIGHT = re.compile(r"(?:0|1)(?:\.\d+)?\Z")

Provider = Literal["vanguard", "ishares", "manual_csv"]
Freshness = Literal["configured_missing", "current", "stale"]
AttemptStatus = Literal["never", "success", "failure"]


def _typed_provider(value: str | None) -> Provider | None:
    return cast(Provider, value) if value in _PROVIDER_VALUES else None


@dataclass(frozen=True, slots=True)
class LocalCsvExposureConfig:
    """Backend-selected local file for one configured ticker; never request-selected."""

    ticker: str
    path: Path

    def __post_init__(self) -> None:
        if not isinstance(self.path, Path):
            raise TypeError("local exposure path must be configured as a Path")


type ExposureSourceConfig = VanguardFundConfig | IsharesFundConfig | LocalCsvExposureConfig


@dataclass(frozen=True, slots=True)
class ExposureDimensionCoverageStatus:
    dimension: str
    covered_weight: Decimal
    complete: bool
    observed_item_count: int
    scope_item_count: int
    provider_universe_verified: bool


@dataclass(frozen=True, slots=True)
class ExposureCacheTickerStatus:
    ticker: str
    freshness: Freshness
    configured_provider: Provider
    provider: Provider | None
    as_of_date: date | None
    cached_at: datetime | None
    last_attempted_at: datetime | None
    last_attempt_provider: Provider | None
    last_attempt_status: AttemptStatus
    last_error_code: str | None
    last_error_summary: str | None
    publication_revision: int
    dimensions: tuple[ExposureDimensionCoverageStatus, ...]


@dataclass(frozen=True, slots=True)
class LocalCsvDimensionCoverage:
    dimension: str
    covered_weight: Decimal
    complete: bool
    observed_item_count: int
    scope_item_count: int


@dataclass(frozen=True, slots=True)
class LocalCsvExposureResult:
    ticker: str
    as_of_date: date
    exposures: tuple[ExposureInput, ...]
    coverage: tuple[LocalCsvDimensionCoverage, ...]


@dataclass(frozen=True, slots=True)
class _DimensionCoverage:
    dimension: str
    covered_weight: Decimal
    complete: bool
    observed_item_count: int
    scope_item_count: int


@dataclass(frozen=True, slots=True)
class _StagedTicker:
    ticker: str
    provider: Provider
    as_of_date: date
    received_at: datetime
    exposures: tuple[ExposureInput, ...]
    coverage: tuple[_DimensionCoverage, ...]


@dataclass(frozen=True, slots=True)
class _BaselineTicker:
    publication_revision: int
    as_of_date: date | None


class _StageFailure(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class _SupersededPublication(Exception):
    pass


class LocalExposureCsvError(ValueError):
    """The configured local exposure CSV does not satisfy the project-owned format."""


def _iter_csv_records(reader: Iterator[list[str]]) -> Iterator[list[str]]:
    try:
        yield from reader
    except csv.Error as exc:
        raise LocalExposureCsvError("configured local exposure CSV is malformed UTF-8") from exc


def parse_local_exposure_csv(config: LocalCsvExposureConfig) -> LocalCsvExposureResult:
    """Parse the exact configured five-column UTF-8 CSV format without network access."""
    ticker = _canonical_ticker(config.ticker)
    try:
        with config.path.open("rb") as stream:
            content = stream.read(MAX_LOCAL_CSV_BYTES + 1)
    except OSError as exc:
        raise LocalExposureCsvError("configured local exposure file could not be read") from exc
    if len(content) > MAX_LOCAL_CSV_BYTES:
        raise LocalExposureCsvError("configured local exposure file exceeds the size limit")
    try:
        text = content.decode("utf-8", errors="strict")
        rows = csv.reader(io.StringIO(text, newline=""), strict=True)
        header = next(rows, None)
    except (csv.Error, UnicodeError) as exc:
        raise LocalExposureCsvError("configured local exposure CSV is malformed UTF-8") from exc
    if header is None or tuple(header) != _LOCAL_HEADER:
        raise LocalExposureCsvError("configured local exposure CSV header is invalid")

    source_date: date | None = None
    exposures: list[ExposureInput] = []
    seen: set[tuple[str, str]] = set()
    dimension_weights: dict[str, list[Decimal]] = defaultdict(list)
    dimension_counts: dict[str, int] = defaultdict(int)
    for row_number, fields in enumerate(_iter_csv_records(rows), start=2):
        if len(fields) != len(_LOCAL_HEADER) or not any(field.strip() for field in fields):
            raise LocalExposureCsvError(f"configured local exposure row {row_number} is malformed")
        row_ticker, date_text, dimension, key, weight_text = fields
        if row_ticker != ticker:
            raise LocalExposureCsvError("configured local exposure CSV contains a different ticker")
        normalized_dimension = _normalise_dimension(dimension)
        if not _LOCAL_DIMENSION.fullmatch(normalized_dimension):
            raise LocalExposureCsvError(
                f"configured local exposure row {row_number} has invalid dimension"
            )
        if not key or any(char in key for char in "\r\n\t"):
            raise LocalExposureCsvError(
                f"configured local exposure row {row_number} has invalid key"
            )
        normalized_key = _normalise_key(normalized_dimension, key)
        if not normalized_key or any(char in normalized_key for char in "\r\n\t"):
            raise LocalExposureCsvError(
                f"configured local exposure row {row_number} has invalid key"
            )
        try:
            row_date = date.fromisoformat(date_text)
            if row_date.isoformat() != date_text:
                raise ValueError("noncanonical date")
        except ValueError as exc:
            raise LocalExposureCsvError(
                f"configured local exposure row {row_number} has invalid date"
            ) from exc
        if source_date is None:
            source_date = row_date
        elif source_date != row_date:
            raise LocalExposureCsvError(
                "configured local exposure CSV contains multiple source dates"
            )
        if len(weight_text) > 128 or not _LOCAL_WEIGHT.fullmatch(weight_text):
            raise LocalExposureCsvError(
                f"configured local exposure row {row_number} has invalid weight"
            )
        try:
            weight = Decimal(weight_text)
        except InvalidOperation as exc:
            raise LocalExposureCsvError(
                f"configured local exposure row {row_number} has invalid weight"
            ) from exc
        if not weight.is_finite() or weight < 0 or weight > 1:
            raise LocalExposureCsvError(
                f"configured local exposure row {row_number} has invalid weight"
            )
        identity = normalized_dimension, normalized_key
        if identity in seen:
            raise LocalExposureCsvError(
                "configured local exposure CSV contains duplicate dimension keys"
            )
        seen.add(identity)
        try:
            exposure = ExposureInput(
                ticker=ticker,
                dimension=normalized_dimension,
                exposure_key=normalized_key,
                weight=weight,
                provider="manual_csv",
                as_of_date=row_date,
            )
        except ValidationError as exc:
            raise LocalExposureCsvError(
                f"configured local exposure row {row_number} is invalid"
            ) from exc
        exposures.append(exposure)
        dimension_weights[normalized_dimension].append(weight)
        dimension_counts[normalized_dimension] += 1

    if source_date is None:
        raise LocalExposureCsvError("configured local exposure CSV contains no holdings")
    coverage: list[LocalCsvDimensionCoverage] = []
    for dimension in sorted(dimension_weights):
        covered_weight = exact_sum(dimension_weights[dimension])
        if covered_weight > 1:
            raise LocalExposureCsvError(f"configured local exposure {dimension} weights exceed one")
        count = dimension_counts[dimension]
        coverage.append(
            LocalCsvDimensionCoverage(
                dimension=dimension,
                covered_weight=covered_weight,
                complete=covered_weight == 1,
                observed_item_count=count,
                scope_item_count=count,
            )
        )
    return LocalCsvExposureResult(ticker, source_date, tuple(exposures), tuple(coverage))


def refresh_exposure_cache(
    factory: sessionmaker[Session],
    sources: Sequence[ExposureSourceConfig],
    *,
    clock: Callable[[], datetime],
    vanguard_client: httpx.Client | None = None,
    ishares_client: httpx.Client | None = None,
    publication_hook: Callable[[], None] | None = None,
) -> tuple[ExposureCacheTickerStatus, ...]:
    """Stage configured sources then atomically replace all requested ticker snapshots.

    The caller owns provider clients and configuration. No client or network transport is created
    here. On any invalid source, the prior success remains intact, attempt metadata is recorded,
    and a sanitized ``AppError`` is raised. A newer overlapping publication supersedes this one.
    """
    configured = _validated_sources(sources)
    if not configured:
        raise AppError(
            "exposure_sources_unconfigured",
            "No look-through exposure sources are configured",
            status_code=503,
        )
    try:
        attempted_at = _utc_datetime(clock())
    except (TypeError, ValueError, OverflowError) as exc:
        raise AppError(
            "exposure_clock_invalid", "Exposure refresh clock must be timezone-aware"
        ) from exc

    tickers = tuple(ticker for ticker, _, _ in configured)
    baseline = _capture_baseline(factory, tickers)
    staged: dict[str, _StagedTicker] = {}
    failures: dict[str, str] = {}
    for ticker, source, provider in configured:
        try:
            value = _fetch_source(
                source,
                provider=provider,
                ticker=ticker,
                vanguard_client=vanguard_client,
                ishares_client=ishares_client,
                clock=clock,
            )
            if value.as_of_date > value.received_at.date():
                raise _StageFailure("exposure_date_invalid")
            old_date = baseline[ticker].as_of_date
            if old_date is not None and value.as_of_date < old_date:
                raise _StageFailure("exposure_date_regression")
            staged[ticker] = value
        except _StageFailure as exc:
            failures[ticker] = exc.code
        except Exception:  # noqa: BLE001 - source failures are reported without provider details
            failures[ticker] = "exposure_source_invalid"

    if failures:
        codes = dict.fromkeys(tickers, "exposure_batch_aborted")
        codes.update(failures)
        _record_failures_or_raise(factory, baseline, attempted_at, configured, codes)
        raise AppError(
            "exposure_refresh_failed",
            "One or more configured exposure sources failed validation; prior cache rows were retained",
            status_code=422,
        )

    try:
        _publish_batch(
            factory,
            staged,
            baseline,
            attempted_at=attempted_at,
            publication_hook=publication_hook,
        )
    except _SupersededPublication as exc:
        raise AppError(
            "exposure_refresh_superseded",
            "A newer exposure cache publication superseded this refresh",
            status_code=409,
        ) from exc
    except Exception as exc:
        codes = dict.fromkeys(tickers, "exposure_cache_publish_failed")
        _record_failures_or_raise(factory, baseline, attempted_at, configured, codes)
        raise AppError(
            "exposure_cache_publish_failed",
            "Validated exposure data could not be published; prior cache rows were retained",
            status_code=500,
        ) from exc

    evaluation_date = max(value.received_at.date() for value in staged.values())
    with factory() as session:
        return get_exposure_cache_status(session, sources, evaluation_date=evaluation_date)


def get_exposure_cache_status(
    session: Session,
    sources: Sequence[ExposureSourceConfig],
    *,
    evaluation_date: date,
) -> tuple[ExposureCacheTickerStatus, ...]:
    """Read configured tickers' persisted success, coverage and independent attempt status only."""
    configured = _validated_sources(sources)
    if not configured:
        return ()
    tickers = tuple(ticker for ticker, _, _ in configured)
    states = {
        state.ticker: state
        for state in session.scalars(
            select(ExposureCacheState).where(ExposureCacheState.ticker.in_(tickers))
        ).all()
    }
    coverage_rows = session.scalars(
        select(ExposureDimensionCoverage)
        .where(ExposureDimensionCoverage.ticker.in_(tickers))
        .order_by(ExposureDimensionCoverage.ticker, ExposureDimensionCoverage.dimension)
    ).all()
    coverage_by_ticker: dict[str, list[ExposureDimensionCoverageStatus]] = defaultdict(list)
    for row in coverage_rows:
        coverage_by_ticker[row.ticker].append(
            ExposureDimensionCoverageStatus(
                dimension=row.dimension,
                covered_weight=row.covered_weight,
                complete=row.complete,
                observed_item_count=row.observed_item_count,
                scope_item_count=row.scope_item_count,
                provider_universe_verified=row.provider_universe_verified,
            )
        )

    statuses: list[ExposureCacheTickerStatus] = []
    for ticker, _, configured_provider in configured:
        state = states.get(ticker)
        state_provider = _typed_provider(state.provider if state is not None else None)
        attempt_provider = _typed_provider(
            state.last_attempt_provider if state is not None else None
        )
        attempt_status: AttemptStatus = "never"
        if state is not None:
            attempt_status = "success" if state.last_attempt_status == "success" else "failure"
        if state is None or state.as_of_date is None:
            freshness: Freshness = "configured_missing"
        else:
            age_days = (evaluation_date - state.as_of_date).days
            freshness = "current" if 0 <= age_days <= EXPOSURE_CACHE_MAX_AGE_DAYS else "stale"
        statuses.append(
            ExposureCacheTickerStatus(
                ticker=ticker,
                freshness=freshness,
                configured_provider=configured_provider,
                provider=state_provider,
                as_of_date=state.as_of_date if state is not None else None,
                cached_at=state.cached_at if state is not None else None,
                last_attempted_at=state.last_attempted_at if state is not None else None,
                last_attempt_provider=attempt_provider,
                last_attempt_status=attempt_status,
                last_error_code=state.last_error_code if state is not None else None,
                last_error_summary=state.last_error_summary if state is not None else None,
                publication_revision=(state.publication_revision if state is not None else 0),
                dimensions=tuple(coverage_by_ticker.get(ticker, ())),
            )
        )
    return tuple(statuses)


def _validated_sources(
    sources: Sequence[ExposureSourceConfig],
) -> tuple[tuple[str, ExposureSourceConfig, Provider], ...]:
    configured: list[tuple[str, ExposureSourceConfig, Provider]] = []
    seen: set[str] = set()
    for source in sources:
        if isinstance(source, VanguardFundConfig):
            provider: Provider = "vanguard"
        elif isinstance(source, IsharesFundConfig):
            provider = "ishares"
        elif isinstance(source, LocalCsvExposureConfig):
            provider = "manual_csv"
        else:
            raise AppError("exposure_source_invalid", "An exposure source configuration is invalid")
        ticker = _canonical_ticker(source.ticker)
        if ticker in seen:
            raise AppError(
                "exposure_source_duplicate",
                "Configure at most one look-through source per ticker",
            )
        seen.add(ticker)
        configured.append((ticker, source, provider))
    return tuple(configured)


def _canonical_ticker(ticker: str) -> str:
    if not isinstance(ticker, str):
        raise TypeError("ticker must be a string")
    normalized = ticker.strip().upper()
    if not _LOCAL_TICKER.fullmatch(normalized):
        raise ValueError("ticker is invalid")
    return normalized


def _utc_datetime(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _fetch_source(
    source: ExposureSourceConfig,
    *,
    provider: Provider,
    ticker: str,
    vanguard_client: httpx.Client | None,
    ishares_client: httpx.Client | None,
    clock: Callable[[], datetime],
) -> _StagedTicker:
    try:
        if isinstance(source, VanguardFundConfig):
            if vanguard_client is None:
                raise _StageFailure("exposure_source_unavailable")
            result = fetch_vanguard_exposures(source, vanguard_client)
            result_ticker = result.fund_ticker
            exposures = result.exposures
            as_of_date = result.as_of_date
            coverage = tuple(
                _DimensionCoverage(
                    dimension=row.dimension,
                    covered_weight=row.covered_weight,
                    complete=row.complete,
                    observed_item_count=row.observed_constituents,
                    scope_item_count=row.total_constituents,
                )
                for row in result.coverage
            )
            received_at = _utc_datetime(clock())
        elif isinstance(source, IsharesFundConfig):
            if ishares_client is None:
                raise _StageFailure("exposure_source_unavailable")
            result = fetch_ishares_exposures(source, ishares_client, clock=clock)
            result_ticker = result.fund_ticker
            exposures = result.exposures
            as_of_date = result.as_of_date
            coverage = tuple(
                _DimensionCoverage(
                    dimension=row.dimension,
                    covered_weight=row.covered_weight,
                    complete=row.complete,
                    observed_item_count=row.observed_holdings,
                    scope_item_count=row.eligible_holdings,
                )
                for row in result.coverage
            )
            received_at = _utc_datetime(result.fetched_at)
        else:
            result = parse_local_exposure_csv(source)
            result_ticker = result.ticker
            exposures = result.exposures
            as_of_date = result.as_of_date
            coverage = tuple(
                _DimensionCoverage(
                    dimension=row.dimension,
                    covered_weight=row.covered_weight,
                    complete=row.complete,
                    observed_item_count=row.observed_item_count,
                    scope_item_count=row.scope_item_count,
                )
                for row in result.coverage
            )
            received_at = _utc_datetime(clock())
        _validate_source_result(
            ticker=ticker,
            provider=provider,
            result_ticker=result_ticker,
            as_of_date=as_of_date,
            exposures=exposures,
            coverage=coverage,
        )
        return _StagedTicker(ticker, provider, as_of_date, received_at, exposures, coverage)
    except _StageFailure:
        raise
    except VanguardMarketDataError, IsharesMarketDataError, LocalExposureCsvError:
        raise _StageFailure("exposure_source_invalid") from None
    except ValidationError, ValueError, TypeError, ArithmeticError, OSError, csv.Error:
        raise _StageFailure("exposure_source_invalid") from None
    except Exception:  # noqa: BLE001 - provider and local failures are sanitized at this boundary
        raise _StageFailure("exposure_source_failed") from None


def _validate_source_result(
    *,
    ticker: str,
    provider: Provider,
    result_ticker: str,
    as_of_date: date,
    exposures: tuple[ExposureInput, ...],
    coverage: tuple[_DimensionCoverage, ...],
) -> None:
    if _canonical_ticker(result_ticker) != ticker or not isinstance(as_of_date, date):
        raise ValueError("source identity or holdings date is inconsistent")
    if provider not in _PROVIDER_VALUES:
        raise ValueError("source provider is invalid")
    exposure_totals: dict[str, list[Decimal]] = defaultdict(list)
    exposure_counts: dict[str, int] = defaultdict(int)
    seen_exposures: set[tuple[str, str]] = set()
    for row in exposures:
        if (
            not isinstance(row, ExposureInput)
            or row.ticker != ticker
            or row.provider != provider
            or row.as_of_date != as_of_date
            or not row.dimension
            or row.dimension != row.dimension.strip()
            or not row.exposure_key
            or row.exposure_key != row.exposure_key.strip()
            or not row.weight.is_finite()
            or row.weight < 0
            or row.weight > 1
        ):
            raise ValueError("source exposure is inconsistent")
        normalized_key = (
            row.exposure_key.upper()
            if row.dimension.strip().lower() in _SECURITY_DIMENSIONS
            else row.exposure_key
        )
        identity = row.dimension, normalized_key
        if identity in seen_exposures:
            raise ValueError("source exposure key is duplicated")
        seen_exposures.add(identity)
        exposure_totals[row.dimension].append(row.weight)
        exposure_counts[row.dimension] += 1
    coverage_by_dimension: dict[str, _DimensionCoverage] = {}
    for row in coverage:
        if (
            not row.dimension
            or row.dimension != row.dimension.strip()
            or row.dimension in coverage_by_dimension
            or not row.covered_weight.is_finite()
            or row.covered_weight < 0
            or row.covered_weight > 1
            or row.observed_item_count < 0
            or row.scope_item_count < row.observed_item_count
        ):
            raise ValueError("source dimension coverage is inconsistent")
        if row.complete and (
            row.covered_weight != 1 or row.observed_item_count != row.scope_item_count
        ):
            raise ValueError("complete dimension does not cover its observed scope")
        coverage_by_dimension[row.dimension] = row
    if not set(exposure_totals).issubset(coverage_by_dimension):
        raise ValueError("source exposure dimension lacks coverage metadata")
    for dimension, metadata in coverage_by_dimension.items():
        covered_weight = exact_sum(exposure_totals.get(dimension, ()))
        if covered_weight != metadata.covered_weight:
            raise ValueError("source exposure weights disagree with coverage metadata")
        if exposure_counts.get(dimension, 0) > metadata.observed_item_count:
            raise ValueError("source exposure count exceeds observed scope")


def _persisted_exposure_date(session: Session, ticker: str) -> date | None:
    dates = session.scalars(
        select(SecurityExposure.as_of_date)
        .join(Security, Security.id == SecurityExposure.security_id)
        .where(Security.ticker == ticker)
    ).all()
    return max(dates, default=None)


def _capture_baseline(
    factory: sessionmaker[Session], tickers: tuple[str, ...]
) -> dict[str, _BaselineTicker]:
    with factory() as session:
        states = session.scalars(
            select(ExposureCacheState).where(ExposureCacheState.ticker.in_(tickers))
        ).all()
        existing = {state.ticker: state for state in states}
        persisted_dates = {ticker: _persisted_exposure_date(session, ticker) for ticker in tickers}
    return {
        ticker: _BaselineTicker(
            publication_revision=(
                existing[ticker].publication_revision if ticker in existing else 0
            ),
            as_of_date=max(
                filter(
                    None,
                    (
                        state.as_of_date if (state := existing.get(ticker)) is not None else None,
                        persisted_dates.get(ticker),
                    ),
                ),
                default=None,
            ),
        )
        for ticker in tickers
    }


def _publish_batch(
    factory: sessionmaker[Session],
    staged: dict[str, _StagedTicker],
    baseline: dict[str, _BaselineTicker],
    *,
    attempted_at: datetime,
    publication_hook: Callable[[], None] | None,
) -> None:
    with factory.begin() as session:
        session.connection(execution_options={"sqlite_begin_mode": "IMMEDIATE"})
        states = {
            state.ticker: state
            for state in session.scalars(
                select(ExposureCacheState).where(ExposureCacheState.ticker.in_(tuple(staged)))
            ).all()
        }
        for ticker, baseline_value in baseline.items():
            state = states.get(ticker)
            current_revision = state.publication_revision if state is not None else 0
            current_attempt = state.last_attempted_at if state is not None else None
            if current_revision != baseline_value.publication_revision or (
                current_attempt is not None and current_attempt > attempted_at
            ):
                raise _SupersededPublication
            current_exposure_date = _persisted_exposure_date(session, ticker)
            if (
                current_exposure_date is not None
                and staged[ticker].as_of_date < current_exposure_date
            ):
                raise _SupersededPublication

        for ticker, value in staged.items():
            security = session.scalar(select(Security).where(Security.ticker == ticker))
            if security is None:
                security = Security(
                    ticker=ticker,
                    asset_type="ETF",
                    is_completion_etf=ticker in {"VB", "VXF"},
                )
                session.add(security)
                session.flush()
            session.execute(
                delete(SecurityExposure).where(SecurityExposure.security_id == security.id)
            )
            session.execute(
                delete(ExposureDimensionCoverage).where(ExposureDimensionCoverage.ticker == ticker)
            )
            session.add_all(
                SecurityExposure(
                    security_id=security.id,
                    dimension=row.dimension,
                    exposure_key=row.exposure_key,
                    weight=row.weight,
                    provider=row.provider,
                    as_of_date=row.as_of_date,
                )
                for row in value.exposures
            )
            session.add_all(
                ExposureDimensionCoverage(
                    ticker=ticker,
                    dimension=row.dimension,
                    covered_weight=row.covered_weight,
                    complete=row.complete,
                    observed_item_count=row.observed_item_count,
                    scope_item_count=row.scope_item_count,
                    provider_universe_verified=False,
                )
                for row in value.coverage
            )
            state = states.get(ticker)
            if state is None:
                state = ExposureCacheState(
                    ticker=ticker,
                    publication_revision=0,
                    last_attempt_status="success",
                )
                session.add(state)
                states[ticker] = state
            state.provider = value.provider
            state.as_of_date = value.as_of_date
            state.cached_at = value.received_at
            state.publication_revision = baseline[ticker].publication_revision + 1
            state.last_attempted_at = attempted_at
            state.last_attempt_provider = value.provider
            state.last_attempt_status = "success"
            state.last_error_code = None
            state.last_error_summary = None
        session.flush()
        if publication_hook is not None:
            publication_hook()


def _record_failures_or_raise(
    factory: sessionmaker[Session],
    baseline: dict[str, _BaselineTicker],
    attempted_at: datetime,
    configured: tuple[tuple[str, ExposureSourceConfig, Provider], ...],
    codes: dict[str, str],
) -> None:
    try:
        _record_failed_attempt(factory, baseline, attempted_at, configured, codes)
    except _SupersededPublication as exc:
        raise AppError(
            "exposure_refresh_superseded",
            "A newer exposure cache publication superseded this refresh",
            status_code=409,
        ) from exc
    except SQLAlchemyError as exc:
        raise AppError(
            "exposure_attempt_status_failed",
            "Exposure attempt status could not be saved; prior cache rows were retained",
            status_code=500,
        ) from exc


def _record_failed_attempt(
    factory: sessionmaker[Session],
    baseline: dict[str, _BaselineTicker],
    attempted_at: datetime,
    configured: tuple[tuple[str, ExposureSourceConfig, Provider], ...],
    codes: dict[str, str],
) -> None:
    with factory.begin() as session:
        session.connection(execution_options={"sqlite_begin_mode": "IMMEDIATE"})
        tickers = tuple(ticker for ticker, _, _ in configured)
        states = {
            state.ticker: state
            for state in session.scalars(
                select(ExposureCacheState).where(ExposureCacheState.ticker.in_(tickers))
            ).all()
        }
        for ticker in tickers:
            state = states.get(ticker)
            current_revision = state.publication_revision if state is not None else 0
            current_attempt = state.last_attempted_at if state is not None else None
            if current_revision != baseline[ticker].publication_revision or (
                current_attempt is not None and current_attempt > attempted_at
            ):
                raise _SupersededPublication
        provider_by_ticker = {ticker: provider for ticker, _, provider in configured}
        for ticker in tickers:
            state = states.get(ticker)
            if state is None:
                state = ExposureCacheState(
                    ticker=ticker,
                    publication_revision=0,
                    last_attempt_status="failure",
                )
                session.add(state)
            state.last_attempted_at = attempted_at
            state.last_attempt_provider = provider_by_ticker[ticker]
            state.last_attempt_status = "failure"
            state.last_error_code = codes[ticker]
            state.last_error_summary = (
                "Configured exposure refresh failed; any previous successful cache was retained"
            )
