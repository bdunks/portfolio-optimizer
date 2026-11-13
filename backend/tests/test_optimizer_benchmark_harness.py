from __future__ import annotations

from scripts.benchmark_optimizer import percentile


def test_percentile_is_nearest_rank_for_small_samples() -> None:
    assert percentile([3.0, 1.0, 2.0], 0.50) == 2.0
    assert percentile([3.0, 1.0, 2.0], 0.95) == 3.0
    assert percentile([], 0.95) is None
