# Roo Task: Phase 3.0 Position Integrity — P&L + HODL Baseline v1

## Context
Runtime already migrated to reader-only execution state source:
- `main.py::_load_execution_states()` reads from `ArbitrumUniswapV3PositionReader`.
- `execution.mock_positions` is deprecated legacy-only.
- `position_value_usd` is now computed from liquidity+tick (`LIQUIDITY_TICK_MODEL_V1`).

Current gap for Phase 3.0:
- `P&L` and `HODL benchmark` for real positions are still not computed.
- reader currently emits `ENTRY_BASELINE_MISSING` markers.

References:
- `ROADMAP.md` (Phase 3.0 open item: `P&L` + `HODL benchmark`)
- `src/defi_agents/tracker/position_reader.py`
- `src/defi_agents/execution/models.py`
- `tests/test_position_reader.py`
- `docs/memory-bank/scout_config.json`

## Goal
Implement deterministic v1 baseline flow so runtime can compute:
- `hodl_value_usd`
- `net_pnl_usd`
- `pnl_vs_hodl_usd`
for positions that have an entry baseline, while keeping fail-safe behavior for missing baseline.

## Scope (must do)
1. Add entry-baseline contract for positions.
2. Add baseline provider (file-backed, deterministic) for runtime:
   - keyed by `position_ref` (`uni-v3:<token_id>`),
   - includes entry token amounts and entry USD prices (or entry value components).
3. Integrate baseline lookup into `ArbitrumUniswapV3PositionReader`.
4. Compute and expose in `PositionState.metadata`:
   - `entry_value_usd`
   - `hodl_value_usd`
   - `net_pnl_usd`
   - `pnl_vs_hodl_usd`
5. Keep explicit reason taxonomy:
   - baseline missing/incomplete -> keep `ENTRY_BASELINE_MISSING` (or more specific codes),
   - do not raise uncaught exceptions.
6. Keep existing reader behavior unchanged for execution safety:
   - stale guard logic,
   - fail-closed empty-state handling in `main.py`.

## Non-goals
- No VPS/systemd changes.
- No commit/push.
- No execution adapter/policy behavior changes.
- No Alchemy historical sync in this task (only deterministic baseline v1 source).

## Constraints
- Work only in `/home/dmitrii/projects/defi_agents`.
- Do not touch secrets/GitHub/n8n/server infra.
- Backward compatible defaults:
  - if baseline source is absent/empty, runtime continues safely with reason codes.
- No silent fabricated P&L values.

## Implementation Notes
- Keep baseline source explicit and auditable (e.g., JSON under `docs/memory-bank/`).
- Add small typed helper/provider module instead of embedding parsing logic into `main.py`.
- Preserve ASCII-only edits unless file already requires otherwise.
- Reuse existing reason-code style from reader/policy.

## Required Tests
1. Baseline present:
   - all four metrics computed and finite.
2. Baseline missing:
   - metrics absent/zero by contract,
   - reason includes `ENTRY_BASELINE_MISSING`,
   - no crash.
3. Baseline malformed/incomplete:
   - deterministic reason code,
   - no crash.
4. Regression:
   - existing `test_execution_state_source.py` behavior unchanged,
   - existing stale/price degrade paths in `test_position_reader.py` remain green.

## Verification Commands
```bash
.venv/bin/python -m json.tool docs/memory-bank/scout_config.json >/dev/null
.venv/bin/pytest -q tests/test_position_reader.py tests/test_execution_state_source.py tests/test_execution_config.py
```

## Deliverables
1. Code changes for baseline provider + reader integration.
2. Updated/added tests (green).
3. Sample baseline data file (safe, no secrets).
4. Memory Bank updates:
   - `docs/memory-bank/activeContext.md`
   - `docs/memory-bank/progress.md`
   - `docs/memory-bank/systemPatterns.md` (only if new pattern appears).
5. Short execution report in this format:
   - Summary (3–6 bullets)
   - Implemented
   - Changed files
   - Commands + results
   - Risks / not checked
   - Recommended commit message (no commit)

## Definition of Done
- Targeted tests pass.
- `P&L/HODL` metrics available for positions with baseline.
- Missing baseline is explicit and fail-safe (no fake values, no crashes).
- Roadmap Phase 3.0 status can be updated with this increment.
