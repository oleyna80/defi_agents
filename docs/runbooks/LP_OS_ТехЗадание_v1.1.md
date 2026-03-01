__LP OPERATING SYSTEM__

Техническое задание  v1\.1

Обновление: интеграция существующих наработок \(Spec 018 / Plan 020\)

__Версия__

__1\.1__

__Статус__

__Актуально__

__Дата__

__Февраль 2026__

__Изменения относительно v1\.0__

✦ Добавлен раздел: Существующие компоненты \(Spec 018 / Plan 020\) — маппинг кода на слои

✦ Добавлен раздел: Gate Architecture \(PAPER / SHADOW / LIVE\) — стандарт rollout

✦ Добавлен раздел: Signing Flow — dedicated hot wallet для keeper

✦ Обновлён раздел 7\.3: Hedger venue → Hyperliquid \(вместо Binance Futures\)

✦ Обновлён раздел 11: Фазы — с учётом критического пути через mock\_positions

✦ Добавлена: Глоссарий терминов P&L / IL

✦ Добавлена: Матрица chain → router с fallback

✦ Добавлены: DoD\-чеклисты для каждой фазы

✦ Добавлены: Security model по фазам, stale data guard, backoff rules

✦ Добавлен: Дизайн главного экрана дашборда

# __1\. Обзор и контекст__

## __1\.1 Что строим__

LP Operating System — персональная платформа для профессионального управления позициями ликвидности\. Четыре слоя: Intelligence \(найти лучшее место\), Tracker \(понять где ты и сколько заработал\), Position Manager \(открыть/закрыть/изменить\), Automation \(делать правильные вещи автоматически\)\.

## __1\.2 Статус на момент v1\.1__

Execution\-ядро уже построено в рамках Spec 018 / Plan 020\. ТЗ v1\.1 интегрирует существующие наработки и устраняет расхождения\.

__Слой__

__Статус__

__Ключевые компоненты__

Слой 3: Automation \(ядро\)

🟡 Частично готов

ExecutionOrchestrator, PolicyGuard, TriggerEngine — PAPER/SHADOW

Слой 3: Hedger

🟡 PoC / Shadow

hummingbot\-shadow\-mock, 88 циклов без ошибок за 24ч

Слой 0: Tracker

❌ Не начат

Работает на mock\_positions — критический путь

Слой 1: Intelligence

❌ Не начат

Сканер, скоринг, оптимизатор диапазонов

Слой 2: Position Manager

❌ Не начат

Zap In/Out, signing flow

Слой 4: Alerts

❌ Не начат

Telegram\-бот, алерты, команды

## __1\.3 Глоссарий терминов P&L__

Чёткие определения — обязательны\. Путаница в терминах ломает доверие к цифрам\.

__Термин__

__Определение__

__Знак__

entry\_value\_usd

Стоимость входа: entry\_amount\_token0 × price0\_at\_open \+ entry\_amount\_token1 × price1\_at\_open

—

current\_value\_usd

Текущая стоимость: current\_amount\_token0 × price0\_now \+ current\_amount\_token1 × price1\_now

—

hodl\_value\_usd

HODL benchmark: entry\_amount\_token0 × price0\_now \+ entry\_amount\_token1 × price1\_now\. Сколько стоило бы просто держать токены

—

gross\_il\_usd

Gross IL = current\_value\_usd − hodl\_value\_usd\. Чистые потери от LP vs HODL\. БЕЗ учёта fees

≤ 0

fees\_earned\_usd

Накопленные комиссии: сумма всех fee\_collect событий в USD по цене на момент сбора

≥ 0

gas\_spent\_usd

Все газ\-затраты: открытие \+ compound \+ rebalance \+ закрытие\. gasUsed × gasPrice × ETH/USD на момент tx

≥ 0

net\_pnl\_usd

Итоговый P&L = current\_value \+ fees\_earned − entry\_value − gas\_spent

\+/−

pnl\_vs\_hodl\_usd

Добавленная стоимость LP = net\_pnl\_usd − \(hodl\_value\_usd − entry\_value\_usd\)

\+/−

fee\_apr

Fee APR = fees\_earned\_usd / entry\_value\_usd / days × 365

—

__Важно__

gross\_il\_usd всегда показывается как 'Gross IL \(без fees\)' в UI — чтобы не путать с net результатом\.

pnl\_vs\_hodl — главная метрика: показывает реальную добавленную стоимость от LP\-стратегии\.

Для Solana: gas\_spent\_usd ≈ 0 \(< $0\.001 на tx\)\. В отчётах показываем но не учитываем в рейтинге\.

# __2\. Существующие компоненты \(Spec 018 / Plan 020\)__

