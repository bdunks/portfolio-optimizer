from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import override
from urllib.parse import parse_qs, urlsplit

import pytest
import requests
from requests.adapters import BaseAdapter
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.broker.etrade_oauth import EtradeOAuthService
from app.broker.etrade_read import EtradeReadAdapter
from app.db.models import Account, Base, CurrentQuote
from app.domain.financial_inputs import QuoteInput
from app.optimizer.core import _quote_is_current
from app.schemas import AllowedSecurityInput, PositionInput
from app.services.errors import AppError
from tests.optimizer_quality_cases import build_small_quality_case

ACCOUNT_KEY = "encoded-account-key"
ACCOUNT_ID = 123456789
NOW = datetime(2026, 11, 13, 16, 0, tzinfo=UTC)
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_NOW_SECONDS = int((NOW - _EPOCH).total_seconds())
_MISSING = object()


class FixedClock:
    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class StubAdapter(BaseAdapter):
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
            raise AssertionError("Unexpected HTTP request; fake transport has no live fallback")
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        if request.url is None:
            raise AssertionError("Fake request was missing its URL")
        result.request = request
        result.url = request.url
        return result

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


def _response(
    payload: object | None = None,
    *,
    status: int = 200,
    raw_body: str | None = None,
) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    body = raw_body if raw_body is not None else _json_text(payload)
    response._content = body.encode()
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
    clock: FixedClock | None = None,
    quote_max_age: timedelta = timedelta(minutes=15),
    configured_account_id_key: str | None = ACCOUNT_KEY,
    before_send: Callable[[requests.PreparedRequest], None] | None = None,
) -> tuple[EtradeReadAdapter, EtradeOAuthService, StubAdapter]:
    fixed_clock = clock or FixedClock()
    transport = StubAdapter(
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
        clock=fixed_clock,
    )
    oauth.start()
    oauth.verify("123456")
    reader = EtradeReadAdapter(
        oauth,
        environment="sandbox",
        configured_account_id_key=configured_account_id_key,
        clock=fixed_clock,
        quote_max_age=quote_max_age,
    )
    return reader, oauth, transport


def _account_payload(account_id: object = ACCOUNT_ID) -> dict[str, object]:
    return {
        "AccountListResponse": {
            "Accounts": {
                "Account": [
                    {
                        "accountIdKey": ACCOUNT_KEY,
                        "accountId": account_id,
                        "accountName": "Synthetic brokerage",
                        "accountType": "BROKERAGE",
                    }
                ]
            }
        }
    }


def _balance_payload(
    *,
    account_id: object = ACCOUNT_ID,
    as_of: object = 1_797_912_345_678,
    computed: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "BalanceResponse": {
            "accountId": account_id,
            "asOfDate": as_of,
            "Computed": computed
            or {
                "cashBalance": Decimal("1234.567890123456789"),
                "settledCashForInvestment": Decimal("987.654321098765432"),
                "cashAvailableForInvestment": Decimal("7777.77"),
                "marginBalance": Decimal("8888.88"),
                "fundsWithdrawing": Decimal("9999.99"),
            },
        }
    }


def _position(ticker: str) -> PositionInput:
    return PositionInput(
        ticker=ticker,
        asset_type="EQUITY",
        shares=Decimal(1),
        market_value_usd=Decimal(10),
    )


def _candidate(ticker: str, *, enabled: bool = True) -> AllowedSecurityInput:
    return AllowedSecurityInput(ticker=ticker, sleeve_key="configured-sleeve", enabled=enabled)


def _epoch_seconds(value: datetime) -> int:
    delta = value - _EPOCH
    return delta.days * 86_400 + delta.seconds


def _quote(
    ticker: str,
    *,
    date_time_utc: object = _NOW_SECONDS,
    status: object = "REALTIME",
    bid: object = Decimal("10.01"),
    ask: object = Decimal("10.03"),
    last: object = Decimal("10.02"),
) -> dict[str, object]:
    row: dict[str, object] = {
        "Product": {"symbol": ticker},
        "All": {"bid": bid, "ask": ask, "lastTrade": last},
        "quoteStatus": status,
    }
    if date_time_utc is not _MISSING:
        row["dateTimeUTC"] = date_time_utc
    return row


def _quote_payload(*rows: dict[str, object]) -> dict[str, object]:
    return {"QuoteResponse": {"QuoteData": list(rows)}}


def _api_calls(transport: StubAdapter) -> list[requests.PreparedRequest]:
    return transport.calls[2:]


