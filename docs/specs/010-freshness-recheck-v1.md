# Specification: Freshness Re-check v1 (Decision-Grade Alerts)

Status: APPROVED
Owner: Tech Lead / Architect
Related Memory: `docs/memory-bank/activeContext.md`
Date: 2026-02-04

## 1. Context & Business Value
Current discovery pipeline is stable and now surfaces actionable candidates, but operators observed lag/mismatch between live DEX UIs and aggregated discovery data.
This creates decision risk: alerts may be technically valid but operationally stale.

Goal: keep DeFiLlama as broad intake, then add a lightweight re-check stage before Telegram publication so actionable alerts represent fresher market state.

## 2. User Stories
- As a user, I want alerts to represent current conditions, not delayed snapshots.
- As an operator, I want explicit freshness and divergence signals in each alert.
- As a risk-first system, I want stale/divergent candidates downgraded automatically instead of silently passing into actionable output.

## 3. Functional Requirements

### REQ-001: Two-Step Re-check Before Telegram
For shortlist candidates (post security/L3 scoring), the system must perform a pre-alert re-check using the nearest source adapter (DEX API/Subgraph/protocol endpoint where available).

The re-check scope must be configurable:
- `recheck_enabled`
- `recheck_max_candidates` (top-N by score)
- `recheck_timeout_seconds`

### REQ-002: Freshness Metadata
Each re-checked candidate must include:
- `source_timestamp`
- `age_minutes`
- `staleness_score` (0..100)
- `freshness_status` (`FRESH`, `STALE`, `UNVERIFIED`)

### REQ-003: Divergence Detection
System must compare discovery vs re-check values and compute:
- `apy_divergence_pct`
- `tvl_divergence_pct`

Configurable thresholds:
- `max_apy_divergence_pct`
- `max_tvl_divergence_pct`

If threshold exceeded, candidate gets reason code `STALE_DATA` or `DIVERGENCE_HIGH`.

### REQ-004: Output Gating Policy
`ACTIONABLE` output must include only candidates with:
- `freshness_status=FRESH`
- no high divergence flags

Candidates failing freshness/divergence rules must be downgraded to `WATCHLIST` with explicit tags:
- `UNVERIFIED_FRESHNESS`
- `STALE_DATA`
- `DIVERGENCE_HIGH`

### REQ-005: Operational Visibility
Each cycle must emit summary counters:
- `rechecked_count`
- `fresh_count`
- `stale_count`
- `unverified_count`
- `diverged_count`
- `downgraded_to_watchlist_count`

### REQ-006: No Silent Fallback in Production
If re-check stage fails globally in production, behavior must be explicit:
- candidates are marked `UNVERIFIED`
- no silent promotion to actionable
- pipeline continues with clear warning logs and status counters

## 4. Non-Functional Requirements
- Deterministic decision logic for freshness/downgrade.
- Bounded overhead: re-check stage must not exceed configured timeout budget.
- Backward-compatible: existing security hard blocks and Lindy rules remain unchanged.

## 5. Constraints
- Discovery source remains DeFiLlama for v1 intake breadth.
- Re-check adapters may have partial chain/protocol coverage; unsupported cases must be explicit.
- Must preserve current scheduler and fail-fast invariants.

## 6. Out of Scope
- Full multi-source replacement of DeFiLlama intake.
- Trade execution automation.
- Historical backtesting engine for freshness policies.

## 7. Acceptance Criteria
- AC-001: Telegram rows include freshness metadata/tags for all reported candidates.
- AC-002: No candidate without `FRESH` status appears in actionable bucket.
- AC-003: Logs include full re-check counters each cycle.
- AC-004: Re-check provider outages do not silently pass candidates as fresh.

## 8. Risks / Open Questions
- Source coverage asymmetry across chains/protocols may produce many `UNVERIFIED` candidates initially.
- Need calibration of divergence thresholds to avoid excessive false downgrades.

## Approvals
- [x] User Approved (explicit "ок. приступай" in chat)
- [x] Architecture Approved
