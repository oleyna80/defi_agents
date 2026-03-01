from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Sequence

from .models import BandDepthResult, PitType


@dataclass(frozen=True)
class TickScanRuntimeMetrics:
    pits_found_count: int
    confident_pit_count: int
    scan_duration_p95_ms: float


def compute_scan_duration_p95_ms(scan_durations_ms: Sequence[float]) -> float:
    if not scan_durations_ms:
        return 0.0
    ordered = sorted(float(v) for v in scan_durations_ms)
    index = max(0, ceil(len(ordered) * 0.95) - 1)
    return ordered[index]


def summarize_tick_scan_runtime_metrics(
    scan_results: Sequence[BandDepthResult],
    scan_durations_ms: Sequence[float],
) -> TickScanRuntimeMetrics:
    pits_found_count = sum(max(0, int(result.pits_found)) for result in scan_results)
    confident_pit_count = sum(1 for result in scan_results if result.pit_type == PitType.CONFIDENT_PIT)
    return TickScanRuntimeMetrics(
        pits_found_count=pits_found_count,
        confident_pit_count=confident_pit_count,
        scan_duration_p95_ms=compute_scan_duration_p95_ms(scan_durations_ms),
    )
