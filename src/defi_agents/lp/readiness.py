from __future__ import annotations

import re
from collections.abc import Mapping

READINESS_BLOCKER_GRAPH_API_KEY_MISSING = "GRAPH_API_KEY_MISSING"
READINESS_BLOCKER_SUBGRAPH_SCHEMA_UNSUPPORTED = "SUBGRAPH_SCHEMA_UNSUPPORTED"
READINESS_BLOCKER_TICK_PROVIDER_INIT_ERROR = "TICK_PROVIDER_INIT_ERROR"
READINESS_BLOCKER_TICK_PROVIDER_RUNTIME_ERROR = "TICK_PROVIDER_RUNTIME_ERROR"
READINESS_BLOCKER_RPC_TICK_UNAVAILABLE = "RPC_TICK_UNAVAILABLE"

READINESS_BLOCKER_CODES: set[str] = {
    READINESS_BLOCKER_GRAPH_API_KEY_MISSING,
    READINESS_BLOCKER_SUBGRAPH_SCHEMA_UNSUPPORTED,
    READINESS_BLOCKER_TICK_PROVIDER_INIT_ERROR,
    READINESS_BLOCKER_TICK_PROVIDER_RUNTIME_ERROR,
    READINESS_BLOCKER_RPC_TICK_UNAVAILABLE,
}

_MACHINE_CODE_RE = re.compile(r"^[A-Z0-9_]+$")


def normalize_readiness_blocker_code(raw_code: object) -> str | None:
    code = str(raw_code or "").strip().upper()
    if not code or code == "NONE":
        return None
    if code in READINESS_BLOCKER_CODES:
        return code

    if "GRAPH_API_KEY" in code and "MISSING" in code:
        return READINESS_BLOCKER_GRAPH_API_KEY_MISSING
    if code == "SUBGRAPH_SCHEMA_UNSUPPORTED":
        return READINESS_BLOCKER_SUBGRAPH_SCHEMA_UNSUPPORTED

    if code in {"RPC_UNAVAILABLE", "RPC_TICK_UNAVAILABLE"}:
        return READINESS_BLOCKER_RPC_TICK_UNAVAILABLE

    if code.startswith("PROVIDER_INIT_"):
        return READINESS_BLOCKER_TICK_PROVIDER_INIT_ERROR
    if code.startswith("TICK_PROVIDER_INIT"):
        return READINESS_BLOCKER_TICK_PROVIDER_INIT_ERROR

    if code.startswith("PROVIDER_UNAVAILABLE_"):
        return READINESS_BLOCKER_TICK_PROVIDER_RUNTIME_ERROR
    if code.startswith("TICK_PROVIDER_RUNTIME"):
        return READINESS_BLOCKER_TICK_PROVIDER_RUNTIME_ERROR
    if code.startswith("PROVIDER_RUNTIME_"):
        return READINESS_BLOCKER_TICK_PROVIDER_RUNTIME_ERROR
    if code in {
        "SUBGRAPH_ERROR",
        "SUBGRAPH_TIMEOUT",
        "PAGINATION_LIMIT_REACHED",
        "TICK_COUNT_ZERO",
        "RPC_DRIFT_EXCEEDED",
        "TICK_SCAN_ERROR",
    }:
        return READINESS_BLOCKER_TICK_PROVIDER_RUNTIME_ERROR

    if _MACHINE_CODE_RE.fullmatch(code):
        return code
    return None


def normalize_readiness_blocker_counts(
    counts: Mapping[object, object] | None,
) -> dict[str, int]:
    out: dict[str, int] = {}
    if not counts:
        return out
    for raw_code, raw_count in counts.items():
        code = normalize_readiness_blocker_code(raw_code)
        if not code:
            continue
        try:
            count = int(str(raw_count).strip())
        except (TypeError, ValueError):
            continue
        if count <= 0:
            continue
        out[code] = int(out.get(code, 0)) + count
    return dict(sorted(out.items()))


def readiness_blocker_from_tick_degradation_reason(raw_reason: object) -> str | None:
    reason = str(raw_reason or "").strip().upper()
    if not reason:
        return None
    if reason == "RPC_UNAVAILABLE":
        return READINESS_BLOCKER_RPC_TICK_UNAVAILABLE
    if reason in {
        "RPC_DRIFT_EXCEEDED",
        "SUBGRAPH_TIMEOUT",
        "SUBGRAPH_ERROR",
        "PAGINATION_LIMIT_REACHED",
        "TICK_COUNT_ZERO",
    }:
        return READINESS_BLOCKER_TICK_PROVIDER_RUNTIME_ERROR
    return normalize_readiness_blocker_code(reason)
