from __future__ import annotations

import sys
from pathlib import Path
import csv
from datetime import datetime, timezone
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.lp.entry_recommendation import _sort_key_actionable, build_entry_recommendations
from defi_agents.history import save_to_history
from defi_agents.lp.models import EntryActionability, EntryConfidenceBand, EntryRecommendation
from defi_agents.lp.stability import (
    compute_stability_observation_counts,
    summarize_entry_stability_telemetry,
)
from defi_agents.lp.entry_recommendation import (
    build_ineligible_entry_recommendations,
    filter_lp_entry_target_scope,
    is_lp_entry_target_scope_match,
    normalize_pair_for_target_matching,
    normalize_target_pairs_for_matching,
    normalize_watchlist_reason,
    split_lp_entry_eligibility,
    summarize_watchlist_blocker_reason_counts,
    summarize_watchlist_reason_counts,
)
from defi_agents.lp.cross_protocol_selector import rank_v1
from defi_agents.scout.models import (
    PriorityTier,
    ScoutCandidate,
    ScoutResult,
    YieldType,
)
from defi_agents.security.models import SecurityResult, SecurityStatus


def _result(
    *,
    chain: str,
    project: str,
    symbol: str,
    pool_id: str,
    score: float,
    metadata: dict[str, str],
    candidate_timestamp: int | None = None,
) -> ScoutResult:
    payload = {
        "pool": pool_id,
        "project": project,
        "chain": chain,
        "symbol": symbol,
        "address": "0x1111111111111111111111111111111111111111",
        "chain_id": 1,
        "tvlUsd": 1_000_000,
        "apy": 10.0,
        "apyBase": 10.0,
        "apyReward": 0.0,
    }
    if candidate_timestamp is not None:
        payload["timestamp"] = int(candidate_timestamp)
    candidate = ScoutCandidate.model_validate(payload)
    return ScoutResult(
        candidate=candidate,
        security=SecurityResult(status=SecurityStatus.WARN, score=70),
        net_apy=10.0,
        score=score,
        net_profit_usd=15.0,
        priority=PriorityTier.COIN_STABLE,
        metadata=dict(metadata),
        flags=[],
    )


def test_entry_recommendation_rank_and_top_n_are_deterministic() -> None:
    base_meta = {
        "report_group": "ACTIONABLE",
        "freshness_status": "FRESH",
        "source_confidence": "VERIFIED",
        "confidence_factor": "1.0",
        "tick_data_quality": "OK",
        "suggested_range_lower_tick": "-100",
        "suggested_range_upper_tick": "100",
        "net_profit_1k_usd": "10.0",
        "score_raw": "5.0",
        "tick_pool_fee_tier": "500",
    }
    # Same rank inputs, tie-break by chain/project/pair/source_pool_id.
    r1 = _result(
        chain="Arbitrum",
        project="p2",
        symbol="WETH-USDC",
        pool_id="pool-2",
        score=5.0,
        metadata=base_meta,
    )
    r2 = _result(
        chain="Base",
        project="p1",
        symbol="WETH-USDC",
        pool_id="pool-1",
        score=5.0,
        metadata=base_meta,
    )
    r3 = _result(
        chain="Ethereum",
        project="p3",
        symbol="WETH-USDC",
        pool_id="pool-3",
        score=4.0,
        metadata={**base_meta, "score_raw": "4.0"},
    )

    out = build_entry_recommendations([r1, r2, r3], top_n=2)
    assert len(out) == 2
    # Deterministic ordering by rank desc then tie-breakers.
    assert [item.source_pool_id for item in out] == ["pool-2", "pool-1"]
    assert all(item.actionability == EntryActionability.ACTIONABLE for item in out)


