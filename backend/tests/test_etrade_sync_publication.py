from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session, sessionmaker

from app.broker.fake import FakeBroker
from app.db.models import (
    Account,
    BrokerTransaction,
    CurrentPosition,
    CurrentQuote,
    CurrentTaxLot,
    Security,
    SecurityExposure,
    SyncState,
)
from app.db.session import create_database_engine, make_session_factory
from app.main import create_app
from app.schemas import BrokerSnapshot
from app.services.broker_snapshot import EtradeReadOnlyBroker
from app.services.financial_input_loader import load_financial_inputs
from tests.test_etrade_snapshot import (
    ACCOUNT_ID,
    ACCOUNT_KEY,
    HISTORY_END,
    HISTORY_START,
    NOW,
    StubTransport,
    _account,
    _adapter,
    _composer,
    _epoch_seconds,
    _http_responses,
    _lot,
    _position,
    _quote,
    _transaction,
)


def _successful_cycle(
    *,
    cash_usd: Decimal = Decimal("1234.567890123456789"),
    settled_cash_usd: Decimal = Decimal("987.654321098765432"),
    position_rows: Sequence[dict[str, object]] | None = None,
    lot_rows: Sequence[dict[str, object]] | None = None,
) -> list[requests.Response]:
    return _http_responses(
        position_rows=position_rows,
        lot_rows=lot_rows,
        transaction_rows=(_transaction(account_id=ACCOUNT_ID),),
        balance_cash_usd=cash_usd,
        balance_settled_cash_usd=settled_cash_usd,
        quote_rows=(_quote("AAA", timestamp=_epoch_seconds(NOW - timedelta(seconds=15))),),
    )


def _failure_cycle(kind: str) -> list[requests.Response | Exception]:
    quote = (_quote("AAA", timestamp=_epoch_seconds(NOW)),)
    if kind == "invalid_balance":
        responses: Sequence[requests.Response | Exception] = _http_responses(
            balance_source=-1, quote_rows=quote
        )
    elif kind == "foreign_balance":
        responses = _http_responses(
            accounts_by_section=(
                (_account(),),
                (_account(),),
                (_account(ACCOUNT_KEY, ACCOUNT_ID + 1),),
            ),
            quote_rows=quote,
        )
    elif kind == "lot_mismatch":
        responses = _http_responses(
            position_rows=(_position(shares=Decimal(2)),),
            lot_rows=(_lot(shares=Decimal(1)),),
            quote_rows=quote,
        )
    elif kind == "partial_page":
        responses = _http_responses(
            transaction_rows=(_transaction(account_id=ACCOUNT_ID),), quote_rows=quote
        )
        responses = (
            *responses[:4],
            requests.ConnectionError("synthetic transaction page failure"),
            *responses[5:],
        )
    elif kind == "incomplete_history":
        responses = _http_responses(
            transaction_rows=(_transaction(transaction_type="Option Assignment"),),
            quote_rows=quote,
        )
    elif kind == "missing_quote":
        responses = _http_responses(transaction_rows=(_transaction(account_id=ACCOUNT_ID),))
    elif kind == "stale_quote":
        responses = _http_responses(
            transaction_rows=(_transaction(account_id=ACCOUNT_ID),),
            quote_rows=(
                _quote("AAA", timestamp=_epoch_seconds(NOW - timedelta(minutes=15, seconds=1))),
            ),
        )
    elif kind == "metadata_mismatch":
        responses = _successful_cycle()
    else:
        raise AssertionError(f"unknown synthetic failure case: {kind}")
    return list(responses)


class _MutableSnapshotBroker:
    mode = "etrade"

    def __init__(self, composer: EtradeReadOnlyBroker) -> None:
        self.composer = composer
        self.mutate_lot_metadata = False

    def fetch_snapshot(self) -> BrokerSnapshot:
        snapshot = self.composer.fetch_snapshot()
        if not self.mutate_lot_metadata:
            return snapshot
        metadata = snapshot.broker_lot_metadata[0].model_copy(
            update={"reserved_shares": Decimal(0)}
        )
        return snapshot.model_copy(update={"broker_lot_metadata": [metadata]})


def _publication_app(
    tmp_path: Path,
    responses: Sequence[requests.Response | Exception],
    *,
    before_send: Callable[[requests.PreparedRequest], None] | None = None,
) -> tuple[FastAPI, Engine, sessionmaker[Session], StubTransport, _MutableSnapshotBroker]:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'etrade-sync.sqlite3'}")

    def assert_no_open_database_connection(request: requests.PreparedRequest) -> None:
        checked_out = getattr(engine.pool, "checkedout", None)
        assert callable(checked_out)
        assert checked_out() == 0, (
            f"database connection checked out during {request.method} {request.path_url}"
        )
        if before_send is not None:
            before_send(request)

    factory = make_session_factory(engine)
    adapter, transport = _adapter(responses, before_send=assert_no_open_database_connection)
    broker = _MutableSnapshotBroker(_composer(adapter, factory))
    app = create_app(engine=engine, broker=broker)
    return app, engine, factory, transport, broker


