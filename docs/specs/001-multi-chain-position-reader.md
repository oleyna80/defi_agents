# Спецификация Phase 3.0.1: Multi-chain Position Reader для Uniswap V3

## 1. Мета

- **Документ:** Phase 3.0.1
- **Статус:** APPROVED (2026-03-06)
- **Область:** tracker-модуль
- **Цель:** расширить текущий reader позиций Uniswap V3 с single-chain (Arbitrum) до multi-chain режима без нарушения существующих fail-safe гарантий.
- **Контекст подтверждения:** утверждено в задаче на реализацию Phase 3.0.1 multi-chain Position Reader (repo-local scope `projects/defi_agents`, обязательные этапы SDD gate + implementation + verification).

## 2. Контекст и исходная точка

Текущий `ArbitrumUniswapV3PositionReader` покрывает только Arbitrum.

Актуальное распределение позиций:

- Base: 2
- Optimism: 3
- Arbitrum: 2
- HypeEVM: 1
- **Итого:** 8 позиций в 4 сетях

## 3. Scope

### In Scope

1. Архитектурное расширение reader-слоя для работы с несколькими EVM-сетями.
2. Введение chain-aware конфигурации `execution.chains`.
3. Рефакторинг базового reader-класса под параметризацию по сети.
4. Унификация ключей baseline-хранилища для multi-chain.
5. Агрегация состояния позиций из всех сетей в единый список `PositionState`.

### Out of Scope

1. Изменение логики расчёта метрик позиции (PnL, fees, APR и т. д.).
2. Миграция исторических данных вне формата ключей baseline.
3. Любые изменения бизнес-логики вне tracker-модуля.

## 4. Нефункциональные и fail-safe требования

### 4.1 Совместимость с текущим fail-safe контрактом

Обязательное требование: поведение fail-safe остаётся неизменным для всей системы.

1. Сигнал `ENTRY_BASELINE_MISSING` сохраняется в прежнем виде и семантике.
2. При RPC-ошибках реализуется деградация: ошибка одной сети не должна приводить к падению полного цикла чтения.
3. Обработчик агрегирует частично успешные результаты и возвращает доступные `PositionState`.

### 4.2 Деградация при RPC-ошибках

Для каждой сети отдельно:

1. Reader перехватывает транспортные/таймаут/JSON-RPC ошибки.
2. Ошибка сети логируется с chain-id/chain-name и причиной.
3. Обработка продолжается для остальных сетей.
4. Итоговый статус цикла: success-with-degradation, если хотя бы одна сеть успешно обработана.

Если недоступны все сети, цикл завершается контролируемой ошибкой верхнего уровня без нарушения формата диагностики.

## 5. Конфигурация `execution.chains`

Вводится обязательная секция конфигурации multi-chain:

```yaml
execution:
  chains:
    base:
      rpc_url: https://...
      coingecko_platform_id: base
      uniswap_v3:
        factory_proxy: "0x..."
        position_manager_proxy: "0x..."
    optimism:
      rpc_url: https://...
      coingecko_platform_id: optimism
      uniswap_v3:
        factory_proxy: "0x..."
        position_manager_proxy: "0x..."
    arbitrum:
      rpc_url: https://...
      coingecko_platform_id: arbitrum-one
      uniswap_v3:
        factory_proxy: "0x..."
        position_manager_proxy: "0x..."
    hypeevm:
      rpc_url: https://...
      coingecko_platform_id: <to-be-confirmed>
      uniswap_v3:
        factory_proxy: "0x..."
        position_manager_proxy: "0x..."
```

### 5.1 Требования к полям

Для каждой сети обязательны:

1. `rpc_url` — endpoint RPC для чтения состояния.
2. `coingecko_platform_id` — идентификатор платформы для ценового слоя.
3. `uniswap_v3.factory_proxy` — proxy-адрес factory.
4. `uniswap_v3.position_manager_proxy` — proxy-адрес manager.

### 5.2 Правила валидации

