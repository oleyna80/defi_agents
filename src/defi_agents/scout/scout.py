from __future__ import annotations

from collections import Counter
import logging
from typing import List, Tuple

from .config import ScoutConfig
from .defillama_client import DeFiLlamaClient
from .cache import ScoutDeduper
from .models import PriorityTier, ScoutCandidate, ScoutResult
from ..security.auditor import SecurityAuditor
from ..security.models import SecurityReason, SecuritySeverity, SecuritySource, SecurityStatus

logger = logging.getLogger(__name__)


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
        raw_count = len(pools)
        filtered = self._apply_heuristics(pools)
        heuristics_count = len(filtered)

        # Prioritize and select *addressable* candidates for security checks.
        # This avoids wasting the audit budget on items without chain_id/address.
        missing_address = 0
        missing_chain_id = 0
        addressable_total = 0
        addressable_candidates: List[ScoutCandidate] = []
        for pool in self._prioritize(filtered):
            if not pool.address:
                missing_address += 1
            if pool.chain_id is None:
                missing_chain_id += 1
            if pool.address and pool.chain_id is not None:
                addressable_total += 1
                if len(addressable_candidates) < self.config.max_audit_candidates:
                    addressable_candidates.append(pool)

        results: List[ScoutResult] = []
        security_counts = {s.value: 0 for s in SecurityStatus}
        lindy_softened = 0
        reason_counts: Counter[str] = Counter()
        tactical_filtered = 0
        capacity_filtered = 0
        cost_filtered = 0

        for pool in addressable_candidates:
            # address + chain_id are guaranteed by selection above
            assert pool.address and pool.chain_id is not None

            target_type = pool.address_source or "TOKEN"
            sec = await self.auditor.evaluate(pool.address, str(pool.chain_id))
            if self._maybe_apply_lindy(pool, sec):
                lindy_softened += 1

            if sec.status.value in security_counts:
                security_counts[sec.status.value] += 1
            if sec.status in {SecurityStatus.WARN, SecurityStatus.BLOCK, SecurityStatus.UNKNOWN}:
                for reason in sec.reasons:
                    reason_counts[reason.code] += 1

            if sec.status in {SecurityStatus.TRUSTED, SecurityStatus.PASS, SecurityStatus.WARN}:
                net_apy = self._calculate_net_apy(pool)
                sleeve, sleeve_reason = self._assign_sleeve(pool, sec.status)
                if not sleeve:
                    tactical_filtered += 1
                    reason_counts[sleeve_reason or "SLEEVE_REJECTED"] += 1
                    continue

                position_size = self._position_size_usd(sleeve)
                capacity_ok, cap_reasons, position_pct_tvl, allocation_pct = self._passes_capacity_guards(
                    pool,
                    position_size,
                    sleeve,
                )
                if not capacity_ok:
                    capacity_filtered += 1
                    for code in cap_reasons:
                        reason_counts[code] += 1
                    continue

                net_profit = self._estimate_monthly_profit_usd(net_apy, position_size)
                if net_profit <= 0:
                    cost_filtered += 1
                    reason_counts["COST_DOMINATED"] += 1
                    continue

                above_benchmark, benchmark_delta, benchmark_threshold = self._benchmark_status(net_apy)
                score = self._calculate_score(pool, sec, position_pct_tvl, above_benchmark)
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
                            "lindy_softened": "true" if self._is_lindy_softened(sec) else "false",
                            "sleeve": sleeve,
                            "position_size_usd": f"{position_size:.2f}",
                            "position_pct_tvl": f"{position_pct_tvl:.6f}",
                            "allocation_pct": f"{allocation_pct:.4f}",
                            "above_benchmark": "true" if above_benchmark else "false",
                            "benchmark_delta_apy": f"{benchmark_delta:.2f}",
                            "benchmark_threshold_apy": f"{benchmark_threshold:.2f}",
                        },
                        flags=self._flags(pool),
                    )
                )

        deduped = self._deduplicate(results)
        logger.info(
            "Funnel metrics: raw=%s heuristics=%s addressable_selected=%s missing_address=%s missing_chain_id=%s "
            "addressable_total=%s security_counts=%s top_reasons=%s lindy_softened=%s tactical_filtered=%s "
            "capacity_filtered=%s cost_filtered=%s results=%s deduped=%s",
            raw_count,
            heuristics_count,
            len(addressable_candidates),
            missing_address,
            missing_chain_id,
            addressable_total,
            security_counts,
            reason_counts.most_common(5),
            lindy_softened,
            tactical_filtered,
            capacity_filtered,
            cost_filtered,
            len(results),
            len(deduped),
        )
        return sorted(deduped, key=lambda x: x.score, reverse=True)

    def _prioritize(self, pools: List[ScoutCandidate]) -> List[ScoutCandidate]:
        """Stable-first + addressable-first sorting to use limited audit budget efficiently."""

        def _priority_rank(pool: ScoutCandidate) -> int:
            tier = self._classify_priority(pool)
            return {
                PriorityTier.LOW_VOLATILITY: 0,
                PriorityTier.COIN_STABLE: 1,
                PriorityTier.COIN_COIN: 2,
            }.get(tier, 9)

        def _is_addressable(pool: ScoutCandidate) -> int:
            return 1 if (pool.address and pool.chain_id is not None) else 0

        def _prelim(pool: ScoutCandidate) -> float:
            return (pool.yield_quality * (pool.apy or 0.0)) if pool.apy is not None else 0.0

        return sorted(
            pools,
            key=lambda p: (
                _priority_rank(p),
                -_is_addressable(p),
                -(p.tvl_usd or 0.0),
                -_prelim(p),
            ),
        )

    def _is_lindy_softened(self, security) -> bool:  # noqa: ANN001
        return any(getattr(r, "code", "") == "LINDY_SOFTENED" for r in getattr(security, "reasons", []) or [])

    def _maybe_apply_lindy(self, pool: ScoutCandidate, security) -> bool:  # noqa: ANN001
        """Softens missing-audit/reputation blocks into WARN for high-lindy pools.

        This must never override critical technical red flags.
        """
        if not getattr(self.config, "enable_lindy", True):
            return False
        if getattr(pool, "tvl_usd", 0.0) < getattr(self.config, "lindy_min_tvl_usd", 100_000_000):
            return False
        age_days = getattr(pool, "contract_age_days", None)
        if age_days is None or age_days < getattr(self.config, "lindy_min_age_days", 180):
            return False
        if getattr(security, "status", None) != SecurityStatus.BLOCK:
            return False

        # Never soften critical tech flags.
        for reason in getattr(security, "reasons", []) or []:
            code = getattr(reason, "code", "")
            severity = getattr(reason, "severity", None)
            if code in {"HONEYPOT_DETECTED", "HIGH_TAX", "HIDDEN_OWNER"}:
                return False
            if severity == SecuritySeverity.CRITICAL:
                return False

        # Only soften blocks that are driven by missing-audit / missing-reputation signals.
        soft_reason_codes = {
            "NO_AUDITS_FOUND",
            "NO_TOP_TIER_AUDIT",
            "UNIDENTIFIED_PROTOCOL",
            "DATA_UNAVAILABLE",
        }
        codes = {getattr(r, "code", "") for r in getattr(security, "reasons", []) or []}
        if not (codes & soft_reason_codes):
            return False

        security.status = SecurityStatus.WARN
        security.score = max(int(getattr(security, "score", 0) or 0), 60)
        security.reasons.append(
            SecurityReason(
                code="LINDY_SOFTENED",
                label=f"Lindy v1: softened missing-audit/reputation block (tvl={pool.tvl_usd}, age_days={age_days})",
                severity=SecuritySeverity.MEDIUM,
                source=SecuritySource.AGGREGATED,
                data={"tvl_usd": float(pool.tvl_usd), "age_days": int(age_days)},
            )
        )
        return True

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

    def _calculate_score(
        self,
        pool: ScoutCandidate,
        security,  # noqa: ANN001
        position_pct_tvl: float,
        above_benchmark: bool,
    ) -> float:
        # Combine yield quality and security status
        base = (pool.apy or 0.0) * pool.yield_quality
        sec_factor = 1.0
        if security.status == SecurityStatus.TRUSTED:
            sec_factor = 1.0
        elif security.status == SecurityStatus.PASS:
            sec_factor = 0.9
        elif security.status == SecurityStatus.WARN:
            sec_factor = 0.6
        max_pct_tvl = max(self.config.capacity_guards.max_position_pct_of_tvl, 1e-9)
        utilization = min(1.0, position_pct_tvl / max_pct_tvl)
        capacity_factor = 1.0 - (0.2 * utilization)
        benchmark_factor = 1.05 if above_benchmark else 0.9
        return base * sec_factor * capacity_factor * benchmark_factor

    def _estimate_monthly_profit_usd(self, net_apy: float, position_size: float) -> float:
        # net_apy is annual percentage; estimate monthly profit on position size,
        # then subtract amortized round-trip gas.
        gross_monthly = position_size * (net_apy / 100.0) / 12.0
        gas_cost = self.config.gas_efficiency.monthly_gas_cost_usd
        return gross_monthly - gas_cost

    def _assign_sleeve(
        self,
        pool: ScoutCandidate,
        security_status: SecurityStatus,
    ) -> Tuple[str | None, str | None]:
        sleeves = self.config.sleeves
        if (pool.apy or 0.0) >= sleeves.tactical_min_apy:
            if not sleeves.tactical_enabled:
                return None, "TACTICAL_DISABLED"
            return "tactical_high_apy", None

        tier = self._classify_priority(pool)
        if security_status in {SecurityStatus.TRUSTED, SecurityStatus.PASS} and tier in {
            PriorityTier.LOW_VOLATILITY,
            PriorityTier.COIN_STABLE,
        }:
            return "core_safe", None
        return "yield_plus", None

    def _position_size_usd(self, sleeve: str) -> float:
        profile = self.config.investor_profile
        deployable_capital = max(0.0, float(profile.deployable_capital_usd))
        base_position = float(self.config.gas_efficiency.effective_position_size_usd)

        if profile.risk_profile == "micro":
            base_position = min(base_position, max(50.0, deployable_capital * 0.20))
        elif profile.risk_profile == "standard":
            base_position = min(base_position, max(250.0, deployable_capital * 0.30))
        else:  # whale
            base_position = max(base_position, deployable_capital * 0.10)

        sleeve_limit_pct = {
            "core_safe": self.config.sleeves.core_safe_pct,
            "yield_plus": self.config.sleeves.yield_plus_pct,
            "tactical_high_apy": self.config.sleeves.tactical_high_apy_pct,
        }.get(sleeve, 1.0)
        if deployable_capital > 0:
            base_position = min(base_position, deployable_capital * sleeve_limit_pct)

        return max(50.0, base_position)

    def _passes_capacity_guards(
        self,
        pool: ScoutCandidate,
        position_size: float,
        sleeve: str,
    ) -> Tuple[bool, List[str], float, float]:
        reasons: List[str] = []
        tvl = max(0.0, float(pool.tvl_usd or 0.0))
        if tvl <= 0:
            return False, ["MISSING_TVL"], 1.0, 1.0

        profile = self.config.investor_profile
        deployable_capital = max(float(profile.deployable_capital_usd), position_size, 1.0)
        position_pct_tvl = position_size / tvl
        allocation_pct = position_size / deployable_capital
        guards = self.config.capacity_guards

        if position_pct_tvl > guards.max_position_pct_of_tvl:
            reasons.append("CAPACITY_TVL_EXCEEDED")
        if allocation_pct > guards.max_protocol_allocation_pct:
            reasons.append("PROTOCOL_CAP_EXCEEDED")
        if allocation_pct > guards.max_chain_allocation_pct:
            reasons.append("CHAIN_CAP_EXCEEDED")

        sleeve_pct = {
            "core_safe": self.config.sleeves.core_safe_pct,
            "yield_plus": self.config.sleeves.yield_plus_pct,
            "tactical_high_apy": self.config.sleeves.tactical_high_apy_pct,
        }.get(sleeve, 1.0)
        if allocation_pct > sleeve_pct:
            reasons.append("SLEEVE_BUDGET_EXCEEDED")

        return len(reasons) == 0, reasons, position_pct_tvl, allocation_pct

    def _benchmark_status(self, net_apy: float) -> Tuple[bool, float, float]:
        threshold = float(self.config.investor_profile.benchmark_threshold_apy)
        delta = float(net_apy - threshold)
        return delta >= 0.0, delta, threshold

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
