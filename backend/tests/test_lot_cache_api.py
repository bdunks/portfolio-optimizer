from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from itertools import pairwise
from pathlib import Path
from urllib.parse import urlsplit

import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.broker.etrade_oauth import EtradeOAuthService
from app.broker.etrade_read import EtradeReadAdapter
from app.broker.fake import FakeBroker
from app.db.models import CurrentPosition, CurrentQuote, CurrentTaxLot, Security
from app.main import create_app
from app.schemas import LotCacheStatusResponse, LotPageResponse
from tests.test_etrade_read import (
    FakePacingClock,
    FixedClock,
    StubAdapter,
    _account,
    _accounts,
    _api_calls,
    _detail,
    _lot,
    _portfolio,
    _position,
    _response,
)
from tests.test_etrade_read import (
    _adapter as make_etrade_adapter,
)

_READ_AS_OF = datetime(2026, 11, 5, 16, 0, tzinfo=UTC)
_ACCOUNT_KEY = "DEMO-ONLY-ACCOUNT"
_ACQUIRED_MS = 1772168400000


def _make_reader(
    *, cycles: int = 1, mismatch_first: bool = False, empty: bool = False
) -> tuple[EtradeReadAdapter, EtradeOAuthService, StubAdapter, FakePacingClock]:
    pacing = FakePacingClock()
    responses: list[requests.Response] = []
    for cycle in range(cycles):
        responses.append(_response(_accounts(_account(_ACCOUNT_KEY))))
        if empty:
            responses.append(_response(_portfolio([], account_key=_ACCOUNT_KEY)))
            continue

        positions = [
            _position("AAA", "101", Decimal("1.25")),
            _position("VTI", "102", Decimal(2), asset_type="ETF"),
        ]
        responses.append(_response(_portfolio(positions, account_key=_ACCOUNT_KEY)))
        if mismatch_first and cycle == 0:
            first_position_lots = _detail(
                _lot(
                    "LOT-A-0",
                    Decimal("0.75"),
                    available=Decimal(0),
                    total_cost=Decimal("10.50"),
                    acquired_ms=_ACQUIRED_MS,
                )
            )
        else:
            first_position_lots = _detail(
                _lot(
                    "LOT-A-0",
                    Decimal("0.75"),
                    available=Decimal(0),
                    total_cost=Decimal("10.50"),
                    acquired_ms=_ACQUIRED_MS,
                ),
                _lot(
                    "LOT-A-1",
                    Decimal("0.50"),
                    available=Decimal("0.25"),
                    total_cost=Decimal("6.25"),
                    acquired_ms=_ACQUIRED_MS,
                ),
            )
        responses.extend(
            [
                _response(first_position_lots),
                _response(
                    _detail(
                        _lot(
                            "LOT-B-0",
                            Decimal(2),
                            available=Decimal("1.5"),
                            total_cost=Decimal("81.00"),
                            acquired_ms=_ACQUIRED_MS,
                        )
                    )
                ),
            ]
        )

    reader, oauth, transport, _ = make_etrade_adapter(
        responses,
        clock=FixedClock(_READ_AS_OF),
        pacing_clock=pacing,
    )
    return reader, oauth, transport, pacing


