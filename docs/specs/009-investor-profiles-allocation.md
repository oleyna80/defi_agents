# Specification: Investor Profiles & Allocation Engine v1

Status: APPROVED
Owner: Tech Lead / Architect
Related Memory: `docs/memory-bank/activeContext.md`
Date: 2026-02-04

## 1. Context & Business Value
Current Scout filtering is generic and does not adapt to investor capital scale or contribution pattern.
Users with very different strategies (e.g., DCA micro-investors vs large portfolios) need different pool selection logic and risk controls.

## 2. User Stories
- As a small investor, I want recommendations that beat my bank benchmark after costs.
- As a growing investor (initial + monthly contribution), I want DCA-aware suggestions that account for fixed costs.
- As a large investor, I want capacity-aware recommendations that avoid over-sizing into shallow pools.
- As an advanced user, I want a small tactical sleeve for high-APY opportunities with strict risk caps.

## 3. Functional Requirements

### REQ-001: Investor Profile Schema
System must support profile inputs:
- `initial_capital_usd`
- `monthly_contribution_usd`
- `risk_profile` (`micro`, `standard`, `whale`)
- `horizon_days`
- `benchmark_apy`

### REQ-002: Allocation Sleeves
System must support portfolio sleeves with configurable risk budgets:
- `core_safe`
- `yield_plus`
- `tactical_high_apy`

Each sleeve has max allocation percentage and per-position caps.

### REQ-003: Capacity Guardrails
For each candidate, apply:
- `max_position_pct_of_tvl`
- per-protocol allocation cap
- per-chain allocation cap

### REQ-004: DCA-aware Filtering
Selection must account for contribution cadence and fixed costs:
- avoid recommending positions where expected net gain is dominated by fixed transaction costs
- support periodic rebalance cadence aligned with contribution schedule

### REQ-005: Benchmark Mode
System must evaluate `net_apy` relative to benchmark:
- highlight candidates that exceed `benchmark_apy + buffer`
- include this tag in report metadata/output

## 4. Non-Functional Requirements
- Deterministic: same inputs/profile => same sleeve assignment.
- Safe-by-default: tactical sleeve disabled unless explicitly enabled.
- Operable: profile and sleeve settings live in config SSOT.

## 5. Constraints
- Must keep existing anti-scam hard blocks.
- Must remain compatible with current Scout/Security/L3 pipeline.

## 6. Out of Scope
- Auto-execution of capital allocation.
- User account management / auth.
- Full historical performance simulation engine.

## 7. Acceptance Criteria
- AC-001: Same candidate can be scored differently for micro vs whale profile due to cost/capacity rules.
- AC-002: Tactical high-APY opportunities are visible only inside tactical sleeve and capped by risk budget.
- AC-003: Reports include benchmark status and sleeve tags.
- AC-004: No hard-blocked candidate reaches any sleeve output.

## 8. Risks / Open Questions
- Need robust TVL-based capacity assumptions by chain/protocol.
- Need baseline benchmark source policy (manual config vs auto feed).

## Approvals
- [x] User Approved (explicit agreement in chat)
- [x] Architecture Approved