def _financial_signature(factory: sessionmaker[Session]) -> tuple[object, ...]:
    with factory() as session:
        account = session.get(Account, 1)
        state = session.get(SyncState, 1)
        securities = {row.id: row for row in session.scalars(select(Security)).all()}
        assert account is not None
        assert state is not None
        account_rows = (
            account.id,
            account.broker_account_id_key,
            account.display_name,
            account.cash_usd,
            account.settled_buying_power_usd,
            account.source,
            account.as_of,
        )
        positions = tuple(
            (
                row.id,
                securities[row.security_id].ticker,
                row.shares,
                row.market_value_usd,
                row.sync_generation,
                row.as_of,
                row.broker_position_id,
                row.broker_product_id,
            )
            for row in session.scalars(select(CurrentPosition).order_by(CurrentPosition.id)).all()
        )
        lots = tuple(
            (
                row.id,
                securities[row.security_id].ticker,
                row.broker_lot_id,
                row.acquired_date,
                row.shares,
                row.available_shares,
                row.adjusted_unit_basis_usd,
                row.as_of,
                row.sync_generation,
                row.broker_total_cost_usd,
                row.broker_total_cost_source_usd,
                row.reserved_shares,
                row.broker_acquired_date_source,
            )
            for row in session.scalars(select(CurrentTaxLot).order_by(CurrentTaxLot.id)).all()
        )
        quotes = tuple(
            (
                row.id,
                securities[row.security_id].ticker,
                row.bid_usd,
                row.ask_usd,
                row.last_usd,
                row.source,
                row.as_of,
                row.quality,
                row.sync_generation,
            )
            for row in session.scalars(select(CurrentQuote).order_by(CurrentQuote.id)).all()
        )
        transactions = tuple(
            (
                row.id,
                row.broker_transaction_key,
                securities[row.security_id].ticker,
                row.transaction_kind,
                row.transaction_time,
                row.trade_date,
                row.shares,
                row.amount_usd,
                row.realized_pl_usd,
                row.is_acquisition,
                row.source,
            )
            for row in session.scalars(
                select(BrokerTransaction).order_by(BrokerTransaction.id)
            ).all()
        )
        exposures = tuple(
            (
                row.id,
                securities[row.security_id].ticker,
                row.dimension,
                row.exposure_key,
                row.weight,
                row.provider,
                row.as_of_date,
            )
            for row in session.scalars(select(SecurityExposure).order_by(SecurityExposure.id)).all()
        )
        sync = (
            state.current_generation,
            state.completed_at,
            dict(state.coverage),
            state.complete,
        )
        return account_rows, positions, lots, quotes, transactions, exposures, sync


def _seed_independent_exposure(factory: sessionmaker[Session]) -> None:
    with factory.begin() as session:
        security = session.scalar(select(Security).where(Security.ticker == "AAA"))
        state = session.get(SyncState, 1)
        assert security is not None
        assert state is not None
        session.add(
            SecurityExposure(
                security_id=security.id,
                dimension="sector",
                exposure_key="Synthetic sector",
                weight=Decimal("0.75"),
                provider="manual_csv",
                as_of_date=date(2025, 8, 1),
            )
        )
        state.coverage = {**state.coverage, "lookthrough": True}


