from __future__ import annotations

import time

from ..scout.config import ExecutionConfig
from .models import ActionIntent, ActionType, PositionState


class TriggerEngine:
    """Deterministic execution trigger classifier for a single position state."""

    def __init__(self, config: ExecutionConfig) -> None:
        self.config = config

    def evaluate_position(self, state: PositionState, now_ts: int | None = None) -> ActionIntent:
        now = int(now_ts if now_ts is not None else time.time())
        rebalance_reasons = self._rebalance_reasons(state)
        compound_due = state.unclaimed_fees_usd >= self.config.compound_min_fees_usd

        if self._is_cooldown_active(state, now):
            hold_reasons = ["COOLDOWN_ACTIVE"]
            if rebalance_reasons:
                hold_reasons.extend(rebalance_reasons)
            elif compound_due:
                hold_reasons.append("COMPOUND_DUE")
            return self._intent(
                state=state,
                action="SKIP",
                now_ts=now,
                reason_codes=hold_reasons,
                expected_net_usd=0.0,
            )

        if rebalance_reasons:
            expected_net = state.expected_rebalance_net_usd - state.estimated_rebalance_gas_usd
            return self._intent(
                state=state,
                action="REBALANCE",
                now_ts=now,
                reason_codes=rebalance_reasons,
                expected_net_usd=expected_net,
                metadata_extra={
                    "estimated_gas_usd": state.estimated_rebalance_gas_usd,
                    "slippage_bps": state.expected_slippage_bps,
                },
            )

        if compound_due:
            expected_net = state.unclaimed_fees_usd - state.estimated_compound_gas_usd
            return self._intent(
                state=state,
                action="COMPOUND",
                now_ts=now,
                reason_codes=["COMPOUND_DUE"],
                expected_net_usd=expected_net,
                metadata_extra={
                    "estimated_gas_usd": state.estimated_compound_gas_usd,
                    "slippage_bps": state.expected_slippage_bps,
                },
            )

        return self._intent(
            state=state,
            action="SKIP",
            now_ts=now,
            reason_codes=["HOLD"],
            expected_net_usd=0.0,
        )

    def _rebalance_reasons(self, state: PositionState) -> list[str]:
        reasons: list[str] = []
        if state.out_of_range:
            reasons.append("OUT_OF_RANGE")
        if state.range_utilization <= self.config.rebalance_min_range_utilization:
            reasons.append("LOW_RANGE_UTILIZATION")
        if state.edge_decay_bps >= self.config.rebalance_edge_decay_bps:
            reasons.append("EDGE_DECAY")
        return reasons

    def _is_cooldown_active(self, state: PositionState, now_ts: int) -> bool:
        if not state.last_rebalance_ts:
            return False
        elapsed = now_ts - int(state.last_rebalance_ts)
        return elapsed < self.config.per_position_cooldown_seconds

    @staticmethod
    def _intent(
        state: PositionState,
        action: ActionType,
        now_ts: int,
        reason_codes: list[str],
        expected_net_usd: float,
        metadata_extra: dict[str, object] | None = None,
    ) -> ActionIntent:
        metadata = {
            "current_tick": state.current_tick,
            "lower_tick": state.lower_tick,
            "upper_tick": state.upper_tick,
            "range_utilization": f"{state.range_utilization:.4f}",
            "edge_decay_bps": state.edge_decay_bps,
        }
        if state.position_manager:
            metadata["position_manager"] = state.position_manager
        if state.compound_data_hex:
            metadata["compound_data_hex"] = state.compound_data_hex
        if state.rebalance_data_hex:
            metadata["rebalance_data_hex"] = state.rebalance_data_hex
        if state.v3utils_compound_params:
            metadata["v3utils_compound_params"] = state.v3utils_compound_params
        if state.v3utils_rebalance_params:
            metadata["v3utils_rebalance_params"] = state.v3utils_rebalance_params
        if state.tx_value_wei:
            metadata["value_wei"] = state.tx_value_wei
        if metadata_extra:
            metadata.update(metadata_extra)
        return ActionIntent(
            intent_id=f"{state.chain}:{state.position_ref}:{action}:{now_ts}",
            action=action,
            chain=state.chain,
            position_ref=state.position_ref,
            reason_codes=reason_codes,
            expected_net_usd=expected_net_usd,
            metadata=metadata,
        )
