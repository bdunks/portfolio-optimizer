from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)


def parse_exact_decimal(value: object) -> Decimal:
    if isinstance(value, (bool, float)):
        raise ValueError("decimal values must be sent as exact strings or integers")  # noqa: TRY004
    if not isinstance(value, (str, int, Decimal)):
        raise ValueError("decimal values must be strings or integers")  # noqa: TRY004
    try:
        result = Decimal(value)
    except (ValueError, TypeError, ArithmeticError) as exc:
        raise ValueError("invalid decimal value") from exc
    if not result.is_finite():
        raise ValueError("decimal values must be finite")
    return result


ExactDecimal = Annotated[Decimal, BeforeValidator(parse_exact_decimal, json_schema_input_type=str)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CoverageInput(StrictModel):
    positions: bool
    lots: bool
    transactions: bool
    balances: bool
    quotes: bool
    lookthrough: bool = False
    transaction_history_start_date: date | None = None
    transaction_history_end_date: date | None = None


class PositionInput(StrictModel):
    ticker: str = Field(min_length=1, max_length=32)
    asset_type: Literal["EQUITY", "ETF"]
    shares: ExactDecimal
    market_value_usd: ExactDecimal
    cusip: str | None = None
    isin: str | None = None
    is_completion_etf: bool = False

    @field_validator("ticker")
    @classmethod
    def ticker_uppercase(cls, value: str) -> str:
        return value.upper()


class LotInput(StrictModel):
    ticker: str = Field(min_length=1, max_length=32)
    broker_lot_id: str = Field(min_length=1, max_length=128)
    acquired_date: date
    shares: ExactDecimal
    available_shares: ExactDecimal
    adjusted_unit_basis_usd: ExactDecimal
    broker_wash_adjustment_usd: ExactDecimal | None = None
    source: str = Field(min_length=1, max_length=40)
    as_of: datetime
    quality_flags: list[str] = Field(default_factory=list)

    @field_validator("ticker")
    @classmethod
    def ticker_uppercase(cls, value: str) -> str:
        return value.upper()


class QuoteInput(StrictModel):
    ticker: str = Field(min_length=1, max_length=32)
    bid_usd: ExactDecimal | None = None
    ask_usd: ExactDecimal | None = None
    last_usd: ExactDecimal | None = None
    source: str = Field(min_length=1, max_length=40)
    as_of: datetime
    quality: str = "good"

    @field_validator("ticker")
    @classmethod
    def ticker_uppercase(cls, value: str) -> str:
        return value.upper()


class TransactionInput(StrictModel):
    broker_transaction_key: str = Field(min_length=1, max_length=128)
    ticker: str = Field(min_length=1, max_length=32)
    transaction_kind: Literal["BUY", "SELL", "DIVIDEND", "OTHER"]
    transaction_time: datetime
    trade_date: date
    shares: ExactDecimal
    amount_usd: ExactDecimal
    realized_pl_usd: ExactDecimal | None = None
    is_acquisition: bool
    broker_lot_id: str | None = None
    source: str = Field(min_length=1, max_length=40)

    @field_validator("ticker")
    @classmethod
    def ticker_uppercase(cls, value: str) -> str:
        return value.upper()


class ExposureInput(StrictModel):
    ticker: str = Field(min_length=1, max_length=32)
    dimension: str = Field(min_length=1, max_length=32)
    exposure_key: str = Field(min_length=1, max_length=128)
    weight: ExactDecimal
    provider: Literal["vanguard", "ishares", "manual_csv"]
    as_of_date: date

    @field_validator("ticker")
    @classmethod
    def ticker_uppercase(cls, value: str) -> str:
        return value.upper()


class BrokerSnapshot(StrictModel):
    account_id_key: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=200)
    account_type: str = "BROKERAGE"
    tax_treatment: str | None = None
    source: str = "FAKE"
    as_of: datetime
    cash_usd: ExactDecimal
    settled_buying_power_usd: ExactDecimal
    coverage: CoverageInput
    positions: list[PositionInput]
    lots: list[LotInput]
    quotes: list[QuoteInput]
    transactions: list[TransactionInput]
    exposures: list[ExposureInput] = Field(default_factory=list)


