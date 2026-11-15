"""Persist demo sell-lot selection and recommendation annotations.

Revision ID: 0003_demo_recommendation_state
Revises: 0002_typed_policy_settings
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_demo_recommendation_state"
down_revision = "0002_typed_policy_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = set(inspector.get_table_names())
    if "recommendation_group" in tables:
        group_columns = {column["name"] for column in inspector.get_columns("recommendation_group")}
        for column in (
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("rejected", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("rejection_reason", sa.Text(), nullable=True),
        ):
            if column.name not in group_columns:
                op.add_column("recommendation_group", column)
    if "recommendation_selected_lot" in tables:
        lot_columns = {
            column["name"] for column in inspector.get_columns("recommendation_selected_lot")
        }
        if "selected" not in lot_columns:
            op.add_column(
                "recommendation_selected_lot",
                sa.Column("selected", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            )


def downgrade() -> None:
    raise NotImplementedError("Demo recommendation user state is intentionally not downgraded")
