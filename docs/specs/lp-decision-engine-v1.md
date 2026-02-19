# LP Decision Engine v1.0 — Low Competition Pool Finder

**Status:** APPROVED  
**Version:** 1.0.0  
**Date:** 2026-02-15  
**Reviewers:** Claude (Senior Architect), ChatGPT (Senior Architect), Gemini (Senior DeFi Architect)  
**Consensus:** 3/3 unanimous on all items  
**Source:** [Discussion & Review Log](../runbooks/low_competition_pool_finder_discussion.md)

---

## 0. Goals & Constraints

### 0.1 User Profile
| Parameter | Value |
|-----------|-------|
| Capital | $2,000 USD |
| Strategy | 60/40 (Core Safe / Tactical) |
| Target chains | Base, Arbitrum |
| DEXes | Uniswap v3, Aerodrome (Slipstream CL) |
| Execution | Manual via krystal.app |
| Optimization goal | **Maximize Net Alpha** (fees + rewards − IL − gas − risk) |

### 0.2 Non-Goals (v1 Hard Blockers)

1. **`MANUAL_EXECUTION_ONLY`**: No automated on-chain transactions. All actions require explicit human approval.
2. **`SINGLE_CHAIN_LAUNCH`**: Base first, Arbitrum second. No multi-chain in v1 launch week.
3. **`GRACEFUL_DEGRADATION`**: `DEGRADED` → `WATCHLIST`; `DOWN` → exclude from scoring, alert operator.
4. **`CASH_IS_A_POSITION`**: If no qualifying candidates exist for a sleeve, hold allocation in USDC. Never force-deploy into sub-threshold pools.

---

## 1. Architecture

Two decoupled pipelines, implemented as a single process with isolated `asyncio.create_task` loops and separate error boundaries.

### 1.1 Discovery Pipeline (Batch)
- **Frequency:** Every 4–6 hours
- **Source:** DeFiLlama (broad) → Subgraph + RPC (deep validation)
- **Output:** Scored `Opportunity` list with risk tags
- **Core logic:** Band depth scoring, reward economics, competition ratio

### 1.2 My Pools Monitor (Real-Time)
- **Frequency:** Every block (WebSocket) or 1-minute polling (RPC)
- **Source:** Direct RPC only. **No subgraph dependency** for critical alerts.
- **Output:** Alerts (`OUT_OF_RANGE`, `PRICE_EDGE`, `LIQUIDITY_DRAIN`, `IL_STOP`)

---

## 2. Core Concept: Competition-Based Scoring

### 2.1 Why Pool APY Fails for Micro Capital

Pool APY assumes uniform liquidity distribution. In Uniswap v3 / Aerodrome CL, liquidity is concentrated. What matters is **band depth** — total liquidity competing in your price range.

```
Pool TVL:           $10M
Band depth (±5%):   $5M     ← actual competition
Your position:      $500
competition_ratio:  $500 / $5M = 0.01%
```

**Key insight:** `Low competition ≠ low TVL`. A $100M pool can have low competition if liquidity is dispersed. A $500k pool can have high competition if 90% is in ±1%.

### 2.2 Primary KPI: Net Alpha

```python
net_alpha = (
    fee_apr_realized
    + reward_apr_realized
    - il_estimate_apr       # Mandatory for volatile pairs
    - gas_drag_apr
    - risk_haircuts_apr
)
```

### 2.3 Fee Share Estimation

```python
fee_share_daily = volume_24h × fee_tier × competition_ratio × realized_fill_factor
competition_ratio = position_size / band_depth_usd
fee_per_1k = (fee_share_daily / position_size) × 1000
```

**`realized_fill_factor`:** Conservative 0.6, Optimistic 0.9. Both shown in reports.

### 2.4 Score Function

```python
from math import exp
score_fee = min(100.0, 50.0 + 50.0 * (1.0 - exp(-fee_per_1k)))
```

Tie-break by: `data_quality` > `wash_risk` (lower better) > `reward_realization_haircut` (lower better).

---

## 3. Band Depth Calculation (Tick Walking) [P0]

> ✅ CONSENSUS: `sum(liquidityNet)` is mathematically invalid. Tick walking is the ONLY valid method.

### 3.1 Algorithm

