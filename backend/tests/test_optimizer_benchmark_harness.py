from __future__ import annotations

import asyncio

from app.optimizer.runtime import WorkerTimeoutError
from scripts.benchmark_optimizer import percentile, run_trial


def test_percentile_is_nearest_rank_for_small_samples() -> None:
    assert percentile([3.0, 1.0, 2.0], 0.50) == 2.0
    assert percentile([3.0, 1.0, 2.0], 0.95) == 3.0
    assert percentile([], 0.95) is None
    assert percentile([1.0, 2.0, 3.0, 4.0], 0.50) == 2.0
    assert percentile([1.0, 2.0, 3.0, 4.0, 5.0], 0.60) == 3.0


def test_trial_timeout_is_recorded_instead_of_aborting_benchmark() -> None:
    class TimedOutSupervisor:
        async def run(self, *args: object, **kwargs: object) -> None:
            raise WorkerTimeoutError("optimizer computation deadline exceeded")

    row = asyncio.run(run_trial(19, TimedOutSupervisor()))  # type: ignore[arg-type]
    assert row["status"] == "failed"
    assert row["error_type"] == "WorkerTimeoutError"
    assert row["error"] == "optimizer computation deadline exceeded"
    assert row["accepted"] is False


def test_trial_defaults_to_baseline_and_forwards_scenario(monkeypatch: object) -> None:
    from types import SimpleNamespace

    import scripts.benchmark_optimizer as benchmark

    scenario_calls: list[str] = []
    inputs = SimpleNamespace(
        policy=SimpleNamespace(
            settings=SimpleNamespace(values=(("max_sell_tickers_per_batch", 1),))
        ),
        positions=[1],
        securities=[1, 2],
        lots=[SimpleNamespace(available_shares=1)],
    )
    monkeypatch.setattr(
        benchmark,
        "build_optimizer_benchmark_inputs",
        lambda seed, scenario="baseline": scenario_calls.append(scenario) or inputs,
    )
    legs = ()
    metadata = SimpleNamespace(
        warnings=(),
        screening_seconds=0.1,
        solve_seconds=0.2,
        repair_validate_rank_seconds=0.3,
        elapsed_seconds=0.5,
        tax_regions_considered=1,
        tax_regions_solved=1,
        tax_region_search_complete=True,
        integer_search_complete=False,
        rounding_attempts=1,
        candidate_types=(),
        implementation_version="test",
        solver_versions=(),
        solver="fake",
    )
    result = SimpleNamespace(status="ready", legs=legs, metadata=metadata)

    async def fake_run(*args: object, **kwargs: object) -> object:
        return SimpleNamespace(value=(result, 123), overall_deadline=float("inf"))

    monkeypatch.setattr(
        benchmark,
        "validate_candidate",
        lambda *args, **kwargs: SimpleNamespace(accepted=True, reasons=(), warnings=()),
    )

    class FakeSupervisor:
        run = fake_run

    default_row = asyncio.run(run_trial(1, FakeSupervisor()))
    scenario_row = asyncio.run(run_trial(2, FakeSupervisor(), scenario="recent_loss"))
    assert scenario_calls == ["baseline", "recent_loss"]
    assert default_row["scenario"] == "baseline"
    assert scenario_row["scenario"] == "recent_loss"
    assert scenario_row["held_position_count"] == 1
    assert scenario_row["security_count"] == 2
    assert scenario_row["available_lot_count"] == 1
    assert (
        scenario_row["repair_all_validation_rank_seconds"]
        >= scenario_row["repair_validate_rank_seconds"]
    )


def test_path_coverage_requires_sell_dependent_buy_and_exact_recent_clearance() -> None:
    from decimal import Decimal
    from types import SimpleNamespace

    from scripts.benchmark_optimizer import _assess, _path_coverage

    sell = SimpleNamespace(
        side="SELL",
        leg_id="sell-1",
        selected_lots=(
            SimpleNamespace(broker_lot_id="EQ000-LOT-001", shares=Decimal(1)),
            SimpleNamespace(broker_lot_id="EQ000-LOT-002", shares=Decimal(2)),
        ),
    )
    buy = SimpleNamespace(
        side="BUY",
        leg_id="buy-1",
        shares=Decimal(1),
        depends_on_leg_ids=("sell-1",),
        selected_lots=(),
    )
    covered = _path_coverage("recent_loss", True, (sell, buy))
    assert covered["path_covered"] is True
    sell_only = _path_coverage("replacement_buy", True, (sell,))
    assert sell_only["path_covered"] is False
    assert sell_only["explicit_failure"] == "accepted_result_has_no_dependent_whole_share_buy"
    assert _assess([{"accepted": False, "screening_seconds": 0.01}], "screening_seconds", 1) is None
