---
name: risk-checks
description: Define and implement portfolio risk checks (health factor, LP imbalance, depeg/oracle checks later) using only aggregator data.
---

# Risk Checks

## Goal
Compute risk metrics and generate alert-worthy events from a canonical portfolio snapshot.

## Workflow
1. Define metrics with explicit data dependencies.
2. Implement checks as pure functions:
   - input: canonical portfolio snapshot
   - output: list of risk findings (severity, message, related positions)
3. Support config:
   - HF threshold (default 1.4)
   - LP imbalance threshold
   - alert dedupe window
4. If required data is missing:
   - produce an "unknown" finding, not a guessed metric

## Outputs
- Deterministic risk findings suitable for JSON report and Telegram summary
