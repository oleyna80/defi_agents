import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.execution.adapters import NativeUniswapV3Adapter
from defi_agents.execution.models import ActionIntent, PositionState
from defi_agents.execution.orchestrator import ExecutionOrchestrator
from defi_agents.execution.policy import PolicyGuard
from defi_agents.execution.triggers import TriggerEngine
from defi_agents.scout.config import ExecutionConfig


def _run(coro):
    return asyncio.run(coro)


def _state() -> PositionState:
    return PositionState(
        chain="Base",
        position_ref="pos-1",
        current_tick=100,
        lower_tick=80,
        upper_tick=120,
        unclaimed_fees_usd=10.0,
        estimated_compound_gas_usd=1.0,
    )


def _state_with_manager() -> PositionState:
    return PositionState(
        chain="Base",
        position_ref="pos-2",
        current_tick=100,
        lower_tick=80,
        upper_tick=120,
        unclaimed_fees_usd=10.0,
        estimated_compound_gas_usd=1.0,
        position_manager="0x1111111111111111111111111111111111111111",
        compound_data_hex="0xabc123",
    )


def test_orchestrator_paper_mode_builds_tx_plans_without_sim_or_exec():
    cfg = ExecutionConfig()
    orchestrator = ExecutionOrchestrator(
        mode="PAPER",
        trigger_engine=TriggerEngine(cfg),
        policy_guard=PolicyGuard(cfg.policy),
        adapter=NativeUniswapV3Adapter(),
    )
    report = _run(orchestrator.run_states([_state()], now_ts=1700000000))
    assert report.mode == "PAPER"
    assert report.counters.intent_count == 1
    assert report.counters.blocked_by_policy == 0
    assert report.counters.sim_ok == 0
    assert report.counters.sim_fail == 0
    assert report.counters.exec_ok == 0
    assert report.counters.exec_fail == 0
    assert len(report.tx_plans) == 1


def test_orchestrator_respects_policy_blocks():
    cfg = ExecutionConfig(policy={"min_expected_net_usd": 20.0})
    orchestrator = ExecutionOrchestrator(
        mode="PAPER",
        trigger_engine=TriggerEngine(cfg),
        policy_guard=PolicyGuard(cfg.policy),
        adapter=NativeUniswapV3Adapter(),
    )
    report = _run(orchestrator.run_states([_state()], now_ts=1700000000))
    assert report.counters.intent_count == 1
    assert report.counters.blocked_by_policy == 1
    assert len(report.tx_plans) == 0
    assert report.policy_block_reason_counts.get("MIN_EXPECTED_NET_NOT_MET") == 1


def test_orchestrator_shadow_mode_records_sim_failure_on_invalid_plan():
    cfg = ExecutionConfig()
    orchestrator = ExecutionOrchestrator(
        mode="SHADOW",
        trigger_engine=TriggerEngine(cfg),
        policy_guard=PolicyGuard(cfg.policy),
        adapter=NativeUniswapV3Adapter(),
    )
    report = _run(orchestrator.run_states([_state()], now_ts=1700000000))
    assert report.counters.intent_count == 1
    assert len(report.tx_plans) == 1
    assert report.counters.sim_ok == 0
    assert report.counters.sim_fail == 1
    assert report.sim_fail_reason_counts.get("TX_PLAN_INVALID") == 1


def test_orchestrator_shadow_mode_records_sim_ok_with_valid_plan():
    cfg = ExecutionConfig()
    orchestrator = ExecutionOrchestrator(
        mode="SHADOW",
        trigger_engine=TriggerEngine(cfg),
        policy_guard=PolicyGuard(cfg.policy),
        adapter=NativeUniswapV3Adapter(),
    )
    report = _run(orchestrator.run_states([_state_with_manager()], now_ts=1700000000))
    assert report.counters.intent_count == 1
    assert len(report.tx_plans) == 1
    assert report.counters.sim_ok == 1
    assert report.counters.sim_fail == 0


def test_orchestrator_live_mode_records_exec_failure_on_safe_stub():
    cfg = ExecutionConfig()
    trigger = TriggerEngine(cfg)

    def _fake_evaluate(_state: PositionState, now_ts: int | None = None) -> ActionIntent:
        return ActionIntent(
            intent_id=f"intent:{now_ts or 0}",
            action="COMPOUND",
            chain="Base",
            position_ref="pos-live",
            expected_net_usd=10.0,
            metadata={
                "estimated_gas_usd": 1.0,
                "slippage_bps": 10,
                "to_address": "0x1234567890123456789012345678901234567890",
                "data_hex": "0xabc123",
            },
        )

    trigger.evaluate_position = _fake_evaluate  # type: ignore[method-assign]

    orchestrator = ExecutionOrchestrator(
        mode="LIVE",
        trigger_engine=trigger,
        policy_guard=PolicyGuard(cfg.policy),
        adapter=NativeUniswapV3Adapter(),
    )
    report = _run(orchestrator.run_states([_state()], now_ts=1700000000))
    assert report.counters.intent_count == 1
    assert report.counters.sim_ok == 1
    assert report.counters.exec_ok == 0
    assert report.counters.exec_fail == 1
    assert report.exec_fail_reason_counts.get("LIVE_EXECUTION_NOT_IMPLEMENTED") == 1