Этот раздел документирует то что уже построено\. Новые модули должны интегрироваться с этими компонентами, а не дублировать их\.

## __2\.1 Execution Pipeline__

Файл: src/defi\_agents/execution/orchestrator\.py

__Полный flow__

trigger → policy\_check → build\_tx\_plan → simulate → execute

Режимы исполнения:

  PAPER   — только build tx\-plan, без simulate/execute \(строки 54\)

  SHADOW  — simulate есть, execute нет \(строки 65\)

  LIVE    — simulate \+ execute \(строки 68\)

## __2\.2 Адаптеры исполнения__

Три адаптера с разными ответственностями \(рекомендуемые новые имена\):

__Текущее имя__

__Рекомендуемое имя__

__Ответственность__

__LIVE capable__

native\_uniswap\_v3

uniswap\_v3\_simulate

PAPER/SHADOW baseline, calldata builder, fallback в цепочке

❌ LIVE\_EXECUTION\_NOT\_IMPLEMENTED

native\_uniswap\_v3\_live

uniswap\_v3\_live

LIVE transport: eth\_sendRawTransaction, принимает signed\_raw\_tx

✅

v3utils

v3utils\_live

Calldata builder для V3Utils контракта \+ live transport от uniswap\_v3\_live

✅

krystal

krystal\_reader

Read\-only: парсинг позиций и данных\. Перемещён из execution в data/reader слой

❌ Перемещён

__Рефакторинг__

Переименование — 10 минут работы, но сильно снижает когнитивную нагрузку для агентов\.

Krystal adapter: убрать из execution chain, переместить в /reader/krystal\_reader\.py как источник данных о позициях\.

Объединять адаптеры НЕ нужно — у каждого своя ответственность\.

## __2\.3 PolicyGuard__

Файл: src/defi\_agents/execution/policy\.py — SSOT для всех параметров исполнения\.

__Параметр__

__Текущее значение__

__Описание__

__Изменить в фазе__

max\_gas\_usd\_per\_tx

$15\.0

Максимальный газ на одну транзакцию

—

max\_slippage\_bps

100 \(1%\)

Максимальный slippage

—

max\_daily\_txs

10

Максимум транзакций в сутки

Фаза 2: поднять до 20

max\_daily\_gas\_usd

$100\.0

Дневной бюджет на газ

—

min\_expected\_net\_usd

$2\.0

Минимальный ожидаемый net доход с операции

—

kill\_switch

false

Полная остановка всей автоматизации

Фаза 1: добавить Telegram /killswitch

__Kill\-switch через Telegram \(добавить в Фазе 1\)__

Сейчас kill\_switch — ручное изменение конфига\. В аварийной ситуации это медленно\.

Добавить команду /killswitch on|off в Telegram\-бот с немедленным эффектом\.

При kill\_switch=true: keeper не исполняет ничего, только мониторит и алертит\.

## __2\.4 TriggerEngine__

Файл: src/defi\_agents/execution/triggers\.py — условия запуска автоматических действий\.

__Триггер__

__Условие__

__Действие__

OUT\_OF\_RANGE

Цена вышла за \[tickLower, tickUpper\]

Ребалансировка

LOW\_RANGE\_UTILIZATION

Позиция в диапазоне но < X% time utilization за N дней

Расширение диапазона

EDGE\_DECAY

Цена в X% от границы диапазона

Превентивная ребалансировка

COMPOUND\_DUE

fees\_earned\_usd > gas\_cost × 3 ИЛИ fees > $50 ИЛИ 24ч

Compound

⚠️  Сейчас TriggerEngine работает на mock\_positions\. Первый приоритет \(Фаза 0\) — подключить Real Position Reader\.

## __2\.5 Hedger PoC \(Plan 020\)__

__Параметр__

__Значение__

Shadow gate результат

88 циклов за 24ч, sim\_ok=176, sim\_fail=0, connector\_errors=0

Текущий connector

hummingbot\-shadow\-mock \(абстрактный, не реальная биржа\)

Запланированный venue

Binance Futures sandbox → ИЗМЕНИТЬ на Hyperliquid testnet \(см\. раздел 7\.3\)

LIVE статус

Прямо запрещён в Spec 020 \(только PAPER/SHADOW\)

# __3\. Gate Architecture — PAPER / SHADOW / LIVE__

Стандарт rollout для всех новых компонентов автоматизации\. Каждый новый модуль проходит все три gate последовательно\.

## __3\.1 Три режима__

__Режим__

__Что происходит__

__Когда переходить__

PAPER

Только расчёт tx\-plan\. Нет simulate, нет execute\. Логируем что 'сделали бы'\.

