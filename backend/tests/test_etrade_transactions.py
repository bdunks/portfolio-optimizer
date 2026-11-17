from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import override
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
import requests
from requests.adapters import BaseAdapter

from app.broker.etrade_oauth import EtradeOAuthService
from app.broker.etrade_read import EtradeReadAdapter, EtradeTransactionHistory
from app.domain.allocation import AllocationPolicy
from app.domain.financial_inputs import (
    AccountInput,
    FinancialInputs,
    InputSourceMetadata,
    PolicyInput,
    PolicySettings,
)
from app.domain.financial_inputs import (
    TransactionInput as DomainTransactionInput,
)
from app.domain.wash import ProposedBuy, ProposedLotSale, assess_proposed_buys, assess_wash_sales
from app.services.errors import AppError

ACCOUNT_KEY = "encoded-account-key"
ACCOUNT_ID = 123456789
TRADE_DATE = date(2026, 11, 13)
NOW = datetime(2026, 11, 13, 16, 0, tzinfo=UTC)
_MISSING = object()


class FixedClock:
    def __call__(self) -> datetime:
        return NOW


class FakeTransport(BaseAdapter):
    def __init__(self, responses: Sequence[requests.Response | Exception]) -> None:
        self.responses = list(responses)
        self.calls: list[requests.PreparedRequest] = []

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
        self.calls.append(request)
        if not self.responses:
            raise AssertionError("Unexpected HTTP request; fake transport has no live fallback")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if request.url is None:
            raise AssertionError("Fake request was missing its URL")
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
                raise TypeError("Synthetic JSON object keys must be strings")
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
) -> tuple[EtradeReadAdapter, FakeTransport]:
    transport = FakeTransport(
        [
            _token_response("request-token-test", "request-secret-test"),
            _token_response("access-token-test", "access-secret-test"),
            *responses,
        ]
    )
    oauth = EtradeOAuthService(
        "consumer-key-test",
        "consumer-secret-test",
        transport=transport,
        clock=FixedClock(),
    )
    oauth.start()
    oauth.verify("123456")
    return (
        EtradeReadAdapter(
            oauth,
            environment="sandbox",
            configured_account_id_key=ACCOUNT_KEY,
            clock=FixedClock(),
        ),
        transport,
    )


def _account_payload(account_id: object = ACCOUNT_ID) -> dict[str, object]:
    account: dict[str, object] = {
        "accountIdKey": ACCOUNT_KEY,
        "accountName": "Synthetic brokerage",
        "accountType": "BROKERAGE",
    }
    if account_id is not _MISSING:
        account["accountId"] = account_id
    return {"AccountListResponse": {"Accounts": {"Account": [account]}}}


def _epoch_milliseconds(day: date) -> int:
    timestamp = datetime.combine(day, datetime.min.time(), tzinfo=UTC)
    delta = timestamp - datetime(1970, 1, 1, tzinfo=UTC)
    return delta.days * 86_400_000 + delta.seconds * 1_000 + delta.microseconds // 1_000


def _transaction(
    transaction_id: str,
    *,
    transaction_type: str | None = "Bought",
    trade_date: date = TRADE_DATE,
    amount: str | None = "-10.00",
    quantity: str | None = "1",
    ticker: str | None = "XYZ",
    account_id: object = ACCOUNT_ID,
    security_type: str | None = "EQ",
    security_subtype: str | None = None,
    settlement_currency: str | None = "USD",
    payment_currency: str | None = "USD",
    post_date: object = _MISSING,
    settlement_date: object = _MISSING,
    order_no: object = _MISSING,
    extra: Mapping[str, object] | None = None,
    brokerage_extra: Mapping[str, object] | None = None,
) -> dict[str, object]:
    row: dict[str, object] = {
        "transactionId": transaction_id,
        "accountId": account_id,
        "transactionDate": _epoch_milliseconds(trade_date),
    }
    if transaction_type is not None:
        row["transactionType"] = transaction_type
    if amount is not None:
        row["amount"] = Decimal(amount)
    if post_date is not _MISSING:
        row["postDate"] = post_date

    brokerage: dict[str, object] = {}
    if ticker is not None or security_type is not None or security_subtype is not None:
        product: dict[str, object] = {}
        if ticker is not None:
            product["symbol"] = ticker
        if security_type is not None:
            product["securityType"] = security_type
        if security_subtype is not None:
            product["securitySubType"] = security_subtype
        brokerage["product"] = product
    if quantity is not None:
        brokerage["quantity"] = Decimal(quantity)
    if settlement_currency is not None:
        brokerage["settlementCurrency"] = settlement_currency
    if payment_currency is not None:
        brokerage["paymentCurrency"] = payment_currency
    if settlement_date is not _MISSING:
        brokerage["settlementDate"] = settlement_date
    if order_no is not _MISSING:
        brokerage["orderNo"] = order_no
    if brokerage_extra is not None:
        brokerage.update(brokerage_extra)
    row["brokerage"] = brokerage
    if extra is not None:
        row.update(extra)
    return row


