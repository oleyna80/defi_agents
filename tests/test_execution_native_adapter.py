import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.execution.adapters import NativeUniswapV3Adapter
from defi_agents.execution.models import ActionIntent


def _run(coro):
    return asyncio.run(coro)


def test_native_adapter_build_compound_tx():
    adapter = NativeUniswapV3Adapter()
    intent = ActionIntent(
        intent_id="intent-1",
        action="COMPOUND",
        chain="Base",
        position_ref="pos-1",
        metadata={
            "position_manager": "0x1111111111111111111111111111111111111111",
            "compound_data_hex": "0xabc123",
            "estimated_compound_gas_usd": 2.5,
            "slippage_bps": 40,
            "gas_estimate": 250_000,
        },
    )
    tx = _run(adapter.build_compound_tx(intent))
    assert tx.plan_id.startswith("native-compound:")
    assert tx.intent_id == "intent-1"
    assert tx.to_address == "0x1111111111111111111111111111111111111111"
    assert tx.data_hex == "0xabc123"
    assert tx.gas_estimate_usd == 2.5
    assert tx.slippage_bps == 40

    sim = _run(adapter.simulate(tx))
    assert sim.ok is True
    assert sim.reason_codes == []


def test_native_adapter_build_rebalance_tx_with_fallback_fields():
    adapter = NativeUniswapV3Adapter()
    intent = ActionIntent(
        intent_id="intent-2",
        action="REBALANCE",
        chain="Arbitrum",
        position_ref="pos-2",
        metadata={
            "to_address": "0x2222222222222222222222222222222222222222",
            "data_hex": "0xdef456",
            "estimated_gas_usd": "4.0",
            "slippage_bps": "60",
        },
    )
    tx = _run(adapter.build_rebalance_tx(intent))
    assert tx.plan_id.startswith("native-rebalance:")
    assert tx.to_address == "0x2222222222222222222222222222222222222222"
    assert tx.data_hex == "0xdef456"
    assert tx.gas_estimate_usd == 4.0
    assert tx.slippage_bps == 60


def test_native_adapter_simulate_rejects_invalid_tx_plan():
    adapter = NativeUniswapV3Adapter()
    intent = ActionIntent(
        intent_id="intent-3",
        action="COMPOUND",
        chain="Base",
        position_ref="pos-3",
        metadata={},
    )
    tx = _run(adapter.build_compound_tx(intent))
    # No to_address in metadata -> invalid plan for simulation.
    sim = _run(adapter.simulate(tx))
    assert sim.ok is False
    assert "TX_PLAN_INVALID" in sim.reason_codes


def test_native_adapter_execute_is_fail_safe():
    adapter = NativeUniswapV3Adapter()
    intent = ActionIntent(
        intent_id="intent-4",
        action="REBALANCE",
        chain="Base",
        position_ref="pos-4",
        metadata={
            "to_address": "0x3333333333333333333333333333333333333333",
            "data_hex": "0xbeef",
        },
    )
    tx = _run(adapter.build_rebalance_tx(intent))
    receipt = _run(adapter.execute(tx))
    assert receipt.ok is False
    assert receipt.chain == "Base"
    assert "LIVE_EXECUTION_NOT_IMPLEMENTED" in receipt.reason_codes
