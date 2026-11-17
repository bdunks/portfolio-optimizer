from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.broker.protocol import ReadOnlyBroker
from app.db.models import (
    Account,
    ActivityEvent,
    BrokerTransaction,
    CurrentPosition,
    CurrentQuote,
    CurrentTaxLot,
    LotCacheState,
    Security,
    SecurityExposure,
    SyncState,
)
from app.domain.decimal_math import exact_product, exact_sum
from app.schemas import BrokerSnapshot
from app.services.errors import AppError

REQUIRED_COVERAGE = ("positions", "lots", "transactions", "balances", "quotes")


@dataclass(frozen=True, slots=True)
class _PositionProvenance:
    broker_position_id: str
    broker_product_id: str | None
    as_of: datetime


@dataclass(frozen=True, slots=True)
class _LotProvenance:
    broker_total_cost_usd: Decimal
    broker_total_cost_source_usd: Decimal
    reserved_shares: Decimal
    broker_acquired_date_source: str


@dataclass(frozen=True, slots=True)
class _SnapshotProvenance:
    positions: dict[str, _PositionProvenance]
    lots: dict[str, _LotProvenance]


def _invalid_snapshot_metadata() -> AppError:
    return AppError(
        "invalid_sync_metadata",
        "Broker provenance does not match the reported positions and lots",
        status_code=422,
    )


def _validate_snapshot_metadata(snapshot: BrokerSnapshot) -> _SnapshotProvenance:
    """Validate and encode optional broker provenance before publication starts."""
    if not snapshot.broker_position_metadata and not snapshot.broker_lot_metadata:
        return _SnapshotProvenance(positions={}, lots={})
    if len(snapshot.broker_position_metadata) != len(snapshot.positions) or len(
        snapshot.broker_lot_metadata
    ) != len(snapshot.lots):
        raise _invalid_snapshot_metadata()

    # Reuse the explicit-refresh path's strict product/date encodings and source-date decoding.
    from app.services.lot_cache import (
        _acquired_date_from_source,
        _encode_acquired_date_source,
        _encode_product_id,
    )

    position_inputs = {position.ticker: position for position in snapshot.positions}
    positions: dict[str, _PositionProvenance] = {}
    seen_position_ids: set[str] = set()
    for metadata in snapshot.broker_position_metadata:
        if (
            metadata.ticker not in position_inputs
            or metadata.ticker in positions
            or not metadata.broker_position_id.strip()
            or metadata.broker_position_id in seen_position_ids
            or metadata.as_of.tzinfo is None
            or metadata.as_of.utcoffset() is None
        ):
            raise _invalid_snapshot_metadata()
        try:
            product_id = _encode_product_id(metadata.broker_product_id)
        except (AppError, ArithmeticError, TypeError, ValueError) as exc:
            raise _invalid_snapshot_metadata() from exc
        positions[metadata.ticker] = _PositionProvenance(
            broker_position_id=metadata.broker_position_id,
            broker_product_id=product_id,
            as_of=metadata.as_of.astimezone(UTC),
        )
        seen_position_ids.add(metadata.broker_position_id)
    if set(positions) != set(position_inputs):
        raise _invalid_snapshot_metadata()

    lot_inputs = {lot.broker_lot_id: lot for lot in snapshot.lots}
    lots: dict[str, _LotProvenance] = {}
    for metadata in snapshot.broker_lot_metadata:
        lot = lot_inputs.get(metadata.broker_lot_id)
        position = positions.get(metadata.ticker)
        if (
            lot is None
            or metadata.broker_lot_id in lots
            or metadata.ticker != lot.ticker
            or position is None
            or metadata.broker_position_id != position.broker_position_id
        ):
            raise _invalid_snapshot_metadata()
        try:
            expected_cost = exact_product(lot.shares, lot.adjusted_unit_basis_usd)
            expected_reserved = exact_sum((lot.shares, -lot.available_shares))
            acquired_date_source = _encode_acquired_date_source(metadata.acquired_date_source)
            acquired_date = _acquired_date_from_source(metadata.acquired_date_source)
        except (AppError, ArithmeticError, TypeError, ValueError) as exc:
            raise _invalid_snapshot_metadata() from exc
        if (
            not metadata.total_cost_usd.is_finite()
            or not metadata.total_cost_source.is_finite()
            or not metadata.reserved_shares.is_finite()
            or metadata.total_cost_usd < 0
            or metadata.total_cost_source != metadata.total_cost_usd
            or metadata.total_cost_usd != expected_cost
            or metadata.reserved_shares != expected_reserved
            or acquired_date != lot.acquired_date
        ):
            raise _invalid_snapshot_metadata()
        lots[metadata.broker_lot_id] = _LotProvenance(
            broker_total_cost_usd=metadata.total_cost_usd,
            broker_total_cost_source_usd=metadata.total_cost_source,
            reserved_shares=metadata.reserved_shares,
            broker_acquired_date_source=acquired_date_source,
        )
    if set(lots) != set(lot_inputs):
        raise _invalid_snapshot_metadata()
    return _SnapshotProvenance(positions=positions, lots=lots)


