#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from defi_agents.execution.gate3_evidence import (
    Gate3LogSummary,
    read_baseline_positions_count,
    summarize_log_lines,
    summarize_position_samples,
)
from defi_agents.tracker import ArbitrumUniswapV3PositionReader


_DEFAULT_PNL_DEVIATION_THRESHOLD_PCT = 1.0
_DEFAULT_NEAR_ZERO_EPSILON = 1e-9


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Gate-3 evidence contract v1 snapshot with deterministic PASS/FAIL "
            "for SHADOW logs and PnL/HODL deviation math."
        )
    )
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
        action="append",
        default=[],
        help=(
            "optional plain-text log file instead of journalctl; "
            "can be provided multiple times and will be concatenated in provided order"
        ),
    )
    parser.add_argument(
        "--positions-file",
        default="",
        help=(
            "optional positions snapshot JSON/CSV file; when set, this input is preferred "
            "over live reader fetch"
        ),
    )
    parser.add_argument(
        "--manual-check-file",
        default="",
        help=(
            "optional JSON/CSV manual-check file with UI reference PnL/HODL values "
            "(position_id + ui_pnl_vs_hodl_usd)"
        ),
    )
    parser.add_argument(
        "--min-positions",
        type=int,
        default=3,
        help="minimum number of validated positions for Gate-3 evidence",
    )
    parser.add_argument(
        "--max-position-samples",
        type=int,
        default=20,
        help="maximum number of position samples to include in output",
    )
    parser.add_argument(
        "--pnl-deviation-threshold-pct",
        type=float,
        default=_DEFAULT_PNL_DEVIATION_THRESHOLD_PCT,
        help="maximum allowed PnL/HODL deviation percentage",
    )
    parser.add_argument(
        "--near-zero-epsilon",
        type=float,
        default=_DEFAULT_NEAR_ZERO_EPSILON,
        help=(
            "epsilon guardrail for near-zero denominator in deviation math; "
            "must be > 0"
        ),
    )
    return parser


def _load_lines(unit: str, window: str, from_file: list[str]) -> list[str]:
    if from_file:
        merged_lines: list[str] = []
        for file_path in from_file:
            merged_lines.extend(Path(file_path).read_text(encoding="utf-8").splitlines())
        return merged_lines

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


def _to_finite_float(value: Any, *, allow_bool: bool = False) -> tuple[float | None, str | None]:
    if value is None:
        return None, "VALUE_MISSING"
    if isinstance(value, bool) and not allow_bool:
        return None, "VALUE_BOOL_NOT_ALLOWED"
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None, "VALUE_NOT_NUMERIC"
    if not math.isfinite(parsed):
        return None, "VALUE_NOT_FINITE"
    return parsed, None


