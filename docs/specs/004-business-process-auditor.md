# Specification: Business Process - Step 2 (Reliability Scoring / Auditor)

Status: DRAFT
Owner: User/Agent
Related Memory: `docs/specs/003-business-process.md`
Date: 2026-02-01

## 1. Goal
Take the Step 1 top candidates and filter/score them for reliability before any recommendation is shown as "actionable".

## 2. Inputs
- Candidate pools from Step 1 (ranked list, stablecoins Tier 1, risk categories excluded).
- Optional: user's current portfolio context (to compute switching ROI and compare with borrow costs).

## 3. Checks (Required)

### 3.1 Safety Score (De.Fi)
- Fetch De.Fi safety score for the pool/protocol/contract.
- Rule: if score < 70/100 => reject candidate.
- If score is unavailable => treat as "unknown" and reject by default (conservative).

### 3.2 Audit History (De.Fi)
- Fetch audit metadata.
- Rule: require at least one audit from the "Big Four":
  - OpenZeppelin
  - Trail of Bits
  - Spearbit
  - Quantstamp
- If no qualifying audit exists => reject candidate (default policy).
- If audit metadata is unavailable => reject candidate by default.

### 3.3 Lending economics (LTV / Borrow Rate vs Farming Yield)
Applies only when the candidate is a lending strategy (or includes a borrow leg).

- Inputs (real-time where possible):
  - supply yield / farming APY (gross)
  - borrow rate (APR/APY)
  - LTV constraint of the lending market
- Rule (initial): compute net carry = farming_yield - borrow_rate.
  - If net carry <= 0 => reject.
  - If net carry is small (threshold TBD) => warn (not in top-10 actionable list).

Notes:
- Exact source for borrow rate and LTV must be defined per universal adapters.
- If these inputs are unavailable for a lending candidate => reject by default.

## 4. Output
- A filtered, reliability-scored list of candidates:
  - `accepted`: list of candidates that passed reliability gates
  - `rejected`: list with explicit reasons (score below threshold, no audit, missing data, negative carry)

## 5. Non-Goals
- No transaction building/execution.
- No deep manual audit; only adapter-driven checks.

## 6. Open Questions
- Which De.Fi endpoints/identifiers are available for pool-level safety score vs protocol-level score?
- If De.Fi returns only protocol-level data, do we accept it as a proxy?
- For lending, which adapter provides borrow rate + LTV consistently across chains?

## Approvals
- [ ] User Approved
- [ ] Architecture Approved
