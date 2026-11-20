from __future__ import annotations

import csv
import io
import json
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.broker.fake import FakeBroker
from app.db.migrate import upgrade_database
from app.db.models import (
    Account,
    ExposureCacheState,
    ExposureDimensionCoverage,
    Security,
    SecurityExposure,
    SyncState,
)
from app.db.session import create_database_engine, make_session_factory
from app.domain.exposure import aggregate_lookthrough_exposure
from app.domain.financial_inputs import financial_inputs_from_provenance
from app.schemas import ExposureInput
from app.services.errors import AppError
from app.services.exposure_cache import (
    ExposureCacheTickerStatus,
    LocalCsvExposureConfig,
    LocalExposureCsvError,
    get_exposure_cache_status,
    parse_local_exposure_csv,
    refresh_exposure_cache,
)
from app.services.financial_input_loader import load_financial_inputs
from app.services.ishares_market_data import ITOT_URL, IsharesFundConfig
from app.services.market_data import VanguardFundConfig
from app.services.sync import sync_portfolio

FIXTURE_DIR = Path(__file__).parent / "fixtures"
FETCHED_AT = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)


def _database(
    tmp_path: Path, name: str = "exposure-cache.sqlite3"
) -> tuple[Engine, sessionmaker[Session]]:
    engine = create_database_engine(f"sqlite:///{tmp_path / name}")
    upgrade_database(engine)
    return engine, make_session_factory(engine)


def _write_csv(
    path: Path,
    ticker: str,
    as_of: date,
    rows: Sequence[tuple[str, str, str]],
) -> None:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(("ticker", "as_of_date", "dimension", "exposure_key", "weight"))
    for dimension, exposure_key, weight in rows:
        writer.writerow((ticker, as_of.isoformat(), dimension, exposure_key, weight))
    path.write_text(output.getvalue(), encoding="utf-8")


def _simple_csv(
    path: Path,
    ticker: str,
    as_of: date,
    *,
    security_key: str = "AAA",
    security_weight: str = "1",
    sector: str | None = None,
) -> None:
    rows = [("security", security_key, security_weight)]
    if sector is not None:
        rows.append(("sector", sector, "1"))
    _write_csv(path, ticker, as_of, rows)


def _client(body: bytes, expected_url: str | None = None) -> httpx.Client:
    def handle(request: httpx.Request) -> httpx.Response:
        if expected_url is not None:
            assert str(request.url) == expected_url
        return httpx.Response(200, content=body)

    return httpx.Client(transport=httpx.MockTransport(handle))


def _status(
    factory: sessionmaker[Session],
    source: LocalCsvExposureConfig | VanguardFundConfig | IsharesFundConfig,
    evaluation_date: date,
) -> ExposureCacheTickerStatus:
    with factory() as session:
        return get_exposure_cache_status(session, [source], evaluation_date=evaluation_date)[0]


def _rows_for_ticker(session: Session, ticker: str) -> Sequence[SecurityExposure]:
    return session.scalars(
        select(SecurityExposure)
        .join(Security, Security.id == SecurityExposure.security_id)
        .where(Security.ticker == ticker)
        .order_by(SecurityExposure.dimension, SecurityExposure.exposure_key)
    ).all()


def test_migration_and_multi_source_refresh_preserve_security_and_record_coverage(
    tmp_path: Path,
) -> None:
    engine, factory = _database(tmp_path)
    vanguard_url = (
        "https://advisors.vanguard.com/investments/products/api/funds/0969/holdings/latest"
    )
    vanguard = VanguardFundConfig("VB", "0969", vanguard_url)
    ishares = IsharesFundConfig("ITOT", ITOT_URL)
    local_path = tmp_path / "schd.csv"
    local = LocalCsvExposureConfig("SCHD", local_path)
    _simple_csv(local_path, "SCHD", date(2026, 11, 18), sector="Utilities")
    with factory.begin() as session:
        session.add(
            Security(
                ticker="ITOT",
                asset_type="EQUITY",
                is_completion_etf=False,
                cusip="KEEPITOTCLASS",
            )
        )

    vanguard_body = (FIXTURE_DIR / "vanguard" / "vb.json").read_bytes()
    ishares_body = (FIXTURE_DIR / "ishares" / "itot_excerpt.csv").read_bytes()
    with (
        _client(vanguard_body, vanguard_url) as vanguard_client,
        _client(ishares_body, ITOT_URL) as ishares_client,
    ):
        statuses = refresh_exposure_cache(
            factory,
            [vanguard, ishares, local],
            vanguard_client=vanguard_client,
            ishares_client=ishares_client,
            clock=lambda: FETCHED_AT,
        )

    assert [status.ticker for status in statuses] == ["VB", "ITOT", "SCHD"]
    assert [status.provider for status in statuses] == ["vanguard", "ishares", "manual_csv"]
    assert [status.as_of_date for status in statuses] == [
        date(2026, 10, 31),
        date(2026, 11, 17),
        date(2026, 11, 18),
    ]
    assert all(status.cached_at == FETCHED_AT for status in statuses)
    assert all(status.last_attempt_status == "success" for status in statuses)
    assert all(
        coverage.provider_universe_verified is False
        for status in statuses
        for coverage in status.dimensions
    )
    assert any(
        coverage.dimension == "sector" and not coverage.complete
        for coverage in statuses[0].dimensions
    )

    with factory() as session:
        assert (
            session.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            == "0013_exposure_cache"
        )
        vb = session.scalar(select(Security).where(Security.ticker == "VB"))
        schd = session.scalar(select(Security).where(Security.ticker == "SCHD"))
        itot = session.scalar(select(Security).where(Security.ticker == "ITOT"))
        assert vb is not None
        assert vb.asset_type == "ETF"
        assert vb.is_completion_etf
        assert schd is not None
        assert schd.asset_type == "ETF"
        assert itot is not None
        assert itot.asset_type == "EQUITY"
        assert itot.cusip == "KEEPITOTCLASS"
        assert len(_rows_for_ticker(session, "VB")) > 0
        assert len(_rows_for_ticker(session, "ITOT")) > 0
        assert len(_rows_for_ticker(session, "SCHD")) == 2
        assert session.scalar(select(ExposureCacheState).where(ExposureCacheState.ticker == "VB"))
        assert (
            session.scalar(
                select(ExposureDimensionCoverage).where(
                    ExposureDimensionCoverage.ticker == "ITOT",
                    ExposureDimensionCoverage.dimension == "security",
                )
            )
            is not None
        )
        assert "exposure_cache_state" in inspect(engine).get_table_names()
    engine.dispose()


