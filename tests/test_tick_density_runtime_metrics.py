from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.lp.models import BandDepthResult, DataQuality, DegradationReason, PitType
from defi_agents.lp.runtime_metrics import (
    compute_scan_duration_p95_ms,
    summarize_tick_scan_runtime_metrics,
)


def test_compute_scan_duration_p95_ms_empty_returns_zero() -> None:
    assert compute_scan_duration_p95_ms([]) == pytest.approx(0.0)


def test_compute_scan_duration_p95_ms_uses_nearest_rank() -> None:
    durations = [float(i) for i in range(1, 21)]  # 1..20
    assert compute_scan_duration_p95_ms(durations) == pytest.approx(19.0)


def test_summarize_tick_scan_runtime_metrics_counts_and_p95() -> None:
    results = [
        BandDepthResult(
            pool_address="0x" + "1" * 40,
            pits_found=2,
            pit_type=PitType.CONFIDENT_PIT,
            data_quality=DataQuality.OK,
        ),
        BandDepthResult(
            pool_address="0x" + "2" * 40,
            pits_found=1,
            pit_type=PitType.NOISE_PIT,
            data_quality=DataQuality.OK,
        ),
        BandDepthResult(
            pool_address="0x" + "3" * 40,
            pits_found=0,
            pit_type=PitType.NONE,
            data_quality=DataQuality.DEGRADED,
            degradation_reason=DegradationReason.RPC_UNAVAILABLE,
        ),
    ]
    metrics = summarize_tick_scan_runtime_metrics(results, [10.0, 20.0, 30.0, 100.0])

    assert metrics.pits_found_count == 3
    assert metrics.confident_pit_count == 1
    assert metrics.scan_duration_p95_ms == pytest.approx(100.0)
