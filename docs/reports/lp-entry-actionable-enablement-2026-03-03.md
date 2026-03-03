# LP Entry Actionable Enablement Report — 2026-03-03

## Scope
- Plans: `docs/plans/029-lp-entry-actionable-enablement-roo-task.md`, `docs/plans/030-lp-entry-lp-scope-range-coverage-roo-task.md`
- Runtime mode: SHADOW-only evidence, без LIVE/infra/secrets изменений.
- Goal: убрать root-cause `all WATCHLIST` за счёт LP-scope pre-filter + range coverage telemetry + детерминированной reason taxonomy при сохранении fail-safe.

## Evidence Sources
- Before snapshot (pre-Plan029 baseline):
  - `docs/reports/artifacts/lp_entry_shadow_calibration_window24_2026-03-03.json`
  - source log: `docs/reports/artifacts/lp_entry_shadow_runtime_2026-03-03_window24.log`
- After snapshot A (Plan029 runtime with explicit no-graph scenario):
  - `docs/reports/artifacts/lp_entry_actionable_enablement_plan029_no_graph_2026-03-03.json`
  - source log: `docs/reports/artifacts/lp_entry_shadow_runtime_2026-03-03_plan029_no_graph.log`
- After snapshot B (Plan029 runtime with current env):
  - `docs/reports/artifacts/lp_entry_actionable_enablement_plan029_2026-03-03.json`
  - source log: `docs/reports/artifacts/lp_entry_shadow_runtime_2026-03-03_plan029.log`
- Plan030 parser snapshot (новый telemetry schema, mandatory command):
  - command: `PYTHONPATH=src .venv/bin/python scripts/lp_entry_shadow_calibration_report.py --from-file docs/reports/artifacts/lp_entry_shadow_runtime_2026-03-03_plan029.log`
  - note: source log — pre-Plan030 runtime artifact (поэтому новые coverage counters ожидаемо `0`).

## Before / After Snapshot

### Before (window24 baseline)
- `cycles_with_entry_telemetry`: `24`
- `entry_total_sum`: `710`
- `actionable_ratio`: `0.0`
- `watchlist_reason_counts`: `{}`
- `tick_density_readiness_blocker_counts`: `{}`

### After A (Plan029, no GRAPH key)
- `cycles_with_entry_telemetry`: `1`
- `entry_total_sum`: `30`
- `actionable_ratio`: `0.0`
- `watchlist_reason_counts`: `{"INVALID_OR_MISSING_RANGE": 30}`
- `tick_density_readiness_blocker_counts`: `{"GRAPH_API_KEY_MISSING": 6}`

### After B (Plan029, current env)
- `cycles_with_entry_telemetry`: `1`
- `entry_total_sum`: `30`
- `actionable_ratio`: `0.0`
- `watchlist_reason_counts`: `{"INVALID_OR_MISSING_RANGE": 22, "REPORT_GROUP_WATCHLIST": 8}`
- `tick_density_readiness_blocker_counts`: `{"SUBGRAPH_SCHEMA_UNSUPPORTED": 1}`

### After C (Plan030 parser snapshot over existing runtime artifact)
- `cycles_with_entry_telemetry`: `1`
- `entry_total_sum`: `30`
- `actionable_ratio`: `0.0`
- `watchlist_reason_counts`: `{"INVALID_OR_MISSING_RANGE": 22, "REPORT_GROUP_WATCHLIST": 8}`
- `entry_input_total_sum`: `0`
- `entry_lp_eligible_total_sum`: `0`
- `entry_lp_ineligible_total_sum`: `0`
- `entry_range_ready_total_sum`: `0`
- `entry_range_missing_total_sum`: `0`

> Coverage counters `0` в After C не означают regression runtime: source log собран до внесения Plan030 telemetry fields.

## Actionable Ratio Gate
- Introduced deterministic gate: `actionable_ratio_positive_pass = actionable_ratio > 0`.
- Current status in all available samples: `actionable_ratio_positive_pass=false`.

## Top Watchlist Reasons
- Top reasons from Plan029 no-graph run (After A):
  1. `INVALID_OR_MISSING_RANGE` — `30`
- Top reasons from Plan029 current-env run (After B / After C source):
  1. `INVALID_OR_MISSING_RANGE` — `22`
  2. `REPORT_GROUP_WATCHLIST` — `8`

## Plan030 Implementation (code-level)
- Added LP-entry pre-filter before recommendation build:
  - `entry_input_total`, `entry_lp_eligible_total`, `entry_lp_ineligible_total`.
- Added deterministic ineligible taxonomy:
  - `NON_LP_YIELD_TYPE`, `UNSUPPORTED_ENTRY_VENUE`, `MISSING_POOL_REFERENCE`.
- Extended range-path taxonomy:
  - `RANGE_NOT_COMPUTED`, `INVALID_OR_MISSING_RANGE`.
- Added range coverage telemetry counters:
  - `entry_range_ready_total`, `entry_range_missing_total`.
- Kept fail-safe contract unchanged:
  - degraded/stale/diverged/invalid-range remain `WATCHLIST`.

## Data-Readiness Blockers (Tick Density)
- Explicitly observed and captured in telemetry/evidence:
  - `GRAPH_API_KEY_MISSING` (missing graph key for subgraph init)
  - `SUBGRAPH_SCHEMA_UNSUPPORTED` (provider/subgraph schema incompatibility)

## Interpretation
- Fail-safe контракт сохранён: `ACTIONABLE` не форсируется; деградации/некорректный range остаются `WATCHLIST`.
- Plan030 закрывает root-cause на уровне runtime contract (LP-scope + taxonomy + coverage counters), но для подтверждения роста `actionable_ratio` требуется новый SHADOW log уже на обновлённом коде.
- Generic fallback причина `REPORT_GROUP_WATCHLIST` больше не является целевым fallback для основных ineligible/range-path причин в новой логике.

## Runbook Drift-Check (minimal)
- Применён workflow из `runbook-runtime-drift-check`:
  - проверен runtime diff и log signatures,
  - проверен `docs/runbooks` на drift-несоответствия.
- Drift для runbooks не зафиксирован; правки `docs/runbooks/*` не требуются.
