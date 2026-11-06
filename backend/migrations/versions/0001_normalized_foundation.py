"""Create the frozen normalized single-account Phase 1A schema.

Revision ID: 0001_normalized_foundation
Revises:
Create Date: 2026-11-06
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_normalized_foundation"
down_revision = None
branch_labels = None
depends_on = None


def _foundation_metadata() -> sa.MetaData:
    """Build the schema as it existed at revision 0001, independent of app models."""
    metadata = sa.MetaData()

    sa.Table(
        "account",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("broker_account_id_key", sa.String(128), nullable=False, unique=True),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("account_type", sa.String(40), nullable=False),
        sa.Column("tax_treatment", sa.String(40)),
        sa.Column("cash_usd", sa.Text(), nullable=False),
        sa.Column("settled_buying_power_usd", sa.Text(), nullable=False),
        sa.Column("source", sa.String(24), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_account_singleton"),
    )
    sa.Table(
        "security",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticker", sa.String(32), nullable=False, unique=True),
        sa.Column("cusip", sa.String(16), unique=True),
        sa.Column("isin", sa.String(16), unique=True),
        sa.Column("asset_type", sa.String(12), nullable=False),
        sa.Column("is_completion_etf", sa.Boolean(), nullable=False),
        sa.Column("vanguard_fund_id", sa.String(40)),
        sa.Column("ishares_holdings_url", sa.Text()),
        sa.Column("tradable", sa.Boolean(), nullable=False),
        sa.CheckConstraint("asset_type IN ('EQUITY', 'ETF')", name="ck_security_asset_type"),
    )
    sa.Index("ix_security_ticker", metadata.tables["security"].c.ticker)
    sa.Table(
        "current_position",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("account.id", ondelete="CASCADE"), nullable=False),
        sa.Column("security_id", sa.Integer(), sa.ForeignKey("security.id"), nullable=False),
        sa.Column("shares", sa.Text(), nullable=False),
        sa.Column("market_value_usd", sa.Text(), nullable=False),
        sa.Column("sync_generation", sa.Integer(), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("account_id", "security_id", name="uq_position_account_security"),
    )
    sa.Index("ix_position_account_security", metadata.tables["current_position"].c.account_id, metadata.tables["current_position"].c.security_id)
    sa.Table(
        "current_tax_lot",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("account.id", ondelete="CASCADE"), nullable=False),
        sa.Column("broker_lot_id", sa.String(128), nullable=False),
        sa.Column("security_id", sa.Integer(), sa.ForeignKey("security.id"), nullable=False),
        sa.Column("acquired_date", sa.Date(), nullable=False),
        sa.Column("shares", sa.Text(), nullable=False),
        sa.Column("available_shares", sa.Text(), nullable=False),
        sa.Column("adjusted_unit_basis_usd", sa.Text(), nullable=False),
        sa.Column("broker_wash_adjustment_usd", sa.Text()),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quality_flags", sa.JSON(), nullable=False),
        sa.Column("fractional_cleanup_unsupported", sa.Boolean(), nullable=False),
        sa.Column("sync_generation", sa.Integer(), nullable=False),
        sa.UniqueConstraint("account_id", "broker_lot_id", name="uq_lot_account_broker_id"),
        sa.CheckConstraint("available_shares NOT LIKE '-%'", name="ck_lot_available_nonnegative"),
        sa.CheckConstraint("shares NOT LIKE '-%' AND shares <> '0'", name="ck_lot_shares_positive"),
    )
    sa.Index("ix_lot_account_security", metadata.tables["current_tax_lot"].c.account_id, metadata.tables["current_tax_lot"].c.security_id)
    sa.Index("ix_lot_account_broker_id", metadata.tables["current_tax_lot"].c.account_id, metadata.tables["current_tax_lot"].c.broker_lot_id)
    sa.Table(
        "current_quote",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("security_id", sa.Integer(), sa.ForeignKey("security.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("bid_usd", sa.Text()),
        sa.Column("ask_usd", sa.Text()),
        sa.Column("last_usd", sa.Text()),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quality", sa.String(32), nullable=False),
        sa.Column("sync_generation", sa.Integer(), nullable=False),
        sa.CheckConstraint("bid_usd IS NULL OR (bid_usd NOT LIKE '-%' AND bid_usd <> '0')", name="ck_quote_bid_positive"),
        sa.CheckConstraint("ask_usd IS NULL OR (ask_usd NOT LIKE '-%' AND ask_usd <> '0')", name="ck_quote_ask_positive"),
        sa.CheckConstraint("last_usd IS NULL OR (last_usd NOT LIKE '-%' AND last_usd <> '0')", name="ck_quote_last_positive"),
    )
    sa.Index("ix_quote_as_of", metadata.tables["current_quote"].c.as_of)
    sa.Table(
        "broker_transaction",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("broker_transaction_key", sa.String(128), nullable=False, unique=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("account.id", ondelete="CASCADE"), nullable=False),
        sa.Column("security_id", sa.Integer(), sa.ForeignKey("security.id"), nullable=False),
        sa.Column("transaction_kind", sa.String(16), nullable=False),
        sa.Column("transaction_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("shares", sa.Text(), nullable=False),
        sa.Column("amount_usd", sa.Text(), nullable=False),
        sa.Column("is_acquisition", sa.Boolean(), nullable=False),
        sa.Column("broker_lot_id", sa.String(128)),
        sa.Column("source", sa.String(40), nullable=False),
        sa.CheckConstraint("transaction_kind IN ('BUY', 'SELL', 'DIVIDEND', 'OTHER')", name="ck_transaction_kind"),
    )
    sa.Index("ix_transaction_security_time", metadata.tables["broker_transaction"].c.security_id, metadata.tables["broker_transaction"].c.transaction_time)
    sa.Index("ix_transaction_account_time", metadata.tables["broker_transaction"].c.account_id, metadata.tables["broker_transaction"].c.transaction_time)
    sa.Table(
        "sync_state",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("current_generation", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("coverage", sa.JSON(), nullable=False),
        sa.Column("complete", sa.Boolean(), nullable=False),
        sa.Column("last_error_code", sa.String(64)),
        sa.Column("last_error_summary", sa.String(500)),
        sa.CheckConstraint("id = 1", name="ck_sync_state_singleton"),
    )
    sa.Table(
        "security_exposure",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("security_id", sa.Integer(), sa.ForeignKey("security.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dimension", sa.String(32), nullable=False),
        sa.Column("exposure_key", sa.String(128), nullable=False),
        sa.Column("weight", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(24), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.UniqueConstraint("security_id", "dimension", "exposure_key", "provider", name="uq_exposure_source"),
        sa.CheckConstraint("provider IN ('vanguard', 'ishares', 'manual_csv')", name="ck_exposure_provider"),
    )
    sa.Index("ix_exposure_security_dimension", metadata.tables["security_exposure"].c.security_id, metadata.tables["security_exposure"].c.dimension)
    sa.Table(
        "policy_revision",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.CheckConstraint("status IN ('DRAFT', 'ACTIVE', 'SUPERSEDED')", name="ck_policy_status"),
        sa.UniqueConstraint("revision_number", name="uq_policy_revision_number"),
    )
    sa.Index("ix_policy_status_revision", metadata.tables["policy_revision"].c.status, metadata.tables["policy_revision"].c.revision_number)
    sa.Table(
        "policy_sleeve",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("policy_revision_id", sa.String(36), sa.ForeignKey("policy_revision.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sleeve_key", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("parent_sleeve_key", sa.String(64)),
        sa.Column("target_pct", sa.Text(), nullable=False),
        sa.Column("drift_band_pp", sa.Text(), nullable=False),
        sa.Column("is_direct_index_container", sa.Boolean(), nullable=False),
        sa.Column("is_direct_index_sleeve", sa.Boolean(), nullable=False),
        sa.Column("is_cash_sleeve", sa.Boolean(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("policy_revision_id", "sleeve_key", name="uq_policy_sleeve_key"),
        sa.ForeignKeyConstraint(["policy_revision_id", "parent_sleeve_key"], ["policy_sleeve.policy_revision_id", "policy_sleeve.sleeve_key"], name="fk_sleeve_parent"),
    )
    sa.Index("ix_policy_sleeve_order", metadata.tables["policy_sleeve"].c.policy_revision_id, metadata.tables["policy_sleeve"].c.sort_order)
    sa.Table(
        "policy_allowed_security",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("policy_revision_id", sa.String(36), nullable=False),
        sa.Column("sleeve_key", sa.String(64), nullable=False),
        sa.Column("sub_sleeve_key", sa.String(64)),
        sa.Column("ticker", sa.String(32), nullable=False),
        sa.Column("replacement_set_id", sa.String(64), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("exposure_suitability", sa.String(200)),
        sa.ForeignKeyConstraint(["policy_revision_id", "sleeve_key"], ["policy_sleeve.policy_revision_id", "policy_sleeve.sleeve_key"], name="fk_allowed_security_sleeve"),
        sa.ForeignKeyConstraint(["ticker"], ["security.ticker"], name="fk_allowed_security_ticker"),
        sa.UniqueConstraint("policy_revision_id", "ticker", "replacement_set_id", name="uq_allowed_security_set"),
    )
    sa.Index("ix_allowed_security_policy_sleeve", metadata.tables["policy_allowed_security"].c.policy_revision_id, metadata.tables["policy_allowed_security"].c.sleeve_key)
    sa.Table(
        "policy_security_override",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("policy_revision_id", sa.String(36), nullable=False),
        sa.Column("security_id", sa.Integer(), nullable=False),
        sa.Column("sleeve_key", sa.String(64), nullable=False),
        sa.Column("sub_sleeve_key", sa.String(64)),
        sa.ForeignKeyConstraint(["policy_revision_id", "sleeve_key"], ["policy_sleeve.policy_revision_id", "policy_sleeve.sleeve_key"], name="fk_override_sleeve"),
        sa.ForeignKeyConstraint(["security_id"], ["security.id"], name="fk_override_security"),
        sa.UniqueConstraint("policy_revision_id", "security_id", name="uq_policy_security_override"),
    )
    sa.Table(
        "optimizer_run",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("policy_revision_id", sa.String(36), sa.ForeignKey("policy_revision.id"), nullable=False),
        sa.Column("source_generation", sa.Integer(), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("solver_version", sa.String(64)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("batch_settings", sa.JSON(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("input_fingerprint", sa.String(128)),
        sa.Column("frozen_input_bundle", sa.JSON(), nullable=False),
        sa.CheckConstraint("status IN ('CREATED', 'COMPLETE', 'INFEASIBLE', 'TIMEOUT', 'FAILED')", name="ck_optimizer_run_status"),
    )
    sa.Index("ix_optimizer_run_policy_asof", metadata.tables["optimizer_run"].c.policy_revision_id, metadata.tables["optimizer_run"].c.as_of)
    sa.Table(
        "recommendation_group",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("optimizer_run.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("group_type", sa.String(48), nullable=False),
        sa.Column("sleeve_key", sa.String(64)),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("estimated_benefit_usd", sa.Text()),
        sa.Column("impact", sa.JSON(), nullable=False),
        sa.Column("dependencies", sa.JSON(), nullable=False),
        sa.Column("selected", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("run_id", "rank", name="uq_recommendation_group_rank"),
    )
    sa.Index("ix_recommendation_group_run_rank", metadata.tables["recommendation_group"].c.run_id, metadata.tables["recommendation_group"].c.rank)
    sa.Table(
        "recommendation_leg",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("group_id", sa.String(36), sa.ForeignKey("recommendation_group.id", ondelete="CASCADE"), nullable=False),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("account.id"), nullable=False),
        sa.Column("security_id", sa.Integer(), sa.ForeignKey("security.id"), nullable=False),
        sa.Column("side", sa.String(4), nullable=False),
        sa.Column("shares", sa.Text(), nullable=False),
        sa.Column("estimated_unit_price_usd", sa.Text(), nullable=False),
        sa.Column("net_st_realized_usd", sa.Text(), nullable=False),
        sa.Column("net_lt_realized_usd", sa.Text(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.CheckConstraint("side IN ('BUY', 'SELL')", name="ck_recommendation_leg_side"),
    )
    sa.Index("ix_recommendation_leg_group", metadata.tables["recommendation_leg"].c.group_id)
    sa.Table(
        "recommendation_selected_lot",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("leg_id", sa.String(36), sa.ForeignKey("recommendation_leg.id", ondelete="CASCADE"), nullable=False),
        sa.Column("broker_lot_id", sa.String(128), nullable=False),
        sa.Column("shares", sa.Text(), nullable=False),
        sa.Column("acquired_date", sa.Date(), nullable=False),
        sa.Column("adjusted_basis_usd", sa.Text(), nullable=False),
        sa.Column("st_lt_term", sa.String(2), nullable=False),
        sa.Column("realized_pl_usd", sa.Text(), nullable=False),
        sa.UniqueConstraint("leg_id", "broker_lot_id", name="uq_selected_lot_leg_broker_id"),
        sa.CheckConstraint("shares NOT LIKE '-%' AND shares <> '0'", name="ck_selected_lot_shares_positive"),
        sa.CheckConstraint("st_lt_term IN ('ST', 'LT')", name="ck_selected_lot_term"),
    )
    sa.Index("ix_selected_lot_broker_id", metadata.tables["recommendation_selected_lot"].c.broker_lot_id)
    sa.Table(
        "activity_event",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
    )
    sa.Index("ix_activity_created_type", metadata.tables["activity_event"].c.created_at, metadata.tables["activity_event"].c.event_type)
    sa.Index("ix_activity_correlation", metadata.tables["activity_event"].c.correlation_id)
    return metadata


_DROP_ORDER = (
    "activity_event",
    "recommendation_selected_lot",
    "recommendation_leg",
    "recommendation_group",
    "optimizer_run",
    "policy_security_override",
    "policy_allowed_security",
    "policy_sleeve",
    "security_exposure",
    "current_quote",
    "broker_transaction",
    "current_tax_lot",
    "current_position",
    "sync_state",
    "policy_revision",
    "security",
    "account",
)


def upgrade() -> None:
    _foundation_metadata().create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    connection = op.get_bind()
    for table_name in _DROP_ORDER:
        if sa.inspect(connection).has_table(table_name):
            op.drop_table(table_name)
