# Specification: Tick Density Scanner (Band Depth Module) v1.0

Status: APPROVED
Owner: Dmitrii / Claude (Tech Lead)
Related Memory: `docs/memory-bank/activeContext.md`
Related Spec: [lp-decision-engine-v1.md](lp-decision-engine-v1.md) (sections 3, 6, 10)
Source Runbook: [Tick Density Scanner.md](../runbooks/Tick%20Density%20Scanner.md)
Date: 2026-02-17

---

## 1. Context & Business Value

### 1.1 Проблема

В CLMM-пулах (Uniswap V3, Aerodrome Slipstream) ликвидность распределена неравномерно по тикам. Существуют **ямы ликвидности** — ценовые зоны с низкой плотностью ликвидности, но значительным объёмом торгов. Размещение позиции в такой яме позволяет с малым капиталом ($200–500) забирать непропорционально большую долю комиссий.

### 1.2 Почему сейчас

LP Decision Engine (утверждённая спека) требует `band_depth_usd` для расчёта `competition_ratio` и `fee_share_daily` — без этого модуля scoring невозможен. Tick Density Scanner — это **Phase 1** LP Decision Engine, фундамент для всех последующих фаз.

### 1.3 Связь с существующей инфраструктурой

- Scout pipeline (DeFiLlama intake) даёт pool-level данные (TVL, APY, volume) — но **не tick-level**
- Freshness re-check (Uniswap/Aave/Morpho subgraph) уже подключается к subgraph — переиспользуемый паттерн
- LP Decision Engine spec (секции 3, 6, 10) определяет data models и interfaces — реализуем их

---

## 2. User Stories

- **US-1:** Как оператор LP, я ввожу адрес CLMM-пула и получаю `band_depth_usd` для диапазонов ±1%, ±2.5%, ±5% от текущей цены, чтобы понять уровень конкуренции.

- **US-2:** Как оператор LP, я хочу видеть гистограмму распределения ликвидности вокруг текущей цены, чтобы визуально найти ямы.

- **US-3:** Как LP Decision Engine, я вызываю `calculate_band_depth()` для каждого candidate pool и получаю структурированный `BandDepthResult`, чтобы рассчитать `competition_ratio` и `fee_share`.

- **US-4:** Как оператор LP, я хочу получать `Suggested Range: [lower, upper]` — оптимальный диапазон, центрированный вокруг ближайшей ямы с высоким volume, с учётом `tickSpacing`.

- **US-5:** Как LP Decision Engine, я хочу знать, стабильна ли яма во времени (≥3 наблюдения за 6h), чтобы не рекомендовать кратковременные артефакты.

- **US-6:** Как оператор LP, я хочу сравнивать ямы по нескольким пулам одной пары (Uniswap 0.05% vs 0.30% vs Aerodrome), чтобы выбрать лучший venue.

- **US-7:** Как LP Decision Engine, я хочу получать classification ямы (`CONFIDENT_PIT` vs `NOISE_PIT`) и flag `WHALE_DEPENDENT`, чтобы фильтровать ненадёжные сигналы.

- **US-8:** Как оператор LP, я хочу получать event-driven Telegram-алерт «Новая яма появилась», чтобы не ждать 4-6h регулярного цикла.

---

## 3. Functional Requirements

### 3.1 Core — Tick Data Acquisition (Phase 1, P0)

- **REQ-001:** Система MUST реализовать `TickDataProvider` protocol (interface):
  ```python
  class TickDataProvider(Protocol):
      async def get_pool_ticks(self, pool_address: str, lower: int, upper: int) -> List[TickData]: ...
      async def get_pool_state(self, pool_address: str) -> PoolState: ...
      def protocol_fee_pct(self) -> float: ...
  ```

- **REQ-002:** Система MUST реализовать `UniswapV3TickProvider` — adapter для Uniswap V3 Subgraph:
  - Paginация: chunk по 1000 тиков с `where: { tickIdx_gt: $lastTick }`
  - Circuit breakers: `MAX_PAGES_PER_POOL` (default 100) и `MAX_TICKS_PER_POOL` (default 50_000)
  - При превышении лимита: остановить scan пула, вернуть `data_quality: DEGRADED`, причину `PAGINATION_LIMIT_REACHED`
  - Timeout: максимум 3 retry × 5 секунд = 15 сек на пул
  - При ошибке: `data_quality: DEGRADED`, цикл НЕ падает (fail-safe)
  - Graph API key injection из environment variable

