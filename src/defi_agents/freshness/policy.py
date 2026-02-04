from __future__ import annotations

from typing import Dict, List

from ..scout.config import FreshnessConfig
from ..scout.models import ScoutResult


def apply_freshness_policy(results: List[ScoutResult], config: FreshnessConfig) -> Dict[str, int]:
    counters = {
        "rechecked_count": 0,
        "fresh_count": 0,
        "stale_count": 0,
        "unverified_count": 0,
        "diverged_count": 0,
        "downgraded_to_watchlist_count": 0,
    }

    if not results:
        return counters

    for res in results:
        meta = res.metadata
        status = (meta.get("freshness_status") or "UNVERIFIED").upper()
        meta["freshness_status"] = status
        meta.setdefault("freshness_provider", "none")
        meta.setdefault("source_timestamp", "")
        meta.setdefault("age_minutes", "")
        meta.setdefault("staleness_score", "")
        meta.setdefault("apy_divergence_pct", "")
        meta.setdefault("tvl_divergence_pct", "")

        if status in {"FRESH", "STALE"}:
            counters["rechecked_count"] += 1

        if status == "FRESH":
            counters["fresh_count"] += 1
        elif status == "STALE":
            counters["stale_count"] += 1
            _append_reason(meta, "STALE_DATA")
        else:
            counters["unverified_count"] += 1
            if config.recheck_enabled:
                _append_reason(meta, "UNVERIFIED_FRESHNESS")

        apy_div = _as_float(meta.get("apy_divergence_pct"))
        tvl_div = _as_float(meta.get("tvl_divergence_pct"))
        has_divergence = (
            apy_div is not None
            and tvl_div is not None
            and (
                apy_div > float(config.max_apy_divergence_pct)
                or tvl_div > float(config.max_tvl_divergence_pct)
            )
        )
        if has_divergence:
            counters["diverged_count"] += 1
            _append_reason(meta, "DIVERGENCE_HIGH")

        should_downgrade = (
            config.recheck_enabled
            and config.enforce_freshness_for_actionable
            and meta.get("report_group") == "ACTIONABLE"
            and (status != "FRESH" or has_divergence)
        )
        if should_downgrade:
            meta["report_group"] = "WATCHLIST"
            counters["downgraded_to_watchlist_count"] += 1

    return counters


def _append_reason(meta: dict, code: str) -> None:
    existing = [item.strip() for item in (meta.get("warn_reasons") or "").split(",") if item.strip()]
    if code not in existing:
        existing.append(code)
    meta["warn_reasons"] = ",".join(existing)


def _as_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
