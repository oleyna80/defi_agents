---
name: lp-entry-test-gate
description: Тестовый gate для Plan 026: фиксированная матрица pytest/make test, проверка fail-safe условий и формат отчёта результатов.
---

# LP Entry Test Gate

## When to use
- После любых изменений по Plan 026.
- Перед техлид-ревью и перед подготовкой commit message.

## Goal
Подтвердить, что P0 реализация `LP Entry Recommendation` не сломала runtime и соблюдает fail-safe контракт.

## Test matrix (mandatory)
1. `pytest -q tests/test_tick_density_scanner.py tests/test_tick_density_phase_ab.py tests/test_notifier.py`
2. `pytest -q tests/test_scout.py tests/test_volatility.py`
3. `make test`
4. `git status --short --branch`

## Additional checks (recommended)
- Поиск ключевых полей/хуков после изменений:
  - `rg -n "suggested_range_lower_tick|suggested_range_upper_tick|LP Entry Recommendations|rank_v1|watchlist_reason" main.py src tests`
- Проверка отсутствия scope drift:
  - `git diff -- main.py src/defi_agents/lp src/defi_agents/notifier.py tests`

## Fail-safe assertions
- Кандидат с `tick_data_quality != OK` не должен быть actionable.
- Missing/invalid range должен приводить к WATCHLIST.
- stale/diverged confidence должен приводить к WATCHLIST.
- Новый report block не должен ломать существующий формат и chunking.

## Failure handling
1. Остановись на первом красном тесте.
2. Зафиксируй root-cause (файл/функция/ветка логики).
3. Внеси минимальный фикс без расширения scope.
4. Перезапусти весь mandatory matrix.

## Reporting format
- Summary (3-6 bullets)
- Что реализовано
- Изменённые файлы
- Запущенные команды и результаты
- Риски/что не проверено
- Recommended commit message (без commit)

## Guardrails
- Не скипать `make test` после зелёных таргетных тестов.
- Не менять тесты только чтобы “сделать зелёным” без исправления логики.
- Не добавлять нестабильные/временные ассерты по случайным значениям.

