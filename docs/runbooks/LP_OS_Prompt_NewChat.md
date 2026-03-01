# LP Operating System — Контекст проекта для нового чата

Ты работаешь как **техлид и старший DeFi-разработчик** на проекте LP Operating System. Ниже полный контекст — прочитай внимательно перед тем как начинать работу.

---

## Что мы строим

**LP Operating System** — персональная платформа для профессионального управления позициями ликвидности в DeFi. Владелец = единственный пользователь на старте. Разработка ведётся через AI-агентов (Google Antigravity, ChatGPT Codex, Claude, Gemini).

Четыре слоя:
- **Слой 0 — Tracker:** реальные позиции, P&L, HODL benchmark, Journal
- **Слой 1 — Intelligence:** сканер пулов, скоринг, оптимизатор диапазонов, anomaly detector
- **Слой 2 — Position Manager:** Zap In/Out, ручное управление
- **Слой 3 — Automation:** compound, rebalance, IL protection bot
- **Слой 4 — Alerts:** Telegram-бот

---

## Технологический стек

**Backend:** Python + FastAPI (монолит), Celery + Redis (очередь), PostgreSQL + TimescaleDB, Alembic  
**Frontend:** Next.js 14 + TypeScript, shadcn/ui + TailwindCSS, TanStack Query, Wagmi + viem  
**Структура:** `/app/chains/`, `/app/protocols/`, `/app/intelligence/`, `/app/tracker/`, `/app/position_manager/`, `/app/automation/`, `/app/alerts/`, `/app/api/`, `/app/workers/`, `/app/db/`

**Принцип адаптера:** каждая сеть = один файл наследующий BaseEVM. Каждый протокол = один файл реализующий BaseProtocol. Новый протокол не трогает остальной код.

---

## Сети и протоколы

**Фаза 0 (сейчас):** Arbitrum — Uniswap v3  
**Фаза 0.5:** Base, BSC, Optimism, Polygon, Avalanche + PancakeSwap v3, Aerodrome, Velodrome, Curve v2, SushiSwap v3  
**Фаза 1.5:** Solana (Orca + Raydium + Helius), HyperEVM  
**Не используем:** Ethereum mainnet (gas нерентабелен для активного LP)  
**Заглушка:** Uniswap v4 (экосистема не созрела — файл есть, код пустой)

**DEX агрегаторы:** 1inch Fusion v6 (все EVM), Jupiter v6 (Solana)  
**Perp для hedge:** Hyperliquid (основной), GMX v2 (fallback для Arbitrum)

---

## Существующий код (Spec 018 / Plan 020)

Это **часть того же проекта**. Уже реализовано:

### ExecutionOrchestrator (`src/defi_agents/execution/orchestrator.py`)
Flow: `trigger → policy_check → build_tx_plan → simulate → execute`

Три режима:
- `PAPER` — только plan, без simulate/execute (строка 54)
- `SHADOW` — simulate есть, execute нет (строка 65)  
- `LIVE` — simulate + execute (строка 68)

### Адаптеры (рекомендуется переименовать):
| Текущее имя | Новое имя | Роль |
|---|---|---|
| `native_uniswap_v3` | `uniswap_v3_simulate` | PAPER/SHADOW baseline + calldata builder + fallback |
| `native_uniswap_v3_live` | `uniswap_v3_live` | LIVE transport: eth_sendRawTransaction |
| `v3utils` | `v3utils_live` | V3Utils calldata + live transport |
| `krystal` | `krystal_reader` | Переместить в /reader/ — только read-only данные |

### PolicyGuard (`src/defi_agents/execution/policy.py`)
Параметры (SSOT `scout_config.json`):
```
max_gas_usd_per_tx = 15.0
max_slippage_bps   = 100   (1%)
max_daily_txs      = 10
max_daily_gas_usd  = 100.0
min_expected_net_usd = 2.0
kill_switch        = false
```
Kill-switch сейчас — ручной флаг в конфиге. **Нужно добавить Telegram команду `/killswitch on|off`** (фаза 1).

### TriggerEngine (`src/defi_agents/execution/triggers.py`)
Триггеры: `OUT_OF_RANGE`, `LOW_RANGE_UTILIZATION`, `EDGE_DECAY`, `COMPOUND_DUE`

⚠️ **КРИТИЧНО:** TriggerEngine сейчас работает на `mock_positions` (`main.py:185`, `main.py:907`). Это главная проблема — весь execution pipeline без реальных данных. **Первая задача — заменить mock_positions на Real Position Reader.**

### Scheduler
Сейчас: systemd timer раз в 15 минут (`deploy/systemd/defi-sentinel.timer`).  
Нужно: снизить до 5 мин для execution decisions + отдельный asyncio loop каждые 30-60 сек для price monitoring.