class SleeveInput(StrictModel):
    sleeve_key: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=120)
    sort_order: int = 0
    parent_sleeve_key: str | None = None
    target_pct: ExactDecimal = Decimal(0)
    drift_band_pp: ExactDecimal = Decimal(0)
    is_direct_index_container: bool = False
    is_direct_index_sleeve: bool = False
    is_transition_destination: bool = False
    is_cash_sleeve: bool = False
    enabled: bool = True

class SectorBandInput(StrictModel):
    sector_key: str = Field(min_length=1, max_length=128)

    target_weight_pct: ExactDecimal
    band_pct: ExactDecimal

    @field_validator("sector_key")
    @classmethod
    def sector_key_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("sector key must not be blank")
        return value



class AllowedSecurityInput(StrictModel):
    ticker: str = Field(min_length=1, max_length=32)
    sleeve_key: str = Field(min_length=1, max_length=64)
    sub_sleeve_key: str | None = None
    replacement_set_id: str = "default"
    priority: int = 0
    enabled: bool = True
    exposure_suitability: str | None = None

    @field_validator("ticker")
    @classmethod
    def ticker_uppercase(cls, value: str) -> str:
        return value.upper()


class OverrideInput(StrictModel):
    ticker: str = Field(min_length=1, max_length=32)
    sleeve_key: str = Field(min_length=1, max_length=64)
    sub_sleeve_key: str | None = None

    @field_validator("ticker")
    @classmethod
    def ticker_uppercase(cls, value: str) -> str:
        return value.upper()


