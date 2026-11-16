from __future__ import annotations

import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path
from threading import Barrier
from typing import Literal, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.broker.etrade_read import (
    EtradeAccountCandidate,
    EtradeLotRecord,
    EtradePortfolioWithLots,
    EtradePositionRecord,
)
from app.broker.fake import FakeBroker
from app.db.migrate import upgrade_database
from app.db.models import (
    Account,
    BrokerTransaction,
    CurrentPosition,
    CurrentQuote,
    CurrentTaxLot,
    LotCacheState,
    PolicyRevision,
    Security,
    SecurityExposure,
    SyncState,
)
from app.db.session import create_database_engine, make_session_factory
from app.main import create_app
from app.schemas import LotInput, PositionInput
from app.services.demo_optimizer import _active_policy, _frozen_input
from app.services.errors import AppError
from app.services.financial_input_loader import load_financial_inputs
from app.services.lot_cache import (
    PortfolioLotCacheStatus,
    get_lot_cache_status,
    refresh_portfolio_lots,
)
from app.services.sync import sync_portfolio

_ACCOUNT_KEY = "DEMO-ONLY-ACCOUNT"
_AS_OF = datetime(2026, 11, 20, 14, 30, tzinfo=UTC)
_UTC_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class _Reader:
    def __init__(
        self,
        result: object,
        *,
        error: Exception | None = None,
        on_fetch: Callable[[], None] | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.on_fetch = on_fetch
        self.calls = 0
        self.bound_account_keys: list[str | None] = []

    def fetch_portfolio_with_lots(
        self, *, previously_bound_account_id_key: str | None = None
    ) -> EtradePortfolioWithLots:
        self.calls += 1
        self.bound_account_keys.append(previously_bound_account_id_key)
        if self.on_fetch is not None:
            self.on_fetch()
        if self.error is not None:
            raise self.error
        return cast(EtradePortfolioWithLots, self.result)


def _position(
    ticker: str,
    shares: str,
    *,
    position_id: str | None = None,
    asset_type: str = "EQUITY",
    market_value: str = "250.25",
    product_id: str | int | Decimal | dict[str, object] | None = None,
) -> EtradePositionRecord:
    return EtradePositionRecord(
        broker_position_id=position_id or f"POS-{ticker}",
        broker_product_id=product_id,
        position=PositionInput(
            ticker=ticker,
            asset_type=cast(Literal["EQUITY", "ETF"], asset_type),
            shares=Decimal(shares),
            market_value_usd=Decimal(market_value),
            is_completion_etf=ticker in {"VB", "VXF"},
        ),
    )


def _source_milliseconds(acquired: date) -> int:
    instant = datetime.combine(acquired, time(17), tzinfo=UTC)
    elapsed = instant - _UTC_EPOCH
    return (elapsed.days * 86_400 + elapsed.seconds) * 1000 + elapsed.microseconds // 1000


def _lot(
    ticker: str,
    position_id: str,
    lot_id: str,
    shares: str,
    total_cost: str,
    *,
    available: str | None = None,
    acquired: date = date(2025, 1, 10),
    acquired_source: Decimal | int | str | None = None,
    source_as_of: datetime = _AS_OF,
) -> EtradeLotRecord:
    remaining = Decimal(shares)
    available_shares = Decimal(available if available is not None else shares)
    cost = Decimal(total_cost)
    unit_basis = cost / remaining
    source_value = (
        acquired_source if acquired_source is not None else _source_milliseconds(acquired)
    )
    lot = LotInput(
        ticker=ticker,
        broker_lot_id=lot_id,
        acquired_date=acquired,
        shares=remaining,
        available_shares=available_shares,
        adjusted_unit_basis_usd=unit_basis,
        source="ETRADE",
        as_of=source_as_of,
    )
    return EtradeLotRecord(
        broker_position_id=position_id,
        broker_lot_id=lot_id,
        ticker=ticker,
        remaining_shares=remaining,
        available_shares=available_shares,
        reserved_shares=remaining - available_shares,
        total_cost_usd=cost,
        total_cost_source=cost,
        acquired_date_source=source_value,
        lot=lot,
    )


def _portfolio(
    positions: tuple[EtradePositionRecord, ...],
    lots: tuple[EtradeLotRecord, ...],
    *,
    as_of: datetime = _AS_OF,
    account_key: str = _ACCOUNT_KEY,
) -> EtradePortfolioWithLots:
    return EtradePortfolioWithLots(
        account=EtradeAccountCandidate(
            account_id_key=account_key,
            display_name="Cached Brokerage",
            account_type="BROKERAGE",
            tax_treatment="TAXABLE",
        ),
        as_of=as_of,
        positions=positions,
        lots=lots,
    )


def _one_position(
    ticker: str = "CACHE",
    shares: str = "1.25",
    *,
    total_cost: str = "125.125",
    available: str = "0",
    position_id: str | None = None,
    lot_id: str | None = None,
    acquired_source: Decimal | int | str | None = None,
    as_of: datetime = _AS_OF,
) -> EtradePortfolioWithLots:
    broker_position_id = position_id or f"POS-{ticker}"
    position = _position(
        ticker,
        shares,
        position_id=broker_position_id,
        market_value="300.75",
        product_id={"typeCode": "EQUITY", "opaqueId": Decimal("9.2500")},
    )
    lot = _lot(
        ticker,
        broker_position_id,
        lot_id or f"LOT-{ticker}",
        shares,
        total_cost,
        available=available,
        acquired_source=acquired_source,
        source_as_of=as_of,
    )
    return _portfolio((position,), (lot,), as_of=as_of)


def _seed_database(database_url: str) -> tuple[Engine, sessionmaker[Session]]:
    engine = create_database_engine(database_url)
    upgrade_database(engine)
    factory = make_session_factory(engine)
    sync_portfolio(factory, FakeBroker(), correlation_id="lot-cache-seed")
    return engine, factory


def _financial_snapshot(factory: sessionmaker[Session]) -> tuple[object, ...]:
    with factory() as session:
        account = session.get(Account, 1)
        state = session.get(SyncState, 1)
        cache = session.get(LotCacheState, 1)
        positions = tuple(
            (
                ticker,
                row.shares,
                row.market_value_usd,
                row.sync_generation,
                row.as_of,
                row.broker_position_id,
                row.broker_product_id,
            )
            for ticker, row in session.execute(
                select(Security.ticker, CurrentPosition).join(CurrentPosition)
            ).all()
        )
        lots = tuple(
            (
                row.broker_lot_id,
                row.security_id,
                row.acquired_date,
                row.shares,
                row.available_shares,
                row.adjusted_unit_basis_usd,
                row.sync_generation,
                row.as_of,
                row.broker_total_cost_usd,
                row.broker_total_cost_source_usd,
                row.reserved_shares,
                row.broker_acquired_date_source,
            )
            for row in session.scalars(select(CurrentTaxLot).order_by(CurrentTaxLot.broker_lot_id))
        )
        quotes = tuple(
            (row.security_id, row.bid_usd, row.ask_usd, row.last_usd, row.source, row.as_of)
            for row in session.scalars(select(CurrentQuote).order_by(CurrentQuote.security_id))
        )
        transactions = tuple(
            (row.broker_transaction_key, row.transaction_time, row.shares, row.amount_usd)
            for row in session.scalars(
                select(BrokerTransaction).order_by(BrokerTransaction.broker_transaction_key)
            )
        )
        exposures = tuple(
            (row.security_id, row.dimension, row.exposure_key, row.weight, row.as_of_date)
            for row in session.scalars(select(SecurityExposure).order_by(SecurityExposure.id))
        )
        return (
            None
            if account is None
            else (
                account.broker_account_id_key,
                account.cash_usd,
                account.settled_buying_power_usd,
                account.as_of,
                account.display_name,
            ),
            None
            if state is None
            else (
                state.current_generation,
                state.started_at,
                state.completed_at,
                state.coverage,
                state.complete,
            ),
            positions,
            lots,
            quotes,
            transactions,
            exposures,
            None
            if cache is None
            else (
                cache.revision,
                cache.source_generation,
                cache.source_as_of,
                cache.cached_at,
            ),
        )


def _assert_status_current(status: PortfolioLotCacheStatus) -> None:
    assert status.freshness == "current"
    assert status.quantity_coverage_complete
    assert status.covered_position_count == status.position_count
    assert status.source_generation == status.current_generation
    assert status.source_as_of is not None
    assert status.cached_at is not None


def test_real_sqlite_refresh_restart_preserves_exact_broker_lot_metadata(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'lot-cache-restart.sqlite3'}"
    engine, factory = _seed_database(database_url)
    restart_engine = None
    try:
        with factory() as session:
            legacy_position = session.scalar(select(CurrentPosition))
            legacy_lot = session.scalar(select(CurrentTaxLot))
            assert legacy_position is not None
            assert legacy_position.broker_position_id is None
            assert legacy_lot is not None
            assert legacy_lot.broker_total_cost_usd is None
            assert get_lot_cache_status(session).freshness == "unknown"
            quote_before = session.scalar(select(CurrentQuote))
            account_before = session.get(Account, 1)
            assert quote_before is not None
            assert account_before is not None
            quote_timestamp = quote_before.as_of
            account_as_of = account_before.as_of
            cash_before = account_before.cash_usd

        source_ms = _source_milliseconds(date(2025, 1, 10))
        portfolio = _one_position(
            acquired_source=source_ms,
            as_of=datetime(2026, 11, 19, 22, 15, tzinfo=UTC),
        )
        reader = _Reader(portfolio)
        status = refresh_portfolio_lots(factory, reader, correlation_id="lot-cache-success")
        _assert_status_current(status)
        assert reader.calls == 1
        assert reader.bound_account_keys == [_ACCOUNT_KEY]
        assert status.position_count == 1
        assert status.lot_count == 1

        with factory() as session:
            position = session.scalar(
                select(CurrentPosition).join(Security).where(Security.ticker == "CACHE")
            )
            lot = session.scalar(
                select(CurrentTaxLot).where(CurrentTaxLot.broker_lot_id == "LOT-CACHE")
            )
            account = session.get(Account, 1)
            quote = session.scalar(select(CurrentQuote))
            state = session.get(SyncState, 1)
            assert position is not None
            assert lot is not None
            assert account is not None
            assert quote is not None
            assert state is not None
            assert position.broker_position_id == "POS-CACHE"
            assert position.broker_product_id == (
                '{"opaqueId":{"$decimal":"9.2500"},"typeCode":"EQUITY"}'
            )
            assert position.shares == Decimal("1.25")
            assert position.sync_generation == status.current_generation
            assert lot.shares == Decimal("1.25")
            assert lot.available_shares == 0
            assert lot.reserved_shares == Decimal("1.25")
            assert lot.adjusted_unit_basis_usd == Decimal("100.1")
            assert lot.broker_total_cost_usd == Decimal("125.125")
            assert lot.broker_total_cost_source_usd == Decimal("125.125")
            assert lot.broker_acquired_date_source == json.dumps(
                {"type": "integer", "value": str(source_ms)},
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            )
            assert lot.acquired_date == date(2025, 1, 10)
            assert lot.as_of == portfolio.as_of
            assert account.cash_usd == cash_before
            assert account.as_of == account_as_of
            assert quote.as_of == quote_timestamp
            assert state.complete is False
            assert state.completed_at is not None
            assert state.coverage["positions"] is True
            assert state.coverage["lots"] is True

        engine.dispose()
        restart_engine = create_database_engine(database_url)
        upgrade_database(restart_engine)
        restarted_factory = make_session_factory(restart_engine)
        with restarted_factory() as session:
            restarted = get_lot_cache_status(session)
            _assert_status_current(restarted)
            position = session.scalar(
                select(CurrentPosition).join(Security).where(Security.ticker == "CACHE")
            )
            lot = session.scalar(
                select(CurrentTaxLot).where(CurrentTaxLot.broker_lot_id == "LOT-CACHE")
            )
            assert position is not None
            assert position.broker_product_id is not None
            assert lot is not None
            assert lot.broker_total_cost_usd == Decimal("125.125")
            assert lot.reserved_shares == Decimal("1.25")
            assert lot.broker_acquired_date_source is not None
    finally:
        engine.dispose()
        if restart_engine is not None:
            restart_engine.dispose()


def test_refresh_replaces_changed_new_removed_and_empty_position_sets(tmp_path: Path) -> None:
    engine, factory = _seed_database(f"sqlite:///{tmp_path / 'lot-cache-replace.sqlite3'}")
    try:
        changed = _position("AAPL", "2", position_id="AAPL-POS", market_value="410")
        added = _position("NEW", "0.5", position_id="NEW-POS", market_value="90")
        portfolio = _portfolio(
            (changed, added),
            (
                _lot("AAPL", "AAPL-POS", "AAPL-NEW-LOT", "2", "300", available="1"),
                _lot("NEW", "NEW-POS", "NEW-LOT", "0.5", "45", available="0.5"),
            ),
        )
        reader = _Reader(portfolio)
        status = refresh_portfolio_lots(factory, reader, correlation_id="replace-one")
        _assert_status_current(status)
        with factory() as session:
            rows = session.execute(
                select(Security.ticker, CurrentPosition.shares).join(CurrentPosition)
            ).all()
            lots = session.scalars(
                select(CurrentTaxLot).order_by(CurrentTaxLot.broker_lot_id)
            ).all()
            assert dict(rows) == {"AAPL": Decimal(2), "NEW": Decimal("0.5")}
            assert {lot.broker_lot_id for lot in lots} == {"AAPL-NEW-LOT", "NEW-LOT"}
            sync_state = session.get(SyncState, 1)
            assert sync_state is not None
            assert sync_state.complete is False

        reader.result = _portfolio((), ())
        empty_status = refresh_portfolio_lots(factory, reader, correlation_id="replace-empty")
        _assert_status_current(empty_status)
        assert empty_status.position_count == 0
        assert empty_status.covered_position_count == 0
        assert empty_status.lot_count == 0
        with factory() as session:
            assert session.scalar(select(CurrentPosition.id)) is None
            assert session.scalar(select(CurrentTaxLot.id)) is None
            assert session.get(Account, 1) is not None
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    [
        ("fetch", "lot_cache_read_failed"),
        ("malformed", "malformed_lot_cache_payload"),
        ("reconciliation", "incomplete_lots"),
        ("publication", "lot_cache_publish_failed"),
    ],
)
def test_refresh_failures_retain_financial_rows_and_last_success(
    tmp_path: Path, failure: str, expected_code: str
) -> None:
    engine, factory = _seed_database(
        f"sqlite:///{tmp_path / f'lot-cache-failure-{failure}.sqlite3'}"
    )
    try:
        initial = _Reader(_one_position())
        initial_status = refresh_portfolio_lots(factory, initial, correlation_id="initial-cache")
        before = _financial_snapshot(factory)
        assert before[-1] is not None
        if failure == "fetch":
            reader = _Reader(
                _one_position(), error=RuntimeError("private_token_must_not_be_persisted")
            )
            publication_hook = None
        elif failure == "malformed":
            reader = _Reader(object())
            publication_hook = None
        elif failure == "reconciliation":
            position = _position("CACHE", "1.25", position_id="POS-CACHE")
            wrong_lot = _lot("CACHE", "POS-CACHE", "LOT-CACHE", "1", "100")
            reader = _Reader(_portfolio((position,), (wrong_lot,)))
            publication_hook = None
        else:
            reader = _Reader(_one_position(shares="2", total_cost="250", available="1"))

            def fail_publication() -> None:
                raise RuntimeError("injected publication failure")

            publication_hook = fail_publication

        with pytest.raises(AppError) as error:
            refresh_portfolio_lots(
                factory,
                reader,
                correlation_id=f"failure-{failure}",
                publication_hook=publication_hook,
            )
        assert error.value.code == expected_code
        after = _financial_snapshot(factory)
        assert after[:-1] == before[:-1]
        assert after[-1] == before[-1]
        with factory() as session:
            status = get_lot_cache_status(session)
            assert status.cache_revision == initial_status.cache_revision
            assert status.source_generation == initial_status.source_generation
            assert status.source_as_of == initial_status.source_as_of
            assert status.cached_at == initial_status.cached_at
            assert status.last_error_code == expected_code
            assert status.last_error_summary is not None
            assert "private_token" not in status.last_error_summary
            assert status.freshness == "current"
    finally:
        engine.dispose()