def _page(
    rows: list[dict[str, object]] | dict[str, object],
    *,
    next_url: str | None = None,
    marker: str | None = None,
    page_markers: object = _MISSING,
    more_transactions: bool | object = False,
    transaction_count: int | None = None,
    total_count: int | None = None,
    wrapper: str = "Transaction",
) -> dict[str, object]:
    row_count = len(rows) if isinstance(rows, list) else 1
    response: dict[str, object] = {
        "transactionCount": row_count if transaction_count is None else transaction_count,
        "moreTransactions": more_transactions,
    }
    if total_count is not None:
        response["totalCount"] = total_count
    if wrapper == "Transaction":
        response["Transaction"] = rows
    else:
        response["Transactions"] = {"Transaction": rows}
    if next_url is not None:
        response["next"] = next_url
    if marker is not None:
        response["marker"] = marker
    if page_markers is not _MISSING:
        response["pageMarkers"] = page_markers
    return {"TransactionListResponse": response}


def _next_url(marker: str, *, account_key: str = ACCOUNT_KEY) -> str:
    query = urlencode((("marker", marker),))
    return f"https://apisb.etrade.com/v1/accounts/{account_key}/transactions?{query}"


def _api_calls(transport: FakeTransport) -> list[requests.PreparedRequest]:
    return transport.calls[2:]


def _header_text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("ascii")
    if isinstance(value, str):
        return value
    raise AssertionError("Prepared request header was not text or ASCII bytes")


def _raise_code(operation: Callable[[], object], code: str) -> AppError:
    with pytest.raises(AppError) as captured:
        operation()
    assert captured.value.code == code
    return captured.value


def _wash_inputs(history: EtradeTransactionHistory) -> FinancialInputs:
    return FinancialInputs(
        account=AccountInput(
            local_account_id=1,
            account_key_fingerprint="synthetic-account",
            display_name="Synthetic brokerage",
            account_type="BROKERAGE",
            tax_treatment=None,
            source="TEST",
            as_of=NOW,
            cash_usd=Decimal(0),
            settled_buying_power_usd=Decimal(0),
        ),
        source_generation=1,
        proposed_trade_date=history.requested_end_date,
        policy=PolicyInput(
            "synthetic-policy",
            AllocationPolicy((), (), ()),
            PolicySettings(()),
        ),
        securities=(),
        positions=(),
        lots=(),
        quotes=(),
        transactions=tuple(
            DomainTransactionInput(
                broker_transaction_key=transaction.broker_transaction_key,
                ticker=transaction.ticker,
                transaction_kind=transaction.transaction_kind,
                transaction_time=transaction.transaction_time,
                trade_date=transaction.trade_date,
                shares=transaction.shares,
                amount_usd=transaction.amount_usd,
                is_acquisition=transaction.is_acquisition,
                broker_lot_id=transaction.broker_lot_id,
                source=transaction.source,
                realized_pl_usd=transaction.realized_pl_usd,
            )
            for transaction in history.transactions
        ),
        source_metadata=InputSourceMetadata(
            transaction_history_complete=history.coverage.transactions,
            transaction_history_start_date=history.coverage.transaction_history_start_date,
            transaction_history_end_date=history.coverage.transaction_history_end_date,
        ),
    )


