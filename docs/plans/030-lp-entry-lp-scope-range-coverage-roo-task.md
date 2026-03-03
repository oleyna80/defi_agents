# Roo Task 030 — LP Entry LP-Scope + Range Coverage Enablement

## 0. Objective
Перевести Phase 2.7.7 из режима `all WATCHLIST` к устойчивому появлению `ACTIONABLE`
без ослабления fail-safe контракта, устранив текущий root-cause:
- в LP Entry попадает общий поток `report_picks`, включая не-LP и не-range-ready кандидатов;
- доминирует причина `INVALID_OR_MISSING_RANGE`, часть кейсов уходит в generic `REPORT_GROUP_WATCHLIST`.

Целевой результат:
- `EntryRecommendation` строится из LP-eligible подмножества с явной детерминированной диагностикой,
- причины WATCHLIST становятся action-oriented (без "немых" generic причин),
- в SHADOW есть шанс на ненулевой `actionable_ratio` при сохранении fail-safe.

## 1. Scope
In scope:
- Ввести явный LP-entry eligibility pre-filter перед `build_entry_recommendations(...)`.
- Добавить reason taxonomy для ineligible/range-unavailable path (детерминированные machine codes).
- Сократить/устранить `REPORT_GROUP_WATCHLIST` как доминирующий fallback reason в LP entry telemetry.
- Добавить telemetry/evidence счётчики покрытия (`input -> lp-eligible -> range-ready`).
- Обновить tests + evidence report + roadmap/memory-bank.

Out of scope:
- LIVE execution / tx automation.
- Ослабление fail-safe downgrade (`degraded/stale/diverged/invalid-range -> WATCHLIST`).
- Изменение внешней инфраструктуры, секретов, n8n, VPS.

## 2. Required File Targets
- `main.py`
- `src/defi_agents/lp/entry_recommendation.py`
- `src/defi_agents/lp/models.py` (только если нужен новый enum/code contract)
- `src/defi_agents/lp/shadow_calibration.py` (если добавляются новые агрегаты snapshot)
- `scripts/lp_entry_shadow_calibration_report.py` (reason/coverage output, если нужно)
- `tests/test_lp_entry_recommendation.py`
- `tests/test_lp_entry_shadow_calibration.py`
- `tests/test_scout.py` (если затронут eligibility contract)
- `docs/reports/lp-entry-actionable-enablement-YYYY-MM-DD.md` (new revision)
- `ROADMAP.md`
- `docs/memory-bank/activeContext.md`
- `docs/memory-bank/progress.md`

## 3. Implementation Requirements
1. LP-entry eligibility pre-filter (mandatory):
   - Перед сборкой `EntryRecommendation` отделить LP-eligible subset.
   - Минимальные критерии v1:
     - `yield_type == lp_fees`,
     - поддерживаемый venue для tick/range path,
     - есть валидная pool-reference база для range computation path.
   - Добавить deterministic counters:
     - `entry_input_total`,
     - `entry_lp_eligible_total`,
     - `entry_lp_ineligible_total`.

2. Deterministic reason taxonomy (mandatory):
   - Для WATCHLIST и/или ineligible path использовать только machine codes.
   - Устранить массовый generic fallback `REPORT_GROUP_WATCHLIST` как primary root-cause.
   - Примеры кодов (можно расширять, но не free-text):
     - `NON_LP_YIELD_TYPE`,
     - `UNSUPPORTED_ENTRY_VENUE`,
     - `MISSING_POOL_REFERENCE`,
     - `RANGE_NOT_COMPUTED`,
     - `INVALID_OR_MISSING_RANGE`.

3. Range coverage visibility:
   - Добавить счётчики покрытия range path:
     - `entry_range_ready_total`,
     - `entry_range_missing_total` (или эквивалент с reason counts).
   - В telemetry/evidence должно быть видно, где именно теряется actionable.

4. Actionable enablement gate:
   - Сохранить gate `actionable_ratio_positive_pass`.
   - При fail: report обязан показать top watchlist reasons + coverage counters.
   - При pass: зафиксировать evidence с ненулевым `actionable_ratio` на SHADOW-окне.

## 4. Acceptance Criteria
- LP Entry telemetry показывает `input -> lp-eligible -> range-ready` цепочку.
- `watchlist_reason_counts` доминирующе содержит конкретные детерминированные причины, а не generic fallback.
- `actionable_ratio_positive_pass` воспроизводимо вычисляется на snapshot.
- Fail-safe инварианты не ослаблены и подтверждены тестами.
- Полный `make test` зелёный.

## 5. Verification Commands
```bash
cd /home/dmitrii/projects/defi_agents
.venv/bin/pytest -q tests/test_lp_entry_recommendation.py tests/test_lp_entry_shadow_calibration.py tests/test_tick_density_scanner.py
.venv/bin/pytest -q tests/test_scout.py tests/test_notifier.py
make test
PYTHONPATH=src .venv/bin/python scripts/lp_entry_shadow_calibration_report.py --from-file docs/reports/artifacts/lp_entry_shadow_runtime_2026-03-03_plan029.log
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
