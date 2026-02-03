---
description: Bootstrap a new project for agent-driven SDD
---
# Project Bootstrap Workflow

## Goal
Initialize a new project so agents can work immediately using SDD and Memory Bank.

## Steps
1. Verify structure exists:
   - `.agent/` with rules, roles, skills, workflows
   - `docs/memory-bank/`, `docs/specs/`, `docs/plans/`, `docs/sdd_templates/`
2. If any are missing, create them from templates.
3. Ask the user for:
   - Project name and goal
   - Tech stack and constraints
   - Primary users and success criteria
4. Fill `docs/memory-bank/productContext.md` with the project details.
5. Initialize `docs/memory-bank/activeContext.md`:
   - Current Spec: None
   - Current Plan: None
   - Active Task: "Project bootstrap"
6. Add a first entry in `docs/memory-bank/progress.md` for initial setup.
7. Ask whether to draft the first spec.

## Output
- List of created/updated files
- Open questions (if any)
- Next recommended action
