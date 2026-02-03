---
name: telegram-alerting
description: Implement Telegram notifications (message formats, dedupe, throttling) for portfolio risks and daily summaries.
---

# Telegram Alerting

## Goal
Send low-noise, actionable alerts and summaries to Telegram.

## Workflow
1. Define severity levels: info/warn/critical.
2. Define message templates:
   - header (project + wallet short id)
   - bullet list of findings
   - suggested action
3. Implement dedupe:
   - stable alert ids (based on finding type + position id)
   - throttle window to prevent spam
4. Keep secrets in env vars; never commit bot token.

## Outputs
- Telegram send function + formatting helpers
- Dedupe state strategy (file or simple store; explicit)
