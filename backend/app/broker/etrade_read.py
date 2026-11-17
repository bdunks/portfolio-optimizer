from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from fractions import Fraction
from typing import Literal, NoReturn, cast
from urllib.parse import parse_qs, parse_qsl, urlencode, urlsplit
from zoneinfo import ZoneInfo

import requests
from pydantic import ValidationError

from app.broker.etrade_oauth import EtradeOAuthService
from app.domain.decimal_math import exact_sum
from app.schemas import CoverageInput, LotInput, PositionInput, TransactionInput
from app.services.errors import AppError

logger = logging.getLogger(__name__)

type EtradeEnvironment = Literal["sandbox", "production"]
type BrokerProductId = str | int | Decimal | Mapping[str, object]

_DATA_BASES: dict[EtradeEnvironment, str] = {
    "sandbox": "https://apisb.etrade.com/v1",
    "production": "https://api.etrade.com/v1",
}
_ACCOUNT_KEY = re.compile(r"[A-Za-z0-9_-]{1,128}\Z", re.ASCII)
_POSITION_ID = re.compile(r"[0-9]{1,19}\Z", re.ASCII)
_EASTERN = ZoneInfo("America/New_York")
_UTC_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_PAGE_SIZE = 200
_MAX_PAGES = 100
_TRANSACTION_PAGE_SIZE = 50


@dataclass(frozen=True, slots=True)
class EtradeAccountCandidate:
    """An account identified from the current read; it is not a durable binding."""

    account_id_key: str
    display_name: str
    account_type: str
    tax_treatment: str | None
    account_id: str | None = None

    @property
    def is_brokerage(self) -> bool:
        return self.account_type.strip().upper() == "BROKERAGE"


@dataclass(frozen=True, slots=True)
class EtradePositionRecord:
    """Broker identity plus the existing typed position value for later assembly."""

    broker_position_id: str
    broker_product_id: BrokerProductId | None
    position: PositionInput


@dataclass(frozen=True, slots=True)
class EtradeLotRecord:
    """Exact broker lot data, including adapter-only source and reserved quantities."""

    broker_position_id: str
    broker_lot_id: str
    ticker: str
    remaining_shares: Decimal
    available_shares: Decimal
    reserved_shares: Decimal
    total_cost_usd: Decimal
    total_cost_source: Decimal
    acquired_date_source: Decimal | int | str
    lot: LotInput


@dataclass(frozen=True, slots=True)
class EtradePortfolioWithLots:
    """Complete read-only account holdings result; no balances or quote coverage implied."""

    account: EtradeAccountCandidate
    as_of: datetime
    positions: tuple[EtradePositionRecord, ...]
    lots: tuple[EtradeLotRecord, ...]


@dataclass(frozen=True, slots=True)
class EtradeTransactionRecord:
    """Source transaction fields plus an optional wash-domain value."""

    transaction_id: str
    account_id: str
    transaction_type_source: object | None
    normalized_transaction_type: str | None
    transaction_date_source: object
    transaction_time: datetime
    trade_date: date
    post_date_source: object | None
    settlement_date_source: object | None
    amount_source: object | None
    quantity_source: object | None
    order_no_source: object | None
    transaction: TransactionInput | None
    wash_relevant: bool
    source_fields: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class EtradeTransactionHistory:
    """Bounded history read with requested coverage distinct from row extrema."""

    account: EtradeAccountCandidate
    requested_start_date: date
    requested_end_date: date
    actual_start_date: date | None
    actual_end_date: date | None
    records: tuple[EtradeTransactionRecord, ...]
    coverage: CoverageInput
    diagnostics: tuple[str, ...]
    page_count: int

    @property
    def transactions(self) -> tuple[TransactionInput, ...]:
        return tuple(
            record.transaction for record in self.records if record.transaction is not None
        )


@dataclass(frozen=True, slots=True)
class _TransactionPage:
    rows: list[dict[str, object]]
    transaction_count: int
    total_count: int | None
    next_url: object | None
    marker: object | None
    page_markers: object | None
    more_transactions: bool | None


@dataclass(frozen=True, slots=True)
class _PageMarkers:
    next_page: int | None
    total_pages: int | None