def _request_url(request: requests.PreparedRequest) -> str:
    value = request.url
    if isinstance(value, bytes):
        return value.decode("ascii")
    if isinstance(value, str):
        return value
    raise AssertionError("Prepared request was missing its URL")


def _header_text(request: requests.PreparedRequest) -> str:
    value = request.headers["Authorization"]
    return value.decode("ascii") if isinstance(value, bytes) else value


def _raise_code(operation: Callable[[], object], code: str) -> AppError:
    assert callable(operation)
    with pytest.raises(AppError) as captured:
        operation()
    assert captured.value.code == code
    return captured.value


def test_balances_preserve_exact_distinct_values_identity_metadata_and_never_publish() -> None:
    quote_response = _quote_payload(_quote("AAA"))
    reader, _, transport = _adapter(
        [
            _response(_account_payload()),
            _response(_balance_payload()),
            _response(quote_response),
        ]
    )
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        balances = reader.fetch_balances()
        coverage = reader.get_quotes([_position("AAA")], [])

        assert balances.account.account_id_key == ACCOUNT_KEY
        assert balances.account.account_id == str(ACCOUNT_ID)
        assert balances.cash_usd == Decimal("1234.567890123456789")
        assert balances.settled_cash_for_investment_usd == Decimal("987.654321098765432")
        assert balances.cash_usd != balances.settled_cash_for_investment_usd
        assert balances.as_of_source == 1_797_912_345_678
        assert balances.received_at == NOW
        computed_source = balances.source_fields["Computed"]
        assert isinstance(computed_source, Mapping)
        assert computed_source["cashBalance"] == balances.cash_usd
        assert computed_source["settledCashForInvestment"] == (
            balances.settled_cash_for_investment_usd
        )
        assert coverage.complete
        assert coverage.as_quote_inputs(1)[0].last_usd == Decimal("10.02")

        calls = _api_calls(transport)
        assert len(calls) == 3
        assert calls[0].url == "https://apisb.etrade.com/v1/accounts/list"
        assert calls[1].url == (
            "https://apisb.etrade.com/v1/accounts/encoded-account-key/balance"
            "?instType=BROKERAGE&realTimeNAV=true"
        )
        assert urlsplit(_request_url(calls[2])).path == "/v1/market/quote/AAA"
        assert parse_qs(urlsplit(_request_url(calls[2])).query) == {"detailFlag": ["ALL"]}
        assert all(call.method == "GET" for call in calls)
        assert all(_header_text(call).startswith("OAuth ") for call in calls)
        assert all("access-secret-test" not in str(call.headers) for call in calls)

        with Session(engine) as session:
            assert session.scalars(select(Account)).all() == []
            assert session.scalars(select(CurrentQuote)).all() == []
    finally:
        engine.dispose()


def test_balance_identity_mismatch_and_missing_identity_fail_closed() -> None:
    mismatch, _, mismatch_transport = _adapter(
        [_response(_account_payload()), _response(_balance_payload(account_id=999))]
    )
    _raise_code(mismatch.fetch_balances, "etrade_read_balance_account_mismatch")
    assert len(_api_calls(mismatch_transport)) == 2

    missing_account = dict(_account_payload())
    account_list = missing_account["AccountListResponse"]
    assert isinstance(account_list, dict)
    accounts = account_list["Accounts"]
    assert isinstance(accounts, dict)
    rows = accounts["Account"]
    assert isinstance(rows, list)
    rows[0].pop("accountId")
    missing, _, missing_transport = _adapter([_response(missing_account)])
    _raise_code(missing.fetch_balances, "etrade_read_balance_account_identity_missing")
    assert len(_api_calls(missing_transport)) == 1


@pytest.mark.parametrize(
    ("payload", "expected_code"),
    [
        ({"balanceResponse": {}}, "etrade_read_balances_malformed"),
        (
            _balance_payload(computed={"settledCashForInvestment": Decimal(1)}),
            "etrade_read_balance_field_missing",
        ),
        (
            _balance_payload(as_of="1797912345678"),
            "etrade_read_balance_as_of_invalid",
        ),
        (
            _balance_payload(as_of=Decimal("1797912345678.5")),
            "etrade_read_balance_as_of_invalid",
        ),
        (
            _balance_payload(computed={"cashBalance": "NaN", "settledCashForInvestment": "1"}),
            "etrade_read_quantity_invalid",
        ),
    ],
)
def test_balance_required_documented_shape_and_values_are_validated(
    payload: dict[str, object], expected_code: str
) -> None:
    reader, _, _ = _adapter([_response(_account_payload()), _response(payload)])
    _raise_code(reader.fetch_balances, expected_code)


