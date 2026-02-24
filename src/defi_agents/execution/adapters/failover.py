from __future__ import annotations

import logging

from ..models import ActionIntent, ExecutionAdapter, ExecutionReceipt, SimulationResult, TxPlan


class FailoverExecutionAdapter:
    """Wrapper that falls back to secondary adapter on primary failures."""

    def __init__(
        self,
        primary: ExecutionAdapter,
        fallback: ExecutionAdapter,
        *,
        logger_name: str = "Execution",
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.logger = logging.getLogger(logger_name)

    async def build_compound_tx(self, intent: ActionIntent) -> TxPlan:
        return await self._with_failover("build_compound_tx", intent)

    async def build_rebalance_tx(self, intent: ActionIntent) -> TxPlan:
        return await self._with_failover("build_rebalance_tx", intent)

    async def simulate(self, tx: TxPlan) -> SimulationResult:
        return await self._with_failover("simulate", tx)

    async def execute(self, tx: TxPlan) -> ExecutionReceipt:
        return await self._with_failover("execute", tx)

    async def _with_failover(self, method_name: str, *args):
        primary_method = getattr(self.primary, method_name)
        fallback_method = getattr(self.fallback, method_name)
        try:
            return await primary_method(*args)
        except Exception as exc:  # noqa: BLE001
            self.logger.warning(
                "Execution adapter failover: primary=%s method=%s err=%s detail=%s",
                self.primary.__class__.__name__,
                method_name,
                exc.__class__.__name__,
                str(exc) or "n/a",
            )
            return await fallback_method(*args)
