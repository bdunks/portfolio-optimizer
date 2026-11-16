from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.broker.fake import FakeBroker
from app.domain.decimal_math import exact_percent_product, whole_share_floor
from app.main import create_app
from app.schemas import BrokerSnapshot


def _policy_payload(client: TestClient) -> dict[str, Any]:
    active = client.get("/api/v1/policy").json()["active"]
    return {
        "source_revision_id": active["id"],
        "settings": active["settings"],
        "sleeves": active["sleeves"],
        "allowed_securities": active["allowed_securities"],
        "overrides": active["overrides"],
        "reassignments": {},
    }


def _activate_policy(client: TestClient, payload: dict[str, Any]) -> str:
    draft = client.post("/api/v1/policy/drafts", json=payload)
    assert draft.status_code == 201, draft.text
    activated = client.post(f"/api/v1/policy/{draft.json()['id']}/activate")
    assert activated.status_code == 200, activated.text
    return draft.json()["id"]


@contextmanager
def _open_app(
    tmp_path: Path, name: str, snapshot: BrokerSnapshot | None = None
) -> Iterator[tuple[FastAPI, TestClient]]:
    app = create_app(
        database_url=f"sqlite:///{tmp_path / name}",
        broker=FakeBroker(snapshot),
        seed_demo_data=True,
    )
    with TestClient(app, base_url="http://localhost") as client:
        yield app, client


def test_cash_sleeve_preserves_explicit_holdings_and_cash_delta(tmp_path: Path) -> None:
    with _open_app(tmp_path, "cash-sleeve.sqlite3") as (_, client):
        payload = _policy_payload(client)
        payload["overrides"] = [{"ticker": "AAPL", "sleeve_key": "cash"}]
        _activate_policy(client, payload)

        run = client.post("/api/v1/optimizer/runs", json={}).json()
        recs = client.get(f"/api/v1/optimizer/runs/{run['run_id']}/recommendations").json()
        assert [leg["ticker"] for leg in recs["consolidated_legs"] if leg["side"] == "SELL"] == [
            "VB"
        ]
        group = recs["groups"][0]

        empty = client.post(
            f"/api/v1/optimizer/runs/{run['run_id']}/selection",
            json={"selected_group_ids": [], "selected_sell_lots": {}},
        )
        assert empty.status_code == 200, empty.text
        empty_effects = empty.json()["groups"][0]["impact"]["portfolio_effects"]["allocation"]
        assert Decimal(empty_effects["current"]["total_portfolio_usd"]) == 3050
        assert Decimal(empty_effects["proposed"]["total_portfolio_usd"]) == 3050
        assert empty_effects["current"]["sleeve_weights_pct"]["cash"] == "86.89"
        assert empty_effects["proposed"]["sleeve_weights_pct"]["cash"] == "86.89"

        selected = client.post(
            f"/api/v1/optimizer/runs/{run['run_id']}/selection",
            json={"selected_group_ids": [group["group_id"]]},
        )
        assert selected.status_code == 200, selected.text
        effects = selected.json()["groups"][0]["impact"]["portfolio_effects"]
        assert (
            effects["allocation"]["current"]["sleeve_weights_pct"]
            == effects["allocation"]["proposed"]["sleeve_weights_pct"]
        )
        assert Decimal(effects["allocation"]["proposed"]["total_portfolio_usd"]) == 3050
        assert Decimal(effects["us_transition"]["current"]["us_sleeve_value_usd"]) == 400
        assert Decimal(effects["us_transition"]["proposed_basket"]["us_sleeve_value_usd"]) == 400


def test_replacement_override_controls_buy_assignment_and_effects(tmp_path: Path) -> None:
    with _open_app(tmp_path, "candidate-override.sqlite3") as (_, client):
        payload = _policy_payload(client)
        payload["overrides"] = [{"ticker": "VTI", "sleeve_key": "international"}]
        _activate_policy(client, payload)

        run = client.post("/api/v1/optimizer/runs", json={}).json()
        recs = client.get(f"/api/v1/optimizer/runs/{run['run_id']}/recommendations").json()
        assert len(recs["groups"]) == 1
        legs = {leg["leg_id"]: leg for leg in recs["consolidated_legs"]}
        sell_id, buy_id = recs["groups"][0]["leg_ids"]
        assert legs[sell_id]["ticker"] == "VB"
        assert legs[buy_id]["ticker"] == "VTI"
        assert legs[buy_id]["details"]["sleeve_key"] == "international"
        assert legs[buy_id]["details"]["sub_sleeve_key"] is None

        effects = recs["groups"][0]["impact"]["portfolio_effects"]
        current = effects["allocation"]["current"]["sleeve_weights_pct"]
        proposed = effects["allocation"]["proposed"]["sleeve_weights_pct"]
        assert proposed["us_equities"] < current["us_equities"]
        assert proposed["international"] > current["international"]
        assert Decimal(effects["us_transition"]["proposed_basket"]["us_sleeve_value_usd"]) == 1800


