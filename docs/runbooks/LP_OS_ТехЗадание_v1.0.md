__LP OPERATING SYSTEM__

Техническое задание

DeFi Liquidity Management Platform

__Версия__

__1\.0__

__Дата__

__Февраль 2025__

# __Содержание__

1\. Обзор проекта

2\. Технологический стек

3\. Архитектура системы

4\. Слой 0 — Трекер позиций и P&L

5\. Слой 1 — Intelligence \(Сканер и аналитика\)

6\. Слой 2 — Position Manager \(Управление позициями\)

7\. Слой 3 — Automation \(Автоматизация\)

8\. Слой 4 — Alerts \(Telegram\-бот\)

9\. Интеграции: DEX\-агрегаторы и биржи деривативов

10\. Дополнительные модули

11\. Фазы разработки

12\. Конфигурация сетей и протоколов

# __1\. Обзор проекта__

## __1\.1 Цель__

LP Operating System — персональная платформа для профессионального управления позициями ликвидности в DeFi\. Система объединяет аналитику, трекинг, автоматизацию и алерты в едином интерфейсе, заменяя разрозненные инструменты \(Revert, Krystal, DeBank\) одним решением\.

## __1\.2 Целевой пользователь__

Активный LP\-менеджер с 1–30 одновременными позициями в нескольких сетях\. Основной пользователь на старте — владелец проекта\. Архитектура проектируется с возможностью последующей монетизации\.

## __1\.3 Ключевые проблемы которые решает система__

- Нет единого P&L с учётом реального IL, gas\-затрат и HODL\-benchmark
- Ручное отслеживание выхода позиции из диапазона — медленно и ненадёжно
- Нет инструмента для поиска оптимального пула и диапазона перед входом
- Compound и ребалансировка выполняются вручную без расчёта оптимального момента
- Нет backtesting для проверки стратегии на исторических данных
- Нет детектора аномалий — wash trading, whale exit, искусственный APY

## __1\.4 Четыре слоя системы__

__Слой__

__Название__

__Что делает__

__Фаза__

Слой 0

Tracker

Позиции, P&L, HODL benchmark, Journal

0

Слой 1

Intelligence

Сканер пулов, скоринг, аномалии, opportunity cost

1

Слой 2

Position Manager

Zap In/Out, ребалансировка, compound, выход

1\.5–2

Слой 3

Automation

Keeper, IL bot, авто\-выход

2–2\.5

Слой 4

Alerts

Telegram\-бот, алерты, команды

1

# __2\. Технологический стек__

## __2\.1 Backend__

__Компонент__

__Технология__

__Обоснование__

API сервер

Python \+ FastAPI

Единый язык, AI\-агенты знают его лучше всего, огромная DeFi\-экосистема

Очередь задач

Celery \+ Redis Broker

Параллельный мониторинг 30 позиций, retry при падении RPC, легко масштабируется

Кеш

Redis

Hot data: цены, топ пулов, метрики — TTL 30–60 сек

Основная БД

PostgreSQL

Метаданные позиций, пулов, токенов, журнал

Time\-series БД

TimescaleDB

История APY, fee, volume, цен — оптимизирован для временных рядов

Миграции

Alembic

Версионирование схемы БД

Telegram\-бот

python\-telegram\-bot

Тот же Python, живёт в монолите на старте

## __2\.2 Frontend__

__Компонент__

__Технология__

__Обоснование__

Фреймворк

Next\.js 14 \(App Router\) \+ TypeScript

Современный стандарт, хорошо генерируется AI\-агентами

UI компоненты

shadcn/ui \+ TailwindCSS

Copy\-paste компоненты, агенты генерируют без ошибок

Data fetching

TanStack Query

Кеш на клиенте, авто\-рефетч, optimistic updates

Графики

Recharts \+ D3

Price distribution, APY timeline, P&L chart

Кошелёк

Wagmi \+ viem

Подключение кошелька, подпись транзакций

Real\-time

WebSocket \(FastAPI\)

Push\-обновления цен и статуса позиций

## __2\.3 Источники данных__

