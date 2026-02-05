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
    stable_tier: str | None = None,
    pair_class: str | None = None,
    fx_exposure: str | None = None,
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
    metadata = {
        "bucket": bucket,
        "sleeve": "yield_plus",
        "net_profit_1k_usd": "7.50",
        "warn_reasons": reasons,
        "freshness_status": "UNVERIFIED",
        "age_minutes": "-",
        "apy_divergence_pct": "-",
        "tvl_divergence_pct": "-",
    }
    if stable_tier is not None:
        metadata["stable_tier"] = stable_tier
    if pair_class is not None:
        metadata["pair_currency_class"] = pair_class
    if fx_exposure is not None:
        metadata["fx_exposure"] = fx_exposure
    return ScoutResult(
        candidate=candidate,
        security=SecurityResult(status=SecurityStatus.WARN, score=70),
        net_apy=apy,
        score=5.0,
        net_profit_usd=15.0,
        priority=priority,
        metadata=metadata,
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
    assert "Fresh `UNVERIFIED`" in message
    assert "Net@1k $7.50/mo" in message
    assert "Reasons `REPUTATION_UNAVAILABLE`" in message
    assert "[Pool](https://defillama.com/yields/pool/pool1)" in message


def test_report_is_chunked_for_telegram_limits():
    notifier = TelegramNotifier()
    many = [
        _result(priority=PriorityTier.COIN_STABLE, bucket="WARN/REPUTATION", symbol=f"T{i}-USDC", apy=10.0 + i)
        for i in range(80)
    ]
    message = notifier._format_report(many)
    chunks = notifier._chunk_message(message, max_len=700)
    assert len(chunks) > 1
    assert all(len(chunk) <= 700 for chunk in chunks)


def test_tags_included_when_flag_enabled():
    notifier = TelegramNotifier(include_tags=True)
    message = notifier._format_report([
        _result(
            priority=PriorityTier.LOW_VOLATILITY,
            bucket="SAFE",
            stable_tier="T1",
            pair_class="USD_STABLE_STABLE",
            fx_exposure="false",
        )
    ])
    assert "Tier:T1" in message
    assert "Class:USD_STABLE_STABLE" in message
    assert "FX_RISK" not in message
    # Ensure tags appear after Risk
    assert "Risk `SAFE` | Tags Tier:T1 Class:USD_STABLE_STABLE" in message


def test_fx_risk_tag_included():
    notifier = TelegramNotifier(include_tags=True)
    message = notifier._format_report([
        _result(
            priority=PriorityTier.COIN_STABLE,
            bucket="WARN/REPUTATION",
            stable_tier="T2",
            pair_class="FX_STABLE",
            fx_exposure="true",
        )
    ])
    assert "Tier:T2" in message
    assert "Class:FX_STABLE" in message
    assert "FX_RISK" in message
    assert "Risk `WARN/REPUTATION` | Tags Tier:T2 Class:FX_STABLE FX_RISK" in message


def test_tags_not_included_when_flag_disabled():
    notifier = TelegramNotifier(include_tags=False)
    message = notifier._format_report([
        _result(
            priority=PriorityTier.LOW_VOLATILITY,
            bucket="SAFE",
            stable_tier="T1",
            pair_class="USD_STABLE_STABLE",
            fx_exposure="false",
        )
    ])
    assert "Tier:T1" not in message
    assert "Class:USD_STABLE_STABLE" not in message
    assert "FX_RISK" not in message
    # Ensure the "Tags" substring does not appear
    assert "Tags" not in message
