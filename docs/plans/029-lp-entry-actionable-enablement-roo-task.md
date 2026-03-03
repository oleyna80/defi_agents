# Roo Task 029 — LP Entry Actionable Enablement (Post-Calibration)

## 0. Objective
После закрытия evidence-gate Plan 028 (`all_pass=true`) перевести LP Entry из состояния
`all WATCHLIST` к устойчивому появлению `ACTIONABLE` кандидатов, не ослабляя fail-safe контракт.

Целевой результат:
- в SHADOW окне наблюдений есть ненулевой `actionable_ratio`,
- причина `WATCHLIST` детерминированно наблюдаема и управляемая,
- деградации данных остаются в `WATCHLIST` (fail-safe unchanged).

## 1. Scope
In scope:
- Добавить/усилить reason-level telemetry для `WATCHLIST` в LP Entry path.
- Добавить data-quality readiness checks для tick-density path (прежде всего зависимости Graph/Subgraph).
- Сформировать evidence отчёт `before/after` по actionable/watchlist причинам.
- Выполнить минимальные безопасные config-tune шаги (0-2 параметра) только при наличии data evidence.

Out of scope:
- LIVE execution / tx automation.
- Ослабление fail-safe downgrade (`degraded/stale/diverged/invalid-range -> WATCHLIST`).
- Изменение внешней инфраструктуры/секретов/серверов.

## 2. Required File Targets
- `main.py` (telemetry logging enrichments)
- `src/defi_agents/lp/entry_recommendation.py` (reason aggregation hooks, если нужно)
- `src/defi_agents/lp/shadow_calibration.py` (при необходимости reason-aware snapshot extension)
- `scripts/lp_entry_shadow_calibration_report.py` (опционально: reason-level output block)
- `tests/test_lp_entry_recommendation.py`
- `tests/test_lp_entry_shadow_calibration.py`
- `docs/reports/lp-entry-actionable-enablement-YYYY-MM-DD.md` (new)
- `ROADMAP.md`
- `docs/memory-bank/activeContext.md`
- `docs/memory-bank/progress.md`

## 3. Implementation Requirements
1. WATCHLIST reason telemetry (mandatory):
   - Логировать агрегат `watchlist_reason_counts` по циклу.
   - Reason-коды должны быть детерминированы (без free-text).
2. Data-quality readiness visibility:
   - Явно учитывать/логировать блокеры tick-density readiness
     (например, отсутствие `GRAPH_API_KEY`, provider init failures).
   - Блокеры должны попадать в evidence-отчёт как separate section.
3. Actionable enablement gate:
   - Добавить проверяемый критерий: `actionable_ratio > 0` в окне наблюдений.
   - Если критерий не выполнен, в отчёте обязателен top-3 watchlist reasons.
4. Controlled tune policy:
   - Разрешено менять максимум 1-2 параметра за итерацию.
   - Только после evidence на причинах и только обратимые изменения.

## 4. Acceptance Criteria
- В логах есть детерминированный `watchlist_reason_counts`.
- Evidence-отчёт содержит:
  - `before/after` snapshot,
  - `actionable_ratio`,
  - top watchlist reasons,
  - data-readiness blockers.
- Fail-safe инварианты не нарушены тестами.
- Полный `make test` зелёный.

## 5. Verification Commands
```bash
cd /home/dmitrii/projects/defi_agents
.venv/bin/pytest -q tests/test_lp_entry_recommendation.py tests/test_lp_entry_shadow_calibration.py tests/test_tick_density_scanner.py
.venv/bin/pytest -q tests/test_scout.py tests/test_notifier.py
make test
PYTHONPATH=src .venv/bin/python scripts/lp_entry_shadow_calibration_report.py --from-file docs/reports/artifacts/lp_entry_shadow_runtime_2026-03-03_window24.log
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
- Не менять внешнюю инфраструктуру/секреты/n8n.
