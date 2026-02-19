**Цель / Критерий успеха**
Найти ценовой диапазон (яму ликвидности) вокруг текущей цены (спота), где отношение  максимально. Это позволяет на твои выделенные 10% капитала забирать непропорционально большую долю комиссий.

Поиск "ямы" — это чистая дата-инженерия. В CLMM (Uniswap V3) ликвидность не размазана ровно, она дискретно лежит на «тиках» (ticks). Тебе нужно вытащить массив этих тиков и найти локальные минимумы.


### 1. Concept

**In scope:** Python-скрипт (Jupyter Notebook или CLI), который подключается к Subgraph выбранной DEX, скачивает распределение ликвидности (Tick Data) для конкретного пула, накладывает на него профиль объема (Volume Profile) за 30 дней и подсвечивает "ямы" в пределах  от текущей цены.
**Out of scope:** Автоматическое открытие позиций, работа с mempool.

### 2. Data

* **Источники:** The Graph API (официальные сабграфы Uniswap V3, Aerodrome, PancakeSwap V3).
* **Сущности GraphQL:**
* `Pool`: текущий `tick`, `liquidity`.
* `Tick`: `tickIdx`, `liquidityNet`, `liquidityGross`.


* **Трансформация:** Перевод `tickIdx` в реальную цену токена по формуле  (с учетом `decimals` токенов).

### 3. Pipeline (План действий: Как найти яму)

1. **Fetch:** Запрос всех активных тиков в диапазоне `[current_tick - 50000, current_tick + 50000]`.
2. **Reconstruct Liquidity:** Проход по массиву тиков для вычисления абсолютной ликвидности  на каждом шаге (через кумулятивную сумму `liquidityNet`).
3. **Binning (Агрегация):** Группировка мелких тиков в "корзины" (bins) по 1% изменения цены для сглаживания шума.
4. **Volume Overlay:** Загрузка 30d Volume Profile (VPVR) из Binance/Bybit API или агрегатора и наложение на те же 1%-корзины.
5. **Pit Detection:** Расчет метрики . Выделение топ-3 корзин (ям) с самым высоким Score.

### 4. Interfaces (Контракты)

```python
def fetch_tick_data(subgraph_url: str, pool_address: str) -> pd.DataFrame:
    """Возвращает DataFrame: [tick_idx, price, liquidity_active]"""
    pass

def calculate_density_score(ticks_df: pd.DataFrame, volume_profile: pd.DataFrame) -> pd.DataFrame:
    """Мерджит ликвидность и объем, возвращает Capital Velocity для каждого бакета."""
    pass

def plot_liquidity_pit(density_df: pd.DataFrame, current_price: float):
    """Строит bar chart: по оси X - цена, по оси Y - ликвидность. Красным подсвечивает 'ямы'."""
    pass

```

### 5. User Stories

* **US1:** Как оператор пула, я ввожу адрес контракта и получаю гистограмму распределения ликвидности вокруг спота, чтобы визуально увидеть "дыры" в стакане.
* **US2:** Как квант, я хочу, чтобы скрипт автоматически выдавал мне `Suggested Range: [Min, Max]`, центрированный вокруг ближайшей ямы ликвидности с высоким историческим объемом.

### 6. Validation (Минимальный набор тестов)

* **Sanity Check:** Сверить выведенный график с вкладкой "Liquidity" в интерфейсе Revert.finance или Uniswap Analytics для этого же пула. Форма колокола (или ее отсутствие) должна совпадать 1 в 1.
* **Precision Check:** Проверка правильности конвертации тиков в цену (ошибка в `decimals` — самая частая проблема при работе с CLMM, особенно для стейблкоинов вроде USDC, где 6 знаков, а не 18).

### 7. Risks (Риски "Ям ликвидности" - Адвокат Дьявола)

Искать ямы выгодно, но это несет скрытые tail-risks:

1. **JIT Liquidity (Just-In-Time):** Ты видишь яму, ставишь туда капитал. Но как только туда приходит крупный ордер, MEV-бот вставляет свою ликвидность на 1 блок прямо перед ордером, забирает 99% комиссии и уходит. Яма была иллюзией.
* *Mitigation:* Яму имеет смысл отрабатывать только на сетях с долгой финализацией или где JIT-боты менее активны, а также делая диапазон чуть шире 1-2 тиков.


