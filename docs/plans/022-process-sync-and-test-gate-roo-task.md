# Roo Task: Process Sync + Test Gate Hardening (P0)

Status: TODO  
Owner: Tech Lead -> RooCode  
Date: 2026-03-02  
Priority: P0  
Related:
- `ROADMAP.md`
- `docs/runbooks/LP_OS_Prompt_NewChat.md`
- `docs/runbooks/LP_OS_ТехЗадание_v1.1.md`
- `docs/memory-bank/activeContext.md`
- `docs/memory-bank/progress.md`
- `docs/memory-bank/systemPatterns.md`

## 1. Цель

Убрать рассинхронизацию между roadmap, LP_OS документацией, Memory Bank и фактическим состоянием кода, а также сделать тестовый gate строгим (без тихих пропусков async-тестов).

## 2. Scope (обязательно)

1. Документация:
- синхронизировать статусы DoD в `LP_OS_ТехЗадание_v1.1.md` с фактическим статусом в `ROADMAP.md` и runtime;
- убрать ложные "выполнено", где нет подтверждённого evidence.

2. Memory Bank:
- обновить `activeContext.md`, `progress.md`, `systemPatterns.md` только по фактическому состоянию;
- не добавлять "completed" без проверяемого результата.

3. Тестовый gate:
- добавить `pytest.ini` со strict-конфигурацией маркеров;
- зарегистрировать `asyncio` marker;
- исключить `PytestUnknownMarkWarning` для `@pytest.mark.asyncio`.

4. README:
- заменить шаблонный README на актуальное краткое описание проекта, модулей и команд запуска/тестов.

## 3. Out of scope (запрещено)

- Никаких изменений runtime-бизнес-логики (`main.py`, `src/defi_agents/*`) в этом таске.
- Никаких infra-изменений (VPS/systemd/secrets/GitHub settings).
- Никаких commit/push.

## 4. Ограничения выполнения

- Работать только в `~/projects/defi_agents`.
- Минимальные и точечные правки.
- Не переписывать большие документы целиком, только противоречивые фрагменты.
- Сохранять fail-safe формулировки и текущую терминологию (`reader-only`, `Gate-3`, `Hyperliquid + GMX`).

## 5. Файлы для правок

Обязательно:
- `docs/runbooks/LP_OS_ТехЗадание_v1.1.md`
- `docs/memory-bank/activeContext.md`
- `docs/memory-bank/progress.md`
- `docs/memory-bank/systemPatterns.md`
- `README.md`
- `pytest.ini` (новый файл)

Опционально:
- `docs/plans/INDEX.md` (если нужен индексный линк)

## 6. Acceptance Criteria (DoD)

- Нет противоречий по статусу Phase 3.0 между:
  - `ROADMAP.md`,
  - `LP_OS_Prompt_NewChat.md`,
  - `LP_OS_ТехЗадание_v1.1.md`,
  - Memory Bank файлами.
- В `LP_OS_ТехЗадание_v1.1.md` DoD-флаги соответствуют фактическому статусу (никаких ложных `✅`).
- `pytest -q` больше не выводит `PytestUnknownMarkWarning` по `asyncio`.
- `make test` проходит.

## 7. Команды верификации (обязательно приложить в отчёте)

```bash
cd /home/dmitrii/projects/defi_agents
git status --short --branch
rg -n "DoD Фазы 0|P&L совпадает|mock_positions|reader-only|Hyperliquid|GMX|binance_perpetual" ROADMAP.md docs/runbooks docs/memory-bank
pytest -q
make test
```

## 8. Формат отчёта RooCode

1. Summary (3-6 пунктов)
2. Что изменено (по файлам)
3. Почему изменения корректны
4. Команды и результаты
5. Риски / что не проверено
6. Рекомендованный commit message (без commit)
