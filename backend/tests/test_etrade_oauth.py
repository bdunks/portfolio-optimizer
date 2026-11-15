from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, parse_qsl, quote, unquote, urlencode, urlsplit
from zoneinfo import ZoneInfo

import pytest
import requests
from fastapi.testclient import TestClient
from requests.adapters import BaseAdapter

from app.broker.etrade_oauth import EtradeOAuthService
from app.broker.fake import FakeBroker
from app.main import create_app
from app.services.errors import AppError


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def _response(status_code: int = 200, text: str = "") -> requests.Response:
    response = requests.Response()
    response.status_code = status_code
    response._content = text.encode()
    response.encoding = "utf-8"
    return response


def _token_response(token: str, secret: str) -> requests.Response:
    body = urlencode(
        {
            "oauth_token": token,
            "oauth_token_secret": secret,
            "oauth_callback_confirmed": "true",
        }
    )
    return _response(text=body)


class StubAdapter(BaseAdapter):
    def __init__(self, responses: Sequence[requests.Response | Exception]) -> None:
        self.remaining = list(responses)
        self.calls: list[requests.PreparedRequest] = []

    def send(self, request: requests.PreparedRequest, **kwargs: object) -> requests.Response:
        self.calls.append(request)
        if not self.remaining:
            raise AssertionError(f"Unexpected fake HTTP request: {request.method} {request.url}")
        result = self.remaining.pop(0)
        if isinstance(result, Exception):
            raise result
        result.request = request
        result.url = request.url
        return result

    def close(self) -> None:
        pass


def _queued_transport(
    responses: Sequence[requests.Response | Exception],
) -> tuple[StubAdapter, list[requests.PreparedRequest]]:
    adapter = StubAdapter(responses)
    return adapter, adapter.calls


def _oauth_parameters(request: requests.PreparedRequest) -> dict[str, str]:
    header = request.headers["authorization"]
    if isinstance(header, bytes):
        header = header.decode()
    assert header.startswith("OAuth ")
    parameters: dict[str, str] = {}
    for item in header.removeprefix("OAuth ").split(","):
        key, value = item.strip().split("=", 1)
        parameters[unquote(key)] = unquote(value.strip('"'))
    return parameters


def _expected_signature(
    request: requests.PreparedRequest,
    *,
    consumer_secret: str,
    token_secret: str = "",
    include_query: bool = True,
) -> str:
    parts = urlsplit(str(request.url))
    parameters = [
        (key, value)
        for key, value in _oauth_parameters(request).items()
        if key not in {"oauth_signature", "realm"}
    ]
    if include_query:
        parameters.extend(parse_qsl(parts.query, keep_blank_values=True))
    normalized_parameters = sorted(
        (quote(key, safe="~"), quote(value, safe="~")) for key, value in parameters
    )
    normalized = "&".join(f"{key}={value}" for key, value in normalized_parameters)
    base_url = parts._replace(query="", fragment="").geturl()
    base_string = "&".join(
        (request.method.upper(), quote(base_url, safe="~"), quote(normalized, safe="~"))
    )
    signing_key = f"{quote(consumer_secret, safe='~')}&{quote(token_secret, safe='~')}"
    digest = hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def _service(
    clock: FixedClock,
    responses: Sequence[requests.Response | Exception],
) -> tuple[EtradeOAuthService, StubAdapter, list[requests.PreparedRequest]]:
    transport, calls = _queued_transport(responses)
    service = EtradeOAuthService(
        "consumer-key-test",
        "consumer-secret-test",
        transport=transport,
        clock=clock,
    )
    return service, transport, calls


def _active_service(
    clock: FixedClock,
    responses: Sequence[requests.Response | Exception],
) -> tuple[EtradeOAuthService, StubAdapter, list[requests.PreparedRequest]]:
    service, transport, calls = _service(clock, responses)
    service.start()
    service.verify("123456")
    return service, transport, calls