def test_refresh_commit_failure_rolls_back_and_records_sanitized_attempt(tmp_path: Path) -> None:
    engine, factory = _seed_database(f"sqlite:///{tmp_path / 'lot-cache-commit-failure.sqlite3'}")
    armed = {"fail": False}

    def fail_commit(session: Session) -> None:
        if armed["fail"] and session.get_bind() is engine:
            armed["fail"] = False
            raise RuntimeError("injected commit failure")

    try:
        first = refresh_portfolio_lots(
            factory, _Reader(_one_position()), correlation_id="commit-baseline"
        )
        before = _financial_snapshot(factory)
        event.listen(Session, "before_commit", fail_commit)
        reader = _Reader(_one_position(shares="2", total_cost="250", available="1"))

        def arm_commit_failure() -> None:
            armed["fail"] = True

        with pytest.raises(AppError) as error:
            refresh_portfolio_lots(
                factory,
                reader,
                correlation_id="commit-failure",
                publication_hook=arm_commit_failure,
            )
        assert error.value.code == "lot_cache_publish_failed"
        assert _financial_snapshot(factory)[:-1] == before[:-1]
        assert _financial_snapshot(factory)[-1] == before[-1]
        with factory() as session:
            status = get_lot_cache_status(session)
            assert status.cache_revision == first.cache_revision
            assert status.cached_at == first.cached_at
            assert status.last_error_code == "lot_cache_publish_failed"
    finally:
        event.remove(Session, "before_commit", fail_commit)
        engine.dispose()


