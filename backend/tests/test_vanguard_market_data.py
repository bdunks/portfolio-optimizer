from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

from app.domain.exposure import aggregate_lookthrough_exposure
from app.domain.financial_inputs import LookThroughExposureInput, PositionInput
from app.schemas import ExposureInput
from app.services.market_data import (
    VanguardDimensionCoverage,
    VanguardExposureResult,
    VanguardFundConfig,
    VanguardMarketDataError,
    fetch_vanguard_exposures,
)
from tests.test_wash_exposure import _inputs, _metadata

FIXTURES = Path(__file__).parent / "fixtures" / "vanguard"
BASE_URL = "https://advisors.vanguard.com/investments/products/api/funds"
FUND_IDS = (
    ("VTI", "0970"),
    ("VB", "0969"),
    ("VXF", "0965"),
    ("VIG", "0920"),
    ("VEA", "0936"),
    ("VWO", "0964"),
    ("VTEB", "4391"),
)


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


def _config(ticker: str, fund_id: str) -> VanguardFundConfig:
    return VanguardFundConfig(ticker, fund_id, f"{BASE_URL}/{fund_id}/holdings/latest")


def _fixture_client(name: str) -> FakeClient:
    return FakeClient(FakeResponse((FIXTURES / f"{name.lower()}.json").read_bytes()))


def _fetch(client: FakeClient, config: VanguardFundConfig) -> VanguardExposureResult:
    return fetch_vanguard_exposures(config, client, timeout=3.25)


def _load_payload(name: str) -> dict[str, object]:
    payload = json.loads((FIXTURES / f"{name.lower()}.json").read_text())
    assert isinstance(payload, dict)
    return payload


def _encode_payload(payload: dict[str, object]) -> bytes:
    return json.dumps(payload).encode()


def _date_section(payload: dict[str, object]) -> dict[str, object]:
    section = payload["2026-10-31"]
    assert isinstance(section, dict)
    return section


def _coverage(result: VanguardExposureResult) -> dict[str, VanguardDimensionCoverage]:
    return {item.dimension: item for item in result.coverage}


def _weights(result: VanguardExposureResult, dimension: str) -> dict[str, Decimal]:
    return {
        item.exposure_key: item.weight for item in result.exposures if item.dimension == dimension
    }


@pytest.mark.parametrize(("ticker", "fund_id"), FUND_IDS)
def test_captured_provider_excerpts_preserve_configured_request_and_provenance(
    ticker: str,
    fund_id: str,
) -> None:
    client = _fixture_client(ticker)
    config = _config(ticker, fund_id)

    result = _fetch(client, config)

    assert client.calls == [(config.url, 3.25)]
    assert result.fund_ticker == ticker
    assert result.fund_id == fund_id
    assert result.source_url == config.url
    assert result.as_of_date == date(2026, 10, 31)
    assert result.identifiers
    assert all(isinstance(row, ExposureInput) for row in result.exposures)
    assert all(
        row.provider == "vanguard" and row.as_of_date == result.as_of_date
        for row in result.exposures
    )
    assert all(not coverage.complete for coverage in result.coverage)


def test_vti_excerpt_converts_direct_weights_exactly_and_excludes_overlapping_sections() -> None:
    result = _fetch(_fixture_client("VTI"), _config("VTI", "0970"))

    assert result.reported_weight_total == Decimal("0.1333707")
    assert _weights(result, "security") == {
        "AAPL": Decimal("0.0690493"),
        "NVDA": Decimal("0.0643214"),
    }
    assert _weights(result, "industry") == {
        "Semiconductors": Decimal("0.0643214"),
        "Technology Hardware, Storage & Peripherals": Decimal("0.0690493"),
    }
    assert _weights(result, "country") == {"US": Decimal("0.1333707")}
    assert not _weights(result, "sector")
    assert not _weights(result, "size")
    assert all(row.exposure_key != "SLCMT1142" for row in result.exposures)

    piii = next(item for item in result.identifiers if item.ticker == "PIII")
    assert (piii.section, piii.holding_name, piii.cusip, piii.sedol) == (
        "equity",
        "P3 Health Partners Inc",
        "744413204",
        "BQH7MZ4",
    )
    assert piii.weight is None
    coverage = _coverage(result)
    assert coverage["security"].observed_constituents == 2
    assert coverage["security"].total_constituents == 3
    assert coverage["security"].covered_weight == Decimal("0.1333707")
    assert coverage["security"].unavailable_weight_count == 1
    assert coverage["sector"].observed_constituents == 0
    assert coverage["sector"].complete is False
    assert coverage["size"].complete is False


