import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.execution.adapters import KrystalAdapterError, KrystalExecutionAdapter
from defi_agents.execution.models import ActionIntent, TxPlan


def _run(coro):
    return asyncio.run(coro)


def test_krystal_adapter_requires_api_key():
    with pytest.raises(ValueError):
        KrystalExecutionAdapter(base_url="https://cloud-api.krystal.app", api_key="")


def test_krystal_build_compound_tx_parses_response():
    calls: list[tuple[str, dict, dict]] = []

    async def fake_request(path, payload, headers):
        calls.append((path, payload, headers))
        return {
            "data": {
                "tx": {
                    "to": "0x1111111111111111111111111111111111111111",
                    "data": "0xabc123",
                    "value": "0",
                    "gasEstimate": "240000",
                    "gasEstimateUsd": "2.4",
                    "slippageBps": "50",
                }
            }
        }

    adapter = KrystalExecutionAdapter(
        base_url="https://cloud-api.krystal.app",
        api_key="test-key",
        request_fn=fake_request,
    )
    intent = ActionIntent(
        intent_id="intent-1",
        action="COMPOUND",
        chain="Base",
        position_ref="pos-1",
        expected_net_usd=8.0,
    )
    tx = _run(adapter.build_compound_tx(intent))
    assert tx.plan_id.startswith("krystal-compound:")
    assert tx.to_address == "0x1111111111111111111111111111111111111111"
    assert tx.data_hex == "0xabc123"
    assert tx.gas_estimate == 240000
    assert tx.gas_estimate_usd == pytest.approx(2.4)
    assert tx.slippage_bps == 50
    assert calls[0][0] == "/v1/execution/compound/build"
    assert calls[0][2]["KC-APIKey"] == "test-key"


def test_krystal_simulate_and_execute_parsing():
    async def fake_request(path, payload, headers):
        if path.endswith("/simulate"):
            return {"data": {"ok": False, "errorCode": "SIM_FAIL", "gasUsed": "250000"}}
        if path.endswith("/execute"):
            return {"data": {"ok": True, "txHash": "0xdeadbeef", "blockNumber": "123"}}
        raise AssertionError(f"unexpected path: {path}")

    adapter = KrystalExecutionAdapter(
        base_url="https://cloud-api.krystal.app",
        api_key="test-key",
        request_fn=fake_request,
    )
    tx = TxPlan(
        plan_id="plan-1",
        intent_id="intent-1",
        chain="Base",
        to_address="0x1111111111111111111111111111111111111111",
        data_hex="0xabc123",
    )
    sim = _run(adapter.simulate(tx))
    assert sim.ok is False
    assert "SIM_FAIL" in sim.reason_codes
    assert sim.estimated_gas_used == 250000

    receipt = _run(adapter.execute(tx))
    assert receipt.ok is True
    assert receipt.tx_hash == "0xdeadbeef"
    assert receipt.block_number == 123


def test_krystal_build_rebalance_tx_raises_on_missing_tx_payload():
    async def fake_request(path, payload, headers):
        return {"data": {"ok": True}}

    adapter = KrystalExecutionAdapter(
        base_url="https://cloud-api.krystal.app",
        api_key="test-key",
        request_fn=fake_request,
    )
    intent = ActionIntent(
        intent_id="intent-2",
        action="REBALANCE",
        chain="Base",
        position_ref="pos-2",
    )
    with pytest.raises(KrystalAdapterError):
        _run(adapter.build_rebalance_tx(intent))


def test_krystal_adapter_short_circuits_when_execution_api_marked_unavailable():
    calls = 0

    async def fake_request(path, payload, headers):
        nonlocal calls
        calls += 1
        return {"data": {"ok": True}}

    adapter = KrystalExecutionAdapter(
        base_url="https://cloud-api.krystal.app",
        api_key="test-key",
        request_fn=fake_request,
    )
    # Simulate previously observed 404 on execution endpoints.
    adapter._execution_api_available = False  # noqa: SLF001
    tx = TxPlan(
        plan_id="plan-1",
        intent_id="intent-1",
        chain="Base",
        to_address="0x1111111111111111111111111111111111111111",
        data_hex="0xabc123",
    )
    with pytest.raises(KrystalAdapterError, match="KRYSTAL_EXECUTION_API_UNAVAILABLE"):
        _run(adapter.simulate(tx))
    assert calls == 0
