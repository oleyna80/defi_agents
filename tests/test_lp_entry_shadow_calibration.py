from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.lp.shadow_calibration import (
    LpEntryShadowCalibrationThresholds,
    evaluate_shadow_calibration_gates,
    parse_entry_stability_telemetry_line,
    parse_tick_density_readiness_telemetry_line,
    summarize_entry_shadow_calibration,
)


def test_parse_entry_stability_telemetry_line_normal() -> None:
    line = (
        "LP entry stability telemetry: entry_total=5 entry_actionable=3 "
        "entry_watchlist=2 entry_watchlist_insufficient_history=1 entry_topn_churn=0.2500 "
        "entry_input_total=7 entry_lp_eligible_total=5 entry_lp_ineligible_total=2 "
        "entry_range_ready_total=4 entry_range_missing_total=1 "
        "entry_target_scope_enabled=1 entry_target_input_total=5 "
        "entry_target_matched_total=3 entry_target_excluded_total=2 "
        "entry_target_reason=NONE "
        "watchlist_reason_counts=INVALID_OR_MISSING_RANGE:1,TICK_DATA_DEGRADED:1 "
        "watchlist_blocker_reason_counts=TICK_PROVIDER_RUNTIME_ERROR:1"
    )
    point = parse_entry_stability_telemetry_line(line)
    assert point is not None
    assert point.entry_total == 5
    assert point.entry_actionable == 3
    assert point.entry_watchlist == 2
    assert point.entry_watchlist_insufficient_history == 1
    assert point.entry_topn_churn == 0.25
    assert point.entry_input_total == 7
    assert point.entry_lp_eligible_total == 5
    assert point.entry_lp_ineligible_total == 2
    assert point.entry_range_ready_total == 4
    assert point.entry_range_missing_total == 1
    assert point.entry_target_scope_enabled == 1
    assert point.entry_target_input_total == 5
    assert point.entry_target_matched_total == 3
    assert point.entry_target_excluded_total == 2
    assert point.entry_target_reason == "NONE"
    assert point.watchlist_reason_counts == {
        "INVALID_OR_MISSING_RANGE": 1,
        "TICK_DATA_DEGRADED": 1,
    }
    assert point.watchlist_blocker_reason_counts == {
        "TICK_PROVIDER_RUNTIME_ERROR": 1,
    }


def test_parse_entry_stability_telemetry_line_malformed_returns_none() -> None:
    line = (
        "LP entry stability telemetry: entry_total=x entry_actionable=3 "
        "entry_watchlist=2 entry_watchlist_insufficient_history=1 entry_topn_churn=0.2500"
    )
    assert parse_entry_stability_telemetry_line(line) is None


def test_parse_tick_density_readiness_telemetry_line_normal() -> None:
    line = (
        "Tick density readiness telemetry: "
        "blocker_counts=GRAPH_API_KEY_MISSING:5,PROVIDER_INIT_SUBGRAPH_ERROR:2"
    )
    parsed = parse_tick_density_readiness_telemetry_line(line)
    assert parsed == {
        "GRAPH_API_KEY_MISSING": 5,
        "TICK_PROVIDER_INIT_ERROR": 2,
    }


