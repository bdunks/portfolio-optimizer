from __future__ import annotations

from datetime import date
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import Account, PolicyRevision, Security, SecurityExposure, SyncState
from app.main import create_app
from app.schemas import ExposureCacheTickerResponse
from app.services.exposure_cache import LocalCsvExposureConfig
from app.services.financial_input_loader import load_financial_inputs
from app.services.ishares_market_data import ITOT_URL, IsharesFundConfig
from app.services.market_data import VANGUARD_BASE_URL, VanguardFundConfig
from tests.test_exposure_cache import FETCHED_AT

ROOT = Path(__file__).resolve().parent
VANGUARD_URL = f"{VANGUARD_BASE_URL}/0970/holdings/latest"


def test_exposure_cache_api_persists_reads_and_preserves_success(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'exposures.sqlite3'}"
    local_path = tmp_path / "schd.csv"
    local_path.write_text(
        "ticker,as_of_date,dimension,exposure_key,weight\n"
        "SCHD,2026-11-17,security,AAA,0.75\n"
        "SCHD,2026-11-17,sector,Industrials,0.75\n",
        encoding="utf-8",
    )
    sources = (
        VanguardFundConfig("VTI", "0970", VANGUARD_URL),
        IsharesFundConfig("ITOT", ITOT_URL),
        LocalCsvExposureConfig("SCHD", local_path),
    )
    vanguard_body = (ROOT / "fixtures/vanguard/vti.json").read_bytes()
    # This representative captured excerpt is served through a fake HTTP client; it is not a full fund universe.
    ishares_body = (ROOT / "fixtures/ishares/itot_excerpt.csv").read_bytes()
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        content = vanguard_body if str(request.url) == VANGUARD_URL else ishares_body
        return httpx.Response(200, content=content, request=request)

    transport_client = httpx.Client(transport=httpx.MockTransport(handler))
    clock_value = FETCHED_AT
    application = create_app(
        database_url=database_url,
        seed_demo_data=True,
        exposure_sources=sources,
        exposure_vanguard_client=transport_client,
        exposure_ishares_client=transport_client,
        exposure_clock=lambda: clock_value,
    )
    with TestClient(application, base_url="http://localhost:8000") as client:
        assert client.get("/api/v1/market-data/exposures/cache").json() == [
            {
                "ticker": ticker,
                "freshness": "configured_missing",
                "configured_provider": provider,
                "provider": None,
                "as_of_date": None,
                "cached_at": None,
                "last_attempted_at": None,
                "last_attempt_provider": None,
                "last_attempt_status": "never",
                "last_error_code": None,
                "last_error_summary": None,
                "publication_revision": 0,
                "dimensions": [],
            }
            for ticker, provider in (
                ("VTI", "vanguard"),
                ("ITOT", "ishares"),
                ("SCHD", "manual_csv"),
            )
        ]
        assert calls == []
        refreshed = client.post("/api/v1/market-data/exposures/refresh")
        assert refreshed.status_code == 200, refreshed.text
        status = [ExposureCacheTickerResponse.model_validate(item) for item in refreshed.json()]
        assert [item.ticker for item in status] == ["VTI", "ITOT", "SCHD"]
        assert status[1].as_of_date == date(2026, 11, 17)
        assert status[1].cached_at == FETCHED_AT
        assert status[1].publication_revision == 1
        assert status[1].dimensions
        assert all(
            isinstance(row.covered_weight, str) for item in status for row in item.dimensions
        )
        assert set(calls) == {VANGUARD_URL, ITOT_URL}
        assert len(calls) == 2

        with application.state.session_factory() as session:
            itot = session.scalar(select(Security).where(Security.ticker == "ITOT"))
            assert itot is not None
            assert (
                session.scalar(
                    select(SecurityExposure).where(
                        SecurityExposure.security_id == itot.id,
                        SecurityExposure.dimension == "security",
                        SecurityExposure.exposure_key == "AAPL",
                    )
                )
                is not None
            )
            account = session.get(Account, 1)
            sync_state = session.get(SyncState, 1)
            revision = session.scalar(
                select(PolicyRevision).where(PolicyRevision.status == "ACTIVE")
            )
            assert account is not None
            assert sync_state is not None
            assert revision is not None
            inputs = load_financial_inputs(
                session,
                account,
                sync_state,
                revision,
                date(2026, 11, 18),
                include_tax_lots=False,
                include_transactions=False,
                require_resolved_assignments=False,
            )
            assert any(row.ticker == "ITOT" for row in inputs.exposures)
            assert any(row.ticker == "ITOT" for row in inputs.exposure_cache)

        # Cache reads never request any provider; failed staged refresh leaves the successful rows intact.
        prior_vti_rows = None
        with application.state.session_factory() as session:
            prior_vti_rows = session.scalar(
                select(SecurityExposure.id).join(Security).where(Security.ticker == "VTI").limit(1)
            )
        local_path.write_text("invalid header\\n", encoding="utf-8")
        failed = client.post("/api/v1/market-data/exposures/refresh")
        assert failed.status_code == 422
        assert failed.json()["code"] == "exposure_refresh_failed"
        assert "invalid header" not in failed.text
        after_failure = client.get("/api/v1/market-data/exposures/cache")
        assert after_failure.status_code == 200
        assert after_failure.json()[1]["publication_revision"] == 1
        assert after_failure.json()[2]["last_attempt_status"] == "failure"
        with application.state.session_factory() as session:
            assert (
                session.scalar(
                    select(SecurityExposure.id)
                    .join(Security)
                    .where(Security.ticker == "VTI")
                    .limit(1)
                )
                == prior_vti_rows
            )

        # Middleware denies an unconfigured cross-origin write before any source is reached.
        denied = client.post(
            "/api/v1/market-data/exposures/refresh",
            headers={"Origin": "http://evil.localhost:5173"},
        )
        assert denied.status_code == 403
        assert denied.json()["code"] == "local_origin_required"
        assert len(calls) == 4  # one successful plus one failed staged provider pass

    restarted = create_app(
        database_url=database_url,
        exposure_sources=sources,
        exposure_vanguard_client=transport_client,
        exposure_ishares_client=transport_client,
        exposure_clock=lambda: FETCHED_AT,
    )
    with TestClient(restarted, base_url="http://localhost:8000") as client:
        cached = client.get("/api/v1/market-data/exposures/cache")
        assert cached.status_code == 200
        assert cached.json()[1]["as_of_date"] == "2026-11-17"
        assert cached.json()[1]["cached_at"] == FETCHED_AT.isoformat().replace("+00:00", "Z")
        assert len(calls) == 4
    transport_client.close()
    application.state.engine.dispose()
    restarted.state.engine.dispose()