def test_actionable_tie_break_prefers_higher_in_range_competition() -> None:
    better_competition = EntryRecommendation(
        chain="Base",
        project="uniswap-v3",
        pair="ETH/USDT",
        fee_tier=500,
        suggested_range_lower_tick=-100,
        suggested_range_upper_tick=100,
        in_range_liquidity_competition=0.9,
        volume_fee_proxy=0.4,
        cost_penalty=0.1,
        confidence_score=0.8,
        confidence=EntryConfidenceBand.HIGH,
        actionability=EntryActionability.ACTIONABLE,
        rank_v1=0.5,
        source_pool_id="pool-better",
    )
    worse_competition = EntryRecommendation(
        chain="Base",
        project="uniswap-v3",
        pair="ETH/USDT",
        fee_tier=500,
        suggested_range_lower_tick=-100,
        suggested_range_upper_tick=100,
        in_range_liquidity_competition=0.2,
        volume_fee_proxy=0.4,
        cost_penalty=0.1,
        confidence_score=0.8,
        confidence=EntryConfidenceBand.HIGH,
        actionability=EntryActionability.ACTIONABLE,
        rank_v1=0.5,
        source_pool_id="pool-worse",
    )
    ordered = sorted(
        [worse_competition, better_competition],
        key=_sort_key_actionable,
    )
    assert [item.source_pool_id for item in ordered] == ["pool-better", "pool-worse"]


def test_entry_recommendation_fail_safe_invalid_or_missing_range_to_watchlist() -> None:
    result = _result(
        chain="Base",
        project="uni",
        symbol="WETH-USDC",
        pool_id="pool-x",
        score=5.0,
        metadata={
            "report_group": "ACTIONABLE",
            "freshness_status": "FRESH",
            "source_confidence": "VERIFIED",
            "tick_data_quality": "OK",
            # invalid range
            "suggested_range_lower_tick": "100",
            "suggested_range_upper_tick": "100",
            "net_profit_1k_usd": "10.0",
        },
    )

    out = build_entry_recommendations([result], top_n=5)
    assert len(out) == 1
    rec = out[0]
    assert rec.actionability == EntryActionability.WATCHLIST
    assert rec.watchlist_reason == "INVALID_OR_MISSING_RANGE"
    assert rec.rank_v1 == 0.0
    assert result.metadata["report_group"] == "WATCHLIST"


def test_entry_recommendation_fail_safe_degraded_stale_diverged_to_watchlist() -> None:
    degraded = _result(
        chain="Base",
        project="uni",
        symbol="WETH-USDC",
        pool_id="pool-d",
        score=5.0,
        metadata={
            "report_group": "ACTIONABLE",
            "freshness_status": "FRESH",
            "source_confidence": "VERIFIED",
            "tick_data_quality": "DEGRADED",
            "suggested_range_lower_tick": "-100",
            "suggested_range_upper_tick": "100",
        },
    )
    stale = _result(
        chain="Base",
        project="uni",
        symbol="WETH-USDT",
        pool_id="pool-s",
        score=5.0,
        metadata={
            "report_group": "ACTIONABLE",
            "freshness_status": "STALE",
            "source_confidence": "STALE",
            "tick_data_quality": "OK",
            "suggested_range_lower_tick": "-100",
            "suggested_range_upper_tick": "100",
        },
    )
    diverged = _result(
        chain="Base",
        project="uni",
        symbol="WETH-DAI",
        pool_id="pool-v",
        score=5.0,
        metadata={
            "report_group": "ACTIONABLE",
            "freshness_status": "FRESH",
            "source_confidence": "DIVERGED",
            "tick_data_quality": "OK",
            "suggested_range_lower_tick": "-100",
            "suggested_range_upper_tick": "100",
        },
    )

    out = build_entry_recommendations([degraded, stale, diverged], top_n=5)
    assert len(out) == 3
    assert all(item.actionability == EntryActionability.WATCHLIST for item in out)
    reasons = {item.watchlist_reason for item in out}
    assert "TICK_DATA_DEGRADED" in reasons
    assert "FRESHNESS_STALE" in reasons
    assert "SOURCE_CONFIDENCE_DIVERGED" in reasons
    assert all(item.confidence == EntryConfidenceBand.LOW for item in out)


def test_entry_recommendation_stability_gate_downgrades_to_watchlist() -> None:
    result = _result(
        chain="Base",
        project="uni",
        symbol="WETH-USDC",
        pool_id="pool-sg",
        score=6.0,
        metadata={
            "report_group": "ACTIONABLE",
            "freshness_status": "FRESH",
            "source_confidence": "VERIFIED",
            "tick_data_quality": "OK",
            "suggested_range_lower_tick": "-120",
            "suggested_range_upper_tick": "120",
            "net_profit_1k_usd": "20.0",
        },
    )

    out = build_entry_recommendations(
        [result],
        top_n=5,
        stability_observation_counts={"pool-sg": 2},
        stability_min_observations=3,
    )
    assert len(out) == 1
    rec = out[0]
    assert rec.actionability == EntryActionability.WATCHLIST
    assert rec.watchlist_reason == "INSUFFICIENT_STABILITY_HISTORY"
    assert rec.rank_v1 == 0.0
    assert result.metadata["report_group"] == "WATCHLIST"
    assert result.metadata["watchlist_reason"] == "INSUFFICIENT_STABILITY_HISTORY"
    assert result.metadata["stability_observations"] == "2"
    assert result.metadata["stability_min_observations"] == "3"


