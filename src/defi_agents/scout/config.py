from __future__ import annotations

import json
from pathlib import Path
from typing import Literal
from typing import List, Optional, Dict

from pydantic import BaseModel, Field

from ..config import CONFIDENCE_PASS, CONFIDENCE_REJECT, CONFIDENCE_WARN


class ReportingConfig(BaseModel):
    """Reporting controls (Telegram output scheduling/shape).

    `telegram_digest_interval_seconds`:
    - 0 => legacy behavior (send report every cycle when picks exist).
    - >0 => digest mode: send at most once per interval (market snapshot style).

    `telegram_report_mode`:
    - snapshot => bypass anti-spam dedupe (still collapse within-run duplicates).
    - delta => keep anti-spam dedupe behavior.
    """

    telegram_digest_interval_seconds: int = Field(default=0, ge=0)
    telegram_report_mode: Literal["delta", "snapshot"] = "delta"
    telegram_top_n_per_section: int = Field(default=0, ge=0)
    telegram_turnover_section_enabled: bool = False
    telegram_turnover_top_n: int = Field(default=10, ge=0)
    telegram_turnover_min_tvl_usd: float = Field(default=100_000.0, ge=0.0)
    telegram_turnover_min_volume_24h_usd: float = Field(default=0.0, ge=0.0)
    telegram_turnover_min_vol_to_tvl: float = Field(default=0.0, ge=0.0)
    telegram_directional_sections_enabled: bool = False
    telegram_directional_top_n: int = Field(default=10, ge=0)
    telegram_directional_lp_min_tvl_usd: float = Field(default=100_000.0, ge=0.0)
    telegram_directional_lp_min_vol_to_tvl: float = Field(default=1.0, ge=0.0)
    telegram_directional_lending_min_tvl_usd: float = Field(default=100_000.0, ge=0.0)
    telegram_directional_borrow_symbols: List[str] = Field(
        default_factory=lambda: ["USDC", "USDT", "DAI", "USDS", "EURC", "GHO", "FRAX", "LUSD"]
    )
    telegram_directional_staking_min_tvl_usd: float = Field(default=100_000.0, ge=0.0)
    telegram_directional_staking_min_apy: float = Field(default=0.0, ge=0.0)
    telegram_show_source_confidence: bool = True


class AssetUniverseConfig(BaseModel):
    """Asset universe filter applied at Scout intake stage (cost/noise control)."""
    intake_target_assets_only: bool = False


class LiquidityGatesConfig(BaseModel):
    """Liquidity/activity gates for DEX/LP candidates.

    Goal: don't discard high-activity pools with low TVL (common on smaller chains),
    while still filtering dead/illiquid pools early to save downstream API cost.

    Semantics (when enabled by setting thresholds > 0):
    - Absolute floor: reject pools with tvl_usd < absolute_min_tvl_usd (risk-first guardrail).
    - Intake passes if (tvl_usd >= min_tvl_usd) OR (volume_24h_usd >= min_volume_24h_usd).
    - Optional ratio guard: if both TVL and volume are present, reject when TVL/Vol24h is too high.
    """

    absolute_min_tvl_usd: float = Field(default=100_000.0, ge=0.0)
    min_volume_24h_usd: float = 0.0
    max_tvl_to_volume_24h_ratio: float = 0.0


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


class TokenBuckets(BaseModel):
    """Stablecoin classification buckets for risk policy."""
    stablecoins_usd: List[str] = Field(
        default_factory=lambda: [
            "USDC", "USDT", "DAI", "USDS",  # T1
            "crvUSD", "GHO", "PYUSD",       # T2
        ]
    )
    stablecoins_eur: List[str] = Field(
        default_factory=lambda: ["EURS", "EURC", "agEUR", "EURe"]
    )
    stablecoins_speculative: List[str] = Field(
        default_factory=lambda: ["USDe", "TUSD", "FDUSD", "FRAX", "LUSD"]
    )
    exclude_symbols: List[str] = Field(default_factory=list)
    exclude_addresses: List[str] = Field(default_factory=list)


