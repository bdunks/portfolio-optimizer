from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


def canonical_decimal(value: Decimal) -> str:
    """Serialize a finite Decimal without exponent notation or insignificant zeros."""
    if not value.is_finite():
        raise ValueError("Decimal values must be finite")
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in {"", "-0", "+0"}:
        return "0"
    return text


class DecimalText(TypeDecorator[Decimal]):
    """Lossless canonical decimal text; deliberately avoids SQLite NUMERIC affinity."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Decimal | str | None, dialect: object) -> str | None:
        del dialect
        if value is None:
            return None
        if not isinstance(value, Decimal):
            value = Decimal(value)
        return canonical_decimal(value)

    def process_result_value(self, value: str | None, dialect: object) -> Decimal | None:
        del dialect
        return Decimal(value) if value is not None else None


class UTCDateTime(TypeDecorator[datetime]):
    """Store instants in UTC; naive values (including legacy rows) mean UTC."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: object) -> datetime | None:
        del dialect
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: object) -> datetime | None:
        del dialect
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = "account"
    __table_args__ = (CheckConstraint("id = 1", name="ck_account_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    broker_account_id_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    account_type: Mapped[str] = mapped_column(String(40), nullable=False, default="BROKERAGE")
    tax_treatment: Mapped[str | None] = mapped_column(String(40))
    cash_usd: Mapped[Decimal] = mapped_column(DecimalText(), nullable=False)
    settled_buying_power_usd: Mapped[Decimal] = mapped_column(DecimalText(), nullable=False)
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="FAKE")
    as_of: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class Security(Base):
    __tablename__ = "security"
    __table_args__ = (
        CheckConstraint("asset_type IN ('EQUITY', 'ETF')", name="ck_security_asset_type"),
        Index("ix_security_ticker", "ticker"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    cusip: Mapped[str | None] = mapped_column(String(16), unique=True)
    isin: Mapped[str | None] = mapped_column(String(16), unique=True)
    asset_type: Mapped[str] = mapped_column(String(12), nullable=False)
    is_completion_etf: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    vanguard_fund_id: Mapped[str | None] = mapped_column(String(40))
    ishares_holdings_url: Mapped[str | None] = mapped_column(Text)
    tradable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class CurrentPosition(Base):
    __tablename__ = "current_position"
    __table_args__ = (
        UniqueConstraint("account_id", "security_id", name="uq_position_account_security"),
        Index("ix_position_account_security", "account_id", "security_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("account.id", ondelete="CASCADE"), nullable=False)
    security_id: Mapped[int] = mapped_column(ForeignKey("security.id"), nullable=False)
    shares: Mapped[Decimal] = mapped_column(DecimalText(), nullable=False)
    market_value_usd: Mapped[Decimal] = mapped_column(DecimalText(), nullable=False)
    sync_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    as_of: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class CurrentTaxLot(Base):
    __tablename__ = "current_tax_lot"
    __table_args__ = (
        UniqueConstraint("account_id", "broker_lot_id", name="uq_lot_account_broker_id"),
        Index("ix_lot_account_security", "account_id", "security_id"),
        Index("ix_lot_account_broker_id", "account_id", "broker_lot_id"),
        CheckConstraint("available_shares NOT LIKE '-%'", name="ck_lot_available_nonnegative"),
        CheckConstraint("shares NOT LIKE '-%' AND shares <> '0'", name="ck_lot_shares_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("account.id", ondelete="CASCADE"), nullable=False)
    broker_lot_id: Mapped[str] = mapped_column(String(128), nullable=False)
    security_id: Mapped[int] = mapped_column(ForeignKey("security.id"), nullable=False)
    acquired_date: Mapped[date] = mapped_column(Date, nullable=False)
    shares: Mapped[Decimal] = mapped_column(DecimalText(), nullable=False)
    available_shares: Mapped[Decimal] = mapped_column(DecimalText(), nullable=False)
    adjusted_unit_basis_usd: Mapped[Decimal] = mapped_column(DecimalText(), nullable=False)
    broker_wash_adjustment_usd: Mapped[Decimal | None] = mapped_column(DecimalText())
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    as_of: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    quality_flags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    fractional_cleanup_unsupported: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sync_generation: Mapped[int] = mapped_column(Integer, nullable=False)


class CurrentQuote(Base):
    __tablename__ = "current_quote"
    __table_args__ = (
        Index("ix_quote_as_of", "as_of"),
        CheckConstraint(
            "bid_usd IS NULL OR (bid_usd NOT LIKE '-%' AND bid_usd <> '0')",
            name="ck_quote_bid_positive",
        ),
        CheckConstraint(
            "ask_usd IS NULL OR (ask_usd NOT LIKE '-%' AND ask_usd <> '0')",
            name="ck_quote_ask_positive",
        ),
        CheckConstraint(
            "last_usd IS NULL OR (last_usd NOT LIKE '-%' AND last_usd <> '0')",
            name="ck_quote_last_positive",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    security_id: Mapped[int] = mapped_column(ForeignKey("security.id", ondelete="CASCADE"), unique=True)
    bid_usd: Mapped[Decimal | None] = mapped_column(DecimalText())
    ask_usd: Mapped[Decimal | None] = mapped_column(DecimalText())
    last_usd: Mapped[Decimal | None] = mapped_column(DecimalText())
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    as_of: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    quality: Mapped[str] = mapped_column(String(32), nullable=False, default="good")
    sync_generation: Mapped[int] = mapped_column(Integer, nullable=False)


class BrokerTransaction(Base):
    __tablename__ = "broker_transaction"
    __table_args__ = (
        CheckConstraint(
            "transaction_kind IN ('BUY', 'SELL', 'DIVIDEND', 'OTHER')",
            name="ck_transaction_kind",
        ),
        Index("ix_transaction_security_time", "security_id", "transaction_time"),
        Index("ix_transaction_account_time", "account_id", "transaction_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    broker_transaction_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    account_id: Mapped[int] = mapped_column(ForeignKey("account.id", ondelete="CASCADE"), nullable=False)
    security_id: Mapped[int] = mapped_column(ForeignKey("security.id"), nullable=False)
    transaction_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    transaction_time: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    shares: Mapped[Decimal] = mapped_column(DecimalText(), nullable=False)
    amount_usd: Mapped[Decimal] = mapped_column(DecimalText(), nullable=False)
    realized_pl_usd: Mapped[Decimal | None] = mapped_column(DecimalText())
    is_acquisition: Mapped[bool] = mapped_column(Boolean, nullable=False)
    broker_lot_id: Mapped[str | None] = mapped_column(String(128))
    source: Mapped[str] = mapped_column(String(40), nullable=False)


class SyncState(Base):
    __tablename__ = "sync_state"
    __table_args__ = (CheckConstraint("id = 1", name="ck_sync_state_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    current_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    coverage: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    last_error_summary: Mapped[str | None] = mapped_column(String(500))


class SecurityExposure(Base):
    __tablename__ = "security_exposure"
    __table_args__ = (
        UniqueConstraint(
            "security_id", "dimension", "exposure_key", "provider", name="uq_exposure_source"
        ),
        Index("ix_exposure_security_dimension", "security_id", "dimension"),
        CheckConstraint(
            "provider IN ('vanguard', 'ishares', 'manual_csv')", name="ck_exposure_provider"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    security_id: Mapped[int] = mapped_column(ForeignKey("security.id", ondelete="CASCADE"), nullable=False)
    dimension: Mapped[str] = mapped_column(String(32), nullable=False)
    exposure_key: Mapped[str] = mapped_column(String(128), nullable=False)
    weight: Mapped[Decimal] = mapped_column(DecimalText(), nullable=False)
    provider: Mapped[str] = mapped_column(String(24), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)


class PolicyRevision(Base):
    __tablename__ = "policy_revision"
    __table_args__ = (
        CheckConstraint("status IN ('DRAFT', 'ACTIVE', 'SUPERSEDED')", name="ck_policy_status"),
        UniqueConstraint("revision_number", name="uq_policy_revision_number"),
        Index("ix_policy_status_revision", "status", "revision_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    short_term_tax_rate: Mapped[Decimal | None] = mapped_column(DecimalText())
    long_term_tax_rate: Mapped[Decimal | None] = mapped_column(DecimalText())
    st_loss_carryforward_usd: Mapped[Decimal] = mapped_column(DecimalText(), nullable=False, default=Decimal(0))
    lt_loss_carryforward_usd: Mapped[Decimal] = mapped_column(DecimalText(), nullable=False, default=Decimal(0))
    ytd_realized_st_usd: Mapped[Decimal] = mapped_column(DecimalText(), nullable=False, default=Decimal(0))
    ytd_realized_lt_usd: Mapped[Decimal] = mapped_column(DecimalText(), nullable=False, default=Decimal(0))
    ytd_source: Mapped[str | None] = mapped_column(String(80))
    ytd_as_of: Mapped[date | None] = mapped_column(Date)
    target_retained_net_loss_usd: Mapped[Decimal] = mapped_column(DecimalText(), nullable=False, default=Decimal(3000))
    ordinary_income_deduction_limit_usd: Mapped[Decimal] = mapped_column(DecimalText(), nullable=False, default=Decimal(3000))
    carryforward_loss_discount_factor: Mapped[Decimal] = mapped_column(DecimalText(), nullable=False, default=Decimal("0.50"))
    gain_budget_usd: Mapped[Decimal | None] = mapped_column(DecimalText())
    max_incremental_tax_cost_usd: Mapped[Decimal | None] = mapped_column(DecimalText())
    st_gain_limit_usd: Mapped[Decimal | None] = mapped_column(DecimalText())
    lt_gain_limit_usd: Mapped[Decimal | None] = mapped_column(DecimalText())
    budget_period: Mapped[str] = mapped_column(String(32), nullable=False, default="calendar_year")
    max_sell_tickers_per_batch: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    max_sell_lots_per_batch: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    max_total_orders_per_batch: Mapped[int] = mapped_column(Integer, nullable=False, default=12)
    max_batch_turnover_pct: Mapped[Decimal] = mapped_column(DecimalText(), nullable=False, default=Decimal("5.0"))
    min_buy_order_notional_usd: Mapped[Decimal] = mapped_column(DecimalText(), nullable=False, default=Decimal("500.00"))
    cash_reserve_usd: Mapped[Decimal] = mapped_column(DecimalText(), nullable=False, default=Decimal(0))
    prefer_etf_buys: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_gain_sales: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    permit_etf_harvest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    permit_muni_exit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    objective_band_weight: Mapped[Decimal | None] = mapped_column(DecimalText())
    objective_allocation_weight: Mapped[Decimal | None] = mapped_column(DecimalText())
    objective_tax_weight: Mapped[Decimal | None] = mapped_column(DecimalText())
    objective_trading_cost_weight: Mapped[Decimal | None] = mapped_column(DecimalText())
    objective_turnover_weight: Mapped[Decimal | None] = mapped_column(DecimalText())
    objective_cleanup_weight: Mapped[Decimal | None] = mapped_column(DecimalText())
    estimated_spread_bps: Mapped[Decimal | None] = mapped_column(DecimalText())
    estimated_fee_per_order_usd: Mapped[Decimal | None] = mapped_column(DecimalText())

class PolicySleeve(Base):
    __tablename__ = "policy_sleeve"
    __table_args__ = (
        UniqueConstraint("policy_revision_id", "sleeve_key", name="uq_policy_sleeve_key"),
        ForeignKeyConstraint(
            ["policy_revision_id", "parent_sleeve_key"],
            ["policy_sleeve.policy_revision_id", "policy_sleeve.sleeve_key"],
            name="fk_sleeve_parent",
        ),
        Index("ix_policy_sleeve_order", "policy_revision_id", "sort_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_revision_id: Mapped[str] = mapped_column(
        ForeignKey("policy_revision.id", ondelete="CASCADE"), nullable=False
    )
    sleeve_key: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_sleeve_key: Mapped[str | None] = mapped_column(String(64))
    target_pct: Mapped[Decimal] = mapped_column(DecimalText(), nullable=False)
    drift_band_pp: Mapped[Decimal] = mapped_column(DecimalText(), nullable=False)
    is_direct_index_container: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_direct_index_sleeve: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_transition_destination: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_cash_sleeve: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)



class PolicySectorBand(Base):
    __tablename__ = "policy_sector_band"
    __table_args__ = (
        UniqueConstraint("policy_revision_id", "sector_key", name="uq_policy_sector_band_key"),
        CheckConstraint("target_weight_pct NOT LIKE '-%'", name="ck_sector_band_target_nonnegative"),
        CheckConstraint("band_pct NOT LIKE '-%'", name="ck_sector_band_band_nonnegative"),
        Index("ix_policy_sector_band_revision", "policy_revision_id", "sector_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_revision_id: Mapped[str] = mapped_column(
        ForeignKey("policy_revision.id", ondelete="CASCADE"), nullable=False
    )
    sector_key: Mapped[str] = mapped_column(String(128), nullable=False)
    target_weight_pct: Mapped[Decimal] = mapped_column(DecimalText(), nullable=False)
    band_pct: Mapped[Decimal] = mapped_column(DecimalText(), nullable=False)

class PolicyAllowedSecurity(Base):
    __tablename__ = "policy_allowed_security"
    __table_args__ = (
        ForeignKeyConstraint(
            ["policy_revision_id", "sleeve_key"],
            ["policy_sleeve.policy_revision_id", "policy_sleeve.sleeve_key"],
            name="fk_allowed_security_sleeve",
        ),
        ForeignKeyConstraint(["ticker"], ["security.ticker"], name="fk_allowed_security_ticker"),
        UniqueConstraint(
            "policy_revision_id", "ticker", "replacement_set_id", name="uq_allowed_security_set"
        ),
        Index("ix_allowed_security_policy_sleeve", "policy_revision_id", "sleeve_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_revision_id: Mapped[str] = mapped_column(String(36), nullable=False)
    sleeve_key: Mapped[str] = mapped_column(String(64), nullable=False)
    sub_sleeve_key: Mapped[str | None] = mapped_column(String(64))
    ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    replacement_set_id: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    exposure_suitability: Mapped[str | None] = mapped_column(String(200))


class PolicySecurityOverride(Base):
    __tablename__ = "policy_security_override"
    __table_args__ = (
        ForeignKeyConstraint(
            ["policy_revision_id", "sleeve_key"],
            ["policy_sleeve.policy_revision_id", "policy_sleeve.sleeve_key"],
            name="fk_override_sleeve",
        ),
        ForeignKeyConstraint(["security_id"], ["security.id"], name="fk_override_security"),
        UniqueConstraint("policy_revision_id", "security_id", name="uq_policy_security_override"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_revision_id: Mapped[str] = mapped_column(String(36), nullable=False)
    security_id: Mapped[int] = mapped_column(Integer, nullable=False)
    sleeve_key: Mapped[str] = mapped_column(String(64), nullable=False)
    sub_sleeve_key: Mapped[str | None] = mapped_column(String(64))


class OptimizerRun(Base):
    __tablename__ = "optimizer_run"
    __table_args__ = (
        CheckConstraint(
            "status IN ('CREATED', 'COMPLETE', 'INFEASIBLE', 'TIMEOUT', 'FAILED')",
            name="ck_optimizer_run_status",
        ),
        Index("ix_optimizer_run_policy_asof", "policy_revision_id", "as_of"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    policy_revision_id: Mapped[str] = mapped_column(ForeignKey("policy_revision.id"), nullable=False)
    source_generation: Mapped[int] = mapped_column(Integer, nullable=False)
    as_of: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    proposed_trade_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    solver_version: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    batch_settings: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    warnings: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    input_fingerprint: Mapped[str | None] = mapped_column(String(128))
    frozen_input_bundle: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class RecommendationGroup(Base):
    __tablename__ = "recommendation_group"
    __table_args__ = (
        UniqueConstraint("run_id", "rank", name="uq_recommendation_group_rank"),
        Index("ix_recommendation_group_run_rank", "run_id", "rank"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("optimizer_run.id", ondelete="CASCADE"), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    group_type: Mapped[str] = mapped_column(String(48), nullable=False)
    sleeve_key: Mapped[str | None] = mapped_column(String(64))
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    estimated_benefit_usd: Mapped[Decimal | None] = mapped_column(DecimalText())
    impact: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    dependencies: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    note: Mapped[str | None] = mapped_column(Text)
    rejected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text)

class RecommendationLeg(Base):
    __tablename__ = "recommendation_leg"
    __table_args__ = (
        CheckConstraint("side IN ('BUY', 'SELL')", name="ck_recommendation_leg_side"),
        Index("ix_recommendation_leg_group", "group_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    group_id: Mapped[str] = mapped_column(
        ForeignKey("recommendation_group.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[int] = mapped_column(ForeignKey("account.id"), nullable=False)
    security_id: Mapped[int] = mapped_column(ForeignKey("security.id"), nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)
    shares: Mapped[Decimal] = mapped_column(DecimalText(), nullable=False)
    estimated_unit_price_usd: Mapped[Decimal] = mapped_column(DecimalText(), nullable=False)
    net_st_realized_usd: Mapped[Decimal] = mapped_column(DecimalText(), nullable=False)
    net_lt_realized_usd: Mapped[Decimal] = mapped_column(DecimalText(), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class RecommendationGroupLeg(Base):
    __tablename__ = "recommendation_group_leg"
    __table_args__ = (Index("ix_recommendation_group_leg_leg", "leg_id"),)

    group_id: Mapped[str] = mapped_column(
        ForeignKey("recommendation_group.id", ondelete="CASCADE"), primary_key=True
    )
    leg_id: Mapped[str] = mapped_column(
        ForeignKey("recommendation_leg.id", ondelete="CASCADE"), primary_key=True
    )


class RecommendationSelectedLot(Base):
    __tablename__ = "recommendation_selected_lot"
    __table_args__ = (
        UniqueConstraint("leg_id", "broker_lot_id", name="uq_selected_lot_leg_broker_id"),
        Index("ix_selected_lot_broker_id", "broker_lot_id"),
        CheckConstraint("shares NOT LIKE '-%' AND shares <> '0'", name="ck_selected_lot_shares_positive"),
        CheckConstraint("st_lt_term IN ('ST', 'LT')", name="ck_selected_lot_term"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    leg_id: Mapped[str] = mapped_column(
        ForeignKey("recommendation_leg.id", ondelete="CASCADE"), nullable=False
    )
    broker_lot_id: Mapped[str] = mapped_column(String(128), nullable=False)
    shares: Mapped[Decimal] = mapped_column(DecimalText(), nullable=False)
    acquired_date: Mapped[date] = mapped_column(Date, nullable=False)
    adjusted_basis_usd: Mapped[Decimal] = mapped_column(DecimalText(), nullable=False)
    st_lt_term: Mapped[str] = mapped_column(String(2), nullable=False)
    realized_pl_usd: Mapped[Decimal] = mapped_column(DecimalText(), nullable=False)

    selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

class ActivityEvent(Base):
    __tablename__ = "activity_event"
    __table_args__ = (
        Index("ix_activity_created_type", "created_at", "event_type"),
        Index("ix_activity_correlation", "correlation_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
