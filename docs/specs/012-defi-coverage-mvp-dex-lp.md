# Specification: DeFi Coverage MVP — DEX/LP Discovery v1

Status: DRAFT
Owner: Codex (Tech Lead)
Related Memory: `docs/memory-bank/activeContext.md`
Date: 2026-02-05

## 1. Context & Business Value
The system must expand beyond “LP only via aggregator” into a reliable DEX/LP discovery layer that can detect new pools quickly and feed the Strategy Simulator with normalized, decision‑grade metadata. This is the lowest‑risk, highest‑impact entry point for the broader DeFi coverage plan.

## 2. User Stories
- As a user, I want to see profitable DEX/LP opportunities across chains without missing newly created pools.
- As Strategy Simulator, I want normalized DEX pool candidates so I can evaluate multi‑leg strategies downstream.
- As Ops, I want this source to fail safe and never spam or bypass security gates.

## 3. Functional Requirements
- REQ-001: The system must ingest DEX/LP pools from DeFiLlama (LP category) with standardized fields (chain, symbol, project, TVL, APY).
- REQ-002: The system must query Uniswap v3 subgraph to detect newly created pools and attach pool age.
- REQ-003: DEX candidates must be normalized into the unified data contract with `class="dex"` and attach `pool_id` for deep linking.
- REQ-004: DEX candidates must continue to pass the existing security pipeline (no bypass).
- REQ-005: DEX candidates must carry freshness metadata (`freshness_status`, `source_timestamp`, divergence fields) and default to `UNVERIFIED` if missing.
- REQ-006: The system must emit per‑cycle counters for DEX pools ingested, new pools detected, and filtered totals.
- REQ-007: The Uniswap subgraph adapter must be configurable (enabled flag, max pools, min TVL filter).

## 4. Non-Functional Requirements
- Performance: Subgraph queries must be bounded (limit, filter by TVL) and cached per cycle.
- Reliability: Failures in Uniswap subgraph must not break the cycle; fallback to `UNVERIFIED`.
- Security: No new SSRF vectors or sensitive data leaks; use existing HTTP safety patterns.
- Compatibility: Must not change existing ScoutResult schema semantics; additions are metadata only.

## 5. Constraints
- Tech stack: Python, current Scout pipeline, DeFiLlama as baseline aggregator.
- Existing logic: DEX pools must still go through Security Auditor + L3 + Freshness.

## 6. Out of Scope
- Real‑time WebSocket pool discovery.
- Full fee‑APR calculation for all pools beyond what sources provide.
- Impermanent loss simulation (handled later in Strategy Simulator).

## 7. Acceptance Criteria
- A DEX/LP candidate appears in Telegram with correct chain/symbol/project/APY/TVL and pool link.
- New pools from Uniswap v3 subgraph appear within minutes when TVL exceeds threshold.
- No increase in false positives (security gates remain intact).
- Freshness tags are present for DEX candidates.
- Unit tests cover adapter enable/disable and basic mapping.

## 8. Risks / Open Questions
- Rate limits or Graph endpoint instability.
- DEX naming inconsistency across chains (Uniswap variants, forks).
- How to handle pools with missing or zero TVL (filter threshold).

## Approvals
- [ ] User Approved
- [ ] Architecture Approved
