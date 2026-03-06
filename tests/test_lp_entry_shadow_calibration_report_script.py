from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "lp_entry_shadow_calibration_report.py"


def test_report_script_emits_top_blockers_when_all_pass_false(tmp_path: Path) -> None:
    log_path = tmp_path / "shadow.log"
    log_path.write_text(
        "\n".join(
            [
                (
                    "LP entry stability telemetry: entry_total=10 entry_actionable=0 "
                    "entry_watchlist=10 entry_watchlist_insufficient_history=0 entry_topn_churn=0.1000 "
                    "watchlist_reason_counts=TICK_DATA_DEGRADED:7,INVALID_OR_MISSING_RANGE:3 "
                    "watchlist_blocker_reason_counts=TICK_PROVIDER_RUNTIME_ERROR:6,RPC_TICK_UNAVAILABLE:1"
                ),
                (
                    "Tick density readiness telemetry: "
                    "blocker_counts=PROVIDER_UNAVAILABLE_SUBGRAPH_TIMEOUT:5,GRAPH_API_KEY_MISSING:2"
                ),
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--from-file",
            str(log_path),
            "--telemetry-min-cycles",
            "1",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)

    assert payload["gate_checks"]["all_pass"] is False
    fail_ctx = payload["calibration_fail_context"]
    assert fail_ctx["top_watchlist_reasons"][0] == {
        "reason": "TICK_DATA_DEGRADED",
        "count": 7,
    }
    assert fail_ctx["top_watchlist_blocker_reasons"][0] == {
        "reason": "TICK_PROVIDER_RUNTIME_ERROR",
        "count": 6,
    }
    assert fail_ctx["top_tick_density_readiness_blockers"][0] == {
        "reason": "TICK_PROVIDER_RUNTIME_ERROR",
        "count": 5,
    }
