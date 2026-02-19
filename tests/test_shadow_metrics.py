import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.cache import CacheController
from defi_agents.scout.models import PriorityTier, ScoutCandidate, ScoutResult
from defi_agents.shadow_metrics import ShadowMetricsTracker


def _result(*, pool_id: str, net_profit_1k: float, net_apy: float = 24.0) -> ScoutResult:
    candidate = ScoutCandidate.model_validate(
        {
            "pool": pool_id,
            "project": "demo",
            "chain": "Base",
            "symbol": "WETH-USDC",
            "address": "0x1111111111111111111111111111111111111111",
            "chain_id": 8453,
            "tvlUsd": 1_000_000,
            "apy": net_apy,
            "apyBase": net_apy,
            "apyReward": 0.0,
        }
    )
    return ScoutResult(
        candidate=candidate,
        security=None,
        net_apy=net_apy,
        score=10.0,
        net_profit_usd=20.0,
        priority=PriorityTier.COIN_STABLE,
        metadata={"net_profit_1k_usd": f"{net_profit_1k:.2f}"},
        flags=[],
    )


def test_shadow_tracker_captures_entries(tmp_path, monkeypatch):
    cache = CacheController(namespace="shadow_test", base_dir=tmp_path)
    tracker = ShadowMetricsTracker(
        cache=cache,
        horizon_seconds=3600,
        capture_interval_seconds=600,
        retention_seconds=86_400,
    )

    monkeypatch.setattr("defi_agents.shadow_metrics.time", lambda: 1_000_000)
    summary = tracker.process([_result(pool_id="pool-1", net_profit_1k=5.0)])

    assert summary.captured_count == 1
    assert summary.evaluated_count == 0
    assert summary.pending_count == 1


def test_shadow_tracker_evaluates_matured_predictions(tmp_path, monkeypatch):
    cache = CacheController(namespace="shadow_eval_test", base_dir=tmp_path)
    tracker = ShadowMetricsTracker(
        cache=cache,
        horizon_seconds=3600,
        capture_interval_seconds=600,
        retention_seconds=86_400,
    )

    monkeypatch.setattr("defi_agents.shadow_metrics.time", lambda: 2_000_000)
    tracker.process([_result(pool_id="pool-1", net_profit_1k=10.0)])

    # Move time beyond horizon and provide later proxy outcome.
    monkeypatch.setattr("defi_agents.shadow_metrics.time", lambda: 2_004_000)
    summary = tracker.process([_result(pool_id="pool-1", net_profit_1k=8.0)])

    assert summary.evaluated_count == 1
    assert summary.pending_count >= 1  # one new capture may be created after evaluation
    assert summary.median_ape_proxy > 0
    assert 0.0 <= summary.directional_accuracy_proxy <= 1.0


def test_shadow_tracker_latest_prediction(tmp_path, monkeypatch):
    cache = CacheController(namespace="shadow_latest_test", base_dir=tmp_path)
    tracker = ShadowMetricsTracker(cache=cache, horizon_seconds=3600, capture_interval_seconds=60, retention_seconds=86_400)
    monkeypatch.setattr("defi_agents.shadow_metrics.time", lambda: 3_000_000)
    tracker.process([_result(pool_id="pool-1", net_profit_1k=6.0)])
    monkeypatch.setattr("defi_agents.shadow_metrics.time", lambda: 3_000_500)
    tracker.process([_result(pool_id="pool-1", net_profit_1k=7.0)])
    latest = tracker.latest_prediction("pool-1")
    assert latest is not None
    assert float(latest["predicted_net_profit_1k"]) == 7.0
