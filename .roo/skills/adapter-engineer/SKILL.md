---
name: adapter-engineer
description: Шаблон интеграции нового источника данных (DEX/Lending/Staking/Perps): интерфейс, таймауты, кеш, fail-safe UNVERIFIED, тесты, rollout.
---

# Adapter Engineer

## Instructions

Цель: добавлять новые источники данных через адаптеры безопасно (bounded calls, timeouts, cache, deterministic fail-safe), без поломки работающего pipeline.

### Rules
- Внешний вызов всегда bounded: timeout + max candidates + rate limit / throttling.
- Ошибки источника не ломают цикл: деградация в `UNVERIFIED` с явной метрикой/counter.
- Без silent fallback: логируй счётчики и провайдера, но без утечек URL/секретов.

### Adapter contract (minimum)
- `supports(candidate) -> bool`
- `fetch_snapshot(candidate) -> snapshot|None` (или batch вариант)
- Метаданные: `freshness_provider`, `source_timestamp`, divergence поля (если применимо)

### Implementation checklist
1) Конфиг-флаги
   - enabled flag, timeout, budget (max candidates), endpoints/ids map
2) Cache
   - per-cycle cache или TTL cache (где уместно), чтобы не дергать одно и то же
3) Safe HTTP
   - используем существующие паттерны клиента (таймаут, ретраи, без логирования секретов)
4) Tests
   - unit tests на enable/disable, mapping, fail-safe
   - integration test: pipeline не ломается при исключениях
5) Rollout
   - disabled by default -> включить на VPS -> 3+ цикла -> оценить counters

### Output / DoD
- Адаптер подключён, fail-safe поведение подтверждено тестами и логами.