def test_paginated_history_preserves_bounds_and_accepts_count_changes() -> None:
    start = date(2026, 10, 1)
    first_rows = [
        _transaction(
            f"page-one-{index}",
            trade_date=start + timedelta(days=index % 5),
            amount="-1.00",
        )
        for index in range(50)
    ]
    final_rows = [
        _transaction(
            f"page-two-{index}",
            transaction_type="Sold",
            trade_date=TRADE_DATE,
            amount="1.00",
        )
        for index in range(17)
    ]
    marker = "opaque+/cursor"
    first_page = _page(
        first_rows,
        next_url=_next_url(marker),
        marker=marker,
        page_markers="opaque-page-marker-string",
        more_transactions=False,
        total_count=409,
    )
    final_page = _page(final_rows, more_transactions=False, total_count=17, wrapper="Transactions")
    reader, transport = _adapter(
        [_response(_account_payload()), _response(first_page), _response(final_page)]
    )

    history = reader.fetch_transactions(start, TRADE_DATE)

    assert history.account.account_id == str(ACCOUNT_ID)
    assert history.account.account_id != history.account.account_id_key
    assert history.requested_start_date == start
    assert history.requested_end_date == TRADE_DATE
    assert history.coverage.transactions is True
    assert history.coverage.transaction_history_start_date == start
    assert history.coverage.transaction_history_end_date == TRADE_DATE
    assert history.actual_start_date == start
    assert history.actual_end_date == TRADE_DATE
    assert history.page_count == 2
    assert len(history.records) == 67
    assert len(history.transactions) == 67

    calls = _api_calls(transport)
    assert len(calls) == 3
    assert calls[0].url == "https://apisb.etrade.com/v1/accounts/list"
    first_url = calls[1].url
    second_url = calls[2].url
    assert isinstance(first_url, str)
    assert isinstance(second_url, str)
    first_query = parse_qs(urlsplit(first_url).query)
    second_query = parse_qs(urlsplit(second_url).query)
    expected_bounds = {
        "startDate": ["10012026"],
        "endDate": ["11132026"],
        "count": ["50"],
    }
    assert {key: first_query[key] for key in expected_bounds} == expected_bounds
    assert first_query.get("marker") is None
    assert {key: second_query[key] for key in expected_bounds} == expected_bounds
    assert second_query["marker"] == [marker]
    assert all(call.method == "GET" for call in calls)
    assert all(_header_text(call.headers.get("Accept")) == "application/json" for call in calls)
    assert all(
        _header_text(call.headers.get("Authorization")).startswith("OAuth ") for call in calls
    )
    assert all("access-secret-test" not in str(call.headers) for call in calls)


