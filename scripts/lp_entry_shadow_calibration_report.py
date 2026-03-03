#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from defi_agents.lp.shadow_calibration import (
    LpEntryShadowCalibrationThresholds,
    evaluate_shadow_calibration_gates,
    summarize_entry_shadow_calibration,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build LP Entry SHADOW calibration snapshot from telemetry logs."
    )
    parser.add_argument(
        "--unit",
        default="defi-sentinel.service",
        help="systemd user unit to read via journalctl when --from-file is not set",
    )
    parser.add_argument(
        "--window",
        default="48 hours ago",
        help="journalctl --since window used when --from-file is not set",
    )
    parser.add_argument(
        "--from-file",
        default="",
        help="optional plain-text log file path; bypasses journalctl when provided",
    )
    parser.add_argument(
        "--telemetry-min-cycles",
        type=int,
        default=LpEntryShadowCalibrationThresholds.telemetry_min_cycles,
        help="minimum number of telemetry cycles required for gate pass",
    )
    parser.add_argument(
        "--max-insufficient-history-ratio",
        type=float,
        default=LpEntryShadowCalibrationThresholds.max_insufficient_history_ratio,
        help="maximum allowed insufficient_history_ratio",
    )
    parser.add_argument(
        "--max-topn-churn-avg",
        type=float,
        default=LpEntryShadowCalibrationThresholds.max_topn_churn_avg,
        help="maximum allowed topn_churn_avg",
    )
    parser.add_argument(
        "--max-topn-churn-p95",
        type=float,
        default=LpEntryShadowCalibrationThresholds.max_topn_churn_p95,
        help="maximum allowed topn_churn_p95",
    )
    return parser


def _load_lines(unit: str, window: str, from_file: str) -> list[str]:
    if from_file:
        return Path(from_file).read_text(encoding="utf-8").splitlines()

    proc = subprocess.run(
        ["journalctl", "--user", "-u", unit, "--since", window, "--no-pager"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        message = (
            proc.stderr.strip() or f"journalctl exited with code {proc.returncode}"
        )
        raise RuntimeError(message)
    return proc.stdout.splitlines()


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    try:
        lines = _load_lines(
            unit=args.unit, window=args.window, from_file=args.from_file
        )
    except (OSError, RuntimeError, UnicodeDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    snapshot = summarize_entry_shadow_calibration(lines)
    try:
        thresholds = LpEntryShadowCalibrationThresholds(
            telemetry_min_cycles=int(args.telemetry_min_cycles),
            max_insufficient_history_ratio=float(args.max_insufficient_history_ratio),
            max_topn_churn_avg=float(args.max_topn_churn_avg),
            max_topn_churn_p95=float(args.max_topn_churn_p95),
        )
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    payload = {
        "source": {
            "unit": args.unit,
            "window": args.window,
            "from_file": args.from_file or None,
        },
        "thresholds": thresholds.to_dict(),
        "snapshot": snapshot.to_dict(),
        "gate_checks": evaluate_shadow_calibration_gates(snapshot, thresholds),
    }
    gate_checks = payload["gate_checks"]
    snapshot_dict = payload["snapshot"]
    actionable_ratio = float(snapshot_dict.get("actionable_ratio", 0.0) or 0.0)
    if not bool(gate_checks.get("actionable_ratio_positive_pass", False)):
        reason_counts = dict(snapshot_dict.get("watchlist_reason_counts", {}) or {})
        top3 = sorted(
            ((str(k), int(v)) for k, v in reason_counts.items()),
            key=lambda item: (-item[1], item[0]),
        )[:3]
        payload["actionable_enablement"] = {
            "actionable_ratio": actionable_ratio,
            "actionable_ratio_positive_pass": False,
            "top_watchlist_reasons": [
                {"reason": reason, "count": count} for reason, count in top3
            ],
        }
    else:
        payload["actionable_enablement"] = {
            "actionable_ratio": actionable_ratio,
            "actionable_ratio_positive_pass": True,
            "top_watchlist_reasons": [],
        }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
