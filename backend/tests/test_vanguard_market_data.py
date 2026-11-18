from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.domain.exposure import aggregate_lookthrough_exposure
from app.domain.financial_inputs import LookThroughExposureInput, PositionInput
from app.schemas import ExposureInput
from app.services.market_data import (
    VanguardExposureResult,
    VanguardFundConfig,
    VanguardMarketDataError,
    fetch_vanguard_exposures,
)
from tests.test_wash_exposure import _inputs, _metadata

FIXTURES = Path(__file__).parent / "fixtures" / "vanguard" / "v1"
CONFIG = VanguardFundConfig("VTI", "1001", "https://configured.invalid/holdings")


class FakeResponse:
    def __init__(self, content: bytes, *, status_error: Exception | None = None) -> None:
        self.content = content
        self.status_error = status_error

    def raise_for_status(self) -> None:
        if self.status_error is not None:
            raise self.status_error


class FakeClient:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, float]] = []

    def get(self, url: str, *, timeout: float) -> FakeResponse:
        self.calls.append((url, timeout))
        return self.response


def _client_for_fixture(name: str) -> FakeClient:
    return FakeClient(FakeResponse((FIXTURES / name).read_bytes()))


def _load_valid() -> dict[str, object]:
    return json.loads((FIXTURES / "valid.json").read_text())


def _fetch(client: FakeClient) -> VanguardExposureResult:
    return fetch_vanguard_exposures(CONFIG, client, timeout=3.25)


def test_valid_v1_converts_exact_weights_and_preserves_provenance() -> None:
    client = _client_for_fixture("valid.json")

    result = _fetch(client)

    assert client.calls == [(CONFIG.url, 3.25)]
    assert result.fund_ticker == "VTI"
    assert result.fund_id == "1001"
    assert result.source_url == CONFIG.url
    assert result.as_of_date == date(2026, 9, 30)
    security_rows = [row for row in result.exposures if row.dimension == "security"]
    assert [(row.exposure_key, row.weight) for row in security_rows] == [
        ("AAA", Decimal("0.12345")),
        ("BBB", Decimal("0.07655")),
    ]
    assert all(isinstance(row, ExposureInput) for row in result.exposures)
    assert all(
        row.provider == "vanguard" and row.as_of_date == result.as_of_date
        for row in result.exposures
    )
    assert [(item.ticker, item.cusip) for item in result.identifiers] == [
        ("AAA", "000000001"),
        ("BBB", "000000002"),
        (None, "000000003"),
    ]
    assert not any(row.exposure_key.startswith("000") for row in security_rows)
    assert [
        (item.dimension, item.observed_constituents, item.total_constituents, item.complete)
        for item in result.coverage
    ] == [
        ("security", 2, 3, False),
        ("sector", 2, 3, False),
        ("size", 2, 3, False),
    ]

    domain_rows = tuple(
        LookThroughExposureInput(
            ticker=row.ticker,
            dimension=row.dimension,
            exposure_key=row.exposure_key,
            weight=row.weight,
            provider=row.provider,
            as_of_date=row.as_of_date,
        )
        for row in result.exposures
    )
    assert all(isinstance(row, LookThroughExposureInput) for row in domain_rows)
    assert not any(
        row.dimension == "sector" and row.exposure_key == "Unknown" for row in domain_rows
    )
    inputs = _inputs(
        positions=(
            PositionInput(
                ticker="VTI",
                asset_type="ETF",
                is_completion_etf=False,
                shares=Decimal(1),
                sync_generation=1,
                as_of=datetime(2026, 11, 13, 16, 0, tzinfo=UTC),
                market_value_usd=Decimal(100),
                assignment=None,
            ),
        ),
        exposures=domain_rows,
        metadata=_metadata(lookthrough_complete=False),
    )
    sector_aggregate = aggregate_lookthrough_exposure(inputs, tickers=("VTI",), dimension="sector")
    assert sector_aggregate.coverage.complete is False
    assert sector_aggregate.coverage.invalid_tickers == ("VTI",)


def test_empty_section_is_not_claimed_complete() -> None:
    result = _fetch(_client_for_fixture("empty.json"))

    assert result.exposures == ()
    assert result.identifiers == ()
    assert all(not item.complete and item.total_constituents == 0 for item in result.coverage)


def test_missing_dimension_rows_remain_missing_without_renormalizing() -> None:
    result = _fetch(_client_for_fixture("missing_dimensions.json"))

    assert [(row.dimension, row.weight) for row in result.exposures] == [("security", Decimal(1))]
    assert [
        (item.dimension, item.observed_constituents, item.complete) for item in result.coverage
    ] == [
        ("security", 1, True),
        ("sector", 0, False),
        ("size", 0, False),
    ]


@pytest.mark.parametrize(
    ("name", "expected_complete"),
    [("fully_labeled_underweight.json", False)],
)
def test_fully_labeled_underweight_response_is_incomplete(
    name: str, expected_complete: bool
) -> None:
    result = _fetch(_client_for_fixture(name))
    assert all(item.complete is expected_complete for item in result.coverage)
    assert sum(
        (row.weight for row in result.exposures if row.dimension == "sector"), Decimal(0)
    ) == Decimal("0.99")


def test_fully_labeled_overweight_response_is_rejected() -> None:
    with pytest.raises(VanguardMarketDataError, match="exceed 100 percent"):
        _fetch(_client_for_fixture("fully_labeled_overweight.json"))


