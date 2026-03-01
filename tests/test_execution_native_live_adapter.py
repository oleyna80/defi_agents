import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.execution.adapters import NativeLiveExecutionAdapter
from defi_agents.execution.models import TxPlan


def _run(coro):
    return asyncio.run(coro)


def _tx_plan(**metadata) -> TxPlan:
    return TxPlan(
        plan_id="plan-1",
        intent_id="intent-1",
        chain="Base",
        to_address="0x1111111111111111111111111111111111111111",
        data_hex="0xabcdef",
        gas_estimate=200_000,
        gas_estimate_usd=1.5,
        metadata=metadata,
    )


def test_native_live_execute_success_waits_for_receipt():
    calls: list[str] = []
    receipt_calls = 0

    async def _request(_url: str, payload: dict, _timeout: float) -> dict:
        nonlocal receipt_calls
        method = payload["method"]
        calls.append(method)
        if method == "eth_sendRawTransaction":
            return {"jsonrpc": "2.0", "id": 1, "result": "0xhash"}
        if method == "eth_getTransactionReceipt":
            receipt_calls += 1
            if receipt_calls == 1:
                return {"jsonrpc": "2.0", "id": 1, "result": None}
            return {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "status": "0x1",
                    "gasUsed": "0x5208",
                    "blockNumber": "0x123",
                    "effectiveGasPrice": "0x3b9aca00",
                },
            }
        return {"jsonrpc": "2.0", "id": 1, "result": None}

    async def _sleep(_seconds: float) -> None:
        return None

    adapter = NativeLiveExecutionAdapter(
        rpc_urls={"Base": "https://base-rpc.local"},
        request_fn=_request,
        sleep_fn=_sleep,
        receipt_timeout_seconds=2.0,
        receipt_poll_seconds=0.1,
    )
    tx = _tx_plan(signed_raw_tx="0xdeadbeef", native_token_price_usd=2500.0)
    receipt = _run(adapter.execute(tx))

    assert receipt.ok is True
    assert receipt.tx_hash == "0xhash"
    assert receipt.block_number == 0x123
    assert receipt.gas_used == 0x5208
    assert receipt.gas_used_usd is not None
    assert "eth_sendRawTransaction" in calls
    assert calls.count("eth_getTransactionReceipt") >= 2


def test_native_live_execute_fails_without_signed_tx():
    adapter = NativeLiveExecutionAdapter(rpc_urls={"Base": "https://base-rpc.local"})
    tx = _tx_plan()
    receipt = _run(adapter.execute(tx))
    assert receipt.ok is False
    assert receipt.reason_codes == ["SIGNED_RAW_TX_MISSING"]


def test_native_live_execute_fails_when_tx_reverted():
    async def _request(_url: str, payload: dict, _timeout: float) -> dict:
        if payload["method"] == "eth_sendRawTransaction":
            return {"jsonrpc": "2.0", "id": 1, "result": "0xhash"}
        return {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"status": "0x0", "gasUsed": "0x7530", "blockNumber": "0x124"},
        }

    adapter = NativeLiveExecutionAdapter(
        rpc_urls={"Base": "https://base-rpc.local"},
        request_fn=_request,
    )
    tx = _tx_plan(signed_raw_tx="0xfeed")
    receipt = _run(adapter.execute(tx))
    assert receipt.ok is False
    assert receipt.reason_codes == ["TX_REVERTED"]


def test_native_live_execute_maps_rpc_error_reason():
    async def _request(_url: str, payload: dict, _timeout: float) -> dict:
        if payload["method"] == "eth_sendRawTransaction":
            return {
                "jsonrpc": "2.0",
                "id": 1,
                "error": {"code": -32000, "message": "nonce too low"},
            }
        return {"jsonrpc": "2.0", "id": 1, "result": None}

    adapter = NativeLiveExecutionAdapter(
        rpc_urls={"Base": "https://base-rpc.local"},
        request_fn=_request,
    )
    tx = _tx_plan(signed_raw_tx="0xfeed")
    receipt = _run(adapter.execute(tx))
    assert receipt.ok is False
    assert receipt.reason_codes == ["RPC_SEND_ERROR"]
    assert "nonce too low" in str(receipt.metadata.get("detail", ""))
