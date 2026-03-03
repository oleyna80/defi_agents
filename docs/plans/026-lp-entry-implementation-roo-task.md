# Roo Task 026 — P0 Implementation: LP Entry Recommendation v1

## 0. Objective
Реализовать P0 design-to-code инкремент после Plan 025:
- wiring `pit -> suggested range`,
- deterministic Top-N `EntryRecommendation`,
- отдельный report block `LP Entry Recommendations`,
- fail-safe контракт (`degraded/stale/diverged/invalid range => WATCHLIST`).

## 1. Scope
In scope:
- Runtime wiring для pit/range в tick scan path.
- Builder для `EntryRecommendation` из текущего `ScoutResult`/metadata.
- Top-N сортировка/срез по `rank_v1` для actionable.
- Новый блок в report output.
- Тесты на ranking/range/fail-safe.

Out of scope:
- Auto-execution tx.
- Новые внешние data providers.
- Multi-venue comparison и stability history gate (это P1).

## 2. Required File Targets
- `src/defi_agents/lp/band_depth.py`
- `src/defi_agents/lp/models.py`
- `main.py`
- `src/defi_agents/notifier.py`
- `tests/test_tick_density_scanner.py`
- `tests/test_tick_density_phase_ab.py`
- `tests/test_notifier.py`
- (при необходимости) новый модуль для recommendation contract/builder в `src/defi_agents/lp/`

## 3. Implementation Requirements
1. Подключить pit pipeline в runtime scan:
   - `build_price_bins(...)`
   - `find_liquidity_pits(...)`
   - `suggest_range(...)` (hybrid v1 default: pit center + vol width floor/guardrails)
2. Заполнять в scan result:
   - `pit_type`, `pits_found`
   - `suggested_range_lower_tick`, `suggested_range_upper_tick`
3. Собрать `EntryRecommendation` Top-N в runtime:
   - включить `chain/project/pair/fee_tier/range/confidence/reasons/watchlist_reason`
   - deterministic ranking `rank_v1` (score + quality factors)
4. Fail-safe:
   - `tick_data_quality != OK` -> WATCHLIST
   - invalid/missing range -> WATCHLIST
   - stale/diverged confidence states -> WATCHLIST
5. Reporting:
   - добавить отдельный блок `LP Entry Recommendations`
   - не ломать существующий Decision View формат.

## 4. Acceptance Criteria
- В runtime появляются валидные `suggested_range_*` для OK tick scans.
- Формируется Top-N recommendation list с детерминированной сортировкой.
- В Telegram/report output появляется `LP Entry Recommendations`.
- Для degraded/stale/diverged/invalid range нет false-actionable.
- Регрессия существующих путей не ломается.

## 5. Verification Commands
```bash
cd /home/dmitrii/projects/defi_agents
pytest -q tests/test_tick_density_scanner.py tests/test_tick_density_phase_ab.py tests/test_notifier.py
pytest -q tests/test_scout.py tests/test_volatility.py
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

