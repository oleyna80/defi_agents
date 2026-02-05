# DeFi Strategy Library (EVM + Solana) — risk-first

## Важные оговорки (коротко)

* **15%+ на стейблах почти всегда означает “оплата риском”**: incentives/points, кредитный риск, риск де-пега, smart-contract, или скрытая экспозиция к волатильности.
* Везде ниже предполагается фильтр: **TVL пула/рынка > $10M**, иначе агент ставит `UNVERIFIED`/`WATCHLIST` (как минимум).
* Все APY — “консервативные вилки” и **не гарантия**.

---

## 🟢 Tier 1 — Passive & Single-Sided (Foundation)

### 1) Liquid Staking (ETH / SOL)

**Strategy Name:** Liquid Staking Core
**Logic (Alpha):** базовый staking yield сети (плюс MEV на Solana LST).
**Composability Stack:**

* ETH: Lido
* SOL: Jito / Marinade
  **Step-by-Step Execution:**

1. Купить ETH/SOL.
2. Минтить LST (stETH/jitoSOL/mSOL).
3. Держать (или использовать как залог в Tier 3–4).
   **Risk Profile:** slashing, smart-contract (LST), LST discount/premium, chain risk.
   **Expected APY Range (conservative):**

* stETH ~ **2–4%** ([stake.lido.fi][1])
* jitoSOL ~ **5–7%** ([defillama.com][2])

---

### 2) Blue-chip Lending (стейблы / majors)

**Strategy Name:** Single-sided Lending
**Logic (Alpha):** процент от заемщиков (utilization-driven).
**Composability Stack:** Aave (добавочно: Spark)
**Step-by-Step Execution:**

1. Внести USDC/USDT/DAI.
2. Следить за utilization/ставками, при необходимости мигрировать между сетями/маркетами.
3. (Опционально) включить авто-реинвест (Tier 2 через агрегатор).
   **Risk Profile:** smart-contract, risk параметров, bad debt в экстремумах, oracle/liq events.
   **Expected APY Range (conservative):**

* USDC supply на Aave часто **3–7%** (сильно плавает по рынкам/сетям) ([Aave][3])

---

### 3) Yield-bearing Stablecoins (sUSDe / sDAI)

**Strategy Name:** Yield-Bearing Stable Core
**Logic (Alpha):** “встроенный” доход (staking/funding/treasury-like) упакован в токен.
**Composability Stack:** Ethena + Spark (sDAI/DSR)
**Step-by-Step Execution:**

1. Минт/купить sUSDe или sDAI.
2. Держать либо использовать как залог/LP leg в Tier 2–4.
3. Контролировать концентрацию и лимиты протокола.
   **Risk Profile:** depeg, контрагентский/hedge-risk (для синтетических), governance-risk (DSR-rate).
   **Expected APY Range (conservative):**

* sUSDe ~ **3–6%** ([App | Ethena][4])
* DAI Savings/DSR около **1–5%** (в зависимости от режима монетарной политики; актуальное значение может быть низким) ([spark][5])

---

## 🔵 Tier 2 — LP & Farming (Intermediate)

### 4) Stable/Stable LP (fee-driven, low IL)

**Strategy Name:** Stable-Stable Fee Capture
**Logic (Alpha):** комиссии свопов при минимальном IL.
**Composability Stack:** Uniswap (stable пары), Curve / (опционально) Convex-слой
**Step-by-Step Execution:**

1. Выбрать stable/stable пул с TVL>10M.
2. LP (на v3/StableSwap).
3. Ребаланс/перекладка при падении объема/комиссий.
   **Risk Profile:** smart-contract, depeg одного из стейблов, curve-risk/peg mechanics.
   **Expected APY Range (conservative):** **2–8%**
   Примеры “живых” уровней (на дату источника):

* USDC-USDT Uniswap v3 ~5%+ ([defillama.com][6])
* USDC-crvUSD через Convex ~6%+ ([defillama.com][7])

---

### 5) CLMM “Managed Ranges” (концентрированная ликвидность с управлением)

**Strategy Name:** CLMM Range Harvest
**Logic (Alpha):** повышенная fee-эффективность за счет узкого диапазона + (иногда) incentives.
**Composability Stack:**

