from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.schemas import ExposureInput
from app.services.ishares_market_data import (
    ITOT_URL,
    IsharesDimensionCoverage,
    IsharesExposureResult,
    IsharesFundConfig,
    IsharesMarketDataError,
    fetch_ishares_exposures,
)

FIXTURE = Path(__file__).parent / "fixtures" / "ishares" / "itot_excerpt.csv"
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
            IsharesFundConfig("ITOT", URL),
            client,
            clock=lambda: FETCHED_AT,
            timeout=2.5,
        )


def _expect_error(content: bytes) -> None:
    with pytest.raises(IsharesMarketDataError):
        _run(content)


def test_captured_excerpt_returns_exact_typed_exposures_and_provenance() -> None:
    result = _run()
    assert result.fund_ticker == "ITOT"
    assert result.source_url == URL
    assert result.as_of_date == date(2026, 11, 17)
    assert result.fetched_at == FETCHED_AT
    assert result.reported_weight_total == Decimal("0.1268")
    assert all(isinstance(row, ExposureInput) for row in result.exposures)
    assert all(
        row.provider == "ishares" and row.as_of_date == result.as_of_date
        for row in result.exposures
    )
    weights = {(row.dimension, row.exposure_key): row.weight for row in result.exposures}
    assert weights[("security", "AAPL")] == Decimal("0.0723")
    assert weights[("security", "NVDA")] == Decimal("0.0530")
    assert weights[("sector", "Information Technology")] == Decimal("0.1254")
    assert weights[("sector", "Energy")] == Decimal(0)
    assert "SOC" not in {key for dimension, key in weights if dimension == "security"}
    assert "BOWL AMERICA INC ESCROW" in {holding.name for holding in result.holdings}
    assert len(result.holdings) == 9
    coverage = {row.dimension: row for row in result.coverage}
    assert all(isinstance(row, IsharesDimensionCoverage) for row in result.coverage)
    assert coverage["security"].covered_weight == Decimal("0.1253")
    assert coverage["security"].shortfall == Decimal("0.0001")
    assert coverage["sector"].total_weight == Decimal("0.1254")
    assert coverage["security"].eligible_holdings == 6


def test_bom_header_column_reorder_and_quoting_are_supported() -> None:
    import csv
    import io

    rows = list(csv.reader(FIXTURE.read_text().splitlines()[4:14]))
    header, source_rows = rows[0], rows[1:]
    reordered = [header[index] for index in (5, 0, 1, 2, 3, 9, 10, 4, 6, 7, 8, 11, 12, 13, 14)]
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(reordered)
    for row in source_rows:
        writer.writerow([row[header.index(column)] for column in reordered])
    output = '\ufeffFund Holdings as of,"Nov 17, 2026"\n\n' + buffer.getvalue()
    result = _run(output.encode())
    assert result.reported_weight_total == Decimal("0.1268")


@pytest.mark.parametrize(
    "mutation",
    ["date", "header", "negative", "nan", "infinity", "partial", "duplicate", "tail"],
)
def test_bad_dates_headers_rows_weights_duplicates_and_structural_tail_fail(mutation: str) -> None:
    body = FIXTURE.read_bytes()
    if mutation == "date":
        changed = body.replace(
            b'Fund Holdings as of,"Nov 17, 2026"', b"Fund Holdings as of,Nov 17 2026"
        )
    elif mutation == "header":
        changed = body.replace(b"Ticker,Name,Sector", b"Asset,Name,Sector")
    elif mutation in {"negative", "nan", "infinity"}:
        value = {"negative": b"-7.23", "nan": b'"NaN"', "infinity": b'"Infinity"'}[mutation]
        changed = body.replace(b',"7.23",', b"," + value + b",", 1)
    elif mutation == "partial":
        changed = body.replace(b'"AAPL","APPLE"', b'"AAPL",""')
    elif mutation == "duplicate":
        changed = body.replace(b'"NVDA","NVIDIA"', b'"AAPL","APPLE"')
    else:
        changed = body + b"\nlate,unknown,record\n"
    _expect_error(changed)


def test_transport_failures_and_unsupported_clock_fail_explicitly() -> None:
    def failing(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    with (
        httpx.Client(transport=httpx.MockTransport(failing)) as client,
        pytest.raises(IsharesMarketDataError),
    ):
        fetch_ishares_exposures(IsharesFundConfig("ITOT", URL), client, clock=lambda: FETCHED_AT)
    with pytest.raises(IsharesMarketDataError, match="UTC"):
        _run_with_clock(datetime(2026, 11, 18, 14, 8, 29))


def _run_with_clock(clock: datetime) -> IsharesExposureResult:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=FIXTURE.read_bytes())

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        return fetch_ishares_exposures(IsharesFundConfig("ITOT", URL), client, clock=lambda: clock)


def test_footer_is_the_only_recognized_nonposition_structural_record() -> None:
    body = FIXTURE.read_bytes().replace(
        b'"The content contained herein', b'"Unknown structural record'
    )
    _expect_error(body)
