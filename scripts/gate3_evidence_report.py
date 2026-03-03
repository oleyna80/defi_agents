#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

from defi_agents.execution.gate3_evidence import read_baseline_positions_count, summarize_log_lines


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gate-3 evidence snapshot from runtime logs.")
    parser.add_argument("--unit", default="defi-sentinel.service", help="systemd user unit name")
    parser.add_argument("--window", default="48 hours ago", help='journalctl --since window')
    parser.add_argument(
        "--reader-threshold",
        type=int,
        default=90,
        help="minimum reader_ok count in the gate window",
    )
    parser.add_argument(
        "--baseline-file",
        default="docs/memory-bank/position_entry_baselines.json",
        help="path to baseline JSON file",
    )
    parser.add_argument(
        "--from-file",
        default="",
        help="optional plain-text log file instead of journalctl",
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
        message = proc.stderr.strip() or f"journalctl exited with code {proc.returncode}"
        raise RuntimeError(message)
    return proc.stdout.splitlines()


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    load_dotenv(dotenv_path=".env", override=False)
    wallet_set = bool(os.getenv("WALLET_ADDRESS"))
    rpc_set = bool(os.getenv("RPC_URL_ARBITRUM"))
    baseline_positions_count = read_baseline_positions_count(args.baseline_file)

    try:
        lines = _load_lines(unit=args.unit, window=args.window, from_file=args.from_file)
    except (OSError, RuntimeError, UnicodeDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    summary = summarize_log_lines(lines)
    payload = {
        "unit": args.unit,
        "window": args.window,
        "reader_threshold": args.reader_threshold,
        "preflight": {
            "wallet_set": wallet_set,
            "rpc_set": rpc_set,
            "baseline_positions_count": baseline_positions_count,
        },
        "summary": summary.to_dict(),
        "gate_checks": {
            "reader_ok_threshold_pass": summary.reader_ok >= args.reader_threshold,
            "errors_zero_pass": summary.errors == 0,
            "sim_fail_zero_pass": summary.sim_fail == 0,
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