* EVM: Uniswap v3-style / Aerodrome (Base)
* Solana: Kamino (как менеджер диапазонов)
  **Step-by-Step Execution:**

1. Определить режим: range / trend.
2. Выставить диапазон (узкий в range, широкий в trend).
3. Триггеры ребаланса: выход цены за band, падение volume, рост IL.
   **Risk Profile:** IL (главный), “липкие” тренды, MEV/LP-JIT, smart-contract.
   **Expected APY Range (conservative):** **5–20%** (высоко вариативно; incentives могут раздуть цифры).
   Примечание: Aerodrome — крупный DEX на Base (TVL сотни млн) ([defillama.com][8]); Kamino как liquidity manager описывает авто-диапазоны/ребаланс ([defillama.com][9])

---

### 6) Auto-Compounding через агрегаторы

**Strategy Name:** Vault Auto-Compound
**Logic (Alpha):** тот же базовый yield, но “без ручного сложного процента”, иногда +оптимизация harvesting.
**Composability Stack:** Beefy / Yearn
**Step-by-Step Execution:**

1. Выбрать vault с прозрачной стратегией (без экзотики).
2. Проверить underlying pool TVL>10M и риски reward-токенов.
3. Держать; ребаланс при ухудшении risk/return.
   **Risk Profile:** добавляется риск агрегатора + стратегия может меняться.
   **Expected APY Range (conservative):** **4–12%** (на стейблах) / **8–25%** (на risk-on, но это уже ближе к Tier2/3 по риску).
   Справочно: Beefy/Yearn как yield-агрегаторы ([defillama.com][10])

---

## 🟣 Tier 3 — Delta-Neutral & Hedging (Advanced)

### 7) Cash & Carry (Spot/LST + Perp Short) — “Funding Capture”

**Strategy Name:** Delta-Neutral Basis (LST + Perp)
**Logic (Alpha):** доход = (staking/LST yield) + (funding, если положительный) − (fees/drag).
**Composability Stack:** LST (Tier1) + Perps: Hyperliquid / dYdX
**Step-by-Step Execution:**

1. Купить ETH или LST (например stETH).
2. Открыть **short perp 1x** на эквивалентную дельту.
3. Риск-контроль: funding flips, basis blow-out, маржинальные буферы.
   **Risk Profile:** funding может стать отрицательным, tail-moves (gap), ликвидация при недостаточном margin, биржевой/маркет-risk.
   **Expected APY Range (conservative):** **4–15%** (в хорошие периоды может быть выше; в плохие — почти ноль или минус).
   Факты “масштаба/ликвидности” Hyperliquid (OI/объем) для реализуемости стратегии ([defillama.com][11])

---

### 8) “LP as the House” на perps-DEX (заработок на проигрыше трейдеров)

**Strategy Name:** Perp LP (Trader PnL Capture)
**Logic (Alpha):** LP зарабатывает на комиссиях/спредах/часто на net-PnL трейдеров + ребаланс пула.
**Composability Stack:** GMX (мульти-ассетные пулы), (опционально) стейбл-хедж через lending.
**Step-by-Step Execution:**

1. Внести ликвидность в LP-пул perps-DEX.
2. Следить за составом пула (экспозиция к волатильным активам).
3. Хеджировать дельту при необходимости (perps/collars).
   **Risk Profile:** скрытая directional-экспозиция пула, стресс-выводы ликвидности, oracle/liquidation events, smart-contract.
   **Expected APY Range (conservative):** **5–20%**, но распределение “толстохвостое” (редко, но больно).
   Описание источников дохода GMX v2 perps (fees/funding/liquidations/rebalancing) ([defillama.com][12])

---

### 9) “Carry-LP” для волатильного токена (ограниченный риск)

**Strategy Name:** Volatile-Stable LP + Protective Perp
**Logic (Alpha):** fee-yield LP + частичный хедж падения цены через short perp/опцион-заменитель.
**Composability Stack:** CLMM (Tier2) + Perps (Tier3)
**Step-by-Step Execution:**

