кроме стейкинга, lending/borrowing и LP есть еще несколько больших источников дохода. Их удобно делить на “базовый yield” и “инцентивы/премии за риск”.

1. Perps / funding carry (delta-neutral)
- Доход: funding + иногда rebate/points.
- Риск: резкие изменения funding, ликвидации при плечах, контрагентский риск биржи/DEX.

2. Basis / cash-and-carry (spot vs futures)
- Доход: фьючерсная премия (basis) при хедже.
- Риск: ликвидность, маржинальные требования, “basis crush”.

3. Arbitrage / MEV (DEX price arb, liquidations)
- Доход: спред/ликвидационные бонусы.
- Риск: инфраструктура, конкуренция, gas, приватные реле, большой операционный риск.

4. Options / volatility selling (covered calls, short puts, LP-like vaults)
- Доход: премии.
- Риск: хвостовые события (vol spikes), недооценка gamma/vega, “страховка” дорого.

5. Protocol revenue share / fee switches / veTokenomics
- Доход: доля комиссий/бребейты/бусты (Curve/Convex-подобное).
- Риск: governance, эмиссия, политический риск протокола.

6. Liquidity mining / points / airdrop farming
- Доход: токены/очки (иногда основной компонент APY).
- Риск: размытие, отсутствие ликвидности, “календарный” риск (закончились стимулы).

7. RWA yield (tokenized T-bills / private credit)
- Доход: процент от реальных активов.
- Риск: регуляторика, кастодиан, redemption/ликвидность, контрагент.

8. Structured products / vault strategies (looping, leverage, automated rebalancing)
- Доход: комбинация lending + LP + incentives + hedges.
- Риск: сложность, скрытые допущения, liquidations, интеграционный риск.

Если цель “универсального” скаута: самый практичный следующий шаг — формально добавить класс “derivatives carry” (funding/basis) и “incentives quality” (доля rewards в APY и liquidity/exit for rewards) как отдельные risk-gates, иначе бот будет постоянно поднимать “высокий APY”, который на деле весь из точек/эмиссии.

Тогда “универсальный скаут” стоит строить как сборщик нормализованных фактов + риск-гейты, а не как “поисковик APY”.

Что именно “самое важное” собирать (decision-grade, минимум):

1. Что это за доход
- `yield_type`: `staking | lending_supply | lending_borrow | lp_fees | incentives | funding_carry | basis | options_premium | rwa`
- `base_vs_incentives`: доля `apy_base` и `apy_reward` (если reward доминирует, это отдельный риск-тег).

2. Можно ли реально войти/выйти
- `tvl_usd`, `vol_24h_usd`, `vol_to_tvl` (и/или `tvl_to_vol`), спред/глубина (если есть источник).
- Для lending: `available_liquidity`, caps, paused/frozen.

3. Риски протокола и контракта
- security-screen: proxy/owner/roles/paused, репутация/аудит/инциденты, whitelist/blacklist.
- для стейблов: tier/class/FX risk.

4. Риски позиции
- `il_risk` (LP), `liq_risk` (borrow/loop), `depeg_risk` (stable), `funding_flip_risk` (perps), `counterparty_reg_risk` (RWA).

5. Привязка к действиям
- ссылка на пул/маркет, chain, протокол, токены, “почему это в отчете” (top reasons), “что проверить руками” (missing data).

Практически в нашем проекте это ложится на 3 отдельных “вывода”:
- `Discovery` (широкий intake) -> факты.
- `Verification` (freshness + protocol inspector) -> достоверность.
- `Decision View` (telegram) -> коротко и с тэгами/цветами.


**Как бы я это формализовал (без лишней магии):**

1. **Taxonomy (направления дохода) как SSOT**
- `lp_fees` (DEX pools, отдельно `stable/stable`, `token/stable`, `token/token`)
- `lending_supply` / `lending_borrow` (markets/reserves)
- `staking` (LST/LRT, native staking, vault-like staking)
- `incentives` (points/emissions как отдельный слой, не “основной yield”)
- позже: `funding_carry` / `basis` (perps/futures), `options_premium`, `rwa`

2. **Two-step verification (confidence)**
- Intake: DeFiLlama даёт `APY/TVL/volume` (где есть) + базовые метаданные.
- Re-check: адаптеры “первого источника” подтверждают минимум `TVL + rate` (для DEX — subgraph/DEX API; для lending — AaveKit/аналог; для стейкинга — официальный endpoint/ончейн).
- Вывод: `freshness_status` + `source_confidence` (например `AGGREGATOR_ONLY / VERIFIED / DIVERGED / STALE`).

3. **Top-10 per direction (что именно ранжируем)**
- Для каждого `yield_type` считаем “rank score” = (доходность) × (liquidity/capacity) × (risk gates) × (confidence).
- В Telegram показываем 2 витрины: `ACTIONABLE` (verified/ok) и `WATCHLIST` (unverified/partial), чтобы не терять идеи, но не вводить в заблуждение.

4. **Protocol Inspector как отдельный сервис — это правильно**
- Его роль: “можно ли доверять контрактному контролю/апгрейдам/пауза-рискам”.
- Интеграция с Scout: если протокол/контракт “новый/неизвестный”, Scout добавляет его в очередь инспектора и помечает результаты как `WATCHLIST` до получения dossier/verdict.
- В отчёте у строки пула добавляется короткий тег `Inspector:PASS/WATCHLIST/FAIL` + ссылка на dossier (локальный кэш/или краткий репорт).

**Следующий практический шаг (минимальный, но дающий пользу):**
1. Зафиксировать SSOT для `yield_type` и правила Top-10 (спек на 1 страницу).
2. Добавить в Telegram отдельные секции `Top-10 LP`, `Top-10 Lending Supply`, `Top-10 Cheapest Borrow`, `Top-10 Staking` с лимитами и сортировкой.
3. Подключить “очередь” в Protocol Inspector от новых протоколов из Scout (только добавление целей + WATCHLIST до результата).