def validate_snapshot(snapshot: BrokerSnapshot) -> _SnapshotProvenance:
    """Validate a complete single-account payload before opening a publication transaction."""
    if not all(getattr(snapshot.coverage, key) for key in REQUIRED_COVERAGE):
        missing = [key for key in REQUIRED_COVERAGE if not getattr(snapshot.coverage, key)]
        raise AppError(
            "incomplete_sync",
            "Broker snapshot is incomplete; current state was not changed",
            status_code=422,
            details={"incomplete_sections": missing},
        )
    if snapshot.cash_usd < 0 or snapshot.settled_buying_power_usd < 0:
        raise AppError(
            "invalid_sync_payload", "Broker balances cannot be negative", status_code=422
        )

    positions = {position.ticker: position for position in snapshot.positions}
    if len(positions) != len(snapshot.positions):
        raise AppError(
            "duplicate_position", "Broker snapshot contains duplicate positions", status_code=422
        )
    lots_by_ticker: dict[str, list[Decimal]] = defaultdict(list)
    lot_ids = [lot.broker_lot_id for lot in snapshot.lots]
    if len(set(lot_ids)) != len(lot_ids):
        raise AppError(
            "duplicate_lot", "Broker snapshot contains duplicate broker lot IDs", status_code=422
        )
    for lot in snapshot.lots:
        if lot.ticker not in positions:
            raise AppError(
                "orphan_lot",
                "Every open lot must belong to a reported current position",
                status_code=422,
                details={"ticker": lot.ticker},
            )
        if not lot.broker_lot_id.strip() or lot.shares <= 0:
            raise AppError(
                "incomplete_lot",
                "Open lots require a broker ID and positive shares",
                status_code=422,
            )
        if lot.available_shares < 0 or lot.available_shares > lot.shares:
            raise AppError(
                "invalid_lot_quantity",
                "Lot available shares must be within its remaining quantity",
                status_code=422,
            )
        if lot.adjusted_unit_basis_usd < 0:
            raise AppError(
                "invalid_lot_basis", "Adjusted lot basis cannot be negative", status_code=422
            )
        lots_by_ticker[lot.ticker].append(lot.shares)

    for ticker, position in positions.items():
        if position.shares <= 0 or position.market_value_usd < 0:
            raise AppError(
                "invalid_position",
                "Positions require positive shares and nonnegative value",
                status_code=422,
            )
        if exact_sum(lots_by_ticker[ticker]) != position.shares:
            raise AppError(
                "incomplete_lots",
                "Reported open lots must exactly cover each current position",
                status_code=422,
                details={"ticker": ticker},
            )

    quote_tickers = [quote.ticker for quote in snapshot.quotes]
    if len(set(quote_tickers)) != len(quote_tickers):
        raise AppError(
            "duplicate_quote", "Broker snapshot contains duplicate quotes", status_code=422
        )
    quotes = {quote.ticker: quote for quote in snapshot.quotes}
    for ticker in positions:
        quote = quotes.get(ticker)
        if quote is None or quote.last_usd is None or quote.last_usd <= 0:
            raise AppError(
                "missing_quote",
                "Each held position requires a current positive last quote",
                status_code=422,
                details={"ticker": ticker},
            )
    for quote in snapshot.quotes:
        if any(
            value is not None and value <= 0
            for value in (quote.bid_usd, quote.ask_usd, quote.last_usd)
        ):
            raise AppError(
                "invalid_quote", "Quote prices must be positive when provided", status_code=422
            )
        if quote.bid_usd and quote.ask_usd and quote.bid_usd > quote.ask_usd:
            raise AppError("invalid_quote", "Quote bid cannot exceed ask", status_code=422)

    transaction_keys = [transaction.broker_transaction_key for transaction in snapshot.transactions]
    if len(set(transaction_keys)) != len(transaction_keys):
        raise AppError(
            "duplicate_transaction",
            "Broker snapshot contains duplicate transaction IDs",
            status_code=422,
        )
    if any(not key.strip() for key in transaction_keys):
        raise AppError(
            "incomplete_transaction",
            "Broker transactions require stable broker IDs",
            status_code=422,
        )

    exposure_keys = [
        (item.ticker, item.dimension, item.exposure_key, item.provider)
        for item in snapshot.exposures
    ]
    if len(set(exposure_keys)) != len(exposure_keys):
        raise AppError(
            "duplicate_exposure",
            "Look-through data contains duplicate exposure rows",
            status_code=422,
        )
    if any(item.weight < 0 for item in snapshot.exposures):
        raise AppError(
            "invalid_exposure", "Look-through weights cannot be negative", status_code=422
        )
    return _validate_snapshot_metadata(snapshot)


