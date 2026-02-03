# Agent Configuration Structure

## 1. Rules (`.agent/rules/`)
Mandatory instructions applied to every request.
Use this for SDD enforcement, memory bank rules, and safety constraints.

## 2. Roles (`.agent/roles/`)
Personas and responsibilities. Open the role file before doing that job.

## 3. Skills (`.agent/skills/`)
Reusable procedures for common tasks. Skills can include scripts or references.

## 4. Workflows (`.agent/workflows/`)
Multi-step processes (spec -> plan -> code, research, bootstrap, etc.).

## 5. Reports (`.agent/reports/`)
Optional output templates for structured handoffs.
