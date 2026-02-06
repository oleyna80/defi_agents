import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.scout.config import ScoutConfig
from defi_agents.scout.defillama_client import DeFiLlamaClient


def _run(coro):
    import asyncio

    return asyncio.run(coro)


def test_lending_snapshot_selects_best_supply_and_lowest_borrow(monkeypatch):
    cfg = ScoutConfig(min_tvl_usd=500_000, min_apy=20.0)
    client = DeFiLlamaClient(cfg)

    async def fake_fetch():
        return [
            {
                "pool": "eth1",
                "project": "aave-v3",
                "chain": "Ethereum",
                "symbol": "WETH",
                "address": "0x1111111111111111111111111111111111111111",
                "tvlUsd": 10_000_000,
                "apy": 3.2,
                "apyBase": 3.2,
                "apyReward": 0.0,
                "apyBaseBorrow": 5.1,
                "apyRewardBorrow": 0.0,
                "totalBorrowUsd": 5_000_000,
            },
            {
                "pool": "eth2",
                "project": "morpho",
                "chain": "Base",
                "symbol": "WETH",
                "address": "0x2222222222222222222222222222222222222222",
                "tvlUsd": 8_000_000,
                "apy": 4.6,
                "apyBase": 4.6,
                "apyReward": 0.0,
                "apyBaseBorrow": 6.0,
                "apyRewardBorrow": 0.0,
                "totalBorrowUsd": 2_000_000,
            },
            {
                "pool": "btc1",
                "project": "compound-v3",
                "chain": "Arbitrum",
                "symbol": "WBTC",
                "address": "0x3333333333333333333333333333333333333333",
                "tvlUsd": 6_000_000,
                "apy": 2.9,
                "apyBase": 2.9,
                "apyReward": 0.0,
                "apyBaseBorrow": 4.8,
                "apyRewardBorrow": 0.0,
                "totalBorrowUsd": 3_000_000,
            },
            {
                "pool": "usdc1",
                "project": "aave-v3",
                "chain": "Ethereum",
                "symbol": "USDC",
                "address": "0x4444444444444444444444444444444444444444",
                "tvlUsd": 12_000_000,
                "apy": 2.0,
                "apyBase": 2.0,
                "apyReward": 0.0,
                "apyBaseBorrow": 2.1,
                "apyRewardBorrow": 0.3,
                "totalBorrowUsd": 4_000_000,
            },
            {
                "pool": "dai1",
                "project": "spark",
                "chain": "Ethereum",
                "symbol": "DAI",
                "address": "0x5555555555555555555555555555555555555555",
                "tvlUsd": 9_000_000,
                "apy": 1.8,
                "apyBase": 1.8,
                "apyReward": 0.0,
                "apyBaseBorrow": 1.2,
                "apyRewardBorrow": 0.0,
                "totalBorrowUsd": 2_000_000,
            },
        ]

    monkeypatch.setattr(client, "_fetch_raw_pools", fake_fetch)

    snapshot = _run(client.get_lending_snapshot())
    assert snapshot.best_eth_supply is not None
    assert snapshot.best_eth_supply.candidate.pool_id == "eth2"
    assert snapshot.best_btc_supply is not None
    assert snapshot.best_btc_supply.candidate.pool_id == "btc1"
    assert snapshot.lowest_stable_borrow is not None
    assert snapshot.lowest_stable_borrow.candidate.pool_id == "dai1"
    assert snapshot.lowest_stable_borrow.metric_value_pct == 1.2


def test_get_pools_still_applies_min_apy_filter(monkeypatch):
    cfg = ScoutConfig(min_tvl_usd=500_000, min_apy=8.0)
    client = DeFiLlamaClient(cfg)

    async def fake_fetch():
        return [
            {
                "pool": "low",
                "project": "aave-v3",
                "chain": "Ethereum",
                "symbol": "WETH",
                "address": "0x1111111111111111111111111111111111111111",
                "tvlUsd": 10_000_000,
                "apy": 3.0,
                "apyBase": 3.0,
                "apyReward": 0.0,
            },
            {
                "pool": "high",
                "project": "aave-v3",
                "chain": "Ethereum",
                "symbol": "WETH",
                "address": "0x2222222222222222222222222222222222222222",
                "tvlUsd": 10_000_000,
                "apy": 9.0,
                "apyBase": 9.0,
                "apyReward": 0.0,
            },
        ]

    monkeypatch.setattr(client, "_fetch_raw_pools", fake_fetch)
    pools = _run(client.get_pools())
    assert len(pools) == 1
    assert pools[0].pool_id == "high"