### Hedger PoC (Plan 020)
- 88 циклов за 24ч, sim_ok=176, sim_fail=0, connector_errors=0
- Текущий connector: `hummingbot-shadow-mock` (абстрактный мок)
- **ИЗМЕНЕНИЕ:** следующий шаг — Hyperliquid testnet коннектор (НЕ Binance Futures sandbox как было в плане)
- LIVE для hedger прямо запрещён в Spec 020 до завершения тестирования

### Gate-3 Canary (условия перехода в LIVE)
Все условия обязательны:
- [ ] SHADOW стабильность ≥ 48ч без ошибок
- [ ] Real Position Reader подключён (не mock)
- [ ] Dedicated hot wallet настроен и протестирован
- [ ] PolicyGuard проверен на тестовых транзакциях
- [ ] ≥ 3 успешных LIVE canary tx с receipt
- [ ] Telegram /killswitch работает

---

## Signing Flow

**Два кошелька:**
- **Main wallet (MetaMask):** основной капитал, ручные операции, новые позиции
- **Keeper wallet (hot):** автоматический compound/rebalance через keeper

**Keeper wallet требования:**
- Отдельный адрес, никогда не main wallet
- Минимальный баланс: только gas reserve (0.01–0.05 ETH на Arbitrum)
- Ключ: `KEEPER_PRIVATE_KEY` в `.env` (переменная окружения, не в коде)
- Ротация ключа каждые 90 дней

```python
# LIVE mode signing
private_key = os.environ['KEEPER_PRIVATE_KEY']
signed_tx   = web3.eth.account.sign_transaction(tx_plan.raw, private_key)
tx_hash     = uniswap_v3_live.execute(signed_tx.rawTransaction)
receipt     = web3.eth.wait_for_transaction_receipt(tx_hash)
```

---

## Glossary — термины P&L (ОБЯЗАТЕЛЬНО использовать точно)

| Термин | Определение |
|---|---|
| `entry_value_usd` | entry_amount_token0 × price0_at_open + entry_amount_token1 × price1_at_open |
| `current_value_usd` | current_amount × price_now для обоих токенов |
| `hodl_value_usd` | entry_amount × price_now (что было бы без LP) |
| `gross_il_usd` | current_value − hodl_value. ВСЕГДА показывать как "Gross IL (без fees)" |
| `fees_earned_usd` | Сумма всех fee_collect событий в USD |
| `gas_spent_usd` | gasUsed × gasPrice × ETH/USD на момент каждой tx |
| `net_pnl_usd` | current_value + fees_earned − entry_value − gas_spent |
| `pnl_vs_hodl_usd` | net_pnl − (hodl_value − entry_value) — главная метрика |
| `fee_apr` | fees_earned / entry_value / days × 365 |

---

## Матрица Chain → Router

| Сеть | Primary | Fallback |
|---|---|---|
| Arbitrum | 1inch Fusion v6 | Paraswap v5 |
| Base | 1inch Fusion v6 | 0x API |
| BSC | 1inch Fusion v6 | PancakeSwap Router |
| Optimism | 1inch Fusion v6 | Paraswap v5 |
| Polygon | 1inch Fusion v6 | Paraswap v5 |
| Avalanche | 1inch Fusion v6 | Trader Joe Router |
| Solana | Jupiter v6 | Raydium direct |
| HyperEVM | HyperLiquid DEX | Raw router call |

**Fallback правило:** primary недоступен ИЛИ price_impact > max_slippage_bps → fallback → если оба недоступны → NO_ACTION + алерт + reason_code.

---

## Stale Data Guard

| Условие | Флаг | Действие |
|---|---|---|
| Данные о позиции > 2 мин | `STALE_POSITION_DATA` | Блокировать LIVE execution |
| CoinGecko недоступен > 5 мин | `STALE_PRICE` | ⚠️ в UI, cached цена |
| RPC chain недоступен > 5 мин | `CHAIN_DEGRADED` | Пауза автоматики по сети + алерт |
| Subgraph отстаёт > 10 блоков | `SUBGRAPH_LAG` | Переключиться на direct RPC |
| История < 14 дней для optimizer | `INSUFFICIENT_HISTORY` | Не запускать, вернуть предупреждение |

**Backoff при ошибках RPC:** 0с → 5с → 15с → 60с → CHAIN_DEGRADED + алерт

---

## Главный экран дашборда

Три блока на первом экране после входа:
1. **Portfolio Summary:** total Net P&L ($, %), P&L vs HODL, total fees, кол-во позиций, gas spent
2. **Positions:** карточки каждой позиции со статусом (✅ in_range / ⚠️ near_edge / 🔴 out_of_range), Net P&L, Fee APR. Out_of_range — вверху.
3. **Opportunity Cost:** топ-3 пула с лучшим Net APY + "переход окупится через X дней". Обновление каждый час.

