---
name: lp-opportunity-scoring
description: Rank where to create a liquidity pool (chain/protocol/pair) using net yield, liquidity quality, and risk gates with explicit formulas.
---

# LP Opportunity Scoring

## Goal
Select the best chain/protocol/pair for opening a new LP position, not just the highest nominal APR.

## Workflow
1. Build candidate set from DeFiLlama pools (and optional direct protocol fields).
2. Compute normalized score:
   - fee_component = f(vol24h, fee_tier, tvl)
   - reward_component = effective reward APR (after haircut)
   - drag_component = IL proxy + gas + rebalance cost
   - net_alpha = fee_component + reward_component - drag_component
3. Apply hard gates:
   - token universe allowlist (BTC/ETH family, top stables, XAUT/PAXG for phase-1)
   - minimum liquidity sanity
   - protocol risk status (Inspector/Security finding)
4. Rank by net_alpha, break ties by liquidity quality and confidence.
5. Return top-N with machine-readable reasons.

## Required Inputs
- Pool APY/APR fields, TVL, 24h volume, chain, project, pair symbol
- Reward metadata (if available)
- Security/Inspector signal (PASS/WATCHLIST/FAIL)
- Configured thresholds and multipliers

## Outputs
- Ranked candidates with:
  - `net_alpha`
  - key contributors (fees/rewards/drag)
  - `source_confidence`
  - reject reasons for filtered pools

## Guardrails
- Do not treat reward APR as fully realizable by default; apply haircut.
- If core fields are missing, downgrade confidence and keep candidate in watchlist only.
- Keep formula weights explicit in config, never hidden in prompt logic.