def test_quote_union_is_batched_at_twenty_five_and_decodes_into_optimizer_guard_input() -> None:
    held_symbols = [f"H{index:02d}" for index in range(25)]
    first_batch = [_quote(symbol) for symbol in held_symbols]
    reader, _, transport = _adapter(
        [
            _response(_quote_payload(*first_batch)),
            _response(_quote_payload(_quote("REPLACEMENT"))),
        ]
    )
    held = [_position(symbol) for symbol in held_symbols]
    candidates = [
        _candidate("H00"),
        _candidate("REPLACEMENT"),
        _candidate("DISABLED", enabled=False),
    ]

    result = reader.get_quotes(held, candidates)

    assert result.complete
    assert result.requested_symbols == (*held_symbols, "REPLACEMENT")
    assert "DISABLED" not in result.requested_symbols
    assert len(result.records) == 26
    batch_sizes = [
        len(urlsplit(_request_url(call)).path.rsplit("/", maxsplit=1)[-1].split(","))
        for call in _api_calls(transport)
    ]
    assert batch_sizes == [25, 1]
    assert all(
        parse_qs(urlsplit(_request_url(call)).query) == {"detailFlag": ["ALL"]}
        for call in _api_calls(transport)
    )
    assert all(_header_text(call).startswith("OAuth ") for call in _api_calls(transport))
    record = result.records[-1]
    assert record.ticker == "REPLACEMENT"
    assert record.quote_status_source == "REALTIME"
    assert record.date_time_utc_source == _NOW_SECONDS
    assert record.as_of == NOW
    assert record.bid_usd == Decimal("10.01")
    assert record.ask_usd == Decimal("10.03")
    assert record.last_usd == Decimal("10.02")

    quality_case = build_small_quality_case("fee-consolidation", 20261113).inputs
    quote_input = result.as_quote_inputs(quality_case.source_generation)[-1]
    assert isinstance(quote_input, QuoteInput)
    assert quote_input.source == "ETRADE"
    assert quote_input.quality == "good"
    optimizer_inputs = replace(
        quality_case,
        account=replace(quality_case.account, as_of=quote_input.as_of),
        quotes=(quote_input,),
    )
    assert _quote_is_current(optimizer_inputs, quote_input)


def test_empty_missing_stale_and_unusable_quote_coverage_is_explicit() -> None:
    empty_reader, _, empty_transport = _adapter([])
    empty = empty_reader.get_quotes([], [_candidate("IGNORED", enabled=False)])
    assert empty.complete
    assert empty.requested_symbols == ()
    assert empty.records == ()
    assert _api_calls(empty_transport) == []

    old_time = _epoch_seconds(NOW - timedelta(minutes=15, seconds=1))
    reader, _, _ = _adapter(
        [
            _response(
                _quote_payload(
                    _quote("PRESENT", date_time_utc=old_time),
                    _quote("NO-TIME", date_time_utc=_MISSING),
                )
            )
        ]
    )
    result = reader.get_quotes(
        [_position("PRESENT"), _position("MISSING"), _position("NO-TIME")], []
    )
    assert not result.complete
    assert result.missing_symbols == ("MISSING",)
    assert result.stale_symbols == ("PRESENT",)
    assert result.unusable_symbols == ("NO-TIME",)
    assert result.records[0].quality == "stale"
    assert result.records[1].as_of is None
    assert result.records[1].date_time_utc_source is None
    assert [quote.ticker for quote in result.as_quote_inputs(4)] == ["PRESENT"]


def test_quote_freshness_boundary_future_and_bad_timestamps_fail_closed() -> None:
    cases: list[tuple[object, str]] = [
        (_epoch_seconds(NOW - timedelta(minutes=15)), "good"),
        (_epoch_seconds(NOW - timedelta(minutes=15, seconds=1)), "stale"),
        (_epoch_seconds(NOW + timedelta(seconds=1)), "stale"),
        ("not-an-epoch", "unusable"),
        (Decimal("1797912345.5"), "unusable"),
        (_MISSING, "unusable"),
    ]
    for index, (raw_time, expected_quality) in enumerate(cases):
        reader, _, _ = _adapter(
            [_response(_quote_payload(_quote(f"Q{index}", date_time_utc=raw_time)))]
        )
        coverage = reader.get_quotes([_position(f"Q{index}")], [])
        record = coverage.records[0]
        assert record.date_time_utc_source == (None if raw_time is _MISSING else raw_time)
        assert record.quality == expected_quality
        assert coverage.complete is (expected_quality == "good")

    custom_reader, _, _ = _adapter(
        [
            _response(
                _quote_payload(
                    _quote("CUSTOM", date_time_utc=_epoch_seconds(NOW - timedelta(minutes=2)))
                )
            )
        ],
        quote_max_age=timedelta(minutes=1),
    )
    custom_coverage = custom_reader.get_quotes([_position("CUSTOM")], [])
    assert custom_coverage.stale_symbols == ("CUSTOM",)


