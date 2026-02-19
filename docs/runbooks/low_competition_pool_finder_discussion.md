# Low Competition Pool Finder - Design Discussion

**Date:** 2026-02-15  
**Participants:** Dmitrii (user), Claude Opus (Senior DeFi Architect)  
**Context:** Designing LP Decision Engine for micro capital ($2000) with focus on finding low-competition pools

---

## User Requirements

**Capital:** $2000 USD  
**Strategy:** 60% stable/stable (passive), 40% volatile/stable (active rebalancing)  
**Target chains:** Base, Arbitrum (gas ~$0.01/tx)  
**Tools:** defi.krystal.app for manual execution  
**Key goal:** Find pools with **low competition** to maximize fee share

**Existing infrastructure:**
- Production Scout bot on VPS (systemd)
- DeFiLlama intake pipeline
- Freshness re-check (Uniswap/Aave/Morpho subgraph)
- Protocol Inspector for security checks
- My Pools Monitor (Phase 2.6)

---

## Critical Analysis: Why Standard "High APY" Search Fails

### Problem: Pool APY ≠ Your APY

**Example:**
```
Pool shows: 50% APY
Pool TVL: $10M
Band depth (±5% range): $5M
Your position: $500

Your actual earnings:
competition_ratio = $500 / $5M = 0.01%
You capture 0.01% of pool fees → effective APY ≈ 0.005% (not 50%)
```

**Root cause:** Pool-level APY calculation assumes:
1. You provide liquidity across full price range (not true for Uniswap v3 concentrated positions)
2. You compete equally with all other LPs (not true - most liquidity is concentrated in narrow bands)

### Solution: Competition-Based Scoring

**Key metric:** `band_depth_usd` — total liquidity in **your price range** (e.g., ±5% around current price)

**Formula:**
```python
competition_ratio = your_position_size / band_depth_usd
fee_share_daily = (volume_24h × fee_tier × competition_ratio) × time_in_range_pct
fee_per_1k_capital = (fee_share_daily / position_size) × 1000
```

**Target:** Find pools where:
- `band_depth_usd < $50k` (volatile pairs) or `< $200k` (stable pairs)
- `volume_24h > $20k` (actual swap activity)
- `competition_ratio > 0.01` (you capture >1% of fees in your range)

---

## Architecture Decisions

### 1. Data Collection: Subgraph Tick-Level Liquidity Query

**What:** Extend Uniswap subgraph re-check to pull `ticks()` distribution

**Query:**
```graphql
query PoolLiquidityBands($poolAddress: String!, $currentTick: Int!) {
  pool(id: $poolAddress) {
    tick
    ticks(
      where: {tickIdx_gte: $lower, tickIdx_lte: $upper}
      orderBy: tickIdx
    ) {
      tickIdx
      liquidityNet
    }
  }
}
```

**Processing:**
- Sum `liquidityNet` for ticks in ±1%, ±2.5%, ±5% bands
- Convert to USD using `sqrtPriceX96` and token prices
- Store in `PoolAnalysis.liquidity_bands`

**Gap identified:** Current freshness re-check only pulls pool-level TVL/APY, not tick distribution

---

### 2. Scoring Model: Fee Share Per 1k Capital

**Primary KPI:**
```python
score = fee_share_per_1k_capital
```

**Thresholds:**
- \>$2/day per $1k (73% APY) → score 80-100
- $1-2/day per $1k (36-73% APY) → score 50-80
- $0.5-1/day per $1k (18-36% APY) → score 20-50
- <$0.5/day per $1k (<18% APY) → score 0-20

**Penalties:**
- JIT activity ratio > 0.5: ×0.5
- Stale data (>90 min): ×0.3
- Fee-on-transfer token: ×0 (hard block)

---

### 3. Portfolio Allocation (60/40 Strategy)

#### Sleeve 1: Core Safe (60% = $1200)
- **Pairs:** 1-2 stable/stable pools (USDC/USDT, USDbC/USDC)
- **Range mode:** WIDE (±1-2%)
- **Rebalance:** Only on depeg events
- **Expected APY:** 10-20% after gas

**Filters:**
```python
{
    "pair_type": "stable_stable",
    "min_tvl_usd": 200_000,
    "max_band_depth_usd": 300_000,  # LOW competition threshold
    "min_volume_24h_usd": 100_000,
    "range_mode": "WIDE"
}
```

#### Sleeve 2: Tactical High-Fee (40% = $800)
- **Pairs:** 3-5 volatile/stable pools (ETH/USDC, ARB/USDC, OP/USDC)
- **Range mode:** MEDIUM (±σ(4d), typically 4-8%)
- **Rebalance:** 1×/week or on out-of-range alert
- **Expected APY:** 40-100% after gas (high variance)

**Filters:**
```python
{
    "pair_type": "volatile_stable",
    "min_tvl_usd": 50_000,
    "max_band_depth_usd": 50_000,  # CRITICAL: very low competition
    "min_volume_24h_usd": 20_000,
    "max_position_pct_of_band": 0.10,  # Don't be >10% of pool
    "range_mode": "MEDIUM"
}
```

---

### 4. Anti-Whale Filters

**Risk:** User position becomes too large relative to pool → slippage on entry/exit

**Mitigation:**
```python
MAX_POSITION_PCT_OF_BAND = {
    "stable_stable": 0.05,   # Max 5% of band depth
    "volatile_stable": 0.10  # Max 10% of band depth
}
```

**Example:**
- Band depth: $30k
- Your position: $500
- Your share: 1.67% (PASS)

- Band depth: $4k
- Your position: $500
- Your share: 12.5% (REJECT - too small pool)

---

## Risk Mitigation

| Risk | Detection | Mitigation |
|------|-----------|------------|
| **Becoming the pool** | `position / band_depth > 10%` | Hard filter rejection |
| **JIT extraction** | `jit_activity_ratio > 0.5` | Score penalty ×0.5 |
| **Liquidity drain** | Band depth ↓30% in 2 windows | Alert + watchlist downgrade |
| **Stale data** | Source age >90 min | Only actionable if VERIFIED |
| **Fee-on-transfer tokens** | TokenRiskProfile flag | Hard block (score = 0) |
| **IL on volatile pairs** | Historical volatility check | Position sizing (40% max) |

---

## Success Metrics (Month 1)

| Metric | Target |
|--------|--------|
| **Core sleeve APY** | 10-20% (stable income) |
| **Tactical sleeve APY** | 40-100% (high variance) |
| **Blended APY** | 22-52% after gas |
| **Gas cost** | <$5/month on Base/Arbitrum |
| **Out-of-range events** | <20% of time (Tactical sleeve) |
| **Positions with net loss** | 0 in first month |

---

## Implementation Phases

### Phase 1: Subgraph Band Depth (Week 1)
- [ ] Add `ticks()` query to `uniswap_subgraph.py`
- [ ] Create `LiquidityBands` model in `pool_analysis.py`
- [ ] Process tick data → calculate band depth (±1%, ±2.5%, ±5%)

### Phase 2: Competition Ratio Calculation (Week 1)
- [ ] New file: `src/defi_agents/scoring/fee_estimator.py`
- [ ] Implement `calculate_competition_ratio()`
- [ ] Implement `estimate_daily_fee_share()`

