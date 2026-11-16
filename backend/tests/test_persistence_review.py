from __future__ import annotations

import importlib
import json
import os
import stat
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import Column, Integer, Table, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.broker.fake import FakeBroker
from app.db.migrate import upgrade_database
from app.db.models import (
    Account,
    Base,
    BrokerTransaction,
    CurrentPosition,
    CurrentQuote,
    CurrentTaxLot,
    OptimizerRun,
    PolicyRevision,
    PolicySleeve,
    RecommendationGroup,
    RecommendationGroupLeg,
    RecommendationLeg,
    RecommendationSelectedLot,
    Security,
    SecurityExposure,
    UTCDateTime,
)
from app.db.session import create_database_engine, make_session_factory
from app.main import create_app


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _upgrade_to(engine: Engine, revision: str) -> None:
    backend_root = _backend_root()
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "migrations"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, revision)


def _constraint_names(engine: Engine, table: str) -> set[str | None]:
    return {item["name"] for item in inspect(engine).get_check_constraints(table)}


def test_each_migration_revision_is_frozen_and_integrity_checks_are_present(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'revisions.sqlite3'}")
    try:
        _upgrade_to(engine, "0001_normalized_foundation")
        inspector = inspect(engine)
        assert "settings" in {column["name"] for column in inspector.get_columns("policy_revision")}
        assert "short_term_tax_rate" not in {
            column["name"] for column in inspector.get_columns("policy_revision")
        }
        assert "note" not in {
            column["name"] for column in inspector.get_columns("recommendation_group")
        }
        assert "selected" not in {
            column["name"] for column in inspector.get_columns("recommendation_selected_lot")
        }
        assert {
            "ck_lot_available_nonnegative",
            "ck_lot_shares_positive",
        } <= _constraint_names(engine, "current_tax_lot")
        assert "ck_quote_last_positive" in _constraint_names(engine, "current_quote")
        assert "ck_exposure_provider" in _constraint_names(engine, "security_exposure")
        assert "ck_selected_lot_term" in _constraint_names(engine, "recommendation_selected_lot")

        # An application model added after 0001 must not leak into that historical revision.
        latest_only = Table(
            "latest_only_model", Base.metadata, Column("id", Integer, primary_key=True)
        )
        revision_0001 = importlib.import_module("migrations.versions.0001_normalized_foundation")
        with (
            engine.begin() as connection,
            Operations.context(MigrationContext.configure(connection)),
        ):
            revision_0001.upgrade()
        assert not inspect(engine).has_table("latest_only_model")
        Base.metadata.remove(latest_only)

        _upgrade_to(engine, "0002_typed_policy_settings")
        inspector = inspect(engine)
        policy_columns = {column["name"] for column in inspector.get_columns("policy_revision")}
        assert "settings" not in policy_columns
        assert {"short_term_tax_rate", "target_retained_net_loss_usd"} <= policy_columns
        assert "note" not in {
            column["name"] for column in inspector.get_columns("recommendation_group")
        }

        _upgrade_to(engine, "0003_demo_recommendation_state")
        assert {"note", "rejected", "rejection_reason"} <= {
            column["name"] for column in inspect(engine).get_columns("recommendation_group")
        }
        assert "selected" in {
            column["name"] for column in inspect(engine).get_columns("recommendation_selected_lot")
        }

        upgrade_database(engine)
        assert "ck_quote_bid_positive" in _constraint_names(engine, "current_quote")
        assert "ck_quote_ask_positive" in _constraint_names(engine, "current_quote")
        assert "ck_quote_last_positive" in _constraint_names(engine, "current_quote")
        assert "ck_selected_lot_shares_positive" in _constraint_names(
            engine, "recommendation_selected_lot"
        )
    finally:
        if "latest_only" in locals() and latest_only in Base.metadata.tables.values():
            Base.metadata.remove(latest_only)
        engine.dispose()


