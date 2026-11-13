/* Generated from backend/openapi.json. Do not edit by hand. */
export type JSONValue = string | number | boolean | null | JSONValue[] | { [key: string]: JSONValue };

export type ActivityEventResponse = {
  "id": string;
  "created_at": string;
  "event_type": string;
  "status": string;
  "correlation_id": string;
  "details": JSONValue;
};

export type ActivityPageResponse = {
  "items": Array<ActivityEventResponse>;
  "total": number;
  "offset": number;
  "limit": number;
};

export type AllocationResponse = {
  "current": AllocationWeightsResponse | null;
  "proposed": AllocationWeightsResponse | null;
  "target": AllocationTargetResponse | null;
};

export type AllocationTargetResponse = {
  "sleeve_weights_pct": Record<string, string>;
};

export type AllocationWeightsResponse = {
  "total_portfolio_usd": string;
  "sleeve_weights_pct": Record<string, string>;
};

export type AllowedSecurityInput = {
  "ticker": string;
  "sleeve_key": string;
  "sub_sleeve_key"?: string | null;
  "replacement_set_id"?: string;
  "priority"?: number;
  "enabled"?: boolean;
  "exposure_suitability"?: string | null;
};

export type AllowedSecurityResponse = {
  "ticker": string;
  "sleeve_key": string;
  "sub_sleeve_key": string | null;
  "replacement_set_id": string;
  "priority": number;
  "enabled": boolean;
  "exposure_suitability": string | null;
};

export type CoverageResponse = {
  "positions": boolean;
  "lots": boolean;
  "transactions": boolean;
  "balances": boolean;
  "quotes": boolean;
  "lookthrough"?: boolean;
};

export type ErrorEnvelope = {
  "code": string;
  "message": string;
  "details": JSONValue;
  "correlation_id": string;
};

export type EtradeAuthStatusResponse = {
  "status": "disabled";
  "available": false;
  "authenticated": false;
  "account_id_key": null;
  "phase": 3;
  "message": string;
};

export type FrozenRunDisplayContextResponse = {
  "available": boolean;
  "source": "frozen_input_bundle" | "policy_revision" | null;
  "policy_revision_id": string;
  "revision_number": number | null;
  "created_at": string | null;
  "activated_at": string | null;
  "sleeves": Array<RunPolicySleeveResponse> | null;
  "settings": Record<string, JSONValue> | null;
  "allowed_securities": Array<RunPolicyAllowedSecurityResponse> | null;
  "overrides": Array<RunPolicyOverrideResponse> | null;
  "unavailable_reason": string | null;
};

export type GroupImpactResponse = {
  "demo": true;
  "wash_status": "not_validated_demo";
  "selected_sell_lots_count": number;
  "sell_proceeds_usd": string;
  "realized_st_usd": string;
  "realized_lt_usd": string;
  "replacement_buy_shares": string;
  "replacement_buy_cost_usd": string;
  "cash_after_usd": string;
  "portfolio_effects": PortfolioEffectsResponse;
  "risk_tracking_score": null;
};

export type HealthResponse = {
  "status": "ok" | "not_ready";
  "schema_ready": boolean;
  "broker_mode": string;
  "live_broker_enabled": false;
  "order_submission_enabled": false;
};

export type LotPageResponse = {
  "items": Array<LotResponse>;
  "total": number;
  "offset": number;
  "limit": number;
  "source_generation": number | null;
};

export type LotResponse = {
  "ticker": string;
  "asset_type": "EQUITY" | "ETF";
  "broker_lot_id": string;
  "acquired_date": string;
  "remaining_shares": string;
  "available_shares": string;
  "adjusted_unit_basis_usd": string;
  "adjusted_total_basis_usd": string;
  "current_price_usd": string | null;
  "unrealized_pl_usd": string | null;
  "unrealized_pl_pct": string | null;
  "source": string;
  "as_of": string;
  "term": "ST" | "LT";
  "sleeve_key": string | null;
  "sub_sleeve_key": string | null;
  "quality_flags": Array<string>;
  "small_lot_cleanup_candidate": boolean;
  "position_cleanup_candidate": boolean;
  "whole_shares_available": string;
  "fractional_shares": string;
  "fractional_cleanup_unsupported": boolean;
};