def test_summarize_entry_shadow_calibration_normal_and_malformed() -> None:
    lines = [
        (
            "2026-03-03 INFO LP entry stability telemetry: entry_total=5 entry_actionable=3 "
            "entry_watchlist=2 entry_watchlist_insufficient_history=1 entry_topn_churn=0.1000 "
            "entry_input_total=7 entry_lp_eligible_total=5 entry_lp_ineligible_total=2 "
            "entry_range_ready_total=4 entry_range_missing_total=1 "
            "entry_target_scope_enabled=1 entry_target_input_total=5 "
            "entry_target_matched_total=4 entry_target_excluded_total=1 "
            "entry_target_reason=NONE "
            "watchlist_reason_counts=INVALID_OR_MISSING_RANGE:2 "
            "watchlist_blocker_reason_counts=PROVIDER_UNAVAILABLE_SUBGRAPH_TIMEOUT:1"
        ),
        (
            "2026-03-03 INFO LP entry stability telemetry: entry_total=4 entry_actionable=2 "
            "entry_watchlist=2 entry_watchlist_insufficient_history=0 entry_topn_churn=0.4000 "
            "entry_input_total=6 entry_lp_eligible_total=4 entry_lp_ineligible_total=2 "
            "entry_range_ready_total=3 entry_range_missing_total=1 "
            "entry_target_scope_enabled=1 entry_target_input_total=4 "
            "entry_target_matched_total=2 entry_target_excluded_total=2 "
            "entry_target_reason=TARGET_SCOPE_EMPTY "
            "watchlist_reason_counts=TICK_DATA_DEGRADED:1,INVALID_OR_MISSING_RANGE:1 "
            "watchlist_blocker_reason_counts=RPC_UNAVAILABLE:1,TICK_PROVIDER_RUNTIME_ERROR:1"
        ),
        (
            "2026-03-03 INFO LP entry stability telemetry: entry_total=6 entry_actionable=3 "
            "entry_watchlist=3 entry_watchlist_insufficient_history=2 entry_topn_churn=0.7000 "
            "entry_input_total=8 entry_lp_eligible_total=6 entry_lp_ineligible_total=2 "
            "entry_range_ready_total=4 entry_range_missing_total=2 "
            "entry_target_scope_enabled=0 entry_target_input_total=6 "
            "entry_target_matched_total=6 entry_target_excluded_total=0 "
            "entry_target_reason=NONE"
        ),
        (
            "2026-03-03 INFO Tick density readiness telemetry: "
            "blocker_counts=GRAPH_API_KEY_MISSING:6,PROVIDER_INIT_VALUEERROR:1"
        ),
        "Traceback (most recent call last):",
        (
            "2026-03-03 INFO LP entry stability telemetry: entry_total=bad entry_actionable=1 "
            "entry_watchlist=0 entry_watchlist_insufficient_history=0 entry_topn_churn=0.3000"
        ),
    ]
    snapshot = summarize_entry_shadow_calibration(lines)
    assert snapshot.cycles_with_entry_telemetry == 3
    assert snapshot.entry_total_sum == 15
    assert snapshot.actionable_ratio == 8 / 15
    assert snapshot.watchlist_ratio == 7 / 15
    assert snapshot.insufficient_history_ratio == 3 / 15
    assert snapshot.topn_churn_avg == (0.1 + 0.4 + 0.7) / 3
    assert snapshot.topn_churn_p95 == 0.7
    assert snapshot.entry_input_total_sum == 21
    assert snapshot.entry_lp_eligible_total_sum == 15
    assert snapshot.entry_lp_ineligible_total_sum == 6
    assert snapshot.entry_range_ready_total_sum == 11
    assert snapshot.entry_range_missing_total_sum == 4
    assert snapshot.entry_target_scope_enabled_cycles == 2
    assert snapshot.entry_target_input_total_sum == 15
    assert snapshot.entry_target_matched_total_sum == 12
    assert snapshot.entry_target_excluded_total_sum == 3
    assert (
        snapshot.entry_target_input_total_sum
        == snapshot.entry_target_matched_total_sum
        + snapshot.entry_target_excluded_total_sum
    )
    assert snapshot.entry_target_reason_counts == {
        "NONE": 2,
        "TARGET_SCOPE_EMPTY": 1,
    }
    assert snapshot.watchlist_reason_counts == {
        "INVALID_OR_MISSING_RANGE": 3,
        "TICK_DATA_DEGRADED": 1,
    }
    assert snapshot.watchlist_blocker_reason_counts == {
        "RPC_TICK_UNAVAILABLE": 1,
        "TICK_PROVIDER_RUNTIME_ERROR": 2,
    }
    assert snapshot.tick_density_readiness_blocker_counts == {
        "GRAPH_API_KEY_MISSING": 6,
        "TICK_PROVIDER_INIT_ERROR": 1,
    }
    assert snapshot.telemetry_parse_errors == 1
    assert snapshot.runtime_error_lines == 1
    assert snapshot.total_errors == 2


def test_summarize_entry_shadow_calibration_no_data() -> None:
    snapshot = summarize_entry_shadow_calibration(
        [
            "2026-03-03 INFO noop",
            "2026-03-03 INFO another line",
        ]
    )
    assert snapshot.cycles_with_entry_telemetry == 0
    assert snapshot.entry_total_sum == 0
    assert snapshot.actionable_ratio == 0.0
    assert snapshot.watchlist_ratio == 0.0
    assert snapshot.insufficient_history_ratio == 0.0
    assert snapshot.topn_churn_avg == 0.0
    assert snapshot.topn_churn_p95 == 0.0
    assert snapshot.entry_input_total_sum == 0
    assert snapshot.entry_lp_eligible_total_sum == 0
    assert snapshot.entry_lp_ineligible_total_sum == 0
    assert snapshot.entry_range_ready_total_sum == 0
    assert snapshot.entry_range_missing_total_sum == 0
    assert snapshot.entry_target_scope_enabled_cycles == 0
    assert snapshot.entry_target_input_total_sum == 0
    assert snapshot.entry_target_matched_total_sum == 0
    assert snapshot.entry_target_excluded_total_sum == 0
    assert (
        snapshot.entry_target_input_total_sum
        == snapshot.entry_target_matched_total_sum
        + snapshot.entry_target_excluded_total_sum
    )
    assert snapshot.entry_target_reason_counts == {}
    assert snapshot.watchlist_reason_counts == {}
    assert snapshot.watchlist_blocker_reason_counts == {}
    assert snapshot.tick_density_readiness_blocker_counts == {}
    assert snapshot.telemetry_parse_errors == 0
    assert snapshot.runtime_error_lines == 0


