from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.domain.allocation import AllocationPolicy, SecurityIdentity
from app.domain.exposure import aggregate_lookthrough_exposure, exposure_overlap
from app.domain.financial_inputs import (
    AccountInput,
    FinancialInputs,
    InputSourceMetadata,
    LookThroughExposureInput,
    LotInput,
    PolicyInput,
    PolicySettings,
    PositionInput,
    SecurityInput,
    TransactionInput,
    financial_inputs_from_provenance,
)
from app.domain.wash import ProposedBuy, ProposedLotSale, assess_wash_sales

TRADE_DATE = date(2026, 11, 13)
NOW = datetime(2026, 11, 13, 16, 0, tzinfo=UTC)


def _metadata(
    *,
    history_complete: bool | None = True,
    history_start: date | None = TRADE_DATE - timedelta(days=30),
    history_end: date | None = TRADE_DATE,
    lookthrough_complete: bool | None = True,
) -> InputSourceMetadata:
    return InputSourceMetadata(
        transaction_history_complete=history_complete,
        transaction_history_start_date=history_start,
        transaction_history_end_date=history_end,
        lookthrough_complete=lookthrough_complete,
    )


def _inputs(
    *,
    positions: tuple[PositionInput, ...] = (),
    lots: tuple[LotInput, ...] = (),
    transactions: tuple[TransactionInput, ...] = (),
    exposures: tuple[LookThroughExposureInput, ...] = (),
    metadata: InputSourceMetadata | None = None,
    asset_types: dict[str, str] | None = None,
) -> FinancialInputs:
    security_tickers = {position.ticker for position in positions}
    security_asset_types = {position.ticker: position.asset_type for position in positions}
    security_asset_types.update(asset_types or {})
    securities = tuple(
        SecurityInput(
            SecurityIdentity(
                ticker,
                security_asset_types.get(ticker, "ETF"),
                ticker in {"VB", "VXF"},
            )
        )
        for ticker in sorted(security_tickers)
    )
    return FinancialInputs(
        account=AccountInput(
            local_account_id=1,
            account_key_fingerprint="test-account",
            display_name="Test account",
            account_type="BROKERAGE",
            tax_treatment=None,
            source="TEST",
            as_of=NOW,
            cash_usd=Decimal(0),
            settled_buying_power_usd=Decimal(0),
        ),
        source_generation=1,
        proposed_trade_date=TRADE_DATE,
        policy=PolicyInput("test-policy", AllocationPolicy((), (), ()), PolicySettings(())),
        securities=securities,
        positions=positions,
        lots=lots,
        quotes=(),
        transactions=transactions,
        exposures=exposures,
        source_metadata=metadata if metadata is not None else _metadata(),
    )


def _lot(
    lot_id: str,
    *,
    acquired_date: date,
    shares: str = "10",
    available_shares: str | None = None,
    ticker: str = "XYZ",
) -> LotInput:
    return LotInput(
        ticker=ticker,
        broker_lot_id=lot_id,
        acquired_date=acquired_date,
        shares=Decimal(shares),
        available_shares=Decimal(available_shares if available_shares is not None else shares),
        adjusted_unit_basis_usd=Decimal(10),
        broker_wash_adjustment_usd=None,
        source="TEST",
        as_of=NOW,
        fractional_cleanup_unsupported=False,
        quality_flags=(),
        sync_generation=1,
    )


def _transaction(
    key: str,
    *,
    trade_date: date,
    lot_id: str | None,
    shares: str = "10",
    ticker: str = "XYZ",
    kind: str = "BUY",
    is_acquisition: bool = True,
) -> TransactionInput:
    return TransactionInput(
        broker_transaction_key=key,
        ticker=ticker,
        transaction_kind=kind,
        transaction_time=datetime.combine(trade_date, datetime.min.time(), tzinfo=UTC),
        trade_date=trade_date,
        shares=Decimal(shares),
        amount_usd=Decimal(0),
        is_acquisition=is_acquisition,
        broker_lot_id=lot_id,
        source="TEST",
    )


def _loss_sale(
    lot_id: str = "loss-lot",
    *,
    shares: str = "1",
    trade_group_id: str = "group-1",
    sale_date: date = TRADE_DATE,
    realized_pl: str = "-5",
    ticker: str = "XYZ",
) -> ProposedLotSale:
    return ProposedLotSale(
        ticker=ticker,
        broker_lot_id=lot_id,
        shares=Decimal(shares),
        realized_pl_usd=Decimal(realized_pl),
        trade_group_id=trade_group_id,
        sale_date=sale_date,
    )


