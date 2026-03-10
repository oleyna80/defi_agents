# Roo Task 033 — LP Entry ETH/USDT Target Scope (Cross-Network + Multi-Protocol, SHADOW)

## 0. Objective
Добавить в LP Entry runtime целевой режим поиска лучшего диапазона для пары `ETH/USDT`
по нескольким сетям и поддерживаемым протоколам в SHADOW-режиме.

Целевой результат:
- оператор может включить `target scope` и получить Top-N рекомендаций только для `ETH/USDT`;
- сравнение выполняется между сетями и поддерживаемыми venue;
- fail-safe контракт LP Entry не ослабляется.

## 1. Scope
In scope:
- Config-driven target scope для LP Entry:
  - целевая пара (`ETH/USDT`, с нормализацией к onchain-symbol, включая `WETH-USDT`);
  - allowlist сетей;
  - allowlist venue/protocol (текущий v1: `uniswap-v3`, `aerodrome-slipstream`);
  - опциональный `top_n` для target output.
- Фильтрация входа в `build_entry_recommendations(...)` по target scope.
- Детерминированная telemetry по target scope в cycle logs.
- Тесты на фильтрацию, нормализацию пары, пустой target-result и сохранение fail-safe.
- Синхронизация docs/memory-bank по факту.

Out of scope:
- LIVE execution / tx automation.
- Добавление новых DEX adapters (Pancake/HyperSwap и т.п.).
- Изменения внешней инфраструктуры, secrets, n8n, VPS.
- Ослабление downgrade правил (`degraded/stale/diverged/invalid-range`).

## 2. Required File Targets
- `src/defi_agents/scout/config.py`
- `docs/memory-bank/scout_config.json`
- `main.py`
- `src/defi_agents/lp/entry_recommendation.py`
- `tests/test_lp_entry_recommendation.py`
- `tests/test_scout.py`
- `tests/test_notifier.py` (если затронут report block)
- `ROADMAP.md`
- `docs/memory-bank/activeContext.md`
- `docs/memory-bank/progress.md`
- `docs/memory-bank/systemPatterns.md` (only if introduced new pattern/contract)

## 3. Implementation Requirements
1. Target scope config (mandatory):
   - Ввести конфиг-блок для LP Entry targeting (например `lp_entry_targeting.*`) с полями:
     - `enabled: bool`
     - `target_pair: str` (default empty/disabled)
     - `allowed_chains: list[str]`
     - `allowed_projects: list[str]`
     - `top_n: int` (optional override)
   - Валидации должны быть fail-fast на уровне schema.

2. Pair normalization (mandatory):
   - Реализовать детерминированную нормализацию пары для матчей (`ETH/USDT` <-> `WETH-USDT`).
   - Нормализация должна использоваться только для target matching, без ломки текущих report symbols.

3. Runtime filtering (mandatory):
   - До `build_entry_recommendations(...)` фильтровать LP-eligible candidates по target scope.
   - Немatching candidates не должны становиться runtime errors.
   - Если matching set пустой: лог/telemetry должны явно фиксировать empty target scope.

4. Telemetry contract (mandatory):
   - Добавить deterministic counters в LP entry telemetry line, минимум:
     - `entry_target_scope_enabled`
     - `entry_target_input_total`
     - `entry_target_matched_total`
     - `entry_target_excluded_total`
   - Если есть empty target-result, добавить machine-readable reason marker (например `TARGET_SCOPE_EMPTY`).

5. Fail-safe invariants (mandatory):
   - Сохранить downgrade rules:
     - `TICK_DATA_DEGRADED`,
     - `SOURCE_CONFIDENCE_STALE/DIVERGED`,
     - `FRESHNESS_STALE`,
     - `RANGE_NOT_COMPUTED`,
     - `INVALID_OR_MISSING_RANGE`,
     - `INSUFFICIENT_STABILITY_HISTORY`.

## 4. Acceptance Criteria
- При включённом target scope рекомендации строятся только для `ETH/USDT` (учитывая `WETH-USDT` normal form).
- Внутри target scope выполняется сравнение по нескольким сетям и поддерживаемым venue.
- В telemetry есть детерминированные counters target scope.
- При пустом matching set цикл не падает и даёт прозрачный reason/telemetry.
- Релевантные тесты и `make test` зелёные.

## 5. Verification Commands
```bash
cd /home/dmitrii/projects/defi_agents
.venv/bin/pytest -q tests/test_lp_entry_recommendation.py tests/test_scout.py tests/test_notifier.py
.venv/bin/pytest -q tests/test_tick_density_scanner.py tests/test_lp_entry_shadow_calibration.py
make test
git status --short --branch
```

## 6. Report Format (mandatory)
- Summary (3-6 bullets)
- Что реализовано
- Изменённые файлы
- Запущенные команды и результаты
- Риски/что не проверено
- Recommended commit message (без commit)

## 7. Constraints
- Работать только в `/home/dmitrii/projects/defi_agents`.
- Не выполнять commit/push.
- Не использовать destructive git-команды.
- Не менять внешнюю инфраструктуру/секреты/n8n/VPS.