__Источник__

__Что даёт__

__Приоритет__

The Graph / Goldsky

Субграфы Uniswap v3, PancakeSwap, Aerodrome — пулы, позиции, события

Основной

Alchemy / Helius

EVM RPC \+ Solana RPC, Transaction API, historical data

Основной

1inch API

Котировки свапов, лучший маршрут, gas estimate для EVM

Основной

Jupiter API

Котировки свапов для Solana

Основной

DeFiLlama API

TVL пулов, audit info, chain overview, протоколы

Дополнительный

CoinGecko API

Цены токенов, историческая волатильность, market cap

Дополнительный

GMX v2 API

Открытие/закрытие perp позиций для IL hedge \(фаза 2\.5\)

Фаза 2\.5

Hyperliquid API

Perps для HyperEVM позиций \(фаза 2\.5\)

Фаза 2\.5

## __2\.4 Инфраструктура__

__Компонент__

__Решение__

Контейнеризация

Docker \+ Docker Compose \(монолит \+ PostgreSQL \+ Redis\)

Переменные окружения

\.env файл — API ключи, RPC endpoints, Telegram token

Логирование

Structlog — JSON\-логи с контекстом позиции/сети/протокола

Мониторинг

Sentry для ошибок \+ простой healthcheck эндпоинт

# __3\. Архитектура системы__

## __3\.1 Структура проекта__

__Файловая структура монолита__

/app

  /chains                   ← адаптеры сетей

    /evm                    ← базовый EVM адаптер \(web3\.py\)

      base\_evm\.py           ← абстрактный класс с общей логикой

      arbitrum\.py           ← наследует EVM, только конфиг \+ особенности

      base\_chain\.py         ← Base network

      bsc\.py                ← BNB Smart Chain

      optimism\.py

      polygon\.py

      avalanche\.py

      hyperevm\.py           ← EVM \+ fallback на raw RPC

    /solana                 ← отдельная архитектура \(anchorpy \+ Helius\)

      solana\.py

  /protocols                ← адаптеры протоколов

    base\_protocol\.py        ← абстрактный интерфейс протокола

    uniswap\_v3\.py           ← работает на всех EVM сетях

    uniswap\_v4\.py           ← заглушка \(раскомментировать в будущем\)

    pancakeswap\_v3\.py       ← ~80% кода от uniswap\_v3

    aerodrome\.py            ← Base / Optimism, ve\(3,3\) логика

    velodrome\.py            ← Optimism

    curve\.py                ← стейблы, другая математика

    sushiswap\_v3\.py         ← форк uni\_v3

    orca\.py                 ← Solana Whirlpools

    raydium\_clmm\.py         ← Solana CLMM

  /intelligence             ← СЛОЙ 1: аналитика и рекомендации

  /tracker                  ← СЛОЙ 0: позиции, P&L, история

  /position\_manager         ← СЛОЙ 2: управление позициями

  /automation               ← СЛОЙ 3: keeper, IL bot

  /alerts                   ← СЛОЙ 4: Telegram

  /api                      ← FastAPI роуты

  /workers                  ← Celery tasks

  /db                       ← модели SQLAlchemy, Alembic миграции

  /core                     ← shared utils: pricing, math, gas

## __3\.2 Принцип адаптера__

Каждый протокол реализует единый интерфейс BaseProtocol\. Весь остальной код — трекер, сканер, автоматизация — работает только через этот интерфейс и не знает о деталях конкретного протокола\.

__Интерфейс BaseProtocol \(Python\)__

class BaseProtocol:

    \# Информация о пуле

    def get\_pool\(pair, fee\_tier\) \-> Pool

    def get\_pool\_apy\(pool\) \-> PoolMetrics

    def get\_pool\_volume\(pool, period\) \-> VolumeData

    \# Управление позицией

    def get\_position\(token\_id\) \-> Position

    def get\_fees\_earned\(position\) \-> FeeData

    def get\_position\_value\(position\) \-> ValueData

    \# Исполнение \(фаза 2\)

    def collect\_fees\(position\) \-> TxHash

    def add\_liquidity\(position, amounts\) \-> TxHash

    def remove\_liquidity\(position, pct\) \-> TxHash

    def rebalance\(position, new\_range\) \-> TxHash

