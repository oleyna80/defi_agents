# Roo Task 031 — LP Entry Actionable Enablement via StrategySim Decoupling

## 0. Objective
Закрыть остаточный root-cause фазы 2.7.7 (`actionable_ratio=0`) без ослабления fail-safe:
- post-Plan030 SHADOW telemetry подтверждает, что LP pipeline живой (`entry_lp_eligible_total > 0`, `entry_range_ready_total > 0`);
- при этом `entry_actionable=0` сохраняется из-за доминирования `REPORT_GROUP_WATCHLIST` в LP-eligible subset;
- в том же окне `StrategySim summary` показывает `ok=0` и массовые `partial/unsupported` downgrade.

Целевой результат:
- LP Entry actionability больше не блокируется структурно из-за ограничений текущего StrategySim v1;
- решение остаётся fail-safe (`degraded/stale/diverged/invalid-range` не становятся actionable);
- на SHADOW evidence появляется воспроизводимый `actionable_ratio > 0` (или прозрачно подтверждён reversible tune fallback).

## 1. Scope
In scope:
- Устранить coupling, при котором `strategy_sim` downgrade без LP-специфичной причины превращает LP-eligible/range-ready кандидаты в generic `REPORT_GROUP_WATCHLIST`.
- Ввести детерминированные machine-code причины для StrategySim downgrade path.
- Сохранить отдельный операторский `Decision View` контракт и не ломать текущий `SAFE/WARN` отчёт.
- Добавить/обновить тесты и evidence-артефакты для post-fix SHADOW.

Out of scope:
- LIVE execution/tx.
- Ослабление risk/freshness/tick/range fail-safe правил.
- Изменение внешней инфраструктуры, secrets, n8n, VPS.

## 2. Required File Targets
- `main.py`
- `src/defi_agents/strategy_sim/engine.py`
- `src/defi_agents/lp/entry_recommendation.py`
- `src/defi_agents/lp/shadow_calibration.py` (если требуется расширить агрегаты)
- `tests/test_lp_entry_recommendation.py`
- `tests/test_scout.py`
- `tests/test_lp_entry_shadow_calibration.py` (если меняется telemetry contract)
- `docs/reports/lp-entry-actionable-enablement-2026-03-04.md` (sync/update)
- `ROADMAP.md`
- `docs/memory-bank/activeContext.md`
- `docs/memory-bank/progress.md`

## 3. Implementation Requirements
1. Root-cause fix (mandatory):
   - Развязать LP Entry actionability от generic `report_group` downgrade, вызванного ограничениями `StrategySim` (`sim_status=PARTIAL/UNSUPPORTED`) при сохранении всех LP fail-safe gates.
   - Развязка должна быть явной и тестируемой (например, seed metadata до StrategySim policy и использование seed path в LP Entry builder).

2. Deterministic StrategySim reasons (mandatory):
   - Любой downgrade в `strategy_sim.apply_policy(...)` должен выставлять machine-code reason (без free-text), например:
     - `SIM_STATUS_PARTIAL`,
     - `SIM_STATUS_UNSUPPORTED`,
     - `SIM_RISK_ABOVE_PROFILE`.
   - Исключить немой fallback в `REPORT_GROUP_WATCHLIST` на этом пути.

3. LP fail-safe invariants (mandatory):
   - Обязательно сохранить downgrade в WATCHLIST для:
     - `TICK_DATA_DEGRADED`,
     - `SOURCE_CONFIDENCE_STALE/DIVERGED`,
     - `FRESHNESS_STALE`,
     - `RANGE_NOT_COMPUTED`,
     - `INVALID_OR_MISSING_RANGE`,
     - `INSUFFICIENT_STABILITY_HISTORY`.

4. Evidence gate for closure:
   - Сформировать новый post-fix SHADOW snapshot через:
     - `scripts/lp_entry_shadow_calibration_report.py --from-file ...`
   - Проверить:
     - `actionable_ratio_positive_pass=true` (в наблюдаемом окне),
     - top reasons остаются детерминированными,
     - `errors_zero_pass=true`.

## 4. Acceptance Criteria
- В LP telemetry исчезает структурная доминация generic `REPORT_GROUP_WATCHLIST` для LP-eligible/range-ready path.
- Для StrategySim downgrade path видны явные machine-code причины.
- На post-fix SHADOW evidence зафиксирован ненулевой `actionable_ratio` без нарушения fail-safe.
- Регрессионные тесты и `make test` зелёные.

## 5. Verification Commands
```bash
cd /home/dmitrii/projects/defi_agents
.venv/bin/pytest -q tests/test_lp_entry_recommendation.py tests/test_scout.py tests/test_tick_density_scanner.py
.venv/bin/pytest -q tests/test_lp_entry_shadow_calibration.py tests/test_notifier.py
make test
PYTHONPATH=src .venv/bin/python scripts/lp_entry_shadow_calibration_report.py --from-file docs/reports/artifacts/lp_entry_shadow_runtime_2026-03-04_post_plan030_mockai.log
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
