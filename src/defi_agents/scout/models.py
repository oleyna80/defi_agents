from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, constr


class L3Judgment(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    HIGH_RISK = "HIGH_RISK"
    INCONCLUSIVE = "INCONCLUSIVE"
    ERROR = "ERROR"


class FinalTag(str, Enum):
    ALPHA_STABLE = "ALPHA_STABLE"
    SOLID_RISK = "SOLID_RISK"
    AI_REJECT = "AI_REJECT"
    AI_DOUBT = "AI_DOUBT"
    PENDING = "PENDING"
    AUDIT_LAG = "AUDIT_LAG"


class ReasonCode(str, Enum):
    PONZI_SIGNAL = "PONZI_SIGNAL"
    UNLOCK_RISK = "UNLOCK_RISK"
    LIQUIDITY_MISMATCH = "LIQUIDITY_MISMATCH"
    DOCS_MISMATCH = "DOCS_MISMATCH"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"
    JSON_PARSE_FAIL = "JSON_PARSE_FAIL"
    PDF_UNSUPPORTED = "PDF_UNSUPPORTED"
    RATE_LIMIT_HIT = "RATE_LIMIT_HIT"
    SSRF_BLOCKED = "SSRF_BLOCKED"
    NO_DATA = "NO_DATA"


class StableTier(str, Enum):
    """Stablecoin risk tier classification."""
    T1 = "T1"  # USDC, USDT, DAI, USDS
    T2 = "T2"  # crvUSD, GHO, PYUSD
    T3 = "T3"  # USDe, TUSD, FDUSD, FRAX, LUSD
    UNKNOWN = "UNKNOWN"


class PairCurrencyClass(str, Enum):
    """Pool pair currency classification."""
    USD_STABLE_STABLE = "USD_STABLE_STABLE"
    EUR_STABLE_STABLE = "EUR_STABLE_STABLE"
    FX_STABLE = "FX_STABLE"  # USD/EUR mix
    TOKEN_STABLE = "TOKEN_STABLE"
    TOKEN_TOKEN = "TOKEN_TOKEN"


class YieldType(str, Enum):
    LP_FEES = "lp_fees"
    LENDING_SUPPLY = "lending_supply"
    LENDING_BORROW = "lending_borrow"
    STAKING = "staking"
    INCENTIVES = "incentives"
    FUNDING_CARRY = "funding_carry"
    BASIS = "basis"
    OPTIONS_PREMIUM = "options_premium"
    RWA = "rwa"
    UNKNOWN = "unknown"


class SourceConfidence(str, Enum):
    """Data quality signal based on freshness re-check outcome."""
    VERIFIED = "VERIFIED"              # FRESH + within divergence limits
    AGGREGATOR_ONLY = "AGGREGATOR_ONLY"  # no re-check or UNVERIFIED
    DIVERGED = "DIVERGED"              # re-checked but divergence exceeded
    STALE = "STALE"                    # re-checked but data too old


class EvidenceItem(BaseModel):
    point: str
    source_type: str  # docs | github | social | onchain
    source_url: Optional[str] = None
    quote: Optional[str] = None
    reliability_score: float = Field(default=0.0, ge=0.0, le=1.0)


class L3Metadata(BaseModel):
    provider: str = "deepseek"
    model: str = "deepseek-chat"
    prompt_version: str = "v1.1"
    extractor_version: str = "v1.0"
    policy_version: str = "v1.0"
    extraction_source: str = "none"  # jina | fallback_http | none
    cache_hit_content: bool = False
    cache_hit_analysis: bool = False
    retry_count: int = 0
    latency_ms: float = 0.0
    tokens_input: int = 0
    tokens_output: int = 0
    analysis_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class L3Result(BaseModel):
    judgment: L3Judgment
    confidence: float = Field(..., ge=0.0, le=1.0)
    reason_codes: List[ReasonCode] = Field(default_factory=list)
    red_flags: List[str] = Field(default_factory=list)
    evidence: List[EvidenceItem] = Field(default_factory=list)
    decision_rationale: Optional[constr(max_length=200)] = None
    metadata: Optional[L3Metadata] = None


class ScoutCandidate(BaseModel):
    pool_id: str = Field(alias="pool")
    project: str
    chain: str
    symbol: str
    address: Optional[str] = None
    address_source: Optional[str] = None
    project_url: Optional[str] = Field(alias="url", default=None)
    underlying_tokens: List[str] = Field(alias="underlyingTokens", default_factory=list)
    chain_id: Optional[int] = None
    tvl_usd: float = Field(alias="tvlUsd")
    volume_24h_usd: Optional[float] = Field(alias="volumeUsd1d", default=None)
    volume_7d_usd: Optional[float] = Field(alias="volumeUsd7d", default=None)
    apy: float
    apy_base: Optional[float] = Field(alias="apyBase", default=0.0)
    apy_reward: Optional[float] = Field(alias="apyReward", default=0.0)
    apy_base_borrow: Optional[float] = Field(alias="apyBaseBorrow", default=None)
    apy_reward_borrow: Optional[float] = Field(alias="apyRewardBorrow", default=None)
    total_supply_usd: Optional[float] = Field(alias="totalSupplyUsd", default=None)
    total_borrow_usd: Optional[float] = Field(alias="totalBorrowUsd", default=None)
    reward_tokens: List[str] = Field(alias="rewardTokens", default_factory=list)
    apy_mean_30d: Optional[float] = Field(alias="apyMean30d", default=None)
    apy_pct_30d: Optional[float] = Field(alias="apyPct30D", default=None)
    apy_pct_7d: Optional[float] = Field(alias="apyPct7D", default=None)
    apy_pct_1d: Optional[float] = Field(alias="apyPct1D", default=None)
    apy_base_7d: Optional[float] = Field(alias="apyBase7d", default=None)
    il_7d: Optional[float] = Field(alias="il7d", default=None)
    il_risk: Optional[str] = Field(alias="ilRisk", default=None)
    outlier: Optional[bool] = Field(alias="outlier", default=None)
    mu: Optional[float] = None
    sigma: Optional[float] = None
    exposure: Optional[str] = Field(alias="exposure", default=None)
    stablecoin: Optional[bool] = Field(alias="stablecoin", default=None)
    timestamp: Optional[int] = None
    contract_age_days: Optional[int] = None
    l3_status: Optional[FinalTag] = None
    l3_data: Optional[L3Result] = None
    ai_security_factor: float = 1.0
    yield_type: YieldType = YieldType.UNKNOWN
    source_confidence: SourceConfidence = SourceConfidence.AGGREGATOR_ONLY

    @property
    def yield_quality(self) -> float:
        if self.apy <= 0:
            return 0.0
        return (self.apy_base or 0.0) / self.apy


class PriorityTier(str, Enum):
    LOW_VOLATILITY = "LOW_VOLATILITY"  # stable-only
    COIN_STABLE = "COIN_STABLE"
    COIN_COIN = "COIN_COIN"


class ScoutResult(BaseModel):
    candidate: ScoutCandidate
    security: Optional[object] = None  # SecurityResult type (import lazily to avoid cycles)
    net_apy: float
    score: float
    net_profit_usd: float
    priority: PriorityTier
    metadata: Dict[str, str] = Field(default_factory=dict)
    flags: List[str] = Field(default_factory=list)


class LendingSnapshotItem(BaseModel):
    candidate: ScoutCandidate
    metric_name: str
    metric_value_pct: float


class LendingSnapshot(BaseModel):
    best_eth_supply: Optional[LendingSnapshotItem] = None
    best_btc_supply: Optional[LendingSnapshotItem] = None
    best_gho_supply: Optional[LendingSnapshotItem] = None
    lowest_stable_borrow: Optional[LendingSnapshotItem] = None
    lowest_eurc_borrow: Optional[LendingSnapshotItem] = None
    lowest_usdc_borrow: Optional[LendingSnapshotItem] = None
    lowest_borrow_by_symbol: Dict[str, LendingSnapshotItem] = Field(default_factory=dict)

    def has_any(self) -> bool:
        return any(
            [
                self.best_eth_supply is not None,
                self.best_btc_supply is not None,
                self.best_gho_supply is not None,
                self.lowest_stable_borrow is not None,
                self.lowest_eurc_borrow is not None,
                self.lowest_usdc_borrow is not None,
                bool(self.lowest_borrow_by_symbol),
            ]
        )


class YieldDirectionSnapshot(BaseModel):
    lp_top: List[LendingSnapshotItem] = Field(default_factory=list)
    lending_supply_top: List[LendingSnapshotItem] = Field(default_factory=list)
    lending_borrow_top: List[LendingSnapshotItem] = Field(default_factory=list)
    staking_top: List[LendingSnapshotItem] = Field(default_factory=list)

    def has_any(self) -> bool:
        return any(
            [
                bool(self.lp_top),
                bool(self.lending_supply_top),
                bool(self.lending_borrow_top),
                bool(self.staking_top),
            ]
        )


class PoolHealthTag(str, Enum):
    HEALTHY = "HEALTHY"
    WATCH_VOLUME = "WATCH_VOLUME"
    WATCH_APY_DRIFT = "WATCH_APY_DRIFT"
    WATCH_TVL_DRAIN = "WATCH_TVL_DRAIN"
    DATA_UNVERIFIED = "DATA_UNVERIFIED"


class MonitoredPoolSnapshot(BaseModel):
    pool_ref: str
    label: str = ""
    chain: Optional[str] = None
    project: Optional[str] = None
    symbol: Optional[str] = None
    tvl_usd: Optional[float] = None
    volume_24h_usd: Optional[float] = None
    vol_to_tvl_24h: Optional[float] = None
    apy: Optional[float] = None
    apy_base: Optional[float] = None
    apy_reward: Optional[float] = None
    apy_mean_30d: Optional[float] = None
    apy_vs_mean_30d_pct: Optional[float] = None
    freshness_status: str = "UNVERIFIED"
    source_confidence: SourceConfidence = SourceConfidence.AGGREGATOR_ONLY
    health_tags: List[PoolHealthTag] = Field(default_factory=list)
    alert_reasons: List[str] = Field(default_factory=list)
    pool_url: Optional[str] = None


class MyPoolsMonitorReport(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    healthy_count: int = 0
    watch_count: int = 0
    unverified_count: int = 0
    show_health: bool = True
    show_alerts: bool = True
    top_n: int = 10
    snapshots: List[MonitoredPoolSnapshot] = Field(default_factory=list)
    market_gap: List[MonitoredPoolSnapshot] = Field(default_factory=list)

    def has_any(self) -> bool:
        return bool(self.snapshots) or bool(self.market_gap)
