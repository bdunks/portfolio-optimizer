from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from app.domain.allocation import (
    AllocationPolicy,
    AllocationSleeve,
    AllowedSecurity,
    SecurityIdentity,
    SecurityOverride,
    SleeveAssignment,
    resolve_holding,
)

type SettingValue = Decimal | date | bool | int | str | None

_DECIMAL_SETTINGS = frozenset(
    {
        "short_term_tax_rate",
        "long_term_tax_rate",
        "st_loss_carryforward_usd",
        "lt_loss_carryforward_usd",
        "ytd_realized_st_usd",
        "ytd_realized_lt_usd",
        "target_retained_net_loss_usd",
        "ordinary_income_deduction_limit_usd",
        "carryforward_loss_discount_factor",
        "gain_budget_usd",
        "max_incremental_tax_cost_usd",
        "st_gain_limit_usd",
        "lt_gain_limit_usd",
        "max_batch_turnover_pct",
        "min_buy_order_notional_usd",
        "cash_reserve_usd",
        "objective_band_weight",
        "objective_allocation_weight",
        "objective_tax_weight",
        "objective_trading_cost_weight",
        "objective_turnover_weight",
        "objective_cleanup_weight",
        "estimated_spread_bps",
        "estimated_fee_per_order_usd",
    }
)
_INT_SETTINGS = frozenset(
    {"max_sell_tickers_per_batch", "max_sell_lots_per_batch", "max_total_orders_per_batch"}
)
_BOOL_SETTINGS = frozenset(
    {"prefer_etf_buys", "allow_gain_sales", "permit_etf_harvest", "permit_muni_exit"}
)
_DATE_SETTINGS = frozenset({"ytd_as_of"})


def _parse_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise TypeError("date provenance is missing or malformed")


def _parse_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        result = datetime.fromisoformat(value)
    else:
        raise TypeError("datetime provenance is missing or malformed")
    return result


def _lot_sync_generation(row: dict[str, object], bundle: dict[str, object]) -> int:
    if "sync_generation" in row:
        return int(row["sync_generation"])
    if bundle.get("schema") == "demo-run-input-v1":
        return int(bundle["source_generation"])
    raise TypeError("frozen lot has no sync_generation")


def _iso_datetime(value: datetime) -> str:
    return value.isoformat()


def _decimal(value: object | None) -> Decimal | None:
    if value is None:
        return None
    return value if isinstance(value, Decimal) else Decimal(str(value))


@dataclass(frozen=True, slots=True)
class PolicySettings:
    """Immutable, lossless typed settings; stored as sorted immutable key/value pairs."""

    values: tuple[tuple[str, SettingValue], ...]

    @classmethod
    def from_mapping(cls, values: dict[str, object]) -> PolicySettings:
        parsed: list[tuple[str, SettingValue]] = []
        for key, value in sorted(values.items()):
            if key in _DECIMAL_SETTINGS:
                parsed_value: SettingValue = _decimal(value)
            elif key in _INT_SETTINGS:
                parsed_value = int(value) if value is not None else None
            elif key in _BOOL_SETTINGS:
                if not isinstance(value, bool):
                    raise ValueError(f"policy setting {key} must be a boolean")
                parsed_value = value
            elif key in _DATE_SETTINGS:
                parsed_value = _parse_date(value) if value is not None else None
            elif value is None or isinstance(value, str):
                parsed_value = value
            else:
                raise ValueError(f"unsupported policy setting type for {key}")
            parsed.append((key, parsed_value))
        return cls(tuple(parsed))

    def get(self, key: str, default: SettingValue = None) -> SettingValue:
        return next((value for name, value in self.values if name == key), default)

    def to_provenance(self) -> dict[str, object]:
        return {
            name: value.isoformat() if isinstance(value, date) else str(value) if isinstance(value, Decimal) else value
            for name, value in self.values
        }


@dataclass(frozen=True, slots=True)
class PolicySectorBandInput:
    sector_key: str
    target_weight_pct: Decimal
    band_pct: Decimal