def test_standard_startup_opt_in_is_manual_and_itot_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import main

    monkeypatch.setenv("PORTFOLIO_DATABASE_URL", f"sqlite:///{tmp_path / 'standard.sqlite3'}")
    monkeypatch.setenv("PORTFOLIO_DEMO_SEED", "1")
    monkeypatch.delenv("PORTFOLIO_ENABLE_ITOT_REFRESH", raising=False)
    unconfigured = main._standard_app(exposure_clock=lambda: FETCHED_AT)
    with TestClient(unconfigured, base_url="http://localhost:8000") as client:
        assert client.get("/api/v1/market-data/exposures/cache").json() == []
        assert client.get("/api/v1/portfolio").json()["demo"] is True
    unconfigured.state.engine.dispose()

    body = (ROOT / "fixtures/ishares/itot_excerpt.csv").read_bytes()
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(200, content=body, request=request)

    original_client = httpx.Client
    client_options: list[tuple[float, bool]] = []

    def fake_client(*, timeout: float, follow_redirects: bool) -> httpx.Client:
        client_options.append((timeout, follow_redirects))
        return original_client(
            transport=httpx.MockTransport(handler),
            timeout=timeout,
            follow_redirects=follow_redirects,
        )

    monkeypatch.setattr(main.httpx, "Client", fake_client)
    monkeypatch.setenv("PORTFOLIO_ENABLE_ITOT_REFRESH", "1")
    enabled = main._standard_app(exposure_clock=lambda: FETCHED_AT)
    assert len(client_options) == 1
    assert client_options[0] == (10.0, False)
    with TestClient(enabled, base_url="http://localhost:8000") as client:
        assert requests == []  # Startup is not a fetch.
        status = client.get("/api/v1/market-data/exposures/cache")
        assert status.status_code == 200
        assert status.json()[0]["ticker"] == "ITOT"
        assert requests == []  # GET remains a persisted-cache read.
        refreshed = client.post("/api/v1/market-data/exposures/refresh")
        assert refreshed.status_code == 200, refreshed.text
        assert refreshed.json()[0]["as_of_date"] == "2026-11-17"
        assert requests == [ITOT_URL]
    enabled.state.engine.dispose()


def test_exposure_cache_api_is_unavailable_without_sources(tmp_path: Path) -> None:
    application = create_app(database_url=f"sqlite:///{tmp_path / 'empty.sqlite3'}")
    specification = application.openapi()
    refresh_operation = specification["paths"]["/api/v1/market-data/exposures/refresh"]["post"]
    cache_operation = specification["paths"]["/api/v1/market-data/exposures/cache"]["get"]
    assert "requestBody" not in refresh_operation
    assert refresh_operation["responses"]["503"]["content"]["application/json"]["schema"][
        "$ref"
    ].endswith("/ErrorEnvelope")
    assert cache_operation["responses"]["200"]["content"]["application/json"]["schema"]["items"][
        "$ref"
    ].endswith("/ExposureCacheTickerResponse")
    assert (
        specification["components"]["schemas"]["ExposureDimensionCoverageResponse"]["properties"][
            "covered_weight"
        ]["type"]
        == "string"
    )
    with TestClient(application, base_url="http://localhost:8000") as client:
        assert client.get("/api/v1/market-data/exposures/cache").json() == []
        response = client.post("/api/v1/market-data/exposures/refresh")
        assert response.status_code == 503
        assert response.json()["code"] == "exposure_sources_unconfigured"
        assert set(response.json()) == {"code", "message", "details", "correlation_id"}
    application.state.engine.dispose()
