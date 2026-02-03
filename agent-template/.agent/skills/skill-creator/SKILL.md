---
name: Skill Creator
description: A meta-skill for creating and maintaining other skills.
---

# Skill Creator

This skill helps you create new skills that follow the standard structure.

## Anatomy of a Skill
A skill is a directory containing:
1. `SKILL.md` (required)
2. `scripts/` (optional)
3. `references/` (optional)

## Creating a New Skill
1. Create a directory: `.agent/skills/<skill-name>/`
2. Create `SKILL.md` with frontmatter:
   ```yaml
   ---
   name: Your Skill Name
   description: Brief description.
   ---
   ```
3. Add clear instructions and examples.
4. Optionally add `scripts/` and `references/`.

## Best Practices
- Keep descriptions concise and specific.
- Use section headers and checklists.
- Prefer simple, executable steps.