def _arm_post_flush_failure(engine: Engine) -> tuple[Callable[..., None], set[str]]:
    armed = True
    observed: set[str] = set()

    def fail_after_tax_lot_insert(
        connection: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        del connection, cursor, parameters, context, executemany
        nonlocal armed
        normalized = " ".join(statement.lower().split())
        for prefix in (
            "update account",
            "delete from current_tax_lot",
            "insert into current_position",
            "insert into current_tax_lot",
        ):
            if normalized.startswith(prefix):
                observed.add(prefix)
        if armed and normalized.startswith("insert into current_tax_lot"):
            armed = False
            raise RuntimeError("synthetic post-flush failure")

    event.listen(engine, "after_cursor_execute", fail_after_tax_lot_insert)
    return fail_after_tax_lot_insert, observed


def test_composed_sync_publishes_exact_generation_readback_and_restart(tmp_path: Path) -> None:
    cycle = _successful_cycle()
    app, engine, factory, transport, _ = _publication_app(tmp_path, [*cycle, *cycle])
    database_url = f"sqlite:///{tmp_path / 'etrade-sync.sqlite3'}"
    try:
        with TestClient(app, base_url="http://localhost:8000") as client:
            first_sync = client.post("/api/v1/portfolio/sync")
            assert first_sync.status_code == 200, first_sync.text
            assert first_sync.json()["generation"] == 1
            portfolio = client.get("/api/v1/portfolio").json()
            assert portfolio["status"] == "ready"
            assert portfolio["demo"] is False
            assert portfolio["cash_usd"] == "1234.567890123456789"
            assert portfolio["settled_buying_power_usd"] == "987.654321098765432"
            assert datetime.fromisoformat(portfolio["as_of"]) == datetime(
                2026, 11, 12, 8, 0, tzinfo=NOW.tzinfo
            )
            assert portfolio["coverage"]["transactions"] is True
            assert portfolio["coverage"]["lookthrough"] is False
            assert (
                portfolio["coverage"]["transaction_history_start_date"] == HISTORY_START.isoformat()
            )
            assert portfolio["coverage"]["transaction_history_end_date"] == HISTORY_END.isoformat()
            position = portfolio["positions"][0]
            assert position["ticker"] == "AAA"
            assert datetime.fromisoformat(position["quote_as_of"]) == NOW - timedelta(seconds=15)

            lot_page = client.get("/api/v1/lots?ticker=AAA").json()
            assert lot_page["source_generation"] == 1
            assert lot_page["cache"]["quantity_coverage_complete"] is True
            assert lot_page["total"] == 1
            lot = lot_page["items"][0]
            assert lot["broker_lot_id"] == "lot-aaa-1"
            assert lot["remaining_shares"] == "1"
            assert lot["available_shares"] == "0.75"
            assert lot["adjusted_unit_basis_usd"] == "255.87"
            assert datetime.fromisoformat(lot["as_of"]) == NOW

            wash = client.get("/api/v1/wash-sales").json()
            assert wash["history"][0]["broker_transaction_key"] == "transaction-1"
            assert wash["history"][0]["source"] == "ETRADE"
            assert wash["acquisitions"][0]["trade_date"] == date(2026, 11, 10).isoformat()
            cache = client.get("/api/v1/lots/cache").json()
            assert cache["current_generation"] == 1
            assert cache["quantity_coverage_complete"] is True

            with factory() as session:
                account = session.get(Account, 1)
                state = session.get(SyncState, 1)
                position_row = session.scalar(select(CurrentPosition))
                lot_row = session.scalar(select(CurrentTaxLot))
                quote_row = session.scalar(select(CurrentQuote))
                transaction_row = session.scalar(select(BrokerTransaction))
                assert account is not None
                assert state is not None
                assert position_row is not None
                assert lot_row is not None
                assert quote_row is not None
                assert transaction_row is not None
                assert account.broker_account_id_key == ACCOUNT_KEY
                assert account.as_of == datetime(2026, 11, 12, 8, 0, tzinfo=NOW.tzinfo)
                assert position_row.broker_position_id == "101"
                assert position_row.broker_product_id is not None
                assert json.loads(position_row.broker_product_id) == {
                    "symbol": "AAA",
                    "typeCode": "EQUITY",
                }
                assert position_row.as_of == NOW
                assert lot_row.broker_total_cost_usd == Decimal("255.87")
                assert lot_row.broker_total_cost_source_usd == Decimal("255.87")
                assert lot_row.reserved_shares == Decimal("0.25")
                assert lot_row.broker_acquired_date_source is not None
                assert json.loads(lot_row.broker_acquired_date_source) == {
                    "type": "integer",
                    "value": "1772168400000",
                }
                assert lot_row.as_of == NOW
                assert quote_row.as_of == NOW - timedelta(seconds=15)
                assert transaction_row.broker_transaction_key == "transaction-1"
                assert transaction_row.transaction_time == datetime(2026, 11, 10, tzinfo=NOW.tzinfo)
                assert state.coverage["lookthrough"] is False
                inputs = load_financial_inputs(
                    session,
                    account,
                    state,
                    None,
                    date(2026, 11, 13),
                    require_resolved_assignments=False,
                )
                assert inputs.account.as_of == account.as_of
                assert len(inputs.positions) == len(inputs.lots) == len(inputs.quotes) == 1
                assert inputs.transactions[0].broker_transaction_key == "transaction-1"

            _seed_independent_exposure(factory)
            second_sync = client.post("/api/v1/portfolio/sync")
            assert second_sync.status_code == 200, second_sync.text
            assert second_sync.json()["generation"] == 2
            assert client.get("/api/v1/portfolio").json()["coverage"]["lookthrough"] is True
            assert client.get("/api/v1/lots").json()["total"] == 1
            with factory() as session:
                assert session.scalar(select(Account.id)) == 1
                assert len(session.scalars(select(CurrentPosition)).all()) == 1
                assert len(session.scalars(select(CurrentTaxLot)).all()) == 1
                assert len(session.scalars(select(CurrentQuote)).all()) == 1
                assert len(session.scalars(select(BrokerTransaction)).all()) == 1
                exposure = session.scalar(select(SecurityExposure))
                state = session.get(SyncState, 1)
                assert exposure is not None
                assert state is not None
                assert exposure.as_of_date == date(2025, 8, 1)
                assert state.current_generation == 2
                assert state.coverage["lookthrough"] is True
                account = session.get(Account, 1)
                assert account is not None
                reloaded = load_financial_inputs(
                    session,
                    account,
                    state,
                    None,
                    date(2026, 11, 13),
                    require_resolved_assignments=False,
                )
                assert len(reloaded.exposures) == 1
                assert reloaded.exposures[0].as_of_date == date(2025, 8, 1)
            assert transport.responses == []

        engine.dispose()
        restarted_engine = create_database_engine(database_url)
        restarted_app = create_app(engine=restarted_engine, broker=FakeBroker())
        try:
            with TestClient(restarted_app, base_url="http://localhost:8000") as restarted_client:
                restarted_portfolio = restarted_client.get("/api/v1/portfolio").json()
                assert restarted_portfolio["sync"]["generation"] == 2
                assert restarted_portfolio["cash_usd"] == "1234.567890123456789"
                assert restarted_portfolio["coverage"]["lookthrough"] is True
                assert (
                    restarted_client.get("/api/v1/lots").json()["items"][0]["broker_lot_id"]
                    == "lot-aaa-1"
                )
                assert (
                    restarted_client.get("/api/v1/wash-sales").json()["history"][0][
                        "broker_transaction_key"
                    ]
                    == "transaction-1"
                )
                assert (
                    restarted_client.get("/api/v1/lots/cache").json()["quantity_coverage_complete"]
                    is True
                )
        finally:
            restarted_engine.dispose()
    finally:
        engine.dispose()


def test_empty_composed_portfolio_publishes_complete_first_binding(tmp_path: Path) -> None:
    responses = _http_responses(
        position_rows=(),
        lot_rows=(),
        transaction_rows=(),
        include_quote_response=False,
    )
    app, engine, factory, transport, _ = _publication_app(tmp_path, responses)
    try:
        with TestClient(app, base_url="http://localhost:8000") as client:
            result = client.post("/api/v1/portfolio/sync")
            assert result.status_code == 200, result.text
            assert result.json()["generation"] == 1
            portfolio = client.get("/api/v1/portfolio").json()
            assert portfolio["status"] == "ready"
            assert portfolio["position_count"] == 0
            assert portfolio["positions"] == []
            assert portfolio["coverage"]["positions"] is True
            assert portfolio["coverage"]["lots"] is True
            assert client.get("/api/v1/lots").json()["items"] == []
            assert client.get("/api/v1/lots/cache").json()["quantity_coverage_complete"] is True
            with factory() as session:
                account = session.get(Account, 1)
                state = session.get(SyncState, 1)
                assert account is not None
                assert account.broker_account_id_key == ACCOUNT_KEY
                assert state is not None
                assert state.current_generation == 1
                assert state.complete
                assert session.scalar(select(CurrentPosition)) is None
                assert session.scalar(select(CurrentTaxLot)) is None
                assert session.scalar(select(CurrentQuote)) is None
                assert session.scalar(select(BrokerTransaction)) is None
            assert transport.responses == []
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("kind", "expected_code"),
    [
        ("invalid_balance", "etrade_read_balance_as_of_invalid"),
        ("foreign_balance", "etrade_read_cross_section_account_mismatch"),
        ("lot_mismatch", "etrade_read_incomplete_lots"),
        ("partial_page", "etrade_read_transport_error"),
        ("incomplete_history", "incomplete_transaction_history"),
        ("missing_quote", "incomplete_quote_coverage"),
        ("stale_quote", "incomplete_quote_coverage"),
        ("metadata_mismatch", "invalid_sync_metadata"),
    ],
)
def test_failed_composed_publication_retains_all_prior_financial_rows(
    tmp_path: Path, kind: str, expected_code: str
) -> None:
    responses = [*_successful_cycle(), *_failure_cycle(kind)]
    app, engine, factory, _, broker = _publication_app(tmp_path, responses)
    try:
        with TestClient(app, base_url="http://localhost:8000") as client:
            successful = client.post("/api/v1/portfolio/sync")
            assert successful.status_code == 200, successful.text
            assert successful.json()["generation"] == 1
            _seed_independent_exposure(factory)
            before = _financial_signature(factory)
            if kind == "metadata_mismatch":
                broker.mutate_lot_metadata = True
            failed = client.post("/api/v1/portfolio/sync")
            assert failed.status_code in {409, 422, 502}, failed.text
            assert failed.json()["code"] == expected_code
            assert _financial_signature(factory) == before
            portfolio = client.get("/api/v1/portfolio").json()
            assert portfolio["sync"]["generation"] == 1
            assert portfolio["sync"]["complete"] is True
            assert portfolio["sync"]["last_error_code"] == expected_code
            assert portfolio["coverage"]["lookthrough"] is True
            failures = client.get("/api/v1/activity?event_type=sync&status=failed").json()
            assert failures["total"] == 1
            assert failures["items"][0]["details"]["code"] == expected_code
    finally:
        engine.dispose()