```python
def calculate_band_depth(pool, ticks, lower_tick, upper_tick) -> float:
    """
    Reconstruct active liquidity via tick walking.
    Start from pool.liquidity at current tick, apply liquidityNet deltas.
    """
    sorted_ticks = sorted(ticks, key=lambda t: t.tickIdx)
    current_L = pool.liquidity  # Active liquidity at current tick
    
    # Walk from current tick to lower bound (backward)
    # Walk from current tick to upper bound (forward)
    # At each initialized tick, apply: L += liquidityNet (forward) or L -= liquidityNet (backward)
    
    total_value_usd = 0.0
    for i in range(len(sorted_ticks) - 1):
        tick_curr = sorted_ticks[i]
        tick_next = sorted_ticks[i + 1]
        
        interval_usd = liquidity_to_usd(current_L, tick_curr.price, tick_next.price)
        total_value_usd += interval_usd
        
        current_L += tick_curr.liquidityNet
    
    return total_value_usd
```

### 3.2 Band Windows

Convert percentage bands to tick-aligned boundaries per fee tier:
- ±1%, ±2.5%, ±5% bands
- Align to `tickSpacing` (1, 10, 60, 200 depending on fee tier)

### 3.3 Freshness Validation [RT-3]

```python
async def validate_tick_freshness(subgraph_tick: int, pool_address: str) -> bool:
    """Cross-check subgraph tick vs RPC pool.slot0()."""
    rpc_slot0 = await rpc.call("slot0", pool_address)
    tick_drift = abs(subgraph_tick - rpc_slot0.tick)
    if tick_drift > pool.tickSpacing:
        return False  # Mark data_quality: DEGRADED
    return True
```

Cost: ~$0.0001/pool on Base. Mandatory for every scoring cycle.

### 3.4 Band Depth Stability [RT-2]

```python
class BandDepthHistory(BaseModel):
    observations: List[Tuple[datetime, float]]
    coefficient_of_variation: float  # std / mean

# Gate: require ≥3 observations over 6 hours
# If cv > 0.30, mark as UNSTABLE_DEPTH → do NOT recommend
```

---

## 4. Reward Economics [P0]

> ✅ CONSENSUS: Fee-only scoring is incomplete. 30–60% of yield on Base/Arbitrum comes from protocol rewards.

### 4.1 Reward Profile Model

```python
class RewardProfile(BaseModel):
    reward_apr_gross: float
    reward_token: str                              # e.g., "AERO", "OP"
    reward_token_tier: Literal["T1", "T2", "T3"]   # Liquidity tier
    reward_liquidity_depth_usd: float              # DEX depth for selling
    reward_vesting_days: int                       # Lock period (0 = immediate)
    reward_claim_gas_usd: float
    reward_epoch_history: List[float]              # Last 3+ epoch APRs
```

### 4.2 Reward Haircut

```python
def calculate_reward_haircut(profile: RewardProfile) -> float:
    base = {"T1": 0.05, "T2": 0.15, "T3": 0.50}[profile.reward_token_tier]
    
    if profile.reward_vesting_days > 0:
        base += min(0.30, profile.reward_vesting_days * 0.01)
    
    if profile.reward_liquidity_depth_usd < 10_000:
        base += 0.20  # Illiquid reward
    
    return min(base, 0.95)
```

### 4.3 Reward Stability [PG-1]

```python
reward_stability = min(epoch_history) / max(epoch_history)
# If reward_stability < 0.3 → flag UNSTABLE_REWARDS
# Only trust pools with ≥3 epoch history for reward-weighted scoring
```

### 4.4 Reward Farming Trap Detection

```python
if (reward_token_tier == "T3" 
    and reward_liquidity_depth_usd < 10_000 
    and reward_apr_gross > fee_apr_net * 5):
    flags.append("REWARD_FARMING_TRAP")
    score *= 0.2  # Near-kill penalty
```

---

## 5. Impermanent Loss Estimation [RT-4]

> ✅ CONSENSUS: IL must be in the net_alpha formula. IL-blind scoring will systematically recommend pools where IL > fees.

```python
from math import sqrt

def estimate_il_apr(volatility_7d: float, range_width_pct: float) -> float:
    """
    IL ≈ σ² / (8 × range_width²) per unit time (concentrated liquidity approximation).
    
    Example: ETH σ_daily=3%, range=±5%:
    IL_daily ≈ 0.03² / (8 × 0.05²) = 0.045 = 4.5%/day
    → Tight ranges on volatile pairs are extremely risky.
    This is an upper-bound heuristic for gating, not exact PnL forecasting.
    """
    sigma_daily = volatility_7d / sqrt(7)
    il_daily = (sigma_daily ** 2) / (8 * (range_width_pct ** 2))
    return il_daily * 365
```

