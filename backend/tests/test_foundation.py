from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import TypedDict

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from app.broker.fake import FakeBroker
from app.db.migrate import upgrade_database
from app.db.models import PolicyRevision, Security
from app.db.session import create_database_engine
from app.domain.allocation import SecurityIdentity, SleeveAssignment, resolve_holding
from app.domain.decimal_math import exact_difference, exact_sum
from app.main import create_app
from app.services.financial_input_loader import load_allocation_policy


class _SectorBand(TypedDict):
    sector_key: str
    target_weight_pct: str
    band_pct: str


class _DraftPayload(TypedDict, total=False):
    source_revision_id: str
    settings: dict[str, object]
    sleeves: list[dict[str, object]]
    allowed_securities: list[dict[str, object]]
    overrides: list[dict[str, object]]
    reassignments: dict[str, str]
    sector_bands: list[_SectorBand]


@pytest.fixture
def seeded_client(tmp_path: Path) -> Iterator[tuple[FastAPI, TestClient]]:
    app = create_app(database_url=f"sqlite:///{tmp_path / 'seeded.sqlite3'}", seed_demo_data=True)
    with TestClient(app, base_url="http://localhost") as client:
        yield app, client


def _draft_payload(client: TestClient) -> _DraftPayload:
    active = client.get("/api/v1/policy").json()["active"]
    assert active is not None
    return {
        "source_revision_id": active["id"],
        "settings": active["settings"],
        "sleeves": active["sleeves"],
        "allowed_securities": active["allowed_securities"],
        "overrides": active["overrides"],
        "reassignments": {},
    }


def test_fresh_upgrade_reupgrade_restart_demo_and_no_order_tables(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'restart.sqlite3'}"
    observed_generation = 0
    for _ in range(2):
        app = create_app(database_url=database_url, seed_demo_data=True)
        with TestClient(app, base_url="http://localhost") as client:
            assert client.get("/health").json()["schema_ready"] is True
            portfolio = client.get("/api/v1/portfolio").json()
            assert portfolio["status"] == "ready"
            assert portfolio["demo"] is True
            observed_generation = portfolio["sync"]["generation"]
            assert client.get("/api/v1/lots").json()["total"] == 2
            assert client.get("/api/v1/policy").json()["active"]["status"] == "ACTIVE"
            columns = {
                column["name"]
                for column in inspect(app.state.engine).get_columns("policy_revision")
            }
            sleeve_columns = {
                column["name"] for column in inspect(app.state.engine).get_columns("policy_sleeve")
            }
            assert "is_transition_destination" in sleeve_columns
            demo_sleeves = client.get("/api/v1/policy").json()["active"]["sleeves"]
            assert (
                next(row for row in demo_sleeves if row["sleeve_key"] == "us_etf")[
                    "is_transition_destination"
                ]
                is True
            )
            assert "settings" not in columns
            assert {
                "short_term_tax_rate",
                "max_sell_lots_per_batch",
                "allow_gain_sales",
                "objective_band_weight",
                "estimated_spread_bps",
            } <= columns
            tables = set(inspect(app.state.engine).get_table_names())
            assert not {"order_record", "order_fill"} & tables
    assert observed_generation == 1


