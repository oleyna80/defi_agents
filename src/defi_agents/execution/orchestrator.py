from __future__ import annotations

from pydantic import BaseModel, Field

from .models import ExecutionAdapter, ExecutionCounters, ExecutionMode, PositionState, TxPlan
from .policy import PolicyGuard
from .triggers import TriggerEngine


class ExecutionRunReport(BaseModel):
    mode: ExecutionMode
    counters: ExecutionCounters = Field(default_factory=ExecutionCounters)
    tx_plans: list[TxPlan] = Field(default_factory=list)
    policy_block_reason_counts: dict[str, int] = Field(default_factory=dict)
    sim_fail_reason_counts: dict[str, int] = Field(default_factory=dict)
    exec_fail_reason_counts: dict[str, int] = Field(default_factory=dict)


class ExecutionOrchestrator:
    """Execution orchestration loop for PAPER/SHADOW/LIVE modes."""

    def __init__(
        self,
        *,
        mode: ExecutionMode,
        trigger_engine: TriggerEngine,
        policy_guard: PolicyGuard,
        adapter: ExecutionAdapter,
    ) -> None:
        self.mode = mode
        self.trigger_engine = trigger_engine
        self.policy_guard = policy_guard
        self.adapter = adapter

    async def run_states(self, states: list[PositionState], *, now_ts: int | None = None) -> ExecutionRunReport:
        report = ExecutionRunReport(mode=self.mode)
        for state in states:
            intent = self.trigger_engine.evaluate_position(state, now_ts=now_ts)
            report.counters.intent_count += 1
            if intent.action == "SKIP":
                continue

            decision = self.policy_guard.evaluate(intent, counters=report.counters, now_ts=now_ts)
            if not decision.allowed:
                self._bump_reasons(report.policy_block_reason_counts, decision.reason_codes)
                continue

            if intent.action == "COMPOUND":
                tx_plan = await self.adapter.build_compound_tx(intent)
            else:
                tx_plan = await self.adapter.build_rebalance_tx(intent)
            report.tx_plans.append(tx_plan)

            if self.mode == "PAPER":
                continue

            sim = await self.adapter.simulate(tx_plan)
            if sim.ok:
                report.counters.sim_ok += 1
            else:
                report.counters.sim_fail += 1
                self._bump_reasons(report.sim_fail_reason_counts, sim.reason_codes)
                continue

            if self.mode == "SHADOW":
                continue

            receipt = await self.adapter.execute(tx_plan)
            if receipt.ok:
                report.counters.exec_ok += 1
                if receipt.gas_used_usd is not None:
                    self.policy_guard.record_executed_tx(receipt.gas_used_usd, now_ts=now_ts)
            else:
                report.counters.exec_fail += 1
                self._bump_reasons(report.exec_fail_reason_counts, receipt.reason_codes)

        return report

    @staticmethod
    def _bump_reasons(bucket: dict[str, int], reasons: list[str]) -> None:
        if not reasons:
            bucket["UNKNOWN"] = bucket.get("UNKNOWN", 0) + 1
            return
        for reason in reasons:
            key = str(reason or "UNKNOWN")
            bucket[key] = bucket.get(key, 0) + 1
