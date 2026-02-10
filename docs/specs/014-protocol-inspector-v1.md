# Specification: Protocol Inspector v1 (Risk-First, Onchain Verifiability)

Status: APPROVED
Owner: Tech Lead / Architect
Related Memory: `docs/memory-bank/activeContext.md`
Date: 2026-02-10

## 1. Context & Business Value

The current Security Auditor is primarily based on third-party scanners and reputation aggregators.
This is effective for many EVM chains, but it does not provide decision-grade, onchain-verifiable answers
for new ecosystems and protocols (e.g., HyperEVM) where upstream providers may be unavailable.

We need an automated inspector that can:
- resolve a protocol's core contract set even when discovery sources omit addresses
- verify core safety properties directly onchain (upgrade/admin/roles/pauses)
- publish a compact, risk-first report to Telegram

This is not trading/execution. It is due diligence automation.

## 2. User Stories

- As an operator, I want an automated "dossier" for a protocol/pool, so that I can decide if it is worth further research or capital allocation.
- As a reader, I want an explicit PASS/WATCHLIST/FAIL verdict with evidence, so that I do not confuse missing data with safety.
- As an operator, I want change alerts (admin/implementation/roles/pauses), so that I am notified when an audited/known protocol changes risk posture.

## 3. Functional Requirements

- REQ-001: The system must support a new inspection pipeline called Protocol Inspector.
- REQ-002: The inspector must accept a target specified by at least one of:
  - DeFiLlama protocol slug (e.g., `altura`)
  - DeFiLlama yield pool id (UUID)
  - Direct seed contract address (vault/manager) plus chain/rpc
- REQ-003: The inspector must resolve a Contract Set (SSOT) using deterministic, bounded steps.
- REQ-004: The inspector must run onchain checks against the resolved contract set:
  - contract existence (`eth_getCode`)
  - proxy detection (EIP-1967 where applicable)
  - implementation/admin extraction for proxies
  - governance/roles best-effort detection (owner/admin roles)
  - emergency controls best-effort detection (pause/sweep/rescue patterns)
- REQ-005: The inspector must produce a "Dossier v0" report containing:
  - identity (protocol/pool), chain info, contracts, evidence, findings, verdict
- REQ-006: The inspector must be risk-first:
  - missing Contract Set data => `verdict=WATCHLIST` and `status=PARTIAL`
  - missing onchain proofs => `verdict=WATCHLIST` and explicit missing fields
  - no "PASS by absence" behavior
- REQ-007: The inspector must persist a minimal last-known snapshot and produce a diff alert when high-impact fields change:
  - proxy implementation change
  - admin/owner change
  - pause flag change (if detectable)

## 4. Non-Functional Requirements

- Performance:
  - bounded number of external calls per run (configurable)
  - bounded block/log scanning (off by default in v1; enable only with explicit budget)
- Security:
  - never log secrets or `.env` values
  - sanitize URLs that may contain API keys (mask `.../api/<key>/...`)
  - never treat upstream unavailability as "safe"
- Compatibility:
  - must not break the existing Scout pipeline or systemd schedule
  - feature-flagged activation

## 5. Constraints

- Tech stack: Python async (`httpx`), existing notifier, existing config patterns.
- Must be able to run as a `systemd --user` oneshot service.

## 6. Out of Scope (v1)

- Trade execution / onchain transactions
- Full formal verification
- Unbounded "scan the whole chain" inference for contract discovery
- Deep economic modeling beyond basic rewards/base APY split and obvious sustainability flags

## 7. Proposed Architecture Decision (Docs-First)

Protocol Inspector should be a separate scheduled job ("service-bot") in production:
- rationale: isolates runtime, rate limits, and failure modes from the Scout cycle
- implementation: separate entrypoint, separate `systemd --user` service+timer, same repo/venv, same Telegram notifier

This decision is documented here; final approval happens when we approve this spec.

## 8. Dossier v0 (Output Contract)

Minimal fields (v1):
- `identity`: name, defillama_slug, docs_url(s)
- `chain`: name, chain_id, rpc_url (not logged), explorer_url
- `contract_set`:
  - `core[]`: address, label, code_hash, is_proxy, implementation, admin
  - `tokens[]`: underlying/reward tokens as applicable
- `evidence[]`: source type + url (no secrets) + extracted identifiers
- `findings[]`: machine-readable issues with severity
- `verification`: checked_at, block_number
- `verdict`:
  - status: OK | PARTIAL
  - verdict: PASS | WATCHLIST | FAIL
  - rationale: compact human summary
  - missing[]: required next data

## 9. Contract Set Acquisition (Resolver v1)

The resolver must attempt these in order, with bounded budgets:
1) DeFiLlama legacy yields metadata (e.g., `poolsOld`) if available
2) Official docs/repo "deployments/addresses" artifacts (file-based)
3) Campaign/opportunity pages (e.g., Merkl) as seed addresses
4) Explorer token-flow heuristics (bounded top holders / inbound fan-in)
5) RPC log inference (last resort; bounded block window; off by default)

Seeds from (2)-(5) are treated as untrusted until validated onchain.

## 10. Acceptance Criteria

- AC-001: Given a seed vault address and RPC, inspector outputs a dossier with:
  - code exists
  - proxy metadata (or explicit "not detected")
  - governance/roles best-effort (or explicit "missing")
  - a risk-first verdict (PARTIAL/WATCHLIST when fields are missing)
- AC-002: Unavailable endpoints/RPC timeouts do not crash the job; output is PARTIAL with `DATA_UNAVAILABLE` findings.
- AC-003: A second run produces a diff alert if implementation/admin changes.
- AC-004: No secrets appear in logs or Telegram messages.

## 11. Risks / Open Questions

- Which chains provide reliable explorer APIs vs RPC-only operation?
- How to maintain chain RPC endpoints (config vs env) without secrets leakage?
- How to avoid false positives for proxy/roles detection on nonstandard contracts?

## Approvals

- [x] User Approved
- [x] Architecture Approved