1. Сеть считается активной только при наличии полного набора обязательных полей.
2. Неполная конфигурация сети исключает сеть из цикла с предупреждением в логах.
3. Исключение сети из-за конфигурации не влияет на обработку остальных сетей.

## 6. Рефакторинг reader-архитектуры

### 6.1 Целевое выделение базового класса

Предлагается выделить абстракцию `BaseUniswapV3PositionReader`.

Ответственность базового класса:

1. Общий пайплайн чтения и нормализации позиции.
2. Обработка типовых RPC-ошибок и fail-safe деградации.
3. Унифицированный контракт выхода в `PositionState`.

Chain-специфичные параметры передаются через конфиг:

1. `chain_name`
2. `rpc_url`
3. `factory_proxy`
4. `position_manager_proxy`
5. `coingecko_platform_id`

### 6.2 Совместимость с текущим Arbitrum-ридером

Текущий Arbitrum reader становится частным случаем per-chain параметризации.

Ожидаемая миграция:

1. Либо переименовать текущий reader в chain-adapter на базе нового класса.
2. Либо оставить thin-wrapper, который инициализирует базовый reader параметрами Arbitrum.

Оба варианта допустимы, если сохраняются текущие fail-safe семантики.

## 7. Схема ключей baseline-хранилища

Файл baseline-хранилища: `position_entry_baselines.json`.

Для исключения коллизий между сетями вводится chain-aware ключ:

`<chain>:uni-v3:<token_id>`

Примеры:

- `base:uni-v3:123`
- `optimism:uni-v3:456`
- `arbitrum:uni-v3:789`
- `hypeevm:uni-v3:999`

### 7.1 Обратная совместимость ключей

1. Для существующих single-chain записей допускается миграционный fallback только на этапе чтения.
2. Все новые записи должны создаваться строго в chain-aware формате.
3. При отсутствии baseline для новой цепочки сохраняется текущая ошибка `ENTRY_BASELINE_MISSING`.

## 8. Агрегация в `main.py`

`main.py` должен собирать данные по всем активным сетям и формировать единый список `PositionState`.

Целевой поток:

1. Загрузить `execution.chains`.
2. Для каждой валидной сети создать chain-сконфигурированный reader.
3. Выполнить чтение позиций сети.
4. Объединить результаты всех сетей в один список `PositionState`.
5. Передать итоговый список в существующий downstream pipeline без изменения контракта.

Требования к агрегации:

1. Порядок в итоговом списке детерминирован (например, по chain-name, затем token_id).
2. Ошибки отдельных сетей не блокируют добавление успешно прочитанных состояний.
3. Диагностика должна позволять определить сеть-источник каждого `PositionState`.

## 9. План внедрения

1. Добавить schema/валидацию `execution.chains`.
2. Вынести общий функционал в `BaseUniswapV3PositionReader`.
3. Подключить per-chain инстанцирование reader в orchestration-слое.
4. Перевести baseline-ключи на chain-aware формат.
5. Обновить `main.py` на multi-chain агрегацию `PositionState`.
6. Проверить fail-safe сценарии: baseline missing и частичная RPC-деградация.

## 10. Критерии приёмки

1. Все 4 сети (Base, Optimism, Arbitrum, HypeEVM) могут быть заданы в `execution.chains`.
2. При отказе одной сети остальные продолжают выдавать `PositionState`.
3. Ошибка `ENTRY_BASELINE_MISSING` не изменена по названию и семантике.
4. Baseline-ключи поддерживают уникальность между сетями.
5. `main.py` возвращает единый список `PositionState` для downstream-обработки.

## 11. Риски и меры

1. **Риск:** несогласованность proxy-адресов по сетям.  
   **Мера:** жёсткая валидация конфигурации и early-warning в логах.
2. **Риск:** неизвестный/нестабильный `coingecko_platform_id` для HypeEVM.  
   **Мера:** явный статус `<to-be-confirmed>` и блокирующая проверка перед production.
3. **Риск:** регресс по fail-safe при рефакторинге.  
   **Мера:** обязательные интеграционные сценарии на частичный RPC-failure и baseline missing.
