import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.notifier import TelegramNotifier
from defi_agents.lp.models import (
    EntryActionability,
    EntryConfidenceBand,
    EntryRecommendation,
)
from defi_agents.scout.models import (
    LendingSnapshot,
    LendingSnapshotItem,
    MonitoredPoolSnapshot,
    MyPoolsMonitorReport,
    PoolHealthTag,
    PriorityTier,
    ScoutCandidate,
    ScoutResult,
    SourceConfidence,
    YieldDirectionSnapshot,
)
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
    volume_24h_usd: float | None = None,
    metadata_overrides: dict[str, str] | None = None,
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
            "volumeUsd1d": volume_24h_usd,
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
    if metadata_overrides:
        metadata.update(metadata_overrides)
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
            _result(
                priority=PriorityTier.COIN_COIN,
                bucket="WARN/SECURITY",
                symbol="WETH-WBTC",
            ),
            _result(
                priority=PriorityTier.COIN_STABLE,
                bucket="WARN/REPUTATION",
                symbol="ETH-USDC",
            ),
            _result(
                priority=PriorityTier.LOW_VOLATILITY, bucket="SAFE", symbol="USDC-USDT"
            ),
        ]
    )
    assert (
        message.find("1) Stable/Stable")
        < message.find("2) Token/Stable")
        < message.find("3) Token/Token")
    )


def test_notifier_uses_custom_chat_id_env(monkeypatch):
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("CHAT_ID", raising=False)
    monkeypatch.setenv("TELEGRAM_SHADOW_CHAT_ID", "shadow-chat")
    notifier = TelegramNotifier(chat_id_env="TELEGRAM_SHADOW_CHAT_ID")
    assert notifier.chat_id == "shadow-chat"


def test_notifier_prefix_applied_once():
    notifier = TelegramNotifier(message_prefix="⚠️ SHADOW — DO NOT ACT")
    out = notifier._with_prefix("hello")
    assert out.startswith("⚠️ SHADOW — DO NOT ACT")
    assert "\nhello" in out
    assert notifier._with_prefix(out) == out


def test_extract_recheck_pool_id_parses_command():
    assert TelegramNotifier._extract_recheck_pool_id("/recheck abc-123") == "abc-123"
    assert (
        TelegramNotifier._extract_recheck_pool_id("/recheck@MyBot abc-123") == "abc-123"
    )
    assert TelegramNotifier._extract_recheck_pool_id("/recheck") is None
    assert TelegramNotifier._extract_recheck_pool_id("/start") is None


def test_report_filters_non_target_tokens():
    notifier = TelegramNotifier()
    message = notifier._format_report(
        [
            _result(
                priority=PriorityTier.COIN_STABLE,
                bucket="WARN/REPUTATION",
                symbol="WETH-USDC",
            ),
            _result(
                priority=PriorityTier.COIN_COIN,
                bucket="WARN/SECURITY",
                symbol="WETH-AERO",
            ),
            _result(
                priority=PriorityTier.COIN_STABLE,
                bucket="WARN/REPUTATION",
                symbol="XAUT-USDC",
            ),
        ]
    )
    assert "`WETH-USDC`" in message
    assert "`XAUT-USDC`" in message
    assert "`WETH-AERO`" not in message


def test_report_includes_volume_ratio_when_available():
    notifier = TelegramNotifier()
    message = notifier._format_report(
        [
            _result(
                priority=PriorityTier.COIN_STABLE,
                bucket="WARN/REPUTATION",
                symbol="WETH-USDC",
                volume_24h_usd=2_000_000,
            ),
        ]
    )
    assert "Vol24h" in message
    assert "Vol/TVL" in message


def test_report_respects_top_n_per_section():
    notifier = TelegramNotifier(top_n_per_section=1)
    message = notifier._format_report(
        [
            _result(
                priority=PriorityTier.COIN_STABLE,
                bucket="WARN/REPUTATION",
                symbol="WETH-USDC",
                apy=12.0,
            ),
            _result(
                priority=PriorityTier.COIN_STABLE,
                bucket="WARN/REPUTATION",
                symbol="WETH-USDT",
                apy=11.0,
            ),
        ]
    )
    assert "`WETH-USDC`" in message
    assert "`WETH-USDT`" not in message


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


