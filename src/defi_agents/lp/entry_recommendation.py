from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from ..scout.models import ScoutResult
from .cross_protocol_selector import (
    compute_rank_v1_components,
    rank_v1,
    resolve_selector_range,
)
from .models import EntryActionability, EntryConfidenceBand, EntryRecommendation
from .readiness import normalize_readiness_blocker_code


_SOURCE_CONFIDENCE_FACTOR: dict[str, float] = {
    "VERIFIED": 1.0,
    "AGGREGATOR_ONLY": 0.85,
    "DIVERGED": 0.25,
    "STALE": 0.15,
}

_CONFIDENCE_ORDER: dict[EntryConfidenceBand, int] = {
    EntryConfidenceBand.HIGH: 3,
    EntryConfidenceBand.MEDIUM: 2,
    EntryConfidenceBand.LOW: 1,
}

_DETERMINISTIC_WATCHLIST_REASONS: set[str] = {
    "REPORT_GROUP_WATCHLIST",
    "SIM_STATUS_PARTIAL",
    "SIM_STATUS_UNSUPPORTED",
    "SIM_RISK_ABOVE_PROFILE",
    "NON_LP_YIELD_TYPE",
    "UNSUPPORTED_ENTRY_VENUE",
    "MISSING_POOL_REFERENCE",
    "RANGE_NOT_COMPUTED",
    "TICK_DATA_DEGRADED",
    "SOURCE_CONFIDENCE_DIVERGED",
    "SOURCE_CONFIDENCE_STALE",
    "FRESHNESS_STALE",
    "NET_PROFIT_BELOW_THRESHOLD",
    "INVALID_OR_MISSING_RANGE",
    "INSUFFICIENT_STABILITY_HISTORY",
    "TARGET_SCOPE_EMPTY",
    "GRAPH_API_KEY_MISSING",
    "SUBGRAPH_SCHEMA_UNSUPPORTED",
    "TICK_PROVIDER_INIT_ERROR",
    "TICK_PROVIDER_RUNTIME_ERROR",
    "RPC_TICK_UNAVAILABLE",
}
_REASON_CODE_RE = re.compile(r"^[A-Z0-9_]+$")
_EVM_ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
_PAIR_SPLIT_RE = re.compile(r"[\s/_-]+")
_PROJECT_NORMALIZE_RE = re.compile(r"[\s_-]+")


def normalize_pair_for_target_matching(raw_pair: object) -> str:
    if not isinstance(raw_pair, str):
        return ""
    parts = [part for part in _PAIR_SPLIT_RE.split(raw_pair.strip().upper()) if part]
    # Target scope only supports deterministic two-token pairs.
    if len(parts) != 2:
        return ""
    left = _normalize_pair_token(parts[0])
    right = _normalize_pair_token(parts[1])
    if not left or not right or left == right:
        return ""
    ordered = sorted((left, right))
    return f"{ordered[0]}/{ordered[1]}"


def filter_lp_entry_target_scope(
    results: Sequence[ScoutResult],
    *,
    target_pair: str,
    allowed_chains: Sequence[str] | None,
    allowed_projects: Sequence[str] | None,
) -> list[ScoutResult]:
    normalized_target_pair = normalize_pair_for_target_matching(target_pair)
    normalized_chains = {
        str(chain).strip().lower()
        for chain in (allowed_chains or [])
        if str(chain).strip()
    }
    normalized_projects = {
        _normalize_project_name_for_target(project)
        for project in (allowed_projects or [])
        if str(project).strip()
    }

    matched: list[ScoutResult] = []
    for result in results:
        if not is_lp_entry_target_scope_match(
            result,
            normalized_target_pair=normalized_target_pair,
            normalized_chains=normalized_chains,
            normalized_projects=normalized_projects,
        ):
            continue
        matched.append(result)
    return matched


