"""Persist explicitly refreshed broker positions and exact lots atomically."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Literal, Protocol
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.broker.etrade_read import (
    EtradeAccountCandidate,
    EtradeLotRecord,
    EtradePortfolioWithLots,
    EtradePositionRecord,
)
from app.db.models import (
    Account,
    CurrentPosition,
    CurrentTaxLot,
    LotCacheState,
    Security,
    SyncState,
    canonical_decimal,
)
from app.domain.decimal_math import exact_product, exact_sum
from app.schemas import LotInput, PositionInput
from app.services.errors import AppError
from app.services.sync import _security_for_ticker

_LotCacheFreshness = Literal["unknown", "current", "stale"]
_UTC_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_EASTERN = ZoneInfo("America/New_York")
_ERROR_CODE = re.compile(r"[a-z0-9_]{1,64}\Z")


class PortfolioWithLotsReader(Protocol):
    """Injected offline-capable broker reader; this service never constructs transport."""

    def fetch_portfolio_with_lots(
        self, *, previously_bound_account_id_key: str | None = None
    ) -> EtradePortfolioWithLots: ...


@dataclass(frozen=True, slots=True)
class PortfolioLotCacheStatus:
    """Persisted cache freshness and current-quantity coverage for API presentation."""

    freshness: _LotCacheFreshness
    current_generation: int | None
    cache_revision: int | None
    source_generation: int | None
    source_as_of: datetime | None
    cached_at: datetime | None
    last_attempted_at: datetime | None
    last_error_code: str | None
    last_error_summary: str | None
    position_count: int
    covered_position_count: int
    lot_count: int
    quantity_coverage_complete: bool


@dataclass(frozen=True, slots=True)
class _Baseline:
    account_id_key: str
    current_generation: int
    cache_revision: int
    portfolio_fingerprint: str


@dataclass(frozen=True, slots=True)
class _ValidatedPosition:
    broker_position_id: str
    broker_product_id: str | None
    position: PositionInput


@dataclass(frozen=True, slots=True)
class _ValidatedLot:
    record: EtradeLotRecord
    acquired_date_source: str


@dataclass(frozen=True, slots=True)
class _ValidatedPortfolio:
    as_of: datetime
    positions: tuple[_ValidatedPosition, ...]
    lots: tuple[_ValidatedLot, ...]


def get_lot_cache_status(session: Session) -> PortfolioLotCacheStatus:
    """Read only persisted cache metadata and verify lot sums against current positions."""
    account = session.get(Account, 1)
    sync_state = session.get(SyncState, 1)
    cache_state = session.get(LotCacheState, 1)
    positions = (
        session.scalars(
            select(CurrentPosition)
            .where(CurrentPosition.account_id == account.id)
            .order_by(CurrentPosition.security_id)
        ).all()
        if account is not None
        else []
    )
    lots = (
        session.scalars(
            select(CurrentTaxLot)
            .where(CurrentTaxLot.account_id == account.id)
            .order_by(CurrentTaxLot.broker_lot_id)
        ).all()
        if account is not None
        else []
    )
    position_by_security = {position.security_id: position for position in positions}
    lots_by_security: dict[int, list[CurrentTaxLot]] = defaultdict(list)
    orphan_lot = False
    for lot in lots:
        if lot.security_id not in position_by_security:
            orphan_lot = True
        lots_by_security[lot.security_id].append(lot)

    current_generation = sync_state.current_generation if sync_state is not None else None
    covered_position_count = 0
    all_rows_current = current_generation is not None
    for position in positions:
        position_lots = lots_by_security.get(position.security_id, [])
        generation_matches = (
            current_generation is not None
            and position.sync_generation == current_generation
            and all(lot.sync_generation == current_generation for lot in position_lots)
        )
        try:
            quantity_matches = (
                position.shares.is_finite()
                and position.shares > 0
                and exact_sum(lot.shares for lot in position_lots) == position.shares
            )
        except ArithmeticError, TypeError, ValueError:
            quantity_matches = False
        if generation_matches and quantity_matches:
            covered_position_count += 1
        else:
            all_rows_current = False
    if orphan_lot or any(
        current_generation is None or lot.sync_generation != current_generation for lot in lots
    ):
        all_rows_current = False
    quantity_coverage_complete = (
        not orphan_lot and covered_position_count == len(positions) and all_rows_current
    )

    if cache_state is None or cache_state.source_generation is None:
        freshness: _LotCacheFreshness = "unknown"
    elif (
        current_generation is not None
        and cache_state.source_generation == current_generation
        and cache_state.source_as_of is not None
        and cache_state.cached_at is not None
        and quantity_coverage_complete
    ):
        freshness = "current"
    else:
        freshness = "stale"
    return PortfolioLotCacheStatus(
        freshness=freshness,
        current_generation=current_generation,
        cache_revision=cache_state.revision if cache_state is not None else None,
        source_generation=cache_state.source_generation if cache_state is not None else None,
        source_as_of=cache_state.source_as_of if cache_state is not None else None,
        cached_at=cache_state.cached_at if cache_state is not None else None,
        last_attempted_at=cache_state.last_attempted_at if cache_state is not None else None,
        last_error_code=cache_state.last_error_code if cache_state is not None else None,
        last_error_summary=cache_state.last_error_summary if cache_state is not None else None,
        position_count=len(positions),
        covered_position_count=covered_position_count,
        lot_count=len(lots),
        quantity_coverage_complete=quantity_coverage_complete,
    )


def refresh_portfolio_lots(
    factory: sessionmaker[Session],
    reader: PortfolioWithLotsReader,
    *,
    correlation_id: str,
    publication_hook: Callable[[], None] | None = None,
) -> PortfolioLotCacheStatus:
    """Fetch all current positions/lots outside writes, then publish one guarded generation."""
    del correlation_id  # Reserved for the connected API/audit increment.
    attempted_at = datetime.now(UTC)
    baseline = _capture_baseline(factory)
    try:
        raw_result = reader.fetch_portfolio_with_lots(
            previously_bound_account_id_key=baseline.account_id_key
        )
        portfolio = _validate_portfolio(raw_result, baseline.account_id_key)
    except AppError as exc:
        _record_failure(
            factory,
            account_id_key=baseline.account_id_key,
            attempted_at=attempted_at,
            code=_safe_error_code(exc.code),
            summary="Broker portfolio and exact lots could not be validated",
        )
        raise AppError(
            _safe_error_code(exc.code),
            "Broker portfolio and exact lots could not be validated",
            status_code=_safe_status_code(exc.status_code),
        ) from exc
    except (ValidationError, TypeError, ValueError, ArithmeticError) as exc:
        _record_failure(
            factory,
            account_id_key=baseline.account_id_key,
            attempted_at=attempted_at,
            code="malformed_lot_cache_payload",
            summary="Broker portfolio and exact lots could not be validated",
        )
        raise AppError(
            "malformed_lot_cache_payload",
            "Broker portfolio and exact lots could not be validated",
            status_code=422,
        ) from exc
    except Exception as exc:
        _record_failure(
            factory,
            account_id_key=baseline.account_id_key,
            attempted_at=attempted_at,
            code="lot_cache_read_failed",
            summary="Broker portfolio and exact lots could not be read",
        )
        raise AppError(
            "lot_cache_read_failed",
            "Broker portfolio and exact lots could not be read",
            status_code=502,
        ) from exc

    try:
        _publish(
            factory,
            baseline=baseline,
            portfolio=portfolio,
            attempted_at=attempted_at,
            publication_hook=publication_hook,
        )
    except AppError as exc:
        _record_failure(
            factory,
            account_id_key=baseline.account_id_key,
            attempted_at=attempted_at,
            code=_safe_error_code(exc.code),
            summary="Validated broker portfolio could not be published; prior rows were retained",
        )
        raise
    except Exception as exc:
        _record_failure(
            factory,
            account_id_key=baseline.account_id_key,
            attempted_at=attempted_at,
            code="lot_cache_publish_failed",
            summary="Validated broker portfolio could not be published; prior rows were retained",
        )
        raise AppError(
            "lot_cache_publish_failed",
            "Validated broker portfolio could not be published; prior rows were retained",
            status_code=500,
        ) from exc

    with factory() as session:
        return get_lot_cache_status(session)


def _capture_baseline(factory: sessionmaker[Session]) -> _Baseline:
    with factory() as session:
        account = session.get(Account, 1)
        if account is None:
            raise AppError(
                "managed_account_unbound",
                "An existing managed brokerage account is required before refreshing portfolio lots",
                status_code=409,
            )
        positions = session.scalars(
            select(CurrentPosition)
            .where(CurrentPosition.account_id == account.id)
            .order_by(CurrentPosition.id)
        ).all()
        lots = session.scalars(
            select(CurrentTaxLot)
            .where(CurrentTaxLot.account_id == account.id)
            .order_by(CurrentTaxLot.id)
        ).all()
        sync_state = session.get(SyncState, 1)
        cache_state = session.get(LotCacheState, 1)
        return _Baseline(
            account_id_key=account.broker_account_id_key,
            current_generation=sync_state.current_generation if sync_state is not None else 0,
            cache_revision=cache_state.revision if cache_state is not None else 0,
            portfolio_fingerprint=_portfolio_fingerprint(positions, lots),
        )


def _validate_portfolio(result: object, account_id_key: str) -> _ValidatedPortfolio:
    if not isinstance(result, EtradePortfolioWithLots):
        raise _malformed_payload()
    if not isinstance(result.account, EtradeAccountCandidate):
        raise _malformed_payload()
    if result.account.account_id_key != account_id_key:
        raise AppError(
            "managed_account_mismatch",
            "The broker result does not match the already-bound managed account",
            status_code=409,
        )
    if not isinstance(result.as_of, datetime) or result.as_of.tzinfo is None:
        raise _malformed_payload()
    if result.as_of.utcoffset() is None:
        raise _malformed_payload()
    as_of = result.as_of.astimezone(UTC)
    if not isinstance(result.positions, tuple) or not isinstance(result.lots, tuple):
        raise _malformed_payload()

    validated_positions: list[_ValidatedPosition] = []
    position_by_id: dict[str, EtradePositionRecord] = {}
    tickers: set[str] = set()
    for record in result.positions:
        if not isinstance(record, EtradePositionRecord) or not isinstance(
            record.position, PositionInput
        ):
            raise _malformed_payload()
        if not _valid_identifier(record.broker_position_id, maximum=128):
            raise _malformed_payload()
        position = record.position
        if (
            not _valid_identifier(position.ticker, maximum=32)
            or position.ticker in tickers
            or record.broker_position_id in position_by_id
            or position.asset_type not in {"EQUITY", "ETF"}
            or not _finite(position.shares)
            or position.shares <= 0
            or not _finite(position.market_value_usd)
            or position.market_value_usd < 0
        ):
            raise _malformed_payload()
        tickers.add(position.ticker)
        position_by_id[record.broker_position_id] = record
        validated_positions.append(
            _ValidatedPosition(
                broker_position_id=record.broker_position_id,
                broker_product_id=_encode_product_id(record.broker_product_id),
                position=position,
            )
        )

    validated_lots: list[_ValidatedLot] = []
    seen_lot_ids: set[str] = set()
    lots_by_position: dict[str, list[Decimal]] = defaultdict(list)
    for record in result.lots:
        if not isinstance(record, EtradeLotRecord) or not isinstance(record.lot, LotInput):
            raise _malformed_payload()
        if (
            not _valid_identifier(record.broker_lot_id, maximum=128)
            or record.broker_lot_id in seen_lot_ids
            or record.broker_position_id not in position_by_id
            or record.ticker != position_by_id[record.broker_position_id].position.ticker
            or record.lot.ticker != record.ticker
            or record.lot.broker_lot_id != record.broker_lot_id
            or not _finite(record.remaining_shares)
            or record.remaining_shares <= 0
            or not _finite(record.available_shares)
            or record.available_shares < 0
            or record.available_shares > record.remaining_shares
            or not _finite(record.reserved_shares)
            or record.reserved_shares < 0
            or record.reserved_shares
            != exact_sum((record.remaining_shares, -record.available_shares))
            or record.lot.shares != record.remaining_shares
            or record.lot.available_shares != record.available_shares
            or not _finite(record.total_cost_usd)
            or record.total_cost_usd < 0
            or not _finite(record.total_cost_source)
            or record.total_cost_source != record.total_cost_usd
            or not _finite(record.lot.adjusted_unit_basis_usd)
            or record.lot.adjusted_unit_basis_usd < 0
            or exact_product(record.remaining_shares, record.lot.adjusted_unit_basis_usd)
            != record.total_cost_usd
            or record.lot.source != "ETRADE"
            or not isinstance(record.lot.acquired_date, date)
            or isinstance(record.lot.acquired_date, datetime)
            or not isinstance(record.lot.as_of, datetime)
            or record.lot.as_of.tzinfo is None
            or record.lot.as_of.astimezone(UTC) != as_of
        ):
            raise _malformed_payload()
        acquired_source = _encode_acquired_date_source(record.acquired_date_source)
        if _acquired_date_from_source(record.acquired_date_source) != record.lot.acquired_date:
            raise _malformed_payload()
        seen_lot_ids.add(record.broker_lot_id)
        lots_by_position[record.broker_position_id].append(record.remaining_shares)
        validated_lots.append(_ValidatedLot(record, acquired_source))

    for position_id, position_record in position_by_id.items():
        if exact_sum(lots_by_position.get(position_id, [])) != position_record.position.shares:
            raise AppError(
                "incomplete_lots",
                "Broker exact lots do not reconcile with every reported position quantity",
                status_code=422,
            )
    return _ValidatedPortfolio(as_of, tuple(validated_positions), tuple(validated_lots))


def _publish(
    factory: sessionmaker[Session],
    *,
    baseline: _Baseline,
    portfolio: _ValidatedPortfolio,
    attempted_at: datetime,
    publication_hook: Callable[[], None] | None,
) -> None:
    cached_at = datetime.now(UTC)
    with factory.begin() as session:
        session.connection(execution_options={"sqlite_begin_mode": "IMMEDIATE"})
        account = session.get(Account, 1)
        if account is None or account.broker_account_id_key != baseline.account_id_key:
            raise AppError(
                "managed_account_mismatch",
                "The managed account changed while portfolio lots were being refreshed",
                status_code=409,
            )
        sync_state = session.get(SyncState, 1)
        current_generation = sync_state.current_generation if sync_state is not None else 0
        cache_state = session.get(LotCacheState, 1)
        current_revision = cache_state.revision if cache_state is not None else 0
        positions = session.scalars(
            select(CurrentPosition)
            .where(CurrentPosition.account_id == account.id)
            .order_by(CurrentPosition.id)
        ).all()
        lots = session.scalars(
            select(CurrentTaxLot)
            .where(CurrentTaxLot.account_id == account.id)
            .order_by(CurrentTaxLot.id)
        ).all()
        if (
            current_generation != baseline.current_generation
            or current_revision != baseline.cache_revision
            or _portfolio_fingerprint(positions, lots) != baseline.portfolio_fingerprint
        ):
            raise AppError(
                "stale_lot_cache_refresh",
                "Portfolio state changed while broker positions and lots were being fetched",
                status_code=409,
            )

        generation = current_generation + 1
        session.execute(delete(CurrentTaxLot).where(CurrentTaxLot.account_id == account.id))
        session.execute(delete(CurrentPosition).where(CurrentPosition.account_id == account.id))
        security_by_ticker: dict[str, Security] = {}
        for position in portfolio.positions:
            value = position.position
            security = _security_for_ticker(
                session,
                value.ticker,
                value.asset_type,
                is_completion_etf=value.is_completion_etf,
                cusip=value.cusip,
                isin=value.isin,
            )
            security_by_ticker[value.ticker] = security
            session.add(
                CurrentPosition(
                    account_id=account.id,
                    security_id=security.id,
                    shares=value.shares,
                    market_value_usd=value.market_value_usd,
                    sync_generation=generation,
                    as_of=portfolio.as_of,
                    broker_position_id=position.broker_position_id,
                    broker_product_id=position.broker_product_id,
                )
            )
        session.flush()
        for item in portfolio.lots:
            record = item.record
            lot = record.lot
            security = security_by_ticker[record.ticker]
            session.add(
                CurrentTaxLot(
                    account_id=account.id,
                    broker_lot_id=record.broker_lot_id,
                    security_id=security.id,
                    acquired_date=lot.acquired_date,
                    shares=record.remaining_shares,
                    available_shares=record.available_shares,
                    adjusted_unit_basis_usd=lot.adjusted_unit_basis_usd,
                    broker_wash_adjustment_usd=lot.broker_wash_adjustment_usd,
                    source=lot.source,
                    as_of=portfolio.as_of,
                    quality_flags=lot.quality_flags,
                    fractional_cleanup_unsupported=(
                        record.available_shares != record.available_shares.to_integral_value()
                    ),
                    sync_generation=generation,
                    broker_total_cost_usd=record.total_cost_usd,
                    broker_total_cost_source_usd=record.total_cost_source,
                    reserved_shares=record.reserved_shares,
                    broker_acquired_date_source=item.acquired_date_source,
                )
            )
        if sync_state is None:
            sync_state = SyncState(
                id=1,
                current_generation=generation,
                coverage={"positions": True, "lots": True},
                complete=False,
            )
            session.add(sync_state)
        else:
            coverage = dict(sync_state.coverage) if isinstance(sync_state.coverage, dict) else {}
            coverage["positions"] = True
            coverage["lots"] = True
            sync_state.current_generation = generation
            sync_state.coverage = coverage
            sync_state.complete = False
        if cache_state is None:
            cache_state = LotCacheState(id=1, revision=0)
            session.add(cache_state)
        cache_state.revision = current_revision + 1
        cache_state.source_generation = generation
        cache_state.source_as_of = portfolio.as_of
        cache_state.cached_at = cached_at
        if cache_state.last_attempted_at is None or attempted_at >= cache_state.last_attempted_at:
            cache_state.last_attempted_at = attempted_at
            cache_state.last_error_code = None
            cache_state.last_error_summary = None
        if publication_hook is not None:
            publication_hook()


def _record_failure(
    factory: sessionmaker[Session],
    *,
    account_id_key: str,
    attempted_at: datetime,
    code: str,
    summary: str,
) -> None:
    try:
        with factory.begin() as session:
            session.connection(execution_options={"sqlite_begin_mode": "IMMEDIATE"})
            account = session.get(Account, 1)
            if account is None or account.broker_account_id_key != account_id_key:
                return
            cache_state = session.get(LotCacheState, 1)
            if cache_state is None:
                cache_state = LotCacheState(id=1, revision=0)
                session.add(cache_state)
            if (
                cache_state.last_attempted_at is None
                or attempted_at >= cache_state.last_attempted_at
            ):
                cache_state.last_attempted_at = attempted_at
                cache_state.last_error_code = _safe_error_code(code)
                cache_state.last_error_summary = summary[:500]
    except SQLAlchemyError:
        # A diagnostic write must never replace the original read/publication failure.
        return


def _portfolio_fingerprint(
    positions: Sequence[CurrentPosition], lots: Sequence[CurrentTaxLot]
) -> str:
    def position_row(row: CurrentPosition) -> dict[str, object]:
        return {
            "id": row.id,
            "security_id": row.security_id,
            "shares": canonical_decimal(row.shares),
            "market_value_usd": canonical_decimal(row.market_value_usd),
            "sync_generation": row.sync_generation,
            "as_of": row.as_of.isoformat(),
            "broker_position_id": row.broker_position_id,
            "broker_product_id": row.broker_product_id,
        }

    def lot_row(row: CurrentTaxLot) -> dict[str, object]:
        return {
            "id": row.id,
            "broker_lot_id": row.broker_lot_id,
            "security_id": row.security_id,
            "acquired_date": row.acquired_date.isoformat(),
            "shares": canonical_decimal(row.shares),
            "available_shares": canonical_decimal(row.available_shares),
            "adjusted_unit_basis_usd": canonical_decimal(row.adjusted_unit_basis_usd),
            "broker_wash_adjustment_usd": (
                canonical_decimal(row.broker_wash_adjustment_usd)
                if row.broker_wash_adjustment_usd is not None
                else None
            ),
            "source": row.source,
            "as_of": row.as_of.isoformat(),
            "quality_flags": row.quality_flags,
            "fractional_cleanup_unsupported": row.fractional_cleanup_unsupported,
            "sync_generation": row.sync_generation,
            "broker_total_cost_usd": (
                canonical_decimal(row.broker_total_cost_usd)
                if row.broker_total_cost_usd is not None
                else None
            ),
            "broker_total_cost_source_usd": (
                canonical_decimal(row.broker_total_cost_source_usd)
                if row.broker_total_cost_source_usd is not None
                else None
            ),
            "reserved_shares": (
                canonical_decimal(row.reserved_shares) if row.reserved_shares is not None else None
            ),
            "broker_acquired_date_source": row.broker_acquired_date_source,
        }

    encoded = json.dumps(
        {
            "positions": [position_row(row) for row in positions],
            "lots": [lot_row(row) for row in lots],
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _encode_product_id(value: object) -> str | None:
    if value is None:
        return None

    def normalize(item: object) -> object:
        if item is None or isinstance(item, (str, bool, int)):
            return item
        if isinstance(item, Decimal):
            if not item.is_finite():
                raise _malformed_payload()
            return {"$decimal": str(item)}
        if isinstance(item, Mapping):
            if any(not isinstance(key, str) for key in item):
                raise _malformed_payload()
            return {key: normalize(item[key]) for key in sorted(item)}
        if isinstance(item, (list, tuple)):
            return [normalize(value) for value in item]
        raise _malformed_payload()

    if isinstance(value, (bool, float)):
        raise _malformed_payload()
    return json.dumps(normalize(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _encode_acquired_date_source(value: Decimal | int | str) -> str:
    if isinstance(value, bool) or not isinstance(value, (Decimal, int, str)):
        raise _malformed_payload()
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise _malformed_payload()
        tagged: dict[str, str] = {"type": "decimal", "value": str(value)}
    elif isinstance(value, int):
        tagged = {"type": "integer", "value": str(value)}
    else:
        tagged = {"type": "string", "value": value}
    return json.dumps(tagged, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _acquired_date_from_source(value: Decimal | int | str) -> date:
    if isinstance(value, bool) or not isinstance(value, (Decimal, int, str)):
        raise _malformed_payload()
    try:
        milliseconds = value if isinstance(value, Decimal) else Decimal(value)
        if not milliseconds.is_finite() or milliseconds != milliseconds.to_integral_value():
            raise _malformed_payload()
        return (_UTC_EPOCH + timedelta(milliseconds=int(milliseconds))).astimezone(_EASTERN).date()
    except (ArithmeticError, TypeError, ValueError) as exc:
        raise _malformed_payload() from exc


def _valid_identifier(value: object, *, maximum: int) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= maximum


def _finite(value: object) -> bool:
    return isinstance(value, Decimal) and value.is_finite()


def _malformed_payload() -> AppError:
    return AppError(
        "malformed_lot_cache_payload",
        "Broker portfolio and exact lots could not be validated",
        status_code=422,
    )


def _safe_error_code(value: object) -> str:
    if isinstance(value, str) and _ERROR_CODE.fullmatch(value):
        return value
    return "lot_cache_refresh_failed"


def _safe_status_code(value: object) -> int:
    return value if isinstance(value, int) and 400 <= value <= 599 else 502
