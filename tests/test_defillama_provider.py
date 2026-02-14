import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.data import DeFiLlamaDataProvider


def _run(coro):
    import asyncio

    return asyncio.run(coro)


def test_provider_fetches_pools_and_uses_cache():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": [
                    {
                        "pool": "pool-1",
                        "project": "aave-v3",
                        "chain": "Ethereum",
                        "symbol": "USDC",
                        "tvlUsd": 1_000_000,
                        "apy": 3.0,
                    }
                ],
            },
            request=request,
        )

    provider = DeFiLlamaDataProvider(
        timeout_seconds=5,
        retry_attempts=0,
        cache_ttl_seconds={"yields_pools": 60},
        yields_base_url="https://test.llama",
        transport=httpx.MockTransport(handler),
    )

    first = _run(provider.get_yield_pools_raw())
    second = _run(provider.get_yield_pools_raw())

    assert len(first) == 1
    assert len(second) == 1
    assert calls["count"] == 1
    stats = provider.get_counters()["yields_pools"]
    assert stats["request_count"] == 1
    assert stats["success_count"] == 1
    assert stats["cache_hit_count"] == 1


def test_provider_retries_on_timeout_then_succeeds():
    calls = {"count": 0}

    def handler(request: httpx.Request):
        calls["count"] += 1
        if calls["count"] < 3:
            raise httpx.ReadTimeout("timeout", request=request)
        return httpx.Response(
            200,
            json={"status": "success", "data": []},
            request=request,
        )

    provider = DeFiLlamaDataProvider(
        timeout_seconds=1,
        retry_attempts=2,
        cache_ttl_seconds={"yields_pools": 0},
        yields_base_url="https://test.llama",
        transport=httpx.MockTransport(handler),
    )
    pools = _run(provider.get_yield_pools_raw())
    assert pools == []
    stats = provider.get_counters()["yields_pools"]
    assert stats["request_count"] == 3
    assert stats["timeout_count"] == 2
    assert stats["success_count"] == 1


def test_provider_parse_error_is_fail_safe():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": []}, request=request)

    provider = DeFiLlamaDataProvider(
        timeout_seconds=5,
        retry_attempts=0,
        cache_ttl_seconds={"yields_pools": 0},
        yields_base_url="https://test.llama",
        transport=httpx.MockTransport(handler),
    )
    pools = _run(provider.get_yield_pools_raw())
    assert pools == []
    stats = provider.get_counters()["yields_pools"]
    assert stats["success_count"] == 1
    assert stats["parse_error_count"] == 1


def test_provider_history_returns_typed_points():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": [
                    {
                        "timestamp": 1700000000,
                        "tvlUsd": 1_000_000,
                        "apy": 3.2,
                    }
                ],
            },
            request=request,
        )

    provider = DeFiLlamaDataProvider(
        timeout_seconds=5,
        retry_attempts=0,
        cache_ttl_seconds={"yields_chart": 0},
        yields_base_url="https://test.llama",
        transport=httpx.MockTransport(handler),
    )
    points = _run(provider.get_yield_pool_history("pool-1"))
    assert len(points) == 1
    assert points[0].timestamp == 1700000000
    assert points[0].apy == 3.2


def test_provider_returns_typed_pool_facts_with_stability_fields():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": [
                    {
                        "pool": "pool-typed-1",
                        "project": "curve",
                        "chain": "Ethereum",
                        "symbol": "USDC-USDT",
                        "tvlUsd": 12_000_000,
                        "apy": 5.3,
                        "apyMean30d": 4.7,
                        "apyPct30D": 12.0,
                        "mu": 5.0,
                        "sigma": 1.1,
                        "ilRisk": "no",
                        "outlier": False,
                        "exposure": "multi",
                    }
                ],
            },
            request=request,
        )

    provider = DeFiLlamaDataProvider(
        timeout_seconds=5,
        retry_attempts=0,
        cache_ttl_seconds={"yields_pools": 0},
        yields_base_url="https://test.llama",
        transport=httpx.MockTransport(handler),
    )
    facts = _run(provider.get_yield_pools())
    assert len(facts) == 1
    fact = facts[0]
    assert fact.apy_mean_30d == 4.7
    assert fact.apy_pct_30d == 12.0
    assert fact.mu == 5.0
    assert fact.sigma == 1.1
    assert fact.il_risk == "no"
    assert fact.outlier is False
    assert fact.exposure == "multi"


