from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import override

import httpx
import pytest

from app.domain.decimal_math import exact_sum
from app.schemas import ExposureInput
from app.services.ishares_market_data import (
    ITOT_URL,
    MAX_RESPONSE_BYTES,
    IsharesDimensionCoverage,
    IsharesExposureResult,
    IsharesFundConfig,
    IsharesMarketDataError,
    fetch_ishares_exposures,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "ishares"
FIXTURE = FIXTURE_DIR / "itot_excerpt.csv"
CASH_FIXTURE = FIXTURE_DIR / "itot_signed_cash_2026-11-16.csv"
URL = ITOT_URL
FETCHED_AT = datetime(2026, 11, 18, 14, 8, 29, tzinfo=UTC)


def _run(content: bytes | None = None, *, status: int = 200) -> IsharesExposureResult:
    body = FIXTURE.read_bytes() if content is None else content

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == URL
        return httpx.Response(
            status, content=body, headers={"content-type": "text/plain; charset=utf-8"}
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        return fetch_ishares_exposures(
            IsharesFundConfig("ITOT", URL), client, clock=lambda: FETCHED_AT, timeout=2.5
        )


def _expect_error(content: bytes) -> None:
    with pytest.raises(IsharesMarketDataError):
        _run(content)


def _weights(result: IsharesExposureResult, dimension: str) -> dict[str, Decimal]:
    return {row.exposure_key: row.weight for row in result.exposures if row.dimension == dimension}


def test_captured_itot_excerpt_uses_market_values_and_exact_normalized_basket() -> None:
    result = _run()
    assert result.fund_ticker == "ITOT"
    assert result.source_url == URL
    assert result.as_of_date == date(2026, 11, 17)
    assert result.fetched_at == FETCHED_AT
    assert result.total_equity_market_value == Decimal("11668291953.02")
    assert all(isinstance(row, ExposureInput) for row in result.exposures)
    assert all(
        row.provider == "ishares" and row.as_of_date == result.as_of_date
        for row in result.exposures
    )
    assert exact_sum(row.weight for row in result.holdings) == Decimal(1)
    assert _weights(result, "security")["AAPL"] == Decimal("0.577057580191699446449064")
    assert _weights(result, "security")["NVDA"] == Decimal("0.422787939539272534451059")
    assert "SOC" not in _weights(result, "security")
    assert "TGLS" not in _weights(result, "security")
    assert _weights(result, "country")["Colombia"] > 0
    assert result.holdings[-1].market_value == Decimal("1620449.58")
    assert result.holdings[-1].weight > 0
    coverage = {row.dimension: row for row in result.coverage}
    assert all(isinstance(row, IsharesDimensionCoverage) for row in result.coverage)
    assert coverage["sector"].total_weight == Decimal(1)
    assert coverage["sector"].complete is True
    assert exact_sum(_weights(result, "sector").values()) == Decimal(1)
    assert exact_sum(_weights(result, "country").values()) == Decimal(1)
    assert coverage["security"].shortfall > 0
    assert coverage["security"].total_weight == Decimal(1)


def test_positive_equity_rounded_zero_weight_foreign_and_placeholders_count_in_denominator() -> (
    None
):
    result = _run()
    eligible = [
        row for row in result.holdings if row.asset_class == "Equity" and row.market_value > 0
    ]
    assert len(eligible) == 6
    assert exact_sum(row.weight for row in eligible) == Decimal(1)
    tgls = next(row for row in eligible if row.ticker == "TGLS")
    assert tgls.weight > 0
    assert tgls.location == "Colombia"
    assert tgls.weight.quantize(Decimal("1e-12")) == Decimal("0.000138876331")
    assert next(row for row in eligible if row.ticker == "-").weight > 0
    assert result.coverage[0].eligible_holdings == 6
    assert result.coverage[0].observed_holdings == 2


def test_zero_market_value_equity_is_retained_diagnostically_but_excluded() -> None:
    body = FIXTURE.read_bytes().replace(b'"0.01","0.00","0.01"', b'"0.00","0.00","0.00"')
    result = _run(body)
    zero = next(row for row in result.holdings if row.name == "BOWL AMERICA INC ESCROW")
    assert zero.market_value == Decimal(0)
    assert zero.weight == Decimal(0)
    assert result.total_equity_market_value == Decimal("11668291953.01")


def test_signed_cash_2026_11_16_is_valid_but_not_in_equity_denominator() -> None:
    body = CASH_FIXTURE.read_bytes()
    equity = (
        b'"AAPL","APPLE","Information Technology","Equity","6,747,027,920.14","7.17",'
        b'"6,747,027,920.14","19,125,313.00","352.78","United States","NASDAQ","USD","1.00","USD","-"\n'
    )
    cash = body[body.index(b'"USD","USD CASH"') :]
    prefix = body[: body.index(b'"AAPL","APPLE"')]
    header = prefix + equity
    # This is a test composition of separately captured same-date rows, not a provider capture fixture.
    dated = header + cash
    result = _run(dated)
    assert result.as_of_date == date(2026, 11, 16)
    assert result.total_equity_market_value == Decimal("6747027920.14")
    assert len(result.holdings) == 2
    assert result.holdings[1].market_value == Decimal("-56366656.93")
    assert result.holdings[1].weight == Decimal(0)
    assert exact_sum(row.weight for row in result.holdings) == Decimal(1)


def test_weight_column_is_not_required_or_consulted() -> None:
    body = FIXTURE.read_bytes().replace(b",Weight (%),", b",Rounded ignored,")
    assert _run(body).total_equity_market_value == Decimal("11668291953.02")


def test_bom_header_reorder_and_quoted_market_values_are_supported() -> None:
    rows = list(csv.reader(FIXTURE.read_text().splitlines()[4:14]))
    header, source_rows = rows[0], rows[1:]
    reordered = [header[index] for index in (5, 0, 1, 2, 3, 9, 10, 4, 6, 7, 8, 11, 12, 13, 14)]
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(reordered)
    for row in source_rows:
        writer.writerow([row[header.index(column)] for column in reordered])
    result = _run(('\ufeffFund Holdings as of,"Nov 17, 2026"\n\n' + buffer.getvalue()).encode())
    assert result.total_equity_market_value == Decimal("11668291953.02")


@pytest.mark.parametrize("bad", ["", "-7.23", "NaN", "Infinity", "1e4", "1,23", "1,000,00"])
def test_invalid_negative_or_malformed_equity_market_values_fail(bad: str) -> None:
    body = FIXTURE.read_bytes().replace(b'"6,733,276,319.38"', f'"{bad}"'.encode(), 1)
    _expect_error(body)


@pytest.mark.parametrize(
    "mutation", ["date", "header", "partial", "duplicate", "tail", "missing_mv"]
)
def test_bad_dates_header_rows_duplicates_and_shape_fail(mutation: str) -> None:
    body = FIXTURE.read_bytes()
    if mutation == "date":
        body = body.replace(
            b'Fund Holdings as of,"Nov 17, 2026"', b"Fund Holdings as of,Nov 17 2026"
        )
    elif mutation == "header":
        body = body.replace(b"Ticker,Name,Sector", b"Asset,Name,Sector")
    elif mutation == "partial":
        body = body.replace(b'"AAPL","APPLE"', b'"AAPL",""')
    elif mutation == "duplicate":
        body = body.replace(b'"NVDA","NVIDIA"', b'"AAPL","APPLE"')
    elif mutation == "tail":
        body += b"\nlate,unknown,record\n"
    else:
        body = body.replace(b',"6,733,276,319.38",', b",,")
    _expect_error(body)


def test_duplicate_footer_and_unknown_structural_records_fail_closed() -> None:
    body = FIXTURE.read_bytes().replace(
        b'"TGLS","TECNOGLASS',
        b'"The content contained herein is owned or licensed by BlackRock and/or its third-party information providers and is protected by applicable copyrights, trademarks, service marks, and/or other intellectual property rights."\n"TGLS","TECNOGLASS',
    )
    _expect_error(body)


def test_response_size_transport_and_clock_are_bounded() -> None:
    _expect_error(b"x" * (MAX_RESPONSE_BYTES + 1))
    with pytest.raises(IsharesMarketDataError):
        _run(status=503)
    with pytest.raises(IsharesMarketDataError, match="UTC"):
        _run_with_clock(datetime(2026, 11, 18, 14, 8, 29))


def _run_with_clock(clock: datetime) -> IsharesExposureResult:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=FIXTURE.read_bytes())

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        return fetch_ishares_exposures(IsharesFundConfig("ITOT", URL), client, clock=lambda: clock)


@pytest.mark.parametrize("asset_class", ["Equit", "Stock", "", "Bond"])
def test_unknown_asset_class_fails_closed(asset_class: str) -> None:
    body = FIXTURE.read_bytes().replace(
        b'"AAPL","APPLE","Information Technology","Equity"',
        f'"AAPL","APPLE","Information Technology","{asset_class}"'.encode(),
    )
    _expect_error(body)


@pytest.mark.parametrize(
    ("ticker", "url"), [("DGRO", URL), ("ITOT", URL + "?other"), ("ITOT", "https://example.com")]
)
def test_unverified_fund_or_url_rejected_before_transport(ticker: str, url: str) -> None:
    with pytest.raises(IsharesMarketDataError):
        IsharesFundConfig(ticker, url)


def test_as_of_date_in_footer_cannot_replace_missing_preamble_date() -> None:
    body = FIXTURE.read_bytes().replace(b'Fund Holdings as of,"Nov 17, 2026"\n', b"")
    body = body.replace(
        b"The content contained herein is owned or licensed by BlackRock",
        b"The content contained herein is owned or licensed by BlackRock\n"
        b'Fund Holdings as of,"Nov 17, 2026"',
    )
    _expect_error(body)


class _ChunkStream(httpx.SyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks
        self.iterated = 0

    @override
    def __iter__(self) -> Iterator[bytes]:
        for chunk in self.chunks:
            self.iterated += 1
            yield chunk

    @override
    def close(self) -> None:
        pass


def test_streamed_response_checks_identity_encoding_and_remaining_budget() -> None:
    chunks = _ChunkStream([b"x" * MAX_RESPONSE_BYTES, b"y"])
    seen_headers: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.append(request.headers["accept-encoding"])
        return httpx.Response(200, stream=chunks)

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(IsharesMarketDataError, match="8 MiB"),
    ):
        fetch_ishares_exposures(IsharesFundConfig("ITOT", URL), client, clock=lambda: FETCHED_AT)
    assert seen_headers == ["identity"]
    assert chunks.iterated == 2


def test_encoded_response_is_rejected_before_reading_body() -> None:
    class UnreadableStream(httpx.SyncByteStream):
        @override
        def __iter__(self) -> Iterator[bytes]:
            raise AssertionError("encoded body must not be iterated")

        @override
        def close(self) -> None:
            pass

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-encoding": "gzip"}, stream=UnreadableStream())

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(IsharesMarketDataError, match="content encoding"),
    ):
        fetch_ishares_exposures(IsharesFundConfig("ITOT", URL), client, clock=lambda: FETCHED_AT)


