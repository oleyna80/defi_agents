# Specification: Security Module (Auditor) v1 - GoPlus Primary, De.Fi Secondary

Status: APPROVED
Owner: User/Agent
Related Memory: `docs/memory-bank/systemPatterns.md`
Date: 2026-02-01

## 1. Context & Business Value
We need automated, explainable security screening to avoid interacting with risky tokens/contracts/pools. The agent must support bot-friendly API access, fast checks, and granular flags to drive decision logic.

## 2. Architecture
Two-stage security pipeline:

### Stage A: Dynamic scan (GoPlus, primary)
- Used:
  - periodically for current holdings/pools (e.g., hourly)
  - immediately before recommending any new candidate
- Provides granular, machine-actionable flags.

### Stage B: Reputation enrichment (De.Fi, secondary)
- Used primarily during candidate evaluation (Discovery -> Candidate -> Security).
- Adds audit / reputation metadata (audit DB / REKT history) to adjust confidence.

## 3. Functional Requirements
- REQ-001: The system must provide a function to evaluate token/contract risk via GoPlus.
- REQ-002: The system must provide approval monitoring via GoPlus (detect risky approvals/spenders).
- REQ-003: The system must provide an enrichment step via De.Fi for candidate pools/tokens (audit/reputation metadata).
  - Primary key: contract address.
  - Secondary mapping: protocol slug from De.Fi response for audit history checks.
- REQ-004: The system must produce a normalized security result:
  - status: trusted/pass/warn/block/unknown
  - reasons: structured flags
  - sources: adapter outputs (GoPlus + optional De.Fi)
- REQ-005: The system must not auto-recommend candidates when security status is unknown.

## 4. Decision Rules (initial)
- If GoPlus indicates honeypot => block.
- If buy/sell tax exceeds configurable threshold => warn/block (configurable).
- If contract is not open source or has dangerous ownership patterns => warn.
- If De.Fi shows no top-tier audit (Tier A/B list) and asset is not Tier 1 => WARN.
- If De.Fi shows rekt history => WARN/BLOCK depending on recency and remediation.

## 5. Non-Functional Requirements
- Reliability: handle API errors gracefully; return unknown with reasons.
- Performance: low latency; cache results with TTL.
- Security: do not store secrets in repo; no private keys.

## 6. Constraints
- Primary adapter must be GoPlus.
- De.Fi is optional enrichment; absence must not break pipeline.
- No protocol-specific security logic (only adapter-driven).

## 7. Out of Scope
- Manual audits.
- Full transaction simulation.

## 8. Acceptance Criteria
- Given a token/contract, the module returns a normalized security result.
- A honeypot-like result blocks recommendation.
- For a new candidate, missing security data yields unknown and requires explicit user confirmation.

## 9. Risks / Open Questions
- Exact De.Fi API access level / partnership requirements.
- Exact GoPlus endpoints and chain coverage needed for our targets.
- How to store/cache security results (file-based vs lightweight DB).

## Approvals
- [x] User Approved (2026-02-01)
- [x] Architecture Approved (2026-02-01)