- **REQ-003:** `PoolState` MUST содержать:
  - `tick` — текущий активный тик
  - `liquidity` — текущая активная ликвидность (anchor для tick walking)
  - `sqrtPriceX96` — текущая цена в формате Uniswap
  - `fee_tier` — fee tier пула
  - `tick_spacing` — tick spacing для данного fee tier
  - `token0_decimals`, `token1_decimals` — decimals обоих токенов

### 3.2 Core — Band Depth Calculation (Phase 1, P0)

- **REQ-004:** Система MUST реализовать **tick walking algorithm** для расчёта `band_depth_usd`:
  1. Anchor: `current_L = pool_state.liquidity` при `pool_state.tick`
  2. Walk outward от текущего тика к границам диапазона
  3. На каждом initialized tick: `L += liquidityNet` (forward) или `L -= liquidityNet` (backward)
  4. Интегрировать: `interval_usd = liquidity_to_usd(L, price_lower, price_upper)` для каждого интервала
  5. Сумма interval_usd = `band_depth_usd`

> [!CAUTION]
> `sum(liquidityNet)` математически невалиден. Это дельты, а не абсолютные значения. Единственный корректный метод — tick walking с anchor `pool.liquidity`.

- **REQ-005:** Система MUST рассчитывать `band_depth_usd` для трёх окон:
  - ±1% от текущей цены
  - ±2.5% от текущей цены
  - ±5% от текущей цены
  Границы MUST быть выровнены по `tickSpacing`.

- **REQ-006:** Конвертация `tickIdx → price` MUST учитывать `decimals` обоих токенов:
  ```
  price = 1.0001^tickIdx × 10^(token0_decimals - token1_decimals)
  ```

### 3.3 Core — Freshness Validation (Phase 1, P0)

- **REQ-007:** Система MUST выполнять RPC cross-check для каждого пула:
  - Fetch `slot0()` через RPC
  - Сравнить `subgraph_tick` vs `rpc_tick`
  - Если `abs(drift) > tickSpacing` → `data_quality: DEGRADED`
  - Стоимость: ~$0.0001/пул на Base

### 3.4 Pit Detection & Classification (Phase 1.5, P0)

- **REQ-008:** Система MUST определять **ямы ликвидности** (liquidity pits):
  - Группировка тиков в bins по 1% изменения цены
  - Яма = bin, где `liquidity_usd < 0.5 × median_liquidity_usd` соседних bins
  - Выделять топ-3 ям по proximity к текущей цене

- **REQ-009:** Система MUST классифицировать каждую яму:

  | Класс | Критерии |
  |-------|----------|
  | `CONFIDENT_PIT` | Ширина ≥5 tick spacings, стабильна 24h+ (≥4 наблюдения), volume в зоне ≥ median |
  | `NOISE_PIT` | Ширина <5 tick spacings, или <3 наблюдений, или volume < 0.3× median |

- **REQ-010:** Яма MUST быть промаркирована `WHALE_DEPENDENT` если top-1 позиция в зоне содержит ≥60% ликвидности.
  - Источник: Subgraph `positions` entity, фильтр по `tickLower/tickUpper` overlap с зоной ямы

### 3.5 Auto-Range Suggestion (Phase 1.5, P1)

- **REQ-011:** Для каждой `CONFIDENT_PIT` система SHOULD генерировать `SuggestedRange`:
  ```python
  class SuggestedRange(BaseModel):
      lower_tick: int          # Выровнен по tickSpacing
      upper_tick: int          # Выровнен по tickSpacing
      lower_price: float       # Человекочитаемая цена
      upper_price: float
      width_pct: float         # Ширина в % от текущей цены
      band_depth_in_range: float  # USD ликвидности в этом диапазоне
      rationale: str           # Почему именно этот range
  ```
  - Range MUST быть расширен до ближайших «стен ликвидности» с обеих сторон ямы
  - Границы MUST быть кратны `tickSpacing` (1, 10, 60, 200 в зависимости от fee tier)

### 3.6 Band Depth Stability & History (Phase 2, P1)

