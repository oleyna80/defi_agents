from __future__ import annotations

from collections import Counter
import logging
import re
from typing import List, Tuple

from .config import ScoutConfig
from .defillama_client import DeFiLlamaClient
from .cache import ScoutDeduper
from .models import LendingSnapshot, PairCurrencyClass, PriorityTier, ScoutCandidate, ScoutResult, StableTier
from .uniswap_v3_new_pools import DexDiscoveryStats, UniswapV3NewPoolsAdapter
from ..security.auditor import SecurityAuditor
from ..security.models import SecurityReason, SecuritySeverity, SecuritySource, SecurityStatus

logger = logging.getLogger(__name__)


class YieldScout:
    _TARGET_BTC = {
        "BTC", "WBTC", "WBTC.B", "CBBTC", "TBTC", "RENBTC", "SBTC", "BTCB", "LBTC",
    }
    _TARGET_ETH = {
        "ETH", "WETH", "STETH", "WSTETH", "RETH", "CBETH", "EETH", "WEETH", "METH", "SETH",
    }
    _TARGET_GOLD = {"XAUT", "PAXG", "PAXGOLD"}

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
        self.deduper = deduper or ScoutDeduper(ttl_seconds=self.config.dedupe_ttl_seconds)
        self._new_pools_adapter = UniswapV3NewPoolsAdapter(config)
        self.last_discovery_stats = DexDiscoveryStats()
        self.last_lending_snapshot = LendingSnapshot()

    async def analyze(self) -> List[ScoutResult]:
        try:
            self.last_lending_snapshot = await self.client.get_lending_snapshot()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Lending snapshot fetch failed: %s", exc.__class__.__name__)
            self.last_lending_snapshot = LendingSnapshot()

        try:
            pools = await self.client.get_pools()
        except Exception as exc:  # noqa: BLE001
            # DeFiLlama is an intake source; transient failures should not crash the whole cycle.
            logger.warning("DeFiLlama pools fetch failed: %s", exc.__class__.__name__)
            pools = []
        discovery = await self._new_pools_adapter.fetch_new_pools(self.config.target_chains)
        if discovery.candidates:
            pools.extend(discovery.candidates)

        self.last_discovery_stats = discovery.stats
        self.last_discovery_stats.dex_llama_count = len(pools) - len(discovery.candidates)
        self.last_discovery_stats.dex_discovery_total = len(pools)

        new_pool_meta = discovery.metadata_by_pool_id
        raw_count = len(pools)
        filtered, liquidity_filtered = self._apply_heuristics(pools)
        universe_filtered = 0
        if self.config.asset_universe.intake_target_assets_only:
            filtered, universe_filtered = self._apply_asset_universe(filtered)
        heuristics_count = len(filtered)

        # Prioritize and select *addressable* candidates for security checks.
        # This avoids wasting the audit budget on items without chain_id/address.
        prioritized = self._prioritize(filtered)
        missing_address = 0
        missing_chain_id = 0
        addressable_total = 0
        for pool in prioritized:
            if not pool.address:
                missing_address += 1
            if pool.chain_id is None:
                missing_chain_id += 1
            if pool.address and pool.chain_id is not None:
                addressable_total += 1
        addressable_candidates = self._select_audit_candidates(prioritized)

        results: List[ScoutResult] = []
        security_counts = {s.value: 0 for s in SecurityStatus}
        lindy_softened = 0
        reason_counts: Counter[str] = Counter()
        tactical_filtered = 0
        capacity_filtered = 0
        cost_filtered = 0
        # Stablecoin risk policy counters
        blacklist_filtered = 0
        tier_counts: Counter[str] = Counter()
        pair_class_counts: Counter[str] = Counter()

        for pool in addressable_candidates:
            # address + chain_id are guaranteed by selection above
            assert pool.address and pool.chain_id is not None

            target_type = pool.address_source or "TOKEN"

            # Stablecoin risk policy: blacklist check (before security calls)
            blocked, blacklist_by = self._check_blacklist(pool)
            if blocked:
                blacklist_filtered += 1
                reason_counts[f"BLACKLIST_{blacklist_by.upper()}"] += 1
                continue

            # Classify for observability
            pool_tier = self._get_pool_tier(pool)
            pair_class, fx_exposure = self._classify_pair(pool)
            tier_counts[pool_tier.value] += 1
            pair_class_counts[pair_class.value] += 1

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
                reason_codes = self._reason_codes(sec)
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
                            "warn_reasons": ",".join(reason_codes[:3]),
                            # Stablecoin risk policy classification
                            "stable_tier": pool_tier.value,
                            "pair_currency_class": pair_class.value,
                            "fx_exposure": "true" if fx_exposure else "false",
                        },
                        flags=self._flags(pool),
                    )
                )
                if pool.pool_id in new_pool_meta:
                    results[-1].metadata.update(new_pool_meta[pool.pool_id])

        deduped = self._deduplicate(results)
        logger.info(
            "Funnel metrics: raw=%s heuristics=%s addressable_selected=%s missing_address=%s missing_chain_id=%s "
            "addressable_total=%s security_counts=%s top_reasons=%s lindy_softened=%s exploration_slots=%s tactical_filtered=%s "
            "capacity_filtered=%s cost_filtered=%s blacklist_filtered=%s liquidity_filtered=%s universe_filtered=%s results=%s deduped=%s",
            raw_count,
            heuristics_count,
            len(addressable_candidates),
            missing_address,
            missing_chain_id,
            addressable_total,
            security_counts,
            reason_counts.most_common(5),
            lindy_softened,
            min(max(0, self.config.exploration_slots), max(0, self.config.max_audit_candidates - 1)),
            tactical_filtered,
            capacity_filtered,
            cost_filtered,
            blacklist_filtered,
            liquidity_filtered,
            universe_filtered,
            len(results),
            len(deduped),
        )
        if self.config.risk_policy.enabled:
            logger.info(
                "Stablecoin risk policy: tier_counts=%s pair_class_counts=%s",
                dict(tier_counts),
                dict(pair_class_counts),
            )
        return sorted(deduped, key=lambda x: x.score, reverse=True)

    def _apply_asset_universe(self, pools: List[ScoutCandidate]) -> Tuple[List[ScoutCandidate], int]:
        """Optional cost/noise control: drop non-target assets before security calls.

        Target universe matches our decision output: BTC/ETH families, stablecoins, and XAUT/PAXG.
        Default is OFF to avoid changing production behavior without explicit opt-in.
        """
        allowed = self._target_asset_symbol_set()
        kept: List[ScoutCandidate] = []
        filtered = 0
        for pool in pools:
            tokens = self._extract_symbol_tokens(pool.symbol)
            if not tokens:
                filtered += 1
                continue
            if all(token in allowed for token in tokens):
                kept.append(pool)
            else:
                filtered += 1
        return kept, filtered

    def _target_asset_symbol_set(self) -> set[str]:
        buckets = self.config.token_buckets
        stable = {
            *(s.upper() for s in buckets.stablecoins_usd),
            *(s.upper() for s in buckets.stablecoins_eur),
            *(s.upper() for s in buckets.stablecoins_speculative),
            *(s.upper() for s in self.config.stable_symbols),
            # Common stable wrappers seen in lending/curve markets.
            "SUSDS", "SDAI",
        }
        return set(stable) | set(self._TARGET_BTC) | set(self._TARGET_ETH) | set(self._TARGET_GOLD)

    @staticmethod
    def _extract_symbol_tokens(symbol: str | None) -> list[str]:
        raw = (symbol or "").upper().strip()
        if not raw:
            return []
        # Split on any non-alphanumeric char (keep dot for variants like WBTC.B).
        parts = [p for p in re.split(r"[^A-Z0-9\\.]+", raw) if p]
        # If symbol is a single token (lending), keep it. If it's a pair, keep both.
        return parts

    def _apply_heuristics(self, pools: List[ScoutCandidate]) -> Tuple[List[ScoutCandidate], int]:
        candidates: List[ScoutCandidate] = []
        filtered_by_liquidity = 0
        for pool in pools:
            if not self._passes_liquidity_gates(pool):
                filtered_by_liquidity += 1
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
        return candidates, filtered_by_liquidity

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

    # --- Stablecoin Risk Policy helpers (Phase 1) ---

    def _check_blacklist(self, pool: ScoutCandidate) -> Tuple[bool, str]:
        """Check if pool should be blocked by blacklist.

        Check order: address → underlyingTokens → symbol.
        Returns: (blocked: bool, blacklist_by: str or empty).
        """
        if not self.config.risk_policy.enabled:
            return False, ""

        buckets = self.config.token_buckets

        # Lazy‑compute normalized blacklist sets once per scout instance
        if not hasattr(self, '_blacklist_address_lower'):
            self._blacklist_address_lower = {a.lower() for a in buckets.exclude_addresses}
            self._blacklist_symbol_upper = {s.upper() for s in buckets.exclude_symbols}

        # Check by address first
        if pool.address and pool.address.lower() in self._blacklist_address_lower:
            return True, "address"

        # Check underlying tokens
        for token in pool.underlying_tokens or []:
            token_lower = token.lower()
            if token_lower in self._blacklist_address_lower:
                return True, "token_address"
            token_upper = token.upper()
            if token_upper in self._blacklist_symbol_upper:
                return True, "token_symbol"

        # Check pool symbol
        symbols = [s.strip().upper() for s in (pool.symbol or "").split("-") if s.strip()]
        for sym in symbols:
            if sym in self._blacklist_symbol_upper:
                return True, "symbol"

        return False, ""

    def _classify_token_tier(self, symbol: str) -> StableTier:
        """Classify a single token symbol into a stablecoin tier."""
        sym_upper = symbol.strip().upper()
        buckets = self.config.token_buckets

        # T1: Core USD stables
        t1_symbols = {"USDC", "USDT", "DAI", "USDS"}
        if sym_upper in t1_symbols:
            return StableTier.T1

        # T2: Secondary stables
        t2_symbols = {"CRVUSD", "GHO", "PYUSD"}
        if sym_upper in t2_symbols:
            return StableTier.T2

        # T3: Speculative stables
        speculative = {s.upper() for s in buckets.stablecoins_speculative}
        if sym_upper in speculative:
            return StableTier.T3

        # Check if in any USD bucket
        usd_all = {s.upper() for s in buckets.stablecoins_usd}
        if sym_upper in usd_all:
            # If in USD bucket but not T1/T2, it's T2 by default
            return StableTier.T2

        # Check if it's a EUR stable
        eur_all = {s.upper() for s in buckets.stablecoins_eur}
        if sym_upper in eur_all:
            return StableTier.T2  # EUR stables are T2 by default

        return StableTier.UNKNOWN

    def _classify_pair(self, pool: ScoutCandidate) -> Tuple[PairCurrencyClass, bool]:
        """Classify pool pair into currency class.

        Returns: (pair_class, fx_exposure).
        """
        if not self.config.risk_policy.enabled:
            return PairCurrencyClass.TOKEN_TOKEN, False

        buckets = self.config.token_buckets
        usd_set = {s.upper() for s in buckets.stablecoins_usd} | {s.upper() for s in buckets.stablecoins_speculative}
        eur_set = {s.upper() for s in buckets.stablecoins_eur}
        all_stables = usd_set | eur_set

        symbols = [s.strip().upper() for s in (pool.symbol or "").split("-") if s.strip()]

        if len(symbols) < 2:
            # Single token or unrecognized format
            if len(symbols) == 1 and symbols[0] in all_stables:
                return PairCurrencyClass.TOKEN_STABLE, False
            return PairCurrencyClass.TOKEN_TOKEN, False

        # Classify each token
        usd_count = sum(1 for s in symbols if s in usd_set)
        eur_count = sum(1 for s in symbols if s in eur_set)
        stable_count = usd_count + eur_count

        # All USD stables
        if usd_count == len(symbols):
            return PairCurrencyClass.USD_STABLE_STABLE, False

        # All EUR stables
        if eur_count == len(symbols):
            return PairCurrencyClass.EUR_STABLE_STABLE, False

        # Mixed USD/EUR = FX exposure
        if usd_count > 0 and eur_count > 0:
            return PairCurrencyClass.FX_STABLE, True

        # At least one stable + non-stable
        if stable_count > 0 and stable_count < len(symbols):
            return PairCurrencyClass.TOKEN_STABLE, False

        return PairCurrencyClass.TOKEN_TOKEN, False

    def _get_pool_tier(self, pool: ScoutCandidate) -> StableTier:
        """Get the worst (highest risk) tier among pool tokens."""
        symbols = [s.strip().upper() for s in (pool.symbol or "").split("-") if s.strip()]
        if not symbols:
            return StableTier.UNKNOWN

        tiers = [self._classify_token_tier(s) for s in symbols]
        # Priority: T3 > T2 > T1 > UNKNOWN (worst tier wins)
        tier_priority = {StableTier.T3: 3, StableTier.T2: 2, StableTier.T1: 1, StableTier.UNKNOWN: 0}
        worst = max(tiers, key=lambda t: tier_priority.get(t, 0))
        return worst

    def _select_audit_candidates(self, prioritized: List[ScoutCandidate]) -> List[ScoutCandidate]:
        budget = max(1, int(self.config.max_audit_candidates))
        reserve_slots = min(max(0, int(self.config.exploration_slots)), max(0, budget - 1))
        primary_budget = budget - reserve_slots
        selected: List[ScoutCandidate] = []
        selected_ids: set[str] = set()

        for pool in prioritized:
            if len(selected) >= primary_budget:
                break
            if not (pool.address and pool.chain_id is not None):
                continue
            selected.append(pool)
            selected_ids.add(pool.pool_id)

        exploration_pool: List[ScoutCandidate] = []
        for pool in prioritized:
            if pool.pool_id in selected_ids:
                continue
            if not (pool.address and pool.chain_id is not None):
                continue
            if self.config.exploration_stable_only and self._classify_priority(pool) not in {
                PriorityTier.LOW_VOLATILITY,
                PriorityTier.COIN_STABLE,
            }:
                continue
            if (pool.apy or 0.0) < self.config.exploration_min_apy:
                continue
            exploration_pool.append(pool)

        exploration_pool.sort(key=lambda p: ((p.apy or 0.0), (p.tvl_usd or 0.0)), reverse=True)
        for pool in exploration_pool:
            if len(selected) >= budget:
                break
            selected.append(pool)
            selected_ids.add(pool.pool_id)

        if len(selected) < budget:
            for pool in prioritized:
                if len(selected) >= budget:
                    break
                if pool.pool_id in selected_ids:
                    continue
                if not (pool.address and pool.chain_id is not None):
                    continue
                selected.append(pool)
                selected_ids.add(pool.pool_id)

        return selected

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

    def _passes_liquidity_gates(self, pool: ScoutCandidate) -> bool:
        tvl = float(getattr(pool, "tvl_usd", 0.0) or 0.0)
        if tvl <= 0:
            return False

        gates = self.config.liquidity_gates
        min_vol = float(getattr(gates, "min_volume_24h_usd", 0.0) or 0.0)
        max_ratio = float(getattr(gates, "max_tvl_to_volume_24h_ratio", 0.0) or 0.0)

        # Default behavior: strict TVL floor (config default is high; schema enforces >=100k).
        tvl_ok = tvl >= float(self.config.min_tvl_usd)

        vol = getattr(pool, "volume_24h_usd", None)
        vol_value = float(vol) if isinstance(vol, (int, float)) else None
        vol_ok = False
        if min_vol > 0 and vol_value is not None:
            vol_ok = vol_value >= min_vol

        # If volume gate is configured, accept if either TVL or 24h volume passes.
        if min_vol > 0:
            if not (tvl_ok or vol_ok):
                return False
        else:
            if not tvl_ok:
                return False

        # Optional ratio guard (only when both values are present).
        if max_ratio > 0 and vol_value is not None and vol_value > 0:
            ratio = tvl / vol_value
            if ratio > max_ratio:
                return False

        return True

    def _classify_priority(self, pool: ScoutCandidate) -> PriorityTier:
        # Stablecoin risk policy: FX_STABLE pairs must not be classified as LOW_VOLATILITY
        if self.config.risk_policy.enabled:
            pair_class, _ = self._classify_pair(pool)
            if pair_class == PairCurrencyClass.FX_STABLE:
                # Force COIN_STABLE (or at least not LOW_VOLATILITY)
                # If pool.stablecoin is True, we still override to COIN_STABLE
                return PriorityTier.COIN_STABLE

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

        # Stablecoin risk policy: FX_STABLE pairs cannot go into core_safe if not allowed
        if self.config.risk_policy.enabled:
            pair_class, _ = self._classify_pair(pool)
            if pair_class == PairCurrencyClass.FX_STABLE and not self.config.risk_policy.fx_pairs_core_safe_allowed:
                # Override any core_safe eligibility
                return "yield_plus", None

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

    def _reason_codes(self, security) -> List[str]:  # noqa: ANN001
        out: List[str] = []
        seen: set[str] = set()
        for reason in getattr(security, "reasons", []) or []:
            code = str(getattr(reason, "code", "") or "").strip()
            if not code or code in seen:
                continue
            seen.add(code)
            out.append(code)
        return out

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