def test_first_account_binding_waits_for_a_successful_post_flush_commit(tmp_path: Path) -> None:
    cycle = _successful_cycle()
    app, engine, factory, _, _ = _publication_app(tmp_path, [*cycle, *cycle])
    listener, observed = _arm_post_flush_failure(engine)
    try:
        with TestClient(app, base_url="http://localhost:8000") as client:
            failed = client.post("/api/v1/portfolio/sync")
            assert failed.status_code == 500
            assert failed.json()["code"] == "sync_publish_failed"
            assert {
                "insert into current_position",
                "insert into current_tax_lot",
            } <= observed
            with factory() as session:
                assert session.get(Account, 1) is None
                state = session.get(SyncState, 1)
                assert state is not None
                assert state.current_generation == 0
                assert state.complete is False
                assert session.scalar(select(CurrentPosition)) is None
                assert session.scalar(select(CurrentTaxLot)) is None
                assert session.scalar(select(CurrentQuote)) is None
                assert session.scalar(select(BrokerTransaction)) is None
            failed_events = client.get("/api/v1/activity?event_type=sync&status=failed").json()
            assert failed_events["total"] == 1
            assert failed_events["items"][0]["details"]["code"] == "sync_publish_failed"

            successful = client.post("/api/v1/portfolio/sync")
            assert successful.status_code == 200, successful.text
            assert successful.json()["generation"] == 1
            with factory() as session:
                account = session.get(Account, 1)
                assert account is not None
                assert account.broker_account_id_key == ACCOUNT_KEY
    finally:
        event.remove(engine, "after_cursor_execute", listener)
        engine.dispose()