def test_policy_settings_are_typed_lossless_and_nested_api_shape_persists(
    seeded_client: tuple[FastAPI, TestClient],
) -> None:
    app, client = seeded_client
    payload = _draft_payload(client)
    settings = payload["settings"]
    assert isinstance(settings, dict)
    settings.update(
        {
            "short_term_tax_rate": "0.35500000000000000000000000000001",
            "long_term_tax_rate": "0.15500000000000000000000000000001",
            "st_loss_carryforward_usd": "123.123456789012345678901234567890123",
            "ytd_realized_st_usd": "42.5",
            "ytd_source": "manual adjustment",
            "ytd_as_of": "2026-11-05",
            "target_retained_net_loss_usd": "1234567890123456789012345678.123456789",
            "max_sell_tickers_per_batch": 3,
            "max_sell_lots_per_batch": 7,
            "max_total_orders_per_batch": 5,
            "prefer_etf_buys": False,
            "allow_gain_sales": True,
            "objective_band_weight": "1.2500000000000000000000000000001",
            "objective_allocation_weight": None,
            "objective_tax_weight": "0.75",
            "objective_trading_cost_weight": "1.0",
            "objective_turnover_weight": "0.5",
            "objective_cleanup_weight": "2.0",
            "estimated_spread_bps": "5.00",
            "estimated_fee_per_order_usd": "1.00",
        }
    )
    response = client.post("/api/v1/policy/drafts", json=payload)
    assert response.status_code == 201, response.text
    revision = response.json()
    assert revision["settings"]["short_term_tax_rate"] == settings["short_term_tax_rate"]
    assert (
        revision["settings"]["target_retained_net_loss_usd"]
        == settings["target_retained_net_loss_usd"]
    )
    assert revision["settings"]["max_sell_lots_per_batch"] == 7
    assert revision["settings"]["allow_gain_sales"] is True
    assert revision["settings"]["objective_band_weight"] == settings["objective_band_weight"]
    assert revision["settings"]["objective_allocation_weight"] is None
    assert revision["settings"]["estimated_spread_bps"] == "5.00"
    with app.state.session_factory() as session:
        persisted = session.get(PolicyRevision, revision["id"])
        assert persisted is not None
        assert isinstance(settings["target_retained_net_loss_usd"], str)
        assert isinstance(settings["st_loss_carryforward_usd"], str)
        assert isinstance(settings["objective_band_weight"], str)
        assert persisted.target_retained_net_loss_usd == Decimal(
            settings["target_retained_net_loss_usd"]
        )
        assert persisted.st_loss_carryforward_usd == Decimal(settings["st_loss_carryforward_usd"])
        assert persisted.ytd_as_of == date(2026, 11, 5)
        assert persisted.max_sell_lots_per_batch == 7
        assert persisted.allow_gain_sales is True
        assert persisted.objective_band_weight == Decimal(settings["objective_band_weight"])
        assert persisted.objective_allocation_weight is None
        assert persisted.estimated_spread_bps == Decimal("5.00")
        assert persisted.estimated_fee_per_order_usd == Decimal("1.00")
        assert not hasattr(persisted, "settings")

    defaults_payload = _draft_payload(client)
    defaults_payload["settings"] = {}
    defaults_response = client.post("/api/v1/policy/drafts", json=defaults_payload)
    assert defaults_response.status_code == 201, defaults_response.text
    defaults = defaults_response.json()["settings"]
    assert defaults["target_retained_net_loss_usd"] == "3000"
    assert defaults["max_sell_tickers_per_batch"] == 10
    assert defaults["max_sell_lots_per_batch"] == 20
    assert defaults["max_total_orders_per_batch"] == 12
    assert all(
        defaults[name] is None
        for name in (
            "objective_band_weight",
            "objective_allocation_weight",
            "objective_tax_weight",
            "objective_trading_cost_weight",
            "objective_turnover_weight",
            "objective_cleanup_weight",
            "estimated_spread_bps",
            "estimated_fee_per_order_usd",
        )
    )


def test_negative_objective_parameters_are_rejected(
    seeded_client: tuple[FastAPI, TestClient],
) -> None:
    _, client = seeded_client
    payload = _draft_payload(client)
    payload["settings"]["objective_tax_weight"] = "-0.01"
    response = client.post("/api/v1/policy/drafts", json=payload)
    assert response.status_code == 422


def test_exact_top_and_nested_sums_beyond_default_decimal_precision_activate(
    seeded_client: tuple[FastAPI, TestClient],
) -> None:
    _, client = seeded_client
    payload = _draft_payload(client)
    sleeves = payload["sleeves"]
    assert isinstance(sleeves, list)
    by_key = {sleeve["sleeve_key"]: sleeve for sleeve in sleeves}
    by_key["us_equities"]["target_pct"] = "60.0000000000000000000000000000001"
    by_key["international"]["target_pct"] = "29.9999999999999999999999999999999"
    by_key["us_etf"]["target_pct"] = "0.0000000000000000000000000000001"
    by_key["direct_indexing"]["target_pct"] = "99.9999999999999999999999999999999"
    created = client.post("/api/v1/policy/drafts", json=payload)
    assert created.status_code == 201, created.text
    assert created.json()["activation_errors"] == []
    activated = client.post(f"/api/v1/policy/{created.json()['id']}/activate")
    assert activated.status_code == 200, activated.text
    assert activated.json()["status"] == "ACTIVE"