2. **Air Pocket (Воздушный карман / Свободное падение):** Если под текущей ценой глубокая "яма", это может быть не неэффективность, а отсутствие уровня поддержки. Если цена туда упадет, она проскользит эту яму за секунду, ты не соберешь объем, а просто получишь 100% IL.
* *Mitigation:* Обязательная кросс-проверка "ямы ликвидности" с техническим уровнем (Support/Resistance) на графике 30-дневного профиля объема (VPVR). Яма должна находиться *внутри* проторгованной зоны, а не под ней.



### 8. Next Actions

Этот функционал идеально ложится в Jupyter Notebook для быстрого прототипирования.
Готов ли ты передать это ТЗ AI-кодеру в Google Antigravity, чтобы он написал скрипт, скачивающий `liquidityNet` из The Graph и рисующий профиль пула?

---

### Gemini Review (2026-02-17)

**Summary:** The concept is sound and aligned with the "Low Competition" goal, but execution details in the *Reconstruction* and *Volume Overlay* steps need technical hardening to avoid "garbage-in/garbage-out".

#### 1. Mathematical Criticality: Tick Walking (Reconstruct Liquidity)
*   **Issue:** The runbook mentions "cumulative sum `liquidityNet`" (Item 3.2).
*   **Risk:** `liquidityNet` is a delta. Summing it arbitrarily is meaningless.
*   **Requirement:** You MUST implement strict **Tick Walking** logic:
    1.  Fetch `pool.liquidity` (Current Active L) from the pool entity.
    2.  Start at `pool.tick` (Current Tick).
    3.  Walk outwards (left/right) to neighbor ticks.
    4.  Apply `liquidityNet` cumulatively at each initialized tick crossing.
*   **Constraint:** Without this anchor (`pool.liquidity`), the "shape" of the pit will be correct, but the "depth" values (USD) will be completely wrong.

#### 2. Volume Overlay Mismatch (CEX vs DEX)
*   **Issue:** Item 3.4 suggests using Binance/Bybit 30d VPVR.
*   **Risk:** CEX volume profile shows where *CEX traders* agree on price (Support/Resistance). It creates "Air Pocket" safety features (as noted in Risk 2), but it does **NOT** predict fee yield. Fees only come from **DEX** volume.
*   **Correction:**
    *   **Yield Signal:** Use **DEX** Volume (Subgraphs daily volume data).
    *   **Risk Signal:** Use **CEX** Volume (Support/Resistance).
    *   **Action:** If a "liquidity pit" exists at Price X:
        *   Check **CEX Volume** at Price X. If HIGH -> Safe (Support exists).
        *   Check **CEX Volume** at Price X. If LOW -> Dangereous (Air Pocket).

#### 3. Metric Definition: Capital Efficiency Score
*   The "Score" mentioned (Item 3.5) needs a concrete formula.
*   **Proposal:**
    ```python
    efficiency_score = (dex_volume_24h_in_bin / active_liquidity_usd_in_bin)
    ```
    *   This represents "Velocity of Money" — how many times typical liquidity turns over per day.
    *   Target: Find bins where Velocity > Market Average (Average is usually 5-20% daily turnover; pits can be 100%+).

#### 4. Architecture Recommendation
*   Instead of a standalone Jupyter Notebook, implement this as a **reusable Skill/Script** in `src/defi_agents/tools/tick_scanner.py`.
*   This allows the "LP Decision Engine" to call it automatically later for "Deep Dives" on specific candidates.

---

### Claude Tech Lead Review (2026-02-17)

#### 0. Общая оценка

**Вердикт: PROCEED WITH MAJOR REWORK → ТЗ нужно переписать как модуль LP Decision Engine, а не standalone инструмент.**

Идея правильная: найти ценовые диапазоны с низкой плотностью ликвидности (ямы) и высоким объёмом — это ровно то, что нужно для тактического слива LP Decision Engine. Но текущий документ:
1. Дублирует ~70% работы, уже утверждённой в [lp-decision-engine-v1.md](../specs/lp-decision-engine-v1.md) (секции 3, 4, 5, 6)
2. Содержит ту же математическую ошибку, которую уже зафиксировали 3 ревьюера (sum `liquidityNet` = мусор)
3. Не учитывает reward economics, IL, и wash/JIT-фильтры, без которых «яма» может быть ловушкой