export type OptimizerExportJSONResponse = {
  "metadata": OptimizerExportMetadataResponse;
  "run": OptimizerRecommendationsResponse;
};

export type OptimizerExportMetadataResponse = {
  "run_id": string;
  "policy_revision_id": string;
  "source_generation": number;
  "as_of": string;
  "proposed_trade_date": string | null;
  "solver_version": "DEMO";
  "demo": true;
  "actionable": false;
  "input_fingerprint": string | null;
  "source_checksum": string | null;
  "warnings": Array<string>;
  "frozen_display_context": FrozenRunDisplayContextResponse;
};

export type OptimizerLotReviewIntentInput = {
  "source_generation": number;
  "broker_lot_ids": Array<string>;
};

export type OptimizerRecommendationsResponse = {
  "run_id": string;
  "status": "demo";
  "mode": "recommendations_only";
  "policy_revision_id": string;
  "source_generation": number;
  "as_of": string;
  "solver_version": "DEMO";
  "proposed_trade_date"?: string | null;
  "demo": true;
  "actionable": false;
  "input_fingerprint": string | null;
  "source_checksum": string | null;
  "batch_settings": Record<string, JSONValue>;
  "estimated_realized_st_usd": string;
  "estimated_realized_lt_usd": string;
  "estimated_tax_benefit_usd": null;
  "estimated_tax_benefit_status": "tax_profile_incomplete" | "optimizer_unavailable";
  "lots_sold_count": number;
  "positions_exited_count": number;
  "orders_count": number;
  "cash_before_usd": string | null;
  "cash_after_usd": string | null;
  "portfolio_effects": PortfolioEffectsResponse | null;
  "constraints_satisfied": null;
  "no_trade_reason": JSONValue | null;
  "warnings": Array<string>;
  "tax_profile_configured": boolean;
  "frozen_display_context": FrozenRunDisplayContextResponse;
  "groups": Array<RecommendationGroupResponse>;
  "consolidated_legs": Array<RecommendationLegResponse>;
};

export type OptimizerRunInput = {
  "mode"?: "recommendations_only" | "real_optimizer";
  "proposed_trade_date"?: string | null;
  "max_sell_tickers_per_batch"?: number | null;
  "max_sell_lots_per_batch"?: number | null;
  "max_total_orders_per_batch"?: number | null;
};

export type OptimizerRunResponse = {
  "run_id": string;
  "status": "demo";
  "mode": "recommendations_only";
  "policy_revision_id": string;
  "source_generation": number;
  "as_of": string;
  "solver_version": "DEMO";
  "proposed_trade_date"?: string | null;
  "demo": true;
  "actionable": false;
  "input_fingerprint": string | null;
  "source_checksum": string | null;
  "batch_settings": Record<string, JSONValue>;
  "estimated_realized_st_usd": string;
  "estimated_realized_lt_usd": string;
  "estimated_tax_benefit_usd": null;
  "estimated_tax_benefit_status": "tax_profile_incomplete" | "optimizer_unavailable";
  "lots_sold_count": number;
  "positions_exited_count": number;
  "orders_count": number;
  "cash_before_usd": string | null;
  "cash_after_usd": string | null;
  "portfolio_effects": PortfolioEffectsResponse | null;
  "constraints_satisfied": null;
  "no_trade_reason": JSONValue | null;
  "warnings": Array<string>;
  "tax_profile_configured": boolean;
  "frozen_display_context": FrozenRunDisplayContextResponse;
};

export type OptimizerSelectionInput = {
  "selected_group_ids"?: Array<string>;
  "selected_sell_lots"?: Record<string, Array<string>>;
};