def test_invalid_draft_saves_but_cannot_activate(seeded_client: tuple[FastAPI, TestClient]) -> None:
    _, client = seeded_client
    payload = _draft_payload(client)
    cash = next(sleeve for sleeve in payload["sleeves"] if sleeve["sleeve_key"] == "cash")
    cash["target_pct"] = "9"
    saved = client.post("/api/v1/policy/drafts", json=payload)
    assert saved.status_code == 201
    assert any(
        error["code"] == "top_level_target_sum" for error in saved.json()["activation_errors"]
    )
    blocked = client.post(f"/api/v1/policy/{saved.json()['id']}/activate")
    assert blocked.status_code == 422
    assert blocked.json()["code"] == "policy_invalid"
    drafts = client.get("/api/v1/policy").json()["drafts"]
    assert any(revision["id"] == saved.json()["id"] for revision in drafts)


def test_transition_destination_policy_is_explicit_and_unconfigured_progress_is_nullable(
    seeded_client: tuple[FastAPI, TestClient],
) -> None:
    _, client = seeded_client
    active = client.get("/api/v1/policy").json()["active"]
    assert active is not None
    destination = next(sleeve for sleeve in active["sleeves"] if sleeve["sleeve_key"] == "us_etf")
    assert destination["is_transition_destination"] is True

    payload = _draft_payload(client)
    for sleeve in payload["sleeves"]:
        sleeve["is_transition_destination"] = False
    saved = client.post("/api/v1/policy/drafts", json=payload)
    assert saved.status_code == 201, saved.text
    assert all(not sleeve["is_transition_destination"] for sleeve in saved.json()["sleeves"])
    activated = client.post(f"/api/v1/policy/{saved.json()['id']}/activate")
    assert activated.status_code == 200, activated.text

    transition = client.get("/api/v1/portfolio").json()["us_transition"]
    assert transition["transition_destination_sleeve_key"] is None
    assert transition["current"]["etf_progress_pct"] is None
    assert transition["proposed_basket"]["etf_progress_pct"] is None


@pytest.mark.parametrize(
    ("destination_keys", "expected_code"),
    [
        (("us_etf", "international"), "multiple_transition_destinations"),
        (("us_equities",), "transition_destination_outside_direct_index_container"),
        (("direct_indexing",), "transition_destination_overlaps_direct_index_branch"),
        (("international",), "transition_destination_outside_direct_index_container"),
    ],
)
def test_invalid_transition_destination_designations_are_rejected(
    seeded_client: tuple[FastAPI, TestClient], destination_keys: tuple[str, ...], expected_code: str
) -> None:
    _, client = seeded_client
    payload = _draft_payload(client)
    for sleeve in payload["sleeves"]:
        sleeve["is_transition_destination"] = sleeve["sleeve_key"] in destination_keys

    saved = client.post("/api/v1/policy/drafts", json=payload)
    assert saved.status_code == 201, saved.text
    assert any(error["code"] == expected_code for error in saved.json()["activation_errors"])
    activated = client.post(f"/api/v1/policy/{saved.json()['id']}/activate")
    assert activated.status_code == 422
    assert activated.json()["code"] == "policy_invalid"


@pytest.mark.parametrize("remove_sleeve", [False, True])
def test_held_sleeve_disable_or_delete_requires_explicit_reassignment(
    seeded_client: tuple[FastAPI, TestClient], remove_sleeve: bool
) -> None:
    _, client = seeded_client
    payload = _draft_payload(client)
    sleeves = payload["sleeves"]
    direct = next(sleeve for sleeve in sleeves if sleeve["sleeve_key"] == "direct_indexing")
    if remove_sleeve:
        sleeves.remove(direct)
    else:
        direct["enabled"] = False
    next(sleeve for sleeve in sleeves if sleeve["sleeve_key"] == "us_etf")["target_pct"] = "100"
    missing = client.post("/api/v1/policy/drafts", json=payload)
    assert missing.status_code == 422
    assert missing.json()["code"] == "reassignment_required"

    payload["reassignments"] = {"direct_indexing": "us_etf"}
    saved = client.post("/api/v1/policy/drafts", json=payload)
    assert saved.status_code == 201, saved.text
    moved_tickers = {item["ticker"] for item in saved.json()["overrides"]}
    assert {"AAPL", "VB"} <= moved_tickers


