import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.freshness import apply_freshness_policy
from defi_agents.scout.config import FreshnessConfig
from defi_agents.scout.models import PriorityTier, ScoutCandidate, ScoutResult
from defi_agents.security.models import SecurityResult, SecurityStatus


def _make_result(report_group: str, freshness_status: str, apy_div: str = "", tvl_div: str = "") -> ScoutResult:
    candidate = ScoutCandidate.model_validate(
        {
            "pool": "pool-fresh-1",
            "project": "demo",
            "chain": "Base",
            "symbol": "USDC-USDT",
            "address": "0x1111111111111111111111111111111111111111",
            "chain_id": 8453,
            "tvlUsd": 2_000_000,
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
        metadata={
            "report_group": report_group,
            "freshness_status": freshness_status,
            "apy_divergence_pct": apy_div,
            "tvl_divergence_pct": tvl_div,
            "warn_reasons": "",
        },
        flags=[],
    )


def test_freshness_policy_downgrades_unverified_when_enforced():
    cfg = FreshnessConfig(
        recheck_enabled=True,
        enforce_freshness_for_actionable=True,
    )
    result = _make_result(report_group="ACTIONABLE", freshness_status="UNVERIFIED")
    counters = apply_freshness_policy([result], cfg)
    assert result.metadata["report_group"] == "WATCHLIST"
    assert "UNVERIFIED_FRESHNESS" in result.metadata["warn_reasons"]
    assert counters["downgraded_to_watchlist_count"] == 1
    assert counters["unverified_count"] == 1


def test_fresh_candidate_stays_actionable_when_within_thresholds():
    cfg = FreshnessConfig(
        recheck_enabled=True,
        enforce_freshness_for_actionable=True,
        max_apy_divergence_pct=25.0,
        max_tvl_divergence_pct=20.0,
    )
    result = _make_result(
        report_group="ACTIONABLE",
        freshness_status="FRESH",
        apy_div="10.0",
        tvl_div="5.0",
    )
    counters = apply_freshness_policy([result], cfg)
    assert result.metadata["report_group"] == "ACTIONABLE"
    assert counters["fresh_count"] == 1
    assert counters["downgraded_to_watchlist_count"] == 0


def test_divergence_high_forces_watchlist_when_enforced():
    cfg = FreshnessConfig(
        recheck_enabled=True,
        enforce_freshness_for_actionable=True,
        max_apy_divergence_pct=25.0,
        max_tvl_divergence_pct=20.0,
    )
    result = _make_result(
        report_group="ACTIONABLE",
        freshness_status="FRESH",
        apy_div="40.0",
        tvl_div="10.0",
    )
    counters = apply_freshness_policy([result], cfg)
    assert result.metadata["report_group"] == "WATCHLIST"
    assert "DIVERGENCE_HIGH" in result.metadata["warn_reasons"]
    assert counters["diverged_count"] == 1
    assert counters["downgraded_to_watchlist_count"] == 1


def test_aave_outcome_counters_include_mismatch_and_schema():
    cfg = FreshnessConfig(recheck_enabled=True, enforce_freshness_for_actionable=False)
    res1 = _make_result(report_group="WATCHLIST", freshness_status="UNVERIFIED")
    res2 = _make_result(report_group="WATCHLIST", freshness_status="UNVERIFIED")
    res3 = _make_result(report_group="WATCHLIST", freshness_status="UNVERIFIED")
    res1.metadata["aave_recheck_checked"] = "1"
    res2.metadata["aave_recheck_checked"] = "1"
    res3.metadata["aave_recheck_checked"] = "1"
    res1.metadata["aave_recheck_outcome"] = "schema_mismatch"
    res2.metadata["aave_recheck_outcome"] = "addr_mismatch"
    res3.metadata["aave_recheck_outcome"] = "error"

    counters = apply_freshness_policy([res1, res2, res3], cfg)

    assert counters["aave_checked_count"] == 3
    assert counters["aave_schema_mismatch_count"] == 1
    assert counters["aave_addr_mismatch_count"] == 1
    assert counters["aave_error_count"] == 1
