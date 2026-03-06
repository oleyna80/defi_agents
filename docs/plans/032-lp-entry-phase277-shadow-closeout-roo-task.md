# Roo Task 032 — Phase 2.7.7 Shadow Closeout (Sustained Evidence + Optional Reversible Tune)

## 0. Objective
Формально закрыть `Phase 2.7.7 (Actionable Enablement)` после Plan 031 на основании устойчивого SHADOW evidence.

Исходное состояние после Plan 031:
- structural suppression устранён;
- `actionable_ratio_positive_pass=true` уже подтверждён на short-window diagnostic;
- остаётся незакрытый long-window критерий (устойчивость/churn/окно наблюдений).

Целевой результат:
- получить sustained SHADOW evidence window с валидной телеметрией;
- подтвердить, что `actionable_ratio > 0` сохраняется без ослабления fail-safe;
- при необходимости выполнить максимум 1 reversible tune (1-2 параметра) и зафиксировать before/after.

## 1. Scope
In scope:
- Сбор post-Plan031 SHADOW telemetry окна (целевое: `>=24` циклов).
- Обновление calibration snapshot + evidence report.
- Проверка gate-условий и прозрачное решение `KEEP` / `ADJUST` / `ROLLBACK`.
- Опциональный reversible tune только через конфиг-параметры (без изменения fail-safe логики).
- Синхронизация `ROADMAP` + memory-bank по факту.

Out of scope:
- LIVE execution / tx automation.
- Изменения внешней инфраструктуры, secrets, n8n, VPS.
- Ослабление LP fail-safe инвариантов.
- Рефакторинг runtime-кода, не связанный с closeout evidence.

## 2. Required File Targets
- `docs/reports/lp-entry-actionable-enablement-2026-03-04.md` (append closeout section or add dated follow-up report)
- `docs/reports/artifacts/*` (new runtime log + calibration snapshot)
- `ROADMAP.md`
- `docs/memory-bank/activeContext.md`
- `docs/memory-bank/progress.md`
- `docs/memory-bank/systemPatterns.md` (only if new pattern/decision appears)

Optional (only if reversible tune required):
- `docs/memory-bank/scout_config.json` (1-2 calibration knobs max, with explicit rollback path)
- related tests if behaviorally impacted

## 3. Implementation Requirements
1. Sustained evidence capture (mandatory):
   - Собрать SHADOW лог post-Plan031 для окна `>=24` циклов.
   - Допустим command-level env override `ALLOW_MOCK_FALLBACK=true` только для локальной диагностической сессии (без изменения `.env`/секретов).

2. Snapshot + gate evaluation (mandatory):
   - Сформировать snapshot через:
     - `scripts/lp_entry_shadow_calibration_report.py --from-file <new_log>`
   - Явно зафиксировать:
     - `errors_zero_pass`,
     - `telemetry_min_cycles_pass`,
     - `actionable_ratio_positive_pass`,
     - churn gates (`topn_churn_avg_pass`, `topn_churn_p95_pass`).

3. Decision logic (mandatory):
   - Если sustained окно проходит целевые критерии -> `KEEP` и закрытие Phase 2.7.7.
   - Если нет -> максимум 1 reversible tune iteration:
     - поменять только 1-2 config knobs,
     - собрать post-tune snapshot,
     - зафиксировать before/after и rollback/no-op path.

4. Fail-safe invariants (mandatory):
   - Нельзя ослаблять downgrade правила:
     - `TICK_DATA_DEGRADED`,
     - `SOURCE_CONFIDENCE_STALE/DIVERGED`,
     - `FRESHNESS_STALE`,
     - `RANGE_NOT_COMPUTED`,
     - `INVALID_OR_MISSING_RANGE`,
     - `INSUFFICIENT_STABILITY_HISTORY`.

## 4. Acceptance Criteria
- Есть sustained SHADOW evidence window (`>=24` cycles_with_entry_telemetry).
- `actionable_ratio_positive_pass=true` сохраняется.
- `errors_zero_pass=true`.
- Решение `KEEP/ADJUST/ROLLBACK` обосновано snapshot-данными.
- `ROADMAP` и memory-bank синхронизированы; статус Phase 2.7.7 обновлён корректно.

## 5. Verification Commands
```bash
cd /home/dmitrii/projects/defi_agents
.venv/bin/pytest -q tests/test_lp_entry_shadow_calibration.py tests/test_lp_entry_recommendation.py tests/test_scout.py
.venv/bin/pytest -q tests/test_notifier.py tests/test_tick_density_scanner.py
make test
PYTHONPATH=src .venv/bin/python scripts/lp_entry_shadow_calibration_report.py --from-file <NEW_POST_PLAN031_LOG>
git status --short --branch
```

## 6. Report Format (mandatory)
- Summary (3-6 bullets)
- Что реализовано
- Изменённые файлы
- Запущенные команды и результаты
- Риски/что не проверено
- Recommended commit message (без commit)

## 7. Constraints
- Работать только в `/home/dmitrii/projects/defi_agents`.
- Не выполнять commit/push.
- Не использовать destructive git-команды.
- Не менять внешнюю инфраструктуру/секреты/n8n/VPS.