def test_auth_api_flow_signing_status_demo_and_memory_only(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="app.broker.etrade_oauth")
    clock = FixedClock(datetime(2026, 11, 5, 16, 0, tzinfo=UTC))
    transport, calls = _queued_transport(
        [
            _token_response("request-public-token", "request-private-secret"),
            _token_response("access-private-token", "access-private-secret"),
            _response(200, text="{}"),
        ]
    )
    service = EtradeOAuthService(
        "consumer-public-key",
        "consumer-private-secret",
        transport=transport,
        clock=clock,
    )
    database_path = tmp_path / "oauth-demo.sqlite3"
    broker = FakeBroker()
    application = create_app(
        database_url=f"sqlite:///{database_path}",
        broker=broker,
        seed_demo_data=True,
        etrade_oauth=service,
    )

    with TestClient(application, base_url="http://localhost") as client:
        initial = client.get("/api/v1/auth/etrade/status").json()
        assert initial["status"] == "unauthenticated"
        assert initial["available"] is True
        fetch_count = broker.fetch_count

        started = client.post("/api/v1/auth/etrade/start")
        assert started.status_code == 200, started.text
        authorization_url = urlsplit(started.json()["authorize_url"])
        assert authorization_url.scheme == "https"
        assert authorization_url.netloc == "us.etrade.com"
        assert authorization_url.path == "/e/t/etws/authorize"
        assert parse_qs(authorization_url.query) == {
            "key": ["consumer-public-key"],
            "token": ["request-public-token"],
        }
        assert "request-private-secret" not in started.text
        assert "consumer-private-secret" not in started.text
        assert "access-private-token" not in started.text

        pending = client.get("/api/v1/auth/etrade/status").json()
        assert pending["status"] == "pending"
        assert pending["authenticated"] is False
        assert pending["pending_expires_at"] == "2026-11-05T16:05:00Z"

        verified = client.post(
            "/api/v1/auth/etrade/verify",
            json={"verifier": "246810"},
        )
        assert verified.status_code == 200, verified.text
        assert verified.json()["status"] == "authenticated"
        assert verified.json()["authenticated"] is True
        assert verified.json()["account_id_key"] is None
        assert verified.json()["expires_at"] == "2026-11-06T00:00:00-05:00"
        assert "access-private-token" not in verified.text
        assert "access-private-secret" not in verified.text
        assert "246810" not in verified.text
        repeated = client.post("/api/v1/auth/etrade/verify", json={"verifier": "246810"})
        assert repeated.status_code == 409
        assert len(calls) == 2

        polled = client.get("/api/v1/auth/etrade/status").json()
        assert polled["last_activity_at"] == verified.json()["last_activity_at"]
        assert polled["renewal_due"] is False
        demo = client.get("/api/v1/portfolio").json()
        assert demo["demo"] is True
        assert demo["account"]["display_name"] == "DEMO — Hypothetical Account"
        assert broker.fetch_count == fetch_count

        read_session = service.auth_for_read()
        try:
            read = read_session.get(
                "https://api.etrade.com/v1/future-read?tag=one&tag=two&count=200",
                timeout=10,
                allow_redirects=False,
            )
        finally:
            read_session.close()
        assert read.status_code == 200
        read_request = calls[-1]
        assert _oauth_parameters(read_request)["oauth_token"] == "access-private-token"
        signature = unquote(_oauth_parameters(read_request)["oauth_signature"])
        assert signature == _expected_signature(
            read_request,
            consumer_secret="consumer-private-secret",
            token_secret="access-private-secret",
        )
        assert signature != _expected_signature(
            read_request,
            consumer_secret="consumer-private-secret",
            token_secret="access-private-secret",
            include_query=False,
        )

        request_auth = _oauth_parameters(calls[0])
        assert calls[0].url == "https://api.etrade.com/oauth/request_token"
        assert calls[0].method == "GET"
        assert request_auth["oauth_callback"] == "oob"
        assert request_auth["oauth_signature_method"] == "HMAC-SHA1"
        assert request_auth["oauth_signature"]
        access_auth = _oauth_parameters(calls[1])
        assert calls[1].url == "https://api.etrade.com/oauth/access_token"
        assert access_auth["oauth_token"] == "request-public-token"
        assert access_auth["oauth_verifier"] == "246810"
        assert access_auth["oauth_signature_method"] == "HMAC-SHA1"
        assert broker.fetch_count == fetch_count

    forbidden = (
        "consumer-private-secret",
        "request-private-secret",
        "access-private-token",
        "access-private-secret",
        "246810",
    )
    assert all(value not in caplog.text for value in forbidden)
    database_bytes = database_path.read_bytes()
    assert all(value.encode() not in database_bytes for value in forbidden)

    restarted = create_app(
        database_url=f"sqlite:///{database_path}",
        broker=FakeBroker(),
        seed_demo_data=False,
    )
    with TestClient(restarted, base_url="http://localhost") as client:
        status = client.get("/api/v1/auth/etrade/status").json()
        assert status["status"] == "disabled"
        assert status["authenticated"] is False
        assert status["account_id_key"] is None
        assert client.post("/api/v1/auth/etrade/start").status_code == 503