@dataclass(frozen=True, slots=True)
class PolicyInput:
    revision_id: str
    allocation: AllocationPolicy
    settings: PolicySettings
    revision_number: int = 0
    status: str = ""
    created_at: datetime | None = None
    activated_at: datetime | None = None
    sector_bands: tuple[PolicySectorBandInput, ...] = ()
    def to_provenance(self) -> dict[str, object]:
        return {
            "id": self.revision_id,
            "settings": self.settings.to_provenance(),
            "revision_number": self.revision_number,
            "status": self.status,
            "created_at": _iso_datetime(self.created_at) if self.created_at else None,
            "activated_at": _iso_datetime(self.activated_at) if self.activated_at else None,
            "sleeves": [
                {
                    "sleeve_key": row.key,
                    "display_name": row.display_name,
                    "sort_order": row.sort_order,
                    "parent_sleeve_key": row.parent_key,
                    "target_pct": str(row.target_pct) if row.target_pct is not None else None,
                    "drift_band_pp": str(row.drift_band_pp) if row.drift_band_pp is not None else None,
                    "enabled": row.enabled,
                    "is_direct_index_container": row.direct_index_container,
                    "is_direct_index_sleeve": row.direct_index_sleeve,
                    "is_transition_destination": row.transition_destination,
                    "is_cash_sleeve": row.cash_sleeve,
                }
                for row in self.allocation.sleeves
            ],
            "sector_bands": [
                {
                    "sector_key": row.sector_key,
                    "target_weight_pct": str(row.target_weight_pct),
                    "band_pct": str(row.band_pct),
                }
                for row in self.sector_bands
            ],
            "allowed_securities": [
                {
                    "ticker": row.ticker,
                    "sleeve_key": row.sleeve_key,
                    "sub_sleeve_key": row.sub_sleeve_key,
                    "replacement_set_id": row.replacement_set_id,
                    "priority": row.priority,
                    "enabled": row.enabled,
                    "exposure_suitability": row.exposure_suitability,
                }
                for row in self.allocation.allowed_securities
            ],
            "overrides": [
                {
                    "ticker": row.ticker,
                    "sleeve_key": row.sleeve_key,
                    "sub_sleeve_key": row.sub_sleeve_key,
                }
                for row in self.allocation.overrides
            ],
        }

@dataclass(frozen=True, slots=True)
class SecurityInput:
    identity: SecurityIdentity
    security_id: int | None = None
    tradable: bool = True


@dataclass(frozen=True, slots=True)
class AccountInput:
    local_account_id: int
    account_key_fingerprint: str
    display_name: str
    account_type: str
    tax_treatment: str | None
    source: str
    as_of: datetime
    cash_usd: Decimal
    settled_buying_power_usd: Decimal


@dataclass(frozen=True, slots=True)
class PositionInput:
    ticker: str
    asset_type: str
    is_completion_etf: bool
    shares: Decimal
    sync_generation: int
    as_of: datetime
    market_value_usd: Decimal
    assignment: SleeveAssignment | None


@dataclass(frozen=True, slots=True)
class LotInput:
    ticker: str
    broker_lot_id: str
    acquired_date: date
    shares: Decimal
    available_shares: Decimal
    adjusted_unit_basis_usd: Decimal
    broker_wash_adjustment_usd: Decimal | None
    source: str
    as_of: datetime
    fractional_cleanup_unsupported: bool
    quality_flags: tuple[str, ...]
    sync_generation: int


@dataclass(frozen=True, slots=True)
class QuoteInput:
    ticker: str
    bid_usd: Decimal | None
    ask_usd: Decimal | None
    last_usd: Decimal | None
    source: str
    as_of: datetime
    quality: str
    sync_generation: int


@dataclass(frozen=True, slots=True)
class TransactionInput:
    broker_transaction_key: str
    ticker: str
    transaction_kind: str
    transaction_time: datetime
    trade_date: date
    shares: Decimal
    amount_usd: Decimal
    is_acquisition: bool
    broker_lot_id: str | None
    source: str
    realized_pl_usd: Decimal | None = None


@dataclass(frozen=True, slots=True)
class LookThroughExposureInput:
    ticker: str
    dimension: str
    exposure_key: str
    weight: Decimal
    provider: str
    as_of_date: date


