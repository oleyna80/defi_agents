---
name: phase3-multichain-position-reader
description: Реализация Phase 3.0.1 multi-chain Position Reader (execution.chains, BaseUniswapV3PositionReader, chain-aware baselines, единый PositionState[]), с жёстким fail-safe контрактом.
---

# Phase3 Multi-Chain Position Reader

## When to use
- Когда approved spec требует расширения reader-only execution state source на несколько EVM-сетей.
- Когда нужно перевести single-chain reader path в chain-aware архитектуру без ослабления policy guard.
- Когда задача включает `execution.chains`, chain-aware baseline keys и агрегацию states в `main.py`.

## When NOT to use
- Для LP-entry/scout/tick-density задач.
- Для LIVE rollout/infra/VPS операций.
- Если spec не утверждён и не доступен в репозитории.

## Goal
Сделать безопасный migration к multi-chain reader path:
- сохранить `reader-only + fail-closed`,
- не ломать reason-code контракт (`ENTRY_BASELINE_MISSING` и др.),
- выдавать единый агрегированный список `PositionState` из нескольких chains,
- обеспечить backwards compatibility конфига и baseline (если явно задано в spec/plan).

## Required inputs
- Approved spec: `docs/specs/001-multi-chain-position-reader.md` (или актуальный эквивалент в repo).
- План задачи в `docs/plans/*` с DoD и тестовой матрицей.
- Актуальный `ROADMAP.md` (Phase 3.0 / Gate-3 constraints).

## Target files (expected)
- `src/defi_agents/scout/config.py`
- `src/defi_agents/tracker/position_reader.py`
- `src/defi_agents/tracker/position_baseline.py`
- `main.py`
- `docs/memory-bank/scout_config.json`
- `tests/test_execution_state_source.py`
- `tests/test_position_reader.py`
- `tests/test_position_baseline.py`
- (опционально) `tests/test_execution_policy.py` при затрагивании stale/reason semantics

## Workflow
1. Scope lock
   - Подтверди наличие approved spec в repo.
   - Зафиксируй, что runtime остаётся fail-closed: отсутствие валидных states => execution loop skip.
2. Config layer (`execution.chains`)
   - Добавь schema/validation для chain entries (enabled, chain id/name, rpc env, reader params).
   - Сохрани обратную совместимость для legacy single-chain fields (если требуется spec).
3. Reader refactor
   - Вынеси общий базовый reader (`BaseUniswapV3PositionReader`) и chain-specific реализации.
   - Не допусти silent fallback на mock или synthetic positions.
4. Baseline contract
   - Введи chain-aware ключи в baseline store (детерминированный формат из spec/plan).
   - Сохрани explicit reason-коды для missing/malformed/incomplete baseline.
5. Runtime aggregation
   - Обнови `_load_execution_states()` в `main.py`: собрать states по всем enabled chains в единый список.
   - Сбой одной chain не должен приводить к крашу цикла; фиксируй деградацию явно.
6. Verification
   - Прогони targeted suites + `make test`.
   - Проверь инварианты: no mock fallback, stale guard intact, reason codes deterministic.
7. Reporting
   - Отчёт строго в формате: Summary / Что реализовано / Изменённые файлы / Команды / Риски / commit message (без commit).

## Guardrails
- Никаких commit/push без явного подтверждения пользователя.
- Никаких destructive git-команд.
- Не ослаблять `STALE_POSITION_DATA` и policy blocking semantics.
- Не удалять существующие reason-коды без миграционного обоснования.
- Не смешивать scope с LP-entry/hedger/runbook большими правками.

## Done criteria
- `execution.chains` работает как основной конфиг источника states.
- Есть общий base reader + chain-specific readers.
- Baseline ключи chain-aware и покрыты тестами.
- `main.py` агрегирует multi-chain states в единый `PositionState[]`.
- Full gate зелёный (`make test`), fail-safe контракт сохранён.
