---
name: config-edit-safe
description: Безопасная правка docs/memory-bank/scout_config.json без дублей ключей и сюрпризов. Валидация, проверка, что рантайм реально подхватил.
---

# Config Edit Safe

## Instructions

Цель: править `docs/memory-bank/scout_config.json` безопасно и проверяемо (без duplicate keys, без “почему в логах другое”).

### Rules
- Всегда валидируй JSON после правок.
- Не добавляй дубли ключей (в JSON это не ошибка синтаксиса, но приводит к неочевидному поведению).
- Меняй 1–2 параметра за итерацию, затем проверка 1 циклом на VPS.

### Workflow
1) Локальная правка
   - Правь только в секции `scout_settings` (если проект так устроен).
2) Валидация
   - `python3 -m json.tool docs/memory-bank/scout_config.json >/dev/null && echo OK`
3) Проверка “рантайм действительно увидел”
   - Запусти 1 цикл и проверь логи:
     - `journalctl --user -u defi-sentinel.service --since "30 minutes ago" --no-pager | grep -E "Final filters|Funnel metrics|Freshness summary|StrategySim summary"`
4) Если менялся threshold, подтверждай по лог-строке, что новое значение отображается.

### Common pitfalls (project-specific)
- `min_monthly_profit_usd` в логах может быть derived (например `effective_min_monthly_profit_usd`) и зависит от `gas_efficiency.position_size_usd` + relative floor.
- `min_warn_score` должен быть один раз, в правильной секции.

### Output / DoD
- JSON валиден, параметры на месте.
- Логи подтверждают, что значения подхвачены.
