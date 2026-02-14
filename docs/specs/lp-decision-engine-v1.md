# LP Decision Engine v1 Specification

**Status:** APPROVED
**Version:** 1.0.2
**Phase:** 6 (Active LP Management)

## 0. Non-Goals & Explicit Constraints (v1)

These constraints are **hard blockers** for the v1 release to ensure safety and manageability.

1.  **`MANUAL_EXECUTION_ONLY`**: The system provides *recommendations* (signals), but **never** executes transactions automatically. All on-chain actions (Mint, Burn, Collect, Swap, Bridge) require explicit human approval via CLI or Telegram.
    *   *Rationale*: Safety, legal compliance (non-custodial, advisory-only technical tool).
2.  **`SINGLE_DEPLOYMENT`**: Initial rollout is limited to **Base Chain + Aerodrome** (or Uniswap v3).
    *   *Rationale*: Verify end-to-end pipeline reliability before scaling to multi-chain complexity.
3.  **`GRACEFUL_DEGRADATION`**:
    *   If `data_quality.provider_status == DEGRADED` -> downgrade this candidate to `WATCHLIST` (do not recommend for immediate entry).
    *   If `data_quality.provider_status == DOWN` -> stop scoring this candidate/source, alert operator, do not fallback to stale data. Mark as `UNVERIFIED_SOURCE` in reports.

---

## 1. High-Level Architecture

The system is divided into two decoupled pipelines to avoid conflict of interest between "finding new gems" and "protecting existing capital".
**Note for v1:** Implemented as a single process with two isolated logical loops (`asyncio.create_task`) and separate error boundaries. Physical separation to distinct systemd units is deferred to v1.1.

### 1.1 Discovery Pipeline (Batch)
*   **Frequency**: Every 4-6 hours (configurable).
*   **Source**: DeFiLlama (broad) -> Subgraph/RPC (deep validation).
*   **Output**: `Opportunity` list with Scores and Risk Tags.
*   **Logic**: Heavy scoring, LLM explainability, historical backtest.

### 1.2 My Pools Monitor (Real-time)
*   **Frequency**: Every block (WebSocket) or 1-minute polling (Direct RPC).
*   **Source**: Direct RPC (node). **No Subgraph dependency** for critical alerts.
*   **Output**: Alerts (`OUT_OF_RANGE`, `Price_Approaching_Edge`, `Liquidity_Drain`).
*   **Logic**: Lightweight, deterministic, low-latency.

---

## 2. Data Models (API Contracts)

All models must be implemented as Pydantic schemas in `src/defi_agents/scout/lp_models.py` (aligned with the current `src/defi_agents/scout/*` package structure).

### 2.1 `PoolSourceData` (Raw Data)
The raw snapshot from the sourcing adapter.

```python
from typing import Literal, Optional
from datetime import datetime
from pydantic import BaseModel

class DataQuality(BaseModel):
    provider_status: Literal["OK", "DEGRADED", "DOWN"]
    source_age_sec: int
    chain_head_lag_blocks: int
    fallback_used: bool
    degraded_reason: Optional[str] = None
    collected_at_utc: datetime

class PoolSourceData(BaseModel):
    pool_ref_id: str  # e.g. "base:aerodrome:0x..."
    chain: str
    dex: str
    
    # Raw metrics
    price_token1_per_token0: float
    tick: Optional[int]
    tvl_usd: float
    volume_24h_usd: float
    fees_24h_usd: float
    
    # Metadata
    data_quality: DataQuality
```

### 2.2 `PoolAnalysis` (Enriched Data)
Derived metrics calculated by the Analysis Engine.

```python
class TokenRiskProfile(BaseModel):
    transfer_restricted: bool  # blacklist/whitelist function?
    redemption_restricted: bool # KYC/min amount for redemption?
    bridge_wrapped: bool       # is this a bridged asset?
    rebasing: bool             # stETH, OHM (incompatible with CL)
    fee_on_transfer: bool      # deflationary/tax tokens (BLOCKER)

class YieldBenchmark(BaseModel):
    risk_free_delta: float
    median_delta: float

class PoolAnalysis(BaseModel):
    # JIT / MEV Risk
    jit_activity_ratio: float  # (mints + burns) / swaps over 24h
    jit_level: Literal["CLEAN", "MODERATE", "HIGH_JIT"]
    
    # Volatility & Range
    volatility_atr_1d: float
    volatility_atr_7d: float   # Needed for regime detection
    derived_band_width_pct: float
    
    # Simulator Assumptions
    liquidity_assumption: Literal["STATIC", "HISTORICAL"]
    assumption_confidence: Literal["HIGH", "MEDIUM", "LOW"]
    
    # Risk Profile
    token_risk_profile: TokenRiskProfile
    
    # Benchmarks
    risk_free_rate_chain: float  # local chain Aave supply rate
    risk_free_source: str        # e.g. "aave_v3_base"
    yield_vs_benchmark: YieldBenchmark
```

