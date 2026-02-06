---
name: spec-writer
description: Создай spec по docs/specs/TEMPLATE.md.
Укажи: контекст, требования, out-of-scope, DoD, риски.
Без кода.
---

# Spec Writer

## Instructions

Цель: написать спецификацию в стиле проекта (через `docs/specs/TEMPLATE.md`) так, чтобы её можно было сразу превратить в план и реализацию без двусмысленности.

### Inputs
- Название фичи и “зачем” (бизнес‑ценность).
- Ограничения (risk-first, ops, совместимость).
- Ссылки на related docs/research (если есть).

### Workflow
1) Выбери номер спека\n
   - следующий свободный номер в `docs/specs/`\n
2) Создай spec-файл на базе `docs/specs/TEMPLATE.md`\n
   - заголовок: `# Specification: <Feature Name>`\n
   - `Status: DRAFT`, `Owner`, `Date`\n
3) Заполни разделы:\n
   - Context & Business Value: 3–6 предложений, без “воды”\n
   - User Stories: 2–5 конкретных\n
   - Functional Requirements: REQ-001… с проверяемыми формулировками\n
   - Non‑Functional: таймауты, ретраи, безопасность, совместимость\n
   - Constraints: что нельзя ломать (scheduler, scoring, risk gates)\n
   - Out of Scope: чтобы не раздувать MVP\n
   - Acceptance Criteria: DoD в виде чек‑пунктов\n
   - Risks/Open Questions: что надо уточнить до реализации\n
4) Обнови индекс спека\n
   - добавь файл в `docs/specs/INDEX.md`\n
5) Обнови Memory Bank (кратко)\n
   - `docs/memory-bank/activeContext.md`: Current Spec/Plan/Active Task\n
   - `docs/memory-bank/progress.md`: добавить строку про новый spec\n
6) Не пиши код в этом скилле\n
   - только spec + связи/DoD\n

### Output / DoD
- Spec готов к утверждению (DRAFT), содержит явные требования и критерии приемки.\n
- Индексы/Memory Bank отражают новый spec.