def test_default_and_unconfigured_auth_never_fall_back_to_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ETRADE_CONSUMER_KEY", "environment-key")
    monkeypatch.setenv("ETRADE_CONSUMER_SECRET", "environment-secret")
    default_app = create_app(
        database_url=f"sqlite:///{tmp_path / 'default.sqlite3'}",
        broker=FakeBroker(),
    )
    assert default_app.state.etrade_oauth is None
    with TestClient(default_app, base_url="http://localhost") as client:
        assert client.get("/api/v1/auth/etrade/status").json()["status"] == "disabled"
        assert client.post("/api/v1/auth/etrade/start").status_code == 503
        assert (
            client.post(
                "/api/v1/auth/etrade/verify",
                json={"verifier": "12345"},
            ).status_code
            == 503
        )

    transport, calls = _queued_transport([])
    unconfigured = EtradeOAuthService(
        None,
        "",
        transport=transport,
        clock=FixedClock(datetime(2026, 11, 5, 16, 0, tzinfo=UTC)),
    )
    application = create_app(
        database_url=f"sqlite:///{tmp_path / 'unconfigured.sqlite3'}",
        broker=FakeBroker(),
        etrade_oauth=unconfigured,
    )
    with TestClient(application, base_url="http://localhost") as client:
        status = client.get("/api/v1/auth/etrade/status").json()
        assert status["status"] == "unavailable"
        assert status["available"] is False
        assert client.post("/api/v1/auth/etrade/start").status_code == 503
        assert calls == []


def test_invalid_verifier_shapes_do_not_consume_pending_state(tmp_path: Path) -> None:
    for verifier_body in (None, {"verifier": "1234"}, {"verifier": "1234567"}):
        transport, calls = _queued_transport([_token_response("request-token", "request-secret")])
        service = EtradeOAuthService(
            "consumer-key",
            "consumer-secret",
            transport=transport,
            clock=lambda: datetime(2026, 11, 5, 16, 0, tzinfo=UTC),
        )
        application = create_app(
            database_url=f"sqlite:///{tmp_path / f'invalid-{verifier_body}.sqlite3'}",
            broker=FakeBroker(),
            etrade_oauth=service,
        )
        with TestClient(application, base_url="http://localhost") as client:
            assert client.post("/api/v1/auth/etrade/start").status_code == 200
            if verifier_body is None:
                response = client.post("/api/v1/auth/etrade/verify")
            else:
                response = client.post("/api/v1/auth/etrade/verify", json=verifier_body)
            assert response.status_code == 422
            assert client.get("/api/v1/auth/etrade/status").json()["status"] == "pending"
            assert len(calls) == 1


