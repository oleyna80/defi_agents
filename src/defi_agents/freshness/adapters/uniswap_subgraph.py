from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
from typing import Iterable

import httpx

from ...scout.models import ScoutResult
from ..types import FreshnessSnapshot

logger = logging.getLogger(__name__)


class UniswapSubgraphAdapter:
    name = "uniswap_subgraph"

    def __init__(
        self,
        endpoints: dict[str, str] | None,
        timeout_seconds: int = 8,
        *,
        subgraph_ids: dict[str, str] | None = None,
        graph_api_key_env: str = "GRAPH_API_KEY",
        project_keywords: Iterable[str] = ("uniswap",),
        adapter_name: str | None = None,
    ) -> None:
        self.endpoints = dict(endpoints or {})
        self.subgraph_ids = dict(subgraph_ids or {})
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.graph_api_key_env = graph_api_key_env
        self.project_keywords = tuple(k.strip().lower() for k in project_keywords if k and k.strip())
        if adapter_name:
            self.name = adapter_name

    def supports(self, result: ScoutResult) -> bool:
        project = (result.candidate.project or "").lower()
        if not any(keyword in project for keyword in self.project_keywords):
            return False
        if not (result.candidate.address and result.candidate.chain):
            return False
        return self._endpoint_for_chain(result.candidate.chain) is not None

    async def fetch_snapshot(self, result: ScoutResult) -> FreshnessSnapshot | None:
        endpoint = self._endpoint_for_chain(result.candidate.chain or "")
        if not endpoint:
            return None
        pool_addr = (result.candidate.address or "").lower()
        if not pool_addr.startswith("0x"):
            return None

        snapshot = await self._fetch_hourly(endpoint, pool_addr)
        if snapshot:
            return snapshot
        return await self._fetch_daily(endpoint, pool_addr)

    def _endpoint_for_chain(self, chain: str) -> str | None:
        endpoint = self._lookup_case_insensitive(self.endpoints, chain)
        if endpoint:
            return self._resolve_endpoint(endpoint)
        subgraph_id = self._lookup_case_insensitive(self.subgraph_ids, chain)
        if subgraph_id:
            if subgraph_id.startswith(("http://", "https://")):
                return self._resolve_endpoint(subgraph_id)
            graph_key = os.getenv(self.graph_api_key_env, "").strip()
            if not graph_key:
                return None
            return f"https://gateway.thegraph.com/api/{graph_key}/subgraphs/id/{subgraph_id}"
        return None

    @staticmethod
    def _lookup_case_insensitive(mapping: dict[str, str], key: str) -> str | None:
        if key in mapping:
            return mapping[key]
        key_lower = key.lower()
        for candidate_key, value in mapping.items():
            if candidate_key.lower() == key_lower:
                return value
        return None

    def _resolve_endpoint(self, endpoint: str) -> str | None:
        if "{GRAPH_API_KEY}" not in endpoint:
            return endpoint
        graph_key = os.getenv(self.graph_api_key_env, "").strip()
        if not graph_key:
            return None
        return endpoint.replace("{GRAPH_API_KEY}", graph_key)

    async def _fetch_hourly(self, endpoint: str, pool_addr: str) -> FreshnessSnapshot | None:
        query = """
        query PoolHourSnapshot($pool: String!) {
          pool(id: $pool) {
            totalValueLockedUSD
          }
          poolHourDatas(
            first: 1
            orderBy: periodStartUnix
            orderDirection: desc
            where: { pool: $pool }
          ) {
            periodStartUnix
            tvlUSD
            feesUSD
          }
        }
        """
        data = await self._query(endpoint, query, {"pool": pool_addr})
        if not data:
            return None

        pool = data.get("pool") or {}
        hours = data.get("poolHourDatas") or []
        if not hours:
            return None
        hour = hours[0] if isinstance(hours[0], dict) else {}

        source_ts = _to_datetime(hour.get("periodStartUnix"))
        tvl = _to_float(hour.get("tvlUSD")) or _to_float(pool.get("totalValueLockedUSD"))
        fees = _to_float(hour.get("feesUSD"))
        apy = _annualize_fees(fees, tvl, periods_per_day=24.0)

        return FreshnessSnapshot(
            provider=self.name,
            source_timestamp=source_ts,
            apy=apy,
            tvl_usd=tvl,
        )

    async def _fetch_daily(self, endpoint: str, pool_addr: str) -> FreshnessSnapshot | None:
        query = """
        query PoolDaySnapshot($pool: String!) {
          pool(id: $pool) {
            totalValueLockedUSD
          }
          poolDayDatas(
            first: 1
            orderBy: date
            orderDirection: desc
            where: { pool: $pool }
          ) {
            date
            tvlUSD
            feesUSD
          }
        }
        """
        data = await self._query(endpoint, query, {"pool": pool_addr})
        if not data:
            return None

        pool = data.get("pool") or {}
        days = data.get("poolDayDatas") or []
        if not days:
            return None
        day = days[0] if isinstance(days[0], dict) else {}

        source_ts = _to_datetime(day.get("date"))
        tvl = _to_float(day.get("tvlUSD")) or _to_float(pool.get("totalValueLockedUSD"))
        fees = _to_float(day.get("feesUSD"))
        apy = _annualize_fees(fees, tvl, periods_per_day=1.0)

        return FreshnessSnapshot(
            provider=self.name,
            source_timestamp=source_ts,
            apy=apy,
            tvl_usd=tvl,
        )

    async def _query(self, endpoint: str, query: str, variables: dict) -> dict | None:
        payload = {"query": query, "variables": variables}
        try:
            async with httpx.AsyncClient(timeout=float(self.timeout_seconds)) as client:
                resp = await client.post(endpoint, json=payload)
            if not resp.is_success:
                logger.warning("Uniswap subgraph request failed: status=%s", resp.status_code)
                return None
            body = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Uniswap subgraph request error: %s", exc.__class__.__name__)
            return None

        if body.get("errors"):
            logger.warning("Uniswap subgraph returned GraphQL errors.")
            return None
        data = body.get("data")
        return data if isinstance(data, dict) else None


class AerodromeSubgraphAdapter(UniswapSubgraphAdapter):
    name = "aerodrome_subgraph"

    def __init__(
        self,
        endpoints: dict[str, str] | None,
        timeout_seconds: int = 8,
        *,
        subgraph_ids: dict[str, str] | None = None,
        graph_api_key_env: str = "GRAPH_API_KEY",
    ) -> None:
        super().__init__(
            endpoints=endpoints,
            timeout_seconds=timeout_seconds,
            subgraph_ids=subgraph_ids,
            graph_api_key_env=graph_api_key_env,
            project_keywords=("aerodrome", "slipstream", "velodrome"),
            adapter_name=self.name,
        )


def _to_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_datetime(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        ts = int(value)
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _annualize_fees(fees: float | None, tvl: float | None, periods_per_day: float) -> float | None:
    if fees is None or tvl is None:
        return None
    if tvl <= 0:
        return None
    return (fees * periods_per_day * 365.0 / tvl) * 100.0