def test_shared_classifications_emit_one_exactly_aggregated_row_per_key() -> None:
    payload = {
        "schema_version": "vanguard.holdings.v1",
        "fund": {"ticker": "VTI", "id": "1001"},
        "as_of_date": "2026-09-30",
        "holdings": [
            {"ticker": "AAA", "weight_pct": "60", "sector": "Technology", "size": "Large"},
            {"ticker": "BBB", "weight_pct": "40", "sector": "Technology", "size": "Large"},
        ],
    }
    result = _fetch(FakeClient(FakeResponse(json.dumps(payload).encode())))
    assert all(item.complete for item in result.coverage)
    assert [
        (row.dimension, row.exposure_key, row.weight)
        for row in result.exposures
        if row.dimension in {"sector", "size"}
    ] == [
        ("sector", "Technology", Decimal(1)),
        ("size", "Large", Decimal(1)),
    ]


def test_percentage_conversion_is_exact_beyond_default_decimal_precision() -> None:
    percentage = "33." + "3" * 80 + "4"
    payload = {
        "schema_version": "vanguard.holdings.v1",
        "fund": {"ticker": "VTI", "id": "1001"},
        "as_of_date": "2026-09-30",
        "holdings": [
            {"ticker": "AAA", "weight_pct": percentage},
            {"ticker": "BBB", "weight_pct": "0"},
        ],
    }
    result = _fetch(FakeClient(FakeResponse(json.dumps(payload).encode())))
    security_row = next(row for row in result.exposures if row.exposure_key == "AAA")
    source_weight = Decimal(percentage)
    exponent = source_weight.as_tuple().exponent
    assert isinstance(exponent, int)
    expected = Decimal(
        (source_weight.as_tuple().sign, source_weight.as_tuple().digits, exponent - 2)
    )
    assert security_row.weight == expected


def test_missing_holdings_section_is_rejected_explicitly() -> None:
    payload = _load_valid()
    del payload["holdings"]
    with pytest.raises(VanguardMarketDataError, match="does not match the v1 contract"):
        _fetch(FakeClient(FakeResponse(json.dumps(payload).encode())))


def test_adapter_derived_complete_coverage_flows_to_sector_consumer() -> None:
    payload = {
        "schema_version": "vanguard.holdings.v1",
        "fund": {"ticker": "VTI", "id": "1001"},
        "as_of_date": "2026-11-05",
        "holdings": [
            {"ticker": "AAA", "weight_pct": "60", "sector": "Technology", "size": "Large"},
            {"ticker": "BBB", "weight_pct": "40", "sector": "Industrials", "size": "Large"},
        ],
    }
    result = _fetch(FakeClient(FakeResponse(json.dumps(payload).encode())))
    domain_rows = tuple(
        LookThroughExposureInput(
            ticker=row.ticker,
            dimension=row.dimension,
            exposure_key=row.exposure_key,
            weight=row.weight,
            provider=row.provider,
            as_of_date=row.as_of_date,
        )
        for row in result.exposures
    )
    derived_coverage = all(item.complete for item in result.coverage)
    inputs = _inputs(
        positions=(
            PositionInput(
                ticker="VTI",
                asset_type="ETF",
                is_completion_etf=False,
                shares=Decimal(1),
                sync_generation=1,
                as_of=datetime(2026, 11, 5, 16, 0, tzinfo=UTC),
                market_value_usd=Decimal(100),
                assignment=None,
            ),
        ),
        exposures=domain_rows,
        metadata=_metadata(lookthrough_complete=derived_coverage),
    )
    aggregate = aggregate_lookthrough_exposure(inputs, tickers=("VTI",), dimension="sector")
    assert derived_coverage is True
    assert aggregate.coverage.complete is True
    assert aggregate.coverage.invalid_tickers == ()


@pytest.mark.parametrize(
    "name",
    ["unknown_dimension.json", "duplicate_identifiers.json", "duplicate_cusips.json"],
)
def test_unsupported_dimensions_and_duplicate_identifiers_rejected(name: str) -> None:
    with pytest.raises(VanguardMarketDataError):
        _fetch(_client_for_fixture(name))


@pytest.mark.parametrize("weight", ["not-a-number", "NaN", "Infinity", "-0.01", "100.01"])
def test_malformed_nonfinite_negative_and_over_100_weights_rejected(weight: str) -> None:
    payload = _load_valid()
    holdings = payload["holdings"]
    assert isinstance(holdings, list)
    first = holdings[0]
    assert isinstance(first, dict)
    first["weight_pct"] = weight
    client = FakeClient(FakeResponse(json.dumps(payload).encode()))

    with pytest.raises(VanguardMarketDataError):
        _fetch(client)


def test_invalid_json_and_http_failure_are_explicit() -> None:
    with pytest.raises(VanguardMarketDataError, match="request failed"):
        _fetch(FakeClient(FakeResponse(b"{")))
    with pytest.raises(VanguardMarketDataError, match="request failed"):
        _fetch(FakeClient(FakeResponse(b"{}", status_error=RuntimeError("HTTP 503"))))


def test_configured_fund_mismatch_is_rejected() -> None:
    payload = _load_valid()
    fund = payload["fund"]
    assert isinstance(fund, dict)
    fund["id"] = "wrong-id"
    client = FakeClient(FakeResponse(json.dumps(payload).encode()))

    with pytest.raises(VanguardMarketDataError, match="does not match configured fund"):
        _fetch(client)
