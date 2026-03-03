from __future__ import annotations

import json

from defi_agents.execution.gate3_evidence import (
    parse_execution_summary_line,
    read_baseline_positions_count,
    summarize_log_lines,
)


def test_parse_execution_summary_line_parses_expected_fields() -> None:
    line = (
        "Execution summary: mode=SHADOW states=2 tx_plans=1 intents=1 blocked_by_policy=3 "
        "sim_ok=4 sim_fail=5 exec_ok=6 exec_fail=7 policy_blocks={} sim_fail_reasons={} exec_fail_reasons={}"
    )
    parsed = parse_execution_summary_line(line)
    assert parsed == {
        "blocked_by_policy": 3,
        "sim_ok": 4,
        "sim_fail": 5,
        "exec_ok": 6,
        "exec_fail": 7,
    }


def test_parse_execution_summary_line_returns_none_for_unrelated_line() -> None:
    assert parse_execution_summary_line("Execution loop disabled.") is None


def test_summarize_log_lines_aggregates_gate3_metrics() -> None:
    lines = [
        "Execution states loaded: source=position_reader chain=Arbitrum active_states=2",
        (
            "Execution summary: mode=SHADOW states=2 tx_plans=1 intents=1 blocked_by_policy=1 "
            "sim_ok=2 sim_fail=0 exec_ok=0 exec_fail=0 policy_blocks={} sim_fail_reasons={} exec_fail_reasons={}"
        ),
        "Some neutral line",
        "CRITICAL runtime panic example",
        "Execution states loaded: source=position_reader chain=Arbitrum active_states=1",
        (
            "Execution summary: mode=SHADOW states=1 tx_plans=1 intents=1 blocked_by_policy=0 "
            "sim_ok=1 sim_fail=1 exec_ok=0 exec_fail=0 policy_blocks={} sim_fail_reasons={} exec_fail_reasons={}"
        ),
    ]
    summary = summarize_log_lines(lines)
    assert summary.execution_cycles == 2
    assert summary.reader_ok == 2
    assert summary.errors == 1
    assert summary.blocked_by_policy == 1
    assert summary.sim_ok == 3
    assert summary.sim_fail == 1
    assert summary.exec_ok == 0
    assert summary.exec_fail == 0


def test_read_baseline_positions_count_handles_shapes(tmp_path) -> None:
    path = tmp_path / "baseline.json"

    path.write_text(json.dumps({"positions": {"uni-v3:1": {}, "uni-v3:2": {}}}), encoding="utf-8")
    assert read_baseline_positions_count(path) == 2

    path.write_text(json.dumps({"positions": []}), encoding="utf-8")
    assert read_baseline_positions_count(path) == 0

    path.write_text("{bad json", encoding="utf-8")
    assert read_baseline_positions_count(path) == 0
