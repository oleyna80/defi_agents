# Plan 024 — LP Entry Recommendation Engine v1

## 0. Status
- Status: DRAFT
- Priority: CRITICAL (NEXT)
- Owner: Tech Lead
- Depends on: `docs/specs/lp-decision-engine-v1.md`, `docs/specs/017-tick-density-scanner-v1.md`

## 1. Problem Statement
Текущий runtime уже умеет считать `band_depth_*` и деградировать сигнал при проблемах данных, но не выдает конечный артефакт для оператора в формате:
- куда заходить (`network + protocol + pair`),
- в каком диапазоне (`range lower/upper`),
- с какой уверенностью и почему.

Из-за этого пайплайн остается аналитическим, а не decision-grade.

## 2. Goal
Сделать decision-layer `LP Entry Recommendations` для ручного исполнения:
- Top-N рекомендаций на цикл;
- детерминированные правила ранжирования и fail-safe деградации;
- явный вывод `range` и причин (`reason_codes`).

## 3. Scope
In scope:
- Контракт рекомендаций `EntryRecommendation` (данные + confidence + reason codes).
- Ранжирование кандидатов с учетом `band_depth`, `tick quality`, `freshness`, `strategy_sim`.
- Генерация диапазона (`suggested_range_lower/upper_tick`) в runtime-path.
- Отдельный report block для оператора.

Out of scope:
- Авто-исполнение транзакций.
- Новые внешние источники данных без research sign-off.
- Расширение beyond v1 сетей (`Base/Arbitrum`) и базовых DEX (`Uniswap v3/Aerodrome`).

## 4. Mandatory Stage Order
1. Research gate (обязателен, без runtime-кода).
2. Design sign-off (фиксируем scoring/range policy).
3. Development + tests.
4. Shadow observation и калибровка.

## 5. Deliverables
- Формализованный `EntryRecommendation` контракт (поля + policy).
- Реализация ранжирования и range selection в runtime.
- Telegram/reporting блок `LP Entry Recommendations`.
- Набор тестов:
  - ranking determinism,
  - range validity,
  - degraded->watchlist fail-safe.

## 6. DoD
- В каждом цикле при наличии валидных данных формируется блок `LP Entry Recommendations`.
- Каждая рекомендация содержит `network/protocol/pair/range/confidence/reasons`.
- При `DEGRADED` данных рекомендация не становится actionable.
- Тесты на новую логику зеленые.

