from __future__ import annotations

from datetime import datetime, timezone
import logging

import httpx

from ...scout.models import ScoutResult
from ..types import FreshnessSnapshot

logger = logging.getLogger(__name__)


class UniswapSubgraphAdapter:
    name = "uniswap_subgraph"

    def __init__(self, endpoints: dict[str, str], timeout_seconds: int = 8) -> None:
        self.endpoints = dict(endpoints or {})
        self.timeout_seconds = max(1, int(timeout_seconds))

    def supports(self, result: ScoutResult) -> bool:
        project = (result.candidate.project or "").lower()
        if "uniswap" not in project:
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
        if chain in self.endpoints:
            return self.endpoints[chain]
        chain_lower = chain.lower()
        for key, value in self.endpoints.items():
            if key.lower() == chain_lower:
                return value
        return None

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