def test_explicit_refresh_uses_fake_etrade_adapter_and_survives_restart(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'connected-lot-cache.sqlite3'}"
    reader, _, transport, pacing = _make_reader()
    application = create_app(
        database_url=database_url,
        broker=FakeBroker(),
        seed_demo_data=True,
        portfolio_lot_reader=reader,
    )

    with TestClient(application, base_url="http://localhost:8000") as client:
        unknown = client.get("/api/v1/lots/cache").json()
        assert unknown["freshness"] == "unknown"
        assert _api_calls(transport) == []

        initial_lots_response = client.get("/api/v1/lots")
        assert initial_lots_response.status_code == 200
        initial_lots = LotPageResponse.model_validate(initial_lots_response.json())
        assert initial_lots.cache is not None
        assert initial_lots.cache.freshness == "unknown"
        assert _api_calls(transport) == []

        empty_filter = client.get("/api/v1/lots?ticker=NOT-HELD")
        assert empty_filter.status_code == 200
        assert empty_filter.json()["items"] == []
        assert empty_filter.json()["cache"] == unknown
        assert client.get("/api/v1/portfolio").status_code == 200
        assert _api_calls(transport) == []

        prior_run_response = client.post("/api/v1/optimizer/runs", json={})
        assert prior_run_response.status_code == 201, prior_run_response.text
        prior_run = prior_run_response.json()
        assert prior_run["demo"] is True

        refreshed = client.post("/api/v1/lots/refresh")
        assert refreshed.status_code == 200, refreshed.text
        status = LotCacheStatusResponse.model_validate(refreshed.json())
        assert status.freshness == "current"
        assert status.current_generation is not None
        assert status.cache_revision == 1
        assert status.source_generation == status.current_generation
        assert status.position_count == status.covered_position_count == 2
        assert status.lot_count == 3
        assert status.quantity_coverage_complete is True
        assert set(refreshed.json()) == {
            "freshness",
            "current_generation",
            "cache_revision",
            "source_generation",
            "source_as_of",
            "cached_at",
            "last_attempted_at",
            "last_error_code",
            "last_error_summary",
            "position_count",
            "covered_position_count",
            "lot_count",
            "quantity_coverage_complete",
        }

        lot_page_response = client.get("/api/v1/lots")
        assert lot_page_response.status_code == 200, lot_page_response.text
        lot_page = LotPageResponse.model_validate(lot_page_response.json())
        assert lot_page.source_generation is None
        assert lot_page.cache == status
        lots_by_id = {lot.broker_lot_id: lot for lot in lot_page.items}
        assert set(lots_by_id) == {"LOT-A-0", "LOT-A-1", "LOT-B-0"}
        assert lots_by_id["LOT-A-0"].remaining_shares == "0.75"
        assert lots_by_id["LOT-A-0"].available_shares == "0"
        assert lots_by_id["LOT-A-0"].acquired_date == date(2026, 2, 27)
        assert lots_by_id["LOT-A-1"].remaining_shares == "0.5"
        assert lots_by_id["LOT-A-1"].available_shares == "0.25"
        assert lots_by_id["LOT-B-0"].remaining_shares == "2"
        assert lots_by_id["LOT-B-0"].available_shares == "1.5"

        portfolio = client.get("/api/v1/portfolio").json()
        assert portfolio["sync"]["complete"] is False
        assert {row["ticker"]: row["shares"] for row in portfolio["positions"]} == {
            "AAA": "1.25",
            "VTI": "2",
        }

        with application.state.session_factory() as session:
            positions = dict(
                session.execute(
                    select(Security.ticker, CurrentPosition).join(
                        CurrentPosition, CurrentPosition.security_id == Security.id
                    )
                ).all()
            )
            assert positions["AAA"].broker_position_id == "101"
            assert positions["VTI"].broker_position_id == "102"
            lots = {lot.broker_lot_id: lot for lot in session.scalars(select(CurrentTaxLot)).all()}
            assert lots["LOT-A-0"].shares == Decimal("0.75")
            assert lots["LOT-A-0"].available_shares == Decimal(0)
            assert lots["LOT-A-0"].reserved_shares == Decimal("0.75")
            assert lots["LOT-A-0"].broker_total_cost_usd == Decimal("10.50")
            assert lots["LOT-A-0"].broker_total_cost_source_usd == Decimal("10.50")
            assert lots["LOT-A-0"].acquired_date == date(2026, 2, 27)
            assert lots["LOT-A-1"].broker_total_cost_usd == Decimal("6.25")
            assert lots["LOT-B-0"].broker_total_cost_usd == Decimal("81.00")

            quote = session.scalar(select(CurrentQuote).limit(1))
            assert quote is not None
        with application.state.session_factory.begin() as session:
            quote = session.scalar(select(CurrentQuote).limit(1))
            assert quote is not None
            quote.last_usd = Decimal("321.09")

        assert client.get("/api/v1/lots").status_code == 200
        assert client.get("/api/v1/lots?ticker=NOT-HELD").json()["cache"] == status.model_dump(
            mode="json"
        )
        assert client.get("/api/v1/lots/cache").json() == status.model_dump(mode="json")
        assert client.get("/api/v1/portfolio").status_code == 200
        assert len(_api_calls(transport)) == 4

        blocked_new_run = client.post("/api/v1/optimizer/runs", json={})
        assert blocked_new_run.status_code == 409, blocked_new_run.text
        assert blocked_new_run.json()["code"] == "current_state_unavailable"
        blocked_review = client.post(
            f"/api/v1/optimizer/runs/{prior_run['run_id']}/lot-review-intent",
            json={"source_generation": prior_run["source_generation"], "broker_lot_ids": []},
        )
        assert blocked_review.status_code == 409
        assert blocked_review.json()["code"] == "stale_run_source"
        assert len(_api_calls(transport)) == 4

        persisted_lots = lot_page_response.json()
        persisted_status = client.get("/api/v1/lots/cache").json()
        persisted_portfolio = client.get("/api/v1/portfolio").json()

    detail_times = [
        started_at
        for url, started_at in transport.api_request_starts
        if "/portfolio/" in urlsplit(url).path
    ]
    assert len(detail_times) == 2
    assert all(later - earlier >= 0.5 for earlier, later in pairwise(detail_times))
    assert pacing.sleeps == [0.5]

    application.state.engine.dispose()
    reopened = create_app(database_url=database_url, broker=FakeBroker(), seed_demo_data=False)
    with TestClient(reopened, base_url="http://localhost:8000") as client:
        assert client.get("/api/v1/lots").json() == persisted_lots
        assert client.get("/api/v1/lots/cache").json() == persisted_status
        assert client.get("/api/v1/portfolio").json() == persisted_portfolio
        assert client.get("/api/v1/lots?ticker=NOT-HELD").json()["cache"] == persisted_status
        assert len(_api_calls(transport)) == 4

        with reopened.state.session_factory.begin() as session:
            position = session.scalar(
                select(CurrentPosition)
                .join(Security, CurrentPosition.security_id == Security.id)
                .where(Security.ticker == "AAA")
            )
            assert position is not None
            position.shares = Decimal("1.5")
        stale_status = client.get("/api/v1/lots/cache").json()
        assert stale_status["freshness"] == "stale"
        assert stale_status["quantity_coverage_complete"] is False
        assert stale_status["covered_position_count"] == 1
        assert client.get("/api/v1/lots").json()["source_generation"] is None
        assert len(_api_calls(transport)) == 4

    reopened.state.engine.dispose()
    empty_reader, _, empty_transport, _ = _make_reader(empty=True)
    empty_app = create_app(
        database_url=database_url,
        broker=FakeBroker(),
        seed_demo_data=False,
        portfolio_lot_reader=empty_reader,
    )
    with TestClient(empty_app, base_url="http://localhost:8000") as client:
        empty_refresh = client.post("/api/v1/lots/refresh")
        assert empty_refresh.status_code == 200, empty_refresh.text
        empty_status = LotCacheStatusResponse.model_validate(empty_refresh.json())
        assert empty_status.freshness == "current"
        assert empty_status.position_count == empty_status.lot_count == 0
        assert empty_status.quantity_coverage_complete is True
        assert client.get("/api/v1/lots").json()["items"] == []
        assert client.get("/api/v1/portfolio").json()["positions"] == []
        assert (
            len([url for url, _ in empty_transport.api_request_starts if "/portfolio/" in url]) == 0
        )


