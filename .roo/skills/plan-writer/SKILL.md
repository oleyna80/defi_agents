---
name: plan-writer
description: Создай plan по docs/plans/ на базе APPROVED spec. Укажи: фазы, файлы, DoD, тесты, rollback. Без кода — только план.
---

# Plan Writer

## When to use
- Когда есть APPROVED spec в `docs/specs/` и нужно перевести его в исполнительный план.
- Когда техлид формулирует задание для RooCode-агента (Coder/Adapter/QA).

## When NOT to use
- Если нет APPROVED spec — сначала используй `spec-writer`.
- Для hotfix / single-file changes (достаточно inline task description).

## Goal
Создать исполнительный план, который Coder-агент может выполнить без дополнительных вопросов:
- фазы с чёткими границами,
- точные целевые файлы,
- команды тестирования,
- критерии завершения.

## Inputs
- Ссылка на APPROVED spec (`docs/specs/XXX-*.md`).
- Контекст из Memory Bank (обязательно `activeContext.md`).
- Ограничения/приоритеты от техлида.

## Workflow
1) Выбери номер плана
   - следующий свободный номер в `docs/plans/`
2) Создай план-файл `docs/plans/XXX-feature-name-plan.md`
   - заголовок: `# Plan: <Feature Name>`
   - ссылка на spec: `Spec: docs/specs/XXX-*.md`
   - `Status: DRAFT`
3) Разбей на фазы (2–5 фаз)
   - Каждая фаза: scope, target files, implementation steps
   - Чёткие зависимости между фазами
4) Для каждой фазы укажи:
   - Целевые файлы (paths)
   - Шаги реализации (numbered)
   - Тестовые команды (`pytest`, `make test`, smoke-check)
   - Done criteria
5) Добавь секции:
   - `Guardrails`: что нельзя ломать
   - `Rollback`: как откатить, если что-то пошло не так
   - `Verification Matrix`: все тесты, которые нужно пройти перед закрытием
6) Обнови Memory Bank
   - `activeContext.md`: Current Spec / Current Plan
   - `progress.md`: строка про новый план

## Output / DoD
- План готов к утверждению техлидом (Status: DRAFT).
- Coder может взять фазу и начать без дополнительных вопросов.
- Тестовая матрица полна и исполняема.
