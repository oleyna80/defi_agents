---
name: agent-skill-bridge-defi
description: Bridge-скилл для Roo: как переиспользовать доменные навыки из .agent/skills (CLMM range, LP scoring, degradation policy) без дублирования и дрейфа.
---

# Agent Skill Bridge DeFi

## When to use
- Когда Roo выполняет DeFi-задачу и нужно использовать существующие доменные правила из `.agent/skills`.
- Когда есть риск дублирования логики между `.roo/skills` и `.agent/skills`.

## When NOT to use
- Для чисто инфраструктурных/операционных задач.
- Когда задача полностью покрыта существующим `.roo/skills/*` без доменных пробелов.

## Goal
Снизить дрейф между двумя наборами инструкций:
- `.roo/skills` (оркестрация и execution discipline),
- `.agent/skills` (доменная DeFi-логика).

## Bridge map (default)
- Range logic: `.agent/skills/clmm-range-ops/SKILL.md`
- LP scoring logic: `.agent/skills/lp-opportunity-scoring/SKILL.md`
- Degradation contract: `.agent/skills/defi-degradation-policy/SKILL.md`

## Workflow
1. Detect overlap
   - Определи, какие части текущей Roo-задачи пересекаются с доменными `.agent/skills`.
2. Load minimal domain context
   - Прочитай только релевантные `.agent/skills/*/SKILL.md` (без лишних файлов).
3. Apply bridge rules
   - В реализации следуй доменным guardrails из `.agent/skills`.
   - В `.roo/skills` оставляй только orchestration/process-правила.
4. Prevent duplication
   - Не копируй формулы/политики целиком в новый Roo-скилл, если они уже описаны в `.agent/skills`.
   - Вместо копирования добавляй ссылку на источник истины.
5. Validate consistency
   - Проверь, что новые/изменённые Roo-скиллы не противоречат `.agent/skills`.

## Consistency checks
- Нет конфликтов в fail-safe правилах.
- Нет двух разных определений одной метрики/формулы.
- В отчёте указаны источники доменных правил (пути в `.agent/skills`).

## Guardrails
- `.agent/skills` считать domain SSOT, `.roo/skills` — execution SSOT.
- Не изменять `.agent/skills` без явной необходимости и согласования.
- Не расширять scope задачи под видом bridge-интеграции.

## Output / DoD
- Для каждой выполненной DeFi-задачи явно указано, какие `.agent/skills` были использованы.
- Дублирование доменных правил в `.roo/skills` минимизировано.

