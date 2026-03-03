---
name: lp-entry-implementation
description: Реализация P0 LP Entry Recommendation v1 по Plan 026: wiring pit->range, EntryRecommendation Top-N, fail-safe downgrade и отдельный report block.
---

# LP Entry Implementation

## When to use
- Когда нужно выполнить P0-инкремент из `docs/plans/026-lp-entry-implementation-roo-task.md`.
- Когда задача включает `pit -> suggested range -> EntryRecommendation -> report`.

## When NOT to use
- Когда требуется только research/docs (используй plan/research workflow).
- Когда задача про infra/VPS/systemd/секреты.
- Когда нужен P1 scope (stability gate, multi-venue compare, shadow calibration).

## Goal
Закрыть P0 design-to-code без scope creep:
- подключить pit/range в runtime-path,
- сформировать deterministic Top-N `EntryRecommendation`,
- сохранить fail-safe контракт (`degraded => WATCHLIST`),
- вывести отдельный блок `LP Entry Recommendations`.

## Required inputs
- `docs/plans/026-lp-entry-implementation-roo-task.md`
- `docs/research/2026-03-lp-entry-recommendation-research.md`
- `ROADMAP.md` (Phase 2.7.5)

## Target files
- `src/defi_agents/lp/band_depth.py`
- `src/defi_agents/lp/models.py`
- `main.py`
- `src/defi_agents/notifier.py`
- `tests/test_tick_density_scanner.py`
- `tests/test_tick_density_phase_ab.py`
- `tests/test_notifier.py`

## Workflow
1. Scope lock
   - Подтверди, что реализуется только P0 из Plan 026.
   - Не добавляй новые провайдеры и не трогай execution/LIVE path.
2. Runtime wiring (tick scan path)
   - Подключи `build_price_bins(...)`, `find_liquidity_pits(...)`, `suggest_range(...)`.
   - Заполни `pit_type`, `pits_found`, `suggested_range_lower_tick`, `suggested_range_upper_tick`.
3. Recommendation builder
   - Добавь deterministic `EntryRecommendation` assembly из текущих candidate/metadata.
   - Включи поля: `chain/project/pair/fee_tier/range/confidence/reasons/watchlist_reason`.
   - Введи `rank_v1` и Top-N selection для actionable.
4. Fail-safe policy
   - `tick_data_quality != OK` => WATCHLIST.
   - missing/invalid range => WATCHLIST.
   - stale/diverged confidence states => WATCHLIST.
5. Reporting
   - Добавь отдельный блок `LP Entry Recommendations`.
   - Не ломай текущий `Decision View` и совместимость отчёта.
6. Validation
   - Прогони таргетные тесты + полный `make test` (см. test-gate skill).
   - Подготовь отчёт в формате Plan 026.

## Guardrails
- Никаких commit/push без явного подтверждения пользователя.
- Никаких destructive git-команд.
- Без silent fallback: любая деградация должна быть reason-coded и видимой в output.
- Минимальный diff: только файлы из целевого scope.

## Done criteria
- `suggested_range_*` появляется для валидных tick scans.
- Есть Top-N `EntryRecommendation` с детерминированной сортировкой.
- Отдельный блок `LP Entry Recommendations` добавлен.
- degraded/stale/diverged/invalid range не становятся actionable.