export type OverrideInput = {
  "ticker": string;
  "sleeve_key": string;
  "sub_sleeve_key"?: string | null;
};

export type PolicyDraftInput = {
  "settings": PolicySettingsInput;
  "sleeves": Array<SleeveInput>;
  "allowed_securities"?: Array<AllowedSecurityInput>;
  "overrides"?: Array<OverrideInput>;
  "reassignments"?: Record<string, string>;
  "source_revision_id"?: string | null;
};

export type PolicyOverrideResponse = {
  "ticker": string;
  "sleeve_key": string;
  "sub_sleeve_key": string | null;
};

export type PolicyResponse = {
  "active": PolicyRevisionResponse | null;
  "drafts": Array<PolicyRevisionResponse>;
  "superseded": Array<PolicyRevisionResponse>;
};

export type PolicyRevisionResponse = {
  "id": string;
  "revision_number": number;
  "status": "DRAFT" | "ACTIVE" | "SUPERSEDED";
  "created_at": string;
  "activated_at": string | null;
  "settings": PolicySettingsResponse;
  "sleeves": Array<PolicySleeveResponse>;
  "allowed_securities": Array<AllowedSecurityResponse>;
  "overrides": Array<PolicyOverrideResponse>;
  "activation_errors"?: Array<PolicyValidationErrorResponse> | null;
};

export type PolicySettingsInput = {
  "short_term_tax_rate"?: string | null;
  "long_term_tax_rate"?: string | null;
  "st_loss_carryforward_usd"?: string;
  "lt_loss_carryforward_usd"?: string;
  "ytd_realized_st_usd"?: string;
  "ytd_realized_lt_usd"?: string;
  "ytd_source"?: string | null;
  "ytd_as_of"?: string | null;
  "target_retained_net_loss_usd"?: string;
  "ordinary_income_deduction_limit_usd"?: string;
  "carryforward_loss_discount_factor"?: string;
  "gain_budget_usd"?: string | null;
  "max_incremental_tax_cost_usd"?: string | null;
  "st_gain_limit_usd"?: string | null;
  "lt_gain_limit_usd"?: string | null;
  "budget_period"?: string;
  "max_sell_tickers_per_batch"?: number;
  "max_sell_lots_per_batch"?: number;
  "max_total_orders_per_batch"?: number;
  "max_batch_turnover_pct"?: string;
  "min_buy_order_notional_usd"?: string;
  "cash_reserve_usd"?: string;
  "prefer_etf_buys"?: boolean;
  "allow_gain_sales"?: boolean;
  "permit_etf_harvest"?: boolean;
  "permit_muni_exit"?: boolean;
  "objective_band_weight"?: string | null;
  "objective_allocation_weight"?: string | null;
  "objective_tax_weight"?: string | null;
  "objective_trading_cost_weight"?: string | null;
  "objective_turnover_weight"?: string | null;
  "objective_cleanup_weight"?: string | null;
  "estimated_spread_bps"?: string | null;
  "estimated_fee_per_order_usd"?: string | null;
};

export type PolicySettingsResponse = {
  "short_term_tax_rate": string | null;
  "long_term_tax_rate": string | null;
  "st_loss_carryforward_usd": string;
  "lt_loss_carryforward_usd": string;
  "ytd_realized_st_usd": string;
  "ytd_realized_lt_usd": string;
  "ytd_source": string | null;
  "ytd_as_of": string | null;
  "target_retained_net_loss_usd": string;
  "ordinary_income_deduction_limit_usd": string;
  "carryforward_loss_discount_factor": string;
  "gain_budget_usd": string | null;
  "max_incremental_tax_cost_usd": string | null;
  "st_gain_limit_usd": string | null;
  "lt_gain_limit_usd": string | null;
  "budget_period": string;
  "max_sell_tickers_per_batch": number;
  "max_sell_lots_per_batch": number;
  "max_total_orders_per_batch": number;
  "max_batch_turnover_pct": string;
  "min_buy_order_notional_usd": string;
  "cash_reserve_usd": string;
  "prefer_etf_buys": boolean;
  "allow_gain_sales": boolean;
  "permit_etf_harvest": boolean;
  "objective_band_weight": string | null;
  "objective_allocation_weight": string | null;
  "objective_tax_weight": string | null;
  "objective_trading_cost_weight": string | null;
  "objective_turnover_weight": string | null;
  "objective_cleanup_weight": string | null;
  "estimated_spread_bps": string | null;
  "estimated_fee_per_order_usd": string | null;
  "permit_muni_exit": boolean;
};