def is_lp_entry_target_scope_match(
    result: ScoutResult,
    *,
    normalized_target_pair: str,
    normalized_chains: set[str],
    normalized_projects: set[str],
) -> bool:
    candidate_pair = normalize_pair_for_target_matching(result.candidate.symbol)
    if normalized_target_pair and candidate_pair != normalized_target_pair:
        return False
    if (
        normalized_chains
        and result.candidate.chain.strip().lower() not in normalized_chains
    ):
        return False
    if (
        normalized_projects
        and _normalize_project_name_for_target(result.candidate.project)
        not in normalized_projects
    ):
        return False
    return True


def split_lp_entry_eligibility(
    results: Sequence[ScoutResult],
) -> tuple[list[ScoutResult], list[tuple[ScoutResult, str]]]:
    eligible: list[ScoutResult] = []
    ineligible: list[tuple[ScoutResult, str]] = []
    for result in results:
        reason = _lp_entry_ineligible_reason(result)
        if reason is None:
            eligible.append(result)
            continue
        ineligible.append((result, reason))
    return eligible, ineligible


def build_ineligible_entry_recommendations(
    ineligible: Sequence[tuple[ScoutResult, str]],
) -> list[EntryRecommendation]:
    recommendations: list[EntryRecommendation] = []
    for result, reason in ineligible:
        deterministic_reason = normalize_watchlist_reason(
            reason,
            default="REPORT_GROUP_WATCHLIST",
        )
        meta = result.metadata
        meta["report_group"] = "WATCHLIST"
        meta["watchlist_reason"] = deterministic_reason
        blocker_reason = normalize_readiness_blocker_code(meta.get("readiness_blocker"))
        if blocker_reason:
            meta["watchlist_blocker_reason"] = blocker_reason
        reasons = _parse_reason_codes(meta.get("warn_reasons"))
        if deterministic_reason not in reasons:
            reasons.append(deterministic_reason)
        recommendations.append(
            EntryRecommendation(
                chain=result.candidate.chain,
                project=result.candidate.project,
                pair=result.candidate.symbol,
                fee_tier=_fee_tier_bps(result),
                range_mode=str(meta.get("entry_range_mode") or "AUTO").upper(),
                market_regime=str(meta.get("entry_market_regime") or "SIDEWAYS").upper(),
                suggested_range_lower_tick=_as_int(
                    meta.get("suggested_range_lower_tick")
                ),
                suggested_range_upper_tick=_as_int(
                    meta.get("suggested_range_upper_tick")
                ),
                in_range_liquidity_competition=0.0,
                volume_fee_proxy=0.0,
                cost_penalty=0.0,
                confidence_score=0.0,
                confidence=EntryConfidenceBand.LOW,
                reasons=reasons,
                watchlist_reason=deterministic_reason,
                watchlist_blocker_reason=blocker_reason,
                actionability=EntryActionability.WATCHLIST,
                rank_v1=0.0,
                source_pool_id=result.candidate.pool_id,
            )
        )
    return sorted(recommendations, key=_sort_key_watchlist)


def normalize_watchlist_reason(
    raw_reason: object,
    *,
    default: str = "REPORT_GROUP_WATCHLIST",
) -> str:
    reason = str(raw_reason or "").strip().upper()
    if not reason:
        return default
    if reason in _DETERMINISTIC_WATCHLIST_REASONS:
        return reason
    # Keep extensibility for future machine-readable reason codes,
    # but hard-reject free-text values.
    if _REASON_CODE_RE.fullmatch(reason):
        return reason
    return default


