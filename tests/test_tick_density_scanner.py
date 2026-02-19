from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.lp.band_depth import scan_pool_band_depth, tick_to_price, validate_tick_freshness
from defi_agents.lp.models import DataQuality, DegradationReason, PoolState, TickData
from defi_agents.lp.tick_provider import TickProviderError, UniswapV3TickProvider
from defi_agents.scout.config import ScoutConfig


class _DummyProvider:
    def __init__(self, state: PoolState, ticks: list[TickData]) -> None:
        self._state = state
        self._ticks = ticks

    async def get_pool_state(self, pool_address: str) -> PoolState:
        return self._state

    async def get_pool_ticks(self, pool_address: str, lower: int, upper: int) -> list[TickData]:
        return self._ticks

    def protocol_fee_pct(self) -> float:
        return 0.05


def test_tick_to_price_respects_decimals() -> None:
    # tick=0 -> base price=1, only decimals delta remains
    price = tick_to_price(0, token0_decimals=18, token1_decimals=6)
    assert float(price) == pytest.approx(1_000_000_000_000.0)


def test_validate_tick_freshness_drift_and_unavailable() -> None:
    drifted = validate_tick_freshness(subgraph_tick=120, rpc_tick=100, tick_spacing=10)
    assert drifted.is_valid is False
    assert drifted.reason == DegradationReason.RPC_DRIFT_EXCEEDED

    missing = validate_tick_freshness(subgraph_tick=120, rpc_tick=None, tick_spacing=10)
    assert missing.is_valid is False
    assert missing.reason == DegradationReason.RPC_UNAVAILABLE

    ok = validate_tick_freshness(subgraph_tick=120, rpc_tick=125, tick_spacing=10)
    assert ok.is_valid is True
    assert ok.reason is None


@pytest.mark.asyncio
async def test_scan_pool_band_depth_degraded_when_no_ticks() -> None:
    state = PoolState(
        pool_address="0xpool",
        tick=0,
        liquidity=1_000_000,
        sqrt_price_x96=0,
        fee_tier=500,
        tick_spacing=10,
        token0_decimals=18,
        token1_decimals=18,
    )
    provider = _DummyProvider(state=state, ticks=[])
    result = await scan_pool_band_depth(provider, "0xpool")
    assert result.data_quality == DataQuality.DEGRADED
    assert result.degradation_reason == DegradationReason.TICK_COUNT_ZERO


@pytest.mark.asyncio
async def test_scan_pool_band_depth_returns_ok_with_monotonic_windows() -> None:
    state = PoolState(
        pool_address="0xpool",
        tick=0,
        liquidity=1_000_000,
        sqrt_price_x96=0,
        fee_tier=500,
        tick_spacing=10,
        token0_decimals=18,
        token1_decimals=18,
    )
    ticks = [
        TickData(tick_index=-500, liquidity_net=0, liquidity_gross=1000),
        TickData(tick_index=-250, liquidity_net=0, liquidity_gross=1000),
        TickData(tick_index=250, liquidity_net=0, liquidity_gross=1000),
        TickData(tick_index=500, liquidity_net=0, liquidity_gross=1000),
    ]
    provider = _DummyProvider(state=state, ticks=ticks)
    result = await scan_pool_band_depth(provider, "0xpool", rpc_tick=0, enforce_rpc_check=True)
    assert result.data_quality == DataQuality.OK
    assert result.degradation_reason is None
    assert result.band_depth_5pct_usd > result.band_depth_2_5pct_usd > result.band_depth_1pct_usd > 0


@pytest.mark.asyncio
async def test_uniswap_provider_pagination_limit_raises() -> None:
    provider = UniswapV3TickProvider(
        endpoint="https://example.com/graphql",
        retry_attempts=0,
        max_pages_per_pool=2,
        max_ticks_per_pool=10_000,
    )

    async def _fake_query(payload: dict) -> dict:
        last_tick = int(payload["variables"]["lastTick"])
        rows = []
        for idx in range(1000):
            rows.append(
                {
                    "tickIdx": str(last_tick + idx + 1),
                    "liquidityNet": "1",
                    "liquidityGross": "2",
                }
            )
        return {"ticks": rows}

    provider._query = _fake_query  # type: ignore[method-assign]

    with pytest.raises(TickProviderError) as exc_info:
        await provider.get_pool_ticks("0x1111111111111111111111111111111111111111", -100, 100)
    assert exc_info.value.reason == DegradationReason.PAGINATION_LIMIT_REACHED


@pytest.mark.asyncio
async def test_uniswap_provider_pool_state_parses_and_maps_tick_spacing() -> None:
    provider = UniswapV3TickProvider(endpoint="https://example.com/graphql", retry_attempts=0)

    async def _fake_query(payload: dict) -> dict:
        return {
            "pool": {
                "id": "0xabc",
                "tick": "123",
                "liquidity": "999999",
                "sqrtPrice": "123456789",
                "feeTier": "3000",
                "token0": {"decimals": "18"},
                "token1": {"decimals": "6"},
            }
        }

    provider._query = _fake_query  # type: ignore[method-assign]
    state = await provider.get_pool_state("0xabc")
    assert state.tick == 123
    assert state.liquidity == 999999
    assert state.tick_spacing == 60
    assert state.token0_decimals == 18
    assert state.token1_decimals == 6
    assert provider.protocol_fee_pct() == pytest.approx(0.3)


def test_scout_config_includes_tick_density_block() -> None:
    cfg = ScoutConfig.model_validate(
        {
            "min_tvl_usd": 100_000,
            "tick_density": {
                "enabled": True,
                "max_pages_per_pool": 10,
                "max_ticks_per_pool": 1000,
            },
        }
    )
    assert cfg.tick_density.enabled is True
    assert cfg.tick_density.max_pages_per_pool == 10
    assert cfg.tick_density.max_ticks_per_pool == 1000
