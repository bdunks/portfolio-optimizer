"""Add the explicit policy transition-destination sleeve role.

Revision ID: 0008_transition_destination
Revises: 0007_optimizer_run_trade_date
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_transition_destination"
down_revision = "0007_optimizer_run_trade_date"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "policy_sleeve" not in set(inspector.get_table_names()):
        return
    columns = {column["name"] for column in inspector.get_columns("policy_sleeve")}
    if "is_transition_destination" not in columns:
        op.add_column(
            "policy_sleeve",
            sa.Column(
                "is_transition_destination", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "policy_sleeve" not in set(inspector.get_table_names()):
        return
    columns = {column["name"] for column in inspector.get_columns("policy_sleeve")}
    if "is_transition_destination" in columns:
        op.drop_column("policy_sleeve", "is_transition_destination")