def test_nested_holding_cash_and_trade_rollup_and_reassignment(tmp_path: Path) -> None:
    original = FakeBroker.demo_snapshot()
    lots = [
        lot.model_copy(update={"adjusted_unit_basis_usd": Decimal(200)})
        if lot.ticker == "AAPL"
        else lot
        for lot in original.lots
    ]
    nested_snapshot = original.model_copy(update={"lots": lots})
    with _open_app(tmp_path, "nested-allocation.sqlite3", nested_snapshot) as (_, client):
        payload = _policy_payload(client)
        by_key = {row["sleeve_key"]: row for row in payload["sleeves"]}
        by_key["cash"].update(
            {"sleeve_key": "cash_bucket", "display_name": "Cash bucket", "is_cash_sleeve": False}
        )
        payload["sleeves"].extend(
            [
                {
                    "sleeve_key": "stocks",
                    "display_name": "Direct-index stocks",
                    "sort_order": 0,
                    "parent_sleeve_key": "direct_indexing",
                    "target_pct": "100",
                    "drift_band_pp": "5",
                },
                {
                    "sleeve_key": "cash",
                    "display_name": "Cash",
                    "sort_order": 0,
                    "parent_sleeve_key": "cash_bucket",
                    "target_pct": "100",
                    "drift_band_pp": "2",
                    "is_cash_sleeve": True,
                },
            ]
        )
        payload["overrides"] = [
            {"ticker": "AAPL", "sleeve_key": "direct_indexing", "sub_sleeve_key": "stocks"}
        ]
        payload["settings"]["max_batch_turnover_pct"] = "100"
        _activate_policy(client, payload)

        portfolio = client.get("/api/v1/portfolio").json()
        current_weights = portfolio["allocation"]["current"]["sleeve_weights_pct"]
        assert Decimal(portfolio["portfolio_total_usd"]) == 3050
        assert current_weights["us_equities"] == "72.13"
        assert current_weights["cash_bucket"] == "27.87"
        transition = portfolio["us_transition"]
        assert Decimal(transition["current"]["us_sleeve_value_usd"]) == 2200
        assert Decimal(transition["current"]["children"]["direct_indexing"]["value_usd"]) == 2200
        assert transition["target"]["children"]["direct_indexing"]["whole_portfolio_pct"] == "60.00"
        aapl_lot = client.get("/api/v1/lots?ticker=AAPL").json()["items"][0]
        assert (aapl_lot["sleeve_key"], aapl_lot["sub_sleeve_key"]) == ("direct_indexing", "stocks")

        run = client.post("/api/v1/optimizer/runs", json={}).json()
        recs = client.get(f"/api/v1/optimizer/runs/{run['run_id']}/recommendations").json()
        aapl_group = next(group for group in recs["groups"] if "AAPL" in group["rationale"])
        no_trade = client.post(
            f"/api/v1/optimizer/runs/{run['run_id']}/selection",
            json={"selected_group_ids": [], "selected_sell_lots": {}},
        )
        assert no_trade.status_code == 200, no_trade.text
        effects = no_trade.json()["groups"][0]["impact"]["portfolio_effects"]
        assert (
            effects["allocation"]["current"]["sleeve_weights_pct"]
            == effects["allocation"]["proposed"]["sleeve_weights_pct"]
        )
        assert effects["allocation"]["current"]["sleeve_weights_pct"]["cash_bucket"] == "27.87"
        assert effects["allocation"]["proposed"]["sleeve_weights_pct"]["cash_bucket"] == "27.87"
        assert Decimal(effects["us_transition"]["current"]["us_sleeve_value_usd"]) == 2200
        assert Decimal(effects["us_transition"]["proposed_basket"]["us_sleeve_value_usd"]) == 2200
        selected = client.post(
            f"/api/v1/optimizer/runs/{run['run_id']}/selection",
            json={"selected_group_ids": [aapl_group["group_id"]]},
        )
        assert selected.status_code == 200, selected.text
        selected_effects = next(
            group["impact"]["portfolio_effects"]
            for group in selected.json()["groups"]
            if group["group_id"] == aapl_group["group_id"]
        )
        proposed_children = selected_effects["us_transition"]["proposed_basket"]["children"]
        assert Decimal(proposed_children["direct_indexing"]["value_usd"]) == 400
        assert Decimal(proposed_children["us_etf"]["value_usd"]) == 1800
        assert (
            Decimal(selected_effects["us_transition"]["proposed_basket"]["us_sleeve_value_usd"])
            == 2200
        )
        assert Decimal(selected.json()["cash_after_usd"]) == 850

        reassignment = _policy_payload(client)
        reassignment["sleeves"] = [
            row for row in reassignment["sleeves"] if row["sleeve_key"] != "stocks"
        ]
        reassignment["overrides"] = list[dict[str, object]]()
        reassignment["reassignments"] = {"stocks": "direct_indexing"}
        _activate_policy(client, reassignment)
        moved_lot = client.get("/api/v1/lots?ticker=AAPL").json()["items"][0]
        assert (moved_lot["sleeve_key"], moved_lot["sub_sleeve_key"]) == (
            "us_equities",
            "direct_indexing",
        )


