# Technical Plan: LP Autocompound + Autorebalance Platform v1

Refers to Spec: `docs/specs/018-lp-autocompound-autorebalance-v1.md`
Module Reuse Add-on Plan: `docs/plans/019-v3utils-reuse-execution-plan.md`

## 1. Architecture Design

Components:
- `PositionStateProvider`: читает on-chain состояние позиции (range, liquidity, fees, tick).
- `TriggerEngine`: решает `COMPOUND_DUE / REBALANCE_DUE / HOLD`.
- `PolicyGuard`: hard checks (gas/slippage/budget/kill-switch/min-net).
- `ExecutionOrchestrator`: связывает trigger -> adapter -> simulate -> execute -> report.
- `ExecutionAdapter` implementations:
  - `NativeUniswapV3Adapter` (baseline fallback),
  - `NativeLiveExecutionAdapter` (RPC sender for pre-signed tx, LIVE-capable),
  - `KrystalExecutionAdapter` (optional, feature-flagged).

Data flow:
1. Load positions/watchlist.
2. Build `ActionIntent` per position.
3. Run `PolicyGuard`.
4. Build tx plan via selected adapter.
5. Simulate (`PAPER/SHADOW/LIVE`).
6. Execute only in `LIVE` and only if policy+simulation pass.
7. Persist counters + action journal.

## 2. API / Interface Changes

### New or Updated Endpoints / Functions

```python
class ActionIntent(BaseModel):
    intent_id: str
    action: Literal["COMPOUND", "REBALANCE", "SKIP"]
    chain: str
    position_ref: str
    reason_codes: list[str]
    expected_net_usd: float

class PolicyDecision(BaseModel):
    allowed: bool
    reason_codes: list[str]

class ExecutionAdapter(Protocol):
    async def build_compound_tx(self, intent: ActionIntent) -> TxPlan: ...
    async def build_rebalance_tx(self, intent: ActionIntent) -> TxPlan: ...
    async def simulate(self, tx: TxPlan) -> SimulationResult: ...
    async def execute(self, tx: TxPlan) -> ExecutionReceipt: ...
```

### Data Models (Schema)
- `ActionIntent`
- `TxPlan`
- `SimulationResult`
- `ExecutionReceipt`
- `ExecutionCounters`
- `PolicyConfig`
- `ExecutionConfig` (`mode`, adapter routing, budget limits)

## 3. File Structure Impact

- [+] `src/defi_agents/execution/models.py`
- [+] `src/defi_agents/execution/policy.py`
- [+] `src/defi_agents/execution/triggers.py`
- [+] `src/defi_agents/execution/orchestrator.py`
- [+] `src/defi_agents/execution/adapters/native_uniswap.py`
- [+] `src/defi_agents/execution/adapters/native_live.py`
- [+] `src/defi_agents/execution/adapters/krystal.py`
- [M] `src/defi_agents/scout/config.py` (execution config block)
- [M] `docs/memory-bank/scout_config.json` (feature flags + limits)
- [M] `main.py` (optional execution cycle hook, isolated from scout digest)
- [+] `tests/test_execution_policy.py`
- [+] `tests/test_execution_triggers.py`
- [+] `tests/test_execution_orchestrator.py`
- [+] `tests/test_execution_krystal_adapter.py`
- [+] `tests/test_execution_native_live_adapter.py`

## 4. Verification Strategy

Unit tests:
- policy guard thresholds
- trigger classification
- idempotency (duplicate intent suppression)
- adapter fallback selection

Integration tests:
- `PAPER`: deterministic tx plans from mocked positions.
- `SHADOW`: simulation path with mocked RPC and adapter responses.
- `LIVE` dry smoke on test wallet/low-value pool with explicit operator confirmation.

Manual checks:
- kill-switch ON blocks all execute calls.
- policy reject writes reason code to logs/summary.
- Krystal unavailable -> fallback adapter selected.

## 5. Implementation Checklist

- [x] Phase A: Contracts + config surface (`ExecutionConfig`, `PolicyConfig`, typed models)
- [x] Phase B: PositionStateProvider + TriggerEngine
- [x] Phase C: PolicyGuard + counters + journal logging
- [x] Phase D: NativeUniswapV3Adapter (baseline)
- [x] Phase E: KrystalExecutionAdapter (optional; gated by key + health checks)
- [x] Phase F: Orchestrator integration in `PAPER` mode
- [x] Phase G: SHADOW rollout (24h), collect counters and failure taxonomy
- [ ] Phase H: LIVE canary (single chain, strict budget, manual kill-switch test)