### Phase 3: Scoring Integration (Week 2)
- [ ] Add `fee_share_per_1k_capital` scoring model
- [ ] Configure per-pair-type filters with `max_band_depth_usd`
- [ ] Add anti-whale guards (`max_position_pct_of_band`)

### Phase 4: Portfolio Optimizer (Week 2)
- [ ] Implement 60/40 allocation logic
- [ ] Add sleeve-specific filters (Core Safe vs Tactical)
- [ ] Diversification constraints (max 2 pools per DEX)

### Phase 5: Telegram Report (Week 2)
- [ ] New report format: show `competition_ratio`, `fee_share_daily`
- [ ] Separate sections for Core/Tactical sleeves
- [ ] Add `your_share_of_band_pct` visibility

### Phase 6: Position Tracker (Week 3)
- [ ] Add `MyPositionsMonitor` pipeline (separate from MyPoolsMonitor)
- [ ] Track NFT position IDs (Uniswap v3 NonFungiblePositionManager)
- [ ] RPC polling: `getNFT(positionId)` for uncollected fees, in-range status
- [ ] Alerts: out-of-range, liquidity drain, fee tier migration

---

## Key Design Insights

1. **Pool APY is misleading for micro capital** — what matters is `your_fee_share / your_position_size`.

2. **Low competition ≠ low TVL** — a $100M pool can have low competition if liquidity is dispersed across wide range. Conversely, $500k pool can have high competition if 90% is concentrated in ±1%.

3. **Gas efficiency critical on micro capital** — Base/Arbitrum ($0.01/tx) makes active management viable. On Ethereum mainnet ($3/tx) it would kill returns.

4. **Manual execution for v1** — with $2000 capital, automation risk (bug → 10-50% loss) outweighs convenience gain.

5. **60/40 allocation is risk management** — stable sleeve provides downside protection while tactical sleeve captures upside from low-competition finds.

---

## Differences from Standard RFC (`lp-decision-engine-v1.md`)

| Aspect | Standard RFC | Low-Competition Variant |
|--------|--------------|------------------------|
| **Primary KPI** | Net Fee Yield (pool-level) | Fee Share Per 1k Capital (user-level) |
| **Key filter** | `min_tvl_usd`, `min_volume_24h` | `max_band_depth_usd` (NEW) |
| **Data source** | Pool-level TVL/APY | Tick-level liquidity distribution |
| **Scoring basis** | Simulator (time-in-range × pool APY) | Competition ratio × volume |
| **Target user** | Whale ($100k+ capital) | Micro ($2-10k capital) |

---

## Next Actions

1. **Review implementation plan** in `/home/dmitrii/.gemini/antigravity/brain/.../implementation_plan.md`
2. **Calibrate thresholds:**
   - Test `max_band_depth_usd` on 20-30 real Base/Arbitrum pools
   - Validate `competition_ratio` formula against actual fee earnings (if user has existing positions)
3. **Phase 1 PR:** Subgraph tick-level query + `LiquidityBands` model
4. **Manual testing:** Find 3-5 low-competition pools → user mints positions on krystal.app → track actual fees earned vs predicted
5. **Iterate:** Adjust penalties (JIT, stale data) based on real-world accuracy

---

## Questions for Future Iterations

1. **Historical liquidity data:** Current design uses static (current) liquidity. Would 7-day average `band_depth` improve predictions?

2. **Multiple range strategies:** Should Tactical sleeve test TIGHT (±2%) vs MEDIUM (±5%) vs WIDE (±10%) to find optimal tradeoff?

3. **Liquidity event detection:** Can we detect when "smart money" is exiting (band depth ↓30%+) and use as exit signal?

4. **Cross-DEX arbitrage:** If Base Uniswap has high competition but Base Aerodrome has low competition for same pair, should we recommend Aerodrome?

5. **Execution automation threshold:** At what capital level ($5k? $10k?) does automation become worth the risk?

---

## Gemini Senior Architect Review (2026-02-15)

I have reviewed the discussion and initial proposal.

- **Gemini: DISAGREE** (Phase 1 Logic - `sum(liquidityNet)`)
  - **Why:** The proposal to "Sum `liquidityNet`" (Line 87) is mathematically invalid. `liquidityNet` is a delta (change at ticks). Summing deltas does not yield active liquidity depth. It yields garbage.
  - **Proposal:** Explicitly require **Tick Walking / Active Liquidity Reconstruction**. Start with `pool.liquidity` (current active) and apply `liquidityNet` as you iterate ticks outwards. Reference Uniswap v3 SDK `TickListDataProvider`.

- **Gemini: PARTIAL** (Success Metrics)
  - **Why:** "Positions with net loss = 0" (Line 199) is an unrealistic vanity metric that encourages paralysis (not entering valid risks).
  - **Proposal:** Replace with **"Portfolio Max Drawdown < 5%"** and **"Win Rate > 60%"**. Losing positions are inevitable; managing the aggregate downside is the goal.

- **Gemini: AGREE** (User Requirements - Rewards)
  - **Why:** The "User Requirements" section implies a focus on fees, but specific "Target chains" (Base/Arb) often have high reward emissions (Aerodrome, etc.).
  - **Proposal:** Explicitly add **"Maximise Net Yield (Fee + Rewards)"** to the goal. Low competition pools are often incentivized. Ignoring rewards is leaving money on the table.

---

## Claude Senior Architect Review (2026-02-15)

### Response to Gemini Review

- Claude: **AGREE** (Gemini: Phase 1 Logic — `sum(liquidityNet)`) — Gemini absolutely right, this is the **most critical bug** in the original proposal. Simple sum of `liquidityNet` produces meaningless numbers. The correct algorithm is **tick walking**: start from `pool.liquidity` (active liquidity at current tick), then apply `liquidityNet` deltas cumulatively as you traverse ticks outward. I already proposed this fix in `implementation_plan.md.resolved` (lines 382-403) referencing Uniswap v3 SDK `TickListDataProvider`. — **Recommended change:** Replace line 87 (`Sum liquidityNet`) with explicit tick walking pseudocode. Mark as P0 blocker for Phase 1.

- Claude: **PARTIAL** (Gemini: Success Metrics — replace "Position losses = 0") — Agree that "Position losses = 0" is a vanity metric. **Disagree** with Gemini's proposed "Win Rate > 60%": win rate alone is misleading because it ignores magnitude (90% win rate but 1 large loss wipes everything). — **Recommended change:** Use a **three-metric DoD**: (1) Portfolio Max Drawdown < 5% (Core) / < 15% (Tactical) — from Gemini, accepted; (2) Signal hit-rate ≥ 60% — % of actionable candidates profitable after 7 days; (3) Median realized fee/day per $1k ≥ $0.80 — tracks actual earnings, not binary win/loss. Win rate is secondary to these.

