# LP Entry Recommendation v1 — Research (Plan 025)

Date: 2026-03-03  
Scope source of truth: `docs/plans/025-lp-entry-research-roo-task.md` (research-only, без runtime changes)

## 1) Что исследовано

- План/DoD и ограничения: `docs/plans/025-lp-entry-research-roo-task.md`.
- Product/active/progress контекст: `docs/memory-bank/productContext.md`, `docs/memory-bank/activeContext.md`, `docs/memory-bank/progress.md`.
- Целевой roadmap-контракт для `EntryRecommendation`: `ROADMAP.md` (Phase 2.7.5).
- Текущие runtime hooks:
  - tick-density scan wiring и downgrade в `WATCHLIST`: `main.py`.
  - tick models/provider/band-depth/pit/volatility: `src/defi_agents/lp/`.
  - freshness confidence + score multipliers: `src/defi_agents/freshness/policy.py`.
  - текущий scoring pipeline: `src/defi_agents/scout/scout.py`.
  - операторский формат отчёта: `src/defi_agents/notifier.py`.

## 2) Verification evidence (обязательные команды плана 025)

Выполнено строго из плана:

1. `rg -n "tick_density|band_depth|pit|suggest_range|volatility|watchlist" main.py src docs tests`
2. `rg -n "LP Entry Recommendation|EntryRecommendation|network|pair|range" ROADMAP.md docs/plans docs/specs docs/research`

Ключевые факты из вывода:

- Runtime действительно пишет `band_depth_*`, `tick_data_quality`, `tick_pit_type`, `tick_pits_found` в metadata и делает degraded->watchlist downgrade в `main.py`.
- Target-поля `EntryRecommendation` зафиксированы в roadmap/plan (`chain/project/pair/fee_tier/range/confidence/reasons/watchlist_reason`).
- В коде есть `find_liquidity_pits()` и `suggest_range()` в `src/defi_agents/lp/pit_classifier.py`, но вызовы этих функций в runtime path отсутствуют (поиск по `src/*.py` на вызовы показал только определения и тесты).

## 3) Текущее фактическое состояние runtime (as-is)

### 3.1 Что уже есть для decision-layer

- Candidate-level ядро:
  - `chain`, `project`, `symbol(pair)`, `pool_meta`, `pool_id`, `address`, `underlying_tokens`.
- Scoring/economics:
  - `score`, `score_raw` (после freshness policy), `net_apy`, `net_profit_usd`, `net_profit_1k_usd`.
- Tick-density metadata:
  - `tick_data_quality`, `band_depth_1pct_usd`, `band_depth_2_5pct_usd`, `band_depth_5pct_usd`,
  - `tick_pit_type`, `tick_pits_found`, `tick_degradation_reason`,
  - `tick_daily_vol`, `tick_annual_vol`, `tick_vol_samples`, `tick_range_half_width_pct`.
- Quality/confidence:
  - `freshness_status`, divergence fields, `source_confidence`, `confidence_factor`.
- Fail-safe downgrade surfaces:
  - `report_group=ACTIONABLE|WATCHLIST`, `watchlist_reason`, `warn_reasons`.

### 3.2 Что критично отсутствует для `EntryRecommendation v1`

- Range recommendation в runtime не формируется:
  - `suggested_range_lower_tick/upper_tick` не записываются в metadata/report block.
  - Price-view диапазона также отсутствует.
- Pit/range functions пока не подключены в runtime scan path (есть только в модуле + тестах).
- Отдельного report-блока `LP Entry Recommendations` пока нет (есть общий Decision View).

## 4) Таблица соответствия: current runtime fields -> required `EntryRecommendation` fields

| Required EntryRecommendation field | Current source | Статус | Комментарий |
|---|---|---|---|
| `network`/`chain` | `candidate.chain` | ✅ READY | Уже есть в `ScoutCandidate`. |
| `project`/`protocol` | `candidate.project` | ✅ READY | Уже есть. |
| `pair` | `candidate.symbol` (+ `underlying_tokens`) | ✅ READY | Для v1 можно брать `symbol`; для v1.1 нормализовать через токены. |
| `fee_tier` | `pool_meta` -> `_parse_fee_tier()` | 🟡 DERIVABLE | Парсинг уже есть в runtime scan path, но поле не в финальном recommendation-контракте. |
| `suggested_range_lower_tick` | `BandDepthResult.suggested_range_lower_tick` | ❌ MISSING (runtime) | Поле есть в модели, но не заполняется в `scan_pool_band_depth()`. |
| `suggested_range_upper_tick` | `BandDepthResult.suggested_range_upper_tick` | ❌ MISSING (runtime) | Аналогично. |
| `suggested_range_lower_price` | Derived from tick + pool decimals | ❌ MISSING | В runtime не вычисляется/не публикуется для рекомендаций. |
| `suggested_range_upper_price` | Derived from tick + pool decimals | ❌ MISSING | В runtime не вычисляется/не публикуется для рекомендаций. |
| `confidence` | `source_confidence` + `confidence_factor` | 🟡 DERIVABLE | Есть primitives, нужен единый banding контракт `HIGH/MEDIUM/LOW` или numeric band. |
| `reason_codes` | `warn_reasons` (+ degradation reason) | ✅/🟡 PARTIAL | Есть список причин, нужен нормализованный список для EntryRecommendation. |
| `watchlist_reason` | `watchlist_reason` | ✅ READY | Уже выставляется при downgrade по tick quality. |
| `actionability` | `report_group` | ✅ READY | `ACTIONABLE/WATCHLIST` уже есть. |

## 5) Сравнение range-policy альтернатив

### A) Pit-based

