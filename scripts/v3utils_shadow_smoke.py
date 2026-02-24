import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.execution import ExecutionOrchestrator, PolicyGuard, PositionState, TriggerEngine  # noqa: E402
from defi_agents.execution.adapters import V3UtilsExecutionAdapter  # noqa: E402
from defi_agents.scout.config import ExecutionConfig  # noqa: E402


def _load_v3utils_base_contract() -> str:
    contracts_path = Path("src/defi_agents/execution/abi/v3utils_contracts.json")
    payload = json.loads(contracts_path.read_text(encoding="utf-8"))
    base = payload.get("8453", {})
    addr = str(base.get("v3Utils") or "").strip()
    if not addr:
        raise RuntimeError("v3Utils address missing in v3utils_contracts.json for chainId=8453")
    return addr


async def main() -> None:
    cfg = ExecutionConfig(
        enabled=True,
        mode="SHADOW",
        primary_adapter="v3utils",
        fallback_adapter="native_uniswap_v3",
        v3utils_enabled=True,
        v3utils_contracts_by_chain={"Base": _load_v3utils_base_contract()},
    )
    adapter = V3UtilsExecutionAdapter(
        rpc_urls={"Base": "https://base-rpc.invalid"},
        contracts_by_chain=cfg.v3utils_contracts_by_chain,
        routers_by_chain=cfg.v3utils_router_by_chain,
        default_slippage_bps=cfg.v3utils_slippage_bps_default,
    )

    now_ts = 1700000000
    states = [
        PositionState(
            chain="Base",
            position_ref="v3utils-structured-compound",
            current_tick=100,
            lower_tick=80,
            upper_tick=120,
            unclaimed_fees_usd=10.0,
            estimated_compound_gas_usd=1.0,
            v3utils_compound_params={
                "nfpm": "0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1",
                "token_id": 12345,
                "instructions": {
                    "recipient": "0x1234567890123456789012345678901234567890",
                    "amount_add_min_0": 1,
                    "amount_add_min_1": 1,
                },
            },
        ),
        PositionState(
            chain="Base",
            position_ref="v3utils-structured-rebalance",
            current_tick=130,
            lower_tick=80,
            upper_tick=120,
            expected_rebalance_net_usd=12.0,
            estimated_rebalance_gas_usd=1.5,
            v3utils_rebalance_params={
                "nfpm": "0x03a520b32C04BF3bEEf7BEb72E919cf822Ed34f1",
                "token_id": 12345,
                "instructions": {
                    "recipient": "0x1234567890123456789012345678901234567890",
                    "tick_lower": -120,
                    "tick_upper": 120,
                    "amount_add_min_0": 1,
                    "amount_add_min_1": 1,
                },
            },
        ),
    ]

    orchestrator = ExecutionOrchestrator(
        mode="SHADOW",
        trigger_engine=TriggerEngine(cfg),
        policy_guard=PolicyGuard(cfg.policy),
        adapter=adapter,
    )
    report = await orchestrator.run_states(states, now_ts=now_ts)
    print(
        json.dumps(
            {
                "mode": report.mode,
                "intent_count": report.counters.intent_count,
                "tx_plans": len(report.tx_plans),
                "sim_ok": report.counters.sim_ok,
                "sim_fail": report.counters.sim_fail,
                "sim_fail_reasons": report.sim_fail_reason_counts,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
