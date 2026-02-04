Понял задачу: собрать **decision-grade intake** без “переписать всё”, сохранив **risk-first инварианты**, и внедрять **поэтапно** поверх текущего DeFiLlama pipeline. Ниже — прикладное исследование и план внедрения.

---

## Раздел 1 — Executive Summary (≈1 страница)

### Почему DeFiLlama “лагает” относительно UI

DeFiLlama yields — отличный **broad discovery**, но это “агрегатор поверх агрегаторов”: данные часто собираются из субграфов/скриптов и перерасчитываются пакетно. Для сигналов уровня “входить сейчас” вам нужен **direct-source re-check** перед алертом.

### Главная идея: 3-ступенчатая модель intake (минимальный риск)

1. **Discovery:** DeFiLlama остаётся как широкое сито кандидатов.
2. **Pre-alert re-check (v1, MVP):** для каждого “кандидата на алерт” вы делаете 1–2 быстрых запроса в **официальный источник протокола** (subgraph / официальный API) и вычисляете freshness/divergence.
3. **Selective multi-source intake (v2):** для топ-протоколов вы начинаете тянуть данные напрямую постоянно (по расписанию), строите собственный “truth layer” и не зависите от DeFiLlama в критическом пути.

### Что считать “официальным источником”

* Для многих DEX и лендинга, “официальный источник” на практике = **субграф на The Graph** (GraphQL) + иногда отдельный REST/GraphQL API у протокола.
* Uniswap прямо описывает субграф как способ получать данные по протоколу. ([docs.uniswap.org][1])
* Balancer описывает субграфи и отмечает необходимость API key для “нерейтлимитных” эндпоинтов. ([docs-v2.balancer.fi][2])
* Aave публикует протокольные субграфы и отдельный API для исторических/рыночных данных. ([GitHub][3])
* Morpho даёт собственный GraphQL-API (и отдельно субграфи). ([docs.morpho.org][4])
* Curve имеет отдельный API-слой (OpenAPI/документация). ([GitHub][5])

### Ключевой риск и как его закрыть

**Риск:** даже direct sources могут лагать (индексация, rate limits, деградации).
**Контрмера:** вы вводите **Freshness & Divergence policy** + **no-silent-fallback**: если direct-check недоступен/расходится — сигнал не становится actionable, уходит в watchlist, а в Telegram приходит отдельный “UNVERIFIED / STALE”.

---

## Раздел 2 — Таблица сравнения источников (DEX / Lending)

> Latency ниже — это *оценка класса источника*. Конкретные значения staleness вы будете измерять сами (см. policy и DoD).