Старт любого нового модуля

SHADOW

Simulate \(eth\_call\) без отправки в сеть\. Проверяем что tx технически корректна\.

После 24ч PAPER без ошибок

LIVE

Simulate \+ execute\. Реальные транзакции\. PolicyGuard как pre\-trade gate\.

После Gate\-3 canary \(см\. ниже\)

## __3\.2 Gate\-3 Canary — условия перехода в LIVE__

Gate\-3 — последний барьер перед реальным исполнением\. Должны быть выполнены все условия:

__Условие__

__Метрика__

__Порог__

SHADOW стабильность

Циклы без ошибок в SHADOW mode

≥ 48ч, 0 ошибок

Real state source

Position reader подключён к реальным данным \(не mock\)

✅ Обязательно

Signing path

Dedicated hot wallet настроен и протестирован

✅ Обязательно

PolicyGuard

Все параметры проверены на тестовых транзакциях

✅ Обязательно

Canary позиция

Первый LIVE compound/rebalance на минимальной позиции

≥ 3 успешных tx с receipt

Kill\-switch

Telegram /killswitch работает и протестирован

✅ Обязательно

## __3\.3 Scheduler__

Текущий: systemd timer раз в 15 минут \(defi\-sentinel\.timer\)\.

Для Фазы 0–1 это приемлемо\. Для Фазы 1\.5\+ \(LIVE\) нужно снизить до 5 минут для execution decisions и добавить отдельный лёгкий loop для price monitoring:

__Loop__

__Интервал__

__Что делает__

__Реализация__

Price monitor

30–60 сек

Проверка in/out of range, update Redis cache, триггер алертов

Лёгкий asyncio loop

Execution decisions

5 мин

TriggerEngine check, PolicyGuard, запуск compound/rebalance

systemd timer → снизить до 5 мин

Analytics jobs

1 час

Пересчёт APY, opportunity cost, anomaly detection

Celery beat

Daily digest

24 часа

P&L summary, whale activity, reward token metrics

Celery beat

# __4\. Signing Flow — Управление ключами__

Критический раздел\. Сейчас native\_uniswap\_v3\_live ожидает signed\_raw\_tx в metadata — источник подписи не задокументирован\. Устраняем этот gap\.

## __4\.1 Два кошелька — два назначения__

__Кошелёк__

__Назначение__

__Где хранится ключ__

__Лимиты__

Main wallet \(MetaMask\)

Основной капитал, открытие новых позиций вручную, крупные операции

MetaMask \(браузер\)

Нет автоматики

Keeper wallet \(hot\)

Автоматический compound и rebalance через keeper

\.env на сервере \(зашифрован\)

PolicyGuard caps

## __4\.2 Keeper Wallet — требования безопасности__

- Отдельный адрес — никогда не использовать main wallet для автоматики
- Минимальный баланс: только gas reserve\. На Arbitrum: 0\.01–0\.05 ETH достаточно
- Approve только нужным контрактам \(Uniswap NonfungiblePositionManager, V3Utils\)
- PolicyGuard daily caps — первая линия защиты от злоупотреблений
- Ключ в \.env: KEEPER\_PRIVATE\_KEY — переменная окружения, не в коде
- Rotation plan: смена ключа каждые 90 дней или при любом подозрении на компрометацию

## __4\.3 Signing Flow в коде__

\# PAPER / SHADOW mode \(без реального ключа\)

tx\_plan = adapter\.build\_tx\_plan\(position, action\)

sim\_result = adapter\.simulate\(tx\_plan\)  \# eth\_call, ключ не нужен

\# LIVE mode

tx\_plan = adapter\.build\_tx\_plan\(position, action\)

sim\_result = adapter\.simulate\(tx\_plan\)

if sim\_result\.ok and policy\.check\(tx\_plan\)\.approved:

    private\_key = os\.environ\['KEEPER\_PRIVATE\_KEY'\]

    signed\_tx   = web3\.eth\.account\.sign\_transaction\(tx\_plan\.raw, private\_key\)

    tx\_hash     = uniswap\_v3\_live\.execute\(signed\_tx\.rawTransaction\)

    receipt     = web3\.eth\.wait\_for\_transaction\_receipt\(tx\_hash\)

__Stale data guard__

Перед любым LIVE исполнением: проверить что данные о позиции свежие \(< 2 мин\)\.

Если данные stale — NO\_ACTION \+ алерт\. Не исполнять на устаревших данных\.

Флаг STALE\_POSITION\_DATA в PolicyDecision\.reason\_codes\.

# __5\. Слой 0 — Real Position Reader & Tracker__