def test_refresh_unavailable_unbound_and_cross_origin_paths_make_no_broker_requests(
    tmp_path: Path,
) -> None:
    no_reader_broker = FakeBroker()
    unavailable = create_app(
        database_url=f"sqlite:///{tmp_path / 'unavailable.sqlite3'}", broker=no_reader_broker
    )
    with TestClient(unavailable, base_url="http://localhost:8000") as client:
        response = client.post("/api/v1/lots/refresh")
        assert response.status_code == 503
        assert response.json()["code"] == "lot_refresh_unavailable"
        assert no_reader_broker.fetch_count == 0

    reader, _, transport, _ = _make_reader()
    unbound = create_app(
        database_url=f"sqlite:///{tmp_path / 'unbound.sqlite3'}",
        broker=FakeBroker(),
        allowed_origins=[],
        portfolio_lot_reader=reader,
    )
    with TestClient(unbound, base_url="http://localhost:8000") as client:
        cross_origin = client.post(
            "/api/v1/lots/refresh", headers={"Origin": "http://localhost:9000"}
        )
        assert cross_origin.status_code == 403
        assert cross_origin.json()["code"] == "local_origin_required"
        assert _api_calls(transport) == []

        missing_account = client.post("/api/v1/lots/refresh")
        assert missing_account.status_code == 409
        assert missing_account.json()["code"] == "managed_account_unbound"
        assert _api_calls(transport) == []


