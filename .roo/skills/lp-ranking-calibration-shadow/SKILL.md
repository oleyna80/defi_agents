---
name: lp-ranking-calibration-shadow
description: Калибровка ranking/confidence порогов для LP Entry Recommendation на SHADOW evidence: метрики, пороги, безопасная корректировка без runtime drift.
---

# LP Ranking Calibration Shadow

## When to use
- После P0 реализации Plan 026, когда нужно откалибровать `rank_v1` и confidence cutoffs.
- Когда есть SHADOW-логи/отчёты и нужно скорректировать пороги без изменения архитектуры.

## When NOT to use
- До завершения P0 wiring (`pit -> range -> EntryRecommendation`).
- Для задач инфраструктуры, деплоя или LIVE-исполнения.

## Goal
Сделать безопасную калибровку параметров ранжирования по evidence:
- повысить качество actionable рекомендаций,
- контролировать долю watchlist,
- избежать false-actionable при degraded данных.

## Inputs required
- `docs/research/2026-03-lp-entry-recommendation-research.md`
- Логи SHADOW/отчёты с counters и recommendation output.
- Текущие пороги/мультипликаторы в runtime/config.

## Core metrics
- `actionable_count / total_recommendations`
- `watchlist_count / total_recommendations`
- доля downgrade по причинам (`tick_data_quality`, `stale/diverged`, invalid range)
- стабильность top-N (перестановки без смены рыночного режима)

## Workflow
1. Baseline snapshot
   - Зафиксируй метрики по окну наблюдения (например 24-48ч).
2. Diagnose drift
   - Найди top-3 причины перевода в WATCHLIST и top-3 причины нестабильности rank.
3. Propose minimal retune
   - Корректируй только 1-2 параметра за итерацию.
   - Не трогай fail-safe правила.
4. Re-run and compare
   - Повторно посчитай те же метрики и сравни с baseline.
5. Decision
   - `KEEP / ADJUST / ROLLBACK` с коротким обоснованием.

## Guardrails
- Никакого ослабления `degraded => WATCHLIST`.
- Не менять одновременно много весов/порогов.
- Любая калибровка должна быть обратимой (чёткий rollback параметров).

## Output format
- Baseline метрики
- Изменённые параметры
- Метрики после изменения
- Вердикт и риски