def test_report_includes_turnover_snapshot_section():
    notifier = TelegramNotifier()
    candidate = ScoutCandidate.model_validate(
        {
            "pool": "pool-turnover",
            "project": "uniswap-v3",
            "chain": "Ethereum",
            "symbol": "USDC-USDT",
            "address": "0x1111111111111111111111111111111111111111",
            "chain_id": 1,
            "tvlUsd": 2_000_000,
            "volumeUsd1d": 5_000_000,
            "apy": 5.0,
            "apyBase": 5.0,
            "apyReward": 0.0,
        }
    )
    message = notifier._format_report(
        [
            _result(
                priority=PriorityTier.COIN_STABLE,
                bucket="WARN/REPUTATION",
                symbol="WETH-USDC",
            ),
        ],
        turnover_snapshot=[candidate],
    )
    assert "High Turnover (24h)" in message
    assert "`USDC-USDT`" in message
    assert "Vol/TVL" in message


def test_report_blocks_are_section_aligned():
    notifier = TelegramNotifier()
    turnover_candidate = ScoutCandidate.model_validate(
        {
            "pool": "pool-turnover",
            "project": "uniswap-v3",
            "chain": "Ethereum",
            "symbol": "USDC-USDT",
            "address": "0x1111111111111111111111111111111111111111",
            "chain_id": 1,
            "tvlUsd": 2_000_000,
            "volumeUsd1d": 5_000_000,
            "apy": 5.0,
            "apyBase": 5.0,
            "apyReward": 0.0,
        }
    )
    blocks = notifier._format_report_blocks(
        [
            _result(
                priority=PriorityTier.COIN_STABLE,
                bucket="WARN/REPUTATION",
                symbol="WETH-USDC",
            ),
        ],
        turnover_snapshot=[turnover_candidate],
    )
    assert blocks
    assert "Legend:" in blocks[0]
    assert "High Turnover (24h)" in "\n".join(blocks)
    assert "(continued)" in "\n".join(blocks[1:])


