import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.execution.adapters import FailoverExecutionAdapter
from defi_agents.execution.models import ActionIntent, ExecutionReceipt, SimulationResult, TxPlan


def _run(coro):
    return asyncio.run(coro)


class _PrimaryBrokenAdapter:
    async def build_compound_tx(self, intent: ActionIntent) -> TxPlan:
        raise RuntimeError("primary down")

    async def build_rebalance_tx(self, intent: ActionIntent) -> TxPlan:
        raise RuntimeError("primary down")

    async def simulate(self, tx: TxPlan) -> SimulationResult:
        raise RuntimeError("primary down")

    async def execute(self, tx: TxPlan) -> ExecutionReceipt:
        raise RuntimeError("primary down")


class _FallbackAdapter:
    async def build_compound_tx(self, intent: ActionIntent) -> TxPlan:
        return TxPlan(plan_id="fb-c", intent_id=intent.intent_id, chain=intent.chain, to_address="0x1", data_hex="0x1")

    async def build_rebalance_tx(self, intent: ActionIntent) -> TxPlan:
        return TxPlan(plan_id="fb-r", intent_id=intent.intent_id, chain=intent.chain, to_address="0x2", data_hex="0x2")

    async def simulate(self, tx: TxPlan) -> SimulationResult:
        return SimulationResult(ok=True)

    async def execute(self, tx: TxPlan) -> ExecutionReceipt:
        return ExecutionReceipt(ok=False, chain=tx.chain, reason_codes=["NO_EXEC"])


def test_failover_adapter_uses_fallback_on_primary_error():
    adapter = FailoverExecutionAdapter(_PrimaryBrokenAdapter(), _FallbackAdapter())
    intent = ActionIntent(intent_id="i1", action="COMPOUND", chain="Base", position_ref="p1")
    tx = _run(adapter.build_compound_tx(intent))
    assert tx.plan_id == "fb-c"

    sim = _run(adapter.simulate(tx))
    assert sim.ok is True

    receipt = _run(adapter.execute(tx))
    assert receipt.ok is False
    assert receipt.reason_codes == ["NO_EXEC"]
