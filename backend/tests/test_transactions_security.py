from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from threading import Barrier, Event

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session, sessionmaker

from app.broker.fake import FakeBroker
from app.db.migrate import upgrade_database
from app.db.models import (
    Account,
    ActivityEvent,
    CurrentPosition,
    CurrentQuote,
    CurrentTaxLot,
    Security,
    SyncState,
)
from app.db.session import create_database_engine, make_session_factory
from app.main import create_app
from app.schemas import BrokerSnapshot
from app.services.sync import sync_portfolio


def _snapshot_with_values(cash: str, aapl_value: str) -> BrokerSnapshot:
    snapshot = FakeBroker.demo_snapshot()
    positions = [
        position.model_copy(update={"market_value_usd": Decimal(aapl_value)})
        if position.ticker == "AAPL"
        else position
        for position in snapshot.positions
    ]
    return snapshot.model_copy(
        update={
            "cash_usd": Decimal(cash),
            "settled_buying_power_usd": Decimal(cash),
            "positions": positions,
        }
    )


def _assert_no_sync_write(factory: sessionmaker[Session], broker: FakeBroker) -> None:
    assert broker.fetch_count == 0
    with factory() as session:
        assert session.get(Account, 1) is None
        assert session.get(SyncState, 1) is None
        assert session.scalar(select(ActivityEvent.id)) is None


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:7777",
        "http://localhost:9000",
        "https://remote.example",
        "null",
        "http://localhost:invalid",
        "http://localhost:",
        "http://localhost?",
        "http://localhost#",
    ],
)
def test_unconfigured_and_malformed_origins_cannot_trigger_simple_sync(
    tmp_path: Path, origin: str
) -> None:
    broker = FakeBroker()
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'origin.sqlite3'}",
        broker=broker,
        allowed_origins=[],
    )
    with TestClient(app, base_url="http://localhost:8000") as client:
        response = client.post("/api/v1/portfolio/sync", headers={"Origin": origin})
        assert response.status_code == 403
        assert response.json()["code"] == "local_origin_required"
        _assert_no_sync_write(app.state.session_factory, broker)


def test_empty_origin_allowlist_allows_actual_same_origin_and_local_cli_but_guards_patch(
    tmp_path: Path,
) -> None:
    broker = FakeBroker()
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'same-origin.sqlite3'}",
        broker=broker,
        allowed_origins=[],
    )
    with TestClient(app, base_url="http://localhost:8000") as client:
        rejected_patch = client.patch(
            "/api/v1/optimizer/runs/missing/recommendations/missing",
            headers={"Origin": "http://localhost:7777"},
            json={},
        )
        assert rejected_patch.status_code == 403
        _assert_no_sync_write(app.state.session_factory, broker)

        same_origin = client.post(
            "/api/v1/portfolio/sync", headers={"Origin": "http://LOCALHOST:08000"}
        )
        assert same_origin.status_code == 200, same_origin.text
        assert same_origin.json()["generation"] == 1

        cli_sync = client.post("/api/v1/portfolio/sync")
        assert cli_sync.status_code == 200, cli_sync.text
        assert cli_sync.json()["generation"] == 2
        assert broker.fetch_count == 2


def test_explicit_development_origin_remains_authorized(tmp_path: Path) -> None:
    broker = FakeBroker()
    app = create_app(database_url=f"sqlite:///{tmp_path / 'dev-origin.sqlite3'}", broker=broker)
    with TestClient(app, base_url="http://localhost:8000") as client:
        response = client.post(
            "/api/v1/portfolio/sync", headers={"Origin": "http://localhost:9000"}
        )
        assert response.status_code == 200, response.text
        assert response.json()["generation"] == 1
        assert broker.fetch_count == 1



def test_failed_publication_retains_generation_and_releases_writer_for_next_sync(
    tmp_path: Path,
) -> None:
    broker = FakeBroker()
    publication = {"fail": False}

    def fail_publication() -> None:
        if publication["fail"]:
            raise RuntimeError("injected publish failure")

    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'failed-publication.sqlite3'}",
        broker=broker,
        publication_hook=fail_publication,
    )
    with TestClient(app, base_url="http://localhost:8000") as client:
        initial = client.post("/api/v1/portfolio/sync")
        assert initial.status_code == 200, initial.text
        before_failure = client.get("/api/v1/portfolio").json()

        publication["fail"] = True
        failed = client.post("/api/v1/portfolio/sync")
        assert failed.status_code == 500
        after_failure = client.get("/api/v1/portfolio").json()
        assert after_failure["sync"]["generation"] == before_failure["sync"]["generation"]
        assert after_failure["cash_usd"] == before_failure["cash_usd"]

        publication["fail"] = False
        broker._snapshot = _snapshot_with_values("5432.00", "6543.00")
        next_sync = client.post("/api/v1/portfolio/sync")
        assert next_sync.status_code == 200, next_sync.text
        assert next_sync.json()["generation"] == before_failure["sync"]["generation"] + 1
        assert client.get("/api/v1/portfolio").json()["cash_usd"] == "5432"


