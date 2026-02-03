from __future__ import annotations

from typing import List

from .config import ScoutConfig
from .defillama_client import DeFiLlamaClient
from .cache import ScoutDeduper
from .models import PriorityTier, ScoutCandidate, ScoutResult
from ..security.auditor import SecurityAuditor
from ..security.models import SecurityStatus


class YieldScout:
    def __init__(
        self,
        config: ScoutConfig,
        client: DeFiLlamaClient,
        auditor: SecurityAuditor,
        deduper: ScoutDeduper | None = None,
    ) -> None:
        self.config = config
        self.client = client
        self.auditor = auditor
        self.deduper = deduper or ScoutDeduper()

    async def analyze(self) -> List[ScoutResult]:
        pools = await self.client.get_pools()
        filtered = self._apply_heuristics(pools)

        # Limit audit volume
        filtered = filtered[: self.config.max_audit_candidates]

        results: List[ScoutResult] = []
        for pool in filtered:
            if not pool.address or pool.chain_id is None:
                continue

            target_type = pool.address_source or "TOKEN"
            sec = await self.auditor.evaluate(pool.address, str(pool.chain_id))
            if sec.status in {SecurityStatus.TRUSTED, SecurityStatus.PASS, SecurityStatus.WARN}:
                net_apy = self._calculate_net_apy(pool)
                net_profit = self._estimate_monthly_profit_usd(net_apy)
                score = self._calculate_score(pool, sec)
                results.append(
                    ScoutResult(
                        candidate=pool,
                        security=sec,
                        net_apy=net_apy,
                        score=score,
                        net_profit_usd=net_profit,
                        priority=self._classify_priority(pool),
                        metadata={
                            "target_address": pool.address,
                            "target_type": target_type,
                            "chain_id": str(pool.chain_id),
                        },
                        flags=self._flags(pool),
                    )
                )

        deduped = self._deduplicate(results)
        return sorted(deduped, key=lambda x: x.score, reverse=True)

    def _apply_heuristics(self, pools: List[ScoutCandidate]) -> List[ScoutCandidate]:
        candidates: List[ScoutCandidate] = []
        for pool in pools:
            if pool.tvl_usd < self.config.min_tvl_usd:
                continue
            # Yield quality check
            if pool.yield_quality < self.config.yield_quality_min:
                continue
            # Volatility check
            if self._is_unstable(pool):
                continue
            candidates.append(pool)

        # Sort by preliminary score (yield quality * apy)
        candidates.sort(key=lambda p: (p.yield_quality * (p.apy or 0.0)), reverse=True)
        return candidates

    def _classify_priority(self, pool: ScoutCandidate) -> PriorityTier:
        if pool.stablecoin is True:
            return PriorityTier.LOW_VOLATILITY

        symbols = [s.strip().upper() for s in (pool.symbol or "").split("-") if s.strip()]
        if any(sym in self.config.stable_symbols for sym in symbols):
            return PriorityTier.COIN_STABLE

        return PriorityTier.COIN_COIN

    def _is_unstable(self, pool: ScoutCandidate) -> bool:
        if pool.apy_mean_30d is None or pool.apy_mean_30d <= 0:
            return False
        return pool.apy >= (pool.apy_mean_30d * self.config.apy_anomaly_ratio)

    def _calculate_net_apy(self, pool: ScoutCandidate) -> float:
        # Placeholder: net APY discounts reward-heavy yields
        return (pool.apy_base or 0.0) + (pool.apy_reward or 0.0) * 0.5

    def _calculate_score(self, pool: ScoutCandidate, security) -> float:
        # Combine yield quality and security status
        base = (pool.apy or 0.0) * pool.yield_quality
        sec_factor = 1.0
        if security.status == SecurityStatus.TRUSTED:
            sec_factor = 1.0
        elif security.status == SecurityStatus.PASS:
            sec_factor = 0.9
        elif security.status == SecurityStatus.WARN:
            sec_factor = 0.6
        return base * sec_factor

    def _estimate_monthly_profit_usd(self, net_apy: float) -> float:
        # net_apy is annual percentage; estimate monthly profit on deposit_usd
        deposit = self.config.gas_efficiency.deposit_usd
        gross_monthly = deposit * (net_apy / 100.0) / 12.0
        # assume gas budget as % of deposit (entry+exit)
        gas_cost = deposit * (self.config.gas_efficiency.budget_pct / 100.0)
        return gross_monthly - gas_cost

    def _flags(self, pool: ScoutCandidate) -> List[str]:
        flags: List[str] = []
        if pool.yield_quality < self.config.yield_quality_min:
            flags.append("SUBSIDIZED")
        if self._is_unstable(pool):
            flags.append("UNSTABLE")
        return flags

    def _deduplicate(self, results: List[ScoutResult]) -> List[ScoutResult]:
        unique: dict[str, ScoutResult] = {}
        for res in results:
            symbols = "-".join(sorted((res.candidate.symbol or "").split("-")))
            key = f"{res.candidate.chain}:{symbols}".lower()
            best = unique.get(key)
            if not best:
                unique[key] = res
                continue

            # Prefer higher security status, then higher score
            if self._security_rank(res) > self._security_rank(best):
                unique[key] = res
            elif res.score > best.score:
                unique[key] = res

        # Anti-spam: drop items seen recently (unchanged)
        filtered: List[ScoutResult] = []
        for key, res in unique.items():
            if self.deduper.seen_recently(key, res.score):
                continue
            self.deduper.update(key, res.score)
            filtered.append(res)
        return filtered

    def _security_rank(self, res: ScoutResult) -> int:
        if not res.security:
            return 0
        status = res.security.status
        return {
            SecurityStatus.TRUSTED: 3,
            SecurityStatus.PASS: 2,
            SecurityStatus.WARN: 1,
        }.get(status, 0)