- **REQ-012:** Система MUST хранить историю `band_depth_usd` для каждого пула:
  ```python
  class BandDepthHistory(BaseModel):
      pool_address: str
      observations: List[Tuple[datetime, float]]  # [(timestamp, band_depth_usd), ...]
      coefficient_of_variation: float              # std / mean
  ```

- **REQ-013:** Система MUST требовать ≥3 наблюдения за 6 часов перед actionable рекомендацией. Если `coefficient_of_variation > 0.30` → `UNSTABLE_DEPTH` → не рекомендовать.

- **REQ-014:** Система SHOULD отслеживать `time_to_fill` для ям:
  - Яма появилась → лог timestamp
  - Яма заполнилась (liquidity вернулась к median) → лог timestamp
  - Вычислить `avg_time_to_fill` по chain/pair_type для калибровки `time_to_crowd`

### 3.7 Multi-Pool Comparison (Phase 2, P1)

- **REQ-015:** Система SHOULD сравнивать ямы по всем пулам одной пары на одной сети:
  - Например: ETH/USDC на Base → Uniswap 0.05%, Uniswap 0.30%, Aerodrome CL
  - Выводить сравнительную таблицу: venue, fee_tier, band_depth, pit_count, best_pit_score

### 3.8 Heatmap Visualization (Phase 2, P1)

- **REQ-016:** Система SHOULD генерировать 2D heatmap:
  - Ось X: цена (bins по 1%)
  - Ось Y: время (observarions за последние 7 дней)
  - Цвет: плотность ликвидности (USD)
  - Подсветка: ямы (low density bins) выделены красным
  - Формат: PNG для Telegram, опционально интерактивный HTML

### 3.9 JIT-Bot Detection (Phase 3, P2)

- **REQ-017:** Система SHOULD анализировать JIT-активность в зоне ямы:
  - Fetch последних 100 `swap` events через Subgraph
  - Для крупных свопов (>$1k): проверить наличие `mint/burn` в том же блоке
  - Рассчитать `jit_capture_ratio` = % fee, захваченных JIT-ботами
  - Если `jit_capture_ratio > 0.50` в зоне ямы → flag `JIT_TRAP`, не рекомендовать

### 3.10 Event-Driven Pit Alert (Phase 3, P2)

- **REQ-018:** Система SHOULD отправлять Telegram-алерт при обнаружении новой стабильной ямы:
  ```
  🕳️ Новая яма в ETH/USDC (Uniswap 0.05%, Base)
  Диапазон: $2,810 – $2,870 | Глубина: $18k
  Volume 24h в зоне: $145k | Score: 8.1x avg
  Стабильность: 3 наблюдения за 4h ✅
  Тип: CONFIDENT_PIT
  ```
  - Триггер: яма получила статус `CONFIDENT_PIT` впервые
  - Дедупликация: не повторять alert для той же ямы в течение 24h

### 3.11 Predictive Pit Model (Phase 4+, P3)

- **REQ-019:** Система MAY прогнозировать появление ям:
  - Позиции с `price_edge` alert (цена в 10% от boundary) → вероятный exit → яма
  - Epoch-end на Aerodrome (четверг) → ребалансировка gauge → ямы
  - Исторический паттерн: после движения ≥3% появляются ямы через 2-6h

### 3.12 Integration Hook for LP Scoring (Phase 1, P0)

- **REQ-020:** Модуль MUST возвращать минимальный контракт для downstream ranking без рефакторинга:
  - `pool_address`
  - `band_depth_1pct_usd`, `band_depth_2_5pct_usd`, `band_depth_5pct_usd`
  - `pit_type` (`CONFIDENT_PIT`/`NOISE_PIT`/`NONE`)
  - `data_quality` (`OK`/`DEGRADED`/`UNVERIFIED`)
  - `scan_timestamp`

### 3.13 Small-Capital Profit Guardrail (Phase 2, P1)

- **REQ-021:** При интеграции с LP scoring pipeline система MUST применять фильтр минимальной полезности для small-cap:
  - вход: `expected_net_monthly_usd` от scorer
  - порог: `min_expected_net_monthly_usd` (default 5.0 USD)
  - если ниже порога → кандидат `WATCHLIST_ONLY` с причиной `SMALL_CAP_UNPROFITABLE`