def test_configured_httpx_redirect_is_not_followed() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(302, headers={"location": "https://off-host.example/redirected"})

    with (
        httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client,
        pytest.raises(IsharesMarketDataError),
    ):
        fetch_ishares_exposures(IsharesFundConfig("ITOT", URL), client, clock=lambda: FETCHED_AT)

    assert [str(request.url) for request in requests] == [URL]


def test_blank_equity_ticker_and_location_remain_in_denominator_with_gaps() -> None:
    body = FIXTURE.read_bytes().replace(
        b'"AAPL","APPLE","Information Technology","Equity","6,733,276,319.38","7.23",'
        b'"6,733,276,319.38","19,133,518.00","351.91","United States","NASDAQ"',
        b'"","APPLE","Information Technology","Equity","6,733,276,319.38","7.23",'
        b'"6,733,276,319.38","19,133,518.00","351.91","","NASDAQ"',
    )
    result = _run(body)
    assert result.total_equity_market_value == Decimal("11668291953.02")
    assert exact_sum(row.weight for row in result.holdings) == Decimal(1)
    coverage = {row.dimension: row for row in result.coverage}
    assert coverage["security"].complete is False
    assert coverage["country"].complete is False
    assert "AAPL" not in _weights(result, "security")
    assert "" not in _weights(result, "country")
    assert coverage["country"].shortfall > 0