- Claude: **AGREE** (Gemini: Rewards — Maximise Net Yield including incentives) — This is the **biggest architectural gap** in the current plan. The entire scoring pipeline is fee-centric, but on Base/Arbitrum the dominant yield sources are often **protocol rewards** (Aerodrome emissions, Uniswap incentive programs, OP/ARB airdrop farming). Ignoring rewards leaves 30-60% of potential yield on the table. — **Recommended change:**
  1. Extend `PoolAnalysis` with `RewardProfile`:
     ```python
     class RewardProfile(BaseModel):
         reward_apr_gross: float          # Raw APR from DeFiLlama/protocol
         reward_token: str                # e.g., "AERO", "OP"
         reward_token_tier: Literal["T1", "T2", "T3"]  # Liquidity tier
         reward_liquidity_depth_usd: float  # Can you sell without slippage?
         reward_vesting_days: int         # Lock period (0 = immediate)
         reward_claim_gas_usd: float      # Cost to harvest
     ```
  2. Adjust scoring: `net_yield = fee_apr_net + reward_apr_realized - gas_drag`
  3. Add as **Phase 2.5** (after fee estimation, before portfolio optimizer). DeFiLlama already exposes `apyReward` — low implementation cost.

### Review of Original Proposal

- Claude: **PARTIAL** (Line 38 — APY calculation example) — The example `competition_ratio = 0.01%` → `effective APY ≈ 0.005%` is **arithmetically wrong**. If pool APY is 50% on $10M TVL, daily fees = $10M × 0.50 / 365 = $13,699/day. User's $500 share: $13,699 × ($500/$10M) = $0.68/day = 50% APY (same as pool APY, because at v2/full-range the ratio is linear). The point becomes valid **only for concentrated v3 positions** where band_depth ≠ TVL. Fix the example to show v3-specific concentration mismatch. — **Recommended change:** Replace with v3-correct example where TVL=$10M but band_depth in ±2% is $5M, and user's `fee_share = position / band_depth` differs from `position / TVL`.

- Claude: **PARTIAL** (Lines 204-210 — Score caps at 100 when `fee_per_1k >= $2`) — Any pool yielding >$2/day scores identically at 100. This removes differentiation at the top end, exactly where tactical sleeve decisions matter most. — **Recommended change:** Use `min(100, 50 + fee_per_1k * 25)` — still bounded but differentiates up to $2/day. Or logarithmic: `score = 50 + 50 × (1 - e^(-fee_per_1k))`.

- Claude: **DISAGREE** (Line 128 — `max_band_depth_usd: 300_000` for Core Safe) — $300k band depth with $600 position = 0.2% of fees. This is **not** low competition for micro capital. — **Recommended change:** Lower to $100-150k for Core Safe. Keep $200k as relaxed fallback if candidate count < 2.

- Claude: **AGREE** (Lines 154-173 — Anti-Whale Filters) — Well-designed. Addition: track `entry_band_depth_usd` per position, alert if current `position_pct_of_band` exceeds 2× entry ratio (liquidity drain detection).

- Claude: **PARTIAL** (Line 284 — Cross-DEX: Uniswap vs Aerodrome) — Answer should be **yes, include Aerodrome in v1**. Aerodrome is the dominant DEX on Base with heavy AERO emissions. Phase 1 needs a DEX-agnostic `TickDataProvider` interface: `UniswapV3TickProvider` (Week 1) + `AerodromeTickProvider` (Week 2).

---

## ChatGPT Review of Claude + Gemini Comments (2026-02-15, append-only)

- ChatGPT: [AGREE] Тезис Gemini/Claude про ошибку `sum(liquidityNet)` корректен — это главный математический блокер точности `band_depth_usd` — ✅ CONSENSUS.  
  **Замена исходного блока Processing (в Phase 1):**
  ```text
  Processing (replacement):
  1) Fetch: `pool.tick`, `pool.liquidity`, `tickSpacing`, initialized `ticks` in target window.
  2) Convert target price bands (±1/2.5/5%) -> ticks, aligned to `tickSpacing`.
  3) Reconstruct active liquidity via tick-walk:
     - start L at current tick,
     - apply `liquidityNet` at each crossed initialized tick,
     - compute interval liquidity across neighboring ticks.
  4) Integrate interval liquidity -> `band_depth_usd` using token price conversion.
  5) Persist `data_quality` and `band_depth_confidence`.
  ```

- ChatGPT: [AGREE] Тезис Gemini/Claude про включение rewards в цель оптимизации верный — fee-only не закрывает исходную цель пользователя (max доходность + рост позиции через награды) — ✅ CONSENSUS.  
  **Замена блока "Primary KPI / scoring objective":**
  ```python
  net_alpha = fee_apr_realized + reward_apr_realized - il_cost_est - gas_drag - risk_haircuts
  ```
  Обязательные поля: `reward_apr_gross`, `reward_realization_haircut`, `reward_liquidity_depth_usd`, `reward_claim_gas_usd`, `reward_reinvest_cycle_days`.

- ChatGPT: [PARTIAL] Тезис Gemini по метрикам ("max drawdown + win-rate") частично верный — drawdown обязателен, но win-rate без magnitudes может маскировать хвостовые потери — компромисс: `max_drawdown + median realized fee/day per $1k + directional hit-rate`, win-rate как secondary.

- ChatGPT: [AGREE] Тезис Claude о неверном APY-примере поддерживаю — текущий пример смешивает v2/full-range и v3/concentrated semantics — рекомендуемая правка: оставить только v3-кейс с явным `band_depth != TVL` и формулой `fee_share ~ position / band_depth`.

- ChatGPT: [PARTIAL] Тезис Claude по score-cap flattening (все >$2/day => 100) поддерживаю, но логарифм лучше линейного растяжения в верхнем хвосте — компромисс:
  ```python
  score = min(100.0, 50.0 + 50.0 * (1.0 - exp(-fee_per_1k)))
  ```
  плюс отдельный tie-break по `data_quality`, `wash_risk`, `reward_realization_haircut`.

- ChatGPT: [PARTIAL] Тезис Claude о `max_band_depth_usd=300k` для Core Safe частично поддерживаю — фикс снижать сразу рискованно без исторической выборки — компромисс: dual-threshold режим в v1: `soft=300k`, `preferred=150k`, при достаточном числе кандидатов брать только `preferred`.

- ChatGPT: [AGREE] Тезис Claude по anti-whale + post-entry liquidity drain поддерживаю — это операционный must-have для active management — рекомендуемая правка: зафиксировать alert rule `current_position_pct_of_band >= 2x entry_position_pct_of_band`.

- ChatGPT: [PARTIAL] Тезис Claude про включение Aerodrome в v1 поддерживаю по бизнес-ценности Base, но не как hard dependency Phase 1 — компромисс: в v1 включить `TickDataProvider` интерфейс и Uniswap provider как P0; Aerodrome provider P1 с отдельным quality-gate и shadow validation.

- ChatGPT: [AGREE] Тезис Gemini про обязательность JIT/fake-volume risk gate поддерживаю — high-turnover low-depth пулы без JIT/wash фильтра дают ложный alpha — рекомендуемая правка: mandatory downgrade при `jit_activity_ratio > threshold` или `wash_risk_score >= threshold`, независимо от fee score.

---

## Gemini Senior DeFi Architect Consensus Review (2026-02-15)

### 1. Mathematical Core (Liquidity & Competition)