def test_vea_keeps_distinct_listing_context_and_skips_colliding_tickers() -> None:
    result = _fetch(_fixture_client("VEA"), _config("VEA", "0936"))
    listings = [item for item in result.identifiers if item.ticker in {"SAP", "GFL", "SHOP"}]

    assert [item.holding_name for item in listings if item.ticker == "SAP"] == [
        "SAP SE",
        "Saputo Inc",
    ]
    gfl = [item for item in listings if item.ticker == "GFL"]
    assert [(item.cusip, item.sedol, item.country) for item in gfl] == [
        ("36168Q104", "BKDT649", "CA"),
        ("36168Q104", "BKDT650", "US"),
    ]
    assert {item.sedol for item in listings if item.ticker == "SHOP"} == {
        "BX865C7",
        "BXDZ9Z0",
    }
    security_keys = set(_weights(result, "security"))
    assert not security_keys.intersection({"SAP", "GFL", "SHOP"})
    assert "36168Q104" not in _weights(result, "cusip")
    assert _weights(result, "industry")["Environmental & Facilities Services"] == Decimal(
        "0.0004927"
    )
    assert _coverage(result)["security"].complete is False


def test_vwo_foreign_and_duplicate_tickers_are_not_security_exposures() -> None:
    result = _fetch(_fixture_client("VWO"), _config("VWO", "0964"))

    assert not _weights(result, "security")
    assert not _weights(result, "cusip")
    assert _coverage(result)["security"].observed_constituents == 0
    quanta_and_sunny = [item for item in result.identifiers if item.ticker == "2382"]
    assert [(item.holding_name, item.sedol) for item in quanta_and_sunny] == [
        ("Quanta Computer Inc", "6141011"),
        ("Sunny Optical Technology Group Co Ltd", "B1YBT08"),
    ]
    tsmc = next(item for item in result.identifiers if item.ticker == "2330")
    assert tsmc.cusip == ""
    blank = next(item for item in result.identifiers if item.ticker == "VGI-W3")
    assert (blank.cusip, blank.sedol, blank.weight) == ("", "BPXZ5G7", None)


def test_vteb_maps_bonds_by_cusip_not_repeated_issuer_ticker() -> None:
    result = _fetch(_fixture_client("VTEB"), _config("VTEB", "4391"))

    assert result.reported_weight_total == Decimal("0.0039265")
    assert _weights(result, "cusip") == {
        "74448XCX8": Decimal("0.0020769"),
        "13063EUN4": Decimal("0.0015258"),
        "74448XED0": Decimal("0.0002801"),
        "74442PSZ9": Decimal("0.0000437"),
    }
    assert not _weights(result, "security")
    pubgen = [item for item in result.identifiers if item.ticker == "PUBGEN"]
    assert [item.cusip for item in pubgen] == ["74448XCX8", "74448XED0", "74442PSZ9"]
    assert all(item.section == "fixedIncome" for item in pubgen)
    assert all(item.sedol == "" for item in pubgen)
    unavailable = next(item for item in result.identifiers if item.cusip == "64990AUU7")
    assert unavailable.weight is None
    assert "64990AUU7" not in _weights(result, "cusip")
    assert _coverage(result)["sector"].complete is False
    assert _coverage(result)["size"].complete is False


def test_unavailable_optimizer_sector_and_size_coverage_cannot_pass_sector_consumer() -> None:
    result = _fetch(_fixture_client("VTI"), _config("VTI", "0970"))
    exposure_rows = tuple(
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
        exposures=exposure_rows,
        metadata=_metadata(lookthrough_complete=True),
    )

    aggregate = aggregate_lookthrough_exposure(inputs, tickers=("VTI",), dimension="sector")

    assert aggregate.coverage.complete is False
    assert aggregate.coverage.missing_tickers == ("VTI",)
    assert _coverage(result)["sector"].complete is False
    assert not _weights(result, "sector")


