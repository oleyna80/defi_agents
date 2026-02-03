# Specification: Scout Module (Discovery) v1.0

Status: DRAFT
Owner: User/Agent
Related Memory: `docs/specs/003-business-process.md`
Date: 2026-02-01

## 1. Concept
Scout is an autonomous discovery agent that pulls data from DeFiLlama, applies hard business filters, and ranks opportunities by yield vs safety. It must only send high-quality candidates into SecurityAuditor.

## 2. Data
- Source: DeFiLlama Yields API (`https://yields.llama.fi/pools`).
- Static filters:
  - `tvlUsd` > 1_000_000
  - No chain restriction (all networks)
  - Pool priority:
    1) stablecoin-only pools
    2) coin + stable pools
    3) coin + coin pools
- Dynamic fields:
  - `apyBase`
  - `apyReward`
  - `predictions` (DeFiLlama APY stability)

## 3. Pipeline
1. Ingestion: Fetch full pool list.
2. Filter layer: TVL, asset type (priority tiers).
3. Analysis:
   - Yield quality: base APY vs reward APY ratio.
   - APY volatility over last 7 days (if available).
4. Security gate: `SecurityAuditor.evaluate()` for each candidate.
5. Ranking: Yield-to-Risk score.

### Scoring (v1)
- `yield_quality = apyBase / apy`
- `score = apy * yield_quality * security_factor`
  - security_factor: TRUSTED=1.0, PASS=0.9, WARN=0.6

## 4. Interfaces
- `find_candidates()` (async)
- `ScoutResult` (Pydantic model): pool info + `SecurityResult`
- `ScoutConfig` (Pydantic): chains, TVL/APY thresholds, gas constraints

## 5. User Stories
- Prefer pools where base APY dominates reward APY.
- Only notify pools with `SecurityStatus` PASS or TRUSTED.
- Show estimated profit on $1,000 net of gas.

## 6. Validation
- Anti-spam: do not recommend the same pool more than once in 24h unless parameters changed.
- Gas sanity: if entry gas cost > 2% of $1,000 ($20), mark `LOW_EFFICIENCY`.

## 7. Risks
- API staleness (30–60 min).
- Ghost liquidity (high APY, low volume).
- Reward token crash risk.

## Approvals
- [ ] User Approved
- [ ] Architecture Approved