---

## Текущие фазы разработки

```
Фаза 0    (2–3 нед.) — Real Position Reader (Arbitrum + Uni v3, замена mock_positions)
                       Tracker: P&L, HODL, IL, Journal
                       Базовый дашборд

Фаза 0.5  (3–4 нед.) — Intelligence: сканер, оптимизатор диапазонов, anomaly detector
                       Opportunity Cost Dashboard
                       Расширение сетей и протоколов

Фаза 1    (2–3 нед.) — Telegram-бот: алерты + команды
                       Kill-switch через Telegram
                       Dedicated hot wallet + signing flow

Фаза 1.5  (3–4 нед.) — Zap In/Out (Position Manager)
                       Solana + HyperEVM адаптеры
                       Gate-3 canary → LIVE compound + rebalance

Фаза 2    (3–4 нед.) — Полная автоматизация (compound + rebalance + auto-exit)
                       IL Bot: Range Shift стратегия
                       Gas Optimizer

Фаза 2.5  (3–4 нед.) — Hyperliquid testnet → LIVE hedger
                       IL Bot: Delta Hedge
                       Liquidation guard
```

**Критический путь:** Real Position Reader → Gate-3 canary → LIVE execution

---

## Текущая задача (Фаза 0)

**Цель:** Заменить `mock_positions` в `main.py` на Real Position Reader для Arbitrum + Uniswap v3.

**Что должен делать Position Reader:**
1. Подключиться к кошельку (адрес из `.env`)
2. Получить все NFT позиции через `NonfungiblePositionManager` (Arbitrum)
3. Для каждой позиции: `tick_lower`, `tick_upper`, `liquidity`, `token0`, `token1`
4. Получить `slot0` пула → `current_price`, `current_tick`
5. Получить `feeGrowth + tokensOwed` → накопленные fees
6. Определить статус: `in_range` если `tickLower ≤ currentTick ≤ tickUpper`
7. Заменить `mock_positions` в `main.py:185` и `main.py:907`

**Источники данных:**
- Позиции: Alchemy NFT API / `eth_call NonfungiblePositionManager`
- Цена пула: `eth_call slot0()` напрямую (TTL: 10 сек)
- Fees: `eth_call positions()` напрямую (TTL: 60 сек)
- История tx: Alchemy Transaction API (разовый импорт)
- Исторические цены: CoinGecko Historical API по timestamp tx

**DoD Фазы 0:**
- [ ] mock_positions заменён реальным reader
- [ ] P&L совпадает с ручным расчётом на ≥ 3 реальных позициях (отклонение < 1%)
- [ ] HODL benchmark считается корректно
- [ ] Statuse in/out_of_range обновляется в реальном времени
- [ ] Stale data guard работает
- [ ] Главный экран дашборда показывает реальные данные

---

## Правила работы с кодом

1. **Не дублировать существующее.** Orchestrator, PolicyGuard, TriggerEngine — они есть, интегрируемся с ними.
2. **Каждый модуль — изолированный контекст.** Изменения в `/tracker/` не должны трогать `/intelligence/`.
3. **Stale data guard** — перед любым LIVE исполнением проверять свежесть данных.
4. **Reason codes** — всегда логировать `PolicyDecision.reason_codes` при отказе.
5. **NO_ACTION при деградации** — если данные неполные или роутер недоступен → не исполнять, алертить.
6. **Adapter pattern** — новый протокол = новый файл наследующий BaseProtocol. Ничего больше.
7. **Переименование адаптеров** — при первом касании кода переименовать: `native_uniswap_v3` → `uniswap_v3_simulate`, `native_uniswap_v3_live` → `uniswap_v3_live`.

---

## Ключевые документы проекта

- `docs/specs/018-lp-autocompound-autorebalance-v1.md` — Spec execution layer
- `docs/plans/018-lp-autocompound-autorebalance-v1-plan.md` — Plan с Gate-3
- `docs/specs/020-delta-hedger-poc-v1.md` — Spec hedger (LIVE запрещён)
- `docs/plans/020-delta-hedger-hummingbot-poc-plan.md` — Plan hedger (обновить: Binance → Hyperliquid)
- `docs/runbooks/execution-loop-rollout-v1.md` — 24h shadow gate операционная дисциплина
- `docs/memory-bank/scout_config.json:359` — SSOT параметры PolicyGuard
- `LP_OS_ТехЗадание_v1.1.docx` — Полное актуальное ТЗ

---

Что делаем дальше?