**Рекомендация:** Не создавать standalone-скрипт. Вместо этого оформить Tick Density Scanner как **Phase 1 модуля `band_depth_calculator`** внутри LP Decision Engine, переиспользуя уже approved спеку и data models.

---

#### 1. Claude: AGREE (Gemini §1 — Tick Walking обязателен)

Полностью поддерживаю. Это P0-блокер. В утверждённой LP-спеке (секция 3.1) уже есть корректный алгоритм:
```python
# Из lp-decision-engine-v1.md, секция 3.1
current_L = pool.liquidity  # Anchor: active liquidity at current tick
# Walk outwards, applying liquidityNet at each initialized tick
```

**Ключевое отличие от текущего runbook (п. 3.2 "Reconstruct Liquidity"):** документ пишет «кумулятивная сумма `liquidityNet`» — это **не кумулятивная сумма**, это **tick walking с anchor**. Разница фундаментальна: без anchor (значения `pool.liquidity` при текущем тике) форма распределения будет верной, но абсолютные значения — произвольными. Форма без масштаба бесполезна для расчёта `competition_ratio`.

**Для ТЗ кодеру:** Алгоритм из LP-спеки секции 3.1 — единственный допустимый. Псевдокод из п. 3.2 runbook необходимо полностью заменить.

---

#### 2. Claude: AGREE + EXTENSION (Gemini §2 — CEX vs DEX Volume)

Gemini верно указал, что CEX volume ≠ DEX volume для расчёта fee yield. Но проблема глубже:

**2a. DEX on-chain volume тоже ненадёжен для fee estimation.**
Subgraph `volumeUsd1d` включает:
- JIT-ботов (Just-In-Time): вставляют ликвидность на 1 блок, забирают ~99% комиссии с крупного ордера, уходят
- Wash trading: самостоятельные сделки для pumping volume metrics
- Арбитраж: high-frequency bots с минимальным slippage

Для пула с `band_depth < $50k` (наша целевая зона) эти компоненты могут составлять **60-90% от `volumeUsd1d`**. Считать fee yield по raw volume = завышать ожидания в 3-10 раз.

**2b. Два usage для volume (Gemini верно разделил):**
| Signal | Source | Purpose |
|--------|--------|---------|
| **Fee yield estimation** | DEX volume (с JIT/wash haircut) | Сколько заработаешь |
| **Air Pocket safety** | CEX VPVR (Support/Resistance) | Не проскользнёт ли цена через яму |

**Для ТЗ:** Нельзя использовать один volume overlay для обеих задач. CEX VPVR — это safety signal, не yield signal. В ТЗ нужно явно разделить.

**Трудность:** Получить per-tick DEX volume (а не pool-level) — возможно только через Subgraph `swaps` events с фильтрацией по tick range. Это дорого по запросам и не все subgraphs поддерживают такую гранулярность.

**Как преодолеть:** 
- v1: Использовать pool-level `volumeUsd1d` из DeFiLlama (уже есть в Scout pipeline) с conservative `realized_fill_factor = 0.6` (уже в LP-спеке, секция 2.3)
- v1.1: Добавить per-tick volume через `swaps(where: {tick_gte, tick_lte})` query для top-5 кандидатов (Deep Dive mode)

---

#### 3. Claude: AGREE + CRITICAL GAP (Gemini §3 — Capital Efficiency Score)

Формула Gemini (`dex_volume_24h / active_liquidity_usd`) — это корректная метрика "Velocity of Money". В LP-спеке это уже есть как `competition_ratio` + `fee_share_daily` (секция 2.3).

**Критический GAP в текущем runbook:**

Документ определяет «Score» (п. 3.5) как `Volume / Liquidity`, но **полностью игнорирует 3 компонента**, которые в LP-спеке являются P0:

1. **Reward APR** — на Base/Arbitrum 30-60% yield = rewards (AERO/OP). Skill `reward-economics` требует haircut по tier ликвидности reward-токена.
2. **Impermanent Loss** — для volatile pairs (ETH/USDC) IL может превышать fee income в 3-5 раз. LP-спека требует `il_estimate_apr` в формуле `net_alpha`.
3. **Wash/JIT filter** — без него "яма с высоким volume" может быть JIT-ловушкой, где 99% комиссий забирает бот.

