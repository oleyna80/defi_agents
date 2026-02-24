import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.execution.models import PositionState
from defi_agents.execution.triggers import TriggerEngine
from defi_agents.scout.config import ExecutionConfig


def _engine(**kwargs) -> TriggerEngine:
    cfg = ExecutionConfig(**kwargs)
    return TriggerEngine(cfg)


def test_trigger_rebalance_when_out_of_range():
    engine = _engine()
    state = PositionState(
        chain="Base",
        position_ref="pos-1",
        current_tick=135,
        lower_tick=80,
        upper_tick=120,
        expected_rebalance_net_usd=9.0,
        estimated_rebalance_gas_usd=1.5,
    )
    intent = engine.evaluate_position(state, now_ts=1700000000)
    assert intent.action == "REBALANCE"
    assert "OUT_OF_RANGE" in intent.reason_codes
    assert intent.expected_net_usd == pytest.approx(7.5)


def test_trigger_rebalance_when_low_range_utilization():
    engine = _engine(rebalance_min_range_utilization=0.20)
    state = PositionState(
        chain="Base",
        position_ref="pos-2",
        current_tick=82,
        lower_tick=80,
        upper_tick=120,
    )
    intent = engine.evaluate_position(state, now_ts=1700000000)
    assert intent.action == "REBALANCE"
    assert "LOW_RANGE_UTILIZATION" in intent.reason_codes


def test_trigger_rebalance_when_edge_decay_high():
    engine = _engine(rebalance_edge_decay_bps=250)
    state = PositionState(
        chain="Base",
        position_ref="pos-3",
        current_tick=100,
        lower_tick=80,
        upper_tick=120,
        edge_decay_bps=260,
    )
    intent = engine.evaluate_position(state, now_ts=1700000000)
    assert intent.action == "REBALANCE"
    assert "EDGE_DECAY" in intent.reason_codes


def test_trigger_rebalance_priority_over_compound():
    engine = _engine(compound_min_fees_usd=5.0)
    state = PositionState(
        chain="Base",
        position_ref="pos-4",
        current_tick=130,
        lower_tick=80,
        upper_tick=120,
        unclaimed_fees_usd=100.0,
    )
    intent = engine.evaluate_position(state, now_ts=1700000000)
    assert intent.action == "REBALANCE"
    assert "OUT_OF_RANGE" in intent.reason_codes
    assert "COMPOUND_DUE" not in intent.reason_codes


def test_trigger_compound_when_fees_above_threshold():
    engine = _engine(compound_min_fees_usd=5.0)
    state = PositionState(
        chain="Base",
        position_ref="pos-5",
        current_tick=100,
        lower_tick=80,
        upper_tick=120,
        unclaimed_fees_usd=7.0,
        estimated_compound_gas_usd=1.2,
    )
    intent = engine.evaluate_position(state, now_ts=1700000000)
    assert intent.action == "COMPOUND"
    assert intent.reason_codes == ["COMPOUND_DUE"]
    assert intent.expected_net_usd == pytest.approx(5.8)


def test_trigger_hold_when_no_conditions():
    engine = _engine(compound_min_fees_usd=10.0, rebalance_edge_decay_bps=300)
    state = PositionState(
        chain="Base",
        position_ref="pos-6",
        current_tick=100,
        lower_tick=80,
        upper_tick=120,
        unclaimed_fees_usd=2.0,
        edge_decay_bps=50,
    )
    intent = engine.evaluate_position(state, now_ts=1700000000)
    assert intent.action == "SKIP"
    assert intent.reason_codes == ["HOLD"]
    assert intent.expected_net_usd == pytest.approx(0.0)


def test_trigger_cooldown_blocks_actions():
    engine = _engine(per_position_cooldown_seconds=3600)
    state = PositionState(
        chain="Base",
        position_ref="pos-7",
        current_tick=130,
        lower_tick=80,
        upper_tick=120,
        last_rebalance_ts=1700000000 - 1200,
        unclaimed_fees_usd=20.0,
    )
    intent = engine.evaluate_position(state, now_ts=1700000000)
    assert intent.action == "SKIP"
    assert "COOLDOWN_ACTIVE" in intent.reason_codes
    assert "OUT_OF_RANGE" in intent.reason_codes


def test_trigger_passes_position_manager_into_intent_metadata():
    engine = _engine(compound_min_fees_usd=5.0)
    state = PositionState(
        chain="Base",
        position_ref="pos-8",
        current_tick=100,
        lower_tick=80,
        upper_tick=120,
        unclaimed_fees_usd=9.0,
        estimated_compound_gas_usd=1.0,
        position_manager="0x1111111111111111111111111111111111111111",
        compound_data_hex="0xabc123",
    )
    intent = engine.evaluate_position(state, now_ts=1700000000)
    assert intent.action == "COMPOUND"
    assert intent.metadata.get("position_manager") == "0x1111111111111111111111111111111111111111"
    assert intent.metadata.get("compound_data_hex") == "0xabc123"