def test_entry_recommendation_stability_gate_keeps_actionable_when_sufficient() -> None:
    result = _result(
        chain="Base",
        project="uni",
        symbol="WETH-USDC",
        pool_id="pool-sg-ok",
        score=6.0,
        metadata={
            "report_group": "ACTIONABLE",
            "freshness_status": "FRESH",
            "source_confidence": "VERIFIED",
            "tick_data_quality": "OK",
            "suggested_range_lower_tick": "-120",
            "suggested_range_upper_tick": "120",
            "net_profit_1k_usd": "20.0",
            "score_raw": "6.0",
        },
    )

    out = build_entry_recommendations(
        [result],
        top_n=5,
        stability_observation_counts={"pool-sg-ok": 3},
        stability_min_observations=3,
    )
    assert len(out) == 1
    rec = out[0]
    assert rec.actionability == EntryActionability.ACTIONABLE
    assert rec.watchlist_reason is None
    assert rec.rank_v1 > 0.0


def test_entry_recommendation_marks_range_not_computed_when_ticks_absent() -> None:
    result = _result(
        chain="Base",
        project="uniswap-v3",
        symbol="WETH-USDC",
        pool_id="pool-range-missing",
        score=6.0,
        metadata={
            "report_group": "ACTIONABLE",
            "freshness_status": "FRESH",
            "source_confidence": "VERIFIED",
            "tick_data_quality": "OK",
        },
    )

    out = build_entry_recommendations([result], top_n=5)
    assert len(out) == 1
    rec = out[0]
    assert rec.actionability == EntryActionability.WATCHLIST
    assert rec.watchlist_reason == "RANGE_NOT_COMPUTED"


def test_lp_entry_eligibility_split_and_ineligible_reason_taxonomy() -> None:
    non_lp = _result(
        chain="Base",
        project="aave-v3",
        symbol="USDC",
        pool_id="pool-non-lp",
        score=4.0,
        metadata={"tick_pool_address": "0x1111111111111111111111111111111111111111"},
    )
    non_lp.candidate.yield_type = YieldType.LENDING_SUPPLY

    unsupported_venue = _result(
        chain="Base",
        project="curve",
        symbol="USDC-USDT",
        pool_id="pool-unsupported-venue",
        score=4.0,
        metadata={"tick_pool_address": "0x2222222222222222222222222222222222222222"},
    )
    unsupported_venue.candidate.yield_type = YieldType.LP_FEES

    missing_ref = _result(
        chain="Base",
        project="uniswap-v3",
        symbol="WETH-USDC",
        pool_id="pool-missing-ref",
        score=4.0,
        metadata={},
    )
    missing_ref.candidate.yield_type = YieldType.LP_FEES

    eligible = _result(
        chain="Base",
        project="uniswap-v3",
        symbol="WETH-USDC",
        pool_id="pool-eligible",
        score=5.0,
        metadata={
            "tick_pool_address": "0x3333333333333333333333333333333333333333",
            "report_group": "ACTIONABLE",
            "freshness_status": "FRESH",
            "source_confidence": "VERIFIED",
            "tick_data_quality": "OK",
            "suggested_range_lower_tick": "-100",
            "suggested_range_upper_tick": "100",
            "net_profit_1k_usd": "10.0",
            "score_raw": "5.0",
        },
    )
    eligible.candidate.yield_type = YieldType.LP_FEES

    sushi_supported = _result(
        chain="Arbitrum",
        project="sushiswap-v3",
        symbol="WETH-USDC",
        pool_id="pool-sushi-supported",
        score=4.5,
        metadata={
            "tick_pool_address": "0x4444444444444444444444444444444444444444",
            "report_group": "ACTIONABLE",
            "freshness_status": "FRESH",
            "source_confidence": "VERIFIED",
            "tick_data_quality": "OK",
            "suggested_range_lower_tick": "-90",
            "suggested_range_upper_tick": "95",
            "score_raw": "4.5",
            "net_profit_1k_usd": "9.0",
        },
    )
    sushi_supported.candidate.yield_type = YieldType.LP_FEES

    eligible_results, ineligible = split_lp_entry_eligibility(
        [non_lp, unsupported_venue, missing_ref, eligible, sushi_supported]
    )
    assert sorted(r.candidate.pool_id for r in eligible_results) == [
        "pool-eligible",
        "pool-sushi-supported",
    ]
    assert sorted(reason for _, reason in ineligible) == [
        "MISSING_POOL_REFERENCE",
        "NON_LP_YIELD_TYPE",
        "UNSUPPORTED_ENTRY_VENUE",
    ]

    ineligible_recs = build_ineligible_entry_recommendations(ineligible)
    assert len(ineligible_recs) == 3
    reason_counts = summarize_watchlist_reason_counts(ineligible_recs)
    assert reason_counts == {
        "MISSING_POOL_REFERENCE": 1,
        "NON_LP_YIELD_TYPE": 1,
        "UNSUPPORTED_ENTRY_VENUE": 1,
    }


