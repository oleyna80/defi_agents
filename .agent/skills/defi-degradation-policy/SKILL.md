---
name: defi-degradation-policy
description: Enforce production-safe degradation rules when market/security/freshness inputs are missing or inconsistent.
---

# DeFi Degradation Policy

## Goal
Keep decisions safe under partial outages or stale sources by applying deterministic downgrade rules.

## Workflow
1. Evaluate data quality dimensions:
   - market data availability
   - freshness re-check status
   - security/inspector availability
2. Map to decision state:
   - `ALLOW` (all critical inputs healthy)
   - `WATCHLIST_ONLY` (partial data, non-critical gaps)
   - `BLOCK` (critical risk or unresolved integrity issue)
3. Attach machine-readable reasons and counters.
4. Ensure Telegram output clearly states degraded mode and why.

## Required Inputs
- Source health + parser outcomes
- Freshness/source confidence status
- Security/Inspector findings

## Outputs
- Deterministic status transition and reason codes
- Rollup counters for ops (`degraded_count`, `blocked_count`, etc.)

## Guardrails
- Never silently promote candidates under degraded conditions.
- Any unknown critical signal must default to conservative mode.