## __3\.3 Поток данных__

__Основной поток \(мониторинг каждые 30 сек\)__

Chain RPC / Subgraph

        ↓

  Celery Workers         ← параллельно по каждой позиции

  \(агрегация событий,

   расчёт метрик\)

        ↓

  TimescaleDB \+ Redis    ← история \+ горячий кеш

        ↓

  Alert Engine           ← проверка правил алертов

        ↓  ↘

  FastAPI        Telegram Bot

        ↓

  Next\.js Dashboard      ← WebSocket push

# __4\. Слой 0 — Трекер позиций и P&L__

Первый модуль к разработке\. Даёт немедленную ценность без автоматизации — просто подключаешь кошелёк и видишь реальный P&L по всем позициям\.

## __4\.1 Структура данных позиции__

__Модель Position \(PostgreSQL\)__

Position:

  id, wallet\_address, protocol, chain, pool\_address

  token\_id                       ← NFT ID позиции \(Uni v3\)

  tick\_lower, tick\_upper

  token0, token1

  \# Данные входа

  opened\_at                      ← timestamp \+ block number

  entry\_price\_token0\_usd

  entry\_price\_token1\_usd

  entry\_amount\_token0

  entry\_amount\_token1

  entry\_value\_usd

  \# Агрегированные метрики \(пересчёт на лету\)

  current\_value\_usd              ← token0 \+ token1 по текущей цене

  fees\_earned\_usd                ← сумма всех claim событий

  gas\_spent\_usd                  ← открытие \+ rebalance \+ compound \+ закрытие

  reward\_tokens\_usd              ← токены наград по цене на момент клейма

  hodl\_value\_usd                 ← entry amounts × current prices

  \# P&L

  net\_pnl\_usd                    ← current\_value \+ fees \- entry\_value \- gas

  net\_pnl\_vs\_hodl\_usd            ← net\_pnl \- \(hodl\_value \- entry\_value\)

  il\_usd                         ← current\_value \- hodl\_value

  apr\_realized                   ← fees\_earned / entry\_value / days × 365

  status                         ← active | out\_of\_range | closed

  closed\_at, exit\_value\_usd

## __4\.2 Расчёт реального P&L__

- Net P&L = Текущая стоимость \+ Собранные fees \+ Reward tokens − Стоимость входа − Gas costs
- HODL Benchmark = сколько бы стоило просто держать токены без LP
- IL = Current Value − HODL Value \(всегда отрицательный при расхождении цен\)
- P&L vs HODL = показывает реальную добавленную стоимость от LP\-стратегии

__Важно__

Gas costs собираются из receipt каждой транзакции \(gasUsed × gasPrice × ETH/USD на момент tx\)\.

Исторические цены берутся из CoinGecko Historical API по timestamp транзакции\.

Для Solana gas пренебрежимо мал — можно не учитывать или считать с нулевым весом\.

## __4\.3 История событий позиции__

Каждое on\-chain событие сохраняется в таблицу PositionEvent:

__Тип события__

__Что фиксируем__

open

Открытие позиции: tick range, суммы токенов, цены, gas

fee\_collect

Сбор fees: суммы token0/token1, USD value

compound

Реинвест: суммы, новые границы позиции если изменились

rebalance

Ребалансировка: старый и новый range, суммы, gas

add\_liquidity

Довнесение в позицию: суммы, USD value

remove\_liquidity

Частичный вывод: % вывода, суммы

close

Закрытие: итоговые суммы, цены выхода, total gas

## __4\.4 Синхронизация on\-chain данных__

1. При первом запуске: сканируем историю кошелька через Alchemy Transaction API — находим все Mint/Burn/Collect события
2. Импортируем все исторические позиции с ценами на момент каждой транзакции
3. Polling каждые 30 сек: проверяем новые события по активным позициям
4. При обнаружении нового события — обновляем P&L и проверяем правила алертов

