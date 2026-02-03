# SYSTEM CRITICAL INSTRUCTION: SDD ENFORCER

You are operating in Strict SDD Mode (Spec-Driven Development).

## 1. The Golden Rule
Do not write production code without an APPROVED specification in `docs/specs/`.

A spec is considered approved when it includes one of these markers:
- `Status: APPROVED`
- `[APPROVED]` in the title
- User explicitly states approval in the conversation AND the spec is updated

## 2. Pre-task Checklist
Before starting any task, you must:
1. Read `docs/memory-bank/activeContext.md`.
2. Check `docs/specs/` for a relevant spec.
   - If no spec exists: stop and draft one using `docs/sdd_templates/SPEC_TEMPLATE.md`.
   - If a spec exists but not approved: stop and ask for approval.
3. If the task is large, create a plan in `docs/plans/` using `docs/sdd_templates/PLAN_TEMPLATE.md`.

## 3. Exceptions
You may bypass SDD only for:
- Exploration/research (read-only).
- Scaffolding the docs/agent structure itself.
- Critical hotfixes (must be documented in Memory Bank).

## 4. Role Integration
- Tech Lead: writes specs and plans.
- Coder: implements approved specs only.
- Advisor: reviews risks and gaps.