def test_types_dates_optional_metadata_and_unknown_rows_are_preserved(
    caplog: pytest.LogCaptureFixture,
) -> None:
    rows = [
        _transaction(
            "buy-one",
            transaction_type="  Bought ",
            amount="-20.00",
            quantity="2",
            post_date=_epoch_milliseconds(date(2026, 11, 14)),
            settlement_date=_epoch_milliseconds(date(2026, 11, 16)),
            order_no=0,
            extra={
                "lotId": "not-an-authorized-lot-field",
                "realizedPL": Decimal("-99.00"),
                "customField": {"retained": "synthetic-value"},
            },
        ),
        _transaction(
            "sell-one",
            transaction_type=" Sold ",
            amount="30.00",
            quantity="3",
            security_subtype="ETF",
        ),
        _transaction(
            "qualified-dividend",
            transaction_type="Qualified Dividend",
            amount="2.50",
            quantity="0",
        ),
        _transaction(
            "drip-dividend",
            transaction_type="Dividend",
            amount="5.00",
            quantity="0",
        ),
        _transaction(
            "drip-reinvestment",
            transaction_type="Reinvestment",
            amount="-5.00",
            quantity="1",
        ),
        _transaction(
            "drip-alias",
            transaction_type=" Dividend Reinvestment ",
            amount="-2.00",
            quantity="1",
        ),
        _transaction(
            "transferred-position",
            transaction_type="Transfer",
            amount="0.00",
            quantity="4",
        ),
        _transaction(
            "synthetic-unknown",
            transaction_type="  Option Assignment ",
            amount="-100.00",
            quantity="1",
            extra={"description": "synthetic-private-description"},
        ),
        _transaction(
            "cash-deposit",
            transaction_type=" ACH Deposit ",
            amount="100.00",
            quantity="0",
            ticker=None,
            security_type=None,
        ),
    ]
    page = _page(rows, more_transactions=False)
    reader, _ = _adapter([_response(_account_payload()), _response(page)])

    history = reader.fetch_transactions(TRADE_DATE, TRADE_DATE)

    assert history.coverage.transactions is False
    assert history.diagnostics == ("unsupported_transaction_type",)
    assert "Option Assignment" not in caplog.text
    assert "synthetic-private-description" not in caplog.text
    records = {record.transaction_id: record for record in history.records}
    buy_record = records["buy-one"]
    assert buy_record.transaction_type_source == "  Bought "
    assert buy_record.normalized_transaction_type == "bought"
    assert buy_record.transaction_date_source == _epoch_milliseconds(TRADE_DATE)
    assert buy_record.transaction_time == datetime(2026, 11, 13, tzinfo=UTC)
    assert buy_record.trade_date == TRADE_DATE
    assert buy_record.post_date_source == _epoch_milliseconds(date(2026, 11, 14))
    assert buy_record.settlement_date_source == _epoch_milliseconds(date(2026, 11, 16))
    assert buy_record.order_no_source == 0
    assert buy_record.source_fields["customField"] == {"retained": "synthetic-value"}
    assert buy_record.transaction is not None
    assert buy_record.transaction.transaction_kind == "BUY"
    assert buy_record.transaction.shares == Decimal(2)
    assert buy_record.transaction.amount_usd == Decimal("-20.00")
    assert buy_record.transaction.is_acquisition is True
    assert buy_record.transaction.broker_lot_id is None
    assert buy_record.transaction.realized_pl_usd is None

    sell = records["sell-one"].transaction
    assert sell is not None
    assert sell.transaction_kind == "SELL"
    assert sell.shares == Decimal(3)
    assert sell.amount_usd == Decimal("30.00")
    assert sell.is_acquisition is False
    assert records["sell-one"].post_date_source is None
    assert records["sell-one"].settlement_date_source is None

    assert records["qualified-dividend"].transaction is not None
    assert records["qualified-dividend"].transaction.transaction_kind == "DIVIDEND"
    assert records["qualified-dividend"].transaction.is_acquisition is False
    assert records["drip-dividend"].transaction is not None
    assert records["drip-dividend"].transaction.is_acquisition is False
    reinvestment = records["drip-reinvestment"].transaction
    alias = records["drip-alias"].transaction
    assert reinvestment is not None
    assert alias is not None
    assert reinvestment.transaction_kind == alias.transaction_kind == "BUY"
    assert reinvestment.is_acquisition
    assert alias.is_acquisition
    assert (
        reinvestment.broker_transaction_key
        != records["drip-dividend"].transaction.broker_transaction_key
    )
    assert alias.broker_transaction_key == "drip-alias"

    transfer = records["transferred-position"].transaction
    assert transfer is not None
    assert transfer.transaction_kind == "OTHER"
    assert transfer.is_acquisition is False
    assert records["cash-deposit"].transaction is None
    unknown = records["synthetic-unknown"]
    assert unknown.transaction_type_source == "  Option Assignment "
    assert unknown.normalized_transaction_type == "option assignment"
    assert unknown.transaction is None
    assert unknown.wash_relevant is True
    assert unknown.source_fields["description"] == "synthetic-private-description"


def test_nested_transaction_type_is_not_a_fallback_and_unknown_history_fails_closed() -> None:
    row = _transaction(
        "nested-only-type",
        transaction_type=None,
        brokerage_extra={"transactionType": "Bought"},
    )
    page = _page([row], more_transactions=False)
    reader, _ = _adapter([_response(_account_payload()), _response(page)])

    history = reader.fetch_transactions(TRADE_DATE - timedelta(days=30), TRADE_DATE)
    inputs = _wash_inputs(history)
    loss_sale = ProposedLotSale(
        "XYZ", "loss-lot", Decimal(1), Decimal(-5), "loss-group", TRADE_DATE
    )
    proposed_buy = ProposedBuy("XYZ", Decimal(1), "replacement", TRADE_DATE)

    assert history.coverage.transactions is False
    assert history.transactions == ()
    brokerage_source = history.records[0].source_fields["brokerage"]
    assert isinstance(brokerage_source, dict)
    assert brokerage_source["transactionType"] == "Bought"
    assert "incomplete_acquisition_history" in assess_wash_sales(inputs, (loss_sale,))[0].reasons
    assert (
        "incomplete_executed_loss_history"
        in assess_proposed_buys(inputs, (proposed_buy,))[0].reasons
    )


