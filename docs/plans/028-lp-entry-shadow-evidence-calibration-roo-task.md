# Roo Task 028 — LP Entry SHADOW Evidence Gate + Controlled Calibration (Phase 2.7.6)

## 0. Objective
Закрыть незавершённый пункт `Phase 2.7.6 (P1, NEXT)` через evidence-driven цикл:
- собрать детерминированный SHADOW evidence по стабильности `EntryRecommendation`,
- выполнить controlled calibration `lp_entry_calibration` (не более 1-2 параметров за итерацию),
- зафиксировать решение `KEEP / ADJUST / ROLLBACK` с явными gate-check критериями.

## 1. Scope
In scope:
- Добавить автоматизированный snapshot/report для LP Entry stability metrics из runtime-логов.
- Зафиксировать baseline-метрики за окно наблюдения (рекомендуемо 48h).
- Выполнить не более одной итерации controlled calibration в `lp_entry_calibration`.
- Подготовить evidence-отчёт и синхронизировать roadmap/memory-bank по факту.

Out of scope:
- Любые LIVE execution изменения.
- Ослабление fail-safe контракта (`degraded/stale/diverged/invalid-range -> WATCHLIST`).
- Новые внешние провайдеры данных и инфраструктурные изменения (VPS/systemd/secrets).

## 2. Required File Targets
- `scripts/lp_entry_shadow_calibration_report.py` (new)
- `src/defi_agents/lp/shadow_calibration.py` (new helper/parser)
- `tests/test_lp_entry_shadow_calibration.py` (new)
- `docs/reports/lp-entry-shadow-calibration-YYYY-MM-DD.md` (new evidence report)
- `docs/memory-bank/scout_config.json` (только если есть калибровка)
- `ROADMAP.md` (статус `Phase 2.7.6`: закрыт или остаётся `NEXT` с blockers)
- `docs/memory-bank/activeContext.md`
- `docs/memory-bank/progress.md`

## 3. Implementation Requirements
1. Evidence snapshot tool:
   - Реализовать CLI-скрипт, который читает runtime-логи (`journalctl` или `--from-file`) и строит JSON snapshot.
   - Парсить строку telemetry:
     - `LP entry stability telemetry: entry_total=... entry_actionable=... entry_watchlist=... entry_watchlist_insufficient_history=... entry_topn_churn=...`
   - Агрегировать минимум:
     - `cycles_with_entry_telemetry`
     - `entry_total_sum`
     - `actionable_ratio`
     - `watchlist_ratio`
     - `insufficient_history_ratio`
     - `topn_churn_avg`
     - `topn_churn_p95`
2. Gate checks (deterministic):
   - Ввести явные булевы checks в JSON output:
     - `errors_zero_pass`
     - `telemetry_min_cycles_pass`
     - `insufficient_history_ratio_pass`
     - `topn_churn_avg_pass`
     - `topn_churn_p95_pass`
   - Пороги должны быть аргументами CLI с безопасными дефолтами.
3. Controlled calibration:
   - Если baseline gate не проходит, разрешено менять только 1-2 параметра в `lp_entry_calibration`.
   - Параметры должны быть обратимыми (в отчёте фиксировать `before -> after`).
   - Запрещено изменять fail-safe downgrade rules.
4. Reporting:
   - Сформировать единый markdown evidence-отчёт:
     - baseline snapshot,
     - изменённые параметры (если были),
     - post-tune snapshot,
     - решение `KEEP / ADJUST / ROLLBACK`,
     - статус `Phase 2.7.6` (close/open с причинами).

## 4. Acceptance Criteria
- Появился автоматизированный JSON snapshot для LP Entry SHADOW calibration evidence.
- Есть тесты на parser/aggregation/gate checks (включая malformed/no-data лог-кейсы).
- При calibration-изменениях зафиксирован rollback path и выполнен post-tune compare.
- `ROADMAP.md` и memory-bank синхронизированы с фактическим результатом gate.
- Полный `make test` зелёный.

## 5. Verification Commands
```bash
cd /home/dmitrii/projects/defi_agents
.venv/bin/pytest -q tests/test_lp_entry_shadow_calibration.py tests/test_lp_entry_recommendation.py tests/test_tick_density_scanner.py
.venv/bin/pytest -q tests/test_scout.py tests/test_notifier.py
make test
PYTHONPATH=src .venv/bin/python scripts/lp_entry_shadow_calibration_report.py --from-file docs/reports/artifacts/lp_entry_shadow_sample.log
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
- Не менять внешнюю инфраструктуру/секреты/n8n.