def test_lp_entry_eligibility_accepts_token_pair_reference_without_pool_address() -> (
    None
):
    token_pair_ref = _result(
        chain="Base",
        project="uniswap-v3",
        symbol="WETH-USDC",
        pool_id="pool-token-pair-ref",
        score=5.0,
        metadata={},
    )
    token_pair_ref.candidate.yield_type = YieldType.LP_FEES
    token_pair_ref.candidate.address_source = "TOKEN"
    token_pair_ref.candidate.underlying_tokens = [
        "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    ]

    eligible_results, ineligible = split_lp_entry_eligibility([token_pair_ref])

    assert [r.candidate.pool_id for r in eligible_results] == ["pool-token-pair-ref"]
    assert ineligible == []


def test_entry_recommendation_calibration_factors_affect_confidence_and_rank() -> None:
    result = _result(
        chain="Base",
        project="uni",
        symbol="WETH-USDT",
        pool_id="pool-cal",
        score=5.0,
        metadata={
            "report_group": "ACTIONABLE",
            "freshness_status": "FRESH",
            "source_confidence": "AGGREGATOR_ONLY",
            "tick_data_quality": "OK",
            "suggested_range_lower_tick": "-80",
            "suggested_range_upper_tick": "90",
            "score_raw": "5.0",
            "net_profit_1k_usd": "80.0",
        },
    )

    out = build_entry_recommendations(
        [result],
        top_n=5,
        calibration={
            "source_confidence_factors": {"AGGREGATOR_ONLY": 0.9},
            "confidence_high_min_factor": 0.85,
            "confidence_medium_min_factor": 0.60,
            "economics_cap_usd": 50.0,
            "rank_confidence_power": 2.0,
            "rank_economics_power": 0.5,
        },
    )

    assert len(out) == 1
    rec = out[0]
    assert rec.actionability == EntryActionability.ACTIONABLE
    assert rec.confidence == EntryConfidenceBand.HIGH
    # Deterministic expected selector score in [0, 1] from rank_v1 components.
    assert rec.rank_v1 == pytest.approx(0.5970, rel=1e-6)


def test_entry_recommendation_emits_selector_score_components() -> None:
    result = _result(
        chain="Base",
        project="uniswap-v3",
        symbol="WETH-USDT",
        pool_id="pool-selector-components",
        score=5.0,
        metadata={
            "report_group": "ACTIONABLE",
            "freshness_status": "FRESH",
            "source_confidence": "VERIFIED",
            "tick_data_quality": "OK",
            "suggested_range_lower_tick": "-100",
            "suggested_range_upper_tick": "100",
            "tick_pool_fee_tier": "500",
            "band_depth_2_5pct_usd": "50000",
            "volume_24h_usd": "1200000",
            "net_profit_1k_usd": "15",
        },
    )

    out = build_entry_recommendations([result], top_n=5)
    assert len(out) == 1
    rec = out[0]
    assert rec.actionability == EntryActionability.ACTIONABLE
    assert rec.in_range_liquidity_competition > 0.0
    assert rec.volume_fee_proxy > 0.0
    assert rec.cost_penalty >= 0.0
    assert rec.confidence_score > 0.0
    assert rec.rank_v1 == pytest.approx(
        rank_v1(
            {
                "in_range_liquidity_competition": rec.in_range_liquidity_competition,
                "volume_fee_proxy": rec.volume_fee_proxy,
                "cost_penalty": rec.cost_penalty,
                "confidence": rec.confidence_score,
            }
        ),
        rel=1e-9,
    )


def test_entry_recommendation_auto_range_mode_respects_market_regime() -> None:
    result = _result(
        chain="Base",
        project="uniswap-v3",
        symbol="WETH-USDT",
        pool_id="pool-auto-range",
        score=5.0,
        metadata={
            "report_group": "ACTIONABLE",
            "freshness_status": "FRESH",
            "source_confidence": "VERIFIED",
            "tick_data_quality": "OK",
            "suggested_range_lower_tick": "-100",
            "suggested_range_upper_tick": "100",
            "tick_pool_fee_tier": "500",
            "band_depth_2_5pct_usd": "50000",
            "volume_24h_usd": "1200000",
            "net_profit_1k_usd": "15",
        },
    )

    out = build_entry_recommendations(
        [result],
        top_n=5,
        range_mode="AUTO",
        market_regime="UPTREND",
    )
    assert len(out) == 1
    rec = out[0]
    assert rec.range_mode == "ASYMMETRIC"
    assert rec.market_regime == "UPTREND"
    assert rec.suggested_range_lower_tick == -80
    assert rec.suggested_range_upper_tick == 120


def test_compute_stability_observation_counts_respects_time_window(
    tmp_path: Path,
) -> None:
    history_path = tmp_path / "history.csv"
    now_dt = datetime(2026, 3, 3, 12, 0, tzinfo=timezone.utc)
    now_ts = int(now_dt.timestamp())

    with history_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "timestamp",
                "chain",
                "symbol",
                "project",
                "pool_id",
                "apy",
                "apy_base",
                "apy_reward",
                "tvl_usd",
                "score",
                "net_apy",
                "net_profit_usd",
                "security_status",
                "l3_status",
                "l3_confidence",
                "l3_reason_codes",
                "l3_cache_hit",
                "l3_model",
            ]
        )
        writer.writerow(
            [
                now_ts - 60,
                "Base",
                "A",
                "uni",
                "pool-a",
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                "",
                "",
                "",
                "",
                "",
                "",
            ]
        )
        writer.writerow(
            [
                now_ts - 120,
                "Base",
                "A",
                "uni",
                "pool-a",
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                "",
                "",
                "",
                "",
                "",
                "",
            ]
        )
        writer.writerow(
            [
                now_ts - 180,
                "Base",
                "A",
                "uni",
                "pool-a",
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                "",
                "",
                "",
                "",
                "",
                "",
            ]
        )
        writer.writerow(
            [
                now_ts - (7 * 3600),
                "Base",
                "A",
                "uni",
                "pool-a",
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                "",
                "",
                "",
                "",
                "",
                "",
            ]
        )
        writer.writerow(
            [
                now_ts - 60,
                "Base",
                "B",
                "uni",
                "pool-b",
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                "",
                "",
                "",
                "",
                "",
                "",
            ]
        )

    counts = compute_stability_observation_counts(
        ["pool-a", "pool-b", "pool-c"],
        history_path=history_path,
        lookback_hours=6,
        now_epoch=now_ts,
    )

    assert counts["pool-a"] == 3
    assert counts["pool-b"] == 1
    assert counts["pool-c"] == 0


