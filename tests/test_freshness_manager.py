import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.freshness.manager import FreshnessManager
from defi_agents.freshness.types import FreshnessSnapshot
from defi_agents.scout.config import FreshnessConfig
from defi_agents.scout.models import PriorityTier, ScoutCandidate, ScoutResult
from defi_agents.security.models import SecurityResult, SecurityStatus


class _MockAdapter:
    name = "mock_freshness"

    def __init__(self) -> None:
        self.calls = 0

    def supports(self, result: ScoutResult) -> bool:
        return "uniswap" in (result.candidate.project or "")

    async def fetch_snapshot(self, result: ScoutResult) -> FreshnessSnapshot | None:
        self.calls += 1
        return FreshnessSnapshot(
            provider=self.name,
            source_timestamp=datetime.now(timezone.utc),
            apy=12.0,
            tvl_usd=2_000_000.0,
        )


def _res(project: str, score: float, apy: float, tvl: float) -> ScoutResult:
    candidate = ScoutCandidate.model_validate(
        {
            "pool": f"pool-{project}-{score}",
            "project": project,
            "chain": "Ethereum",
            "symbol": "USDC-USDT",
            "address": "0x1111111111111111111111111111111111111111",
            "chain_id": 1,
            "tvlUsd": tvl,
            "apy": apy,
            "apyBase": apy,
            "apyReward": 0.0,
        }
    )
    return ScoutResult(
        candidate=candidate,
        security=SecurityResult(status=SecurityStatus.WARN, score=70),
        net_apy=apy,
        score=score,
        net_profit_usd=10.0,
        priority=PriorityTier.COIN_STABLE,
        metadata={},
        flags=[],
    )


@pytest.mark.asyncio
async def test_recheck_respects_max_candidates_and_supports_filter():
    cfg = FreshnessConfig(recheck_enabled=True, recheck_max_candidates=1, max_age_minutes=90)
    adapter = _MockAdapter()
    manager = FreshnessManager(cfg, adapters=[adapter])

    results = [
        _res("uniswap-v3", 9.0, 10.0, 2_200_000.0),
        _res("uniswap-v3", 8.0, 9.5, 2_400_000.0),
        _res("aerodrome-slipstream", 10.0, 20.0, 1_500_000.0),
    ]
    await manager.recheck(results)

    # Highest score is aerodrome, but adapter does not support it.
    # Next in sorted top-1 window is still aerodrome => zero calls in this specific setup.
    assert adapter.calls == 0

    cfg2 = FreshnessConfig(recheck_enabled=True, recheck_max_candidates=2, max_age_minutes=90)
    manager2 = FreshnessManager(cfg2, adapters=[adapter])
    await manager2.recheck(results)
    assert adapter.calls == 1
    assert results[0].metadata["freshness_provider"] == "mock_freshness"
    assert results[0].metadata["freshness_status"] == "FRESH"


@pytest.mark.asyncio
async def test_recheck_populates_divergence_fields():
    cfg = FreshnessConfig(recheck_enabled=True, recheck_max_candidates=3, max_age_minutes=90)
    adapter = _MockAdapter()
    manager = FreshnessManager(cfg, adapters=[adapter])
    result = _res("uniswap-v3", 10.0, 9.0, 1_800_000.0)
    await manager.recheck([result])

    assert result.metadata["freshness_status"] == "FRESH"
    assert float(result.metadata["apy_divergence_pct"]) > 0
    assert float(result.metadata["tvl_divergence_pct"]) > 0
