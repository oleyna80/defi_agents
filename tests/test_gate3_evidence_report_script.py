from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "gate3_evidence_report.py"


def _run_report(
    *,
    tmp_path: Path,
    positions_payload: object,
    log_lines: list[str],
    manual_payload: object | None = None,
    extra_args: list[str] | None = None,
) -> dict[str, object]:
    positions_path = tmp_path / "positions.json"
    positions_path.write_text(json.dumps(positions_payload), encoding="utf-8")

    log_path = tmp_path / "shadow.log"
    log_path.write_text("\n".join(log_lines), encoding="utf-8")

    command = [
        sys.executable,
        str(SCRIPT),
        "--from-file",
        str(log_path),
        "--positions-file",
        str(positions_path),
        "--reader-threshold",
        "2",
        "--min-positions",
        "3",
        "--pnl-deviation-threshold-pct",
        "1.0",
    ]

    if manual_payload is not None:
        manual_path = tmp_path / "manual.json"
        manual_path.write_text(json.dumps(manual_payload), encoding="utf-8")
        command.extend(["--manual-check-file", str(manual_path)])

    if extra_args:
        command.extend(extra_args)

    env = dict(os.environ)
    env.setdefault("PYTHONPATH", "src")
    proc = subprocess.run(
        command,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_gate3_contract_v1_pass_with_zero_small_and_negative_values(tmp_path: Path) -> None:
    payload = _run_report(
        tmp_path=tmp_path,
        positions_payload={
            "positions": [
                {
                    "position_id": "uni-v3:1",
                    "position_pnl_usd": -10.0,
                    "hodl_pnl_usd": -8.0,
                    "pnl_vs_hodl_usd": -2.0,
                },
                {
                    "position_id": "uni-v3:2",
                    "position_pnl_usd": 0.0,
                    "hodl_pnl_usd": 0.0,
                    "pnl_vs_hodl_usd": 0.0,
                },
                {
                    "position_id": "uni-v3:3",
                    "position_pnl_usd": 2e-10,
                    "hodl_pnl_usd": 1e-10,
                    "pnl_vs_hodl_usd": 1e-10,
                },
            ]
        },
        manual_payload={
            "manual_checks": [
                {"position_id": "uni-v3:1", "ui_pnl_vs_hodl_usd": -2.0},
                {"position_id": "uni-v3:2", "ui_pnl_vs_hodl_usd": 0.0},
                {"position_id": "uni-v3:3", "ui_pnl_vs_hodl_usd": 0.0},
            ]
        },
        log_lines=[
            "Execution states loaded: source=position_reader chain=Arbitrum active_states=2",
            "Execution states loaded: source=position_reader chain=Arbitrum active_states=2",
            "Execution summary: mode=SHADOW states=2 tx_plans=1 intents=1 blocked_by_policy=0 sim_ok=1 sim_fail=0 exec_ok=0 exec_fail=0 policy_blocks={} sim_fail_reasons={} exec_fail_reasons={}",
        ],
        extra_args=["--near-zero-epsilon", "1e-6"],
    )

    assert payload["positions_total"] == 3
    assert payload["positions_validated_count"] == 3
    assert payload["reader_ok_count"] == 2
    assert payload["pnl_hodl_under_1pct_pass"] is True
    assert payload["min_positions_pass"] is True
    assert payload["reader_ok_threshold_pass"] is True
    assert payload["errors_zero_pass"] is True
    assert payload["all_pass"] is True
    assert payload["pnl_hodl_deviation_max_pct"] <= 1.0
    assert payload["pnl_hodl_deviation_p95_pct"] <= 1.0
    assert payload["evidence_gaps"] == []


def test_gate3_contract_v1_fail_safe_on_malformed_records_and_errors(tmp_path: Path) -> None:
    payload = _run_report(
        tmp_path=tmp_path,
        positions_payload={
            "positions": [
                {
                    "position_id": "uni-v3:ok",
                    "position_pnl_usd": 10.0,
                    "hodl_pnl_usd": 9.0,
                    "pnl_vs_hodl_usd": 1.0,
                },
                {
                    "position_id": "uni-v3:bad",
                    "position_pnl_usd": True,
                    "hodl_pnl_usd": "not-a-number",
                    "pnl_vs_hodl_usd": "abc",
                },
            ]
        },
        log_lines=[
            "Execution states loaded: source=position_reader chain=Arbitrum active_states=1",
            "Execution states loaded: source=position_reader chain=Arbitrum active_states=1",
            "CRITICAL runtime panic example",
        ],
    )

    assert payload["positions_total"] == 2
    assert payload["positions_validated_count"] == 1
    assert payload["errors_zero_pass"] is False
    assert payload["all_pass"] is False
    assert payload["verdict"] == "FAIL"
    reasons = payload["reasons"]
    assert any(str(item).startswith("MALFORMED_POSITION_RECORD:uni-v3:bad") for item in reasons)
    assert "SHADOW_ERRORS_NOT_ZERO_OR_LOG_UNAVAILABLE" in reasons
    gaps = payload["evidence_gaps"]
    assert "VALIDATED_POSITIONS_BELOW_MIN_THRESHOLD" in gaps
    assert "SHADOW_ERRORS_NON_ZERO_OR_LOG_UNAVAILABLE" in gaps


def test_gate3_contract_v1_is_deterministic_for_same_input(tmp_path: Path) -> None:
    kwargs = {
        "tmp_path": tmp_path,
        "positions_payload": {
            "positions": [
                {
                    "position_id": "uni-v3:1",
                    "position_pnl_usd": -5.0,
                    "hodl_pnl_usd": -4.5,
                    "pnl_vs_hodl_usd": -0.5,
                },
                {
                    "position_id": "uni-v3:2",
                    "position_pnl_usd": 2.0,
                    "hodl_pnl_usd": 1.5,
                    "pnl_vs_hodl_usd": 0.5,
                },
                {
                    "position_id": "uni-v3:3",
                    "position_pnl_usd": 0.0,
                    "hodl_pnl_usd": 0.0,
                    "pnl_vs_hodl_usd": 0.0,
                },
            ]
        },
        "log_lines": [
            "Execution states loaded: source=position_reader chain=Arbitrum active_states=3",
            "Execution states loaded: source=position_reader chain=Arbitrum active_states=3",
        ],
        "extra_args": ["--near-zero-epsilon", "1e-6"],
    }
    first = _run_report(**kwargs)
    second = _run_report(**kwargs)
    assert first == second


def test_gate3_contract_v1_fail_safe_when_inputs_missing(tmp_path: Path) -> None:
    missing_log = tmp_path / "missing.log"
    missing_positions = tmp_path / "missing_positions.json"

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--from-file",
            str(missing_log),
            "--positions-file",
            str(missing_positions),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": "src"},
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["all_pass"] is False
    assert payload["verdict"] == "FAIL"
    assert "SHADOW_LOG" in payload["missing_artifacts"]
    assert "POSITIONS_SNAPSHOT" in payload["missing_artifacts"]
    assert "VALIDATED_POSITIONS_BELOW_MIN_THRESHOLD" in payload["evidence_gaps"]


def test_gate3_contract_v1_prefers_positions_file_when_empty_and_no_reader_fallback(
    tmp_path: Path,
) -> None:
    positions_path = tmp_path / "positions.json"
    positions_path.write_text(json.dumps({"positions": []}), encoding="utf-8")

    log_path = tmp_path / "shadow.log"
    log_path.write_text(
        "\n".join(
            [
                "Execution states loaded: source=position_reader chain=Arbitrum active_states=1",
                "Execution states loaded: source=position_reader chain=Arbitrum active_states=1",
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
            "--positions-file",
            str(positions_path),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "PYTHONPATH": "src",
            "WALLET_ADDRESS": "0x0000000000000000000000000000000000000001",
            "RPC_URL_ARBITRUM": "http://127.0.0.1:8545",
        },
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["positions_total"] == 0
    assert "POSITIONS_FILE_EMPTY" in payload["reasons"]
    assert "POSITION_SAMPLE_LOAD_ERROR" not in " ".join(str(x) for x in payload["reasons"])


def test_gate3_contract_v1_supports_multiple_from_file_inputs(tmp_path: Path) -> None:
    positions_path = tmp_path / "positions.json"
    positions_path.write_text(
        json.dumps(
            {
                "positions": [
                    {
                        "position_id": "uni-v3:1",
                        "position_pnl_usd": 11.0,
                        "hodl_pnl_usd": 10.0,
                        "pnl_vs_hodl_usd": 1.0,
                    },
                    {
                        "position_id": "uni-v3:2",
                        "position_pnl_usd": 20.0,
                        "hodl_pnl_usd": 19.0,
                        "pnl_vs_hodl_usd": 1.0,
                    },
                    {
                        "position_id": "uni-v3:3",
                        "position_pnl_usd": 30.0,
                        "hodl_pnl_usd": 29.0,
                        "pnl_vs_hodl_usd": 1.0,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    log_a = tmp_path / "shadow_a.log"
    log_a.write_text(
        "\n".join(
            [
                "Execution states loaded: source=position_reader chain=Arbitrum active_states=1",
                "Execution states loaded: source=position_reader chain=Arbitrum active_states=1",
            ]
        ),
        encoding="utf-8",
    )
    log_b = tmp_path / "shadow_b.log"
    log_b.write_text(
        "\n".join(
            [
                "Execution states loaded: source=position_reader chain=Arbitrum active_states=1",
                "Execution summary: mode=SHADOW states=1 tx_plans=0 intents=0 blocked_by_policy=0 sim_ok=0 sim_fail=0 exec_ok=0 exec_fail=0 policy_blocks={} sim_fail_reasons={} exec_fail_reasons={}",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--from-file",
            str(log_a),
            "--from-file",
            str(log_b),
            "--positions-file",
            str(positions_path),
            "--reader-threshold",
            "3",
            "--min-positions",
            "3",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": "src"},
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["reader_ok_count"] == 3
    assert payload["reader_ok_threshold_pass"] is True
    assert payload["positions_validated_count"] == 3
    assert payload["errors_zero_pass"] is True
    assert payload["all_pass"] is True
    assert payload["verdict"] == "PASS"
    preflight = payload["preflight"]
    assert preflight["from_files"] == [str(log_a), str(log_b)]
