from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import override
from urllib.parse import parse_qs, urlsplit

import pytest
import requests
from requests.adapters import BaseAdapter

from app.broker.etrade_oauth import EtradeOAuthService
from app.broker.etrade_read import EtradeReadAdapter
from app.services.errors import AppError


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class StubAdapter(BaseAdapter):
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
        return (
            "{"
            + ",".join(f"{json.dumps(key)}:{_json_text(item)}" for key, item in value.items())
            + "}"
        )
    if isinstance(value, list):
        return "[" + ",".join(_json_text(item) for item in value) + "]"
    return json.dumps(value, separators=(",", ":"))


def _response(
    payload: object | None = None,
    *,
    status: int = 200,
    content_type: str = "application/json",
    raw_body: str | None = None,
) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response._content = (raw_body if raw_body is not None else _json_text(payload)).encode()
    response.encoding = "utf-8"
    response.headers["Content-Type"] = content_type
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


def _service(
    responses: Sequence[requests.Response | Exception],
    clock: FixedClock,
) -> tuple[EtradeOAuthService, StubAdapter]:
    transport = StubAdapter(
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
        clock=clock,
    )
    oauth.start()
    oauth.verify("123456")
    return oauth, transport


def _adapter(
    responses: Sequence[requests.Response | Exception],
    *,
    configured: str | None = None,
    clock: FixedClock | None = None,
) -> tuple[EtradeReadAdapter, EtradeOAuthService, StubAdapter, FixedClock]:
    fixed_clock = clock or FixedClock(datetime(2026, 11, 5, 16, 0, tzinfo=UTC))
    oauth, transport = _service(responses, fixed_clock)
    reader = EtradeReadAdapter(
        oauth,
        environment="sandbox",
        configured_account_id_key=configured,
        clock=fixed_clock,
    )
    return reader, oauth, transport, fixed_clock


def _accounts(*accounts: dict[str, object]) -> dict[str, object]:
    return {"AccountListResponse": {"Accounts": {"Account": list(accounts)}}}


def _account(
    key: str,
    *,
    account_type: str = "BROKERAGE",
    name: str | None = None,
) -> dict[str, object]:
    return {
        "accountIdKey": key,
        "accountName": name or f"Synthetic {key}",
        "accountType": account_type,
    }


def _position(
    ticker: str,
    position_id: str,
    shares: Decimal,
    *,
    inline_lots: list[dict[str, object]] | dict[str, object] | None = None,
    asset_type: str = "EQUITY",
    product_id: object = "synthetic-product-1",
) -> dict[str, object]:
    position: dict[str, object] = {
        "symbol": ticker,
        "positionId": position_id,
        "quantity": shares,
        "marketValue": Decimal("100.25"),
        "Product": {
            "productId": product_id,
            "securityTypeDisplay": asset_type,
            "securityType": "EQ" if asset_type == "EQUITY" else "ETF",
            "cusip": "123456789" if ticker == "AAA" else None,
            "isin": "US1234567890" if ticker == "AAA" else None,
        },
    }
    if inline_lots is not None:
        position["positionLot"] = inline_lots
    return position


def _lot(
    lot_id: str,
    shares: Decimal,
    *,
    available: Decimal | None = None,
    total_cost: Decimal = Decimal(20),
    acquired_ms: int = 0,
    **extra: object,
) -> dict[str, object]:
    row: dict[str, object] = {
        "positionLotId": lot_id,
        "remainingQty": shares,
        "availableQty": shares if available is None else available,
        "totalCost": total_cost,
        "acquiredDate": acquired_ms,
        **extra,
    }
    return row


def _portfolio(
    positions: list[dict[str, object]] | dict[str, object],
    *,
    account_key: str | None = None,
    **markers: object,
) -> dict[str, object]:
    wrapper: dict[str, object] = {"Position": positions, **markers}
    if account_key is not None:
        wrapper["accountIdKey"] = account_key
    return {"PortfolioResponse": {"AccountPortfolio": wrapper}}


def _detail(*lots: dict[str, object]) -> dict[str, object]:
    return {"PositionLotsResponse": {"PositionLot": list(lots)}}


def _api_calls(transport: StubAdapter) -> list[requests.PreparedRequest]:
    return transport.calls[2:]



