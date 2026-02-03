# Specification: Universal DeFi Agent - Monitoring Module (Observer) v1

Status: DRAFT
Owner: User/Agent
Related Memory: `docs/memory-bank/activeContext.md`
Date: 2026-02-01

## 1. Context & Business Value
Create the Monitoring module ("Observer") of the Universal DeFi Agent.
It aggregates positions for a wallet address via Debank Cloud, evaluates key risks,
and produces actionable outputs. This module is the foundation for the broader
agent (Discovery + Security + Portfolio management), but those are not implemented here.

## 2. User Stories
- As a DeFi user, I want to see all my positions across protocols/chains in one view, so I can manage risk centrally.
- As a DeFi user, I want alerts when health factor is low or LP pools become imbalanced, so I can exit in time.
- As a DeFi user, I want a JSON report and Telegram notification, so I can automate monitoring.

## 3. Functional Requirements
- REQ-001: The system must fetch all wallet positions via Debank Cloud API for a given address.
- REQ-002: The system must classify positions into lending and LP categories (at minimum).
- REQ-003: The system must compute risk flags:
  - Lending: health factor threshold alert (default < 1.4).
  - LP: imbalance alert when one asset exceeds a configurable share threshold.
- REQ-004: The system must produce a compact "portfolio snapshot" suitable for later enrichment by Discovery/Security modules.
- REQ-005: The system must output a JSON report containing positions, risk flags, and comparisons.
- REQ-006: The system must send a Telegram notification with a compact summary of risks.

## 4. Non-Functional Requirements
- Performance: tolerate 1–2 minute API latency; polling is acceptable.
- Security: read-only access; no private keys stored.
- Reliability: graceful handling of API errors and partial data.

## 5. Constraints
- Tech stack: Python (async), Debank Cloud API, Telegram bot API.
- No protocol-specific integrations in v1 (Debank is the adapter).
- No automated trading or transaction execution in v1.

## 6. Out of Scope
- Discovery module (DeFiLlama) and Security module (De.Fi/GoPlus).
- Portfolio recommendations and rebalancing actions.
- One-click exit transaction building.

## 7. Acceptance Criteria
- Given a wallet address, the system returns a JSON report listing positions with risk flags.
- If health factor < 1.4 on any lending position, Telegram alert is sent.
- If LP imbalance exceeds threshold, Telegram alert is sent.
- Report includes a stable position schema that can be enriched later.

## 8. Risks / Open Questions
- Debank Cloud auth requirements and rate limits.
- LP imbalance calculation: define exact metric and data availability.
- Desired polling cadence and alerting policy (dedupe, severity levels).

## Approvals
- [ ] User Approved
- [ ] Architecture Approved
