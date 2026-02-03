# Specification: Business Process - Step 3 (Universal Monitoring / Observer)

Status: DRAFT
Owner: User/Agent
Related Memory: `docs/specs/000-universal-defi-agent-concept.md`
Date: 2026-02-01

## 1. Goal
Continuously monitor a wallet across chains/protocols via an aggregator API and raise actionable alerts.

## 2. Primary Data Source (to confirm)
- Debank Cloud (wallet-centric positions across chains/protocols)

## 3. Inputs
- `wallet_address`
- `hf_threshold`: 1.4
- `lp_imbalance_threshold`: TBD
- `poll_interval_seconds`: TBD
- `asset_classifier_policy`: fail-safe (if not sure => exclude / require manual approval)

## 4. Triggers

### 4.1 Trigger 1: Health Factor (Lending)
- Aggregate all lending borrows across protocols (Aave v3, Morpho, Compound, Spark, etc.) as seen by the adapter.
- Compute portfolio-level metric:
  - Initial: average HF across active borrowing positions.
- Rule: if average HF < 1.4 => alert.

Open question: do we use average HF, minimum HF, or weighted-by-debt HF? (business decision).

### 4.2 Trigger 2: Depeg / LP Imbalance (Stable LP)
- Monitor LP positions that contain stablecoins.
- Detect "skew": one stablecoin dominating pool composition (one stable pushes out the other).
- Rule: if imbalance exceeds threshold => alert "Exit now".

Open questions:
- Which imbalance metric is used (share %, deviation from 50/50, time-based drift)?
- Does the adapter provide current pool composition or do we need an additional pricing/source?

## 5. Output
- Telegram alerts with:
  - severity (warn/critical)
  - trigger name
  - affected positions
  - suggested action (e.g., "reduce borrow" / "exit LP")
- JSON snapshot (optional later) as SSOT for downstream analysis.

## 6. Non-Goals (Step 3)
- No transaction execution.
- No discovery/recommendation (handled in Steps 1-2).

## Approvals
- [ ] User Approved
- [ ] Architecture Approved
