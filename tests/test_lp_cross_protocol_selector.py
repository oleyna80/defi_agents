from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.lp.cross_protocol_selector import (  # noqa: E402
    compute_rank_v1_components,
    rank_v1,
    resolve_selector_range,
)
from defi_agents.scout.models import (  # noqa: E402
    PriorityTier,
    ScoutCandidate,
    ScoutResult,
)
from defi_agents.security.models import SecurityResult, SecurityStatus  # noqa: E402


def _result(*, band_depth_2_5pct_usd: str, volume_24h_usd: float) -> ScoutResult:
    candidate = ScoutCandidate.model_validate(
        {
            "pool": "pool-1",
            "project": "uniswap-v3",
            "chain": "Base",
            "symbol": "WETH-USDT",
            "address": "0x1111111111111111111111111111111111111111",
            "chain_id": 8453,
            "tvlUsd": 2_000_000,
            "volumeUsd1d": volume_24h_usd,
            "apy": 10.0,
            "apyBase": 10.0,
            "apyReward": 0.0,
        }
    )
    return ScoutResult(
        candidate=candidate,
        security=SecurityResult(status=SecurityStatus.WARN, score=70),
        net_apy=10.0,
        score=5.0,
        net_profit_usd=15.0,
        priority=PriorityTier.COIN_STABLE,
        metadata={
            "band_depth_2_5pct_usd": band_depth_2_5pct_usd,
            "net_profit_1k_usd": "15.0",
            "tick_pool_fee_tier": "500",
        },
        flags=[],
    )


def test_rank_v1_monotonic_for_lower_competition() -> None:
    high_competition = _result(band_depth_2_5pct_usd="500000", volume_24h_usd=1_000_000)
    low_competition = _result(band_depth_2_5pct_usd="10000", volume_24h_usd=1_000_000)

    high_components = compute_rank_v1_components(
        result=high_competition,
        source_confidence="VERIFIED",
        confidence_factor=1.0,
        tick_quality="OK",
        has_valid_range=True,
        range_lower_tick=-100,
        range_upper_tick=100,
        fee_tier=500,
    )
    low_components = compute_rank_v1_components(
        result=low_competition,
        source_confidence="VERIFIED",
        confidence_factor=1.0,
        tick_quality="OK",
        has_valid_range=True,
        range_lower_tick=-100,
        range_upper_tick=100,
        fee_tier=500,
    )

    assert low_components["in_range_liquidity_competition"] > high_components[
        "in_range_liquidity_competition"
    ]
    assert rank_v1(low_components) > rank_v1(high_components)


def test_rank_v1_is_deterministic_for_same_components() -> None:
    components = {
        "in_range_liquidity_competition": 0.42,
        "volume_fee_proxy": 0.71,
        "cost_penalty": 0.06,
        "confidence": 0.88,
    }
    first = rank_v1(components)
    second = rank_v1(components)
    assert first == pytest.approx(second, rel=0, abs=0)


def test_resolve_selector_range_auto_by_market_regime() -> None:
    lower, upper, mode = resolve_selector_range(
        base_lower_tick=-100,
        base_upper_tick=100,
        range_mode="AUTO",
        market_regime="UPTREND",
        manual_lower_tick=None,
        manual_upper_tick=None,
    )
    assert mode == "ASYMMETRIC"
    assert lower == -80
    assert upper == 120

