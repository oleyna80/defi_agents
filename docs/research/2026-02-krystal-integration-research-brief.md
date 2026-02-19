# Krystal Integration Research Brief

**Date:** 2026-02-19  
**Owner:** Tech Lead  
**Requester:** Dmitrii  
**Context:** `docs/research/krystal-api-discovery.md` currently concludes `NO-GO` for server-side access because of Cloudflare challenge (`403 cf-mitigated`).

## 1. Goal
Find a production-safe path to use Krystal data in our stack, or recommend the best alternative stack with equivalent business value.

## 2. Decisions Needed
1. Is there an official server-to-server access path for Krystal (`service key`, `IP allowlist`, `partner endpoint`)?
2. If yes: is it viable for our LP discovery contract and operationally stable?
3. If no: what is the best replacement stack for discovery/tick-level needs, with minimal impact on current architecture?

## 3. Hard Constraints
- No bypass/hacking of anti-bot systems.
- Only legal, supportable, production-safe integrations.
- Keep current architecture contracts:
  - Tick-level core path remains `TickDataProvider`/Subgraph-based.
  - Krystal can only be optional discovery provider unless proven otherwise.
- Recommendations must include rollout risk and fallback.

## 4. Research Questions
1. Krystal Access:
   - Official API onboarding path?
   - Required credentials and process?
   - SLA/rate limits/pricing/usage restrictions?
2. Data Contract Fit:
   - Can Krystal provide: `pool_address`, `token0`, `token1`, `volume_30d`, `fee_tier`?
   - Is schema stable (backward compatibility/versioning)?
3. Alternatives (if Krystal blocked):
   - Top 2-3 provider stacks for discovery + quality of data.
   - Integration cost in our current codebase.
4. Risk/Compliance:
   - TOS constraints, vendor lock risk, operational fragility.

## 5. Deliverables
1. `GO / CONDITIONAL GO / NO-GO` verdict for Krystal with evidence.
2. Comparison table: Krystal vs alternatives:
   - access model
   - required fields coverage
   - reliability
   - implementation effort
   - cost/rate limits
   - key risks
3. Recommended implementation plan (2-week horizon):
   - primary path
   - fallback path
   - explicit stop/go checkpoints
4. Source appendix with links.

## 6. Acceptance Criteria
- Recommendation is actionable, not theoretical.
- Every key claim has a source or direct evidence.
- Includes a concrete next action list for engineering.

## 7. Output Format (mandatory)
1. Executive summary (max 10 lines)
2. Findings by category
3. Decision matrix
4. Final recommendation
5. 2-week action plan
6. Sources

