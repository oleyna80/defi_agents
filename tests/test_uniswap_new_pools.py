import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.scout.config import ScoutConfig
from defi_agents.scout.uniswap_v3_new_pools import UniswapV3NewPoolsAdapter


def _run(coro):
    import asyncio

    return asyncio.run(coro)


def test_uniswap_new_pools_adapter_disabled_returns_empty():
    cfg = ScoutConfig(dex_discovery={"uniswap_v3_new_pools": {"enabled": False}})
    adapter = UniswapV3NewPoolsAdapter(cfg)
    result = _run(adapter.fetch_new_pools(["Ethereum"]))

    assert result.candidates == []
    assert result.metadata_by_pool_id == {}
    assert result.stats.dex_uniswap_new_count == 0


def test_uniswap_new_pools_adapter_filters_by_tvl_and_maps_metadata(monkeypatch):
    cfg = ScoutConfig(
        dex_discovery={
            "uniswap_v3_new_pools": {
                "enabled": True,
                "min_tvl_usd": 100_000,
                "max_pools": 10,
                "subgraph_endpoints": {"Ethereum": "https://example.com/graphql"},
            }
        }
    )
    adapter = UniswapV3NewPoolsAdapter(cfg)

    async def fake_fetch(_endpoint):
        return [
            {
                "id": "0x1111111111111111111111111111111111111111",
                "createdAtTimestamp": "1700000000",
                "totalValueLockedUSD": "150000",
                "token0": {"symbol": "USDC"},
                "token1": {"symbol": "USDT"},
            },
            {
                "id": "0x2222222222222222222222222222222222222222",
                "createdAtTimestamp": "1700000000",
                "totalValueLockedUSD": "50000",
                "token0": {"symbol": "DAI"},
                "token1": {"symbol": "USDC"},
            },
        ]

    monkeypatch.setattr(adapter, "_fetch_chain_rows", fake_fetch)
    result = _run(adapter.fetch_new_pools(["Ethereum"]))

    assert len(result.candidates) == 1
    c = result.candidates[0]
    assert c.pool_id == "0x1111111111111111111111111111111111111111"
    assert c.symbol == "USDC-USDT"
    meta = result.metadata_by_pool_id[c.pool_id]
    assert meta["dex_new_pool"] == "true"
    assert meta["freshness_status"] == "UNVERIFIED"
    assert meta["source_timestamp"]
    assert meta["pool_age_minutes"]
    assert result.stats.dex_filtered_count == 1
    assert result.stats.dex_uniswap_new_count == 1


def test_uniswap_new_pools_adapter_fail_safe_timeout(monkeypatch):
    cfg = ScoutConfig(
        dex_discovery={
            "uniswap_v3_new_pools": {
                "enabled": True,
                "subgraph_endpoints": {"Ethereum": "https://example.com/graphql"},
            }
        }
    )
    adapter = UniswapV3NewPoolsAdapter(cfg)

    async def raise_timeout(_endpoint):
        raise httpx.TimeoutException("timeout")

    monkeypatch.setattr(adapter, "_fetch_chain_rows", raise_timeout)
    result = _run(adapter.fetch_new_pools(["Ethereum"]))

    assert result.candidates == []
    assert result.stats.dex_timeout_count == 1
    assert result.stats.dex_error_count == 0


def test_sanitize_endpoint_masks_graph_key():
    endpoint = "https://gateway.thegraph.com/api/abc123SECRET/subgraphs/id/QmTest"
    masked = UniswapV3NewPoolsAdapter._sanitize_endpoint(endpoint)
    assert masked == "https://gateway.thegraph.com/api/***/subgraphs/id/QmTest"