export type PolicySleeveResponse = {
  "sleeve_key": string;
  "display_name": string;
  "sort_order": number;
  "parent_sleeve_key": string | null;
  "target_pct": string;
  "drift_band_pp": string;
  "is_direct_index_container": boolean;
  "is_direct_index_sleeve": boolean;
  "is_transition_destination": boolean;
  "is_cash_sleeve": boolean;
  "enabled": boolean;
};

export type PolicyValidationErrorResponse = {
  "code": string;
  "message": string;
};

export type PortfolioAccountResponse = {
  "display_name": string;
  "account_type": string;
  "tax_treatment": string | null;
};

export type PortfolioEffectsResponse = {
  "allocation": AllocationResponse;
  "us_transition": USTransitionResponse | null;
};

export type PortfolioNotSyncedResponse = {
  "status": "not_synced";
  "demo": boolean;
  "account": null;
  "as_of": null;
  "cash_usd": string;
  "portfolio_total_usd": string;
  "positions": Array<PositionResponse>;
  "coverage": Record<string, boolean>;
  "sync": SyncStatusResponse;
  "allocation": AllocationResponse;
  "us_transition": null;
};

export type PortfolioReadyResponse = {
  "status": "ready";
  "demo": boolean;
  "source": string;
  "account": PortfolioAccountResponse;
  "as_of": string;
  "cash_usd": string;
  "settled_buying_power_usd": string;
  "positions_market_value_usd": string;
  "portfolio_total_usd": string;
  "position_count": number;
  "positions": Array<PositionResponse>;
  "active_policy_revision_id": string | null;
  "unassigned_tickers": Array<string>;
  "coverage": Record<string, boolean>;
  "sync": SyncStatusResponse;
  "allocation": AllocationResponse;
  "us_transition": USTransitionResponse | null;
};

export type PositionResponse = {
  "ticker": string;
  "asset_type": "EQUITY" | "ETF";
  "shares": string;
  "market_value_usd": string;
  "last_price_usd": string | null;
  "quote_source": string | null;
  "quote_as_of": string | null;
  "sleeve_key": string | null;
  "sub_sleeve_key": string | null;
};

export type RecommendationAnnotationInput = {
  "note"?: string | null;
  "rejected"?: boolean | null;
  "rejection_reason"?: string | null;
};

export type RecommendationGroupResponse = {
  "group_id": string;
  "rank": number;
  "group_type": "demo_loss_harvest";
  "sleeve_key": string;
  "rationale": string;
  "estimated_benefit_usd": null;
  "impact": GroupImpactResponse;
  "dependencies": Array<string>;
  "selected": boolean;
  "rejected": boolean;
  "note": string | null;
  "rejection_reason": string | null;
  "leg_ids": Array<string>;
  "warnings": Array<string>;
};

export type RecommendationLegResponse = {
  "leg_id": string;
  "side": "BUY" | "SELL";
  "ticker": string | null;
  "shares": string;
  "estimated_unit_price_usd": string;
  "estimated_notional_usd": string;
  "net_st_realized_usd": string;
  "selected": boolean;
  "group_ids": Array<string>;
  "net_lt_realized_usd": string;
  "sequence": number;
  "dependencies": Array<string>;
  "selected_lots": Array<SelectedLotResponse>;
  "details": Record<string, JSONValue>;
};

