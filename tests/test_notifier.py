import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.notifier import TelegramNotifier
from defi_agents.scout.models import PriorityTier, ScoutCandidate, ScoutResult
from defi_agents.security.models import SecurityResult, SecurityStatus


def _result(
    *,
    priority: PriorityTier,
    bucket: str,
    reasons: str = "",
    symbol: str = "USDC-USDT",
    chain: str = "Ethereum",
    apy: float = 10.0,
) -> ScoutResult:
    candidate = ScoutCandidate.model_validate(
        {
            "pool": "pool1",
            "project": "demo",
            "chain": chain,
            "symbol": symbol,
            "address": "0x1111111111111111111111111111111111111111",
            "chain_id": 1,
            "tvlUsd": 10_000_000,
            "apy": apy,
            "apyBase": apy,
            "apyReward": 0.0,
        }
    )
    return ScoutResult(
        candidate=candidate,
        security=SecurityResult(status=SecurityStatus.WARN, score=70),
        net_apy=apy,
        score=5.0,
        net_profit_usd=15.0,
        priority=priority,
        metadata={
            "bucket": bucket,
            "sleeve": "yield_plus",
            "net_profit_1k_usd": "7.50",
            "warn_reasons": reasons,
        },
        flags=[],
    )


def test_report_sorts_by_pair_categories():
    notifier = TelegramNotifier()
    message = notifier._format_report(
        [
            _result(priority=PriorityTier.COIN_COIN, bucket="WARN/SECURITY", symbol="WETH-WBTC"),
            _result(priority=PriorityTier.COIN_STABLE, bucket="WARN/REPUTATION", symbol="ETH-USDC"),
            _result(priority=PriorityTier.LOW_VOLATILITY, bucket="SAFE", symbol="USDC-USDT"),
        ]
    )
    assert message.find("1) Stable/Stable") < message.find("2) Token/Stable") < message.find("3) Token/Token")


def test_report_includes_decision_fields_and_colors():
    notifier = TelegramNotifier()
    message = notifier._format_report(
        [
            _result(
                priority=PriorityTier.COIN_STABLE,
                bucket="WARN/REPUTATION",
                reasons="REPUTATION_UNAVAILABLE",
                apy=12.34,
            )
        ]
    )
    assert "🟡" in message
    assert "APY 12.34%" in message
    assert "TVL $10.00M" in message
    assert "Risk `WARN/REPUTATION`" in message
    assert "Net@1k $7.50/mo" in message
    assert "Reasons `REPUTATION_UNAVAILABLE`" in message