@pytest.mark.parametrize(
    ("body", "status_code"),
    [
        ("oauth_token_secret=request-secret-marker", 200),
        (
            "oauth_token=first&oauth_token=second&oauth_token_secret=request-secret-marker",
            200,
        ),
        ("malformed=response=request-secret-marker", 200),
        ("oauth_token_secret=request-secret-marker", 503),
    ],
)
def test_start_rejects_invalid_or_failed_broker_responses_without_leaking(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    body: str,
    status_code: int,
) -> None:
    caplog.set_level(logging.INFO, logger="app.broker.etrade_oauth")
    transport, _ = _queued_transport([_response(status_code, text=body)])
    service = EtradeOAuthService(
        "consumer-key",
        "consumer-secret-marker",
        transport=transport,
        clock=lambda: datetime(2026, 11, 5, 16, 0, tzinfo=UTC),
    )
    application = create_app(
        database_url=f"sqlite:///{tmp_path / 'bad-start.sqlite3'}",
        broker=FakeBroker(),
        etrade_oauth=service,
    )
    with TestClient(application, base_url="http://localhost") as client:
        response = client.post("/api/v1/auth/etrade/start")
        assert response.status_code == 502
        assert client.get("/api/v1/auth/etrade/status").json()["status"] == "unauthenticated"
    assert "request-secret-marker" not in response.text
    assert "consumer-secret-marker" not in response.text
    assert "request-secret-marker" not in caplog.text
    assert "consumer-secret-marker" not in caplog.text


@pytest.mark.parametrize(
    ("access_body", "access_status"),
    [
        ("oauth_token_secret=access-secret-marker", 200),
        (
            "oauth_token=first&oauth_token=second&oauth_token_secret=access-secret-marker",
            200,
        ),
        ("oauth_token=bad&oauth_token_secret=access-secret-marker", 401),
    ],
)
def test_access_exchange_errors_are_sanitized_and_pending_is_one_use(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    access_body: str,
    access_status: int,
) -> None:
    caplog.set_level(logging.INFO, logger="app.broker.etrade_oauth")
    transport, calls = _queued_transport(
        [
            _token_response("request-token", "request-secret-marker"),
            _response(access_status, text=access_body),
        ]
    )
    service = EtradeOAuthService(
        "consumer-key",
        "consumer-secret-marker",
        transport=transport,
        clock=lambda: datetime(2026, 11, 5, 16, 0, tzinfo=UTC),
    )
    application = create_app(
        database_url=f"sqlite:///{tmp_path / 'bad-access.sqlite3'}",
        broker=FakeBroker(),
        etrade_oauth=service,
    )
    with TestClient(application, base_url="http://localhost") as client:
        assert client.post("/api/v1/auth/etrade/start").status_code == 200
        response = client.post("/api/v1/auth/etrade/verify", json={"verifier": "123456"})
        assert response.status_code == 502
        assert client.get("/api/v1/auth/etrade/status").json()["status"] == "unauthenticated"
        repeated = client.post("/api/v1/auth/etrade/verify", json={"verifier": "123456"})
        assert repeated.status_code == 409
        assert len(calls) == 2
    assert "access-secret-marker" not in response.text
    assert "request-secret-marker" not in response.text
    assert "consumer-secret-marker" not in response.text
    assert "access-secret-marker" not in caplog.text
    assert "request-secret-marker" not in caplog.text
    assert "consumer-secret-marker" not in caplog.text


def test_replaced_and_expired_pending_states_cannot_be_reused(
    tmp_path: Path,
) -> None:
    clock = FixedClock(datetime(2026, 11, 5, 16, 0, tzinfo=UTC))
    responses = [
        _token_response("request-one", "secret-one"),
        _token_response("request-two", "secret-two"),
        _response(401, text="old verifier rejected"),
        _token_response("request-three", "secret-three"),
    ]
    service, _, calls = _service(clock, responses)
    application = create_app(
        database_url=f"sqlite:///{tmp_path / 'pending.sqlite3'}",
        broker=FakeBroker(),
        etrade_oauth=service,
    )
    with TestClient(application, base_url="http://localhost") as client:
        first = client.post("/api/v1/auth/etrade/start").json()
        second = client.post("/api/v1/auth/etrade/start").json()
        assert parse_qs(urlsplit(first["authorize_url"]).query)["token"] == ["request-one"]
        assert parse_qs(urlsplit(second["authorize_url"]).query)["token"] == ["request-two"]

        stale = client.post("/api/v1/auth/etrade/verify", json={"verifier": "123456"})
        assert stale.status_code == 502
        assert _oauth_parameters(calls[2])["oauth_token"] == "request-two"
        assert (
            client.post(
                "/api/v1/auth/etrade/verify",
                json={"verifier": "123456"},
            ).status_code
            == 409
        )
        assert len(calls) == 3

        assert client.post("/api/v1/auth/etrade/start").status_code == 200
        clock.now += timedelta(minutes=5)
        expired = client.post("/api/v1/auth/etrade/verify", json={"verifier": "123456"})
        assert expired.status_code == 409
        assert client.get("/api/v1/auth/etrade/status").json()["status"] == "unauthenticated"
        assert len(calls) == 4


