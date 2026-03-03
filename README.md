# DeFi Agents

Репозиторий для **Universal DeFi Agent**: мониторинг, оценка и автоматизация DeFi-позиций с fail-safe подходом, reader-only критическими путями и staged rollout (`PAPER -> SHADOW -> LIVE`).

## Назначение

- Поиск и оценка DeFi-возможностей (Scout + risk/freshness).
- Мониторинг существующих позиций и состояния execution/hedger контуров.
- Подготовка и оркестрация execution-интентов через адаптеры с policy-gate.
- Операторская дисциплина через runbooks, планы и Memory Bank.

## Основные модули

- `main.py` — основной цикл Sentinel.
- `src/defi_agents/scout/` — discovery, фильтрация, скоринг кандидатов.
- `src/defi_agents/freshness/` — re-check свежести/дивергенции данных.
- `src/defi_agents/security/` — security screening и policy tags.
- `src/defi_agents/execution/` — trigger/policy/orchestrator/adapter слой.
- `src/defi_agents/tracker/` — reader-only state source и метрики позиций.
- `src/defi_agents/hedger/` + `hedger_main.py` — изолированный hedger worker (PAPER/SHADOW).
- `tests/` — регрессионный pytest-набор.

## Запуск

```bash
make setup
make run
```

Для hedger worker:

```bash
make hedger-run
```

## Тестирование

```bash
pytest -q
make test
```

`pytest.ini` включает strict markers и регистрирует `asyncio` marker, чтобы test gate падал на неизвестных маркерах и не допускал тихих предупреждений по async-тестам.
