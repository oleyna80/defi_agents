from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Iterable, List

from ..scout.config import FreshnessConfig
from ..scout.models import ScoutResult
from .adapters import AaveDirectAdapter, AerodromeSubgraphAdapter, FreshnessAdapter, UniswapSubgraphAdapter
from .types import FreshnessSnapshot


class FreshnessManager:
    def __init__(
        self,
        config: FreshnessConfig,
        adapters: Iterable[FreshnessAdapter] | None = None,
    ) -> None:
        self.config = config
        self.adapters = list(adapters or self._default_adapters(config))

    async def recheck(self, results: List[ScoutResult]) -> None:
        if not self.config.recheck_enabled or not results:
            return

        max_candidates = max(0, int(self.config.recheck_max_candidates))
        if max_candidates == 0:
            return

        sorted_candidates = sorted(results, key=lambda r: r.score, reverse=True)
        for result in sorted_candidates[:max_candidates]:
            await self._recheck_one(result)

    async def _recheck_one(self, result: ScoutResult) -> None:
        adapter = next((a for a in self.adapters if a.supports(result)), None)
        if adapter is None:
            return
        try:
            snapshot = await asyncio.wait_for(
                adapter.fetch_snapshot(result),
                timeout=max(1, int(self.config.recheck_timeout_seconds)),
            )
        except Exception:  # noqa: BLE001
            snapshot = None
        if snapshot is None:
            return
        self._apply_snapshot(result, snapshot)

    def _apply_snapshot(self, result: ScoutResult, snapshot: FreshnessSnapshot) -> None:
        now = datetime.now(timezone.utc)
        age_minutes = _age_minutes(snapshot.source_timestamp, now)
        staleness_score = _staleness_score(age_minutes, int(self.config.max_age_minutes))
        apy_div = _pct_divergence(result.candidate.apy, snapshot.apy)
        tvl_div = _pct_divergence(result.candidate.tvl_usd, snapshot.tvl_usd)

        freshness_status = "UNVERIFIED"
        if age_minutes is not None:
            freshness_status = "FRESH" if age_minutes <= int(self.config.max_age_minutes) else "STALE"

        meta = result.metadata
        meta["freshness_provider"] = snapshot.provider
        meta["source_timestamp"] = snapshot.source_timestamp.isoformat() if snapshot.source_timestamp else ""
        meta["age_minutes"] = str(age_minutes) if age_minutes is not None else ""
        meta["staleness_score"] = f"{staleness_score:.2f}" if staleness_score is not None else ""
        meta["apy_divergence_pct"] = f"{apy_div:.2f}" if apy_div is not None else ""
        meta["tvl_divergence_pct"] = f"{tvl_div:.2f}" if tvl_div is not None else ""
        meta["freshness_status"] = freshness_status

    @staticmethod
    def _default_adapters(config: FreshnessConfig) -> List[FreshnessAdapter]:
        return [
            UniswapSubgraphAdapter(
                endpoints=config.uniswap_subgraph_endpoints,
                subgraph_ids=config.uniswap_subgraph_ids,
                graph_api_key_env=config.graph_api_key_env,
                timeout_seconds=config.recheck_timeout_seconds,
            ),
            AerodromeSubgraphAdapter(
                endpoints=config.aerodrome_subgraph_endpoints,
                subgraph_ids=config.aerodrome_subgraph_ids,
                graph_api_key_env=config.graph_api_key_env,
                timeout_seconds=config.recheck_timeout_seconds,
            ),
            AaveDirectAdapter(
                enabled=config.aave_direct_enabled,
                timeout_seconds=config.aave_direct_timeout_seconds,
                endpoints=config.aave_direct_endpoints,
                reserve_symbols=config.aave_direct_reserve_symbols,
                api_key_env=config.aave_direct_api_key_env,
            ),
        ]


def _pct_divergence(observed: float | None, reference: float | None) -> float | None:
    if observed in (None, 0) or reference in (None, 0):
        return None
    base = abs(float(reference))
    if base < 1e-9:
        return None
    return abs(float(observed) - float(reference)) / base * 100.0


def _age_minutes(ts: datetime | None, now: datetime) -> int | None:
    if ts is None:
        return None
    return max(0, int((now - ts).total_seconds() // 60))


def _staleness_score(age_minutes: int | None, max_age: int) -> float | None:
    if age_minutes is None:
        return None
    limit = max(1, int(max_age))
    return min(100.0, (float(age_minutes) / float(limit)) * 100.0)
