from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from .readiness import (
    normalize_readiness_blocker_code,
    normalize_readiness_blocker_counts,
)

_TELEMETRY_PREFIX = "LP entry stability telemetry:"
_READINESS_PREFIX = "Tick density readiness telemetry:"
_TELEMETRY_RE = re.compile(
    r"LP entry stability telemetry:\s+"
    r"entry_total=(?P<entry_total>\d+)\s+"
    r"entry_actionable=(?P<entry_actionable>\d+)\s+"
    r"entry_watchlist=(?P<entry_watchlist>\d+)\s+"
    r"entry_watchlist_insufficient_history=(?P<entry_watchlist_insufficient_history>\d+)\s+"
    r"entry_topn_churn=(?P<entry_topn_churn>-?\d+(?:\.\d+)?)"
    r"(?:\s+entry_input_total=(?P<entry_input_total>\d+))?"
    r"(?:\s+entry_lp_eligible_total=(?P<entry_lp_eligible_total>\d+))?"
    r"(?:\s+entry_lp_ineligible_total=(?P<entry_lp_ineligible_total>\d+))?"
    r"(?:\s+entry_range_ready_total=(?P<entry_range_ready_total>\d+))?"
    r"(?:\s+entry_range_missing_total=(?P<entry_range_missing_total>\d+))?"
    r"(?:\s+entry_target_scope_enabled=(?P<entry_target_scope_enabled>\d+))?"
    r"(?:\s+entry_target_input_total=(?P<entry_target_input_total>\d+))?"
    r"(?:\s+entry_target_matched_total=(?P<entry_target_matched_total>\d+))?"
    r"(?:\s+entry_target_excluded_total=(?P<entry_target_excluded_total>\d+))?"
    r"(?:\s+entry_target_reason=(?P<entry_target_reason>[A-Z0-9_]+))?"
    r"(?:\s+entry_selector_range_mode=(?P<entry_selector_range_mode>[A-Z]+))?"
    r"(?:\s+entry_selector_market_regime=(?P<entry_selector_market_regime>[A-Z]+))?"
    r"(?:\s+entry_selector_input_total=(?P<entry_selector_input_total>\d+))?"
    r"(?:\s+entry_selector_matched_total=(?P<entry_selector_matched_total>\d+))?"
    r"(?:\s+entry_selector_actionable_total=(?P<entry_selector_actionable_total>\d+))?"
    r"(?:\s+entry_selector_watchlist_total=(?P<entry_selector_watchlist_total>\d+))?"
    r"(?:\s+watchlist_reason_counts=(?P<watchlist_reason_counts>\S+))?"
    r"(?:\s+watchlist_blocker_reason_counts=(?P<watchlist_blocker_reason_counts>\S+))?"
)
_READINESS_RE = re.compile(
    r"Tick density readiness telemetry:\s+" r"blocker_counts=(?P<blocker_counts>\S+)"
)
_ERROR_RE = re.compile(r"\b(?:Traceback|CRITICAL|ERROR)\b")