def test_returned_buy_and_loss_sell_keep_unknown_attribution_fail_closed() -> None:
    start = TRADE_DATE - timedelta(days=30)
    rows = [
        _transaction("recent-buy", trade_date=TRADE_DATE - timedelta(days=5), amount="-50.00"),
        _transaction(
            "recent-sell",
            transaction_type="Sold",
            trade_date=TRADE_DATE - timedelta(days=3),
            amount="60.00",
            quantity="2",
        ),
    ]
    reader, _ = _adapter([_response(_account_payload()), _response(_page(rows))])
    history = reader.fetch_transactions(start, TRADE_DATE)
    inputs = _wash_inputs(history)
    loss_sale = ProposedLotSale(
        "XYZ", "current-loss-lot", Decimal(1), Decimal(-5), "loss-group", TRADE_DATE
    )
    proposed_buy = ProposedBuy("XYZ", Decimal(1), "replacement", TRADE_DATE)

    assert history.coverage.transactions is True
    assert inputs.source_metadata.transaction_history_start_date == start
    assert inputs.source_metadata.transaction_history_end_date == TRADE_DATE
    assert history.actual_start_date == TRADE_DATE - timedelta(days=5)
    assert history.actual_end_date == TRADE_DATE - timedelta(days=3)
    acquisition_assessment = assess_wash_sales(inputs, (loss_sale,))[0]
    buy_assessment = assess_proposed_buys(inputs, (proposed_buy,))[0]
    assert "unattributed_recent_acquisition" in acquisition_assessment.reasons
    assert "executed_loss_attribution_unknown" in buy_assessment.reasons
    assert buy_assessment.conflicting_transaction_keys == ("recent-sell",)


def test_complete_empty_and_singleton_wrapped_pages_are_distinct_from_unavailable() -> None:
    empty_page = _page([], more_transactions=False, total_count=0)
    reader, _ = _adapter([_response(_account_payload()), _response(empty_page)])
    empty_history = reader.fetch_transactions(TRADE_DATE, TRADE_DATE)
    assert empty_history.transactions == ()
    assert empty_history.records == ()
    assert empty_history.coverage.transactions is True
    assert empty_history.actual_start_date is None
    assert empty_history.actual_end_date is None

    singleton = _transaction("single-buy", amount="-10.00")
    wrapped_page = _page(singleton, more_transactions=False, total_count=1, wrapper="Transactions")
    wrapped_reader, _ = _adapter([_response(_account_payload()), _response(wrapped_page)])
    wrapped_history = wrapped_reader.fetch_transactions(TRADE_DATE, TRADE_DATE)
    assert len(wrapped_history.records) == 1
    assert wrapped_history.transactions[0].broker_transaction_key == "single-buy"
    assert wrapped_history.coverage.transactions is True

    malformed_json_reader, _ = _adapter([_response(_account_payload()), _response(raw_body="{")])
    _raise_code(
        lambda: malformed_json_reader.fetch_transactions(TRADE_DATE, TRADE_DATE),
        "etrade_read_invalid_json",
    )

    malformed_page_reader, _ = _adapter([_response(_account_payload()), _response([])])
    _raise_code(
        lambda: malformed_page_reader.fetch_transactions(TRADE_DATE, TRADE_DATE),
        "etrade_read_response_malformed",
    )

    unavailable_reader, _ = _adapter([_response(_account_payload()), _response(status=204)])
    _raise_code(
        lambda: unavailable_reader.fetch_transactions(TRADE_DATE, TRADE_DATE),
        "etrade_read_transactions_incomplete",
    )


