from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any, Protocol

import httpx

from .models import DegradationReason, PoolState, TickData

logger = logging.getLogger(__name__)


class TickProviderError(RuntimeError):
    def __init__(self, reason: DegradationReason, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class TickDataProvider(Protocol):
    async def get_pool_ticks(self, pool_address: str, lower: int, upper: int) -> list[TickData]:
        ...

    async def get_pool_state(self, pool_address: str) -> PoolState:
        ...

    def protocol_fee_pct(self) -> float:
        ...


class UniswapV3TickProvider:
    _TICK_PAGE_SIZE = 1000
    _FEE_TIER_TO_TICK_SPACING = {
        100: 1,
        500: 10,
        3000: 60,
        10000: 200,
    }

    def __init__(
        self,
        *,
        endpoint: str | None = None,
        subgraph_id: str | None = None,
        graph_api_key_env: str = "GRAPH_API_KEY",
        timeout_seconds: int = 5,
        retry_attempts: int = 3,
        max_pages_per_pool: int = 100,
        max_ticks_per_pool: int = 50_000,
    ) -> None:
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.retry_attempts = max(0, int(retry_attempts))
        self.max_pages_per_pool = max(1, int(max_pages_per_pool))
        self.max_ticks_per_pool = max(1, int(max_ticks_per_pool))
        self.graph_api_key_env = graph_api_key_env
        self.endpoint = self._resolve_endpoint(endpoint=endpoint, subgraph_id=subgraph_id)
        self._last_fee_tier: int | None = None

    async def get_pool_ticks(self, pool_address: str, lower: int, upper: int) -> list[TickData]:
        if lower > upper:
            return []
        pool = (pool_address or "").strip().lower()
        if not pool.startswith("0x"):
            return []

        ticks: list[TickData] = []
        pages = 0
        last_tick = lower - 1

        while True:
            pages += 1
            if pages > self.max_pages_per_pool or len(ticks) > self.max_ticks_per_pool:
                raise TickProviderError(
                    DegradationReason.PAGINATION_LIMIT_REACHED,
                    "Tick pagination exceeded configured limits.",
                )

            payload = {
                "query": """
                query PoolTicks($pool: String!, $lower: BigInt!, $upper: BigInt!, $lastTick: BigInt!, $first: Int!) {
                  ticks(
                    first: $first
                    orderBy: tickIdx
                    orderDirection: asc
                    where: {
                      pool: $pool
                      tickIdx_gte: $lower
                      tickIdx_lte: $upper
                      tickIdx_gt: $lastTick
                    }
                  ) {
                    tickIdx
                    liquidityNet
                    liquidityGross
                  }
                }
                """,
                "variables": {
                    "pool": pool,
                    "lower": int(lower),
                    "upper": int(upper),
                    "lastTick": int(last_tick),
                    "first": int(self._TICK_PAGE_SIZE),
                },
            }
            data = await self._query(payload)
            rows = data.get("ticks", []) if isinstance(data, dict) else []
            if not isinstance(rows, list):
                raise TickProviderError(DegradationReason.SUBGRAPH_ERROR, "Invalid ticks payload shape.")
            if not rows:
                break

            page_ticks: list[TickData] = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                tick_idx = _to_int(row.get("tickIdx"))
                liq_net = _to_int(row.get("liquidityNet"))
                liq_gross = _to_int(row.get("liquidityGross"), default=0)
                if tick_idx is None or liq_net is None:
                    continue
                page_ticks.append(
                    TickData(
                        tick_index=tick_idx,
                        liquidity_net=liq_net,
                        liquidity_gross=liq_gross or 0,
                    )
                )
            if not page_ticks:
                break
            ticks.extend(page_ticks)
            if len(ticks) > self.max_ticks_per_pool:
                raise TickProviderError(
                    DegradationReason.PAGINATION_LIMIT_REACHED,
                    "Tick list exceeded configured max_ticks_per_pool.",
                )
            last_tick = page_ticks[-1].tick_index
            if len(rows) < self._TICK_PAGE_SIZE:
                break

        return ticks

    async def get_pool_state(self, pool_address: str) -> PoolState:
        pool = (pool_address or "").strip().lower()
        if not pool.startswith("0x"):
            raise TickProviderError(DegradationReason.SUBGRAPH_ERROR, "Invalid pool address.")

        payload = {
            "query": """
            query PoolState($pool: String!) {
              pool(id: $pool) {
                id
                tick
                liquidity
                sqrtPrice
                feeTier
                token0 { decimals }
                token1 { decimals }
              }
            }
            """,
            "variables": {"pool": pool},
        }
        data = await self._query(payload)
        pool_data = data.get("pool") if isinstance(data, dict) else None
        if not isinstance(pool_data, dict):
            raise TickProviderError(DegradationReason.SUBGRAPH_ERROR, "Pool not found in subgraph response.")

        fee_tier = _to_int(pool_data.get("feeTier"))
        tick_spacing = self._tick_spacing_for_fee_tier(fee_tier)
        state = PoolState(
            pool_address=pool,
            tick=_to_int(pool_data.get("tick"), default=0) or 0,
            liquidity=_to_int(pool_data.get("liquidity"), default=0) or 0,
            sqrt_price_x96=_to_int(pool_data.get("sqrtPrice"), default=0) or 0,
            fee_tier=fee_tier or 0,
            tick_spacing=tick_spacing,
            token0_decimals=_extract_decimals(pool_data.get("token0")),
            token1_decimals=_extract_decimals(pool_data.get("token1")),
        )
        self._last_fee_tier = state.fee_tier
        return state

    def protocol_fee_pct(self) -> float:
        if self._last_fee_tier is None:
            return 0.0
        return float(self._last_fee_tier) / 10_000.0

    def _resolve_endpoint(self, *, endpoint: str | None, subgraph_id: str | None) -> str:
        if endpoint and endpoint.strip():
            return self._inject_graph_key(endpoint.strip())
        if not subgraph_id:
            raise ValueError("Either `endpoint` or `subgraph_id` must be provided for UniswapV3TickProvider.")
        if subgraph_id.startswith(("http://", "https://")):
            return self._inject_graph_key(subgraph_id)
        graph_key = os.getenv(self.graph_api_key_env, "").strip()
        if not graph_key:
            raise ValueError(f"Missing env `{self.graph_api_key_env}` required to resolve Graph subgraph id.")
        return f"https://gateway.thegraph.com/api/{graph_key}/subgraphs/id/{subgraph_id}"

    def _inject_graph_key(self, value: str) -> str:
        if "{GRAPH_API_KEY}" not in value:
            return value
        graph_key = os.getenv(self.graph_api_key_env, "").strip()
        if not graph_key:
            raise ValueError(f"Missing env `{self.graph_api_key_env}` for endpoint template expansion.")
        return value.replace("{GRAPH_API_KEY}", graph_key)

    async def _query(self, payload: dict[str, Any]) -> dict[str, Any]:
        safe_endpoint = self._sanitize_endpoint(self.endpoint)
        for attempt in range(self.retry_attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=float(self.timeout_seconds)) as client:
                    response = await client.post(self.endpoint, json=payload)
                if not response.is_success:
                    logger.warning("Uniswap tick provider HTTP failure: status=%s endpoint=%s", response.status_code, safe_endpoint)
                    if attempt >= self.retry_attempts:
                        raise TickProviderError(
                            DegradationReason.SUBGRAPH_ERROR,
                            f"Uniswap subgraph HTTP failure: {response.status_code}",
                        )
                    await asyncio.sleep(2 ** attempt)
                    continue
                body = response.json()
                if body.get("errors"):
                    logger.warning("Uniswap tick provider GraphQL errors endpoint=%s", safe_endpoint)
                    if attempt >= self.retry_attempts:
                        raise TickProviderError(DegradationReason.SUBGRAPH_ERROR, "GraphQL errors in subgraph response.")
                    await asyncio.sleep(2 ** attempt)
                    continue
                data = body.get("data")
                if not isinstance(data, dict):
                    if attempt >= self.retry_attempts:
                        raise TickProviderError(DegradationReason.SUBGRAPH_ERROR, "Missing GraphQL `data` object.")
                    await asyncio.sleep(2 ** attempt)
                    continue
                return data
            except httpx.TimeoutException:
                logger.warning("Uniswap tick provider timeout endpoint=%s", safe_endpoint)
                if attempt >= self.retry_attempts:
                    raise TickProviderError(DegradationReason.SUBGRAPH_TIMEOUT, "Subgraph request timed out.")
                await asyncio.sleep(2 ** attempt)
            except TickProviderError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("Uniswap tick provider request error endpoint=%s err=%s", safe_endpoint, exc.__class__.__name__)
                if attempt >= self.retry_attempts:
                    raise TickProviderError(DegradationReason.SUBGRAPH_ERROR, "Unhandled request error.") from exc
                await asyncio.sleep(2 ** attempt)

        raise TickProviderError(DegradationReason.SUBGRAPH_ERROR, "Unknown subgraph query error.")

    @classmethod
    def _tick_spacing_for_fee_tier(cls, fee_tier: int | None) -> int:
        if fee_tier is None:
            return 1
        return cls._FEE_TIER_TO_TICK_SPACING.get(int(fee_tier), 1)

    @staticmethod
    def _sanitize_endpoint(endpoint: str) -> str:
        return re.sub(r"/api/[^/]+/", "/api/***/", endpoint)


def _to_int(value: object, *, default: int | None = None) -> int | None:
    if value in (None, ""):
        return default
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def _extract_decimals(token_data: object) -> int:
    if not isinstance(token_data, dict):
        return 18
    decimals = _to_int(token_data.get("decimals"), default=18)
    if decimals is None:
        return 18
    return max(0, decimals)