1. LP в volatile/stable (например OP/USDC).
2. Открыть short perp на часть volatile-дельты (не 100%, чтобы оставить upside).
3. Ребаланс при смене режима (trend vs range).
   **Risk Profile:** basis/funding, неполный хедж (или over-hedge), IL всё равно присутствует.
   **Expected APY Range (conservative):** **8–25%** (если объем/комиссии высокие и хедж дисциплинирован).

---

## 🟠 Tier 4 — Looping & Leverage (Risk-On)

### 10) Recursive Lending (Leveraged Staking / LST Loop)

**Strategy Name:** LST Loop
**Logic (Alpha):** увеличить exposure к staking yield через заем/ре-депозит.
**Composability Stack:** LST + Aave / Spark
**Step-by-Step Execution:**

1. Supply LST.
2. Borrow base asset (ETH/стейбл), свап в LST.
3. Supply снова; держать LTV в “зелёной зоне”.
   **Risk Profile:** ликвидация (главный), рост borrow rate, depeg LST, хвостовые движения.
   **Expected APY Range (conservative):** **6–18%** (до комиссий/страховок; зависит от LTV и ставок).

---

### 11) Delta-Neutral Looping (Stable-driven)

**Strategy Name:** Stable Loop (carry on borrow spread)
**Logic (Alpha):** когда доход по “сберегательному” активу > ставки займа, можно построить цикл (по сути — кредитное плечо на carry).
**Composability Stack:** DSR/sDAI через Spark + заем USDC/USDT
**Step-by-Step Execution:**

1. Держать yield-bearing stable (sDAI/sUSDe).
2. Под него занять дешёвый стейбл.
3. Докупить yield-bearing stable и повторить (строгий LTV-лимит).
   **Risk Profile:** borrow rate jump, depeg yield-stable, smart-contract, liquidity exits.
   **Expected APY Range (conservative):** **5–15%** (главный драйвер — спред “доходность − стоимость долга”; иногда спред исчезает).
   Идея “выше APY чем стоимость займа” для sDAI-loop описывается как класс стратегий на Spark-экосистеме ([Summer.fi blog][13])

---

### 12) Leveraged LP (плечо на свою ликвидность)

**Strategy Name:** Leveraged CLMM / Leveraged LP
**Logic (Alpha):** усилить fee-yield LP плечом (часто через lending-primitive + LP-позиция).
**Composability Stack:**

* Solana: Kamino (лендинг/левередж примитив)
* EVM аналоги существуют, но агент должен whitelisting’ом ограничить протоколы.
  **Step-by-Step Execution:**

1. Создать LP-позицию.
2. Заложить LP-токен/позицию, занять, увеличить позицию.
3. Жёсткие правила stop-LTV + стресс-тесты.
   **Risk Profile:** ликвидация + IL (суммарный риск), резкие тренды, oracle risk.
   **Expected APY Range (conservative):** **10–35%** (но “risk of ruin” резко растёт).

---

## 🔴 Tier 5 — Exotic & Cross-Protocol (Wizard)

### 13) Pendle PT/YT (фиксированная доходность / торговля yield)

**Strategy Name:** PT Fixed Yield Strip
**Logic (Alpha):** купить PT, чтобы зафиксировать yield до экспирации (или арбитражить кривую доходности).
**Composability Stack:** Pendle + базовый yield-asset (LST, sUSDe и т.д.)
**Step-by-Step Execution:**

1. Выбрать рынок (например PT-LST / PT-yield-stable) с достаточной ликвидностью.
2. Купить PT (фикс. доходность) или управлять YT (плавающая доходность).
3. Держать до экспирации или ребалансить при изменении implied yield.
   **Risk Profile:** smart-contract, liquidity around expiry, yield-curve mispricing, базовый актив (LST/depeg).
   **Expected APY Range (conservative):** **4–12% фикс** (в отдельные периоды может быть существенно выше, но агент должен помечать как `RISK_ON`).
   Документация Pendle прямо иллюстрирует кейс “PT-stETH фикс 5%” и yield-арб через money market ([docs.pendle.finance][14])

---

### 14) LRT / Restaking Cascade (points-driven, субсидируемая доходность)