### 3.14 Optional Discovery Provider — Krystal (Phase 2+, P1)

- **REQ-022:** Система MAY реализовать `KrystalDiscoveryProvider` как **дополнительный** источник pool discovery:
  - Предоставляет pool-level агрегаты (volume_30d, TVL, fee_tier) для расширения candidate list
  - НЕ заменяет `TickDataProvider` — tick-level данные MUST поступать через `UniswapV3TickProvider` (REQ-001/002)
  - Реализация зависит от gate: наличие service-level API auth (см. OQ-6)
  - Провайдер MUST реализовать `PoolDiscoveryProvider` protocol:
    ```python
    class PoolDiscoveryProvider(Protocol):
        async def discover_pools(
            self, chain_id: int, min_volume_30d: float, limit: int = 50,
        ) -> List[PoolSummary]: ...
    ```
  - `PoolSummary` — lightweight model (pool_address, token0, token1, volume_30d, tvl_usd, fee_tier)
  - Если Krystal недоступен → fallback на текущий DeFiLlama discovery, `data_quality` не затрагивается

### 3.15 Explicit Degradation Reason Codes (Phase 1, P0)

- **REQ-023:** Система MUST возвращать явный `degradation_reason` в `BandDepthResult` при `data_quality != OK`:
  ```python
  class DegradationReason(str, Enum):
      PAGINATION_LIMIT_REACHED = "PAGINATION_LIMIT_REACHED"
      SUBGRAPH_TIMEOUT = "SUBGRAPH_TIMEOUT"
      SUBGRAPH_ERROR = "SUBGRAPH_ERROR"
      RPC_DRIFT_EXCEEDED = "RPC_DRIFT_EXCEEDED"
      RPC_UNAVAILABLE = "RPC_UNAVAILABLE"
      TICK_COUNT_ZERO = "TICK_COUNT_ZERO"
  ```
  - Каждый `DEGRADED` результат MUST содержать ровно один `degradation_reason`
  - Logging MUST включать reason code (NFR-007)
  - Downstream consumers (LP scorer, notifier) MUST использовать reason для display, а не generic "degraded"
  - Недоступность optional discovery provider (например, Krystal) НЕ должна деградировать `BandDepthResult`; при таком сценарии используется fallback discovery (REQ-022)

---

## 4. Non-Functional Requirements

### Performance
- **NFR-001:** Полный scan одного пула (fetch + walk + classify) ≤ 15 секунд
- **NFR-002:** Batch scan 20 пулов ≤ 2 минуты (parallel async)
- **NFR-003:** Subgraph query timeout: 5 сек per request, max 3 retries

### Reliability
- **NFR-004:** Любая ошибка subgraph/RPC → `DEGRADED`/`UNVERIFIED`, цикл не падает
- **NFR-005:** Strict provider initialization: no silent Mock fallback (per systemPatterns.md)
- **NFR-006:** Atomic writes для cache/history файлов (per systemPatterns.md)

### Observability
- **NFR-007:** Logging: каждый scan пула логирует `pool_address`, `band_depth_*`, `data_quality`, `duration_ms`
- **NFR-008:** Metrics: `pits_found_count`, `confident_pit_count`, `degraded_count` per cycle
- **NFR-011:** Runtime метрики MUST включать `scan_duration_p95_ms` на цикл/батч

### Security
- **NFR-009:** Subgraph API keys и RPC endpoints — только из environment variables, не в коде
- **NFR-010:** Secret-safe logging: не логировать API keys (per systemPatterns.md)

---

## 5. Constraints

### Tech Stack
- Python 3.11+, async/await
- `aiohttp` для HTTP (subgraph GraphQL + RPC JSON-RPC)
- `pydantic` для data models
- `matplotlib` / `plotly` для визуализации (optional)
- Без внешних CLMM SDK (чистая имплементация tick math)

### Existing Logic
- Переиспользовать паттерн из `src/defi_agents/freshness/` для subgraph queries
- Data models из LP Decision Engine spec секция 6 (`PoolAnalysis`, `DataQuality`)
- `TickDataProvider` interface из LP spec секция 10.1

### Target DEX Scope (phased)
- Phase 1 (P0): Uniswap V3
- Phase 1.5 (P0.5): Aerodrome CL
- Phase 2 (P1): PancakeSwap V3, HyperSwap CL