def test_default_direct_index_allowed_etf_and_override_precedence(
    seeded_client: tuple[FastAPI, TestClient],
) -> None:
    app, client = seeded_client
    with app.state.session_factory.begin() as session:
        active = session.query(PolicyRevision).filter_by(status="ACTIVE").one()
        aapl = session.query(Security).filter_by(ticker="AAPL").one()
        allocation = load_allocation_policy(session, active.id)

        def resolved(security: Security) -> SleeveAssignment | None:
            resolution = resolve_holding(
                allocation,
                SecurityIdentity(security.ticker, security.asset_type, security.is_completion_etf),
            )
            return resolution.assignment

        vb = session.query(Security).filter_by(ticker="VB").one()
        vti = session.query(Security).filter_by(ticker="VTI").one()
        vxf = Security(ticker="VXF", asset_type="ETF", is_completion_etf=True)
        session.add(vxf)
        session.flush()
        assert resolved(aapl) == SleeveAssignment("us_equities", "direct_indexing")
        assert resolved(vb) == SleeveAssignment("us_equities", "direct_indexing")
        assert resolved(vxf) == SleeveAssignment("us_equities", "direct_indexing")
        assert resolved(vti) == SleeveAssignment("us_equities", "us_etf")

    payload = _draft_payload(client)
    payload["overrides"] = [{"ticker": "VTI", "sleeve_key": "international"}]
    saved = client.post("/api/v1/policy/drafts", json=payload)
    assert saved.status_code == 201, saved.text
    with app.state.session_factory() as session:
        vti = session.query(Security).filter_by(ticker="VTI").one()
        allocation = load_allocation_policy(session, saved.json()["id"])
        resolution = resolve_holding(
            allocation, SecurityIdentity(vti.ticker, vti.asset_type, vti.is_completion_etf)
        )
        assert resolution.assignment == SleeveAssignment("international")


def test_sync_publication_is_atomic_for_failure_incomplete_and_duplicate_payloads(
    tmp_path: Path,
) -> None:
    broker = FakeBroker()
    publication = {"fail": False}

    def fail_publication() -> None:
        if publication["fail"]:
            raise RuntimeError("injected publish failure")

    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'atomic.sqlite3'}",
        broker=broker,
        seed_demo_data=True,
        publication_hook=fail_publication,
    )
    with TestClient(app, base_url="http://localhost") as client:
        previous = client.get("/api/v1/portfolio").json()
        changed = broker.fetch_snapshot().model_copy(
            update={"cash_usd": Decimal("321.09"), "settled_buying_power_usd": Decimal("321.09")}
        )
        broker._snapshot = changed
        assert client.post("/api/v1/portfolio/sync").status_code == 200
        current = client.get("/api/v1/portfolio").json()
        assert current["sync"]["generation"] == previous["sync"]["generation"] + 1
        assert current["cash_usd"] == "321.09"
        expected_lots = client.get("/api/v1/lots").json()["items"]

        publication["fail"] = True
        failed = client.post("/api/v1/portfolio/sync")
        assert failed.status_code == 500
        publication["fail"] = False
        after_failure = client.get("/api/v1/portfolio").json()
        assert after_failure["sync"]["generation"] == current["sync"]["generation"]
        assert after_failure["cash_usd"] == current["cash_usd"]
        assert client.get("/api/v1/lots").json()["items"] == expected_lots

        incomplete = changed.model_copy(
            update={"coverage": changed.coverage.model_copy(update={"lots": False})}
        )
        broker._snapshot = incomplete
        assert client.post("/api/v1/portfolio/sync").status_code == 422
        assert (
            client.get("/api/v1/portfolio").json()["sync"]["generation"]
            == current["sync"]["generation"]
        )
        assert client.get("/api/v1/portfolio").json()["cash_usd"] == current["cash_usd"]
        assert client.get("/api/v1/lots").json()["items"] == expected_lots

        duplicate_position = changed.positions[0]
        duplicate = changed.model_copy(
            update={"positions": [*changed.positions, duplicate_position]}
        )
        broker._snapshot = duplicate
        assert client.post("/api/v1/portfolio/sync").status_code == 422
        after_duplicate = client.get("/api/v1/portfolio").json()
        assert after_duplicate["sync"]["generation"] == current["sync"]["generation"]
        assert after_duplicate["cash_usd"] == current["cash_usd"]
        assert client.get("/api/v1/lots").json()["items"] == expected_lots