## __4\.5 Position Journal__

К каждой позиции можно прикрепить структурированные заметки:

- Тезис входа — почему открыл эту позицию
- Стратегия — тип диапазона, планируемая частота ребалансировки
- Целевой APY и условие выхода
- Теги — для фильтрации и анализа паттернов \(например: 'волатильная пара', 'стейблы', 'новый листинг'\)
- Post\-mortem после закрытия — вывод и оценка решения

Через 3–6 месяцев Journal становится базой для анализа: какие стратегии работают лучше, какие тезисы оказались верными\.

# __5\. Слой 1 — Intelligence__

## __5\.1 Сканер пулов__

Сканирует все поддерживаемые протоколы и сети, возвращает ранжированный список пулов с метриками\.

### __Входные параметры фильтрации__

- Сети \(мультиселект или все\)
- Протоколы \(мультиселект или все\)
- Минимальный TVL \(default: $100k\)
- Минимальный возраст пула в днях \(default: 14\)
- Минимальный audit score \(0–100, default: 60\)
- Тип пары: volatile / stable\-correlated / все

### __Метрики расчёта для каждого пула__

__Метрика__

__Формула / источник__

__Вес в скоре__

Fee APY

volume\_24h × fee\_tier / TVL\_in\_range × 365

40%

Real APY

Fee APY \+ Reward APY × \(1 − inflation\_factor\)

—

Net APY

Real APY − projected\_IL − gas\_cost\_pct

—

IL Score

Моделирование IL при σ за 30 дней, для заданного диапазона

20%

Active Range %

% времени цена в диапазоне за 7/30 дней

20%

Audit Score

DeFiLlama audits \+ возраст контракта \+ bug bounty size

10%

Whale Activity

Входы/выходы крупных LP за 48ч \(>$500k\)

10%

## __5\.2 Оптимизатор диапазона__

Для выбранного пула рассчитывает оптимальный диапазон \[tickLower, tickUpper\]:

1. Берём историю цен за 30/90 дней
2. Строим вероятностное распределение \(lognormal \+ fat tails\)
3. Ищем диапазон с максимальным E\[Net APY\] при условии P\(in\-range\) ≥ threshold
4. Threshold настраивается: Conservative 80%, Balanced 70%, Degen 55%
5. Выводим 3 варианта диапазона с разным балансом доходность/риск

## __5\.3 Anomaly Detector__

Детектирует нетипичные паттерны в пуле которые могут искажать реальный APY:

__Аномалия__

__Сигнал__

__Действие__

Wash Trading

High volume \+ minimal price movement \+ circular addresses

Флаг: APY может быть искусственным

Whale Exit

TVL падение >10% за <1 час

Алерт: крупный LP выходит

Fee Spike

Fee tier utilization аномально высокий

Флаг: возможна манипуляция

Reward Dump

Токен наград падает >15% за 24ч

Флаг: реальный APY ниже заявленного

Liquidity Thin

Резкое уменьшение глубины стакана

Флаг: повышенный slippage

## __5\.4 Opportunity Cost Dashboard__

Один экран который отвечает на вопрос: стоит ли оставаться в текущей позиции или переложиться?

- Берёт каждую активную позицию
- Находит топ\-5 альтернатив с лучшим Net APY в той же сети
- Считает стоимость перехода: gas на закрытие \+ открытие
- Показывает: 'Переход окупится через X дней' или 'Переход нецелесообразен'
- Учитывает накопленные unrealized fees — вывод до закрытия позиции

## __5\.5 Correlation Monitor__

Агрегирует риск всего портфеля позиций:

- Считает дельту каждой позиции по отношению к BTC, ETH, SOL
- Строит корреляционную матрицу пар портфеля
- Выводит агрегированную дельту портфеля: 'Ты на 60% long ETH'
- Предупреждает о концентрации риска: 'Три позиции сильно коррелируют — IL придёт одновременно'

# __6\. Слой 2 — Position Manager__