def _header_text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("ascii")
    if isinstance(value, str):
        return value
    raise AssertionError("Prepared request header was not text or ASCII bytes")

def _raise_code(call: Callable[[], object], code: str) -> AppError:
    with pytest.raises(AppError) as captured:
        call()
    assert captured.value.code == code
    return captured.value


def test_configured_account_paginates_exact_inline_and_detail_lots() -> None:
    clock = FixedClock(datetime(2026, 11, 5, 16, 0, tzinfo=UTC))
    inline = _lot(
        "lot-exact-40",
        Decimal(40),
        available=Decimal(0),
        total_cost=Decimal("255.87"),
        acquired_ms=1772168400000,
        price=Decimal("6.3967"),
        totalCostForGainPct=Decimal("255.868"),
        adjPrice=Decimal(0),
        orderNo=0,
    )
    page_one = _portfolio(
        [_position("AAA", "101", Decimal(40), inline_lots=[inline])],
        account_key="chosen-account",
        totalNoOfPages=2,
        nextPageNo=2,
    )
    page_two = _portfolio(
        [_position("BBB", "102", Decimal("0.5"), asset_type="ETF")],
        account_key="chosen-account",
        totalNoOfPages=2,
    )
    detail = _detail(
        _lot(
            "lot-fractional",
            Decimal("0.5"),
            available=Decimal("0.25"),
            total_cost=Decimal("1.2345"),
        )
    )
    reader, oauth, transport, clock = _adapter(
        [
            _response(
                _accounts(
                    _account("other-account"),
                    _account("chosen-account"),
                    _account("retirement", account_type="IRA"),
                )
            ),
            _response(page_one),
            _response(page_two),
            _response(detail),
        ],
        configured="chosen-account",
        clock=clock,
    )
    clock.now = datetime(2026, 11, 5, 16, 1, tzinfo=UTC)

    result = reader.fetch_portfolio_with_lots()

    assert result.account.account_id_key == "chosen-account"
    assert result.account.display_name == "Synthetic chosen-account"
    assert [position.position.ticker for position in result.positions] == ["AAA", "BBB"]
    assert result.positions[0].broker_position_id == "101"
    assert result.positions[0].broker_product_id == "synthetic-product-1"
    assert result.positions[0].position.cusip == "123456789"
    assert result.positions[0].position.isin == "US1234567890"
    assert result.positions[1].position.asset_type == "ETF"
    assert result.positions[1].position.shares == Decimal("0.5")
    assert [lot.broker_lot_id for lot in result.lots] == ["lot-exact-40", "lot-fractional"]
    first, second = result.lots
    assert first.remaining_shares == Decimal(40)
    assert first.available_shares == Decimal(0)
    assert first.reserved_shares == Decimal(40)
    assert first.total_cost_usd == first.total_cost_source == Decimal("255.87")
    assert first.lot.adjusted_unit_basis_usd == Decimal("6.39675")
    assert first.lot.adjusted_unit_basis_usd * first.lot.shares != Decimal("255.87") * Decimal(
        "6.3967"
    )
    assert first.lot.acquired_date.isoformat() == "2026-02-27"
    assert first.acquired_date_source == Decimal(1772168400000)
    assert second.remaining_shares == Decimal("0.5")
    assert second.available_shares == Decimal("0.25")
    assert second.reserved_shares == Decimal("0.25")
    assert second.lot.adjusted_unit_basis_usd == Decimal("2.469")
    assert all(
        isinstance(item.position, type(result.positions[0].position)) for item in result.positions
    )
    assert all(lot.lot.broker_lot_id == lot.broker_lot_id for lot in result.lots)
    assert result.as_of == datetime(2026, 11, 5, 16, 1, tzinfo=UTC)
    assert oauth.status()["last_activity_at"] == datetime(2026, 11, 5, 16, 1, tzinfo=UTC)

    calls = _api_calls(transport)
    assert len(calls) == 4
    assert calls[0].url == "https://apisb.etrade.com/v1/accounts/list"
    portfolio_urls = [str(call.url) for call in calls if "/portfolio?" in str(call.url)]
    assert len(portfolio_urls) == 2
    assert parse_qs(urlsplit(portfolio_urls[0]).query) == {
        "sortBy": ["SYMBOL"],
        "sortOrder": ["ASC"],
        "count": ["200"],
        "pageNumber": ["1"],
        "lotsRequired": ["true"],
    }
    assert parse_qs(urlsplit(portfolio_urls[1]).query)["pageNumber"] == ["2"]
    assert calls[3].url == "https://apisb.etrade.com/v1/accounts/chosen-account/portfolio/102"
    assert all(call.method == "GET" for call in calls)
    assert all(_header_text(call.headers.get("Accept")) == "application/json" for call in calls)
    assert all(_header_text(call.headers.get("Authorization")).startswith("OAuth ") for call in calls)
    assert all("access-secret-test" not in str(call.headers) for call in calls)


