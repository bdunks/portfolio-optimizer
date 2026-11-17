from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import override
from urllib.parse import parse_qs, urlsplit

import pytest
import requests
from requests.adapters import BaseAdapter
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.broker.etrade_oauth import EtradeOAuthService
from app.broker.etrade_read import EtradeReadAdapter
from app.db.models import (
    Account,
    Base,
    PolicyAllowedSecurity,
    PolicyRevision,
    PolicySleeve,
    Security,
)
from app.db.session import create_database_engine, make_session_factory
from app.services.broker_snapshot import EtradeReadOnlyBroker
from app.services.errors import AppError

NOW = datetime(2026, 11, 13, 16, 0, tzinfo=UTC)
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
ACCOUNT_KEY = "encoded-managed-account"
ACCOUNT_ID = 123456789
HISTORY_START = date(2024, 1, 2)
HISTORY_END = date(2026, 11, 13)
BALANCE_AS_OF_MS = 1_794_470_400_000
_MISSING = object()


class StubTransport(BaseAdapter):
    """Ordered HTTP fixture; exhaustion fails rather than reaching a live endpoint."""

    def __init__(
        self,
        responses: Sequence[requests.Response | Exception],
        *,
        before_send: Callable[[requests.PreparedRequest], None] | None = None,
    ) -> None:
        self.responses = list(responses)
        self.calls: list[requests.PreparedRequest] = []
        self.before_send = before_send

    @override
    def send(
        self,
        request: requests.PreparedRequest,
        stream: bool = False,
        timeout: float | tuple[float, float] | tuple[float, None] | None = None,
        verify: bool | str = True,
        cert: bytes | str | tuple[bytes | str, bytes | str] | None = None,
        proxies: Mapping[str, str] | None = None,
    ) -> requests.Response:
        if self.before_send is not None:
            self.before_send(request)
        self.calls.append(request)
        if not self.responses:
            raise AssertionError("Unexpected HTTP request; fixture has no live fallback")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if request.url is None:
            raise AssertionError("Fake request has no URL")
        response.request = request
        response.url = request.url
        return response

    @override
    def close(self) -> None:
        pass


def _json_text(value: object) -> str:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        fields: list[str] = []
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("Synthetic JSON keys must be strings")
            fields.append(f"{json.dumps(key)}:{_json_text(item)}")
        return "{" + ",".join(fields) + "}"
    if isinstance(value, list):
        return "[" + ",".join(_json_text(item) for item in value) + "]"
    return json.dumps(value, separators=(",", ":"))


def _response(payload: object) -> requests.Response:
    response = requests.Response()
    response.status_code = 200
    response._content = _json_text(payload).encode()
    response.encoding = "utf-8"
    response.headers["Content-Type"] = "application/json"
    return response


def _token_response(token: str, secret: str) -> requests.Response:
    response = requests.Response()
    response.status_code = 200
    response._content = (
        f"oauth_token={token}&oauth_token_secret={secret}&oauth_callback_confirmed=true".encode()
    )
    response.encoding = "utf-8"
    response.headers["Content-Type"] = "application/x-www-form-urlencoded"
    return response


def _adapter(
    responses: Sequence[requests.Response | Exception],
    *,
    before_send: Callable[[requests.PreparedRequest], None] | None = None,
) -> tuple[EtradeReadAdapter, StubTransport]:
    transport = StubTransport(
        [
            _token_response("request-token-test", "request-secret-test"),
            _token_response("access-token-test", "access-secret-test"),
            *responses,
        ],
        before_send=before_send,
    )
    oauth = EtradeOAuthService(
        "consumer-key-test",
        "consumer-secret-test",
        transport=transport,
        clock=lambda: NOW,
    )
    oauth.start()
    oauth.verify("123456")
    return (
        EtradeReadAdapter(
            oauth,
            environment="sandbox",
            clock=lambda: NOW,
            sleep=lambda _: None,
        ),
        transport,
    )