@dataclass(frozen=True, slots=True)
class InputSourceMetadata:
    sync_complete: bool | None = None
    sync_started_at: datetime | None = None
    sync_completed_at: datetime | None = None
    transaction_history_complete: bool | None = None
    transaction_history_start_date: date | None = None
    transaction_history_end_date: date | None = None
    lookthrough_complete: bool | None = None

    def to_provenance(self) -> dict[str, object]:
        return {
            "sync_complete": self.sync_complete,
            "sync_started_at": _iso_datetime(self.sync_started_at)
            if self.sync_started_at
            else None,
            "sync_completed_at": _iso_datetime(self.sync_completed_at)
            if self.sync_completed_at
            else None,
            "transaction_history_complete": self.transaction_history_complete,
            "transaction_history_start_date": (
                self.transaction_history_start_date.isoformat()
                if self.transaction_history_start_date
                else None
            ),
            "transaction_history_end_date": (
                self.transaction_history_end_date.isoformat()
                if self.transaction_history_end_date
                else None
            ),
            "lookthrough_complete": self.lookthrough_complete,
        }

    @classmethod
    def from_provenance(cls, value: object) -> InputSourceMetadata:
        if not isinstance(value, dict):
            return cls()

        def optional_bool(name: str) -> bool | None:
            result = value.get(name)
            return result if isinstance(result, bool) else None

        def optional_date(name: str) -> date | None:
            raw = value.get(name)
            if not isinstance(raw, str):
                return None
            try:
                return date.fromisoformat(raw)
            except ValueError:
                return None

        def optional_datetime(name: str) -> datetime | None:
            raw = value.get(name)
            if not isinstance(raw, str):
                return None
            try:
                return datetime.fromisoformat(raw)
            except ValueError:
                return None

        return cls(
            sync_complete=optional_bool("sync_complete"),
            sync_started_at=optional_datetime("sync_started_at"),
            sync_completed_at=optional_datetime("sync_completed_at"),
            transaction_history_complete=optional_bool("transaction_history_complete"),
            transaction_history_start_date=optional_date("transaction_history_start_date"),
            transaction_history_end_date=optional_date("transaction_history_end_date"),
            lookthrough_complete=optional_bool("lookthrough_complete"),
        )


@dataclass(frozen=True, slots=True)
class FinancialInputs:
    account: AccountInput
    source_generation: int
    proposed_trade_date: date
    policy: PolicyInput
    securities: tuple[SecurityInput, ...]
    positions: tuple[PositionInput, ...]
    lots: tuple[LotInput, ...]
    quotes: tuple[QuoteInput, ...]
    transactions: tuple[TransactionInput, ...]
    source_checksum: str | None = None
    exposures: tuple[LookThroughExposureInput, ...] = ()
    source_metadata: InputSourceMetadata = InputSourceMetadata()

    def quote_for(self, ticker: str) -> QuoteInput | None:
        return next((row for row in self.quotes if row.ticker == ticker), None)

    def security_for(self, ticker: str) -> SecurityInput | None:
        return next((row for row in self.securities if row.identity.ticker == ticker), None)

    def to_provenance(self) -> dict[str, object]:
        return {
            "schema": "demo-run-input-v2",
            "account": {
                "local_account_id": self.account.local_account_id,
                "account_key_fingerprint": self.account.account_key_fingerprint,
                "display_name": self.account.display_name,
                "account_type": self.account.account_type,
                "tax_treatment": self.account.tax_treatment,
                "source": self.account.source,
                "as_of": _iso_datetime(self.account.as_of),
                "cash_usd": str(self.account.cash_usd),
                "settled_buying_power_usd": str(self.account.settled_buying_power_usd),
            },
            "source_generation": self.source_generation,
            "proposed_trade_date": self.proposed_trade_date.isoformat(),
            "securities": [
                {
                    "security_id": row.security_id,
                    "ticker": row.identity.ticker,
                    "asset_type": row.identity.asset_type,
                    "is_completion_etf": row.identity.is_completion_etf,
                    "tradable": row.tradable,
                }
                for row in self.securities
            ],
            "positions": [
                {
                    "ticker": row.ticker,
                    "asset_type": row.asset_type,
                    "is_completion_etf": row.is_completion_etf,
                    "shares": str(row.shares),
                    "sync_generation": row.sync_generation,
                    "as_of": _iso_datetime(row.as_of),
                    "market_value_usd": str(row.market_value_usd),
                    "sleeve_key": row.assignment.sleeve_key if row.assignment is not None else None,
                    "sub_sleeve_key": row.assignment.sub_sleeve_key if row.assignment is not None else None,
                }
                for row in self.positions
            ],
            "lots": [
                {
                    "ticker": row.ticker,
                    "broker_lot_id": row.broker_lot_id,
                    "acquired_date": row.acquired_date.isoformat(),
                    "shares": str(row.shares),
                    "available_shares": str(row.available_shares),
                    "adjusted_unit_basis_usd": str(row.adjusted_unit_basis_usd),
                    "broker_wash_adjustment_usd": (
                        str(row.broker_wash_adjustment_usd)
                        if row.broker_wash_adjustment_usd is not None
                        else None
                    ),
                    "source": row.source,
                    "as_of": _iso_datetime(row.as_of),
                    "fractional_cleanup_unsupported": row.fractional_cleanup_unsupported,
                    "quality_flags": list(row.quality_flags),
                    "sync_generation": row.sync_generation,
                }
                for row in self.lots
            ],
            "quotes": {
                row.ticker: {
                    "bid_usd": str(row.bid_usd) if row.bid_usd is not None else None,
                    "ask_usd": str(row.ask_usd) if row.ask_usd is not None else None,
                    "last_usd": str(row.last_usd) if row.last_usd is not None else None,
                    "source": row.source,
                    "as_of": _iso_datetime(row.as_of),
                    "quality": row.quality,
                    "sync_generation": row.sync_generation,
                }
                for row in self.quotes
            },
            "policy": self.policy.to_provenance(),
            "transactions": [
                {
                    "broker_transaction_key": row.broker_transaction_key,
                    "ticker": row.ticker,
                    "transaction_kind": row.transaction_kind,
                    "transaction_time": _iso_datetime(row.transaction_time),
                    "trade_date": row.trade_date.isoformat(),
                    "shares": str(row.shares),
                    "amount_usd": str(row.amount_usd),
                    "realized_pl_usd": str(row.realized_pl_usd) if row.realized_pl_usd is not None else None,
                    "is_acquisition": row.is_acquisition,
                    "broker_lot_id": row.broker_lot_id,
                    "source": row.source,
                }
                for row in self.transactions
            ],
            "exposures": [
                {
                    "ticker": row.ticker,
                    "dimension": row.dimension,
                    "exposure_key": row.exposure_key,
                    "weight": str(row.weight),
                    "provider": row.provider,
                    "as_of_date": row.as_of_date.isoformat(),
                }
                for row in self.exposures
            ],
            "source_metadata": self.source_metadata.to_provenance(),
            "source_checksum": self.source_checksum,
        }