def _refresh_outcome(factory: sessionmaker[Session], reader: _Reader, correlation_id: str) -> str:
    try:
        refresh_portfolio_lots(factory, reader, correlation_id=correlation_id)
    except AppError as exc:
        return exc.code
    return "published"


def test_competing_refreshes_publish_one_generation_only(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'lot-cache-competing-refresh.sqlite3'}"
    engine_a, factory_a = _seed_database(database_url)
    engine_b = create_database_engine(database_url)
    factory_b = make_session_factory(engine_b)
    barrier = Barrier(2)

    def wait_for_both_reads() -> None:
        barrier.wait(timeout=10)

    try:
        result = _one_position()
        first_reader = _Reader(result, on_fetch=wait_for_both_reads)
        second_reader = _Reader(result, on_fetch=wait_for_both_reads)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(_refresh_outcome, factory_a, first_reader, "parallel-one")
            second = pool.submit(_refresh_outcome, factory_b, second_reader, "parallel-two")
            outcomes = [first.result(timeout=15), second.result(timeout=15)]
        assert sorted(outcomes) == ["published", "stale_lot_cache_refresh"]
        with factory_a() as session:
            state = session.get(SyncState, 1)
            status = get_lot_cache_status(session)
            assert state is not None
            assert state.current_generation == 2
            assert status.freshness == "current"
            assert status.cache_revision == 1
    finally:
        engine_a.dispose()
        engine_b.dispose()


