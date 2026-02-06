from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import os
from typing import Any

import httpx

from .config import ScoutConfig
from .models import ScoutCandidate

logger = logging.getLogger(__name__)


@dataclass
class DexDiscoveryStats:
    dex_llama_count: int = 0
    dex_uniswap_new_count: int = 0
    dex_filtered_count: int = 0
    dex_error_count: int = 0
    dex_timeout_count: int = 0
    dex_discovery_total: int = 0


@dataclass
class NewPoolsDiscoveryResult:
    candidates: list[ScoutCandidate] = field(default_factory=list)
    metadata_by_pool_id: dict[str, dict[str, str]] = field(default_factory=dict)
    stats: DexDiscoveryStats = field(default_factory=DexDiscoveryStats)


class UniswapV3NewPoolsAdapter:
    def __init__(self, config: ScoutConfig) -> None:
        self.config = config

    async def fetch_new_pools(self, chains: list[str] | None = None) -> NewPoolsDiscoveryResult:
        cfg = self.config.dex_discovery.uniswap_v3_new_pools
        result = NewPoolsDiscoveryResult()
        if not cfg.enabled:
            return result

        target_chains = chains if chains else list(cfg.subgraph_endpoints.keys() or cfg.subgraph_ids.keys())
        if not target_chains:
            return result

        per_chain_limit = max(1, int(cfg.max_pools))
        for chain in target_chains:
            endpoint = self._endpoint_for_chain(chain)
            if not endpoint:
                continue
            try:
                chain_rows = await self._fetch_chain_rows(endpoint)
            except httpx.TimeoutException:
                result.stats.dex_timeout_count += 1
                continue
            except Exception as exc:  # noqa: BLE001
                logger.warning("Uniswap new-pools adapter error: chain=%s err=%s", chain, exc.__class__.__name__)
                result.stats.dex_error_count += 1
                continue

            selected = 0
            for row in chain_rows:
                if selected >= per_chain_limit:
                    break
                candidate = self._row_to_candidate(chain, row)
                if candidate is None:
                    result.stats.dex_filtered_count += 1
                    continue
                if candidate.tvl_usd < float(cfg.min_tvl_usd):
                    result.stats.dex_filtered_count += 1
                    continue
                selected += 1
                result.candidates.append(candidate)
                result.metadata_by_pool_id[candidate.pool_id] = {
                    "dex_new_pool": "true",
                    "pool_age_minutes": self._pool_age_minutes_str(candidate.timestamp),
                    "source_timestamp": self._source_timestamp_str(candidate.timestamp),
                    "freshness_status": "UNVERIFIED",
                }

        result.stats.dex_uniswap_new_count = len(result.candidates)
        return result

    async def _fetch_chain_rows(self, endpoint: str) -> list[dict[str, Any]]:
        cfg = self.config.dex_discovery.uniswap_v3_new_pools
        page_size = max(1, int(cfg.page_size))
        max_pages = max(1, int(cfg.max_pages))
        all_rows: list[dict[str, Any]] = []

        for page in range(max_pages):
            skip = page * page_size
            data = await self._query(
                endpoint,
                """
                query NewPools($first: Int!, $skip: Int!, $orderBy: Pool_orderBy!, $orderDirection: OrderDirection!) {
                  pools(first: $first, skip: $skip, orderBy: $orderBy, orderDirection: $orderDirection) {
                    id
                    createdAtTimestamp
                    totalValueLockedUSD
                    token0 { symbol }
                    token1 { symbol }
                  }
                }
                """,
                {
                    "first": page_size,
                    "skip": skip,
                    "orderBy": cfg.order_by,
                    "orderDirection": cfg.order_direction,
                },
                timeout_seconds=max(1, int(cfg.timeout_seconds)),
            )
            rows = data.get("pools") if isinstance(data, dict) else None
            if not isinstance(rows, list) or not rows:
                break
            all_rows.extend([r for r in rows if isinstance(r, dict)])
            if len(rows) < page_size:
                break

        return all_rows

    def _row_to_candidate(self, chain: str, row: dict[str, Any]) -> ScoutCandidate | None:
        pool_id = str(row.get("id") or "").strip().lower()
        ts_raw = row.get("createdAtTimestamp")
        tvl_raw = row.get("totalValueLockedUSD")
        token0 = self._token_symbol(row.get("token0"))
        token1 = self._token_symbol(row.get("token1"))
        if not pool_id or not token0 or not token1:
            return None

        try:
            created_ts = int(ts_raw)
            tvl = float(tvl_raw)
        except (TypeError, ValueError):
            return None

        chain_id = self.config.chain_id_map.get(chain)
        if chain_id is None:
            for key, value in self.config.chain_id_map.items():
                if key.lower() == chain.lower():
                    chain_id = value
                    break

        return ScoutCandidate.model_validate(
            {
                "pool": pool_id,
                "project": "Uniswap V3",
                "chain": chain,
                "symbol": f"{token0}-{token1}",
                "address": pool_id,
                "chain_id": chain_id,
                "tvlUsd": tvl,
                # Keep discovery candidates compatible with existing Scout heuristics
                # (yield_quality uses apy/apyBase and requires apy > 0).
                "apy": max(float(self.config.min_apy), 0.01),
                "apyBase": max(float(self.config.min_apy), 0.01),
                "apyReward": 0.0,
                "timestamp": created_ts,
            }
        )

    @staticmethod
    def _token_symbol(token_obj: object) -> str:
        if not isinstance(token_obj, dict):
            return ""
        return str(token_obj.get("symbol") or "").strip().upper()

    @staticmethod
    def _pool_age_minutes_str(created_ts: int | None) -> str:
        if not created_ts:
            return ""
        now_ts = int(datetime.now(timezone.utc).timestamp())
        return str(max(0, int((now_ts - int(created_ts)) // 60)))

    @staticmethod
    def _source_timestamp_str(created_ts: int | None) -> str:
        if not created_ts:
            return ""
        return datetime.fromtimestamp(int(created_ts), tz=timezone.utc).isoformat()

    def _endpoint_for_chain(self, chain: str) -> str | None:
        cfg = self.config.dex_discovery.uniswap_v3_new_pools
        endpoint = self._lookup_case_insensitive(cfg.subgraph_endpoints, chain)
        if endpoint:
            return self._resolve_endpoint(endpoint)

        subgraph_id = self._lookup_case_insensitive(cfg.subgraph_ids, chain)
        if not subgraph_id:
            return None
        if subgraph_id.startswith(("http://", "https://")):
            return self._resolve_endpoint(subgraph_id)
        graph_key = os.getenv(cfg.graph_api_key_env, "").strip()
        if not graph_key:
            return None
        return f"https://gateway.thegraph.com/api/{graph_key}/subgraphs/id/{subgraph_id}"

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
        cfg = self.config.dex_discovery.uniswap_v3_new_pools
        if "{GRAPH_API_KEY}" not in endpoint:
            return endpoint
        graph_key = os.getenv(cfg.graph_api_key_env, "").strip()
        if not graph_key:
            return None
        return endpoint.replace("{GRAPH_API_KEY}", graph_key)

    async def _query(self, endpoint: str, query: str, variables: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
        payload = {"query": query, "variables": variables}
        async with httpx.AsyncClient(timeout=float(timeout_seconds)) as client:
            resp = await client.post(endpoint, json=payload)
        resp.raise_for_status()
        body = resp.json()
        if body.get("errors"):
            raise RuntimeError("graphql_errors")
        data = body.get("data")
        if not isinstance(data, dict):
            raise RuntimeError("invalid_graphql_data")
        return data