def test_stability_observation_counts_use_history_observation_time_not_source_timestamp(
    tmp_path: Path,
) -> None:
    history_path = tmp_path / "history.csv"
    old_source_ts = int(datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp())
    result = _result(
        chain="Base",
        project="uni",
        symbol="WETH-USDC",
        pool_id="pool-old-ts",
        score=5.0,
        metadata={"report_group": "ACTIONABLE"},
        candidate_timestamp=old_source_ts,
    )
    now_ts = int(datetime.now(timezone.utc).timestamp())
    save_to_history([result], path=history_path)

    counts = compute_stability_observation_counts(
        ["pool-old-ts"],
        history_path=history_path,
        lookback_hours=6,
        now_epoch=now_ts + 10,
    )
    assert counts["pool-old-ts"] == 1


def test_summarize_entry_stability_telemetry_includes_topn_churn() -> None:
    actionable = _result(
        chain="Base",
        project="uni",
        symbol="WETH-USDC",
        pool_id="pool-1",
        score=6.0,
        metadata={
            "report_group": "ACTIONABLE",
            "freshness_status": "FRESH",
            "source_confidence": "VERIFIED",
            "tick_data_quality": "OK",
            "suggested_range_lower_tick": "-100",
            "suggested_range_upper_tick": "100",
            "score_raw": "6.0",
            "net_profit_1k_usd": "10.0",
        },
    )
    watchlist = _result(
        chain="Base",
        project="uni",
        symbol="WETH-DAI",
        pool_id="pool-3",
        score=5.0,
        metadata={
            "report_group": "ACTIONABLE",
            "freshness_status": "FRESH",
            "source_confidence": "VERIFIED",
            "tick_data_quality": "OK",
            "suggested_range_lower_tick": "100",
            "suggested_range_upper_tick": "100",
        },
    )
    out = build_entry_recommendations([actionable, watchlist], top_n=2)
    telemetry = summarize_entry_stability_telemetry(
        out,
        top_n=2,
        previous_topn_pool_ids=["pool-1", "pool-2"],
    )

    assert telemetry.entry_total == 2
    assert telemetry.entry_actionable == 1
    assert telemetry.entry_watchlist == 1
    assert telemetry.entry_watchlist_insufficient_history == 0
    assert telemetry.topn_pool_ids == ["pool-1"]
    assert telemetry.entry_topn_churn == pytest.approx(0.5, rel=1e-9)


