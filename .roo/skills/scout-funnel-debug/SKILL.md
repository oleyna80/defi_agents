---
name: scout-funnel-debug
description: Быстрое расследование “почему 0 кандидатов” (воронка Scout). Что смотреть в логах, какие knobs трогать безопасно, как откатить.
---

# Scout Funnel Debug

## Instructions

Цель: быстро понять, на каком этапе воронки Scout “обнуляется” поток кандидатов и как это исправить минимальным изменением (без ослабления security gates).

### Rules
- Не проси показывать содержимое `.env` и не печатай секреты.
- Любые изменения конфигов/кода: маленький diff, затем проверка (pytest / 1 цикл на VPS).
- Не “лечи” 0 кандидатов снятием risk gates; сначала локализуй узкое место.

### Workflow (read-only first)
1) Собери базовые метрики из логов (VPS):
   - `journalctl --user -u defi-sentinel.service --since "2 hours ago" --no-pager | grep -E "Funnel metrics|Final filters|Reported|Freshness summary|StrategySim summary"`
2) Определи, где “падает” поток:
   - `missing_address` / `missing_chain_id` высокие -> маппинг сетей/адресов
   - `security_counts` показывает `block/unknown` -> проблемы security stage / rate limits / mapping
   - `eligible=0` при нормальном `results` -> слишком высокие пороги (profit/score) или cost/capacity фильтры
   - `deduped` слишком высокий -> dedupe TTL слишком агрессивный / нужен clear cache
   - `freshness` переводит в watchlist -> recheck/strict thresholds
3) Выпиши 1–3 наиболее частые причины (top_reasons) и предложи минимальный фикс.

### Safe knobs (конфиг)
Трогай по одному параметру за раз, затем 1–2 цикла:
- `exploration_slots`, `exploration_min_apy`, `max_audit_candidates`
- `dedupe_ttl_seconds` (и разовый clear dedupe cache после крупных изменений)
- `min_warn_score` (не трогать `safe_min_score` без явного согласования)
- `gas_efficiency.position_size_usd` (влияет на `effective_min_monthly_profit_usd`)
- `freshness.enforce_freshness_for_actionable` (строгость включать только после телеметрии)

### Output / DoD
- Короткий вывод: “воронка падает на стадии X по причине Y”.
- Конкретный минимальный change set (1–2 knob’а) + как проверить (команды логов).