**Вывод:** «Score = Volume / Liquidity» — необходимое, но **не достаточное** условие. ТЗ должно использовать формулу `net_alpha` из LP-спеки:
```
net_alpha = fee_apr + reward_apr_realized - il_estimate - gas_drag - risk_haircuts
```

---

#### 4. Claude: PARTIAL (Gemini §4 — Architecture)

Gemini предлагает `src/defi_agents/tools/tick_scanner.py`. **Частично согласен, но placement неверный.**

**Почему не `tools/`:**
- В проекте нет директории `tools/`, и modules layout уже устоялся (`src/defi_agents/scout/`, `src/defi_agents/data/`, `src/defi_agents/freshness/`)
- Tick scanning — это не утилита, это **core data acquisition** для LP scoring

**Правильный placement (по skill `clmm-range-ops` + `lp-opportunity-scoring`):**
```
src/defi_agents/lp/
├── tick_provider.py         # TickDataProvider interface + Uniswap/Aerodrome adapters
├── band_depth.py            # Tick walking → band_depth_usd calculation
├── competition_scorer.py    # competition_ratio + fee_share + net_alpha
└── models.py                # PoolAnalysis, BandDepthHistory, RewardProfile, DataQuality
```

Это соответствует LP-спеке (секция 6: Data Models → `src/defi_agents/scout/lp_models.py`) и позволяет LP Decision Engine вызывать scanner как внутренний модуль, а не внешний инструмент.

---

#### 5. Claude: NEW — Трудности и как их преодолеть

##### 5.1 Subgraph Pagination (HARD)

GraphQL subgraph лимитирует `ticks()` запрос до **1000 элементов**. Для ETH/USDC 0.05% fee tier (tickSpacing=10) в диапазоне ±50000 тиков — это ~10,000 initialized ticks. Потребуется пагинация.

**Как преодолеть:**
- Запрашивать тики chunk-ами по 1000, с `where: { tickIdx_gt: $lastTick }`
- Timeout budget: максимум 3 retry × 5 секунд = 15 сек на пул
- Если не удалось получить все тики — `data_quality: DEGRADED`, не блокировать цикл

##### 5.2 Разные схемы Subgraph (MEDIUM)

Uniswap v3 и Aerodrome CL имеют разные имена полей:
| | Uniswap v3 | Aerodrome CL |
|--|-----------|-------------|
| Pool entity | `Pool` | `CLPool` |
| Current tick | `tick` | `tickCurrent` |
| Protocol fee | 0% | 20% |

**Как преодолеть:** `TickDataProvider` protocol (interface) — уже в LP-спеке, секция 10.1. Каждый DEX получает свой adapter.

##### 5.3 Decimal confusion (MEDIUM, самая частая ошибка)

Конвертация `tickIdx → price` требует знать `decimals` обоих токенов. Для USDC (6 decimals) vs WETH (18 decimals) ошибка в decimals даёт цены, отличающиеся на 12 порядков.

**Как преодолеть:**
- Validation check (п. 6 Validation): сверка с Revert.finance / Uniswap UI
- Автоматический тест: для известного пула (например, ETH/USDC 0.05% Base) `price(currentTick)` должна быть в диапазоне $2000-$4000. Если нет — ошибка в decimals.

##### 5.4 Band Depth Stability (HARD)

Skill `defi-degradation-policy` требует: "Partial data → WATCHLIST_ONLY". Для low-liquidity пулов (наша целевая зона) `band_depth` может меняться на 30-50% в течение часа.

**Как преодолеть:** LP-спека уже содержит решение (секция 3.4):
- Требовать ≥3 наблюдения за 6 часов
- `coefficient_of_variation > 0.30` → `UNSTABLE_DEPTH` → не рекомендовать

##### 5.5 Subgraph Lag vs RPC (MEDIUM)

Subgraph отстаёт на 5-30 блоков от on-chain реальности. Для low-liquidity пулов это критично: цена могла уже уйти.

**Как преодолеть:** LP-спека, секция 3.3 — cross-check subgraph tick vs RPC `slot0()`. Стоимость: ~$0.0001/пул на Base.

---

#### 6. Claude: NEW — Что должно быть в ТЗ для кодера (структура)

Учитывая overlap с LP-спекой и Gemini-замечания, предлагаю следующую структуру ТЗ:

**Scope:** Реализовать `band_depth_calculator` как Phase 1 LP Decision Engine (не standalone скрипт).

**Модули:**

