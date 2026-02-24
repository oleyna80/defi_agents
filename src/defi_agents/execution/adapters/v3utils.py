from __future__ import annotations

from time import time
from typing import Any

from ..models import ActionIntent, SimulationResult, TxPlan
from .native_live import NativeLiveExecutionAdapter

V3UTILS_UPSTREAM_REPO = "https://github.com/KrystalDeFi/v3utils"
V3UTILS_UPSTREAM_COMMIT = "33f487253051c3d6f439dc911b0e415b28b4cc9c"
V3UTILS_EXECUTE_ABI_FILE = "v3utils_execute.abi.json"
V3AUTOMATION_EXECUTE_ABI_FILE = "v3automation_execute.abi.json"
V3UTILS_EXECUTE_SELECTOR = "0xfd2d17d1"


class V3UtilsAdapterError(RuntimeError):
    pass


class V3UtilsExecutionAdapter(NativeLiveExecutionAdapter):
    """Execution adapter scaffold for Krystal/Revert v3utils-style calls.

    v1 behavior:
    - supports structured params for compound/rebalance calldata encoding;
    - keeps pre-encoded calldata fallback for backward compatibility;
    - execute path uses inherited raw-tx transport from NativeLiveExecutionAdapter.
    """

    supports_live_execution = True

    def __init__(
        self,
        *,
        rpc_urls: dict[str, str],
        contracts_by_chain: dict[str, str],
        routers_by_chain: dict[str, str] | None = None,
        default_slippage_bps: int = 50,
        timeout_seconds: float = 12.0,
        receipt_timeout_seconds: float = 45.0,
        receipt_poll_seconds: float = 1.5,
        request_fn=None,
        sleep_fn=None,
    ) -> None:
        super().__init__(
            rpc_urls=rpc_urls,
            timeout_seconds=timeout_seconds,
            receipt_timeout_seconds=receipt_timeout_seconds,
            receipt_poll_seconds=receipt_poll_seconds,
            request_fn=request_fn,
            sleep_fn=sleep_fn,
        )
        normalized_contracts = self._normalize_chain_map(contracts_by_chain)
        if not normalized_contracts:
            raise ValueError("V3UTILS_CONTRACTS_MISSING")
        self.contracts_by_chain = normalized_contracts
        self.routers_by_chain = self._normalize_chain_map(routers_by_chain or {})
        self.default_slippage_bps = int(max(0, min(10_000, int(default_slippage_bps))))

    async def build_compound_tx(self, intent: ActionIntent) -> TxPlan:
        return self._build_tx(intent, tx_kind="compound")

    async def build_rebalance_tx(self, intent: ActionIntent) -> TxPlan:
        return self._build_tx(intent, tx_kind="rebalance")

    async def simulate(self, tx: TxPlan) -> SimulationResult:
        base = await super().simulate(tx)
        if not base.ok:
            return base

        metadata = dict(tx.metadata or {})
        payload_mode = str(metadata.get("v3utils_payload_mode") or "raw_hex")
        expected_selector = str(metadata.get("v3utils_expected_selector") or V3UTILS_EXECUTE_SELECTOR)

        if payload_mode.startswith("structured_"):
            if not str(tx.data_hex or "").startswith(expected_selector):
                return SimulationResult(
                    ok=False,
                    reason_codes=["V3UTILS_SELECTOR_MISMATCH"],
                    estimated_gas_used=tx.gas_estimate,
                    estimated_gas_usd=tx.gas_estimate_usd,
                    metadata={"adapter": "v3utils", "payload_mode": payload_mode},
                )
            declared_contract = str(metadata.get("v3utils_contract") or "").lower()
            if declared_contract and str(tx.to_address or "").lower() != declared_contract:
                return SimulationResult(
                    ok=False,
                    reason_codes=["V3UTILS_CONTRACT_MISMATCH"],
                    estimated_gas_used=tx.gas_estimate,
                    estimated_gas_usd=tx.gas_estimate_usd,
                    metadata={"adapter": "v3utils", "payload_mode": payload_mode},
                )

        return SimulationResult(
            ok=True,
            reason_codes=[],
            estimated_gas_used=base.estimated_gas_used,
            estimated_gas_usd=base.estimated_gas_usd,
            expected_net_usd=base.expected_net_usd,
            metadata={
                "adapter": "v3utils",
                "payload_mode": payload_mode,
                "selector": expected_selector,
            },
        )

    def _build_tx(self, intent: ActionIntent, *, tx_kind: str) -> TxPlan:
        to_address = self._resolve_contract_address(intent.chain, intent.metadata)
        data_hex = self._resolve_data_hex(intent.metadata, tx_kind=tx_kind)
        structured_mode = self._detect_payload_mode(intent.metadata, tx_kind=tx_kind)
        gas_estimate = self._as_int(intent.metadata.get("gas_estimate"), None)
        gas_estimate_usd = self._as_float(
            intent.metadata.get("estimated_gas_usd"),
            self._as_float(intent.metadata.get(f"estimated_{tx_kind}_gas_usd"), None),
        )
        value_wei = self._as_int(intent.metadata.get("value_wei"), 0) or 0
        slippage_bps = self._as_int(intent.metadata.get("slippage_bps"), self.default_slippage_bps)
        router = self._resolve_router_address(intent.chain)
        metadata: dict[str, Any] = {
            "adapter": "v3utils",
            "tx_kind": tx_kind,
            "position_ref": intent.position_ref,
            "position_manager": intent.metadata.get("position_manager"),
            "v3utils_contract": to_address,
            "v3utils_upstream_repo": V3UTILS_UPSTREAM_REPO,
            "v3utils_upstream_commit": V3UTILS_UPSTREAM_COMMIT,
            "v3utils_abi_file": V3UTILS_EXECUTE_ABI_FILE,
            "v3automation_abi_file": V3AUTOMATION_EXECUTE_ABI_FILE,
            "v3utils_payload_mode": structured_mode,
            "v3utils_expected_selector": V3UTILS_EXECUTE_SELECTOR if structured_mode.startswith("structured_") else "",
        }
        for key in ("signed_raw_tx", "raw_tx_hex", "signed_tx", "native_token_price_usd"):
            if key in intent.metadata:
                metadata[key] = intent.metadata.get(key)
        if router:
            metadata["v3utils_router"] = router
        return TxPlan(
            plan_id=f"v3utils-{tx_kind}:{intent.intent_id}",
            intent_id=intent.intent_id,
            chain=intent.chain,
            to_address=to_address,
            data_hex=data_hex,
            value_wei=max(0, value_wei),
            gas_estimate=gas_estimate,
            gas_estimate_usd=gas_estimate_usd,
            slippage_bps=slippage_bps,
            metadata=metadata,
        )

    def _resolve_contract_address(self, chain: str, metadata: dict[str, Any]) -> str:
        override = str(metadata.get("v3utils_contract") or "").strip()
        if override:
            return override
        key = str(chain or "").strip().lower()
        contract = self.contracts_by_chain.get(key, "")
        if contract:
            return contract
        raise V3UtilsAdapterError("V3UTILS_CONTRACT_MISSING")

    def _resolve_router_address(self, chain: str) -> str:
        key = str(chain or "").strip().lower()
        return self.routers_by_chain.get(key, "")

    @staticmethod
    def _resolve_data_hex(metadata: dict[str, Any], *, tx_kind: str) -> str:
        if tx_kind == "compound":
            structured = metadata.get("v3utils_compound_params")
            if isinstance(structured, dict):
                return V3UtilsExecutionAdapter._encode_v3utils_compound_execute(structured)
        if tx_kind == "rebalance":
            structured = metadata.get("v3utils_rebalance_params")
            if isinstance(structured, dict):
                return V3UtilsExecutionAdapter._encode_v3utils_rebalance_execute(structured)

        keys = (
            "v3utils_compound_data_hex",
            "compound_data_hex",
            "v3utils_data_hex",
            "data_hex",
        ) if tx_kind == "compound" else (
            "v3utils_rebalance_data_hex",
            "rebalance_data_hex",
            "v3utils_data_hex",
            "data_hex",
        )
        for key in keys:
            candidate = str(metadata.get(key) or "").strip()
            if candidate:
                return candidate
        raise V3UtilsAdapterError("V3UTILS_DATA_HEX_MISSING")

    @classmethod
    def _encode_v3utils_compound_execute(cls, payload: dict[str, Any]) -> str:
        return cls._encode_v3utils_execute(payload, default_what_to_do=2)

    @classmethod
    def _encode_v3utils_rebalance_execute(cls, payload: dict[str, Any]) -> str:
        instructions_raw = payload.get("instructions")
        if not isinstance(instructions_raw, dict):
            raise V3UtilsAdapterError("V3UTILS_INSTRUCTIONS_MISSING")
        cls._validate_rebalance_instructions(instructions_raw)
        return cls._encode_v3utils_execute(payload, default_what_to_do=0)

    @classmethod
    def _encode_v3utils_execute(cls, payload: dict[str, Any], *, default_what_to_do: int) -> str:
        nfpm = cls._normalize_address(payload.get("nfpm"))
        token_id = cls._as_int(payload.get("token_id"), None)
        if token_id is None or token_id < 0:
            raise V3UtilsAdapterError("V3UTILS_TOKEN_ID_MISSING")

        instructions_raw = payload.get("instructions")
        if not isinstance(instructions_raw, dict):
            raise V3UtilsAdapterError("V3UTILS_INSTRUCTIONS_MISSING")
        instructions = dict(instructions_raw)
        encoded_tuple = cls._encode_instructions_tuple(instructions, default_what_to_do=default_what_to_do)
        args_head = b"".join(
            (
                cls._encode_address_word(nfpm),
                cls._encode_uint_word(token_id, bits=256),
                cls._encode_uint_word(96, bits=256),  # offset to tuple payload
            )
        )
        selector = bytes.fromhex(V3UTILS_EXECUTE_SELECTOR[2:])
        calldata = selector + args_head + encoded_tuple
        return "0x" + calldata.hex()

    @classmethod
    def _encode_instructions_tuple(cls, value: dict[str, Any], *, default_what_to_do: int) -> bytes:
        # Matches v3utils `Instructions` struct field order.
        fields: list[tuple[str, Any]] = [
            ("uint8", cls._as_int(value.get("what_to_do"), default_what_to_do)),
            ("uint8", cls._as_int(value.get("protocol"), 0)),
            ("address", cls._normalize_address(value.get("target_token"), allow_zero=True)),
            ("uint256", cls._as_int(value.get("amount_remove_min_0"), 0)),
            ("uint256", cls._as_int(value.get("amount_remove_min_1"), 0)),
            ("uint256", cls._as_int(value.get("amount_in_0"), 0)),
            ("uint256", cls._as_int(value.get("amount_out_0_min"), 0)),
            ("bytes", cls._coerce_bytes(value.get("swap_data_0"), default=b"")),
            ("uint256", cls._as_int(value.get("amount_in_1"), 0)),
            ("uint256", cls._as_int(value.get("amount_out_1_min"), 0)),
            ("bytes", cls._coerce_bytes(value.get("swap_data_1"), default=b"")),
            ("int24", cls._as_int(value.get("tick_lower"), 0)),
            ("int24", cls._as_int(value.get("tick_upper"), 0)),
            ("bool", bool(value.get("compound_fees", True))),
            ("uint128", cls._as_int(value.get("liquidity"), 0)),
            ("uint256", cls._as_int(value.get("amount_add_min_0"), 0)),
            ("uint256", cls._as_int(value.get("amount_add_min_1"), 0)),
            ("uint256", cls._as_int(value.get("deadline"), int(time()) + 600)),
            ("address", cls._normalize_address(value.get("recipient"), allow_zero=False)),
            ("bool", bool(value.get("unwrap", False))),
            ("uint64", cls._as_int(value.get("liquidity_fee_x64"), 0)),
            ("uint64", cls._as_int(value.get("performance_fee_x64"), 0)),
            ("uint64", cls._as_int(value.get("gas_fee_x64"), 0)),
        ]

        head_size = 32 * len(fields)
        head_chunks: list[bytes] = []
        tail_chunks: list[bytes] = []
        current_offset = head_size

        for ftype, fvalue in fields:
            if ftype == "bytes":
                encoded = cls._encode_bytes_blob(fvalue)
                head_chunks.append(cls._encode_uint_word(current_offset, bits=256))
                tail_chunks.append(encoded)
                current_offset += len(encoded)
                continue
            head_chunks.append(cls._encode_primitive_word(ftype, fvalue))

        return b"".join(head_chunks + tail_chunks)

    @staticmethod
    def _detect_payload_mode(metadata: dict[str, Any], *, tx_kind: str) -> str:
        if tx_kind == "compound" and isinstance(metadata.get("v3utils_compound_params"), dict):
            return "structured_compound"
        if tx_kind == "rebalance" and isinstance(metadata.get("v3utils_rebalance_params"), dict):
            return "structured_rebalance"
        return "raw_hex"

    @classmethod
    def _validate_rebalance_instructions(cls, instructions: dict[str, Any]) -> None:
        lower = cls._as_int(instructions.get("tick_lower"), None)
        upper = cls._as_int(instructions.get("tick_upper"), None)
        if lower is None or upper is None:
            raise V3UtilsAdapterError("V3UTILS_REBALANCE_TICKS_MISSING")
        if int(lower) >= int(upper):
            raise V3UtilsAdapterError("V3UTILS_REBALANCE_TICKS_INVALID")

    @classmethod
    def _encode_primitive_word(cls, ftype: str, value: Any) -> bytes:
        if ftype == "bool":
            return cls._encode_uint_word(1 if value else 0, bits=8)
        if ftype == "address":
            return cls._encode_address_word(str(value))
        if ftype.startswith("uint"):
            bits = int(ftype[4:])
            return cls._encode_uint_word(int(value), bits=bits)
        if ftype.startswith("int"):
            bits = int(ftype[3:])
            return cls._encode_int_word(int(value), bits=bits)
        raise V3UtilsAdapterError("V3UTILS_ABI_TYPE_UNSUPPORTED")

    @staticmethod
    def _encode_bytes_blob(value: bytes) -> bytes:
        size = len(value)
        pad = (32 - (size % 32)) % 32
        return size.to_bytes(32, byteorder="big") + value + (b"\x00" * pad)

    @staticmethod
    def _encode_uint_word(value: int, *, bits: int) -> bytes:
        if value is None:
            raise V3UtilsAdapterError("V3UTILS_ABI_VALUE_MISSING")
        intval = int(value)
        if intval < 0:
            raise V3UtilsAdapterError("V3UTILS_ABI_UINT_NEGATIVE")
        max_value = (1 << bits) - 1
        if intval > max_value:
            raise V3UtilsAdapterError("V3UTILS_ABI_UINT_OVERFLOW")
        return intval.to_bytes(32, byteorder="big", signed=False)

    @staticmethod
    def _encode_int_word(value: int, *, bits: int) -> bytes:
        if value is None:
            raise V3UtilsAdapterError("V3UTILS_ABI_VALUE_MISSING")
        intval = int(value)
        min_value = -(1 << (bits - 1))
        max_value = (1 << (bits - 1)) - 1
        if intval < min_value or intval > max_value:
            raise V3UtilsAdapterError("V3UTILS_ABI_INT_OVERFLOW")
        return intval.to_bytes(32, byteorder="big", signed=True)

    @staticmethod
    def _encode_address_word(value: str) -> bytes:
        text = str(value or "").strip()
        if not text.startswith("0x") or len(text) != 42:
            raise V3UtilsAdapterError("V3UTILS_ADDRESS_INVALID")
        try:
            raw = bytes.fromhex(text[2:])
        except ValueError as exc:
            raise V3UtilsAdapterError("V3UTILS_ADDRESS_INVALID") from exc
        return (b"\x00" * 12) + raw

    @staticmethod
    def _normalize_address(value: Any, *, allow_zero: bool = True) -> str:
        text = str(value or "").strip()
        if not text:
            if allow_zero:
                return "0x0000000000000000000000000000000000000000"
            raise V3UtilsAdapterError("V3UTILS_ADDRESS_MISSING")
        if not text.startswith("0x"):
            text = "0x" + text
        if len(text) != 42:
            raise V3UtilsAdapterError("V3UTILS_ADDRESS_INVALID")
        try:
            int(text[2:], 16)
        except ValueError as exc:
            raise V3UtilsAdapterError("V3UTILS_ADDRESS_INVALID") from exc
        if not allow_zero and text.lower() == "0x0000000000000000000000000000000000000000":
            raise V3UtilsAdapterError("V3UTILS_ADDRESS_MISSING")
        return text

    @staticmethod
    def _coerce_bytes(value: Any, *, default: bytes) -> bytes:
        if value is None:
            return default
        if isinstance(value, bytes):
            return value
        if isinstance(value, bytearray):
            return bytes(value)
        text = str(value).strip()
        if not text:
            return default
        if text.startswith("0x"):
            try:
                return bytes.fromhex(text[2:])
            except ValueError as exc:
                raise V3UtilsAdapterError("V3UTILS_BYTES_INVALID_HEX") from exc
        return text.encode("utf-8")

    @staticmethod
    def _normalize_chain_map(raw: dict[str, str]) -> dict[str, str]:
        output: dict[str, str] = {}
        for chain, value in dict(raw or {}).items():
            chain_key = str(chain).strip().lower()
            val = str(value).strip()
            if chain_key and val:
                output[chain_key] = val
        return output

    @staticmethod
    def _as_int(value: Any, default: int | None = None) -> int | None:
        if value is None:
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _as_float(value: Any, default: float | None = None) -> float | None:
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
