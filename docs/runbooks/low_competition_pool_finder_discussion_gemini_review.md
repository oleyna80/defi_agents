
## Gemini Critical Review (2026-02-15)

I have reviewed the proposal and implementation plan. While the core "Competition Ratio" thesis is solid for micro-capital, there is a **FATAL TECHNICAL FLAW** in the proposed Data Collection (Phase 1) that will render the entire system useless if not fixed.

### 1. The "Sum of liquidityNet" Fallacy (CRITICAL)

The document proposes:
> "Sum `liquidityNet` for ticks in ±1%, ±2.5%, ±5% bands"

**This is mathematically wrong.**
*   `liquidityNet` is the **DELTA** (change) in active liquidity when crossing a tick. It can be positive or negative.
*   Summing deltas in a range gives you `Net Liquidity Change`, NOT `Total Active Liquidity`.
*   *Example:* If tick 100 has `liqNet=+100` and tick 200 has `liqNet=-100`, the sum is 0. But the Active Liquidity between 100 and 200 is 100.
*   **Consequence:** Your `band_depth` calculation will be random noise, often close to zero or negative, completely breaking the scoring.

**Correction Required:**
You must implement a **Tick Walking Algorithm**:
1.  Fetch `pool.liquidity` (active liquidity at current tick).
2.  Fetch `ticks` array around current tick.
3.  Traverse ticks outwards from current tick.
4.  At each initialized tick, apply `liquidityNet` to current `L` to get `L_next`.
5.  `BandDepth = Sum(L_interval * (tick_next - tick_current))` converted to USD.

*Alternatively for MVP:* Use the `activeLiquidity` field from a reliable API (like Uniswap/Aerodrome official subgraph `tick` entities if iterated correctly), but "Sum liquidityNet" is definitely wrong.

### 2. Market Impact & "Fake Volume" Risk

Targeting pools with `band_depth < $50k` with a `$500` position (1%) is economically improved, but statistically dangerous:
*   **High Turnover with Low Liquidity** often implies **Wash Trading** or **JIT/MEV-only volume**.
*   Standard "Volume" metrics in subgraphs include JIT-trades that you *cannot* capture (because JIT liquidity enters/exits in the same block).
*   **Recommendation:** The `jit_activity_ratio` penalty (from the main Spec) is **mandatory**, not optional. If `JIT > 50%`, the real available volume for you is 0, even if competition is low.

### 3. Alignment with `lp-decision-engine-v1.md`

This proposal is a valid **Configuration Profile** of the main engine, not a separate system.
*   `LiquidityBands` should legally reside in `PoolAnalysis`.
*   `CompetitionRatio` is a derived metric in `Opportunity`.
*   **Spec Deviation:** The proposal ignores `PoolSourceData.data_quality`. For low-liquidity pools, data quality is often `DEGRADED`. Attempting to trade based on stale data in a low-liquidity pool is a guaranteed loss (price moved, you provided liquidity at wrong price -> 100% IL).

### 4. Implementation Plan Corrections

**Phase 1 (Data Collection) MUST be rewritten:**
*   **❌ Wrong:** `_add_liquidity_net_sum()`
*   **✅ Right:** `_calculate_active_liquidity_distribution()` (requires logic to initialize `L` from authorized source and iterate).

**Final Verdict:**
The strategy is viable **ONLY IF** the liquidity calculation is fixed. Proceeding with "Sum liquidityNet" will result in garbage data.
