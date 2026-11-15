from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select

from app.db.models import PolicySectorBand
from tests.test_foundation import _draft_payload

pytest_plugins = ("test_foundation",)


def test_sector_targets_must_sum_exactly_100_before_activation(
    seeded_client: tuple[FastAPI, TestClient],
) -> None:
    _, client = seeded_client
    payload = _draft_payload(client)
    payload["sector_bands"] = [
        {
            "sector_key": "Technology",
            "target_weight_pct": "33.3333333333333333333333333333",
            "band_pct": "0",
        },
        {
            "sector_key": "Health Care",
            "target_weight_pct": "66.6666666666666666666666666666",
            "band_pct": "0",
        },
    ]
    response = client.post("/api/v1/policy/drafts", json=payload)
    assert response.status_code == 201, response.text
    assert any(
        error["code"] == "sector_target_sum" for error in response.json()["activation_errors"]
    )
    activated = client.post(f"/api/v1/policy/{response.json()['id']}/activate")
    assert activated.status_code == 422


@pytest.mark.parametrize("value", ["-0.01", "100.01", "NaN", "Infinity", "-Infinity"])
def test_sector_band_values_reject_nonfinite_or_out_of_range_values(
    seeded_client: tuple[FastAPI, TestClient], value: str
) -> None:
    _, client = seeded_client
    payload = _draft_payload(client)
    payload["sector_bands"] = [
        {"sector_key": "Technology", "target_weight_pct": value, "band_pct": "0"},
        {"sector_key": "Rest", "target_weight_pct": "100", "band_pct": "0"},
    ]
    assert client.post("/api/v1/policy/drafts", json=payload).status_code == 422


@pytest.mark.parametrize("sector_key", ["", "   ", "\t\n"])
def test_sector_keys_must_not_be_blank(
    seeded_client: tuple[FastAPI, TestClient], sector_key: str
) -> None:
    _, client = seeded_client
    payload = _draft_payload(client)
    payload["sector_bands"] = [
        {"sector_key": sector_key, "target_weight_pct": "100", "band_pct": "0"},
    ]
    assert client.post("/api/v1/policy/drafts", json=payload).status_code == 422


def test_sector_band_keys_must_be_unique_and_zero_bands_are_valid(
    seeded_client: tuple[FastAPI, TestClient],
) -> None:
    _, client = seeded_client
    duplicate = _draft_payload(client)
    duplicate["sector_bands"] = [
        {"sector_key": "Technology", "target_weight_pct": "60", "band_pct": "0"},
        {"sector_key": "Technology", "target_weight_pct": "40", "band_pct": "0"},
    ]
    assert client.post("/api/v1/policy/drafts", json=duplicate).status_code == 422

    valid = _draft_payload(client)
    valid["sector_bands"] = [
        {"sector_key": "Technology", "target_weight_pct": "60", "band_pct": "0"},
        {"sector_key": "Rest", "target_weight_pct": "40", "band_pct": "0"},
    ]
    created = client.post("/api/v1/policy/drafts", json=valid)
    assert created.status_code == 201, created.text
    assert created.json()["activation_errors"] == []


def test_legacy_draft_without_sector_bands_remains_unconfigured(
    seeded_client: tuple[FastAPI, TestClient],
) -> None:
    _, client = seeded_client
    payload = _draft_payload(client)
    payload.pop("sector_bands", None)
    created = client.post("/api/v1/policy/drafts", json=payload)
    assert created.status_code == 201, created.text
    assert created.json()["sector_bands"] == []


def test_sector_migration_installs_revision_unique_and_nonnegative_constraints(
    seeded_client: tuple[FastAPI, TestClient],
) -> None:
    app, _ = seeded_client
    inspector = inspect(app.state.engine)
    assert inspector.has_table("policy_sector_band")
    unique_names = {item["name"] for item in inspector.get_unique_constraints("policy_sector_band")}
    check_names = {item["name"] for item in inspector.get_check_constraints("policy_sector_band")}
    assert "uq_policy_sector_band_key" in unique_names
    assert {
        "ck_sector_band_target_nonnegative",
        "ck_sector_band_band_nonnegative",
    } <= check_names


def test_sector_rows_are_revision_owned_and_activation_preserves_prior_policy(
    seeded_client: tuple[FastAPI, TestClient],
) -> None:
    app, client = seeded_client
    active = client.get("/api/v1/policy").json()["active"]
    assert active is not None
    original_id = active["id"]
    with app.state.session_factory() as session:
        original_rows = session.scalars(
            select(PolicySectorBand)
            .where(PolicySectorBand.policy_revision_id == original_id)
            .order_by(PolicySectorBand.sector_key)
        ).all()
        original_values = [
            (row.sector_key, row.target_weight_pct, row.band_pct) for row in original_rows
        ]
    assert original_values

    payload = _draft_payload(client)
    payload["sector_bands"] = [
        {"sector_key": "Technology", "target_weight_pct": "75", "band_pct": "3"},
        {"sector_key": "Health Care", "target_weight_pct": "25", "band_pct": "7"},
    ]
    draft = client.post("/api/v1/policy/drafts", json=payload)
    assert draft.status_code == 201, draft.text
    assert draft.json()["sector_bands"] == sorted(
        payload["sector_bands"], key=lambda row: row["sector_key"]
    )
    with app.state.session_factory() as session:
        unchanged_rows = session.scalars(
            select(PolicySectorBand)
            .where(PolicySectorBand.policy_revision_id == original_id)
            .order_by(PolicySectorBand.sector_key)
        ).all()
        assert [
            (row.sector_key, row.target_weight_pct, row.band_pct) for row in unchanged_rows
        ] == original_values

    activated = client.post(f"/api/v1/policy/{draft.json()['id']}/activate")
    assert activated.status_code == 200, activated.text
    with app.state.session_factory() as session:
        unchanged_rows = session.scalars(
            select(PolicySectorBand)
            .where(PolicySectorBand.policy_revision_id == original_id)
            .order_by(PolicySectorBand.sector_key)
        ).all()
        assert [
            (row.sector_key, row.target_weight_pct, row.band_pct) for row in unchanged_rows
        ] == original_values
        new_rows = session.scalars(
            select(PolicySectorBand)
            .where(PolicySectorBand.policy_revision_id == draft.json()["id"])
            .order_by(PolicySectorBand.sector_key)
        ).all()
        assert [(row.sector_key, row.target_weight_pct, row.band_pct) for row in new_rows] == [
            ("Health Care", Decimal(25), Decimal(7)),
            ("Technology", Decimal(75), Decimal(3)),
        ]