- Gemini: **[AGREE]** **Tick Walking is the ONLY valid method.**
  - **Why:** `sum(liquidityNet)` is mathematically meaningless (sum of deltas ≠ depth). Using it guarantees garbage data.
  - **✅ CONSENSUS Proposal:**
    Refactor Phase 1 to use **Active Liquidity Reconstruction**:
    ```python
    def calculate_band_depth(pool, ticks, lower_price, upper_price):
        # 1. Sort ticks by index
        sorted_ticks = sorted(ticks, key=lambda t: t.tickIdx)
        
        # 2. Find starting liquidity L at lower_price
        current_L = pool.liquidity  # Currently active L
        # Backtrack/Walk to find L at lower_price if needed, or start walking from current
        
        # 3. Walk from lower to upper, accumulating value
        total_value_usd = 0
        for i in range(len(sorted_ticks)-1):
            tick_curr = sorted_ticks[i]
            tick_next = sorted_ticks[i+1]
            
            # Add liquidity in this interval ( L * (price_next - price_curr) )
            interval_usd = liquidity_to_usd(current_L, tick_curr.price, tick_next.price)
            total_value_usd += interval_usd
            
            # Update L for next interval
            current_L += tick_curr.liquidityNet
            
        return total_value_usd
    ```
    *Strictly reference Uniswap v3 `TickMath` for precision.*

### 2. Reward Economics (Net Alpha)

- Gemini: **[AGREE]** **Rewards are mandatory for Base/Arbitrum.**
  - **Why:** On these chains, 30-60% of yield comes from incentives (AERO, OP, ARB). Ignoring them creates a blind spot for the most profitable "low competition" pools (often incentivized to *attract* liquidity).
  - **✅ CONSENSUS Proposal:**
    Replace `fee_share_per_1k` with `NetAlpha` utilization:
    ```python
    net_alpha_apr = (
        fee_apr_projected * (1 - risk_haircut) 
        + reward_apr_realized 
        - gas_drag_apr
    )
    ```
    where `reward_apr_realized = raw_reward_apr * liquidity_discount_factor`.
    *If reward token slippage > 2% for $50 sell, `liquidity_discount_factor` = 0.5.*

### 3. Success Metrics & Gates

- Gemini: **[AGREE]** **Multi-metric Shadow Gate.**
  - **Why:** RMSE is fragile for power-law distributions. We need to know "did the ranker pick winners?".
  - **✅ CONSENSUS Proposal:**
    Shadow Mode Exit Criteria:
    1.  **Directional Accuracy:** >60% of top-5 recommendations outperformed the median pool.
    2.  **Liquidity Safety:** <10% of recommendations suffered >30% liquidity drain within 24h.
    3.  **Positive Expectancy:** Median theoretical PnL (fee + reward - gas) > $0.
    4.  **Telegram:** Use `⚠️ SHADOW — DO NOT ACT` channel.

### 4. Strategic Adjustments

- Gemini: **[PARTIAL]** **Tactical Allocation on Reward Quality.**
  - **Why:** I agree with Claude that hard-cutting the Tactical % is too rigid.
  - **Compromise:** Use **Risk-Weighted Position Sizing** within the Tactical Sleeve.
    - If `reward_quality == LOW` (illiquid/vested): Max position $200 (instead of $500).
    - If `reward_quality == HIGH` (liquid/bluechip): Max position $800.
    *This naturally reduces exposure to bad rewards without changing the top-level sleeve allocation.*

### 5. Aerodrome Support

- Gemini: **[AGREE]** **Include Aerodrome in v1 (Priority P0).**
  - **Why:** Base *is* Aerodrome. Running a "Base LP Strategy" without Aerodrome is negligent.
  - **✅ CONSENSUS:** Implement `TickDataProvider` interface immediately. Support `UniswapV3` and `Aerodrome` (v3/CL) adapters from Day 1.

---
**Final Recommendation:** Proceed to Implementation Plan update. Phase 1 must be rewritten to strict Tick Walking specs.

---

## Claude Red Team Review — Logic Bomb Analysis (2026-02-15)

### 🔴 CRITICAL WARNINGS

**RT-1: Reward Dilution Race (The Honeypot Trap)**

The plan adds `reward_apr_realized` to scoring. This creates a **self-defeating feedback loop** that nobody addressed:

1. System finds pool with LOW band_depth ($30k) + HIGH AERO rewards (200% APR)
2. **But reward APR is high precisely BECAUSE band_depth is low** — fewer LPs split the reward gauge
3. System reports it as top candidate → user enters → band_depth grows to $31k
4. The same signal is visible to **every other yield aggregator** (Beefy, Yearn, DefiLlama front page)
5. Within 24-48 hours, professional vaults deploy $500k+ → band_depth jumps to $530k
6. User's competition_ratio drops from 1.5% → 0.09%, reward_apr drops from 200% → 12%
7. **The opportunity was real at observation time but dead at execution time**

This is not a bug — it's **structural**. Low-competition high-reward pools are inherently unstable equilibria. The system will consistently recommend pools that are about to get crowded.

**Mitigation (mandatory for v1):**
```python
class OpportunityDecay(BaseModel):
    """Track how fast similar pools historically get crowded."""
    band_depth_velocity_24h: float  # $/hour growth rate of band_depth
    reward_half_life_estimate: float  # Hours until reward_apr halves based on inflow rate
    time_to_crowd: float  # Estimated hours until competition_ratio < 0.5%
    
# Hard gate: if time_to_crowd < 6 hours, mark as FLEETING_ALPHA
# User with manual execution CANNOT act on opportunities with < 6h window
```

**RT-2: `band_depth` Snapshot Illusion**

