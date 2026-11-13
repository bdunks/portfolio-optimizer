"""Persist configurable optimizer objective weights and estimated costs.

Revision ID: 0009_objective_policy_parameters
Revises: 0008_transition_destination
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_objective_policy_parameters"
down_revision = "0008_transition_destination"
branch_labels = None
depends_on = None

_FIELDS = (
    "objective_band_weight",
    "objective_allocation_weight",
    "objective_tax_weight",
    "objective_trading_cost_weight",
    "objective_turnover_weight",
    "objective_cleanup_weight",
    "estimated_spread_bps",
    "estimated_fee_per_order_usd",
)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "policy_revision" not in set(inspector.get_table_names()):
        return
    columns = {column["name"] for column in inspector.get_columns("policy_revision")}
    for name in _FIELDS:
        if name not in columns:
            op.add_column("policy_revision", sa.Column(name, sa.Text(), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "policy_revision" not in set(inspector.get_table_names()):
        return
    columns = {column["name"] for column in inspector.get_columns("policy_revision")}
    for name in reversed(_FIELDS):
        if name in columns:
            op.drop_column("policy_revision", name)
