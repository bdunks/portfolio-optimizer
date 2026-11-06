"""Move policy settings into lossless typed revision columns.

Revision ID: 0002_typed_policy_settings
Revises: 0001_normalized_foundation
"""
from __future__ import annotations

import json
import sqlite3

import sqlalchemy as sa
from alembic import op

revision = "0002_typed_policy_settings"
down_revision = "0001_normalized_foundation"
branch_labels = None
depends_on = None

_DECIMAL_SETTINGS = (
    "short_term_tax_rate",
    "long_term_tax_rate",
    "st_loss_carryforward_usd",
    "lt_loss_carryforward_usd",
    "ytd_realized_st_usd",
    "ytd_realized_lt_usd",
    "target_retained_net_loss_usd",
    "ordinary_income_deduction_limit_usd",
    "carryforward_loss_discount_factor",
    "gain_budget_usd",
    "max_incremental_tax_cost_usd",
    "st_gain_limit_usd",
    "lt_gain_limit_usd",
    "max_batch_turnover_pct",
    "min_buy_order_notional_usd",
    "cash_reserve_usd",
)
_SETTING_COLUMNS = (
    sa.Column("short_term_tax_rate", sa.Text(), nullable=True),
    sa.Column("long_term_tax_rate", sa.Text(), nullable=True),
    sa.Column("st_loss_carryforward_usd", sa.Text(), nullable=False, server_default=sa.text("'0'")),
    sa.Column("lt_loss_carryforward_usd", sa.Text(), nullable=False, server_default=sa.text("'0'")),
    sa.Column("ytd_realized_st_usd", sa.Text(), nullable=False, server_default=sa.text("'0'")),
    sa.Column("ytd_realized_lt_usd", sa.Text(), nullable=False, server_default=sa.text("'0'")),
    sa.Column("ytd_source", sa.String(80), nullable=True),
    sa.Column("ytd_as_of", sa.Date(), nullable=True),
    sa.Column("target_retained_net_loss_usd", sa.Text(), nullable=False, server_default=sa.text("'3000'")),
    sa.Column("ordinary_income_deduction_limit_usd", sa.Text(), nullable=False, server_default=sa.text("'3000'")),
    sa.Column("carryforward_loss_discount_factor", sa.Text(), nullable=False, server_default=sa.text("'0.50'")),
    sa.Column("gain_budget_usd", sa.Text(), nullable=True),
    sa.Column("max_incremental_tax_cost_usd", sa.Text(), nullable=True),
    sa.Column("st_gain_limit_usd", sa.Text(), nullable=True),
    sa.Column("lt_gain_limit_usd", sa.Text(), nullable=True),
    sa.Column("budget_period", sa.String(32), nullable=False, server_default=sa.text("'calendar_year'")),
    sa.Column("max_sell_tickers_per_batch", sa.Integer(), nullable=False, server_default=sa.text("10")),
    sa.Column("max_sell_lots_per_batch", sa.Integer(), nullable=False, server_default=sa.text("20")),
    sa.Column("max_total_orders_per_batch", sa.Integer(), nullable=False, server_default=sa.text("12")),
    sa.Column("max_batch_turnover_pct", sa.Text(), nullable=False, server_default=sa.text("'5.0'")),
    sa.Column("min_buy_order_notional_usd", sa.Text(), nullable=False, server_default=sa.text("'500.00'")),
    sa.Column("cash_reserve_usd", sa.Text(), nullable=False, server_default=sa.text("'0'")),
    sa.Column("prefer_etf_buys", sa.Boolean(), nullable=False, server_default=sa.text("1")),
    sa.Column("allow_gain_sales", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    sa.Column("permit_etf_harvest", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    sa.Column("permit_muni_exit", sa.Boolean(), nullable=False, server_default=sa.text("0")),
)


def upgrade() -> None:
    connection = op.get_bind()
    existing = {column["name"] for column in sa.inspect(connection).get_columns("policy_revision")}
    legacy_settings = "settings" in existing
    if legacy_settings and connection.dialect.name == "sqlite" and sqlite3.sqlite_version_info < (3, 35, 0):
        raise RuntimeError("SQLite 3.35 or newer is required to safely drop legacy policy settings")

    for column in _SETTING_COLUMNS:
        if column.name not in existing:
            op.add_column("policy_revision", column)

    if legacy_settings:
        rows = connection.execute(sa.text("SELECT id, settings FROM policy_revision")).mappings().all()
        for row in rows:
            settings = row["settings"]
            if isinstance(settings, str):
                settings = json.loads(settings)
            if not isinstance(settings, dict):
                continue
            names = [column.name for column in _SETTING_COLUMNS if column.name in settings]
            if not names:
                continue
            values = {name: settings[name] for name in names}
            for name in _DECIMAL_SETTINGS:
                if name in values and values[name] is not None:
                    values[name] = str(values[name])
            if values.get("ytd_as_of") is not None:
                values["ytd_as_of"] = str(values["ytd_as_of"])
            assignments = ", ".join(f'"{name}" = :{name}' for name in names)
            connection.execute(
                sa.text(f'UPDATE policy_revision SET {assignments} WHERE id = :id'),
                {**values, "id": row["id"]},
            )
        if connection.dialect.name == "sqlite":
            connection.exec_driver_sql("ALTER TABLE policy_revision DROP COLUMN settings")
        else:
            op.drop_column("policy_revision", "settings")


def downgrade() -> None:
    raise NotImplementedError("Typed policy settings are intentionally not downgraded to JSON")
