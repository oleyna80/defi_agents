---
name: memory-bank-sync
description: Перед работой прочитай: docs/memory-bank/productContext.md, activeContext.md, progress.md.
Коротко суммируй: цель, текущий фокус, риски.
После изменения: обнови activeContext.md и progress.md (и systemPatterns.md только если новый паттерн).
---

# Memory Bank Sync

## Instructions

Цель: держать Memory Bank актуальным и согласованным, чтобы любой агент мог продолжить работу без потери контекста.

### Before Work (mandatory)
1) Прочитай (в этом порядке):  
   - `docs/memory-bank/productContext.md`  
   - `docs/memory-bank/activeContext.md`  
   - `docs/memory-bank/progress.md`
2) Сформируй краткое резюме (5–10 строк):  
   - что строим (1–2 предложения)  
   - текущий фокус / активная фаза  
   - главные риски/блокеры (до 3)  
   - следующий проверяемый шаг

### After Significant Work (mandatory)
Обновляй Memory Bank, если было сделано хотя бы одно из: новый функционал, изменение конфигов/политик, изменение пайплайна/вывода, новый runbook/spec/plan, важный bugfix, изменение deployment/ops.

1) Обнови `docs/memory-bank/activeContext.md`  
   - обнови `Current Spec / Current Plan / Active Task` (если изменилось)  
   - добавь 1–3 пункта в `Recent Changes` с датой и ссылками на файлы
2) Обнови `docs/memory-bank/progress.md`  
   - добавь 1 строку в соответствующий раздел (обычно в конце списка “Completed/Changelog”)  
   - не переписывай историю: добавляй, не ломай структуру
3) Обнови `docs/memory-bank/systemPatterns.md` только если появился новый паттерн/решение  
   - пример: “ввели новый слой/гейт”, “новая политика risk-first”, “единый исполнительный план”, “новый подход к источникам данных”

### Guardrails
- Не вставляй секреты, токены и содержимое `.env` в Memory Bank.
- Пиши коротко и предметно: 1 пункт = 1 событие, со ссылкой на файл.
- Если что-то неясно, фиксируй это в `Open Questions / Decisions` (в `activeContext.md`).

### Output / DoD
- Резюме текущего состояния (в сообщении пользователю).
- Memory Bank отражает фактический текущий фокус и последние изменения.
