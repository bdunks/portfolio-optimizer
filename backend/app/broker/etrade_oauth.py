from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from urllib.parse import parse_qs, urlencode
from zoneinfo import ZoneInfo

import httpx
from authlib.integrations.httpx_client import OAuth1Auth

from app.services.errors import AppError

logger = logging.getLogger(__name__)

REQUEST_TOKEN_URL = "https://api.etrade.com/oauth/request_token"
ACCESS_TOKEN_URL = "https://api.etrade.com/oauth/access_token"
RENEW_TOKEN_URL = "https://api.etrade.com/oauth/renew_access_token"
AUTHORIZE_URL = "https://us.etrade.com/e/t/etws/authorize"
PENDING_TOKEN_TTL = timedelta(minutes=5)
RENEW_AFTER_IDLE = timedelta(minutes=90)
EXPIRE_AFTER_IDLE = timedelta(hours=2)
EASTERN = ZoneInfo("America/New_York")


@dataclass(slots=True)
class _PendingToken:
    token: str
    secret: str
    expires_at: datetime


@dataclass(slots=True)
class _AccessToken:
    token: str
    secret: str
    last_activity_at: datetime
    expires_at: datetime


class EtradeOAuthService:
    """In-memory OAuth lifecycle requiring an explicitly injected HTTP transport."""

    def __init__(
        self,
        consumer_key: str | None,
        consumer_secret: str | None,
        *,
        transport: httpx.BaseTransport,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._consumer_key = consumer_key if consumer_key and consumer_key.strip() else None
        self._consumer_secret = (
            consumer_secret if consumer_secret and consumer_secret.strip() else None
        )
        self._client = httpx.Client(
            transport=transport,
            follow_redirects=False,
            timeout=10.0,
        )
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.RLock()
        self._pending: _PendingToken | None = None
        self._access: _AccessToken | None = None
        self._expired_access: tuple[datetime, datetime] | None = None

    @property
    def available(self) -> bool:
        return self._consumer_key is not None and self._consumer_secret is not None

    def close(self) -> None:
        with self._lock:
            self._pending = None
            self._access = None
            self._expired_access = None
            self._client.close()

    def start(self) -> dict[str, str]:
        with self._lock:
            self._require_available()
            # A new start replaces pending state; active access remains until a successful exchange.
            self._pending = None
            response = self._request(
                "request-token",
                REQUEST_TOKEN_URL,
                redirect_uri="oob",
            )
            token, secret = self._parse_token_pair(response.text, "request-token")
            now = self._now()
            self._pending = _PendingToken(token, secret, now + PENDING_TOKEN_TTL)
            authorize_url = (
                f"{AUTHORIZE_URL}?{urlencode({'key': self._consumer_key, 'token': token})}"
            )
            return {"authorize_url": authorize_url}

    def verify(self, verifier: str) -> dict[str, object]:
        with self._lock:
            self._require_available()
            normalized_verifier = verifier.strip() if isinstance(verifier, str) else ""
            if not 5 <= len(normalized_verifier) <= 6:
                raise AppError(
                    "etrade_verifier_invalid",
                    "The E*TRADE verifier must contain 5 or 6 characters.",
                    status_code=422,
                )
            now = self._now()
            pending = self._pending
            if pending is None:
                raise AppError(
                    "etrade_pending_authorization_missing",
                    "Start a new E*TRADE authorization before verifying.",
                    status_code=409,
                )
            if pending.expires_at <= now:
                self._pending = None
                raise AppError(
                    "etrade_pending_authorization_expired",
                    "The E*TRADE authorization request expired; start again.",
                    status_code=409,
                )

            # Consume before exchanging so a failed exchange cannot be replayed.
            self._pending = None
            response = self._request(
                "access-token",
                ACCESS_TOKEN_URL,
                token=pending.token,
                token_secret=pending.secret,
                verifier=normalized_verifier,
            )
            token, secret = self._parse_token_pair(response.text, "access-token")
            issued_at = self._now()
            self._access = _AccessToken(
                token=token,
                secret=secret,
                last_activity_at=issued_at,
                expires_at=self._next_eastern_midnight(issued_at),
            )
            self._expired_access = None
            return self._status_locked(issued_at)

    def status(self) -> dict[str, object]:
        """Return status without counting the poll as broker activity."""
        with self._lock:
            return self._status_locked(self._now())

    def auth_for_read(self) -> OAuth1Auth:
        """Ensure usable credentials and return an OAuth signer for a future broker read."""
        with self._lock:
            self._require_available()
            now = self._now()
            access = self._access
            if access is None:
                raise self._auth_required_error()
            if self._access_is_expired(access, now):
                self._expire_access_locked()
                raise self._auth_expired_error()

            if now - access.last_activity_at > RENEW_AFTER_IDLE:
                try:
                    response = self._request(
                        "renew-access-token",
                        RENEW_TOKEN_URL,
                        token=access.token,
                        token_secret=access.secret,
                    )
                    token, secret = self._parse_renewal_pair(
                        response.text, access.token, access.secret
                    )
                except AppError:
                    self._expire_access_locked()
                    raise
                renewed_at = self._now()
                if self._access_is_expired(
                    _AccessToken(token, secret, renewed_at, access.expires_at), renewed_at
                ):
                    self._expire_access_locked()
                    raise self._auth_expired_error()
                access = _AccessToken(token, secret, renewed_at, access.expires_at)
                self._access = access

            return self._auth(token=access.token, token_secret=access.secret)

    def record_activity(self) -> None:
        """Record a successful future broker read; status and auth preparation do not count."""
        with self._lock:
            self._require_available()
            now = self._now()
            access = self._access
            if access is None:
                raise self._auth_required_error()
            if self._access_is_expired(access, now):
                self._expire_access_locked()
                raise self._auth_expired_error()
            access.last_activity_at = now

    def _request(
        self,
        operation: str,
        url: str,
        *,
        token: str | None = None,
        token_secret: str | None = None,
        redirect_uri: str | None = None,
        verifier: str | None = None,
    ) -> httpx.Response:
        auth = self._auth(
            token=token,
            token_secret=token_secret,
            redirect_uri=redirect_uri,
            verifier=verifier,
        )
        try:
            response = self._client.get(url, auth=auth)
        except httpx.HTTPError:
            logger.warning("E*TRADE OAuth %s request failed (transport error)", operation)
            raise AppError(
                "etrade_oauth_transport_error",
                "E*TRADE OAuth could not complete the request.",
                status_code=502,
                details={"operation": operation},
            ) from None

        if response.status_code != 200:
            logger.warning(
                "E*TRADE OAuth %s request failed (HTTP %d)", operation, response.status_code
            )
            raise AppError(
                "etrade_oauth_broker_error",
                f"E*TRADE OAuth {operation} failed (HTTP {response.status_code}).",
                status_code=502,
                details={"operation": operation, "upstream_status": response.status_code},
            )
        logger.info("E*TRADE OAuth %s request completed (HTTP 200)", operation)
        return response

    def _auth(
        self,
        *,
        token: str | None = None,
        token_secret: str | None = None,
        redirect_uri: str | None = None,
        verifier: str | None = None,
    ) -> OAuth1Auth:
        self._require_available()
        return OAuth1Auth(
            client_id=self._consumer_key,
            client_secret=self._consumer_secret,
            token=token,
            token_secret=token_secret,
            redirect_uri=redirect_uri,
            verifier=verifier,
            signature_method="HMAC-SHA1",
            signature_type="HEADER",
        )

    def _parse_token_pair(self, body: str, operation: str) -> tuple[str, str]:
        try:
            fields = parse_qs(body, keep_blank_values=True, strict_parsing=True, max_num_fields=20)
        except ValueError:
            fields = {}
        tokens = fields.get("oauth_token", [])
        secrets = fields.get("oauth_token_secret", [])
        if len(tokens) != 1 or not tokens[0] or len(secrets) != 1 or not secrets[0]:
            logger.warning("E*TRADE OAuth %s response was invalid", operation)
            raise AppError(
                "etrade_oauth_invalid_response",
                f"E*TRADE returned an invalid {operation} response.",
                status_code=502,
                details={"operation": operation},
            )
        return tokens[0], secrets[0]

    def _parse_renewal_pair(
        self, body: str, current_token: str, current_secret: str
    ) -> tuple[str, str]:
        if not body:
            return current_token, current_secret
        try:
            fields = parse_qs(body, keep_blank_values=True, strict_parsing=True, max_num_fields=20)
        except ValueError:
            fields = {}
        token_values = fields.get("oauth_token", [])
        secret_values = fields.get("oauth_token_secret", [])
        if not token_values and not secret_values:
            return current_token, current_secret
        if (
            len(token_values) != 1
            or not token_values[0]
            or len(secret_values) != 1
            or not secret_values[0]
        ):
            logger.warning("E*TRADE OAuth renew-access-token response was invalid")
            raise AppError(
                "etrade_oauth_invalid_response",
                "E*TRADE returned an invalid renew-access-token response.",
                status_code=502,
                details={"operation": "renew-access-token"},
            )
        return token_values[0], secret_values[0]

    def _status_locked(self, now: datetime) -> dict[str, object]:
        if not self.available:
            return self._status_payload(
                status="unavailable",
                available=False,
                authenticated=False,
                message="E*TRADE OAuth credentials are not configured.",
            )

        pending = self._pending
        if pending is not None and pending.expires_at <= now:
            self._pending = None
            pending = None

        access = self._access
        if access is not None and self._access_is_expired(access, now):
            self._expire_access_locked()
            access = None

        if access is not None:
            return self._status_payload(
                status="authenticated",
                available=True,
                authenticated=True,
                message="E*TRADE OAuth tokens are active in backend memory; no account is bound.",
                expires_at=access.expires_at,
                idle_expires_at=access.last_activity_at + EXPIRE_AFTER_IDLE,
                last_activity_at=access.last_activity_at,
                renewal_due=now - access.last_activity_at > RENEW_AFTER_IDLE,
                pending_expires_at=pending.expires_at if pending is not None else None,
            )
        if pending is not None:
            return self._status_payload(
                status="pending",
                available=True,
                authenticated=False,
                message="E*TRADE authorization is pending verifier exchange.",
                pending_expires_at=pending.expires_at,
            )
        if self._expired_access is not None:
            expires_at, last_activity_at = self._expired_access
            return self._status_payload(
                status="expired",
                available=True,
                authenticated=False,
                message="E*TRADE OAuth tokens expired; start a new authorization.",
                expires_at=expires_at,
                idle_expires_at=last_activity_at + EXPIRE_AFTER_IDLE,
                last_activity_at=last_activity_at,
            )
        return self._status_payload(
            status="unauthenticated",
            available=True,
            authenticated=False,
            message="E*TRADE OAuth is available but no tokens are active.",
        )

    @staticmethod
    def _status_payload(
        *,
        status: str,
        available: bool,
        authenticated: bool,
        message: str,
        expires_at: datetime | None = None,
        idle_expires_at: datetime | None = None,
        pending_expires_at: datetime | None = None,
        last_activity_at: datetime | None = None,
        renewal_due: bool = False,
    ) -> dict[str, object]:
        return {
            "status": status,
            "available": available,
            "authenticated": authenticated,
            "account_id_key": None,
            "phase": 3,
            "message": message,
            "expires_at": expires_at,
            "idle_expires_at": idle_expires_at,
            "pending_expires_at": pending_expires_at,
            "last_activity_at": last_activity_at,
            "renewal_due": renewal_due,
        }

    def _require_available(self) -> None:
        if not self.available:
            raise AppError(
                "etrade_auth_unavailable",
                "E*TRADE OAuth credentials are not configured.",
                status_code=503,
                details={"available": False},
            )

    def _expire_access_locked(self) -> None:
        if self._access is not None:
            self._expired_access = (self._access.expires_at, self._access.last_activity_at)
            self._access = None

    def _access_is_expired(self, access: _AccessToken, now: datetime) -> bool:
        return now >= access.expires_at or now >= access.last_activity_at + EXPIRE_AFTER_IDLE

    def _auth_required_error(self) -> AppError:
        if self._expired_access is not None:
            return self._auth_expired_error()
        return AppError(
            "etrade_auth_required",
            "E*TRADE OAuth is not authenticated.",
            status_code=401,
            details={"authenticated": False},
        )

    @staticmethod
    def _auth_expired_error() -> AppError:
        return AppError(
            "etrade_auth_expired",
            "E*TRADE OAuth tokens expired; start a new authorization.",
            status_code=401,
            details={"authenticated": False},
        )

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("OAuth clock must return a timezone-aware datetime")
        return value.astimezone(UTC)

    @staticmethod
    def _next_eastern_midnight(now: datetime) -> datetime:
        local_now = now.astimezone(EASTERN)
        next_day = local_now.date() + timedelta(days=1)
        return datetime.combine(next_day, time.min, tzinfo=EASTERN)