def test_watchlist_reason_is_normalized_to_deterministic_code() -> None:
    result = _result(
        chain="Base",
        project="uni",
        symbol="WETH-USDC",
        pool_id="pool-free-text",
        score=6.0,
        metadata={
            "report_group": "WATCHLIST",
            "watchlist_reason": "some human readable reason",
            "freshness_status": "FRESH",
            "source_confidence": "VERIFIED",
            "tick_data_quality": "OK",
            "suggested_range_lower_tick": "-120",
            "suggested_range_upper_tick": "120",
        },
    )

    out = build_entry_recommendations([result], top_n=5)
    assert len(out) == 1
    rec = out[0]
    assert rec.actionability == EntryActionability.WATCHLIST
    assert rec.watchlist_reason == "REPORT_GROUP_WATCHLIST"


def test_degraded_path_preserves_normalized_readiness_blocker_root_cause() -> None:
    result = _result(
        chain="Base",
        project="uniswap-v3",
        symbol="WETH-USDC",
        pool_id="pool-degraded-root-cause",
        score=6.0,
        metadata={
            "report_group": "ACTIONABLE",
            "freshness_status": "FRESH",
            "source_confidence": "VERIFIED",
            "tick_data_quality": "DEGRADED",
            "tick_degradation_reason": "SUBGRAPH_TIMEOUT",
            # legacy/free-form-ish runtime bucket from old telemetry path:
            "readiness_blocker": "PROVIDER_UNAVAILABLE_SUBGRAPH_TIMEOUT",
            "suggested_range_lower_tick": "-120",
            "suggested_range_upper_tick": "120",
            "score_raw": "6.0",
            "net_profit_1k_usd": "12.0",
        },
    )

    out = build_entry_recommendations([result], top_n=5)
    assert len(out) == 1
    rec = out[0]
    assert rec.actionability == EntryActionability.WATCHLIST
    assert rec.watchlist_reason == "TICK_DATA_DEGRADED"
    assert rec.watchlist_blocker_reason == "TICK_PROVIDER_RUNTIME_ERROR"
    assert result.metadata["watchlist_blocker_reason"] == "TICK_PROVIDER_RUNTIME_ERROR"

    blocker_counts = summarize_watchlist_blocker_reason_counts(out)
    assert blocker_counts == {"TICK_PROVIDER_RUNTIME_ERROR": 1}