def _position(ticker: str, value: str, *, asset_type: str = "ETF") -> PositionInput:
    return PositionInput(
        ticker=ticker,
        asset_type=asset_type,
        is_completion_etf=ticker in {"VB", "VXF"},
        shares=Decimal(1),
        sync_generation=1,
        as_of=NOW,
        market_value_usd=Decimal(value),
        assignment=None,
    )


def _exposure(
    ticker: str,
    key: str,
    weight: str,
    *,
    provider: str = "vanguard",
    as_of_date: date = TRADE_DATE,
    dimension: str = "security",
) -> LookThroughExposureInput:
    return LookThroughExposureInput(
        ticker=ticker,
        dimension=dimension,
        exposure_key=key,
        weight=Decimal(weight),
        provider=provider,
        as_of_date=as_of_date,
    )


@pytest.mark.parametrize(("days_before", "blocked"), [(30, True), (31, False)])
def test_acquisition_lookback_includes_day_30_but_not_day_31(
    days_before: int, blocked: bool
) -> None:
    acquisition_date = TRADE_DATE - timedelta(days=days_before)
    inputs = _inputs(
        transactions=(
            _transaction(
                "recent-buy", trade_date=acquisition_date, lot_id="recent-lot", kind="DRIP"
            ),
        )
    )

    assessment = assess_wash_sales(inputs, (_loss_sale(),))[0]

    assert ("recent_acquisition_not_fully_disposed" in assessment.reasons) is blocked
    assert assessment.eligible is not blocked
    assert assessment.conflicting_transaction_keys == (("recent-buy",) if blocked else ())


@pytest.mark.parametrize(("days_after", "blocked"), [(30, True), (31, False)])
def test_proposed_buy_forward_window_includes_day_30_not_day_31(
    days_after: int, blocked: bool
) -> None:
    buy = ProposedBuy(
        ticker="XYZ",
        shares=Decimal(1),
        trade_group_id="replacement",
        buy_date=TRADE_DATE + timedelta(days=days_after),
    )

    assessment = assess_wash_sales(_inputs(), (_loss_sale(),), (buy,))[0]

    assert ("proposed_same_security_buy" in assessment.reasons) is blocked
    assert assessment.eligible is not blocked
    assert assessment.no_buy_through == TRADE_DATE + timedelta(days=30)
    assert assessment.next_eligible_purchase_date == TRADE_DATE + timedelta(days=31)


def test_recent_acquisition_is_excepted_only_by_full_available_same_group_disposal() -> None:
    recent_lot = _lot("recent-lot", acquired_date=TRADE_DATE - timedelta(days=5))
    buy = _transaction(
        "buy-recent-lot", trade_date=TRADE_DATE - timedelta(days=5), lot_id="recent-lot"
    )
    loss_sale = _loss_sale()
    full_disposal = _loss_sale("recent-lot", shares="10", realized_pl="0")
    inputs = _inputs(lots=(recent_lot,), transactions=(buy,))

    same_group = assess_wash_sales(inputs, (loss_sale, full_disposal))[0]
    partial = assess_wash_sales(
        inputs,
        (loss_sale, _loss_sale("recent-lot", shares="9", realized_pl="0")),
    )[0]
    different_group = assess_wash_sales(
        inputs,
        (loss_sale, _loss_sale("recent-lot", shares="10", realized_pl="0", trade_group_id="other")),
    )[0]

    assert same_group.eligible
    assert not partial.eligible
    assert "recent_acquisition_not_fully_disposed" in partial.reasons
    assert not different_group.eligible
    assert "recent_acquisition_not_fully_disposed" in different_group.reasons


def test_recent_acquisition_requires_full_lot_availability_and_quantity_match() -> None:
    buy = _transaction("buy-recent", trade_date=TRADE_DATE - timedelta(days=5), lot_id="recent-lot")
    unavailable_lot = _lot(
        "recent-lot", acquired_date=TRADE_DATE - timedelta(days=5), available_shares="9"
    )
    sale = _loss_sale("recent-lot", shares="10", realized_pl="0")
    unavailable = assess_wash_sales(
        _inputs(lots=(unavailable_lot,), transactions=(buy,)),
        (_loss_sale(), sale),
    )[0]
    mismatched = assess_wash_sales(
        _inputs(
            lots=(_lot("recent-lot", acquired_date=TRADE_DATE - timedelta(days=5), shares="8"),),
            transactions=(buy,),
        ),
        (_loss_sale(), _loss_sale("recent-lot", shares="8", realized_pl="0")),
    )[0]

    assert "recent_acquisition_not_fully_disposed" in unavailable.reasons
    assert "recent_acquisition_quantity_mismatch" in mismatched.reasons