def _security_for_ticker(
    session: Session,
    ticker: str,
    asset_type: str,
    *,
    is_completion_etf: bool = False,
    cusip: str | None = None,
    isin: str | None = None,
) -> Security:
    security = session.scalar(select(Security).where(Security.ticker == ticker))
    if security is None:
        security = Security(
            ticker=ticker,
            asset_type=asset_type,
            is_completion_etf=is_completion_etf or ticker in {"VB", "VXF"},
            cusip=cusip,
            isin=isin,
        )
        session.add(security)
        session.flush()
    else:
        if security.asset_type != asset_type and ticker in {"VB", "VXF"}:
            raise AppError(
                "security_type_mismatch",
                "Broker security metadata conflicts with stored type",
                status_code=422,
            )
        security.is_completion_etf = (
            security.is_completion_etf or is_completion_etf or ticker in {"VB", "VXF"}
        )
        security.cusip = security.cusip or cusip
        security.isin = security.isin or isin
    return security


def _record_failure(
    factory: sessionmaker[Session],
    *,
    code: str,
    summary: str,
    correlation_id: str,
    started_at: datetime,
) -> None:
    with factory.begin() as session:
        session.connection(execution_options={"sqlite_begin_mode": "IMMEDIATE"})
        state = session.get(SyncState, 1)
        if state is None:
            state = SyncState(id=1, current_generation=0, coverage={}, complete=False)
            session.add(state)
        state.started_at = started_at
        state.last_error_code = code
        state.last_error_summary = summary[:500]
        session.add(
            ActivityEvent(
                id=str(uuid4()),
                created_at=datetime.now(UTC),
                event_type="sync",
                status="failed",
                correlation_id=correlation_id,
                details={"code": code, "message": summary[:300]},
            )
        )