def summarize_watchlist_reason_counts(
    recommendations: Sequence[EntryRecommendation],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for rec in recommendations:
        if rec.actionability != EntryActionability.WATCHLIST:
            continue
        reason = normalize_watchlist_reason(rec.watchlist_reason)
        counts[reason] = int(counts.get(reason, 0)) + 1
    return dict(sorted(counts.items()))


def summarize_watchlist_blocker_reason_counts(
    recommendations: Sequence[EntryRecommendation],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for rec in recommendations:
        if rec.actionability != EntryActionability.WATCHLIST:
            continue
        reason = normalize_readiness_blocker_code(rec.watchlist_blocker_reason)
        if not reason:
            continue
        counts[reason] = int(counts.get(reason, 0)) + 1
    return dict(sorted(counts.items()))


def build_entry_recommendations(
    results: list[ScoutResult],
    *,
    top_n: int = 5,
    range_mode: str = "AUTO",
    market_regime: str = "SIDEWAYS",
    range_lower_tick: int | None = None,
    range_upper_tick: int | None = None,
    stability_observation_counts: Mapping[str, int] | None = None,
    stability_min_observations: int = 0,
    calibration: object | None = None,
) -> list[EntryRecommendation]:
    """Build deterministic LP entry recommendations.

    Contract:
    - Actionable candidates are sorted by rank_v1 DESC with stable tie-breakers.
    - Only actionable Top-N are kept.
    - Watchlist tail is preserved and sorted deterministically.
    - Fail-safe downgrades are mirrored back into ScoutResult metadata.
    """
    if not results:
        return []

    stability_counts: Mapping[str, int] = stability_observation_counts or {}
    minimum_observations = max(0, int(stability_min_observations or 0))
    calibration_values = _resolve_calibration(calibration)

    recommendations = [
        _build_one(
            result,
            range_mode=range_mode,
            market_regime=market_regime,
            range_lower_tick=range_lower_tick,
            range_upper_tick=range_upper_tick,
            stability_observation_counts=stability_counts,
            stability_min_observations=minimum_observations,
            calibration=calibration_values,
        )
        for result in results
    ]
    actionable = [
        r for r in recommendations if r.actionability == EntryActionability.ACTIONABLE
    ]
    watchlist = [
        r for r in recommendations if r.actionability == EntryActionability.WATCHLIST
    ]

    actionable_sorted = sorted(actionable, key=_sort_key_actionable)
    watchlist_sorted = sorted(watchlist, key=_sort_key_watchlist)

    limited_top_n = max(1, int(top_n))
    return actionable_sorted[:limited_top_n] + watchlist_sorted


def _build_one(
    result: ScoutResult,
    *,
    range_mode: str,
    market_regime: str,
    range_lower_tick: int | None,
    range_upper_tick: int | None,
    stability_observation_counts: Mapping[str, int],
    stability_min_observations: int,
    calibration: dict[str, object],
) -> EntryRecommendation:
    meta = result.metadata
    source_confidence = str(meta.get("source_confidence") or "AGGREGATOR_ONLY").upper()
    freshness_status = str(meta.get("freshness_status") or "UNVERIFIED").upper()
    tick_quality = str(meta.get("tick_data_quality") or "").upper()

    base_lower_tick = _as_int(meta.get("suggested_range_lower_tick"))
    base_upper_tick = _as_int(meta.get("suggested_range_upper_tick"))
    lower_tick, upper_tick, effective_range_mode = resolve_selector_range(
        base_lower_tick=base_lower_tick,
        base_upper_tick=base_upper_tick,
        range_mode=range_mode,
        market_regime=market_regime,
        manual_lower_tick=range_lower_tick,
        manual_upper_tick=range_upper_tick,
    )
    has_valid_range = (
        lower_tick is not None and upper_tick is not None and lower_tick < upper_tick
    )

    actionability = EntryActionability.ACTIONABLE
    watchlist_reason: str | None = None
    watchlist_blocker_reason: str | None = normalize_readiness_blocker_code(
        meta.get("readiness_blocker")
    )
    seed_report_group = str(
        meta.get("lp_entry_seed_report_group")
        or meta.get("report_group")
        or "WATCHLIST"
    ).upper()
    seed_watchlist_reason = meta.get("lp_entry_seed_watchlist_reason") or meta.get(
        "watchlist_reason"
    )

    if seed_report_group != "ACTIONABLE":
        actionability = EntryActionability.WATCHLIST
        watchlist_reason = normalize_watchlist_reason(
            seed_watchlist_reason,
            default="REPORT_GROUP_WATCHLIST",
        )

    if tick_quality not in {"", "OK"}:
        actionability = EntryActionability.WATCHLIST
        watchlist_reason = "TICK_DATA_DEGRADED"

    if source_confidence in {"DIVERGED", "STALE"}:
        actionability = EntryActionability.WATCHLIST
        watchlist_reason = f"SOURCE_CONFIDENCE_{source_confidence}"

    if freshness_status == "STALE":
        actionability = EntryActionability.WATCHLIST
        watchlist_reason = "FRESHNESS_STALE"

    if lower_tick is None and upper_tick is None:
        actionability = EntryActionability.WATCHLIST
        watchlist_reason = "RANGE_NOT_COMPUTED"
    elif not has_valid_range:
        actionability = EntryActionability.WATCHLIST
        watchlist_reason = "INVALID_OR_MISSING_RANGE"

    stability_observations = max(
        0,
        int(stability_observation_counts.get(result.candidate.pool_id, 0) or 0),
    )
    if (
        actionability == EntryActionability.ACTIONABLE
        and stability_min_observations > 0
    ):
        if stability_observations < stability_min_observations:
            actionability = EntryActionability.WATCHLIST
            watchlist_reason = "INSUFFICIENT_STABILITY_HISTORY"

    meta["stability_observations"] = str(stability_observations)
    if stability_min_observations > 0:
        meta["stability_min_observations"] = str(stability_min_observations)

    # Mirror fail-safe downgrade back into report metadata.
    if actionability == EntryActionability.WATCHLIST:
        meta["report_group"] = "WATCHLIST"
        if watchlist_reason:
            meta["watchlist_reason"] = watchlist_reason
        if watchlist_blocker_reason:
            meta["watchlist_blocker_reason"] = watchlist_blocker_reason
    else:
        watchlist_blocker_reason = None

    confidence = _confidence_band(
        source_confidence=source_confidence,
        tick_quality=tick_quality,
        freshness_status=freshness_status,
        has_valid_range=has_valid_range,
        calibration=calibration,
    )

    confidence_factor = _resolve_confidence_factor(
        source_confidence=source_confidence,
        meta=meta,
        calibration=calibration,
    )

    reasons = _parse_reason_codes(meta.get("warn_reasons"))
    if watchlist_reason and watchlist_reason not in reasons:
        reasons.append(watchlist_reason)

    fee_tier = _fee_tier_bps(result)
    rank_components = compute_rank_v1_components(
        result=result,
        source_confidence=source_confidence,
        confidence_factor=confidence_factor,
        tick_quality=tick_quality,
        has_valid_range=has_valid_range,
        range_lower_tick=lower_tick,
        range_upper_tick=upper_tick,
        fee_tier=fee_tier,
    )
    rank_value = rank_v1(rank_components)

    if actionability == EntryActionability.WATCHLIST and rank_value > 0:
        # Fail-closed: watchlist entries must not compete with actionable by score.
        rank_value = 0.0

    meta["entry_range_mode"] = effective_range_mode
    meta["entry_market_regime"] = str(market_regime or "SIDEWAYS").upper()
    meta["in_range_liquidity_competition"] = (
        f"{rank_components['in_range_liquidity_competition']:.6f}"
    )
    meta["volume_fee_proxy"] = f"{rank_components['volume_fee_proxy']:.6f}"
    meta["cost_penalty"] = f"{rank_components['cost_penalty']:.6f}"
    meta["entry_confidence_score"] = f"{rank_components['confidence']:.6f}"

    return EntryRecommendation(
        chain=result.candidate.chain,
        project=result.candidate.project,
        pair=result.candidate.symbol,
        fee_tier=fee_tier,
        range_mode=effective_range_mode,
        market_regime=str(market_regime or "SIDEWAYS").upper(),
        suggested_range_lower_tick=lower_tick,
        suggested_range_upper_tick=upper_tick,
        in_range_liquidity_competition=rank_components[
            "in_range_liquidity_competition"
        ],
        volume_fee_proxy=rank_components["volume_fee_proxy"],
        cost_penalty=rank_components["cost_penalty"],
        confidence_score=rank_components["confidence"],
        confidence=confidence,
        reasons=reasons,
        watchlist_reason=watchlist_reason,
        watchlist_blocker_reason=watchlist_blocker_reason,
        actionability=actionability,
        rank_v1=rank_value,
        source_pool_id=result.candidate.pool_id,
    )


def _resolve_confidence_factor(
    *,
    source_confidence: str,
    meta: Mapping[str, str],
    calibration: dict[str, object],
) -> float:
    confidence_factor = _as_float(meta.get("confidence_factor"))
    if confidence_factor is None:
        source_factors = calibration.get("source_confidence_factors")
        if isinstance(source_factors, dict):
            confidence_factor = _as_float(source_factors.get(source_confidence))
    if confidence_factor is None:
        confidence_factor = _SOURCE_CONFIDENCE_FACTOR.get(source_confidence, 0.85)
    confidence_power = _as_float(calibration.get("rank_confidence_power"))
    if confidence_power is None:
        confidence_power = 1.0
    confidence_power = max(0.0, confidence_power)
    return max(0.0, float(confidence_factor)) ** confidence_power


def _confidence_band(
    *,
    source_confidence: str,
    tick_quality: str,
    freshness_status: str,
    has_valid_range: bool,
    calibration: dict[str, object],
) -> EntryConfidenceBand:
    if tick_quality != "OK" or not has_valid_range:
        return EntryConfidenceBand.LOW
    if freshness_status == "STALE":
        return EntryConfidenceBand.LOW

    source_factors = calibration.get("source_confidence_factors")
    confidence_factor = None
    if isinstance(source_factors, dict):
        confidence_factor = _as_float(source_factors.get(source_confidence))
    if confidence_factor is None:
        confidence_factor = _SOURCE_CONFIDENCE_FACTOR.get(source_confidence, 0.85)

    high_min = _as_float(calibration.get("confidence_high_min_factor"))
    if high_min is None:
        high_min = 0.95
    high_min = max(0.0, min(1.0, high_min))

    medium_min = _as_float(calibration.get("confidence_medium_min_factor"))
    if medium_min is None:
        medium_min = 0.70
    medium_min = max(0.0, min(1.0, medium_min))
    if medium_min > high_min:
        medium_min = high_min

    if confidence_factor >= high_min and freshness_status == "FRESH":
        return EntryConfidenceBand.HIGH
    if confidence_factor >= medium_min:
        return EntryConfidenceBand.MEDIUM
    return EntryConfidenceBand.LOW


def _resolve_calibration(calibration: object | None) -> dict[str, object]:
    resolved: dict[str, object] = {
        "source_confidence_factors": dict(_SOURCE_CONFIDENCE_FACTOR),
        "economics_cap_usd": 100.0,
        "rank_confidence_power": 1.0,
        "rank_economics_power": 1.0,
        "confidence_high_min_factor": 0.95,
        "confidence_medium_min_factor": 0.70,
    }
    if calibration is None:
        return resolved

    source_factors_raw = _cfg_get(calibration, "source_confidence_factors")
    if isinstance(source_factors_raw, Mapping):
        source_factors: dict[str, float] = dict(_SOURCE_CONFIDENCE_FACTOR)
        for key, value in source_factors_raw.items():
            parsed = _as_float(value)
            if parsed is None:
                continue
            source_factors[str(key).upper()] = max(0.0, parsed)
        resolved["source_confidence_factors"] = source_factors

    for key in (
        "economics_cap_usd",
        "rank_confidence_power",
        "rank_economics_power",
        "confidence_high_min_factor",
        "confidence_medium_min_factor",
    ):
        parsed = _as_float(_cfg_get(calibration, key))
        if parsed is not None:
            resolved[key] = parsed
    return resolved


def _cfg_get(config: object, key: str) -> object | None:
    if isinstance(config, Mapping):
        return config.get(key)
    return getattr(config, key, None)


def _fee_tier_bps(result: ScoutResult) -> int | None:
    meta = result.metadata
    from_meta = _as_int(meta.get("tick_pool_fee_tier"))
    if from_meta is not None and from_meta > 0:
        return from_meta

    raw = str(result.candidate.pool_meta or "").strip()
    if not raw:
        return None
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*%", raw)
    if not match:
        return None
    try:
        pct = float(match.group(1))
    except ValueError:
        return None
    if pct <= 0:
        return None
    return max(1, int(round(pct * 10_000.0)))


def _lp_entry_ineligible_reason(result: ScoutResult) -> str | None:
    yield_type = str(getattr(result.candidate.yield_type, "value", "") or "").lower()
    if yield_type != "lp_fees":
        return "NON_LP_YIELD_TYPE"

    project_norm = (result.candidate.project or "").lower().replace(" ", "")
    if not (
        "uniswap-v3" in project_norm
        or "uniswapv3" in project_norm
        or "aerodrome-slipstream" in project_norm
        or "aerodromeslipstream" in project_norm
        or "sushiswap-v3" in project_norm
        or "sushiswapv3" in project_norm
    ):
        return "UNSUPPORTED_ENTRY_VENUE"

    if not _has_pool_reference(result):
        return "MISSING_POOL_REFERENCE"
    return None


def _has_pool_reference(result: ScoutResult) -> bool:
    meta = result.metadata
    if _is_evm_address(meta.get("tick_pool_address")):
        return True
    address_source = str(result.candidate.address_source or "").upper()
    if address_source == "POOL" and _is_evm_address(result.candidate.address):
        return True
    # Token-pair resolver path is also a valid pool reference for tick scan:
    # runtime can resolve pool address by token0/token1 even when direct pool
    # address is not present in candidate metadata.
    token_refs: list[str] = []
    for token in list(getattr(result.candidate, "underlying_tokens", []) or []):
        if not _is_evm_address(token):
            continue
        normalized = str(token).strip().lower()
        if normalized not in token_refs:
            token_refs.append(normalized)
    if len(token_refs) >= 2:
        return True
    return False


def _is_evm_address(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return _EVM_ADDRESS_RE.fullmatch(value.strip()) is not None


def _parse_reason_codes(raw: object) -> list[str]:
    if not isinstance(raw, str) or not raw.strip():
        return []
    out: list[str] = []
    for item in raw.split(","):
        code = item.strip()
        if code and code not in out:
            out.append(code)
    return out


def _sort_key_actionable(
    item: EntryRecommendation,
) -> tuple[float, float, float, float, float, int, float, str, str, str, int, str]:
    width_ticks = 0.0
    if (
        item.suggested_range_lower_tick is not None
        and item.suggested_range_upper_tick is not None
    ):
        width_ticks = float(
            item.suggested_range_upper_tick - item.suggested_range_lower_tick
        )
    fee = item.fee_tier if item.fee_tier is not None else 10**9
    return (
        -float(item.rank_v1),
        -float(item.in_range_liquidity_competition),
        -float(item.volume_fee_proxy),
        float(item.cost_penalty),
        -float(item.confidence_score),
        -_CONFIDENCE_ORDER.get(item.confidence, 0),
        width_ticks,
        item.chain.lower(),
        item.project.lower(),
        item.pair.lower(),
        fee,
        item.source_pool_id.lower(),
    )


def _sort_key_watchlist(
    item: EntryRecommendation,
) -> tuple[str, float, str, str, str, int, str]:
    fee = item.fee_tier if item.fee_tier is not None else 10**9
    return (
        str(item.watchlist_reason or ""),
        -float(item.rank_v1),
        item.chain.lower(),
        item.project.lower(),
        item.pair.lower(),
        fee,
        item.source_pool_id.lower(),
    )


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _as_int(value: object) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def _normalize_pair_token(raw: str) -> str:
    token = raw.strip().upper()
    if token == "WETH":
        return "ETH"
    return token


def _normalize_project_name_for_target(raw: str) -> str:
    return _PROJECT_NORMALIZE_RE.sub("", str(raw).strip().lower())