def test_unknown_or_incomplete_history_fails_closed_for_loss_sales() -> None:
    inputs = _inputs(metadata=InputSourceMetadata())

    assessment = assess_wash_sales(inputs, (_loss_sale(),))[0]

    assert not assessment.eligible
    assert assessment.reasons == ("incomplete_acquisition_history",)
    assert assess_wash_sales(inputs, (_loss_sale(realized_pl="0"),))[0].eligible


def test_lookthrough_aggregates_duplicate_and_direct_overlapping_holdings() -> None:
    left = _inputs(
        positions=(_position("FUND-L", "100"), _position("AAA", "50", asset_type="EQUITY")),
        exposures=(
            _exposure("FUND-L", "AAA", "0.6"),
            _exposure("FUND-L", "AAA", "0.6", provider="ishares"),
            _exposure("FUND-L", "BBB", "0.4"),
        ),
    )
    right = _inputs(
        positions=(_position("FUND-R", "100"),),
        exposures=(_exposure("FUND-R", "AAA", "0.25"), _exposure("FUND-R", "CCC", "0.75")),
    )

    left_aggregate = aggregate_lookthrough_exposure(left)
    right_aggregate = aggregate_lookthrough_exposure(right)
    left_values = {
        (row.dimension, row.exposure_key): row.value_usd for row in left_aggregate.values
    }
    overlap = exposure_overlap(left_aggregate, right_aggregate)

    assert left_aggregate.coverage.complete is True
    assert left_aggregate.coverage.duplicate_rows_removed == 1
    assert left_values[("security", "AAA")] == Decimal("110.0")
    assert left_values[("security", "BBB")] == Decimal("40.0")
    assert overlap.overlap_pct == Decimal("25.00")
    assert overlap.reason is None


def test_vb_and_vxf_cached_lookthrough_rows_are_included() -> None:
    inputs = _inputs(
        positions=(_position("VB", "100"), _position("VXF", "200")),
        exposures=(_exposure("VB", "AAA", "0.2"), _exposure("VXF", "BBB", "0.75")),
    )

    aggregate = aggregate_lookthrough_exposure(inputs)
    values = {(row.dimension, row.exposure_key): row.value_usd for row in aggregate.values}

    assert aggregate.coverage.complete is True
    assert values[("security", "AAA")] == Decimal("20.0")
    assert values[("security", "BBB")] == Decimal("150.00")


@pytest.mark.parametrize("failure", ["missing", "stale", "conflicting"])
def test_missing_stale_and_conflicting_lookthrough_coverage_fail_closed(failure: str) -> None:
    rows: tuple[LookThroughExposureInput, ...]
    if failure == "missing":
        rows = ()
    elif failure == "stale":
        rows = (_exposure("FUND", "AAA", "1", as_of_date=TRADE_DATE - timedelta(days=96)),)
    else:
        rows = (
            _exposure("FUND", "AAA", "0.7"),
            _exposure("FUND", "AAA", "0.6", provider="ishares"),
        )
    aggregate = aggregate_lookthrough_exposure(
        _inputs(positions=(_position("FUND", "100"),), exposures=rows)
    )
    overlap = exposure_overlap(aggregate, aggregate)

    assert aggregate.coverage.complete is False
    assert overlap.overlap_pct is None
    if failure == "missing":
        assert aggregate.coverage.missing_tickers == ("FUND",)
    elif failure == "stale":
        assert aggregate.coverage.stale_tickers == ("FUND",)
    else:
        assert aggregate.coverage.conflicting_tickers == ("FUND",)


def test_direct_equity_exposure_does_not_require_lookthrough_metadata() -> None:
    inputs = _inputs(
        positions=(_position("AAA", "100", asset_type="EQUITY"),),
        metadata=InputSourceMetadata(lookthrough_complete=False),
    )

    aggregate = aggregate_lookthrough_exposure(inputs)

    assert aggregate.coverage.complete is True
    assert aggregate.values[0].exposure_key == "AAA"
    assert aggregate.values[0].value_usd == Decimal(100)


def test_exposure_and_known_source_metadata_round_trip_and_legacy_absence_stays_unknown() -> None:
    inputs = _inputs(
        exposures=(_exposure("VTI", "AAA", "0.4", as_of_date=TRADE_DATE - timedelta(days=1)),),
        metadata=_metadata(
            history_start=TRADE_DATE - timedelta(days=60),
            lookthrough_complete=True,
        ),
    )
    bundle = inputs.to_provenance()
    restored = financial_inputs_from_provenance(bundle)

    assert restored == inputs
    legacy_bundle = dict(bundle)
    legacy_bundle.pop("exposures")
    legacy_bundle.pop("source_metadata")
    legacy_restored = financial_inputs_from_provenance(legacy_bundle)
    assert legacy_restored.exposures == ()
    assert legacy_restored.source_metadata.transaction_history_complete is None
    assert legacy_restored.source_metadata.lookthrough_complete is None
