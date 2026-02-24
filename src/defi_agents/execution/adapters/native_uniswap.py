from __future__ import annotations

from typing import Any

from ..models import ActionIntent, ExecutionReceipt, SimulationResult, TxPlan


def _as_float(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int | None = None) -> int | None:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class NativeUniswapV3Adapter:
    """Baseline execution adapter for Uniswap V3 style actions.

    This adapter is intentionally fail-safe in v1 foundation:
    - tx plans are deterministic and metadata-driven;
    - `simulate()` performs structural checks only;
    - `execute()` never sends on-chain tx and returns explicit unsupported receipt.
    """
    supports_live_execution = False

    async def build_compound_tx(self, intent: ActionIntent) -> TxPlan:
        return self._build_tx(intent, tx_kind="compound")

    async def build_rebalance_tx(self, intent: ActionIntent) -> TxPlan:
        return self._build_tx(intent, tx_kind="rebalance")

    async def simulate(self, tx: TxPlan) -> SimulationResult:
        if not tx.to_address or not tx.data_hex:
            return SimulationResult(
                ok=False,
                reason_codes=["TX_PLAN_INVALID"],
                estimated_gas_usd=tx.gas_estimate_usd,
            )
        return SimulationResult(
            ok=True,
            reason_codes=[],
            estimated_gas_used=tx.gas_estimate,
            estimated_gas_usd=tx.gas_estimate_usd,
            metadata={"adapter": "native_uniswap_v3"},
        )

    async def execute(self, tx: TxPlan) -> ExecutionReceipt:
        return ExecutionReceipt(
            ok=False,
            chain=tx.chain,
            reason_codes=["LIVE_EXECUTION_NOT_IMPLEMENTED"],
            metadata={"adapter": "native_uniswap_v3"},
        )

    def _build_tx(self, intent: ActionIntent, *, tx_kind: str) -> TxPlan:
        to_address = str(intent.metadata.get("position_manager") or intent.metadata.get("to_address") or "")
        default_data = "0xcompound" if tx_kind == "compound" else "0xrebalance"
        data_hex = str(intent.metadata.get("data_hex") or intent.metadata.get(f"{tx_kind}_data_hex") or default_data)
        gas_estimate = _as_int(intent.metadata.get("gas_estimate"), None)
        gas_estimate_usd = _as_float(
            intent.metadata.get("estimated_gas_usd"),
            _as_float(intent.metadata.get(f"estimated_{tx_kind}_gas_usd"), None),
        )
        slippage_bps = _as_int(intent.metadata.get("slippage_bps"), None)
        value_wei = _as_int(intent.metadata.get("value_wei"), 0) or 0
        plan_id = f"native-{tx_kind}:{intent.intent_id}"

        return TxPlan(
            plan_id=plan_id,
            intent_id=intent.intent_id,
            chain=intent.chain,
            to_address=to_address,
            data_hex=data_hex,
            value_wei=max(0, value_wei),
            gas_estimate=gas_estimate,
            gas_estimate_usd=gas_estimate_usd,
            slippage_bps=slippage_bps,
            metadata={
                "adapter": "native_uniswap_v3",
                "tx_kind": tx_kind,
                "position_ref": intent.position_ref,
            },
        )