def test_valid_empty_direct_arrays_return_incomplete_coverage() -> None:
    payload = _load_payload("VTEB")
    section = _date_section(payload)
    empty_equity: list[dict[str, object]] = []
    empty_fixed_income: list[dict[str, object]] = []
    section["equity"] = empty_equity
    section["fixedIncome"] = empty_fixed_income

    result = _fetch(
        FakeClient(FakeResponse(_encode_payload(payload))),
        _config("VTEB", "4391"),
    )

    assert result.exposures == ()
    assert result.identifiers == ()
    assert result.reported_weight_total == Decimal(0)
    assert all(not item.complete and item.total_constituents == 0 for item in result.coverage)


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        ("NaN", "must be a JSON number or blank"),
        ("Infinity", "must be a JSON number or blank"),
        ('"6.90493"', "must be a JSON number or blank"),
        ("true", "must be a JSON number or blank"),
        ("-0.01", "between 0 and 100"),
        ("100.01", "between 0 and 100"),
        ("1e1001", "bounded decimal exponent"),
        ("1e-1001", "bounded decimal exponent"),
    ],
)
def test_malformed_or_out_of_range_numeric_weights_fail_explicitly(
    replacement: str,
    message: str,
) -> None:
    content = (FIXTURES / "vti.json").read_bytes()
    mutated = content.replace(
        b'"percentOfFunds": 6.90493',
        f'"percentOfFunds": {replacement}'.encode(),
        1,
    )

    with pytest.raises(VanguardMarketDataError, match=message):
        _fetch(FakeClient(FakeResponse(mutated)), _config("VTI", "0970"))


def test_exact_decimal_conversion_preserves_long_json_numbers() -> None:
    percentage = "33." + "3" * 80 + "4"
    content = (
        (FIXTURES / "vti.json")
        .read_bytes()
        .replace(
            b'"percentOfFunds": 6.90493',
            f'"percentOfFunds": {percentage}'.encode(),
            1,
        )
    )

    result = _fetch(FakeClient(FakeResponse(content)), _config("VTI", "0970"))

    source_value = Decimal(percentage)
    exponent = source_value.as_tuple().exponent
    assert isinstance(exponent, int)
    expected = Decimal((source_value.as_tuple().sign, source_value.as_tuple().digits, exponent - 2))
    assert _weights(result, "security")["AAPL"] == expected


def test_exact_total_above_one_is_rejected_without_renormalization() -> None:
    content = (FIXTURES / "vti.json").read_bytes()
    content = content.replace(b'"percentOfFunds": 6.90493', b'"percentOfFunds": 60', 1)
    content = content.replace(b'"percentOfFunds": 6.43214', b'"percentOfFunds": 41', 1)

    with pytest.raises(VanguardMarketDataError, match="direct holding weights exceed 100 percent"):
        _fetch(FakeClient(FakeResponse(content)), _config("VTI", "0970"))


def test_duplicate_true_listing_is_rejected_but_shared_cusip_listings_are_preserved() -> None:
    vea = _fetch(_fixture_client("VEA"), _config("VEA", "0936"))
    gfl = [item for item in vea.identifiers if item.cusip == "36168Q104"]
    assert len(gfl) == 2
    assert len({item.sedol for item in gfl}) == 2

    payload = _load_payload("VEA")
    section = _date_section(payload)
    rows = cast(list[dict[str, object]], section["equity"])
    rows.append(dict(rows[2]))
    client = FakeClient(FakeResponse(_encode_payload(payload)))

    with pytest.raises(VanguardMarketDataError, match="Duplicate Vanguard listing identity"):
        _fetch(client, _config("VEA", "0936"))