@dataclass(frozen=True)
class EntryStabilityTelemetryPoint:
    entry_total: int
    entry_actionable: int
    entry_watchlist: int
    entry_watchlist_insufficient_history: int
    entry_topn_churn: float
    entry_input_total: int | None = None
    entry_lp_eligible_total: int | None = None
    entry_lp_ineligible_total: int | None = None
    entry_range_ready_total: int | None = None
    entry_range_missing_total: int | None = None
    entry_target_scope_enabled: int | None = None
    entry_target_input_total: int | None = None
    entry_target_matched_total: int | None = None
    entry_target_excluded_total: int | None = None
    entry_target_reason: str | None = None
    watchlist_reason_counts: dict[str, int] = field(default_factory=dict)
    watchlist_blocker_reason_counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class LpEntryShadowCalibrationSnapshot:
    cycles_with_entry_telemetry: int
    entry_total_sum: int
    actionable_ratio: float
    watchlist_ratio: float
    insufficient_history_ratio: float
    topn_churn_avg: float
    topn_churn_p95: float
    entry_input_total_sum: int
    entry_lp_eligible_total_sum: int
    entry_lp_ineligible_total_sum: int
    entry_range_ready_total_sum: int
    entry_range_missing_total_sum: int
    entry_target_scope_enabled_cycles: int
    entry_target_input_total_sum: int
    entry_target_matched_total_sum: int
    entry_target_excluded_total_sum: int
    entry_target_reason_counts: dict[str, int]
    watchlist_reason_counts: dict[str, int]
    watchlist_blocker_reason_counts: dict[str, int]
    tick_density_readiness_blocker_counts: dict[str, int]
    telemetry_parse_errors: int
    runtime_error_lines: int

    @property
    def total_errors(self) -> int:
        return int(self.telemetry_parse_errors) + int(self.runtime_error_lines)

    def to_dict(self) -> dict[str, int | float | dict[str, int]]:
        return {
            "cycles_with_entry_telemetry": self.cycles_with_entry_telemetry,
            "entry_total_sum": self.entry_total_sum,
            "actionable_ratio": self.actionable_ratio,
            "watchlist_ratio": self.watchlist_ratio,
            "insufficient_history_ratio": self.insufficient_history_ratio,
            "topn_churn_avg": self.topn_churn_avg,
            "topn_churn_p95": self.topn_churn_p95,
            "entry_input_total_sum": self.entry_input_total_sum,
            "entry_lp_eligible_total_sum": self.entry_lp_eligible_total_sum,
            "entry_lp_ineligible_total_sum": self.entry_lp_ineligible_total_sum,
            "entry_range_ready_total_sum": self.entry_range_ready_total_sum,
            "entry_range_missing_total_sum": self.entry_range_missing_total_sum,
            "entry_target_scope_enabled_cycles": self.entry_target_scope_enabled_cycles,
            "entry_target_input_total_sum": self.entry_target_input_total_sum,
            "entry_target_matched_total_sum": self.entry_target_matched_total_sum,
            "entry_target_excluded_total_sum": self.entry_target_excluded_total_sum,
            "entry_target_reason_counts": dict(self.entry_target_reason_counts),
            "watchlist_reason_counts": dict(self.watchlist_reason_counts),
            "watchlist_blocker_reason_counts": dict(
                self.watchlist_blocker_reason_counts
            ),
            "tick_density_readiness_blocker_counts": dict(
                self.tick_density_readiness_blocker_counts
            ),
            "telemetry_parse_errors": self.telemetry_parse_errors,
            "runtime_error_lines": self.runtime_error_lines,
            "total_errors": self.total_errors,
        }


@dataclass(frozen=True)
class LpEntryShadowCalibrationThresholds:
    telemetry_min_cycles: int = 24
    max_insufficient_history_ratio: float = 0.35
    max_topn_churn_avg: float = 0.45
    max_topn_churn_p95: float = 0.75

    def __post_init__(self) -> None:
        if int(self.telemetry_min_cycles) < 1:
            raise ValueError("telemetry_min_cycles must be >= 1")
        _validate_unit_interval(
            "max_insufficient_history_ratio",
            float(self.max_insufficient_history_ratio),
        )
        _validate_unit_interval("max_topn_churn_avg", float(self.max_topn_churn_avg))
        _validate_unit_interval("max_topn_churn_p95", float(self.max_topn_churn_p95))
        if float(self.max_topn_churn_avg) > float(self.max_topn_churn_p95):
            raise ValueError("max_topn_churn_avg must be <= max_topn_churn_p95")

    def to_dict(self) -> dict[str, int | float]:
        return {
            "telemetry_min_cycles": self.telemetry_min_cycles,
            "max_insufficient_history_ratio": self.max_insufficient_history_ratio,
            "max_topn_churn_avg": self.max_topn_churn_avg,
            "max_topn_churn_p95": self.max_topn_churn_p95,
        }


def parse_entry_stability_telemetry_line(
    line: str,
) -> EntryStabilityTelemetryPoint | None:
    match = _TELEMETRY_RE.search(line)
    if match is None:
        return None

    values = match.groupdict()
    try:
        point = EntryStabilityTelemetryPoint(
            entry_total=int(values["entry_total"]),
            entry_actionable=int(values["entry_actionable"]),
            entry_watchlist=int(values["entry_watchlist"]),
            entry_watchlist_insufficient_history=int(
                values["entry_watchlist_insufficient_history"]
            ),
            entry_topn_churn=float(values["entry_topn_churn"]),
            entry_input_total=_parse_optional_non_negative_int(
                values.get("entry_input_total")
            ),
            entry_lp_eligible_total=_parse_optional_non_negative_int(
                values.get("entry_lp_eligible_total")
            ),
            entry_lp_ineligible_total=_parse_optional_non_negative_int(
                values.get("entry_lp_ineligible_total")
            ),
            entry_range_ready_total=_parse_optional_non_negative_int(
                values.get("entry_range_ready_total")
            ),
            entry_range_missing_total=_parse_optional_non_negative_int(
                values.get("entry_range_missing_total")
            ),
            entry_target_scope_enabled=_parse_optional_non_negative_int(
                values.get("entry_target_scope_enabled")
            ),
            entry_target_input_total=_parse_optional_non_negative_int(
                values.get("entry_target_input_total")
            ),
            entry_target_matched_total=_parse_optional_non_negative_int(
                values.get("entry_target_matched_total")
            ),
            entry_target_excluded_total=_parse_optional_non_negative_int(
                values.get("entry_target_excluded_total")
            ),
            entry_target_reason=_parse_optional_reason_code(
                values.get("entry_target_reason")
            ),
            watchlist_reason_counts=_parse_reason_counts_blob(
                values.get("watchlist_reason_counts")
            ),
            watchlist_blocker_reason_counts=_parse_reason_counts_blob(
                values.get("watchlist_blocker_reason_counts"),
                normalize_readiness=True,
            ),
        )
    except (TypeError, ValueError):
        return None

    if (
        point.entry_total < 0
        or point.entry_actionable < 0
        or point.entry_watchlist < 0
        or point.entry_watchlist_insufficient_history < 0
        or point.entry_topn_churn < 0.0
    ):
        return None
    return point


