from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

import app.domain.wash as wash_module
from app.domain.allocation import AllocationPolicy, SecurityIdentity
from app.domain.exposure import (
    ExposureSourceFreshness,
    aggregate_lookthrough_exposure,
    exposure_overlap,
)
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
from app.domain.wash import (
    ProposedBuy,
    ProposedLotSale,
    WashAssessmentDeadlineError,
    assess_proposed_buys,
    assess_wash_sales,
)

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
    realized_pl_usd: str | None = None,
) -> TransactionInput:
    return TransactionInput(
        broker_transaction_key=key,
        ticker=ticker,
        transaction_kind=kind,
        transaction_time=datetime.combine(trade_date, datetime.min.time(), tzinfo=UTC),
        trade_date=trade_date,
        shares=Decimal(shares),
        amount_usd=Decimal(0),
        realized_pl_usd=Decimal(realized_pl_usd) if realized_pl_usd is not None else None,
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


@pytest.mark.parametrize(("days_since_loss", "blocked"), [(0, True), (30, True), (31, False)])
def test_executed_loss_blocks_buy_through_day_30_but_not_day_31(
    days_since_loss: int, blocked: bool
) -> None:
    loss_date = TRADE_DATE - timedelta(days=days_since_loss)
    executed_loss = _transaction(
        "executed-loss",
        trade_date=loss_date,
        lot_id=None,
        kind="SELL",
        is_acquisition=False,
        realized_pl_usd="-5",
    )
    buy = ProposedBuy("XYZ", Decimal(1), "replacement", TRADE_DATE)
    inputs = _inputs(
        transactions=(executed_loss,),
        metadata=_metadata(history_start=TRADE_DATE - timedelta(days=31)),
    )

    assessment = assess_proposed_buys(inputs, (buy,))[0]

    assert assessment.eligible is not blocked
    assert ("executed_loss_restriction" in assessment.reasons) is blocked
    assert assessment.conflicting_transaction_keys == (("executed-loss",) if blocked else ())
    if blocked:
        assert assessment.no_buy_through == loss_date + timedelta(days=30)
        assert assessment.next_eligible_purchase_date == loss_date + timedelta(days=31)
    else:
        assert assessment.no_buy_through is None
        assert assessment.next_eligible_purchase_date is None


def test_executed_loss_buy_check_requires_explicit_attribution_and_complete_history() -> None:
    buy = ProposedBuy("XYZ", Decimal(1), "replacement", TRADE_DATE)
    unknown_sale = _transaction(
        "unknown-loss",
        trade_date=TRADE_DATE - timedelta(days=3),
        lot_id=None,
        kind="SELL",
        is_acquisition=False,
    )
    unknown = assess_proposed_buys(_inputs(transactions=(unknown_sale,)), (buy,))[0]
    assert not unknown.eligible
    assert "executed_loss_attribution_unknown" in unknown.reasons
    assert unknown.conflicting_transaction_keys == ("unknown-loss",)

    gain_sale = _transaction(
        "known-gain",
        trade_date=TRADE_DATE - timedelta(days=3),
        lot_id="known-gain-lot",
        kind="SELL",
        is_acquisition=False,
        realized_pl_usd="10",
    )
    known_gain = assess_proposed_buys(_inputs(transactions=(gain_sale,)), (buy,))[0]
    assert known_gain.eligible
    assert not known_gain.reasons

    incomplete = assess_proposed_buys(_inputs(metadata=InputSourceMetadata()), (buy,))[0]
    assert not incomplete.eligible
    assert incomplete.reasons == ("incomplete_executed_loss_history",)


@pytest.mark.parametrize("order_level_pl", ["10", "0"])
def test_unattributed_nonnegative_sell_pl_does_not_clear_buy(
    order_level_pl: str,
) -> None:
    buy = ProposedBuy("XYZ", Decimal(1), "replacement", TRADE_DATE)
    consolidated_sale = _transaction(
        f"consolidated-{order_level_pl}",
        trade_date=TRADE_DATE - timedelta(days=3),
        lot_id=None,
        kind="SELL",
        is_acquisition=False,
        realized_pl_usd=order_level_pl,
    )

    assessment = assess_proposed_buys(_inputs(transactions=(consolidated_sale,)), (buy,))[0]

    assert not assessment.eligible
    assert assessment.reasons == ("executed_loss_attribution_unknown",)
    assert assessment.conflicting_transaction_keys == (consolidated_sale.broker_transaction_key,)


def test_executed_loss_sell_is_checked_even_when_flagged_as_acquisition() -> None:
    buy = ProposedBuy("XYZ", Decimal(1), "replacement", TRADE_DATE)
    contradictory_loss = _transaction(
        "loss-flagged-acquisition",
        trade_date=TRADE_DATE - timedelta(days=3),
        lot_id=None,
        kind="SELL",
        is_acquisition=True,
        realized_pl_usd="-5",
    )

    assessment = assess_proposed_buys(_inputs(transactions=(contradictory_loss,)), (buy,))[0]

    assert not assessment.eligible
    assert assessment.reasons == ("executed_loss_restriction",)
    assert assessment.conflicting_transaction_keys == ("loss-flagged-acquisition",)


def test_wash_action_dates_must_match_frozen_trade_date_and_proposed_losses_gate_buys() -> None:
    inputs = _inputs()
    with pytest.raises(
        ValueError, match="wash-sale action date must match frozen proposed trade date"
    ):
        assess_wash_sales(inputs, (_loss_sale(sale_date=TRADE_DATE - timedelta(days=1)),))

    wrong_date_buy = ProposedBuy("XYZ", Decimal(1), "replacement", TRADE_DATE + timedelta(days=1))
    with pytest.raises(
        ValueError, match="wash-sale action date must match frozen proposed trade date"
    ):
        assess_proposed_buys(inputs, (wrong_date_buy,))

    buy = ProposedBuy("XYZ", Decimal(1), "replacement", TRADE_DATE)
    assessment = assess_proposed_buys(inputs, (buy,), (_loss_sale(),))[0]
    assert not assessment.eligible
    assert assessment.reasons == ("proposed_loss_sale_restriction",)
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


def test_assess_wash_sales_without_deadline_keeps_legacy_results() -> None:
    inputs = _inputs()
    sales = (_loss_sale(),)

    assert assess_wash_sales(inputs, sales) == assess_wash_sales(inputs, sales, deadline=None)


def test_assess_wash_sales_checks_deadline_during_transaction_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = _inputs(
        transactions=tuple(
            _transaction(
                f"recent-buy-{index}",
                trade_date=TRADE_DATE,
                lot_id=f"recent-lot-{index}",
            )
            for index in range(65)
        )
    )
    clock_reads = 0

    def expire_during_scan() -> float:
        nonlocal clock_reads
        clock_reads += 1
        return 1.0 if clock_reads >= 5 else 0.0

    monkeypatch.setattr(wash_module.time, "monotonic", expire_during_scan)
    with pytest.raises(WashAssessmentDeadlineError, match="wash-sale assessment deadline exceeded"):
        assess_wash_sales(inputs, (_loss_sale(),), deadline=1.0)

    assert clock_reads == 5


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


def test_lookthrough_uses_one_latest_snapshot_and_does_not_resurrect_removed_constituents() -> None:
    inputs = _inputs(
        positions=(_position("FUND", "100"),),
        exposures=(
            _exposure("FUND", "AAA", "0.6", as_of_date=TRADE_DATE - timedelta(days=1)),
            _exposure("FUND", "BBB", "0.4", as_of_date=TRADE_DATE - timedelta(days=1)),
            _exposure("FUND", "AAA", "1.0", as_of_date=TRADE_DATE),
        ),
    )

    aggregate = aggregate_lookthrough_exposure(inputs)
    values = {row.exposure_key: row.value_usd for row in aggregate.values}

    assert aggregate.coverage.complete is True
    assert values == {"AAA": Decimal("100.0")}
    assert aggregate.coverage.duplicate_rows_removed == 2


def test_lookthrough_falls_back_to_a_current_provider_snapshot() -> None:
    inputs = _inputs(
        positions=(_position("FUND", "100"),),
        exposures=(
            _exposure("FUND", "AAA", "1.0", as_of_date=TRADE_DATE - timedelta(days=96)),
            _exposure(
                "FUND", "AAA", "0.5", provider="ishares", as_of_date=TRADE_DATE - timedelta(days=2)
            ),
        ),
    )

    aggregate = aggregate_lookthrough_exposure(inputs)

    assert aggregate.coverage.complete is True
    assert aggregate.values[0].value_usd == Decimal("50.0")
    assert aggregate.coverage.sources == (
        ExposureSourceFreshness("ishares", TRADE_DATE - timedelta(days=2)),
    )


def test_requested_dimension_requires_coverage_for_every_selected_holding() -> None:
    inputs = _inputs(
        positions=(_position("FUND-A", "100"), _position("FUND-B", "50")),
        exposures=(
            _exposure("FUND-A", "AAA", "1", dimension="security"),
            _exposure("FUND-B", "BBB", "1", dimension="security"),
            _exposure("FUND-A", "US", "1", dimension="region"),
        ),
    )

    security = aggregate_lookthrough_exposure(inputs)
    region = aggregate_lookthrough_exposure(inputs, dimension="region")
    selected_region = aggregate_lookthrough_exposure(
        inputs, tickers=("FUND-A",), dimension="region"
    )

    assert security.coverage.complete is True
    assert region.coverage.complete is False
    assert region.coverage.missing_tickers == ("FUND-B",)
    assert exposure_overlap(region, region, dimension="region").overlap_pct is None
    assert selected_region.coverage.complete is True
    assert (
        exposure_overlap(security, security, dimension="region").reason
        == "requested_dimension_not_aggregated"
    )


def test_direct_equity_requires_explicit_non_security_exposure_coverage() -> None:
    direct_equity = _position("AAA", "100", asset_type="EQUITY")
    missing = aggregate_lookthrough_exposure(
        _inputs(positions=(direct_equity,)), dimension="region"
    )
    covered = aggregate_lookthrough_exposure(
        _inputs(
            positions=(direct_equity,),
            exposures=(_exposure("AAA", "US", "1", dimension="region"),),
        ),
        dimension="region",
    )

    assert missing.coverage.complete is False
    assert missing.coverage.missing_tickers == ("AAA",)
    assert covered.coverage.complete is True
    assert covered.values[0].value_usd == Decimal(100)


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
            _exposure("FUND", "AAA", "0.6", provider="vanguard"),
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


def test_sector_coverage_requires_exact_unit_weight_per_ticker() -> None:
    holdings = (_position("A", "50"), _position("B", "50"), _position("C", "50"))
    exposures = (
        _exposure("A", "Technology", "0.4", dimension="sector"),
        _exposure("A", "Health", "0.4", dimension="sector"),
        _exposure("B", "Technology", "0.6", dimension="sector"),
        _exposure("B", "Health", "0.6", dimension="sector"),
        _exposure("C", "Technology", "0.3", dimension="sector"),
        _exposure("C", "Health", "0.7", dimension="sector"),
    )
    inputs = _inputs(positions=holdings, exposures=exposures)

    portfolio = aggregate_lookthrough_exposure(inputs, dimension="sector")
    traded = aggregate_lookthrough_exposure(inputs, tickers=("C",), dimension="sector")

    assert portfolio.coverage.complete is False
    assert portfolio.coverage.invalid_tickers == ("A", "B")
    assert traded.coverage.complete is True


def test_sector_coverage_accepts_exact_decimal_unit_weight_without_normalizing() -> None:
    inputs = _inputs(
        positions=(_position("FUND", "100"),),
        exposures=(
            _exposure("FUND", "Technology", "0.1", dimension="sector"),
            _exposure("FUND", "Health", "0.2", dimension="sector"),
            _exposure("FUND", "Utilities", "0.7", dimension="sector"),
        ),
    )

    aggregate = aggregate_lookthrough_exposure(inputs, dimension="sector")

    assert aggregate.coverage.complete is True
    assert aggregate.coverage.invalid_tickers == ()
    assert sum(row.value_usd for row in aggregate.values) == Decimal("100.0")


@pytest.mark.parametrize(
    ("first_weight", "second_weight"),
    [("0.4", "0.4"), ("0.6", "0.6")],
)
def test_sector_coverage_rejects_under_and_overallocated_ticker(
    first_weight: str, second_weight: str
) -> None:
    inputs = _inputs(
        positions=(_position("FUND", "100"),),
        exposures=(
            _exposure("FUND", "Technology", first_weight, dimension="sector"),
            _exposure("FUND", "Health", second_weight, dimension="sector"),
        ),
    )

    aggregate = aggregate_lookthrough_exposure(inputs, dimension="sector")

    assert aggregate.coverage.complete is False
    assert aggregate.coverage.invalid_tickers == ("FUND",)


@pytest.mark.parametrize("dimension", ["security", "region"])
def test_non_sector_coverage_does_not_gain_unit_sum_assumption(dimension: str) -> None:
    inputs = _inputs(
        positions=(_position("FUND", "100"),),
        exposures=(_exposure("FUND", "A", "0.6", dimension=dimension),),
    )

    aggregate = aggregate_lookthrough_exposure(inputs, dimension=dimension)

    assert aggregate.coverage.complete is True


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