### Module Placement
```
src/defi_agents/lp/
├── __init__.py
├── tick_provider.py         # TickDataProvider protocol + UniswapV3TickProvider
├── band_depth.py            # calculate_band_depth(), pit_detection()
├── pit_classifier.py        # CONFIDENT/NOISE classification, whale detection
├── models.py                # PoolState, TickData, BandDepthResult, PitInfo, SuggestedRange
├── history.py               # BandDepthHistory, time_to_fill tracking
└── visualization.py         # Heatmap, bar chart (Phase 2)
```

---

## 6. Out of Scope (v1)

| Item | Reason | Phase |
|------|--------|-------|
| Автоматическое открытие позиций | `MANUAL_EXECUTION_ONLY` policy | — |
| Reward economics scoring | Отдельный модуль (LP Engine Phase 2.5) | 2.5 |
| IL estimation | Отдельный модуль (LP Engine Phase 2) | 2 |
| Полный competition scoring (`net_alpha`) | Использует band_depth как input (LP Engine Phase 2); в v1 обязателен только output-hook `REQ-020` | 2 |
| Portfolio allocation (60/40) | LP Engine Phase 3 | 3 |
| Aerodrome CL adapter | Отдельный provider (LP Engine Phase 1.5) | 1.5 |
| Mempool analysis | Не в scope проекта | — |
| Predictive model training | Требует 30+ дней исторических данных | 4+ |
| Krystal как primary tick-level source | API за Cloudflare challenge; tick-data контракт не подтверждён (см. OQ-6, R-8) | 2+ |

---

## 7. Acceptance Criteria

### Phase 1 (Core)

- **AC-01:** Для ETH/USDC 0.05% pool на Base: `band_depth_5pct_usd` совпадает с Revert.finance ±15%
- **AC-02:** Для USDC/USDT 0.01% pool на Base: `band_depth_1pct_usd` совпадает с Revert.finance ±15%
- **AC-03:** Decimal conversion: `price(currentTick)` для ETH/USDC = текущая market price ±1%
- **AC-04:** Freshness cross-check: при drift > tickSpacing → `data_quality: DEGRADED`
- **AC-05:** Subgraph pagination: корректно обрабатывает пулы с >1000 initialized ticks
- **AC-06:** Timeout: scan одного пула ≤ 15 секунд включая retry
- **AC-07:** Fail-safe: при subgraph 500/timeout → `DEGRADED`, pipeline продолжает
- **AC-17:** Pagination guardrails: при broken pagination срабатывает `MAX_PAGES_PER_POOL`/`MAX_TICKS_PER_POOL`, цикл не падает

### Phase 1.5 (Pit Detection)

- **AC-08:** Pit detection: находит ямы, визуально соответствующие Uniswap Analytics / Revert.finance
- **AC-09:** Classification: `CONFIDENT_PIT` vs `NOISE_PIT` корректно разделяет стабильные и кратковременные ямы
- **AC-10:** `SuggestedRange` границы кратны `tickSpacing`
- **AC-11:** `WHALE_DEPENDENT` flag корректно определяет доминирование одной позиции

### Phase 2 (History & Comparison)

- **AC-12:** History: хранит ≥3 observations per pool, корректно рассчитывает `coefficient_of_variation`
- **AC-13:** Multi-pool: сравнение ≥2 venues одной пары с корректным ранжированием
- **AC-14:** Heatmap: визуально читаемый PNG, ямы подсвечены

### Phase 3 (Advanced)

- **AC-15:** JIT detection: `jit_capture_ratio` для пула с известной JIT-активностью > 0.3
- **AC-16:** Pit alert: Telegram-сообщение отправляется при первом `CONFIDENT_PIT`, не дублируется 24h

### Ops / Shadow Rollout (Phase 1 gate)

- **AC-18:** 24h VPS shadow-run без cycle failures (`errors=0`)
- **AC-19:** В логах есть `pits_found_count`, `degraded_count`, `scan_duration_p95_ms`
- **AC-20:** При `data_quality != OK` не формируются actionable рекомендации (только watchlist)

---

## 8. Risks / Open Questions

### Risks

