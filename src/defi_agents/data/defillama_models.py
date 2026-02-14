from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class YieldPoolFact(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    pool_id: str = Field(alias="pool")
    project: str
    chain: str
    symbol: str
    tvl_usd: float = Field(alias="tvlUsd")
    apy: float = 0.0
    apy_base: float | None = Field(default=None, alias="apyBase")
    apy_reward: float | None = Field(default=None, alias="apyReward")
    apy_mean_30d: float | None = Field(default=None, alias="apyMean30d")
    apy_pct_30d: float | None = Field(default=None, alias="apyPct30D")
    apy_pct_7d: float | None = Field(default=None, alias="apyPct7D")
    apy_pct_1d: float | None = Field(default=None, alias="apyPct1D")
    volume_usd_1d: float | None = Field(default=None, alias="volumeUsd1d")
    volume_usd_7d: float | None = Field(default=None, alias="volumeUsd7d")
    stablecoin: bool | None = None
    il_risk: str | None = Field(default=None, alias="ilRisk")
    outlier: bool | None = None
    mu: float | None = None
    sigma: float | None = None
    exposure: str | None = None
    underlying_tokens: list[str] = Field(default_factory=list, alias="underlyingTokens")
    reward_tokens: list[str] = Field(default_factory=list, alias="rewardTokens")
    pool_meta: str | None = Field(default=None, alias="poolMeta")


class YieldPoolHistoryPoint(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    timestamp: int
    tvl_usd: float | None = Field(default=None, alias="tvlUsd")
    apy: float | None = None
    apy_base: float | None = Field(default=None, alias="apyBase")
    apy_reward: float | None = Field(default=None, alias="apyReward")
    apy_base_7d: float | None = Field(default=None, alias="apyBase7d")
    il7d: float | None = None


class MarketProtocolRow(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    defillama_id: int | None = Field(default=None, alias="defillamaId")
    name: str | None = None
    display_name: str | None = Field(default=None, alias="displayName")
    module: str | None = None
    total_24h: float | None = Field(default=None, alias="total24h")
    total_7d: float | None = Field(default=None, alias="total7d")
    total_30d: float | None = Field(default=None, alias="total30d")
    change_1d: float | None = Field(default=None, alias="change_1d")
    change_7d: float | None = Field(default=None, alias="change_7d")
    change_1m: float | None = Field(default=None, alias="change_1m")


class MarketOverviewFact(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    category: str
    total_24h: float | None = Field(default=None, alias="total24h")
    total_7d: float | None = Field(default=None, alias="total7d")
    total_30d: float | None = Field(default=None, alias="total30d")
    change_1d: float | None = Field(default=None, alias="change_1d")
    change_7d: float | None = Field(default=None, alias="change_7d")
    change_1m: float | None = Field(default=None, alias="change_1m")
    protocols: list[MarketProtocolRow] = Field(default_factory=list)
    all_chains: list[str] = Field(default_factory=list)


class MarketSummaryFact(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    category: str
    protocol: str
    total_24h: float | None = Field(default=None, alias="total24h")
    total_7d: float | None = Field(default=None, alias="total7d")
    total_30d: float | None = Field(default=None, alias="total30d")
    total_1y: float | None = Field(default=None, alias="total1y")
    change_1d: float | None = Field(default=None, alias="change_1d")
    change_7d: float | None = Field(default=None, alias="change_7d")
    change_1m: float | None = Field(default=None, alias="change_1m")


class StablecoinAssetFact(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    asset_id: int | None = Field(default=None, alias="id")
    name: str | None = None
    symbol: str | None = None
    peg_type: str | None = Field(default=None, alias="pegType")
    circulating: float | None = None
    circulating_prev_day: float | None = Field(default=None, alias="circulatingPrevDay")
    circulating_prev_week: float | None = Field(default=None, alias="circulatingPrevWeek")
    circulating_prev_month: float | None = Field(default=None, alias="circulatingPrevMonth")
    price: float | None = None
    chains: list[str] = Field(default_factory=list)
    chain_circulating: dict[str, float] = Field(default_factory=dict, alias="chainCirculating")


class StablecoinSnapshotFact(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    assets: list[StablecoinAssetFact] = Field(default_factory=list)
    chains: list[str] = Field(default_factory=list)


class BridgeFact(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    bridge_id: int | None = Field(default=None, alias="id")
    defillama_id: int | None = Field(default=None, alias="defillamaId")
    name: str | None = None
    display_name: str | None = Field(default=None, alias="displayName")
    last_24h_volume: float | None = Field(default=None, alias="last24hVolume")
    weekly_volume: float | None = Field(default=None, alias="weeklyVolume")
    monthly_volume: float | None = Field(default=None, alias="monthlyVolume")
    chains: list[str] = Field(default_factory=list)
    destination_chain: list[str] = Field(default_factory=list, alias="destinationChain")
    url: str | None = None
    slug: str | None = None


class BridgeSnapshotFact(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    bridges: list[BridgeFact] = Field(default_factory=list)
    chains: list[str] = Field(default_factory=list)


class PriceFact(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    key: str
    symbol: str | None = None
    price: float | None = None
    timestamp: int | None = None
    confidence: float | None = None
    raw: dict[str, Any] = Field(default_factory=dict)