def _account(key: str = ACCOUNT_KEY, account_id: int = ACCOUNT_ID) -> dict[str, object]:
    return {
        "accountIdKey": key,
        "accountId": account_id,
        "accountName": f"Synthetic {key}",
        "accountType": "BROKERAGE",
        "taxTreatment": "TAXABLE",
    }


def _accounts(*rows: dict[str, object]) -> dict[str, object]:
    return {"AccountListResponse": {"Accounts": {"Account": list(rows)}}}


def _position(
    ticker: str = "AAA",
    *,
    position_id: str = "101",
    shares: Decimal = Decimal(1),
    product_id: object = _MISSING,
) -> dict[str, object]:
    product: dict[str, object] = {"securityType": "EQ", "cusip": "123456789"}
    if product_id is _MISSING:
        product["productId"] = {"symbol": ticker, "typeCode": "EQUITY"}
    else:
        product["productId"] = product_id
    return {
        "symbol": ticker,
        "positionId": position_id,
        "quantity": shares,
        "marketValue": Decimal("100.25"),
        "Product": product,
    }


def _portfolio(
    positions: Sequence[dict[str, object]], *, account_key: str = ACCOUNT_KEY
) -> dict[str, object]:
    return {
        "PortfolioResponse": {
            "AccountPortfolio": {"Position": list(positions), "accountIdKey": account_key}
        }
    }


def _lot(
    *,
    lot_id: str = "lot-aaa-1",
    shares: Decimal = Decimal(1),
    available: Decimal = Decimal("0.75"),
    total_cost: Decimal = Decimal("255.87"),
    acquired_ms: int = 1_772_168_400_000,
) -> dict[str, object]:
    return {
        "positionLotId": lot_id,
        "remainingQty": shares,
        "availableQty": available,
        "totalCost": total_cost,
        "acquiredDate": acquired_ms,
    }


def _detail(*lots: dict[str, object]) -> dict[str, object]:
    return {"PositionLotsResponse": {"PositionLot": list(lots)}}


def _transaction(
    *,
    transaction_type: str = "Bought",
    account_id: int = ACCOUNT_ID,
    ticker: str = "AAA",
    trade_date: date = date(2026, 11, 10),
) -> dict[str, object]:
    transaction_time = datetime.combine(trade_date, datetime.min.time(), tzinfo=UTC)
    delta = transaction_time - EPOCH
    timestamp_ms = delta.days * 86_400_000 + delta.seconds * 1_000
    return {
        "transactionId": "transaction-1",
        "accountId": account_id,
        "transactionType": transaction_type,
        "transactionDate": timestamp_ms,
        "amount": Decimal("-10.25"),
        "brokerage": {
            "product": {"symbol": ticker, "securityType": "EQ"},
            "quantity": Decimal(1),
            "settlementCurrency": "USD",
            "paymentCurrency": "USD",
        },
    }


def _history(*rows: dict[str, object]) -> dict[str, object]:
    return {
        "TransactionListResponse": {
            "Transaction": list(rows),
            "transactionCount": len(rows),
            "moreTransactions": False,
        }
    }


def _balance(
    *,
    account_id: int = ACCOUNT_ID,
    as_of: object = BALANCE_AS_OF_MS,
    cash_usd: Decimal = Decimal("1234.567890123456789"),
    settled_cash_usd: Decimal = Decimal("987.654321098765432"),
) -> dict[str, object]:
    return {
        "BalanceResponse": {
            "accountId": account_id,
            "asOfDate": as_of,
            "Computed": {
                "cashBalance": cash_usd,
                "settledCashForInvestment": settled_cash_usd,
                "cashAvailableForInvestment": Decimal("9999.99"),
                "marginBalance": Decimal("8888.88"),
            },
        }
    }


def _epoch_seconds(value: datetime) -> int:
    delta = value - EPOCH
    return delta.days * 86_400 + delta.seconds