| ID | Risk | Severity | Mitigation |
|----|------|----------|------------|
| R-1 | Subgraph rate limiting (The Graph API) | HIGH | API key rotation, caching, progressive backoff |
| R-2 | Decimal confusion (USDC 6 vs WETH 18) | HIGH | Automated sanity check: price ∈ expected range |
| R-3 | Band depth snapshot illusion | HIGH | ≥3 observations / 6h gate (REQ-013) |
| R-4 | JIT bots filling pits before user | MEDIUM | JIT detector (Phase 3) + `realized_fill_factor = 0.6` |
| R-5 | Air Pocket — яма это отсутствие support | MEDIUM | CEX VPVR cross-check (manual, Phase 2+) |
| R-6 | Subgraph lag (5-30 blocks on Base) | MEDIUM | RPC `slot0()` cross-check (REQ-007) |
| R-7 | Low-liquidity pool data noise | MEDIUM | `NOISE_PIT` classification + stability gate |
| R-8 | Krystal API vendor risk: Cloudflare WAF challenge blocks all server-side calls (confirmed 2026-02-19) | HIGH | P0 не зависит от Krystal; discovery gated behind OQ-6 resolution. Timeboxed API discovery (2 weeks). |

### Open Questions

1. **Volume data source:** Использовать pool-level `volumeUsd1d` (DeFiLlama, уже есть) или per-tick volume из Subgraph `swaps`? Рекомендация: pool-level в v1, per-tick в v1.1 для Deep Dive mode.

2. **Heatmap delivery:** PNG в Telegram или интерактивный HTML на VPS? Telegram ограничивает размер, HTML требует веб-сервер.

3. **History storage:** File-backed JSON (как L3 cache) или SQLite? File-backed проще, SQLite масштабируется лучше для >100 пулов.

4. **Aerodrome subgraph access:** Официальный Aerodrome subgraph на The Graph требует API key. Нужно подтвердить доступ.

5. **Multi-chain priority:** Base first (Q: сколько пулов сканировать?). Arbitrum — Phase 1.5?

6. **Krystal API auth:** Все эндпоинты (`api.krystal.app`, `defi.krystal.app`, `cloud.krystal.app`) возвращают 403 + `cf-mitigated: challenge`. Для server-side интеграции нужен один из: (a) service API key от Krystal team, (b) IP allowlist, (c) партнёрский доступ. До решения — Krystal gated, P0 не блокирован. См. `docs/research/krystal-api-discovery.md`.

---

## 9. Implementation Roadmap

### Phase 1: Core Band Depth (Week 1)
- [ ] `TickDataProvider` protocol + `UniswapV3TickProvider`
- [ ] `PoolState`, `TickData`, `BandDepthResult` models
- [ ] `calculate_band_depth()` — tick walking algorithm
- [ ] `validate_tick_freshness()` — RPC cross-check
- [ ] Unit tests: tick walking with mock data
- [ ] Integration test: ETH/USDC Base → compare with Revert.finance

### Phase 1.5: Pit Detection & Range (Week 2)
- [ ] Pit detection (binning + threshold)
- [ ] `CONFIDENT_PIT` / `NOISE_PIT` classification
- [ ] `WHALE_DEPENDENT` flag (positions query)
- [ ] `SuggestedRange` generation (tickSpacing-aligned)
- [ ] `AerodromeTickProvider` adapter
- [ ] Bar chart visualization (matplotlib)

### Phase 2: History & Comparison (Week 3)
- [ ] `BandDepthHistory` — file-backed storage
- [ ] Stability gate (3+ observations / 6h / cv < 0.30)
- [ ] `time_to_fill` tracking for pits
- [ ] Multi-pool comparison for same pair
- [ ] `PancakeSwapV3TickProvider` adapter
- [ ] `HyperSwapTickProvider` adapter
- [ ] 2D heatmap (time × price × liquidity)

### Phase 3: Advanced Detection (Week 4+)
- [ ] JIT-bot detection (`jit_capture_ratio`)
- [ ] Event-driven Telegram pit alert
- [ ] Integration with LP Decision Engine scoring pipeline

### Phase 4: Predictive (Future)
- [ ] Price edge → pit prediction
- [ ] Aerodrome epoch-based pit patterns
- [ ] Historical pattern database

---

## 10. Volume Signal Architecture

> [!IMPORTANT]
> CEX volume и DEX volume — разные сигналы для разных задач. Смешивание приведёт к ложным рекомендациям.

