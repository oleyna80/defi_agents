# LP Entry Actionable Enablement Report — 2026-03-04

## Scope
- Track: Phase 2.7.7 actionable enablement continuation after Plan 030.
- Runtime mode: локальный SHADOW evidence (WSL), без LIVE/infra изменений.
- Goal: подтвердить post-Plan030 status и зафиксировать следующий root-cause для узкого инкремента.

## Evidence Sources
- Startup-fail snapshot (prod-like startup guard):
  - `docs/reports/artifacts/lp_entry_shadow_runtime_2026-03-04_post_plan030.log`
  - `docs/reports/artifacts/lp_entry_shadow_calibration_post_plan030_2026-03-04.json`
- Runtime snapshot with local diagnostic fallback:
  - command-level env: `ALLOW_MOCK_FALLBACK=true` (no file/env mutation)
  - `docs/reports/artifacts/lp_entry_shadow_runtime_2026-03-04_post_plan030_mockai.log`
  - `docs/reports/artifacts/lp_entry_shadow_calibration_post_plan030_mockai_2026-03-04.json`

## Snapshot A — Startup Guard
- `cycles_with_entry_telemetry`: `0`
- `runtime_error_lines`: `40`
- `errors_zero_pass`: `false`
- Root cause: `DEEPSEEK_API_KEY is not set` + `ALLOW_MOCK_FALLBACK=false` -> `Production AI Init Failure`.

Interpretation:
- Snapshot A невалиден для LP calibration (cycle не доходит до LP telemetry блока).
- Это не regression Plan030, а env-startup gate behavior.

## Snapshot B — Post-Plan030 Runtime (MockAI Diagnostic)
- `cycles_with_entry_telemetry`: `4`
- `entry_total_sum`: `110`
- `actionable_ratio`: `0.0`
- `watchlist_ratio`: `1.0`
- `entry_lp_eligible_total_sum`: `26`
- `entry_range_ready_total_sum`: `23`
- `watchlist_reason_counts`:
  - `NON_LP_YIELD_TYPE`: `66`
  - `REPORT_GROUP_WATCHLIST`: `19`
  - `UNSUPPORTED_ENTRY_VENUE`: `18`
  - `NET_PROFIT_BELOW_THRESHOLD`: `4`
  - `RANGE_NOT_COMPUTED`: `3`
- `tick_density_readiness_blocker_counts`:
  - `SUBGRAPH_SCHEMA_UNSUPPORTED`: `4`

## Root-Cause Update
- LP pipeline после Plan030 работает (есть LP-eligible и range-ready candidates).
- Однако actionable остаётся `0`: в LP-eligible subset сохраняется существенная доля `REPORT_GROUP_WATCHLIST`.
- По runtime строкам `StrategySim summary` в том же окне: `ok=0` (доминируют `partial/unsupported`), что указывает на structural suppression через общий `report_group` path.

## Decision (Historical, Pre-Plan031)
- На момент post-Plan030 диагностики Phase 2.7.7 ещё не закрывалась.
- Был открыт следующий узкий инкремент: `docs/plans/031-lp-entry-strategysim-decoupling-roo-task.md`.
- Цель Plan 031: убрать coupling LP Entry с generic StrategySim downgrade (без ослабления fail-safe), добавить deterministic sim reason-codes и получить post-fix `actionable_ratio > 0` в SHADOW evidence.

## Snapshot C — Post-Plan031 Runtime (MockAI Diagnostic)
- Source log:
  - `docs/reports/artifacts/lp_entry_shadow_runtime_2026-03-04_post_plan031_mockai.log`
- Calibration snapshot:
  - `docs/reports/artifacts/lp_entry_shadow_calibration_post_plan031_mockai_2026-03-04.json`
