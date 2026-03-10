---
name: shadow-evidence-gate
description: Сбор и оценка SHADOW evidence window для gate-решений (PASS/FAIL/KEEP). Парсинг логов, счётчики, gate booleans, отчёт.
---

# Shadow Evidence Gate

## When to use
- Перед любым SHADOW → LIVE переходом (Gate-3, hedger gate, LP calibration gate).
- Когда нужно собрать evidence-snapshot из VPS логов.
- Когда нужно принять решение PASS/FAIL/KEEP на основе SHADOW window.

## When NOT to use
- Для unit-тестов (используй `pytest-gate`).
- Для config changes (используй `config-edit-safe`).
- До завершения SHADOW deployment.

## Goal
Формализовать сбор SHADOW evidence и gate-оценку в единый воспроизводимый процесс.

## Inputs
- Gate type: `execution-gate3`, `hedger-gate`, `lp-entry-calibration`, или custom.
- Observation window: минимум часов/циклов (default: 24h).
- Gate thresholds (из spec/plan или defaults).

## Workflow

### 1. Collect raw evidence
```bash
# Execution / Scout
journalctl --user -u defi-sentinel.service --since "24 hours ago" --no-pager | grep -cE "Execution summary|LP entry stability"

# Hedger
journalctl --user -u defi-hedger.service --since "24 hours ago" --no-pager | grep -cE "Hedger summary"

# Inspector
journalctl --user -u defi-inspector.service --since "24 hours ago" --no-pager | grep -cE "Inspector summary"
```

### 2. Parse counters
Из логов извлеки стандартные поля:
- `cycles_total` — количество циклов в окне
- `errors_total` — суммарные ошибки
- `sim_ok` / `sim_fail` — результаты симуляций (если применимо)
- Domain-specific counters (actionable_ratio, churn, etc.)

### 3. Evaluate gate booleans
Стандартный gate-контракт:
- `min_cycles_pass`: `cycles_total >= threshold` (default 24)
- `errors_zero_pass`: `errors_total == 0`
- `sim_fail_zero_pass`: `sim_fail == 0` (если применимо)
- Domain-specific gates (из spec/plan)

### 4. Decision
| Условие | Решение |
|---|---|
| Все gate pass | `PASS` — можно переходить к следующей фазе |
| min_cycles_pass = false | `FAIL (insufficient evidence)` — продолжить SHADOW |
| errors > 0 | `FAIL (runtime errors)` — исследовать с `scout-funnel-debug` |
| Gate pass, но нет retune необходимости | `KEEP` — сохранить текущие параметры |

### 5. Output report
Сохрани JSON-snapshot в `docs/reports/artifacts/`:
```json
{
  "gate_type": "...",
  "window_hours": 24,
  "cycles_total": 88,
  "errors_total": 0,
  "min_cycles_pass": true,
  "errors_zero_pass": true,
  "domain_gates": {},
  "decision": "PASS|FAIL|KEEP",
  "timestamp": "2026-03-06T10:00:00Z"
}
```

## Guardrails
- Не фальсифицировать evidence (используй реальные логи).
- Не менять gate thresholds post-factum, чтобы "дотянуть" до PASS.
- При FAIL — не переходить к LIVE. Сначала устрани root-cause.

## Output / DoD
- JSON-snapshot сохранён в `docs/reports/artifacts/`.
- Gate-решение обосновано и воспроизводимо.
- Memory Bank обновлён (если gate = PASS).
