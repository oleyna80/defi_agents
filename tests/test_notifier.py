import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.notifier import TelegramNotifier
from defi_agents.scout.models import ScoutCandidate, ScoutResult
from defi_agents.security.models import SecurityResult, SecurityStatus


def _result(*, group: str, reasons: str = "") -> ScoutResult:
    candidate = ScoutCandidate.model_validate(
        {
            "pool": "pool1",
            "project": "demo",
            "chain": "Ethereum",
            "symbol": "USDC-USDT",
            "address": "0x1111111111111111111111111111111111111111",
            "chain_id": 1,
            "tvlUsd": 10_000_000,
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
        net_profit_usd=15.0,
        priority="COIN_STABLE",
        metadata={
            "bucket": "WARN/REPUTATION",
            "sleeve": "yield_plus",
            "above_benchmark": "true",
            "benchmark_delta_apy": "4.00",
            "report_group": group,
            "warn_reasons": reasons,
        },
        flags=[],
    )


def test_report_splits_actionable_and_watchlist_sections():
    notifier = TelegramNotifier()
    message = notifier._format_report(
        [_result(group="ACTIONABLE"), _result(group="WATCHLIST")]
    )
    assert "Actionable (Net >= Min Profit)" in message
    assert "Watchlist (Manual Review)" in message


def test_report_includes_warn_reason_codes():
    notifier = TelegramNotifier()
    message = notifier._format_report(
        [_result(group="WATCHLIST", reasons="REPUTATION_UNAVAILABLE,HIDDEN_OWNER")]
    )
    assert "Reasons `REPUTATION_UNAVAILABLE,HIDDEN_OWNER`" in message