| Source                                   | Coverage (chains/pools)                |                                                                 Data latency | Key fields                                                                             | Auth                                                                | Rate limits                                                           | Reliability risk                                                   | Integration effort |
| ---------------------------------------- | -------------------------------------- | ---------------------------------------------------------------------------: | -------------------------------------------------------------------------------------- | ------------------------------------------------------------------- | --------------------------------------------------------------------- | ------------------------------------------------------------------ | ------------------ |
| Uniswap Subgraph (GraphQL)               | per-chain subgraph                     |            near-real-time; индексируется по событиям ([docs.uniswap.org][6]) | pools, swaps, liquidity, volume, fees, ticks (частично) ([docs.uniswap.org][7])        | Graph API key (через gateway) ([The Graph][8])                      | quota/платежи/лимиты по plan; есть free tier 100k/mo ([The Graph][9]) | schema drift, индексинг лаг, зависимость от Graph gateway          | Medium             |
| Aerodrome Subgraph (GraphQL, Base)       | Base DEX                               |                    near-real-time; через Graph explorer ID ([The Graph][10]) | pairs/pools, swaps, liquidity, daily stats (зависит от схемы)                          | Graph API key                                                       | как у Graph gateway                                                   | зависит от поддержки субграфа/обновлений                           | Medium             |
| Curve API (REST/OpenAPI)                 | pools/gauges (по докам curve-api/core) | near-real-time (API-слой поверх onchain + расчёты) *(часть полей расчетные)* | список пулов, gauges, APY/metadata (вариативно) ([GitHub][5])                          | обычно без auth (уточнять per endpoint)                             | не стандартизировано публично → измерять/дросселить                   | API может менять поля/формулы                                      | Medium             |
| Balancer Subgraph (GraphQL)              | Balancer v2                            |                      event-driven, near-real-time ([docs-v2.balancer.fi][2]) | pools, swaps, liquidity, tokensList, historical aggregates ([docs-v2.balancer.fi][11]) | Graph API key для non-rate-limited ([docs-v2.balancer.fi][2])       | как у Graph gateway                                                   | schema changes/подграф обновления                                  | Medium             |
| Aave Protocol Subgraphs (GraphQL)        | multi-chain (v3)                       |                                    event-driven; snapshots/агрегации с лагом | reserves, user positions, snapshots ([GitHub][3])                                      | Graph API key                                                       | как у Graph gateway                                                   | лаг по snapshots; версионирование                                  | Medium             |
| Aave API v2 (REST)                       | market/rates history endpoints         |                                         зависит от сервиса; часто ближе к UI | rates-history, pools, staking stats ([aave-api-v2.aave.com][12])                       | без user auth (по докам)                                            | не описано публично → измерять                                        | vendor endpoint может менять контракт                              | Low–Medium         |
| Morpho API (GraphQL)                     | markets/vaults (+ rewards)             |                                 designed for bots/dashboards; near-real-time | markets, vaults, positions, rewards ([docs.morpho.org][4])                             | публичный GraphQL endpoint (указан в доках) ([docs.morpho.org][13]) | лимиты не всегда явные → измерять; кешировать                         | chain coverage “subset” (в доках отмечено) ([docs.morpho.org][14]) | Low                |
| Spark subgraph (GraphQL)                 | per-network subgraph                   |                                                event-driven; через Graph API | protocol data via subgraph ([GitHub][15])                                              | Graph API key                                                       | как у Graph gateway                                                   | зависимость от поддерживаемости сабграфа                           | Medium             |
| Compound v3 community subgraph (GraphQL) | mainnet etc.                           |                      event-driven; через Graph explorer ID ([The Graph][16]) | markets/comet events/positions                                                         | Graph API key                                                       | как у Graph gateway                                                   | community-maintained                                               | Medium             |

---

## Раздел 3 — Short-list источников для MVP (Top 3–5)

Цель MVP: **перед алертом подтверждать APR/TVL/volume/fees/утилку из direct source**, не расширяя blast radius.

### 1) Uniswap Subgraph (GraphQL через The Graph)

Почему: крупнейшая база CL-рынков, богатая схема по пулам/свапам, удобен для DEX-метрик. ([docs.uniswap.org][1])

### 2) Aave: субграф + Aave API v2

Почему: для lending важны **utilization, borrow/supply rate, liquidity** и их история; REST API v2 даёт “rates-history/pools” близко к UI, субграф — как fallback/validation. ([aave-api-v2.aave.com][12])

### 3) Morpho API (GraphQL)

Почему: протокол сам даёт API для рынков/вальтов/наград, очевидно заточен под ботов/дашборды. ([docs.morpho.org][4])

### 4) Aerodrome Subgraph (если вы мониторите Base/OP-экосистему)

Почему: высокое влияние на Base-ликвидность; сабграф уже доступен через Graph Explorer (быстро подключить). ([The Graph][10])

### 5) Curve API (как “stable yield” источник)

Почему: stable-пулы важны для вашего use-case, Curve имеет отдельный API-слой (но нужно дисциплинированно валидировать расчетные поля). ([GitHub][5])

---

## Раздел 4 — Target architecture (v1 → v2 roadmap) + внедрение по неделям

### v1 (MVP): DeFiLlama discovery + direct-source re-check перед алертом