def test_lp_entry_decouples_from_generic_strategysim_watchlist_downgrade() -> None:
    result = _result(
        chain="Base",
        project="uniswap-v3",
        symbol="WETH-USDC",
        pool_id="pool-sim-decouple",
        score=6.0,
        metadata={
            # Generic StrategySim policy already downgraded report_group to WATCHLIST,
            # but LP seed says this candidate was ACTIONABLE before sim policy.
            "report_group": "WATCHLIST",
            "watchlist_reason": "SIM_STATUS_PARTIAL",
            "lp_entry_seed_report_group": "ACTIONABLE",
            "lp_entry_seed_watchlist_reason": "",
            "freshness_status": "FRESH",
            "source_confidence": "VERIFIED",
            "tick_data_quality": "OK",
            "suggested_range_lower_tick": "-120",
            "suggested_range_upper_tick": "120",
            "score_raw": "6.0",
            "net_profit_1k_usd": "12.0",
        },
    )

    out = build_entry_recommendations([result], top_n=5)
    assert len(out) == 1
    rec = out[0]
    assert rec.actionability == EntryActionability.ACTIONABLE
    assert rec.watchlist_reason is None
    assert rec.rank_v1 > 0.0


def test_summarize_watchlist_reason_counts_sorted_and_deterministic() -> None:
    actionable = _result(
        chain="Base",
        project="uni",
        symbol="WETH-USDC",
        pool_id="pool-a",
        score=6.0,
        metadata={
            "report_group": "ACTIONABLE",
            "freshness_status": "FRESH",
            "source_confidence": "VERIFIED",
            "tick_data_quality": "OK",
            "suggested_range_lower_tick": "-120",
            "suggested_range_upper_tick": "120",
            "score_raw": "6.0",
            "net_profit_1k_usd": "20.0",
        },
    )
    watchlist_1 = _result(
        chain="Base",
        project="uni",
        symbol="WETH-USDT",
        pool_id="pool-b",
        score=6.0,
        metadata={
            "report_group": "WATCHLIST",
            "watchlist_reason": "INVALID_OR_MISSING_RANGE",
            "freshness_status": "FRESH",
            "source_confidence": "VERIFIED",
            "tick_data_quality": "OK",
            "suggested_range_lower_tick": "10",
            "suggested_range_upper_tick": "10",
        },
    )
    watchlist_2 = _result(
        chain="Base",
        project="uni",
        symbol="WETH-DAI",
        pool_id="pool-c",
        score=6.0,
        metadata={
            "report_group": "WATCHLIST",
            "watchlist_reason": "INVALID_OR_MISSING_RANGE",
            "freshness_status": "FRESH",
            "source_confidence": "VERIFIED",
            "tick_data_quality": "OK",
            "suggested_range_lower_tick": "20",
            "suggested_range_upper_tick": "20",
        },
    )

    recommendations = build_entry_recommendations(
        [actionable, watchlist_1, watchlist_2],
        top_n=5,
    )
    counts = summarize_watchlist_reason_counts(recommendations)
    assert counts == {"INVALID_OR_MISSING_RANGE": 2}


def test_normalize_watchlist_reason_accepts_machine_code_and_rejects_free_text() -> (
    None
):
    assert (
        normalize_watchlist_reason("invalid_or_missing_range")
        == "INVALID_OR_MISSING_RANGE"
    )
    assert normalize_watchlist_reason("SOME_NEW_REASON_CODE") == "SOME_NEW_REASON_CODE"
    assert (
        normalize_watchlist_reason("not deterministic free text")
        == "REPORT_GROUP_WATCHLIST"
    )


def test_target_pair_normalization_matches_eth_usdt_and_weth_usdt() -> None:
    assert normalize_pair_for_target_matching("ETH/USDT") == "ETH/USDT"
    assert normalize_pair_for_target_matching("WETH-USDT") == "ETH/USDT"
    assert normalize_pair_for_target_matching("usdt_weth") == "ETH/USDT"
    assert normalize_pair_for_target_matching("ETH-USDT-USDC") == ""
    assert normalize_pair_for_target_matching("ETH") == ""


def test_target_pairs_normalization_merges_single_and_list() -> None:
    assert normalize_target_pairs_for_matching(
        target_pair="ETH/USDT",
        target_pairs=["WETH-USDC", "ETH-USDE", "bad-pair-format-1-2-3"],
    ) == {"ETH/USDT", "ETH/USDC", "ETH/USDE"}