export type RunPolicyAllowedSecurityResponse = {
  "ticker": string;
  "sleeve_key": string;
  "sub_sleeve_key": string | null;
  "replacement_set_id": string;
  "priority": number;
  "enabled": boolean;
  "exposure_suitability": string | null;
};

export type RunPolicyOverrideResponse = {
  "ticker": string;
  "sleeve_key": string;
  "sub_sleeve_key": string | null;
};

export type RunPolicySleeveResponse = {
  "sleeve_key": string;
  "display_name": string;
  "sort_order": number;
  "parent_sleeve_key": string | null;
  "target_pct": string | null;
  "drift_band_pp": string | null;
  "enabled": boolean;
  "is_direct_index_container": boolean;
  "is_direct_index_sleeve": boolean;
  "is_transition_destination": boolean;
  "is_cash_sleeve": boolean;
};

export type SelectedLotResponse = {
  "broker_lot_id": string;
  "shares": string;
  "acquired_date": string;
  "adjusted_basis_usd": string;
  "st_lt": "ST" | "LT";
  "realized_pl_usd": string;
  "selected": boolean;
};

export type SleeveInput = {
  "sleeve_key": string;
  "display_name": string;
  "sort_order"?: number;
  "parent_sleeve_key"?: string | null;
  "target_pct"?: string;
  "drift_band_pp"?: string;
  "is_direct_index_container"?: boolean;
  "is_direct_index_sleeve"?: boolean;
  "is_transition_destination"?: boolean;
  "is_cash_sleeve"?: boolean;
  "enabled"?: boolean;
};

export type SyncResponseDTO = {
  "generation": number;
  "status": "complete";
  "as_of": string;
  "coverage": CoverageResponse;
  "account": string;
  "demo": boolean;
};

export type SyncStatusResponse = {
  "generation": number;
  "complete": boolean;
  "started_at": string | null;
  "completed_at": string | null;
  "last_error_code": string | null;
  "last_error_summary": string | null;
};

export type TransitionChildResponse = {
  "value_usd": string;
  "within_us_sleeve_pct": string;
  "whole_portfolio_pct": string;
};

export type TransitionSnapshotResponse = {
  "us_sleeve_value_usd": string;
  "us_sleeve_whole_portfolio_pct": string;
  "etf_progress_pct": string | null;
  "children": Record<string, TransitionChildResponse>;
};

export type TransitionTargetChildResponse = {
  "within_us_sleeve_pct": string;
  "whole_portfolio_pct": string;
};

export type TransitionTargetResponse = {
  "us_sleeve_whole_portfolio_pct": string;
  "children": Record<string, TransitionTargetChildResponse>;
};

export type USTransitionResponse = {
  "sleeve_key": string;
  "transition_destination_sleeve_key": string | null;
  "label": string;
  "current": TransitionSnapshotResponse;
  "proposed_basket": TransitionSnapshotResponse;
  "target": TransitionTargetResponse;
};

export type WashAcquisitionResponse = {
  "broker_transaction_key": string;
  "ticker": string | null;
  "transaction_kind": "BUY" | "SELL" | "DIVIDEND" | "OTHER";
  "trade_date": string;
  "transaction_time": string;
  "shares": string;
  "source": string;
  "is_acquisition": boolean;
  "lookback_window_end_date": string;
};

export type WashRestrictionResponse = {
  "run_id"?: string | null;
  "ticker": string;
  "trigger": string;
  "loss_sale_date": string;
  "source": string;
  "next_eligible_purchase_date": string;
  "validation": string;
};

export type WashSalesResponse = {
  "demo": true;
  "source": string;
  "history": Array<WashTransactionResponse>;
  "acquisitions": Array<WashAcquisitionResponse>;
  "current_restrictions": Array<WashRestrictionResponse>;
  "proposed_restrictions": Array<WashRestrictionResponse>;
  "warnings": Array<string>;
};

