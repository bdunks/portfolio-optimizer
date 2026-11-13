from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterator
from copy import deepcopy
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from query_test_support import count_selects
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from app.broker.fake import FakeBroker
from app.db.models import (
    CurrentPosition,
    CurrentQuote,
    CurrentTaxLot,
    OptimizerRun,
    PolicyRevision,
    RecommendationGroup,
    RecommendationGroupLeg,
    RecommendationLeg,
    Security,
)
from app.db.session import create_database_engine
from app.main import create_app
from app.schemas import BrokerSnapshot
from app.services import demo_optimizer
from app.services.demo_optimizer import _fingerprint


@pytest.fixture
def split_lot_snapshot() -> BrokerSnapshot:
    """Two one-share VB lots exercise consolidated SELL and replacement BUY resizing."""
    snapshot = FakeBroker.demo_snapshot()
    lots = []
    for lot in snapshot.lots:
        if lot.ticker == "VB":
            lots.extend(
                [
                    lot.model_copy(
                        update={"broker_lot_id": "DEMO-VB-LOT-1", "shares": Decimal(1), "available_shares": Decimal(1), "acquired_date": date(2025, 11, 5)}
                    ),
                    lot.model_copy(
                        update={"broker_lot_id": "DEMO-VB-LOT-2", "shares": Decimal(1), "available_shares": Decimal(1), "acquired_date": date(2025, 11, 5)}
                    ),
                ]
            )
        else:
            lots.append(lot)
    quotes = [quote.model_copy(update={"as_of": quote.as_of.replace(day=6)}) for quote in snapshot.quotes]
    return snapshot.model_copy(update={"lots": lots, "quotes": quotes})


@pytest.fixture
def demo_app(tmp_path: Path, split_lot_snapshot: BrokerSnapshot) -> Iterator[tuple[FastAPI, TestClient, FakeBroker, Path]]:
    database_path = tmp_path / "demo-api.sqlite3"
    broker = FakeBroker(split_lot_snapshot)
    app = create_app(database_url=f"sqlite:///{database_path}", broker=broker, seed_demo_data=True)
    with TestClient(app, base_url="http://localhost") as client:
        yield app, client, broker, database_path

def test_portfolio_preserves_unresolved_holding_display(demo_app: tuple[FastAPI, TestClient, FakeBroker, Path]) -> None:
    app, client, _, _ = demo_app
    with app.state.session_factory() as session, session.begin():
        position = session.query(CurrentPosition).first()
        assert position is not None
        security = session.get(Security, position.security_id)
        assert security is not None
        security.ticker = "UNASSIGNED-ROUTE"
        security.asset_type = "ETF"
        security.is_completion_etf = False

    response = client.get("/api/v1/portfolio")
    assert response.status_code == 200, response.text
    portfolio = response.json()
    unresolved = next(row for row in portfolio["positions"] if row["ticker"] == "UNASSIGNED-ROUTE")
    assert unresolved["sleeve_key"] is None
    assert portfolio["unassigned_tickers"] == ["UNASSIGNED-ROUTE"]
    assert Decimal(portfolio["portfolio_total_usd"]) == sum(
        (Decimal(row["market_value_usd"]) for row in portfolio["positions"]),
        Decimal(portfolio["cash_usd"]),
    )


def test_portfolio_without_active_policy_returns_unassigned_current_state(
    demo_app: tuple[FastAPI, TestClient, FakeBroker, Path],
) -> None:
    app, client, _, _ = demo_app
    with app.state.session_factory() as session, session.begin():
        updated = session.query(PolicyRevision).filter_by(status="ACTIVE").update({"status": "SUPERSEDED"})
        assert updated == 1

    response = client.get("/api/v1/portfolio")
    assert response.status_code == 200, response.text
    portfolio = response.json()
    assert portfolio["active_policy_revision_id"] is None
    assert portfolio["unassigned_tickers"] == sorted(row["ticker"] for row in portfolio["positions"])
    assert portfolio["allocation"]["current"] is None
    assert portfolio["us_transition"] is None




def _downgrade_to_0006(database_path: Path) -> None:
    backend_root = Path(__file__).resolve().parents[1]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "migrations"))
    engine = create_database_engine(f"sqlite:///{database_path}")
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0006_repair_orders_count")
    engine.dispose()


def _sqlite_table_snapshot(connection: Connection, table: str) -> list[dict[str, object]]:
    rows = connection.execute(text(f"SELECT * FROM {table}")).mappings().all()
    return sorted(
        (
            {
                key: value
                for key, value in row.items()
                if not (table == "optimizer_run" and key == "proposed_trade_date")
            }
            for row in rows
        ),
        key=repr,
    )
def _shared_replacement_snapshot(aapl_lot_quantities: tuple[int, ...] = (1, 1)) -> BrokerSnapshot:
    snapshot = FakeBroker.demo_snapshot()
    aapl_position = snapshot.positions[0].model_copy(
        update={"shares": Decimal(sum(aapl_lot_quantities)), "market_value_usd": Decimal(175 * sum(aapl_lot_quantities))}
    )
    msft_position = aapl_position.model_copy(
        update={"ticker": "MSFT", "shares": Decimal(2), "market_value_usd": Decimal(350)}
    )
    aapl_template = snapshot.lots[0]
    aapl_lots = [
        aapl_template.model_copy(
            update={
                "broker_lot_id": f"DEMO-AAPL-SHARED-{index}",
                "shares": Decimal(shares),
                "available_shares": Decimal(shares),
                "adjusted_unit_basis_usd": Decimal(200),
            }
        )
        for index, shares in enumerate(aapl_lot_quantities, start=1)
    ]
    msft_lot = aapl_template.model_copy(
        update={
            "ticker": "MSFT",
            "broker_lot_id": "DEMO-MSFT-SHARED-1",
            "shares": Decimal(2),
            "available_shares": Decimal(2),
            "adjusted_unit_basis_usd": Decimal(200),
        }
    )
    aapl_quote = next(quote for quote in snapshot.quotes if quote.ticker == "AAPL").model_copy(
        update={"last_usd": Decimal(175), "bid_usd": Decimal(174), "ask_usd": Decimal(176)}
    )
    msft_quote = aapl_quote.model_copy(update={"ticker": "MSFT"})
    other_quotes = [quote for quote in snapshot.quotes if quote.ticker != "AAPL"]
    return snapshot.model_copy(
        update={
            "positions": [aapl_position, msft_position],
            "lots": [*aapl_lots, msft_lot],
            "quotes": [*other_quotes, aapl_quote, msft_quote],
        }
    )


def _configure_batch_policy(client: TestClient, *, minimum_buy: str) -> None:
    active = client.get("/api/v1/policy").json()["active"]
    payload = {
        "source_revision_id": active["id"],
        "settings": active["settings"],
        "sleeves": active["sleeves"],
        "allowed_securities": active["allowed_securities"],
        "overrides": active["overrides"],
        "reassignments": {},
    }
    payload["settings"].update(
        {
            "min_buy_order_notional_usd": minimum_buy,
            "max_batch_turnover_pct": "100",
            "max_total_orders_per_batch": 3,
        }
    )
    draft = client.post("/api/v1/policy/drafts", json=payload)
    assert draft.status_code == 201, draft.text
    activated = client.post(f"/api/v1/policy/{draft.json()['id']}/activate")
    assert activated.status_code == 200, activated.text


@pytest.fixture
def shared_replacement_app(tmp_path: Path) -> Iterator[tuple[FastAPI, TestClient, Path]]:
    database_path = tmp_path / "shared-replacement.sqlite3"
    app = create_app(
        database_url=f"sqlite:///{database_path}",
        broker=FakeBroker(_shared_replacement_snapshot()),
        seed_demo_data=True,
    )
    with TestClient(app, base_url="http://localhost") as client:
        _configure_batch_policy(client, minimum_buy="500")
        yield app, client, database_path



