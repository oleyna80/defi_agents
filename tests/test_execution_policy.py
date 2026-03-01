import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.execution.models import ActionIntent, ExecutionCounters
from defi_agents.execution.policy import PolicyGuard
from defi_agents.scout.config import ExecutionPolicyConfig


def _intent(
    *,
    action: str = "COMPOUND",
    expected_net_usd: float = 10.0,
    metadata: dict | None = None,
) -> ActionIntent:
    return ActionIntent(
        intent_id="intent-1",
        action=action,
        chain="Base",
        position_ref="pos-1",
        expected_net_usd=expected_net_usd,
        metadata=metadata or {},
    )


def test_policy_blocks_on_kill_switch_and_tracks_counter_journal():
    guard = PolicyGuard(ExecutionPolicyConfig(kill_switch=True))
    counters = ExecutionCounters()
    decision = guard.evaluate(
        _intent(metadata={"estimated_gas_usd": 2.0, "slippage_bps": 20}),
        counters=counters,
        now_ts=1700000000,
    )
    assert decision.allowed is False
    assert "KILL_SWITCH_ENABLED" in decision.reason_codes
    assert counters.blocked_by_policy == 1

    journal = guard.get_journal()
    assert len(journal) == 1
    assert journal[0].allowed is False
    assert journal[0].intent_id == "intent-1"


def test_policy_blocks_when_expected_net_below_threshold():
    guard = PolicyGuard(ExecutionPolicyConfig(min_expected_net_usd=5.0))
    decision = guard.evaluate(
        _intent(expected_net_usd=2.0, metadata={"estimated_gas_usd": 1.0, "slippage_bps": 10}),
        now_ts=1700000000,
    )
    assert decision.allowed is False
    assert "MIN_EXPECTED_NET_NOT_MET" in decision.reason_codes


def test_policy_blocks_when_gas_or_slippage_missing():
    guard = PolicyGuard(ExecutionPolicyConfig())
    decision = guard.evaluate(_intent(), now_ts=1700000000)
    assert decision.allowed is False
    assert "GAS_ESTIMATE_MISSING" in decision.reason_codes
    assert "SLIPPAGE_BPS_MISSING" in decision.reason_codes


def test_policy_blocks_when_gas_or_slippage_exceeds_limits():
    guard = PolicyGuard(ExecutionPolicyConfig(max_gas_usd_per_tx=5.0, max_slippage_bps=50))
    decision = guard.evaluate(
        _intent(metadata={"estimated_gas_usd": 8.0, "slippage_bps": 75}),
        now_ts=1700000000,
    )
    assert decision.allowed is False
    assert "MAX_GAS_USD_PER_TX_EXCEEDED" in decision.reason_codes
    assert "MAX_SLIPPAGE_BPS_EXCEEDED" in decision.reason_codes


def test_policy_blocks_on_daily_budgets():
    guard = PolicyGuard(
        ExecutionPolicyConfig(max_daily_txs=1, max_daily_gas_usd=5.0),
    )
    guard.record_executed_tx(4.0, now_ts=1700000000)
    decision = guard.evaluate(
        _intent(metadata={"estimated_gas_usd": 2.0, "slippage_bps": 10}),
        now_ts=1700000000,
    )
    assert decision.allowed is False
    assert "MAX_DAILY_TXS_REACHED" in decision.reason_codes
    assert "MAX_DAILY_GAS_USD_REACHED" in decision.reason_codes


def test_policy_allows_safe_intent_and_uses_metadata_fallback():
    guard = PolicyGuard(ExecutionPolicyConfig())
    decision = guard.evaluate(
        _intent(metadata={"estimated_gas_usd": "2.5", "slippage_bps": "30"}),
        now_ts=1700000000,
    )
    assert decision.allowed is True
    assert decision.reason_codes == []

    journal = guard.get_journal(limit=1)
    assert journal[0].estimated_gas_usd == pytest.approx(2.5)
    assert journal[0].slippage_bps == 30


def test_policy_day_rollover_resets_daily_usage():
    guard = PolicyGuard(ExecutionPolicyConfig(max_daily_txs=1, max_daily_gas_usd=100.0))
    guard.record_executed_tx(1.0, now_ts=1700000000)

    blocked_same_day = guard.evaluate(
        _intent(metadata={"estimated_gas_usd": 1.0, "slippage_bps": 10}),
        now_ts=1700000100,
    )
    assert blocked_same_day.allowed is False
    assert "MAX_DAILY_TXS_REACHED" in blocked_same_day.reason_codes

    allowed_next_day = guard.evaluate(
        _intent(metadata={"estimated_gas_usd": 1.0, "slippage_bps": 10}),
        now_ts=1700086500,  # next UTC day
    )
    assert allowed_next_day.allowed is True


def test_policy_skip_intent_is_allowed():
    guard = PolicyGuard(ExecutionPolicyConfig(kill_switch=True))
    decision = guard.evaluate(_intent(action="SKIP"), now_ts=1700000000)
    assert decision.allowed is True
    assert decision.reason_codes == []


def test_policy_enforces_stale_guard_only_when_enabled():
    guard = PolicyGuard(ExecutionPolicyConfig())
    intent = _intent(
        expected_net_usd=10.0,
        metadata={"estimated_gas_usd": 1.0, "slippage_bps": 10, "stale_position_data": True},
    )

    decision_shadow = guard.evaluate(intent, enforce_stale_guard=False, now_ts=1700000000)
    assert decision_shadow.allowed is True

    decision_live = guard.evaluate(intent, enforce_stale_guard=True, now_ts=1700000001)
    assert decision_live.allowed is False
    assert "STALE_POSITION_DATA" in decision_live.reason_codes
