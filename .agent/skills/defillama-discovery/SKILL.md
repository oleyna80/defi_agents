---
name: defillama-discovery
description: Use DeFiLlama Yields API to discover and rank yield opportunities using explicit filters and a scoring function.
---

# DeFiLlama Discovery

## Goal
Discover market opportunities (starting with stablecoin yields) without protocol-specific integrations.

## Workflow
1. Query DeFiLlama Yields API.
2. Apply explicit filters (configurable):
   - stablecoin=true
   - TVL threshold
   - allowed chains
   - optionally: pool type exclusions
3. Rank results using a transparent scoring model:
   - yield vs tvl vs volatility proxy (if available)
   - penalties for low liquidity / hard exit
4. Output candidates in a canonical format that can be security-screened.

## Outputs
- Candidate list with rationale and fields needed for Security checks
