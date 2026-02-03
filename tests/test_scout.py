import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.scout.config import ScoutConfig
from defi_agents.scout.models import ScoutCandidate
from defi_agents.scout.scout import YieldScout
from defi_agents.security.models import SecurityResult, SecurityStatus


class _MockClient:
    def __init__(self, pools):
        self._pools = pools

    async def get_pools(self):
        return self._pools


class _MockAuditor:
    def __init__(self, status_map):
        self._status_map = status_map

    async def evaluate(self, address, chain_id):
        return self._status_map[address]


def _candidate(pool, chain, symbol, apy, apy_mean_30d, tvl):
    suffix = pool[-1] if pool and pool[-1].isdigit() else "1"
    return ScoutCandidate.model_validate(
        {
            "pool": pool,
            "project": "dex",
            "chain": chain,
            "symbol": symbol,
            "address": "0x" + (suffix * 40),
            "chain_id": 8453,
            "tvlUsd": tvl,
            "apy": apy,
            "apyBase": apy,
            "apyReward": 0.0,
            "apyMean30d": apy_mean_30d,
        }
    )


def test_aggregator_dedup():
    cfg = ScoutConfig(min_tvl_usd=1)
    pools = [
        _candidate("pool1", "Base", "USDC-USDT", 12, 10, 10_000_000),
        _candidate("pool2", "Base", "USDT-USDC", 10, 9, 12_000_000),
    ]
    status_map = {
        pools[0].address: SecurityResult.pass_as_tier1(),
        pools[1].address: SecurityResult.pass_as_tier1(),
    }
    scout = YieldScout(cfg, _MockClient(pools), _MockAuditor(status_map))
    results = _run(scout.analyze())
    assert len(results) == 1


def test_volatility_trap_filtered():
    cfg = ScoutConfig(min_tvl_usd=1, apy_anomaly_ratio=2.0)
    pools = [
        _candidate("pool1", "Base", "USDC-USDT", 100, 5, 10_000_000),
    ]
    status_map = {pools[0].address: SecurityResult.pass_as_tier1()}
    scout = YieldScout(cfg, _MockClient(pools), _MockAuditor(status_map))
    results = _run(scout.analyze())
    assert len(results) == 0


def test_security_block_excluded():
    cfg = ScoutConfig(min_tvl_usd=1)
    pools = [
        _candidate("pool1", "Base", "USDC-USDT", 20, 18, 10_000_000),
    ]
    status_map = {
        pools[0].address: SecurityResult(status=SecurityStatus.BLOCK, score=0, reasons=[], sources=[])
    }
    scout = YieldScout(cfg, _MockClient(pools), _MockAuditor(status_map))
    results = _run(scout.analyze())
    assert len(results) == 0


def _run(coro):
    import asyncio

    return asyncio.run(coro)
