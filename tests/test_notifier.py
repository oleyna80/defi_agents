import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.notifier import TelegramNotifier
from defi_agents.scout.models import LendingSnapshot, LendingSnapshotItem, PriorityTier, ScoutCandidate, ScoutResult
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
    sim_status: str | None = None,
    sim_best_strategy: str | None = None,
    sim_fit_score: str | None = None,
    sim_exp_net_apy_min: str | None = None,
    sim_exp_net_apy_max: str | None = None,
    sim_risk_score: str | None = None,
    sim_required_data_missing: str | None = None,
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
    if sim_status is not None:
        metadata["sim_status"] = sim_status
    if sim_best_strategy is not None:
        metadata["sim_best_strategy"] = sim_best_strategy
    if sim_fit_score is not None:
        metadata["sim_fit_score"] = sim_fit_score
    if sim_exp_net_apy_min is not None:
        metadata["sim_exp_net_apy_min"] = sim_exp_net_apy_min
    if sim_exp_net_apy_max is not None:
        metadata["sim_exp_net_apy_max"] = sim_exp_net_apy_max
    if sim_risk_score is not None:
        metadata["sim_risk_score"] = sim_risk_score
    if sim_required_data_missing is not None:
        metadata["sim_required_data_missing"] = sim_required_data_missing
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


def test_report_includes_lending_snapshot_section():
    notifier = TelegramNotifier()
    candidate_eth = ScoutCandidate.model_validate(
        {
            "pool": "eth-market",
            "project": "aave-v3",
            "chain": "Ethereum",
            "symbol": "WETH",
            "address": "0x1111111111111111111111111111111111111111",
            "chain_id": 1,
            "tvlUsd": 20_000_000,
            "apy": 4.5,
            "apyBase": 4.5,
            "apyReward": 0.0,
        }
    )
    candidate_gho = ScoutCandidate.model_validate(
        {
            "pool": "gho-market",
            "project": "aave-v3",
            "chain": "Arbitrum",
            "symbol": "GHO",
            "address": "0x2222222222222222222222222222222222222222",
            "chain_id": 42161,
            "tvlUsd": 7_000_000,
            "apy": 5.2,
            "apyBase": 5.2,
            "apyReward": 0.0,
        }
    )
    candidate_eurc = ScoutCandidate.model_validate(
        {
            "pool": "eurc-market",
            "project": "aave-v3",
            "chain": "Base",
            "symbol": "EURC",
            "address": "0x3333333333333333333333333333333333333333",
            "chain_id": 8453,
            "tvlUsd": 5_000_000,
            "apy": 2.0,
            "apyBase": 2.0,
            "apyReward": 0.0,
            "apyBaseBorrow": 1.9,
            "apyRewardBorrow": 0.0,
        }
    )
    candidate_usdc = ScoutCandidate.model_validate(
        {
            "pool": "usdc-market",
            "project": "aave-v3",
            "chain": "Ethereum",
            "symbol": "USDC",
            "address": "0x4444444444444444444444444444444444444444",
            "chain_id": 1,
            "tvlUsd": 12_000_000,
            "apy": 2.1,
            "apyBase": 2.1,
            "apyReward": 0.0,
            "apyBaseBorrow": 2.3,
            "apyRewardBorrow": 0.0,
        }
    )
    candidate_dai = ScoutCandidate.model_validate(
        {
            "pool": "dai-market",
            "project": "spark",
            "chain": "Ethereum",
            "symbol": "DAI",
            "address": "0x5555555555555555555555555555555555555555",
            "chain_id": 1,
            "tvlUsd": 8_000_000,
            "apy": 1.9,
            "apyBase": 1.9,
            "apyReward": 0.0,
            "apyBaseBorrow": 1.7,
            "apyRewardBorrow": 0.0,
        }
    )
    snapshot = LendingSnapshot(
        best_eth_supply=LendingSnapshotItem(candidate=candidate_eth, metric_name="supply_apy", metric_value_pct=4.5),
        best_gho_supply=LendingSnapshotItem(candidate=candidate_gho, metric_name="supply_apy", metric_value_pct=5.2),
        lowest_eurc_borrow=LendingSnapshotItem(candidate=candidate_eurc, metric_name="borrow_apr", metric_value_pct=1.9),
        lowest_usdc_borrow=LendingSnapshotItem(candidate=candidate_usdc, metric_name="borrow_apr", metric_value_pct=2.3),
        lowest_borrow_by_symbol={
            "EURC": LendingSnapshotItem(candidate=candidate_eurc, metric_name="borrow_apr", metric_value_pct=1.9),
            "USDC": LendingSnapshotItem(candidate=candidate_usdc, metric_name="borrow_apr", metric_value_pct=2.3),
            "DAI": LendingSnapshotItem(candidate=candidate_dai, metric_name="borrow_apr", metric_value_pct=1.7),
        },
    )
    message = notifier._format_report([], lending_snapshot=snapshot)
    assert "Lending Snapshot" in message
    assert "Best ETH supply" in message
    assert "Supply APY 4.50%" in message
    assert "Best GHO supply" in message
    assert "Supply APY 5.20%" in message
    assert "Cheapest EURC borrow" in message
    assert "Borrow APR 1.90%" in message
    assert "Cheapest USDC borrow" in message
    assert "Borrow APR 2.30%" in message
    assert "Cheapest DAI borrow" in message
    assert "Borrow APR 1.70%" in message
    assert "Carry pre-check" in message
    assert "Spread +3.30pp" in message
    assert "[Pool](https://defillama.com/yields/pool/eth-market)" in message