1. **`TickDataProvider` interface** — Protocol (ABC) с методами:
   - `get_pool_ticks(pool_address, lower_tick, upper_tick) → List[TickData]`
   - `get_pool_state(pool_address) → PoolState` (содержит `tick`, `liquidity`, `sqrtPriceX96`)
   - `protocol_fee_pct() → float`

2. **`UniswapV3TickProvider`** — adapter для Uniswap v3 subgraph:
   - Paginación (1000 ticks per query)
   - Timeout + retry + fail-safe (`UNVERIFIED` при ошибке)
   - Graph API key injection из env

3. **`calculate_band_depth(pool_state, ticks, lower_tick, upper_tick) → BandDepthResult`** — tick walking:
   - Anchor: `pool_state.liquidity` при `pool_state.tick`
   - Walk outward, apply `liquidityNet`
   - Convert L to USD (`liquidity_to_usd(L, price_lower, price_upper)`)
   - Return `band_depth_usd` для ±1%, ±2.5%, ±5%

4. **`validate_tick_freshness(subgraph_tick, pool_address) → DataQuality`** — RPC cross-check

5. **Models** (из LP-спеки секция 6):
   - `PoolState`, `TickData`, `BandDepthResult`, `DataQuality`

**Что НЕ входит в Phase 1:**
- Reward economics (Phase 2.5)
- IL estimation (Phase 2)
- Competition scoring (Phase 2)
- Portfolio allocation (Phase 3)
- Aerodrome adapter (Phase 1.5)
- Visualization/plotting (optional, later)

**Acceptance Criteria:**
- Для ETH/USDC 0.05% pool на Base: `band_depth_5pct_usd` совпадает с Revert.finance ±15%
- Freshness cross-check работает (subgraph vs RPC drift < tickSpacing)
- Timeout < 15 секунд на пул
- Все ошибки → `DEGRADED`/`UNVERIFIED`, цикл не падает
- Unit тесты для tick walking (mock ticks → expected band_depth)

---

#### 7. Claude: Итоговые рекомендации

| # | Пункт | Решение |
|---|-------|---------|
| 1 | Standalone скрипт vs модуль | **Модуль** `src/defi_agents/lp/` внутри LP Decision Engine |
| 2 | `sum(liquidityNet)` | **Заменить** на tick walking с anchor `pool.liquidity` |
| 3 | Volume overlay (CEX) | **Разделить**: DEX volume → yield, CEX VPVR → safety |
| 4 | Score = Volume/Liquidity | **Расширить** до `net_alpha` (fee + reward - IL - gas) |
| 5 | Jupyter Notebook прототип | **Допустимо** для визуализации на этапе калибровки, но production код — в модуле |
| 6 | Aerodrome | **P0.5**, после Uniswap v3, с отдельной shadow validation |
| 7 | Риски JIT/wash | **Обязательные** фильтры, не optional |
| 8 | Band depth stability | **3+ observations / 6h** перед actionable рекомендацией |

**Next step:** Обсудить эту структуру ТЗ, после чего я готов оформить полноценный spec+plan по шаблону SDD (`docs/specs/` + `docs/plans/`). 

---

### ChatGPT Review (2026-02-18)

- ChatGPT: AGREE — текущий standalone-подход нужно закрепить как модуль LP Decision Engine; иначе будет дублирование логики и расхождение формул между Scout и LP scoring.
- ChatGPT: AGREE — `sum(liquidityNet)` должен быть запрещен как подход; только tick walking с anchor `pool.liquidity` + проверка по `tickSpacing`.
- ChatGPT: PARTIAL — CEX VPVR полезен как safety-сигнал, но для v1 лучше явно отметить его как optional/manual check, чтобы не блокировать запуск из-за лишней внешней зависимости.
- ChatGPT: AGREE — для production-safe rollout нужно добавить gate по качеству данных: если `DEGRADED/UNVERIFIED`, то только watchlist и без actionable рекомендации.
- ChatGPT: NEW — добавить капитал-зависимый фильтр (для small capital): не рекомендовать диапазон, если ожидаемый `net_monthly_usd` после gas/rebalance ниже порога (например, <$5/мес) даже при хорошей яме.
- ChatGPT: NEW — зафиксировать в runbook поддержку целевых DEX из roadmap (Uniswap/Aerodrome/Hyperswap/Pancake) как phased adapters, чтобы не потерять Hyperswap при реализации.