Полный lifecycle управления позицией\. Аналог функциональности Revert Finance, но интегрированный с трекером и intelligence\-слоем\.

## __6\.1 Zap In \(Deposit с автоконвертацией\)__

Открытие позиции с любым входным токеном за одну операцию:

1. Пользователь указывает: пул, диапазон, входной токен, сумму
2. Система рассчитывает нужное соотношение token0/token1 для заданного диапазона
3. Запрашивает котировку у 1inch/Jupiter для оптимального свапа
4. Учитывает price impact свапа — при необходимости итеративно корректирует суммы
5. Открывает позицию — пользователь подписывает транзакцию в кошельке
6. Возвращает остаток токенов если есть

__Архитектурное решение: no\-custody__

На старте \(фаза 1\.5\): система готовит параметры транзакции, пользователь подписывает сам\.

Смарт\-контракт не хранит средства\. Аудит не требуется\.

Фаза 2\+: опциональный vault\-контракт на базе open\-source кода Revert Finance\.

## __6\.2 Zap Out \(Вывод депозита\)__

Три режима вывода:

- Вывести оба токена в исходном соотношении \(без свапа\)
- Вывести всё в один выбранный токен \(через 1inch/Jupiter\)
- Частичный вывод — указать % от позиции

## __6\.3 Авторебалансировка__

### __Триггеры \(настраиваются per\-position\)__

- Цена вышла за диапазон \(немедленно\)
- Цена приблизилась к границе на X% \(default: 15%\)
- Прошло N дней с последней ребалансировки
- APY пула упал ниже минимального порога
- Ручной триггер через Telegram /rebalance \[id\]

### __Стратегии ребалансировки__

__Стратегия__

__Описание__

Recenter

Новый диапазон той же ширины центрируется вокруг текущей цены

Wider Range

Если часто выходит — автоматически расширяет диапазон на X%

Custom Range

Пользователь задаёт новый диапазон вручную \(через UI или Telegram\)

IL\-Optimized

Оптимизатор диапазона пересчитывает лучший range на текущий момент

## __6\.4 Автокомпаунд__

### __Триггеры__

- Накопленные fees > gas\_cost × 3 \(минимальный порог эффективности\)
- Накопленные fees > $X \(настраивается, default: $50\)
- Каждые N часов \(настраивается, default: 24ч\)

### __Gas Optimizer__

Модуль рассчитывает оптимальную частоту compound для каждой позиции:

- Optimal compound interval = breakeven при текущем APY и gas costs
- На Arbitrum/Base — может быть ежедневно или чаще
- Показывает разницу в итоговом APY между разными частотами

### __Логика compound__

1. Собрать fees \(token0 \+ token1\)
2. Рассчитать текущее соотношение в диапазоне
3. Своп части одного токена в другой через 1inch/Jupiter
4. Добавить ликвидность обратно в позицию
5. Записать событие compound в Position History

## __6\.5 Автовыход \(Auto\-Exit\)__

Условия выхода настраиваются per\-position:

- Take Profit: Net P&L достиг X% \(например \+50%\)
- Stop Loss: Net P&L ушёл в минус на X% \(например \-10%\)
- Time Stop: позиция вне диапазона более N часов без улучшения
- APY Stop: APY ниже минимума N дней подряд
- Ручной выход: команда /exit \[id\] в Telegram

После выхода — опциональный Zap Out в указанный токен\.

## __6\.6 Ручное управление__

Все автоматические действия доступны и вручную:

__Команда__

__Действие__

/deposit \[id\] \[amount\] \[token\]

Добавить средства в позицию \(Zap In\)

/withdraw \[id\] \[%\]

Частичный вывод из позиции

/compound \[id\]

Немедленный compound накопленных fees

/rebalance \[id\]

Ребалансировка с подтверждением нового диапазона

/exit \[id\]

Полный выход из позиции \(Zap Out\)

/pause \[id\]

Приостановить автоматизацию по позиции

/resume \[id\]

Возобновить автоматизацию

# __7\. Слой 3 — Automation__

## __7\.1 Keeper Architecture__

