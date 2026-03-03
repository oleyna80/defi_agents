from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, model_validator


class DataQuality(str, Enum):
    OK = "OK"
    DEGRADED = "DEGRADED"
    UNVERIFIED = "UNVERIFIED"


class PitType(str, Enum):
    CONFIDENT_PIT = "CONFIDENT_PIT"
    NOISE_PIT = "NOISE_PIT"
    NONE = "NONE"


class EntryActionability(str, Enum):
    ACTIONABLE = "ACTIONABLE"
    WATCHLIST = "WATCHLIST"


class EntryConfidenceBand(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class DegradationReason(str, Enum):
    PAGINATION_LIMIT_REACHED = "PAGINATION_LIMIT_REACHED"
    SUBGRAPH_TIMEOUT = "SUBGRAPH_TIMEOUT"
    SUBGRAPH_ERROR = "SUBGRAPH_ERROR"
    RPC_DRIFT_EXCEEDED = "RPC_DRIFT_EXCEEDED"
    RPC_UNAVAILABLE = "RPC_UNAVAILABLE"
    TICK_COUNT_ZERO = "TICK_COUNT_ZERO"


class TickData(BaseModel):
    tick_index: int
    liquidity_net: int
    liquidity_gross: int = 0


class PoolState(BaseModel):
    pool_address: str
    tick: int
    liquidity: int
    sqrt_price_x96: int
    fee_tier: int
    tick_spacing: int
    token0_decimals: int = 18
    token1_decimals: int = 18


class BandDepthResult(BaseModel):
    pool_address: str
    band_depth_1pct_usd: float = 0.0
    band_depth_2_5pct_usd: float = 0.0
    band_depth_5pct_usd: float = 0.0
    pit_type: PitType = PitType.NONE
    pits_found: int = 0
    suggested_range_lower_tick: int | None = None
    suggested_range_upper_tick: int | None = None
    data_quality: DataQuality = DataQuality.UNVERIFIED
    degradation_reason: DegradationReason | None = None
    scan_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def _validate_reason(self) -> "BandDepthResult":
        if self.data_quality != DataQuality.OK and self.degradation_reason is None:
            raise ValueError(
                "degradation_reason is required when data_quality is not OK"
            )
        if self.data_quality == DataQuality.OK:
            self.degradation_reason = None
        return self


class EntryRecommendation(BaseModel):
    chain: str
    project: str
    pair: str
    fee_tier: int | None = None
    suggested_range_lower_tick: int | None = None
    suggested_range_upper_tick: int | None = None
    confidence: EntryConfidenceBand = EntryConfidenceBand.LOW
    reasons: list[str] = Field(default_factory=list)
    watchlist_reason: str | None = None
    actionability: EntryActionability = EntryActionability.WATCHLIST
    rank_v1: float = 0.0
    source_pool_id: str = ""
