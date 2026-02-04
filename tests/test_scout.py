import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.scout.config import ScoutConfig
from defi_agents.scout.cache import ScoutDeduper
from defi_agents.scout.models import ScoutCandidate
from defi_agents.scout.scout import YieldScout
from defi_agents.security.models import (
    SecurityReason,
    SecurityResult,
    SecuritySeverity,
    SecuritySource,
    SecurityStatus,
)


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


def _candidate(pool, chain, symbol, apy, apy_mean_30d, tvl, age_days=None):
    suffix = pool[-1] if pool and pool[-1].isdigit() else "1"
    candidate = ScoutCandidate.model_validate(
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
    candidate.contract_age_days = age_days
    return candidate


def _scout(cfg, pools, status_map):
    return YieldScout(cfg, _MockClient(pools), _MockAuditor(status_map), deduper=ScoutDeduper(ttl_seconds=0))


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
    scout = _scout(cfg, pools, status_map)
    results = _run(scout.analyze())
    assert len(results) == 1


def test_volatility_trap_filtered():
    cfg = ScoutConfig(min_tvl_usd=1, apy_anomaly_ratio=2.0)
    pools = [
        _candidate("pool1", "Base", "USDC-USDT", 100, 5, 10_000_000),
    ]
    status_map = {pools[0].address: SecurityResult.pass_as_tier1()}
    scout = _scout(cfg, pools, status_map)
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
    scout = _scout(cfg, pools, status_map)
    results = _run(scout.analyze())
    assert len(results) == 0


def test_lindy_softens_missing_audit_block():
    cfg = ScoutConfig(min_tvl_usd=1, lindy_min_tvl_usd=100_000_000, lindy_min_age_days=180)
    pool = _candidate("pool1", "Base", "USDC-USDT", 20, 18, 150_000_000, age_days=365)
    status_map = {
        pool.address: SecurityResult(
            status=SecurityStatus.BLOCK,
            score=10,
            reasons=[
                SecurityReason(
                    code="NO_TOP_TIER_AUDIT",
                    label="No top tier audit",
                    severity=SecuritySeverity.MEDIUM,
                    source=SecuritySource.DEFI_REPUTATION,
                )
            ],
            sources=[],
        )
    }
    scout = _scout(cfg, [pool], status_map)
    results = _run(scout.analyze())
    assert len(results) == 1
    assert results[0].security.status == SecurityStatus.WARN
    assert results[0].metadata.get("lindy_softened") == "true"


def test_lindy_does_not_override_hidden_owner_block():
    cfg = ScoutConfig(min_tvl_usd=1, lindy_min_tvl_usd=100_000_000, lindy_min_age_days=180)
    pool = _candidate("pool1", "Base", "USDC-USDT", 20, 18, 150_000_000, age_days=365)
    status_map = {
        pool.address: SecurityResult(
            status=SecurityStatus.BLOCK,
            score=10,
            reasons=[
                SecurityReason(
                    code="HIDDEN_OWNER",
                    label="Owner hidden",
                    severity=SecuritySeverity.HIGH,
                    source=SecuritySource.GOPLUS,
                )
            ],
            sources=[],
        )
    }
    scout = _scout(cfg, [pool], status_map)
    results = _run(scout.analyze())
    assert len(results) == 0


def test_net_profit_uses_position_size_and_amortized_gas():
    cfg = ScoutConfig(
        min_tvl_usd=1,
        gas_efficiency={
            "position_size_usd": 2500,
            "estimated_roundtrip_gas_usd": 8,
            "holding_period_days": 45,
        },
    )
    pool = _candidate("pool1", "Base", "USDC-USDT", 12, 10, 10_000_000)
    status_map = {pool.address: SecurityResult.pass_as_tier1()}
    scout = _scout(cfg, [pool], status_map)
    results = _run(scout.analyze())
    assert len(results) == 1
    # Gross: 2500 * 12% / 12 = 25.0, Gas amortized: 8 * (30/45) = 5.333...
    assert results[0].net_profit_usd == pytest.approx(19.6666, rel=1e-3)


def _run(coro):
    import asyncio

    return asyncio.run(coro)
