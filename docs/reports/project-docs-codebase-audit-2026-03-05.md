# Project Docs & Codebase Audit — 2026-03-05

## 1) Scope и методика

Аудит выполнен по документации, коду и тестам репозитория `defi_agents` (repo-local, без infra/secrets/LIVE изменений).

Покрытые источники:
- Memory Bank: `productContext / activeContext / progress`.
- Дорожная карта: `ROADMAP.md`.
- LP Entry план-трек: `024 → 033`.
- Runtime path: `main.py`, LP/scout/strategy_sim/notifier модули.
- Тесты: `tests/test_lp_entry_recommendation.py`, `tests/test_tick_density_scanner.py`, `tests/test_strategy_sim.py`, `tests/test_scout.py`, `tests/test_notifier.py`, `tests/test_lp_entry_shadow_calibration.py`.

---

## 2) Executive Summary

### 2.1 Соответствие кода целям проекта

**Вердикт: ЧАСТИЧНО СООТВЕТСТВУЕТ (сильное соответствие по LP Entry v1, неполное по end-to-end execution vision).**

Что хорошо совпадает с целью (выбор `network/protocol/pair/range`):
- Реализован детерминированный LP Entry recommendation path (Top-N, rank/confidence, reason taxonomy).
- Реализован fail-safe контракт (degraded/stale/diverged/invalid-range не становятся actionable).
- Реализован target scope для `ETH/USDT` (включая `WETH-USDT` нормализацию).
- Реализована телеметрия стабильности/деградаций/причин WATCHLIST и shadow-calibration tooling.

Что пока ограничивает полное соответствие продуктовой цели:
- Общая продуктовая цель подразумевает дальнейший переход в execution-слой (Phase 3.x+), а он ещё не закрыт по DoD.
- В `strategy_sim` часть required-data checks формально описана, но фактически stub-реализация (`_has_fees/_has_utilization/... -> False`) ограничивает decision-grade полноту по стратегиям вне текущего LP fail-safe контура.
- Freshness Phase D (Morpho + калибровка порогов) в roadmap остаётся незавершённой.

### 2.2 Статус фаз (done / in-progress / not-started)

| Фаза | Статус | Комментарий |
|---|---|---|
| Phase 1: Core Stabilization | **Done** | Отмечена завершённой в roadmap; базовый fail-fast/ops фундамент есть. |
| Phase 2: Pipeline Relaxation | **In Progress** | Большая часть закрыта, но freshness re-check v1 (Phase D) ещё открыт. |
| Phase 2.5: Investor Profiles | **Done** | Закрыта по roadmap/progress. |
| Phase 2.6: My Pools Monitor | **Done** | Закрыта, есть мониторинг/алерты и тесты. |
| Phase 2.7: Tick Density Scanner | **In Progress** | P0 ядро сделано, но master-phase ещё не полностью закрыта по всем подпунктам. |
| Phase 2.7.5: LP Entry Recommendation v1 | **Done** | Реализация + fail-safe + report block + тесты. |
| Phase 2.7.6: Stability + Calibration | **Done** | Закрыта на shadow evidence window, decision KEEP. |
| Phase 2.7.7: Actionable Enablement | **Done** | Закрыта после Plan 031/032, non-zero actionable и sustained evidence. |
| Phase 2.7.8: ETH/USDT Target Selector | **Done** | Target scope + counters + validation/test coverage выполнены. |
| Phase 2.8: Protocol Inspector | **In Progress** | Базовый сервис есть, rollout-gate часть остаётся открытой. |
| Phase 3.x (Execution pipeline), 4, 5 | **Not Started / Partially Prepared** | Есть задел/частичные реализации, но roadmap DoD этих фаз не закрыт. |

### 2.3 Готовность данных для выбора `network/pair/range` (max-yield LP entry)

**Отдельный вывод: ЧАСТИЧНО ГОТОВО.**

Почему «частично», а не «да»:
1. **Pair/Network selector** в SHADOW реализован и детерминирован (target scope фильтр, telemetry counters, reason codes).
2. **Range selector** реализован (pit + vol-aware path, suggested range ticks, fail-safe downgrade).
3. Но остаются **операционные data-readiness риски** (subgraph/schema/key blockers), которые периодически переводят поток в WATCHLIST.
4. По части strategy-sim required data виден технический долг (stub checks), что снижает полноту decision-layer для долгосрочной product цели.

Итог: для SHADOW-оператора система уже полезна для отбора кандидатов `network/pair/range`, но для устойчивого «max-yield decision-grade» ещё нужен закрывающий hardening.

---

## 3) Ключевые подтверждённые сильные стороны