def _quote(
    ticker: str,
    *,
    timestamp: int | None = None,
    status: str = "REALTIME",
) -> dict[str, object]:
    quote: dict[str, object] = {
        "Product": {"symbol": ticker},
        "All": {"bid": Decimal("10.01"), "ask": Decimal("10.03"), "lastTrade": Decimal("10.02")},
        "quoteStatus": status,
    }
    if timestamp is not None:
        quote["dateTimeUTC"] = timestamp
    return quote


def _quote_response(*rows: dict[str, object]) -> dict[str, object]:
    return {"QuoteResponse": {"QuoteData": list(rows)}}


def _http_responses(
    *,
    accounts_by_section: Sequence[Sequence[dict[str, object]]] | None = None,
    position_rows: Sequence[dict[str, object]] | None = None,
    lot_rows: Sequence[dict[str, object]] | None = None,
    transaction_rows: Sequence[dict[str, object]] = (),
    balance_source: object = BALANCE_AS_OF_MS,
    balance_cash_usd: Decimal = Decimal("1234.567890123456789"),
    balance_settled_cash_usd: Decimal = Decimal("987.654321098765432"),
    quote_rows: Sequence[dict[str, object]] = (),
    include_quote_response: bool = True,
    portfolio_account_key: str = ACCOUNT_KEY,
) -> list[requests.Response]:
    account = _account()
    account_sets = accounts_by_section or ((account,), (account,), (account,))
    if len(account_sets) != 3:
        raise ValueError("three account lists are required")
    positions = list(position_rows if position_rows is not None else (_position(),))
    lots = list(lot_rows if lot_rows is not None else (_lot(),))

    def account_id_for(rows: Sequence[dict[str, object]]) -> int:
        for row in rows:
            if row["accountIdKey"] == portfolio_account_key:
                account_id = row.get("accountId")
                if type(account_id) is not int:
                    raise ValueError("synthetic account row needs an integer account ID")
                return account_id
        return ACCOUNT_ID

    balance_account_id = account_id_for(account_sets[2])

    responses = [
        _response(_accounts(*account_sets[0])),
        _response(_portfolio(positions, account_key=portfolio_account_key)),
    ]
    if positions:
        responses.append(_response(_detail(*lots)))
    responses.extend(
        (
            _response(_accounts(*account_sets[1])),
            _response(_history(*transaction_rows)),
            _response(_accounts(*account_sets[2])),
            _response(
                _balance(
                    account_id=balance_account_id,
                    as_of=balance_source,
                    cash_usd=balance_cash_usd,
                    settled_cash_usd=balance_settled_cash_usd,
                )
            ),
        )
    )
    if include_quote_response:
        responses.append(_response(_quote_response(*quote_rows)))
    return responses


def _database(tmp_path: Path) -> tuple[Engine, sessionmaker[Session]]:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'snapshot-composition.sqlite3'}")
    Base.metadata.create_all(engine)
    return engine, make_session_factory(engine)


def _seed_account(factory: sessionmaker[Session], account_key: str = ACCOUNT_KEY) -> None:
    with factory.begin() as session:
        session.add(
            Account(
                id=1,
                broker_account_id_key=account_key,
                display_name="Previously bound account",
                account_type="BROKERAGE",
                tax_treatment="TAXABLE",
                cash_usd=Decimal(1),
                settled_buying_power_usd=Decimal(1),
                source="ETRADE",
                as_of=NOW,
            )
        )