Calibration rule: tune IL coefficient during Phase 0.5 shadow by comparing estimated vs realized IL, and store per pair-type multipliers.

---

## 6. Data Models

All models in `src/defi_agents/scout/lp_models.py`.

### 6.1 Data Quality

```python
class DataQuality(BaseModel):
    provider_status: Literal["OK", "DEGRADED", "DOWN"]
    source_age_sec: int
    chain_head_lag_blocks: int
    fallback_used: bool
    degraded_reason: Optional[str] = None
    collected_at_utc: datetime
    tick_drift_from_rpc: Optional[int] = None  # RT-3: subgraph vs RPC delta
```

### 6.2 Pool Analysis (Extended)

```python
class PoolAnalysis(BaseModel):
    # Band depth (tick-walked)
    band_depth_1pct_usd: float
    band_depth_2_5pct_usd: float
    band_depth_5pct_usd: float
    band_depth_confidence: Literal["HIGH", "MEDIUM", "LOW"]
    band_depth_history: BandDepthHistory  # RT-2
    
    # Competition
    competition_ratio: float
    fee_share_daily_conservative: float  # fill_factor=0.6
    fee_share_daily_optimistic: float    # fill_factor=0.9
    fee_per_1k_capital: float
    
    # JIT / MEV
    jit_activity_ratio: float
    jit_level: Literal["CLEAN", "MODERATE", "HIGH_JIT"]
    
    # Wash trading
    wash_risk_score: float
    vol_tvl_ratio: float
    volume_cv_7d: float  # Coefficient of variation
    
    # Volatility
    volatility_atr_1d: float
    volatility_atr_7d: float
    il_estimate_apr: float  # Section 5
    
    # Rewards
    reward_profile: Optional[RewardProfile]
    
    # Opportunity decay (RT-1)
    band_depth_velocity_24h: Optional[float]  # $/hour growth rate
    time_to_crowd_hours: Optional[float]
    
    # Token risk
    token_risk_profile: TokenRiskProfile
    
    # Data quality
    data_quality: DataQuality
```

### 6.3 Opportunity

```python
class Opportunity(BaseModel):
    opportunity_id: str
    pool_ref: PoolRef
    sleeve: Literal["CORE_SAFE", "TACTICAL_FEE", "TACTICAL_REWARD"]
    
    # Scoring
    net_alpha_apr: float
    score: float
    score_breakdown: Dict[str, float]  # fee, reward, il, gas, risk
    
    # Estimates
    fee_apr_conservative: float
    fee_apr_optimistic: float
    reward_apr_realized: float
    il_estimate_apr: float
    gas_drag_apr: float
    
    # Risk flags
    flags: List[str]  # FLEETING_ALPHA, UNSTABLE_DEPTH, REWARD_FARMING_TRAP, etc.
    
    # Diagnostics
    decision_log: List[DecisionStep]
```

---

## 7. Portfolio Allocation (60/40)

### 7.1 Core Safe Sleeve (60% = $1,200)

| Parameter | Value |
|-----------|-------|
| Pairs | 1–2 stable/stable (USDC/USDT, USDbC/USDC) |
| Range mode | WIDE (±1–2%) |
| Rebalance | Only on depeg events |
| Target APY | 10–20% after gas |

**Filters:**
```python
CORE_SAFE_FILTERS = {
    "min_tvl_usd": 200_000,
    "max_band_depth_usd": 150_000,      # Preferred threshold
    "max_band_depth_usd_soft": 300_000,  # Fallback if < 2 candidates at preferred
    "min_volume_24h_usd": 100_000,
    "max_position_pct_of_band": 0.05,    # Max 5% of band
    "stablecoin_tier_min": "T2",         # T1/T1 or T1/T2 only
}
```

### 7.2 Tactical Sleeve (40% = $800)

Sub-classified by yield source:
- **Tactical-Fee** (`reward_apr < fee_apr × 0.5`): Standard allocation
- **Tactical-Reward** (`reward_apr > fee_apr × 2`): Requires reward quality gate

| Parameter | Value |
|-----------|-------|
| Pairs | 3–5 volatile/stable (ETH/USDC, ARB/USDC, OP/USDC) |
| Range mode | MEDIUM (±σ(4d), typically 4–8%) |
| Rebalance | 1×/week or on out-of-range alert |
| Target APY | 40–100% after gas (high variance) |

