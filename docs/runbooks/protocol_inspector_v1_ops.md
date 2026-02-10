# Protocol Inspector v1: Operational Runbook

Status: DRAFT
Version: 1.0
Context: Onchain due diligence automation (non-trading, risk-first)

## 1. Rollout Plan (Safe Activation)

Goal: enable inspector without breaking Scout cycles and without spamming Telegram.

Step 0: Pre-flight
- confirm `inspector.enabled` is `false` by default
- confirm secrets are only in `.env` (never in JSON)

Step 1: Silent activation (watchlist only)
- set `inspector.enabled=true`
- set targets to 1-2 protocols (seed addresses recommended)
- run inspector manually (oneshot) and review logs

Step 2: Schedule activation
- enable systemd user timer for inspector job (separate unit from Scout)
- validate 3+ runs without traceback

Step 3: Diff alerts
- simulate a diff using local fixtures (unit test), then validate real diff alert in Telegram

## 2. Debug Checklist

Logs:
- `journalctl --user -u defi-inspector.service --since "2 hours ago" --no-pager`

Key signals to look for:
- resolver result: `contract_set_status=OK|PARTIAL`
- missing fields list
- proxy detection output
- diff alert emitted / suppressed

## 3. DoD (v1)

- 3+ runs without critical errors
- reports show explicit PARTIAL when missing data
- no secrets in logs or Telegram output
- diff alert triggers on high-impact changes

