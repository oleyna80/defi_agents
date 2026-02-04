import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.freshness.adapters import UniswapSubgraphAdapter
from defi_agents.scout.models import PriorityTier, ScoutCandidate, ScoutResult
from defi_agents.security.models import SecurityResult, SecurityStatus


def _result(project: str, chain: str, address: str = "0x1111111111111111111111111111111111111111") -> ScoutResult:
    candidate = ScoutCandidate.model_validate(
        {
            "pool": "pool-adapter-1",
            "project": project,
            "chain": chain,
            "symbol": "USDC-USDT",
            "address": address,
            "chain_id": 1,
            "tvlUsd": 1_000_000,
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
        net_profit_usd=10.0,
        priority=PriorityTier.COIN_STABLE,
        metadata={},
        flags=[],
    )


def test_uniswap_adapter_supports_only_uniswap_project_with_chain_endpoint():
    adapter = UniswapSubgraphAdapter({"Ethereum": "https://example.com/graphql"})
    assert adapter.supports(_result("uniswap-v3", "Ethereum")) is True
    assert adapter.supports(_result("aerodrome-slipstream", "Base")) is False


def test_uniswap_adapter_requires_endpoint_for_chain():
    adapter = UniswapSubgraphAdapter({"Ethereum": "https://example.com/graphql"})
    assert adapter.supports(_result("uniswap-v3", "Arbitrum")) is False