def parse_tick_density_readiness_telemetry_line(line: str) -> dict[str, int] | None:
    match = _READINESS_RE.search(line)
    if match is None:
        return None
    return _parse_reason_counts_blob(
        match.group("blocker_counts"), normalize_readiness=True
    )


def summarize_entry_shadow_calibration(
    lines: Iterable[str],
) -> LpEntryShadowCalibrationSnapshot:
    points: list[EntryStabilityTelemetryPoint] = []
    watchlist_reason_counts_total: dict[str, int] = {}
    watchlist_blocker_reason_counts_total: dict[str, int] = {}
    target_reason_counts_total: dict[str, int] = {}
    readiness_blockers_total: dict[str, int] = {}
    telemetry_parse_errors = 0
    runtime_error_lines = 0

    for raw_line in lines:
        line = str(raw_line)
        if _ERROR_RE.search(line):
            runtime_error_lines += 1

        point = parse_entry_stability_telemetry_line(line)
        if point is not None:
            points.append(point)
            _merge_reason_counts(
                target=watchlist_reason_counts_total,
                source=point.watchlist_reason_counts,
            )
            _merge_reason_counts(
                target=watchlist_blocker_reason_counts_total,
                source=point.watchlist_blocker_reason_counts,
            )
            continue

        readiness_counts = parse_tick_density_readiness_telemetry_line(line)
        if readiness_counts is not None:
            _merge_reason_counts(
                target=readiness_blockers_total,
                source=readiness_counts,
            )
            continue

        if _TELEMETRY_PREFIX in line:
            telemetry_parse_errors += 1

    entry_total_sum = sum(point.entry_total for point in points)
    entry_actionable_sum = sum(point.entry_actionable for point in points)
    entry_watchlist_sum = sum(point.entry_watchlist for point in points)
    entry_watchlist_insufficient_history_sum = sum(
        point.entry_watchlist_insufficient_history for point in points
    )
    churn_values = [point.entry_topn_churn for point in points]
    entry_input_total_sum = _sum_optional_int(
        point.entry_input_total for point in points
    )
    entry_lp_eligible_total_sum = _sum_optional_int(
        point.entry_lp_eligible_total for point in points
    )
    entry_lp_ineligible_total_sum = _sum_optional_int(
        point.entry_lp_ineligible_total for point in points
    )
    entry_range_ready_total_sum = _sum_optional_int(
        point.entry_range_ready_total for point in points
    )
    entry_range_missing_total_sum = _sum_optional_int(
        point.entry_range_missing_total for point in points
    )
    entry_target_scope_enabled_cycles = sum(
        1 for point in points if int(point.entry_target_scope_enabled or 0) > 0
    )
    entry_target_input_total_sum = _sum_optional_int(
        point.entry_target_input_total for point in points
    )
    entry_target_matched_total_sum = _sum_optional_int(
        point.entry_target_matched_total for point in points
    )
    entry_target_excluded_total_sum = _sum_optional_int(
        point.entry_target_excluded_total for point in points
    )
    for point in points:
        reason = str(point.entry_target_reason or "").strip().upper()
        if not reason:
            continue
        target_reason_counts_total[reason] = (
            int(target_reason_counts_total.get(reason, 0)) + 1
        )

    return LpEntryShadowCalibrationSnapshot(
        cycles_with_entry_telemetry=len(points),
        entry_total_sum=entry_total_sum,
        actionable_ratio=_safe_ratio(entry_actionable_sum, entry_total_sum),
        watchlist_ratio=_safe_ratio(entry_watchlist_sum, entry_total_sum),
        insufficient_history_ratio=_safe_ratio(
            entry_watchlist_insufficient_history_sum, entry_total_sum
        ),
        topn_churn_avg=_mean(churn_values),
        topn_churn_p95=_p95(churn_values),
        entry_input_total_sum=entry_input_total_sum,
        entry_lp_eligible_total_sum=entry_lp_eligible_total_sum,
        entry_lp_ineligible_total_sum=entry_lp_ineligible_total_sum,
        entry_range_ready_total_sum=entry_range_ready_total_sum,
        entry_range_missing_total_sum=entry_range_missing_total_sum,
        entry_target_scope_enabled_cycles=entry_target_scope_enabled_cycles,
        entry_target_input_total_sum=entry_target_input_total_sum,
        entry_target_matched_total_sum=entry_target_matched_total_sum,
        entry_target_excluded_total_sum=entry_target_excluded_total_sum,
        entry_target_reason_counts=dict(sorted(target_reason_counts_total.items())),
        watchlist_reason_counts=dict(sorted(watchlist_reason_counts_total.items())),
        watchlist_blocker_reason_counts=dict(
            sorted(watchlist_blocker_reason_counts_total.items())
        ),
        tick_density_readiness_blocker_counts=dict(
            sorted(readiness_blockers_total.items())
        ),
        telemetry_parse_errors=telemetry_parse_errors,
        runtime_error_lines=runtime_error_lines,
    )