**Filters:**
```python
TACTICAL_FILTERS = {
    "min_tvl_usd": 50_000,
    "max_band_depth_usd": 50_000,
    "min_volume_24h_usd": 20_000,
    "max_position_pct_of_band": 0.10,    # Max 10% of band
    "min_time_to_crowd_hours": 6,        # RT-1: reject FLEETING_ALPHA
    "min_band_depth_observations": 3,    # RT-2: require stability data
}
```

**Risk-weighted sizing within Tactical (Gemini proposal):**
- `reward_quality == LOW` (illiquid/vested): Max position $200
- `reward_quality == HIGH` (liquid/bluechip): Max position $800

**If no qualifying candidates:** Hold as USDC. Do not force-deploy.

---

## 8. Hard Filters & Risk Gates

### 8.1 Token Risk Gates
- `fee_on_transfer` OR `rebasing` → **HARD REJECT (score 0)**
- `bridge_wrapped` → risk penalty ×0.8

### 8.2 Anti-Whale Guard
```python
MAX_POSITION_PCT_OF_BAND = {
    "stable_stable": 0.05,   # Max 5%
    "volatile_stable": 0.10  # Max 10%
}
```

### 8.3 Post-Entry Liquidity Drain Alert
```python
# Track entry_band_depth_usd per position
# Alert if current_position_pct_of_band >= 2 × entry_position_pct_of_band
```

### 8.4 Wash Trading Detection
Mandatory downgrade when any of:
- `vol_tvl_ratio` abnormally high vs chain+pair-type median
- `volume_cv_7d > threshold` (unstable volume)
- `jit_activity_ratio > 0.5` → score penalty ×0.5

### 8.5 Opportunity Decay [RT-1]
```python
# If time_to_crowd < 6 hours → flag FLEETING_ALPHA
# Manual execution cannot act on < 6h windows
```

---

## 9. Stablecoin Tiers

Config file: `config/stablecoin_tiers.yaml`, versioned in git, refreshed monthly + on-incident.

```yaml
version: "2026-02-15"
chains:
  base:
    T1: [USDC, USDT]
    T2: [USDbC, DAI]
    T3: [axlUSDC]      # Excluded from Core Safe
    deny: [BUSD]        # Hard block
  arbitrum:
    T1: [USDC, USDT, USDC.e]
    T2: [DAI, FRAX]
    T3: []
    deny: []
```

Rules:
- Core Safe: only T1/T1 or T1/T2 pairs
- Tactical: T1/T2 acceptable, T3 excluded from both sleeves

---

## 10. DEX Adapters

### 10.1 Interface

```python
class TickDataProvider(Protocol):
    async def get_pool_ticks(self, pool_address: str, lower: int, upper: int) -> List[TickData]: ...
    async def get_pool_state(self, pool_address: str) -> PoolState: ...
    def protocol_fee_pct(self) -> float: ...
```

### 10.2 Uniswap v3 Adapter [P0]
- Subgraph: standard Uniswap v3 subgraph schema (`Pool`, `tick`, `liquidityNet`)
- Protocol fee: 0% (to LPs)
- Ships Day 1

### 10.3 Aerodrome Adapter [P0.5]
- Subgraph: Aerodrome schema (`CLPool`, `tickCurrent`, different field names)
- **Protocol fee: 20%** of swap fees → `user_fees = swap_fees × 0.80`
- **NFT staking required** for AERO rewards (unstaked = zero rewards)
- Ships +3–5 days after Uniswap, with dedicated 3-day shadow validation
- Quality gate: pool must exist ≥3 epochs (3 weeks)

---

## 11. Exit Rules

```python
EXIT_RULES = {
    "core_safe": {
        "out_of_range_hours_max": 48,   # 2 days OOR → close
        "il_pct_max": 2.0,              # >2% IL on stables → immediate close (depeg risk)
    },
    "tactical": {
        "out_of_range_hours_max": 6,    # 6 hours OOR → close or rebalance
        "il_pct_max": 5.0,              # >5% IL → close
        "fee_earned_vs_il": 0.5,        # If fees < 50% of IL → pool is net-losing, close
    }
}
```

Gas budget monitoring:
- Track `rebalance_count_monthly` and `gas_spent_vs_fees_earned`
- If gas > 10% of fees → widen range to reduce rebalance frequency

---

## 12. Alerting (Hysteresis)