def test_only_realtime_status_and_valid_prices_are_good() -> None:
    statuses = (
        "DELAYED",
        "CLOSING",
        "INVALID",
        "EH_REALTIME",
        "EH_BEFORE_OPEN",
        "EH_CLOSED",
        "INDICATIVE_REALTIME",
        "UNRECOGNIZED",
        None,
    )
    rows = [_quote(f"S{index}", status=status) for index, status in enumerate(statuses)]
    rows.extend(
        (
            _quote("ZERO", bid=Decimal(0)),
            _quote("CROSSED", bid=Decimal(11), ask=Decimal(10)),
            _quote("NO-PRICE", bid=None, ask=None, last=None),
        )
    )
    reader, _, _ = _adapter([_response(_quote_payload(*rows))])
    held_status_symbols = [_position(f"S{index}") for index in range(len(statuses))]
    held_status_symbols.extend((_position("ZERO"), _position("CROSSED"), _position("NO-PRICE")))
    result = reader.get_quotes(held_status_symbols, [])

    assert not result.complete
    assert len(result.unusable_symbols) == len(rows)
    assert all(record.quality == "unusable" for record in result.records)
    assert [record.quote_status_source for record in result.records[: len(statuses)]] == list(
        statuses
    )
    assert result.records[len(statuses)].bid_usd == Decimal(0)

    quality_case = build_small_quality_case("fee-consolidation", 20261113).inputs
    rejected_quote = result.records[0].as_quote_input(quality_case.source_generation)
    assert rejected_quote is not None
    optimizer_inputs = replace(
        quality_case,
        account=replace(quality_case.account, as_of=rejected_quote.as_of),
        quotes=(rejected_quote,),
    )
    assert not _quote_is_current(optimizer_inputs, rejected_quote)


def test_duplicate_foreign_malformed_and_batch_cap_responses_fail_closed() -> None:
    duplicate_reader, _, _ = _adapter([_response(_quote_payload(_quote("AAA"), _quote("AAA")))])
    _raise_code(
        lambda: duplicate_reader.get_quotes([_position("AAA")], []),
        "etrade_read_duplicate_quote",
    )

    foreign_reader, _, _ = _adapter([_response(_quote_payload(_quote("OTHER")))])
    _raise_code(
        lambda: foreign_reader.get_quotes([_position("AAA")], []),
        "etrade_read_quote_symbol_foreign",
    )

    malformed_reader, _, _ = _adapter(
        [_response(_quote_payload({"Product": {"symbol": "AAA"}, "All": {"bid": "bad"}}))]
    )
    _raise_code(
        lambda: malformed_reader.get_quotes([_position("AAA")], []),
        "etrade_read_quote_price_missing",
    )

    bad_price_reader, _, _ = _adapter(
        [
            _response(
                _quote_payload(
                    _quote("AAA", last="not-money"),
                )
            )
        ]
    )
    _raise_code(
        lambda: bad_price_reader.get_quotes([_position("AAA")], []),
        "etrade_read_quantity_invalid",
    )

    bounded_reader, _, bounded_transport = _adapter([])
    excessive = [_position(f"X{index:04d}") for index in range(2501)]
    _raise_code(
        lambda: bounded_reader.get_quotes(excessive, []),
        "etrade_read_quote_batch_limit",
    )
    assert _api_calls(bounded_transport) == []


