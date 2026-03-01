from __future__ import annotations

from typing import Any, Awaitable, Callable

import httpx

from ..models import ActionIntent, ExecutionReceipt, SimulationResult, TxPlan

RequestFn = Callable[[str, dict[str, Any], dict[str, str]], Awaitable[dict[str, Any]]]


class KrystalAdapterError(RuntimeError):
    pass


class KrystalExecutionAdapter:
    """Krystal Cloud adapter (feature-flagged, fail-safe friendly)."""
    # Krystal Cloud currently exposes pool/position data APIs; execution endpoints
    # are treated as experimental and not considered live-capable by default.
    supports_live_execution = False

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: float = 8.0,
        request_fn: RequestFn | None = None,
    ) -> None:
        key = (api_key or "").strip()
        if not key:
            raise ValueError("Krystal API key is required")
        self.base_url = base_url.rstrip("/")
        self.api_key = key
        self.timeout_seconds = float(timeout_seconds)
        self._request_fn = request_fn
        self._execution_api_available: bool | None = None

    async def build_compound_tx(self, intent: ActionIntent) -> TxPlan:
        payload = self._build_intent_payload(intent)
        response = await self._post_json("/v1/execution/compound/build", payload)
        tx = self._extract_tx(response)
        return self._to_tx_plan(intent, tx, tx_kind="compound")

    async def build_rebalance_tx(self, intent: ActionIntent) -> TxPlan:
        payload = self._build_intent_payload(intent)
        response = await self._post_json("/v1/execution/rebalance/build", payload)
        tx = self._extract_tx(response)
        return self._to_tx_plan(intent, tx, tx_kind="rebalance")

    async def simulate(self, tx: TxPlan) -> SimulationResult:
        payload = {"chain": tx.chain, "tx": self._tx_payload(tx)}
        response = await self._post_json("/v1/execution/simulate", payload)
        body = self._extract_data_obj(response)
        ok = bool(body.get("ok", body.get("success", False)))
        reason_codes = self._extract_reason_codes(body)
        return SimulationResult(
            ok=ok,
            reason_codes=reason_codes if not ok else [],
            estimated_gas_used=self._as_int(body.get("gasUsed"), self._as_int(body.get("gasEstimate"), None)),
            estimated_gas_usd=self._as_float(body.get("gasUsedUsd"), self._as_float(body.get("gasEstimateUsd"), None)),
            expected_net_usd=self._as_float(body.get("expectedNetUsd"), None),
            metadata={"adapter": "krystal"},
        )

    async def execute(self, tx: TxPlan) -> ExecutionReceipt:
        payload = {"chain": tx.chain, "tx": self._tx_payload(tx)}
        response = await self._post_json("/v1/execution/execute", payload)
        body = self._extract_data_obj(response)
        ok = bool(body.get("ok", body.get("success", False)))
        reason_codes = self._extract_reason_codes(body)
        return ExecutionReceipt(
            ok=ok,
            chain=tx.chain,
            tx_hash=self._as_str(body.get("txHash"), self._as_str(body.get("hash"), None)),
            block_number=self._as_int(body.get("blockNumber"), None),
            gas_used=self._as_int(body.get("gasUsed"), None),
            gas_used_usd=self._as_float(body.get("gasUsedUsd"), None),
            reason_codes=reason_codes if not ok else [],
            metadata={"adapter": "krystal"},
        )

    async def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if path.startswith("/v1/execution/") and self._execution_api_available is False:
            raise KrystalAdapterError("KRYSTAL_EXECUTION_API_UNAVAILABLE")

        headers = {
            "KC-APIKey": self.api_key,
            "Content-Type": "application/json",
        }
        if self._request_fn is not None:
            response = await self._request_fn(path, payload, headers)
            if not isinstance(response, dict):
                raise KrystalAdapterError("INVALID_RESPONSE_SHAPE")
            return response

        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            if not isinstance(data, dict):
                raise KrystalAdapterError("INVALID_RESPONSE_SHAPE")
            return data
        except httpx.TimeoutException as exc:
            raise KrystalAdapterError("KRYSTAL_TIMEOUT") from exc
        except httpx.HTTPStatusError as exc:
            status = getattr(exc.response, "status_code", "unknown")
            if path.startswith("/v1/execution/") and status == 404:
                self._execution_api_available = False
                raise KrystalAdapterError("KRYSTAL_EXECUTION_API_UNAVAILABLE") from exc
            raise KrystalAdapterError(f"KRYSTAL_HTTP_{status}") from exc
        except httpx.HTTPError as exc:
            raise KrystalAdapterError("KRYSTAL_HTTP_ERROR") from exc
        except ValueError as exc:
            raise KrystalAdapterError("KRYSTAL_INVALID_JSON") from exc

    @staticmethod
    def _build_intent_payload(intent: ActionIntent) -> dict[str, Any]:
        return {
            "intentId": intent.intent_id,
            "action": intent.action,
            "chain": intent.chain,
            "positionRef": intent.position_ref,
            "expectedNetUsd": intent.expected_net_usd,
            "metadata": dict(intent.metadata),
        }

    @staticmethod
    def _extract_data_obj(response: dict[str, Any]) -> dict[str, Any]:
        data = response.get("data")
        if isinstance(data, dict):
            return data
        return response

    @classmethod
    def _extract_tx(cls, response: dict[str, Any]) -> dict[str, Any]:
        data_obj = cls._extract_data_obj(response)
        for key in ("tx", "transaction"):
            candidate = data_obj.get(key)
            if isinstance(candidate, dict):
                return candidate
        if cls._looks_like_tx(data_obj):
            return data_obj
        raise KrystalAdapterError("KRYSTAL_TX_PAYLOAD_MISSING")

    @classmethod
    def _to_tx_plan(cls, intent: ActionIntent, tx: dict[str, Any], *, tx_kind: str) -> TxPlan:
        return TxPlan(
            plan_id=f"krystal-{tx_kind}:{intent.intent_id}",
            intent_id=intent.intent_id,
            chain=intent.chain,
            to_address=cls._as_str(tx.get("to"), cls._as_str(tx.get("toAddress"), "")) or "",
            data_hex=cls._as_str(tx.get("data"), "") or "",
            value_wei=cls._as_int(tx.get("value"), 0) or 0,
            gas_estimate=cls._as_int(tx.get("gasEstimate"), None),
            gas_estimate_usd=cls._as_float(tx.get("gasEstimateUsd"), None),
            slippage_bps=cls._as_int(tx.get("slippageBps"), None),
            metadata={
                "adapter": "krystal",
                "tx_kind": tx_kind,
                "position_ref": intent.position_ref,
            },
        )

    @staticmethod
    def _tx_payload(tx: TxPlan) -> dict[str, Any]:
        return {
            "to": tx.to_address,
            "data": tx.data_hex,
            "value": str(tx.value_wei),
            "gasEstimate": tx.gas_estimate,
            "gasEstimateUsd": tx.gas_estimate_usd,
            "slippageBps": tx.slippage_bps,
        }

    @staticmethod
    def _extract_reason_codes(body: dict[str, Any]) -> list[str]:
        explicit = body.get("reason_codes")
        if isinstance(explicit, list):
            return [str(x) for x in explicit if str(x)]
        error_code = body.get("errorCode")
        error_text = body.get("error")
        reasons: list[str] = []
        if error_code:
            reasons.append(str(error_code))
        if error_text:
            reasons.append(str(error_text))
        return reasons

    @staticmethod
    def _looks_like_tx(value: Any) -> bool:
        if not isinstance(value, dict):
            return False
        return any(key in value for key in ("to", "toAddress", "data", "value"))

    @staticmethod
    def _as_int(value: Any, default: int | None) -> int | None:
        if value is None:
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _as_float(value: Any, default: float | None) -> float | None:
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _as_str(value: Any, default: str | None) -> str | None:
        if value is None:
            return default
        text = str(value)
        return text if text else default