1. **Детерминированный LP Entry контракт**
   - Явная модель `EntryRecommendation` с actionable/watchlist семантикой.
   - Нормализованный reason taxonomy вместо free-text.

2. **Fail-safe invariants соблюдены**
   - Degraded/stale/diverged/invalid-range не поднимаются в actionable.
   - Ineligible и missing-range path покрыты machine-readable кодами.

3. **Telemetry-first подход**
   - Cycle-level counters + watchlist reason aggregation + churn метрики.
   - Отдельный shadow calibration parser/report для gate-проверок.

4. **Тестовое покрытие по критичным инвариантам**
   - Есть регрессии на ранжирование, target-scope matching, stability gate, notifier section, parser/gates.

---

## 4) Наблюдаемые ограничения и технический долг

1. **Freshness track не полностью закрыт**
   - В roadmap остаётся открытый хвост Phase D (Morpho + threshold calibration).

2. **StrategySim data-completeness checks частично заглушены**
   - `_has_fees`, `_has_utilization`, `_has_supply_rate`, `_has_protocol_yield`, `_has_staking_rate`, `_has_price_range`, `_has_volatility_proxy` возвращают `False` (stub behavior), что ограничивает качество required-data оценки.

3. **Data-source availability остаётся чувствительной точкой**
   - Зафиксированы blockers класса `GRAPH_API_KEY_MISSING`, `SUBGRAPH_SCHEMA_UNSUPPORTED` и provider init/schema ошибки; система деградирует корректно, но это режет долю actionable.

4. **Execution vision (Phase 3.x+) не доведён до продуктового DoD**
   - Для полной цели «не только совет, но и управление позицией» блокеры ещё есть (в т.ч. Gate-3 evidence criteria в roadmap).

---

## 5) Практичные улучшения (P0 / P1 / P2)

## P0 (критично, ближайший приоритет)

1. **Закрыть runtime data-readiness blockers до стабильного actionable baseline**
   - Цель: снизить долю WATCHLIST из-за source-готовности, зафиксировать стабильный actionable_ratio на новом окне (`>=24` cycles).
   - Результат: более надёжный выбор `network/pair/range` в SHADOW.

2. **Довести StrategySim required-data проверки от stub к фактической валидации**
   - Минимум для полей, уже присутствующих в metadata/кандидатах (`fees`, `utilization/proxy`, `volatility proxy`, `price range proxy` где доступно).
   - Результат: более корректный status/metadata в decision-layer.

3. **Зафиксировать decision-grade критерий готовности данных для LP Entry в runbook-формате**
   - Явный gate-чеклист: какие counters/thresholds обязательны для «готово к операторскому выбору».

## P1 (важно, после P0)

1. **Расширить устойчивость cross-network/cross-venue сравнения**
   - Укрепить покрытие по поддерживаемым DEX/сетям и качество fallback-path.

2. **Довести freshness Phase D до закрытия по roadmap**
   - Снять открытый фазовый хвост, связанный с divergence calibration.

3. **Добавить сводный quality index для LP Entry recommendation**
   - Композитный индикатор на базе freshness/tick-quality/stability/target-match.

## P2 (дальнейшее развитие)

1. **Увязка LP Entry advisory с execution readiness (Phase 3.x bridge)**
   - Явный handoff-контракт между recommendation и execution phase gates.

2. **Operator UX/observability polish**
   - Более наглядный digest по причинам downgrade и сравнению кандидатов внутри target-scope.

---

## 6) Итоговый ответ на целевой вопрос

**Можно ли сейчас выбирать `network/pair/range` для max-yield LP entry на основе имеющихся данных?**

**Ответ: ЧАСТИЧНО.**

Система уже даёт структурированный и детерминированный SHADOW-level выбор с явными причинами и fail-safe защитой, но устойчивость decision-grade качества всё ещё зависит от закрытия data-readiness и strategy-sim completeness долгов (P0).

---

## 7) Addendum (2026-03-05)

- Подтверждён внедрённый фикс Telegram-шумов через конфиг-флаг `reporting.telegram_opportunity_sections_enabled=false` в `docs/memory-bank/scout_config.json`.
- Влияние на выводы аудита: риск операторского шума/перегрузки от объёмных opportunity-секций снижен (из активного эксплуатационного риска в контролируемый конфигурационный риск).
- При этом базовые выводы по data-readiness не изменяются: часть LP Entry потока по-прежнему уходит в WATCHLIST из-за source-готовности и strategy-sim completeness долгов.
- Drift-check для runbook/runtime contract выполнен в минимальном режиме; противоречий по log-signatures/ожиданиям не выявлено, правки `docs/runbooks/*` не требуются.
