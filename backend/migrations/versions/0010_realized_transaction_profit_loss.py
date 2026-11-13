"""Add explicit realized profit/loss attribution to broker transactions.

Revision ID: 0010_realized_transaction_pl
Revises: 0009_objective_policy_parameters
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_realized_transaction_pl"
down_revision = "0009_objective_policy_parameters"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "broker_transaction" not in set(inspector.get_table_names()):
        return
    columns = {column["name"] for column in inspector.get_columns("broker_transaction")}
    if "realized_pl_usd" not in columns:
        op.add_column("broker_transaction", sa.Column("realized_pl_usd", sa.Text(), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "broker_transaction" not in set(inspector.get_table_names()):
        return
    columns = {column["name"] for column in inspector.get_columns("broker_transaction")}
    if "realized_pl_usd" in columns:
        op.drop_column("broker_transaction", "realized_pl_usd")
