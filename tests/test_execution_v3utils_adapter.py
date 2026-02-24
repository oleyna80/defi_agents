import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.execution.adapters import V3UtilsAdapterError, V3UtilsExecutionAdapter
from defi_agents.execution.models import ActionIntent


def _run(coro):
    return asyncio.run(coro)


def test_v3utils_build_compound_tx_uses_chain_contract_and_metadata_data():
    adapter = V3UtilsExecutionAdapter(
        rpc_urls={"Base": "https://base-rpc.local"},
        contracts_by_chain={"Base": "0x1111111111111111111111111111111111111111"},
        default_slippage_bps=45,
    )
    intent = ActionIntent(
        intent_id="intent-c",
        action="COMPOUND",
        chain="Base",
        position_ref="pos-1",
        metadata={
            "v3utils_compound_data_hex": "0xabc123",
            "estimated_compound_gas_usd": 1.2,
            "gas_estimate": 220000,
        },
    )
    tx = _run(adapter.build_compound_tx(intent))
    assert tx.plan_id == "v3utils-compound:intent-c"
    assert tx.to_address == "0x1111111111111111111111111111111111111111"
    assert tx.data_hex == "0xabc123"
    assert tx.gas_estimate == 220000
    assert tx.gas_estimate_usd == 1.2
    assert tx.slippage_bps == 45
    assert tx.metadata["adapter"] == "v3utils"
    assert tx.metadata["v3utils_upstream_commit"] == "33f487253051c3d6f439dc911b0e415b28b4cc9c"
    assert tx.metadata["v3utils_abi_file"] == "v3utils_execute.abi.json"


def test_v3utils_build_compound_tx_from_structured_params_encodes_execute_call():
    adapter = V3UtilsExecutionAdapter(
        rpc_urls={"Base": "https://base-rpc.local"},
        contracts_by_chain={"Base": "0x1111111111111111111111111111111111111111"},
        default_slippage_bps=45,
    )
    intent = ActionIntent(
        intent_id="intent-structured",
        action="COMPOUND",
        chain="Base",
        position_ref="pos-structured",
        metadata={
            "v3utils_compound_params": {
                "nfpm": "0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1",
                "token_id": 12345,
                "instructions": {
                    "protocol": 0,
                    "target_token": "0x0000000000000000000000000000000000000000",
                    "amount_in_0": 0,
                    "amount_in_1": 0,
                    "amount_add_min_0": 1,
                    "amount_add_min_1": 1,
                    "deadline": 1700001234,
                    "recipient": "0x1234567890123456789012345678901234567890",
                    "swap_data_0": "0x",
                    "swap_data_1": "0x",
                },
            }
        },
    )
    tx = _run(adapter.build_compound_tx(intent))
    assert tx.data_hex.startswith("0xfd2d17d1")
    assert len(tx.data_hex) > 10
    assert tx.to_address == "0x1111111111111111111111111111111111111111"
    assert tx.metadata["v3utils_payload_mode"] == "structured_compound"


def test_v3utils_build_rebalance_tx_uses_override_contract():
    adapter = V3UtilsExecutionAdapter(
        rpc_urls={"Base": "https://base-rpc.local"},
        contracts_by_chain={"Base": "0x1111111111111111111111111111111111111111"},
    )
    intent = ActionIntent(
        intent_id="intent-r",
        action="REBALANCE",
        chain="Base",
        position_ref="pos-2",
        metadata={
            "v3utils_contract": "0x2222222222222222222222222222222222222222",
            "v3utils_rebalance_data_hex": "0xdef456",
            "slippage_bps": "60",
        },
    )
    tx = _run(adapter.build_rebalance_tx(intent))
    assert tx.plan_id == "v3utils-rebalance:intent-r"
    assert tx.to_address == "0x2222222222222222222222222222222222222222"
    assert tx.data_hex == "0xdef456"
    assert tx.slippage_bps == 60
    assert tx.metadata["v3utils_payload_mode"] == "raw_hex"


def test_v3utils_build_rebalance_tx_from_structured_params_encodes_execute_call():
    adapter = V3UtilsExecutionAdapter(
        rpc_urls={"Base": "https://base-rpc.local"},
        contracts_by_chain={"Base": "0x1111111111111111111111111111111111111111"},
    )
    intent = ActionIntent(
        intent_id="intent-r-structured",
        action="REBALANCE",
        chain="Base",
        position_ref="pos-r-structured",
        metadata={
            "v3utils_rebalance_params": {
                "nfpm": "0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1",
                "token_id": 12345,
                "instructions": {
                    "protocol": 0,
                    "tick_lower": -120,
                    "tick_upper": 120,
                    "amount_add_min_0": 1,
                    "amount_add_min_1": 1,
                    "deadline": 1700001234,
                    "recipient": "0x1234567890123456789012345678901234567890",
                },
            }
        },
    )
    tx = _run(adapter.build_rebalance_tx(intent))
    assert tx.plan_id == "v3utils-rebalance:intent-r-structured"
    assert tx.data_hex.startswith("0xfd2d17d1")
    assert tx.metadata["v3utils_payload_mode"] == "structured_rebalance"


