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

## Project Roles (DeFi Agent)
- Orchestrator: `.agent/roles/orchestrator.md`
- DeFi Strategist: `.agent/roles/defi-strategist.md`
- Adapter Engineer: `.agent/roles/adapter-engineer.md`
- Risk Engineer: `.agent/roles/risk-engineer.md`
- Security Auditor: `.agent/roles/security-auditor.md`
- Notifications/Reporting: `.agent/roles/notifier.md`
- QA Automation: `.agent/roles/qa.md`

## Core Skills
- Skill Creator: `.agent/skills/skill-creator/SKILL.md`
- Memory Bank Manager: `.agent/skills/memory-bank-manager.md`
- Example Skill: `.agent/skills/example_skill/SKILL.md`

## Project Skills (DeFi Agent)
- Debank Adapter: `.agent/skills/debank-adapter/SKILL.md`
- DeFiLlama Discovery: `.agent/skills/defillama-discovery/SKILL.md`
- Security Screening: `.agent/skills/security-screening/SKILL.md`
- Asset Classifier: `.agent/skills/asset-classifier/SKILL.md`
- Risk Checks: `.agent/skills/risk-checks/SKILL.md`
- Portfolio Schema: `.agent/skills/portfolio-schema/SKILL.md`
- Telegram Alerting: `.agent/skills/telegram-alerting/SKILL.md`

## Core Workflows
- Project Bootstrap: `.agent/workflows/project-bootstrap.md`
- SDD Protocol: `.agent/workflows/sdd-protocol.md`
- Codebase Research: `.agent/workflows/codebase_research.md`
- Troubleshooting: `.agent/workflows/troubleshooting.md`

## Roster
See `.agent/ROSTER.md` for a single table of roles/skills and suggested trigger phrases.

## How to invoke
- "Use role tech-lead" or "Open `.agent/roles/tech-lead.md` and follow it."
- "Use skill memory-bank-manager" or "Open `.agent/skills/memory-bank-manager.md`."
- "Run workflow project-bootstrap" or "Follow `.agent/workflows/project-bootstrap.md`."
