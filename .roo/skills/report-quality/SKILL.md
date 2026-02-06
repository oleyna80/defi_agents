---
name: report-quality
description: Изменения Telegram отчёта без шума и регрессий: Markdown, chunking, ссылки, сортировки, скрытие полей, тесты.
---

# Report Quality

## Instructions

Цель: улучшать Telegram отчёт (Decision View) без регрессий: не ломать форматирование, не превышать лимиты, не повышать шум.

### Rules
- Любое изменение отчёта должно иметь тест в `tests/test_notifier.py` (или аналогичном).
- Не выводи секреты в ошибках/логах.
- Сохраняй совместимость: старые поля остаются, новые добавляются осторожно.

### Checklist
1) Markdown safety
   - экранирование/безопасные вставки (символы, backticks)
2) Size limits
   - chunking <= лимита Telegram (проверить unit test на chunking)
3) Decision-grade fields first
   - `chain/pair/project/APY/TVL/risk` всегда видны
4) Noise control
   - показывай детали (например StrategySim) только если они дают пользу (например `SimStatus=OK`)
5) Links
   - pool link должен быть валидным и кликабельным

### Verification
- локально: `pytest -q tests/test_notifier.py`
- на VPS: один цикл + убедиться, что сообщение пришло и читаемо

### Output / DoD
- Отчёт читабелен, не шумит, тесты зелёные.
