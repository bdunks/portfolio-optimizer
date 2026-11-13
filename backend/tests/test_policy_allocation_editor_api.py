from __future__ import annotations

from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_foundation import _draft_payload

from app.domain.decimal_math import exact_sum

pytest_plugins = ("test_foundation",)


def test_allocation_editor_draft_round_trip_preserves_configuration_and_roles(
    seeded_client: tuple[FastAPI, TestClient],
) -> None:
    _, client = seeded_client
    policy = client.get("/api/v1/policy").json()
    active = policy["active"]
    assert active is not None
    assert active["status"] == "ACTIVE"
    active_id = active["id"]
    active_cash = next(row for row in active["sleeves"] if row["sleeve_key"] == "cash")
    before_portfolio = client.get("/api/v1/portfolio").json()
    before_transition = before_portfolio["us_transition"]
    before_lots = client.get("/api/v1/lots").json()["items"]
    before_assignments = {
        row["ticker"]: (row["sleeve_key"], row["sub_sleeve_key"]) for row in before_lots
    }
    assert before_assignments["AAPL"] == ("us_equities", "direct_indexing")
    assert before_assignments["VB"] == ("us_equities", "direct_indexing")

    payload = _draft_payload(client)
    sleeves = {row["sleeve_key"]: row for row in payload["sleeves"]}
    legacy_target = "33.3333333333333333333333333333333"
    new_target = "66.6666666666666666666666666666667"
    us = sleeves["us_equities"]
    legacy = sleeves["direct_indexing"]
    new = sleeves["us_etf"]
    us.update(
        {
            "display_name": "US",
            "is_direct_index_container": True,
            "is_direct_index_sleeve": False,
            "is_transition_destination": False,
        }
    )
    legacy.update(
        {
            "display_name": "Legacy",
            "sort_order": 1,
            "target_pct": legacy_target,
            "is_direct_index_container": False,
            "is_direct_index_sleeve": True,
            "is_transition_destination": False,
        }
    )
    new.update(
        {
            "display_name": "New",
            "sort_order": 2,
            "target_pct": new_target,
            "is_direct_index_container": False,
            "is_direct_index_sleeve": False,
            "is_transition_destination": True,
        }
    )
    payload["sleeves"] = list(reversed(payload["sleeves"]))
    assert exact_sum((Decimal(legacy_target), Decimal(new_target))) == Decimal(100)

    candidates = {row["ticker"]: row for row in payload["allowed_securities"]}
    candidates["VTI"].update(
        {"replacement_set_id": "us-replacements-v2", "priority": 4, "enabled": True}
    )
    candidates["ITOT"].update(
        {"replacement_set_id": "us-replacements-v2", "priority": 8, "enabled": False}
    )
    payload["allowed_securities"].append(
        {
            "ticker": "SCHB",
            "sleeve_key": "international",
            "sub_sleeve_key": None,
            "replacement_set_id": "custom-international-shortlist",
            "priority": 6,
            "enabled": False,
        }
    )
    payload["overrides"] = [
        {"ticker": "AAPL", "sleeve_key": "us_equities", "sub_sleeve_key": "direct_indexing"}
    ]

    created = client.post("/api/v1/policy/drafts", json=payload)
    assert created.status_code == 201, created.text
    draft = created.json()
    assert draft["status"] == "DRAFT"
    assert draft["activation_errors"] == []
    after_draft = client.get("/api/v1/policy").json()
    assert after_draft["active"]["id"] == active_id
    assert after_draft["active"]["status"] == "ACTIVE"
    assert (
        next(row for row in after_draft["active"]["sleeves"] if row["sleeve_key"] == "cash")
        == active_cash
    )
    assert client.get("/api/v1/portfolio").json()["us_transition"] == before_transition

    saved = next(row for row in after_draft["drafts"] if row["id"] == draft["id"])
    saved_sleeves = {row["sleeve_key"]: row for row in saved["sleeves"]}
    role_flags = {
        key: (
            saved_sleeves[key]["is_direct_index_container"],
            saved_sleeves[key]["is_direct_index_sleeve"],
            saved_sleeves[key]["is_transition_destination"],
        )
        for key in ("us_equities", "direct_indexing", "us_etf")
    }
    assert role_flags == {
        "us_equities": (True, False, False),
        "direct_indexing": (False, True, False),
        "us_etf": (False, False, True),
    }
    assert saved_sleeves["direct_indexing"]["target_pct"] == legacy_target
    assert saved_sleeves["us_etf"]["target_pct"] == new_target
    assert saved_sleeves["cash"] == active_cash
    assert [
        row["sleeve_key"] for row in saved["sleeves"] if row["parent_sleeve_key"] == "us_equities"
    ] == [
        "direct_indexing",
        "us_etf",
    ]
    assert {
        (row["ticker"], row["replacement_set_id"]): (
            row["sleeve_key"],
            row["sub_sleeve_key"],
            row["priority"],
            row["enabled"],
        )
        for row in saved["allowed_securities"]
    } == {
        ("VTI", "us-replacements-v2"): ("us_equities", "us_etf", 4, True),
        ("ITOT", "us-replacements-v2"): ("us_equities", "us_etf", 8, False),
        ("SCHB", "custom-international-shortlist"): ("international", None, 6, False),
    }
    assert saved["overrides"] == [
        {"ticker": "AAPL", "sleeve_key": "us_equities", "sub_sleeve_key": "direct_indexing"}
    ]

    activated = client.post(f"/api/v1/policy/{draft['id']}/activate")
    assert activated.status_code == 200, activated.text
    assert activated.json()["status"] == "ACTIVE"
    portfolio = client.get("/api/v1/portfolio").json()
    transition = portfolio["us_transition"]
    assert transition["transition_destination_sleeve_key"] == "us_etf"
    assert set(transition["current"]["children"]) == {"direct_indexing", "us_etf"}
    assert portfolio["cash_usd"] == before_portfolio["cash_usd"]
    assert transition["current"] == transition["proposed_basket"]
    assert (
        Decimal(transition["current"]["etf_progress_pct"]),
        Decimal(transition["proposed_basket"]["etf_progress_pct"]),
    ) == (Decimal("0.00"), Decimal("0.00"))
    assert Decimal(transition["target"]["children"]["us_etf"]["within_us_sleeve_pct"]) == Decimal(
        new_target
    )
    after_lots = client.get("/api/v1/lots").json()["items"]
    after_assignments = {
        row["ticker"]: (row["sleeve_key"], row["sub_sleeve_key"]) for row in after_lots
    }
    assert before_assignments == after_assignments