**Strategy Name:** Restaking Points + DeFi Carry
**Logic (Alpha):** базовый staking yield + “внешние субсидии” (points/airdrop-ожидания) + возможный доп. yield в DeFi.
**Composability Stack:** LST → Restaking (EigenLayer) → LRT (пример: ether.fi) → lending/LP
**Step-by-Step Execution:**

1. Войти через LST/LRT.
2. Использовать receipt-asset как залог/LP leg.
3. Ограничить leverage, т.к. “доход” часто не в виде стабильного кэша.
   **Risk Profile:** points ≠ cashflow, изменение правил, depeg LRT/LST, smart-contract слой 2–3 протокола.
   **Expected APY Range (conservative):** **staking-yield + 0–5%** “доп.” (часто это не денежный APY).
   Пример обсуждения “restaking APY” как добавки к ETH staking (и что он может быть небольшим) ([EigenLayer Forum][15])

---

### 15) Flashloan/MEV Arbitrage (только как “модуль логики”, не как базовая доходность)

**Strategy Name:** Opportunistic Arb (Executor)
**Logic (Alpha):** извлечение мгновенных неэффективностей (цены/ликвидации).
**Composability Stack:** DEX + lending + flashloan provider
**Step-by-Step Execution:** (высокоуровнево) детект → симуляция → исполнение → контроль revert-риска.
**Risk Profile:** экстремальный технологический риск, конкуренция с MEV-ботами, высокий операционный риск.
**Expected APY Range:** **не нормируется** (скорее “PnL distribution”, чем APY).

---

# Практическая “Regime-Switch” логика для агента (то, что ты хотел про bull/bear)

1. **Trend Up:**

* базово: Tier1 (LST) + Tier2 CLMM (шире диапазон) + частичный hedge (Tier3-9).

2. **Sideways/Range:**

* Tier2 stable/stable + Tier2 CLMM (узко) + авто-компаунд.

3. **Trend Down / Risk-Off:**

* Tier1/3 yield-bearing stables (sUSDe/sDAI) + Lending, без leverage.

4. **Volatility spike:**

* выключить leverage loops (Tier4), расширить диапазоны или выйти в single-sided.

---



[1]: https://stake.lido.fi/?utm_source=chatgpt.com "Stake with Lido | Lido"
[2]: https://defillama.com/yields/pool/0e7d0722-9054-4907-8593-567b353c0900?utm_source=chatgpt.com "JITOSOL(Jito Liquid Staking - Solana)"
[3]: https://app.aave.com/?marketName=proto_base_v3&utm_source=chatgpt.com "Base Market"
[4]: https://app.ethena.fi/dashboards/market-data?utm_source=chatgpt.com "Market Data"
[5]: https://app.spark.fi/savings/mainnet/sdai?utm_source=chatgpt.com "Savings"
[6]: https://defillama.com/yields/pool/e737d721-f45c-40f0-9793-9f56261862b9?utm_source=chatgpt.com "USDC-USDT (0.01%)(Uniswap V3 - Ethereum)"
[7]: https://defillama.com/yields/pool/755fcec6-f4fd-4150-9184-60f099206694?utm_source=chatgpt.com "USDC-CRVUSD(Convex Finance - Ethereum)"
[8]: https://defillama.com/protocol/aerodrome?utm_source=chatgpt.com "Aerodrome"
[9]: https://defillama.com/protocol/kamino-liquidity?utm_source=chatgpt.com "Kamino Liquidity"
[10]: https://defillama.com/protocol/beefy?utm_source=chatgpt.com "Beefy"
[11]: https://defillama.com/protocol/hyperliquid?utm_source=chatgpt.com "Hyperliquid"
[12]: https://defillama.com/protocol/gmx-v2-perps?utm_source=chatgpt.com "GMX V2 Perps"
[13]: https://blog.summer.fi/boost-your-sdai-yield-with-spark/?utm_source=chatgpt.com "Boost your sDAI yield with Summer.fi and Spark"
[14]: https://docs.pendle.finance/pendle-v2/Developers/Oracles/PTAsCollateral?utm_source=chatgpt.com "PT as Collateral in a Money Market"
[15]: https://forum.eigenlayer.xyz/t/yield-the-new-yield-scaling-curve-for-restaking/14456?utm_source=chatgpt.com "the new yield scaling curve for restaking - AVS Research"
