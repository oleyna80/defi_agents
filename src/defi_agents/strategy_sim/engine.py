from __future__ import annotations

import logging
import math
from typing import List, Optional, Dict, Any
from .models import (
    StrategyId,
    SimStatus,
    SimulationResult,
    SimulationCounters,
)
from .catalog import get_strategy_catalog, get_strategy_by_id, get_required_data
from ..scout.models import ScoutResult, ScoutCandidate
from ..scout.config import ScoutConfig

logger = logging.getLogger(__name__)

_SIM_POLICY_REASON_BY_STATUS: dict[str, str] = {
    SimStatus.PARTIAL.value: "SIM_STATUS_PARTIAL",
    SimStatus.UNSUPPORTED.value: "SIM_STATUS_UNSUPPORTED",
}
_SIM_POLICY_REASON_RISK_ABOVE_PROFILE = "SIM_RISK_ABOVE_PROFILE"


class StrategySimEngine:
    """Deterministic strategy simulation engine (v1)."""

    def __init__(self, config: ScoutConfig) -> None:
        self.config = config
        self.strategy_catalog = get_strategy_catalog()

    def simulate_one(self, result: ScoutResult) -> SimulationResult:
        """Simulate a single candidate."""
        candidate = result.candidate
        metadata = result.metadata

        # 1) EVM-only gate
        if not self._is_evm_supported(candidate):
            return SimulationResult(
                status=SimStatus.UNSUPPORTED,
                best_strategy=None,
                fit_score=0,
                exp_net_apy_min=0.0,
                exp_net_apy_max=0.0,
                risk_score=100,
                constraints_hit=["NON_EVM"],
                required_data_missing=[],
                candidates_compact="",
            )

        # 2) Match best strategy
        best_strategy = self._match_best_strategy(candidate, metadata)
        if best_strategy is None:
            # No strategy matches -> treat as UNSUPPORTED for now
            return SimulationResult(
                status=SimStatus.UNSUPPORTED,
                best_strategy=None,
                fit_score=0,
                exp_net_apy_min=0.0,
                exp_net_apy_max=0.0,
                risk_score=100,
                constraints_hit=["NO_STRATEGY_MATCH"],
                required_data_missing=[],
                candidates_compact="",
            )

        # 3) Check required data
        required = get_required_data(best_strategy)
        missing = self._check_missing_data(candidate, metadata, required)
        if missing:
            return SimulationResult(
                status=SimStatus.PARTIAL,
                best_strategy=best_strategy,
                fit_score=0,
                exp_net_apy_min=0.0,
                exp_net_apy_max=0.0,
                risk_score=100,
                constraints_hit=[],
                required_data_missing=missing,
                candidates_compact="",
            )

        # 4) Compute deterministic scores
        fit_score = self._compute_fit_score(candidate, metadata, best_strategy)
        risk_score = self._compute_risk_score(candidate, metadata, best_strategy)
        exp_min, exp_max = self._compute_expected_net_apy_range(result, best_strategy)
        constraints_hit = self._detect_constraints_hit(candidate, metadata, best_strategy)

        return SimulationResult(
            status=SimStatus.OK,
            best_strategy=best_strategy,
            fit_score=fit_score,
            exp_net_apy_min=exp_min,
            exp_net_apy_max=exp_max,
            risk_score=risk_score,
            constraints_hit=constraints_hit,
            required_data_missing=[],
            candidates_compact=self._compact_candidates(candidate),
        )

    def _is_evm_supported(self, candidate: ScoutCandidate) -> bool:
        """Check if candidate chain is EVM (known chain_id)."""
        if candidate.chain_id is None:
            return False
        # If chain is in chain_id_map, treat as EVM
        return candidate.chain in self.config.chain_id_map

    def _match_best_strategy(
        self, candidate: ScoutCandidate, metadata: Dict[str, str]
    ) -> Optional[StrategyId]:
        """Determine best matching strategy (simple deterministic heuristics)."""
        symbol = (candidate.symbol or "").upper()
        project = (candidate.project or "").lower()
        pair_class = metadata.get("pair_currency_class", "")

        # Heuristic mapping (v1)
        if any(lst in symbol for lst in ["STETH", "RETH", "SFRXETH", "JITOSOL", "MSOL"]):
            return StrategyId.LIQUID_STAKING_CORE
        if any(lend in project for lend in ["aave", "spark", "morpho"]):
            return StrategyId.SINGLE_SIDED_LENDING
        if any(ystable in symbol for ystable in ["SUSDE", "SDAI", "USDE"]):
            return StrategyId.YIELD_BEARING_STABLE_CORE
        if pair_class in {"USD_STABLE_STABLE", "EUR_STABLE_STABLE", "FX_STABLE"}:
            return StrategyId.STABLE_STABLE_FEE_CAPTURE
        if "uniswap v3" in project or "aerodrome" in project or "velodrome" in project:
            return StrategyId.CLMM_RANGE_HARVEST

        return None

    def _check_missing_data(
        self, candidate: ScoutCandidate, metadata: Dict[str, str], required: List[str]
    ) -> List[str]:
        """Check which required data fields are missing."""
        missing = []
        for field in required:
            if field == "tvl_usd" and candidate.tvl_usd is None:
                missing.append(field)
            elif field == "apy" and candidate.apy is None:
                missing.append(field)
            elif field == "volume_24h_usd" and not self._has_volume(candidate, metadata):
                missing.append(field)
            elif field == "fees_24h_usd" and not self._has_fees(candidate, metadata):
                missing.append(field)
            elif field == "utilization" and not self._has_utilization(candidate, metadata):
                missing.append(field)
            elif field == "supply_rate" and not self._has_supply_rate(candidate, metadata):
                missing.append(field)
            elif field == "protocol_yield" and not self._has_protocol_yield(candidate, metadata):
                missing.append(field)
            elif field == "staking_rate" and not self._has_staking_rate(candidate, metadata):
                missing.append(field)
            elif field == "price_range" and not self._has_price_range(metadata):
                missing.append(field)
            elif field == "volatility_proxy" and not self._has_volatility_proxy(metadata):
                missing.append(field)
        return missing

    def _parse_finite_float(self, raw: Any) -> Optional[float]:
        if isinstance(raw, bool):
            return None
        if isinstance(raw, (int, float)):
            value = float(raw)
            return value if math.isfinite(value) else None
        if isinstance(raw, str):
            token = raw.strip()
            if not token:
                return None
            try:
                value = float(token)
            except ValueError:
                return None
            return value if math.isfinite(value) else None
        return None

    def _metadata_value(self, metadata: Dict[str, str], *keys: str) -> Optional[float]:
        for key in keys:
            value = self._parse_finite_float(metadata.get(key))
            if value is not None:
                return value
        return None

    def _read_strict_metadata_values(
        self, metadata: Dict[str, str], *keys: str
    ) -> tuple[bool, Optional[list[float]]]:
        present = False
        parsed_values: list[float] = []
        for key in keys:
            if key not in metadata:
                continue
            present = True
            parsed = self._parse_finite_float(metadata.get(key))
            if parsed is None:
                return True, None
            parsed_values.append(parsed)
        return present, parsed_values

    def _has_volume(self, candidate: ScoutCandidate, metadata: Dict[str, str]) -> bool:
        vol = getattr(candidate, "volume_24h_usd", None)
        if isinstance(vol, (int, float)) and float(vol) > 0:
            return True
        raw = (metadata.get("volume_24h_usd") or "").strip()
        if not raw:
            return False
        try:
            return float(raw) > 0
        except ValueError:
            return False

    def _has_fees(self, candidate: ScoutCandidate, metadata: Dict[str, str]) -> bool:
        fees_present, fee_values = self._read_strict_metadata_values(
            metadata, "fees_24h_usd", "fee_24h_usd", "fees_usd_24h"
        )
        if fees_present:
            if fee_values is None:
                return False
            return any(v > 0 for v in fee_values)

        apr_present, apr_values = self._read_strict_metadata_values(metadata, "fee_apr", "fees_apr")
        if apr_present:
            if apr_values is None:
                return False
            return any(v > 0 for v in apr_values)

        apy_base = self._parse_finite_float(getattr(candidate, "apy_base", None))
        return apy_base is not None and apy_base > 0

    def _has_utilization(self, candidate: ScoutCandidate, metadata: Dict[str, str]) -> bool:
        present, values = self._read_strict_metadata_values(
            metadata, "utilization", "utilization_ratio", "borrow_utilization"
        )
        if present:
            if values is None:
                return False
            return all(0 <= v <= 1 for v in values)

        supply = self._parse_finite_float(getattr(candidate, "total_supply_usd", None))
        borrow = self._parse_finite_float(getattr(candidate, "total_borrow_usd", None))
        if supply is None or borrow is None:
            return False
        if supply <= 0 or borrow < 0:
            return False
        return borrow <= supply

    def _has_supply_rate(self, candidate: ScoutCandidate, metadata: Dict[str, str]) -> bool:
        present, values = self._read_strict_metadata_values(
            metadata, "supply_rate", "supply_apy", "lending_supply_apy"
        )
        if present:
            if values is None:
                return False
            return any(v > 0 for v in values)

        apy_base = self._parse_finite_float(getattr(candidate, "apy_base", None))
        return apy_base is not None and apy_base > 0

    def _has_protocol_yield(self, candidate: ScoutCandidate, metadata: Dict[str, str]) -> bool:
        present, values = self._read_strict_metadata_values(
            metadata, "protocol_yield", "protocol_yield_rate", "apy_base_7d"
        )
        if present:
            if values is None:
                return False
            return any(v > 0 for v in values)

        apy_base = self._parse_finite_float(getattr(candidate, "apy_base", None))
        return apy_base is not None and apy_base > 0

    def _has_staking_rate(self, candidate: ScoutCandidate, metadata: Dict[str, str]) -> bool:
        present, values = self._read_strict_metadata_values(
            metadata, "staking_rate", "staking_rewards", "reward_rate"
        )
        if present:
            if values is None:
                return False
            return any(v > 0 for v in values)

        apy_reward = self._parse_finite_float(getattr(candidate, "apy_reward", None))
        return apy_reward is not None and apy_reward > 0

    def _has_price_range(self, metadata: Dict[str, str]) -> bool:
        has_lower = "suggested_range_lower_tick" in metadata or "price_range_lower" in metadata
        has_upper = "suggested_range_upper_tick" in metadata or "price_range_upper" in metadata
        if has_lower or has_upper:
            lower = self._metadata_value(metadata, "suggested_range_lower_tick", "price_range_lower")
            upper = self._metadata_value(metadata, "suggested_range_upper_tick", "price_range_upper")
            if lower is None or upper is None:
                return False
            return upper > lower

        present, widths = self._read_strict_metadata_values(
            metadata,
            "price_range",
            "range_width",
            "range_width_pct",
            "tick_range_half_width_pct",
        )
        if present:
            if widths is None:
                return False
            return any(v > 0 for v in widths)
        return False

    def _has_volatility_proxy(self, metadata: Dict[str, str]) -> bool:
        present, values = self._read_strict_metadata_values(
            metadata,
            "volatility_proxy",
            "tick_daily_vol",
            "tick_annual_vol",
            "daily_vol",
            "annual_vol",
            "sigma",
            "price_vol_7d",
            "apy_sigma_30d",
            "apy_pct_1d",
            "apy_pct_7d",
            "apy_pct_30d",
        )
        if present:
            if values is None:
                return False
            return any(v > 0 for v in values)
        return False

    def _compute_fit_score(
        self, candidate: ScoutCandidate, metadata: Dict[str, str], strategy: StrategyId
    ) -> int:
        """Compute fit score 0..100 (deterministic)."""
        score = 50  # baseline
        # Adjust based on data completeness
        if candidate.tvl_usd is not None:
            score += 10
        if candidate.apy is not None:
            score += 10
        # Adjust based on pair class alignment
        pair_class = metadata.get("pair_currency_class", "")
        strat = get_strategy_by_id(strategy)
        if pair_class in strat.supported_pair_classes:
            score += 20
        # Cap
        return max(0, min(100, score))

    def _compute_risk_score(
        self, candidate: ScoutCandidate, metadata: Dict[str, str], strategy: StrategyId
    ) -> int:
        """Compute risk score 0..100 (higher = riskier)."""
        score = 50
        # FX exposure
        if metadata.get("fx_exposure", "false") == "true":
            score += 20
        # T3 stable tier
        if metadata.get("stable_tier") == "T3":
            score += 15
        # High reward share
        if candidate.apy_reward and candidate.apy_base:
            reward_share = candidate.apy_reward / (candidate.apy_base + candidate.apy_reward)
            if reward_share > 0.5:
                score += 10
        # Freshness unverified
        if metadata.get("freshness_status") == "UNVERIFIED":
            score += 10
        # Divergence
        apy_div = float(metadata.get("apy_divergence_pct") or "0")
        if apy_div > 10:
            score += 5
        return max(0, min(100, score))

    def _compute_expected_net_apy_range(
        self, result: ScoutResult, strategy: StrategyId
    ) -> tuple[float, float]:
        """Compute expected net APY range (bounded heuristic)."""
        net_apy = result.net_apy
        if net_apy <= 0:
            return 0.0, 0.0
        # Simple deterministic factors
        quality_factor = 0.8 if result.candidate.yield_quality < 0.5 else 0.95
        safety_factor = 0.9
        cap_factor = 1.1
        exp_min = net_apy * quality_factor * safety_factor
        exp_max = net_apy * cap_factor
        return round(exp_min, 2), round(exp_max, 2)

    def _detect_constraints_hit(
        self, candidate: ScoutCandidate, metadata: Dict[str, str], strategy: StrategyId
    ) -> List[str]:
        """Detect constraints hit (e.g., capacity, risk limits)."""
        constraints = []
        # Example: TVL too low for strategy
        if candidate.tvl_usd and candidate.tvl_usd < 1_000_000:
            constraints.append("TVL_BELOW_1M")
        # Example: APY below min for T3 premium
        if metadata.get("stable_tier") == "T3":
            min_premium = self.config.risk_policy.t3_min_apy_premium
            if candidate.apy and candidate.apy < min_premium:
                constraints.append("T3_APY_BELOW_PREMIUM")
        return constraints

    def _compact_candidates(self, candidate: ScoutCandidate) -> str:
        """Generate compact candidate summary."""
        parts = []
        if candidate.symbol:
            parts.append(candidate.symbol[:10])
        if candidate.chain:
            parts.append(candidate.chain[:3])
        if candidate.apy is not None:
            parts.append(f"{candidate.apy:.1f}%")
        return ":".join(parts)

    def apply_policy(
        self, results: List[ScoutResult], counters: SimulationCounters
    ) -> SimulationCounters:
        """Apply decision gates (downgrade to WATCHLIST if needed)."""
        for res in results:
            meta = res.metadata
            sim_status = meta.get("sim_status")
            sim_risk = int(meta.get("sim_risk_score") or "0")
            profile = self.config.investor_profile.risk_profile
            threshold = self.config.strategy_sim.risk_thresholds_by_profile.get(profile, 50)

            # PARTIAL/UNSUPPORTED => WATCHLIST
            if sim_status in (SimStatus.PARTIAL.value, SimStatus.UNSUPPORTED.value):
                if meta.get("report_group") != "WATCHLIST":
                    meta["report_group"] = "WATCHLIST"
                    reason_code = _SIM_POLICY_REASON_BY_STATUS.get(
                        sim_status, "SIM_STATUS_UNSUPPORTED"
                    )
                    meta["watchlist_reason"] = reason_code
                    meta["sim_policy_reason"] = reason_code
                    counters.downgraded_to_watchlist_count += 1
                if sim_status == SimStatus.PARTIAL.value:
                    counters.watchlist_by_missing_data_count += 1
            # OK but risk score exceeds threshold => downgrade
            elif sim_status == SimStatus.OK.value and sim_risk > threshold:
                if meta.get("report_group") != "WATCHLIST":
                    meta["report_group"] = "WATCHLIST"
                    meta["watchlist_reason"] = _SIM_POLICY_REASON_RISK_ABOVE_PROFILE
                    meta["sim_policy_reason"] = _SIM_POLICY_REASON_RISK_ABOVE_PROFILE
                    counters.downgraded_to_watchlist_count += 1
        return counters