def test_api_reconciliation_failure_keeps_previous_lots_and_reports_sanitized_error(
    tmp_path: Path,
) -> None:
    reader, _, transport, _ = _make_reader(mismatch_first=True)
    application: FastAPI = create_app(
        database_url=f"sqlite:///{tmp_path / 'reconciliation-api.sqlite3'}",
        broker=FakeBroker(),
        seed_demo_data=True,
        portfolio_lot_reader=reader,
    )
    with TestClient(application, base_url="http://localhost:8000") as client:
        before = client.get("/api/v1/lots").json()
        failed = client.post("/api/v1/lots/refresh")
        assert failed.status_code == 422
        assert failed.json()["code"] == "etrade_read_incomplete_lots"
        assert "Broker portfolio and exact lots" in failed.json()["message"]
        after = client.get("/api/v1/lots").json()
        assert [item["broker_lot_id"] for item in after["items"]] == [
            item["broker_lot_id"] for item in before["items"]
        ]
        assert after["cache"]["freshness"] == "unknown"
        assert after["cache"]["last_error_code"] == "etrade_read_incomplete_lots"
        assert after["cache"]["last_error_summary"] == (
            "Broker portfolio and exact lots could not be validated"
        )
        assert len(_api_calls(transport)) == 4


def test_api_publication_hook_failure_retains_prior_cache_rows(tmp_path: Path) -> None:
    reader, _, transport, _ = _make_reader(cycles=2)
    publication = {"fail": False}

    def fail_publication() -> None:
        if publication["fail"]:
            raise RuntimeError("private-publication-test-marker")

    application: FastAPI = create_app(
        database_url=f"sqlite:///{tmp_path / 'publication-api.sqlite3'}",
        broker=FakeBroker(),
        seed_demo_data=True,
        publication_hook=fail_publication,
        portfolio_lot_reader=reader,
    )
    with TestClient(application, base_url="http://localhost:8000") as client:
        first = client.post("/api/v1/lots/refresh")
        assert first.status_code == 200, first.text
        before_status = first.json()
        before_page = client.get("/api/v1/lots").json()
        before_portfolio = client.get("/api/v1/portfolio").json()

        publication["fail"] = True
        failed = client.post("/api/v1/lots/refresh")
        assert failed.status_code == 500
        assert failed.json()["code"] == "lot_cache_publish_failed"
        assert "private-publication-test-marker" not in failed.text

        after_status = client.get("/api/v1/lots/cache").json()
        after_page = client.get("/api/v1/lots").json()
        after_portfolio = client.get("/api/v1/portfolio").json()
        assert after_status["freshness"] == "current"
        assert after_status["cache_revision"] == before_status["cache_revision"]
        assert after_status["source_generation"] == before_status["source_generation"]
        assert after_status["cached_at"] == before_status["cached_at"]
        assert after_status["last_error_code"] == "lot_cache_publish_failed"
        assert after_page["items"] == before_page["items"]
        assert after_portfolio["positions"] == before_portfolio["positions"]
        assert len(_api_calls(transport)) == 8