def test_renewal_idle_boundaries_activity_and_hard_expiry() -> None:
    initial = datetime(2026, 11, 5, 16, 0, tzinfo=UTC)
    clock = FixedClock(initial)
    service, _, calls = _active_service(
        clock,
        [
            _token_response("request-token", "request-secret"),
            _token_response("access-token", "access-secret"),
            _token_response("rotated-access-token", "rotated-access-secret"),
        ],
    )
    original_expiry = service.status()["expires_at"]

    clock.now = initial + timedelta(minutes=90)
    assert service.status()["renewal_due"] is False
    service.auth_for_read()
    assert len(calls) == 2

    clock.now += timedelta(seconds=1)
    assert service.status()["renewal_due"] is True
    service.auth_for_read()
    assert len(calls) == 3
    assert calls[2].url == "https://api.etrade.com/oauth/renew_access_token"
    renewal_auth = _oauth_parameters(calls[2])
    assert renewal_auth["oauth_token"] == "access-token"
    assert renewal_auth["oauth_signature_method"] == "HMAC-SHA1"
    renewed_status = service.status()
    assert renewed_status["last_activity_at"] == clock.now
    assert renewed_status["expires_at"] == original_expiry
    assert renewed_status["renewal_due"] is False

    clock.now += timedelta(minutes=45)
    service.record_activity()
    last_activity = clock.now
    clock.now = last_activity + timedelta(minutes=90)
    service.auth_for_read()
    assert len(calls) == 3
    assert service.status()["renewal_due"] is False

    clock.now = last_activity + timedelta(hours=2)
    expired = service.status()
    assert expired["status"] == "expired"
    assert expired["authenticated"] is False
    assert expired["last_activity_at"] == last_activity
    with pytest.raises(AppError) as error:
        service.auth_for_read()
    assert error.value.status_code == 401
    assert len(calls) == 3
    service.close()


