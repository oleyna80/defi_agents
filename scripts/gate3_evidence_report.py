#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

from defi_agents.execution.gate3_evidence import (
    read_baseline_positions_count,
    summarize_log_lines,
    summarize_position_samples,
)
from defi_agents.tracker import ArbitrumUniswapV3PositionReader


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
    parser.add_argument(
        "--min-positions",
        type=int,
        default=3,
        help="minimum number of valid position samples for Gate-3 position evidence",
    )
    parser.add_argument(
        "--max-position-samples",
        type=int,
        default=20,
        help="maximum number of position samples to include in output",
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


async def _load_position_samples(wallet_address: str, rpc_url: str) -> tuple[list[dict[str, object]], int]:
    reader = ArbitrumUniswapV3PositionReader(rpc_url=rpc_url)
    states = await reader.load_active_position_states(wallet_address)
    return summarize_position_samples(states)


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
    position_samples: list[dict[str, object]] = []
    valid_position_samples = 0
    if wallet_set and rpc_set:
        try:
            samples, valid_count = asyncio.run(
                _load_position_samples(
                    wallet_address=str(os.getenv("WALLET_ADDRESS")),
                    rpc_url=str(os.getenv("RPC_URL_ARBITRUM")),
                )
            )
            position_samples = samples[: max(0, int(args.max_position_samples))]
            valid_position_samples = int(valid_count)
        except Exception as exc:  # noqa: BLE001
            position_samples = [{"error": f"POSITION_SAMPLE_LOAD_ERROR: {exc.__class__.__name__}"}]
            valid_position_samples = 0

    payload = {
        "unit": args.unit,
        "window": args.window,
        "reader_threshold": args.reader_threshold,
        "min_positions": args.min_positions,
        "preflight": {
            "wallet_set": wallet_set,
            "rpc_set": rpc_set,
            "baseline_positions_count": baseline_positions_count,
        },
        "summary": summary.to_dict(),
        "position_samples": position_samples,
        "position_samples_count": len(position_samples),
        "position_samples_valid_count": valid_position_samples,
        "gate_checks": {
            "reader_ok_threshold_pass": summary.reader_ok >= args.reader_threshold,
            "errors_zero_pass": summary.errors == 0,
            "sim_fail_zero_pass": summary.sim_fail == 0,
            "position_samples_min_pass": valid_position_samples >= int(args.min_positions),
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