**Идея:** использовать `find_liquidity_pits()` + `suggest_range()` без `daily_vol` (границы от pit boundaries + margin).  
**Плюсы:**
- Привязка к реальной microstructure ликвидности.
- Хорошо для low-vol/stable сегмента.
**Минусы:**
- Слабая адаптация к regime-shift волатильности.
- Риск «слишком узкого» range на волатильных парах.

### B) Volatility-adjusted

**Идея:** ширина диапазона от `k * sigma_daily * sqrt(holding_days)` (уже реализовано в `volatility.py` и поддержано в `suggest_range`).  
**Плюсы:**
- Устойчиво к изменению режима волатильности.
- Простая калибровка через `k`, `holding_days`, cap/floor.
**Минусы:**
- Без pit-context может игнорировать локальные «конкурентные» зоны ликвидности.
- Требует надежной ценовой истории.

### C) Hybrid (pit + volatility) — **рекомендованный v1-default**

**Идея:**
1) центр диапазона от nearest `CONFIDENT_PIT` (или spot fallback),  
2) half-width = `max(pit_min_width, vol_width)` c upper cap,  
3) выравнивание по `tickSpacing`,  
4) fail-safe downgrade при недостатке любого критичного входа.

**Почему v1-default:**
- Минимизирует риск «узкого pit-only» в high-vol,
- и одновременно не теряет microstructure edge (в отличие от pure-vol).
- Опирается на уже существующие функции, но требует wiring в runtime (P0 backlog).

## 6) Предложенная модель v1 (network/pair/range + scoring)

### 6.1 Network/pair selection (deterministic)

Гейт кандидата в EntryRecommendation:

1. Chain in v1 scope: `Base | Arbitrum`.
2. Venue in v1 scope: `Uniswap v3 | Aerodrome Slipstream`.
3. `report_group == ACTIONABLE` после freshness + tick fail-safe policy.
4. `tick_data_quality == OK` для actionable-рекомендаций.
5. `net_profit_usd > 0` и/или `net_profit_1k_usd >= configurable floor`.

### 6.2 Range selection (hybrid default)

Псевдополитика v1:

- `pit = nearest CONFIDENT_PIT` (если нет -> spot fallback).
- `vol_width = k * sigma_daily * sqrt(holding_days)`.
- `pit_width = width_from_pit_boundaries(+margin)`.
- `final_half_width = clamp(max(pit_width, vol_width), min_w, max_w)`.
- `lower_tick/upper_tick` align по `tickSpacing`.
- Если `tick_data_quality != OK` или range invalid -> `WATCHLIST` + reason.

### 6.3 Ranking formula v1 (proposal)

Для минимального изменения существующего пайплайна:

`rank_v1 = score_raw * confidence_factor * tick_quality_factor * range_quality_factor * economics_factor`

Где:
- `score_raw` — существующая база из scout scoring,
- `confidence_factor` — уже реализованные multipliers,
- `tick_quality_factor`: `1.0` при `tick_data_quality=OK`, иначе `0.0` (actionable path),
- `range_quality_factor`: `1.0` если range валиден, иначе `0.0`,
- `economics_factor`: плавный multiplier от `net_profit_1k_usd` (например через min-profit floor).

Top-N формируется сортировкой `rank_v1 DESC` по actionable, затем отдельный watchlist tail.

## 7) Confidence bands + fail-safe downgrade

### Confidence bands (proposal)

- **HIGH**:
  - `source_confidence=VERIFIED`,
  - `tick_data_quality=OK`,
  - range valid/aligned,
  - без критичных деградаций.
- **MEDIUM**:
  - `source_confidence=AGGREGATOR_ONLY`,
  - `tick_data_quality=OK`,
  - range valid, но неполная валидация данных.
- **LOW**:
  - `DIVERGED|STALE` или missing/invalid range, либо degraded tick.

### Fail-safe downgrade rules (v1)

Кандидат принудительно переводится в `WATCHLIST`, если:

1. `tick_data_quality != OK`.
2. `freshness_status != FRESH` при включенной strict freshness policy.
3. `source_confidence in {DIVERGED, STALE}`.
4. `suggested_range` отсутствует или невалиден (`lower >= upper` / misaligned spacing).
5. Экономика ниже floor (`SMALL_CAP_UNPROFITABLE` / non-positive net).

## 8) Gaps / Risks backlog (P0/P1)

## P0 (must-have для v1 implementation)

1. Подключить pit pipeline в runtime scan (`build_price_bins` -> `find_liquidity_pits` -> `suggest_range`).
2. Заполнять `BandDepthResult.suggested_range_lower_tick/upper_tick` (+ price view fields в recommendation contract).
3. Ввести explicit `EntryRecommendation` model + builder из текущего `ScoutResult`.
4. Добавить deterministic `rank_v1` и Top-N selection с `ACTIONABLE`/`WATCHLIST` split.
5. Добавить report block `LP Entry Recommendations` в notifier.
6. Тесты fail-safe: degraded/stale/diverged/range-invalid никогда не actionable.

## P1 (после v1)

1. Stability gate `>=3 observations / 6h` для pit confidence.
2. Multi-venue comparison по одной паре (`same chain + pair`).
3. Калибровка коэффициентов `k`, `holding_days`, confidence cutoffs на shadow evidence.
4. Нормализация пары по token addresses + fee-tier disambiguation (не только `symbol`).
5. Метрики качества ранжирования: precision actionable / watchlist share / top-N stability.

## 9) Ограничения исследования

- Это research-only артефакт: runtime-код не менялся.
- Выводы ограничены текущими артефактами репозитория и результатами двух обязательных `rg` команд.
- Runtime-метрики «как ведет себя в проде» не выводились из предположений; только из кода/доков.