def _seed_policy(
    factory: sessionmaker[Session],
    *,
    status: str,
    revision_id: str,
    candidates: Sequence[tuple[str, bool, str]],
) -> None:
    with factory.begin() as session:
        session.add(
            PolicyRevision(
                id=revision_id,
                revision_number=1 if status == "ACTIVE" else 0,
                status=status,
                created_at=NOW,
            )
        )
        session.add(
            PolicySleeve(
                policy_revision_id=revision_id,
                sleeve_key="replacement-sleeve",
                display_name="Replacement sleeve",
                sort_order=0,
                target_pct=Decimal(100),
                drift_band_pp=Decimal(0),
            )
        )
        session.flush()
        seen_tickers = set(session.scalars(select(Security.ticker)).all())
        for ticker, _, _ in candidates:
            if ticker not in seen_tickers:
                session.add(Security(ticker=ticker, asset_type="ETF"))
                seen_tickers.add(ticker)
        session.flush()
        for ticker, enabled, replacement_set_id in candidates:
            session.add(
                PolicyAllowedSecurity(
                    policy_revision_id=revision_id,
                    sleeve_key="replacement-sleeve",
                    ticker=ticker,
                    replacement_set_id=replacement_set_id,
                    priority=0,
                    enabled=enabled,
                )
            )


def _composer(
    adapter: EtradeReadAdapter,
    factory: sessionmaker[Session],
) -> EtradeReadOnlyBroker:
    return EtradeReadOnlyBroker(
        adapter,
        factory,
        history_start_date=HISTORY_START,
        history_end_date=HISTORY_END,
    )


def _api_urls(transport: StubTransport) -> list[str]:
    return [request.url for request in transport.calls[2:] if request.url is not None]


def test_composes_exact_complete_snapshot_and_provenance_with_bound_account_and_candidates(
    tmp_path: Path,
) -> None:
    engine, factory = _database(tmp_path)
    try:
        _seed_account(factory, "bound-account")
        _seed_policy(
            factory,
            status="ACTIVE",
            revision_id="active-policy",
            candidates=(
                ("IVV", True, "primary"),
                ("VTI", True, "primary"),
                ("VTI", True, "secondary"),
                ("SPY", False, "disabled"),
            ),
        )
        _seed_policy(
            factory,
            status="SUPERSEDED",
            revision_id="old-policy",
            candidates=(("VOO", True, "old"),),
        )

        def assert_session_closed(_: requests.PreparedRequest) -> None:
            checkedout = getattr(engine.pool, "checkedout", None)
            assert callable(checkedout)
            assert checkedout() == 0

        quote_time = _epoch_seconds(NOW - timedelta(seconds=15))
        account_rows = (_account("first-listed-account", 111), _account("bound-account", 222))
        responses = _http_responses(
            accounts_by_section=(account_rows, account_rows, account_rows),
            portfolio_account_key="bound-account",
            transaction_rows=(_transaction(account_id=222),),
            quote_rows=tuple(
                _quote(ticker, timestamp=quote_time) for ticker in ("AAA", "IVV", "VTI")
            ),
        )
        adapter, transport = _adapter(responses, before_send=assert_session_closed)
        snapshot = _composer(adapter, factory).fetch_snapshot()

        assert _composer(adapter, factory).mode == "etrade"
        assert snapshot.source == "ETRADE"
        assert snapshot.account_id_key == "bound-account"
        assert snapshot.as_of == datetime(2026, 11, 12, 8, 0, tzinfo=UTC)
        assert snapshot.balance_as_of_source_ms == BALANCE_AS_OF_MS
        assert snapshot.balance_received_at == NOW
        assert snapshot.cash_usd == Decimal("1234.567890123456789")
        assert snapshot.settled_buying_power_usd == Decimal("987.654321098765432")
        assert snapshot.coverage.transaction_history_start_date == HISTORY_START
        assert snapshot.coverage.transaction_history_end_date == HISTORY_END
        assert snapshot.transactions[0].trade_date == date(2026, 11, 10)
        assert [quote.ticker for quote in snapshot.quotes] == ["AAA", "IVV", "VTI"]
        assert snapshot.quotes[0].as_of == NOW - timedelta(seconds=15)
        assert snapshot.quotes[0].quality == "good"

        assert len(snapshot.positions) == 1
        assert snapshot.positions[0].shares == Decimal(1)
        assert snapshot.broker_position_metadata[0].ticker == "AAA"
        assert snapshot.broker_position_metadata[0].broker_position_id == "101"
        assert snapshot.broker_position_metadata[0].broker_product_id == {
            "symbol": "AAA",
            "typeCode": "EQUITY",
        }
        assert snapshot.broker_position_metadata[0].as_of == NOW
        assert snapshot.lots[0].broker_lot_id == "lot-aaa-1"
        assert snapshot.lots[0].shares == Decimal(1)
        assert snapshot.lots[0].available_shares == Decimal("0.75")
        assert snapshot.lots[0].as_of == NOW
        lot_metadata = snapshot.broker_lot_metadata[0]
        assert lot_metadata.broker_position_id == "101"
        assert lot_metadata.total_cost_usd == Decimal("255.87")
        assert lot_metadata.total_cost_source == Decimal("255.87")
        assert lot_metadata.reserved_shares == Decimal("0.25")
        assert lot_metadata.acquired_date_source == 1_772_168_400_000

        urls = _api_urls(transport)
        assert any("/accounts/bound-account/portfolio" in url for url in urls)
        assert any("/accounts/bound-account/transactions" in url for url in urls)
        assert any("/accounts/bound-account/balance" in url for url in urls)
        assert not any("first-listed-account" in url for url in urls)
        quote_url = next(url for url in urls if "/market/quote/" in url)
        requested_symbols = urlsplit(quote_url).path.rsplit("/", maxsplit=1)[-1].split(",")
        assert requested_symbols == ["AAA", "IVV", "VTI"]
        transaction_url = next(url for url in urls if "/transactions?" in url)
        assert parse_qs(urlsplit(transaction_url).query)["startDate"] == ["01022024"]
        assert parse_qs(urlsplit(transaction_url).query)["endDate"] == ["11132026"]
        assert transport.responses == []
    finally:
        engine.dispose()


