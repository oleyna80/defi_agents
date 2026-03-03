from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


_EXEC_SUMMARY_RE = re.compile(
    r"Execution summary: .*?\bblocked_by_policy=(?P<blocked_by_policy>\d+)\s+"
    r"sim_ok=(?P<sim_ok>\d+)\s+sim_fail=(?P<sim_fail>\d+)\s+"
    r"exec_ok=(?P<exec_ok>\d+)\s+exec_fail=(?P<exec_fail>\d+)"
)
_ERROR_RE = re.compile(r"\b(?:Traceback|CRITICAL|ERROR)\b")


@dataclass(frozen=True)
class Gate3LogSummary:
    execution_cycles: int = 0
    reader_ok: int = 0
    errors: int = 0
    blocked_by_policy: int = 0
    sim_ok: int = 0
    sim_fail: int = 0
    exec_ok: int = 0
    exec_fail: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "execution_cycles": self.execution_cycles,
            "reader_ok": self.reader_ok,
            "errors": self.errors,
            "blocked_by_policy": self.blocked_by_policy,
            "sim_ok": self.sim_ok,
            "sim_fail": self.sim_fail,
            "exec_ok": self.exec_ok,
            "exec_fail": self.exec_fail,
        }


def parse_execution_summary_line(line: str) -> dict[str, int] | None:
    match = _EXEC_SUMMARY_RE.search(line)
    if match is None:
        return None
    return {key: int(value) for key, value in match.groupdict().items()}


def summarize_log_lines(lines: Iterable[str]) -> Gate3LogSummary:
    execution_cycles = 0
    reader_ok = 0
    errors = 0
    blocked_by_policy = 0
    sim_ok = 0
    sim_fail = 0
    exec_ok = 0
    exec_fail = 0

    for line in lines:
        if "Execution states loaded: source=position_reader" in line:
            reader_ok += 1
        if _ERROR_RE.search(line):
            errors += 1

        parsed = parse_execution_summary_line(line)
        if parsed is None:
            continue
        execution_cycles += 1
        blocked_by_policy += parsed["blocked_by_policy"]
        sim_ok += parsed["sim_ok"]
        sim_fail += parsed["sim_fail"]
        exec_ok += parsed["exec_ok"]
        exec_fail += parsed["exec_fail"]

    return Gate3LogSummary(
        execution_cycles=execution_cycles,
        reader_ok=reader_ok,
        errors=errors,
        blocked_by_policy=blocked_by_policy,
        sim_ok=sim_ok,
        sim_fail=sim_fail,
        exec_ok=exec_ok,
        exec_fail=exec_fail,
    )


def read_baseline_positions_count(path: str | Path) -> int:
    file_path = Path(path)
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError, UnicodeDecodeError):
        return 0
    if not isinstance(payload, dict):
        return 0
    positions = payload.get("positions")
    if not isinstance(positions, dict):
        return 0
    return len(positions)