__Критический путь__

Real Position Reader = замена mock\_positions в main\.py:185 и main\.py:907\.

Без него невозможен LIVE execution\. Это первое что строим\.

Старт: Arbitrum \(приоритет №1\) → Uniswap v3 → затем расширяем на другие сети\.

## __5\.1 Real Position Reader — что должен делать__

1. Подключиться к кошельку \(адрес из конфига или wallet connect\)
2. Запросить все NFT позиции через Uniswap NonfungiblePositionManager \(Arbitrum\)
3. Для каждой позиции: получить tick\_lower, tick\_upper, liquidity, token0, token1
4. Получить текущий slot0 пула: sqrtPriceX96, tick → вычислить current\_price
5. Получить накопленные fees: positions\(\) → feeGrowth \+ tokensOwed
6. Определить статус: in\_range если tickLower ≤ currentTick ≤ tickUpper
7. Заменить mock\_positions в main\.py на вызов этого reader

## __5\.2 Источники данных по приоритету__

__Данные__

__Источник__

__Fallback__

__TTL кеш__

Позиции кошелька

Alchemy NFT API / eth\_call NonfungiblePositionManager

The Graph subgraph

30 сек

Текущая цена пула

eth\_call slot0\(\) напрямую

CoinGecko

10 сек

Накопленные fees

eth\_call positions\(\) напрямую

The Graph

60 сек

История транзакций

Alchemy Transaction API \(по адресу кошелька\)

Moralis

1 раз при импорте

Исторические цены

CoinGecko Historical API \(по timestamp tx\)

DeFiLlama

Нет TTL \(история\)

## __5\.3 Stale Data Guard__

Правила NO\_ACTION при деградации данных:

__Условие__

__Флаг__

__Действие__

Данные о позиции старше 2 мин

STALE\_POSITION\_DATA

Блокировать LIVE execution

CoinGecko недоступен > 5 мин

STALE\_PRICE

Показывать ⚠️ в UI, использовать cached цену

RPC chain недоступен > 5 мин

CHAIN\_DEGRADED

Приостановить автоматику по сети, алерт

The Graph subgraph отстаёт > 10 блоков

SUBGRAPH\_LAG

Переключиться на direct RPC calls

Optimizer получил < 14 дней истории

INSUFFICIENT\_HISTORY

Не запускать optimizer, вернуть предупреждение

## __5\.4 Backoff Strategy при ошибках RPC__

attempt 1: немедленно

attempt 2: \+5 сек

attempt 3: \+15 сек

attempt 4: \+60 сек

attempt 5: пометить chain как DEGRADED, алерт в Telegram

asyncio\.Semaphore\(max\_concurrent=5\) per chain — защита от rate limit

## __5\.5 Модель данных Position__

__Position \(PostgreSQL\)__

\# Идентификация

id, wallet\_address, protocol, chain, pool\_address, token\_id

token0, token1, fee\_tier, tick\_lower, tick\_upper

\# Вход

opened\_at, entry\_block, entry\_price\_token0\_usd, entry\_price\_token1\_usd

entry\_amount\_token0, entry\_amount\_token1, entry\_value\_usd

\# Текущее состояние \(обновляется каждые 30\-60 сек\)

current\_amount\_token0, current\_amount\_token1

current\_value\_usd, current\_tick, in\_range: bool

fees\_pending\_token0, fees\_pending\_token1  ← ещё не собраны

\# Накопленные данные

fees\_earned\_usd, gas\_spent\_usd, reward\_tokens\_usd

\# Расчётные метрики \(on the fly\)

hodl\_value\_usd, gross\_il\_usd

net\_pnl\_usd, pnl\_vs\_hodl\_usd, fee\_apr

\# Мета

status: active | out\_of\_range | closed

data\_freshness\_at, stale: bool

closed\_at, exit\_value\_usd

## __5\.6 Position Journal__

- Тезис входа — почему открыл позицию
- Стратегия — тип диапазона, планируемая частота ребалансировки
- Целевой APY и условие выхода
- Теги — для фильтрации \(примеры: 'волатильная', 'стейблы', 'новый листинг'\)
- Post\-mortem после закрытия — вывод, оценка решения

## __5\.7 DoD Фазы 0__

__Definition of Done — Фаза 0__

✅ Real Position Reader: подключён к Arbitrum, Uniswap v3

✅ mock\_positions заменён на реальный reader в main\.py

✅ P&L совпадает с ручным расчётом для ≥ 3 реальных позиций \(отклонение < 1%\)

✅ HODL benchmark считается корректно на known positions

✅ Статус in/out\_of\_range обновляется в реальном времени

