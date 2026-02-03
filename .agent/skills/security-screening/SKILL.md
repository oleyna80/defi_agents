---
name: security-screening
description: Screen tokens/contracts/pools using De.Fi Scanner API or GoPlus Security and map results to normalized security risk outputs.
---

# Security Screening

## Goal
Provide automated, explainable security checks for candidates and current holdings.

## Workflow
1. Use GoPlus as primary (dynamic) and De.Fi as secondary (reputation enrichment).
0. Check local memory approvals first:
   - If token/protocol is in `docs/memory-bank/security/whitelist.json` => PASS (Trusted) unless explicit block flags exist.
2. Stage A (dynamic scan, GoPlus):
   - token/contract checks (honeypot, blacklist, taxes, proxy, ownership, minting)
   - approvals monitoring (new risky approvals, suspicious spenders)
3. Stage B (reputation, De.Fi):
   - audit database / REKT metadata for candidate pools
4. Define normalized output fields:
   - status: pass/warn/block/unknown
   - reasons: list of flags
   - sources: list of adapter results (goplus primary + defi enrichment)
5. For missing security data:
   - classify as unknown
   - do not auto-recommend; require explicit user confirmation
6. Store example payloads as fixtures and add tests.
7. Prefer deterministic rules over scalar "scores":
   - Example: if buy_tax > 10% => block (configurable).
8. Apply stablecoin tiering rules (from `docs/memory-bank/systemPatterns.md`):
   - Tier 1 can pass without extra warnings (subject to other flags).
   - Tier 2 requires context checks (protocol/ecosystem) -> usually warn unless explicitly allowed.
   - Tier 3 should default to warn/block for recommendations.

## Outputs
- Security screening function returning normalized decision + reasons