def test_empty_portfolio_and_history_compose_without_demo_fills_or_quote_http(
    tmp_path: Path,
) -> None:
    engine, factory = _database(tmp_path)
    try:
        responses = _http_responses(
            position_rows=(),
            lot_rows=(),
            transaction_rows=(),
            include_quote_response=False,
        )
        adapter, transport = _adapter(responses)
        snapshot = _composer(adapter, factory).fetch_snapshot()

        assert snapshot.positions == []
        assert snapshot.lots == []
        assert snapshot.transactions == []
        assert snapshot.quotes == []
        assert snapshot.source == "ETRADE"
        assert snapshot.coverage.positions is True
        assert snapshot.coverage.lots is True
        assert snapshot.coverage.transactions is True
        assert snapshot.coverage.quotes is True
        assert not any("/market/quote/" in url for url in _api_urls(transport))
        assert transport.responses == []
    finally:
        engine.dispose()


def test_unbound_single_brokerage_account_is_selected_and_explicit_bounds_are_coverage(
    tmp_path: Path,
) -> None:
    engine, factory = _database(tmp_path)
    try:
        adapter, transport = _adapter(
            _http_responses(
                transaction_rows=(_transaction(trade_date=date(2026, 11, 10)),),
                quote_rows=(_quote("AAA", timestamp=_epoch_seconds(NOW)),),
            )
        )
        snapshot = _composer(adapter, factory).fetch_snapshot()

        assert snapshot.account_id_key == ACCOUNT_KEY
        assert snapshot.coverage.transaction_history_start_date == HISTORY_START
        assert snapshot.coverage.transaction_history_end_date == HISTORY_END
        assert snapshot.transactions[0].trade_date == date(2026, 11, 10)
        transaction_url = next(url for url in _api_urls(transport) if "/transactions?" in url)
        query = parse_qs(urlsplit(transaction_url).query)
        assert query["startDate"] == ["01022024"]
        assert query["endDate"] == ["11132026"]
    finally:
        engine.dispose()