**Pipeline (не ломает текущий):**

1. **Ingest:** DeFiLlama yields → кандидаты.
2. **Filter (risk-first):** allowlist chains + min TVL + token sanity + blacklist. *(инварианты сохраняем)*
3. **Direct re-check (async fanout):**

   * определить `source_id` по `project/chain/pool_id`
   * 1 запрос в direct source за **точками правды** (см. unified schema ниже)
4. **Decision layer:**

   * рассчитать freshness/divergence
   * `FRESH` → можно алертить
   * `STALE/UNVERIFIED` → watchlist + отдельный “non-actionable” алерт
5. **Telegram output**: actionable отдельно от watchlist.

### v2: selective multi-source intake (постоянный сбор прямых источников)

* Для Top-протоколов запускаете **периодические поллеры** (каждые N минут), пишете в timeseries store.
* DeFiLlama остаётся как discovery и как “coverage fallback”, но **не в критическом пути**.

### По неделям

* **Неделя 1:** v1 для 2 источников (Uniswap + Aave API).
* **Неделя 2:** добавить Morpho API + Aerodrome subgraph.
* **Неделя 3:** Curve API + стабилизация, метрики расхождений.
* **Неделя 4+:** начать v2 ingestion для top-N пулов, backfill, hardening.

---

## Раздел 3.5 — Unified schema + mapping (core)

Минимальный unified schema (ваш “truth record”):

* `chain_id` (e.g., 1, 10, 8453)
* `project` (string; canonical)
* `pool_id` (canonical: contract address / pool address / market id)
* `pair` (e.g., "OP/USDC")
* `apy` (float, annualized; + `apy_components`: base/reward/fees)
* `tvl_usd` (float)
* `volume_24h_usd` (float)
* `fees_24h_usd` (float)
* `utilization` (lending)
* `timestamp_observed` (UTC)
* `source_id` (e.g., `graph:subgraph_id`, `rest:aave-api-v2`, `graphql:morpho-api`)
* `source_block` (if available)
* `age_minutes` (computed)
* `quality_status` ∈ {FRESH, STALE, UNVERIFIED}

**Mapping strategy:**

* DEX pools: `pool_id = pool address` (или pair address) + chain.
* Lending markets: `pool_id = market/reserve identifier` + chain.
* Для Graph-сабграфов: хранить `subgraph_id` (из Graph Explorer) как часть `source_id`. ([The Graph][8])

---

## Раздел 3.6 — Conflict-resolution (когда источники расходятся)

**Правило 0 (risk-first):** если расхождение выше порога и вы не можете объяснить — **не actionable**.

Приоритет источников *по полям*:

* `tvl_usd`: protocol-native API/сабграф > агрегатор.
* `apy`:

  * lending: protocol API/сабграф (rate model) > агрегатор
  * DEX fee APY: лучше считать самим из `fees_24h` и `tvl` (если доступны) → снижает “магические формулы”.
* `rewards`: только протокольные источники (или явно помечать “rewards_unverified”).

**Стратегия объединения:**

* `median-of-2+` если у вас ≥2 direct sources (v2), иначе “winner-takes-all” по trust score.
* trust score = стабильность источника + наличие `source_block` + историческая согласованность с UI.

---

## Раздел 4 — Freshness & divergence policy (пороги + downgrade)

### Рекомендуемые пороги (стартовые, затем калибровка по метрикам)

**Freshness:**

* DEX: `age_minutes <= 5` → FRESH; 5–30 → STALE; >30 → UNVERIFIED
* Lending: `age_minutes <= 10` → FRESH; 10–60 → STALE; >60 → UNVERIFIED
  *(Почему разные: lending ставки меняются реже, DEX fees/volume — быстрее.)*

**Divergence:**

* `apy_divergence_pct`:

  * stable lending: 5–10%
  * incentives/rewards: 15–25% (часто сложные формулы)
  * DEX fee APY: 10–15%