class StableRiskPolicy(BaseModel):
    """Stablecoin risk policy configuration."""
    enabled: bool = False
    apply_scoring_penalties: bool = False
    stable_tier_weights: dict[str, float] = Field(
        default_factory=lambda: {"T1": 1.0, "T2": 0.9, "T3": 0.7}
    )
    fx_pair_penalty: float = 0.15
    fx_pairs_core_safe_allowed: bool = False
    t3_min_apy_premium: float = 3.0
    include_tags_in_report: bool = False


class FreshnessConfig(BaseModel):
    recheck_enabled: bool = False
    enforce_freshness_for_actionable: bool = False
    recheck_max_candidates: int = 10
    recheck_timeout_seconds: int = 8
    max_age_minutes: int = 90
    max_apy_divergence_pct: float = 25.0
    max_tvl_divergence_pct: float = 20.0
    graph_api_key_env: str = "GRAPH_API_KEY"
    uniswap_subgraph_endpoints: dict[str, str] = Field(
        default_factory=dict
    )
    uniswap_subgraph_ids: dict[str, str] = Field(
        default_factory=lambda: {
            "Ethereum": "5zvR82QoaXYFyDEKLZ9t6v9adgnptxYpKpSbxtgVENFV",
            "Arbitrum": "C2KJVEU6fA9Bqf8QwK4MAnuS8xPYYn9N6HqFA7gKjsXo",
            "Base": "3hCPRGfHk8NAxU1wR8UWQ2N8isf2Xn7u6xQ5q4VYqW3G",
            "BSC": "6zfiRjwudV3wRMMWfDh29k14bP4fXp6q6qJZNk9b8f6R",
            "Binance": "6zfiRjwudV3wRMMWfDh29k14bP4fXp6q6qJZNk9b8f6R",
            "Avalanche": "4iA7jQX3U7zFfD6J2Wf6ByfQX7Qd8L1nY3mA6P7Y5b5M",
        }
    )
    aerodrome_subgraph_endpoints: dict[str, str] = Field(
        default_factory=dict
    )
    aerodrome_subgraph_ids: dict[str, str] = Field(
        default_factory=dict
    )
    aave_direct_enabled: bool = False
    aave_direct_timeout_seconds: int = 8
    aave_direct_api_key_env: str = "AAVE_DIRECT_API_KEY"
    # Per-chain endpoint(s): supports single URL string or ordered fallback list.
    aave_direct_endpoints: dict[str, str | list[str]] = Field(
        default_factory=lambda: {"Ethereum": ["https://api.v3.aave.com/graphql"]}
    )
    # Per-chain Aave GraphQL chainId map.
    aave_direct_chain_ids: dict[str, int] = Field(
        default_factory=lambda: {
            "Ethereum": 1,
            "Arbitrum": 42161,
            "Avalanche": 43114,
            "Base": 8453,
            "BSC": 56,
            "Binance": 56,
            "Optimism": 10,
            "Polygon": 137,
        }
    )
    # Allowlist map: SYMBOL -> underlying EVM address (not reserve symbol string).
    aave_direct_reserve_symbols: dict[str, dict[str, str]] = Field(
        default_factory=lambda: {
            "Ethereum": {
                "WETH": "0xC02aaA39b223FE8D0A0E5C4F27eAD9083C756Cc2",
                "WBTC": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",
                "USDC": "0xA0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
                "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
                "DAI": "0x6B175474E89094C44Da98b954EedeAC495271d0F",
                "GHO": "0x40D16FC0246aB6A3AE3E2fD7D8F9aE22fE2387bD",
            }
        }
    )