def test_full_sync_and_manual_quantity_changes_invalidate_or_reject_cache(tmp_path: Path) -> None:
    engine, factory = _seed_database(f"sqlite:///{tmp_path / 'lot-cache-races.sqlite3'}")
    try:
        with TestClient(
            create_app(engine=engine, seed_demo_data=True), base_url="http://localhost:8000"
        ):
            pass

        def perform_full_sync() -> None:
            sync_portfolio(factory, FakeBroker(), correlation_id="full-sync-during-fetch")

        reader = _Reader(_one_position(), on_fetch=perform_full_sync)
        with pytest.raises(AppError, match="Portfolio state changed") as stale:
            refresh_portfolio_lots(factory, reader, correlation_id="stale-after-full-sync")
        assert stale.value.code == "stale_lot_cache_refresh"
        with factory() as session:
            status = get_lot_cache_status(session)
            assert status.freshness == "unknown"
            position = session.scalar(select(CurrentPosition))
            assert position is not None
            assert position.broker_position_id is None

        portfolio = _portfolio(
            (
                _position("AAPL", "10", position_id="AAPL-POS", market_value="1800"),
                _position("VB", "2", position_id="VB-POS", asset_type="ETF", market_value="400"),
            ),
            (
                _lot("AAPL", "AAPL-POS", "AAPL-LOT", "10", "1500", available="10"),
                _lot("VB", "VB-POS", "VB-LOT", "2", "350", available="2"),
            ),
        )
        status = refresh_portfolio_lots(
            factory, _Reader(portfolio), correlation_id="fresh-before-edit"
        )
        assert status.freshness == "current"
        with factory.begin() as session:
            aapl_position = session.scalar(
                select(CurrentPosition).join(Security).where(Security.ticker == "AAPL")
            )
            assert aapl_position is not None
            aapl_position.shares = Decimal(11)
        with factory() as session:
            stale_status = get_lot_cache_status(session)
            assert stale_status.freshness == "stale"
            assert stale_status.quantity_coverage_complete is False
            assert stale_status.covered_position_count == 1

        # A complete legacy/DEMO sync restores its old behavior but clears explicit-cache provenance.
        sync_portfolio(factory, FakeBroker(), correlation_id="restore-full-demo-sync")
        with factory.begin() as session:
            aapl_position = session.scalar(
                select(CurrentPosition).join(Security).where(Security.ticker == "AAPL")
            )
            assert aapl_position is not None
            aapl_position.shares = Decimal(11)
        with factory() as session:
            account = session.get(Account, 1)
            sync_state = session.get(SyncState, 1)
            assert account is not None
            assert sync_state is not None
            assert sync_state.complete
            unknown_status = get_lot_cache_status(session)
            assert unknown_status.freshness == "unknown"
            assert unknown_status.quantity_coverage_complete is False
            policy = _active_policy(session)
            with pytest.raises(AppError) as optimizer_error:
                _frozen_input(
                    session,
                    account,
                    sync_state,
                    policy,
                    date(2026, 11, 5),
                )
            assert optimizer_error.value.code == "incomplete_lots"
    finally:
        engine.dispose()


