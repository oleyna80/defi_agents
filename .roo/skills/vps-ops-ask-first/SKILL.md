---
name: vps-ops-ask-first
description: Никаких команд без подтверждения. Планируй безопасные шаги.
Проверяй systemd, логи, env права, rollback.
Секреты не печатай.
---

# Vps Ops Ask First

## Instructions

Цель: безопасные ops-действия на VPS без “сломать рабочий пайплайн”, с режимом ask-first для команд/изменений.

### Rules (Ask-First)
- Не запускать команды, не менять файлы и не перезапускать сервисы без явного подтверждения пользователя (“GO”).
- Любая команда должна быть объяснена: зачем, какой риск, как откатить.

### Workflow (Recommended)
1) Сбор фактов (read-only)\n
   - systemd: `systemctl --user status`, timers, unit files\n
   - логи: `journalctl --user -u <service> -n 200`\n
   - repo: `git status -sb`, `git log -n 5`\n
   - env: проверка наличия ключей через `grep -q '^KEY=.' .env` (не печатать значения)\n
2) Риск‑оценка\n
   - double-run риск (системный vs user mode)\n
   - fail-fast поведение (exit code != 0 при ошибках)\n
   - rate limits/таймауты/ретраи\n
3) Предложение Runbook‑шага\n
   - одна операция за раз\n
   - команда(ы)\n
   - проверка успеха\n
   - rollback\n
4) Исполнение (только после GO)\n
5) Верификация\n
   - статус unit + последние логи\n
   - smoke-run\n

### Guardrails
- Никогда не выводи секреты (`TELEGRAM_BOT_TOKEN`, API keys). Не делай `cat .env`.\n
- Не используй разрушительные команды (`rm -rf`, `git reset --hard`) без явного запроса.\n
- Не изменяй scheduler/units без проверки overlap и smoke-test.\n

### Output / DoD
- Чёткий runbook: команды + проверки + rollback.\n
- После выполнения: краткий статус “что сделано / как проверить / что дальше”.
