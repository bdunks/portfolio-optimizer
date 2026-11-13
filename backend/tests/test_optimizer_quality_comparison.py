"""Tests for the provisional offline small-case optimizer comparison harness."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace

from scripts.compare_optimizer_quality import (
    _build_summaries,
    _production_domain_check,
    nearest_rank,
    objective_gap_percent,
    run_comparison,
)
from tests.optimizer_quality_cases import CASE_FAMILIES, build_small_quality_case


def test_small_quality_families_have_stable_seeded_checksums() -> None:
    assert len(CASE_FAMILIES) == 6
    assert len(set(CASE_FAMILIES)) == len(CASE_FAMILIES)
    for index, family in enumerate(CASE_FAMILIES):
        seed = 20261113 + index
        first = build_small_quality_case(family, seed)
        again = build_small_quality_case(family, seed)
        variant = build_small_quality_case(family, seed + 100)

        assert first.case_id == f"{family}-seed-{seed}"
        assert first.inputs.source_checksum == again.inputs.source_checksum
        assert first.inputs.source_checksum != variant.inputs.source_checksum
        assert first.universe == again.universe
        assert len(first.universe.sells) == 3
        assert len(first.universe.buys) == 2


def test_nearest_rank_and_nonpositive_objective_suppression() -> None:
    values = [Decimal(value) for value in range(1, 21)]
    assert nearest_rank(values, Decimal("0.95")) == Decimal(19)
    assert nearest_rank([], Decimal("0.95")) is None
    assert objective_gap_percent(Decimal(2), Decimal(10)) == Decimal(20)
    assert objective_gap_percent(Decimal(2), Decimal(0)) is None
    assert objective_gap_percent(Decimal(2), Decimal(-1)) is None


def test_out_of_domain_legs_are_not_clipped_or_counted_in_exact_denominators() -> None:
    case = build_small_quality_case("fee-consolidation", 20261113)
    leg = SimpleNamespace(
        side="SELL",
        ticker="EQ1",
        shares=Decimal(2),
        selected_lots=(
            SimpleNamespace(broker_lot_id="EQ1-L1", shares=Decimal(2)),
        ),
    )

    domain = _production_domain_check(case, (leg,))
    assert domain["in_domain"] is False
    assert "sell_lot_quantity_exceeds_bound:EQ1:EQ1-L1" in domain["reasons"]

    summary = _build_summaries(
        [
            {
                "case_id": "outside",
                "reference": {"complete": True, "feasible_basket_count": 1},
                "comparison": {
                    "exact_small_case_denominator_eligible": False,
                    "out_of_domain_production_candidate": True,
                    "missed_feasibility_case": False,
                    "missed_improvement_case": None,
                },
            },
            {
                "case_id": "in-domain",
                "reference": {"complete": True, "feasible_basket_count": 1},
                "comparison": {
                    "exact_small_case_denominator_eligible": True,
                    "out_of_domain_production_candidate": False,
                    "missed_feasibility_case": True,
                    "missed_improvement_case": False,
                },
            },
        ]
    )
    assert summary["exact_small_case_denominator_eligible_count"] == 1
    assert summary["out_of_domain_production_case_count"] == 1
    assert summary["missed_feasibility"] == {
        "numerator": 1,
        "denominator": 1,
        "synthetic_case_fraction_not_probability": "1",
        "eligible_case_ids": ["in-domain"],
    }
    assert summary["missed_improvement"]["numerator"] == 0
    assert summary["missed_improvement"]["denominator"] == 1


def test_one_real_spawned_production_comparison_is_provisional_and_bounded() -> None:
    report = asyncio.run(
        run_comparison(
            case_count=1,
            seed=20261113,
            max_assignments=64,
            reference_time_limit_seconds=2,
            production_timeout_seconds=10,
            validation_reserve_seconds=2,
        )
    )

    assert report["acceptance_claim"] is False
    assert report["assessment_status"] == "PROVISIONAL_NOT_ACCEPTANCE"
    assert report["run_bounds"]["production_process_supervisor_max_workers"] == 1
    assert len(report["cases"]) == 1
    row = report["cases"][0]
    assert row["reference"]["theoretical_assignment_count"] == 48
    assert row["reference"]["complete"] is True
    assert row["input_checksum_sha256"] == row["production"]["reported_input_checksum"]
    assert row["production"]["independently_revalidated"] is True
    assert row["production"]["supervisor_wall_seconds"] < 10
