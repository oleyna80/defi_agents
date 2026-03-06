# Roo Task Plan: 035 — Gate-3 PASS enablement (evidence sufficiency)

Связанные артефакты:
- `docs/reports/gate3-evidence-phase30-closeout-2026-03-06.md`
- `docs/reports/artifacts/gate3_evidence_contract_v1_2026-03-06_plan035.json`
- `docs/reports/artifacts/plan035_startup_git_check_2026-03-06.txt`

## 1) Цель

Довести evidence-пакет Gate-3 до PASS-критериев **без изменения fail-safe runtime decision logic**:

1. `positions_validated_count >= 3`
2. `reader_ok_threshold_pass=true` на окне `48h`
3. `errors_zero_pass=true`

## 2) Scope и ограничения

### Разрешённый scope
- `docs/plans/*`
- `scripts/*` (только evidence/tooling)
- `docs/reports/*`
- `docs/reports/artifacts/*`
- `docs/memory-bank/activeContext.md`
- `docs/memory-bank/progress.md`
- `tests/*` (только для evidence/tooling)

### Запрещено
- Любые изменения runtime decision logic в `main.py` и `src/defi_agents/*`
- Любые infra/secrets/VPS/n8n изменения
- destructive git-команды
- commit/push

## 3) Execution-ready фазы

### F1 — Startup git-check evidence capture

**Задача:** выполнить обязательный git-check и сохранить stdout как артефакт.

**Команды:**
- `git status --short --branch`
- `git branch -vv`
- `git stash list`
- `git fetch origin --prune`
- `git rev-parse HEAD`
- `git rev-parse origin/main`
- `rg -n "Gate-3|gate3|evidence|reader_ok_threshold_pass|positions_validated_count|errors_zero_pass" docs/plans docs/reports docs/runbooks scripts tests || true`

**DoD F1:**
- stdout сохранён в `docs/reports/artifacts/plan035_startup_git_check_2026-03-06.txt`
- отчёт ссылается на этот артефакт

---

### F2 — Tooling hardening для reproducible PASS/FAIL

**Задача:** доработать evidence-tooling без runtime влияния.

**Требования:**
- поддержка объединения нескольких лог-файлов evidence-окна (`--from-file` repeatable)
- явный `verdict` (`PASS|FAIL`) в contract v1
- сохранение fail-safe semantics и contract v1 полей `evidence_gaps`/`reasons`

**DoD F2:**
- tooling выдаёт детерминированный PASS/FAIL по одинаковому input
- тестами покрыт multi-file log path

---

### F3 — Evidence artifact/report refresh

**Задача:** собрать новый contract v1 snapshot и синхронизировать отчёт.

**Требования:**
- artifact JSON содержит contract v1 поля и `evidence_gaps`/`reasons`
- отчёт фиксирует явный verdict и причины
- в отчёт добавлен startup git-check stdout (или ссылка + выдержка)

**DoD F3:**
- `docs/reports/artifacts/gate3_evidence_contract_v1_2026-03-06_plan035.json` сформирован
- `docs/reports/gate3-evidence-phase30-closeout-2026-03-06.md` обновлён до актуального verdict

---

### F4 — Runbook/runtime drift-check + Memory Bank sync

**Задача:** подтвердить отсутствие runtime drift и синхронизировать docs context.

**Требования:**
- выполнить runbook/runtime drift-check
- править runbook только при evidence-contract sync необходимости
- обновить `activeContext.md` и `progress.md`

**DoD F4:**
- drift-check выполнен
- Memory Bank отражает Plan 035 и результаты test gate

---

### F5 — Verification matrix

**Обязательные проверки:**

```bash
cd /home/dmitrii/projects/defi_agents
PYTHONPATH=src .venv/bin/pytest -q tests/test_gate3_evidence.py tests/test_gate3_evidence_report_script.py
PYTHONPATH=src .venv/bin/pytest -q tests/test_execution_state_source.py tests/test_position_reader.py tests/test_position_baseline.py
make test
```

**DoD F5:**
- targeted evidence tests green
- regression trio green
- full `make test` green

## 4) Acceptance / DoD

- Создан и синхронизирован Plan 035 (`docs/plans/035-...` + `docs/plans/INDEX.md`)
- Обновлён evidence report с явным verdict
- Обновлён artifact JSON contract v1 с `evidence_gaps` и `reasons`
- Все обязательные тесты зелёные
- runtime decision logic не менялся