class EtradeReadAdapter:
    """Offline-injected E*TRADE account and exact-lot reader."""

    def __init__(
        self,
        oauth: EtradeOAuthService,
        *,
        environment: EtradeEnvironment,
        configured_account_id_key: str | None = None,
        clock: Callable[[], datetime] | None = None,
        monotonic_clock: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        if environment not in _DATA_BASES:
            raise ValueError("Unsupported E*TRADE environment")
        self._oauth = oauth
        self._base_url = _DATA_BASES[environment]
        self._configured_account_id_key = (
            _validate_account_key(configured_account_id_key)
            if configured_account_id_key is not None
            else None
        )
        self._clock = clock or (lambda: datetime.now(UTC))
        self._monotonic_clock = monotonic_clock or time.monotonic
        self._sleep = sleep or time.sleep
        self._last_position_detail_start: float | None = None

    def list_accounts(self) -> tuple[EtradeAccountCandidate, ...]:
        """Return validated accounts without selecting or persisting a managed account."""
        payload = self._get_json("accounts", "/accounts/list")
        if payload is None:
            return ()

        root = _as_mapping(payload, "accounts response")
        response = root.get("AccountListResponse", root)
        response_mapping = _as_mapping(response, "accounts response")
        accounts_container = response_mapping.get("Accounts")
        accounts_mapping = _as_mapping(accounts_container, "accounts")
        if "Account" not in accounts_mapping:
            _fail("etrade_read_accounts_malformed", "E*TRADE account list is incomplete.")
        rows = _as_rows(accounts_mapping["Account"], "account")

        parsed: list[EtradeAccountCandidate] = []
        seen_keys: set[str] = set()
        for row in rows:
            account_key = _validate_account_key(row.get("accountIdKey"))
            if account_key in seen_keys:
                _fail("etrade_read_duplicate_account", "E*TRADE returned duplicate account IDs.")
            seen_keys.add(account_key)
            display_name = _required_text(row, "accountName", "account")
            account_type = _required_text(row, "accountType", "account")
            tax_treatment = _optional_text(row.get("taxTreatment"), "account tax treatment")
            account_id = (
                _identifier(row["accountId"], "user account ID", maximum=128)
                if row.get("accountId") is not None
                else None
            )
            parsed.append(
                EtradeAccountCandidate(
                    account_id_key=account_key,
                    display_name=display_name,
                    account_type=account_type,
                    tax_treatment=tax_treatment,
                    account_id=account_id,
                )
            )
        return tuple(parsed)

    def fetch_portfolio_with_lots(
        self,
        *,
        previously_bound_account_id_key: str | None = None,
    ) -> EtradePortfolioWithLots:
        """Resolve one brokerage account and fetch every position and exact open lot."""
        accounts = self.list_accounts()
        account = self._resolve_account(accounts, previously_bound_account_id_key)
        as_of = self._now()

        positions: list[EtradePositionRecord] = []
        lots: list[EtradeLotRecord] = []
        seen_position_ids: set[str] = set()
        current_page = 1
        visited_pages: set[int] = set()

        for _ in range(_MAX_PAGES):
            if current_page in visited_pages:
                _fail(
                    "etrade_read_pagination_repeated",
                    "E*TRADE portfolio pagination repeated a page.",
                )
            visited_pages.add(current_page)
            page_data = self._get_json(
                "portfolio",
                self._portfolio_path(account.account_id_key, current_page),
            )
            if page_data is None:
                if current_page == 1:
                    return EtradePortfolioWithLots(account, as_of, (), ())
                _fail(
                    "etrade_read_portfolio_incomplete",
                    "E*TRADE portfolio pagination ended unexpectedly.",
                )

            page_rows, markers = self._portfolio_page(page_data, account, current_page)
            for row in page_rows:
                position = self._decode_position(row)
                if position.broker_position_id in seen_position_ids:
                    _fail(
                        "etrade_read_duplicate_position", "E*TRADE returned duplicate position IDs."
                    )
                seen_position_ids.add(position.broker_position_id)
                if any(item.position.ticker == position.position.ticker for item in positions):
                    _fail(
                        "etrade_read_duplicate_position",
                        "E*TRADE returned duplicate security positions.",
                    )
                positions.append(position)

                detail_payload = self._get_json(
                    "position-lots",
                    self._position_detail_path(
                        account.account_id_key,
                        position.broker_position_id,
                    ),
                )
                detail_rows = self._position_lot_rows(detail_payload)
                lots.extend(self._decode_lot(lot_row, position, as_of) for lot_row in detail_rows)

            next_page = markers.next_page
            if next_page is None:
                break
            if next_page != current_page + 1:
                _fail(
                    "etrade_read_pagination_invalid",
                    "E*TRADE portfolio pagination is inconsistent.",
                )
            current_page = next_page
        else:
            _fail("etrade_read_page_limit", "E*TRADE portfolio exceeded the page limit.")

        self._validate_lot_coverage(positions, lots)
        return EtradePortfolioWithLots(account, as_of, tuple(positions), tuple(lots))

    def fetch_transactions(
        self,
        start_date: date,
        end_date: date,
        *,
        previously_bound_account_id_key: str | None = None,
    ) -> EtradeTransactionHistory:
        """Read complete bounded transaction history for the one resolved account."""
        if type(start_date) is not date or type(end_date) is not date or start_date > end_date:
            _fail(
                "etrade_read_transactions_query_invalid",
                "E*TRADE transaction history requires a valid bounded date interval.",
            )

        accounts = self.list_accounts()
        account = self._resolve_account(accounts, previously_bound_account_id_key)
        if account.account_id is None:
            _fail(
                "etrade_read_transaction_account_identity_missing",
                "E*TRADE account identity is unavailable for transaction validation.",
            )

        records: list[EtradeTransactionRecord] = []
        seen_transaction_ids: set[str] = set()
        seen_markers: set[str] = set()
        actual_dates: list[date] = []
        diagnostic_codes: set[str] = set()
        history_complete = True
        marker: str | None = None
        pages_read = 0

        for _ in range(_MAX_PAGES):
            payload = self._get_json(
                "transactions",
                self._transactions_path(account.account_id_key, start_date, end_date, marker),
            )
            if payload is None:
                _fail(
                    "etrade_read_transactions_incomplete",
                    "E*TRADE transaction history ended without an authoritative page.",
                )
            page = _transaction_page(payload)
            pages_read += 1
            if (
                page.transaction_count != len(page.rows)
                or page.transaction_count > _TRANSACTION_PAGE_SIZE
                or (page.total_count is not None and page.total_count < page.transaction_count)
            ):
                _fail(
                    "etrade_read_transactions_count_mismatch",
                    "E*TRADE transaction page counts are inconsistent.",
                )

            for row in page.rows:
                record, row_complete, row_diagnostics = _decode_transaction_record(
                    row,
                    account,
                    start_date,
                    end_date,
                )
                if record.transaction_id in seen_transaction_ids:
                    _fail(
                        "etrade_read_transactions_duplicate",
                        "E*TRADE returned duplicate transaction IDs.",
                    )
                seen_transaction_ids.add(record.transaction_id)
                records.append(record)
                actual_dates.append(record.trade_date)
                history_complete = history_complete and row_complete
                diagnostic_codes.update(row_diagnostics)

            next_marker = _transaction_continuation(
                page,
                base_url=self._base_url,
                account_key=account.account_id_key,
            )
            if next_marker is not None:
                if next_marker in seen_markers:
                    _fail(
                        "etrade_read_transactions_pagination_repeated",
                        "E*TRADE transaction pagination repeated a continuation marker.",
                    )
                seen_markers.add(next_marker)
                marker = next_marker
                continue

            if (
                page.total_count is not None
                and page.more_transactions is not True
                and page.transaction_count < _TRANSACTION_PAGE_SIZE
                and page.total_count != page.transaction_count
            ):
                _fail(
                    "etrade_read_transactions_count_mismatch",
                    "E*TRADE transaction page counts are inconsistent.",
                )
            if page.more_transactions is True or page.transaction_count >= _TRANSACTION_PAGE_SIZE:
                _fail(
                    "etrade_read_transactions_incomplete",
                    "E*TRADE transaction history has no consistent exhaustion evidence.",
                )
            break
        else:
            _fail(
                "etrade_read_transactions_page_limit",
                "E*TRADE transaction history exceeded the page limit.",
            )

        if diagnostic_codes:
            logger.warning(
                "E*TRADE transaction history contains unsupported or unrepresentable rows; "
                "coverage is incomplete"
            )
        coverage = CoverageInput(
            positions=False,
            lots=False,
            transactions=history_complete,
            balances=False,
            quotes=False,
            transaction_history_start_date=start_date,
            transaction_history_end_date=end_date,
        )
        return EtradeTransactionHistory(
            account=account,
            requested_start_date=start_date,
            requested_end_date=end_date,
            actual_start_date=min(actual_dates) if actual_dates else None,
            actual_end_date=max(actual_dates) if actual_dates else None,
            records=tuple(records),
            coverage=coverage,
            diagnostics=tuple(sorted(diagnostic_codes)),
            page_count=pages_read,
        )

    def _resolve_account(
        self,
        accounts: Sequence[EtradeAccountCandidate],
        previously_bound_account_id_key: str | None,
    ) -> EtradeAccountCandidate:
        previous_key = (
            _validate_account_key(previously_bound_account_id_key)
            if previously_bound_account_id_key is not None
            else None
        )
        configured_key = self._configured_account_id_key
        if (
            configured_key is not None
            and previous_key is not None
            and configured_key != previous_key
        ):
            _fail(
                "etrade_read_account_binding_mismatch",
                "Configured and bound E*TRADE accounts differ.",
                409,
            )
        requested_key = configured_key or previous_key
        eligible = [account for account in accounts if account.is_brokerage]

        if requested_key is not None:
            matches = [account for account in accounts if account.account_id_key == requested_key]
            if len(matches) != 1:
                _fail(
                    "etrade_read_account_not_found",
                    "The configured E*TRADE brokerage account was not found.",
                    409,
                )
            account = matches[0]
            if not account.is_brokerage:
                _fail(
                    "etrade_read_account_not_brokerage",
                    "The configured E*TRADE account is not a brokerage account.",
                    409,
                )
            return account
        if not eligible:
            _fail(
                "etrade_read_no_brokerage_account",
                "No eligible E*TRADE brokerage account was found.",
                409,
            )
        if len(eligible) != 1:
            _fail(
                "etrade_read_account_ambiguous",
                "Multiple E*TRADE brokerage accounts require explicit binding.",
                409,
            )
        return eligible[0]

    def _get_json(self, operation: str, path: str) -> object | None:
        session = self._oauth.auth_for_read()
        try:
            if operation == "position-lots":
                self._pace_position_detail_request()
            response = session.get(
                f"{self._base_url}{path}",
                headers={"Accept": "application/json"},
                timeout=10,
                allow_redirects=False,
            )
        except requests.RequestException:
            logger.warning("E*TRADE read %s request failed (transport error)", operation)
            _fail(
                "etrade_read_transport_error",
                "E*TRADE could not complete the read request.",
                502,
            )
        finally:
            session.close()

        if response.status_code == 204:
            self._oauth.record_activity()
            return None
        if response.status_code != 200:
            logger.warning("E*TRADE read %s failed (HTTP %d)", operation, response.status_code)
            _fail(
                "etrade_read_http_error",
                f"E*TRADE {operation} read failed (HTTP {response.status_code}).",
                502,
            )
        content_type = (
            response.headers.get("Content-Type", "").split(";", maxsplit=1)[0].strip().lower()
        )
        if content_type != "application/json" and not content_type.endswith("+json"):
            logger.warning("E*TRADE read %s returned a non-JSON response", operation)
            _fail("etrade_read_invalid_json", "E*TRADE returned a non-JSON response.", 502)
        try:
            payload: object = json.loads(
                response.content,
                parse_float=Decimal,
                parse_constant=_reject_json_constant,
            )
        except UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError:
            logger.warning("E*TRADE read %s returned malformed JSON", operation)
            _fail("etrade_read_invalid_json", "E*TRADE returned malformed JSON.", 502)
        self._oauth.record_activity()
        return payload

    def _pace_position_detail_request(self) -> None:
        if self._last_position_detail_start is not None:
            while True:
                elapsed = self._monotonic_clock() - self._last_position_detail_start
                remaining = 0.5 - elapsed
                if remaining <= 0:
                    break
                self._sleep(remaining)
        self._last_position_detail_start = self._monotonic_clock()

    def _transactions_path(
        self,
        account_key: str,
        start_date: date,
        end_date: date,
        marker: str | None,
    ) -> str:
        query: list[tuple[str, str]] = [
            ("startDate", start_date.strftime("%m%d%Y")),
            ("endDate", end_date.strftime("%m%d%Y")),
            ("count", str(_TRANSACTION_PAGE_SIZE)),
        ]
        if marker is not None:
            query.append(("marker", marker))
        return f"/accounts/{account_key}/transactions?{urlencode(query)}"

    def _portfolio_path(self, account_key: str, page_number: int) -> str:
        query = urlencode(
            (
                ("sortBy", "SYMBOL"),
                ("sortOrder", "ASC"),
                ("count", str(_PAGE_SIZE)),
                ("pageNumber", str(page_number)),
            )
        )
        return f"/accounts/{account_key}/portfolio?{query}"

    @staticmethod
    def _position_detail_path(account_key: str, position_id: str) -> str:
        if _POSITION_ID.fullmatch(position_id) is None:
            _fail("etrade_read_position_id_invalid", "E*TRADE returned an invalid position ID.")
        return f"/accounts/{account_key}/portfolio/{position_id}"

    def _portfolio_page(
        self,
        payload: object,
        account: EtradeAccountCandidate,
        page_number: int,
    ) -> tuple[list[dict[str, object]], _PageMarkers]:
        root = _as_mapping(payload, "portfolio response")
        response = _as_mapping(root.get("PortfolioResponse"), "portfolio response")
        account_portfolio = _first_alias(
            response, ("AccountPortfolio", "accountPortfolio"), "account portfolio"
        )
        wrappers = _as_rows(account_portfolio, "account portfolio")
        if len(wrappers) != 1:
            _fail(
                "etrade_read_portfolio_malformed",
                "E*TRADE returned an ambiguous portfolio wrapper.",
            )
        wrapper = wrappers[0]
        returned_key = wrapper.get("accountIdKey")
        if returned_key is not None and returned_key != account.account_id_key:
            _fail(
                "etrade_read_portfolio_account_mismatch",
                "E*TRADE returned a different account portfolio.",
            )
        position_value = _first_alias(wrapper, ("Position", "position"), "portfolio positions")
        rows = _as_rows(position_value, "position")
        markers = _page_markers(wrapper, page_number)
        return rows, markers

    def _position_lot_rows(self, payload: object | None) -> list[dict[str, object]]:
        if payload is None:
            _fail("etrade_read_lots_missing", "E*TRADE returned no exact position lots.")
        root = _as_mapping(payload, "position lots response")
        response = _as_mapping(root.get("PositionLotsResponse"), "position lots response")
        if "PositionLot" not in response:
            _fail("etrade_read_lots_missing", "E*TRADE position-lot response is incomplete.")
        rows = _as_rows(response["PositionLot"], "position lot")
        if not rows:
            _fail("etrade_read_lots_missing", "E*TRADE returned no exact position lots.")
        return rows

    def _decode_position(self, row: Mapping[str, object]) -> EtradePositionRecord:
        position_id = _identifier(row.get("positionId"), "position ID", maximum=19)
        if _POSITION_ID.fullmatch(position_id) is None:
            _fail("etrade_read_position_id_invalid", "E*TRADE returned an invalid position ID.")
        product_values = [row[key] for key in ("Product", "product") if key in row]
        if len(product_values) > 1 and any(
            value != product_values[0] for value in product_values[1:]
        ):
            _fail("etrade_read_field_conflict", "E*TRADE product fields conflict.")
        product = _optional_mapping(product_values[0] if product_values else None)
        symbol_values = [
            value for value in (row.get("symbol"), product.get("symbol")) if value is not None
        ]
        if not symbol_values or any(value != symbol_values[0] for value in symbol_values[1:]):
            _fail("etrade_read_field_conflict", "E*TRADE position symbols are missing or conflict.")
        if not isinstance(symbol_values[0], str) or not symbol_values[0].strip():
            _fail("etrade_read_field_missing", "E*TRADE position symbol is missing or invalid.")
        ticker = symbol_values[0].strip().upper()
        asset_type = _asset_type(product)
        cusip = _first_optional_text(row, product, ("cusip",), "CUSIP")
        isin = _first_optional_text(row, product, ("isin",), "ISIN")
        product_id = _product_id(product)
        try:
            position_input = PositionInput(
                ticker=ticker,
                asset_type=asset_type,
                shares=_decimal(row.get("quantity"), "position quantity"),
                market_value_usd=_decimal(row.get("marketValue"), "position market value"),
                cusip=cusip,
                isin=isin,
            )
        except ValidationError, ValueError:
            _fail("etrade_read_position_invalid", "E*TRADE returned an invalid position.")
        if position_input.shares <= 0 or position_input.market_value_usd < 0:
            _fail(
                "etrade_read_position_invalid",
                "E*TRADE returned an invalid position quantity or value.",
            )
        return EtradePositionRecord(position_id, product_id, position_input)

    def _decode_lot(
        self,
        row: Mapping[str, object],
        position: EtradePositionRecord,
        as_of: datetime,
    ) -> EtradeLotRecord:
        lot_id = _identifier(row.get("positionLotId"), "lot ID", maximum=128)
        remaining = _decimal(row.get("remainingQty"), "remaining quantity")
        available = _decimal(row.get("availableQty"), "available quantity")
        total_cost = _decimal(row.get("totalCost"), "total cost")
        acquired_value, acquired_source = _acquired_date(row)
        if remaining <= 0 or available < 0 or available > remaining or total_cost < 0:
            _fail("etrade_read_lot_invalid", "E*TRADE returned an invalid lot quantity or cost.")
        unit_basis = _exact_unit_basis(total_cost, remaining)
        reserved = exact_sum((remaining, -available))
        try:
            lot_input = LotInput(
                ticker=position.position.ticker,
                broker_lot_id=lot_id,
                acquired_date=acquired_value,
                shares=remaining,
                available_shares=available,
                adjusted_unit_basis_usd=unit_basis,
                broker_wash_adjustment_usd=None,
                source="ETRADE",
                as_of=as_of,
            )
        except ValidationError, ValueError:
            _fail("etrade_read_lot_invalid", "E*TRADE returned an invalid exact lot.")
        return EtradeLotRecord(
            broker_position_id=position.broker_position_id,
            broker_lot_id=lot_id,
            ticker=position.position.ticker,
            remaining_shares=remaining,
            available_shares=available,
            reserved_shares=reserved,
            total_cost_usd=total_cost,
            total_cost_source=total_cost,
            acquired_date_source=acquired_source,
            lot=lot_input,
        )

    @staticmethod
    def _validate_lot_coverage(
        positions: Sequence[EtradePositionRecord],
        lots: Sequence[EtradeLotRecord],
    ) -> None:
        seen_lot_ids: set[str] = set()
        lots_by_position: dict[str, list[Decimal]] = {}
        for lot in lots:
            if lot.broker_lot_id in seen_lot_ids:
                _fail("etrade_read_duplicate_lot", "E*TRADE returned duplicate lot IDs.")
            seen_lot_ids.add(lot.broker_lot_id)
            lots_by_position.setdefault(lot.broker_position_id, []).append(lot.remaining_shares)
        for position in positions:
            reported_lots = lots_by_position.get(position.broker_position_id, [])
            if exact_sum(reported_lots) != position.position.shares:
                _fail(
                    "etrade_read_incomplete_lots",
                    "E*TRADE position lots do not exactly cover the position.",
                )

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            _fail(
                "etrade_read_clock_invalid", "The E*TRADE read clock must be timezone-aware.", 500
            )
        return value.astimezone(UTC)


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"Invalid JSON numeric constant: {value}")