✅ История транзакций импортирована корректно

✅ Stale data guard работает \(тест: отключить RPC → проверить флаг\)

✅ Dashboard главный экран: сводка портфеля \+ статус позиций \+ opportunity cost

# __6\. Дизайн главного экрана дашборда__

Первый экран после входа\. Три блока: сводка портфеля, статус позиций, opportunity cost\.

## __6\.1 Макет главного экрана__

__MAIN DASHBOARD__

┌─────────────────────────────────────────────────────────────────┐

│  PORTFOLIO SUMMARY                                              │

│  Net P&L: \+$1,247  \(\+12\.4%\)   vs HODL: \+$389   Fees: \+$1,891  │

│  Active: 4 positions   Out of range: 1   Gas spent: $34        │

└─────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────┐  ┌─────────────────────────────┐

│  POSITIONS                       │  │  OPPORTUNITY COST           │

│                                  │  │                             │

│  ✅ ETH/USDC  Arb   \+$423  8\.2%  │  │  🔥 WBTC/ETH Base  42% APY │

│  ✅ WBTC/ETH  Base  \+$198  6\.1%  │  │     Переход окупится: 3 дня │

│  ⚠️  ARB/USDC  Arb  \+$89   4\.2%  │  │                             │

│  🔴 SOL/USDC  Base  OUT   \-$12   │  │  📊 PENDLE/ETH Arb  38% APY │

│                                  │  │     Переход окупится: 5 дней│

└──────────────────────────────────┘  └─────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐

│  ALERTS \(последние 24ч\)                                         │

│  🔴 12:34  SOL/USDC вышла из диапазона \(31 мин назад\)           │

│  🟡 08:15  ETH/USDC: fees $47 — готово к compound               │

└─────────────────────────────────────────────────────────────────┘

## __6\.2 Блок Portfolio Summary__

- Total Net P&L \($\) и \(%\) — главная цифра
- P&L vs HODL — добавленная стоимость LP
- Total fees earned — весь доход от комиссий
- Активные позиции / out of range / закрытые за период
- Total gas spent — для контроля эффективности

## __6\.3 Блок Positions__

- Карточка каждой позиции: пара, сеть, Net P&L, Fee APR
- Статус\-иконка: ✅ in\_range, ⚠️ near\_edge \(< 15% до границы\), 🔴 out\_of\_range
- Сортировка по умолчанию: out\_of\_range вверху, затем по P&L
- Click → детальная страница позиции

## __6\.4 Блок Opportunity Cost__

- Топ\-3 пула с лучшим Net APY из сканера прямо сейчас
- Для каждого: 'Переход окупится через X дней' \(с учётом gas\)
- Обновление каждый час
- Если нет лучших альтернатив — скрывать блок

# __7\. Слой 1 — Intelligence__

## __7\.1 Сканер пулов__

__Параметр__

__Default__

__Описание__

Минимальный TVL

$100k

Пулы с меньшим TVL — слишком высокий slippage

Минимальный возраст

14 дней

Новые пулы — неопределённый volume паттерн

Минимальный audit score

60/100

DeFiLlama audits \+ возраст контракта \+ bug bounty

Тип пары

all

volatile / stable\-correlated / all

Мин\. volume 24h

$50k

Фильтр по активности

## __7\.2 Матрица Chain → Router \(с fallback\)__

SSOT для всех свапов в системе\. Используется в compound, rebalance и Zap In/Out\.

__Сеть__

__Primary Router__

__Fallback__

__Примечание__

Arbitrum

1inch Fusion v6

Paraswap v5

—

Base

1inch Fusion v6

0x API

—

BSC

1inch Fusion v6

PancakeSwap Router

Нативный роутер как fallback

Optimism

1inch Fusion v6

Paraswap v5

—

Polygon

1inch Fusion v6

Paraswap v5

—

Avalanche

1inch Fusion v6

Trader Joe Router

—

Solana

Jupiter v6

Raydium direct

Только Jupiter — нет EVM агрегаторов

HyperEVM

HyperLiquid DEX

Raw router call

Молодая экосистема — мониторим

__Fallback правило__

1\. Запрос к primary router\.

2\. Если недоступен ИЛИ price\_impact > max\_slippage\_bps → fallback router\.

3\. Если оба недоступны или price\_impact > лимита → NO\_ACTION \+ алерт\.

4\. Логировать reason\_code: SWAP\_ROUTER\_UNAVAILABLE или PRICE\_IMPACT\_EXCEEDED\.

## __7\.3 Оптимизатор диапазона__

