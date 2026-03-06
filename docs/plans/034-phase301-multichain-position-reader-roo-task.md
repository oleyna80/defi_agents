# Roo Task Plan: 034 — Phase 3.0.1 Multi-chain Position Reader

Связанная спека: `docs/specs/001-multi-chain-position-reader.md` (Status: `APPROVED`).

## 1) Цель

Реализовать Phase 3.0.1 для execution state source:
- chain-aware конфиг `execution.chains`;
- общий `BaseUniswapV3PositionReader` + chain adapters;
- chain-aware baseline keys с backward-compatible read fallback;
- multi-chain aggregation в единый `PositionState[]` в `main.py`;
- fail-safe контракт: per-chain degradation, `ENTRY_BASELINE_MISSING` unchanged, `all-chains-fail` -> controlled top-level failure.

## 2) Scope и ограничения

### In Scope
- `src/defi_agents/scout/config.py`
- `src/defi_agents/tracker/position_reader.py`
- `src/defi_agents/tracker/position_baseline.py`
- `main.py`
- `tests/test_execution_state_source.py`
- `tests/test_position_reader.py`
- `tests/test_position_baseline.py`
- `docs/memory-bank/scout_config.json` (только если нужен sync)

### Out of Scope
- Изменение бизнес-логики расчётов PnL/fees/APR.
- Любые infra/VPS/secrets/n8n изменения.
- Git commit/push.

## 3) Execution-ready фазы

### F1 — Config schema: `execution.chains`

**Цель:** активировать только валидные chain entries.

**Требования:**
- `execution.chains.<chain>.rpc_url`
- `execution.chains.<chain>.coingecko_platform_id`
- `execution.chains.<chain>.uniswap_v3.factory_proxy`
- `execution.chains.<chain>.uniswap_v3.position_manager_proxy`
- Невалидная chain-конфигурация исключается из active set с warning.

**DoD F1:**
- В `ExecutionConfig` активны только complete chains.
- Неполные chains не ломают цикл.

---

### F2 — `BaseUniswapV3PositionReader` + chain adapters

**Цель:** единый reader pipeline с chain-параметризацией.

**Требования:**
- Общая абстракция `BaseUniswapV3PositionReader` с параметрами сети.
- Thin wrappers/adapters для Arbitrum/Base/Optimism/HypeEVM.
- Reader-only semantics без mock/synthetic fallback.

**DoD F2:**
- Reader создаётся per chain из execution config.
- Контракт `PositionState` не меняется.

---

### F3 — Baseline: chain-aware key + fallback-read

**Цель:** устранить межсетевые коллизии baseline ключей.

**Требования:**
- Canonical key: `<chain>:uni-v3:<token_id>`.
- Legacy read fallback: `uni-v3:<token_id>` только на чтение.
- `ENTRY_BASELINE_MISSING` и остальные reason codes не переименовывать и не менять семантику.

**DoD F3:**
- Chain-aware ключи приоритетны при lookup.
- Legacy fallback сохраняет backward compatibility.

---

### F4 — `main.py` multi-chain aggregation

**Цель:** собрать единый `PositionState[]` по всем активным сетям.

**Требования:**
- Orchestration по всем активным chains.
- Deterministic order: `(chain, token_id)`.
- Ошибка одной сети не валит весь цикл.
- Если fail по всем сетям: controlled top-level failure.

**DoD F4:**
- Partial success при частичной деградации.
- Controlled failure при `all-chains-fail`.

---

### F5 — Tests + drift-check + docs sync

**Цель:** закрыть test/ops/doc gate.

**Требования:**
- Targeted pytest по изменённым модулям.
- `make test` обязателен.
- runbook runtime drift-check обязателен.
- Memory Bank sync по фактическим изменениям.

**DoD F5:**
- Targeted и full test suite green.
- Нет runbook/runtime drift для изменённых runtime path.

## 4) Verification matrix

```bash
cd /home/dmitrii/projects/defi_agents
.venv/bin/pytest -q tests/test_execution_state_source.py tests/test_position_reader.py tests/test_position_baseline.py
make test

# runtime drift-check
git diff -- main.py src/defi_agents/execution src/defi_agents/tracker
rg -n "fallback|mock_positions|reason=|Execution state|Execution summary" docs/runbooks
git diff -- docs/runbooks
```

## 5) Rollback section

Если проверка не проходит:
1. Откатить только изменения текущего task scope-файлов (`config.py`, `position_reader.py`, `position_baseline.py`, `main.py`, тесты, docs plan/index, memory bank updates).
2. Вернуть предыдущий runtime контракт execution state source (последний green state в рабочей ветке).
3. Повторно прогнать verification matrix (targeted + `make test`) до фиксации regression root cause.

## 6) Итоговые критерии приёмки

- Реализован multi-chain execution state source через `execution.chains`.
- Fail-safe контракт сохранён (`ENTRY_BASELINE_MISSING` unchanged, reader-only semantics intact).
- Per-chain degradation работает; `all-chains-fail` даёт controlled top-level failure.
- Unified `PositionState[]` агрегируется и сортируется детерминированно по `(chain, token_id)`.
- Тестовый и drift-check gate закрыты.
