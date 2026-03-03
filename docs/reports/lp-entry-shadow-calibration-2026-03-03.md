# LP Entry SHADOW Calibration Evidence Report — 2026-03-03

## Scope
- Plan: `docs/plans/028-lp-entry-shadow-evidence-calibration-roo-task.md`
- Execution mode: SHADOW evidence only (no LIVE/infra/secrets changes)
- Source artifacts:
  - initial runtime check: `docs/reports/artifacts/lp_entry_shadow_runtime_2026-03-03_no_telegram.log`
  - window-24 runtime check: `docs/reports/artifacts/lp_entry_shadow_runtime_2026-03-03_window24.log`

## Baseline Snapshot (initial)
Source: `PYTHONPATH=src .venv/bin/python scripts/lp_entry_shadow_calibration_report.py --from-file docs/reports/artifacts/lp_entry_shadow_runtime_2026-03-03_no_telegram.log`

Snapshot JSON artifact: `docs/reports/artifacts/lp_entry_shadow_calibration_runtime_2026-03-03.json`

- `cycles_with_entry_telemetry`: `1`
- `entry_total_sum`: `30`
- `actionable_ratio`: `0.0`
- `watchlist_ratio`: `1.0`
- `insufficient_history_ratio`: `0.0`
- `topn_churn_avg`: `0.0`
- `topn_churn_p95`: `0.0`
- `telemetry_parse_errors`: `0`
- `runtime_error_lines`: `0`
- `total_errors`: `0`

## Window-24 Snapshot (gate window)
Source: `PYTHONPATH=src .venv/bin/python scripts/lp_entry_shadow_calibration_report.py --from-file docs/reports/artifacts/lp_entry_shadow_runtime_2026-03-03_window24.log`

Snapshot JSON artifact: `docs/reports/artifacts/lp_entry_shadow_calibration_window24_2026-03-03.json`

- `cycles_with_entry_telemetry`: `24`
- `entry_total_sum`: `710`
- `actionable_ratio`: `0.0`
- `watchlist_ratio`: `1.0`
- `insufficient_history_ratio`: `0.0`
- `topn_churn_avg`: `0.0`
- `topn_churn_p95`: `0.0`
- `telemetry_parse_errors`: `0`
- `runtime_error_lines`: `0`
- `total_errors`: `0`

## Gate Checks (Deterministic)
Thresholds (safe defaults):
- `telemetry_min_cycles=24`
- `max_insufficient_history_ratio=0.35`
- `max_topn_churn_avg=0.45`
- `max_topn_churn_p95=0.75`

Gate booleans:
- `errors_zero_pass`: `true`
- `telemetry_min_cycles_pass`: `true`
- `insufficient_history_ratio_pass`: `true`
- `topn_churn_avg_pass`: `true`
- `topn_churn_p95_pass`: `true`
- `all_pass`: `true`

## Evidence Quality / Data Sufficiency
- В runtime-артефакте подтверждена telemetry-сигнатура LP entry в полном окне (`cycles_with_entry_telemetry=24`).
- Gate PASS достигнут в window-24 прогоне: все deterministic checks `true`.
- Данные не дополнялись синтетически; решение принято fail-safe на основании имеющегося артефакта.

## Controlled Calibration (max 1 iteration)
Статус: **не выполнялась**.

Обоснование:
- Window-24 gates PASS без изменения параметров.
- Текущее решение: подтвердить стабильность и оставить параметры без ретюна (`KEEP`), т.к. evidence не показывает необходимости корректировки.

Config changes:
- `docs/memory-bank/scout_config.json`: **без изменений**.

## Post-Tune Compare
- Не применимо (изменения параметров отсутствуют).

## Decision
**KEEP** (no-op):
- оставить текущие safe defaults без ретюна;
- зафиксировать проход evidence-gate по window-24 telemetry.

## Runbook Drift-Check (minimal)
- Проверен drift между runtime/log signatures и runbook-инструкциями по workflow `runbook-runtime-drift-check`.
- В этом инкременте runtime ветки `main.py`/execution/tracker не менялись (изменения только evidence tooling и тесты).
- Противоречий runbook не обнаружено; правки в `docs/runbooks/*` не требуются.

## Rollback Path
- Текущий rollout без изменений параметров (`before == after`), rollback = no-op.
- Для будущего controlled retune: фиксировать `before -> after` в `docs/memory-bank/scout_config.json` и откатывать ровно эти 1-2 параметра до `before` значений.

## Phase 2.7.6 Status
- **CLOSED (Plan 028 evidence gate passed)**
