"""Persist the proposed trade date used to classify recommendation lots."""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "0007_optimizer_run_trade_date"
down_revision = "0006_repair_orders_count"
branch_labels = None
depends_on = None


def _bundle(value: object) -> dict[str, Any] | None:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return None
    return value if isinstance(value, dict) else None


def upgrade() -> None:
    if "optimizer_run" not in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    with op.batch_alter_table("optimizer_run") as batch:
        batch.add_column(sa.Column("proposed_trade_date", sa.Date(), nullable=True))

    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, frozen_input_bundle FROM optimizer_run")
    ).mappings()
    for row in rows:
        bundle = _bundle(row["frozen_input_bundle"])
        raw_date = bundle.get("proposed_trade_date") if bundle is not None else None
        try:
            if isinstance(raw_date, str):
                proposed_date = date.fromisoformat(raw_date)
            elif (
                bundle is not None
                and bundle.get("schema") == "demo-run-input-v1"
                and isinstance(bundle.get("account"), dict)
                and isinstance(bundle["account"].get("as_of"), str)
            ):
                proposed_date = datetime.fromisoformat(bundle["account"]["as_of"]).date()
            else:
                continue
        except (KeyError, TypeError, ValueError):
            continue
        connection.execute(
            sa.text("UPDATE optimizer_run SET proposed_trade_date = :date WHERE id = :run_id"),
            {"date": proposed_date, "run_id": row["id"]},
        )


def downgrade() -> None:
    connection = op.get_bind()
    if "optimizer_run" not in set(sa.inspect(connection).get_table_names()):
        return
    columns = {column["name"] for column in sa.inspect(connection).get_columns("optimizer_run")}
    if "proposed_trade_date" not in columns:
        return
    if connection.dialect.name == "sqlite":
        if sqlite3.sqlite_version_info < (3, 35, 0):
            raise RuntimeError("SQLite 3.35 or newer is required to safely drop the proposed trade date")
        connection.exec_driver_sql("ALTER TABLE optimizer_run DROP COLUMN proposed_trade_date")
    else:
        op.drop_column("optimizer_run", "proposed_trade_date")