def test_local_parser_requires_exact_format_and_reports_incomplete_dimension(
    tmp_path: Path,
) -> None:
    path = tmp_path / "holdings.csv"
    _write_csv(
        path,
        "SCHD",
        date(2026, 11, 18),
        [("security", "AAA", "0.6"), ("sector", "Utilities", "0.75")],
    )
    parsed = parse_local_exposure_csv(LocalCsvExposureConfig("SCHD", path))
    assert parsed.as_of_date == date(2026, 11, 18)
    assert [row.weight for row in parsed.exposures] == [Decimal("0.6"), Decimal("0.75")]
    coverage = {row.dimension: row for row in parsed.coverage}
    assert coverage["security"].complete is False
    assert coverage["sector"].covered_weight == Decimal("0.75")
    assert coverage["sector"].complete is False


def test_local_parser_normalizes_dimensions_and_keys_before_duplicate_and_total_checks(
    tmp_path: Path,
) -> None:
    path = tmp_path / "canonical.csv"
    path.write_text(
        "ticker,as_of_date,dimension,exposure_key,weight\n"
        "SCHD,2026-11-18,security,AAA,0.5\n"
        "SCHD,2026-11-18,ticker,aaa,0.5000000000000000000000000001\n",
        encoding="utf-8",
    )
    with pytest.raises(LocalExposureCsvError, match="duplicate dimension keys"):
        parse_local_exposure_csv(LocalCsvExposureConfig("SCHD", path))

    path.write_text(
        "ticker,as_of_date,dimension,exposure_key,weight\n"
        "SCHD,2026-11-18,SECTOR,Utilities,0.5\n"
        "SCHD,2026-11-18,sector,Consumer,0.5000000000000000000000000001\n",
        encoding="utf-8",
    )
    with pytest.raises(LocalExposureCsvError, match="weights exceed one"):
        parse_local_exposure_csv(LocalCsvExposureConfig("SCHD", path))