def test_unique_brokerage_account_supports_singleton_wrappers_and_empty_holdings() -> None:
    account_payload = {
        "AccountListResponse": {
            "Accounts": {"Account": _account("unique-brokerage")},
        }
    }
    portfolio_payload = {
        "PortfolioResponse": {
            "AccountPortfolio": {"Position": [], "totalNoOfPages": 1},
        }
    }
    reader, _, transport, _ = _adapter([_response(account_payload), _response(portfolio_payload)])

    result = reader.fetch_portfolio_with_lots()

    assert result.account.account_id_key == "unique-brokerage"
    assert result.positions == ()
    assert result.lots == ()
    assert len(_api_calls(transport)) == 2


def test_previous_binding_selects_one_account_and_preserves_product_id_casing() -> None:
    accounts = _accounts(_account("first"), _account("previous"))
    position = _position("AAA", "123", Decimal(1), product_id={"symbol": "AAA", "typeCode": "1"})
    position["Product"] = {
        "ProductId": {"symbol": "AAA", "typeCode": "1"},
        "securityTypeDisplay": "Equity",
    }
    portfolio = _portfolio([position], account_key="previous")
    detail = _detail(_lot("lot-123", Decimal(1), total_cost=Decimal("7.25")))
    reader, _, transport, _ = _adapter(
        [_response(accounts), _response(portfolio), _response(detail)]
    )

    result = reader.fetch_portfolio_with_lots(previously_bound_account_id_key="previous")

    assert result.account.account_id_key == "previous"
    assert result.positions[0].broker_product_id == {"symbol": "AAA", "typeCode": "1"}
    assert (
        _api_calls(transport)[2].url
        == "https://apisb.etrade.com/v1/accounts/previous/portfolio/123"
    )


@pytest.mark.parametrize(
    ("accounts", "configured", "previous", "expected_code"),
    [
        ((_account("one"), _account("two")), None, None, "etrade_read_account_ambiguous"),
        ((_account("ira", account_type="IRA"),), None, None, "etrade_read_no_brokerage_account"),
        ((_account("one"),), "missing", None, "etrade_read_account_not_found"),
        ((_account("one"),), "one", "two", "etrade_read_account_binding_mismatch"),
        ((_account("ira", account_type="IRA"),), "ira", None, "etrade_read_account_not_brokerage"),
    ],
)
def test_account_resolution_fails_closed(
    accounts: tuple[dict[str, object], ...],
    configured: str | None,
    previous: str | None,
    expected_code: str,
) -> None:
    reader, _, transport, _ = _adapter([_response(_accounts(*accounts))], configured=configured)

    _raise_code(
        lambda: reader.fetch_portfolio_with_lots(previously_bound_account_id_key=previous),
        expected_code,
    )

    assert len(_api_calls(transport)) == 1
    assert str(_api_calls(transport)[0].url).endswith("/accounts/list")


def test_missing_configured_account_does_not_select_another_eligible_account() -> None:
    reader, _, transport, _ = _adapter(
        [_response(_accounts(_account("first"), _account("second")))],
        configured="not-returned",
    )

    _raise_code(lambda: reader.fetch_portfolio_with_lots(), "etrade_read_account_not_found")

    assert len(_api_calls(transport)) == 1


