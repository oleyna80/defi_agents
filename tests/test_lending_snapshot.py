import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.scout.config import ScoutConfig
from defi_agents.scout.defillama_client import DeFiLlamaClient
from defi_agents.scout.models import YieldType


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
                "pool": "eth-dex",
                "project": "sparkdex-v3.1",
                "chain": "Flare",
                "symbol": "WETH-USDT0",
                "address": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "tvlUsd": 650_000,
                "apy": 33.5,
                "apyBase": 33.5,
                "apyReward": 0.0,
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
                "pool": "btc-dex",
                "project": "morpho-v1",
                "chain": "Katana",
                "symbol": "YOG-WBTC",
                "address": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                "tvlUsd": 3_940_000,
                "apy": 0.04,
                "apyBase": 0.04,
                "apyReward": 0.0,
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
                "pool": "eurc1",
                "project": "aave-v3",
                "chain": "Base",
                "symbol": "EURC",
                "address": "0x6666666666666666666666666666666666666666",
                "tvlUsd": 5_000_000,
                "apy": 2.1,
                "apyBase": 2.1,
                "apyReward": 0.0,
                "apyBaseBorrow": 1.8,
                "apyRewardBorrow": 0.0,
                "totalBorrowUsd": 1_500_000,
            },
            {
                "pool": "gho1",
                "project": "aave-v3",
                "chain": "Arbitrum",
                "symbol": "GHO",
                "address": "0x7777777777777777777777777777777777777777",
                "tvlUsd": 7_000_000,
                "apy": 5.1,
                "apyBase": 5.1,
                "apyReward": 0.0,
                "apyBaseBorrow": 7.0,
                "apyRewardBorrow": 0.0,
                "totalBorrowUsd": 1_000_000,
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
    assert snapshot.best_gho_supply is not None
    assert snapshot.best_gho_supply.candidate.pool_id == "gho1"
    assert snapshot.lowest_stable_borrow is not None
    assert snapshot.lowest_stable_borrow.candidate.pool_id == "dai1"
    assert snapshot.lowest_stable_borrow.metric_value_pct == 1.2
    assert snapshot.lowest_eurc_borrow is not None
    assert snapshot.lowest_eurc_borrow.candidate.pool_id == "eurc1"
    assert snapshot.lowest_eurc_borrow.metric_value_pct == 1.8
    assert snapshot.lowest_usdc_borrow is not None
    assert snapshot.lowest_usdc_borrow.candidate.pool_id == "usdc1"
    assert snapshot.lowest_usdc_borrow.metric_value_pct == 2.4
    assert snapshot.lowest_borrow_by_symbol["DAI"].candidate.pool_id == "dai1"
    assert snapshot.lowest_borrow_by_symbol["USDC"].candidate.pool_id == "usdc1"
    assert snapshot.lowest_borrow_by_symbol["EURC"].candidate.pool_id == "eurc1"


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


def test_directional_snapshot_uses_independent_criteria(monkeypatch):
    cfg = ScoutConfig(min_tvl_usd=500_000, min_apy=20.0)
    cfg.reporting.telegram_directional_top_n = 10
    cfg.reporting.telegram_directional_lp_min_tvl_usd = 100_000
    cfg.reporting.telegram_directional_lp_min_vol_to_tvl = 1.0
    cfg.reporting.telegram_directional_lending_min_tvl_usd = 100_000
    cfg.reporting.telegram_directional_staking_min_tvl_usd = 100_000
    cfg.reporting.telegram_directional_staking_min_apy = 3.0
    cfg.reporting.telegram_directional_borrow_symbols = ["USDC", "USDT", "EURC"]
    client = DeFiLlamaClient(cfg)

    async def fake_fetch():
        return [
            {
                "pool": "lp-high-turnover",
                "project": "aerodrome-slipstream",
                "chain": "Base",
                "symbol": "WETH-USDC",
                "address": "0x1111111111111111111111111111111111111111",
                "tvlUsd": 150_000,
                "volumeUsd1d": 2_400_000,
                "apy": 1.1,
                "apyBase": 1.1,
                "apyReward": 0.0,
            },
            {
                "pool": "supply-eth",
                "project": "aave-v3",
                "chain": "Ethereum",
                "symbol": "WETH",
                "address": "0x2222222222222222222222222222222222222222",
                "tvlUsd": 5_000_000,
                "apy": 2.8,
                "apyBase": 2.8,
                "apyReward": 0.0,
                "apyBaseBorrow": 5.0,
                "apyRewardBorrow": 0.0,
            },
            {
                "pool": "borrow-usdc-cheap",
                "project": "aave-v3",
                "chain": "Base",
                "symbol": "USDC",
                "address": "0x3333333333333333333333333333333333333333",
                "tvlUsd": 8_000_000,
                "apy": 1.8,
                "apyBase": 1.8,
                "apyReward": 0.0,
                "apyBaseBorrow": 1.2,
                "apyRewardBorrow": 0.1,
                "totalBorrowUsd": 2_000_000,
            },
            {
                "pool": "borrow-usdt-expensive",
                "project": "aave-v3",
                "chain": "Arbitrum",
                "symbol": "USDT",
                "address": "0x4444444444444444444444444444444444444444",
                "tvlUsd": 7_000_000,
                "apy": 1.7,
                "apyBase": 1.7,
                "apyReward": 0.0,
                "apyBaseBorrow": 2.0,
                "apyRewardBorrow": 0.0,
                "totalBorrowUsd": 1_500_000,
            },
            {
                "pool": "staking-wsteth",
                "project": "lido",
                "chain": "Ethereum",
                "symbol": "WSTETH",
                "address": "0x5555555555555555555555555555555555555555",
                "tvlUsd": 12_000_000,
                "apy": 4.1,
                "apyBase": 4.1,
                "apyReward": 0.0,
            },
        ]

    monkeypatch.setattr(client, "_fetch_raw_pools", fake_fetch)

    snapshot = _run(client.get_directional_snapshot())
    assert snapshot.has_any()
    assert snapshot.lp_top and snapshot.lp_top[0].candidate.pool_id == "lp-high-turnover"
    assert snapshot.lending_supply_top and snapshot.lending_supply_top[0].candidate.pool_id == "supply-eth"
    assert snapshot.lending_borrow_top and snapshot.lending_borrow_top[0].candidate.pool_id == "borrow-usdc-cheap"
    assert snapshot.staking_top and snapshot.staking_top[0].candidate.pool_id == "staking-wsteth"


def test_candidate_yield_type_classification_ssot():
    cfg = ScoutConfig(min_tvl_usd=100_000, min_apy=0.0)
    client = DeFiLlamaClient(cfg)
    pools = [
        {
            "pool": "lp-1",
            "project": "uniswap-v3",
            "chain": "Ethereum",
            "symbol": "WETH-USDC",
            "tvlUsd": 2_000_000,
            "apy": 7.0,
            "apyBase": 7.0,
            "apyReward": 0.0,
        },
        {
            "pool": "lend-1",
            "project": "aave-v3",
            "chain": "Ethereum",
            "symbol": "USDC",
            "tvlUsd": 9_000_000,
            "apy": 2.0,
            "apyBase": 2.0,
            "apyReward": 0.0,
            "apyBaseBorrow": 3.1,
            "apyRewardBorrow": 0.0,
        },
        {
            "pool": "stake-1",
            "project": "lido",
            "chain": "Ethereum",
            "symbol": "WSTETH",
            "tvlUsd": 15_000_000,
            "apy": 4.0,
            "apyBase": 4.0,
            "apyReward": 0.0,
        },
    ]
    candidates = client._build_reporting_candidates(pools, min_tvl_floor=0.0)
    by_pool = {candidate.pool_id: candidate.yield_type for candidate in candidates}
    assert by_pool["lp-1"] == YieldType.LP_FEES
    assert by_pool["lend-1"] == YieldType.LENDING_SUPPLY
    assert by_pool["stake-1"] == YieldType.STAKING