def _first_present(raw: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in raw:
            return raw[key]
    return None


def _extract_position_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    for key in ("positions", "position_samples", "records", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if key == "positions" and isinstance(value, dict):
            records: list[dict[str, Any]] = []
            for position_id, row in sorted(value.items(), key=lambda item: str(item[0])):
                if not isinstance(row, dict):
                    continue
                item = dict(row)
                item.setdefault("position_id", str(position_id))
                records.append(item)
            return records
    return []


def _load_positions_from_file(path: str) -> tuple[list[dict[str, Any]], list[str]]:
    reasons: list[str] = []
    file_path = Path(path)
    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        return [], [f"POSITIONS_FILE_READ_ERROR:{exc.__class__.__name__}"]

    if file_path.suffix.lower() == ".csv":
        try:
            reader = csv.DictReader(content.splitlines())
            rows = [dict(row) for row in reader]
        except (csv.Error, ValueError) as exc:
            return [], [f"POSITIONS_FILE_CSV_PARSE_ERROR:{exc.__class__.__name__}"]
        if not rows:
            return [], ["POSITIONS_FILE_EMPTY"]
        return rows, reasons

    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return [], ["POSITIONS_FILE_JSON_PARSE_ERROR"]

    records = _extract_position_records(payload)
    if not records:
        return [], ["POSITIONS_FILE_EMPTY"]
    return records, reasons


def _extract_manual_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    for key in ("manual_checks", "records", "positions", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if key == "positions" and isinstance(value, dict):
            rows: list[dict[str, Any]] = []
            for position_id, row in sorted(value.items(), key=lambda item: str(item[0])):
                if not isinstance(row, dict):
                    continue
                record = dict(row)
                record.setdefault("position_id", str(position_id))
                rows.append(record)
            return rows
    return []


def _build_manual_check_map(rows: list[dict[str, Any]]) -> tuple[dict[str, float], list[str]]:
    reasons: list[str] = []
    mapping: dict[str, float] = {}

    for index, row in enumerate(rows, start=1):
        position_id = str(
            _first_present(row, ("position_id", "position_ref", "id", "token_id")) or ""
        ).strip()
        if not position_id:
            reasons.append(f"MANUAL_CHECK_ROW_MISSING_POSITION_ID:{index}")
            continue

        reference_raw = _first_present(
            row,
            (
                "ui_pnl_vs_hodl_usd",
                "pnl_vs_hodl_usd",
                "reference_pnl_vs_hodl_usd",
                "manual_pnl_vs_hodl_usd",
            ),
        )
        reference, parse_reason = _to_finite_float(reference_raw)
        if reference is None:
            reasons.append(f"MANUAL_CHECK_ROW_INVALID_REFERENCE:{position_id}:{parse_reason}")
            continue
        mapping[position_id] = reference

    return mapping, reasons


def _load_manual_check_map(path: str) -> tuple[dict[str, float], list[str]]:
    if not path:
        return {}, []

    file_path = Path(path)
    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        return {}, [f"MANUAL_CHECK_FILE_READ_ERROR:{exc.__class__.__name__}"]

    if file_path.suffix.lower() == ".csv":
        try:
            reader = csv.DictReader(content.splitlines())
            rows = [dict(row) for row in reader]
        except (csv.Error, ValueError) as exc:
            return {}, [f"MANUAL_CHECK_FILE_CSV_PARSE_ERROR:{exc.__class__.__name__}"]
        if not rows:
            return {}, ["MANUAL_CHECK_FILE_EMPTY"]
        return _build_manual_check_map(rows)

    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return {}, ["MANUAL_CHECK_FILE_JSON_PARSE_ERROR"]

    rows = _extract_manual_rows(payload)
    if not rows:
        return {}, ["MANUAL_CHECK_FILE_EMPTY"]
    return _build_manual_check_map(rows)


def _compute_deviation_pct(
    *,
    actual: float,
    reference: float,
    near_zero_epsilon: float,
) -> tuple[float | None, str | None]:
    if not (math.isfinite(actual) and math.isfinite(reference)):
        return None, "DEVIATION_INPUT_NOT_FINITE"

    denominator = abs(reference)
    abs_diff = abs(actual - reference)
    if denominator < near_zero_epsilon:
        if abs_diff <= near_zero_epsilon:
            return 0.0, "NEAR_ZERO_DENOMINATOR"
        return (abs_diff / near_zero_epsilon) * 100.0, "NEAR_ZERO_DENOMINATOR"
    return (abs_diff / denominator) * 100.0, None


def _percentile_nearest_rank(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    if percentile <= 0:
        return min(values)
    if percentile >= 1:
        return max(values)
    ordered = sorted(values)
    rank_index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[rank_index]


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _evaluate_positions(
    *,
    raw_positions: list[dict[str, Any]],
    manual_check_map: dict[str, float],
    near_zero_epsilon: float,
) -> dict[str, Any]:
    normalized_rows: list[dict[str, Any]] = []
    reasons: list[str] = []
    deviation_values: list[float] = []
    validated_count = 0

    ordered_rows = sorted(
        list(enumerate(raw_positions, start=1)),
        key=lambda item: str(
            _first_present(item[1], ("position_id", "position_ref", "id", "token_id"))
            or f"__row_{item[0]}"
        ),
    )

    for row_index, row in ordered_rows:
        position_id = str(
            _first_present(row, ("position_id", "position_ref", "id", "token_id"))
            or f"row:{row_index}"
        ).strip()

        position_pnl_raw = _first_present(row, ("position_pnl_usd", "net_pnl_usd", "pnl_usd"))
        hodl_pnl_raw = _first_present(row, ("hodl_pnl_usd",))
        pnl_vs_hodl_raw = _first_present(row, ("pnl_vs_hodl_usd",))

        position_pnl_usd, reason_position = _to_finite_float(position_pnl_raw)
        hodl_pnl_usd, reason_hodl = _to_finite_float(hodl_pnl_raw)
        pnl_vs_hodl_usd, reason_pnl_vs_hodl = _to_finite_float(pnl_vs_hodl_raw)

        validation_reasons: list[str] = []
        if position_pnl_usd is None:
            validation_reasons.append(f"position_pnl_usd:{reason_position}")
        if hodl_pnl_usd is None:
            validation_reasons.append(f"hodl_pnl_usd:{reason_hodl}")
        if pnl_vs_hodl_usd is None:
            validation_reasons.append(f"pnl_vs_hodl_usd:{reason_pnl_vs_hodl}")

        expected_pnl_vs_hodl_usd = (
            None
            if (position_pnl_usd is None or hodl_pnl_usd is None)
            else position_pnl_usd - hodl_pnl_usd
        )

        manual_reference = manual_check_map.get(position_id)
        reference_source = "manual_check" if manual_reference is not None else "computed"
        reference_pnl_vs_hodl_usd = (
            manual_reference
            if manual_reference is not None
            else expected_pnl_vs_hodl_usd
        )

        deviation_pct: float | None = None
        if (
            pnl_vs_hodl_usd is not None
            and reference_pnl_vs_hodl_usd is not None
            and math.isfinite(reference_pnl_vs_hodl_usd)
        ):
            deviation_pct, deviation_reason = _compute_deviation_pct(
                actual=pnl_vs_hodl_usd,
                reference=reference_pnl_vs_hodl_usd,
                near_zero_epsilon=near_zero_epsilon,
            )
            if deviation_pct is None:
                validation_reasons.append(f"deviation_pct:{deviation_reason}")
            elif deviation_reason == "NEAR_ZERO_DENOMINATOR":
                validation_reasons.append("deviation_pct:NEAR_ZERO_DENOMINATOR")
        else:
            validation_reasons.append("reference_pnl_vs_hodl_usd:VALUE_MISSING_OR_INVALID")

        is_validated = (
            position_pnl_usd is not None
            and hodl_pnl_usd is not None
            and pnl_vs_hodl_usd is not None
            and deviation_pct is not None
        )
        if is_validated:
            validated_count += 1
            deviation_values.append(float(deviation_pct))
        else:
            reasons.append(
                f"MALFORMED_POSITION_RECORD:{position_id}:"
                + ",".join(sorted(set(validation_reasons)))
            )

        normalized_rows.append(
            {
                "position_id": position_id,
                "position_pnl_usd": position_pnl_usd,
                "hodl_pnl_usd": hodl_pnl_usd,
                "pnl_vs_hodl_usd": pnl_vs_hodl_usd,
                "computed_pnl_vs_hodl_usd": expected_pnl_vs_hodl_usd,
                "reference_pnl_vs_hodl_usd": reference_pnl_vs_hodl_usd,
                "reference_source": reference_source,
                "deviation_pct": deviation_pct,
                "is_validated": is_validated,
                "validation_reasons": sorted(set(validation_reasons)),
            }
        )

    return {
        "positions_total": len(raw_positions),
        "positions_validated_count": validated_count,
        "pnl_hodl_deviation_max_pct": (max(deviation_values) if deviation_values else None),
        "pnl_hodl_deviation_p95_pct": _percentile_nearest_rank(deviation_values, 0.95),
        "position_rows": normalized_rows,
        "position_validation_reasons": _dedupe_preserve_order(reasons),
    }


def build_gate3_contract_snapshot(
    *,
    summary: Gate3LogSummary,
    reader_threshold: int,
    min_positions: int,
    pnl_deviation_threshold_pct: float,
    position_eval: dict[str, Any],
    shadow_log_loaded: bool,
    input_reasons: list[str],
) -> dict[str, Any]:
    positions_total = int(position_eval.get("positions_total", 0) or 0)
    positions_validated_count = int(position_eval.get("positions_validated_count", 0) or 0)
    deviation_max = position_eval.get("pnl_hodl_deviation_max_pct")
    deviation_p95 = position_eval.get("pnl_hodl_deviation_p95_pct")

    reader_ok_count = int(summary.reader_ok) if shadow_log_loaded else 0
    reader_ok_threshold_pass = shadow_log_loaded and reader_ok_count >= int(reader_threshold)
    errors_zero_pass = shadow_log_loaded and int(summary.errors) == 0
    min_positions_pass = positions_validated_count >= int(min_positions)
    pnl_hodl_under_1pct_pass = (
        positions_total > 0
        and positions_validated_count == positions_total
        and deviation_max is not None
        and float(deviation_max) <= float(pnl_deviation_threshold_pct)
    )

    reasons: list[str] = []
    reasons.extend(input_reasons)
    reasons.extend([str(reason) for reason in position_eval.get("position_validation_reasons", [])])

    if not shadow_log_loaded:
        reasons.append("SHADOW_LOG_UNAVAILABLE")
    if positions_total == 0:
        reasons.append("POSITIONS_SNAPSHOT_MISSING_OR_EMPTY")
    if not min_positions_pass:
        reasons.append("MIN_VALIDATED_POSITIONS_THRESHOLD_NOT_MET")
    if not pnl_hodl_under_1pct_pass:
        reasons.append("PNL_HODL_DEVIATION_THRESHOLD_NOT_MET")
    if not reader_ok_threshold_pass:
        reasons.append("READER_OK_THRESHOLD_NOT_MET")
    if not errors_zero_pass:
        reasons.append("SHADOW_ERRORS_NOT_ZERO_OR_LOG_UNAVAILABLE")

    all_pass = (
        pnl_hodl_under_1pct_pass
        and min_positions_pass
        and reader_ok_threshold_pass
        and errors_zero_pass
    )
    verdict = "PASS" if all_pass else "FAIL"

    missing_artifacts: list[str] = []
    if not shadow_log_loaded:
        missing_artifacts.append("SHADOW_LOG")
    if positions_total == 0:
        missing_artifacts.append("POSITIONS_SNAPSHOT")

    evidence_gaps: list[str] = []
    if not min_positions_pass:
        evidence_gaps.append("VALIDATED_POSITIONS_BELOW_MIN_THRESHOLD")
    if not reader_ok_threshold_pass:
        evidence_gaps.append("READER_OK_BELOW_THRESHOLD")
    if not errors_zero_pass:
        evidence_gaps.append("SHADOW_ERRORS_NON_ZERO_OR_LOG_UNAVAILABLE")
    if not pnl_hodl_under_1pct_pass:
        evidence_gaps.append("PNL_HODL_DEVIATION_ABOVE_THRESHOLD_OR_INCOMPLETE")

    return {
        "positions_total": positions_total,
        "positions_validated_count": positions_validated_count,
        "pnl_hodl_deviation_max_pct": deviation_max,
        "pnl_hodl_deviation_p95_pct": deviation_p95,
        "pnl_hodl_under_1pct_pass": pnl_hodl_under_1pct_pass,
        "min_positions_pass": min_positions_pass,
        "reader_ok_count": reader_ok_count,
        "reader_ok_threshold_pass": reader_ok_threshold_pass,
        "errors_zero_pass": errors_zero_pass,
        "all_pass": all_pass,
        "verdict": verdict,
        "reasons": _dedupe_preserve_order(reasons),
        "missing_artifacts": _dedupe_preserve_order(missing_artifacts),
        "evidence_gaps": _dedupe_preserve_order(evidence_gaps),
    }


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    near_zero_epsilon, epsilon_reason = _to_finite_float(args.near_zero_epsilon)
    if near_zero_epsilon is None or near_zero_epsilon <= 0:
        fallback_epsilon = _DEFAULT_NEAR_ZERO_EPSILON
        input_reasons = [
            (
                "INVALID_NEAR_ZERO_EPSILON"
                if epsilon_reason is None
                else f"INVALID_NEAR_ZERO_EPSILON:{epsilon_reason}"
            )
        ]
        near_zero_epsilon = fallback_epsilon
    else:
        input_reasons = []

    pnl_deviation_threshold_pct, threshold_reason = _to_finite_float(
        args.pnl_deviation_threshold_pct
    )
    if pnl_deviation_threshold_pct is None or pnl_deviation_threshold_pct < 0:
        input_reasons.append(
            (
                "INVALID_PNL_DEVIATION_THRESHOLD"
                if threshold_reason is None
                else f"INVALID_PNL_DEVIATION_THRESHOLD:{threshold_reason}"
            )
        )
        pnl_deviation_threshold_pct = _DEFAULT_PNL_DEVIATION_THRESHOLD_PCT

    load_dotenv(dotenv_path=".env", override=False)
    wallet_set = bool(os.getenv("WALLET_ADDRESS"))
    rpc_set = bool(os.getenv("RPC_URL_ARBITRUM"))
    baseline_positions_count = read_baseline_positions_count(args.baseline_file)

    lines: list[str] = []
    shadow_log_loaded = False
    try:
        lines = _load_lines(unit=args.unit, window=args.window, from_file=args.from_file)
        shadow_log_loaded = True
    except (OSError, RuntimeError, UnicodeDecodeError) as exc:
        input_reasons.append(f"SHADOW_LOG_LOAD_ERROR:{exc.__class__.__name__}")

    summary = summarize_log_lines(lines) if shadow_log_loaded else Gate3LogSummary()

    position_rows: list[dict[str, Any]] = []
    if args.positions_file:
        position_rows, reasons = _load_positions_from_file(args.positions_file)
        input_reasons.extend(reasons)

    position_samples: list[dict[str, object]] = []
    if not position_rows and not args.positions_file and wallet_set and rpc_set:
        try:
            samples, valid_count = asyncio.run(
                _load_position_samples(
                    wallet_address=str(os.getenv("WALLET_ADDRESS")),
                    rpc_url=str(os.getenv("RPC_URL_ARBITRUM")),
                )
            )
            position_samples = samples[: max(0, int(args.max_position_samples))]
            position_rows = [dict(sample) for sample in samples]
            if int(valid_count) <= 0 and not position_rows:
                input_reasons.append("POSITIONS_READER_EMPTY")
        except Exception as exc:  # noqa: BLE001
            input_reasons.append(f"POSITION_SAMPLE_LOAD_ERROR:{exc.__class__.__name__}")
    elif not position_rows:
        input_reasons.append(
            "POSITIONS_SNAPSHOT_EMPTY_OR_INVALID"
            if args.positions_file
            else "POSITIONS_SNAPSHOT_NOT_PROVIDED"
        )

    if not position_samples:
        position_samples = [
            {
                "position_id": str(
                    _first_present(record, ("position_id", "position_ref", "id", "token_id"))
                    or ""
                ),
                "position_pnl_usd": _first_present(record, ("position_pnl_usd", "net_pnl_usd", "pnl_usd")),
                "hodl_pnl_usd": _first_present(record, ("hodl_pnl_usd",)),
                "pnl_vs_hodl_usd": _first_present(record, ("pnl_vs_hodl_usd",)),
            }
            for record in position_rows[: max(0, int(args.max_position_samples))]
        ]

    manual_check_map, manual_reasons = _load_manual_check_map(args.manual_check_file)
    input_reasons.extend(manual_reasons)

    position_eval = _evaluate_positions(
        raw_positions=position_rows,
        manual_check_map=manual_check_map,
        near_zero_epsilon=float(near_zero_epsilon),
    )
    contract_snapshot = build_gate3_contract_snapshot(
        summary=summary,
        reader_threshold=int(args.reader_threshold),
        min_positions=int(args.min_positions),
        pnl_deviation_threshold_pct=float(pnl_deviation_threshold_pct),
        position_eval=position_eval,
        shadow_log_loaded=shadow_log_loaded,
        input_reasons=input_reasons,
    )

    gate_checks = {
        "reader_ok_threshold_pass": contract_snapshot["reader_ok_threshold_pass"],
        "errors_zero_pass": contract_snapshot["errors_zero_pass"],
        "sim_fail_zero_pass": shadow_log_loaded and summary.sim_fail == 0,
        "position_samples_min_pass": contract_snapshot["min_positions_pass"],
        "pnl_hodl_under_1pct_pass": contract_snapshot["pnl_hodl_under_1pct_pass"],
        "all_pass": contract_snapshot["all_pass"],
    }

    payload = {
        "contract": "gate3_evidence_contract_v1",
        "unit": args.unit,
        "window": args.window,
        "reader_threshold": args.reader_threshold,
        "min_positions": args.min_positions,
        "pnl_deviation_threshold_pct": pnl_deviation_threshold_pct,
        "near_zero_epsilon": near_zero_epsilon,
        "formula": {
            "expected_pnl_vs_hodl_usd": "position_pnl_usd - hodl_pnl_usd",
            "deviation_pct": (
                "abs(actual_pnl_vs_hodl_usd - reference_pnl_vs_hodl_usd) / "
                "max(abs(reference_pnl_vs_hodl_usd), near_zero_epsilon) * 100"
            ),
            "p95_method": "nearest-rank (ceil(0.95 * N))",
        },
        "preflight": {
            "wallet_set": wallet_set,
            "rpc_set": rpc_set,
            "baseline_positions_count": baseline_positions_count,
            "from_files": args.from_file or None,
            "positions_file": args.positions_file or None,
            "manual_check_file": args.manual_check_file or None,
            "shadow_log_loaded": shadow_log_loaded,
        },
        "summary": summary.to_dict(),
        "position_samples": position_samples,
        "position_samples_count": len(position_samples),
        "position_samples_valid_count": int(position_eval["positions_validated_count"]),
        "position_evidence": {
            "rows": position_eval["position_rows"][: max(0, int(args.max_position_samples))],
            "validation_reasons": position_eval["position_validation_reasons"],
        },
        "gate_checks": gate_checks,
        "sim_fail_zero_pass": gate_checks["sim_fail_zero_pass"],
        "positions_total": contract_snapshot["positions_total"],
        "positions_validated_count": contract_snapshot["positions_validated_count"],
        "pnl_hodl_deviation_max_pct": contract_snapshot["pnl_hodl_deviation_max_pct"],
        "pnl_hodl_deviation_p95_pct": contract_snapshot["pnl_hodl_deviation_p95_pct"],
        "pnl_hodl_under_1pct_pass": contract_snapshot["pnl_hodl_under_1pct_pass"],
        "min_positions_pass": contract_snapshot["min_positions_pass"],
        "reader_ok_count": contract_snapshot["reader_ok_count"],
        "reader_ok_threshold_pass": contract_snapshot["reader_ok_threshold_pass"],
        "errors_zero_pass": contract_snapshot["errors_zero_pass"],
        "all_pass": contract_snapshot["all_pass"],
        "verdict": contract_snapshot["verdict"],
        "missing_artifacts": contract_snapshot["missing_artifacts"],
        "evidence_gaps": contract_snapshot["evidence_gaps"],
        "reasons": contract_snapshot["reasons"],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
