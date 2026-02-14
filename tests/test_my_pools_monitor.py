import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.scout.defillama_client import DeFiLlamaClient
from defi_agents.scout.config import ScoutConfig
from defi_agents.scout.models import (
    MonitoredPoolSnapshot,
    MyPoolsMonitorReport,
    PoolHealthTag,
)


def _run(coro):
    import asyncio

    return asyncio.run(coro)


def test_my_pools_monitor_defaults_off():
    cfg = ScoutConfig()
    assert cfg.my_pools_monitor.enabled is False
    assert cfg.my_pools_monitor.pools == []
    assert cfg.my_pools_monitor.show_health is True
    assert cfg.my_pools_monitor.show_alerts is True


def test_my_pools_monitor_accepts_pool_id_or_chain_address():
    cfg_by_pool_id = ScoutConfig(
        my_pools_monitor={
            "enabled": True,
            "pools": [{"pool_id": "pool-123", "label": "Main USDC/USDT"}],
        }
    )
    assert cfg_by_pool_id.my_pools_monitor.pools[0].pool_id == "pool-123"
    assert cfg_by_pool_id.my_pools_monitor.pools[0].label == "Main USDC/USDT"

    cfg_by_chain_address = ScoutConfig(
        my_pools_monitor={
            "enabled": True,
            "pools": [{"chain": "Base", "address": "0x1111111111111111111111111111111111111111"}],
        }
    )
    assert cfg_by_chain_address.my_pools_monitor.pools[0].chain == "Base"
    assert cfg_by_chain_address.my_pools_monitor.pools[0].address == "0x1111111111111111111111111111111111111111"


def test_my_pools_monitor_target_requires_pool_ref_or_chain_address():
    with pytest.raises(ValidationError):
        ScoutConfig(
            my_pools_monitor={
                "enabled": True,
                "pools": [{"label": "broken-entry"}],
            }
        )


def test_my_pools_monitor_report_contract():
    snapshot = MonitoredPoolSnapshot(
        pool_ref="pool-123",
        label="Main USDC/USDT",
        health_tags=[PoolHealthTag.HEALTHY],
    )
    report = MyPoolsMonitorReport(
        healthy_count=1,
        watch_count=0,
        unverified_count=0,
        snapshots=[snapshot],
    )
    assert report.has_any() is True
    assert report.snapshots[0].health_tags == [PoolHealthTag.HEALTHY]

    empty_report = MyPoolsMonitorReport()
    assert empty_report.has_any() is False


def test_my_pools_monitor_report_resolves_watchlist_and_tags(monkeypatch):
    cfg = ScoutConfig(
        my_pools_monitor={
            "enabled": True,
            "pools": [
                {"pool_id": "pool-good", "label": "Good"},
                {"chain": "Base", "address": "0x2222222222222222222222222222222222222222", "label": "Watch"},
                {"pool_id": "pool-missing", "label": "Missing"},
            ],
            "min_vol_to_tvl_24h": 1.0,
            "max_apy_drop_pct_24h": 20.0,
            "max_tvl_drop_pct_24h": 10.0,
        }
    )
    client = DeFiLlamaClient(cfg)

    async def fake_fetch():
        return [
            {
                "pool": "pool-good",
                "project": "aerodrome-slipstream",
                "chain": "Base",
                "symbol": "USDC-USDT",
                "address": "0x1111111111111111111111111111111111111111",
                "tvlUsd": 1_000_000,
                "volumeUsd1d": 2_200_000,
                "apy": 10.0,
                "apyMean30d": 8.0,
            },
            {
                "pool": "pool-watch",
                "project": "aerodrome-slipstream",
                "chain": "Base",
                "symbol": "WETH-USDC",
                "address": "0x2222222222222222222222222222222222222222",
                "tvlUsd": 1_000_000,
                "volumeUsd1d": 100_000,
                "apy": 5.0,
                "apyMean30d": 7.0,
            },
        ]

    async def fake_history(pool_id: str):
        if pool_id == "pool-good":
            return [
                {"timestamp": 1, "tvlUsd": 1_050_000, "apy": 11.0},
                {"timestamp": 2, "tvlUsd": 1_000_000, "apy": 10.0},
            ]
        if pool_id == "pool-watch":
            return [
                {"timestamp": 1, "tvlUsd": 1_500_000, "apy": 7.0},
                {"timestamp": 2, "tvlUsd": 1_000_000, "apy": 5.0},
            ]
        return []

    monkeypatch.setattr(client, "_fetch_raw_pools", fake_fetch)
    monkeypatch.setattr(client, "get_pool_history", fake_history)

    report = _run(client.get_my_pools_monitor_report())
    assert len(report.snapshots) == 3
    assert report.healthy_count == 1
    assert report.watch_count == 2
    assert report.unverified_count == 1

    by_label = {snap.label: snap for snap in report.snapshots}
    good = by_label["Good"]
    assert good.health_tags == [PoolHealthTag.HEALTHY]
    assert good.apy_vs_mean_30d_pct == pytest.approx(25.0)

    watch = by_label["Watch"]
    assert PoolHealthTag.WATCH_VOLUME in watch.health_tags
    assert PoolHealthTag.WATCH_APY_DRIFT in watch.health_tags
    assert PoolHealthTag.WATCH_TVL_DRAIN in watch.health_tags
    assert "LOW_VOL_TO_TVL" in watch.alert_reasons
    assert "APY_DROP_24H" in watch.alert_reasons
    assert "TVL_DROP_24H" in watch.alert_reasons

    missing = by_label["Missing"]
    assert missing.health_tags == [PoolHealthTag.DATA_UNVERIFIED]
    assert missing.alert_reasons == ["POOL_NOT_FOUND"]


def test_my_pools_monitor_history_accepts_iso_timestamps(monkeypatch):
    cfg = ScoutConfig(
        my_pools_monitor={
            "enabled": True,
            "pools": [{"pool_id": "pool-iso", "label": "ISO pool"}],
            "min_vol_to_tvl_24h": 0.0,
            "max_apy_drop_pct_24h": 10.0,
            "max_tvl_drop_pct_24h": 10.0,
        }
    )
    client = DeFiLlamaClient(cfg)

    async def fake_fetch():
        return [
            {
                "pool": "pool-iso",
                "project": "aerodrome-slipstream",
                "chain": "Base",
                "symbol": "USDC-USDT",
                "address": "0x1111111111111111111111111111111111111111",
                "tvlUsd": 1_000_000,
                "volumeUsd1d": 1_000_000,
                "apy": 8.0,
                "apyMean30d": 8.0,
            },
        ]

    async def fake_history(_pool_id: str):
        return [
            {"timestamp": "2026-02-12T21:00:00Z", "tvlUsd": 1_500_000, "apy": 12.0},
            {"timestamp": "2026-02-13T21:00:00Z", "tvlUsd": 1_000_000, "apy": 8.0},
        ]

    monkeypatch.setattr(client, "_fetch_raw_pools", fake_fetch)
    monkeypatch.setattr(client, "get_pool_history", fake_history)

    report = _run(client.get_my_pools_monitor_report())
    assert len(report.snapshots) == 1
    snap = report.snapshots[0]
    assert PoolHealthTag.WATCH_APY_DRIFT in snap.health_tags
    assert PoolHealthTag.WATCH_TVL_DRAIN in snap.health_tags
