"""Tests for the provisional offline small-case optimizer comparison harness."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace

from scripts.compare_optimizer_quality import (
    _build_summaries,
    _compare_case,
    _git_value,
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

        assert first.case_id == f"{family}-seed-{seed}"
        assert first.inputs.source_checksum == again.inputs.source_checksum
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
        selected_lots=(SimpleNamespace(broker_lot_id="EQ1-L1", shares=Decimal(2)),),
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


def test_production_worker_failures_count_against_complete_reference() -> None:

    case = build_small_quality_case("fee-consolidation", 20261113)

    class FailingSupervisor:
        def __init__(self, error: Exception) -> None:
            self.error = error

        async def run(self, *args: object, **kwargs: object) -> object:
            raise self.error

    for error in (TimeoutError("supervisor deadline"), RuntimeError("worker failed")):
        row = asyncio.run(
            _compare_case(
                case, FailingSupervisor(error), max_assignments=64,
                reference_time_limit_seconds=2, production_timeout_seconds=1,
                validation_reserve_seconds=0,
            )
        )
        assert row["reference"]["complete"] is True
        assert row["production"]["reported_input_checksum"] is None
        assert row["submitted_request_input_checksum"] == case.inputs.source_checksum
        assert row["comparison"]["exact_small_case_denominator_eligible"] is True
        assert row["comparison"]["missed_feasibility_case"] is True
        assert row["comparison"]["economic_metrics"]["production"] is None
        assert row["comparison"]["economic_metrics"]["reference"] is not None


def test_owner_validation_deadline_failure_counts_as_missed_feasibility() -> None:
    import time

    case = build_small_quality_case("fee-consolidation", 20261113)
    metadata = SimpleNamespace(source_checksum=case.inputs.source_checksum)

    class LateResultSupervisor:
        async def run(self, *args: object, **kwargs: object) -> object:
            return SimpleNamespace(
                value=SimpleNamespace(status="no_trade", legs=(), metadata=metadata),
                overall_deadline=time.monotonic() - 1,
            )

    row = asyncio.run(
        _compare_case(
            case, LateResultSupervisor(), max_assignments=64,
            reference_time_limit_seconds=2, production_timeout_seconds=1,
            validation_reserve_seconds=0,
        )
    )
    assert row["reference"]["complete"] is True
    assert row["production"]["error_type"] == "TimeoutError"
    assert row["comparison"]["exact_small_case_denominator_eligible"] is True
    assert row["comparison"]["missed_feasibility_case"] is True


def test_malformed_worker_output_is_production_failure_and_reference_still_runs() -> None:
    case = build_small_quality_case("fee-consolidation", 20261113)
    malformed_leg = SimpleNamespace(side="SELL", shares=Decimal(1), selected_lots=())
    metadata = SimpleNamespace(source_checksum=case.inputs.source_checksum)

    class ReturningSupervisor:
        async def run(self, *args: object, **kwargs: object) -> object:
            return SimpleNamespace(
                value=SimpleNamespace(status="ready", legs=(malformed_leg,), metadata=metadata),
                overall_deadline=10**9,
            )

    row = asyncio.run(
        _compare_case(
            case, ReturningSupervisor(), max_assignments=64,
            reference_time_limit_seconds=2, production_timeout_seconds=1,
            validation_reserve_seconds=0,
        )
    )
    assert row["reference"]["complete"] is True
    assert "fixture_error" not in row
    assert row["production"]["status"] == "failed"
    assert row["production"]["malformed_output"] is True
    assert row["production"]["error_type"] is not None
    assert row["comparison"]["out_of_domain_production_candidate"] is False
    assert row["comparison"]["exact_small_case_denominator_eligible"] is True
    assert row["comparison"]["missed_feasibility_case"] is True

def test_checksum_mismatch_and_actual_out_of_domain_output_remain_excluded() -> None:
    case = build_small_quality_case("fee-consolidation", 20261113)

    def result(legs: tuple[object, ...], checksum: str) -> object:
        metadata = SimpleNamespace(source_checksum=checksum)
        value = SimpleNamespace(status="failed", legs=legs, metadata=metadata)
        return SimpleNamespace(value=value, overall_deadline=10**9)

    class FixedSupervisor:
        def __init__(self, worker_result: object) -> None:
            self.worker_result = worker_result

        async def run(self, *args: object, **kwargs: object) -> object:
            return self.worker_result

    oversized_leg = SimpleNamespace(
        leg_id="sell-eq1", side="SELL", ticker="EQ1", shares=Decimal(2),
        estimated_unit_price_usd=Decimal(10),
        selected_lots=(SimpleNamespace(broker_lot_id="EQ1-L1", shares=Decimal(2)),),
        depends_on_leg_ids=(), sequence=1,
    )
    for worker_result in (
        result((), "different-checksum"),
        result((oversized_leg,), case.inputs.source_checksum),
    ):
        row = asyncio.run(
            _compare_case(
                case, FixedSupervisor(worker_result), max_assignments=64,
                reference_time_limit_seconds=2, production_timeout_seconds=1,
                validation_reserve_seconds=0,
            )
        )
        assert row["reference"]["complete"] is True
        assert row["comparison"]["exact_small_case_denominator_eligible"] is False
        assert row["comparison"]["missed_feasibility_case"] is False


def test_sector_fixture_security_and_sector_dimensions_are_consistent() -> None:
    case = build_small_quality_case("sector-constraints", 20261113)
    for ticker in ("ETF_A", "ETF_B"):
        exposure = [row for row in case.inputs.exposures if row.ticker == ticker]
        sectors = {row.exposure_key: row.weight for row in exposure if row.dimension == "sector"}
        securities = {row.exposure_key: row.weight for row in exposure if row.dimension == "security"}
        from_security = {
            "technology": securities.get("EQ1", Decimal(0)),
            "healthcare": securities.get("EQ2", Decimal(0)),
        }
        assert from_security == sectors

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
    assert row["comparison"]["frozen_inputs_match"] is True
    assert row["production"]["independently_revalidated"] is True
    assert row["production"]["supervisor_wall_seconds"] < 10
    assert row["production"]["production_total_wall_seconds"] < 10


def test_file_last_commit_uses_repository_root_path_context() -> None:
    commit = _git_value(
        "log",
        "-1",
        "--format=%H",
        "--",
        "backend/tests/optimizer_quality_reference.py",
    )

    assert commit is not None
    assert len(commit) == 40
    assert all(character in "0123456789abcdef" for character in commit)