Phase G status update:
- STARTED (2026-02-21 22:50 UTC): `defi-sentinel.timer` enabled/active.
- PASSED (2026-02-23): Gate-2 24h window met all criteria:
  - `runs=85`, `execution_summaries=85`, `errors=0`
  - `execution_cycles=85`, `intents=255`, `tx_plans=170`
  - `sim_ok=170`, `sim_fail=0`, `exec_ok=0`, `exec_fail=0`
  - `blocked_by_policy=85` with expected policy reason map in each cycle.

Phase H prep update (2026-02-23):
- Kill-switch drill executed in controlled LIVE canary profile (manual run, timer paused):
  - Drill A (`mode=LIVE`, `kill_switch=true`): `blocked_by_policy=3`, `tx_plans=0`, reason map includes `KILL_SWITCH_ENABLED`.
  - Drill B (`mode=LIVE`, `kill_switch=false`): `tx_plans=2`, `sim_ok=2`, `exec_fail=2`, `exec_fail_reasons={'LIVE_EXECUTION_NOT_IMPLEMENTED': 2}`.
- Rollback completed: config restored to SHADOW baseline; `defi-sentinel.timer` re-started (`active`), systemd cycle confirms `Execution summary: mode=SHADOW`.
- Krystal credential smoke (SHADOW, primary=krystal, fallback=native) executed with `KRYSTAL_CLOUD_API_KEY`:
  - primary adapter calls fail with `KrystalAdapterError` on `build_*` and `simulate`,
  - runtime failover path is healthy (`FailoverExecutionAdapter` switched to native, cycle completed),
  - no crash/fatal; execution summary remained stable (`sim_ok=2`, `sim_fail=0`, `blocked_by_policy=1`).
- Root-cause confirmed by direct probe: `cloud-api.krystal.app` returns `404` for `/v1/execution/*`; adapter now maps this to deterministic `KRYSTAL_EXECUTION_API_UNAVAILABLE` and LIVE gate treats Krystal as non-live-capable until official execution endpoints exist.
- Added `native_uniswap_v3_live` adapter path as LIVE-capable native fallback:
  - execute path uses `eth_sendRawTransaction` + receipt polling via chain RPC,
  - requires configured RPC env per chain (`execution.native_live_rpc_env_by_chain`) and pre-signed payload in `TxPlan.metadata.signed_raw_tx`,
  - fail-safe reason taxonomy added for runtime diagnostics (`SIGNED_RAW_TX_MISSING`, `TX_RECEIPT_TIMEOUT`, `RPC_*`).
- Added dedicated reuse-integration track for `KrystalDeFi/v3utils` + `revert-finance` modules:
  - execution intent mechanics will be reused through adapter boundaries (no vendor API dependency for liquidity data),
  - integration sequence and DoD captured in `docs/plans/019-v3utils-reuse-execution-plan.md`.
- Landed initial code scaffold for reuse track:
  - added feature-flagged `v3utils` adapter path in runtime (`primary_adapter=v3utils`),
  - added config surface `v3utils_*` and adapter tests,
  - pinned ABI/address bundle added under `src/defi_agents/execution/abi/` with commit lock `33f487...`,
  - structured `compound` + `rebalance` calldata encoding paths added, with simulation selector/contract consistency checks,
  - execution suite validation remains green (`72 passed`).

## 6. Rollout Gates

- Gate-1 (`PAPER`):
  - tests green
  - no fatal errors on full cycle
  - stable intent generation

- Gate-2 (`SHADOW`, 24h):
  - `exec_ok == 0` (by design)
  - simulation success ratio >= target
  - no crash loops

- Gate-3 (`LIVE` canary):
  - explicit operator approval
  - kill-switch validated
  - max daily tx/gas budget respected

## 7. Risks & Mitigations

- Risk: vendor outage/rate-limit (Krystal)
  - Mitigation: adapter timeout + fallback to native adapter.
- Risk: unprofitable churn via over-rebalance
  - Mitigation: `min_expected_net_usd` + cooldown window per position.
- Risk: slippage/MEV spikes
  - Mitigation: strict `max_slippage_bps`, simulation check, reject on uncertainty.