The entire scoring model treats `band_depth_usd` as a **stable property** of a pool. In reality, on low-liquidity pools (which is exactly what we're targeting), band_depth can swing **30-50% within a single block**:

- One LP removes $15k from a $30k band → band_depth halves → your competition_ratio doubles
- One LP adds $50k → band_depth triples → your effective APY drops 3×

The system takes a **point-in-time snapshot** and presents it as an investment thesis. For pools with $30-50k band_depth (our target), this snapshot is **meaningless within 2 hours** because a single whale move can restructure the entire tick distribution.

**Mitigation (mandatory for v1):**
```python
# Require MINIMUM 3 observations over 6 hours before marking as actionable
class BandDepthHistory(BaseModel):
    observations: List[Tuple[datetime, float]]  # [(timestamp, band_depth_usd), ...]
    coefficient_of_variation: float  # std(observations) / mean(observations)
    
# Gate: if len(observations) < 3 or cv > 0.30, mark as UNSTABLE_DEPTH
# Do NOT recommend pools where band_depth volatility > 30%
```

**RT-3: Subgraph Lag — The Blind Spot Window**

The plan uses The Graph Protocol subgraphs for tick data. **Critical issue:** Base subgraphs typically lag **5-30 blocks** (10-60 seconds on Base's 2-second blocks). During high volatility:

- Subgraph shows `band_depth = $40k` (from 30 seconds ago)
- Current on-chain reality: price moved 3%, half the LPs are out of range, `band_depth = $15k`
- System reports "low competition" but the ACTUAL competition (among remaining in-range LPs) is even lower — however the VOLUME may also be spiking, meaning JIT bots are active

The danger isn't that subgraph data is wrong — it's that **stale data creates false confidence**. The system will show `data_quality: OK` because the subgraph responded, but the data is from a different market regime.

**Mitigation (mandatory for v1):**
```python
# Cross-check subgraph tick vs RPC pool.slot0()
async def validate_tick_freshness(subgraph_tick: int, pool_address: str) -> bool:
    """Compare subgraph current tick to RPC current tick."""
    rpc_slot0 = await rpc.call("slot0", pool_address)
    rpc_tick = rpc_slot0.tick
    tick_drift = abs(subgraph_tick - rpc_tick)
    
    # If tick drifted > 1 tickSpacing, data is stale
    if tick_drift > pool.tickSpacing:
        return False  # Mark data_quality: DEGRADED
    return True

# Cost: 1 RPC call per pool (~$0.0001 on Base). Worth it.
```

**RT-4: IL-Blind Scoring**

The `net_alpha` formula from consensus:
```python
net_alpha = fee_apr_realized + reward_apr_realized - gas_drag - risk_haircuts
```

**Where is impermanent loss?** ChatGPT added `il_cost_est` in one version but the consensus formula from Gemini (line 428-432) drops it. For volatile/stable pairs in the Tactical sleeve, IL is **the dominant cost**:

- ETH/USDC with ±5% range: if ETH moves 8% in a week, IL ≈ 3-5% of position
- Fee income might be 1-2% in that week
- **Net result: -1% to -3%** despite "high alpha" fee signals

The system will consistently recommend volatile pairs during low-volatility periods (when band_depth is stable and competition looks low), then the user enters and volatility spikes.

**Mitigation (mandatory for v1):**
```python
net_alpha = (
    fee_apr_realized 
    + reward_apr_realized 
    - il_estimate_apr       # MUST be in the formula
    - gas_drag 
    - risk_haircuts
)

# IL estimate for concentrated liquidity:
def estimate_il_apr(volatility_7d: float, range_width_pct: float) -> float:
    """
    Approximation: IL ≈ σ² / (8 × range_width²) per unit time
    For ETH with σ_daily = 3%, range = ±5%:
    IL_daily ≈ 0.03² / (8 × 0.05²) = 0.045 = 4.5%/day (!!!)
    
    This shows why TIGHT ranges on volatile pairs are suicide.
    """
    sigma_daily = volatility_7d / sqrt(7)
    il_daily = (sigma_daily ** 2) / (8 * (range_width_pct ** 2))
    return il_daily * 365  # Annualized
```

---

### 🟡 OPERATIONAL RISKS

**OR-1: Manual Execution Decay Window**

System runs every ~30 minutes. User checks Telegram... eventually. Realistic timeline:
```
T+0min:   Scout detects opportunity (band_depth=$35k, competition=LOW)
T+30min:  Telegram report sent
T+60min:  User sees notification (maybe)
T+90min:  User opens krystal.app, connects wallet, reviews pool
T+120min: User executes mint position  ← 2 HOURS LATER
```

In 2 hours on a low-competition pool:
- band_depth can change 30-50% (see RT-2)
- A professional vault (Beefy/Gamma) can deploy and take 80% of the band
- Price can move 2-3% → your planned range is already suboptimal

**For the Tactical sleeve (volatile pairs), a 2-hour delay makes the signal nearly worthless.**

**Mitigation:**
- Core Safe sleeve (stable/stable): 2-hour delay is acceptable (stable band_depth, minimal price movement). **Focus v1 manual execution here.**
- Tactical sleeve: require real-time `band_depth` re-check via RPC **at execution time** (user clicks "re-check" in Telegram before acting). If band_depth changed >20% from signal, abort.

**OR-2: Reward Harvest Timing Trap**

For Aerodrome CL positions, rewards accrue per-epoch (weekly on Aerodrome, resets every Thursday). If user enters Tuesday:
- Only 2 days of reward accrual in first epoch
- If reward APR was calculated on full-epoch basis, first week earnings will be ~30% of projected
- User may panic-exit before seeing normal returns

**Mitigation:** Add `epoch_remaining_pct` to Telegram report. Warn user: "Enter early in epoch for full reward capture."

**OR-3: Position Exit — The Forgotten Leg**

The entire plan focuses on ENTRY (finding pools, minting positions). **Zero discussion of EXIT strategy.** Questions:
- When to close a position? (Out-of-range for how long?)
- How to handle IL-dominated positions? (Cut loss or wait for mean reversion?)
- What's the cost of closing? (Burn NFT + collect fees + swap back to single asset)
- What happens to unclaimed rewards during exit?

**Mitigation (v1 minimum):**
```python
EXIT_RULES = {
    "core_safe": {
        "out_of_range_hours_max": 48,   # 2 days OOR → close
        "il_pct_max": 2.0,              # >2% IL on stables → immediate close (depeg risk)
    },
    "tactical": {
        "out_of_range_hours_max": 6,    # 6 hours OOR → close or rebalance
        "il_pct_max": 5.0,              # >5% IL → close, don't wait
        "fee_earned_vs_il": 0.5,        # If fees < 50% of IL → pool is losing, close
    }
}
```

**OR-4: Rebalance Cascade — The Hidden Gas Sink**

Plan says "rebalance 1×/week" for Tactical sleeve. Actual rebalance flow:
1. Close existing position (burn NFT): 1 tx
2. Collect unclaimed fees: 1 tx (can be combined)
3. Swap tokens to new ratio: 1 tx
4. Mint new position with new range: 1 tx
5. Claim any pending rewards: 1 tx

= **3-5 transactions per rebalance.** At $0.01/tx = $0.03-0.05 per rebalance. Sounds cheap, but:
- If you get 3 out-of-range events per week × 4 positions = 12 rebalances
- 12 × $0.05 = $0.60/week = $2.40/month
- On $800 tactical sleeve, that's **3.6% annual gas drag** — significant for micro capital

And this assumes $0.01/tx. Base gas spikes during high activity to $0.05-0.10/tx, which could 5-10× the cost.

**Mitigation:** Track `rebalance_count_monthly` and `gas_spent_vs_fees_earned`. If gas > 10% of fees, widen the range (accept lower capital efficiency for lower rebalance frequency).

---

### 🟠 PROTOCOL-SPECIFIC GOTCHAS (Base / Aerodrome)

**PG-1: Aerodrome Epoch Voting — Reward Instability**

Aerodrome rewards are determined by **weekly veAERO voting**. Voters direct AERO emissions to specific gauges (pools). This means:
- Pool X gets 300% APR this week because whales voted for it
- Next Thursday, votes shift → Pool X gets 40% APR
- **Reward APR can 8× swing week-to-week** based on voting dynamics

Your system will recommend pools with high current rewards, but those rewards are **non-persistent**. The system has no visibility into vote distribution or voter intent.

**Mitigation:**
```python
# Track reward_apr stability over 3+ epochs
reward_epoch_history: List[float]  # [epoch_n_apr, epoch_n-1_apr, epoch_n-2_apr]
reward_stability = min(reward_epoch_history) / max(reward_epoch_history)

# If reward_stability < 0.3 (e.g., APR swung from 40% to 300%), flag as UNSTABLE_REWARDS
# Only include pools with 3+ epoch history for Reward-weighted scoring
```

**PG-2: Aerodrome CL ≠ Uniswap v3**

Aerodrome's concentrated liquidity (Slipstream) is a **fork of Uniswap v3** but with key differences:
- **Fee switch:** Aerodrome takes a protocol fee (currently ~20% of swap fees). Your fee estimation must account for this: `user_fees = swap_fees × 0.80`, not `swap_fees × 1.0`
- **NFT staking:** To earn AERO rewards, you must **stake your LP NFT** via `NonFungiblePositionManager.safeTransferFrom()` to the gauge contract. Unstaked positions earn swap fees but ZERO rewards
- **Different subgraph schema:** Aerodrome subgraph uses different field names (`CLPool` vs `Pool`, `tickCurrent` vs `tick`). The `TickDataProvider` interface must handle this

**Mitigation:** Create `AerodromeAdapter` with:
```python
AERODROME_PROTOCOL_FEE_PCT = 0.20  # 20% of swap fees go to protocol
# Adjusted fee calculation:
aerodrome_fee_to_lp = swap_fee * (1 - AERODROME_PROTOCOL_FEE_PCT)
```

**PG-3: Aerodrome Gauge Manipulation**

Low-TVL Aerodrome gauges can be **vote-manipulated** by small veAERO holders. Scenario:
1. Attacker creates obscure pair (SHITCOIN/USDC)
2. Votes for its gauge → high AERO emissions
3. Provides initial liquidity to make TVL look decent
4. Your system detects: low band_depth + high reward APR = top candidate
5. User enters → attacker removes liquidity → user is alone with IL exposure
6. Reward tokens (AERO) may be worth it, but the exit is rugged

This is a **variant of wash trading** but using the **voting mechanism** instead of volume.

**Mitigation:** For Aerodrome pools, add:
```python
# Hard filter: pool must have existed for ≥ 3 epochs (3 weeks)
# Hard filter: voting concentration — if top 3 voters control > 70% of gauge votes, flag VOTE_MANIPULATION_RISK
# Only available via veNFT voting data (Aerodrome API, not subgraph)
```

**PG-4: Base Sequencer Downtime**

Base uses a centralized sequencer (Coinbase operated). Historical downtimes: 1-2 incidents per quarter, lasting 30-120 minutes. During downtime:
- RPC calls fail → your position tracker goes blind
- Pending transactions queue up → rebalance may execute at stale price
- When sequencer restarts, pending tx burst can cause price spikes and cascading liquidations on adjacent protocols

**For LP positions:** If price moves 5% during downtime and your range was ±5%, you're out of range when sequencer restarts. No alert was sent (RPC was down). By the time you notice, you've lost hours of fee income.

**Mitigation:**
```python
# Monitor Base sequencer health (Coinbase status page API)
# If sequencer was down in last 30 min:
#   - Mark ALL Base candidates as data_quality: DEGRADED
#   - Suppress actionable recommendations
#   - Send alert: "Base sequencer recovered — data stabilizing, wait 15 min"
```

**PG-5: Bridged Stablecoin Risk (USDbC, axlUSDC)**

Base has multiple USDC variants:
- **USDC** (native Circle): fully backed, safe
- **USDbC** (bridged from Ethereum): legacy, being deprecated by Circle
- **axlUSDC** (Axelar bridge): bridge security risk

Your "Core Safe" stable/stable sleeve may target USDbC/USDC or axlUSDC/USDC pools. These pools earn fees from **arbitrage between USDC variants** — which is healthy. But:
- USDbC can depeg if bridge has issues (even briefly)
- At $1200 Core Safe allocation, a 2% depeg = $24 loss — wipes a month of fee income

**Mitigation:**
```python
STABLECOIN_TIERS = {
    "USDC": "T1",     # Native Circle — safe
    "USDT": "T1",     # Tether — safe for Base
    "USDbC": "T2",    # Bridged — acceptable with lower position size
    "axlUSDC": "T3",  # Bridge risk — exclude from Core Safe
    "DAI": "T2",      # Algorithmic component — T2
}

# Core Safe: only T1/T1 or T1/T2 pairs
# Tactical: T1/T2 acceptable, T3 excluded
```

---

### ⚖️ VERDICT: **PROCEED WITH GUARDRAILS**

The core thesis (band_depth-based competition scoring) is **architecturally sound** and differentiated from standard yield aggregators. The math fixes (tick walking, cumulative liquidity) are non-negotiable P0 items. Reward economics addition is correct.

**However, the plan has 4 logic bombs that will cause user loss if not addressed:**

| # | Logic Bomb | Severity | Fix Cost |
|---|-----------|----------|----------|
| RT-1 | Reward dilution race (honeypot) | 🔴 HIGH | Add `time_to_crowd` estimate, require historical band_depth stability |
| RT-2 | band_depth snapshot illusion | 🔴 HIGH | Require 3+ observations over 6h before actionable |
| RT-3 | Subgraph lag false confidence | 🟡 MEDIUM | Add RPC tick cross-check (1 call per pool) |
| RT-4 | IL-blind scoring | 🔴 HIGH | Add `il_estimate_apr` to net_alpha formula |

**Recommended execution order:**
1. **Week 0:** Shadow mode + fix RT-1/RT-2/RT-4 (add decay tracking, multi-observation, IL estimate)
2. **Week 1:** Phase 1 (tick walking) + RT-3 (RPC cross-check)
3. **Week 2:** Core Safe sleeve only (manual execution acceptable for stables)
4. **Week 3:** Tactical sleeve IF Shadow metrics pass AND user demonstrates < 30 min execution latency

**Do NOT deploy Tactical sleeve with manual execution until OR-1 (execution decay) is resolved — either with a "re-check before act" button or with < 15 min response time.**

---

## ChatGPT Senior Architect Review — Round 3 (2026-02-15, append-only)

- ChatGPT: [AGREE] Tick-walking вместо `sum(liquidityNet)` — это математический P0 для корректного `band_depth_usd`; без этого конкуренция считается неверно — ✅ CONSENSUS.  
  **Replacement (Phase 1 core logic):**
  ```python
  # replace "sum(liquidityNet)" block
  # 1) get current active liquidity + initialized ticks
  L = pool.liquidity
  # 2) walk tick-by-tick across aligned [lower_tick, upper_tick]
  # 3) apply liquidityNet deltas at crossed initialized ticks
  # 4) integrate interval liquidity -> USD depth
  band_depth_usd = integrate_liquidity_intervals_to_usd(L, ticks, lower_tick, upper_tick)
  ```

- ChatGPT: [AGREE] Цель оптимизации должна быть `fee + rewards` (а не fee-only) — это прямое требование задачи и единая позиция ревьюеров — ✅ CONSENSUS.  
  **Replacement (scoring objective):**
  ```python
  net_alpha = fee_apr_realized + reward_apr_realized - il_estimate_apr - gas_drag_apr - risk_haircuts_apr
  ```

- ChatGPT: [AGREE] KPI `Position losses = 0` нужно удалить — это неоперабельная метрика и поощряет ложный no-trade режим — ✅ CONSENSUS.  
  **Replacement (DoD metrics block):**
  ```text
  1) Max drawdown: Core <= 5%, Tactical <= 15%
  2) Median realized fee/day per $1k >= target floor
  3) Directional hit-rate recommendations >= 60%
  4) False-positive rate on actionable <= 30%
  ```

- ChatGPT: [AGREE] Shadow-gate должен быть multi-metric и видимым в отдельном канале — RMSE-only недостаточен для heavy-tail LP доходностей — ✅ CONSENSUS.  
  **Replacement (Shadow exit gate):**
  ```text
  Pass if >=3/4:
  - median_ape < 40%
  - p75_ape < 60%
  - directional_accuracy >= 70%
  - normalized_rmse < 100%
  Telegram channel: "SHADOW" with prefix "⚠️ SHADOW — DO NOT ACT"
  ```

- ChatGPT: [AGREE] Комментарий Claude по формуле `tickSpacing`/`price<->tick` корректен — фиксированные `±200 ticks` недопустимы как универсальное правило — рекомендуемое изменение: хранить band в процентах и всегда конвертировать в aligned ticks по fee-tier.

- ChatGPT: [AGREE] Комментарий Claude про неверный APY-пример корректен — нельзя смешивать full-range и concentrated math — рекомендуемое изменение: оставить только v3-case с `band_depth != TVL` и явной формулой `fee_share ~ position / band_depth`.

- ChatGPT: [PARTIAL] Комментарий Claude про score-cap flattening верный по сути, но линейный скейл хуже логарифмического в хвосте — компромисс: `score_fee = 50 + 50*(1-exp(-fee_per_1k))` + tie-break по `data_quality/wash_risk/reward_haircut`.

- ChatGPT: [PARTIAL] Комментарий Claude по `max_band_depth_usd` (сразу 100-150k) рискован без локальной статистики — компромисс: hybrid v1 (`hard_cap=300k`, `preferred=150k`, логировать `p25/p35` как read-only, пересмотр после 2 недель shadow/production).

- ChatGPT: [AGREE] Anti-whale тезис Claude корректен — нужен post-entry drain контроль — рекомендуемое изменение: alert `current_position_pct_of_band >= 2 * entry_position_pct_of_band`.

- ChatGPT: [PARTIAL] Тезис Gemini/Claude «Aerodrome как P0 day-1 adapter» бизнес-правильный, но повышает delivery risk — компромисс: P0 интерфейс `TickDataProvider` + обязательный Uniswap adapter; Aerodrome adapter как P0.5 (в той же итерации) с отдельным quality-gate и 3-дневным shadow.

- ChatGPT: [AGREE] Комментарий Claude про `data_quality`/`band_depth_confidence` обязателен — деградация источника не должна проходить в actionable — рекомендуемое изменение: `DEGRADED => WATCHLIST`, `DOWN => exclude`, `LOW confidence => score penalty`.

- ChatGPT: [AGREE] Комментарий Claude про `realized_fill_factor` обязателен — иначе APY системно завышается — рекомендуемое изменение: показывать в отчете conservative/optimistic сценарии и маркировать как estimate.

- ChatGPT: [AGREE] Комментарий Claude по wash/fake-volume детекторам корректен — Vol/TVL без quality-gate создает ложный alpha — рекомендуемое изменение: mandatory downgrade при `vol_tvl`/`volume_cv` аномалиях + source-confidence penalty.

- ChatGPT: [AGREE] Комментарий Claude про `REWARD_FARMING_TRAP` корректен — illiquid reward APR не должен конвертироваться в полноценный alpha — рекомендуемое изменение: hard-flag + near-kill penalty и лимит на Tactical sizing.

- ChatGPT: [AGREE] Red-team тезис Claude RT-1 (reward dilution race) корректен — high-reward low-depth окна быстро схлопываются — рекомендуемое изменение: добавить `time_to_crowd` и флаг `FLEETING_ALPHA` при окне < 6h.

- ChatGPT: [AGREE] Red-team тезис Claude RT-2 (snapshot illusion) корректен — одиночный snapshot недостаточен для micro-depth пулов — рекомендуемое изменение: минимум 3 наблюдения за 6 часов + gate по `band_depth_cv`.

- ChatGPT: [AGREE] Red-team тезис Claude RT-3 (subgraph lag) корректен — нужна проверка drift относительно RPC `slot0()` — рекомендуемое изменение: tick-drift check, при drift > tickSpacing ставить `data_quality=DEGRADED`.

- ChatGPT: [AGREE] Red-team тезис Claude RT-4 (IL-blind scoring) критически верен — без IL модель системно переоценивает volatile/stable — рекомендуемое изменение: `il_estimate_apr` сделать обязательным вычитанием в `net_alpha_apr`.

- ChatGPT: [AGREE] Operational тезис Claude OR-1 (manual execution decay) корректен — сигнал стареет быстрее, чем пользователь исполняет сделку — рекомендуемое изменение: pre-execution re-check кнопка/команда и abort при изменении `band_depth` > 20%.

- ChatGPT: [AGREE] Operational тезис Claude OR-3 (отсутствие exit rules) корректен — вход без системного выхода повышает хвостовые убытки — рекомендуемое изменение: v1 должен включать минимум `max_out_of_range_hours`, `il_stop`, `fee_vs_il close rule`.

- ChatGPT: [PARTIAL] Protocol тезис Claude про Aerodrome gauge/vote dynamics корректен по риску, но данные top-voter concentration не всегда доступны стабильно — компромисс: v1 использовать epoch APR stability proxy + age/TVL floor; vote concentration подключить в v1.1.

- ChatGPT: [PARTIAL] Protocol тезис Claude про stable tiers (USDC/USDbC/axlUSDC) корректен по принципу, но mapping должен быть chain-aware и versioned — компромисс: держать denylist/allowlist в конфиге с weekly refresh и explicit source-of-truth.

---

## Quick Index — Consensus vs Open Items (for next review round)

### ✅ Consensus (ready to lock into spec)

- Tick-walking / active liquidity reconstruction (replace `sum(liquidityNet)`).
- Net alpha scoring must include rewards (`fee + rewards`) and IL/gas/risk haircuts.
- Remove KPI `Position losses = 0`; use drawdown + realized fee + hit-rate metrics.
- Shadow rollout via separate Telegram channel (`⚠️ SHADOW — DO NOT ACT`).
- Multi-metric shadow gate (not RMSE-only).
- Add `data_quality` / `band_depth_confidence` degradation policy.
- Add `realized_fill_factor` + conservative/optimistic reporting.
- Add wash/fake-volume gates and reward farming trap flag.
- Add post-entry liquidity drain alert (`position_pct_of_band` vs entry baseline).

### ⚠️ Open / Needs final decision

- Tactical sizing policy when reward quality is low:
  - option A: auto-cut Tactical sleeve share,
  - option B: keep sleeve size, exclude low-quality reward pools and refill with fee-driven candidates.
- Aerodrome rollout level in v1:
  - option A: hard P0 day-1 adapter,
  - option B: P0.5 in same iteration with dedicated shadow/quality gate.
- Band-depth threshold policy for v1:
  - option A: fixed absolute thresholds only,
  - option B: hybrid (`hard cap + preferred`) with percentile logging (`p25/p35`) as read-only.
- Aerodrome vote concentration risk:
  - option A: enforce top-voter concentration gate now,
  - option B: epoch-stability proxy in v1, concentration gate in v1.1.
- Stablecoin tiering governance:
  - finalize chain-aware, versioned allow/deny source-of-truth and refresh cadence.

---

## Decision Closure — Round 4 (2026-02-15, operator lock for implementation)

- ChatGPT: [AGREE] Open item `Tactical sizing with low reward quality` closed as **Option B** — preserve Tactical sleeve budget, exclude low-quality reward pools, refill with next fee-driven candidates to avoid unintended cash drag.
- ChatGPT: [AGREE] Open item `Aerodrome rollout in v1` closed as **Option B (P0.5)** — keep `TickDataProvider` + Uniswap adapter as P0, ship Aerodrome in same wave with dedicated 3-day SHADOW quality gate.
- ChatGPT: [AGREE] Open item `band-depth thresholds` closed as **hybrid** — `hard_cap + preferred` in v1, plus percentile telemetry (`p25/p35`) read-only for v1.1 recalibration.
- ChatGPT: [AGREE] Open item `vote concentration risk timing` closed as **Option B** — use epoch stability proxy in v1, move explicit top-voter concentration gate to v1.1 when dependable data source is integrated.
- ChatGPT: [AGREE] Open item `stablecoin tier governance` closed — maintain chain-aware, versioned YAML allow/deny source-of-truth with scheduled refresh (monthly) and incident-driven hot updates.

---

## Claude Vote on Open Items (2026-02-15)

**Open Item 1: Tactical sizing policy when reward quality is low**
- Claude: **VOTE B** (keep sleeve size, exclude + refill) — Tactical sleeve exists for high-fee-share opportunities. Cutting it from 40% to 20% because *rewards* are bad penalizes *fee-only* plays, which are the original thesis. The correct response to bad rewards is to exclude reward-dependent pools and fill the budget with fee-driven candidates. If there aren't enough fee-driven candidates, the sleeve naturally shrinks via candidate scarcity, not a forced cap. Option A conflates two independent signals (fee quality vs reward quality).

**Open Item 2: Aerodrome rollout level in v1**
- Claude: **VOTE B** (P0.5 with quality gate) — Business value of Aerodrome is undeniable (Base ≈ Aerodrome). But shipping two adapters day-1 doubles QA surface. P0 interface + Uniswap adapter gives us the abstraction layer immediately. Aerodrome adapter ships 3-5 days later with its own 3-day shadow validation. This is not "deferring Aerodrome" — it's sequencing delivery risk. If Aerodrome adapter has a bug in fee calculation (20% protocol fee) or tick schema mapping, it doesn't block the entire v1 launch.

**Open Item 3: Band-depth threshold policy for v1**
- Claude: **VOTE B** (hybrid with percentile logging) — Fixed-only thresholds (Option A) are safe but blind — we won't know if $50k/$200k are too tight or too loose until production. Option B costs nothing extra: keep the same fixed filters, but log `p25`/`p35` band_depth per chain+pair-type every cycle. After 2 weeks of data, we can validate whether the fixed thresholds are in the right ballpark. Zero runtime risk, high calibration value.

**Open Item 4: Aerodrome vote concentration risk**
- Claude: **VOTE B** (epoch-stability proxy in v1, concentration gate in v1.1) — Top-voter concentration data requires Aerodrome-specific API calls to veNFT contracts. This adds a new external dependency with uncertain reliability. The epoch-stability proxy (`min(last_3_epoch_apr) / max(last_3_epoch_apr)`) catches the same end-effect (unstable rewards) without needing voter-level data. If a pool's reward APR swings 8× between epochs, it fails the stability check regardless of *why* it swung. Concentration gate is more precise but can wait for v1.1 when we have the Aerodrome adapter battle-tested.

**Open Item 5: Stablecoin tiering governance**
- Claude: **VOTE** — Chain-aware config file (`stablecoin_tiers.yaml`), versioned in git, refreshed weekly (manual review, not automated). Structure:
  ```yaml
  # stablecoin_tiers.yaml
  version: "2026-02-15"
  chains:
    base:
      T1: [USDC, USDT]
      T2: [USDbC, DAI]
      T3: [axlUSDC]  # Excluded from Core Safe
      deny: [BUSD]   # Hard block
    arbitrum:
      T1: [USDC, USDT, USDC.e]
      T2: [DAI, FRAX]
      T3: []
      deny: []
  refresh_cadence: "weekly"
  source_of_truth: "manual review + Circle/bridge announcements"
  ```
  Automated refresh is premature — stablecoin risk changes on bridge incidents and issuer announcements, not on a schedule. Manual weekly review is appropriate for $2000 capital.

---

## Gemini Vote on Open Items (2026-02-15)

**Open Item 1: Tactical sizing policy when reward quality is low**
- Gemini: **VOTE B** (keep sleeve size, exclude + refill) — **AGREE with Claude.** Cutting the 40% sleeve arbitrarily reduces upside potential. If there are no high-quality reward pools, the budget should flow to the best pure-fee pools (e.g., volatile pairs with high organic volume). *Caveat:* If no pools meet the "Fee-Only" hurdles either, the system must hold the allocation in USDC (Cash is a position), not force deployment into mediocre pools.

**Open Item 2: Aerodrome rollout level in v1**
- Gemini: **VOTE B** (P0.5 with quality gate) — **AGREE with Claude.** Launching a partially-tested Aerodrome adapter risks capital. The `TickDataProvider` interface is the correct abstraction. If Uniswap works, we have a Minimum Viable Product. Aerodrome can follow days later. Prioritize correctness over feature-completeness for v1 launch.

**Open Item 3: Band-depth threshold policy for v1**
- Gemini: **VOTE B** (hybrid w/ logging) — **AGREE with Claude.** We have zero data on Base/Arbitrum micro-pool depth distribution. Hard coding $50k is a guess. Logging percentiles (`p25`, `p50`) lets us calibrate without risking empty reports in week 1.

**Open Item 4: Aerodrome vote concentration risk**
- Gemini: **VOTE B** (epoch-stability proxy) — **AGREE with Claude.** Direct veNFT auditing is complex and fragile (API changes, rate limits). Epoch stability (`min/max APR < 0.3`) is a robust enough proxy for "is this reward sustainable?". We can add "Whale Watch" alerts later.

**Open Item 5: Stablecoin tiering governance**
- Gemini: **VOTE** (Manual YAML) — **AGREE with Claude.** For $2000 capital, automated risk feeds are overkill and a maintenance liability. A simple `stablecoin_tiers.yaml` updated monthly/on-incident is sufficient.

---

## Claude Closing Comment — All Open Items Resolved (2026-02-15)

**Result: 5/5 unanimous VOTE B** across Claude + Gemini. No remaining disputes.

One addition from Gemini worth locking into the spec:

- Claude: **AGREE** (Gemini caveat on Item 1: "Cash is a position") — If Tactical sleeve has no qualifying candidates (neither fee-driven nor reward-driven pass thresholds), the undeployed capital should **stay in USDC**, not force-deploy into mediocre pools. This is critical for $2000 capital — forced deployment into sub-threshold pools to "fill the sleeve" is how small accounts bleed out via gas + IL.
  ```python
  # In portfolio allocator:
  if len(tactical_candidates) == 0:
      tactical_allocation = "HOLD_USDC"
      log.info("Tactical sleeve: no qualifying candidates. Holding as USDC.")
  ```

Also noting Gemini's minor divergence on Item 5 refresh cadence ("monthly/on-incident" vs my "weekly"). For $2000 capital, **monthly + on-incident** is sufficient — weekly is overkill given how rarely stablecoin risk profiles change.

**All 5 Open Items are now ready for user arbitration and spec lock.**