def test_distinct_account_id_is_required_and_foreign_rows_are_rejected() -> None:
    missing_account_reader, missing_transport = _adapter(
        [_response(_account_payload(account_id=_MISSING))]
    )
    _raise_code(
        lambda: missing_account_reader.fetch_transactions(TRADE_DATE, TRADE_DATE),
        "etrade_read_transaction_account_identity_missing",
    )
    assert len(_api_calls(missing_transport)) == 1

    foreign_row = _transaction("foreign-account", account_id=987654321)
    foreign_reader, _ = _adapter([_response(_account_payload()), _response(_page([foreign_row]))])
    _raise_code(
        lambda: foreign_reader.fetch_transactions(TRADE_DATE, TRADE_DATE),
        "etrade_read_transaction_account_mismatch",
    )

    missing_row_identity = _transaction("missing-account-id")
    del missing_row_identity["accountId"]
    missing_row_reader, _ = _adapter(
        [_response(_account_payload()), _response(_page([missing_row_identity]))]
    )
    _raise_code(
        lambda: missing_row_reader.fetch_transactions(TRADE_DATE, TRADE_DATE),
        "etrade_read_transaction_account_identity_missing",
    )


def test_next_url_host_account_and_query_are_validated_before_following() -> None:
    marker = "opaque-marker"
    candidates = [
        (
            f"https://evil.example/v1/accounts/{ACCOUNT_KEY}/transactions?marker={marker}",
            "etrade_read_transactions_pagination_foreign",
        ),
        (
            _next_url(marker, account_key="other-account"),
            "etrade_read_transactions_pagination_foreign",
        ),
        (
            _next_url("other-marker"),
            "etrade_read_transactions_pagination_invalid",
        ),
        (
            _next_url(marker) + "&count=50",
            "etrade_read_transactions_pagination_invalid",
        ),
    ]
    for next_url, expected_code in candidates:
        first_page = _page(
            [_transaction("first-page")],
            next_url=next_url,
            marker=marker,
            page_markers="opaque-page-markers",
            more_transactions=False,
        )
        reader, transport = _adapter([_response(_account_payload()), _response(first_page)])
        _raise_code(
            lambda current=reader: current.fetch_transactions(TRADE_DATE, TRADE_DATE),
            expected_code,
        )
        assert len(_api_calls(transport)) == 2


def test_pagination_counts_markers_and_duplicates_fail_closed() -> None:
    mismatch_reader, _ = _adapter(
        [
            _response(_account_payload()),
            _response(_page([_transaction("count-one")], transaction_count=2)),
        ]
    )
    _raise_code(
        lambda: mismatch_reader.fetch_transactions(TRADE_DATE, TRADE_DATE),
        "etrade_read_transactions_count_mismatch",
    )

    more_without_next_reader, _ = _adapter(
        [
            _response(_account_payload()),
            _response(_page([_transaction("truncated")], more_transactions=True)),
        ]
    )
    _raise_code(
        lambda: more_without_next_reader.fetch_transactions(TRADE_DATE, TRADE_DATE),
        "etrade_read_transactions_incomplete",
    )

    full_final_reader, _ = _adapter(
        [
            _response(_account_payload()),
            _response(
                _page(
                    [_transaction(f"full-{index}") for index in range(50)],
                    more_transactions=False,
                )
            ),
        ]
    )
    _raise_code(
        lambda: full_final_reader.fetch_transactions(TRADE_DATE, TRADE_DATE),
        "etrade_read_transactions_incomplete",
    )

    repeated_marker_page = _page(
        [_transaction("second-page")],
        next_url=_next_url("same-marker"),
        marker="same-marker",
        more_transactions=False,
    )
    repeated_reader, _ = _adapter(
        [
            _response(_account_payload()),
            _response(
                _page(
                    [_transaction("first-page")],
                    next_url=_next_url("same-marker"),
                    marker="same-marker",
                    more_transactions=False,
                )
            ),
            _response(repeated_marker_page),
        ]
    )
    _raise_code(
        lambda: repeated_reader.fetch_transactions(TRADE_DATE, TRADE_DATE),
        "etrade_read_transactions_pagination_repeated",
    )

    duplicate_id_reader, _ = _adapter(
        [
            _response(_account_payload()),
            _response(
                _page(
                    [_transaction("duplicate-id")],
                    next_url=_next_url("next-marker"),
                    marker="next-marker",
                )
            ),
            _response(_page([_transaction("duplicate-id")])),
        ]
    )
    _raise_code(
        lambda: duplicate_id_reader.fetch_transactions(TRADE_DATE, TRADE_DATE),
        "etrade_read_transactions_duplicate",
    )