class PolicySettingsInput(StrictModel):
    short_term_tax_rate: ExactDecimal | None = None
    long_term_tax_rate: ExactDecimal | None = None
    st_loss_carryforward_usd: ExactDecimal = Decimal(0)
    lt_loss_carryforward_usd: ExactDecimal = Decimal(0)
    ytd_realized_st_usd: ExactDecimal = Decimal(0)
    ytd_realized_lt_usd: ExactDecimal = Decimal(0)
    ytd_source: str | None = None
    ytd_as_of: date | None = None
    target_retained_net_loss_usd: ExactDecimal = Decimal(3000)
    ordinary_income_deduction_limit_usd: ExactDecimal = Decimal(3000)
    carryforward_loss_discount_factor: ExactDecimal = Decimal("0.50")
    gain_budget_usd: ExactDecimal | None = None
    max_incremental_tax_cost_usd: ExactDecimal | None = None
    st_gain_limit_usd: ExactDecimal | None = None
    lt_gain_limit_usd: ExactDecimal | None = None
    budget_period: str = "calendar_year"
    max_sell_tickers_per_batch: int = 10
    max_sell_lots_per_batch: int = 20
    max_total_orders_per_batch: int = 12
    max_batch_turnover_pct: ExactDecimal = Decimal("5.0")
    min_buy_order_notional_usd: ExactDecimal = Decimal("500.00")
    cash_reserve_usd: ExactDecimal = Decimal(0)
    prefer_etf_buys: bool = True
    allow_gain_sales: bool = False
    permit_etf_harvest: bool = False
    permit_muni_exit: bool = False
    objective_band_weight: ExactDecimal | None = None
    objective_allocation_weight: ExactDecimal | None = None
    objective_tax_weight: ExactDecimal | None = None
    objective_trading_cost_weight: ExactDecimal | None = None
    objective_turnover_weight: ExactDecimal | None = None
    objective_cleanup_weight: ExactDecimal | None = None
    estimated_spread_bps: ExactDecimal | None = None
    estimated_fee_per_order_usd: ExactDecimal | None = None

    @field_validator(
        "objective_band_weight",
        "objective_allocation_weight",
        "objective_tax_weight",
        "objective_trading_cost_weight",
        "objective_turnover_weight",
        "objective_cleanup_weight",
        "estimated_spread_bps",
        "estimated_fee_per_order_usd",
    )
    @classmethod
    def nonnegative_objective_parameters(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and value < 0:
            raise ValueError("objective weights and estimated costs must be nonnegative")
        return value


class PolicyDraftInput(StrictModel):
    sector_bands: list[SectorBandInput] = Field(default_factory=list)
    settings: PolicySettingsInput
    sleeves: list[SleeveInput]
    allowed_securities: list[AllowedSecurityInput] = Field(default_factory=list)
    overrides: list[OverrideInput] = Field(default_factory=list)
    reassignments: dict[str, str] = Field(default_factory=dict)
    source_revision_id: str | None = None


class PolicySectorBandResponse(StrictModel):
    sector_key: str
    target_weight_pct: str
    band_pct: str



class OptimizerRunInput(StrictModel):
    mode: Literal["recommendations_only", "real_optimizer"] = "recommendations_only"
    proposed_trade_date: date | None = None
    max_sell_tickers_per_batch: int | None = Field(default=None, gt=0)
    max_sell_lots_per_batch: int | None = Field(default=None, gt=0)
    max_total_orders_per_batch: int | None = Field(default=None, gt=0)


class OptimizerSelectionInput(StrictModel):
    selected_group_ids: list[str] = Field(default_factory=list, max_length=100)
    selected_sell_lots: dict[str, list[str]] = Field(default_factory=dict)

    @field_validator("selected_group_ids")
    @classmethod
    def unique_groups(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("selected_group_ids must not contain duplicates")
        return value

    @field_validator("selected_sell_lots")
    @classmethod
    def unique_lots(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        if any(len(set(lot_ids)) != len(lot_ids) for lot_ids in value.values()):
            raise ValueError("selected sell lot IDs must not contain duplicates")
        return value


class OptimizerLotReviewIntentInput(StrictModel):
    """Generation-bound desired sell-lot basket; this is not order approval."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    source_generation: StrictInt = Field(
        ge=0,
        description="Source sync generation the requested lots were reviewed against.",
    )
    broker_lot_ids: list[StrictStr] = Field(
        max_length=500,
        description="Complete desired SELL-lot set for the confirmed DEMO basket; an empty list clears it.",
    )

    @field_validator("broker_lot_ids")
    @classmethod
    def valid_unique_broker_lot_ids(cls, value: list[str]) -> list[str]:
        if any(not broker_lot_id or len(broker_lot_id) > 128 for broker_lot_id in value):
            raise ValueError("broker lot IDs must contain 1 to 128 characters")
        if len(set(value)) != len(value):
            raise ValueError("broker_lot_ids must not contain duplicates")
        return value


class RecommendationAnnotationInput(StrictModel):
    note: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional note (maximum 2000 characters); omitted leaves it unchanged and explicit null clears it.",
    )
    rejected: bool | None = Field(
        default=None,
        description="Set rejection state; restoring with false clears the reason and does not reselect the group.",
    )
    rejection_reason: str | None = Field(
        default=None,
        max_length=500,
        description="Optional rejection reason (maximum 500 characters); may be changed only with rejected=true.",
    )

    @model_validator(mode="after")
    def require_annotation(self) -> RecommendationAnnotationInput:
        fields_set = self.model_fields_set
        if not fields_set or ("note" not in fields_set and self.rejected is None):
            raise ValueError("at least one annotation change is required")
        if "rejection_reason" in fields_set and self.rejected is not True:
            raise ValueError("a rejection reason may only be supplied with rejected=true")
        return self



# Response DTOs are the authoritative HTTP contracts. Monetary and share values
# are serialized as exact decimal strings; only provenance/details are open JSON.
type JSONValue = str | int | float | bool | list[JSONValue] | dict[str, JSONValue] | None
class ErrorEnvelope(StrictModel):
    code: str
    message: str
    details: JSONValue
    correlation_id: str




class CoverageResponse(StrictModel):
    positions: bool
    lots: bool
    transactions: bool
    balances: bool
    quotes: bool
    lookthrough: bool = False
    transaction_history_start_date: date | None = None
    transaction_history_end_date: date | None = None


class SyncStatusResponse(StrictModel):
    generation: int
    complete: bool
    started_at: datetime | None
    completed_at: datetime | None
    last_error_code: str | None
    last_error_summary: str | None


class HealthResponse(StrictModel):
    status: Literal["ok", "not_ready"]
    schema_ready: bool
    broker_mode: str
    live_broker_enabled: Literal[False]
    order_submission_enabled: Literal[False]


class SyncResponseDTO(StrictModel):
    generation: int
    status: Literal["complete"]
    as_of: datetime
    coverage: CoverageResponse
    account: str
    demo: bool


class PositionResponse(StrictModel):
    ticker: str
    asset_type: Literal["EQUITY", "ETF"]
    shares: str
    market_value_usd: str
    last_price_usd: str | None
    quote_source: str | None
    quote_as_of: datetime | None
    sleeve_key: str | None
    sub_sleeve_key: str | None


class AllocationWeightsResponse(StrictModel):
    total_portfolio_usd: str
    sleeve_weights_pct: dict[str, str]


class AllocationTargetResponse(StrictModel):
    sleeve_weights_pct: dict[str, str]


class AllocationResponse(StrictModel):
    current: AllocationWeightsResponse | None
    proposed: AllocationWeightsResponse | None
    target: AllocationTargetResponse | None


class TransitionChildResponse(StrictModel):
    value_usd: str
    within_us_sleeve_pct: str
    whole_portfolio_pct: str


class TransitionSnapshotResponse(StrictModel):
    us_sleeve_value_usd: str
    us_sleeve_whole_portfolio_pct: str
    etf_progress_pct: str | None
    children: dict[str, TransitionChildResponse]


class TransitionTargetChildResponse(StrictModel):
    within_us_sleeve_pct: str
    whole_portfolio_pct: str


class TransitionTargetResponse(StrictModel):
    us_sleeve_whole_portfolio_pct: str
    children: dict[str, TransitionTargetChildResponse]


class USTransitionResponse(StrictModel):
    sleeve_key: str
    transition_destination_sleeve_key: str | None
    label: str
    current: TransitionSnapshotResponse
    proposed_basket: TransitionSnapshotResponse
    target: TransitionTargetResponse


class PortfolioAccountResponse(StrictModel):
    display_name: str
    account_type: str
    tax_treatment: str | None


class PortfolioNotSyncedResponse(StrictModel):
    status: Literal["not_synced"]
    demo: bool
    account: None
    as_of: None
    cash_usd: str
    portfolio_total_usd: str
    positions: list[PositionResponse]
    coverage: dict[str, bool | str | None]
    sync: SyncStatusResponse
    allocation: AllocationResponse
    us_transition: None


class PortfolioReadyResponse(StrictModel):
    status: Literal["ready"]
    demo: bool
    source: str
    account: PortfolioAccountResponse
    as_of: datetime
    cash_usd: str
    settled_buying_power_usd: str
    positions_market_value_usd: str
    portfolio_total_usd: str
    position_count: int
    positions: list[PositionResponse]
    active_policy_revision_id: str | None
    unassigned_tickers: list[str]
    coverage: dict[str, bool | str | None]
    sync: SyncStatusResponse
    allocation: AllocationResponse
    us_transition: USTransitionResponse | None


PortfolioResponse = PortfolioNotSyncedResponse | PortfolioReadyResponse


class LotResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    ticker: str
    asset_type: Literal["EQUITY", "ETF"]
    broker_lot_id: str
    acquired_date: date
    remaining_shares: str
    available_shares: str
    adjusted_unit_basis_usd: str
    adjusted_total_basis_usd: str
    current_price_usd: str | None
    unrealized_pl_usd: str | None
    unrealized_pl_pct: str | None
    source: str
    as_of: datetime
    term: Literal["ST", "LT"]
    sleeve_key: str | None
    sub_sleeve_key: str | None
    quality_flags: list[str]
    small_lot_cleanup_candidate: bool
    position_cleanup_candidate: bool
    whole_shares_available: str
    fractional_shares: str
    fractional_cleanup_unsupported: bool


class LotPageResponse(StrictModel):
    items: list[LotResponse]
    total: int
    offset: int
    limit: int
    source_generation: int | None = Field(
        description="Complete current sync generation for the lots in this query, or null when unavailable."
    )

class PolicySettingsResponse(StrictModel):
    short_term_tax_rate: str | None
    long_term_tax_rate: str | None
    st_loss_carryforward_usd: str
    lt_loss_carryforward_usd: str
    ytd_realized_st_usd: str
    ytd_realized_lt_usd: str
    ytd_source: str | None
    ytd_as_of: date | None
    target_retained_net_loss_usd: str
    ordinary_income_deduction_limit_usd: str
    carryforward_loss_discount_factor: str
    gain_budget_usd: str | None
    max_incremental_tax_cost_usd: str | None
    st_gain_limit_usd: str | None
    lt_gain_limit_usd: str | None
    budget_period: str
    max_sell_tickers_per_batch: int
    max_sell_lots_per_batch: int
    max_total_orders_per_batch: int
    max_batch_turnover_pct: str
    min_buy_order_notional_usd: str
    cash_reserve_usd: str
    prefer_etf_buys: bool
    allow_gain_sales: bool
    permit_etf_harvest: bool
    objective_band_weight: str | None
    objective_allocation_weight: str | None
    objective_tax_weight: str | None
    objective_trading_cost_weight: str | None
    objective_turnover_weight: str | None
    objective_cleanup_weight: str | None
    estimated_spread_bps: str | None
    estimated_fee_per_order_usd: str | None
    permit_muni_exit: bool


class PolicySleeveResponse(StrictModel):
    sleeve_key: str
    display_name: str
    sort_order: int
    parent_sleeve_key: str | None
    target_pct: str
    drift_band_pp: str
    is_direct_index_container: bool
    is_direct_index_sleeve: bool
    is_transition_destination: bool
    is_cash_sleeve: bool
    enabled: bool


class AllowedSecurityResponse(StrictModel):
    ticker: str
    sleeve_key: str
    sub_sleeve_key: str | None
    replacement_set_id: str
    priority: int
    enabled: bool
    exposure_suitability: str | None


class PolicyOverrideResponse(StrictModel):
    ticker: str
    sleeve_key: str
    sub_sleeve_key: str | None


class PolicyValidationErrorResponse(StrictModel):
    code: str
    message: str


class PolicyRevisionResponse(StrictModel):
    sector_bands: list[PolicySectorBandResponse] = Field(default_factory=list)
    id: str
    revision_number: int
    status: Literal["DRAFT", "ACTIVE", "SUPERSEDED"]
    created_at: datetime
    activated_at: datetime | None
    settings: PolicySettingsResponse
    sleeves: list[PolicySleeveResponse]
    allowed_securities: list[AllowedSecurityResponse]
    overrides: list[PolicyOverrideResponse]
    activation_errors: list[PolicyValidationErrorResponse] | None = None


class PolicyResponse(StrictModel):
    active: PolicyRevisionResponse | None
    drafts: list[PolicyRevisionResponse]
    superseded: list[PolicyRevisionResponse]


class ActivityEventResponse(StrictModel):
    id: str
    created_at: datetime
    event_type: str
    status: str
    correlation_id: str
    details: JSONValue


class ActivityPageResponse(StrictModel):
    items: list[ActivityEventResponse]
    total: int
    offset: int
    limit: int


class PortfolioEffectsResponse(StrictModel):
    allocation: AllocationResponse
    us_transition: USTransitionResponse | None


class GroupImpactResponse(StrictModel):
    demo: bool
    wash_status: str
    selected_sell_lots_count: int
    sell_proceeds_usd: str
    realized_st_usd: str
    realized_lt_usd: str
    replacement_buy_shares: str | None
    replacement_buy_cost_usd: str | None
    cash_after_usd: str | None
    portfolio_effects: PortfolioEffectsResponse | None
    risk_tracking_score: str | None




class SelectedLotResponse(StrictModel):
    broker_lot_id: str
    shares: str
    acquired_date: date
    adjusted_basis_usd: str
    st_lt: Literal["ST", "LT"]
    realized_pl_usd: str
    selected: bool


class RecommendationLegResponse(StrictModel):
    leg_id: str
    side: Literal["BUY", "SELL"]
    ticker: str | None
    shares: str
    estimated_unit_price_usd: str
    estimated_notional_usd: str
    net_st_realized_usd: str
    selected: bool
    group_ids: list[str]
    net_lt_realized_usd: str
    sequence: int
    dependencies: list[str]
    selected_lots: list[SelectedLotResponse]
    details: dict[str, JSONValue]


class RecommendationGroupResponse(StrictModel):
    group_id: str
    rank: int
    group_type: str
    sleeve_key: str | None
    rationale: str
    estimated_benefit_usd: str | None
    impact: GroupImpactResponse | None
    dependencies: list[str]
    selected: bool
    rejected: bool
    note: str | None
    rejection_reason: str | None
    leg_ids: list[str]
    warnings: list[str]


class RunPolicySleeveResponse(StrictModel):
    sleeve_key: str
    display_name: str
    sort_order: int
    parent_sleeve_key: str | None
    target_pct: str | None
    drift_band_pp: str | None
    enabled: bool
    is_direct_index_container: bool
    is_direct_index_sleeve: bool
    is_transition_destination: bool
    is_cash_sleeve: bool


class RunPolicyAllowedSecurityResponse(StrictModel):
    ticker: str
    sleeve_key: str
    sub_sleeve_key: str | None
    replacement_set_id: str
    priority: int
    enabled: bool
    exposure_suitability: str | None


class RunPolicyOverrideResponse(StrictModel):
    ticker: str
    sleeve_key: str
    sub_sleeve_key: str | None


class FrozenRunDisplayContextResponse(StrictModel):
    available: bool
    source: Literal["frozen_input_bundle", "policy_revision"] | None
    policy_revision_id: str
    revision_number: int | None
    created_at: datetime | None
    activated_at: datetime | None
    sleeves: list[RunPolicySleeveResponse] | None
    settings: dict[str, JSONValue] | None
    allowed_securities: list[RunPolicyAllowedSecurityResponse] | None
    overrides: list[RunPolicyOverrideResponse] | None
    unavailable_reason: str | None


class OptimizerRunResponse(StrictModel):
    run_id: str
    status: str
    mode: Literal["recommendations_only", "real_optimizer"]
    policy_revision_id: str
    source_generation: int
    as_of: datetime
    solver_version: str
    proposed_trade_date: date | None = None
    demo: bool
    actionable: Literal[False]
    input_fingerprint: str | None
    source_checksum: str | None
    batch_settings: dict[str, JSONValue]
    estimated_realized_st_usd: str
    estimated_realized_lt_usd: str
    estimated_tax_benefit_usd: str | None
    estimated_tax_benefit_status: str
    lots_sold_count: int
    positions_exited_count: int
    orders_count: int
    cash_before_usd: str | None
    cash_after_usd: str | None
    portfolio_effects: PortfolioEffectsResponse | None
    constraints_satisfied: bool | None
    no_trade_reason: JSONValue | None
    warnings: list[str]
    tax_profile_configured: bool
    frozen_display_context: FrozenRunDisplayContextResponse
    optimizer_metrics: dict[str, JSONValue] = Field(default_factory=dict)


class OptimizerRecommendationsResponse(OptimizerRunResponse):
    groups: list[RecommendationGroupResponse]
    consolidated_legs: list[RecommendationLegResponse]


class WashTransactionResponse(StrictModel):
    broker_transaction_key: str
    ticker: str | None
    transaction_kind: Literal["BUY", "SELL", "DIVIDEND", "OTHER"]
    trade_date: date
    transaction_time: datetime
    shares: str
    source: str
    is_acquisition: bool


class WashAcquisitionResponse(WashTransactionResponse):
    lookback_window_end_date: date


class WashRestrictionResponse(StrictModel):
    run_id: str | None = None
    ticker: str
    trigger: str
    loss_sale_date: date
    source: str
    next_eligible_purchase_date: date
    validation: str


class WashSalesResponse(StrictModel):
    demo: Literal[True]
    source: str
    history: list[WashTransactionResponse]
    acquisitions: list[WashAcquisitionResponse]
    current_restrictions: list[WashRestrictionResponse]
    proposed_restrictions: list[WashRestrictionResponse]
    warnings: list[str]


class EtradeAuthStatusResponse(StrictModel):
    status: Literal["disabled"]
    available: Literal[False]
    authenticated: Literal[False]
    account_id_key: None
    phase: Literal[3]
    message: str


class OptimizerExportMetadataResponse(StrictModel):
    run_id: str
    policy_revision_id: str
    source_generation: int
    as_of: datetime
    proposed_trade_date: date | None
    solver_version: str
    demo: bool
    mode: Literal["recommendations_only", "real_optimizer"] = "recommendations_only"
    actionable: Literal[False]
    input_fingerprint: str | None
    source_checksum: str | None
    warnings: list[str]
    frozen_display_context: FrozenRunDisplayContextResponse
    optimizer_metrics: dict[str, JSONValue] = Field(default_factory=dict)


class OptimizerExportJSONResponse(StrictModel):
    metadata: OptimizerExportMetadataResponse
    run: OptimizerRecommendationsResponse