* `tvl_divergence_pct`: 10–20% (в зависимости от волатильности ассетов)

### Downgrade логика (не допустить silent false-positive)

* Если direct source недоступен (timeout/429/5xx) → **UNVERIFIED** (не actionable) + отдельный ops-алерт “source_down”.
* Если `STALE`, но APY высокий → **watchlist** (не actionable) и повторная проверка через X минут.
* Если divergence высокий → **UNVERIFIED** + divergence-alert (для дебага маппинга/формул).

---

## Раздел 5 — Стоимость и операционка (support cost + риски + fallback)

### Что реально “болит” в проде

1. **Rate limits / billing** у Graph gateway: есть free quota и биллинг/лимиты по API keys, можно ставить spending limit. ([The Graph][9])
2. **Schema drift** у сабграфов (особенно community): ломаются поля/названия.
3. **Partial coverage** (протоколы не на всех chain одинаково доступны). Morpho прямо отмечает “subset of chains” для API. ([docs.morpho.org][14])
4. **Кэш и дедупликация:** без агрессивного caching вы упрётесь в лимиты и стоимость.

### Fallback механика (без silent fallback)

* Если direct source упал:

  * **не подменять тихо** на DeFiLlama,
  * пометить запись `UNVERIFIED`,
  * отправить **ops-алерт** + перевести кандидата в watchlist.
* Если DeFiLlama видит yield, а direct source не мапится (pool_id mismatch):

  * пометить `UNVERIFIED: mapping_missing`,
  * создать task в backlog на маппинг.

---

## Раздел 4.5 — Технические детали интеграции (Python async, production-grade)

**Клиенты:**

* GraphQL: пул соединений, persisted queries где возможно, лимит на depth/complexity.
* REST: aiohttp + retry/backoff + jitter.

**Resilience:**

* per-source circuit breaker (open/half-open)
* per-source rate limiter (token bucket)
* “hedged requests” только для *read* (иногда помогает убрать tail latency, но осторожно с лимитами)

**Observability:**

* latency histogram per source
* % ошибок по классам (429/5xx/timeouts)
* staleness distribution (median/p95) по каждому источнику

---

## Раздел 5 — Implementation backlog

### P0 (неделя 1) — минимальный direct re-check (не ломая pipeline)

* [ ] Ввести `source_registry` (конфиг маппинга проект→источник→эндпоинт/сабграф id).
* [ ] Реализовать Graph gateway client (API key, budgeting). ([The Graph][8])
* [ ] Добавить Uniswap direct re-check: `tvl`, `volume/fees`, `last_updated` (через сабграф). ([docs.uniswap.org][1])
* [ ] Добавить Aave direct re-check (через Aave API v2): текущие/исторические rates. ([aave-api-v2.aave.com][12])
* [ ] Внедрить `quality_status` + policy (FRESH/STALE/UNVERIFIED) + “no actionable if not FRESH”.

### P1 (неделя 2–3) — расширение покрытия + калибровка divergence

* [ ] Подключить Morpho API (GraphQL) + rewards поля. ([docs.morpho.org][4])
* [ ] Подключить Aerodrome сабграф (Base) и верифицировать маппинг pool_id. ([The Graph][10])
* [ ] Ввести conflict-resolution rules (field-level precedence) + divergence-alerts.
* [ ] Добавить метрики staleness vs UI (см. DoD).

### P2 (после стабилизации) — selective ingestion (v2)

* [ ] Планировщик поллеров для top-N источников (каждые 1–5 минут DEX, 5–15 минут lending).
* [ ] Timeseries store для “truth records” (even SQLite/duckdb на MVP, дальше — Postgres/Timescale).
* [ ] Автоматическая валидация schema (GraphQL introspection snapshot + тестовые запросы в CI).
* [ ] Добавить Curve API и/или Balancer сабграф по приоритету стратегий. ([docs-v2.balancer.fi][11])

---

## Раздел 6 — DoD / метрики успеха (чётко)