- Snapshot metrics:
  - `cycles_with_entry_telemetry`: `4`
  - `entry_total_sum`: `112`
  - `actionable_ratio`: `0.1964`
  - `watchlist_ratio`: `0.8036`
  - `entry_lp_eligible_total_sum`: `32`
  - `entry_range_ready_total_sum`: `32`
  - `entry_range_missing_total_sum`: `0`
  - `watchlist_reason_counts`:
    - `NON_LP_YIELD_TYPE`: `64`
    - `UNSUPPORTED_ENTRY_VENUE`: `16`
    - `INSUFFICIENT_STABILITY_HISTORY`: `6`
    - `NET_PROFIT_BELOW_THRESHOLD`: `4`
  - `tick_density_readiness_blocker_counts`:
    - `SUBGRAPH_SCHEMA_UNSUPPORTED`: `4`

Gate interpretation (Plan031 closure evidence):
- `actionable_ratio_positive_pass=true` ✅
- `errors_zero_pass=true` ✅
- `telemetry_min_cycles_pass=false` (ожидаемо при 4-cycle diagnostic окне)
- `topn_churn_p95_pass=false` (`1.0`) в short-window diagnostic; это не отменяет факт снятия structural suppression.

Runtime/log signature check:
- `StrategySim summary` остаётся `ok=0 partial=13 unsupported=15 downgraded=7` (generic sim path жив).
- Одновременно LP telemetry больше не несёт `REPORT_GROUP_WATCHLIST`-доминацию в LP-eligible path; `entry_actionable` стал >0 (`4`, `4`, `7`, `7` по циклам).
- Это подтверждает decoupling LP Entry от generic StrategySim downgrade path при сохранении fail-safe downgrade по LP-специфичным причинам.

## Snapshot D — Plan032 Sustained SHADOW Closeout (MockAI, `>=24` cycles)
- Source log:
  - `docs/reports/artifacts/lp_entry_shadow_runtime_2026-03-04_phase277_closeout_mockai.log`
- Calibration snapshot:
  - `docs/reports/artifacts/lp_entry_shadow_calibration_phase277_closeout_mockai_2026-03-04.json`
- Runtime capture note:
  - для локальной диагностической сессии использовался command-level override `ALLOW_MOCK_FALLBACK=true` (без изменения `.env`/secrets).

Snapshot metrics:
- `cycles_with_entry_telemetry`: `24`
- `entry_total_sum`: `696`
- `actionable_ratio`: `0.2399`
- `watchlist_ratio`: `0.7601`
- `insufficient_history_ratio`: `0.0029`
- `topn_churn_avg`: `0.0605`
- `topn_churn_p95`: `0.3750`
- `entry_lp_eligible_total_sum`: `194`
- `entry_range_ready_total_sum`: `193`
- `entry_range_missing_total_sum`: `1`
- `watchlist_reason_counts`:
  - `NON_LP_YIELD_TYPE`: `406`
  - `UNSUPPORTED_ENTRY_VENUE`: `96`
  - `NET_PROFIT_BELOW_THRESHOLD`: `24`
  - `INSUFFICIENT_STABILITY_HISTORY`: `2`
  - `RANGE_NOT_COMPUTED`: `1`
- `tick_density_readiness_blocker_counts`:
  - `SUBGRAPH_SCHEMA_UNSUPPORTED`: `24`

Gate interpretation (Plan032 closeout):
- `errors_zero_pass=true` ✅
- `telemetry_min_cycles_pass=true` ✅
- `actionable_ratio_positive_pass=true` ✅
- `insufficient_history_ratio_pass=true` ✅
- `topn_churn_avg_pass=true` ✅
- `topn_churn_p95_pass=true` ✅
- `all_pass=true` ✅

Decision (Phase 2.7.7 closeout):
- `KEEP`.
- Обоснование: sustained SHADOW окно (`24` цикла) прошло обязательные gates без ошибок и с устойчивым ненулевым actionable ratio.
- Reversible tune не требуется (no-op path).

Runbook/runtime drift-check (minimal):
- Выполнено сравнение runtime/log signatures с runbook ожиданиями (`Execution states loaded`, `Execution summary`, `StrategySim summary`, `LP entry stability telemetry`).
- Runtime-contract drift, требующий правок `docs/runbooks/*`, не обнаружен.
