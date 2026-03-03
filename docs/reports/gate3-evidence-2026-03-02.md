# Gate-3 Evidence Pack — 2026-03-02

## Scope

- Plan 023 (Gate-3 Evidence Pack), repo-local evidence only.
- Runtime code changes are out of scope; docs/evidence only.

## Evidence Sources Used

1. Reader-only runtime contract/log signatures from `main.py` and runbooks.
2. Local reader invocation attempt in `.venv` with repo `.env`.
3. Baseline source file `docs/memory-bank/position_entry_baselines.json`.
4. Test evidence from targeted pytest and full `make test`.

## Reader Availability Snapshot (repo-local)

| check | value | note |
|---|---:|---|
| `wallet_set` | `true` | local `.env` now exposes `WALLET_ADDRESS` |
| `rpc_set` | `true` | local `.env` now exposes `RPC_URL_ARBITRUM` |
| baseline positions count | `1` | `positions` map contains baseline for `uni-v3:5340024` |

Raw command output used:

```json
{"wallet_set": true, "rpc_set": true}
```

## Required Position Evidence (`pnl_vs_hodl`) 

Requirement: at least 3 real positions via reader-only path with fields:
`position_id`, `as_of_ts`, `position_pnl_usd`, `hodl_pnl_usd`, `pnl_vs_hodl_usd`, `reason_code`.

Collected in this repository session: **1 / 3** real positions.

| position_id | as_of_ts | position_pnl_usd | hodl_pnl_usd | pnl_vs_hodl_usd | reason_code |
|---|---|---:|---:|---:|---|
| `uni-v3:5340024` | `1772541767` | `-10.3341` | `-9.2831` | `-1.0511` | `[]` |

## SHADOW Stability Check

- N criterion source: `docs/runbooks/shadow-gate-real-positions-v1.md` (`reader_ok >= 90`, 48h gate window).
- Threshold used for this pack: `reader_ok >= 90` events in the 48h gate window (per runbook wording).
- Required by Plan 023: SHADOW stability evidence in the gate window with no critical reason-codes and no fail-open behavior.

Observed from repo-local artifacts in this session:

- No 48h runtime journal extract with real reader cycles is available in repository files.
- Therefore, N-cycle stability cannot be confirmed from local artifacts.
- Fail-open behavior at code-contract level remains fail-closed:
  - reader unavailability paths return empty state set with explicit reasons,
  - no runtime fallback to `execution.mock_positions`.

## Test/Verification Commands

Executed:

1. `PYTHONPATH=src .venv/bin/pytest -q tests/test_position_reader.py tests/test_execution_policy.py tests/test_execution_orchestrator.py`
   - Result: `24 passed`
2. `make test`
   - Result: `318 passed`

3. `make gate3-evidence-report`
   - Result (snapshot):

```json
{
  "unit": "defi-sentinel.service",
  "window": "48 hours ago",
  "reader_threshold": 90,
  "preflight": {
    "wallet_set": true,
    "rpc_set": true,
    "baseline_positions_count": 1
  },
  "summary": {
    "execution_cycles": 0,
    "reader_ok": 0,
    "errors": 0,
    "blocked_by_policy": 0,
    "sim_ok": 0,
    "sim_fail": 0,
    "exec_ok": 0,
    "exec_fail": 0
  },
  "gate_checks": {
    "reader_ok_threshold_pass": false,
    "errors_zero_pass": true,
    "sim_fail_zero_pass": true
  }
}
```

## Gate-3 Verdict (Plan 023)

**FAIL (insufficient evidence)**

Rationale:

1. Real-position evidence table is below minimum (`1 < 3`).
2. SHADOW stability evidence for the 48h gate window (`reader_ok >= 90`) is unavailable from repo-local logs/artifacts.
3. Gate-3 PASS cannot be claimed without both conditions above.