def test_failure_after_good_page_returns_no_history() -> None:
    first_page = _page(
        [_transaction("first-good-page")],
        next_url=_next_url("next-marker"),
        marker="next-marker",
    )
    reader, transport = _adapter(
        [_response(_account_payload()), _response(first_page), _response(status=503)]
    )

    _raise_code(
        lambda: reader.fetch_transactions(TRADE_DATE, TRADE_DATE),
        "etrade_read_http_error",
    )
    assert len(_api_calls(transport)) == 3


def test_invalid_query_and_outside_rows_do_not_claim_complete_coverage() -> None:
    reader, transport = _adapter([])
    _raise_code(
        lambda: reader.fetch_transactions(TRADE_DATE, TRADE_DATE - timedelta(days=1)),
        "etrade_read_transactions_query_invalid",
    )
    assert _api_calls(transport) == []

    start = TRADE_DATE - timedelta(days=30)
    outside_date = start - timedelta(days=1)
    outside_row = _transaction("outside-interval", trade_date=outside_date)
    outside_reader, _ = _adapter([_response(_account_payload()), _response(_page([outside_row]))])
    history = outside_reader.fetch_transactions(start, TRADE_DATE)

    assert history.coverage.transactions is False
    assert history.coverage.transaction_history_start_date == start
    assert history.coverage.transaction_history_end_date == TRADE_DATE
    assert history.actual_start_date == outside_date
    assert history.actual_end_date == outside_date
    assert history.transactions[0].trade_date == outside_date
    assert "transaction_outside_requested_interval" in history.diagnostics


def test_ambiguous_reinvestment_and_cash_sign_conflicts_remain_fail_closed() -> None:
    ambiguous_reinvestment = _transaction(
        "missing-reinvestment-security",
        transaction_type="Reinvestment",
        amount="-5.00",
        quantity="1",
        ticker=None,
        security_type=None,
    )
    contradictory_buy = _transaction(
        "buy-with-inflow",
        transaction_type="Bought",
        amount="5.00",
        quantity="1",
    )
    reader, _ = _adapter(
        [
            _response(_account_payload()),
            _response(_page([ambiguous_reinvestment, contradictory_buy])),
        ]
    )

    history = reader.fetch_transactions(TRADE_DATE, TRADE_DATE)

    assert history.coverage.transactions is False
    assert all(record.transaction is None for record in history.records)
    assert history.records[0].normalized_transaction_type == "reinvestment"
    assert history.records[1].normalized_transaction_type == "bought"
    assert "wash_transaction_unrepresentable" in history.diagnostics
    assert "transaction_kind_inconsistent" in history.diagnostics


def test_unknown_history_coverage_blocks_wash_clearance_but_retains_raw_fields() -> None:
    start = TRADE_DATE - timedelta(days=30)
    unknown_row = _transaction(
        "unsupported-event",
        transaction_type="Reorganization",
        extra={"unmodeled": {"token_like": "synthetic-not-a-secret"}},
    )
    reader, _ = _adapter([_response(_account_payload()), _response(_page([unknown_row]))])
    history = reader.fetch_transactions(start, TRADE_DATE)
    inputs = _wash_inputs(history)

    assert history.coverage.transactions is False
    assert history.records[0].source_fields["unmodeled"] == {"token_like": "synthetic-not-a-secret"}
    assert history.diagnostics == ("unsupported_transaction_type",)
    loss_sale = ProposedLotSale(
        "XYZ", "loss-lot", Decimal(1), Decimal(-5), "loss-group", TRADE_DATE
    )
    proposed_buy = ProposedBuy("XYZ", Decimal(1), "replacement", TRADE_DATE)
    assert "incomplete_acquisition_history" in assess_wash_sales(inputs, (loss_sale,))[0].reasons
    assert (
        "incomplete_executed_loss_history"
        in assess_proposed_buys(inputs, (proposed_buy,))[0].reasons
    )