def evaluate_shadow_calibration_gates(
    snapshot: LpEntryShadowCalibrationSnapshot,
    thresholds: LpEntryShadowCalibrationThresholds,
) -> dict[str, bool]:
    gates = {
        "errors_zero_pass": snapshot.total_errors == 0,
        "telemetry_min_cycles_pass": (
            snapshot.cycles_with_entry_telemetry >= int(thresholds.telemetry_min_cycles)
        ),
        "actionable_ratio_positive_pass": snapshot.actionable_ratio > 0.0,
        "insufficient_history_ratio_pass": (
            snapshot.insufficient_history_ratio
            <= float(thresholds.max_insufficient_history_ratio)
        ),
        "topn_churn_avg_pass": (
            snapshot.topn_churn_avg <= float(thresholds.max_topn_churn_avg)
        ),
        "topn_churn_p95_pass": (
            snapshot.topn_churn_p95 <= float(thresholds.max_topn_churn_p95)
        ),
    }
    gates["all_pass"] = all(gates.values())
    return gates


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return float(numerator) / float(denominator)


def _mean(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return float(sum(values)) / float(len(values))


def _p95(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(float(v) for v in values)
    # Nearest-rank percentile, deterministic for short operational samples.
    rank = int(math.ceil(0.95 * len(sorted_values)))
    index = max(0, min(len(sorted_values) - 1, rank - 1))
    return float(sorted_values[index])


def _validate_unit_interval(name: str, value: float) -> None:
    if value < 0.0 or value > 1.0:
        raise ValueError(f"{name} must be within [0.0, 1.0]")


def _parse_reason_counts_blob(
    raw: object,
    *,
    normalize_readiness: bool = False,
) -> dict[str, int]:
    text = str(raw or "").strip()
    if not text or text.upper() == "NONE":
        return {}
    out: dict[str, int] = {}
    parsed_raw: dict[str, int] = {}
    for token in text.split(","):
        item = token.strip()
        if not item or ":" not in item:
            continue
        reason, count_raw = item.split(":", 1)
        reason_code = str(reason or "").strip().upper()
        if not reason_code:
            continue
        try:
            count = int(count_raw)
        except (TypeError, ValueError):
            continue
        if count <= 0:
            continue
        parsed_raw[reason_code] = int(parsed_raw.get(reason_code, 0)) + count
    if normalize_readiness:
        return normalize_readiness_blocker_counts(parsed_raw)
    out = dict(parsed_raw)
    return dict(sorted(out.items()))


def _merge_reason_counts(*, target: dict[str, int], source: dict[str, int]) -> None:
    for key, value in source.items():
        normalized = str(key or "").strip().upper()
        if not normalized:
            continue
        count = int(value or 0)
        if count <= 0:
            continue
        target[normalized] = int(target.get(normalized, 0)) + count


def _parse_optional_non_negative_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    parsed = int(str(value).strip())
    if parsed < 0:
        raise ValueError("optional telemetry counters must be non-negative")
    return parsed


def _parse_optional_reason_code(value: object) -> str | None:
    text = str(value or "").strip().upper()
    if not text:
        return None
    if re.fullmatch(r"[A-Z0-9_]+", text) is None:
        raise ValueError("entry_target_reason must be machine-readable code")
    return text


def _sum_optional_int(values: Iterable[int | None]) -> int:
    total = 0
    for value in values:
        if value is None:
            continue
        total += int(value)
    return total