class StrategySimConfig(BaseModel):
    """Strategy simulation configuration (v1)."""
    enabled: bool = False
    max_candidates: int = 20
    supported_tiers: List[str] = Field(default_factory=lambda: ["T1", "T2"])
    allow_unsupported_as_watchlist: bool = True
    risk_thresholds_by_profile: Dict[str, int] = Field(
        default_factory=lambda: {
            "micro": 30,
            "standard": 50,
            "whale": 70,
        }
    )
    min_data_completeness_pct: float = 80.0


class UniswapV3NewPoolsConfig(BaseModel):
    enabled: bool = False
    timeout_seconds: int = 8
    max_pools: int = 200
    min_tvl_usd: float = Field(default=250_000.0, ge=100_000)
    page_size: int = 50
    max_pages: int = 4
    order_by: str = "createdAtTimestamp"
    order_direction: Literal["desc", "asc"] = "desc"
    graph_api_key_env: str = "GRAPH_API_KEY"
    subgraph_endpoints: dict[str, str] = Field(default_factory=dict)
    subgraph_ids: dict[str, str] = Field(default_factory=dict)


class DexDiscoveryConfig(BaseModel):
    uniswap_v3_new_pools: UniswapV3NewPoolsConfig = Field(default_factory=UniswapV3NewPoolsConfig)


class InspectorTargetConfig(BaseModel):
    target_id: str
    name: str = ""
    chain: str = "Ethereum"
    chain_id: int | None = None
    rpc_url: str | None = None
    explorer_url: str | None = None
    defillama_protocol_slug: str | None = None
    defillama_yield_pool_id: str | None = None
    docs_urls: List[str] = Field(default_factory=list)
    seed_addresses: List[str] = Field(default_factory=list)


class InspectorBudgetsConfig(BaseModel):
    max_http_requests: int = 20
    max_rpc_calls: int = 100
    max_targets_per_run: int = 5
    enable_rpc_log_inference: bool = False
    rpc_log_inference_block_window: int = 5000


class InspectorConfig(BaseModel):
    enabled: bool = False
    timeout_seconds: int = 10
    output_dir: str = "docs/memory-bank/cache/inspector"
    rpc_urls: Dict[str, str] = Field(default_factory=dict)
    budgets: InspectorBudgetsConfig = Field(default_factory=InspectorBudgetsConfig)
    targets: List[InspectorTargetConfig] = Field(default_factory=list)


class ScoutConfig(BaseModel):
    min_tvl_usd: float = Field(default=1_000_000, ge=100_000)
    min_apy: float = 0.0
    target_chains: Optional[List[str]] = None  # None or [] => all chains
    global_search: bool = True
    reporting: ReportingConfig = Field(default_factory=ReportingConfig)
    asset_universe: AssetUniverseConfig = Field(default_factory=AssetUniverseConfig)
    liquidity_gates: LiquidityGatesConfig = Field(default_factory=LiquidityGatesConfig)
    risk_filters: RiskFilters = Field(default_factory=RiskFilters)
    gas_efficiency: GasEfficiency = Field(default_factory=GasEfficiency)
    investor_profile: InvestorProfile = Field(default_factory=InvestorProfile)
    sleeves: SleevesConfig = Field(default_factory=SleevesConfig)
    capacity_guards: CapacityGuards = Field(default_factory=CapacityGuards)
    freshness: FreshnessConfig = Field(default_factory=FreshnessConfig)
    dex_discovery: DexDiscoveryConfig = Field(default_factory=DexDiscoveryConfig)
    inspector: InspectorConfig = Field(default_factory=InspectorConfig)
    strategy_sim: StrategySimConfig = Field(default_factory=StrategySimConfig)
    token_buckets: TokenBuckets = Field(default_factory=TokenBuckets)
    risk_policy: StableRiskPolicy = Field(default_factory=StableRiskPolicy)
    confidence_factors: Dict[str, float] = Field(
        default_factory=lambda: {
            "VERIFIED": 1.0,
            "AGGREGATOR_ONLY": 0.75,
            "DIVERGED": 0.4,
            "STALE": 0.2,
        }
    )
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
