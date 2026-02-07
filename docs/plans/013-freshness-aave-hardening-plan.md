# Technical Plan: Freshness Aave Hardening (Phase C+ Stabilization)

Refers to Spec: `docs/specs/010-freshness-recheck-v1.md`  
Related Plan: `docs/plans/010-freshness-recheck-v1-plan.md`

## 1. Objective
Stabilize Aave direct freshness re-check so it can run in production shadow-mode with measurable reliability and safe rollout gates before strict freshness enforcement.

## 2. Scope
- Keep `risk-first` semantics unchanged.
- Keep fail-safe behavior unchanged (`None` snapshot on adapter issues, no cycle crash).
- Add production diagnostics and fallback mechanics for Aave direct path.

Out of scope:
- Enabling strict freshness by default.
- Any scheduler/systemd changes.
- Scoring changes or strategy logic changes.

## 3. Technical Changes
### Adapter reliability
- Add primary + fallback endpoint strategy in `AaveDirectAdapter`.
- Keep bounded request timeout.
- Sanitize all warning logs (no token/raw endpoint leakage).

### Mapping/mismatch policy
- Preserve hard reject for invalid allowlist mapping.
- Keep deterministic match by underlying address.
- On candidate/reserve mismatch where reserve identity is still deterministic, return safe snapshot with diagnostic tag (no silent promotion).

### Observability
- Extend freshness counters for Aave path:
  - `aave_checked`
  - `aave_ok`
  - `aave_timeout`
  - `aave_error`
  - `aave_schema_mismatch`
  - `aave_addr_mismatch`
- Emit counters in cycle summary logs.

## 4. Config Surface
Expected freshness config fields:
- `aave_direct_enabled` (`false` by default)
- `aave_direct_timeout_seconds`
- `aave_direct_api_key_env`
- `aave_direct_endpoints` (per-chain primary endpoints)
- `aave_direct_fallback_endpoints` (per-chain optional fallback endpoints)
- `aave_direct_reserve_symbols` (allowlist: `symbol -> underlying address`)

## 5. File Structure Impact
- [M] `src/defi_agents/freshness/adapters/aave_direct.py`
- [M] `src/defi_agents/freshness/manager.py`
- [M] `src/defi_agents/scout/config.py`
- [M] `docs/memory-bank/scout_config.json`
- [M] `main.py` (only if summary logs are emitted there)
- [M] `tests/test_aave_adapter.py`
- [M] `tests/test_freshness_manager.py`

## 6. Implementation Checklist
- [ ] Implement primary/fallback endpoint logic with timeout budget.
- [ ] Add sanitized diagnostics for endpoint fallback and failures.
- [ ] Keep deterministic matching by underlying address + explicit mismatch diagnostics.
- [ ] Add Aave freshness counters and summary logging.
- [ ] Validate config defaults remain production-safe (`enabled=false`, no secrets in JSON).
- [ ] Update memory-bank status after merge.

## 7. Verification Strategy
Unit tests:
- Primary endpoint fail + fallback success.
- Timeout/error fail-safe path.
- Address-mismatch handling path.
- Secret-safe logging assertions.

Integration tests:
- Manager counters aggregation with mixed adapter outcomes.
- Full pipeline remains non-failing on adapter errors.

Commands:
- `.venv/bin/python -m json.tool docs/memory-bank/scout_config.json >/dev/null`
- `.venv/bin/pytest -q tests/test_aave_adapter.py tests/test_freshness_manager.py tests/test_freshness_policy.py`
- `.venv/bin/pytest -q`

## 8. VPS Rollout Gates
1. Shadow mode only:
   - `aave_direct_enabled=true`
   - `enforce_freshness_for_actionable=false`
2. Collect telemetry for 24h.
3. Promote to strict only if:
   - `aave_ok / aave_checked >= 0.70`
   - no sustained timeout/error streaks
   - no secret leakage in logs

## 9. Acceptance Criteria
- No cycle failures introduced by Aave adapter.
- Adapter warnings are secret-safe.
- Fallback path works when primary endpoint fails.
- Aave counters are visible in logs and usable for rollout decisions.
- Test suites stay green.