@pytest.mark.parametrize("failure_kind", ["rate-limit", "timeout", "malformed"])
def test_later_quote_batch_failure_returns_no_partial_coverage_or_retry(
    failure_kind: str,
) -> None:
    first_batch = [_quote(f"B{index:02d}") for index in range(25)]
    if failure_kind == "rate-limit":
        failure: requests.Response | Exception = _response(status=429)
    elif failure_kind == "timeout":
        failure = requests.Timeout("synthetic timeout")
    else:
        failure = _response({"QuoteResponse": {}})
    reader, _, transport = _adapter([_response(_quote_payload(*first_batch)), failure])
    held = [_position(f"B{index:02d}") for index in range(25)] + [_position("LAST")]

    expected_code = {
        "rate-limit": "etrade_read_http_error",
        "timeout": "etrade_read_transport_error",
        "malformed": "etrade_read_quotes_malformed",
    }[failure_kind]
    _raise_code(lambda: reader.get_quotes(held, []), expected_code)
    assert len(_api_calls(transport)) == 2


def test_quote_aging_during_later_batch_downgrades_earlier_batch_at_completion() -> None:
    clock = FixedClock()
    quote_requests = 0

    def advance_during_second_batch(request: requests.PreparedRequest) -> None:
        nonlocal quote_requests
        if request.url is not None and "/market/quote/" in request.url:
            quote_requests += 1
            if quote_requests == 2:
                clock.now += timedelta(seconds=1)

    first_batch = [
        _quote(f"B{index:02d}", date_time_utc=_epoch_seconds(NOW - timedelta(minutes=15)))
        for index in range(25)
    ]
    reader, _, _ = _adapter(
        [_response(_quote_payload(*first_batch)), _response(_quote_payload(_quote("LAST")))],
        clock=clock,
        before_send=advance_during_second_batch,
    )
    held = [_position(f"B{index:02d}") for index in range(25)] + [_position("LAST")]

    coverage = reader.get_quotes(held, [])

    first_quote = coverage.records[0]
    assert first_quote.received_at == NOW
    assert coverage.completed_at == NOW + timedelta(seconds=1)
    assert first_quote.quality == "stale"
    assert coverage.stale_symbols == tuple(f"B{index:02d}" for index in range(25))
    assert not coverage.complete
    quote_input = first_quote.as_quote_input(sync_generation=1)
    assert quote_input is not None
    quality_case = build_small_quality_case("fee-consolidation", 20261113).inputs
    optimizer_inputs = replace(
        quality_case,
        account=replace(quality_case.account, as_of=coverage.completed_at),
        quotes=(quote_input,),
    )
    assert not _quote_is_current(optimizer_inputs, quote_input)


def test_held_quote_requires_last_while_candidate_shapes_match_optimizer_marks() -> None:
    reader, _, _ = _adapter(
        [
            _response(
                _quote_payload(
                    _quote("HELD", last=None),
                    _quote("OVERLAP", last=None),
                    _quote("SPREAD", last=None),
                    _quote("LAST", bid=None, ask=None),
                    _quote("BID_ONLY", ask=None, last=None),
                    _quote("ASK_ONLY", bid=None, last=None),
                )
            )
        ]
    )
    coverage = reader.get_quotes(
        [_position("HELD"), _position("OVERLAP")],
        [
            _candidate("OVERLAP"),
            _candidate("SPREAD"),
            _candidate("LAST"),
            _candidate("BID_ONLY"),
            _candidate("ASK_ONLY"),
        ],
    )

    assert coverage.requested_symbols == (
        "HELD",
        "OVERLAP",
        "SPREAD",
        "LAST",
        "BID_ONLY",
        "ASK_ONLY",
    )
    assert coverage.complete is False
    assert coverage.unusable_symbols == ("HELD", "OVERLAP", "BID_ONLY", "ASK_ONLY")
    records = {record.ticker: record for record in coverage.records}
    assert records["HELD"].quality == "unusable"
    assert records["OVERLAP"].quality == "unusable"
    assert records["SPREAD"].quality == "good"
    assert records["LAST"].quality == "good"
    assert records["BID_ONLY"].quality == "unusable"
    assert records["ASK_ONLY"].quality == "unusable"

    quality_case = build_small_quality_case("fee-consolidation", 20261113).inputs
    quote_inputs = coverage.as_quote_inputs(quality_case.source_generation)
    optimizer_inputs = replace(
        quality_case,
        account=replace(quality_case.account, as_of=coverage.completed_at),
        quotes=quote_inputs,
    )
    current_by_ticker = {
        ticker: _quote_is_current(optimizer_inputs, quote_input)
        for ticker, quote_input in ((quote.ticker, quote) for quote in quote_inputs)
    }
    assert current_by_ticker == {
        "HELD": False,
        "OVERLAP": False,
        "SPREAD": True,
        "LAST": True,
        "BID_ONLY": False,
        "ASK_ONLY": False,
    }
