from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import time
from typing import Any

import httpx

from .defillama_models import (
    BridgeSnapshotFact,
    MarketOverviewFact,
    MarketSummaryFact,
    PriceFact,
    StablecoinSnapshotFact,
    YieldPoolFact,
    YieldPoolHistoryPoint,
)
from .defillama_parsers import (
    parse_bridge_snapshot,
    parse_data_list_payload,
    parse_market_overview,
    parse_market_summary,
    parse_price_map,
    parse_stablecoin_snapshot,
    parse_yield_pool_facts,
    parse_yield_pool_history,
)


@dataclass
class _CacheEntry:
    expires_at: float
    payload: Any


class DeFiLlamaDataProvider:
    """Centralized, fail-safe DeFiLlama HTTP provider with bounded retries and cache."""

    def __init__(
        self,
        timeout_seconds: float = 8.0,
        retry_attempts: int = 2,
        cache_ttl_seconds: dict[str, int] | None = None,
        yields_base_url: str = "https://yields.llama.fi",
        api_base_url: str = "https://api.llama.fi",
        stablecoins_base_url: str = "https://stablecoins.llama.fi",
        bridges_base_url: str = "https://bridges.llama.fi",
        coins_base_url: str = "https://coins.llama.fi",
        enable_optional_market_surfaces: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._timeout = float(timeout_seconds)
        self._retry_attempts = max(0, int(retry_attempts))
        self._cache_ttl = dict(cache_ttl_seconds or {})
        self._yields_base = yields_base_url.rstrip("/")
        self._api_base = api_base_url.rstrip("/")
        self._stablecoins_base = stablecoins_base_url.rstrip("/")
        self._bridges_base = bridges_base_url.rstrip("/")
        self._coins_base = coins_base_url.rstrip("/")
        self._enable_optional_market_surfaces = bool(enable_optional_market_surfaces)
        self._transport = transport
        self._cache: dict[str, _CacheEntry] = {}
        self._counters: dict[str, dict[str, int]] = {}

    async def get_yield_pools_raw(self) -> list[dict]:
        payload = await self._fetch_json("yields_pools", f"{self._yields_base}/pools")
        rows = parse_data_list_payload(payload)
        if rows is None:
            self._inc("yields_pools", "parse_error_count")
            return []
        return rows

    async def get_yield_pools_old_raw(self) -> list[dict]:
        payload = await self._fetch_json("yields_pools_old", f"{self._yields_base}/poolsOld")
        rows = parse_data_list_payload(payload)
        if rows is None:
            self._inc("yields_pools_old", "parse_error_count")
            return []
        return rows

    async def get_yield_pool_history_raw(self, pool_id: str) -> list[dict]:
        key = f"yields_chart:{pool_id}"
        payload = await self._fetch_json(key, f"{self._yields_base}/chart/{pool_id}")
        rows = parse_data_list_payload(payload)
        if rows is None:
            self._inc(key, "parse_error_count")
            return []
        return rows

    async def get_yield_pools(self) -> list[YieldPoolFact]:
        rows = await self.get_yield_pools_raw()
        return parse_yield_pool_facts(rows)

    async def get_yield_pool_history(self, pool_id: str) -> list[YieldPoolHistoryPoint]:
        rows = await self.get_yield_pool_history_raw(pool_id)
        return parse_yield_pool_history(rows)

    async def get_market_overview(self, category: str) -> MarketOverviewFact | None:
        if not self._enable_optional_market_surfaces:
            return None
        endpoint = f"overview:{category}"
        url = (
            f"{self._api_base}/overview/{category}"
            f"?excludeTotalDataChart=true&excludeTotalDataChartBreakdown=true"
        )
        payload = await self._fetch_json(endpoint, url)
        fact = parse_market_overview(category, payload)
        if fact is None:
            self._inc(endpoint, "parse_error_count")
        return fact

    async def get_market_summary(self, category: str, protocol: str) -> MarketSummaryFact | None:
        if not self._enable_optional_market_surfaces:
            return None
        endpoint = f"summary:{category}:{protocol}"
        url = f"{self._api_base}/summary/{category}/{protocol}"
        payload = await self._fetch_json(endpoint, url)
        fact = parse_market_summary(category, protocol, payload)
        if fact is None:
            self._inc(endpoint, "parse_error_count")
        return fact

    async def get_stablecoin_snapshot(self) -> StablecoinSnapshotFact | None:
        if not self._enable_optional_market_surfaces:
            return None
        endpoint = "stablecoins_snapshot"
        url = f"{self._stablecoins_base}/stablecoins?includePrices=true"
        payload = await self._fetch_json(endpoint, url)
        fact = parse_stablecoin_snapshot(payload)
        if fact is None:
            self._inc(endpoint, "parse_error_count")
        return fact

    async def get_bridge_snapshot(self) -> BridgeSnapshotFact | None:
        if not self._enable_optional_market_surfaces:
            return None
        endpoint = "bridges_snapshot"
        url = f"{self._bridges_base}/bridges?includeChains=true"
        payload = await self._fetch_json(endpoint, url)
        fact = parse_bridge_snapshot(payload)
        if fact is None:
            self._inc(endpoint, "parse_error_count")
        return fact

    async def get_prices_current(self, keys: list[str]) -> list[PriceFact]:
        if not keys:
            return []
        endpoint = "prices_current"
        joined = ",".join(keys)
        url = f"{self._coins_base}/prices/current/{joined}"
        payload = await self._fetch_json(endpoint, url)
        prices = parse_price_map(payload)
        if payload is None:
            return []
        if not prices:
            self._inc(endpoint, "parse_error_count")
        return prices

    async def get_prices_historical(self, timestamp: int, keys: list[str]) -> list[PriceFact]:
        if not keys:
            return []
        endpoint = f"prices_historical:{int(timestamp)}"
        joined = ",".join(keys)
        url = f"{self._coins_base}/prices/historical/{int(timestamp)}/{joined}"
        payload = await self._fetch_json(endpoint, url)
        prices = parse_price_map(payload)
        if payload is None:
            return []
        if not prices:
            self._inc(endpoint, "parse_error_count")
        return prices

    def get_counters(self) -> dict[str, dict[str, int]]:
        return {name: dict(values) for name, values in self._counters.items()}

    async def _fetch_json(self, endpoint: str, url: str) -> Any | None:
        cached = self._cache_get(endpoint)
        if cached is not None:
            self._inc(endpoint, "cache_hit_count")
            return cached

        last_error: Exception | None = None
        attempts = self._retry_attempts + 1
        for attempt in range(attempts):
            self._inc(endpoint, "request_count")
            try:
                async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
                    response = await client.get(url)
                    response.raise_for_status()
                    payload = response.json()
                self._inc(endpoint, "success_count")
                self._cache_set(endpoint, payload)
                return payload
            except httpx.TimeoutException as exc:
                last_error = exc
                self._inc(endpoint, "timeout_count")
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                self._inc(endpoint, "error_count")

            if attempt < attempts - 1:
                await asyncio.sleep(min(0.25 * (attempt + 1), 1.0))

        # Non-fatal by design for Scout pipeline.
        _ = last_error
        return None

    def _cache_get(self, endpoint: str) -> Any | None:
        entry = self._cache.get(endpoint)
        if entry is None:
            return None
        if entry.expires_at <= time():
            self._cache.pop(endpoint, None)
            return None
        return entry.payload

    def _cache_set(self, endpoint: str, payload: Any) -> None:
        ttl = self._ttl_for(endpoint)
        if ttl <= 0:
            return
        self._cache[endpoint] = _CacheEntry(expires_at=time() + ttl, payload=payload)

    def _ttl_for(self, endpoint: str) -> int:
        if endpoint in self._cache_ttl:
            return max(0, int(self._cache_ttl.get(endpoint, 0) or 0))
        if endpoint.startswith("yields_chart:"):
            return max(0, int(self._cache_ttl.get("yields_chart", 0) or 0))
        if endpoint.startswith("overview:"):
            return max(0, int(self._cache_ttl.get("overview", 0) or 0))
        if endpoint.startswith("summary:"):
            return max(0, int(self._cache_ttl.get("summary", 0) or 0))
        if endpoint.startswith("prices_historical:"):
            return max(0, int(self._cache_ttl.get("prices_historical", 0) or 0))
        return 0

    def _inc(self, endpoint: str, field: str) -> None:
        row = self._counters.setdefault(
            endpoint,
            {
                "request_count": 0,
                "success_count": 0,
                "timeout_count": 0,
                "error_count": 0,
                "parse_error_count": 0,
                "cache_hit_count": 0,
            },
        )
        row[field] = row.get(field, 0) + 1