def test_high_precision_cash_reserve_still_funds_vb_swap_and_share_floor(tmp_path: Path) -> None:
    cash = Decimal("850.000000000000000000000000001")
    snapshot = FakeBroker.demo_snapshot().model_copy(
        update={"cash_usd": cash, "settled_buying_power_usd": cash}
    )
    with localcontext() as context:
        context.prec = 3
        assert whole_share_floor(
            Decimal("400.0000000000000000000000000002"),
            Decimal("200.0000000000000000000000000001"),
        ) == Decimal(2)

    with _open_app(tmp_path, "exact-cash.sqlite3", snapshot) as (_, client):
        payload = _policy_payload(client)
        payload["settings"]["cash_reserve_usd"] = str(cash)
        payload["settings"]["max_batch_turnover_pct"] = "100"
        payload["settings"]["min_buy_order_notional_usd"] = "0"
        _activate_policy(client, payload)
        run = client.post("/api/v1/optimizer/runs", json={}).json()
        recs = client.get(f"/api/v1/optimizer/runs/{run['run_id']}/recommendations").json()
        assert len(recs["groups"]) == 1
        buy = next(leg for leg in recs["consolidated_legs"] if leg["side"] == "BUY")
        assert (buy["ticker"], buy["shares"]) == ("VTI", "2")
        assert run["cash_after_usd"] == str(cash)


@pytest.mark.parametrize(
    ("turnover_pct", "expected_groups"),
    [
        ("99.9999999999999999999999999998", 0),
        ("100", 1),
    ],
)
def test_turnover_decisions_use_exact_percent_scaling(
    tmp_path: Path, turnover_pct: str, expected_groups: int
) -> None:
    original = FakeBroker.demo_snapshot()
    vb = next(position for position in original.positions if position.ticker == "VB")
    vb_lot = next(lot for lot in original.lots if lot.ticker == "VB")
    snapshot = original.model_copy(
        update={
            "positions": [vb],
            "lots": [vb_lot],
            "cash_usd": Decimal(0),
            "settled_buying_power_usd": Decimal(0),
        }
    )
    exact_limit = exact_percent_product(Decimal(400), Decimal(turnover_pct))
    if expected_groups == 0:
        assert exact_limit == Decimal("399.9999999999999999999999999992")
        assert exact_limit < Decimal(400)

    with _open_app(tmp_path, f"turnover-{expected_groups}.sqlite3", snapshot) as (_, client):
        payload = _policy_payload(client)
        payload["settings"]["max_batch_turnover_pct"] = turnover_pct
        payload["settings"]["min_buy_order_notional_usd"] = "0"
        _activate_policy(client, payload)
        run = client.post("/api/v1/optimizer/runs", json={}).json()
        recs = client.get(f"/api/v1/optimizer/runs/{run['run_id']}/recommendations").json()
        assert len(recs["groups"]) == expected_groups


def test_fractional_share_remainder_is_lossless_beyond_context_precision(tmp_path: Path) -> None:
    original = FakeBroker.demo_snapshot()
    high_precision = Decimal("10.123456789012345678901234567890123456789")
    positions = [
        row.model_copy(update={"shares": high_precision}) if row.ticker == "AAPL" else row
        for row in original.positions
    ]
    lots = [
        row.model_copy(update={"shares": high_precision, "available_shares": high_precision})
        if row.ticker == "AAPL"
        else row
        for row in original.lots
    ]
    snapshot = original.model_copy(update={"positions": positions, "lots": lots})
    with _open_app(tmp_path, "fractional-precision.sqlite3", snapshot) as (_, client):
        lot = client.get("/api/v1/lots?ticker=AAPL").json()["items"][0]
        assert lot["fractional_shares"] == "0.123456789012345678901234567890123456789"
        assert lot["fractional_cleanup_unsupported"] is True