export type WashTransactionResponse = {
  "broker_transaction_key": string;
  "ticker": string | null;
  "transaction_kind": "BUY" | "SELL" | "DIVIDEND" | "OTHER";
  "trade_date": string;
  "transaction_time": string;
  "shares": string;
  "source": string;
  "is_acquisition": boolean;
};

export interface ApiOperations {
  "GET /health": {
    path: Record<never, never>;
    query: Record<never, never>;
    request: never;
    responses: {
      "200": HealthResponse;
      "403": ErrorEnvelope;
      "404": ErrorEnvelope;
      "409": ErrorEnvelope;
      "422": ErrorEnvelope;
      "500": ErrorEnvelope;
      "502": ErrorEnvelope;
      "503": ErrorEnvelope;
    };
  };
  "POST /api/v1/portfolio/sync": {
    path: Record<never, never>;
    query: Record<never, never>;
    request: never;
    responses: {
      "200": SyncResponseDTO;
      "403": ErrorEnvelope;
      "404": ErrorEnvelope;
      "409": ErrorEnvelope;
      "422": ErrorEnvelope;
      "500": ErrorEnvelope;
      "502": ErrorEnvelope;
      "503": ErrorEnvelope;
    };
  };
  "GET /api/v1/portfolio": {
    path: Record<never, never>;
    query: Record<never, never>;
    request: never;
    responses: {
      "200": PortfolioNotSyncedResponse | PortfolioReadyResponse;
      "403": ErrorEnvelope;
      "404": ErrorEnvelope;
      "409": ErrorEnvelope;
      "422": ErrorEnvelope;
      "500": ErrorEnvelope;
      "502": ErrorEnvelope;
      "503": ErrorEnvelope;
    };
  };
  "GET /api/v1/lots": {
    path: Record<never, never>;
    query: {
  "ticker"?: string | null;
  "term"?: string | null;
  "fractional"?: boolean | null;
  "search"?: string | null;
  "sort_by"?: "ticker" | "broker_lot_id" | "acquired_date" | "remaining_shares" | "available_shares" | "adjusted_unit_basis_usd" | "adjusted_total_basis_usd" | "current_price_usd" | "unrealized_pl_usd" | "unrealized_pl_pct" | "term" | "sleeve_key" | "sub_sleeve_key";
  "sort_direction"?: "asc" | "desc";
  "offset"?: number;
  "limit"?: number;
};
    request: never;
    responses: {
      "200": LotPageResponse;
      "403": ErrorEnvelope;
      "404": ErrorEnvelope;
      "409": ErrorEnvelope;
      "422": ErrorEnvelope;
      "500": ErrorEnvelope;
      "502": ErrorEnvelope;
      "503": ErrorEnvelope;
    };
  };
  "GET /api/v1/policy": {
    path: Record<never, never>;
    query: Record<never, never>;
    request: never;
    responses: {
      "200": PolicyResponse;
      "403": ErrorEnvelope;
      "404": ErrorEnvelope;
      "409": ErrorEnvelope;
      "422": ErrorEnvelope;
      "500": ErrorEnvelope;
      "502": ErrorEnvelope;
      "503": ErrorEnvelope;
    };
  };
  "POST /api/v1/policy/drafts": {
    path: Record<never, never>;
    query: Record<never, never>;
    request: PolicyDraftInput;
    responses: {
      "201": PolicyRevisionResponse;
      "403": ErrorEnvelope;
      "404": ErrorEnvelope;
      "409": ErrorEnvelope;
      "422": ErrorEnvelope;
      "500": ErrorEnvelope;
      "502": ErrorEnvelope;
      "503": ErrorEnvelope;
    };
  };
  "POST /api/v1/policy/{revision_id}/activate": {
    path: {
  "revision_id": string;
};
    query: Record<never, never>;
    request: never;
    responses: {
      "200": PolicyRevisionResponse;
      "403": ErrorEnvelope;
      "404": ErrorEnvelope;
      "409": ErrorEnvelope;
      "422": ErrorEnvelope;
      "500": ErrorEnvelope;
      "502": ErrorEnvelope;
      "503": ErrorEnvelope;
    };
  };
  "GET /api/v1/activity": {
    path: Record<never, never>;
    query: {
  "offset"?: number;
  "limit"?: number;
  "event_type"?: string | null;
  "status"?: string | null;
  "correlation_id"?: string | null;
  "since"?: string | null;
  "until"?: string | null;
};
    request: never;
    responses: {
      "200": ActivityPageResponse;
      "403": ErrorEnvelope;
      "404": ErrorEnvelope;
      "409": ErrorEnvelope;
      "422": ErrorEnvelope;
      "500": ErrorEnvelope;
      "502": ErrorEnvelope;
      "503": ErrorEnvelope;
    };
  };
  "POST /api/v1/optimizer/runs": {
    path: Record<never, never>;
    query: Record<never, never>;
    request: OptimizerRunInput;
    responses: {
      "201": OptimizerRecommendationsResponse;
      "403": ErrorEnvelope;
      "404": ErrorEnvelope;
      "409": ErrorEnvelope;
      "422": ErrorEnvelope;
      "500": ErrorEnvelope;
      "502": ErrorEnvelope;
      "503": ErrorEnvelope;
    };
  };
  "GET /api/v1/optimizer/runs/{run_id}": {
    path: {
  "run_id": string;
};
    query: Record<never, never>;
    request: never;
    responses: {
      "200": OptimizerRunResponse;
      "403": ErrorEnvelope;
      "404": ErrorEnvelope;
      "409": ErrorEnvelope;
      "422": ErrorEnvelope;
      "500": ErrorEnvelope;
      "502": ErrorEnvelope;
      "503": ErrorEnvelope;
    };
  };
  "GET /api/v1/optimizer/runs/{run_id}/recommendations": {
    path: {
  "run_id": string;
};
    query: Record<never, never>;
    request: never;
    responses: {
      "200": OptimizerRecommendationsResponse;
      "403": ErrorEnvelope;
      "404": ErrorEnvelope;
      "409": ErrorEnvelope;
      "422": ErrorEnvelope;
      "500": ErrorEnvelope;
      "502": ErrorEnvelope;
      "503": ErrorEnvelope;
    };
  };
  "POST /api/v1/optimizer/runs/{run_id}/selection": {
    path: {
  "run_id": string;
};
    query: Record<never, never>;
    request: OptimizerSelectionInput;
    responses: {
      "200": OptimizerRecommendationsResponse;
      "403": ErrorEnvelope;
      "404": ErrorEnvelope;
      "409": ErrorEnvelope;
      "422": ErrorEnvelope;
      "500": ErrorEnvelope;
      "502": ErrorEnvelope;
      "503": ErrorEnvelope;
    };
  };
  "POST /api/v1/optimizer/runs/{run_id}/lot-review-intent": {
    path: {
  "run_id": string;
};
    query: Record<never, never>;
    request: OptimizerLotReviewIntentInput;
    responses: {
      "200": OptimizerRecommendationsResponse;
      "403": ErrorEnvelope;
      "404": ErrorEnvelope;
      "409": ErrorEnvelope;
      "422": ErrorEnvelope;
      "500": ErrorEnvelope;
      "502": ErrorEnvelope;
      "503": ErrorEnvelope;
    };
  };
  "PATCH /api/v1/optimizer/runs/{run_id}/recommendations/{group_id}": {
    path: {
  "run_id": string;
  "group_id": string;
};
    query: Record<never, never>;
    request: RecommendationAnnotationInput;
    responses: {
      "200": OptimizerRecommendationsResponse;
      "403": ErrorEnvelope;
      "404": ErrorEnvelope;
      "409": ErrorEnvelope;
      "422": ErrorEnvelope;
      "500": ErrorEnvelope;
      "502": ErrorEnvelope;
      "503": ErrorEnvelope;
    };
  };
  "GET /api/v1/optimizer/runs/{run_id}/export": {
    path: {
  "run_id": string;
};
    query: {
  "format"?: string;
};
    request: never;
    responses: {
      "200": OptimizerExportJSONResponse | string;
      "403": ErrorEnvelope;
      "404": ErrorEnvelope;
      "409": ErrorEnvelope;
      "422": ErrorEnvelope;
      "500": ErrorEnvelope;
      "502": ErrorEnvelope;
      "503": ErrorEnvelope;
    };
  };
  "GET /api/v1/wash-sales": {
    path: Record<never, never>;
    query: Record<never, never>;
    request: never;
    responses: {
      "200": WashSalesResponse;
      "403": ErrorEnvelope;
      "404": ErrorEnvelope;
      "409": ErrorEnvelope;
      "422": ErrorEnvelope;
      "500": ErrorEnvelope;
      "502": ErrorEnvelope;
      "503": ErrorEnvelope;
    };
  };
  "GET /api/v1/auth/etrade/status": {
    path: Record<never, never>;
    query: Record<never, never>;
    request: never;
    responses: {
      "200": EtradeAuthStatusResponse;
      "403": ErrorEnvelope;
      "404": ErrorEnvelope;
      "409": ErrorEnvelope;
      "422": ErrorEnvelope;
      "500": ErrorEnvelope;
      "502": ErrorEnvelope;
      "503": ErrorEnvelope;
    };
  };
  "POST /api/v1/auth/etrade/start": {
    path: Record<never, never>;
    query: Record<never, never>;
    request: never;
    responses: {
      "503": ErrorEnvelope;
      "403": ErrorEnvelope;
      "404": ErrorEnvelope;
      "409": ErrorEnvelope;
      "422": ErrorEnvelope;
      "500": ErrorEnvelope;
      "502": ErrorEnvelope;
    };
  };
  "POST /api/v1/auth/etrade/verify": {
    path: Record<never, never>;
    query: Record<never, never>;
    request: never;
    responses: {
      "503": ErrorEnvelope;
      "403": ErrorEnvelope;
      "404": ErrorEnvelope;
      "409": ErrorEnvelope;
      "422": ErrorEnvelope;
      "500": ErrorEnvelope;
      "502": ErrorEnvelope;
    };
  };
  "POST /api/v1/orders/{leg_id}/preview": {
    path: {
  "leg_id": string;
};
    query: Record<never, never>;
    request: never;
    responses: {
      "503": ErrorEnvelope;
      "403": ErrorEnvelope;
      "404": ErrorEnvelope;
      "409": ErrorEnvelope;
      "422": ErrorEnvelope;
      "500": ErrorEnvelope;
      "502": ErrorEnvelope;
    };
  };
  "POST /api/v1/orders/{leg_id}/submit": {
    path: {
  "leg_id": string;
};
    query: Record<never, never>;
    request: never;
    responses: {
      "503": ErrorEnvelope;
      "403": ErrorEnvelope;
      "404": ErrorEnvelope;
      "409": ErrorEnvelope;
      "422": ErrorEnvelope;
      "500": ErrorEnvelope;
      "502": ErrorEnvelope;
    };
  };
}

export type ApiOperationName = keyof ApiOperations;
export type ApiPath<K extends ApiOperationName> = ApiOperations[K]['path'];
export type ApiQuery<K extends ApiOperationName> = ApiOperations[K]['query'];
export type ApiRequest<K extends ApiOperationName> = ApiOperations[K]['request'];
export type ApiResponse<K extends ApiOperationName> = ApiOperations[K]['responses'][keyof ApiOperations[K]['responses']];
export type ApiSuccessResponse<K extends ApiOperationName> = {
  [S in keyof ApiOperations[K]['responses']]: `${S & (string | number)}` extends `2${string}`
    ? ApiOperations[K]['responses'][S]
    : never
}[keyof ApiOperations[K]['responses']];
