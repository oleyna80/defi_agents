from __future__ import annotations

import json
from pathlib import Path
from typing import Literal
from typing import List, Optional

from pydantic import BaseModel, Field

from ..config import CONFIDENCE_PASS, CONFIDENCE_REJECT, CONFIDENCE_WARN


class RiskFilters(BaseModel):
    min_bridge_liquidity: float = 0.0
    max_chain_risk_score: int = 10


class GasEfficiency(BaseModel):
    # Portfolio-level capital target (informational for strategy sizing).
    portfolio_total_usd: float = 10_000.0
    # Per-opportunity position sizing used for monthly net-profit estimation.
    position_size_usd: float = 2_500.0
    # Absolute minimum monthly profit target (can be auto-raised by relative floor).
    min_monthly_net_profit_usd: float = 50.0
    # Round-trip cost for opening + closing position.
    estimated_roundtrip_gas_usd: float = 8.0
    # Expected holding horizon for amortizing round-trip gas cost.
    holding_period_days: int = 45
    # Legacy fields kept for backward compatibility with old config files.
    budget_pct: float | None = None
    deposit_usd: float | None = None

    @property
    def effective_position_size_usd(self) -> float:
        if self.position_size_usd > 0:
            return float(self.position_size_usd)
        if self.deposit_usd is not None and self.deposit_usd > 0:
            return float(self.deposit_usd)
        return 1_000.0

    @property
    def monthly_gas_cost_usd(self) -> float:
        days = max(1, int(self.holding_period_days))
        return float(self.estimated_roundtrip_gas_usd) * (30.0 / float(days))

    @property
    def effective_min_monthly_profit_usd(self) -> float:
        # Relative floor: at least 0.5% of position size per month.
        relative_floor = self.effective_position_size_usd * 0.005
        return max(float(self.min_monthly_net_profit_usd), relative_floor)


class InvestorProfile(BaseModel):
    initial_capital_usd: float = 10_000.0
    monthly_contribution_usd: float = 0.0
    risk_profile: Literal["micro", "standard", "whale"] = "standard"
    horizon_days: int = 45
    benchmark_apy: float = 5.0
    benchmark_buffer_apy: float = 1.0

    @property
    def deployable_capital_usd(self) -> float:
        months = max(0.0, float(self.horizon_days) / 30.0)
        return max(0.0, self.initial_capital_usd + (self.monthly_contribution_usd * months))

    @property
    def benchmark_threshold_apy(self) -> float:
        return float(self.benchmark_apy + self.benchmark_buffer_apy)


class SleevesConfig(BaseModel):
    core_safe_pct: float = 0.70
    yield_plus_pct: float = 0.25
    tactical_high_apy_pct: float = 0.05
    tactical_enabled: bool = False
    tactical_min_apy: float = 100.0


class CapacityGuards(BaseModel):
    max_position_pct_of_tvl: float = 0.005  # 0.5%
    max_protocol_allocation_pct: float = 0.40
    max_chain_allocation_pct: float = 0.50


class FreshnessConfig(BaseModel):
    recheck_enabled: bool = False
    enforce_freshness_for_actionable: bool = False
    recheck_max_candidates: int = 10
    recheck_timeout_seconds: int = 8
    max_age_minutes: int = 90
    max_apy_divergence_pct: float = 25.0
    max_tvl_divergence_pct: float = 20.0


class ScoutConfig(BaseModel):
    min_tvl_usd: float = 1_000_000
    min_apy: float = 0.0
    target_chains: Optional[List[str]] = None  # None or [] => all chains
    global_search: bool = True
    risk_filters: RiskFilters = Field(default_factory=RiskFilters)
    gas_efficiency: GasEfficiency = Field(default_factory=GasEfficiency)
    investor_profile: InvestorProfile = Field(default_factory=InvestorProfile)
    sleeves: SleevesConfig = Field(default_factory=SleevesConfig)
    capacity_guards: CapacityGuards = Field(default_factory=CapacityGuards)
    freshness: FreshnessConfig = Field(default_factory=FreshnessConfig)
    stable_symbols: List[str] = Field(
        default_factory=lambda: [
            "USDC",
            "USDT",
            "DAI",
            "USDS",
            "FRAX",
            "USDE",
            "LUSD",
        ]
    )
    yield_quality_min: float = 0.2
    apy_anomaly_ratio: float = 2.0
    max_audit_candidates: int = 40
    dedupe_ttl_seconds: int = 14_400
    # Reserve part of audit budget for high-APR exploration so low-TVL gems are not starved by TVL sorting.
    exploration_slots: int = 10
    exploration_min_apy: float = 20.0
    exploration_stable_only: bool = True
    chain_id_map: dict[str, int] = Field(
        default_factory=lambda: {
            "Ethereum": 1,
            "Base": 8453,
            "Arbitrum": 42161,
            "Avalanche": 43114,
            "Optimism": 10,
            # Common EVM networks (Phase 2 intake expansion)
            "Polygon": 137,
            "BSC": 56,
            "Binance": 56,
            "Fantom": 250,
            "Gnosis": 100,
            "Celo": 42220,
            "Moonbeam": 1284,
            "Moonriver": 1285,
            "Linea": 59144,
            "Scroll": 534352,
            "zkSync": 324,
            "ZkSync": 324,
            "Blast": 81457,
            "Mantle": 5000,
        }
    )
    # Lindy v1 (soften-only) thresholds
    enable_lindy: bool = True
    lindy_min_tvl_usd: float = 100_000_000
    lindy_min_age_days: int = 180
    l3_max_audits_per_cycle: int = 3
    l3_timeout_seconds: int = 45
    l3_cache_ttl_hours: int = 72
    l3_prompt_version: str = "prompt_v1"
    l3_model: str = "mock-v1"
    l3_pass_confidence_threshold: float = CONFIDENCE_PASS
    l3_warn_confidence_threshold: float = CONFIDENCE_WARN
    l3_high_risk_confidence_threshold: float = CONFIDENCE_REJECT
    min_final_score: float = 10.0
    min_warn_score: float = 2.0

    @classmethod
    def from_file(cls, path: str | Path) -> "ScoutConfig":
        data = json.loads(Path(path).read_text())
        if "scout_settings" in data:
            data = data["scout_settings"]
        return cls(**data)
