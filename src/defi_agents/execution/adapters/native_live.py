from __future__ import annotations

import asyncio
from time import monotonic
from typing import Any, Awaitable, Callable

import httpx

from ..models import ExecutionReceipt, TxPlan
from .native_uniswap import NativeUniswapV3Adapter

RpcRequestFn = Callable[[str, dict[str, Any], float], Awaitable[dict[str, Any]]]
SleepFn = Callable[[float], Awaitable[None]]


class NativeLiveAdapterError(RuntimeError):
    def __init__(self, reason_code: str, detail: str | None = None) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.detail = detail


class NativeLiveExecutionAdapter(NativeUniswapV3Adapter):
    """On-chain sender for pre-signed EVM transactions.

    Assumptions:
    - tx signing is external (HSM/wallet service/manual signer).
    - `TxPlan.metadata` includes `signed_raw_tx` (or alias keys).
    """

    supports_live_execution = True

    def __init__(
        self,
        *,
        rpc_urls: dict[str, str],
        timeout_seconds: float = 12.0,
        receipt_timeout_seconds: float = 45.0,
        receipt_poll_seconds: float = 1.5,
        request_fn: RpcRequestFn | None = None,
        sleep_fn: SleepFn | None = None,
    ) -> None:
        normalized = {
            str(chain).strip().lower(): str(url).strip()
            for chain, url in dict(rpc_urls).items()
            if str(chain).strip() and str(url).strip()
        }
        if not normalized:
            raise ValueError("NATIVE_LIVE_RPC_URLS_MISSING")
        self.rpc_urls = normalized
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.receipt_timeout_seconds = max(0.0, float(receipt_timeout_seconds))
        self.receipt_poll_seconds = max(0.1, float(receipt_poll_seconds))
        self._request_fn = request_fn
        self._sleep_fn = sleep_fn or asyncio.sleep

    async def execute(self, tx: TxPlan) -> ExecutionReceipt:
        try:
            rpc_url = self._resolve_rpc_url(tx.chain)
            raw_tx = self._extract_signed_raw_tx(tx)
            tx_hash_any = await self._rpc_call(rpc_url, "eth_sendRawTransaction", [raw_tx], stage="send")
            tx_hash = self._as_hex_str(tx_hash_any)
            if tx_hash is None:
                raise NativeLiveAdapterError("RPC_INVALID_TX_HASH")

            receipt = await self._wait_for_receipt(rpc_url, tx_hash)
            if receipt is None:
                return self._fail_receipt(
                    tx,
                    "TX_RECEIPT_TIMEOUT",
                    tx_hash=tx_hash,
                )

            status = self._to_int(receipt.get("status"), default=0)
            gas_used = self._to_int(receipt.get("gasUsed"), default=None)
            block_number = self._to_int(receipt.get("blockNumber"), default=None)
            gas_used_usd = self._compute_gas_used_usd(tx, receipt)
            ok = status == 1

            return ExecutionReceipt(
                ok=ok,
                chain=tx.chain,
                tx_hash=tx_hash,
                block_number=block_number,
                gas_used=gas_used,
                gas_used_usd=gas_used_usd,
                reason_codes=[] if ok else ["TX_REVERTED"],
                metadata={
                    "adapter": "native_uniswap_v3_live",
                    "rpc_chain": tx.chain,
                    "tx_kind": str(tx.metadata.get("tx_kind") or ""),
                },
            )
        except NativeLiveAdapterError as exc:
            return self._fail_receipt(tx, exc.reason_code, detail=exc.detail)
        except Exception as exc:  # noqa: BLE001
            return self._fail_receipt(tx, "NATIVE_LIVE_EXECUTE_ERROR", detail=exc.__class__.__name__)

    async def _wait_for_receipt(self, rpc_url: str, tx_hash: str) -> dict[str, Any] | None:
        deadline = monotonic() + self.receipt_timeout_seconds
        while True:
            result = await self._rpc_call(rpc_url, "eth_getTransactionReceipt", [tx_hash], stage="receipt")
            if isinstance(result, dict):
                return result
            if monotonic() >= deadline:
                return None
            await self._sleep_fn(self.receipt_poll_seconds)

    async def _rpc_call(self, rpc_url: str, method: str, params: list[Any], *, stage: str) -> Any:
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        response = await self._post_json(rpc_url, payload)
        if not isinstance(response, dict):
            raise NativeLiveAdapterError(f"RPC_{stage.upper()}_INVALID_RESPONSE")

        error_obj = response.get("error")
        if isinstance(error_obj, dict):
            code = error_obj.get("code")
            message = error_obj.get("message")
            detail = f"{code}:{message}" if (code is not None or message) else None
            raise NativeLiveAdapterError(f"RPC_{stage.upper()}_ERROR", detail=detail)

        return response.get("result")

    async def _post_json(self, rpc_url: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self._request_fn is not None:
            response = await self._request_fn(rpc_url, payload, self.timeout_seconds)
            if not isinstance(response, dict):
                raise NativeLiveAdapterError("RPC_HTTP_INVALID_RESPONSE")
            return response

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.post(rpc_url, json=payload)
                resp.raise_for_status()
                data = resp.json()
            if not isinstance(data, dict):
                raise NativeLiveAdapterError("RPC_HTTP_INVALID_RESPONSE")
            return data
        except httpx.TimeoutException as exc:
            raise NativeLiveAdapterError("RPC_HTTP_TIMEOUT") from exc
        except httpx.HTTPStatusError as exc:
            code = getattr(exc.response, "status_code", "unknown")
            raise NativeLiveAdapterError("RPC_HTTP_STATUS_ERROR", detail=str(code)) from exc
        except httpx.HTTPError as exc:
            raise NativeLiveAdapterError("RPC_HTTP_ERROR") from exc
        except ValueError as exc:
            raise NativeLiveAdapterError("RPC_HTTP_INVALID_JSON") from exc

    def _resolve_rpc_url(self, chain: str) -> str:
        key = str(chain or "").strip().lower()
        rpc = self.rpc_urls.get(key)
        if not rpc:
            raise NativeLiveAdapterError("NATIVE_LIVE_RPC_URL_MISSING", detail=str(chain))
        return rpc

    @staticmethod
    def _extract_signed_raw_tx(tx: TxPlan) -> str:
        metadata = dict(tx.metadata or {})
        for field in ("signed_raw_tx", "raw_tx_hex", "signed_tx"):
            candidate = metadata.get(field)
            hex_value = NativeLiveExecutionAdapter._as_hex_str(candidate)
            if hex_value:
                return hex_value
        raise NativeLiveAdapterError("SIGNED_RAW_TX_MISSING")

    @staticmethod
    def _as_hex_str(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        if not text.startswith("0x"):
            text = f"0x{text}"
        return text

    @staticmethod
    def _to_int(value: Any, default: int | None) -> int | None:
        if value is None:
            return default
        try:
            text = str(value)
            base = 16 if text.startswith("0x") else 10
            return int(text, base=base)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _compute_gas_used_usd(cls, tx: TxPlan, receipt: dict[str, Any]) -> float | None:
        gas_used = cls._to_int(receipt.get("gasUsed"), default=None)
        effective_gas_price = cls._to_int(receipt.get("effectiveGasPrice"), default=None)
        native_price = tx.metadata.get("native_token_price_usd")
        if gas_used is not None and effective_gas_price is not None and native_price is not None:
            try:
                return float(gas_used) * float(effective_gas_price) * float(native_price) / 1e18
            except (TypeError, ValueError):
                pass
        return tx.gas_estimate_usd

    @staticmethod
    def _fail_receipt(
        tx: TxPlan,
        reason_code: str,
        *,
        detail: str | None = None,
        tx_hash: str | None = None,
    ) -> ExecutionReceipt:
        metadata: dict[str, Any] = {"adapter": "native_uniswap_v3_live"}
        if detail:
            metadata["detail"] = detail
        if tx_hash:
            metadata["tx_hash"] = tx_hash
        return ExecutionReceipt(
            ok=False,
            chain=tx.chain,
            tx_hash=tx_hash,
            reason_codes=[reason_code],
            metadata=metadata,
        )