| Alert | Trigger | Release | Confirmations | Cooldown |
|-------|---------|---------|---------------|----------|
| Out of Range | Price crosses tick boundary | Returns to range | 2 checks | 15 min |
| Price Edge | Price within 10% of boundary | Moves to center 50% | 1 check | 30 min |
| Liquidity Drain | band_depth ↓30% in 2 windows | Recovery to 80% of prev | 2 checks | 1 hour |
| IL Stop | IL > threshold per sleeve | — (exit signal) | 1 check | — |
| Sequencer Down | Base RPC unreachable | RPC responds + 15 min stabilization | 3 checks | — |

---

## 13. Shadow Testing (Phase 0.5) [Mandatory Pre-Production]

### 13.1 Setup
- Duration: 7–14 days, read-only pipeline
- Telegram: Separate `SHADOW` channel with `⚠️ SHADOW — DO NOT ACT` prefix
- Track 20–30 top candidates (no capital deployed)

### 13.2 Exit Gate (Multi-Metric)

Pass if ≥3 of 4 metrics pass:

| Metric | Threshold |
|--------|-----------|
| Median Absolute % Error | < 40% |
| P75 Absolute % Error | < 60% |
| Directional Accuracy | ≥ 70% (signals beat risk-free rate) |
| Normalized RMSE | < 100% (RMSE / mean predicted) |

### 13.3 Post-Mortem Analysis
- How many had `band_depth` degrade >30%? (liquidity drain risk)
- How many had `volume_7d` diverge >50%? (wash trading indicator)
- If we had entered, what would realized fees be? (backtest vs subgraph swaps)

### 13.4 Calibration Outputs
- Adjust `realized_fill_factor` default
- Adjust `time_in_range_pct` default
- Log `band_depth_p25` / `band_depth_p35` per chain+pair-type (read-only, for v1.1 threshold calibration)
- Update JIT penalty if correlation observed

---

## 14. Telegram Report Format

### 14.1 Discovery Report (every 4–6h)

```
🔍 LP Scout — Low Competition Finder
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 CORE SAFE (60% sleeve)
┌─────────────────────────────────
│ #1 USDC/USDT · Aerodrome Base
│ Band depth (±1%): $85k | Competition: 0.7%
│ Fee/day per $1k: $0.95 (cons) / $1.42 (opt)
│ Reward APR: 12% AERO (T2, stable 3ep)
│ Net Alpha: 28% APR
│ ⚡ Data: OK | Wash: CLEAN
└─────────────────────────────────

📈 TACTICAL (40% sleeve)
┌─────────────────────────────────
│ #1 ETH/USDC · Uniswap v3 Base
│ Band depth (±5%): $32k | Competition: 1.6%
│ Fee/day per $1k: $1.85 (cons) / $2.78 (opt)
│ IL estimate: 18% APR (σ7d=21%)
│ Net Alpha: 45% APR
│ ⚠️ time_to_crowd: ~14h
│ ⚡ Data: OK | Wash: CLEAN
└─────────────────────────────────

🔴 No candidates: 0 tactical pools (holding USDC)
```

### 14.2 Pre-Execution Re-Check

User sends `/recheck <pool_id>` → system runs RPC band_depth check → confirms or aborts:
```
✅ CONFIRMED — band_depth changed +8% (within 20% gate). Proceed.
❌ ABORT — band_depth changed -35% since signal. Do NOT enter.
```

---

## 15. Success Metrics (Month 1)

> ✅ CONSENSUS: Remove "Position losses = 0" — use testable output metrics.

| Metric | Target | Measurement |
|--------|--------|-------------|
| Signal hit-rate | ≥60% of actionable candidates profitable after 7 days | Predicted vs realized fees |
| Median realized fee/day per $1k | ≥$0.80 (≈29% APY floor) | User logs from 3+ positions |
| Max drawdown (Core) | ≤5% | IL + gas − fees over 30 days |
| Max drawdown (Tactical) | ≤15% | IL + gas − fees over 30 days |
| Alert accuracy | ≥70% of OOR alerts trigger within 6h of actual event | Alert timestamp vs RPC |
| False positive rate | ≤30% of candidates degrade >50% band_depth within 48h | Liquidity stability tracking |

---

## 16. Implementation Roadmap

### Phase 0.5: Shadow Testing (Week 0)
- [ ] Deploy read-only pipeline
- [ ] Set up SHADOW Telegram channel
- [ ] Track 20–30 candidates for 7–14 days
- [ ] Run post-mortem, calibrate model coefficients
- [ ] **Gate:** Multi-metric shadow gate must pass before production

