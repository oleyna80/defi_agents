# Agent Manifest

This project uses a small, reusable set of agent roles, skills, and workflows.
All agents must follow `.agent/rules/` and the Memory Bank protocol.

## Memory Bank (mandatory)
Read before any work:
- `docs/memory-bank/productContext.md`
- `docs/memory-bank/activeContext.md`
- `docs/memory-bank/progress.md`

Update after significant work:
- `docs/memory-bank/activeContext.md`
- `docs/memory-bank/progress.md`
- `docs/memory-bank/systemPatterns.md` (only when new decisions/patterns appear)

## Core Roles
- Tech Lead: `.agent/roles/tech-lead.md`
- Architect: `.agent/roles/architect.md`
- Coder: `.agent/roles/coder.md`
- Codebase Researcher: `.agent/roles/codebase-researcher.md`
- Advisor/Reviewer: `.agent/roles/advisor.md`

## Core Skills
- Skill Creator: `.agent/skills/skill-creator/SKILL.md`
- Memory Bank Manager: `.agent/skills/memory-bank-manager.md`
- Example Skill: `.agent/skills/example_skill/SKILL.md`

## Core Workflows
- Project Bootstrap: `.agent/workflows/project-bootstrap.md`
- SDD Protocol: `.agent/workflows/sdd-protocol.md`
- Codebase Research: `.agent/workflows/codebase_research.md`
- Troubleshooting: `.agent/workflows/troubleshooting.md`

## How to invoke
- "Use role tech-lead" or "Open `.agent/roles/tech-lead.md` and follow it."
- "Use skill memory-bank-manager" or "Open `.agent/skills/memory-bank-manager.md`."
- "Run workflow project-bootstrap" or "Follow `.agent/workflows/project-bootstrap.md`."
