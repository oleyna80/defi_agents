---
name: clmm-range-ops
description: Define practical CLMM range setup and rebalance triggers for active LP management with cost-aware constraints.
---

# CLMM Range Ops

## Goal
Convert a selected LP candidate into an executable range plan with explicit rebalance triggers.

## Workflow
1. Classify market regime (calm/trending/volatile) from recent volatility proxy.
2. Choose initial range policy:
   - tight for low-vol stable pairs
   - wider for volatile pairs
3. Define rebalance trigger set:
   - out-of-range condition
   - drift threshold from mid price
   - minimum expected uplift vs gas/slippage cost
4. Estimate rebalance cost and enforce cooldown.
5. Return action plan with stop conditions.

## Required Inputs
- Pair type, fee tier, liquidity depth
- Volatility proxy / APY stability proxies
- Chain gas cost assumptions

## Outputs
- `range_plan` (center, width policy, rationale)
- `rebalance_policy` (triggers, cooldown, min edge)
- `abort_conditions` (liquidity collapse, risk downgrade, data degradation)

## Guardrails
- Do not trigger rebalance when expected benefit < execution cost.
- On degraded data quality, switch to monitor-only mode.