### Phase 1: Tick Walking + Band Depth (Week 1)
- [ ] Implement `TickDataProvider` interface
- [ ] Implement `UniswapV3TickProvider` (subgraph + RPC freshness check)
- [ ] Implement tick walking algorithm (`calculate_band_depth`)
- [ ] Create `LiquidityBands` model with ±1%, ±2.5%, ±5% windows
- [ ] Add `BandDepthHistory` (3+ observations over 6h gate)

### Phase 1.5: Aerodrome Adapter (Week 1–2)
- [ ] Implement `AerodromeTickProvider`
- [ ] Handle 20% protocol fee in fee estimation
- [ ] Handle subgraph schema differences (`CLPool`, `tickCurrent`)
- [ ] 3-day shadow validation before merging into scoring

### Phase 2: Competition Scoring (Week 2)
- [ ] Implement `calculate_competition_ratio()`
- [ ] Implement `estimate_daily_fee_share()` with `realized_fill_factor`
- [ ] Implement `estimate_il_apr()` for volatile pairs
- [ ] Score function with logarithmic curve

### Phase 2.5: Reward Economics (Week 2)
- [ ] Add `RewardProfile` model
- [ ] Implement `calculate_reward_haircut()`
- [ ] Integrate DeFiLlama `apyReward` + `rewardTokens[]`
- [ ] Implement `REWARD_FARMING_TRAP` detection
- [ ] Implement `reward_stability` (3-epoch history)
- [ ] Calculate `net_alpha` with full formula

### Phase 3: Portfolio Optimizer (Week 3)
- [ ] 60/40 allocation logic with Tactical sub-classification
- [ ] Sleeve-specific filters (Core Safe / Tactical-Fee / Tactical-Reward)
- [ ] Risk-weighted position sizing within Tactical
- [ ] "Cash is a position" logic for empty sleeves

### Phase 4: Filters & Risk Gates (Week 3)
- [ ] Anti-whale guard with `max_position_pct_of_band`
- [ ] Post-entry liquidity drain alert
- [ ] Wash trading detection (`vol_tvl`, `volume_cv`)
- [ ] Opportunity decay tracking (`time_to_crowd`)
- [ ] Stablecoin tier enforcement from YAML config
- [ ] Exit rules implementation

### Phase 5: Telegram Reports (Week 4)
- [ ] Discovery report with competition metrics
- [ ] Pre-execution `/recheck` command
- [ ] Epoch timing info for Aerodrome rewards
- [ ] Conservative/optimistic dual estimates

### Phase 6: Position Tracker (Week 4)
- [ ] Track NFT position IDs
- [ ] RPC polling for uncollected fees, in-range status
- [ ] Exit rule monitoring (OOR hours, IL stops)
- [ ] Gas budget tracking (`rebalance_count`, `gas_vs_fees`)

---

## 17. Protocol-Specific Notes

### Base
- Sequencer: centralized (Coinbase), 1–2 downtimes/quarter (30–120 min)
- During downtime: mark all Base data as `DEGRADED`, suppress recommendations
- After recovery: wait 15 min for data stabilization

### Aerodrome
- Rewards: weekly epoch (resets Thursday), determined by veAERO voting
- Reward APR can swing 8× week-to-week — require 3-epoch stability history
- NFT must be staked in gauge contract to earn AERO rewards
- Gauge manipulation risk: require pool age ≥3 epochs + TVL floor

---

## Appendix: Decision Log

All architectural decisions were debated across 4 review rounds with 3 independent reviewers. Full transcript: [Discussion Doc](../runbooks/low_competition_pool_finder_discussion.md).

Key resolved disputes:
- **Tick walking vs sum(liquidityNet):** Unanimous — tick walking only (P0)
- **Fee-only vs fee+rewards scoring:** Unanimous — full net_alpha (P0)
- **Tactical auto-cut vs sub-classification:** Unanimous VOTE B — sub-classify, don't cut %
- **Aerodrome Day 1 vs P0.5:** Unanimous VOTE B — P0.5 with quality gate
- **Fixed vs hybrid thresholds:** Unanimous VOTE B — hybrid with percentile logging
- **Vote concentration gate timing:** Unanimous VOTE B — epoch proxy v1, concentration v1.1
- **Stablecoin tier governance:** Unanimous — manual YAML, monthly + on-incident