def test_status_financial_reads_and_quote_updates_do_not_fetch_details(tmp_path: Path) -> None:
    app: FastAPI = create_app(
        database_url=f"sqlite:///{tmp_path / 'lot-cache-no-read-fetch.sqlite3'}",
        seed_demo_data=True,
    )
    reader = _Reader(
        _portfolio(
            (
                _position("AAPL", "10", position_id="AAPL-POS", market_value="1800"),
                _position("VB", "2", position_id="VB-POS", asset_type="ETF", market_value="400"),
            ),
            (
                _lot("AAPL", "AAPL-POS", "AAPL-LOT", "10", "1500", available="10"),
                _lot("VB", "VB-POS", "VB-LOT", "2", "350", available="2"),
            ),
        )
    )
    with TestClient(app, base_url="http://localhost:8000"):
        factory = app.state.session_factory
        refresh_portfolio_lots(factory, reader, correlation_id="one-explicit-read")
        calls_after_refresh = reader.calls
        with factory() as session:
            status = get_lot_cache_status(session)
            assert status.freshness == "current"
            account = session.get(Account, 1)
            sync_state = session.get(SyncState, 1)
            assert account is not None
            assert sync_state is not None
            policy = session.scalar(select(PolicyRevision).where(PolicyRevision.status == "ACTIVE"))
            assert policy is not None
            inputs = load_financial_inputs(
                session,
                account,
                sync_state,
                policy,
                date(2026, 11, 5),
            )
            assert len(inputs.positions) == 2
            assert len(inputs.lots) == 2
        with factory.begin() as session:
            quote = session.scalar(select(CurrentQuote))
            assert quote is not None
            quote.last_usd = Decimal("123.45")
            quote.as_of = datetime(2026, 11, 20, 15, 0, tzinfo=UTC)
        with factory() as session:
            assert get_lot_cache_status(session).freshness == "current"
        assert reader.calls == calls_after_refresh == 1
