"""Add typed look-through exposure cache provenance and coverage.

Revision ID: 0013_exposure_cache
Revises: 0012_portfolio_lot_cache
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013_exposure_cache"
down_revision = "0012_portfolio_lot_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "exposure_cache_state",
        sa.Column("ticker", sa.String(length=32), primary_key=True),
        sa.Column("provider", sa.String(length=24)),
        sa.Column("as_of_date", sa.Date()),
        sa.Column("cached_at", sa.DateTime(timezone=True)),
        sa.Column("publication_revision", sa.Integer(), nullable=False),
        sa.Column("last_attempted_at", sa.DateTime(timezone=True)),
        sa.Column("last_attempt_provider", sa.String(length=24)),
        sa.Column("last_attempt_status", sa.String(length=16), nullable=False),
        sa.Column("last_error_code", sa.String(length=64)),
        sa.Column("last_error_summary", sa.String(length=500)),
        sa.CheckConstraint(
            "publication_revision >= 0", name="ck_exposure_cache_revision_nonnegative"
        ),
        sa.CheckConstraint(
            "last_attempt_status IN ('success', 'failure')",
            name="ck_exposure_cache_attempt_status",
        ),
        sa.CheckConstraint(
            "provider IS NULL OR provider IN ('vanguard', 'ishares', 'manual_csv')",
            name="ck_exposure_cache_provider",
        ),
        sa.CheckConstraint(
            "last_attempt_provider IS NULL OR last_attempt_provider IN ('vanguard', 'ishares', 'manual_csv')",
            name="ck_exposure_cache_attempt_provider",
        ),
    )
    op.create_table(
        "exposure_dimension_coverage",
        sa.Column("ticker", sa.String(length=32), primary_key=True),
        sa.Column("dimension", sa.String(length=32), primary_key=True),
        sa.Column("covered_weight", sa.Text(), nullable=False),
        sa.Column("complete", sa.Boolean(), nullable=False),
        sa.Column("observed_item_count", sa.Integer(), nullable=False),
        sa.Column("scope_item_count", sa.Integer(), nullable=False),
        sa.Column("provider_universe_verified", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["ticker"],
            ["exposure_cache_state.ticker"],
            name="fk_exposure_coverage_cache_state",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "observed_item_count >= 0 AND scope_item_count >= observed_item_count",
            name="ck_exposure_coverage_item_counts",
        ),
    )


def downgrade() -> None:
    op.drop_table("exposure_dimension_coverage")
    op.drop_table("exposure_cache_state")