def test_pool_link_uses_explorer_for_address_like_pool_id():
    notifier = TelegramNotifier()
    candidate = ScoutCandidate.model_validate(
        {
            "pool": "0x1111111111111111111111111111111111111111",
            "project": "Uniswap V3",
            "chain": "Base",
            "symbol": "USDC-USDT",
            "address": "0x2222222222222222222222222222222222222222",
            "chain_id": 8453,
            "tvlUsd": 1_000_000,
            "apy": 10.0,
            "apyBase": 10.0,
            "apyReward": 0.0,
        }
    )
    result = ScoutResult(
        candidate=candidate,
        security=SecurityResult(status=SecurityStatus.WARN, score=70),
        net_apy=10.0,
        score=5.0,
        net_profit_usd=15.0,
        priority=PriorityTier.LOW_VOLATILITY,
        metadata={
            "bucket": "WARN/REPUTATION",
            "sleeve": "yield_plus",
            "net_profit_1k_usd": "7.50",
            "warn_reasons": "REPUTATION_UNAVAILABLE",
            "freshness_status": "UNVERIFIED",
            "age_minutes": "-",
            "apy_divergence_pct": "-",
            "tvl_divergence_pct": "-",
        },
        flags=[],
    )
    assert notifier._pool_link(result) == "https://basescan.org/address/0x1111111111111111111111111111111111111111"


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


def test_strategy_fields_hidden_when_not_ok():
    notifier = TelegramNotifier()
    message = notifier._format_report([
        _result(
            priority=PriorityTier.COIN_COIN,
            bucket="WARN/REPUTATION",
            symbol="WETH-AERO",
            sim_status="PARTIAL",
            sim_best_strategy="clmm_range_harvest",
            sim_fit_score="0",
            sim_exp_net_apy_min="0.00",
            sim_exp_net_apy_max="0.00",
            sim_risk_score="100",
            sim_required_data_missing="volume24h,fees24h",
        )
    ])
    assert "BestStrategy" not in message
    assert "SimStatus" not in message
    assert "FitScore" not in message
    assert "ExpNetAPY" not in message
    assert "SimRisk" not in message
    assert "MissingData" not in message


def test_strategy_fields_visible_when_ok():
    notifier = TelegramNotifier()
    message = notifier._format_report([
        _result(
            priority=PriorityTier.COIN_COIN,
            bucket="WARN/REPUTATION",
            symbol="WETH-AERO",
            sim_status="OK",
            sim_best_strategy="clmm_range_harvest",
            sim_fit_score="42",
            sim_exp_net_apy_min="5.00",
            sim_exp_net_apy_max="9.00",
            sim_risk_score="25",
        )
    ])
    assert "BestStrategy:clmm_range_harvest" in message
    assert "SimStatus:OK" in message
    assert "FitScore:42" in message
    assert "ExpNetAPY:5.00-9.00%" in message
    assert "SimRisk:25" in message