def test_filter_lp_entry_target_scope_applies_pair_chain_and_project_allowlists() -> None:
    base_meta = {
        "report_group": "ACTIONABLE",
        "freshness_status": "FRESH",
        "source_confidence": "VERIFIED",
        "tick_data_quality": "OK",
        "suggested_range_lower_tick": "-100",
        "suggested_range_upper_tick": "100",
    }
    target_ok = _result(
        chain="Base",
        project="Uniswap V3",
        symbol="WETH-USDT",
        pool_id="pool-target-ok",
        score=6.0,
        metadata=base_meta,
    )
    wrong_chain = _result(
        chain="Arbitrum",
        project="Uniswap V3",
        symbol="ETH/USDT",
        pool_id="pool-target-wrong-chain",
        score=5.0,
        metadata=base_meta,
    )
    wrong_project = _result(
        chain="Base",
        project="Aerodrome Slipstream",
        symbol="ETH-USDT",
        pool_id="pool-target-wrong-project",
        score=5.0,
        metadata=base_meta,
    )
    wrong_pair = _result(
        chain="Base",
        project="Uniswap V3",
        symbol="WETH-USDC",
        pool_id="pool-target-wrong-pair",
        score=5.0,
        metadata=base_meta,
    )

    matched = filter_lp_entry_target_scope(
        [target_ok, wrong_chain, wrong_project, wrong_pair],
        target_pair="ETH/USDT",
        allowed_chains=["base"],
        allowed_projects=["uniswap-v3"],
    )
    assert [item.candidate.pool_id for item in matched] == ["pool-target-ok"]


def test_filter_lp_entry_target_scope_accepts_multiple_target_pairs() -> None:
    target_usdt = _result(
        chain="Base",
        project="Uniswap V3",
        symbol="WETH-USDT",
        pool_id="pool-target-usdt",
        score=6.0,
        metadata={"report_group": "ACTIONABLE"},
    )
    target_usdc = _result(
        chain="Base",
        project="Uniswap V3",
        symbol="ETH-USDC",
        pool_id="pool-target-usdc",
        score=5.0,
        metadata={"report_group": "ACTIONABLE"},
    )
    non_target = _result(
        chain="Base",
        project="Uniswap V3",
        symbol="ETH-DAI",
        pool_id="pool-non-target",
        score=4.0,
        metadata={"report_group": "ACTIONABLE"},
    )

    matched = filter_lp_entry_target_scope(
        [target_usdt, target_usdc, non_target],
        target_pair="",
        target_pairs=["ETH/USDT", "ETH-USDC"],
        allowed_chains=[],
        allowed_projects=[],
    )
    assert [item.candidate.pool_id for item in matched] == [
        "pool-target-usdt",
        "pool-target-usdc",
    ]


def test_filter_lp_entry_target_scope_with_empty_constraints_is_pair_only() -> None:
    target_1 = _result(
        chain="Base",
        project="uniswap-v3",
        symbol="ETH/USDT",
        pool_id="pool-target-1",
        score=6.0,
        metadata={"report_group": "ACTIONABLE"},
    )
    target_2 = _result(
        chain="Arbitrum",
        project="aerodrome-slipstream",
        symbol="WETH-USDT",
        pool_id="pool-target-2",
        score=6.0,
        metadata={"report_group": "ACTIONABLE"},
    )
    non_target = _result(
        chain="Base",
        project="uniswap-v3",
        symbol="ETH-USDC",
        pool_id="pool-non-target",
        score=6.0,
        metadata={"report_group": "ACTIONABLE"},
    )

    matched = filter_lp_entry_target_scope(
        [target_1, target_2, non_target],
        target_pair="eth-usdt",
        allowed_chains=[],
        allowed_projects=[],
    )
    assert [item.candidate.pool_id for item in matched] == [
        "pool-target-1",
        "pool-target-2",
    ]


def test_is_lp_entry_target_scope_match_checks_pair_chain_project() -> None:
    result = _result(
        chain="Base",
        project="Uniswap V3",
        symbol="WETH-USDT",
        pool_id="pool-match",
        score=5.0,
        metadata={"report_group": "ACTIONABLE"},
    )
    assert (
        is_lp_entry_target_scope_match(
            result,
            normalized_target_pair="ETH/USDT",
            normalized_chains={"base"},
            normalized_projects={"uniswapv3"},
        )
        is True
    )
    assert (
        is_lp_entry_target_scope_match(
            result,
            normalized_target_pair="ETH/USDT",
            normalized_chains={"arbitrum"},
            normalized_projects={"uniswapv3"},
        )
        is False
    )
