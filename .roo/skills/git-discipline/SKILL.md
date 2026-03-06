---
name: git-discipline
description: Git-гигиена для агентов: branching, commit convention, запрет destructive ops, ask-first перед push.
---

# Git Discipline

## When to use
- Перед началом любой задачи с изменением кода.
- Перед commit/push.
- При merge/rebase/cleanup.

## Rules (HARD)

### Branching
- Работай в feature-ветке: `feat/<short-name>`, `fix/<short-name>`, `chore/<short-name>`.
- Никогда не коммить напрямую в `main` без явного разрешения пользователя.
- Перед началом: `git status -sb` — убедись, что дерево чистое.

### Commits
- Формат: `<type>(<scope>): <short description>`
  - `type`: feat, fix, refactor, test, docs, chore
  - `scope`: модуль (lp, execution, freshness, scout, hedger, inspector, notifier)
  - Пример: `feat(lp): add stability gate for entry recommendations`
- Один commit = один логический change.
- Не коммитить `.env`, секреты, кеш-файлы.

### Prohibited operations (без явного запроса)
- `git reset --hard`
- `git push --force`
- `git rebase` на shared ветках
- `git clean -fd`
- Удаление веток без подтверждения

### Before push
1. `git diff --stat` — проверь scope изменений.
2. `make test` — все тесты зелёные.
3. Спроси пользователя: "Готово к push? Вот summary: ..."

## Workflow
1. `git status -sb` — состояние.
2. `git checkout -b <branch>` — создай ветку (если не существует).
3. Работай.
4. `git add <specific files>` — только нужные файлы, не `git add .`.
5. `git commit -m "<conventional message>"`.
6. Спроси пользователя перед push.

## Guardrails
- `git add .` запрещён (используй точечное добавление).
- Не включай в commit файлы вне scope задачи.
- При конфликтах — не резолви автоматически, покажи пользователю.
