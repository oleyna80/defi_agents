from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field, model_validator

HedgeMode = Literal["PAPER", "SHADOW", "LIVE"]
HedgeAction = Literal["HEDGE", "HOLD", "SKIP"]
HedgeSide = Literal["LONG", "SHORT", "NONE"]


class HedgeExposure(BaseModel):
    chain: str
    position_ref: str
    symbol: str
    delta_usd: float = 0.0
    mark_price_usd: float = Field(default=0.0, ge=0.0)
    snapshot_ts: int = Field(default=0, ge=0)
    freshness_age_seconds: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_symbol(self) -> "HedgeExposure":
        if not (self.symbol or "").strip():
            raise ValueError("hedge exposure symbol cannot be empty")
        return self


class HedgeIntent(BaseModel):
    intent_id: str
    action: HedgeAction
    side: HedgeSide = "NONE"
    chain: str
    symbol: str
    target_notional_usd: float = Field(default=0.0, ge=0.0)
    reason_codes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class HedgeDecision(BaseModel):
    allowed: bool
    reason_codes: list[str] = Field(default_factory=list)


class HedgeCounters(BaseModel):
    exposures_seen: int = 0
    intents_hedge: int = 0
    intents_hold: int = 0
    intents_skip: int = 0
    skipped_by_policy: int = 0
    skipped_by_data: int = 0
    connector_errors: int = 0


class HedgeExposureProvider(Protocol):
    async def list_exposures(self) -> list[HedgeExposure]: ...


class HedgeConnectorHealth(BaseModel):
    ok: bool
    auth_ok: bool = False
    instrument_ok: bool = False
    bbo_ok: bool = False
    reason_codes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class HedgeSimulationResult(BaseModel):
    ok: bool
    reason_codes: list[str] = Field(default_factory=list)
    expected_fill_price: float | None = Field(default=None, ge=0.0)
    mid_price: float | None = Field(default=None, ge=0.0)
    expected_slippage_bps: float | None = Field(default=None, ge=0.0)
    estimated_quantity: float | None = Field(default=None, ge=0.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class HedgeConnector(Protocol):
    async def probe_health(self, symbol: str) -> HedgeConnectorHealth: ...

    async def simulate_order(self, intent: HedgeIntent, *, max_slippage_bps: int) -> HedgeSimulationResult: ...
