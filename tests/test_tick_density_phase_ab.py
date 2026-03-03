"""Tests for Phase A/B tick density scanner additions:
- RPC helper (slot0 fetch)
- Pit classifier (price bins, pit detection, suggested range)
- Config additions (max_scan_candidates, rpc_url_env_map)
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.lp.band_depth import tick_to_price
from defi_agents.lp.models import (
    DataQuality,
    DegradationReason,
    PitType,
    PoolState,
    TickData,
)
from defi_agents.lp.pit_classifier import (
    PitInfo,
    PriceBin,
    SuggestedRange,
    build_price_bins,
    find_liquidity_pits,
    suggest_range,
)
from defi_agents.lp.rpc_helper import fetch_slot0_tick
from defi_agents.scout.config import ScoutConfig


# --- RPC Helper Tests ---


@pytest.mark.asyncio
async def test_rpc_slot0_returns_tick_from_valid_response() -> None:
    """Mock a successful eth_call for slot0() returning a known tick value."""
    tick_value = 200408
    tick_hex = f"{tick_value:064x}"
    sqrt_price_hex = "0" * 64
    result_hex = "0x" + sqrt_price_hex + tick_hex + ("0" * 64 * 5)

    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": result_hex}

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = False

    with patch("defi_agents.lp.rpc_helper.httpx.AsyncClient", return_value=mock_client):
        tick = await fetch_slot0_tick(
            "https://rpc.example.com", "0x1234567890abcdef1234567890abcdef12345678"
        )

    assert tick == tick_value


@pytest.mark.asyncio
async def test_rpc_slot0_negative_tick() -> None:
    """Verify negative tick (signed int24) is correctly decoded."""
    tick_value = -5000
    tick_unsigned = (1 << 256) + tick_value
    tick_hex = f"{tick_unsigned:064x}"
    sqrt_price_hex = "0" * 64
    result_hex = "0x" + sqrt_price_hex + tick_hex + ("0" * 64 * 5)

    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": result_hex}

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = False

    with patch("defi_agents.lp.rpc_helper.httpx.AsyncClient", return_value=mock_client):
        tick = await fetch_slot0_tick(
            "https://rpc.example.com", "0x1234567890abcdef1234567890abcdef12345678"
        )

    assert tick == tick_value


@pytest.mark.asyncio
async def test_rpc_slot0_timeout_returns_none() -> None:
    """Verify timeout returns None (fail-safe, no crash)."""
    import httpx

    mock_client = AsyncMock()
    mock_client.post.side_effect = httpx.TimeoutException("timeout")
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = False

    with patch("defi_agents.lp.rpc_helper.httpx.AsyncClient", return_value=mock_client):
        tick = await fetch_slot0_tick(
            "https://rpc.example.com", "0x1234567890abcdef1234567890abcdef12345678"
        )

    assert tick is None


@pytest.mark.asyncio
async def test_rpc_slot0_invalid_address_returns_none() -> None:
    """Invalid pool address → None without making any HTTP call."""
    tick = await fetch_slot0_tick("https://rpc.example.com", "not-an-address")
    assert tick is None


# --- Pit Classifier Tests ---


def _make_pool_state(tick: int = 0, fee_tier: int = 500) -> PoolState:
    return PoolState(
        pool_address="0xpool",
        tick=tick,
        liquidity=10_000_000,
        sqrt_price_x96=0,
        fee_tier=fee_tier,
        tick_spacing=10,
        token0_decimals=18,
        token1_decimals=18,
    )


def test_build_price_bins_returns_bins() -> None:
    """Verify build_price_bins produces bins with nonzero liquidity."""
    state = _make_pool_state()
    ticks = [
        TickData(tick_index=-100, liquidity_net=5_000_000, liquidity_gross=5_000_000),
        TickData(tick_index=-50, liquidity_net=2_000_000, liquidity_gross=2_000_000),
        TickData(tick_index=50, liquidity_net=-2_000_000, liquidity_gross=2_000_000),
        TickData(tick_index=100, liquidity_net=-5_000_000, liquidity_gross=5_000_000),
    ]
    bins = build_price_bins(state, ticks)
    assert len(bins) > 0
    assert any(b.liquidity_usd > 0 for b in bins)


def test_build_price_bins_empty_ticks_returns_empty() -> None:
    state = _make_pool_state()
    bins = build_price_bins(state, [])
    assert bins == []


def test_find_liquidity_pits_with_synthetic_pit() -> None:
    """Synthetic L-shaped distribution: high liquidity except near center → should detect pit."""
    state = _make_pool_state()
    # Create bins manually: high liquidity everywhere except bins -1, 0, 1
    bins = []
    for i in range(-10, 11):
        liq = 100.0 if abs(i) > 1 else 1.0  # pit at center
        bins.append(
            PriceBin(
                bin_index=i,
                lower_price=1.0 + i * 0.01,
                upper_price=1.0 + (i + 1) * 0.01,
                liquidity_usd=liq,
            )
        )

    pits = find_liquidity_pits(bins, pit_threshold=0.5, min_consecutive=3)
    assert len(pits) >= 1
    assert pits[0].pit_type == PitType.CONFIDENT_PIT


def test_find_liquidity_pits_no_pit_uniform_liquidity() -> None:
    """Uniform liquidity → no pits detected."""
    bins = [
        PriceBin(
            bin_index=i,
            lower_price=1.0 + i * 0.01,
            upper_price=1.0 + (i + 1) * 0.01,
            liquidity_usd=100.0,
        )
        for i in range(-10, 11)
    ]
    pits = find_liquidity_pits(bins, pit_threshold=0.5, min_consecutive=3)
    assert pits == []


def test_suggest_range_tick_spacing_aligned() -> None:
    """Verify suggested range boundaries are multiples of tickSpacing."""
    state = _make_pool_state(tick=0, fee_tier=3000)
    state = PoolState(
        pool_address="0xpool",
        tick=0,
        liquidity=10_000_000,
        sqrt_price_x96=0,
        fee_tier=3000,
        tick_spacing=60,
        token0_decimals=18,
        token1_decimals=18,
    )
    pit = PitInfo(
        pit_type=PitType.CONFIDENT_PIT,
        center_tick=0,
        width_ticks=3,
        distance_to_spot_pct=0.0,
        depth_ratio=0.1,
    )
    sr = suggest_range(pit, state)
    assert sr.lower_tick % 60 == 0
    assert sr.upper_tick % 60 == 0
    assert sr.upper_tick > sr.lower_tick
    assert sr.width_pct > 0


def test_suggest_range_with_volatility_keeps_valid_order() -> None:
    state = PoolState(
        pool_address="0xpool",
        tick=0,
        liquidity=10_000_000,
        sqrt_price_x96=0,
        fee_tier=500,
        tick_spacing=10,
        token0_decimals=18,
        token1_decimals=18,
    )
    pit = PitInfo(
        pit_type=PitType.CONFIDENT_PIT,
        center_tick=0,
        width_ticks=4,
        distance_to_spot_pct=0.0,
        depth_ratio=0.25,
    )
    sr = suggest_range(pit, state, daily_vol=0.03)
    assert sr.lower_tick < sr.upper_tick
    assert sr.lower_tick % 10 == 0
    assert sr.upper_tick % 10 == 0


# --- Config Tests ---


def test_tick_density_config_new_fields() -> None:
    """Verify new config fields are present and have correct defaults."""
    cfg = ScoutConfig.model_validate(
        {
            "min_tvl_usd": 100_000,
            "tick_density": {"enabled": True},
        }
    )
    assert cfg.tick_density.max_scan_candidates == 10
    assert cfg.tick_density.rpc_timeout_seconds == pytest.approx(3.0)
    assert "Ethereum" in cfg.tick_density.rpc_url_env_map
    assert "Arbitrum" in cfg.tick_density.rpc_url_env_map
    assert "Base" in cfg.tick_density.rpc_url_env_map


def test_tick_density_config_custom_rpc_env() -> None:
    """Verify custom rpc_url_env_map is accepted."""
    cfg = ScoutConfig.model_validate(
        {
            "min_tvl_usd": 100_000,
            "tick_density": {
                "enabled": True,
                "rpc_url_env_map": {"Arbitrum": "MY_ARB_RPC"},
            },
        }
    )
    assert cfg.tick_density.rpc_url_env_map == {"Arbitrum": "MY_ARB_RPC"}
