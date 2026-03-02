---
name: runbook-runtime-drift-check
description: Verify that runtime behavior, log signatures, and runbook instructions are consistent after execution/ops changes.
---

# Runbook Runtime Drift Check

## Goal
Prevent operator-facing documentation drift after runtime changes (especially around fail-safe behavior, reason codes, and expected logs).

## When to Use
- After changes in `main.py`, orchestration, adapter routing, or policy gating.
- After introducing or removing fallback paths.
- Before SHADOW/LIVE gate work.

## Workflow
1) Identify changed runtime behavior
- `git diff -- main.py src/defi_agents/execution src/defi_agents/tracker`
- Extract key log signatures and reason codes from changed code.

2) Scan runbooks for stale expectations
- `rg -n "fallback|mock_positions|reason=|Execution state|Execution summary" docs/runbooks`
- Compare runbook examples with current log lines in code.

3) Validate operational contract
- Ensure runbook preflight/env requirements match runtime requirements.
- Ensure gate criteria do not rely on removed paths.

4) Patch minimal docs
- Update only affected runbook lines.
- Keep historical notes only when explicitly marked as historical.

5) Verify
- `git diff -- docs/runbooks`
- Optional targeted tests for changed runtime branch.

## Guardrails
- Do not invent new rollout policy without matching spec/plan.
- Prefer minimal, surgical edits over broad rewrites.
- Keep fail-safe semantics explicit (`NO_ACTION`, skip behavior, reason codes).

## Output / DoD
- No stale runbook instructions that contradict runtime behavior.
- Expected log examples in runbooks match current code paths.