def test_optional_market_surfaces_disabled_are_noops():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(500, json={}, request=request)

    provider = DeFiLlamaDataProvider(
        timeout_seconds=5,
        retry_attempts=0,
        cache_ttl_seconds={},
        yields_base_url="https://test.llama",
        api_base_url="https://test.api",
        stablecoins_base_url="https://test.stable",
        bridges_base_url="https://test.bridges",
        coins_base_url="https://test.coins",
        enable_optional_market_surfaces=False,
        transport=httpx.MockTransport(handler),
    )

    assert _run(provider.get_market_overview("fees")) is None
    assert _run(provider.get_market_summary("fees", "curve-finance")) is None
    assert _run(provider.get_stablecoin_snapshot()) is None
    assert _run(provider.get_bridge_snapshot()) is None
    assert calls["count"] == 0


def test_market_overview_and_summary_parse_when_enabled():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/overview/fees":
            return httpx.Response(
                200,
                json={
                    "total24h": 100.0,
                    "total7d": 700.0,
                    "change_1d": 1.2,
                    "change_7d": -3.1,
                    "allChains": ["Ethereum", "Base"],
                    "protocols": [
                        {"name": "Uniswap", "displayName": "Uniswap", "total24h": 10.0},
                        {"name": "Curve", "displayName": "Curve", "total24h": 8.0},
                    ],
                },
                request=request,
            )
        if path == "/summary/fees/curve-finance":
            return httpx.Response(
                200,
                json={"total24h": 8.0, "total7d": 56.0, "change_1d": 0.4},
                request=request,
            )
        return httpx.Response(404, json={}, request=request)

    provider = DeFiLlamaDataProvider(
        timeout_seconds=5,
        retry_attempts=0,
        cache_ttl_seconds={"overview": 0, "summary": 0},
        yields_base_url="https://test.llama",
        api_base_url="https://test.api",
        enable_optional_market_surfaces=True,
        transport=httpx.MockTransport(handler),
    )
    overview = _run(provider.get_market_overview("fees"))
    summary = _run(provider.get_market_summary("fees", "curve-finance"))

    assert overview is not None
    assert overview.category == "fees"
    assert overview.total_24h == 100.0
    assert overview.all_chains == ["Ethereum", "Base"]
    assert len(overview.protocols) == 2
    assert summary is not None
    assert summary.category == "fees"
    assert summary.protocol == "curve-finance"
    assert summary.total_24h == 8.0


def test_stablecoin_bridge_and_prices_parse():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/stablecoins":
            return httpx.Response(
                200,
                json={
                    "peggedAssets": [
                        {"id": 1, "name": "USD Coin", "symbol": "USDC", "pegType": "peggedUSD", "price": 1.0}
                    ],
                    "chains": [{"name": "Ethereum"}, {"name": "Base"}],
                },
                request=request,
            )
        if path == "/bridges":
            return httpx.Response(
                200,
                json={
                    "bridges": [
                        {"id": 56, "name": "Across", "displayName": "Across", "last24hVolume": 123.0}
                    ],
                    "chains": [{"name": "Ethereum"}],
                },
                request=request,
            )
        if path.startswith("/prices/current/"):
            return httpx.Response(
                200,
                json={"coins": {"coingecko:ethereum": {"symbol": "ETH", "price": 3000.0, "timestamp": 1700000000}}},
                request=request,
            )
        if path.startswith("/prices/historical/"):
            return httpx.Response(
                200,
                json={"coins": {"coingecko:ethereum": {"symbol": "ETH", "price": 2000.0, "timestamp": 1690000000}}},
                request=request,
            )
        return httpx.Response(404, json={}, request=request)

    provider = DeFiLlamaDataProvider(
        timeout_seconds=5,
        retry_attempts=0,
        cache_ttl_seconds={"stablecoins_snapshot": 0, "bridges_snapshot": 0, "prices_current": 0, "prices_historical": 0},
        yields_base_url="https://test.llama",
        stablecoins_base_url="https://test.stable",
        bridges_base_url="https://test.bridges",
        coins_base_url="https://test.coins",
        enable_optional_market_surfaces=True,
        transport=httpx.MockTransport(handler),
    )

    stable = _run(provider.get_stablecoin_snapshot())
    bridges = _run(provider.get_bridge_snapshot())
    prices_now = _run(provider.get_prices_current(["coingecko:ethereum"]))
    prices_hist = _run(provider.get_prices_historical(1690000000, ["coingecko:ethereum"]))

    assert stable is not None
    assert len(stable.assets) == 1
    assert stable.assets[0].symbol == "USDC"
    assert stable.chains == ["Ethereum", "Base"]
    assert bridges is not None
    assert len(bridges.bridges) == 1
    assert bridges.bridges[0].name == "Across"
    assert prices_now and prices_now[0].price == 3000.0
    assert prices_hist and prices_hist[0].price == 2000.0
