---
description: Strict Spec-Driven Development (SDD) Protocol
---
# SDD Protocol Workflow

This workflow implements a strict Spec-Driven Development cycle. No code is generated without an approved specification and plan.

Prerequisites:
- Ensure `docs/memory-bank/` exists and is initialized.
- Ensure `docs/specs/` exists.

## Phase 1: Specification (The What)
1. Analyze the request and clarify intent.
2. Read Memory Bank: `productContext.md` and `activeContext.md`.
3. Draft a spec in `docs/specs/XXX-feature-name.md` using `docs/sdd_templates/SPEC_TEMPLATE.md`.
4. Ask the user to review and approve the spec.

## Phase 2: Planning (The How)
1. Read the approved spec.
2. Draft a plan in `docs/plans/XXX-feature-name-plan.md` using `docs/sdd_templates/PLAN_TEMPLATE.md`.
3. Update Memory Bank (Current Spec/Plan).
4. Ask the user to approve the plan.

## Phase 3: Task Slicing (The When)
1. Create a checklist of atomic tasks.
2. Update `docs/memory-bank/progress.md` with feature status.

## Phase 4: Execution (The Code)
1. Select the next unchecked task.
2. Implement strictly according to the spec and plan.
3. Run tests/verification steps.
4. Mark tasks done and update Memory Bank.

## Phase 5: Closure
1. Final verification.
2. Update Memory Bank with completed feature and new capabilities.
3. Handover to the user.
