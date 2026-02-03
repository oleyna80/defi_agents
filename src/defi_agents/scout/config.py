from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

from ..config import CONFIDENCE_PASS, CONFIDENCE_REJECT, CONFIDENCE_WARN


class RiskFilters(BaseModel):
    min_bridge_liquidity: float = 0.0
    max_chain_risk_score: int = 10


class GasEfficiency(BaseModel):
    budget_pct: float = 2.0
    min_monthly_net_profit_usd: float = 10.0
    deposit_usd: float = 1000.0


class ScoutConfig(BaseModel):
    min_tvl_usd: float = 1_000_000
    min_apy: float = 0.0
    target_chains: Optional[List[str]] = None  # None or [] => all chains
    global_search: bool = True
    risk_filters: RiskFilters = Field(default_factory=RiskFilters)
    gas_efficiency: GasEfficiency = Field(default_factory=GasEfficiency)
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
    max_audit_candidates: int = 15
    chain_id_map: dict[str, int] = Field(
        default_factory=lambda: {
            "Ethereum": 1,
            "Base": 8453,
            "Arbitrum": 42161,
            "Avalanche": 43114,
            "Optimism": 10,
        }
    )
    l3_max_audits_per_cycle: int = 3
    l3_timeout_seconds: int = 45
    l3_cache_ttl_hours: int = 72
    l3_prompt_version: str = "prompt_v1"
    l3_model: str = "mock-v1"
    l3_pass_confidence_threshold: float = CONFIDENCE_PASS
    l3_warn_confidence_threshold: float = CONFIDENCE_WARN
    l3_high_risk_confidence_threshold: float = CONFIDENCE_REJECT
    min_final_score: float = 10.0

    @classmethod
    def from_file(cls, path: str | Path) -> "ScoutConfig":
        data = json.loads(Path(path).read_text())
        if "scout_settings" in data:
            data = data["scout_settings"]
        return cls(**data)
