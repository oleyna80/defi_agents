# Product Context

## Vision
- Build a "Universal DeFi Agent" (Multi-Protocol, Multi-Chain) that helps create,
  monitor, and manage a DeFi portfolio via universal data/security aggregators,
  not protocol-specific integrations.

## Primary Users
- DeFi users with positions across multiple protocols and chains.
- Power users who want unified monitoring, alerts, and safe exit paths.

## Goals / Success Criteria
- Unified visibility of wallet positions across protocols/chains (Supply/Borrow/LP).
- Automated discovery of best risk/return opportunities (starting with stablecoins).
- Built-in security screening of contracts/pools before suggestions/actions.
- Continuous monitoring + alerts (Telegram) + machine-readable reports (JSON).

## Scope
- In scope:
  - Discovery module via DeFiLlama Yields API (market-wide yields).
  - Monitoring module via Debank Cloud (wallet positions across chains/protocols).
  - Security module via De.Fi Scanner API or GoPlus (contract/pool risk checks).
  - Risk checks: lending health factor, depeg/LP imbalance signals (as data allows).
  - Portfolio management assistance: recommendations, comparisons, watchlists.
  - Outputs: JSON report + Telegram alerts (v1), later dashboards/automation.
- Out of scope:
  - Writing custom integrations per protocol as the primary approach.
  - High-frequency/low-latency trading or arb execution.
  - Custody of user funds (private keys) by default.

## Constraints
- Tech stack: Python (async), external REST APIs, Telegram notifications.
- Performance: tolerate aggregator latency; focus on robustness and correctness.
- Security/Compliance: avoid storing private keys; read-only by default, explicit opt-in for any tx building later.
- Timeline: start with Monitoring (Debank) as foundation; add Discovery and Security as first-class modules.

## Glossary
- Universal adapters: API wrappers abstracting protocol-specific details.
- Health factor: lending safety metric across protocols.
- LP imbalance: skew between assets in a liquidity pool.
