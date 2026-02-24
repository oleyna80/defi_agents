from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

ExecutionMode = Literal["PAPER", "SHADOW", "LIVE"]
ActionType = Literal["COMPOUND", "REBALANCE", "SKIP"]


class ActionIntent(BaseModel):
    intent_id: str
    action: ActionType
    chain: str
    position_ref: str
    reason_codes: list[str] = Field(default_factory=list)
    expected_net_usd: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class PositionState(BaseModel):
    chain: str
    position_ref: str
    current_tick: int
    lower_tick: int
    upper_tick: int
    liquidity: float = Field(default=0.0, ge=0.0)
    unclaimed_fees_usd: float = Field(default=0.0, ge=0.0)
    position_value_usd: float = Field(default=0.0, ge=0.0)
    last_rebalance_ts: int | None = Field(default=None, ge=0)
    estimated_compound_gas_usd: float = Field(default=0.0, ge=0.0)
    estimated_rebalance_gas_usd: float = Field(default=0.0, ge=0.0)
    edge_decay_bps: int = Field(default=0, ge=0, le=10_000)
    expected_rebalance_net_usd: float = 0.0
    expected_slippage_bps: int = Field(default=50, ge=0, le=10_000)
    position_manager: str | None = None
    compound_data_hex: str | None = None
    rebalance_data_hex: str | None = None
    v3utils_compound_params: dict[str, Any] | None = None
    v3utils_rebalance_params: dict[str, Any] | None = None
    tx_value_wei: int = Field(default=0, ge=0)

    @property
    def out_of_range(self) -> bool:
        return self.current_tick < self.lower_tick or self.current_tick > self.upper_tick

    @property
    def range_utilization(self) -> float:
        width = self.upper_tick - self.lower_tick
        if width <= 0:
            return 0.0
        if self.out_of_range:
            return 0.0
        distance_to_edge = min(self.current_tick - self.lower_tick, self.upper_tick - self.current_tick)
        half_width = max(width / 2.0, 1.0)
        return max(0.0, min(1.0, float(distance_to_edge) / float(half_width)))


class PolicyDecision(BaseModel):
    allowed: bool
    reason_codes: list[str] = Field(default_factory=list)


class TxPlan(BaseModel):
    plan_id: str
    intent_id: str
    chain: str
    to_address: str = ""
    data_hex: str = ""
    value_wei: int = Field(default=0, ge=0)
    gas_estimate: int | None = Field(default=None, ge=0)
    gas_estimate_usd: float | None = Field(default=None, ge=0.0)
    slippage_bps: int | None = Field(default=None, ge=0, le=10_000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SimulationResult(BaseModel):
    ok: bool
    reason_codes: list[str] = Field(default_factory=list)
    estimated_gas_used: int | None = Field(default=None, ge=0)
    estimated_gas_usd: float | None = Field(default=None, ge=0.0)
    expected_net_usd: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionReceipt(BaseModel):
    ok: bool
    chain: str
    tx_hash: str | None = None
    block_number: int | None = Field(default=None, ge=0)
    gas_used: int | None = Field(default=None, ge=0)
    gas_used_usd: float | None = Field(default=None, ge=0.0)
    reason_codes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionCounters(BaseModel):
    intent_count: int = 0
    blocked_by_policy: int = 0
    sim_ok: int = 0
    sim_fail: int = 0
    exec_ok: int = 0
    exec_fail: int = 0


class ExecutionAdapter(Protocol):
    async def build_compound_tx(self, intent: ActionIntent) -> TxPlan: ...

    async def build_rebalance_tx(self, intent: ActionIntent) -> TxPlan: ...

    async def simulate(self, tx: TxPlan) -> SimulationResult: ...

    async def execute(self, tx: TxPlan) -> ExecutionReceipt: ...


class PositionStateProvider(Protocol):
    async def get_position_state(self, chain: str, position_ref: str) -> PositionState: ...