def test_evaluate_shadow_calibration_gates_threshold_boundary_pass() -> None:
    snapshot = summarize_entry_shadow_calibration(
        [
            (
                "LP entry stability telemetry: entry_total=10 entry_actionable=8 "
                "entry_watchlist=2 entry_watchlist_insufficient_history=3 entry_topn_churn=0.2000"
            ),
            (
                "LP entry stability telemetry: entry_total=10 entry_actionable=8 "
                "entry_watchlist=2 entry_watchlist_insufficient_history=3 entry_topn_churn=0.6000"
            ),
        ]
    )
    thresholds = LpEntryShadowCalibrationThresholds(
        telemetry_min_cycles=2,
        max_insufficient_history_ratio=0.3,
        max_topn_churn_avg=0.4,
        max_topn_churn_p95=0.6,
    )
    gates = evaluate_shadow_calibration_gates(snapshot, thresholds)

    assert snapshot.insufficient_history_ratio == 0.3
    assert snapshot.topn_churn_avg == 0.4
    assert snapshot.topn_churn_p95 == 0.6
    assert gates["errors_zero_pass"] is True
    assert gates["telemetry_min_cycles_pass"] is True
    assert gates["actionable_ratio_positive_pass"] is True
    assert gates["insufficient_history_ratio_pass"] is True
    assert gates["topn_churn_avg_pass"] is True
    assert gates["topn_churn_p95_pass"] is True
    assert gates["all_pass"] is True


def test_evaluate_shadow_calibration_gates_fail_with_errors_and_low_cycles() -> None:
    snapshot = summarize_entry_shadow_calibration(
        [
            "Traceback (most recent call last):",
            (
                "LP entry stability telemetry: entry_total=4 entry_actionable=1 "
                "entry_watchlist=3 entry_watchlist_insufficient_history=2 entry_topn_churn=0.9000"
            ),
        ]
    )
    thresholds = LpEntryShadowCalibrationThresholds(
        telemetry_min_cycles=2,
        max_insufficient_history_ratio=0.4,
        max_topn_churn_avg=0.8,
        max_topn_churn_p95=0.8,
    )
    gates = evaluate_shadow_calibration_gates(snapshot, thresholds)

    assert gates["errors_zero_pass"] is False
    assert gates["telemetry_min_cycles_pass"] is False
    assert gates["actionable_ratio_positive_pass"] is True
    assert gates["insufficient_history_ratio_pass"] is False
    assert gates["topn_churn_avg_pass"] is False
    assert gates["topn_churn_p95_pass"] is False
    assert gates["all_pass"] is False


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"telemetry_min_cycles": 0}, "telemetry_min_cycles must be >= 1"),
        (
            {"max_insufficient_history_ratio": -0.01},
            "max_insufficient_history_ratio must be within [0.0, 1.0]",
        ),
        (
            {"max_topn_churn_avg": 1.01},
            "max_topn_churn_avg must be within [0.0, 1.0]",
        ),
        (
            {"max_topn_churn_p95": 1.01},
            "max_topn_churn_p95 must be within [0.0, 1.0]",
        ),
        (
            {"max_topn_churn_avg": 0.8, "max_topn_churn_p95": 0.7},
            "max_topn_churn_avg must be <= max_topn_churn_p95",
        ),
    ],
)
def test_thresholds_reject_invalid_values(
    kwargs: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=re.escape(message)):
        LpEntryShadowCalibrationThresholds(**cast(dict[str, Any], kwargs))


def test_evaluate_shadow_calibration_gates_fails_when_actionable_ratio_zero() -> None:
    snapshot = summarize_entry_shadow_calibration(
        [
            (
                "LP entry stability telemetry: entry_total=10 entry_actionable=0 "
                "entry_watchlist=10 entry_watchlist_insufficient_history=0 entry_topn_churn=0.1000 "
                "watchlist_reason_counts=INVALID_OR_MISSING_RANGE:10"
            )
        ]
    )
    thresholds = LpEntryShadowCalibrationThresholds(telemetry_min_cycles=1)
    gates = evaluate_shadow_calibration_gates(snapshot, thresholds)

    assert snapshot.actionable_ratio == 0.0
    assert gates["telemetry_min_cycles_pass"] is True
    assert gates["actionable_ratio_positive_pass"] is False
    assert gates["all_pass"] is False


def test_parse_tick_density_readiness_telemetry_line_rpc_unavailable_normalized() -> None:
    line = (
        "Tick density readiness telemetry: "
        "blocker_counts=RPC_UNAVAILABLE:2,PROVIDER_UNAVAILABLE_SUBGRAPH_TIMEOUT:1"
    )
    parsed = parse_tick_density_readiness_telemetry_line(line)
    assert parsed == {
        "RPC_TICK_UNAVAILABLE": 2,
        "TICK_PROVIDER_RUNTIME_ERROR": 1,
    }
