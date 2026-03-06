# Technical Plan: 034 — Multi-chain Position Reader (Phase 3.0.1)

Refers to Spec: `docs/specs/001-multi-chain-position-reader.md` (approved per task context; source file currently outside `projects/defi_agents` tree).

## 1. Summary

Цель плана: перевести single-chain runtime чтения позиций Uniswap V3 (Arbitrum-only) в multi-chain режим с сохранением fail-safe контракта.

Ключевые результаты:
- ввести chain-aware конфиг `execution.chains`;
- выделить общий `BaseUniswapV3PositionReader`;
- перевести baseline-ключи в chain-aware формат;
- агрегировать multi-chain `PositionState[]` в `main.py` без ломки downstream-контракта;
- закрыть тестовую матрицу и деградационные сценарии.

## 2. Path Mapping (requested -> actual in repo)

| Requested in task | Actual path in this repo | Action in this plan |
|---|---|---|
| `src/defi_agents/execution/config.py` | `src/defi_agents/scout/config.py` | Update execution schema here (actual SSOT config path). |
| `tracker/position_reader.py` | `src/defi_agents/tracker/position_reader.py` | Refactor + base reader extraction. |
| `tracker/position_baseline.py` | `src/defi_agents/tracker/position_baseline.py` | Chain-aware baseline keys + legacy fallback read. |
| `main.py` | `main.py` | Multi-chain reader orchestration + aggregation. |

Дополнительно (при необходимости):
- `tests/test_execution_config.py`
- `tests/test_position_reader.py`
- `tests/test_position_baseline.py`
- `tests/test_execution_state_source.py`

## 3. Phase Plan

### Phase 1 — Config schema (`execution.chains`) + `BaseUniswapV3PositionReader`

#### Scope
1. Добавить multi-chain schema в `src/defi_agents/scout/config.py`:
   - `execution.chains.<chain>.rpc_url`
   - `execution.chains.<chain>.coingecko_platform_id`
   - `execution.chains.<chain>.uniswap_v3.factory_proxy`
   - `execution.chains.<chain>.uniswap_v3.position_manager_proxy`
2. Определить правила валидации:
   - сеть активна только при полном наборе обязательных полей;
   - неполная сеть исключается из цикла с warning (не фатально);
   - остальные сети продолжают обработку.
3. Выделить общий `BaseUniswapV3PositionReader` в `src/defi_agents/tracker/position_reader.py`:
   - общий пайплайн чтения/нормализации;
   - контекст сети (`chain_name`, `rpc_url`, `factory_proxy`, `position_manager_proxy`, `coingecko_platform_id`);
   - единый выход в `PositionState`.

#### Deliverables
- schema-ready `execution.chains`;
- базовый reader-класс с chain-параметризацией;
- тесты на конфиг-валидацию и базовый reader pipeline.

#### Exit Criteria
- конфигурация валидируется детерминированно;
- базовый reader не ломает текущий `PositionState` контракт;
- тесты конфиг/reader green.

---

### Phase 2 — Arbitrum reader refactor + baseline provider (chain-aware keys)

#### Scope
1. Рефакторить текущий Arbitrum reader в thin-wrapper/adapter поверх `BaseUniswapV3PositionReader` в `src/defi_agents/tracker/position_reader.py`.
2. Обновить baseline provider в `src/defi_agents/tracker/position_baseline.py`:
   - новый ключ: `<chain>:uni-v3:<token_id>`;
   - все новые записи — только chain-aware;
   - чтение поддерживает legacy fallback (`uni-v3:<token_id>`) только как backward-compatible read path.
3. Сохранить fail-safe семантику `ENTRY_BASELINE_MISSING` без переименования и без изменения meaning.

#### Deliverables
- Arbitrum reader как частный случай chain-конфигурации;
- chain-aware baseline keying;
- backward-compatible read fallback для legacy baseline keys;
- тесты baseline/read-path/fail-safe.

#### Exit Criteria
- Arbitrum flow работает через новый base-layer;
- ключевые baseline коллизии между сетями устранены;
- `ENTRY_BASELINE_MISSING` поведенчески и семантически неизменён.

---

### Phase 3 — Multi-chain aggregation in `main.py` + full test matrix

#### Scope
1. В `main.py` реализовать orchestration по `execution.chains`:
   - создать reader per active chain;
   - собрать states из всех успешных сетей;
   - вернуть единый список `PositionState[]` для downstream без изменения интерфейса.
2. Ввести deterministic aggregation order:
   - сортировка минимум по `chain_name`, затем `token_id`.
3. Реализовать per-chain fail-safe деградацию:
   - RPC ошибка одной сети логируется и не прерывает остальные;
   - цикл возвращает частично успешный результат, если хотя бы одна сеть успешна;
   - при отказе всех сетей — контролируемый fail-fast верхнего уровня с сохранением диагностического формата.
4. Закрыть полную тестовую матрицу (config + reader + baseline + orchestration).

#### Deliverables
- multi-chain aggregation path в `main.py`;
- diagnostics/logging для per-chain деградации;
- интеграционные/регрессионные тесты под multi-chain и fail-safe кейсы.

#### Exit Criteria
- multi-chain states агрегируются в единый список;
- деградация одной сети не останавливает весь цикл;
- full verification commands green.

## 4. Fail-safe Checks (mandatory)

1. **`ENTRY_BASELINE_MISSING` не должен ломаться**
   - reason-code, семантика и fail-safe поведение сохраняются;
   - отсутствие baseline не приводит к аварийному падению цикла;
   - не формируются ложные `P&L/HODL` значения.

2. **RPC-деградация одной сети не должна останавливать остальные сети**
   - ошибка одной сети обрабатывается локально (per-chain try/catch);
   - остальные сети продолжают чтение;
   - агрегатор возвращает частичный успех при наличии валидных states.

## 5. Verification

Обязательные команды:

```bash
cd /home/dmitrii/projects/defi_agents
make test
```

Pytest-gate (конкретные исполнимые команды):

```bash
cd /home/dmitrii/projects/defi_agents
.venv/bin/pytest -q tests/test_execution_config.py tests/test_position_reader.py tests/test_position_baseline.py
.venv/bin/pytest -q tests/test_execution_state_source.py tests/test_scout.py
```

## 6. Implementation Checklist

- [ ] Phase 1 complete: `execution.chains` schema + `BaseUniswapV3PositionReader`.
- [ ] Phase 2 complete: Arbitrum refactor + chain-aware baseline keys + legacy read fallback.
- [ ] Phase 3 complete: `main.py` multi-chain aggregation + deterministic ordering + degraded success path.
- [ ] Fail-safe checks confirmed (`ENTRY_BASELINE_MISSING`, per-chain RPC degradation).
- [ ] Verification matrix green (`make test` + pytest-gate commands).

## 7. Non-goals for this plan

- Изменение бизнес-логики execution/strategy вне tracker-orchestration цепочки.
- LIVE/infra/secrets/n8n/VPS изменения.
- Любые runtime-правки в рамках текущей подзадачи (документация only).

