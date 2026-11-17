from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.broker.etrade_read import (
    EtradeAccountCandidate,
    EtradeBalanceResult,
    EtradeQuoteCoverage,
    EtradeReadAdapter,
    EtradeTransactionHistory,
)
from app.db.models import Account, PolicyAllowedSecurity, PolicyRevision
from app.schemas import AllowedSecurityInput, BrokerSnapshot, CoverageInput, QuoteInput
from app.services.errors import AppError
from app.services.sync import validate_snapshot


class EtradeReadOnlyBroker:
    """Compose one complete, explicitly injected read-only E*TRADE snapshot."""

    mode = "etrade"

    def __init__(
        self,
        adapter: EtradeReadAdapter,
        session_factory: sessionmaker[Session],
        *,
        history_start_date: date,
        history_end_date: date,
    ) -> None:
        if (
            type(history_start_date) is not date
            or type(history_end_date) is not date
            or history_start_date > history_end_date
        ):
            raise ValueError("transaction history requires explicit ordered dates")
        self._adapter = adapter
        self._session_factory = session_factory
        self._history_start_date = history_start_date
        self._history_end_date = history_end_date

    def fetch_snapshot(self) -> BrokerSnapshot:
        """Read binding and candidates, then compose and validate all broker sections."""
        bound_account_id_key, candidates = self._read_binding_and_candidates()

        portfolio = self._adapter.fetch_portfolio_with_lots(
            previously_bound_account_id_key=bound_account_id_key
        )
        account = portfolio.account
        history = self._adapter.fetch_transactions(
            self._history_start_date,
            self._history_end_date,
            previously_bound_account_id_key=account.account_id_key,
        )
        balance = self._adapter.fetch_balances(
            previously_bound_account_id_key=account.account_id_key
        )
        quotes = self._adapter.get_quotes(
            [record.position for record in portfolio.positions], candidates
        )

        self._validate_section_identity(account, history, balance)
        self._validate_history(history)
        self._validate_quotes(quotes)

        snapshot = BrokerSnapshot(
            account_id_key=account.account_id_key,
            display_name=account.display_name,
            account_type=account.account_type,
            tax_treatment=account.tax_treatment,
            source="ETRADE",
            as_of=_balance_as_of_datetime(balance.as_of_source),
            cash_usd=balance.cash_usd,
            settled_buying_power_usd=balance.settled_cash_for_investment_usd,
            coverage=CoverageInput(
                positions=True,
                lots=True,
                transactions=history.coverage.transactions,
                balances=True,
                quotes=quotes.complete,
                lookthrough=False,
                transaction_history_start_date=self._history_start_date,
                transaction_history_end_date=self._history_end_date,
            ),
            positions=[record.position for record in portfolio.positions],
            lots=[record.lot for record in portfolio.lots],
            quotes=[
                QuoteInput(
                    ticker=record.ticker,
                    bid_usd=record.bid_usd,
                    ask_usd=record.ask_usd,
                    last_usd=record.last_usd,
                    source="ETRADE",
                    as_of=record.as_of,
                    quality=record.quality,
                )
                for record in quotes.records
                if record.as_of is not None
            ],
            transactions=list(history.transactions),
            balance_as_of_source_ms=balance.as_of_source,
            balance_received_at=balance.received_at,
            broker_position_metadata=[
                {
                    "ticker": record.position.ticker,
                    "broker_position_id": record.broker_position_id,
                    "broker_product_id": record.broker_product_id,
                    "as_of": portfolio.as_of,
                }
                for record in portfolio.positions
            ],
            broker_lot_metadata=[
                {
                    "ticker": record.ticker,
                    "broker_position_id": record.broker_position_id,
                    "broker_lot_id": record.broker_lot_id,
                    "total_cost_usd": record.total_cost_usd,
                    "total_cost_source": record.total_cost_source,
                    "reserved_shares": record.reserved_shares,
                    "acquired_date_source": record.acquired_date_source,
                }
                for record in portfolio.lots
            ],
        )
        validate_snapshot(snapshot)
        return snapshot

    def _read_binding_and_candidates(
        self,
    ) -> tuple[str | None, tuple[AllowedSecurityInput, ...]]:
        """Read only durable binding and enabled active-policy candidates before HTTP."""
        with self._session_factory() as session:
            account = session.get(Account, 1)
            bound_account_id_key = account.broker_account_id_key if account is not None else None
            active_policy_ids = session.scalars(
                select(PolicyRevision.id)
                .where(PolicyRevision.status == "ACTIVE")
                .order_by(PolicyRevision.revision_number.desc(), PolicyRevision.id)
            ).all()
            if len(active_policy_ids) > 1:
                raise AppError(
                    "active_policy_inconsistent",
                    "More than one active policy is configured; broker data was not read",
                    status_code=409,
                )
            if not active_policy_ids:
                return bound_account_id_key, ()

            allowed_rows = session.scalars(
                select(PolicyAllowedSecurity)
                .where(
                    PolicyAllowedSecurity.policy_revision_id == active_policy_ids[0],
                    PolicyAllowedSecurity.enabled.is_(True),
                )
                .order_by(
                    PolicyAllowedSecurity.ticker,
                    PolicyAllowedSecurity.priority,
                    PolicyAllowedSecurity.id,
                )
            ).all()
            candidates = tuple(
                AllowedSecurityInput(
                    ticker=row.ticker,
                    sleeve_key=row.sleeve_key,
                    sub_sleeve_key=row.sub_sleeve_key,
                    replacement_set_id=row.replacement_set_id,
                    priority=row.priority,
                    enabled=row.enabled,
                    exposure_suitability=row.exposure_suitability,
                )
                for row in allowed_rows
            )
        return bound_account_id_key, candidates

    @staticmethod
    def _validate_section_identity(
        account: EtradeAccountCandidate,
        history: EtradeTransactionHistory,
        balance: EtradeBalanceResult,
    ) -> None:
        for section_account in (history.account, balance.account):
            if section_account.account_id_key != account.account_id_key or (
                account.account_id is not None
                and section_account.account_id is not None
                and section_account.account_id != account.account_id
            ):
                raise AppError(
                    "etrade_read_cross_section_account_mismatch",
                    "E*TRADE read sections resolved different account identities",
                    status_code=409,
                )

    def _validate_history(self, history: EtradeTransactionHistory) -> None:
        if (
            history.requested_start_date != self._history_start_date
            or history.requested_end_date != self._history_end_date
            or history.coverage.transaction_history_start_date != self._history_start_date
            or history.coverage.transaction_history_end_date != self._history_end_date
        ):
            raise AppError(
                "etrade_read_history_bounds_mismatch",
                "E*TRADE transaction coverage did not match the requested history interval",
                status_code=422,
            )
        if not history.coverage.transactions:
            raise AppError(
                "incomplete_transaction_history",
                "E*TRADE transaction history is incomplete; current state was not changed",
                status_code=422,
            )

    @staticmethod
    def _validate_quotes(quotes: EtradeQuoteCoverage) -> None:
        if not quotes.complete:
            raise AppError(
                "incomplete_quote_coverage",
                "E*TRADE quote coverage is incomplete; current state was not changed",
                status_code=422,
                details={
                    "missing_symbols": list(quotes.missing_symbols),
                    "stale_symbols": list(quotes.stale_symbols),
                    "unusable_symbols": list(quotes.unusable_symbols),
                },
            )


def _balance_as_of_datetime(source_milliseconds: int) -> datetime:
    """Decode P1's balance-only Unix millisecond timestamp without float arithmetic."""
    if type(source_milliseconds) is not int or source_milliseconds < 0:
        raise AppError(
            "etrade_read_balance_as_of_invalid",
            "E*TRADE balance as-of timestamp is invalid",
            status_code=422,
        )
    try:
        return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(milliseconds=source_milliseconds)
    except (OverflowError, ValueError) as exc:
        raise AppError(
            "etrade_read_balance_as_of_invalid",
            "E*TRADE balance as-of timestamp is out of range",
            status_code=422,
        ) from exc
