from __future__ import annotations

import math
from collections.abc import Mapping

from ..scout.models import ScoutResult

_SOURCE_CONFIDENCE_FACTOR: dict[str, float] = {
    "VERIFIED": 1.0,
    "AGGREGATOR_ONLY": 0.85,
    "DIVERGED": 0.25,
    "STALE": 0.15,
}


def normalize_range_mode(raw: object) -> str:
    value = str(raw or "").strip().upper()
    if value in {"SYMMETRIC", "ASYMMETRIC", "AUTO"}:
        return value
    return "AUTO"


def normalize_market_regime(raw: object) -> str:
    value = str(raw or "").strip().upper()
    if value in {"SIDEWAYS", "UPTREND", "DOWNTREND"}:
        return value
    return "SIDEWAYS"


def resolve_selector_range(
    *,
    base_lower_tick: int | None,
    base_upper_tick: int | None,
    range_mode: str,
    market_regime: str,
    manual_lower_tick: int | None,
    manual_upper_tick: int | None,
) -> tuple[int | None, int | None, str]:
    """Resolve comparison range used by cross-protocol selector.

    Priority:
    1) explicit manual range from config,
    2) derived from scanner suggestion + range mode / regime.
    """
    mode = normalize_range_mode(range_mode)
    regime = normalize_market_regime(market_regime)

    if manual_lower_tick is not None and manual_upper_tick is not None:
        return int(manual_lower_tick), int(manual_upper_tick), mode

    if base_lower_tick is None and base_upper_tick is None:
        return None, None, mode
    if base_lower_tick is None or base_upper_tick is None:
        return base_lower_tick, base_upper_tick, mode
    if int(base_lower_tick) >= int(base_upper_tick):
        return int(base_lower_tick), int(base_upper_tick), mode

    lower = int(base_lower_tick)
    upper = int(base_upper_tick)
    width = upper - lower
    center = lower + (width / 2.0)

    effective_mode = mode
    if mode == "AUTO":
        effective_mode = "ASYMMETRIC" if regime in {"UPTREND", "DOWNTREND"} else "SYMMETRIC"

    if effective_mode == "SYMMETRIC":
        width_factor = 1.0
        if regime in {"UPTREND", "DOWNTREND"}:
            width_factor = 0.9
        half = max(1.0, (width * width_factor) / 2.0)
        out_lower = int(round(center - half))
        out_upper = int(round(center + half))
        return out_lower, out_upper, effective_mode

    # ASYMMETRIC mode
    if regime == "UPTREND":
        lower_share, upper_share = 0.40, 0.60
    elif regime == "DOWNTREND":
        lower_share, upper_share = 0.60, 0.40
    else:
        lower_share, upper_share = 0.50, 0.50

    out_lower = int(round(center - (width * lower_share)))
    out_upper = int(round(center + (width * upper_share)))
    return out_lower, out_upper, effective_mode


def compute_rank_v1_components(
    *,
    result: ScoutResult,
    source_confidence: str,
    confidence_factor: float | None,
    tick_quality: str,
    has_valid_range: bool,
    range_lower_tick: int | None,
    range_upper_tick: int | None,
    fee_tier: int | None,
) -> dict[str, float]:
    meta = result.metadata

    band_depth = _as_float(meta.get("band_depth_2_5pct_usd"))
    if band_depth is None:
        band_depth = _as_float(meta.get("band_depth_1pct_usd"))
    if band_depth is None:
        band_depth = 0.0
    in_range_liquidity_competition = 1.0 / (1.0 + math.log10(1.0 + max(0.0, float(band_depth))))

    volume_24h = _as_float(meta.get("volume_24h_usd"))
    if volume_24h is None and isinstance(result.candidate.volume_24h_usd, (int, float)):
        volume_24h = float(result.candidate.volume_24h_usd)
    if volume_24h is None:
        volume_24h = 0.0
    fee_bps = int(fee_tier or 0)
    fee_rate = max(0.0, float(fee_bps) / 10_000.0)
    fee_proxy_raw = max(0.0, float(volume_24h)) * fee_rate
    volume_fee_proxy = min(1.0, math.log10(1.0 + fee_proxy_raw) / 8.0)

    net_1k = _as_float(meta.get("net_profit_1k_usd"))
    if net_1k is None:
        cost_penalty = 0.15
    elif net_1k >= 0:
        cost_penalty = max(0.0, 0.15 - min(float(net_1k), 50.0) / 500.0)
    else:
        cost_penalty = min(1.0, (abs(float(net_1k)) / 50.0) + 0.15)

    confidence = confidence_factor
    if confidence is None:
        confidence = _SOURCE_CONFIDENCE_FACTOR.get(source_confidence, 0.85)
    confidence = max(0.0, min(1.0, float(confidence)))
    if tick_quality not in {"", "OK"}:
        confidence = 0.0
    if not has_valid_range:
        confidence = 0.0
    if range_lower_tick is None or range_upper_tick is None or range_lower_tick >= range_upper_tick:
        confidence = 0.0

    return {
        "in_range_liquidity_competition": float(in_range_liquidity_competition),
        "volume_fee_proxy": float(volume_fee_proxy),
        "cost_penalty": float(cost_penalty),
        "confidence": float(confidence),
    }


def rank_v1(components: Mapping[str, float]) -> float:
    in_range = max(0.0, min(1.0, float(components.get("in_range_liquidity_competition", 0.0))))
    vol_fee = max(0.0, min(1.0, float(components.get("volume_fee_proxy", 0.0))))
    cost_penalty = max(0.0, min(1.0, float(components.get("cost_penalty", 0.0))))
    confidence = max(0.0, min(1.0, float(components.get("confidence", 0.0))))
    score = (0.45 * in_range) + (0.35 * vol_fee) + (0.20 * confidence) - (0.30 * cost_penalty)
    return round(max(0.0, float(score)), 8)


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

