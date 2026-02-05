from __future__ import annotations

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class SimStatus(str, Enum):
    """Strategy simulation status."""
    OK = "OK"
    PARTIAL = "PARTIAL"
    UNSUPPORTED = "UNSUPPORTED"


class StrategyId(str, Enum):
    """Supported strategy IDs (v1)."""
    LIQUID_STAKING_CORE = "liquid_staking_core"
    SINGLE_SIDED_LENDING = "single_sided_lending"
    YIELD_BEARING_STABLE_CORE = "yield_bearing_stable_core"
    STABLE_STABLE_FEE_CAPTURE = "stable_stable_fee_capture"
    CLMM_RANGE_HARVEST = "clmm_range_harvest"


class StrategyMetadata(BaseModel):
    """Strategy-specific metadata (entry/exit rules, required data)."""
    id: StrategyId
    name: str
    description: str = ""
    entry_rules: List[str] = Field(default_factory=list)
    exit_rules: List[str] = Field(default_factory=list)
    required_data: List[str] = Field(default_factory=list)
    risk_limits: Dict[str, Any] = Field(default_factory=dict)
    supported_chains: List[str] = Field(default_factory=list)
    supported_pair_classes: List[str] = Field(default_factory=list)
    tier: str = "T1"  # T1/T2/T3


class SimulationResult(BaseModel):
    """Result of simulating a single candidate."""
    status: SimStatus = SimStatus.OK
    best_strategy: Optional[StrategyId] = None
    fit_score: int = 0  # 0..100
    exp_net_apy_min: float = 0.0
    exp_net_apy_max: float = 0.0
    risk_score: int = 0  # 0..100
    constraints_hit: List[str] = Field(default_factory=list)
    required_data_missing: List[str] = Field(default_factory=list)
    candidates_compact: str = ""

    def to_metadata_dict(self) -> Dict[str, str]:
        """Convert to flat key-value dict for ScoutResult.metadata."""
        return {
            "sim_status": self.status.value,
            "sim_best_strategy": self.best_strategy.value if self.best_strategy else "",
            "sim_fit_score": str(self.fit_score),
            "sim_exp_net_apy_min": f"{self.exp_net_apy_min:.2f}",
            "sim_exp_net_apy_max": f"{self.exp_net_apy_max:.2f}",
            "sim_risk_score": str(self.risk_score),
            "sim_constraints_hit": ",".join(self.constraints_hit),
            "sim_required_data_missing": ",".join(self.required_data_missing),
            "sim_candidates_compact": self.candidates_compact,
        }


class SimulationCounters(BaseModel):
    """Observability counters per cycle."""
    simulated_count: int = 0
    ok_count: int = 0
    partial_count: int = 0
    unsupported_count: int = 0
    watchlist_by_missing_data_count: int = 0
    best_strategy_distribution: Dict[str, int] = Field(default_factory=dict)
    downgraded_to_watchlist_count: int = 0

    def to_log_line(self) -> str:
        """Format as a compact log line."""
        parts = [
            f"simulated={self.simulated_count}",
            f"ok={self.ok_count}",
            f"partial={self.partial_count}",
            f"unsupported={self.unsupported_count}",
            f"watchlist_missing={self.watchlist_by_missing_data_count}",
            f"downgraded={self.downgraded_to_watchlist_count}",
        ]
        if self.best_strategy_distribution:
            dist = ",".join(f"{k}:{v}" for k, v in self.best_strategy_distribution.items())
            parts.append(f"best_strategy_dist={dist}")
        return "StrategySim summary: " + " ".join(parts)