"""Store revision-owned sector drift-band policy rows.

Revision ID: 0011_sector_bands
Revises: 0010_realized_transaction_pl
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_sector_bands"
down_revision = "0010_realized_transaction_pl"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "policy_sector_band",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("policy_revision_id", sa.String(length=36), sa.ForeignKey("policy_revision.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sector_key", sa.String(length=128), nullable=False),
        sa.Column("target_weight_pct", sa.Text(), nullable=False),
        sa.Column("band_pct", sa.Text(), nullable=False),
        sa.CheckConstraint("target_weight_pct NOT LIKE '-%'", name="ck_sector_band_target_nonnegative"),
        sa.CheckConstraint("band_pct NOT LIKE '-%'", name="ck_sector_band_band_nonnegative"),
        sa.UniqueConstraint("policy_revision_id", "sector_key", name="uq_policy_sector_band_key"),
    )
    op.create_index("ix_policy_sector_band_revision", "policy_sector_band", ["policy_revision_id", "sector_key"])


def downgrade() -> None:
    op.drop_index("ix_policy_sector_band_revision", table_name="policy_sector_band")
    op.drop_table("policy_sector_band")