def test_local_parser_accepts_exact_byte_limit_and_rejects_one_byte_over(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import exposure_cache

    path = tmp_path / "boundary.csv"
    content = b"ticker,as_of_date,dimension,exposure_key,weight\nSCHD,2026-11-18,security,AAA,1\n"
    path.write_bytes(content)
    monkeypatch.setattr(exposure_cache, "MAX_LOCAL_CSV_BYTES", len(content))
    assert len(parse_local_exposure_csv(LocalCsvExposureConfig("SCHD", path)).exposures) == 1
    monkeypatch.setattr(exposure_cache, "MAX_LOCAL_CSV_BYTES", len(content) - 1)
    with pytest.raises(LocalExposureCsvError, match="size limit"):
        parse_local_exposure_csv(LocalCsvExposureConfig("SCHD", path))


@pytest.mark.parametrize(
    "content",
    [
        b"ticker,as_of_date,dimension,exposure_key,weight\nOTHER,2026-11-18,security,AAA,1\n",
        b"ticker,as_of_date,dimension,exposure_key,weight\nSCHD,2026-11-18,security,AAA,0.6\nSCHD,2026-11-18,security,AAA,0.4\n",
        b"ticker,as_of_date,dimension,exposure_key,weight\nSCHD,2026-11-18,security,AAA,0.6\nSCHD,2026-11-18,security,BBB,0.5\n",
        b"ticker,as_of_date,dimension,exposure_key,weight\nSCHD,2026-11-18,security,AAA,NaN\n",
        b"ticker,as_of_date,dimension,exposure_key,weight\nSCHD,2026-11-18,security,AAA,1e-1\n",
        b"ticker,as_of_date,dimension,exposure_key,weight\nSCHD,2026-11-18,security,AAA,1\nSCHD,2026-11-19,security,BBB,0\n",
        b'ticker,as_of_date,dimension,exposure_key,weight\nSCHD,2026-11-18,security,"unterminated,1\n',
        b"ticker,as_of_date,dimension,exposure_key,weight\n",
    ],
)
def test_local_parser_rejects_wrong_duplicate_overweight_malformed_or_interrupted_files(
    tmp_path: Path, content: bytes
) -> None:
    path = tmp_path / "invalid.csv"
    path.write_bytes(content)
    with pytest.raises(LocalExposureCsvError):
        parse_local_exposure_csv(LocalCsvExposureConfig("SCHD", path))


@pytest.mark.parametrize("failure", ["partial", "empty"])
def test_failed_mixed_provider_refresh_rolls_back_staged_changes_and_both_cache_entries(
    tmp_path: Path, failure: str
) -> None:
    engine, factory = _database(tmp_path)
    vanguard_url = (
        "https://advisors.vanguard.com/investments/products/api/funds/0969/holdings/latest"
    )
    vanguard = VanguardFundConfig("VB", "0969", vanguard_url)
    ishares = IsharesFundConfig("ITOT", ITOT_URL)
    vb_body = (FIXTURE_DIR / "vanguard" / "vb.json").read_bytes()
    itot_body = (FIXTURE_DIR / "ishares" / "itot_excerpt.csv").read_bytes()

    def clients(vb_status: int, vb_payload: bytes) -> tuple[httpx.Client, httpx.Client]:
        def vanguard_handler(request: httpx.Request) -> httpx.Response:
            assert str(request.url) == vanguard_url
            return httpx.Response(vb_status, content=vb_payload)

        def ishares_handler(request: httpx.Request) -> httpx.Response:
            assert str(request.url) == ITOT_URL
            return httpx.Response(200, content=itot_body)

        return (
            httpx.Client(transport=httpx.MockTransport(vanguard_handler)),
            httpx.Client(transport=httpx.MockTransport(ishares_handler)),
        )

    initial_clients = clients(200, vb_body)
    with initial_clients[0] as vanguard_client, initial_clients[1] as ishares_client:
        refresh_exposure_cache(
            factory,
            [vanguard, ishares],
            vanguard_client=vanguard_client,
            ishares_client=ishares_client,
            clock=lambda: FETCHED_AT,
        )

    with factory() as session:
        original: dict[
            str, tuple[list[tuple[object, ...]], list[tuple[object, ...]], date, int]
        ] = {}
        for ticker in ("VB", "ITOT"):
            state = session.get(ExposureCacheState, ticker)
            assert state is not None
            assert state.as_of_date is not None
            rows = _rows_for_ticker(session, ticker)
            coverage = session.scalars(
                select(ExposureDimensionCoverage)
                .where(ExposureDimensionCoverage.ticker == ticker)
                .order_by(ExposureDimensionCoverage.dimension)
            ).all()
            original[ticker] = (
                [(r.dimension, r.exposure_key, r.weight, r.provider, r.as_of_date) for r in rows],
                [
                    (r.dimension, r.covered_weight, r.complete, r.observed_item_count)
                    for r in coverage
                ],
                state.as_of_date,
                state.publication_revision,
            )

    if failure == "empty":
        payload = json.loads(vb_body)
        payload["2026-10-31"]["equity"] = []
        payload["2026-10-31"]["fixedIncome"] = []
        vb_body = json.dumps(payload).encode()
        vb_status = 200
    else:
        vb_status = 206
    changed_path = tmp_path / "staged.csv"
    staged_local = LocalCsvExposureConfig("SCHD", changed_path)
    _simple_csv(changed_path, "SCHD", date(2026, 11, 19), security_key="STAGED")
    current_clients = clients(vb_status, vb_body)
    with (
        current_clients[0] as vanguard_client,
        current_clients[1] as ishares_client,
        pytest.raises(AppError),
    ):
        refresh_exposure_cache(
            factory,
            [staged_local, vanguard, ishares],
            vanguard_client=vanguard_client,
            ishares_client=ishares_client,
            clock=lambda: FETCHED_AT + timedelta(days=1),
        )

    with factory() as session:
        for ticker in ("VB", "ITOT"):
            state = session.get(ExposureCacheState, ticker)
            assert state is not None
            rows = _rows_for_ticker(session, ticker)
            coverage = session.scalars(
                select(ExposureDimensionCoverage)
                .where(ExposureDimensionCoverage.ticker == ticker)
                .order_by(ExposureDimensionCoverage.dimension)
            ).all()
            assert [
                (r.dimension, r.exposure_key, r.weight, r.provider, r.as_of_date) for r in rows
            ] == original[ticker][0]
            assert [
                (r.dimension, r.covered_weight, r.complete, r.observed_item_count) for r in coverage
            ] == original[ticker][1]
            assert (state.as_of_date, state.publication_revision) == original[ticker][2:]
        assert _rows_for_ticker(session, "SCHD") == []
    engine.dispose()


@pytest.mark.parametrize("provider", ["vanguard", "ishares"])
def test_malformed_captured_provider_response_rolls_back_sqlite_publication(
    tmp_path: Path, provider: str
) -> None:
    engine, factory = _database(tmp_path)
    vanguard_url = (
        "https://advisors.vanguard.com/investments/products/api/funds/0969/holdings/latest"
    )
    if provider == "vanguard":
        source = VanguardFundConfig("VB", "0969", vanguard_url)
        payload = (FIXTURE_DIR / "vanguard" / "vb.json").read_bytes()
        malformed = payload.replace(
            b'"percentOfFunds": 0.7027,',
            b'"percentOfFunds": 0.7027, "percentOfFunds": 0,',
            1,
        )
    else:
        source = IsharesFundConfig("ITOT", ITOT_URL)
        payload = (FIXTURE_DIR / "ishares" / "itot_excerpt.csv").read_bytes()
        # Keep the captured preamble, header, and complete AAPL row; omit the terminal record.
        malformed = b"".join(payload.splitlines(keepends=True)[:6])
        assert b'"AAPL","APPLE"' in malformed
        assert b"BlackRock" not in malformed

    staged_path = tmp_path / "staged.csv"
    staged = LocalCsvExposureConfig("SCHD", staged_path)
    _simple_csv(staged_path, "SCHD", date(2026, 11, 19), security_key="STAGED")
    if provider == "vanguard":
        with _client(payload, vanguard_url) as client:
            refresh_exposure_cache(
                factory, [source], vanguard_client=client, clock=lambda: FETCHED_AT
            )
    else:
        with _client(payload, ITOT_URL) as client:
            refresh_exposure_cache(
                factory, [source], ishares_client=client, clock=lambda: FETCHED_AT
            )

    ticker = source.ticker
    with factory() as session:
        state = session.get(ExposureCacheState, ticker)
        assert state is not None
        assert state.as_of_date is not None
        assert state.cached_at is not None
        rows_before = [
            (row.dimension, row.exposure_key, row.weight, row.provider, row.as_of_date)
            for row in _rows_for_ticker(session, ticker)
        ]
        coverage_before = [
            (row.dimension, row.covered_weight, row.complete, row.observed_item_count)
            for row in session.scalars(
                select(ExposureDimensionCoverage)
                .where(ExposureDimensionCoverage.ticker == ticker)
                .order_by(ExposureDimensionCoverage.dimension)
            ).all()
        ]
        success_before = (state.as_of_date, state.cached_at, state.publication_revision)

    if provider == "vanguard":
        bad_vanguard, bad_ishares = _client(malformed, vanguard_url), _client(b"", ITOT_URL)
    else:
        bad_vanguard, bad_ishares = _client(b"", vanguard_url), _client(malformed, ITOT_URL)
    with (
        bad_vanguard as vanguard_client,
        bad_ishares as ishares_client,
        pytest.raises(AppError),
    ):
        refresh_exposure_cache(
            factory,
            [staged, source],
            vanguard_client=vanguard_client,
            ishares_client=ishares_client,
            clock=lambda: FETCHED_AT + timedelta(days=1),
        )

    with factory() as session:
        state = session.get(ExposureCacheState, ticker)
        assert state is not None
        assert [
            (row.dimension, row.exposure_key, row.weight, row.provider, row.as_of_date)
            for row in _rows_for_ticker(session, ticker)
        ] == rows_before
        assert [
            (row.dimension, row.covered_weight, row.complete, row.observed_item_count)
            for row in session.scalars(
                select(ExposureDimensionCoverage)
                .where(ExposureDimensionCoverage.ticker == ticker)
                .order_by(ExposureDimensionCoverage.dimension)
            ).all()
        ] == coverage_before
        assert (state.as_of_date, state.cached_at, state.publication_revision) == success_before
        assert _rows_for_ticker(session, "SCHD") == []
        assert (
            session.scalars(
                select(ExposureDimensionCoverage).where(ExposureDimensionCoverage.ticker == "SCHD")
            ).all()
            == []
        )
        staged_state = session.get(ExposureCacheState, "SCHD")
        assert staged_state is None or staged_state.last_attempt_status == "failure"
        assert staged_state is None or (
            staged_state.as_of_date is None
            and staged_state.cached_at is None
            and staged_state.publication_revision == 0
        )
    engine.dispose()


def test_failed_staged_batch_preserves_every_previous_success_and_unrelated_ticker(
    tmp_path: Path,
) -> None:
    engine, factory = _database(tmp_path)
    first_path, second_path = tmp_path / "first.csv", tmp_path / "second.csv"
    first = LocalCsvExposureConfig("SCHD", first_path)
    second = LocalCsvExposureConfig("VTI", second_path)
    old_date = date(2026, 11, 17)
    _simple_csv(first_path, "SCHD", old_date, security_key="AAA")
    _simple_csv(second_path, "VTI", old_date, security_key="BBB")
    refresh_exposure_cache(factory, [first, second], clock=lambda: FETCHED_AT)
    with factory() as session:
        original_first = [
            (row.dimension, row.exposure_key, row.weight, row.as_of_date)
            for row in _rows_for_ticker(session, "SCHD")
        ]
        original_second = [
            (row.dimension, row.exposure_key, row.weight, row.as_of_date)
            for row in _rows_for_ticker(session, "VTI")
        ]
        first_state = session.get(ExposureCacheState, "SCHD")
        assert first_state is not None
        first_revision = first_state.publication_revision
        original_cached_at = first_state.cached_at

    _simple_csv(first_path, "SCHD", date(2026, 11, 18), security_key="CCC")
    second_path.write_text("ticker,as_of_date,dimension,exposure_key,weight\n", encoding="utf-8")
    with pytest.raises(AppError) as error:
        refresh_exposure_cache(
            factory, [first, second], clock=lambda: FETCHED_AT + timedelta(days=1)
        )
    assert error.value.code == "exposure_refresh_failed"
    with factory() as session:
        assert [
            (row.dimension, row.exposure_key, row.weight, row.as_of_date)
            for row in _rows_for_ticker(session, "SCHD")
        ] == original_first
        assert [
            (row.dimension, row.exposure_key, row.weight, row.as_of_date)
            for row in _rows_for_ticker(session, "VTI")
        ] == original_second
        first_state = session.get(ExposureCacheState, "SCHD")
        second_state = session.get(ExposureCacheState, "VTI")
        assert first_state is not None
        assert second_state is not None
        assert first_state.publication_revision == first_revision
        assert first_state.cached_at == original_cached_at
        assert first_state.as_of_date == old_date
        assert first_state.last_attempt_status == "failure"
        assert first_state.last_error_code == "exposure_batch_aborted"
        assert second_state.last_attempt_status == "failure"
        assert second_state.last_error_code == "exposure_source_invalid"

    # A later subset refresh replaces only its requested ticker.
    _simple_csv(first_path, "SCHD", old_date, security_key="DDD")
    refresh_exposure_cache(factory, [first], clock=lambda: FETCHED_AT + timedelta(days=2))
    with factory() as session:
        assert [row.exposure_key for row in _rows_for_ticker(session, "VTI")] == ["BBB"]
        assert [row.exposure_key for row in _rows_for_ticker(session, "SCHD")] == ["DDD"]
    engine.dispose()


def test_freshness_uses_holdings_date_and_failure_is_independent_of_age(tmp_path: Path) -> None:
    engine, factory = _database(tmp_path)
    path = tmp_path / "fresh.csv"
    source_date = date(2026, 11, 17)
    source = LocalCsvExposureConfig("SCHD", path)
    _simple_csv(path, "SCHD", source_date)
    first_receipt = datetime(2026, 11, 18, 10, 0, tzinfo=UTC)
    refresh_exposure_cache(factory, [source], clock=lambda: first_receipt)

    second_receipt = datetime(2026, 11, 19, 10, 0, tzinfo=UTC)
    _simple_csv(path, "SCHD", source_date, security_key="BBB")
    refresh_exposure_cache(factory, [source], clock=lambda: second_receipt)
    with factory() as session:
        state = session.get(ExposureCacheState, "SCHD")
        assert state is not None
        assert state.as_of_date == source_date
        assert state.cached_at == second_receipt
        assert state.publication_revision == 2

    failure_time = datetime.combine(source_date + timedelta(days=95), datetime.min.time(), UTC)
    path.write_text("ticker,as_of_date,dimension,exposure_key,weight\n", encoding="utf-8")
    with pytest.raises(AppError):
        refresh_exposure_cache(factory, [source], clock=lambda: failure_time)
    day_95 = _status(factory, source, source_date + timedelta(days=95))
    day_96 = _status(factory, source, source_date + timedelta(days=96))
    assert day_95.freshness == "current"
    assert day_96.freshness == "stale"
    assert day_95.last_attempt_status == day_96.last_attempt_status == "failure"
    assert day_95.as_of_date == day_96.as_of_date == source_date
    assert day_95.cached_at == day_96.cached_at == second_receipt
    assert day_95.last_error_code == "exposure_source_invalid"
    assert any(row.dimension == "security" for row in day_95.dimensions)
    with factory() as session:
        assert [row.exposure_key for row in _rows_for_ticker(session, "SCHD")] == ["BBB"]
    engine.dispose()


def test_configured_missing_future_and_regressed_source_dates(tmp_path: Path) -> None:
    engine, factory = _database(tmp_path)
    path = tmp_path / "date.csv"
    source = LocalCsvExposureConfig("SCHD", path)
    missing = LocalCsvExposureConfig("VTI", tmp_path / "missing.csv")
    with pytest.raises(AppError):
        refresh_exposure_cache(factory, [missing], clock=lambda: FETCHED_AT)
    missing_status = _status(factory, missing, FETCHED_AT.date())
    assert missing_status.freshness == "configured_missing"
    assert missing_status.last_attempt_status == "failure"
    assert missing_status.provider is None

    current_date = date(2026, 11, 17)
    _simple_csv(path, "SCHD", current_date)
    refresh_exposure_cache(factory, [source], clock=lambda: FETCHED_AT)
    for rejected_date, expected_code in (
        (current_date - timedelta(days=1), "exposure_date_regression"),
        (FETCHED_AT.date() + timedelta(days=1), "exposure_date_invalid"),
    ):
        _simple_csv(path, "SCHD", rejected_date, security_key="BBB")
        with pytest.raises(AppError):
            refresh_exposure_cache(factory, [source], clock=lambda: FETCHED_AT)
        status = _status(factory, source, FETCHED_AT.date())
        assert status.last_error_code == expected_code
        assert status.as_of_date == current_date
        assert status.publication_revision == 1
        with factory() as session:
            assert [row.exposure_key for row in _rows_for_ticker(session, "SCHD")] == ["AAA"]
    engine.dispose()


def test_omitted_dimensions_are_replaced_and_post_write_failure_rolls_back(
    tmp_path: Path,
) -> None:
    engine, factory = _database(tmp_path)
    path = tmp_path / "dimensions.csv"
    source = LocalCsvExposureConfig("SCHD", path)
    current_date = date(2026, 11, 17)
    _simple_csv(path, "SCHD", current_date, sector="Utilities")
    refresh_exposure_cache(factory, [source], clock=lambda: FETCHED_AT)
    with factory() as session:
        assert {row.dimension for row in _rows_for_ticker(session, "SCHD")} == {
            "security",
            "sector",
        }
        first_state = session.get(ExposureCacheState, "SCHD")
        assert first_state is not None
        first_receipt = first_state.cached_at

    # The next successful snapshot explicitly omits sector, clearing both its rows and metadata.
    _simple_csv(path, "SCHD", current_date, security_key="BBB")
    refresh_exposure_cache(factory, [source], clock=lambda: FETCHED_AT + timedelta(days=1))
    with factory() as session:
        assert {row.dimension for row in _rows_for_ticker(session, "SCHD")} == {"security"}
        assert session.get(ExposureDimensionCoverage, ("SCHD", "sector")) is None
        state = session.get(ExposureCacheState, "SCHD")
        assert state is not None
        second_receipt = state.cached_at
        assert second_receipt != first_receipt
        assert state.publication_revision == 2

    _simple_csv(path, "SCHD", current_date, security_key="CCC")

    def fail_after_writes() -> None:
        raise RuntimeError("injected post-write rollback")

    with pytest.raises(AppError) as error:
        refresh_exposure_cache(
            factory,
            [source],
            clock=lambda: FETCHED_AT + timedelta(days=2),
            publication_hook=fail_after_writes,
        )
    assert error.value.code == "exposure_cache_publish_failed"
    with factory() as session:
        rows = _rows_for_ticker(session, "SCHD")
        state = session.get(ExposureCacheState, "SCHD")
        assert [(row.dimension, row.exposure_key, row.as_of_date) for row in rows] == [
            ("security", "BBB", current_date)
        ]
        assert state is not None
        assert state.provider == "manual_csv"
        assert state.as_of_date == current_date
        assert state.cached_at == second_receipt
        assert state.publication_revision == 2
        assert state.last_attempt_status == "failure"
    engine.dispose()


def test_newer_overlapping_publication_rejects_superseded_provider_attempt(tmp_path: Path) -> None:
    engine, factory = _database(tmp_path)
    vanguard_url = (
        "https://advisors.vanguard.com/investments/products/api/funds/0969/holdings/latest"
    )
    vanguard = VanguardFundConfig("VB", "0969", vanguard_url)
    path = tmp_path / "newer.csv"
    local = LocalCsvExposureConfig("VB", path)
    _simple_csv(path, "VB", FETCHED_AT.date(), security_key="NEW")
    vanguard_body = (FIXTURE_DIR / "vanguard" / "vb.json").read_bytes()

    def handle(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == vanguard_url
        # This refresh starts after the outer attempt captured revision zero and publishes first.
        refresh_exposure_cache(factory, [local], clock=lambda: FETCHED_AT)
        return httpx.Response(200, content=vanguard_body)

    with (
        httpx.Client(transport=httpx.MockTransport(handle)) as client,
        pytest.raises(AppError) as error,
    ):
        refresh_exposure_cache(
            factory,
            [vanguard],
            vanguard_client=client,
            clock=lambda: FETCHED_AT,
        )
    assert error.value.code == "exposure_refresh_superseded"
    with factory() as session:
        state = session.get(ExposureCacheState, "VB")
        rows = _rows_for_ticker(session, "VB")
        assert state is not None
        assert state.provider == "manual_csv"
        assert state.publication_revision == 1
        assert state.last_attempt_status == "success"
        assert state.last_error_code is None
        assert [(row.provider, row.exposure_key) for row in rows] == [("manual_csv", "NEW")]
    engine.dispose()


def test_success_survives_process_restart_with_sqlite_migration(tmp_path: Path) -> None:
    engine, factory = _database(tmp_path, "restart.sqlite3")
    path = tmp_path / "restart.csv"
    source = LocalCsvExposureConfig("SCHD", path)
    _simple_csv(path, "SCHD", date(2026, 11, 17), security_key="AAA")
    refresh_exposure_cache(factory, [source], clock=lambda: FETCHED_AT)
    database_url = str(engine.url)
    engine.dispose()

    restarted_engine = create_database_engine(database_url)
    upgrade_database(restarted_engine)
    restarted_factory = make_session_factory(restarted_engine)
    status = _status(restarted_factory, source, FETCHED_AT.date())
    assert status.freshness == "current"
    assert status.as_of_date == date(2026, 11, 17)
    assert status.provider == "manual_csv"
    assert status.last_attempt_status == "success"
    with restarted_factory() as session:
        assert [row.exposure_key for row in _rows_for_ticker(session, "SCHD")] == ["AAA"]
    restarted_engine.dispose()


ITOT_SOURCE_DATE = date(2026, 11, 17)


def test_itot_cache_evidence_loads_and_freezes_after_restart(tmp_path: Path) -> None:
    engine, factory = _database(tmp_path, "itot-cache-restart.sqlite3")
    database_url = str(engine.url)
    source = IsharesFundConfig("ITOT", ITOT_URL)
    body = (FIXTURE_DIR / "ishares" / "itot_excerpt.csv").read_bytes()
    requested_urls: list[str] = []

    def respond(status: int) -> httpx.Client:
        def handle(request: httpx.Request) -> httpx.Response:
            requested_urls.append(str(request.url))
            return httpx.Response(status, content=body)

        return httpx.Client(transport=httpx.MockTransport(handle))

    with factory.begin() as session:
        session.add(
            Account(
                id=1,
                broker_account_id_key="test-managed-account",
                display_name="Test account",
                account_type="BROKERAGE",
                tax_treatment="TAXABLE",
                cash_usd=Decimal(100),
                settled_buying_power_usd=Decimal(100),
                source="TEST",
                as_of=FETCHED_AT,
            )
        )
        session.add(
            SyncState(
                id=1,
                current_generation=1,
                coverage={"lookthrough": False},
                complete=True,
            )
        )
        session.add(Security(ticker="ITOT", asset_type="EQUITY"))

    with respond(200) as client:
        refresh_exposure_cache(factory, [source], ishares_client=client, clock=lambda: FETCHED_AT)
    second_receipt = FETCHED_AT + timedelta(days=1)
    with respond(200) as client:
        refresh_exposure_cache(
            factory, [source], ishares_client=client, clock=lambda: second_receipt
        )
    with respond(206) as client, pytest.raises(AppError):
        refresh_exposure_cache(
            factory,
            [source],
            ishares_client=client,
            clock=lambda: FETCHED_AT + timedelta(days=2),
        )

    with factory() as session:
        state = session.get(ExposureCacheState, "ITOT")
        assert state is not None
        assert state.provider == "ishares"
        assert state.as_of_date == ITOT_SOURCE_DATE
        assert state.cached_at == second_receipt
        assert state.last_attempt_status == "failure"
        assert state.publication_revision == 2
        coverage_rows = session.scalars(
            select(ExposureDimensionCoverage)
            .where(ExposureDimensionCoverage.ticker == "ITOT")
            .order_by(ExposureDimensionCoverage.dimension)
        ).all()
        assert coverage_rows
        assert all(not row.provider_universe_verified for row in coverage_rows)
    engine.dispose()

    restarted_engine = create_database_engine(database_url)
    upgrade_database(restarted_engine)
    restarted_factory = make_session_factory(restarted_engine)
    try:
        with restarted_factory() as session:
            account = session.get(Account, 1)
            sync_state = session.get(SyncState, 1)
            assert account is not None
            assert sync_state is not None
            inputs = load_financial_inputs(
                session,
                account,
                sync_state,
                None,
                ITOT_SOURCE_DATE + timedelta(days=95),
                require_resolved_assignments=False,
            )
            assert inputs.exposure_cache
            assert any(
                row.dimension == "security" and not row.complete
                for row in inputs.exposure_cache[0].dimensions
            )
            evidence = inputs.exposure_cache[0]
            assert (evidence.ticker, evidence.provider, evidence.as_of_date) == (
                "ITOT",
                "ishares",
                ITOT_SOURCE_DATE,
            )
            assert tuple(row.dimension for row in evidence.dimensions) == tuple(
                row.dimension for row in coverage_rows
            )
            assert tuple(row.complete for row in evidence.dimensions) == tuple(
                row.complete for row in coverage_rows
            )
            assert inputs.source_metadata.lookthrough_complete is False
            assert all(
                (row.provider, row.as_of_date) == (evidence.provider, evidence.as_of_date)
                for row in inputs.exposures
            )
            security_exposure = aggregate_lookthrough_exposure(
                inputs, tickers=("ITOT",), dimension="security"
            )
            assert security_exposure.values
            assert security_exposure.coverage.complete is False
            assert security_exposure.coverage.invalid_tickers == ("ITOT",)

            frozen = json.loads(json.dumps(inputs.to_provenance()))
            assert "exposure_cache" in frozen
            assert financial_inputs_from_provenance(frozen) == inputs
            legacy_bundle = dict(frozen)
            legacy_bundle.pop("exposure_cache")
            assert financial_inputs_from_provenance(legacy_bundle).exposure_cache == ()
            without_cache = replace(inputs, exposure_cache=())
            assert "exposure_cache" not in without_cache.to_provenance()
            assert (
                financial_inputs_from_provenance(without_cache.to_provenance()).exposure_cache == ()
            )
        assert len(requested_urls) == 3
        assert all(url == ITOT_URL for url in requested_urls)
    finally:
        restarted_engine.dispose()


def test_broker_sync_preserves_successful_cache_and_updates_legacy_exposures(
    tmp_path: Path,
) -> None:
    engine, factory = _database(tmp_path, "cache-sync-preservation.sqlite3")
    source = IsharesFundConfig("ITOT", ITOT_URL)
    itot_body = (FIXTURE_DIR / "ishares" / "itot_excerpt.csv").read_bytes()
    with _client(itot_body, ITOT_URL) as client:
        refresh_exposure_cache(factory, [source], ishares_client=client, clock=lambda: FETCHED_AT)

    failed_path = tmp_path / "failed-first.csv"
    failed_path.write_text("ticker,as_of_date,dimension,exposure_key,weight\n", encoding="utf-8")
    failed_first = LocalCsvExposureConfig("FIRST", failed_path)
    with pytest.raises(AppError):
        refresh_exposure_cache(factory, [failed_first], clock=lambda: FETCHED_AT)

    with factory.begin() as session:
        for ticker in ("LEGACY", "FIRST"):
            security = Security(ticker=ticker, asset_type="ETF")
            session.add(security)
            session.flush()
            session.add(
                SecurityExposure(
                    security_id=security.id,
                    dimension="security",
                    exposure_key=f"OLD-{ticker}",
                    weight=Decimal(1),
                    provider="manual_csv",
                    as_of_date=date(2026, 11, 18),
                )
            )
        cached_before = [
            (row.dimension, row.exposure_key, row.weight, row.provider, row.as_of_date)
            for row in _rows_for_ticker(session, "ITOT")
        ]
        assert cached_before

    snapshot = FakeBroker.demo_snapshot().model_copy(
        update={
            "exposures": [
                ExposureInput(
                    ticker="ITOT",
                    dimension="security",
                    exposure_key="CONFLICTING-BROKER-ROW",
                    weight=Decimal(1),
                    provider="manual_csv",
                    as_of_date=date(2026, 11, 19),
                ),
                ExposureInput(
                    ticker="LEGACY",
                    dimension="security",
                    exposure_key="NEW-LEGACY",
                    weight=Decimal(1),
                    provider="manual_csv",
                    as_of_date=date(2026, 11, 19),
                ),
                ExposureInput(
                    ticker="FIRST",
                    dimension="security",
                    exposure_key="NEW-FIRST",
                    weight=Decimal(1),
                    provider="manual_csv",
                    as_of_date=date(2026, 11, 19),
                ),
            ]
        }
    )
    sync_portfolio(factory, FakeBroker(snapshot), correlation_id="cache-protection")

    with factory() as session:
        cached_after = [
            (row.dimension, row.exposure_key, row.weight, row.provider, row.as_of_date)
            for row in _rows_for_ticker(session, "ITOT")
        ]
        assert cached_after == cached_before
        assert [row.exposure_key for row in _rows_for_ticker(session, "LEGACY")] == ["NEW-LEGACY"]
        assert [row.exposure_key for row in _rows_for_ticker(session, "FIRST")] == ["NEW-FIRST"]
        failed_state = session.get(ExposureCacheState, "FIRST")
        assert failed_state is not None
        assert failed_state.publication_revision == 0
        assert failed_state.last_attempt_status == "failure"
    engine.dispose()