def test_report_blocks_include_directional_sections():
    notifier = TelegramNotifier()
    lp_candidate = ScoutCandidate.model_validate(
        {
            "pool": "pool-lp",
            "project": "aerodrome-slipstream",
            "chain": "Base",
            "symbol": "WETH-USDC",
            "address": "0x1111111111111111111111111111111111111111",
            "chain_id": 8453,
            "tvlUsd": 2_000_000,
            "volumeUsd1d": 6_000_000,
            "apy": 9.0,
            "apyBase": 9.0,
            "apyReward": 0.0,
        }
    )
    supply_candidate = ScoutCandidate.model_validate(
        {
            "pool": "pool-supply",
            "project": "aave-v3",
            "chain": "Ethereum",
            "symbol": "WETH",
            "address": "0x2222222222222222222222222222222222222222",
            "chain_id": 1,
            "tvlUsd": 10_000_000,
            "apy": 3.4,
            "apyBase": 3.4,
            "apyReward": 0.0,
        }
    )
    snapshot = YieldDirectionSnapshot(
        lp_top=[
            LendingSnapshotItem(
                candidate=lp_candidate, metric_name="vol_to_tvl", metric_value_pct=3.0
            )
        ],
        lending_supply_top=[
            LendingSnapshotItem(
                candidate=supply_candidate,
                metric_name="supply_apy",
                metric_value_pct=3.4,
            )
        ],
    )
    blocks = notifier._format_report_blocks([], directional_snapshot=snapshot)
    joined = "\n".join(blocks)
    assert "Top-10 LP (High Turnover)" in joined
    assert "Top-10 Lending Supply" in joined
    assert "High Turnover (24h)" not in joined
    assert "Lending Snapshot" not in joined


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
        best_eth_supply=LendingSnapshotItem(
            candidate=candidate_eth, metric_name="supply_apy", metric_value_pct=4.5
        ),
        best_gho_supply=LendingSnapshotItem(
            candidate=candidate_gho, metric_name="supply_apy", metric_value_pct=5.2
        ),
        lowest_eurc_borrow=LendingSnapshotItem(
            candidate=candidate_eurc, metric_name="borrow_apr", metric_value_pct=1.9
        ),
        lowest_usdc_borrow=LendingSnapshotItem(
            candidate=candidate_usdc, metric_name="borrow_apr", metric_value_pct=2.3
        ),
        lowest_borrow_by_symbol={
            "EURC": LendingSnapshotItem(
                candidate=candidate_eurc, metric_name="borrow_apr", metric_value_pct=1.9
            ),
            "USDC": LendingSnapshotItem(
                candidate=candidate_usdc, metric_name="borrow_apr", metric_value_pct=2.3
            ),
            "DAI": LendingSnapshotItem(
                candidate=candidate_dai, metric_name="borrow_apr", metric_value_pct=1.7
            ),
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
    assert (
        notifier._pool_link(result)
        == "https://basescan.org/address/0x1111111111111111111111111111111111111111"
    )


def test_report_is_chunked_for_telegram_limits():
    notifier = TelegramNotifier()
    many = [
        _result(
            priority=PriorityTier.COIN_STABLE,
            bucket="WARN/REPUTATION",
            symbol="WETH-USDC",
            apy=10.0 + i,
        )
        for i in range(80)
    ]
    message = notifier._format_report(many)
    chunks = notifier._chunk_message(message, max_len=700)
    assert len(chunks) > 1
    assert all(len(chunk) <= 700 for chunk in chunks)


def test_tags_included_when_flag_enabled():
    notifier = TelegramNotifier(include_tags=True)
    message = notifier._format_report(
        [
            _result(
                priority=PriorityTier.LOW_VOLATILITY,
                bucket="SAFE",
                stable_tier="T1",
                pair_class="USD_STABLE_STABLE",
                fx_exposure="false",
            )
        ]
    )
    assert "Tier:T1" in message
    assert "Class:USD_STABLE_STABLE" in message
    assert "FX_RISK" not in message
    # Ensure tags appear after Risk
    assert "Risk `SAFE` | Tags Tier:T1 Class:USD_STABLE_STABLE" in message


def test_fx_risk_tag_included():
    notifier = TelegramNotifier(include_tags=True)
    message = notifier._format_report(
        [
            _result(
                priority=PriorityTier.COIN_STABLE,
                bucket="WARN/REPUTATION",
                stable_tier="T2",
                pair_class="FX_STABLE",
                fx_exposure="true",
            )
        ]
    )
    assert "Tier:T2" in message
    assert "Class:FX_STABLE" in message
    assert "FX_RISK" in message
    assert "Risk `WARN/REPUTATION` | Tags Tier:T2 Class:FX_STABLE FX_RISK" in message


def test_tags_not_included_when_flag_disabled():
    notifier = TelegramNotifier(include_tags=False)
    message = notifier._format_report(
        [
            _result(
                priority=PriorityTier.LOW_VOLATILITY,
                bucket="SAFE",
                stable_tier="T1",
                pair_class="USD_STABLE_STABLE",
                fx_exposure="false",
            )
        ]
    )
    assert "Tier:T1" not in message
    assert "Class:USD_STABLE_STABLE" not in message
    assert "FX_RISK" not in message
    # Ensure the "Tags" substring does not appear
    assert "Tags" not in message


def test_strategy_fields_hidden_when_not_ok():
    notifier = TelegramNotifier()
    message = notifier._format_report(
        [
            _result(
                priority=PriorityTier.COIN_COIN,
                bucket="WARN/REPUTATION",
                symbol="WETH-WBTC",
                sim_status="PARTIAL",
                sim_best_strategy="clmm_range_harvest",
                sim_fit_score="0",
                sim_exp_net_apy_min="0.00",
                sim_exp_net_apy_max="0.00",
                sim_risk_score="100",
                sim_required_data_missing="volume24h,fees24h",
            )
        ]
    )
    assert "BestStrategy" not in message
    assert "SimStatus" not in message
    assert "FitScore" not in message
    assert "ExpNetAPY" not in message
    assert "SimRisk" not in message
    assert "MissingData" not in message


def test_strategy_fields_visible_when_ok():
    notifier = TelegramNotifier()
    message = notifier._format_report(
        [
            _result(
                priority=PriorityTier.COIN_COIN,
                bucket="WARN/REPUTATION",
                symbol="WETH-WBTC",
                sim_status="OK",
                sim_best_strategy="clmm_range_harvest",
                sim_fit_score="42",
                sim_exp_net_apy_min="5.00",
                sim_exp_net_apy_max="9.00",
                sim_risk_score="25",
            )
        ]
    )
    assert "BestStrategy:clmm_range_harvest" in message
    assert "SimStatus:OK" in message
    assert "FitScore:42" in message
    assert "ExpNetAPY:5.00-9.00%" in message
    assert "SimRisk:25" in message


def test_report_includes_confidence_tag():
    notifier = TelegramNotifier(show_source_confidence=True)
    message = notifier._format_report(
        [
            _result(
                priority=PriorityTier.COIN_STABLE,
                bucket="WARN/REPUTATION",
                symbol="WETH-USDC",
            ),
        ]
    )
    assert "Conf `AGGREGATOR_ONLY`" in message
    assert "⚪" in message


def test_confidence_tag_hidden_when_disabled():
    notifier = TelegramNotifier(show_source_confidence=False)
    message = notifier._format_report(
        [
            _result(
                priority=PriorityTier.COIN_STABLE,
                bucket="WARN/REPUTATION",
                symbol="WETH-USDC",
            ),
        ]
    )
    assert "Conf" not in message


def test_directional_section_includes_confidence():
    notifier = TelegramNotifier(show_source_confidence=True)
    supply_candidate = ScoutCandidate.model_validate(
        {
            "pool": "pool-supply",
            "project": "aave-v3",
            "chain": "Ethereum",
            "symbol": "WETH",
            "address": "0x2222222222222222222222222222222222222222",
            "chain_id": 1,
            "tvlUsd": 10_000_000,
            "apy": 3.4,
            "apyBase": 3.4,
            "apyReward": 0.0,
        }
    )
    snapshot = YieldDirectionSnapshot(
        lending_supply_top=[
            LendingSnapshotItem(
                candidate=supply_candidate,
                metric_name="supply_apy",
                metric_value_pct=3.4,
            )
        ],
    )
    blocks = notifier._format_report_blocks([], directional_snapshot=snapshot)
    joined = "\n".join(blocks)
    assert "Conf `AGGREGATOR_ONLY`" in joined
    assert "⚪" in joined


def test_market_signals_hidden_when_disabled():
    notifier = TelegramNotifier(show_market_signals=False)
    message = notifier._format_report(
        [
            _result(
                priority=PriorityTier.COIN_STABLE,
                bucket="WARN/REPUTATION",
                symbol="WETH-USDC",
                metadata_overrides={
                    "apy_vs_mean_30d_pct": "33.33",
                    "stability_factor": "0.9000",
                    "stability_signals": "OUTLIER,APY_VS_30D_HIGH",
                },
            ),
        ]
    )
    assert "APYvs30d" not in message
    assert "StabF" not in message
    assert "Flags:" not in message


def test_market_signals_visible_when_enabled():
    notifier = TelegramNotifier(show_market_signals=True)
    message = notifier._format_report(
        [
            _result(
                priority=PriorityTier.COIN_STABLE,
                bucket="WARN/REPUTATION",
                symbol="WETH-USDC",
                metadata_overrides={
                    "apy_vs_mean_30d_pct": "33.33",
                    "stability_factor": "0.9000",
                    "stability_signals": "OUTLIER,APY_VS_30D_HIGH",
                },
            ),
        ]
    )
    assert "APYvs30d:+33.3%" in message
    assert "StabF:0.9000" in message
    assert "Flags:OUTLIER,APY_VS_30D_HIGH" in message


def test_report_includes_my_pools_health_and_alert_blocks():
    notifier = TelegramNotifier(show_source_confidence=True)
    my_pools_report = MyPoolsMonitorReport(
        healthy_count=1,
        watch_count=1,
        unverified_count=1,
        show_health=True,
        show_alerts=True,
        top_n=10,
        snapshots=[
            MonitoredPoolSnapshot(
                pool_ref="pool-healthy",
                label="Healthy pool",
                chain="Base",
                project="aerodrome-slipstream",
                symbol="USDC-USDT",
                tvl_usd=1_000_000,
                volume_24h_usd=2_000_000,
                vol_to_tvl_24h=2.0,
                apy=8.0,
                freshness_status="UNVERIFIED",
                source_confidence=SourceConfidence.AGGREGATOR_ONLY,
                health_tags=[PoolHealthTag.HEALTHY],
                pool_url="https://defillama.com/yields/pool/pool-healthy",
            ),
            MonitoredPoolSnapshot(
                pool_ref="pool-watch",
                label="Watch pool",
                chain="Base",
                project="aerodrome-slipstream",
                symbol="WETH-USDC",
                tvl_usd=1_000_000,
                volume_24h_usd=100_000,
                vol_to_tvl_24h=0.1,
                apy=4.0,
                freshness_status="UNVERIFIED",
                source_confidence=SourceConfidence.AGGREGATOR_ONLY,
                health_tags=[PoolHealthTag.WATCH_VOLUME, PoolHealthTag.WATCH_APY_DRIFT],
                alert_reasons=["LOW_VOL_TO_TVL", "APY_DROP_24H"],
                pool_url="https://defillama.com/yields/pool/pool-watch",
            ),
            MonitoredPoolSnapshot(
                pool_ref="pool-missing",
                label="Missing pool",
                chain="Base",
                freshness_status="UNVERIFIED",
                source_confidence=SourceConfidence.AGGREGATOR_ONLY,
                health_tags=[PoolHealthTag.DATA_UNVERIFIED],
                alert_reasons=["POOL_NOT_FOUND"],
            ),
        ],
    )
    blocks = notifier._format_report_blocks([], my_pools_report=my_pools_report)
    joined = "\n".join(blocks)
    assert "My Pools — Health" in joined
    assert "Pools: 3 | Healthy 1 | Watch 1 | Unverified 1" in joined
    assert "My Pools — Alerts" in joined
    assert "LOW_VOL_TO_TVL,APY_DROP_24H" in joined
    assert "POOL_NOT_FOUND" in joined
    assert "Conf `AGGREGATOR_ONLY`" in joined


def test_report_hides_my_pools_alerts_when_disabled():
    notifier = TelegramNotifier()
    my_pools_report = MyPoolsMonitorReport(
        healthy_count=0,
        watch_count=1,
        unverified_count=0,
        show_health=True,
        show_alerts=False,
        snapshots=[
            MonitoredPoolSnapshot(
                pool_ref="pool-watch",
                label="Watch pool",
                chain="Base",
                project="aerodrome-slipstream",
                symbol="WETH-USDC",
                tvl_usd=1_000_000,
                volume_24h_usd=100_000,
                vol_to_tvl_24h=0.1,
                apy=4.0,
                freshness_status="UNVERIFIED",
                source_confidence=SourceConfidence.AGGREGATOR_ONLY,
                health_tags=[PoolHealthTag.WATCH_VOLUME],
                alert_reasons=["LOW_VOL_TO_TVL"],
            ),
        ],
    )
    blocks = notifier._format_report_blocks([], my_pools_report=my_pools_report)
    joined = "\n".join(blocks)
    assert "My Pools — Health" in joined
    assert "My Pools — Alerts" not in joined


def test_report_blocks_include_lp_entry_recommendations_section():
    notifier = TelegramNotifier()
    recs = [
        EntryRecommendation(
            chain="Base",
            project="aerodrome-slipstream",
            pair="WETH-USDC",
            fee_tier=500,
            suggested_range_lower_tick=-120,
            suggested_range_upper_tick=120,
            confidence=EntryConfidenceBand.HIGH,
            reasons=["OK"],
            watchlist_reason=None,
            actionability=EntryActionability.ACTIONABLE,
            rank_v1=6.125,
            source_pool_id="pool-1",
        ),
        EntryRecommendation(
            chain="Ethereum",
            project="uniswap-v3",
            pair="WETH-USDT",
            fee_tier=3000,
            suggested_range_lower_tick=None,
            suggested_range_upper_tick=None,
            confidence=EntryConfidenceBand.LOW,
            reasons=["INVALID_OR_MISSING_RANGE"],
            watchlist_reason="INVALID_OR_MISSING_RANGE",
            watchlist_blocker_reason="TICK_PROVIDER_RUNTIME_ERROR",
            actionability=EntryActionability.WATCHLIST,
            rank_v1=0.0,
            source_pool_id="pool-2",
        ),
    ]
    blocks = notifier._format_report_blocks([], entry_recommendations=recs)
    joined = "\n".join(blocks)
    assert "LP Entry Recommendations" in joined
    assert "LP Entry — Network/Protocol/Range Selector" in joined
    assert "- Actionable:" in joined
    assert "- Watchlist:" in joined
    assert "Range: [-120,120]" in joined
    assert "reason `INVALID_OR_MISSING_RANGE`" in joined


def test_report_blocks_can_hide_lp_entry_watchlist() -> None:
    notifier = TelegramNotifier(show_lp_entry_watchlist=False)
    recs = [
        EntryRecommendation(
            chain="Base",
            project="aerodrome-slipstream",
            pair="WETH-USDC",
            fee_tier=500,
            suggested_range_lower_tick=-120,
            suggested_range_upper_tick=120,
            confidence=EntryConfidenceBand.HIGH,
            reasons=["OK"],
            watchlist_reason=None,
            actionability=EntryActionability.ACTIONABLE,
            rank_v1=6.125,
            source_pool_id="pool-1",
        ),
        EntryRecommendation(
            chain="Ethereum",
            project="uniswap-v3",
            pair="WETH-USDT",
            fee_tier=3000,
            suggested_range_lower_tick=None,
            suggested_range_upper_tick=None,
            confidence=EntryConfidenceBand.LOW,
            reasons=["INVALID_OR_MISSING_RANGE"],
            watchlist_reason="INVALID_OR_MISSING_RANGE",
            actionability=EntryActionability.WATCHLIST,
            rank_v1=0.0,
            source_pool_id="pool-2",
        ),
    ]
    blocks = notifier._format_report_blocks([], entry_recommendations=recs)
    joined = "\n".join(blocks)
    assert "LP Entry Recommendations" in joined
    assert "- Actionable:" in joined
    assert "- Watchlist:" not in joined
    assert "reason `INVALID_OR_MISSING_RANGE`" not in joined
    assert "LP Entry — Network/Protocol/Range Selector" in joined


def test_report_blocks_can_hide_opportunity_sections_but_keep_lp_entry() -> None:
    notifier = TelegramNotifier(show_opportunity_sections=False)
    recs = [
        EntryRecommendation(
            chain="Base",
            project="aerodrome-slipstream",
            pair="ETH-USDT",
            fee_tier=500,
            suggested_range_lower_tick=-120,
            suggested_range_upper_tick=120,
            confidence=EntryConfidenceBand.HIGH,
            reasons=["OK"],
            watchlist_reason=None,
            actionability=EntryActionability.ACTIONABLE,
            rank_v1=6.125,
            source_pool_id="pool-1",
        ),
    ]
    blocks = notifier._format_report_blocks(
        [
            _result(
                priority=PriorityTier.COIN_STABLE,
                bucket="WARN/REPUTATION",
                symbol="WETH-USDC",
            )
        ],
        entry_recommendations=recs,
    )
    joined = "\n".join(blocks)
    assert "LP Entry Recommendations" in joined
    assert "1) Stable/Stable" not in joined
    assert "`WETH-USDC`" not in joined


def test_report_blocks_returns_empty_when_opportunity_hidden_and_no_other_sections() -> (
    None
):
    notifier = TelegramNotifier(show_opportunity_sections=False)
    blocks = notifier._format_report_blocks(
        [
            _result(
                priority=PriorityTier.COIN_STABLE,
                bucket="WARN/REPUTATION",
                symbol="WETH-USDC",
            )
        ]
    )
    assert blocks == []
