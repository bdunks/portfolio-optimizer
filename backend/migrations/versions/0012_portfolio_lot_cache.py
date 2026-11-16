"""Persist explicit broker portfolio and exact-lot cache provenance.

Revision ID: 0012_portfolio_lot_cache
Revises: 0011_sector_bands
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_portfolio_lot_cache"
down_revision = "0011_sector_bands"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing_tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "current_position" in existing_tables:
        op.add_column("current_position", sa.Column("broker_position_id", sa.String(length=128)))
        op.add_column("current_position", sa.Column("broker_product_id", sa.Text()))
    if "current_tax_lot" in existing_tables:
        op.add_column("current_tax_lot", sa.Column("broker_total_cost_usd", sa.Text()))
        op.add_column("current_tax_lot", sa.Column("broker_total_cost_source_usd", sa.Text()))
        op.add_column("current_tax_lot", sa.Column("reserved_shares", sa.Text()))
        op.add_column("current_tax_lot", sa.Column("broker_acquired_date_source", sa.Text()))
    op.create_table(
        "lot_cache_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("source_generation", sa.Integer()),
        sa.Column("source_as_of", sa.DateTime(timezone=True)),
        sa.Column("cached_at", sa.DateTime(timezone=True)),
        sa.Column("last_attempted_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.String(length=64)),
        sa.Column("last_error_summary", sa.String(length=500)),
        sa.CheckConstraint("id = 1", name="ck_lot_cache_state_singleton"),
    )


def downgrade() -> None:
    existing_tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "lot_cache_state" in existing_tables:
        op.drop_table("lot_cache_state")
    if "current_tax_lot" in existing_tables:
        with op.batch_alter_table("current_tax_lot") as batch:
            batch.drop_column("broker_acquired_date_source")
            batch.drop_column("reserved_shares")
            batch.drop_column("broker_total_cost_source_usd")
            batch.drop_column("broker_total_cost_usd")
    if "current_position" in existing_tables:
        with op.batch_alter_table("current_position") as batch:
            batch.drop_column("broker_product_id")
            batch.drop_column("broker_position_id")
