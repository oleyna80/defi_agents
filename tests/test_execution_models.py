import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.execution.models import (
    ActionIntent,
    ExecutionCounters,
    ExecutionReceipt,
    PolicyDecision,
    PositionState,
    SimulationResult,
    TxPlan,
)


def test_action_intent_contract():
    intent = ActionIntent(
        intent_id="intent-1",
        action="COMPOUND",
        chain="Base",
        position_ref="position-123",
        reason_codes=["COMPOUND_DUE"],
        expected_net_usd=4.2,
        metadata={"pool": "0xabc"},
    )
    assert intent.action == "COMPOUND"
    assert intent.chain == "Base"
    assert intent.reason_codes == ["COMPOUND_DUE"]
    assert intent.metadata["pool"] == "0xabc"


def test_tx_plan_rejects_invalid_numeric_fields():
    with pytest.raises(ValidationError):
        TxPlan(
            plan_id="plan-1",
            intent_id="intent-1",
            chain="Base",
            slippage_bps=-1,
        )


def test_execution_counters_defaults():
    counters = ExecutionCounters()
    assert counters.intent_count == 0
    assert counters.blocked_by_policy == 0
    assert counters.sim_ok == 0
    assert counters.sim_fail == 0
    assert counters.exec_ok == 0
    assert counters.exec_fail == 0


def test_simulation_and_receipt_contracts():
    simulation = SimulationResult(ok=False, reason_codes=["SIM_TIMEOUT"])
    assert simulation.ok is False
    assert simulation.reason_codes == ["SIM_TIMEOUT"]

    receipt = ExecutionReceipt(ok=True, chain="Base", tx_hash="0xdeadbeef")
    assert receipt.ok is True
    assert receipt.chain == "Base"
    assert receipt.tx_hash == "0xdeadbeef"

    decision = PolicyDecision(allowed=False, reason_codes=["MAX_SLIPPAGE_EXCEEDED"])
    assert decision.allowed is False
    assert decision.reason_codes == ["MAX_SLIPPAGE_EXCEEDED"]


def test_position_state_range_properties():
    state_center = PositionState(
        chain="Base",
        position_ref="pos-1",
        current_tick=100,
        lower_tick=80,
        upper_tick=120,
    )
    assert state_center.out_of_range is False
    assert state_center.range_utilization == pytest.approx(1.0)

    state_edge = PositionState(
        chain="Base",
        position_ref="pos-2",
        current_tick=80,
        lower_tick=80,
        upper_tick=120,
    )
    assert state_edge.out_of_range is False
    assert state_edge.range_utilization == pytest.approx(0.0)

    state_out = PositionState(
        chain="Base",
        position_ref="pos-3",
        current_tick=140,
        lower_tick=80,
        upper_tick=120,
    )
    assert state_out.out_of_range is True
    assert state_out.range_utilization == pytest.approx(0.0)


def test_position_state_accepts_optional_tx_fields():
    state = PositionState(
        chain="Base",
        position_ref="pos-4",
        current_tick=100,
        lower_tick=80,
        upper_tick=120,
        position_manager="0x1111111111111111111111111111111111111111",
        compound_data_hex="0xabc123",
        rebalance_data_hex="0xdef456",
        tx_value_wei=123,
    )
    assert state.position_manager == "0x1111111111111111111111111111111111111111"
    assert state.compound_data_hex == "0xabc123"
    assert state.rebalance_data_hex == "0xdef456"
    assert state.tx_value_wei == 123


def test_position_state_accepts_v3utils_structured_params():
    state = PositionState(
        chain="Base",
        position_ref="pos-5",
        current_tick=100,
        lower_tick=80,
        upper_tick=120,
        v3utils_compound_params={"nfpm": "0xabc", "token_id": 1, "instructions": {"recipient": "0xdef"}},
        v3utils_rebalance_params={"nfpm": "0xabc", "token_id": 1, "instructions": {"recipient": "0xdef"}},
    )
    assert isinstance(state.v3utils_compound_params, dict)
    assert isinstance(state.v3utils_rebalance_params, dict)
