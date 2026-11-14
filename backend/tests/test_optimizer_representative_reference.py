from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from optimizer_quality_cases import build_small_quality_case
from optimizer_representative_reference import search_representative_best_known

from app.domain.financial_inputs import FinancialInputs, PolicySettings
from app.domain.portfolio_accounting import ConsolidatedLeg, LotAllocation
from app.optimizer.validation import validate_candidate


def _multi_lot_incumbent(inputs: FinancialInputs) -> tuple[ConsolidatedLeg, ...]:
    return (
        ConsolidatedLeg(
            leg_id="sell:EQ1",
            side="SELL",
            ticker="EQ1",
            shares=Decimal(2),
            estimated_unit_price_usd=Decimal("9.99"),
            selected_lots=(
                LotAllocation("EQ1-L1", Decimal(1)),
                LotAllocation("EQ1-L2", Decimal(1)),
            ),
            sequence=0,
            group_ids=("sale:EQ1",),
        ),
    )


def _coupled_sector_inputs() -> FinancialInputs:
    inputs = build_small_quality_case("sector-constraints", 20261120).inputs
    positions = tuple(
        replace(
            row,
            shares=Decimal(7) if row.ticker == "EQ1" else Decimal(3),
            market_value_usd=Decimal(70) if row.ticker == "EQ1" else Decimal(30),
        )
        for row in inputs.positions
    )
    lots = (
        replace(inputs.lots[0], shares=Decimal(3), available_shares=Decimal(3)),
        replace(inputs.lots[1], shares=Decimal(4), available_shares=Decimal(4)),
        replace(inputs.lots[2], shares=Decimal(3), available_shares=Decimal(3)),
    )
    settings: dict[str, object] = dict(inputs.policy.settings.values)
    settings["cash_reserve_usd"] = Decimal(4)
    return replace(
        inputs,
        account=replace(
            inputs.account,
            cash_usd=Decimal(0),
            settled_buying_power_usd=Decimal(0),
        ),
        policy=replace(inputs.policy, settings=PolicySettings.from_mapping(settings)),
        positions=positions,
        lots=lots,
    )


def test_reference_consolidates_multiple_lots_and_charges_one_sell_fee() -> None:
    inputs = build_small_quality_case("fee-consolidation", 20261113).inputs
    result = search_representative_best_known(
        inputs, (), seed=7, max_candidate_count=12, time_limit_seconds=5
    )

    example = next(row for row in result.candidate_trace if row.source == "multi_lot_sell")
    assert result.pool_complete
    assert example.validation_completed
    assert len(example.legs) == 1
    sell = example.legs[0]
    assert sell.side == "SELL"
    assert sell.ticker == "EQ1"
    assert sell.shares == Decimal(2)
    assert tuple(row.broker_lot_id for row in sell.selected_lots) == ("EQ1-L1", "EQ1-L2")
    assert example.estimated_trading_cost_usd == Decimal("2.02")


def test_seeded_search_finds_funded_coupled_trade_when_isolated_legs_fail() -> None:
    inputs = _coupled_sector_inputs()
    result = search_representative_best_known(
        inputs, (), seed=0, max_candidate_count=120, time_limit_seconds=8
    )

    coupled = next(row for row in result.candidate_trace if row.source == "coupled")
    assert coupled.validation_completed
    assert coupled.feasible
    sell = next(leg for leg in coupled.legs if leg.side == "SELL")
    buy = next(leg for leg in coupled.legs if leg.side == "BUY")
    assert sell.ticker == "EQ1"
    assert buy.ticker == "ETF_A"
    assert buy.depends_on_leg_ids == (sell.leg_id,)
    assert validate_candidate(inputs, (sell,)).accepted is False

    isolated_buy = replace(buy, depends_on_leg_ids=(), sequence=0)
    assert validate_candidate(inputs, (isolated_buy,)).accepted is False
    assert validate_candidate(inputs, coupled.legs).accepted


def test_incumbent_is_revalidated_and_kept_when_search_budget_stops() -> None:
    inputs = build_small_quality_case("fee-consolidation", 20261114).inputs
    incumbent = _multi_lot_incumbent(inputs)
    direct = validate_candidate(inputs, incumbent)
    baseline = validate_candidate(inputs, ())
    assert direct.accepted
    assert direct.objective_value is not None
    assert baseline.accepted
    assert baseline.objective_value is not None
    assert direct.objective_value < baseline.objective_value

    result = search_representative_best_known(
        inputs, incumbent, seed=3, max_candidate_count=2, time_limit_seconds=5
    )
    assert result.incumbent_assessment.validation_completed
    assert result.incumbent_assessment.feasible
    assert result.incumbent_assessment.legs == incumbent
    assert result.no_trade_assessment.feasible
    assert result.best_known is not None
    assert result.best_known.legs == incumbent
    assert result.candidate_proposal_count == 2
    assert result.validation_attempt_count == 2
    assert result.stop_reason == "candidate_budget"
    assert not result.search_complete
    assert not result.global_optimality_proven


def test_tiny_deadline_is_reported_including_metadata_and_validation_counts() -> None:
    inputs = build_small_quality_case("fee-consolidation", 20261115).inputs
    result = search_representative_best_known(
        inputs, (), seed=4, max_candidate_count=20, time_limit_seconds=1e-300
    )

    assert result.stop_reason == "deadline"
    assert result.candidate_proposal_count == 1
    assert result.validation_attempt_count == 0
    assert result.pool_scan_count == 0
    assert not result.pool_complete
    assert not result.no_trade_assessment.validation_completed
    assert not result.metadata_within_time_budget
    assert not result.search_complete
    assert not result.global_optimality_proven


def test_seed_repeats_candidates_and_cutoffs_are_counted_truthfully() -> None:
    inputs = build_small_quality_case("tiny-replacement-buy", 20261116).inputs
    first = search_representative_best_known(
        inputs, (), seed=19, max_candidate_count=10, time_limit_seconds=5
    )
    second = search_representative_best_known(
        inputs, (), seed=19, max_candidate_count=10, time_limit_seconds=5
    )

    assert first.seed == second.seed == 19
    assert first.input_checksum == second.input_checksum
    assert first.candidate_trace == second.candidate_trace
    assert first.generation_mode_attempts == second.generation_mode_attempts
    assert first.candidate_proposal_count == second.candidate_proposal_count == 10
    assert first.validation_attempt_count <= first.candidate_proposal_count
    assert first.unique_candidate_count <= first.candidate_proposal_count
    assert first.stop_reason == second.stop_reason == "candidate_budget"
    assert not first.search_complete
    assert not first.global_optimality_proven