def test_plain_account_id_change_between_sections_is_rejected(tmp_path: Path) -> None:
    engine, factory = _database(tmp_path)
    try:
        same_key_changed_id = (
            (_account(ACCOUNT_KEY, 123),),
            (_account(ACCOUNT_KEY, 456),),
            (_account(ACCOUNT_KEY, 456),),
        )
        adapter, _ = _adapter(
            _http_responses(
                accounts_by_section=same_key_changed_id,
                transaction_rows=(_transaction(account_id=456),),
                quote_rows=(_quote("AAA", timestamp=_epoch_seconds(NOW)),),
            )
        )
        with pytest.raises(AppError) as captured:
            _composer(adapter, factory).fetch_snapshot()
        assert captured.value.code == "etrade_read_cross_section_account_mismatch"
    finally:
        engine.dispose()


def test_later_section_cannot_switch_away_from_the_first_resolved_account(tmp_path: Path) -> None:
    engine, factory = _database(tmp_path)
    try:
        adapter, _ = _adapter(
            _http_responses(
                accounts_by_section=(
                    (_account("first-account", 111),),
                    (_account("different-account", 222),),
                    (_account("different-account", 222),),
                ),
                portfolio_account_key="first-account",
                transaction_rows=(_transaction(account_id=222),),
            )
        )
        with pytest.raises(AppError) as captured:
            _composer(adapter, factory).fetch_snapshot()
        assert captured.value.code == "etrade_read_account_not_found"
    finally:
        engine.dispose()


def test_incomplete_history_is_rejected_even_when_pages_return_successfully(tmp_path: Path) -> None:
    engine, factory = _database(tmp_path)
    try:
        unknown = _transaction(transaction_type="Option Assignment")
        adapter, _ = _adapter(
            _http_responses(
                transaction_rows=(unknown,),
                quote_rows=(_quote("AAA", timestamp=_epoch_seconds(NOW)),),
            )
        )
        with pytest.raises(AppError) as captured:
            _composer(adapter, factory).fetch_snapshot()
        assert captured.value.code == "incomplete_transaction_history"
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("quote_rows", "expected_code"),
    [
        ((), "incomplete_quote_coverage"),
        (
            (_quote("AAA", timestamp=_epoch_seconds(NOW - timedelta(minutes=15, seconds=1))),),
            "incomplete_quote_coverage",
        ),
        (
            (_quote("AAA", timestamp=_epoch_seconds(NOW), status="DELAYED"),),
            "incomplete_quote_coverage",
        ),
    ],
)
def test_missing_stale_and_unusable_quotes_are_rejected(
    tmp_path: Path, quote_rows: Sequence[dict[str, object]], expected_code: str
) -> None:
    engine, factory = _database(tmp_path)
    try:
        adapter, _ = _adapter(_http_responses(quote_rows=quote_rows))
        with pytest.raises(AppError) as captured:
            _composer(adapter, factory).fetch_snapshot()
        assert captured.value.code == expected_code
    finally:
        engine.dispose()


@pytest.mark.parametrize("source", [-1, True, 10**30])
def test_invalid_or_out_of_range_balance_milliseconds_are_rejected(
    tmp_path: Path, source: object
) -> None:
    engine, factory = _database(tmp_path)
    try:
        adapter, _ = _adapter(
            _http_responses(
                balance_source=source,
                quote_rows=(_quote("AAA", timestamp=_epoch_seconds(NOW)),),
            )
        )
        with pytest.raises(AppError) as captured:
            _composer(adapter, factory).fetch_snapshot()
        assert captured.value.code == "etrade_read_balance_as_of_invalid"
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (date(2026, 1, 2), date(2026, 1, 1)),
        (datetime(2026, 1, 1, tzinfo=UTC), date(2026, 1, 2)),
    ],
)
def test_history_bounds_must_be_explicit_ordered_calendar_dates(
    tmp_path: Path, start: date, end: date
) -> None:
    engine, factory = _database(tmp_path)
    adapter, _ = _adapter(())
    try:
        with pytest.raises(ValueError, match="explicit ordered dates"):
            EtradeReadOnlyBroker(
                adapter,
                factory,
                history_start_date=start,
                history_end_date=end,
            )
    finally:
        engine.dispose()
