# Roo Task 025 — Research Gate for LP Entry Recommendations

## 0. Objective
Подготовить research-пакет перед разработкой `LP Entry Recommendation Engine`, чтобы зафиксировать:
- какую модель выбора `network/pair/range` берем в v1,
- какие пороги и сигналы используем в ранжировании,
- какие риски/пробелы должны быть закрыты в коде.

## 1. Scope (research only)
In scope:
- Анализ текущих артефактов репозитория (roadmap/specs/plans/runbooks/tests/runtime hooks).
- Сверка текущих метаданных runtime с целевым `EntryRecommendation` контрактом.
- Сравнение стратегий range selection:
  - pit-based,
  - volatility-adjusted,
  - hybrid.
- Предложение scoring-политики для top-N рекомендаций.

Out of scope:
- Любые runtime-изменения в `main.py` / `src/defi_agents/**`.
- Commit/push.
- Изменение инфраструктуры/секретов.

## 2. Required Inputs
- `ROADMAP.md` (Phase 2.7 / 2.7.5 / 3.x)
- `docs/specs/lp-decision-engine-v1.md`
- `docs/specs/017-tick-density-scanner-v1.md`
- `docs/plans/017-tick-density-scanner-v1-plan.md`
- `main.py` tick-density integration block
- `src/defi_agents/lp/*` (models, scanner, pit_classifier, volatility)
- `src/defi_agents/notifier.py`

## 3. Deliverables
1. Research report:
   - `docs/research/2026-03-lp-entry-recommendation-research.md`
2. Proposed contract draft:
   - `EntryRecommendation` fields with обязательными/опциональными полями.
3. Policy proposal:
   - ranking formula v1,
   - confidence bands,
   - fail-safe downgrade rules.
4. Gap list to implement:
   - конкретный backlog задач для разработки (P0/P1).

## 4. Acceptance Criteria
- В отчете есть явный ответ на вопрос: “как именно выбираем сеть + пару + диапазон в v1”.
- Есть таблица соответствия: `current runtime fields` -> `required recommendation fields`.
- Есть минимум 2 альтернативы range policy и обоснованный выбор одной.
- Есть финальный implementation backlog с оценкой рисков.

## 5. Verification Commands
```bash
cd /home/dmitrii/projects/defi_agents
rg -n "tick_density|band_depth|pit|suggest_range|volatility|watchlist" main.py src docs tests
rg -n "LP Entry Recommendation|EntryRecommendation|network|pair|range" ROADMAP.md docs/plans docs/specs docs/research
```

## 6. Reporting Format
- Summary (3-6 пунктов)
- Что исследовано
- Предложенная модель (ranking + range + fail-safe)
- Gaps/risks
- Recommended next implementation task (без code changes)