1. История цен за 30/90 дней из CoinGecko \(OHLCV\)
2. Вероятностное распределение возвратов \(lognormal \+ fat tails\)
3. Поиск \[tickLower, tickUpper\] с максимальным E\[Net APY\] при P\(in\-range\) ≥ threshold
4. Три варианта: Conservative \(80%\), Balanced \(70%\), Degen \(55%\)

__INSUFFICIENT\_HISTORY guard__

Если история < 14 дней → не запускать optimizer\.

Вернуть: \{status: 'INSUFFICIENT\_HISTORY', min\_days: 14, available\_days: N\}

UI показывает предупреждение вместо результата\.

## __7\.4 Anomaly Detector__

__Аномалия__

__Сигнал__

__Флаг__

__Действие__

Wash Trading

High volume \+ minimal price movement \+ circular tx

WASH\_TRADING\_SUSPECTED

⚠️ APY может быть искусственным

Whale Exit

TVL −10% за < 1 час

WHALE\_EXIT\_DETECTED

🔴 Алерт немедленно

Fee Spike

Fee utilization аномально высокий \(> 3σ\)

FEE\_SPIKE\_DETECTED

⚠️ Возможна манипуляция

Reward Dump

Токен наград −15% за 24ч

REWARD\_TOKEN\_DUMPING

⚠️ Реальный APY ниже

Liquidity Thin

Резкое уменьшение depth в диапазоне

LIQUIDITY\_THINNING

⚠️ Повышенный slippage

# __8\. Слой 2 — Position Manager__

## __8\.1 Zap In — Deposit с автоконвертацией__

1. Пользователь: пул, диапазон, входной токен, сумма
2. Система рассчитывает соотношение token0/token1 для диапазона
3. Запрашивает котировку у router \(1inch/Jupiter\) с учётом price impact
4. Итерация если price impact смещает соотношение \(max 3 итерации\)
5. Подготовка транзакции → пользователь подписывает в MetaMask
6. Запись события open в Position History

__No\-custody модель \(Фаза 1\.5\)__

Система готовит tx параметры, пользователь подписывает в MetaMask\.

Для keeper auto\-compound/rebalance — dedicated hot wallet \(Фаза 1\.5\+\)\.

Смарт\-контракт не хранит средства\. Аудит не требуется\.

## __8\.2 Zap Out — Вывод депозита__

__Режим__

__Описание__

Dual token

Вывести оба токена в текущем соотношении позиции \(без свапа\)

Single token

Вывести всё в один выбранный токен \(своп через router\)

Partial

Частичный вывод — указать % от ликвидности

## __8\.3 Ручные команды__

__Команда Telegram__

__Действие__

/compound \[id\]

Немедленный compound \(с подтверждением через inline кнопку\)

/rebalance \[id\]

Ребалансировка: показывает новый диапазон → подтверждение

/exit \[id\]

Полный выход из позиции \(Zap Out\)

/deposit \[id\] \[sum\] \[token\]

Добавить в позицию \(Zap In\)

/withdraw \[id\] \[%\]

Частичный вывод

/pause \[id\]

Приостановить автоматику по позиции

/killswitch on|off

kill\_switch в PolicyGuard: полная остановка автоматики

# __9\. Слой 3 — Automation__

## __9\.1 Execution flow \(существующий, интегрируем\)__

\# Каждые 5 мин \(execution decisions loop\)

positions = position\_reader\.get\_all\_active\(\)  ← ЗАМЕНА mock\_positions

for position in positions:

    triggers = trigger\_engine\.evaluate\(position\)

    for trigger in triggers:

        decision = policy\_guard\.check\(trigger, position\)

        if decision\.approved:

            orchestrator\.execute\(trigger, position, mode=LIVE\)

        else:

            log\(decision\.reason\_codes\)

## __9\.2 Стратегии ребалансировки__

__Стратегия__

__Описание__

__Триггер__

Recenter

Новый диапазон той же ширины, центр = текущая цена

OUT\_OF\_RANGE

Wider Range

Расширить диапазон на 20% если EDGE\_DECAY повторяется >3 раз за 7 дней

LOW\_RANGE\_UTILIZATION

IL\-Optimized

Оптимизатор пересчитывает лучший range на текущий момент

Manual или OUT\_OF\_RANGE

Custom

Пользователь задаёт range через Telegram или UI

Manual

## __9\.3 Gas Optimizer — оптимальный интервал compound__

Рассчитывает когда compound выгоден с учётом gas costs:

\# Оптимальный интервал T \(дней\) между compound:

APY\(T\) = \(1 \+ daily\_fee\_rate\)^\(365/T\) \- \(gas\_cost\_per\_compound / position\_size\) × \(365/T\)