def test_post_flush_failure_rolls_back_complete_generation_and_reports_failure(
    tmp_path: Path,
) -> None:
    initial = _successful_cycle()
    changed_position = _position()
    changed_position["marketValue"] = Decimal("200.50")
    update = _successful_cycle(
        cash_usd=Decimal("4321.00"),
        settled_cash_usd=Decimal("6543.00"),
        position_rows=(changed_position,),
        lot_rows=(_lot(total_cost=Decimal("255.87")),),
    )
    app, engine, factory, _, _ = _publication_app(tmp_path, [*initial, *update])
    try:
        with TestClient(app, base_url="http://localhost:8000") as client:
            first = client.post("/api/v1/portfolio/sync")
            assert first.status_code == 200, first.text
            _seed_independent_exposure(factory)
            before = _financial_signature(factory)
            listener, observed = _arm_post_flush_failure(engine)
            try:
                failed = client.post("/api/v1/portfolio/sync")
            finally:
                event.remove(engine, "after_cursor_execute", listener)
            assert failed.status_code == 500
            assert failed.json()["code"] == "sync_publish_failed"
            assert {
                "update account",
                "delete from current_tax_lot",
                "insert into current_position",
                "insert into current_tax_lot",
            } <= observed
            assert _financial_signature(factory) == before
            portfolio = client.get("/api/v1/portfolio").json()
            assert portfolio["cash_usd"] == "1234.567890123456789"
            assert portfolio["sync"]["generation"] == 1
            assert portfolio["sync"]["complete"] is True
            assert portfolio["sync"]["last_error_code"] == "sync_publish_failed"
            assert portfolio["coverage"]["lookthrough"] is True
            failures = client.get("/api/v1/activity?event_type=sync&status=failed").json()
            assert failures["total"] == 1
            assert failures["items"][0]["details"]["code"] == "sync_publish_failed"
    finally:
        engine.dispose()