Keeper — это Celery воркер который периодически проверяет условия и исполняет on\-chain действия:

__Расписание Celery задач__

Каждые 30 сек:  мониторинг цен \+ статуса позиций \(in/out of range\)

Каждые 5 мин:   проверка триггеров ребалансировки и compound

Каждые 1 час:   пересчёт оптимальных диапазонов \+ opportunity cost

Каждые 6 часов: обновление whale activity \+ anomaly detection

Каждые 24 часа: обновление audit scores \+ reward token metrics

                расчёт дневного P&L дайджеста

## __7\.2 Rate Limiting__

30 позиций × мониторинг каждые 30 сек = нагрузка на RPC nodes\. Нужен контроль:

- Rate limiter per chain — максимум X запросов/мин к каждому RPC
- Connection pool — переиспользование web3 соединений
- Приоритетная очередь — критические проверки \(out\-of\-range\) имеют приоритет над фоновыми
- Failover — если основной RPC недоступен, переключение на резервный

## __7\.3 IL Protection Bot \(Фаза 2\.5\)__

### __Стратегия A — Range Shift \(запускаем первой\)__

Самая реалистичная стратегия на старте\. Не устраняет IL, но минимизирует время вне диапазона:

1. Мониторим: когда цена приближается к границе на 15%
2. Собираем все накопленные fees \(фиксируем прибыль\)
3. Закрываем позицию
4. Optimizer рассчитывает новый оптимальный диапазон
5. Открываем новую центрированную позицию

### __Стратегия B — Delta Hedge через Perps \(фаза 2\.5\+\)__

Математически чистая защита\. Открываем perp позицию противоположную дельте LP:

- LP\-позиция создаёт динамическую дельту — меняется по мере движения цены
- Hедж на GMX v2 \(EVM\) или Hyperliquid \(HyperEVM\) компенсирует эту дельту
- При ребалансировке LP — корректируем размер хеджа
- Стоимость хеджа \(funding rate\) вычитается из итогового APY

__Предупреждение__

Delta hedge через perps требует постоянной корректировки и стоит funding rate\.

Эффективен только при высоком APY пула \(>50% годовых\) где IL действительно болезненен\.

Начинаем с Range Shift, добавляем Delta Hedge только после валидации на реальных позициях\.

# __8\. Слой 4 — Telegram Alerts__

## __8\.1 Типы алертов__

__Приоритет__

__Событие__

__Задержка__

🔴 Критический

Позиция вышла за диапазон

Мгновенно

🔴 Критический

Whale exit >10% TVL пула

Мгновенно

🔴 Критический

Ошибка исполнения автоматизации

Мгновенно

🟡 Важный

Цена в 15% от границы диапазона

5 мин

🟡 Важный

Fees достигли порога compound

5 мин

🟡 Важный

APY пула упал ниже минимума

5 мин

🟡 Важный

Anomaly detected в пуле

5 мин

🟢 Информационный

Утренний P&L дайджест

09:00 daily

🟢 Информационный

Compound/Rebalance выполнен

По факту

🟢 Информационный

Новый топ\-пул обогнал твою позицию

1 раз в день

## __8\.2 Управление шумом__

- Cooldown per position — один алерт по одной позиции не чаще 1 раза в N минут
- Severity escalation — вышел из диапазона 5 мин → тихий, 30 мин → повторный 🔴, 2ч → эскалация
- Quiet hours — настраиваемое окно, в котором слать только критические
- Digest mode — все не\-срочные алерты объединяются в один утренний отчёт

## __8\.3 Формат сообщений__

__Пример алерта: выход из диапазона__

🔴 ПОЗИЦИЯ ВЫШЛА ЗА ДИАПАЗОН

ETH/USDC • Uniswap v3 • Arbitrum

Диапазон: $1,850 – $2,200

Текущая цена: $2,247 ↑

Вне диапазона: 18 минут

Упущено fees: ~$12\.40

P&L позиции: \+$234 \(\+8\.7%\)

vs HODL: \+$89

Действия: /rebalance 42  /exit 42  /pause 42

## __8\.4 Команды бота__

