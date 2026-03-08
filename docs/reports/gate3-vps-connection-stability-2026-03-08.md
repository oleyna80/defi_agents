# Gate-3 VPS Connection Stability Report
**Date (UTC):** 2026-03-08
**Scope:** Step 1 connectivity/runtime blocker removal for reader path (`POSITION_READER_ALL_CHAINS_FAILED`, `Traceback|CRITICAL`, mass `POSITION_READER_ERROR err=RPC_HTTP_ERROR`)

## 1. Startup check (requested)
- `git status --short --branch`: branch `feat/multi-chain-reader`, 2 pre-existing untracked artifacts in `docs/reports/artifacts`.
- `git branch -vv`: `feat/multi-chain-reader` at `af6098b`, synced with `origin/feat/multi-chain-reader`.
- `git stash list`: `stash@{0}: On main: Pre-v3.6 uncommitted changes`.
- `git fetch origin --prune`: success.
- `git rev-parse HEAD`: `af6098b5238895025982812f8b8b4c9a5bcf4bdb`.
- `git rev-parse origin/feat/multi-chain-reader`: `af6098b5238895025982812f8b8b4c9a5bcf4bdb`.
- `rg` scan for reader/runtime markers: completed (matches in `main.py`, `position_reader.py`, tests, docs).

## 2. Runtime env/config verification
- `.env` presence check:
  - `WALLET_ADDRESS=SET`
  - `RPC_URL_ARBITRUM=SET`
  - `RPC_URL_BASE=SET`
  - `RPC_URL_OPTIMISM=SET`
  - `RPC_URL_HYPEEVM=SET`
- `execution.chains.*.rpc_url` vs `.env`:
  - Arbitrum: `MATCH`
  - Base: `MATCH`
  - Optimism: `MISMATCH`
  - HypeEVM: `MISMATCH`

## 3. RPC smoke-test results
### Before runtime fix (effective config URLs)
- Arbitrum: `eth_blockNumber OK`, `eth_call OK`
- Base: `eth_blockNumber OK`, `eth_call OK`
- Optimism: `ConnectError`
- HypeEVM: `ConnectError`

### After runtime fix (service mode with `.env` loaded)
- Arbitrum (`RPC_URL_ARBITRUM`): `eth_blockNumber OK`, `eth_call OK`
- Base (`RPC_URL_BASE`): `eth_blockNumber OK`, `eth_call OK`
- Optimism (`RPC_URL_OPTIMISM`): `eth_blockNumber OK`, `eth_call OK`
- HypeEVM (`RPC_URL_HYPEEVM`): `eth_blockNumber OK`, `eth_call OK`

## 4. Implemented minimal fix (connectivity/observability only)
- `main.py`:
  - Added deterministic RPC env resolution for execution chains: `RPC_URL_<CHAIN_NAME>`.
  - Added safe override behavior in `_build_execution_position_reader(...)`:
    - if env RPC exists -> use it,
    - otherwise fallback to `execution.chains.<chain>.rpc_url`.
  - Added explicit log line when env override differs from config URL.
- Tests:
  - Added regression tests for env-key normalization and override/fallback behavior in `tests/test_execution_state_source.py`.

## 5. Service restart and 48h log window
- Service restart executed: `systemctl --user restart --no-block defi-sentinel.service`.
- Fresh 48h artifact generated:
  - `docs/reports/artifacts/vps_reader_window_48h_2026-03-08.log`

### 48h counters (journal window still contains pre-fix history)
- `POSITION_READER_ALL_CHAINS_FAILED=7`
- `Traceback|CRITICAL=3`
- `POSITION_READER_ERROR=238`
- `RPC_HTTP_ERROR=170`

### Post-fix counters (since 2026-03-08 19:29:00 UTC)
- `POSITION_READER_ALL_CHAINS_FAILED=0`
- `Traceback|CRITICAL=0`
- `POSITION_READER_ERROR=0`
- `RPC_HTTP_ERROR=0`

## 6. Rebuilt Gate-3 evidence
- Artifact: `docs/reports/artifacts/gate3_evidence_contract_v1_2026-03-08_step1.json`
- Note: live `gate3_evidence_report.py` sampling via `WALLET_ADDRESS + RPC_URL_ARBITRUM` was long-running on VPS; for deterministic Step-1 packaging the report was generated with `--positions-file docs/reports/artifacts/gate3_positions_snapshot_plan035_2026-03-06.json` while keeping `--window \"48 hours ago\"` log evidence unchanged.
- Snapshot:
  - `execution_cycles=61`
  - `reader_ok=303`
  - `reader_ok_threshold_pass=true`
  - `positions_validated_count=3`
  - `errors_zero_pass=false`
  - `all_pass=false`
  - `reasons=["SHADOW_ERRORS_NOT_ZERO_OR_LOG_UNAVAILABLE"]`

## 7. Step-1 DoD status
1. No `POSITION_READER_ALL_CHAINS_FAILED` in 48h evidence: **NOT MET** (historical 48h entries remain).
2. No `Traceback|CRITICAL` in 48h evidence: **NOT MET** (historical 48h entries remain).
3. `reader_ok_threshold_pass=true`: **MET**.
4. `all_pass` false only due `<3 positions`: **N/A** (positions criterion already met, remaining blocker is historical errors in 48h window).

## 8. Next blocker
- To fully close Step-1 DoD by contract, a clean rolling window is required: wait for historical errors to age out of the 48h interval and re-run evidence packaging.
