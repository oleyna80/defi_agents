# Roo Task: Freshness Aave Hardening (Phase C+)

## Context
Base branch already contains `AaveDirectAdapter` with fail-safe behavior and tests.  
Need to harden reliability and observability before strict freshness gating on VPS.

References:
- `docs/specs/010-freshness-recheck-v1.md`
- `docs/plans/013-freshness-aave-hardening-plan.md`
- `src/defi_agents/freshness/adapters/aave_direct.py`
- `src/defi_agents/freshness/manager.py`
- `src/defi_agents/scout/config.py`

## Scope (must do)
1. Add primary + fallback endpoint flow for Aave direct adapter.
2. Keep deterministic reserve match by underlying address.
3. Add explicit counters for Aave adapter outcomes.
4. Keep all failures non-fatal for cycle execution.
5. Keep logs sanitized (no tokens, no raw key-bearing URLs).

## Non-goals
- No scheduler/systemd edits.
- No scoring/strategy changes.
- No default strict freshness enablement.

## Constraints
- Default config remains production-safe:
  - `aave_direct_enabled=false`
  - no secret values in JSON
- Maintain risk-first behavior:
  - uncertain/missing data must remain `UNVERIFIED`/watchlist path
- Preserve backward compatibility with existing freshness adapters.

## Implementation Notes
- Config additions/usage:
  - `aave_direct_endpoints` (primary)
  - `aave_direct_fallback_endpoints` (optional fallback)
  - `aave_direct_timeout_seconds`
  - `aave_direct_api_key_env`
  - `aave_direct_reserve_symbols`
- Counters to emit:
  - `aave_checked`, `aave_ok`, `aave_timeout`, `aave_error`, `aave_schema_mismatch`, `aave_addr_mismatch`

## Required Tests
- Adapter:
  - primary failure -> fallback success
  - timeout/error returns `None`
  - address mismatch diagnostic path
  - secret-safe logging assertions
- Manager:
  - counters aggregation for mixed outcomes
  - no pipeline crash on adapter errors

## Verification Commands
```bash
.venv/bin/python -m json.tool docs/memory-bank/scout_config.json >/dev/null
.venv/bin/pytest -q tests/test_aave_adapter.py tests/test_freshness_manager.py tests/test_freshness_policy.py
.venv/bin/pytest -q
```

## Deliverables
1. Code changes in freshness adapter/manager/config.
2. Updated tests (green).
3. Updated memory bank:
   - `docs/memory-bank/activeContext.md`
   - `docs/memory-bank/progress.md`
4. Short rollout note for VPS shadow-mode enablement.

## Definition of Done
- All required tests pass.
- No secret leakage in logs under error paths.
- Fallback endpoint path works as designed.
- Aave counters visible in cycle logs.
- Config defaults remain safe (`enabled=false`).