__Команда__

__Ответ__

/status

Список всех позиций: статус in/out of range, текущий P&L

/pnl

P&L за сегодня / неделю / всё время, разбивка по позициям

/top

Топ\-5 пулов из сканера прямо сейчас

/position \[id\]

Детальная информация о конкретной позиции

/compound \[id\]

Немедленный compound \(с подтверждением\)

/rebalance \[id\]

Ребалансировка с показом нового диапазона и подтверждением

/exit \[id\]

Выход из позиции с подтверждением

/pause \[id\]

Пауза автоматизации по позиции

/alerts on|off

Включить/выключить все алерты

/digest on|off

Переключить в digest mode

# __9\. Интеграции__

## __9\.1 DEX\-агрегаторы \(свапы\)__

__Агрегатор__

__Сети__

__Применение__

1inch Fusion API

Arbitrum, Base, BSC, Optimism, Polygon, Avalanche

Все свапы при compound и rebalance на EVM

Jupiter API v6

Solana

Все свапы при compound и rebalance на Solana

Li\.Fi

Cross\-chain

Опционально фаза 3 — переброс между сетями

__Логика выбора маршрута__

Перед каждым свапом: запрашиваем котировки у агрегатора с параметрами:

  — slippage tolerance \(default 0\.5%, для волатильных пар выше\)

  — max price impact \(default 1%\)

  — deadline \(default 20 мин\)

Если price impact > 1% — отменяем и уведомляем пользователя\.

## __9\.2 Perp биржи \(IL Hedge, Фаза 2\.5\)__

__Биржа__

__Сети__

__Приоритет__

GMX v2

Arbitrum, Avalanche

Основной для EVM позиций

Hyperliquid

HyperEVM

Основной для HyperEVM позиций

dYdX v4

Cosmos app\-chain

Запасной вариант для крупных позиций

# __10\. Дополнительные модули__

## __10\.1 Backtesting Engine__

Отвечает на вопрос: сколько бы заработала эта стратегия на исторических данных?

### __Входные параметры__

- Пул \+ сеть \+ протокол
- Диапазон \[tickLower, tickUpper\] или стратегия ребалансировки
- Начальный капитал и токен входа
- Период тестирования \(последние 30/90/180 дней или кастомный\)
- Параметры автоматизации: порог compound, триггер ребалансировки

### __Что считает__

- Fee APY по каждому дню \(на основе реального исторического volume\)
- IL на каждый день
- Газ на compound и rebalance при заданной стратегии
- Итоговый Net P&L и APR за период
- Сравнение с HODL benchmark
- Equity curve — график стоимости позиции по дням

__Источники исторических данных__

Исторические цены: CoinGecko API \(OHLCV по дням\)

Исторический volume пула: The Graph \(Uniswap subgraph, исторические снимки\)

Исторический TVL: DeFiLlama API

## __10\.2 Gas Optimizer__

Рассчитывает оптимальную частоту compound для максимизации итогового APY:

__Формула оптимального интервала__

При compound каждые T дней:

  APY\_compounded = \(1 \+ daily\_fee\_rate\)^\(365/T\) \- gas\_cost\_per\_compound / position\_size × \(365/T\)

Оптимальный T находится численно \(golden section search\)\.

Показываем график: APY vs\. частота compound\.

## __10\.3 Reward Token Monitor__

Оценивает реальную ценность токенов наград:

- Отслеживает circulating supply и emission schedule токена наград
- Считает inflation dilution factor за последние 30 дней
- Real Reward APY = Nominal APY × \(1 − dilution\_factor\)
- Если токен теряет >20% в месяц — понижаем его вес, выводим предупреждение

# __11\. Фазы разработки__

Каждая фаза самодостаточна — даёт реальную ценность сама по себе\.

__Фаза 0__

__2–3 недели__