### 2.3 `Opportunity` (Decision)
Final candidate object for the operator.

```python
class Opportunity(BaseModel):
    opportunity_id: str
    pool_ref: PoolRef
    
    # Commercials
    estimates: PnLEstimates  # net_fees, gas_cost, time_in_range
    score_raw: float         # Before confidence/risk multipliers
    score_adjusted: float    # After: score_raw * confidence_factor * inspector_factor
    
    # Benchmarks
    yield_vs_benchmark: YieldBenchmark
    risk_free_rate_chain: float
    
    # Diagnostics
    decision_log: List[DecisionStep]  # Audit trail of filtering
    rejection_reasons: List[str]
```

---

## 3. Scoring Engine ("Fees-Max" Strategy)

### 3.1 Net Fee Yield Formula
```
NetFeeYield = ExpectedFees - (Gas + AutomationFees + Slippage) - ImpermanentLoss_RiskPremium
```
*   `ExpectedFees`: derived from `volume_24h` * `fee_tier` * `concentration_factor`.
*   `Gas`: estimated cost of 1 open + 1 close + `N` rebalances over period `H`.

### 3.2 Benchmarking
Every candidate is compared against:
1.  **Hard Floor**: `RiskFreeRate` (local chain Aave USDC supply APY). If `NetFeeYield < RiskFree`, Score = 0.
2.  **Soft Benchmark**: `MedianYield` of the top-10 filtered candidates.

### 3.3 Token Risk Gates
*   If `fee_on_transfer` OR `rebasing` is True -> **HARD REJECT (Score 0)**.
*   If `bridge_wrapped` is True -> Apply risk penalty (e.g. 0.8x multiplier).

### 3.4 Hard Filters (Per-Pair Configuration)
Configuration driven filters to remove noise before scoring.
```yaml
hard_filters:
  stable_stable: {min_tvl_usd: 500_000, min_volume_24h_usd: 100_000}
  volatile_stable: {min_tvl_usd: 2_000_000, min_volume_24h_usd: 500_000}
  gold_stable: {min_tvl_usd: 1_000_000, min_volume_24h_usd: 200_000}
```

---

## 4. Alerting Logic (Hysteresis)

To prevent alert fatigue, alerts use a state machine with debouncing.

**Structure**: `AlertRule` (Dataclass)
*   `trigger_threshold`: Value to activate alert (e.g., `liquidity < $50k`).
*   `release_threshold`: Value to clear alert (e.g., `liquidity > $60k`).
*   `min_confirmations`: Number of consecutive checks (windows) to confirm state change.
*   `cooldown`: Minimum time between identical alerts.

**Key Alerts**:
1.  **Liquidity Drain**: Sudden drop in `liquidityNet` active.
2.  **Fee Tier Migration**: Volume moving to a different fee tier.
3.  **Out of Range**: Price crosses Lower/Upper Tick.
4.  **Provider Health**: Alert if `provider_status` becomes `DOWN` or `DEGRADED`.

---

## 5. Implementation Roadmap

### P0: Foundation + Capital Protection (Weeks 1-2)
*   [ ] Implement `src/defi_agents/scout/lp_models.py` with data models from this spec.
*   [ ] Implement `EndpointRegistry` with Aave v3 `lending_benchmarks` for per-chain RiskFree.
*   [ ] Enhance **MyPoolsMonitor** (existing P2.6) with Direct RPC/WebSocket support & heartbeat alerts.
*   [ ] Build basic "Discovery" pipeline for **Base/Aerodrome** only.
*   [ ] Output: Telegram alerts for own positions + simple Top-10 list.

### P1: Simulation & Precision (Weeks 3-4)
*   [ ] Implement `RangeSimulator` (Static Liquidity Assumption + `assumption_confidence` guardrail).
*   [ ] Add `jit_activity_ratio` detection (Subgraph Mint+Burn/Swap count queries).
*   [ ] Implement `NetFeeYield` calculator with gas estimation.
*   [ ] Implement PnL P0: `RealizedFees - Gas` from Collect events.
*   [ ] Implement **RangeRegime** state machine (TIGHT/MEDIUM/WIDE with asymmetric cooldowns).

### P2: Alerting, Calibration & Scaling (Weeks 5-6)
*   [ ] Implement AlertEngine with hysteresis (`AlertRule`).
*   [ ] Scoring calibration: compare predictions vs actual PnL.
*   [ ] Expand to Arbitrum/Optimism/Polygon.
