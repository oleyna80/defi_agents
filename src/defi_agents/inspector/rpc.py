from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import httpx

EIP1967_IMPLEMENTATION_SLOT = (
    "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
)
EIP1967_ADMIN_SLOT = (
    "0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103"
)


def _normalize_hex(value: str) -> str:
    if not value:
        return "0x"
    return value if value.startswith("0x") else f"0x{value}"


def _decode_address_from_slot(slot_value: str) -> str | None:
    raw = slot_value.lower().replace("0x", "")
    if len(raw) < 40:
        return None
    address = raw[-40:]
    if set(address) == {"0"}:
        return None
    return f"0x{address}"


def _decode_address_from_call(call_result: str) -> str | None:
    if not isinstance(call_result, str):
        return None
    raw = call_result.lower().replace("0x", "")
    if len(raw) < 40:
        return None
    address = raw[-40:]
    if set(address) == {"0"}:
        return None
    return f"0x{address}"


def _decode_bool_from_call(call_result: str) -> bool | None:
    if not isinstance(call_result, str):
        return None
    raw = call_result.lower().replace("0x", "")
    if not raw:
        return None
    try:
        return bool(int(raw, 16))
    except ValueError:
        return None


def code_hash(code_hex: str) -> str:
    if not code_hex or code_hex in {"0x", "0X"}:
        return ""
    payload = code_hex[2:] if code_hex.startswith("0x") else code_hex
    return hashlib.sha256(bytes.fromhex(payload)).hexdigest()


@dataclass
class EvmRpcClient:
    rpc_url: str
    timeout_seconds: int = 10

    async def _rpc(self, method: str, params: list[Any]) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        }
        async with httpx.AsyncClient(timeout=float(self.timeout_seconds)) as client:
            response = await client.post(self.rpc_url, json=payload)
            response.raise_for_status()
            body = response.json()
            if "error" in body:
                raise RuntimeError(f"RPC error in {method}")
            return body.get("result")

    async def chain_id(self) -> int:
        value = await self._rpc("eth_chainId", [])
        return int(_normalize_hex(value), 16)

    async def block_number(self) -> int:
        value = await self._rpc("eth_blockNumber", [])
        return int(_normalize_hex(value), 16)

    async def get_code(self, address: str) -> str:
        return await self._rpc("eth_getCode", [address, "latest"])

    async def get_storage_at(self, address: str, slot: str) -> str:
        return await self._rpc("eth_getStorageAt", [address, slot, "latest"])

    async def eth_call(self, address: str, data: str) -> str:
        return await self._rpc("eth_call", [{"to": address, "data": data}, "latest"])

    async def detect_proxy(self, address: str) -> tuple[bool, str | None, str | None]:
        impl_slot = await self.get_storage_at(address, EIP1967_IMPLEMENTATION_SLOT)
        admin_slot = await self.get_storage_at(address, EIP1967_ADMIN_SLOT)
        implementation = _decode_address_from_slot(impl_slot)
        admin = _decode_address_from_slot(admin_slot)
        return bool(implementation), implementation, admin

    async def read_owner(self, address: str) -> str | None:
        # owner()
        result = await self.eth_call(address, "0x8da5cb5b")
        return _decode_address_from_call(result)

    async def read_paused(self, address: str) -> bool | None:
        # paused()
        result = await self.eth_call(address, "0x5c975abb")
        return _decode_bool_from_call(result)