def test_startup_migration_preserves_legacy_policy_dependents_and_foreign_keys(
    tmp_path: Path,
) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'legacy-populated.sqlite3'}")
    _upgrade_to(engine, "0001_normalized_foundation")
    legacy_settings = (
        '{"short_term_tax_rate":"0.35","target_retained_net_loss_usd":"'
        '1234567890123456789012345678.123456789","max_sell_lots_per_batch":7}'
    )
    created_at = "2026-11-05 20:00:00"
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO account (id, broker_account_id_key, display_name, account_type, cash_usd, "
                "settled_buying_power_usd, source, as_of) VALUES "
                "(1, 'acct-key', 'Test account', 'BROKERAGE', '10', '10', 'TEST', :created)"
            ),
            {"created": created_at},
        )
        connection.execute(
            text(
                "INSERT INTO security (id, ticker, asset_type, is_completion_etf, tradable) "
                "VALUES (1, 'ABC', 'EQUITY', 0, 1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO policy_revision (id, revision_number, status, created_at, settings) "
                "VALUES ('policy-1', 1, 'DRAFT', :created, :settings)"
            ),
            {"created": created_at, "settings": legacy_settings},
        )
        connection.execute(
            text(
                "INSERT INTO policy_sleeve (policy_revision_id, sleeve_key, display_name, sort_order, "
                "target_pct, drift_band_pp, is_direct_index_container, is_direct_index_sleeve, "
                "is_cash_sleeve, enabled) VALUES ('policy-1', 'equities', 'Equities', 0, '100', '5', 0, 0, 0, 1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO policy_allowed_security (policy_revision_id, sleeve_key, ticker, "
                "replacement_set_id, priority, enabled) VALUES ('policy-1', 'equities', 'ABC', 'default', 0, 1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO policy_security_override (policy_revision_id, security_id, sleeve_key) "
                "VALUES ('policy-1', 1, 'equities')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO optimizer_run (id, policy_revision_id, source_generation, as_of, status, "
                "batch_settings, metrics, warnings, frozen_input_bundle) "
                "VALUES ('run-1', 'policy-1', 1, :created, 'COMPLETE', '{}', '{}', '[]', '{}')"
            ),
            {"created": created_at},
        )

    # This is the protected engine path used during application startup.
    upgrade_database(engine)
    with engine.connect() as connection:
        assert connection.scalar(
            text(
                "SELECT is_transition_destination FROM policy_sleeve WHERE policy_revision_id = 'policy-1'"
            )
        ) in (0, False)
        assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
        for table in (
            "account",
            "security",
            "policy_revision",
            "policy_sleeve",
            "policy_allowed_security",
            "policy_security_override",
            "optimizer_run",
        ):
            assert connection.scalar(text(f"SELECT count(*) FROM {table}")) == 1
        typed = connection.execute(
            text(
                "SELECT short_term_tax_rate, target_retained_net_loss_usd, max_sell_lots_per_batch "
                "FROM policy_revision WHERE id = 'policy-1'"
            )
        ).one()
        assert typed == ("0.35", "1234567890123456789012345678.123456789", 7)
    engine.dispose()