\# Порог по умолчанию \(из PolicyGuard\):

compound\_if: fees\_earned\_usd > max\_gas\_usd\_per\_tx × 3

         OR: fees\_earned\_usd > 50 USD

         OR: elapsed > 24h

## __9\.4 IL Protection Bot \(Фаза 2\)__

### __Стратегия A — Range Shift \(запускаем первой\)__

1. Мониторим: цена в 15% от границы \(EDGE\_DECAY триггер\)
2. Собираем накопленные fees \(фиксируем прибыль\)
3. Закрываем позицию
4. Optimizer рассчитывает новый оптимальный диапазон
5. Открываем новую центрированную позицию

### __Стратегия B — Delta Hedge через Hyperliquid \(Фаза 2\.5\)__

Основной venue изменён с Binance Futures на Hyperliquid\. Обоснование: полностью on\-chain, нет custody риска, нет KYC, низкие fees, совместим с HyperEVM стеком\.

__Параметр hedge__

__Значение__

__Описание__

Max leverage

2x

Жёсткий лимит для hedge позиций

Min margin buffer

3x от ликвидационной цены

Обязательный collateral buffer

Liquidation distance guard

< 15% до ликвидации → алерт \+ уменьшение хеджа

—

Funding cap

0\.05%/8ч

Если funding rate выше → хедж дороже IL → автовыход из хеджа

Fail\-closed

Если мониторинг хеджа недоступен > 10 мин → уведомление \+ опциональный автовыход

—

__Изменение в Plan 020__

Следующий шаг: НЕ Binance Futures sandbox\.

Следующий шаг: Hyperliquid testnet коннектор \(заменить hummingbot\-shadow\-mock\)\.

GMX v2 — fallback для позиций на Arbitrum где Hyperliquid может быть неудобен\.

LIVE для hedger: только после 48ч SHADOW на реальном testnet без ошибок\.

# __10\. Слой 4 — Telegram Alerts__

## __10\.1 Security модель Telegram\-бота__

Бот принимает команды только от авторизованного chat\_id\. Это первая и главная защита\.

__Фаза__

__Auth модель__

__Что защищать__

0–1\.5 \(no\-custody\)

Хардкод ALLOWED\_CHAT\_ID в \.env\. Rate limit: max 10 команд/мин

Telegram: только owner

2\+ \(LIVE keeper\)

ALLOWED\_CHAT\_ID \+ HMAC подпись для критических команд \(/killswitch, /exit\)

Policy guard как pre\-trade gate

## __10\.2 Типы алертов__

__Приоритет__

__Событие__

__Задержка__

🔴 Критический

Позиция вышла из диапазона

Мгновенно

🔴 Критический

Whale exit >10% TVL пула

Мгновенно

🔴 Критический

CHAIN\_DEGRADED — автоматика приостановлена

Мгновенно

🔴 Критический

Ошибка LIVE execution

Мгновенно

🔴 Критический

Hedge: liquidation distance < 15%

Мгновенно

🟡 Важный

Цена в 15% от границы \(EDGE\_DECAY\)

5 мин

🟡 Важный

Fees достигли порога compound

5 мин

🟡 Важный

Anomaly detected в пуле

5 мин

🟢 Информационный

Compound/Rebalance выполнен

По факту

🟢 Информационный

Утренний P&L дайджест

09:00 ежедневно

## __10\.3 Формат алерта — пример__

__🔴 ПОЗИЦИЯ ВЫШЛА ЗА ДИАПАЗОН__

ETH/USDC  •  Uniswap v3  •  Arbitrum

Диапазон:      $1,850 – $2,200

Текущая цена:  $2,247 ↑

Вне диапазона: 18 минут

Упущено fees:  ~$12\.40

Net P&L:  \+$234 \(\+8\.7%\)

vs HODL:  \+$89

\[ /rebalance 42 \]  \[ /exit 42 \]  \[ /pause 42 \]

# __11\. Фазы разработки__

Обновлены с учётом существующего кода\. Критический путь: Real Position Reader → Gate\-3 canary → LIVE\.

__Фаза 0__

__Position Reader__

2–3 нед\.

- Real Position Reader: Arbitrum \+ Uniswap v3 \(замена mock\_positions\)
- Синхронизация истории кошелька через Alchemy Transaction API
- Tracker: P&L, Gross IL, HODL benchmark, Fee APR
- Position Journal: теги, тезисы, заметки
- Stale data guard \+ backoff rules
- Базовый веб\-дашборд: сводка портфеля \+ статус позиций \+ opportunity cost \(заглушка\)
- DoD: mock\_positions заменён, P&L верен на ≥ 3 реальных позициях