def test_v3utils_build_compound_fails_without_data_hex():
    adapter = V3UtilsExecutionAdapter(
        rpc_urls={"Base": "https://base-rpc.local"},
        contracts_by_chain={"Base": "0x1111111111111111111111111111111111111111"},
    )
    intent = ActionIntent(
        intent_id="intent-missing",
        action="COMPOUND",
        chain="Base",
        position_ref="pos-3",
        metadata={},
    )
    with pytest.raises(V3UtilsAdapterError, match="V3UTILS_DATA_HEX_MISSING"):
        _run(adapter.build_compound_tx(intent))


def test_v3utils_build_compound_structured_fails_without_recipient():
    adapter = V3UtilsExecutionAdapter(
        rpc_urls={"Base": "https://base-rpc.local"},
        contracts_by_chain={"Base": "0x1111111111111111111111111111111111111111"},
    )
    intent = ActionIntent(
        intent_id="intent-missing-recipient",
        action="COMPOUND",
        chain="Base",
        position_ref="pos-4",
        metadata={
            "v3utils_compound_params": {
                "nfpm": "0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1",
                "token_id": 123,
                "instructions": {
                    "deadline": 1700001234,
                },
            }
        },
    )
    with pytest.raises(V3UtilsAdapterError, match="V3UTILS_ADDRESS_MISSING"):
        _run(adapter.build_compound_tx(intent))


def test_v3utils_build_rebalance_structured_fails_without_ticks():
    adapter = V3UtilsExecutionAdapter(
        rpc_urls={"Base": "https://base-rpc.local"},
        contracts_by_chain={"Base": "0x1111111111111111111111111111111111111111"},
    )
    intent = ActionIntent(
        intent_id="intent-r-missing-ticks",
        action="REBALANCE",
        chain="Base",
        position_ref="pos-r-5",
        metadata={
            "v3utils_rebalance_params": {
                "nfpm": "0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1",
                "token_id": 999,
                "instructions": {
                    "deadline": 1700001234,
                    "recipient": "0x1234567890123456789012345678901234567890",
                },
            }
        },
    )
    with pytest.raises(V3UtilsAdapterError, match="V3UTILS_REBALANCE_TICKS_MISSING"):
        _run(adapter.build_rebalance_tx(intent))


def test_v3utils_simulate_ok_for_structured_payload():
    adapter = V3UtilsExecutionAdapter(
        rpc_urls={"Base": "https://base-rpc.local"},
        contracts_by_chain={"Base": "0x1111111111111111111111111111111111111111"},
    )
    intent = ActionIntent(
        intent_id="intent-sim-structured",
        action="COMPOUND",
        chain="Base",
        position_ref="pos-sim-1",
        metadata={
            "v3utils_compound_params": {
                "nfpm": "0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1",
                "token_id": 12345,
                "instructions": {
                    "recipient": "0x1234567890123456789012345678901234567890",
                },
            }
        },
    )
    tx = _run(adapter.build_compound_tx(intent))
    sim = _run(adapter.simulate(tx))
    assert sim.ok is True
    assert sim.metadata["adapter"] == "v3utils"
    assert sim.metadata["payload_mode"] == "structured_compound"


def test_v3utils_simulate_fails_on_selector_mismatch_for_structured_payload():
    adapter = V3UtilsExecutionAdapter(
        rpc_urls={"Base": "https://base-rpc.local"},
        contracts_by_chain={"Base": "0x1111111111111111111111111111111111111111"},
    )
    intent = ActionIntent(
        intent_id="intent-sim-mismatch",
        action="COMPOUND",
        chain="Base",
        position_ref="pos-sim-2",
        metadata={
            "v3utils_compound_params": {
                "nfpm": "0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1",
                "token_id": 12345,
                "instructions": {
                    "recipient": "0x1234567890123456789012345678901234567890",
                },
            }
        },
    )
    tx = _run(adapter.build_compound_tx(intent))
    tx.data_hex = "0xdeadbeef"
    sim = _run(adapter.simulate(tx))
    assert sim.ok is False
    assert sim.reason_codes == ["V3UTILS_SELECTOR_MISMATCH"]


def test_v3utils_execute_reuses_native_live_transport():
    async def _request(_url: str, payload: dict, _timeout: float) -> dict:
        if payload["method"] == "eth_sendRawTransaction":
            return {"jsonrpc": "2.0", "id": 1, "result": "0xhash"}
        return {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"status": "0x1", "gasUsed": "0x5208", "blockNumber": "0x222"},
        }

    adapter = V3UtilsExecutionAdapter(
        rpc_urls={"Base": "https://base-rpc.local"},
        contracts_by_chain={"Base": "0x1111111111111111111111111111111111111111"},
        request_fn=_request,
    )
    intent = ActionIntent(
        intent_id="intent-live",
        action="COMPOUND",
        chain="Base",
        position_ref="pos-live",
        metadata={
            "v3utils_compound_data_hex": "0xabc",
            "signed_raw_tx": "0xdeadbeef",
        },
    )
    tx = _run(adapter.build_compound_tx(intent))
    receipt = _run(adapter.execute(tx))
    assert receipt.ok is True
    assert receipt.tx_hash == "0xhash"
