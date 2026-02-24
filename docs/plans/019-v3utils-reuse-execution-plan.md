# Technical Plan: V3Utils/Compoundor Reuse for Execution Layer v1

Refers to Spec: `docs/specs/018-lp-autocompound-autorebalance-v1.md`
Related Plan: `docs/plans/018-lp-autocompound-autorebalance-v1-plan.md`
Date: 2026-02-23
Status: STARTED (R1 ABI pin + R2 scaffold + R3 compound + R4 rebalance encoding)

## 1. Goal

Use open-source execution modules from `KrystalDeFi/v3utils` and `revert-finance` to avoid rebuilding autocompound/autorebalance mechanics from scratch, while preserving our existing safety and orchestration contracts.

## 2. Core Architecture Rule

- Liquidity/tick analytics stay direct from DEX (`subgraph + RPC`), not from vendor API.
- Execution logic can reuse open-source on-chain/off-chain modules.
- Runtime control remains ours: `TriggerEngine`, `PolicyGuard`, `ExecutionOrchestrator`, kill-switch, budgets.

In short: **external modules for tx intent mechanics, internal runtime for risk and control plane**.

## 3. Reuse Mapping

| Source | Reuse Mode | Target in Our System |
|---|---|---|
| `KrystalDeFi/v3utils` (`V3Utils`, `V3Automation`) | Primary code reuse for CLMM execution calls | `V3UtilsExecutionAdapter` tx builders (`build_compound_tx`, `build_rebalance_tx`) |
| `revert-finance/compoundor` (Solidity) | Reference for compound flow and safety semantics | Validation of call sequence + guard assumptions |
| `revert-finance/compoundor-js` | Reference for off-chain parameter assembly and job patterns | Adapter parameterization and canary scripts |

## 4. Planned Components

1. `src/defi_agents/execution/adapters/v3utils.py`
- New adapter implementing `ExecutionAdapter`.
- `supports_live_execution=True` only when chain contracts + signer prerequisites are met.
- `build_*` creates ABI-encoded calls for v3utils automation contracts.

2. `src/defi_agents/execution/abi/` (new folder)
- Pinned ABI JSON files used by tx builders.
- No runtime remote ABI fetches.

3. Execution config extensions (in `ScoutConfig.execution`)
- `v3utils_enabled: bool`
- `v3utils_contracts_by_chain: dict[str, str]`
- `v3utils_router_by_chain: dict[str, str]` (optional)
- `v3utils_slippage_bps_default: int` (bounded by policy caps)

4. Transport/signing integration
- Use current native live transport path (`eth_sendRawTransaction` + receipt polling).
- Keep key management external (pre-signed raw tx / signer service), no hot private key in scout process.

## 5. Delivery Phases

### Phase R1: Contract Pinning + ABI Baseline
- Pin target repo commits and contract set for wave-1 chain.
- Add ABI files to repository.
- Add minimal config schema for v3utils addresses.

DoD:
- ABI files committed.
- Config validates with safe defaults (`v3utils_enabled=false`).

### Phase R2: Adapter Scaffold
- Add `V3UtilsExecutionAdapter` class.
- Wire adapter builder in `main.py`.
- Keep feature-flag off by default.

DoD:
- Unit tests: adapter selection, fail-closed LIVE behavior, disabled-flag safety.

### Phase R3: Compound Path
- Implement `build_compound_tx` using pinned ABI encoding.
- Implement simulation path (`eth_call`/dry-run) for compound tx.

DoD:
- Deterministic unit tests for encoded payload and plan fields.
- SHADOW cycle produces valid tx plans for compound intents.

### Phase R4: Rebalance Path
- Implement `build_rebalance_tx` (range adjust / close+open depending on module flow).
- Add reason taxonomy for unsupported param sets.

DoD:
- Unit tests for rebalance payload encoding.
- SHADOW scenario shows stable `sim_ok` with no runtime crash.

### Phase R5: LIVE Canary
- Canary on one chain (Base), dust exposure, strict budget caps.
- Operator-run kill-switch drill during canary window.

DoD:
- At least one successful compound receipt.
- At least one successful rebalance receipt.
- Rollback procedure verified.

## 6. Safety and Guardrails

- All live sends still gated by `PolicyGuard`.
- `allow_live_mode=true` only for explicit canary window.
- Daily tx/gas caps and slippage caps remain mandatory.
- Fail-closed behavior preserved when adapter prerequisites are missing.

## 7. Test Strategy

Unit:
- ABI encoding correctness (`to`, `data`, `value`).
- Reason-code mapping for invalid or missing params.
- Adapter selection matrix (`native`, `native_live`, `v3utils`, `krystal`).

Integration (SHADOW):
- compound/rebalance mock intents -> tx plans -> simulate.
- fallback behavior on RPC/encoding errors.

Canary (LIVE):
- dust position only.
- receipt validation (`tx_hash`, `block_number`, `gas_used`).
- rollback-to-shadow checklist.

## 8. Risks

- ABI/contract drift between upstream repos and deployed addresses.
- Chain-specific differences in router/position manager interactions.
- Partial reuse mismatch: some flows may still require custom wrappers.

Mitigations:
- Pin commits + ABI snapshots.
- Wave-1 single chain.
- Feature flag with fail-closed fallback.

## 9. Next Engineering Step

Start Phase R1 immediately:
1. pin target v3utils commit,
2. extract ABI set,
3. add config schema + adapter scaffold under feature flag.

## 10. Status Update (2026-02-23)

- R1 ABI pin completed:
  - upstream commit pinned: `33f487253051c3d6f439dc911b0e415b28b4cc9c`,
  - ABI/address snapshot bundle added under `src/defi_agents/execution/abi/`:
    - `v3utils_execute.abi.json`
    - `v3automation_execute.abi.json`
    - `v3utils_contracts.json`
    - `v3utils.lock.json` (+ `README.md`).
- R2 scaffold implemented:
  - new adapter `src/defi_agents/execution/adapters/v3utils.py` (`V3UtilsExecutionAdapter`),
  - runtime routing enabled in `main.py` (`primary_adapter=v3utils`),
  - config surface added (`v3utils_enabled`, `v3utils_contracts_by_chain`, `v3utils_router_by_chain`, `v3utils_slippage_bps_default`),
  - tests added (`tests/test_execution_v3utils_adapter.py`, `tests/test_execution_v3utils_abi_assets.py`, builder/config updates).
- Validation:
  - execution suite green: `72 passed`.
- R3 compound path started:
  - `V3UtilsExecutionAdapter` now supports structured `v3utils_compound_params` input and builds `execute(...)` calldata using ABI encoding (selector `0xfd2d17d1`),
  - metadata `*_data_hex` fallback remains for backward compatibility,
  - structured payload tests added (success + validation failure).
- R4 rebalance path started:
  - `V3UtilsExecutionAdapter` now supports structured `v3utils_rebalance_params` input and builds `execute(...)` calldata for change-range flow,
  - rebalance validation added (`tick_lower`/`tick_upper` required and ordered),
  - adapter `simulate()` now enforces selector/contract consistency for structured payloads.
- Next:
  - run SHADOW integration with real structured params on Base,
  - then move to canary prep with bounded dust exposure.