@pytest.mark.parametrize(
    ("markers", "expected_code"),
    [
        ({"totalNoOfPages": 2, "totalPages": 3}, "etrade_read_pagination_conflict"),
        ({"nextPageNo": 1}, "etrade_read_pagination_repeated"),
        (
            {
                "next": "https://api.etrade.com/v1/accounts/not-this/portfolio?pageNumber=2",
                "nextPageNo": 3,
            },
            "etrade_read_pagination_conflict",
        ),
        ({"nextPageNo": 3}, "etrade_read_pagination_invalid"),
        ({"totalNoOfPages": 1, "nextPageNo": 2}, "etrade_read_pagination_conflict"),
    ],
)
def test_portfolio_pagination_marker_contradictions_are_rejected(
    markers: dict[str, object], expected_code: str
) -> None:
    reader, _, transport, _ = _adapter(
        [
            _response(_accounts(_account("one"))),
            _response(_portfolio([], **markers)),
        ]
    )

    _raise_code(lambda: reader.fetch_portfolio_with_lots(), expected_code)

    assert len(_api_calls(transport)) == 2


def test_repeated_continuation_on_later_page_is_rejected() -> None:
    first = _portfolio([], nextPageNo=2)
    second = _portfolio([], nextPageNo=2)
    reader, _, transport, _ = _adapter(
        [_response(_accounts(_account("one"))), _response(first), _response(second)]
    )

    _raise_code(lambda: reader.fetch_portfolio_with_lots(), "etrade_read_pagination_repeated")

    assert len(_api_calls(transport)) == 3


def test_partial_portfolio_fetch_failure_returns_no_partial_result() -> None:
    first = _portfolio(
        [_position("AAA", "101", Decimal(1), inline_lots=[_lot("lot-a", Decimal(1))])],
        nextPageNo=2,
    )
    failure = _response({"private": "synthetic-upstream-body"}, status=503)
    reader, _, transport, _ = _adapter(
        [_response(_accounts(_account("one"))), _response(first), failure]
    )

    error = _raise_code(lambda: reader.fetch_portfolio_with_lots(), "etrade_read_http_error")

    assert "synthetic-upstream-body" not in str(error)
    assert len(_api_calls(transport)) == 3


def test_detail_lot_values_preserve_zero_availability_and_fractional_shares() -> None:
    position = _position("AAA", "101", Decimal("0.125"), inline_lots=[])
    lot = _lot(
        "fractional-lot", Decimal("0.125"), available=Decimal(0), total_cost=Decimal("0.3125")
    )
    reader, _, _, _ = _adapter(
        [
            _response(_accounts(_account("one"))),
            _response(_portfolio(position)),
            _response({"PositionLotsResponse": {"PositionLot": lot}}),
        ]
    )

    result = reader.fetch_portfolio_with_lots()

    assert result.lots[0].remaining_shares == Decimal("0.125")
    assert result.lots[0].available_shares == Decimal(0)
    assert result.lots[0].reserved_shares == Decimal("0.125")
    assert result.lots[0].lot.available_shares == Decimal(0)
    assert result.lots[0].lot.adjusted_unit_basis_usd == Decimal("2.5")


def test_unrepresentable_basis_conversion_fails_without_rounding() -> None:
    position = _position("AAA", "101", Decimal(3), inline_lots=[])
    reader, _, _, _ = _adapter(
        [
            _response(_accounts(_account("one"))),
            _response(_portfolio(position)),
            _response(_detail(_lot("thirds", Decimal(3), total_cost=Decimal(1)))),
        ]
    )

    _raise_code(lambda: reader.fetch_portfolio_with_lots(), "etrade_read_basis_unrepresentable")


def test_missing_lot_fields_or_empty_detail_fail_closed() -> None:
    position = _position("AAA", "101", Decimal(1), inline_lots=[])
    missing_available = _lot("missing-available", Decimal(1))
    del missing_available["availableQty"]
    reader, _, _, _ = _adapter(
        [
            _response(_accounts(_account("one"))),
            _response(_portfolio(position)),
            _response(_detail(missing_available)),
        ]
    )

    _raise_code(lambda: reader.fetch_portfolio_with_lots(), "etrade_read_field_missing")

    empty_reader, _, _, _ = _adapter(
        [
            _response(_accounts(_account("one"))),
            _response(_portfolio(position)),
            _response({"PositionLotsResponse": {"PositionLot": []}}),
        ]
    )
    _raise_code(lambda: empty_reader.fetch_portfolio_with_lots(), "etrade_read_lots_missing")


