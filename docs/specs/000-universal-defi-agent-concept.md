# Specification: Universal DeFi Agent (Multi-Protocol) - Concept & Architecture

Status: DRAFT
Owner: User/Agent
Related Memory: `docs/memory-bank/productContext.md`
Date: 2026-02-01

## 1. Context & Business Value
In 2026 DeFi protocols are too interconnected to manage one-by-one. We need a universal agent that works across chains and protocols using aggregator APIs (universal adapters), providing discovery, monitoring, and security screening to help create and manage a DeFi portfolio.

## 2. Core Concept
Shift from protocol-specific integrations to modular architecture with universal adapters:
- Discovery: DeFiLlama Yields API (market-wide yield opportunities)
- Monitoring: Debank Cloud (wallet positions across chains/protocols)
- Security: GoPlus Security (primary) + De.Fi (secondary enrichment)

## 3. Modules (Modular Architecture)
### 3.1 Discovery (Scout)
- Input: filters (stablecoin=true, tvl threshold, allowed chains)
- Output: ranked candidate pools/strategies with metadata

### 3.2 Monitoring (Observer)
- Input: wallet address
- Output: normalized portfolio snapshot (Supply/Borrow/LP), risk flags, alerts

### 3.3 Security (Auditor)
- Input: contract/pool identifiers from Discovery or current portfolio
- Output:
  - Dynamic risk flags (GoPlus): honeypot, blacklist, minting/taxes, proxy/ownership risks, approvals monitoring
  - Reputation enrichment (De.Fi): audit database / REKT history metadata for candidate evaluation

### 3.4 Orchestration (Sentinel)
- Coordinates modules, schedules runs, dedupes alerts, writes reports.

## 4. Interfaces (User Outputs)
- Daily Alpha: suggestions with ROI vs gas + safety score and rationale.
- Emergency Dashboard: unified table of all positions and liquidation risk.
- Notifications: Telegram alerts with severity and recommended actions.
- Reports: JSON (SSOT), optional Markdown summaries.

## 5. Constraints
- Use universal adapters first; avoid protocol-by-protocol code.
- Read-only by default; no private keys.
- Tolerate aggregator latency; focus on robustness and correctness.

## 6. Out of Scope (for this concept spec)
- Specific protocol execution logic; tx building/execution is a later phase.

## 7. Acceptance Criteria
- We have a clear module boundary and interface contracts.
- We have an MVP sequencing plan (Observer first, then Discovery, then Security).

## Approvals
- [ ] User Approved
- [ ] Architecture Approved