def test_integrity_migration_repairs_existing_head_tables_without_losing_rows(
    tmp_path: Path,
) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'old-head.sqlite3'}")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"
        )
        connection.exec_driver_sql(
            "INSERT INTO alembic_version VALUES ('0003_demo_recommendation_state')"
        )
        connection.exec_driver_sql("CREATE TABLE account (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("CREATE TABLE security (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("CREATE TABLE recommendation_leg (id VARCHAR(36) PRIMARY KEY)")
        connection.exec_driver_sql(
            "CREATE TABLE current_tax_lot (id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL, "
            "broker_lot_id VARCHAR(128) NOT NULL, security_id INTEGER NOT NULL, acquired_date DATE NOT NULL, "
            "shares TEXT NOT NULL, available_shares TEXT NOT NULL, adjusted_unit_basis_usd TEXT NOT NULL, "
            "broker_wash_adjustment_usd TEXT, source VARCHAR(40) NOT NULL, as_of DATETIME NOT NULL, "
            "quality_flags JSON NOT NULL, fractional_cleanup_unsupported BOOLEAN NOT NULL, "
            "sync_generation INTEGER NOT NULL, FOREIGN KEY(account_id) REFERENCES account(id) ON DELETE CASCADE, "
            "FOREIGN KEY(security_id) REFERENCES security(id))"
        )
        connection.exec_driver_sql(
            "CREATE TABLE current_quote (id INTEGER PRIMARY KEY, security_id INTEGER UNIQUE, bid_usd TEXT, "
            "ask_usd TEXT, last_usd TEXT, source VARCHAR(40) NOT NULL, as_of DATETIME NOT NULL, "
            "quality VARCHAR(32) NOT NULL, sync_generation INTEGER NOT NULL, "
            "FOREIGN KEY(security_id) REFERENCES security(id) ON DELETE CASCADE)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE security_exposure (id INTEGER PRIMARY KEY, security_id INTEGER NOT NULL, "
            "dimension VARCHAR(32) NOT NULL, exposure_key VARCHAR(128) NOT NULL, weight TEXT NOT NULL, "
            "provider VARCHAR(24) NOT NULL, as_of_date DATE NOT NULL, "
            "FOREIGN KEY(security_id) REFERENCES security(id) ON DELETE CASCADE)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE recommendation_selected_lot (id INTEGER PRIMARY KEY, leg_id VARCHAR(36) NOT NULL, "
            "broker_lot_id VARCHAR(128) NOT NULL, shares TEXT NOT NULL, acquired_date DATE NOT NULL, "
            "adjusted_basis_usd TEXT NOT NULL, st_lt_term VARCHAR(2) NOT NULL, realized_pl_usd TEXT NOT NULL, "
            "selected BOOLEAN NOT NULL, FOREIGN KEY(leg_id) REFERENCES recommendation_leg(id) ON DELETE CASCADE)"
        )
        connection.exec_driver_sql("INSERT INTO account VALUES (1)")
        connection.exec_driver_sql("INSERT INTO security VALUES (1)")
        connection.exec_driver_sql("INSERT INTO recommendation_leg VALUES ('leg')")
        connection.exec_driver_sql(
            "INSERT INTO current_tax_lot VALUES (1, 1, 'lot', 1, '2025-01-01', '2', '1', '10', NULL, "
            "'TEST', '2026-11-05 20:00:00', '[]', 0, 1)"
        )
        connection.exec_driver_sql(
            "INSERT INTO current_quote VALUES (1, 1, '10', '11', '10.5', 'TEST', "
            "'2026-11-05 20:00:00', 'good', 1)"
        )
        connection.exec_driver_sql(
            "INSERT INTO security_exposure VALUES (1, 1, 'sector', 'technology', '1', 'vanguard', '2026-11-05')"
        )
        connection.exec_driver_sql(
            "INSERT INTO recommendation_selected_lot VALUES "
            "(1, 'leg', 'lot', '1', '2025-01-01', '10', 'ST', '1', 1)"
        )

    upgrade_database(engine)
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
        assert (
            connection.scalar(text("SELECT available_shares FROM current_tax_lot WHERE id = 1"))
            == "1"
        )
        assert connection.scalar(text("SELECT last_usd FROM current_quote WHERE id = 1")) == "10.5"
        assert (
            connection.scalar(text("SELECT provider FROM security_exposure WHERE id = 1"))
            == "vanguard"
        )
        assert (
            connection.scalar(
                text("SELECT st_lt_term FROM recommendation_selected_lot WHERE id = 1")
            )
            == "ST"
        )
        assert "ck_lot_available_nonnegative" in _constraint_names(engine, "current_tax_lot")
        assert "ck_quote_last_positive" in _constraint_names(engine, "current_quote")
        assert "ck_exposure_provider" in _constraint_names(engine, "security_exposure")
        assert "ck_selected_lot_term" in _constraint_names(engine, "recommendation_selected_lot")
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(text("UPDATE current_tax_lot SET available_shares = '-1' WHERE id = 1"))
    engine.dispose()


@pytest.mark.parametrize(
    ("legacy_details", "expected_details"),
    [
        (
            {"depends_on_leg_id": "sell-a", "min_buy_order_notional_usd": "500"},
            {"min_buy_order_notional_usd": "500"},
        ),
        ([], {}),
        (
            [["depends_on_leg_id", "sell-a"], ["legacy_note", "preserved"]],
            {"legacy_note": "preserved"},
        ),
        ("invalid", None),
    ],
)
def test_consolidation_migration_preserves_legacy_subset_notes_and_frozen_inputs(
    tmp_path: Path,
    legacy_details: object,
    expected_details: dict[str, object] | None,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'legacy-consolidated.sqlite3'}"
    engine = create_database_engine(database_url)
    _upgrade_to(engine, "0004_database_integrity_checks")
    factory = make_session_factory(engine)
    timestamp = datetime(2026, 11, 5, 20, tzinfo=UTC)
    frozen = {
        "schema": "demo-run-input-v1",
        "account": {"as_of": timestamp.isoformat()},
        "original_bundle": "unchanged",
        "lot_ids": ["lot-a1", "lot-a2", "lot-b"],
    }
    with factory.begin() as session:
        session.add(
            Account(
                id=1,
                broker_account_id_key="legacy-account",
                display_name="Legacy test account",
                account_type="BROKERAGE",
                cash_usd=Decimal(0),
                settled_buying_power_usd=Decimal(0),
                source="TEST",
                as_of=timestamp,
            )
        )
        sell_security = Security(ticker="ABC", asset_type="EQUITY")
        buy_security = Security(ticker="ETF", asset_type="ETF")
        sell_security_b = Security(ticker="XYZ", asset_type="EQUITY")
        session.add_all([sell_security, sell_security_b, buy_security])
        session.flush()
        policy_id = "legacy-policy"
        session.execute(
            text(
                "INSERT INTO policy_revision (id, revision_number, status, created_at) VALUES (:id, 1, 'ACTIVE', :created_at)"
            ),
            {"id": policy_id, "created_at": timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")},
        )
        run_id = "legacy-run"
        session.execute(
            text(
                "INSERT INTO optimizer_run "
                "(id, policy_revision_id, source_generation, as_of, solver_version, status, "
                "batch_settings, metrics, warnings, input_fingerprint, frozen_input_bundle) "
                "VALUES (:id, :policy, :generation, :as_of, :solver, :status, :batch, :metrics, "
                ":warnings, :fingerprint, :bundle)"
            ),
            {
                "id": run_id,
                "policy": policy_id,
                "generation": 7,
                "as_of": timestamp.strftime("%Y-%m-%d %H:%M:%S.%f"),
                "solver": "DEMO",
                "status": "COMPLETE",
                "batch": json.dumps({"max_total_orders_per_batch": 3}),
                "metrics": json.dumps({"orders_count": 4, "legacy_metric": "preserve me"}),
                "warnings": json.dumps(["legacy"]),
                "fingerprint": "original-fingerprint",
                "bundle": json.dumps(frozen),
            },
        )
        session.execute(
            text(
                "INSERT INTO optimizer_run "
                "(id, policy_revision_id, source_generation, as_of, status, batch_settings, "
                "metrics, warnings, frozen_input_bundle) "
                "VALUES ('legacy-no-date', :policy, 7, :as_of, 'COMPLETE', '{}', '{}', '[]', :bundle)"
            ),
            {
                "policy": policy_id,
                "as_of": timestamp.strftime("%Y-%m-%d %H:%M:%S.%f"),
                "bundle": json.dumps({"legacy": True}),
            },
        )
        session.execute(
            text(
                "INSERT INTO optimizer_run "
                "(id, policy_revision_id, source_generation, as_of, status, batch_settings, "
                "metrics, warnings, frozen_input_bundle) "
                "VALUES ('legacy-explicit-date', :policy, 7, :as_of, 'COMPLETE', '{}', '{}', '[]', :bundle)"
            ),
            {
                "policy": policy_id,
                "as_of": timestamp.strftime("%Y-%m-%d %H:%M:%S.%f"),
                "bundle": json.dumps({"proposed_trade_date": "2026-11-07"}),
            },
        )
        legacy_impact: dict[str, object] = {
            "demo": True,
            "wash_status": "not_validated_demo",
            "selected_sell_lots_count": 1,
            "sell_proceeds_usd": "200",
            "realized_st_usd": "0",
            "realized_lt_usd": "-20",
            "replacement_buy_shares": "3",
            "replacement_buy_cost_usd": "600",
            "cash_after_usd": "0",
            "portfolio_effects": {
                "allocation": {"current": None, "proposed": None, "target": None},
                "us_transition": None,
            },
            "risk_tracking_score": None,
        }
        group_a = RecommendationGroup(
            id="group-a",
            run_id=run_id,
            rank=1,
            group_type="demo_loss_harvest",
            rationale="A",
            sleeve_key="us",
            impact=legacy_impact,
            selected=True,
            rejected=False,
            note="preserve note A",
        )
        group_b = RecommendationGroup(
            id="group-b",
            run_id=run_id,
            rank=2,
            group_type="demo_loss_harvest",
            rationale="B",
            sleeve_key="us",
            impact=legacy_impact,
            selected=False,
            rejected=True,
            note="preserve note B",
            rejection_reason="old rejection",
        )
        session.add_all([group_a, group_b])
        session.flush()
        sell_a = RecommendationLeg(
            id="sell-a",
            group_id=group_a.id,
            account_id=1,
            security_id=sell_security.id,
            side="SELL",
            shares=Decimal(2),
            estimated_unit_price_usd=Decimal(100),
            net_st_realized_usd=Decimal(0),
            net_lt_realized_usd=Decimal(-20),
            sequence=1,
            details={"sleeve_key": "us"},
        )
        sell_b = RecommendationLeg(
            id="sell-b",
            group_id=group_b.id,
            account_id=1,
            security_id=sell_security_b.id,
            side="SELL",
            shares=Decimal(1),
            estimated_unit_price_usd=Decimal(100),
            net_st_realized_usd=Decimal(0),
            net_lt_realized_usd=Decimal(-10),
            sequence=1,
            details={"sleeve_key": "us"},
        )
        zero_sell = RecommendationLeg(
            id="sell-zero",
            group_id=group_b.id,
            account_id=1,
            security_id=sell_security_b.id,
            side="SELL",
            shares=Decimal(0),
            estimated_unit_price_usd=Decimal(100),
            net_st_realized_usd=Decimal(0),
            net_lt_realized_usd=Decimal(0),
            sequence=3,
            details={"sleeve_key": "us"},
        )
        buy_a = RecommendationLeg(
            id="buy-a",
            group_id=group_a.id,
            account_id=1,
            security_id=buy_security.id,
            side="BUY",
            shares=Decimal(1),
            estimated_unit_price_usd=Decimal(200),
            net_st_realized_usd=Decimal(0),
            net_lt_realized_usd=Decimal(0),
            sequence=2,
            details={"depends_on_leg_id": "sell-a", "min_buy_order_notional_usd": "500"},
        )
        buy_b = RecommendationLeg(
            id="buy-b",
            group_id=group_b.id,
            account_id=1,
            security_id=buy_security.id,
            side="BUY",
            shares=Decimal(2),
            estimated_unit_price_usd=Decimal(200),
            net_st_realized_usd=Decimal(0),
            net_lt_realized_usd=Decimal(0),
            sequence=2,
            details={"depends_on_leg_id": "sell-b", "min_buy_order_notional_usd": "500"},
        )
        session.add_all([sell_a, sell_b, zero_sell, buy_a, buy_b])
        session.flush()
        session.execute(
            text("UPDATE recommendation_leg SET details = :details WHERE id = 'buy-a'"),
            {"details": json.dumps(legacy_details)},
        )
        session.add_all(
            [
                RecommendationSelectedLot(
                    leg_id="sell-a",
                    broker_lot_id="lot-a1",
                    shares=Decimal(1),
                    acquired_date=date(2025, 1, 1),
                    adjusted_basis_usd=Decimal(110),
                    st_lt_term="LT",
                    realized_pl_usd=Decimal(-10),
                    selected=True,
                ),
                RecommendationSelectedLot(
                    leg_id="sell-a",
                    broker_lot_id="lot-a2",
                    shares=Decimal(1),
                    acquired_date=date(2025, 1, 2),
                    adjusted_basis_usd=Decimal(110),
                    st_lt_term="LT",
                    realized_pl_usd=Decimal(-10),
                    selected=False,
                ),
                RecommendationSelectedLot(
                    leg_id="sell-b",
                    broker_lot_id="lot-b",
                    shares=Decimal(1),
                    acquired_date=date(2025, 1, 3),
                    adjusted_basis_usd=Decimal(110),
                    st_lt_term="LT",
                    realized_pl_usd=Decimal(-10),
                    selected=True,
                ),
            ]
        )

    if expected_details is None:
        with pytest.raises(ValueError, match="dictionary update sequence"):
            _upgrade_to(engine, "0005_consolidated_recommendation_legs")
        assert "recommendation_group_leg" not in inspect(engine).get_table_names()
        engine.dispose()
        return
    _upgrade_to(engine, "0005_consolidated_recommendation_legs")
    with factory() as session:
        buys = session.query(RecommendationLeg).filter_by(side="BUY").all()
        assert len(buys) == 1
        assert buys[0].id == "buy-a"
        assert buys[0].shares == Decimal(3)
        assert buys[0].details == {
            **expected_details,
            "depends_on_leg_ids": ["sell-a", "sell-b"],
        }
        assert session.query(RecommendationGroupLeg).filter_by(leg_id="buy-a").count() == 2
        assert session.get(RecommendationLeg, "buy-b") is None
        sell_a = session.get(RecommendationLeg, "sell-a")
        assert sell_a is not None
        assert sell_a.shares == Decimal(2)
        sell_b = session.get(RecommendationLeg, "sell-b")
        assert sell_b is not None
        assert sell_b.shares == Decimal(1)
        zero_sell = session.get(RecommendationLeg, "sell-zero")
        assert zero_sell is not None
        assert zero_sell.shares == Decimal(0)
        run = (
            session.execute(
                text(
                    "SELECT metrics, batch_settings, frozen_input_bundle, input_fingerprint, warnings "
                    "FROM optimizer_run WHERE id = 'legacy-run'"
                )
            )
            .mappings()
            .one()
        )
        assert json.loads(run["metrics"]) == {"orders_count": 3, "legacy_metric": "preserve me"}
        assert json.loads(run["batch_settings"]) == {"max_total_orders_per_batch": 3}
        assert json.loads(run["frozen_input_bundle"]) == frozen
        assert run["input_fingerprint"] == "original-fingerprint"
        assert json.loads(run["warnings"]) == ["legacy"]
        group_a = session.get(RecommendationGroup, "group-a")
        assert group_a is not None
        assert group_a.note == "preserve note A"
        assert group_a.selected is True
        group_b = session.get(RecommendationGroup, "group-b")
        assert group_b is not None
        assert group_b.note == "preserve note B"
        assert group_b.selected is False
        assert group_b.rejected is True
        assert group_b.rejection_reason == "old rejection"
        assert (
            session.query(RecommendationSelectedLot)
            .filter_by(broker_lot_id="lot-a1")
            .one()
            .selected
            is True
        )
        assert (
            session.query(RecommendationSelectedLot)
            .filter_by(broker_lot_id="lot-a2")
            .one()
            .selected
            is False
        )
        assert {
            lot.broker_lot_id: lot.shares for lot in session.query(RecommendationSelectedLot).all()
        } == {"lot-a1": Decimal(1), "lot-a2": Decimal(1), "lot-b": Decimal(1)}

    # Simulate an already-upgraded 0005 database with a stale count and a deselected canonical owner.
    with factory.begin() as session:
        metrics = json.loads(
            session.scalar(text("SELECT metrics FROM optimizer_run WHERE id = 'legacy-run'"))
        )
        metrics["orders_count"] = 4
        session.execute(
            text("UPDATE optimizer_run SET metrics = :metrics WHERE id = 'legacy-run'"),
            {"metrics": json.dumps(metrics)},
        )
        group_a = session.get(RecommendationGroup, "group-a")
        assert group_a is not None
        group_a.selected = False
        group_b = session.get(RecommendationGroup, "group-b")
        assert group_b is not None
        group_b.selected = True
        group_b.rejected = False
    upgrade_database(engine)
    with factory.begin() as session:
        run = session.get(OptimizerRun, "legacy-run")
        assert run is not None
        policy = session.get(PolicyRevision, "legacy-policy")
        assert policy is not None
        assert policy.objective_band_weight is None
        assert policy.objective_cleanup_weight is None
        assert policy.estimated_spread_bps is None
        assert policy.estimated_fee_per_order_usd is None
        assert run.proposed_trade_date == date(2026, 11, 5)
        missing_date_run = session.get(OptimizerRun, "legacy-no-date")
        assert missing_date_run is not None
        assert missing_date_run.proposed_trade_date is None
        explicit_date_run = session.get(OptimizerRun, "legacy-explicit-date")
        assert explicit_date_run is not None
        assert explicit_date_run.proposed_trade_date == date(2026, 11, 7)
        assert run.metrics == {"orders_count": 3, "legacy_metric": "preserve me"}
        # Restore original subset state after exercising the forward repair's shared-BUY case.
        group_a = session.get(RecommendationGroup, "group-a")
        assert group_a is not None
        group_a.selected = True
        group_b = session.get(RecommendationGroup, "group-b")
        assert group_b is not None
        group_b.selected = False
        group_b.rejected = True
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
    engine.dispose()

    app = create_app(database_url=database_url, broker=FakeBroker(), seed_demo_data=False)
    with TestClient(app, base_url="http://localhost") as client:
        summary = client.get("/api/v1/optimizer/runs/legacy-run")
        assert summary.status_code == 200, summary.text
        assert summary.json()["orders_count"] == 3
        assert summary.json()["proposed_trade_date"] == "2026-11-05"
        missing_date = client.get("/api/v1/optimizer/runs/legacy-no-date")
        assert missing_date.status_code == 200, missing_date.text
        assert missing_date.json()["proposed_trade_date"] is None
        explicit_date = client.get("/api/v1/optimizer/runs/legacy-explicit-date")
        assert explicit_date.status_code == 200
        assert explicit_date.json()["proposed_trade_date"] == "2026-11-07"
        recommendations = client.get("/api/v1/optimizer/runs/legacy-run/recommendations")
        assert recommendations.status_code == 200, recommendations.text
        assert recommendations.json()["orders_count"] == 3
        exported = client.get("/api/v1/optimizer/runs/legacy-run/export?format=json")
        assert exported.status_code == 200, exported.text
        assert exported.json()["run"]["orders_count"] == 3


def test_alembic_cli_uses_private_protected_engine_and_environment_url(tmp_path: Path) -> None:
    database_path = tmp_path / "new-private-dir" / "nested" / "cli.sqlite3"
    database_url = f"sqlite:///{database_path}"
    env = os.environ.copy()
    env["PORTFOLIO_DATABASE_URL"] = database_url
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=_backend_root(),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert stat.S_IMODE(database_path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(database_path.stat().st_mode) == 0o600

    engine = create_database_engine(database_url)
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("PRAGMA foreign_keys")) == 1
            assert connection.scalar(text("PRAGMA journal_mode")).lower() == "wal"
            assert connection.scalar(text("PRAGMA busy_timeout")) == 5000
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                "0012_portfolio_lot_cache"
            )
    finally:
        engine.dispose()


def test_orm_persistence_rejects_invalid_decimal_and_enum_values(tmp_path: Path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'checks.sqlite3'}")
    upgrade_database(engine)
    factory: sessionmaker[Session] = make_session_factory(engine)
    timestamp = datetime(2026, 11, 5, 20, tzinfo=UTC)
    with factory.begin() as session:
        session.add(
            Account(
                id=1,
                broker_account_id_key="acct",
                display_name="Test",
                account_type="BROKERAGE",
                cash_usd=Decimal(0),
                settled_buying_power_usd=Decimal(0),
                source="TEST",
                as_of=timestamp,
            )
        )
        security = Security(ticker="ABC", asset_type="EQUITY")
        revision = PolicyRevision(
            id="policy", revision_number=1, status="DRAFT", created_at=timestamp
        )
        session.add_all([security, revision])
        session.flush()
        sleeve = PolicySleeve(
            policy_revision_id=revision.id,
            sleeve_key="equities",
            display_name="Equities",
            sort_order=0,
            target_pct=Decimal(100),
            drift_band_pp=Decimal(5),
        )
        session.add(sleeve)
        run = OptimizerRun(
            id="run",
            policy_revision_id=revision.id,
            source_generation=1,
            as_of=timestamp,
            status="COMPLETE",
        )
        session.add(run)
        group = RecommendationGroup(
            id="group",
            run_id=run.id,
            rank=1,
            group_type="SELL",
            rationale="test",
        )
        session.add(group)
        leg = RecommendationLeg(
            id="leg",
            group_id=group.id,
            account_id=1,
            security_id=security.id,
            side="SELL",
            shares=Decimal(1),
            estimated_unit_price_usd=Decimal(10),
            net_st_realized_usd=Decimal(0),
            net_lt_realized_usd=Decimal(0),
            sequence=1,
        )
        session.add(leg)

    def assert_rejected(record: object) -> None:
        with pytest.raises(IntegrityError), factory.begin() as session:
            session.add(record)

    lot_values = {
        "account_id": 1,
        "broker_lot_id": "lot",
        "security_id": 1,
        "acquired_date": date(2025, 1, 1),
        "shares": Decimal(1),
        "available_shares": Decimal(-1),
        "adjusted_unit_basis_usd": Decimal(1),
        "source": "TEST",
        "as_of": timestamp,
        "sync_generation": 1,
    }
    assert_rejected(CurrentTaxLot(**lot_values))
    assert_rejected(
        CurrentTaxLot(
            **{
                **lot_values,
                "broker_lot_id": "zero-lot",
                "shares": Decimal(0),
                "available_shares": Decimal(0),
            }
        )
    )

    for field in ("bid_usd", "ask_usd", "last_usd"):
        assert_rejected(
            CurrentQuote(
                security_id=1,
                source="TEST",
                as_of=timestamp,
                **{field: Decimal(0)},
            )
        )
    assert_rejected(
        SecurityExposure(
            security_id=1,
            dimension="sector",
            exposure_key="technology",
            weight=Decimal(1),
            provider="unknown",
            as_of_date=date(2026, 11, 5),
        )
    )
    selected_lot = {
        "leg_id": "leg",
        "broker_lot_id": "selected-lot",
        "shares": Decimal(1),
        "acquired_date": date(2025, 1, 1),
        "adjusted_basis_usd": Decimal(1),
        "st_lt_term": "XX",
        "realized_pl_usd": Decimal(0),
    }
    assert_rejected(RecommendationSelectedLot(**selected_lot))
    assert_rejected(
        RecommendationSelectedLot(
            **{
                **selected_lot,
                "broker_lot_id": "zero-selected-lot",
                "shares": Decimal(0),
                "st_lt_term": "ST",
            }
        )
    )
    engine.dispose()


def test_offset_timestamps_survive_sync_restart_and_frozen_run(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'offset.sqlite3'}"
    expected = datetime(2026, 11, 5, 20, tzinfo=UTC)
    supplied = datetime(2026, 11, 5, 15, tzinfo=timezone(timedelta(hours=-5)))
    snapshot = FakeBroker.demo_snapshot()
    snapshot = snapshot.model_copy(
        update={
            "as_of": supplied,
            "lots": [lot.model_copy(update={"as_of": supplied}) for lot in snapshot.lots],
            "quotes": [quote.model_copy(update={"as_of": supplied}) for quote in snapshot.quotes],
            "transactions": [
                txn.model_copy(update={"transaction_time": supplied})
                for txn in snapshot.transactions
            ],
        }
    )
    broker = FakeBroker(snapshot)
    app = create_app(database_url=database_url, broker=broker, seed_demo_data=True)
    with TestClient(app, base_url="http://localhost") as client:
        created = client.post("/api/v1/optimizer/runs", json={})
        assert created.status_code == 201, created.text
        run_id = created.json()["run_id"]
        detail = client.get(f"/api/v1/optimizer/runs/{run_id}").json()
        assert isinstance(detail["as_of"], str)
        assert datetime.fromisoformat(detail["as_of"]) == expected
        with app.state.session_factory() as session:
            assert session.get(Account, 1).as_of == expected
            assert all(
                position.as_of == expected for position in session.query(CurrentPosition).all()
            )
            assert session.query(CurrentTaxLot).first().as_of == expected
            assert session.query(CurrentQuote).first().as_of == expected
            assert session.query(BrokerTransaction).one().transaction_time == expected
            persisted_run = session.get(OptimizerRun, run_id)
            assert persisted_run is not None
            assert persisted_run.as_of == expected
            assert persisted_run.frozen_input_bundle["account"]["as_of"] == expected.isoformat()
            assert session.query(CurrentTaxLot).first().acquired_date == date(2025, 1, 10)

    restarted = create_app(database_url=database_url, broker=broker, seed_demo_data=True)
    with TestClient(restarted, base_url="http://localhost") as client:
        detail = client.get(f"/api/v1/optimizer/runs/{run_id}").json()
        assert datetime.fromisoformat(detail["as_of"]) == expected
        with restarted.state.session_factory() as session:
            assert session.get(Account, 1).as_of == expected
            assert (
                session.get(OptimizerRun, run_id).frozen_input_bundle["account"]["as_of"]
                == expected.isoformat()
            )
    bound_timestamp = UTCDateTime().process_bind_param(datetime(2026, 1, 1), None)
    assert bound_timestamp is not None
    assert bound_timestamp.tzinfo is UTC
