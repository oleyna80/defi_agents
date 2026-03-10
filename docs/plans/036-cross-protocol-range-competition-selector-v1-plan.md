# Plan 036 — Cross-Protocol Range Competition Selector v1

## 0. Status
- Status: SYNCED_WITH_IMPLEMENTATION (2026-03-08)
- Priority: CRITICAL (NEXT)
- Owner: Tech Lead
- Depends on:
  - `docs/specs/lp-decision-engine-v1.md`
  - `docs/specs/017-tick-density-scanner-v1.md`
  - `docs/plans/033-lp-entry-eth-usdt-target-scope-roo-task.md`

## 1. Problem Statement
Сейчас LP Entry уже умеет давать рекомендации в SHADOW, но продуктовая цель оператора шире: по заданным `pair + range` выбирать не просто пул, а лучший `network + protocol` среди нескольких CLMM venue.

Критичный gap: отсутствует единый decision-layer для сравнения конкуренции ликвидности внутри целевого диапазона между протоколами и сетями.

## 2. Goal
Сделать decision-grade селектор, который:
- принимает вход `pair + range` (симметричный/асимметричный, с `AUTO` по режиму рынка),
- сравнивает `network x protocol` по конкуренции в диапазоне,
- возвращает Top-N с объяснимым ранжированием и fail-safe причинами деградации.

## 3. Scope
In scope:
- Входной контракт:
  - `target_pair` (например, `ETH/USDT`),
  - `range_mode=SYMMETRIC|ASYMMETRIC|AUTO`,
  - `market_regime=SIDEWAYS|UPTREND|DOWNTREND`,
  - optional manual `range_lower/range_upper`,
  - allowlist `chains/projects`.
- Cross-protocol сравнение в поддерживаемых CLMM:
  - `uniswap-v3`,
  - `aerodrome-slipstream`,
  - `sushiswap-v3`,
  - аналогичные venue по сети (через config allowlist).
- Детерминированный score:
  - in-range liquidity competition,
  - volume/fee proxy,
  - gas/cost sanity,
  - confidence/freshness gates.
- Отдельный operator block в отчёте: сравнение `network/protocol/range` + причины выбора.

Out of scope:
- LIVE execution / auto-trading.
- Добавление новых внешних провайдеров без отдельного research gate.
- Ослабление fail-safe политик.

## 4. Mandatory Stage Order
1. Design lock: фикс входного контракта и формулы score v1.
2. Runtime wiring: selector + telemetry + report block.
3. Tests: ranking math, tie-break determinism, fail-safe degradation.
4. SHADOW evidence: минимум 24 цикла на целевой паре.

## 5. DoD
- Для `ETH/USDT` формируется Top-N cross-network/cross-protocol recommendations.
- Для каждой рекомендации есть объяснимые machine-readable поля:
  - `network`, `protocol`, `pair`, `range`,
  - `competition metrics`,
  - `rank_v1`, `confidence`, `reason_codes`.
- Degraded/stale/diverged/invalid-range не попадают в actionable.
- Тесты на математику score/ranking и fail-safe contract проходят стабильно.

## 6. Implementation Sync (2026-03-08)
- Config selector v1 расширен: `target_pair`, `range_mode`, `market_regime`, optional manual `range_lower/range_upper`, allowlists `allowed_chains/allowed_projects`, `top_n`.
- Добавлен отдельный cross-protocol ranking модуль `rank_v1` + components:
  - `in_range_liquidity_competition`
  - `volume_fee_proxy`
  - `cost_penalty`
  - `confidence`
- Runtime wiring добавляет selector telemetry counters (`input/matched/actionable/watchlist`) и учитывает selector range settings при построении LP Entry Top-N.
- Reporting расширен отдельным блоком сравнения `network/protocol/range` (без удаления текущего LP Entry блока).
- Fail-safe контракт сохранён: degraded/stale/diverged/invalid-range остаются `WATCHLIST`, без false-actionable.
- Plan 036 gap closeout (repo-local):
  - eligibility: `sushiswap-v3` больше не классифицируется как `UNSUPPORTED_ENTRY_VENUE` в LP entry pre-filter;
  - runtime/provider routing: для `sushiswap-v3` добавлен совместимый safe-path через UniV3-compatible tick provider (по chain), а при отсутствии provider выполняется явная fail-safe деградация с machine-readable blocker code `SUSHISWAP_V3_PROVIDER_UNAVAILABLE` (без false-actionable);
  - tests/docs sync: обновлены targeted тесты (`lp_entry_recommendation`, `tick_density_scanner`, `scout`) и пример target scope allowlist с `sushiswap-v3` в memory-bank config.
