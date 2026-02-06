---
name: freshness-rollout
description: Безопасное включение freshness re-check (telemetry → enforce). Проверки, rollback, что считать baseline.
---

# Freshness Rollout

## Instructions

Цель: включить freshness/re-check так, чтобы не сломать pipeline и не ухудшить качество сигналов из-за ложных stale/divergence.

### Rules
- Режимы включаем поэтапно: telemetry -> recheck -> enforce.
- Любой провайдер/адаптер, который падает/таймаутит, обязан деградировать в `UNVERIFIED` (fail-safe).
- Никаких “тихих” фоллбеков: состояние должно быть видно в counters/logs.

### Rollout sequence
1) Telemetry-only
   - `recheck_enabled=true`
   - `enforce_freshness_for_actionable=false`
   - Наблюдать 5+ циклов
2) Calibrate
   - Сравнить долю `UNVERIFIED/STALE/DIVERGED` по сетям/протоколам
   - Подкрутить: `max_age_minutes`, `max_apy_divergence_pct`, `max_tvl_divergence_pct`, `recheck_timeout_seconds`, `recheck_max_candidates`
3) Enforce
   - `enforce_freshness_for_actionable=true`
   - Наблюдать 3+ цикла и сравнить actionable baseline

### Verification (VPS)
- `journalctl --user -u defi-sentinel.service --since "2 hours ago" --no-pager | grep -E "Freshness summary|Reported|Final filters"`
- Убедиться, что `Freshness summary` показывает ожидаемые counters и не растут ошибки/таймауты.

### Rollback
- Вернуть `enforce_freshness_for_actionable=false`
- При необходимости: `recheck_enabled=false` (только если провайдер нестабилен)

### Output / DoD
- Baseline до/после: доля UNVERIFIED/STALE/DIVERGED и actionable volume.
- Рекомендация: какие пороги оставить и какие источники “шумят”.