def sync_portfolio(
    factory: sessionmaker[Session],
    broker: ReadOnlyBroker,
    *,
    correlation_id: str,
    publication_hook: Callable[[], None] | None = None,
) -> dict[str, object]:
    """Capture cache revision before fetching; validate outside SQL writes, then publish only if unchanged."""
    started_at = datetime.now(UTC)
    with factory() as session:
        cache_state = session.get(LotCacheState, 1)
        baseline_cache_revision = cache_state.revision if cache_state is not None else 0
    try:
        raw_snapshot = broker.fetch_snapshot()
        snapshot = BrokerSnapshot.model_validate(raw_snapshot)
        provenance = validate_snapshot(snapshot)
    except AppError as exc:
        _record_failure(
            factory,
            code=exc.code,
            summary=exc.message,
            correlation_id=correlation_id,
            started_at=started_at,
        )
        raise
    except ValidationError as exc:
        _record_failure(
            factory,
            code="malformed_sync_payload",
            summary="Broker snapshot is malformed; current state was not changed",
            correlation_id=correlation_id,
            started_at=started_at,
        )
        raise AppError(
            "malformed_sync_payload",
            "Broker snapshot is malformed; current state was not changed",
            status_code=422,
        ) from exc
    except Exception as exc:
        _record_failure(
            factory,
            code="broker_sync_failed",
            summary="Read-only broker snapshot could not be obtained or validated",
            correlation_id=correlation_id,
            started_at=started_at,
        )
        raise AppError(
            "broker_sync_failed",
            "Read-only broker snapshot could not be obtained",
            status_code=502,
        ) from exc

    try:
        with factory.begin() as session:
            session.connection(execution_options={"sqlite_begin_mode": "IMMEDIATE"})
            cache_state = session.get(LotCacheState, 1)
            current_cache_revision = cache_state.revision if cache_state is not None else 0
            if current_cache_revision != baseline_cache_revision:
                raise AppError(
                    "stale_sync_publication",
                    "Portfolio cache revision changed while broker data was being fetched; sync was not published",
                    status_code=409,
                )
            account = session.get(Account, 1)
            if account is not None and account.broker_account_id_key != snapshot.account_id_key:
                raise AppError(
                    "managed_account_mismatch",
                    "Sync payload does not match the single managed account",
                    status_code=409,
                )
            state = session.get(SyncState, 1)
            generation = (state.current_generation if state else 0) + 1

            coverage = snapshot.coverage.model_dump(mode="json")
            if not snapshot.exposures and state is not None and isinstance(state.coverage, dict):
                cached_lookthrough = state.coverage.get("lookthrough")
                if type(cached_lookthrough) is bool:
                    coverage["lookthrough"] = cached_lookthrough
            # All destructive changes are after payload validation and remain transaction-scoped.
            session.execute(delete(CurrentTaxLot))
            session.execute(delete(CurrentPosition))
            session.execute(delete(CurrentQuote))
            if publication_hook is not None:
                publication_hook()

            if account is None:
                account = Account(
                    id=1,
                    broker_account_id_key=snapshot.account_id_key,
                    display_name=snapshot.display_name,
                    account_type=snapshot.account_type,
                    tax_treatment=snapshot.tax_treatment,
                    cash_usd=snapshot.cash_usd,
                    settled_buying_power_usd=snapshot.settled_buying_power_usd,
                    source=snapshot.source,
                    as_of=snapshot.as_of,
                )
                session.add(account)
            else:
                account.display_name = snapshot.display_name
                account.account_type = snapshot.account_type
                account.tax_treatment = snapshot.tax_treatment
                account.cash_usd = snapshot.cash_usd
                account.settled_buying_power_usd = snapshot.settled_buying_power_usd
                account.source = snapshot.source
                account.as_of = snapshot.as_of
            session.flush()

            securities: dict[str, Security] = {}
            for position in snapshot.positions:
                security = _security_for_ticker(
                    session,
                    position.ticker,
                    position.asset_type,
                    is_completion_etf=position.is_completion_etf,
                    cusip=position.cusip,
                    isin=position.isin,
                )
                securities[position.ticker] = security
                position_provenance = provenance.positions.get(position.ticker)
                session.add(
                    CurrentPosition(
                        account_id=1,
                        security_id=security.id,
                        shares=position.shares,
                        market_value_usd=position.market_value_usd,
                        sync_generation=generation,
                        as_of=position_provenance.as_of
                        if position_provenance is not None
                        else snapshot.as_of,
                        broker_position_id=(
                            position_provenance.broker_position_id
                            if position_provenance is not None
                            else None
                        ),
                        broker_product_id=(
                            position_provenance.broker_product_id
                            if position_provenance is not None
                            else None
                        ),
                    )
                )
            for lot in snapshot.lots:
                security = securities[lot.ticker]
                lot_provenance = provenance.lots.get(lot.broker_lot_id)
                fractional = lot.available_shares != lot.available_shares.to_integral_value()
                session.add(
                    CurrentTaxLot(
                        account_id=1,
                        broker_lot_id=lot.broker_lot_id,
                        security_id=security.id,
                        acquired_date=lot.acquired_date,
                        shares=lot.shares,
                        available_shares=lot.available_shares,
                        adjusted_unit_basis_usd=lot.adjusted_unit_basis_usd,
                        broker_wash_adjustment_usd=lot.broker_wash_adjustment_usd,
                        source=lot.source,
                        as_of=lot.as_of,
                        quality_flags=lot.quality_flags,
                        fractional_cleanup_unsupported=fractional,
                        sync_generation=generation,
                        broker_total_cost_usd=(
                            lot_provenance.broker_total_cost_usd
                            if lot_provenance is not None
                            else None
                        ),
                        broker_total_cost_source_usd=(
                            lot_provenance.broker_total_cost_source_usd
                            if lot_provenance is not None
                            else None
                        ),
                        reserved_shares=(
                            lot_provenance.reserved_shares if lot_provenance is not None else None
                        ),
                        broker_acquired_date_source=(
                            lot_provenance.broker_acquired_date_source
                            if lot_provenance is not None
                            else None
                        ),
                    )
                )
            for quote in snapshot.quotes:
                security = securities.get(quote.ticker)
                if security is None:
                    security = _security_for_ticker(session, quote.ticker, "ETF")
                    securities[quote.ticker] = security
                session.add(
                    CurrentQuote(
                        security_id=security.id,
                        bid_usd=quote.bid_usd,
                        ask_usd=quote.ask_usd,
                        last_usd=quote.last_usd,
                        source=quote.source,
                        as_of=quote.as_of,
                        quality=quote.quality,
                        sync_generation=generation,
                    )
                )

            if snapshot.exposures:
                session.execute(delete(SecurityExposure))
                for exposure in snapshot.exposures:
                    security = securities.get(exposure.ticker) or _security_for_ticker(
                        session, exposure.ticker, "ETF"
                    )
                    securities[exposure.ticker] = security
                    session.add(
                        SecurityExposure(
                            security_id=security.id,
                            dimension=exposure.dimension,
                            exposure_key=exposure.exposure_key,
                            weight=exposure.weight,
                            provider=exposure.provider,
                            as_of_date=exposure.as_of_date,
                        )
                    )

            for transaction in snapshot.transactions:
                security = securities.get(transaction.ticker) or _security_for_ticker(
                    session, transaction.ticker, "EQUITY"
                )
                existing = session.scalar(
                    select(BrokerTransaction).where(
                        BrokerTransaction.broker_transaction_key
                        == transaction.broker_transaction_key
                    )
                )
                if existing is None:
                    existing = BrokerTransaction(
                        broker_transaction_key=transaction.broker_transaction_key,
                        account_id=1,
                        security_id=security.id,
                        transaction_kind=transaction.transaction_kind,
                        transaction_time=transaction.transaction_time,
                        trade_date=transaction.trade_date,
                        shares=transaction.shares,
                        amount_usd=transaction.amount_usd,
                        realized_pl_usd=transaction.realized_pl_usd,
                        is_acquisition=transaction.is_acquisition,
                        broker_lot_id=transaction.broker_lot_id,
                        source=transaction.source,
                    )
                    session.add(existing)
                else:
                    existing.security_id = security.id
                    existing.transaction_kind = transaction.transaction_kind
                    existing.transaction_time = transaction.transaction_time
                    existing.trade_date = transaction.trade_date
                    existing.shares = transaction.shares
                    existing.amount_usd = transaction.amount_usd
                    existing.realized_pl_usd = transaction.realized_pl_usd
                    existing.is_acquisition = transaction.is_acquisition
                    existing.broker_lot_id = transaction.broker_lot_id
                    existing.source = transaction.source

            if state is None:
                state = SyncState(id=1, current_generation=generation)
                session.add(state)
            state.current_generation = generation
            state.started_at = started_at
            state.completed_at = datetime.now(UTC)
            state.coverage = coverage
            state.complete = True
            state.last_error_code = None
            state.last_error_summary = None
            if cache_state is not None:
                cache_state.source_generation = None
                cache_state.source_as_of = None
                cache_state.cached_at = None
            session.add(
                ActivityEvent(
                    id=str(uuid4()),
                    created_at=datetime.now(UTC),
                    event_type="sync",
                    status="complete",
                    correlation_id=correlation_id,
                    details={
                        "generation": generation,
                        "source": snapshot.source,
                        "coverage": coverage,
                        "positions": len(snapshot.positions),
                        "lots": len(snapshot.lots),
                        "transactions": len(snapshot.transactions),
                    },
                )
            )
        return {
            "generation": generation,
            "status": "complete",
            "as_of": snapshot.as_of,
            "coverage": coverage,
            "account": snapshot.display_name,
            "demo": snapshot.source.upper() in {"DEMO", "FAKE"},
        }
    except AppError as exc:
        _record_failure(
            factory,
            code=exc.code,
            summary=exc.message,
            correlation_id=correlation_id,
            started_at=started_at,
        )
        raise
    except (SQLAlchemyError, RuntimeError, ValueError) as exc:
        _record_failure(
            factory,
            code="sync_publish_failed",
            summary="Validated broker data could not be published; prior state was retained",
            correlation_id=correlation_id,
            started_at=started_at,
        )
        raise AppError(
            "sync_publish_failed",
            "Validated broker data could not be published; prior state was retained",
            status_code=500,
        ) from exc
