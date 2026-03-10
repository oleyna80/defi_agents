---
name: pytest-gate
description: Универсальный тестовый gate для Python/pytest. Запусти targeted + full suite, проверь fail-safe контракт, выдай GO/NO-GO.
---

# Pytest Gate

## When to use
- После любых изменений кода перед commit/review.
- Как финальная проверка перед закрытием плана/фазы.
- Когда техлид просит верифицировать изменения.

## When NOT to use
- Для read-only research/analysis.
- Для изменений только в docs/config (но если config влияет на runtime — используй).

## Goal
Подтвердить, что изменения не сломали runtime и соблюдают fail-safe контракт проекта.

## Test matrix (mandatory)

### Step 1: Targeted tests
Запусти тесты, связанные с изменёнными модулями:
```bash
# Определи изменённые файлы
git diff --name-only HEAD | grep -E '\.py$'

# Найди связанные тесты
# Пример: src/defi_agents/lp/ → tests/test_tick_density_*.py, tests/test_lp_*.py
pytest -q <targeted_test_files>
```

### Step 2: Full suite
```bash
make test
```
Если `make test` недоступен:
```bash
python -m pytest tests/ -q --tb=short
```

### Step 3: Scope check
```bash
git diff --stat
git status --short --branch
```

## Fail-safe assertions (project-specific)
- Degraded data → WATCHLIST (никогда не ACTIONABLE).
- Missing/invalid inputs → explicit reason codes (не silent fallback).
- Exceptions не проглатываются (fail-fast / re-raise after telemetry).

## Failure handling
1. Остановись на первом красном тесте.
2. Зафиксируй root-cause: файл, функция, assertion.
3. Минимальный fix без расширения scope.
4. Перезапусти ВЕСЬ mandatory matrix (не только упавший тест).

## Reporting format
```
## Test Gate Report
- **Targeted tests:** X passed / Y failed
- **Full suite:** X passed / Y failed
- **Changed files:** [list]
- **Verdict:** GO / NO-GO
- **Issues (if any):** [description]
- **Recommended commit message:** (без commit)
```

## Guardrails
- Не скипать `make test` после зелёных targeted тестов.
- Не менять тесты только чтобы "сделать зелёным" без исправления логики.
- Не коммитить с красными тестами.
