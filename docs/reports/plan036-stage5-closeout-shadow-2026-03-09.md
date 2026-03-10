# Plan 036 — Stage-5 Closeout (SHADOW evidence)

**Date (UTC):** 2026-03-09  
**Scope:** repo-local only, без VPS/infra/secrets/n8n изменений, без commit/push

## 1) Startup check (mandatory, stdout)

- Full stdout artifact:
  - `docs/reports/artifacts/plan036_stage5_startup_check_2026-03-09.txt`

Key stdout lines:

```text
>>> 1) pwd
/home/dmitrii/projects/defi_agents
>>> 2) git status --short --branch
## feat/multi-chain-reader...origin/feat/multi-chain-reader
>>> 3) git branch -vv
* feat/multi-chain-reader f09d390 [origin/feat/multi-chain-reader] ...
>>> 4) git stash list
stash@{0}: On feat/multi-chain-reader: wip-local-doc-priority-before-sync-2026-03-08
stash@{1}: On main: wip: sentinel-cycle local change
>>> 5) git fetch origin --prune
>>> 6) git rev-parse HEAD
f09d390bc486a6a070c0c412de35b1b9e95c89fc
>>> 7) git rev-parse origin/feat/multi-chain-reader
f09d390bc486a6a070c0c412de35b1b9e95c89fc
>>> 8) rg -n "Plan 036|Stage-4|Stage-5|ADJUST|KEEP|selector|churn|DEEPSEEK_API_KEY" ROADMAP.md docs src tests || true
ROADMAP.md:260:  - 2026-03-09 (Plan 036 Stage-4 closeout, repo-local SHADOW evidence):
...
```

## 2) Runtime fix (SHADOW-only) + machine-readable startup marker

Цель Stage-5 — убрать зависимость базового repo-local SHADOW evidence от command-scoped fallback (`ALLOW_MOCK_FALLBACK=true` в командной строке).

Сделано:

- В `main.py` добавлен минимальный SHADOW-only startup path для AI provider:
  - если `DEEPSEEK_API_KEY` отсутствует и run в SHADOW-mode, используется `MockAIService` без command-scoped env override;
  - для non-SHADOW path fail-safe поведение сохранено: при недоступном provider и выключенном fallback startup fail-closed.
- Добавлен machine-readable runtime marker startup path:
  - `AI startup path: provider=<...> reason=<...> shadow_mode=<0|1> allow_mock_fallback=<0|1>`
  - подтверждённый reason для базового SHADOW run:
    - `MOCK_FALLBACK_SHADOW_DEEPSEEK_API_KEY_MISSING`.

Важно:

- LP selector/ranking decision logic не менялась.
- Fail-safe контракт не ослаблен.

## 3) Sustained SHADOW evidence (>=24 cycles)

Runtime artifact:

- `docs/reports/artifacts/plan036_stage5_shadow_runtime_2026-03-09T19-21-40Z.log`

Результат окна:

- 24/24 циклов завершены успешно (`rc=0` каждый цикл).
- На каждом цикле присутствуют:
  - startup marker (`AI startup path: ...`);
  - selector telemetry (`LP entry stability telemetry: ...`).

## 4) Selector stability/churn snapshot + final verdict

Evidence artifact:

- `docs/reports/artifacts/plan036_stage5_shadow_evidence_2026-03-09.json`

Ключевые значения:

- `cycles_with_selector_telemetry=24`
- `entry_selector_input_total_sum=360`
- `entry_selector_matched_total_sum=360`
- `entry_selector_actionable_total_sum=117`
- `entry_selector_watchlist_total_sum=243`
- `entry_selector_actionable_ratio=0.3250`

Stability/churn:

- `entry_topn_churn_avg=0.0354`
- `entry_topn_churn_p95=0.2000`

Gate checks:

- `errors_zero_pass=true`
- `telemetry_min_cycles_pass=true`
- `actionable_ratio_positive_pass=true`
- `insufficient_history_ratio_pass=true`
- `topn_churn_avg_pass=true`
- `topn_churn_p95_pass=true`
- `all_pass=true`

**Final verdict: `KEEP`**

## 5) Tests / verification

Обязательные прогоны:

- `PYTHONPATH=src .venv/bin/pytest -q tests/test_lp_entry_recommendation.py tests/test_tick_density_scanner.py tests/test_lp_cross_protocol_selector.py tests/test_notifier.py`
  - `77 passed`
- `make test`
  - `454 passed`

Дополнительно (из-за изменения startup/runtime path):

- `PYTHONPATH=src .venv/bin/pytest -q tests/test_startup_provider_path.py tests/test_lp_entry_recommendation.py tests/test_tick_density_scanner.py tests/test_lp_cross_protocol_selector.py tests/test_notifier.py`
  - `81 passed`

## 6) Guardrails confirmation

- VPS/infra/secrets/n8n changes: **none**
- Destructive git-команды: **не использовались**
- Commit/push: **не выполнялись**
- Fail-safe контракт: **сохранён (не ослаблялся)**

## Addendum (policy-tightening mini-fix, 2026-03-09)

- Выполнен post-review mini-fix для startup policy в `main.py`:
  - SHADOW startup fallback с reason `MOCK_FALLBACK_SHADOW_DEEPSEEK_API_KEY_MISSING`
    теперь срабатывает **только** при runtime `config.execution.mode == "SHADOW"`.
  - `reporting.telegram_shadow_mode_enabled` исключён из startup policy (остаётся
    reporting/notification-флагом).
- Сохранены инварианты:
  - machine-readable startup marker (`AI startup path: provider=<...> reason=<...> shadow_mode=<0|1> allow_mock_fallback=<0|1>`);
  - fail-closed вне SHADOW при `ALLOW_MOCK_FALLBACK=false` и отсутствующем
    `DEEPSEEK_API_KEY` (`Production AI Init Failure`);
  - env fallback `ALLOW_MOCK_FALLBACK=true` продолжает работать.
- Добавлены/обновлены runtime-path тесты в `tests/test_startup_provider_path.py`:
  - `reporting.telegram_shadow_mode_enabled=true` + `execution.mode!=SHADOW` +
    `ALLOW_MOCK_FALLBACK=false` + no key => fail-closed.
  - `execution.mode=SHADOW` + no key => SHADOW fallback to Mock.