def test_fractional_quantities_are_lossless_flagged_and_remote_origins_rejected(
    tmp_path: Path,
) -> None:
    broker = FakeBroker()
    snapshot = broker.fetch_snapshot()
    lots = list(snapshot.lots)
    lots[0] = lots[0].model_copy(
        update={
            "available_shares": Decimal("9.123456789012345678901"),
            "quality_flags": ["fractional legacy lot"],
        }
    )
    broker._snapshot = snapshot.model_copy(update={"lots": lots})
    app = create_app(database_url=f"sqlite:///{tmp_path / 'fractional.sqlite3'}", broker=broker)
    with TestClient(app, base_url="http://localhost") as client:
        assert client.post("/api/v1/portfolio/sync").status_code == 200
        lot = client.get("/api/v1/lots?ticker=AAPL").json()["items"][0]
        assert lot["available_shares"] == "9.123456789012345678901"
        assert lot["fractional_shares"] == "0.123456789012345678901"
        assert lot["fractional_cleanup_unsupported"] is True
        assert lot["quality_flags"] == ["fractional legacy lot"]
        fetch_count = broker.fetch_count
        rejected = client.post(
            "/api/v1/portfolio/sync", headers={"origin": "https://remote.example"}
        )
        assert rejected.status_code == 403
        assert rejected.json()["code"] == "local_origin_required"
        assert broker.fetch_count == fetch_count


def test_legacy_json_policy_migration_preserves_settings(tmp_path: Path) -> None:
    database_path = tmp_path / "legacy.sqlite3"
    engine = create_database_engine(f"sqlite:///{database_path}")
    legacy_settings = (
        '{"short_term_tax_rate":"0.35","target_retained_net_loss_usd":"'
        '1234567890123456789012345678.123456789","max_sell_lots_per_batch":7,'
        '"allow_gain_sales":true,"ytd_as_of":"2026-11-05"}'
    )
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(
            text("INSERT INTO alembic_version VALUES ('0001_normalized_foundation')")
        )
        connection.execute(
            text(
                "CREATE TABLE policy_revision (id VARCHAR(36) PRIMARY KEY, revision_number INTEGER NOT NULL, "
                "status VARCHAR(16) NOT NULL, created_at DATETIME NOT NULL, activated_at DATETIME, settings JSON NOT NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO policy_revision VALUES ('legacy', 1, 'DRAFT', :created, NULL, :settings)"
            ),
            {"created": datetime(2026, 11, 5, tzinfo=UTC), "settings": legacy_settings},
        )
    upgrade_database(engine)
    with engine.connect() as connection:
        columns = {column["name"] for column in inspect(connection).get_columns("policy_revision")}
        assert "settings" not in columns
        row = connection.execute(
            text(
                "SELECT short_term_tax_rate, target_retained_net_loss_usd, max_sell_lots_per_batch, "
                "allow_gain_sales, ytd_as_of FROM policy_revision WHERE id = 'legacy'"
            )
        ).one()
        assert row == (
            "0.35",
            "1234567890123456789012345678.123456789",
            7,
            1,
            "2026-11-05",
        )
    engine.dispose()


def test_exact_difference_does_not_round_unary_negation() -> None:
    left = Decimal(1)
    right = Decimal("0.123456789012345678901234567890123456789")
    assert exact_difference(left, right) == Decimal("0.876543210987654321098765432109876543211")


@pytest.mark.parametrize("special_value", ["NaN", "sNaN", "Infinity", "-Infinity"])
def test_exact_sum_rejects_nonfinite_decimal_values(special_value: str) -> None:
    with pytest.raises(TypeError, match="Decimal exponent must be an integer"):
        exact_sum([Decimal(special_value)])


def test_exact_sum_preserves_empty_and_finite_sum_behavior() -> None:
    assert exact_sum(list[Decimal]()) == Decimal(0)
    assert exact_sum([Decimal("1.25"), Decimal("2.75")]) == Decimal(4)