class _BarrierBroker(FakeBroker):
    def __init__(self, snapshot: BrokerSnapshot, barrier: Barrier) -> None:
        super().__init__(snapshot)
        self._barrier = barrier

    def fetch_snapshot(self) -> BrokerSnapshot:
        snapshot = super().fetch_snapshot()
        self._barrier.wait(timeout=10)
        return snapshot


def _publish(
    factory: sessionmaker[Session], broker: FakeBroker, correlation_id: str
) -> dict[str, object]:
    return sync_portfolio(factory, broker, correlation_id=correlation_id)


def test_concurrent_syncs_on_separate_engines_allocate_distinct_generations(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'concurrent-sync.sqlite3'}"
    first_engine = create_database_engine(database_url)
    second_engine = create_database_engine(database_url)
    try:
        upgrade_database(first_engine)
        first_factory = make_session_factory(first_engine)
        second_factory = make_session_factory(second_engine)
        assert sync_portfolio(first_factory, FakeBroker(), correlation_id="initial")["generation"] == 1

        first_snapshot = _snapshot_with_values("1200.00", "2100.00")
        second_snapshot = _snapshot_with_values("2400.00", "3300.00")
        barrier = Barrier(2)
        first_broker = _BarrierBroker(first_snapshot, barrier)
        second_broker = _BarrierBroker(second_snapshot, barrier)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(_publish, first_factory, first_broker, "concurrent-a")
            second = pool.submit(_publish, second_factory, second_broker, "concurrent-b")
            first_result = first.result(timeout=15)
            second_result = second.result(timeout=15)

        first_generation = int(first_result["generation"])
        second_generation = int(second_result["generation"])
        assert sorted((first_generation, second_generation)) == [2, 3]
        expected_by_generation = {
            first_generation: (first_snapshot.cash_usd, Decimal("2100.00")),
            second_generation: (second_snapshot.cash_usd, Decimal("3300.00")),
        }
        with first_factory() as session:
            state = session.get(SyncState, 1)
            account = session.get(Account, 1)
            assert state is not None
            assert state.current_generation == 3
            assert account is not None
            assert account.cash_usd == expected_by_generation[3][0]
            positions = dict(
                session.execute(
                    select(Security.ticker, CurrentPosition.market_value_usd).join(CurrentPosition)
                ).all()
            )
            assert positions["AAPL"] == expected_by_generation[3][1]
            assert all(row.sync_generation == 3 for row in session.scalars(select(CurrentPosition)))
            assert all(row.sync_generation == 3 for row in session.scalars(select(CurrentTaxLot)))
            assert all(row.sync_generation == 3 for row in session.scalars(select(CurrentQuote)))
    finally:
        first_engine.dispose()
        second_engine.dispose()


def test_portfolio_response_keeps_one_read_snapshot_during_sync_commit(tmp_path: Path) -> None:
    broker = FakeBroker()
    app = create_app(database_url=f"sqlite:///{tmp_path / 'read-snapshot.sqlite3'}", broker=broker)
    with TestClient(app, base_url="http://localhost:8000") as client:
        synced = client.post("/api/v1/portfolio/sync")
        assert synced.status_code == 200, synced.text
        old_portfolio = client.get("/api/v1/portfolio").json()
        old_positions = {item["ticker"]: item["market_value_usd"] for item in old_portfolio["positions"]}
        broker._snapshot = _snapshot_with_values("4321.00", "7654.00")

        account_read = Event()
        continue_read = Event()

        def pause_after_account_select(
            connection: Connection,
            cursor: object,
            statement: str,
            parameters: object,
            context: object,
            executemany: bool,
        ) -> None:
            del connection, cursor, parameters, context, executemany
            normalized_sql = statement.lower()
            if not account_read.is_set() and "from account" in normalized_sql and "account.id" in normalized_sql:
                account_read.set()
                if not continue_read.wait(timeout=10):
                    raise RuntimeError("portfolio read was not released")

        event.listen(app.state.engine, "after_cursor_execute", pause_after_account_select)
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                response_future = pool.submit(client.get, "/api/v1/portfolio")
                assert account_read.wait(timeout=10), "portfolio did not read its account row"
                published = sync_portfolio(
                    app.state.session_factory, broker, correlation_id="during-portfolio-read"
                )
                assert published["generation"] == old_portfolio["sync"]["generation"] + 1
                continue_read.set()
                response = response_future.result(timeout=10)
        finally:
            continue_read.set()
            event.remove(app.state.engine, "after_cursor_execute", pause_after_account_select)

        assert response.status_code == 200, response.text
        portfolio = response.json()
        assert portfolio["cash_usd"] == old_portfolio["cash_usd"]
        assert portfolio["sync"]["generation"] == old_portfolio["sync"]["generation"]
        assert {item["ticker"]: item["market_value_usd"] for item in portfolio["positions"]} == old_positions
        latest = client.get("/api/v1/portfolio").json()
        assert latest["cash_usd"] == "4321"
        assert latest["sync"]["generation"] == old_portfolio["sync"]["generation"] + 1
        assert next(item for item in latest["positions"] if item["ticker"] == "AAPL")["market_value_usd"] == "7654"