**DoD для v1 (MVP):**

* ≥ 80% “actionable alerts” имеют `freshness=FRESH` (по вашим порогам).
* ≥ 90% actionable по топ-источникам сходятся с UI в пределах:

  * `apy_divergence_pct <= 10%` (lending),
  * `tvl_divergence_pct <= 15%`.
* Доля `UNVERIFIED` среди всех кандидатов ≤ 20% (если больше — маппинг/лимиты/источники).

**Метрики (операционные):**

* `freshness_fresh_share = count(FRESH actionable) / count(actionable total)`
* `ui_divergence_median` и `ui_divergence_p95` по полям (apy/tvl)
* `unverified_share` и причины (mapping_missing / source_down / stale)
* `divergence_alert_rate` (должно падать со временем, если маппинг стабилизируется)

---

### Две “hypothesis”, которые нужно подтвердить измерением (не догадками)

1. **Staleness сабграфов**: обычно минуты, но хвост может быть десятки минут при деградациях индексации. (Нужно измерить: `chain_head_time - source_last_update_time`.)
2. **APR/APY формулы UI vs агрегатор**: UI часто включает/исключает rewards иначе (особенно для Curve-подобных пулов). (Нужно валидировать компонентно: base + rewards + fees.)

---

Если хотите, следующий шаг сделаю максимально прикладным: дам **конкретный “source_registry.yaml” формат**, и список **минимальных запросов GraphQL** (по 1 запросу на протокол) так, чтобы вы за 1–2 вечера собрали working MVP re-check в вашем async pipeline.

[1]: https://docs.uniswap.org/api/subgraph/overview?utm_source=chatgpt.com "Overview"
[2]: https://docs-v2.balancer.fi/reference/subgraph/?utm_source=chatgpt.com "V2 Subgraphs"
[3]: https://github.com/aave/protocol-subgraphs?utm_source=chatgpt.com "The code of Aave protocol subgraphs"
[4]: https://docs.morpho.org/tools/offchain/api/get-started/?utm_source=chatgpt.com "Morpho API"
[5]: https://github.com/curvefi/curve-api-core?utm_source=chatgpt.com "curvefi/curve-api-core"
[6]: https://docs.uniswap.org/contracts/v2/reference/API/overview?utm_source=chatgpt.com "API Overview"
[7]: https://docs.uniswap.org/sdk/v3/guides/web3-development-basics?utm_source=chatgpt.com "Web3 Development Basics"
[8]: https://thegraph.com/docs/en/subgraphs/querying/introduction/?utm_source=chatgpt.com "How to Query a Subgraph Using The Graph | Docs"
[9]: https://thegraph.com/docs/fr/subgraphs/guides/polymarket/?utm_source=chatgpt.com "Interroger les données de la blockchain à partir ..."
[10]: https://thegraph.com/explorer/subgraphs/GENunSHWLBXm59mBSgPzQ8metBEp9YDfdqwFr91Av1UM?chain=arbitrum-one&view=Query&utm_source=chatgpt.com "Aerodrome Base Full"
[11]: https://docs-v2.balancer.fi/reference/subgraph/core/queries.html?utm_source=chatgpt.com "Querying"
[12]: https://aave-api-v2.aave.com/?utm_source=chatgpt.com "Aave API Documentation"
[13]: https://docs.morpho.org/tools/offchain/api/morpho/?utm_source=chatgpt.com "Morpho Markets"
[14]: https://docs.morpho.org/build/earn/tutorials/get-data?utm_source=chatgpt.com "Get Data"
[15]: https://github.com/sparkdotfi/spark-utilities?utm_source=chatgpt.com "sparkdotfi/spark-utilities"
[16]: https://thegraph.com/explorer/subgraphs/5nwMCSHaTqG3Kd2gHznbTXEnZ9QNWsssQfbHhDqQSQFp?chain=arbitrum-one&view=Query&utm_source=chatgpt.com "Compound V3 Mainnet"