def test_malformed_renewal_response_expires_tokens_without_extending_activity(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    initial = datetime(2026, 11, 5, 16, 0, tzinfo=UTC)
    clock = FixedClock(initial)
    service, _, calls = _active_service(
        clock,
        [
            _token_response("request-token", "request-secret-marker"),
            _token_response("access-token-marker", "access-secret-marker"),
            _response(200, text="oauth_token=partial-token-marker"),
        ],
    )
    clock.now += timedelta(minutes=90, seconds=1)

    with pytest.raises(AppError) as error:
        service.auth_for_read()

    assert error.value.status_code == 502
    assert error.value.code == "etrade_oauth_invalid_response"
    assert error.value.details == {"operation": "renew-access-token"}
    status = service.status()
    assert status["status"] == "expired"
    assert status["authenticated"] is False
    assert status["last_activity_at"] == initial
    assert len(calls) == 3
    with pytest.raises(AppError) as unusable:
        service.auth_for_read()
    assert unusable.value.status_code == 401
    assert all(
        value not in caplog.text
        for value in (
            "consumer-secret-test",
            "request-secret-marker",
            "access-token-marker",
            "access-secret-marker",
            "partial-token-marker",
        )
    )
    service.close()


def test_empty_body_renewal_retains_active_tokens() -> None:
    initial = datetime(2026, 11, 5, 16, 0, tzinfo=UTC)
    clock = FixedClock(initial)
    service, _, calls = _active_service(
        clock,
        [
            _token_response("request-token", "request-secret"),
            _token_response("access-token", "access-secret"),
            _response(200),
        ],
    )
    clock.now += timedelta(minutes=90, seconds=1)

    session = service.auth_for_read()
    session.close()
    status = service.status()
    assert status["status"] == "authenticated"
    assert status["last_activity_at"] == clock.now
    assert status["renewal_due"] is False
    assert len(calls) == 3
    service.close()


def test_oauth_dependency_debug_logging_does_not_expose_credentials(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    clock = FixedClock(datetime(2026, 11, 5, 16, 0, tzinfo=UTC))
    service, _, calls = _service(
        clock,
        [
            _token_response("request-public-token", "request-private-secret"),
            _token_response("access-private-token", "access-private-secret"),
            _token_response("rotated-access-token", "rotated-access-secret"),
            _response(200, text="{}"),
        ],
    )
    started = service.start()
    assert parse_qs(urlsplit(started["authorize_url"]).query)["token"] == ["request-public-token"]
    service.verify("246810")
    clock.now += timedelta(minutes=90, seconds=1)

    session = service.auth_for_read()
    try:
        response = session.get(
            "https://api.etrade.com/v1/future-read?count=200",
            timeout=10,
            allow_redirects=False,
        )
    finally:
        session.close()
    assert response.status_code == 200
    assert [call.url for call in calls] == [
        "https://api.etrade.com/oauth/request_token",
        "https://api.etrade.com/oauth/access_token",
        "https://api.etrade.com/oauth/renew_access_token",
        "https://api.etrade.com/v1/future-read?count=200",
    ]
    assert "OAuth request-token request completed (HTTP 200)" in caplog.text
    assert "OAuth access-token request completed (HTTP 200)" in caplog.text
    assert "OAuth renew-access-token request completed (HTTP 200)" in caplog.text
    assert all(
        value not in caplog.text
        for value in (
            "consumer-private-secret",
            "request-private-secret",
            "access-private-token",
            "access-private-secret",
            "rotated-access-token",
            "rotated-access-secret",
            "246810",
        )
    )
    service.close()


def test_renewal_failure_expires_tokens_and_hides_broker_body(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="app.broker.etrade_oauth")
    clock = FixedClock(datetime(2026, 11, 5, 16, 0, tzinfo=UTC))
    service, _, calls = _active_service(
        clock,
        [
            _token_response("request-token", "request-secret"),
            _token_response("access-token", "access-secret"),
            _response(500, text="oauth_token_secret=upstream-secret-marker"),
        ],
    )
    clock.now += timedelta(minutes=90, seconds=1)
    with pytest.raises(AppError) as error:
        service.auth_for_read()
    assert error.value.status_code == 502
    assert "upstream-secret-marker" not in str(error.value)
    status = service.status()
    assert status["status"] == "expired"
    assert status["authenticated"] is False
    assert len(calls) == 3
    assert "upstream-secret-marker" not in caplog.text
    service.close()


@pytest.mark.parametrize(
    ("issued_at", "expected_expiry"),
    [
        (
            datetime(2026, 11, 1, 5, 30, tzinfo=UTC),
            datetime(2026, 11, 2, 0, 0, tzinfo=ZoneInfo("America/New_York")),
        ),
        (
            datetime(2026, 3, 8, 6, 30, tzinfo=UTC),
            datetime(2026, 3, 9, 0, 0, tzinfo=ZoneInfo("America/New_York")),
        ),
    ],
)
def test_expiry_uses_next_eastern_midnight_across_dst(
    issued_at: datetime,
    expected_expiry: datetime,
) -> None:
    clock = FixedClock(issued_at)
    service, _, calls = _active_service(
        clock,
        [
            _token_response("request-token", "request-secret"),
            _token_response("access-token", "access-secret"),
        ],
    )
    assert service.status()["expires_at"] == expected_expiry
    deadline = expected_expiry.astimezone(UTC)
    while clock.now + timedelta(hours=1) < deadline:
        clock.now += timedelta(hours=1)
        service.record_activity()
    clock.now = deadline - timedelta(seconds=1)
    assert service.status()["authenticated"] is True
    clock.now = deadline
    assert service.status()["status"] == "expired"
    with pytest.raises(AppError) as error:
        service.auth_for_read()
    assert error.value.status_code == 401
    assert len(calls) == 2
    service.close()