__Фаза 0\.5__

__Intelligence__

3–4 нед\.

- Сканер пулов: Arbitrum, Base, BSC \+ Uniswap v3, PancakeSwap, Aerodrome
- Оптимизатор диапазонов \(3 варианта: conservative/balanced/degen\)
- Anomaly Detector: wash trading, whale exit, fee spike
- Opportunity Cost Dashboard \(заполняет заглушку из Фазы 0\)
- Correlation Monitor
- Расширение сетей: Optimism, Polygon, Avalanche

__Фаза 1__

__Alerts \+ Signing__

2–3 нед\.

- Telegram\-бот: алерты \+ команды \(/status, /pnl, /top, /killswitch\)
- Dedicated hot wallet: настройка, тест на testnet
- Kill\-switch через Telegram → обновление PolicyGuard
- Signing flow: KEEPER\_PRIVATE\_KEY → native\_uniswap\_v3\_live
- Переименование адаптеров: simulate / live / v3utils\_live
- Krystal: перемещение в reader слой

__Фаза 1\.5__

__Zap \+ LIVE__

3–4 нед\.

- Position Manager: Zap In / Zap Out \(1\-click, MetaMask подпись\)
- Solana адаптер \(Orca \+ Raydium \+ Helius API\)
- HyperEVM адаптер
- Gate\-3 canary: 48ч SHADOW \+ 3 успешных LIVE canary tx
- LIVE compound \+ rebalance \(ядро уже готово в Spec 018\)
- Backtesting Engine

__Фаза 2__

__Automation__

3–4 нед\.

- Полная автоматизация: compound \+ rebalance \+ auto\-exit
- IL Bot Стратегия A: Range Shift
- Gas Optimizer: оптимальный интервал compound
- Reward Token Monitor
- Все Telegram команды управления позициями

__Фаза 2\.5__

__Hedger LIVE__

3–4 нед\.

- Hyperliquid testnet коннектор \(замена hummingbot\-shadow\-mock\)
- 48ч SHADOW на реальном testnet → LIVE hedger
- IL Bot Стратегия B: Delta Hedge через Hyperliquid
- GMX v2 как fallback для Arbitrum позиций
- Delta Monitor Dashboard
- Liquidation guard: margin buffer, funding cap, fail\-closed

# __12\. Конфигурация сетей и протоколов__

## __12\.1 Сети по группам__

__Сеть__

__Группа__

__RPC__

__Субграфы__

__Фаза__

Arbitrum One

A / Приоритет

Alchemy

The Graph / Goldsky

0

Base

A

Alchemy

The Graph

0\.5

BNB Smart Chain

A

Alchemy/QuickNode

The Graph

0\.5

Optimism

A

Alchemy

The Graph

0\.5

Polygon

A

Alchemy

The Graph

0\.5

Avalanche

A

Alchemy

The Graph

0\.5

Solana

B

Helius

Helius Enhanced API

1\.5

HyperEVM

C

Hyperliquid RPC

Raw RPC events

1\.5

Ethereum mainnet

Резерв

—

—

По запросу

## __12\.2 Протоколы__

__Протокол__

__Тип__

__Сети__

__Фаза__

Uniswap v3

CLMM

Arbitrum, Base, Optimism, Polygon

0

PancakeSwap v3

CLMM \(Uni fork\)

BSC, Arbitrum, Base

0\.5

Aerodrome

ve\(3,3\) CLMM

Base

0\.5

Velodrome

ve\(3,3\) CLMM

Optimism

0\.5

Curve v2

Cryptopools

Arbitrum, Polygon

0\.5

SushiSwap v3

CLMM \(Uni fork\)

Arbitrum, Polygon, BSC

0\.5

Orca Whirlpools

CLMM

Solana

1\.5

Raydium CLMM

CLMM

Solana

1\.5

Uniswap v4

CLMM \+ Hooks

—

Заглушка

## __12\.3 Добавление нового протокола__

1. Создать /protocols/\[name\]\.py наследующий BaseProtocol
2. Реализовать обязательные методы интерфейса
3. Добавить адреса фабрик и subgraph URL в конфиг
4. Написать unit\-тест: get\_pool, get\_position, get\_fees\_earned
5. Добавить в реестр протоколов → автоматически появится в сканере

__Критерий добавления__

Есть subgraph или SDK с документацией → 1–2 дня на адаптер \(пример: SushiSwap — форк Uni v3\)\.

Только raw RPC → 3–5 дней на адаптер\.

Нет документации / молодой протокол → ждём или форкаем похожий адаптер\.

LP Operating System  •  Техническое задание v1\.1  •  Февраль 2026