def _fail(code: str, message: str, status_code: int = 422) -> NoReturn:
    raise AppError(code, message, status_code=status_code)


def _as_mapping(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        _fail("etrade_read_response_malformed", f"E*TRADE {field} is malformed.")
    return cast(dict[str, object], value)


def _as_rows(value: object, field: str) -> list[dict[str, object]]:
    if isinstance(value, list):
        rows: list[dict[str, object]] = []
        for item in value:
            if not isinstance(item, dict) or any(not isinstance(key, str) for key in item):
                _fail("etrade_read_response_malformed", f"E*TRADE {field} list is malformed.")
            rows.append(cast(dict[str, object], item))
        return rows
    if isinstance(value, dict):
        return [_as_mapping(value, field)]
    _fail("etrade_read_response_malformed", f"E*TRADE {field} list is missing or malformed.")


def _transaction_page(payload: object) -> _TransactionPage:
    root = _as_mapping(payload, "transaction response")
    if "TransactionListResponse" not in root:
        _fail("etrade_read_transactions_malformed", "E*TRADE transaction response is malformed.")
    response = _as_mapping(root["TransactionListResponse"], "transaction response")
    has_direct_rows = "Transaction" in response
    has_wrapped_rows = "Transactions" in response
    if has_direct_rows == has_wrapped_rows:
        _fail("etrade_read_transactions_malformed", "E*TRADE transaction rows are ambiguous.")
    if has_direct_rows:
        rows = _as_rows(response["Transaction"], "transactions")
    else:
        wrapped = _as_mapping(response["Transactions"], "transactions")
        if "Transaction" not in wrapped:
            _fail("etrade_read_transactions_malformed", "E*TRADE transaction rows are missing.")
        rows = _as_rows(wrapped["Transaction"], "transactions")

    if "transactionCount" not in response:
        _fail("etrade_read_transactions_malformed", "E*TRADE transaction page count is missing.")
    transaction_count = _page_integer(response["transactionCount"], "transaction count")
    total_count = (
        _page_integer(response["totalCount"], "total transaction count")
        if response.get("totalCount") is not None
        else None
    )
    more_transactions_value = response.get("moreTransactions")
    if more_transactions_value is not None and not isinstance(more_transactions_value, bool):
        _fail("etrade_read_transactions_malformed", "E*TRADE transaction continuation is invalid.")

    return _TransactionPage(
        rows=rows,
        transaction_count=transaction_count,
        total_count=total_count,
        next_url=response.get("next"),
        marker=response.get("marker"),
        page_markers=response.get("pageMarkers"),
        more_transactions=more_transactions_value,
    )


def _transaction_continuation(
    page: _TransactionPage,
    *,
    base_url: str,
    account_key: str,
) -> str | None:
    if page.page_markers is not None and not isinstance(page.page_markers, str):
        _fail(
            "etrade_read_transactions_pagination_invalid",
            "E*TRADE transaction markers are invalid.",
        )
    has_next = page.next_url is not None
    has_marker = page.marker is not None
    if not has_next and not has_marker:
        if page.page_markers not in (None, ""):
            _fail(
                "etrade_read_transactions_incomplete",
                "E*TRADE returned an opaque continuation without a validated next marker.",
            )
        return None
    if not has_next or not has_marker:
        _fail(
            "etrade_read_transactions_pagination_invalid",
            "E*TRADE transaction continuation fields are inconsistent.",
        )
    if not isinstance(page.next_url, str) or not isinstance(page.marker, str) or not page.marker:
        _fail(
            "etrade_read_transactions_pagination_invalid",
            "E*TRADE transaction marker is invalid.",
        )
    if len(page.marker) > 8192:
        _fail(
            "etrade_read_transactions_pagination_invalid",
            "E*TRADE transaction marker is too large.",
        )

    try:
        next_parts = urlsplit(page.next_url)
        base_parts = urlsplit(base_url)
        query = parse_qsl(next_parts.query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        _fail(
            "etrade_read_transactions_pagination_invalid",
            "E*TRADE transaction next URL is invalid.",
        )
    expected_path = f"{base_parts.path}/accounts/{account_key}/transactions"
    if (
        next_parts.scheme != "https"
        or next_parts.netloc.lower() != base_parts.netloc.lower()
        or next_parts.path != expected_path
        or next_parts.username is not None
        or next_parts.password is not None
        or next_parts.fragment
    ):
        _fail(
            "etrade_read_transactions_pagination_foreign",
            "E*TRADE returned a continuation outside the bound transaction endpoint.",
        )
    if query != [("marker", page.marker)]:
        _fail(
            "etrade_read_transactions_pagination_invalid",
            "E*TRADE transaction continuation query does not match its marker.",
        )
    return page.marker


def _transaction_time(value: object) -> datetime:
    milliseconds = _decimal(value, "transaction date")
    if milliseconds != milliseconds.to_integral_value():
        _fail("etrade_read_transaction_date_invalid", "E*TRADE transaction date is invalid.")
    try:
        return _UTC_EPOCH + timedelta(milliseconds=int(milliseconds))
    except OverflowError, ValueError:
        _fail("etrade_read_transaction_date_invalid", "E*TRADE transaction date is out of range.")


def _optional_transaction_decimal(value: object | None, field: str) -> Decimal | None:
    if value is None:
        return None
    try:
        return _decimal(value, field)
    except AppError:
        return None


def _transaction_currency_is_usd(brokerage: Mapping[str, object]) -> bool:
    currencies: list[str] = []
    for field in ("settlementCurrency", "paymentCurrency"):
        value = brokerage.get(field)
        if not isinstance(value, str) or not value.strip():
            return False
        currencies.append(value.strip().upper())
    return all(currency == "USD" for currency in currencies)


def _make_transaction_input(
    *,
    transaction_id: str,
    ticker: str,
    transaction_kind: Literal["BUY", "SELL", "DIVIDEND", "OTHER"],
    transaction_time: datetime,
    trade_date: date,
    shares: Decimal,
    amount_usd: Decimal,
    is_acquisition: bool,
) -> TransactionInput | None:
    try:
        return TransactionInput(
            broker_transaction_key=transaction_id,
            ticker=ticker,
            transaction_kind=transaction_kind,
            transaction_time=transaction_time,
            trade_date=trade_date,
            shares=shares,
            amount_usd=amount_usd,
            realized_pl_usd=None,
            is_acquisition=is_acquisition,
            broker_lot_id=None,
            source="ETRADE",
        )
    except ValidationError, ValueError:
        return None


def _decode_transaction_record(
    row: dict[str, object],
    account: EtradeAccountCandidate,
    requested_start_date: date,
    requested_end_date: date,
) -> tuple[EtradeTransactionRecord, bool, set[str]]:
    transaction_id = _identifier(row.get("transactionId"), "transaction ID", maximum=128)
    source_account_id = row.get("accountId")
    if source_account_id is None:
        _fail(
            "etrade_read_transaction_account_identity_missing",
            "E*TRADE transaction account identity is missing.",
        )
    account_id = _identifier(source_account_id, "transaction account ID", maximum=128)
    if account.account_id is None or account_id != account.account_id:
        _fail(
            "etrade_read_transaction_account_mismatch",
            "E*TRADE returned a transaction for a different account.",
        )

    transaction_date_source = row.get("transactionDate")
    if transaction_date_source is None:
        _fail("etrade_read_transaction_date_missing", "E*TRADE transaction date is missing.")
    transaction_time = _transaction_time(transaction_date_source)
    trade_date = transaction_time.date()
    transaction_type_source = row.get("transactionType")
    normalized_type = (
        transaction_type_source.strip().lower()
        if isinstance(transaction_type_source, str)
        else None
    )
    brokerage_value = row.get("brokerage")
    brokerage: Mapping[str, object] = (
        cast(Mapping[str, object], brokerage_value)
        if isinstance(brokerage_value, dict)
        and all(isinstance(key, str) for key in brokerage_value)
        else {}
    )
    product_value = brokerage.get("product")
    product: Mapping[str, object] = (
        cast(Mapping[str, object], product_value)
        if isinstance(product_value, dict) and all(isinstance(key, str) for key in product_value)
        else {}
    )
    symbol_value = product.get("symbol")
    ticker = (
        symbol_value.strip().upper()
        if isinstance(symbol_value, str) and symbol_value.strip()
        else None
    )
    amount_source = row.get("amount")
    quantity_source = brokerage.get("quantity")
    diagnostics: set[str] = set()
    row_complete = True
    if not requested_start_date <= trade_date <= requested_end_date:
        row_complete = False
        diagnostics.add("transaction_outside_requested_interval")

    transaction_kind: Literal["BUY", "SELL", "DIVIDEND", "OTHER"] | None = None
    is_acquisition = False
    wash_relevant = False
    supported_trade_type = normalized_type in {
        "bought",
        "sold",
        "reinvestment",
        "dividend reinvestment",
    }
    dividend_type = normalized_type in {
        "dividend",
        "qualified dividend",
        "non-qualified dividend",
        "short term cap gain",
        "long term cap gain",
    }
    safe_other_type = normalized_type in {"funds received", "transfer", "ach deposit"}
    if supported_trade_type:
        wash_relevant = True
        transaction_kind = "SELL" if normalized_type == "sold" else "BUY"
        is_acquisition = transaction_kind == "BUY"
    elif dividend_type:
        transaction_kind = "DIVIDEND"
    elif safe_other_type:
        transaction_kind = "OTHER"
    else:
        row_complete = False
        wash_relevant = True
        diagnostics.add("unsupported_transaction_type")

    transaction: TransactionInput | None = None
    if transaction_kind in {"BUY", "SELL"}:
        asset_supported = False
        if product:
            try:
                _asset_type(product)
                asset_supported = True
            except AppError:
                pass
        quantity = _optional_transaction_decimal(quantity_source, "transaction quantity")
        amount = _optional_transaction_decimal(amount_source, "transaction amount")
        expected_cash_sign = -1 if transaction_kind == "BUY" else 1
        kind_consistent = (
            quantity is not None
            and quantity > 0
            and amount is not None
            and ((amount < 0) if expected_cash_sign < 0 else (amount > 0))
        )
        if not kind_consistent:
            row_complete = False
            diagnostics.add("transaction_kind_inconsistent")
        if (
            ticker is None
            or not asset_supported
            or not _transaction_currency_is_usd(brokerage)
            or not kind_consistent
        ):
            row_complete = False
            diagnostics.add("wash_transaction_unrepresentable")
        else:
            transaction = _make_transaction_input(
                transaction_id=transaction_id,
                ticker=ticker,
                transaction_kind=transaction_kind,
                transaction_time=transaction_time,
                trade_date=trade_date,
                shares=quantity,
                amount_usd=amount,
                is_acquisition=is_acquisition,
            )
            if transaction is None:
                row_complete = False
                diagnostics.add("wash_transaction_unrepresentable")
    elif transaction_kind == "DIVIDEND":
        quantity = _optional_transaction_decimal(quantity_source, "transaction quantity")
        amount = _optional_transaction_decimal(amount_source, "transaction amount")
        if amount is not None and amount <= 0:
            row_complete = False
            diagnostics.add("transaction_kind_inconsistent")
        elif (
            ticker is not None
            and quantity is not None
            and amount is not None
            and _transaction_currency_is_usd(brokerage)
        ):
            transaction = _make_transaction_input(
                transaction_id=transaction_id,
                ticker=ticker,
                transaction_kind="DIVIDEND",
                transaction_time=transaction_time,
                trade_date=trade_date,
                shares=quantity,
                amount_usd=amount,
                is_acquisition=False,
            )
    elif transaction_kind == "OTHER" and ticker is not None:
        quantity = _optional_transaction_decimal(quantity_source, "transaction quantity")
        amount = _optional_transaction_decimal(amount_source, "transaction amount")
        if quantity is not None and amount is not None and _transaction_currency_is_usd(brokerage):
            transaction = _make_transaction_input(
                transaction_id=transaction_id,
                ticker=ticker,
                transaction_kind="OTHER",
                transaction_time=transaction_time,
                trade_date=trade_date,
                shares=quantity,
                amount_usd=amount,
                is_acquisition=False,
            )

    record = EtradeTransactionRecord(
        transaction_id=transaction_id,
        account_id=account_id,
        transaction_type_source=transaction_type_source,
        normalized_transaction_type=normalized_type,
        transaction_date_source=transaction_date_source,
        transaction_time=transaction_time,
        trade_date=trade_date,
        post_date_source=row.get("postDate"),
        settlement_date_source=brokerage.get("settlementDate"),
        amount_source=amount_source,
        quantity_source=quantity_source,
        order_no_source=brokerage.get("orderNo"),
        transaction=transaction,
        wash_relevant=wash_relevant,
        source_fields=dict(row),
    )
    return record, row_complete, diagnostics


def _first_alias(row: Mapping[str, object], keys: tuple[str, ...], field: str) -> object:
    present = [row[key] for key in keys if key in row]
    if not present:
        _fail("etrade_read_field_missing", f"E*TRADE {field} is missing.")
    if len(present) > 1 and any(value != present[0] for value in present[1:]):
        _fail("etrade_read_field_conflict", f"E*TRADE {field} fields conflict.")
    return present[0]


def _optional_mapping(value: object) -> Mapping[str, object]:
    if value is None:
        return {}
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        _fail("etrade_read_product_malformed", "E*TRADE product data is malformed.")
    return cast(Mapping[str, object], value)


def _required_text(row: Mapping[str, object], key: str, field: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        _fail("etrade_read_field_missing", f"E*TRADE {field} field is missing or invalid.")
    return value.strip()


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        _fail("etrade_read_field_invalid", f"E*TRADE {field} is invalid.")
    return value.strip()


def _first_optional_text(
    row: Mapping[str, object],
    secondary: Mapping[str, object],
    keys: tuple[str, ...],
    field: str,
) -> str | None:
    first_values = [row[key] for key in keys if key in row]
    second_values = [secondary[key] for key in keys if key in secondary]
    values = first_values + second_values
    if not values:
        return None
    if any(value != values[0] for value in values[1:]):
        _fail("etrade_read_field_conflict", f"E*TRADE {field} fields conflict.")
    return _optional_text(values[0], field)


def _validate_account_key(value: object) -> str:
    if not isinstance(value, str) or _ACCOUNT_KEY.fullmatch(value) is None:
        _fail("etrade_read_account_id_invalid", "E*TRADE returned an invalid account ID.")
    return value


def _identifier(value: object, field: str, *, maximum: int) -> str:
    if isinstance(value, bool):
        _fail("etrade_read_identifier_invalid", f"E*TRADE {field} is invalid.")
    if isinstance(value, int):
        identifier = str(value)
    elif isinstance(value, Decimal):
        if not value.is_finite() or value != value.to_integral_value():
            _fail("etrade_read_identifier_invalid", f"E*TRADE {field} is invalid.")
        identifier = str(int(value))
    elif isinstance(value, str):
        identifier = value
    else:
        _fail("etrade_read_identifier_invalid", f"E*TRADE {field} is invalid.")
    if not identifier or len(identifier) > maximum or not identifier.strip():
        _fail("etrade_read_identifier_invalid", f"E*TRADE {field} is invalid.")
    return identifier


def _decimal(value: object, field: str) -> Decimal:
    if isinstance(value, (bool, float)):
        _fail("etrade_read_quantity_invalid", f"E*TRADE {field} is invalid.")
    if not isinstance(value, (Decimal, int, str)):
        _fail("etrade_read_field_missing", f"E*TRADE {field} is missing or invalid.")
    try:
        result = Decimal(value)
    except ValueError, TypeError, ArithmeticError:
        _fail("etrade_read_quantity_invalid", f"E*TRADE {field} is invalid.")
    if not result.is_finite():
        _fail("etrade_read_quantity_invalid", f"E*TRADE {field} must be finite.")
    return result


def _asset_type(product: Mapping[str, object]) -> Literal["EQUITY", "ETF"]:
    security_type = product.get("securityType")
    if not isinstance(security_type, str) or security_type.strip().upper() != "EQ":
        _fail(
            "etrade_read_security_type_unsupported",
            "E*TRADE position security type is unsupported.",
        )
    if "securitySubType" not in product:
        return "EQUITY"
    security_subtype = product["securitySubType"]
    if not isinstance(security_subtype, str) or security_subtype.strip().upper() != "ETF":
        _fail(
            "etrade_read_security_type_unsupported",
            "E*TRADE position security type is unsupported.",
        )
    return "ETF"


def _product_id(product: Mapping[str, object]) -> BrokerProductId | None:
    value = product.get("productId")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal, dict)):
        _fail("etrade_read_product_id_invalid", "E*TRADE product identity is invalid.")
    if isinstance(value, str) and not value.strip():
        _fail("etrade_read_product_id_invalid", "E*TRADE product identity is invalid.")
    return value


def _acquired_date(row: Mapping[str, object]) -> tuple[date, Decimal | int | str]:
    raw = row.get("acquiredDate")
    if raw is None:
        _fail("etrade_read_field_missing", "E*TRADE lot acquisition date is missing.")
    if not isinstance(raw, (Decimal, int, str)) or isinstance(raw, bool):
        _fail("etrade_read_acquired_date_invalid", "E*TRADE acquisition timestamp is invalid.")
    milliseconds = _decimal(raw, "acquired date")
    if milliseconds != milliseconds.to_integral_value():
        _fail("etrade_read_acquired_date_invalid", "E*TRADE acquisition timestamp is invalid.")
    try:
        acquired = (
            (_UTC_EPOCH + timedelta(milliseconds=int(milliseconds))).astimezone(_EASTERN).date()
        )
    except OverflowError, ValueError:
        _fail("etrade_read_acquired_date_invalid", "E*TRADE acquisition timestamp is invalid.")
    return acquired, raw


def _exact_unit_basis(total_cost: Decimal, remaining: Decimal) -> Decimal:
    ratio = Fraction(total_cost) / Fraction(remaining)
    denominator = ratio.denominator
    twos = 0
    fives = 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    if denominator != 1:
        _fail(
            "etrade_read_basis_unrepresentable",
            "E*TRADE total cost cannot be represented as an exact decimal unit basis.",
        )
    scale = max(twos, fives)
    coefficient = ratio.numerator * (10**scale // ratio.denominator)
    sign = 1 if coefficient < 0 else 0
    digits = tuple(int(digit) for digit in str(abs(coefficient)))
    return Decimal((sign, digits, -scale))


def _page_markers(row: Mapping[str, object], current_page: int) -> _PageMarkers:
    totals = [
        _page_integer(row[key], "total page count")
        for key in ("totalNoOfPages", "totalPages")
        if key in row and row[key] is not None
    ]
    if len(totals) > 1 and any(total != totals[0] for total in totals[1:]):
        _fail("etrade_read_pagination_conflict", "E*TRADE portfolio page totals conflict.")
    total_pages = totals[0] if totals else None
    if total_pages is not None and (total_pages < 1 or current_page > total_pages):
        _fail("etrade_read_pagination_invalid", "E*TRADE portfolio page total is invalid.")
    if total_pages is not None and total_pages > _MAX_PAGES:
        _fail("etrade_read_page_limit", "E*TRADE portfolio exceeded the page limit.")

    explicit: list[int] = []
    if "next" in row and row["next"] is not None:
        explicit.append(_next_url_page(row["next"]))
    if "nextPageNo" in row and row["nextPageNo"] is not None:
        explicit.append(_page_integer(row["nextPageNo"], "next page number"))
    if len(explicit) > 1 and any(page != explicit[0] for page in explicit[1:]):
        _fail("etrade_read_pagination_conflict", "E*TRADE portfolio continuation markers conflict.")
    next_page = explicit[0] if explicit else None
    if next_page is not None and next_page <= current_page:
        _fail(
            "etrade_read_pagination_repeated",
            "E*TRADE portfolio continuation marker repeated a page.",
        )
    if next_page is not None and next_page != current_page + 1:
        _fail("etrade_read_pagination_invalid", "E*TRADE portfolio pagination is inconsistent.")
    if total_pages is not None:
        expected_next = current_page + 1 if current_page < total_pages else None
        if next_page is not None and next_page != expected_next:
            _fail("etrade_read_pagination_conflict", "E*TRADE portfolio page markers conflict.")
        next_page = expected_next
    return _PageMarkers(next_page, total_pages)


def _next_url_page(value: object) -> int:
    if not isinstance(value, str) or not value:
        _fail("etrade_read_pagination_invalid", "E*TRADE portfolio continuation marker is invalid.")
    query = parse_qs(urlsplit(value).query, keep_blank_values=True)
    pages = query.get("pageNumber", [])
    if len(pages) != 1:
        _fail("etrade_read_pagination_invalid", "E*TRADE portfolio continuation marker is invalid.")
    return _page_integer(pages[0], "next page number")


def _page_integer(value: object, field: str) -> int:
    if isinstance(value, bool):
        _fail("etrade_read_pagination_invalid", f"E*TRADE {field} is invalid.")
    if isinstance(value, int):
        result = value
    elif (
        isinstance(value, Decimal) and value.is_finite() and value == value.to_integral_value()
    ) or (isinstance(value, str) and value.isascii() and value.isdecimal()):
        result = int(value)
    else:
        _fail("etrade_read_pagination_invalid", f"E*TRADE {field} is invalid.")
    return result
