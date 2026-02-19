---
name: reward-economics
description: Evaluate incentive sustainability and convert nominal rewards into conservative effective APR for decision scoring.
---

# Reward Economics

## Goal
Prevent false positives from unstable incentive programs by converting headline rewards into conservative effective yield.

## Workflow
1. Split yield into base fees vs incentives.
2. For each reward token, evaluate:
   - liquidity depth / sellability
   - emission schedule and unlock pressure
   - concentration and governance mint risk
3. Compute reward haircut by risk tier.
4. Produce:
   - `reward_apr_nominal`
   - `reward_apr_effective`
   - `reward_risk_flags`
5. Feed effective reward into LP scoring instead of nominal reward.

## Required Inputs
- Reward token list and APR contribution
- Token market quality proxies (volume/liquidity concentration if available)
- Protocol emission metadata (when available)

## Outputs
- Effective reward adjustment per candidate
- Structured flags (`HIGH_DILUTION_RISK`, `LOW_EXIT_LIQUIDITY`, `EMISSION_UNCLEAR`, etc.)

## Guardrails
- Missing reward data => use conservative default haircut, never optimistic assumption.
- If reward token cannot be reasonably exited, mark as watchlist-only candidate.