def financial_inputs_from_provenance(
    bundle: dict[str, object], *, proposed_trade_date: date | None = None
) -> FinancialInputs:
    """Rehydrate frozen JSON into the same immutable domain inputs used for current state."""
    account_data = bundle.get("account")
    policy_data = bundle.get("policy")
    if not isinstance(account_data, dict) or not isinstance(policy_data, dict):
        raise TypeError("frozen financial provenance is missing account or policy data")
    settings_data = policy_data.get("settings")
    sleeve_data = policy_data.get("sleeves")
    allowed_data = policy_data.get("allowed_securities")
    override_data = policy_data.get("overrides")
    sector_band_data = policy_data.get("sector_bands", [])
    if not isinstance(sector_band_data, list):
        raise ValueError("frozen sector band policy data is malformed")
    sector_bands = tuple(
        PolicySectorBandInput(
            sector_key=str(row["sector_key"]),
            target_weight_pct=Decimal(str(row["target_weight_pct"])),
            band_pct=Decimal(str(row["band_pct"])),
        )
        for row in sector_band_data
        if isinstance(row, dict)
    )
    if len(sector_bands) != len(sector_band_data):
        raise ValueError("frozen sector band policy data is malformed")
    if not all(isinstance(value, (dict, list)) for value in (settings_data, sleeve_data, allowed_data, override_data)):
        raise ValueError("frozen financial provenance contains malformed policy data")
    sleeves = tuple(
        AllocationSleeve(
            key=str(row["sleeve_key"]),
            parent_key=str(row["parent_sleeve_key"]) if row.get("parent_sleeve_key") is not None else None,
            enabled=bool(row["enabled"]),
            direct_index_container=bool(row.get("is_direct_index_container", False)),
            direct_index_sleeve=bool(row.get("is_direct_index_sleeve", False)),
            transition_destination=bool(row.get("is_transition_destination", False)),
            cash_sleeve=bool(row.get("is_cash_sleeve", False)),
            display_name=str(row.get("display_name", "")),
            sort_order=int(row.get("sort_order", 0)),
            target_pct=_decimal(row.get("target_pct")),
            drift_band_pp=_decimal(row.get("drift_band_pp")), 
        )
        for row in sleeve_data
        if isinstance(row, dict)
    )
    allowed = tuple(
        AllowedSecurity(
            ticker=str(row["ticker"]),
            sleeve_key=str(row["sleeve_key"]),
            sub_sleeve_key=str(row["sub_sleeve_key"]) if row.get("sub_sleeve_key") is not None else None,
            priority=int(row.get("priority", 0)),
            enabled=bool(row.get("enabled", False)),
            replacement_set_id=str(row.get("replacement_set_id", "default")),
            exposure_suitability=(
                str(row["exposure_suitability"]) if row.get("exposure_suitability") is not None else None
            ),
        )
        for row in allowed_data
        if isinstance(row, dict)
    )
    overrides = tuple(
        SecurityOverride(
            ticker=str(row["ticker"]),
            sleeve_key=str(row["sleeve_key"]),
            sub_sleeve_key=str(row["sub_sleeve_key"]) if row.get("sub_sleeve_key") is not None else None,
        )
        for row in override_data
        if isinstance(row, dict)
    )
    policy = PolicyInput(
        revision_id=str(policy_data.get("id", "")),
        allocation=AllocationPolicy(sleeves, allowed, overrides),
        settings=PolicySettings.from_mapping(settings_data),
        sector_bands=sector_bands,
        revision_number=int(policy_data.get("revision_number", 0)),
        status=str(policy_data.get("status", "")),
        created_at=_parse_datetime(policy_data["created_at"]) if policy_data.get("created_at") else None,
        activated_at=_parse_datetime(policy_data["activated_at"]) if policy_data.get("activated_at") else None,
    )

    raw_securities = bundle.get("securities")
    raw_positions = bundle.get("positions")
    if not isinstance(raw_positions, list):
        raise TypeError("frozen financial provenance is missing positions")
    security_inputs: dict[str, SecurityInput] = {}
    if isinstance(raw_securities, list):
        for row in raw_securities:
            if isinstance(row, dict) and isinstance(row.get("ticker"), str):
                identity = SecurityIdentity(
                    row["ticker"], str(row.get("asset_type", "ETF")), bool(row.get("is_completion_etf", False))
                )
                security_inputs[identity.ticker] = SecurityInput(
                    identity,
                    int(row["security_id"]) if row.get("security_id") is not None else None,
                    bool(row.get("tradable", True)),
                )
    for row in raw_positions:
        if isinstance(row, dict) and isinstance(row.get("ticker"), str):
            ticker = row["ticker"]
            identity = SecurityIdentity(
                ticker, str(row.get("asset_type", "EQUITY")), bool(row.get("is_completion_etf", False))
            )
            security_inputs.setdefault(ticker, SecurityInput(identity))
    for row in allowed_data:
        if isinstance(row, dict) and isinstance(row.get("ticker"), str):
            ticker = row["ticker"]
            security_inputs.setdefault(ticker, SecurityInput(SecurityIdentity(ticker, "ETF")))

    positions: list[PositionInput] = []
    for row in raw_positions:
        if not isinstance(row, dict):
            raise TypeError("frozen position data is malformed")
        ticker = str(row["ticker"])
        security = security_inputs[ticker].identity
        resolution = resolve_holding(policy.allocation, security)
        if resolution.assignment is None:
            raise ValueError(f"frozen position {ticker} has no valid policy assignment: {resolution.reason}")
        positions.append(
            PositionInput(
                ticker=ticker,
                asset_type=str(row["asset_type"]),
                is_completion_etf=bool(row.get("is_completion_etf", False)),
                shares=Decimal(str(row["shares"])),
                sync_generation=int(row["sync_generation"]),
                as_of=_parse_datetime(row["as_of"]),
                market_value_usd=Decimal(str(row["market_value_usd"])),
                assignment=resolution.assignment,
            )
        )

    raw_quotes = bundle.get("quotes")
    if not isinstance(raw_quotes, dict):
        raise TypeError("frozen financial provenance is missing quotes")
    quotes = tuple(
        QuoteInput(
            ticker=str(ticker),
            bid_usd=_decimal(row.get("bid_usd")),
            ask_usd=_decimal(row.get("ask_usd")),
            last_usd=_decimal(row.get("last_usd")),
            source=str(row["source"]),
            as_of=_parse_datetime(row["as_of"]),
            quality=str(row["quality"]),
            sync_generation=int(row["sync_generation"]),
        )
        for ticker, row in sorted(raw_quotes.items())
        if isinstance(row, dict)
    )
    raw_lots = bundle.get("lots")
    raw_transactions = bundle.get("transactions", [])

    raw_exposures = bundle.get("exposures", [])
    if not isinstance(raw_exposures, list):
        raise TypeError("frozen exposure data is malformed")
    exposure_rows: list[dict[str, object]] = []
    for row in raw_exposures:
        if not isinstance(row, dict):
            raise TypeError("frozen exposure data is malformed")
        exposure_rows.append(row)
    exposures = tuple(
        LookThroughExposureInput(
            ticker=str(row["ticker"]),
            dimension=str(row["dimension"]),
            exposure_key=str(row["exposure_key"]),
            weight=Decimal(str(row["weight"])),
            provider=str(row["provider"]),
            as_of_date=_parse_date(row["as_of_date"]),
        )
        for row in exposure_rows
    )
    source_metadata = InputSourceMetadata.from_provenance(bundle.get("source_metadata"))
    if not isinstance(raw_lots, list) or not isinstance(raw_transactions, list):
        raise TypeError("frozen lot or transaction data is malformed")
    lots = tuple(
        LotInput(
            ticker=str(row["ticker"]),
            broker_lot_id=str(row["broker_lot_id"]),
            acquired_date=_parse_date(row["acquired_date"]),
            shares=Decimal(str(row["shares"])),
            available_shares=Decimal(str(row["available_shares"])),
            adjusted_unit_basis_usd=Decimal(str(row["adjusted_unit_basis_usd"])),
            broker_wash_adjustment_usd=_decimal(row.get("broker_wash_adjustment_usd")),
            source=str(row["source"]),
            as_of=_parse_datetime(row["as_of"]),
            fractional_cleanup_unsupported=bool(row.get("fractional_cleanup_unsupported", False)),
            quality_flags=tuple(str(flag) for flag in row.get("quality_flags", [])),
            sync_generation=_lot_sync_generation(row, bundle),
        )
        for row in raw_lots
        if isinstance(row, dict)
    )
    transactions = tuple(
        TransactionInput(
            broker_transaction_key=str(row["broker_transaction_key"]),
            ticker=str(row["ticker"]),
            transaction_kind=str(row["transaction_kind"]),
            transaction_time=_parse_datetime(row["transaction_time"]),
            trade_date=_parse_date(row["trade_date"]),
            shares=Decimal(str(row["shares"])),
            amount_usd=Decimal(str(row["amount_usd"])),
            is_acquisition=bool(row["is_acquisition"]),
            broker_lot_id=(
                str(row["broker_lot_id"]) if row.get("broker_lot_id") is not None else None
            ),
            source=str(row["source"]),
            realized_pl_usd=_decimal(row.get("realized_pl_usd")),
        )
        for row in raw_transactions
        if isinstance(row, dict)
    )
    trade_date_raw = bundle.get("proposed_trade_date")
    if isinstance(trade_date_raw, str):
        trade_date = _parse_date(trade_date_raw)
        if proposed_trade_date is not None and proposed_trade_date != trade_date:
            raise ValueError("persisted and frozen proposed trade dates do not match")
    elif bundle.get("schema") == "demo-run-input-v1" and proposed_trade_date is not None:
        legacy_as_of = account_data.get("as_of")
        if not isinstance(legacy_as_of, str):
            raise TypeError("legacy frozen run has no date provenance")
        trade_date = _parse_datetime(legacy_as_of).date()
        if proposed_trade_date != trade_date:
            raise ValueError("legacy persisted date does not match its frozen account date")
    else:
        raise ValueError("frozen run has no proposed trade date provenance")
    account = AccountInput(
        local_account_id=int(account_data.get("local_account_id", 1)),
        account_key_fingerprint=str(account_data["account_key_fingerprint"]),
        display_name=str(account_data["display_name"]),
        account_type=str(account_data["account_type"]),
        tax_treatment=str(account_data["tax_treatment"]) if account_data.get("tax_treatment") is not None else None,
        source=str(account_data["source"]),
        as_of=_parse_datetime(account_data["as_of"]),
        cash_usd=Decimal(str(account_data["cash_usd"])),
        settled_buying_power_usd=Decimal(str(account_data["settled_buying_power_usd"])),
    )
    return FinancialInputs(
        account=account,
        source_generation=int(bundle["source_generation"]),
        proposed_trade_date=trade_date,
        policy=policy,
        securities=tuple(security_inputs[key] for key in sorted(security_inputs)),
        positions=tuple(positions),
        lots=lots,
        quotes=quotes,
        transactions=transactions,
        exposures=exposures,
        source_metadata=source_metadata,
        source_checksum=str(bundle["source_checksum"]) if bundle.get("source_checksum") else None,
    )
