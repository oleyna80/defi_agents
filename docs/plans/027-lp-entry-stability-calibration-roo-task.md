# Roo Task 027 — P1 Stability Gate & Shadow Calibration for LP Entry Recommendations

## 0. Objective
После закрытия Plan 026 (P0) реализовать P1-контур устойчивости и калибровки:
- history/stability gate для рекомендаций (`>=3 observations / 6h`),
- метрики стабильности Top-N и доли downgrade в WATCHLIST,
- controlled calibration параметров ранжирования/уверенности на SHADOW evidence,
- без ослабления fail-safe правил.

## 1. Scope
In scope:
- Добавить history-backed stability gate для `EntryRecommendation` pipeline.
- Добавить runtime counters/metadata для причин unstable/unstable-rank.
- Реализовать минимальный calibration loop для `rank_v1`/confidence cutoffs (config-driven).
- Добавить/обновить тесты на stability gate и fail-safe invariants.
- Обновить docs/memory-bank по факту.

Out of scope:
- LIVE execution/auto-trading.
- Новые внешние провайдеры данных.
- Изменение fail-safe контракта `degraded/stale/diverged/invalid-range -> WATCHLIST`.

## 2. Required File Targets
- `main.py`
- `src/defi_agents/lp/entry_recommendation.py`
- `src/defi_agents/lp/models.py` (при необходимости расширения контракта)
- `src/defi_agents/scout/config.py` (config knobs для stability/calibration)
- `src/defi_agents/notifier.py` (только если нужны безопасные telemetry fields)
- `tests/test_lp_entry_recommendation.py`
- `tests/test_notifier.py` (при изменении report block)
- (при необходимости) новый модуль history/gate в `src/defi_agents/lp/`

## 3. Implementation Requirements
1. Stability gate (P1):
   - Для actionable-рекомендаций учитывать только кандидаты с достаточной историей:
     - минимум `3` наблюдения в окне `6h` (конфигурируемо).
   - При нехватке истории переводить в `WATCHLIST` с reason code `INSUFFICIENT_STABILITY_HISTORY`.
2. Top-N stability telemetry:
   - Добавить counters:
     - `entry_total`,
     - `entry_actionable`,
     - `entry_watchlist`,
     - `entry_watchlist_insufficient_history`,
     - `entry_topn_churn` (доля изменений состава Top-N vs prev snapshot).
3. Controlled calibration:
   - Все пороги/веса должны быть config-driven и обратимы.
   - Менять не более 1-2 параметров за итерацию (из runbook-практики).
   - Не изменять существующие fail-safe downgrade правила.
4. Backward compatibility:
   - При отсутствии history-данных pipeline не падает.
   - Поведение fail-closed сохраняется.

## 4. Acceptance Criteria
- Stability gate применён к actionable path и покрыт тестами.
- У unstable кандидатов выставляется явный watchlist reason (`INSUFFICIENT_STABILITY_HISTORY`).
- Появились детерминированные telemetry counters для Top-N stability.
- Full test gate зелёный, регрессий по Plan 026 нет.

## 5. Verification Commands
```bash
cd /home/dmitrii/projects/defi_agents
.venv/bin/pytest -q tests/test_lp_entry_recommendation.py tests/test_tick_density_scanner.py tests/test_notifier.py
.venv/bin/pytest -q tests/test_scout.py tests/test_volatility.py
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
- Не менять внешнюю инфраструктуру/секреты.
