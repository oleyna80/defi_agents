from __future__ import annotations

from typing import Dict, List

from ..scout.config import FreshnessConfig
from ..scout.models import ScoutResult, SourceConfidence


def map_source_confidence(meta: dict, config: FreshnessConfig) -> SourceConfidence:
    """Pure mapper: freshness metadata → SourceConfidence.

    Guardrail: unknown/empty freshness_status always returns AGGREGATOR_ONLY.
    VERIFIED requires explicit FRESH status AND divergence within configured limits.
    """
    status = (meta.get("freshness_status") or "").upper()
    if status == "STALE":
        return SourceConfidence.STALE
    if status != "FRESH":
        # Unknown, empty, UNVERIFIED, or any unexpected value → safe default.
        return SourceConfidence.AGGREGATOR_ONLY

    # FRESH — check divergence thresholds before promoting to VERIFIED.
    apy_div = _as_float(meta.get("apy_divergence_pct"))
    tvl_div = _as_float(meta.get("tvl_divergence_pct"))
    if _has_divergence(apy_div, tvl_div, config):
        return SourceConfidence.DIVERGED

    return SourceConfidence.VERIFIED


def apply_freshness_policy(results: List[ScoutResult], config: FreshnessConfig) -> Dict[str, int]:
    counters = {
        "rechecked_count": 0,
        "fresh_count": 0,
        "stale_count": 0,
        "unverified_count": 0,
        "diverged_count": 0,
        "downgraded_to_watchlist_count": 0,
        "aave_checked_count": 0,
        "aave_ok_count": 0,
        "aave_timeout_count": 0,
        "aave_error_count": 0,
        "aave_schema_mismatch_count": 0,
        "aave_addr_mismatch_count": 0,
    }

    if not results:
        return counters

    for res in results:
        meta = res.metadata
        if meta.get("aave_recheck_checked") == "1":
            counters["aave_checked_count"] += 1
            outcome = (meta.get("aave_recheck_outcome") or "").strip().lower()
            if outcome == "ok":
                counters["aave_ok_count"] += 1
            elif outcome == "timeout":
                counters["aave_timeout_count"] += 1
            elif outcome == "schema_mismatch":
                counters["aave_schema_mismatch_count"] += 1
            elif outcome == "addr_mismatch":
                counters["aave_addr_mismatch_count"] += 1
            else:
                counters["aave_error_count"] += 1

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
        has_divergence = _has_divergence(apy_div, tvl_div, config)
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

        # Compute and set source confidence on candidate + metadata.
        confidence = map_source_confidence(meta, config)
        res.candidate.source_confidence = confidence
        meta["source_confidence"] = confidence.value

    return counters


def apply_confidence_factors(results: List[ScoutResult], factors: Dict[str, float]) -> None:
    """Apply source-confidence multipliers to report ranking score.

    Idempotent per result: preserves pre-confidence score in metadata["score_raw"].
    """
    if not results:
        return
    for res in results:
        meta = res.metadata
        raw_score = _as_float(meta.get("score_raw"))
        if raw_score is None:
            raw_score = float(res.score or 0.0)
            meta["score_raw"] = f"{raw_score:.6f}"

        confidence = str(meta.get("source_confidence") or "AGGREGATOR_ONLY").upper()
        factor = _resolve_confidence_factor(confidence, factors)
        meta["confidence_factor"] = f"{factor:.4f}"
        res.score = raw_score * factor


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


def _has_divergence(apy_div: float | None, tvl_div: float | None, config: FreshnessConfig) -> bool:
    return (
        (apy_div is not None and apy_div > float(config.max_apy_divergence_pct))
        or (tvl_div is not None and tvl_div > float(config.max_tvl_divergence_pct))
    )


def _resolve_confidence_factor(confidence: str, factors: Dict[str, float]) -> float:
    fallback = _as_float(factors.get("AGGREGATOR_ONLY")) if factors else None
    if fallback is None:
        fallback = 1.0
    value = _as_float(factors.get(confidence)) if factors else None
    if value is None:
        return fallback
    return max(0.0, float(value))