- Базовая инфраструктура: PostgreSQL \+ Redis \+ FastAPI \+ Celery
- Адаптеры сетей: Arbitrum, Base, BSC \(EVM base adapter\)
- Адаптер протокола: Uniswap v3
- Синхронизация истории кошелька через Alchemy
- Трекер позиций: P&L, HODL benchmark, IL, газ
- Position Journal: теги, тезисы, заметки
- Простой веб\-дашборд: список позиций \+ P&L таблица

__Фаза 1__

__4–5 недель__

- Сканер пулов: все поддерживаемые сети и протоколы
- Оптимизатор диапазона: 3 варианта \(conservative / balanced / degen\)
- Anomaly Detector: wash trading, whale exit, fee spike
- Opportunity Cost Dashboard
- Correlation Monitor
- Gas Optimizer
- Telegram\-бот: алерты \+ базовые команды \(/status, /pnl, /top\)
- Добавление сетей: Optimism, Polygon, Avalanche
- Добавление протоколов: PancakeSwap v3, Aerodrome, Curve

__Фаза 1\.5__

__3–4 недели__

- Solana адаптер \(Orca Whirlpools \+ Raydium CLMM \+ Helius API\)
- HyperEVM адаптер
- Position Manager: Zap In / Zap Out \(1\-click, без custody\)
- Backtesting Engine
- Reward Token Monitor

__Фаза 2__

__4–5 недель__

- Keeper: автокомпаунд с gas optimizer
- Keeper: авторебалансировка \(все стратегии\)
- Keeper: автовыход по условиям
- Telegram: полные команды управления \(/compound, /rebalance, /exit\)
- Telegram: интерактивные подтверждения действий

__Фаза 2\.5__

__3–4 недели__

- IL Protection Bot: Range Shift стратегия
- IL Protection Bot: Delta Hedge через GMX v2 \+ Hyperliquid
- Delta Monitor Dashboard
- Интеграция Uniswap v4 \(если экосистема созреет\)

# __12\. Конфигурация сетей и протоколов__

## __12\.1 Сети__

__Сеть__

__Группа__

__RPC Provider__

__Субграфы__

__Фаза__

Arbitrum One

A

Alchemy

The Graph \(Goldsky\)

0

Base

A

Alchemy

The Graph

0

BNB Smart Chain

A

Alchemy / QuickNode

The Graph

0

Optimism

A

Alchemy

The Graph

1

Polygon

A

Alchemy

The Graph

1

Avalanche C\-Chain

A

Alchemy

The Graph

1

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

__Адаптер__

__Фаза__

Uniswap v3

CLMM

Arbitrum, Base, Optimism, Polygon

uniswap\_v3\.py

0

PancakeSwap v3

CLMM \(Uni fork\)

BSC, Arbitrum, Base

pancakeswap\_v3\.py

1

Aerodrome

ve\(3,3\) CLMM

Base

aerodrome\.py

1

Velodrome

ve\(3,3\) CLMM

Optimism

velodrome\.py

1

Curve v2

Cryptopools

Arbitrum, Polygon

curve\.py

1

SushiSwap v3

CLMM \(Uni fork\)

Arbitrum, Polygon, BSC

sushiswap\_v3\.py

1

Orca Whirlpools

CLMM

Solana

orca\.py

1\.5

Raydium CLMM

CLMM

Solana

raydium\_clmm\.py

1\.5

Uniswap v4

CLMM \+ Hooks

—

Заглушка

Будущее

## __12\.3 Добавление нового протокола__

Процедура добавления любого нового протокола \(SushiSwap, Trader Joe, Ramses и др\.\):

1. Создать /protocols/\[name\]\.py наследующий BaseProtocol
2. Реализовать обязательные методы интерфейса
3. Добавить адреса фабрик и subgraph URL в конфиг
4. Написать unit\-тест для get\_pool и get\_position
5. Добавить в реестр протоколов — автоматически появится в сканере

__Критерий добавления протокола__

Есть subgraph или SDK с хорошей документацией → адаптер пишется быстро \(1–2 дня\)\.

Только raw RPC без субграфа → закладывать 3–5 дней на адаптер\.

Нет документации / молодой протокол → ждём созревания или форкаем похожий адаптер\.

LP Operating System • Техническое задание v1\.0