### 10.1 DEX Volume → Yield Signal
- Источник: DeFiLlama `volumeUsd1d` (pool-level, уже в Scout pipeline)
- Используется для: `fee_share_daily = volume × fee_tier × competition_ratio × fill_factor`
- Haircut: `realized_fill_factor = 0.6` (conservative default, calibrate in shadow)
- Ограничение v1: pool-level, не per-tick

### 10.2 CEX Volume → Safety Signal (Phase 2+)
- Источник: Binance/Bybit candles API (30d VPVR)
- Используется для: проверки «яма = Air Pocket?»
- Логика: если CEX volume в зоне ямы HIGH → safe (support exists). Если LOW → dangerous (free fall risk)
- Delivery: manual check в v1, automated в v2

### 10.3 Per-Tick DEX Volume (Phase 2+, Deep Dive)
- Источник: Subgraph `swaps(where: {tick_gte, tick_lte})` query
- Используется для: точный fee yield estimate для конкретной ямы
- Ограничение: дорого по запросам (100+ swaps per query), только для top-5 candidates

---

## Approvals
- [x] User Approved
- [x] Architecture Approved

---

### Gemini Review (2026-02-17)

**Summary:** The specification `017-tick-density-scanner-v1.md` is **excellent** and addresses all critical mathematical and architectural concerns raised in previous reviews. It correctly positions the scanner as a foundational module for the LP Decision Engine.

#### 1. Completeness & Correctness
*   **Tick Walking (REQ-004):** Correctly defines the anchor (`pool.liquidity`) and walking logic. The warning against `sum(liquidityNet)` is appropriate.
*   **Freshness (REQ-007):** The RPC cross-check for tick drift is a vital reliability feature for Base/Arbitrum.
*   **Module Placement:** `src/defi_agents/lp/` is the correct location, aligning with the domain-driven design of the project.

#### 2. Risk Mitigation
*   **Decimal Confusion (REQ-006):** Explicit formula for price conversion reduces the risk of order-of-magnitude errors.
*   **Sub-optimal Pits (REQ-009):** The classification into `CONFIDENT_PIT` and `NOISE_PIT` is a smart way to handle the noisy nature of low-liquidity pools.

#### 3. Suggestions for Refinement (Non-Blocking)
*   **Resource Management:** For `REQ-002` (Pagination), consider adding a specific `MAX_TICKS_PER_POOL` limit (e.g., 50k) to prevent infinite loops if the subgraph returns broken pagination data.
*   **Visualization:** For `REQ-016` (Heatmap), since this is Phase 2, consider simply generating a CSV first. It's lighter and easier to debug than generating PNG images on a headless VPS.

#### 4. Approval
*   **Verdict:** **APPROVED**. Proceed to Implementation Plan.

---

### ChatGPT Review (2026-02-18)

- ChatGPT: AGREE — спецификация технически сильная, особенно `REQ-004` (tick walking), `REQ-007` (RPC drift check) и fail-safe требования (`NFR-004`).
- ChatGPT: AGREE — placement в `src/defi_agents/lp/` корректен и совместим с текущей архитектурой Scout/Freshness.
- ChatGPT: PARTIAL — в разделе Out of Scope `competition scoring` вынесен полностью в Phase 2; для v1 стоит оставить минимальный output-hook: `band_depth_usd`, `pit_type`, `data_quality`, чтобы ranking мог использовать модуль без рефакторинга интерфейса.
- ChatGPT: NEW — добавить hard guardrail для small-cap deployment: `min_expected_net_monthly_usd` (после gas/rebalance drag), иначе candidate автоматически в watchlist.
- ChatGPT: NEW — добавить `MAX_TICKS_PER_POOL` и `MAX_PAGES_PER_POOL` в REQ-002 как явный circuit breaker против broken pagination.
- ChatGPT: NEW — добавить acceptance criterion на shadow rollout: 24h на VPS без cycle failures, с метриками `pits_found_count`, `degraded_count`, `scan_duration_p95`.
- ChatGPT: NEW — зафиксировать phased adapter roadmap для целевых площадок из продукта: Uniswap (P0), Aerodrome/Pancake/Hyperswap (P0.5/P1), чтобы избежать vendor drift в реализации.
