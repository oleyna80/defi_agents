# Roo Task: Protocol Inspector v1 (Docs-Only, No Production Code Yet)

Status: READY
Owner: Roo (Implementation Agent)
Ref Spec: `docs/specs/014-protocol-inspector-v1.md`
Ref Plan: `docs/plans/014-protocol-inspector-v1-plan.md`

## Objective

Prepare an implementation-ready package for `Protocol Inspector v1` without changing production code yet.

Deliverables:
- confirm/clarify the 6-point inspection checklist as a stable SSOT list
- propose `Dossier v0` JSON schema (final field names/types)
- propose bounded budgets (RPC/http/explorer) defaults for v1
- propose Telegram message format (compact, decision-grade)

## Constraints

- No production code changes in this task.
- No secrets in docs.
- Risk-first semantics: missing data must be explicit (`PARTIAL`), no "PASS by absence".

## Inputs (Read These First)

- `docs/memory-bank/productContext.md`
- `docs/memory-bank/activeContext.md`
- `docs/memory-bank/progress.md`
- `docs/specs/014-protocol-inspector-v1.md`
- `docs/plans/014-protocol-inspector-v1-plan.md`

## Output Files

Create or update only documentation:
- [M] `docs/specs/014-protocol-inspector-v1.md` (fill missing details)
- [M] `docs/plans/014-protocol-inspector-v1-plan.md` (make checklist executable)
- [M] `docs/runbooks/protocol_inspector_v1_ops.md` (add concrete commands + DoD)

## Checklist (DoD)

- The spec contains an explicit, numbered checklist of inspection checks (6 items max, stable wording).
- The plan contains an implementable `Dossier v0` schema section and "budgets" section with defaults.
- The ops runbook contains safe rollout steps and minimal debug grep patterns.
- Memory Bank is not updated in this task (docs-only; we'll update after approval/implementation).