def test_repeated_bond_cusip_is_excluded_from_coverage_without_double_counting() -> None:
    payload = _load_payload("VTEB")
    section = _date_section(payload)
    rows = cast(list[dict[str, object]], section["fixedIncome"])
    duplicate = dict(rows[0])
    duplicate["sedol"] = "DISTINCT-LISTING"
    rows.append(duplicate)

    result = _fetch(
        FakeClient(FakeResponse(_encode_payload(payload))),
        _config("VTEB", "4391"),
    )

    assert "74448XCX8" not in _weights(result, "cusip")
    assert _coverage(result)["cusip"].observed_constituents == 3
    assert _coverage(result)["cusip"].complete is False
    assert sum(_weights(result, "cusip").values(), Decimal(0)) == Decimal("0.0018496")


def test_equity_ticker_collision_with_a_bond_issuer_is_not_emitted_as_security() -> None:
    payload = _load_payload("VTI")
    section = _date_section(payload)
    bonds = _date_section(_load_payload("VTEB"))["fixedIncome"]
    assert isinstance(bonds, list)
    bond = cast(dict[str, object], dict(bonds[0]))
    bond["ticker"] = "AAPL"
    section["fixedIncome"] = [bond]

    result = _fetch(
        FakeClient(FakeResponse(_encode_payload(payload))),
        _config("VTI", "0970"),
    )

    assert "AAPL" not in _weights(result, "security")
    assert len([item for item in result.identifiers if item.ticker == "AAPL"]) == 2


@pytest.mark.parametrize(
    ("section_name", "section_value", "message"),
    [
        ("equity", None, "equity direct holdings must be an array"),
        ("fixedIncome", {}, "fixedIncome direct holdings must be an array"),
    ],
)
def test_malformed_direct_arrays_are_rejected(
    section_name: str,
    section_value: object,
    message: str,
) -> None:
    payload = _load_payload("VTI")
    _date_section(payload)[section_name] = section_value

    with pytest.raises(VanguardMarketDataError, match=message):
        _fetch(
            FakeClient(FakeResponse(_encode_payload(payload))),
            _config("VTI", "0970"),
        )


def test_missing_direct_array_and_old_synthetic_root_are_not_accepted() -> None:
    payload = _load_payload("VTI")
    del _date_section(payload)["equity"]
    with pytest.raises(VanguardMarketDataError, match="equity direct holdings must be an array"):
        _fetch(
            FakeClient(FakeResponse(_encode_payload(payload))),
            _config("VTI", "0970"),
        )

    old_shape = b'{"as_of_date":"2026-10-31","holdings":[]}'
    with pytest.raises(VanguardMarketDataError, match="latestEffectiveDate"):
        _fetch(FakeClient(FakeResponse(old_shape)), _config("VTI", "0970"))


def test_missing_weight_or_effective_date_section_is_rejected() -> None:
    payload = _load_payload("VTI")
    section = _date_section(payload)
    rows = cast(list[dict[str, object]], section["equity"])
    del rows[0]["percentOfFunds"]
    with pytest.raises(VanguardMarketDataError, match="percentOfFunds is required"):
        _fetch(
            FakeClient(FakeResponse(_encode_payload(payload))),
            _config("VTI", "0970"),
        )

    payload = _load_payload("VTI")
    del payload["2026-10-31"]
    with pytest.raises(VanguardMarketDataError, match="effective-date section"):
        _fetch(
            FakeClient(FakeResponse(_encode_payload(payload))),
            _config("VTI", "0970"),
        )


@pytest.mark.parametrize("date_value", [" 2026-10-31", "20261031", "2026-W44-6"])
def test_noncanonical_effective_date_is_rejected(date_value: str) -> None:
    payload = _load_payload("VTI")
    payload["latestEffectiveDate"] = date_value

    with pytest.raises(VanguardMarketDataError, match="latestEffectiveDate must be an ISO date"):
        _fetch(
            FakeClient(FakeResponse(_encode_payload(payload))),
            _config("VTI", "0970"),
        )


def test_invalid_json_and_http_failure_are_explicit() -> None:
    config = _config("VTI", "0970")
    with pytest.raises(VanguardMarketDataError, match="request failed"):
        _fetch(FakeClient(FakeResponse(b"{")), config)
    with pytest.raises(VanguardMarketDataError, match="request failed"):
        _fetch(FakeClient(FakeResponse(b"{}", status_error=RuntimeError("HTTP 503"))), config)