def test_duplicate_lot_and_position_ids_are_rejected() -> None:
    position = _position("AAA", "101", Decimal(2), inline_lots=[])
    duplicate_lots = _detail(
        _lot("same-lot", Decimal(1), total_cost=Decimal(5)),
        _lot("same-lot", Decimal(1), total_cost=Decimal(5)),
    )
    reader, _, _, _ = _adapter(
        [
            _response(_accounts(_account("one"))),
            _response(_portfolio(position)),
            _response(duplicate_lots),
        ]
    )
    _raise_code(lambda: reader.fetch_portfolio_with_lots(), "etrade_read_duplicate_lot")

    first = _portfolio(
        [_position("AAA", "101", Decimal(1), inline_lots=[_lot("lot-1", Decimal(1))])],
        nextPageNo=2,
    )
    second = _portfolio(
        [_position("BBB", "101", Decimal(1), inline_lots=[_lot("lot-2", Decimal(1))])]
    )
    duplicate_positions, _, _, _ = _adapter(
        [
            _response(_accounts(_account("one"))),
            _response(first),
            _response(second),
        ]
    )
    _raise_code(
        lambda: duplicate_positions.fetch_portfolio_with_lots(),
        "etrade_read_duplicate_position",
    )


def test_malformed_and_nonfinite_numeric_responses_are_sanitized(
    caplog: pytest.LogCaptureFixture,
) -> None:
    position = _position("AAA", "101", Decimal(1), inline_lots=[])
    nonfinite = _response(
        raw_body='{"PositionLotsResponse":{"PositionLot":{"positionLotId":"lot","remainingQty":NaN}}}'
    )
    reader, _, _, _ = _adapter(
        [
            _response(_accounts(_account("one"))),
            _response(_portfolio(position)),
            nonfinite,
        ]
    )
    caplog.set_level(logging.WARNING, logger="app.broker.etrade_read")

    error = _raise_code(lambda: reader.fetch_portfolio_with_lots(), "etrade_read_invalid_json")

    assert "NaN" not in str(error)
    assert "NaN" not in caplog.text

    malformed, _, _, _ = _adapter(
        [
            _response(_accounts(_account("one"))),
            _response(_portfolio(position)),
            _response(_detail(_lot("bad-quantity", Decimal(1), available=Decimal(2)))),
        ]
    )
    _raise_code(lambda: malformed.fetch_portfolio_with_lots(), "etrade_read_lot_invalid")


def test_upstream_redirect_is_not_followed_and_response_body_is_not_exposed() -> None:
    redirect = _response(status=302, content_type="text/plain", raw_body="synthetic-secret-body")
    redirect.headers["Location"] = "https://unexpected.example/collect"
    reader, _, transport, _ = _adapter([redirect])

    error = _raise_code(lambda: reader.list_accounts(), "etrade_read_http_error")

    assert "synthetic-secret-body" not in str(error)
    assert len(_api_calls(transport)) == 1
    assert _api_calls(transport)[0].url == "https://apisb.etrade.com/v1/accounts/list"
    assert "unexpected.example" not in str(_api_calls(transport)[0].url)


def test_inline_missing_exact_fields_uses_detail_but_never_invents_availability() -> None:
    inline = {
        "positionLotId": "legacy-inline",
        "positionLotQuantity": Decimal(1),
        "pricePaid": Decimal(8),
        "dateAcquired": "2024-01-02",
        "orderNo": 0,
    }
    position = _position("AAA", "101", Decimal(1), inline_lots=[inline])
    missing_availability = _lot("detail-lot", Decimal(1), total_cost=Decimal(8))
    del missing_availability["availableQty"]
    reader, _, transport, _ = _adapter(
        [
            _response(_accounts(_account("one"))),
            _response(_portfolio(position)),
            _response(_detail(missing_availability)),
        ]
    )

    _raise_code(lambda: reader.fetch_portfolio_with_lots(), "etrade_read_field_missing")

    assert len(_api_calls(transport)) == 3
    assert _api_calls(transport)[2].url.endswith("/portfolio/101")