def _create_run(client: TestClient, proposed_trade_date: str | None = None) -> dict[str, Any]:
    response = client.post(
        "/api/v1/optimizer/runs",
        json={"proposed_trade_date": proposed_trade_date} if proposed_trade_date else {},
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["proposed_trade_date"] == (proposed_trade_date or "2026-11-05")
    assert payload["status"] == "demo"
    assert payload["solver_version"] == "DEMO"
    assert payload["demo"] is True
    assert payload["actionable"] is False
    assert "real_optimizer_unavailable" in payload["warnings"]
    return payload

def _assert_historical_progress_unavailable(effects: dict[str, object]) -> None:
    transition = effects["us_transition"]
    assert transition["transition_destination_sleeve_key"] is None
    assert transition["current"]["etf_progress_pct"] is None
    assert transition["proposed_basket"]["etf_progress_pct"] is None






def test_populated_v1_run_migrates_reopens_and_reselects_without_rewriting_bundle(
    tmp_path: Path, split_lot_snapshot: BrokerSnapshot
) -> None:
    database_path = tmp_path / "legacy-v1-restart.sqlite3"
    database_url = f"sqlite:///{database_path}"
    app = create_app(
        database_url=database_url,
        broker=FakeBroker(split_lot_snapshot),
        seed_demo_data=True,
    )
    with TestClient(app, base_url="http://localhost") as client:
        run = _create_run(client)
        assert run["groups"]
        run_id = run["run_id"]
        with app.state.session_factory() as session:
            persisted = session.get(OptimizerRun, run_id)
            assert persisted is not None
            legacy_bundle = json.loads(json.dumps(persisted.frozen_input_bundle))
            historical_metrics = deepcopy(persisted.metrics)
            group = session.query(RecommendationGroup).filter_by(run_id=run_id).first()
            assert group is not None
            historical_group_impact = deepcopy(group.impact)

        for effects in (
            historical_metrics["portfolio_effects"],
            historical_group_impact["portfolio_effects"],
        ):
            transition = effects["us_transition"]
            assert transition["current"]["etf_progress_pct"] is not None
            assert transition["proposed_basket"]["etf_progress_pct"] is not None
            transition.pop("transition_destination_sleeve_key")
        expected_metrics = deepcopy(historical_metrics)
        expected_group_impact = deepcopy(historical_group_impact)

        legacy_bundle["schema"] = "demo-run-input-v1"
        legacy_bundle.pop("proposed_trade_date")
        legacy_bundle.pop("securities")
        legacy_bundle.pop("input_fingerprint")
        assert legacy_bundle["lots"]
        for lot in legacy_bundle["lots"]:
            lot.pop("sync_generation")
        fingerprint = _fingerprint(legacy_bundle)
        legacy_bundle["input_fingerprint"] = fingerprint
        expected_bundle = json.loads(json.dumps(legacy_bundle))
        with app.state.session_factory.begin() as session:
            persisted = session.get(OptimizerRun, run_id)
            assert persisted is not None
            persisted.metrics = historical_metrics
            group = session.query(RecommendationGroup).filter_by(run_id=run_id).first()
            assert group is not None
            group.impact = historical_group_impact
            persisted.frozen_input_bundle = legacy_bundle
            persisted.input_fingerprint = fingerprint
        before_summary = client.get(f"/api/v1/optimizer/runs/{run_id}").json()
        before_recommendations = client.get(
            f"/api/v1/optimizer/runs/{run_id}/recommendations"
        ).json()
        _assert_historical_progress_unavailable(before_summary["portfolio_effects"])
        _assert_historical_progress_unavailable(before_recommendations["portfolio_effects"])
        _assert_historical_progress_unavailable(
            before_recommendations["groups"][0]["impact"]["portfolio_effects"]
        )
        preserved_tables = (
            "optimizer_run",
            "recommendation_group",
            "recommendation_leg",
            "recommendation_group_leg",
            "recommendation_selected_lot",
        )
        with app.state.engine.connect() as connection:
            expected_tables = {
                table: _sqlite_table_snapshot(connection, table) for table in preserved_tables
            }

    app.state.engine.dispose()
    _downgrade_to_0006(database_path)
    downgraded_engine = create_database_engine(database_url)
    with downgraded_engine.connect() as connection:
        assert "proposed_trade_date" not in {
            column["name"] for column in inspect(connection).get_columns("optimizer_run")
        }
        assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == (
            "0006_repair_orders_count"
        )
        downgraded_tables = {
            table: _sqlite_table_snapshot(connection, table) for table in preserved_tables
        }
    assert downgraded_tables == expected_tables
    downgraded_engine.dispose()
    restarted = create_app(database_url=database_url, broker=FakeBroker(), seed_demo_data=False)
    with TestClient(restarted, base_url="http://localhost") as client:
        summary = client.get(f"/api/v1/optimizer/runs/{run_id}")
        assert summary.status_code == 200, summary.text
        assert summary.json() == before_summary
        assert summary.json()["proposed_trade_date"] == "2026-11-05"
        with restarted.state.session_factory() as session:
            persisted = session.get(OptimizerRun, run_id)
            assert persisted is not None
            assert persisted.proposed_trade_date == date(2026, 11, 5)
            assert persisted.frozen_input_bundle == expected_bundle
            assert all("sync_generation" not in lot for lot in persisted.frozen_input_bundle["lots"])

        recommendations = client.get(f"/api/v1/optimizer/runs/{run_id}/recommendations")
        assert recommendations.status_code == 200, recommendations.text
        assert recommendations.json() == before_recommendations
        _assert_historical_progress_unavailable(recommendations.json()["portfolio_effects"])
        _assert_historical_progress_unavailable(
            recommendations.json()["groups"][0]["impact"]["portfolio_effects"]
        )
        exported = client.get(f"/api/v1/optimizer/runs/{run_id}/export?format=json")
        assert exported.status_code == 200, exported.text
        exported_run = exported.json()["run"]
        _assert_historical_progress_unavailable(exported_run["portfolio_effects"])
        _assert_historical_progress_unavailable(
            exported_run["groups"][0]["impact"]["portfolio_effects"]
        )
        with restarted.state.session_factory() as session:
            persisted = session.get(OptimizerRun, run_id)
            assert persisted is not None
            assert persisted.metrics == expected_metrics
            assert persisted.frozen_input_bundle == expected_bundle
            persisted_group = session.query(RecommendationGroup).filter_by(run_id=run_id).first()
            assert persisted_group is not None
            assert persisted_group.impact == expected_group_impact
        with restarted.state.engine.connect() as connection:
            upgraded_tables = {
                table: _sqlite_table_snapshot(connection, table) for table in preserved_tables
            }
        assert upgraded_tables == expected_tables
        group = recommendations.json()["groups"][0]
        sell = next(
            leg
            for leg in recommendations.json()["consolidated_legs"]
            if leg["side"] == "SELL" and leg["group_ids"] == [group["group_id"]]
        )
        lot_ids = [lot["broker_lot_id"] for lot in sell["selected_lots"]]
        selection = client.post(
            f"/api/v1/optimizer/runs/{run_id}/selection",
            json={
                "selected_group_ids": [group["group_id"]],
                "selected_sell_lots": {group["group_id"]: lot_ids},
            },
        )
        assert selection.status_code == 200, selection.text
        assert selection.json()["proposed_trade_date"] == "2026-11-05"
        selected_sell = next(
            leg for leg in selection.json()["consolidated_legs"] if leg["side"] == "SELL"
        )
        assert {lot["st_lt"] for lot in selected_sell["selected_lots"]} == {"ST"}
        with restarted.state.session_factory() as session:
            persisted = session.get(OptimizerRun, run_id)
            assert persisted is not None
            assert persisted.frozen_input_bundle == expected_bundle
    restarted.state.engine.dispose()
def test_explicit_proposed_trade_date_is_persisted_and_reopened(demo_app: tuple[FastAPI, TestClient, FakeBroker, Path]) -> None:
    app, client, _, database_path = demo_app
    run = _create_run(client, "2026-11-06")
    assert run["estimated_realized_st_usd"] == "0"
    assert Decimal(run["estimated_realized_lt_usd"]) == Decimal(-40)
    run_id = run["run_id"]
    recommendations = client.get(f"/api/v1/optimizer/runs/{run_id}/recommendations").json()
    sell = next(leg for leg in recommendations["consolidated_legs"] if leg["side"] == "SELL")
    assert {lot["st_lt"] for lot in sell["selected_lots"]} == {"LT"}
    with app.state.session_factory() as session:
        persisted = session.get(OptimizerRun, run_id)
        assert persisted is not None
        assert persisted.proposed_trade_date == date(2026, 11, 6)
        assert persisted.frozen_input_bundle["proposed_trade_date"] == "2026-11-06"

    app.state.engine.dispose()
    restarted = create_app(
        database_url=f"sqlite:///{database_path}",
        broker=FakeBroker(),
        seed_demo_data=False,
    )
    with TestClient(restarted, base_url="http://localhost") as restarted_client:
        reopened = restarted_client.get(f"/api/v1/optimizer/runs/{run_id}/recommendations")
        assert reopened.status_code == 200, reopened.text
        assert reopened.json()["proposed_trade_date"] == "2026-11-06"
        reopened_sell = next(
            leg for leg in reopened.json()["consolidated_legs"] if leg["side"] == "SELL"
        )
        assert {lot["st_lt"] for lot in reopened_sell["selected_lots"]} == {"LT"}
    restarted.state.engine.dispose()


def test_demo_run_persistence_selection_arithmetic_and_restart(
    demo_app: tuple[FastAPI, TestClient, FakeBroker, Path], split_lot_snapshot: BrokerSnapshot
) -> None:
    app, client, broker, database_path = demo_app
    run = _create_run(client)
    run_id = run["run_id"]
    assert run["source_generation"] == 1
    assert run["source_checksum"]
    assert run["input_fingerprint"]
    assert run["estimated_tax_benefit_usd"] is None
    assert run["estimated_tax_benefit_status"] == "tax_profile_incomplete"
    recommendations = client.get(f"/api/v1/optimizer/runs/{run_id}/recommendations").json()
    groups = recommendations["groups"]
    legs_by_id = {leg["leg_id"]: leg for leg in recommendations["consolidated_legs"]}
    assert len(groups) == 1
    group = groups[0]
    sell, buy = (legs_by_id[leg_id] for leg_id in group["leg_ids"])
    assert group["leg_ids"] == [sell["leg_id"], buy["leg_id"]]
    assert len({leg["leg_id"] for leg in recommendations["consolidated_legs"]}) == len(recommendations["consolidated_legs"])
    assert buy["group_ids"] == [group["group_id"]]
    assert buy["dependencies"] == [sell["leg_id"]]
    assert sell["side"] == "SELL"
    assert sell["ticker"] == "VB"
    assert sell["shares"] == "2"
    assert {lot["broker_lot_id"] for lot in sell["selected_lots"]} == {
        "DEMO-VB-LOT-1",
        "DEMO-VB-LOT-2",
    }
    assert {lot["st_lt"] for lot in sell["selected_lots"]} == {"ST"}
    lot_page = client.get("/api/v1/lots?ticker=VB").json()
    assert {lot["term"] for lot in lot_page["items"]} == {"ST"}
    portfolio = client.get("/api/v1/portfolio").json()
    vb_quote_as_of = next(row["quote_as_of"] for row in portfolio["positions"] if row["ticker"] == "VB")
    assert vb_quote_as_of.startswith("2026-11-06")
    assert buy["side"] == "BUY"
    assert buy["ticker"] == "VTI"
    assert buy["shares"] == "2"
    assert Decimal(run["estimated_realized_st_usd"]) == Decimal(-40)
    assert run["estimated_realized_lt_usd"] == "0"
    assert Decimal(run["cash_after_usd"]) == Decimal(850)
    current = group["impact"]["portfolio_effects"]["us_transition"]["current"]["us_sleeve_value_usd"]
    proposed = group["impact"]["portfolio_effects"]["us_transition"]["proposed_basket"]["us_sleeve_value_usd"]
    assert Decimal(current) == Decimal(proposed) == Decimal(2200)
    wash_view = client.get("/api/v1/wash-sales").json()
    assert wash_view["demo"] is True
    assert wash_view["current_restrictions"] == []
    assert wash_view["proposed_restrictions"][0]["ticker"] == "VB"
    assert wash_view["proposed_restrictions"][0]["next_eligible_purchase_date"] == "2026-12-06"
    assert wash_view["proposed_restrictions"][0]["source"].startswith("DEMO recommendation")


    selected = client.post(
        f"/api/v1/optimizer/runs/{run_id}/selection",
        json={
            "selected_group_ids": [group["group_id"]],
            "selected_sell_lots": {group["group_id"]: ["DEMO-VB-LOT-1"]},
        },
    )
    assert selected.status_code == 200, selected.text
    selected_payload = selected.json()
    selected_group = selected_payload["groups"][0]
    selected_legs = {leg["leg_id"]: leg for leg in selected_payload["consolidated_legs"]}
    selected_sell, selected_buy = (selected_legs[leg_id] for leg_id in selected_group["leg_ids"])
    assert selected_sell["shares"] == "1"
    assert Decimal(selected_sell["net_st_realized_usd"]) == Decimal(-20)
    assert selected_buy["shares"] == "1"
    assert Decimal(selected_buy["estimated_notional_usd"]) == Decimal(200)
    assert Decimal(selected_group["impact"]["sell_proceeds_usd"]) == Decimal(200)
    assert Decimal(selected.json()["estimated_realized_st_usd"]) == Decimal(-20)
    assert selected.json()["lots_sold_count"] == 1
    assert selected.json()["orders_count"] == 2

    no_trade = client.post(
        f"/api/v1/optimizer/runs/{run_id}/selection",
        json={"selected_group_ids": [], "selected_sell_lots": {}},
    )
    assert no_trade.status_code == 200, no_trade.text
    assert no_trade.json()["orders_count"] == 0
    assert Decimal(no_trade.json()["estimated_realized_lt_usd"]) == Decimal(0)
    assert no_trade.json()["groups"][0]["selected"] is False

    current_portfolio = client.get("/api/v1/portfolio").json()
    assert no_trade.json()["proposed_trade_date"] == "2026-11-05"
    empty_effects = no_trade.json()["groups"][0]["impact"]["portfolio_effects"]
    assert empty_effects["allocation"]["current"] == current_portfolio["allocation"]["current"]
    assert empty_effects["allocation"]["proposed"] == current_portfolio["allocation"]["current"]
    assert empty_effects["us_transition"]["current"] == current_portfolio["us_transition"]["current"]
    assert empty_effects["us_transition"]["proposed_basket"] == current_portfolio["us_transition"]["current"]
    assert no_trade.json()["cash_after_usd"] == current_portfolio["cash_usd"]
    assert broker.fetch_count == 1
    app.state.engine.dispose()
    restarted = create_app(
        database_url=f"sqlite:///{database_path}",
        broker=FakeBroker(split_lot_snapshot),
    )
    with TestClient(restarted, base_url="http://localhost") as second_client:
        reopened = second_client.get(f"/api/v1/optimizer/runs/{run_id}")
        assert reopened.status_code == 200
        assert reopened.json()["status"] == "demo"
        assert reopened.json()["source_generation"] == 1
        reopened_recommendations = second_client.get(
            f"/api/v1/optimizer/runs/{run_id}/recommendations"
        ).json()
        reopened_groups = reopened_recommendations["groups"]
        reopened_legs = {leg["leg_id"]: leg for leg in reopened_recommendations["consolidated_legs"]}
        reopened_sell_id, reopened_buy_id = reopened_groups[0]["leg_ids"]
        assert reopened_legs[reopened_buy_id]["shares"] == "0"
        assert reopened_legs[reopened_sell_id]["selected_lots"][0]["broker_lot_id"].startswith("DEMO-VB-LOT-")
        reopened_no_trade = second_client.post(
            f"/api/v1/optimizer/runs/{run_id}/selection",
            json={"selected_group_ids": [], "selected_sell_lots": {}},
        )
        assert reopened_no_trade.status_code == 200, reopened_no_trade.text
        reopened_effects = reopened_no_trade.json()["groups"][0]["impact"]["portfolio_effects"]
        assert reopened_effects["allocation"]["current"] == current_portfolio["allocation"]["current"]
        assert reopened_effects["allocation"]["proposed"] == current_portfolio["allocation"]["current"]
        assert reopened_effects["us_transition"]["proposed_basket"] == current_portfolio["us_transition"]["current"]
        assert reopened_no_trade.json()["proposed_trade_date"] == "2026-11-05"
        assert {"note", "rejected", "rejection_reason"} <= {
            column["name"] for column in inspect(restarted.state.engine).get_columns("recommendation_group")
        }
    restarted.state.engine.dispose()
    del app


def test_demo_selection_reports_full_position_exit_from_shared_evaluator(tmp_path: Path) -> None:
    original = FakeBroker.demo_snapshot()
    vb_position = next(row for row in original.positions if row.ticker == "VB")
    vb_lot = next(row for row in original.lots if row.ticker == "VB")
    snapshot = original.model_copy(
        update={
            "positions": [vb_position.model_copy(update={"shares": Decimal(1), "market_value_usd": Decimal(200)})],
            "lots": [vb_lot.model_copy(update={"shares": Decimal(1), "available_shares": Decimal(1)})],
            "cash_usd": Decimal(850),
            "settled_buying_power_usd": Decimal(850),
        }
    )
    database_path = tmp_path / "full-position-exit.sqlite3"
    app = create_app(
        database_url=f"sqlite:///{database_path}",
        broker=FakeBroker(snapshot),
        seed_demo_data=True,
    )
    with TestClient(app, base_url="http://localhost") as client:
        _configure_batch_policy(client, minimum_buy="0")
        run = client.post("/api/v1/optimizer/runs", json={}).json()
        assert run["positions_exited_count"] == 1
        recs = client.get(f"/api/v1/optimizer/runs/{run['run_id']}/recommendations").json()
        group = recs["groups"][0]
        selected = client.post(
            f"/api/v1/optimizer/runs/{run['run_id']}/selection",
            json={"selected_group_ids": [group["group_id"]]},
        )
        assert selected.status_code == 200, selected.text
        assert selected.json()["positions_exited_count"] == 1
        sell = next(leg for leg in selected.json()["consolidated_legs"] if leg["side"] == "SELL")
        assert sell["shares"] == "1"
        assert sell["selected_lots"][0]["broker_lot_id"] == vb_lot.broker_lot_id
    app.state.engine.dispose()


def test_shared_replacement_buy_pools_proceeds_and_counts_consolidated_orders(
    shared_replacement_app: tuple[FastAPI, TestClient, Path],
) -> None:
    app, client, _ = shared_replacement_app
    response = client.post("/api/v1/optimizer/runs", json={})
    assert response.status_code == 201, response.text
    run = response.json()
    assert run["orders_count"] == 3
    assert run["lots_sold_count"] == 3
    recs = client.get(f"/api/v1/optimizer/runs/{run['run_id']}/recommendations").json()
    assert len(recs["groups"]) == 2
    legs = {leg["leg_id"]: leg for leg in recs["consolidated_legs"]}
    assert len(legs) == len(recs["consolidated_legs"]) == 3
    sells = [leg for leg in recs["consolidated_legs"] if leg["side"] == "SELL"]
    buys = [leg for leg in recs["consolidated_legs"] if leg["side"] == "BUY"]
    assert [leg["side"] for leg in recs["consolidated_legs"]] == ["SELL", "SELL", "BUY"]
    assert len(sells) == 2
    assert all(Decimal(leg["estimated_notional_usd"]) == Decimal(350) for leg in sells)
    assert len(buys) == 1
    buy = buys[0]
    assert buy["ticker"] == "VTI"
    assert buy["shares"] == "3"
    assert buy["estimated_notional_usd"] == "600"
    assert set(buy["dependencies"]) == {leg["leg_id"] for leg in sells}
    assert set(buy["group_ids"]) == {group["group_id"] for group in recs["groups"]}
    for group in recs["groups"]:
        assert len(group["leg_ids"]) == 2
        assert set(group["leg_ids"]) <= set(legs)
        assert buy["leg_id"] in group["leg_ids"]

    with app.state.session_factory() as session:
        database_buy_legs = (
            session.query(RecommendationLeg)
            .join(RecommendationGroup, RecommendationGroup.id == RecommendationLeg.group_id)
            .filter(RecommendationGroup.run_id == run["run_id"], RecommendationLeg.side == "BUY")
            .all()
        )
        assert len(database_buy_legs) == 1
        assert session.query(RecommendationGroupLeg).filter_by(leg_id=buy["leg_id"]).count() == 2

    json_export = client.get(f"/api/v1/optimizer/runs/{run['run_id']}/export?format=json").json()
    assert json_export["metadata"]["proposed_trade_date"] == "2026-11-05"
    assert [leg["leg_id"] for leg in json_export["run"]["consolidated_legs"]].count(buy["leg_id"]) == 1
    csv_response = client.get(f"/api/v1/optimizer/runs/{run['run_id']}/export?format=csv")
    rows = list(csv.DictReader(io.StringIO(csv_response.text)))
    assert rows[0]["proposed_trade_date"] == "2026-11-05"
    assert [row["leg_id"] for row in rows if row["side"] == "BUY"] == [buy["leg_id"]]

    deselected = client.post(
        f"/api/v1/optimizer/runs/{run['run_id']}/selection",
        json={"selected_group_ids": [recs["groups"][0]["group_id"]]},
    )
    assert deselected.status_code == 422
    assert deselected.json()["code"] == "selected_basket_infeasible"
    unchanged = client.get(f"/api/v1/optimizer/runs/{run['run_id']}/recommendations").json()
    unchanged_buy = next(leg for leg in unchanged["consolidated_legs"] if leg["side"] == "BUY")
    assert unchanged_buy["shares"] == "3"
    assert set(unchanged_buy["dependencies"]) == {leg["leg_id"] for leg in sells}


def test_recommendation_response_bulk_loads_once_and_reopens_with_constant_queries(
    demo_app: tuple[FastAPI, TestClient, FakeBroker, Path],
    shared_replacement_app: tuple[FastAPI, TestClient, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    single_app, single_client, _, database_path = demo_app
    shared_app, shared_client, _ = shared_replacement_app
    single_run = _create_run(single_client)
    shared_run = _create_run(shared_client)

    serializer = Mock(wraps=demo_optimizer._leg_dict)
    monkeypatch.setattr(demo_optimizer, "_leg_dict", serializer)
    single_response, single_selects = count_selects(
        single_app.state.engine,
        lambda: single_client.get(f"/api/v1/optimizer/runs/{single_run['run_id']}/recommendations"),
    )
    shared_response, shared_selects = count_selects(
        shared_app.state.engine,
        lambda: shared_client.get(f"/api/v1/optimizer/runs/{shared_run['run_id']}/recommendations"),
    )
    assert single_response.status_code == 200, single_response.text
    assert shared_response.status_code == 200, shared_response.text
    single_body = single_response.json()
    shared_body = shared_response.json()
    assert len(single_body["groups"]) == 1
    assert len(single_body["consolidated_legs"]) == 2
    assert len(shared_body["groups"]) == 2
    assert len(shared_body["consolidated_legs"]) == 3
    assert single_selects == shared_selects == 6
    assert [leg["side"] for leg in shared_body["consolidated_legs"]] == ["SELL", "SELL", "BUY"]
    shared_sells = [leg for leg in shared_body["consolidated_legs"] if leg["side"] == "SELL"]
    shared_buy = next(leg for leg in shared_body["consolidated_legs"] if leg["side"] == "BUY")
    assert set(shared_buy["dependencies"]) == {leg["leg_id"] for leg in shared_sells}
    for response_body in (single_body, shared_body):
        assert len({leg["leg_id"] for leg in response_body["consolidated_legs"]}) == len(
            response_body["consolidated_legs"]
        )
    serialized_ids = [call.args[0].id for call in serializer.call_args_list]
    expected_ids = [
        leg["leg_id"]
        for response_body in (single_body, shared_body)
        for leg in response_body["consolidated_legs"]
    ]
    assert sorted(serialized_ids) == sorted(expected_ids)

    reopened_app = create_app(
        database_url=f"sqlite:///{database_path}", broker=FakeBroker(), seed_demo_data=False
    )
    serializer.reset_mock()
    with TestClient(reopened_app, base_url="http://localhost") as reopened_client:
        reopened_response, reopened_selects = count_selects(
            reopened_app.state.engine,
            lambda: reopened_client.get(
                f"/api/v1/optimizer/runs/{single_run['run_id']}/recommendations"
            ),
        )
        assert reopened_response.status_code == 200, reopened_response.text
        assert reopened_response.json() == single_body
        assert reopened_selects == single_selects
        assert serializer.call_count == len(single_body["consolidated_legs"])
    reopened_app.state.engine.dispose()

    single_group = single_body["groups"][0]
    single_sell = next(leg for leg in single_body["consolidated_legs"] if leg["side"] == "SELL")
    single_lot_ids = [lot["broker_lot_id"] for lot in single_sell["selected_lots"]]
    serializer.reset_mock()
    one_lot_selection, one_lot_selects = count_selects(
        single_app.state.engine,
        lambda: single_client.post(
            f"/api/v1/optimizer/runs/{single_run['run_id']}/selection",
            json={
                "selected_group_ids": [single_group["group_id"]],
                "selected_sell_lots": {single_group["group_id"]: single_lot_ids[:1]},
            },
        ),
    )
    all_lots_selection, all_lots_selects = count_selects(
        single_app.state.engine,
        lambda: single_client.post(
            f"/api/v1/optimizer/runs/{single_run['run_id']}/selection",
            json={
                "selected_group_ids": [single_group["group_id"]],
                "selected_sell_lots": {single_group["group_id"]: single_lot_ids},
            },
        ),
    )
    shared_selection, shared_selection_selects = count_selects(
        shared_app.state.engine,
        lambda: shared_client.post(
            f"/api/v1/optimizer/runs/{shared_run['run_id']}/selection",
            json={"selected_group_ids": [group["group_id"] for group in shared_body["groups"]]},
        ),
    )
    assert one_lot_selection.status_code == all_lots_selection.status_code == 200
    assert shared_selection.status_code == 200, shared_selection.text
    assert one_lot_selects == all_lots_selects == 31
    assert shared_selection_selects == 42
    assert serializer.call_count == 2 * len(single_body["consolidated_legs"]) + len(
        shared_body["consolidated_legs"]
    )


def test_removing_one_sell_lot_resizes_shared_buy_and_keeps_only_funding_dependencies(
    shared_replacement_app: tuple[FastAPI, TestClient, Path],
) -> None:
    _, client, _ = shared_replacement_app
    _configure_batch_policy(client, minimum_buy="300")
    run = client.post("/api/v1/optimizer/runs", json={}).json()
    recs = client.get(f"/api/v1/optimizer/runs/{run['run_id']}/recommendations").json()
    groups = recs["groups"]
    aapl_group = next(group for group in groups if group["sleeve_key"] == "us_equities" and "AAPL" in group["rationale"])
    legs = {leg["leg_id"]: leg for leg in recs["consolidated_legs"]}
    aapl_sell = next(legs[leg_id] for leg_id in aapl_group["leg_ids"] if legs[leg_id]["side"] == "SELL")
    selected = client.post(
        f"/api/v1/optimizer/runs/{run['run_id']}/selection",
        json={
            "selected_group_ids": [group["group_id"] for group in groups],
            "selected_sell_lots": {aapl_group["group_id"]: ["DEMO-AAPL-SHARED-1"]},
        },
    )
    assert selected.status_code == 200, selected.text
    updated_legs = {leg["leg_id"]: leg for leg in selected.json()["consolidated_legs"]}
    buy = next(leg for leg in updated_legs.values() if leg["side"] == "BUY")
    assert buy["shares"] == "2"
    assert buy["estimated_notional_usd"] == "400"
    assert set(buy["dependencies"]) == {
        leg["leg_id"] for leg in updated_legs.values() if leg["side"] == "SELL" and leg["shares"] != "0"
    }
    assert updated_legs[aapl_sell["leg_id"]]["shares"] == "1"
    assert [lot["broker_lot_id"] for lot in updated_legs[aapl_sell["leg_id"]]["selected_lots"] if lot["selected"]] == [
        "DEMO-AAPL-SHARED-1"
    ]


def test_rejecting_group_preserves_other_groups_existing_sell_lot_subset(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "reject-preserves-subset.sqlite3"
    app = create_app(
        database_url=f"sqlite:///{database_path}",
        broker=FakeBroker(_shared_replacement_snapshot((2, 1))),
        seed_demo_data=True,
    )
    with TestClient(app, base_url="http://localhost") as client:
        _configure_batch_policy(client, minimum_buy="0")
        run = client.post("/api/v1/optimizer/runs", json={}).json()
        recs = client.get(f"/api/v1/optimizer/runs/{run['run_id']}/recommendations").json()
        groups = recs["groups"]
        aapl_group = next(group for group in groups if "AAPL" in group["rationale"])
        msft_group = next(group for group in groups if "MSFT" in group["rationale"])
        selection = client.post(
            f"/api/v1/optimizer/runs/{run['run_id']}/selection",
            json={
                "selected_group_ids": [aapl_group["group_id"], msft_group["group_id"]],
                "selected_sell_lots": {aapl_group["group_id"]: ["DEMO-AAPL-SHARED-1"]},
            },
        )
        assert selection.status_code == 200, selection.text
        before = selection.json()
        before_groups = {group["group_id"]: group for group in before["groups"]}
        before_legs = {leg["leg_id"]: leg for leg in before["consolidated_legs"]}
        aapl_sell_id = next(leg_id for leg_id in before_groups[aapl_group["group_id"]]["leg_ids"] if before_legs[leg_id]["side"] == "SELL")
        before_aapl = before_legs[aapl_sell_id]
        assert before_aapl["shares"] == "2"
        assert before_aapl["net_lt_realized_usd"] == "-50"
        assert before_groups[aapl_group["group_id"]]["impact"]["selected_sell_lots_count"] == 1

        rejected = client.patch(
            f"/api/v1/optimizer/runs/{run['run_id']}/recommendations/{msft_group['group_id']}",
            json={"rejected": True, "rejection_reason": "not selected"},
        )
        assert rejected.status_code == 200, rejected.text
        after = rejected.json()
        assert after == client.get(f"/api/v1/optimizer/runs/{run['run_id']}/recommendations").json()
        assert {"groups", "consolidated_legs", "cash_before_usd", "cash_after_usd", "portfolio_effects"} <= set(after)
        assert after["estimated_realized_st_usd"] is not None
        assert after["orders_count"] == 2
        after_groups = {group["group_id"]: group for group in after["groups"]}
        after_legs = {leg["leg_id"]: leg for leg in after["consolidated_legs"]}
        after_aapl = after_legs[aapl_sell_id]
        assert after_groups[aapl_group["group_id"]]["selected"] is True
        assert after_groups[msft_group["group_id"]]["selected"] is False
        assert after_groups[msft_group["group_id"]]["rejected"] is True
        assert after_aapl["shares"] == before_aapl["shares"] == "2"
        assert after_aapl["net_lt_realized_usd"] == before_aapl["net_lt_realized_usd"] == "-50"
        assert [lot["broker_lot_id"] for lot in after_aapl["selected_lots"] if lot["selected"]] == [
            "DEMO-AAPL-SHARED-1"
        ]
        buy = next(leg for leg in after["consolidated_legs"] if leg["side"] == "BUY")
        assert buy["shares"] == "1"
        assert buy["dependencies"] == [aapl_sell_id]
        assert set(buy["group_ids"]) == {aapl_group["group_id"], msft_group["group_id"]}
        assert after["lots_sold_count"] == 1
        assert after["orders_count"] == 2
    app.state.engine.dispose()




def test_generation_bound_lot_review_intent_changes_the_confirmed_demo_basket(
    demo_app: tuple[FastAPI, TestClient, FakeBroker, Path],
) -> None:
    _, client, _, _ = demo_app
    run = _create_run(client)
    lot_page = client.get("/api/v1/lots?search=DEMO-VB-LOT-1&limit=1").json()
    assert lot_page["source_generation"] == run["source_generation"]
    assert lot_page["total"] == 1

    requested_lot_id = lot_page["items"][0]["broker_lot_id"]
    response = client.post(
        f"/api/v1/optimizer/runs/{run['run_id']}/lot-review-intent",
        json={"source_generation": lot_page["source_generation"], "broker_lot_ids": [requested_lot_id]},
    )
    assert response.status_code == 200, response.text
    confirmed = response.json()
    assert confirmed["demo"] is True
    assert confirmed["actionable"] is False
    assert confirmed["lots_sold_count"] == 1
    assert confirmed["orders_count"] == 2
    assert "order_approved" not in confirmed
    group = confirmed["groups"][0]
    assert group["selected"] is True
    legs = {leg["leg_id"]: leg for leg in confirmed["consolidated_legs"]}
    sell = next(leg for leg in legs.values() if leg["side"] == "SELL")
    buy = next(leg for leg in legs.values() if leg["side"] == "BUY")
    assert sell["shares"] == "1"
    assert {lot["broker_lot_id"] for lot in sell["selected_lots"] if lot["selected"]} == {
        requested_lot_id
    }
    assert buy["shares"] == "1"
    assert buy["dependencies"] == [sell["leg_id"]]


def test_lot_review_intent_stale_missing_unsupported_and_outside_fail_atomically(
    demo_app: tuple[FastAPI, TestClient, FakeBroker, Path],
) -> None:
    app, client, _, _ = demo_app
    run = _create_run(client)
    run_id = run["run_id"]
    before = client.get(f"/api/v1/optimizer/runs/{run_id}/recommendations").json()

    stale = client.post(
        f"/api/v1/optimizer/runs/{run_id}/lot-review-intent",
        json={"source_generation": run["source_generation"] + 1, "broker_lot_ids": ["DEMO-VB-LOT-1"]},
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "stale_lot_review_intent"
    assert stale.json()["details"]["basket_unchanged"] is True
    assert client.get(f"/api/v1/optimizer/runs/{run_id}/recommendations").json() == before

    rejected = client.post(
        f"/api/v1/optimizer/runs/{run_id}/lot-review-intent",
        json={
            "source_generation": run["source_generation"],
            "broker_lot_ids": ["DEMO-VB-LOT-1", "NOT-A-LOT", "DEMO-AAPL-LOT-1"],
        },
    )
    assert rejected.status_code == 422
    assert rejected.json()["code"] == "lot_review_intent_rejected"
    assert rejected.json()["details"]["basket_unchanged"] is True
    reasons = {item["broker_lot_id"]: item["reason"] for item in rejected.json()["details"]["rejected_lots"]}
    assert reasons == {
        "NOT-A-LOT": "missing_current_lot",
        "DEMO-AAPL-LOT-1": "outside_saved_demo_candidates",
    }
    assert client.get(f"/api/v1/optimizer/runs/{run_id}/recommendations").json() == before

    with app.state.session_factory.begin() as session:
        persisted = session.get(OptimizerRun, run_id)
        assert persisted is not None
        persisted.solver_version = "PHASE2"
    unsupported = client.post(
        f"/api/v1/optimizer/runs/{run_id}/lot-review-intent",
        json={"source_generation": run["source_generation"], "broker_lot_ids": ["DEMO-VB-LOT-1"]},
    )
    assert unsupported.status_code == 503
    assert unsupported.json()["code"] == "lot_review_intent_unsupported"
    assert unsupported.json()["details"]["basket_unchanged"] is True
    assert client.get(f"/api/v1/optimizer/runs/{run_id}/recommendations").json() == before


def test_infeasible_lot_review_intent_preserves_the_confirmed_basket(
    shared_replacement_app: tuple[FastAPI, TestClient, Path],
) -> None:
    _, client, _ = shared_replacement_app
    run = _create_run(client)
    run_id = run["run_id"]
    before = client.get(f"/api/v1/optimizer/runs/{run_id}/recommendations").json()
    aapl_sell = next(
        leg for leg in before["consolidated_legs"] if leg["side"] == "SELL" and leg["ticker"] == "AAPL"
    )
    requested_lot_id = next(lot["broker_lot_id"] for lot in aapl_sell["selected_lots"])

    infeasible = client.post(
        f"/api/v1/optimizer/runs/{run_id}/lot-review-intent",
        json={"source_generation": run["source_generation"], "broker_lot_ids": [requested_lot_id]},
    )
    assert infeasible.status_code == 422
    assert infeasible.json()["code"] == "selected_basket_infeasible"
    assert infeasible.json()["details"]["basket_unchanged"] is True
    assert client.get(f"/api/v1/optimizer/runs/{run_id}/recommendations").json() == before

def test_selection_rejects_unknown_or_empty_lot_subsets_and_stale_runs(
    demo_app: tuple[FastAPI, TestClient, FakeBroker, Path]
) -> None:
    _, client, _, _ = demo_app
    run = _create_run(client)
    group_id = run["groups"][0]["group_id"]

    invalid = client.post(
        f"/api/v1/optimizer/runs/{run['run_id']}/selection",
        json={"selected_group_ids": [group_id], "selected_sell_lots": {group_id: ["NOT-A-LOT"]}},
    )
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "invalid_lot_selection"
    empty = client.post(
        f"/api/v1/optimizer/runs/{run['run_id']}/selection",
        json={"selected_group_ids": [group_id], "selected_sell_lots": {group_id: []}},
    )
    assert empty.status_code == 422
    assert empty.json()["code"] == "empty_selected_group"
    unknown_group = client.post(
        f"/api/v1/optimizer/runs/{run['run_id']}/selection",
        json={"selected_group_ids": ["not-a-group"]},
    )
    assert unknown_group.status_code == 422
    assert unknown_group.json()["code"] == "invalid_group_selection"

    assert client.post("/api/v1/portfolio/sync").status_code == 200
    stale = client.post(
        f"/api/v1/optimizer/runs/{run['run_id']}/selection",
        json={"selected_group_ids": [group_id]},
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "stale_run_source"


def test_selection_blocks_same_generation_quote_and_lot_changes(
    demo_app: tuple[FastAPI, TestClient, FakeBroker, Path]
) -> None:
    app, client, _, _ = demo_app
    run = _create_run(client)
    group_id = run["groups"][0]["group_id"]

    with app.state.session_factory.begin() as session:
        vti = session.query(Security).filter_by(ticker="VTI").one()
        quote = session.query(CurrentQuote).filter_by(security_id=vti.id).one()
        quote.last_usd = Decimal(201)
    changed_quote = client.post(
        f"/api/v1/optimizer/runs/{run['run_id']}/selection",
        json={"selected_group_ids": [group_id]},
    )
    assert changed_quote.status_code == 409
    assert changed_quote.json()["code"] == "stale_run_quote"
    with app.state.session_factory.begin() as session:
        vti = session.query(Security).filter_by(ticker="VTI").one()
        session.query(CurrentQuote).filter_by(security_id=vti.id).one().last_usd = Decimal(200)

    with app.state.session_factory.begin() as session:
        lot = session.query(CurrentTaxLot).filter_by(broker_lot_id="DEMO-VB-LOT-1").one()
        lot.available_shares = Decimal(0)
    unavailable_lot = client.post(
        f"/api/v1/optimizer/runs/{run['run_id']}/selection",
        json={"selected_group_ids": [group_id]},
    )
    assert unavailable_lot.status_code == 409
    assert unavailable_lot.json()["code"] == "stale_run_lot"


def test_configured_tax_rates_do_not_fabricate_a_demo_tax_estimate(
    demo_app: tuple[FastAPI, TestClient, FakeBroker, Path]
) -> None:
    _, client, _, _ = demo_app
    active = client.get("/api/v1/policy").json()["active"]
    payload = {
        "source_revision_id": active["id"],
        "settings": active["settings"],
        "sleeves": active["sleeves"],
        "allowed_securities": active["allowed_securities"],
        "overrides": active["overrides"],
        "reassignments": {},
    }
    payload["settings"]["short_term_tax_rate"] = "0.35"
    payload["settings"]["long_term_tax_rate"] = "0.15"
    draft = client.post("/api/v1/policy/drafts", json=payload)
    assert draft.status_code == 201, draft.text
    activated = client.post(f"/api/v1/policy/{draft.json()['id']}/activate")
    assert activated.status_code == 200, activated.text

    run = _create_run(client)
    assert run["tax_profile_configured"] is True
    assert run["estimated_tax_benefit_usd"] is None
    assert run["estimated_tax_benefit_status"] == "optimizer_unavailable"

def test_export_metadata_lot_attribution_notes_activity_and_disabled_future_routes(
    demo_app: tuple[FastAPI, TestClient, FakeBroker, Path]
) -> None:
    _, client, broker, _ = demo_app
    run = _create_run(client)
    group = run["groups"][0]
    run_id = run["run_id"]
    group_id = group["group_id"]

    json_export = client.get(f"/api/v1/optimizer/runs/{run_id}/export?format=json")
    assert json_export.status_code == 200
    export_body = json_export.json()
    assert export_body["metadata"]["solver_version"] == "DEMO"
    assert export_body["metadata"]["demo"] is True
    assert export_body["metadata"]["frozen_display_context"] == export_body["run"]["frozen_display_context"]
    exported_lot_ids = {
        lot["broker_lot_id"]
        for leg in export_body["run"]["consolidated_legs"]
        for lot in leg["selected_lots"]
    }
    assert exported_lot_ids == {"DEMO-VB-LOT-1", "DEMO-VB-LOT-2"}

    csv_export = client.get(f"/api/v1/optimizer/runs/{run_id}/export?format=csv")
    assert csv_export.status_code == 200
    rows = list(csv.DictReader(io.StringIO(csv_export.text)))
    exported_run = export_body["run"]
    metadata_row = rows[0]
    assert metadata_row["record_type"] == "metadata"
    assert metadata_row["proposed_trade_date"] == exported_run["proposed_trade_date"] == "2026-11-05"
    for field in (
        "orders_count",
        "lots_sold_count",
        "positions_exited_count",
        "estimated_realized_st_usd",
        "estimated_realized_lt_usd",
        "estimated_tax_benefit_status",
        "cash_before_usd",
        "cash_after_usd",
    ):
        assert metadata_row[field] == str(exported_run[field])
    assert metadata_row["portfolio_effects_json"] == json.dumps(
        exported_run["portfolio_effects"], sort_keys=True, separators=(",", ":")
    )
    assert metadata_row["frozen_display_context_json"] == json.dumps(
        exported_run["frozen_display_context"], sort_keys=True, separators=(",", ":")
    )
    assert exported_run["estimated_tax_benefit_usd"] is None
    assert metadata_row["estimated_tax_benefit_usd"] == ""

    json_legs = {leg["leg_id"]: leg for leg in exported_run["consolidated_legs"]}
    csv_leg_ids = {row["leg_id"] for row in rows[1:] if row["leg_id"]}
    assert csv_leg_ids == set(json_legs)
    assert len(json_legs) == exported_run["orders_count"]
    for leg_id, leg in json_legs.items():
        leg_rows = [row for row in rows[1:] if row["leg_id"] == leg_id]
        assert {row["shares"] for row in leg_rows} == {leg["shares"]}
        assert {row["estimated_notional_usd"] for row in leg_rows} == {leg["estimated_notional_usd"]}
        assert {tuple(json.loads(row["dependencies"])) for row in leg_rows} == {tuple(leg["dependencies"])}
        assert {tuple(json.loads(row["group_ids"])) for row in leg_rows} == {tuple(leg["group_ids"])}
        if leg["side"] == "SELL":
            csv_lots = {row["broker_lot_id"]: row for row in leg_rows if row["broker_lot_id"]}
            expected_lots = {lot["broker_lot_id"]: lot for lot in leg["selected_lots"]}
            assert set(csv_lots) == set(expected_lots)
            for lot_id, lot in expected_lots.items():
                assert csv_lots[lot_id]["lot_shares"] == lot["shares"]
                assert csv_lots[lot_id]["acquired_date"] == lot["acquired_date"]
                assert csv_lots[lot_id]["adjusted_basis_usd"] == lot["adjusted_basis_usd"]
                assert csv_lots[lot_id]["st_lt"] == lot["st_lt"]
                assert csv_lots[lot_id]["realized_pl_usd"] == lot["realized_pl_usd"]
                assert csv_lots[lot_id]["lot_selected"] == str(lot["selected"])

    assert {row["broker_lot_id"] for row in rows if row["broker_lot_id"]} == exported_lot_ids
    assert all(row["run_id"] == run_id and row["solver_version"] == "DEMO" for row in rows)

    patch_preflight = client.options(
        f"/api/v1/optimizer/runs/{run_id}/recommendations/{group_id}",
        headers={"Origin": "http://localhost:9000", "Access-Control-Request-Method": "PATCH"},
    )
    assert patch_preflight.status_code == 200
    assert "PATCH" in patch_preflight.headers["access-control-allow-methods"]
    remote_preflight = client.options(
        f"/api/v1/optimizer/runs/{run_id}/recommendations/{group_id}",
        headers={"Origin": "https://remote.example", "Access-Control-Request-Method": "PATCH"},
    )
    assert remote_preflight.status_code == 400

    annotation = client.patch(
        f"/api/v1/optimizer/runs/{run_id}/recommendations/{group_id}",
        json={"note": "Reviewed offline", "rejected": True, "rejection_reason": "Demo only"},
    )
    assert annotation.status_code == 200, annotation.text
    annotation_body = annotation.json()
    annotated_group = next(item for item in annotation_body["groups"] if item["group_id"] == group_id)
    assert annotated_group["note"] == "Reviewed offline"
    assert annotated_group["rejected"] is True
    assert annotated_group["selected"] is False
    assert annotation_body == client.get(f"/api/v1/optimizer/runs/{run_id}/recommendations").json()
    annotated = annotation_body
    annotated_legs = {leg["leg_id"]: leg for leg in annotated["consolidated_legs"]}
    assert all(annotated_legs[leg_id]["shares"] == "0" for leg_id in annotated_group["leg_ids"] if annotated_legs[leg_id]["side"] == "SELL")
    activity = client.get("/api/v1/activity?event_type=recommendation_annotation&status=complete")
    assert activity.status_code == 200
    assert activity.json()["total"] == 1
    assert activity.json()["items"][0]["details"]["group_id"] == group_id

    wash = client.get("/api/v1/wash-sales")
    assert wash.status_code == 200
    assert wash.json()["demo"] is True
    assert wash.json()["current_restrictions"] == []
    assert any("historical realized-loss lot attribution is unavailable" in warning for warning in wash.json()["warnings"])

    disabled = [
        client.get("/api/v1/auth/etrade/status"),
        client.post("/api/v1/auth/etrade/start"),
        client.post("/api/v1/auth/etrade/verify", json={"verifier": "12345"}),
        client.post("/api/v1/orders/fake-leg/preview"),
        client.post("/api/v1/orders/fake-leg/submit"),
    ]
    assert disabled[0].json()["status"] == "disabled"
    for response in disabled[1:]:
        assert response.status_code == 503
        assert {"code", "message", "details", "correlation_id"} <= set(response.json())
        assert response.json()["details"]["available"] is False
    real_run_response = client.post("/api/v1/optimizer/runs", json={"mode": "real_optimizer"})
    assert real_run_response.status_code == 201, real_run_response.text
    real_run = real_run_response.json()
    assert real_run["mode"] == "real_optimizer"
    assert real_run["demo"] is False
    assert real_run["actionable"] is False
    assert real_run["optimizer_metrics"]["engine"] == "production_optimizer"
    assert real_run["solver_version"] != "DEMO"
    assert broker.fetch_count == 1
    assert not hasattr(broker, "preview_order")
    assert not hasattr(broker, "submit_approved_order")
    tables = set(inspect(client.app.state.engine).get_table_names())
    assert not {"order_record", "order_fill"} & tables



def test_annotation_field_presence_clear_restore_and_reason_limits(
    demo_app: tuple[FastAPI, TestClient, FakeBroker, Path],
) -> None:
    _, client, _, _ = demo_app
    run = _create_run(client)
    run_id = run["run_id"]
    group_id = run["groups"][0]["group_id"]
    endpoint = f"/api/v1/optimizer/runs/{run_id}/recommendations/{group_id}"
    recommendations_url = f"/api/v1/optimizer/runs/{run_id}/recommendations"
    original = client.get(recommendations_url).json()
    original_group = original["groups"][0]
    assert original_group["selected"] is True

    too_long = client.patch(
        endpoint,
        json={"note": "must not be written", "rejected": True, "rejection_reason": "x" * 501},
    )
    assert too_long.status_code == 422
    assert client.get(recommendations_url).json() == original

    note = "n" * 2000
    saved_note = client.patch(endpoint, json={"note": note})
    assert saved_note.status_code == 200, saved_note.text
    saved_group = saved_note.json()["groups"][0]
    assert saved_group["note"] == note

    rejected = client.patch(endpoint, json={"rejected": True})
    assert rejected.status_code == 200, rejected.text
    rejected_group = rejected.json()["groups"][0]
    assert rejected_group["note"] == note
    assert rejected_group["selected"] is False
    assert rejected_group["rejected"] is True
    assert rejected_group["rejection_reason"] is None
    assert rejected.json()["consolidated_legs"]

    reason = "r" * 500
    with_reason = client.patch(endpoint, json={"rejected": True, "rejection_reason": reason})
    assert with_reason.status_code == 200, with_reason.text
    assert with_reason.json()["groups"][0]["rejection_reason"] == reason

    restored = client.patch(endpoint, json={"rejected": False})
    assert restored.status_code == 200, restored.text
    restored_group = restored.json()["groups"][0]
    assert restored_group["rejected"] is False
    assert restored_group["rejection_reason"] is None
    assert restored_group["selected"] is False
    assert restored_group["note"] == note

    cleared = client.patch(endpoint, json={"note": None})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["groups"][0]["note"] is None
    assert cleared.json()["groups"][0]["selected"] is False


def test_annotation_recalculation_failure_rolls_back_annotations_and_basket(
    shared_replacement_app: tuple[FastAPI, TestClient, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, client, _ = shared_replacement_app
    _configure_batch_policy(client, minimum_buy="0")
    run = client.post("/api/v1/optimizer/runs", json={}).json()
    run_id = run["run_id"]
    recs = client.get(f"/api/v1/optimizer/runs/{run_id}/recommendations").json()
    aapl_group = next(group for group in recs["groups"] if "AAPL" in group["rationale"])
    msft_group = next(group for group in recs["groups"] if "MSFT" in group["rationale"])
    selection = client.post(
        f"/api/v1/optimizer/runs/{run_id}/selection",
        json={
            "selected_group_ids": [aapl_group["group_id"], msft_group["group_id"]],
            "selected_sell_lots": {aapl_group["group_id"]: ["DEMO-AAPL-SHARED-1"]},
        },
    )
    assert selection.status_code == 200, selection.text
    annotation_url = f"/api/v1/optimizer/runs/{run_id}/recommendations/{msft_group['group_id']}"
    note = client.patch(annotation_url, json={"note": "preserve me"})
    assert note.status_code == 200, note.text
    before = client.get(f"/api/v1/optimizer/runs/{run_id}/recommendations").json()

    def fail_recalculation(*args: object, **kwargs: object) -> None:
        raise demo_optimizer.AppError("test_recalculation_failure", "Forced recalculation failure", status_code=422)

    monkeypatch.setattr(demo_optimizer, "_recalculate_selection", fail_recalculation)
    failed = client.patch(
        annotation_url,
        json={"note": "must roll back", "rejected": True, "rejection_reason": "not selected"},
    )
    assert failed.status_code == 422
    assert client.get(f"/api/v1/optimizer/runs/{run_id}/recommendations").json() == before



def test_frozen_run_display_context_survives_renamed_disabled_and_removed_sleeves_after_restart(
    tmp_path: Path, split_lot_snapshot: BrokerSnapshot
) -> None:
    database_path = tmp_path / "frozen-display-context.sqlite3"
    database_url = f"sqlite:///{database_path}"
    app = create_app(database_url=database_url, broker=FakeBroker(split_lot_snapshot), seed_demo_data=True)
    with TestClient(app, base_url="http://localhost") as client:
        active = client.get("/api/v1/policy").json()["active"]
        run = _create_run(client)
        run_id = run["run_id"]
        original_context = run["frozen_display_context"]
        assert original_context["available"] is True
        assert original_context["source"] == "frozen_input_bundle"
        original_sleeves = {row["sleeve_key"]: row for row in original_context["sleeves"]}
        assert original_sleeves["us_equities"]["display_name"] == "DEMO US Equities"
        assert original_sleeves["us_etf"]["parent_sleeve_key"] == "us_equities"
        assert original_sleeves["us_etf"]["is_transition_destination"] is True
        original_retained_loss_target = original_context["settings"]["target_retained_net_loss_usd"]

        renamed_payload = {
            "source_revision_id": active["id"],
            "settings": active["settings"],
            "sleeves": active["sleeves"],
            "allowed_securities": active["allowed_securities"],
            "overrides": active["overrides"],
            "reassignments": {},
        }
        renamed_payload["settings"]["target_retained_net_loss_usd"] = "9876.54"
        next(row for row in renamed_payload["sleeves"] if row["sleeve_key"] == "us_equities")[
            "display_name"
        ] = "Current US sleeve name"
        renamed_draft = client.post("/api/v1/policy/drafts", json=renamed_payload)
        assert renamed_draft.status_code == 201, renamed_draft.text
        renamed_activation = client.post(f"/api/v1/policy/{renamed_draft.json()['id']}/activate")
        assert renamed_activation.status_code == 200, renamed_activation.text

        active = client.get("/api/v1/policy").json()["active"]
        disabled_payload = {
            "source_revision_id": active["id"],
            "settings": active["settings"],
            "sleeves": active["sleeves"],
            "allowed_securities": active["allowed_securities"],
            "overrides": active["overrides"],
            "reassignments": {},
        }
        disabled_sleeve = next(row for row in disabled_payload["sleeves"] if row["sleeve_key"] == "us_etf")
        disabled_sleeve["enabled"] = False
        disabled_sleeve["is_transition_destination"] = False
        for candidate in disabled_payload["allowed_securities"]:
            if candidate["sleeve_key"] == "us_equities" and candidate["sub_sleeve_key"] == "us_etf":
                candidate["sub_sleeve_key"] = None
        disabled_draft = client.post("/api/v1/policy/drafts", json=disabled_payload)
        assert disabled_draft.status_code == 201, disabled_draft.text
        disabled_activation = client.post(f"/api/v1/policy/{disabled_draft.json()['id']}/activate")
        assert disabled_activation.status_code == 200, disabled_activation.text
        disabled_active = client.get("/api/v1/policy").json()["active"]
        assert next(row for row in disabled_active["sleeves"] if row["sleeve_key"] == "us_etf")["enabled"] is False

        removed_payload = {
            "source_revision_id": disabled_active["id"],
            "settings": disabled_active["settings"],
            "sleeves": [row for row in disabled_active["sleeves"] if row["sleeve_key"] != "us_etf"],
            "allowed_securities": disabled_active["allowed_securities"],
            "overrides": disabled_active["overrides"],
            "reassignments": {},
        }
        removed_draft = client.post("/api/v1/policy/drafts", json=removed_payload)
        assert removed_draft.status_code == 201, removed_draft.text
        removed_activation = client.post(f"/api/v1/policy/{removed_draft.json()['id']}/activate")
        assert removed_activation.status_code == 200, removed_activation.text
        latest_active = client.get("/api/v1/policy").json()["active"]
        assert "us_etf" not in {row["sleeve_key"] for row in latest_active["sleeves"]}
        assert next(row for row in latest_active["sleeves"] if row["sleeve_key"] == "us_equities")[
            "display_name"
        ] == "Current US sleeve name"
        assert latest_active["settings"]["target_retained_net_loss_usd"] == "9876.54"

        before_summary = client.get(f"/api/v1/optimizer/runs/{run_id}").json()
        before_recommendations = client.get(f"/api/v1/optimizer/runs/{run_id}/recommendations").json()
        assert before_summary["frozen_display_context"] == original_context

    app.state.engine.dispose()
    restarted = create_app(database_url=database_url, broker=FakeBroker(), seed_demo_data=False)
    try:
        with TestClient(restarted, base_url="http://localhost") as client:
            summary = client.get(f"/api/v1/optimizer/runs/{run_id}").json()
            recommendations = client.get(f"/api/v1/optimizer/runs/{run_id}/recommendations").json()
            assert summary == before_summary
            assert recommendations == before_recommendations
            context = summary["frozen_display_context"]
            assert context["source"] == "frozen_input_bundle"
            assert context["settings"]["target_retained_net_loss_usd"] == original_retained_loss_target
            sleeves = {row["sleeve_key"]: row for row in context["sleeves"]}
            assert sleeves["us_equities"]["display_name"] == "DEMO US Equities"
            assert sleeves["us_etf"]["enabled"] is True
            assert sleeves["us_etf"]["is_transition_destination"] is True

            exported = client.get(f"/api/v1/optimizer/runs/{run_id}/export?format=json").json()
            assert exported["metadata"]["frozen_display_context"] == context
            assert exported["run"]["frozen_display_context"] == context
            csv_response = client.get(f"/api/v1/optimizer/runs/{run_id}/export?format=csv")
            metadata_row = next(csv.DictReader(io.StringIO(csv_response.text)))
            assert json.loads(metadata_row["frozen_display_context_json"]) == context
    finally:
        restarted.state.engine.dispose()


def test_missing_frozen_policy_context_uses_only_exact_revision_or_reports_unavailable(
    demo_app: tuple[FastAPI, TestClient, FakeBroker, Path],
) -> None:
    app, client, _, _ = demo_app
    run = _create_run(client)
    run_id = run["run_id"]
    original_context = run["frozen_display_context"]
    original_name = next(row["display_name"] for row in original_context["sleeves"] if row["sleeve_key"] == "us_equities")

    with app.state.session_factory.begin() as session:
        persisted = session.get(OptimizerRun, run_id)
        assert persisted is not None
        persisted.frozen_input_bundle = {"legacy": True}
    with app.state.session_factory() as session:
        persisted = session.get(OptimizerRun, run_id)
        assert persisted is not None
        unavailable = demo_optimizer.run_summary(persisted)["frozen_display_context"]
    assert unavailable["available"] is False
    assert unavailable["source"] is None
    assert unavailable["sleeves"] is None

    active = client.get("/api/v1/policy").json()["active"]
    payload = {
        "source_revision_id": active["id"],
        "settings": active["settings"],
        "sleeves": active["sleeves"],
        "allowed_securities": active["allowed_securities"],
        "overrides": active["overrides"],
        "reassignments": {},
    }
    next(row for row in payload["sleeves"] if row["sleeve_key"] == "us_equities")["display_name"] = "New active label"
    draft = client.post("/api/v1/policy/drafts", json=payload)
    assert draft.status_code == 201, draft.text
    activated = client.post(f"/api/v1/policy/{draft.json()['id']}/activate")
    assert activated.status_code == 200, activated.text

    reopened = client.get(f"/api/v1/optimizer/runs/{run_id}").json()
    exact_revision_context = reopened["frozen_display_context"]
    assert exact_revision_context["available"] is True
    assert exact_revision_context["source"] == "policy_revision"
    assert exact_revision_context["policy_revision_id"] == run["policy_revision_id"]
    old_sleeve = next(row for row in exact_revision_context["sleeves"] if row["sleeve_key"] == "us_equities")
    assert old_sleeve["display_name"] == original_name
    assert old_sleeve["display_name"] != "New active label"



def test_real_optimizer_timeout_app_error_is_not_a_generic_http_500(
    demo_app: tuple[FastAPI, TestClient, FakeBroker, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    app, client, _, _ = demo_app

    async def timeout_run(*args: object, **kwargs: object) -> None:
        del args, kwargs
        from app.optimizer.runtime import WorkerTimeoutError

        raise WorkerTimeoutError("injected integration-test timeout")

    monkeypatch.setattr(app.state.optimizer_supervisor, "run", timeout_run)
    response = client.post("/api/v1/optimizer/runs", json={"mode": "real_optimizer"})

    assert response.status_code == 504, response.text
    body = response.json()
    assert body["code"] == "optimizer_timeout"
    run_id = body["details"]["run_id"]
    assert run_id

    with app.state.session_factory() as session:
        run = session.get(OptimizerRun, run_id)
        assert run is not None
        assert run.status == "TIMEOUT"
        assert run.frozen_input_bundle is not None
        assert session.query(RecommendationGroup).filter_by(run_id=run_id).count() == 0

    readback = client.get(f"/api/v1/optimizer/runs/{run_id}")
    assert readback.status_code == 200, readback.text
    assert readback.json()["status"] == "timeout"
    assert readback.json()["orders_count"] == 0

    recommendations = client.get(f"/api/v1/optimizer/runs/{run_id}/recommendations")
    assert recommendations.status_code == 200, recommendations.text
    assert recommendations.json()["groups"] == []
    assert recommendations.json()["consolidated_legs"] == []

    with app.state.session_factory() as session:
        run = session.get(OptimizerRun, run_id)
        assert run is not None
        assert session.query(RecommendationGroup).filter_by(run_id=run_id).count() == 0
        assert run.status == "TIMEOUT"
