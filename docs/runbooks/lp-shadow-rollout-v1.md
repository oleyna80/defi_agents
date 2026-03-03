# LP Shadow Rollout v1

Runbook for enabling and validating Phase 0.5 SHADOW mode on VPS.

## 1) Pre-flight

```bash
cd ~/projects/defi_agents
git pull
.venv/bin/python -m json.tool docs/memory-bank/scout_config.json >/dev/null && echo "config: OK"
```

## 2) Enable SHADOW mode in config

Set in `docs/memory-bank/scout_config.json`:

- `scout_settings.reporting.telegram_shadow_mode_enabled=true`
- `scout_settings.reporting.telegram_shadow_chat_id_env="TELEGRAM_SHADOW_CHAT_ID"`
- keep digest cadence (example): `telegram_digest_interval_seconds=21600`

Optional shadow telemetry defaults:

- `telegram_shadow_metrics_horizon_seconds=86400`
- `telegram_shadow_capture_interval_seconds=21600`
- `telegram_shadow_retention_seconds=1209600`

Optional `/recheck` command (proxy mode):

- `telegram_recheck_enabled=true`
- `telegram_recheck_poll_limit=20`
- `telegram_recheck_command="/recheck"`
- `telegram_recheck_change_threshold_pct=20.0`

## 3) Set SHADOW Telegram target (no secrets in JSON)

In user service env file (or shell profile for manual runs), set:

```bash
export TELEGRAM_SHADOW_CHAT_ID="<your_shadow_channel_chat_id>"
```

If using systemd user service with `EnvironmentFile`, put it there and restart daemon:

```bash
systemctl --user daemon-reload
```

## 4) Restart and smoke-check

```bash
systemctl --user restart defi-sentinel.service
sleep 10
journalctl --user -u defi-sentinel.service -n 120 --no-pager | \
grep -E "Shadow mode enabled|Shadow metrics:|Reported|Report suppressed|Traceback|ERROR|CRITICAL"
```

Expected:

- `Shadow mode enabled: chat_id_env=TELEGRAM_SHADOW_CHAT_ID ...`
- `Shadow metrics: captured=... evaluated=... pending=...`
- Telegram messages in SHADOW channel with prefix `⚠️ SHADOW — DO NOT ACT`

## 5) 24h validation snapshot

```bash
journalctl --user -u defi-sentinel.service --since "24 hours ago" --no-pager | \
grep -E "Shadow metrics:|Reported|Report suppressed|Traceback|ERROR|CRITICAL"

echo "runs=$(journalctl --user -u defi-sentinel.service --since '24 hours ago' --no-pager | grep -c 'Starting Global Scout Cycle')"
echo "shadow_metrics=$(journalctl --user -u defi-sentinel.service --since '24 hours ago' --no-pager | grep -c 'Shadow metrics:')"
echo "errors=$(journalctl --user -u defi-sentinel.service --since '24 hours ago' --no-pager | grep -c -E 'Traceback|ERROR|CRITICAL')"
```

Gate:

- `errors=0`
- `shadow_metrics` appears on every (or near every) cycle with picks
- SHADOW channel receives digest at configured interval

## 5.1) Gate-3 evidence linkage (reader-only path)

For Gate-3 Evidence Pack use this runbook together with:

- `docs/runbooks/shadow-gate-real-positions-v1.md`
- `docs/reports/gate3-evidence-YYYY-MM-DD.md`

Current Gate-3 evidence expectations:

- at least 3 real reader-backed positions with `pnl_vs_hodl` fields recorded;
- SHADOW stability evidence for the current N-cycle threshold from runbook/roadmap
  (`reader_ok >= 90` in the 48h gate window);
- no fail-open behavior (reader unavailability must remain explicit reason-coded skip path,
  not silent mock fallback).

Do not mark Gate-3 as PASS when these evidence conditions are not met.

## 5.2 `/recheck` smoke (optional, proxy mode)

In Telegram SHADOW chat send:

```text
/recheck <defillama_pool_id>
```

Expected response:

- `✅ CONFIRMED` when proxy delta is within threshold
- `❌ ABORT` when proxy delta exceeds threshold
- `⚪ NEED_BASELINE` when shadow baseline is not yet available

Note: current command uses shadow proxy (`Net@1k` delta), not on-chain band-depth diff yet.

## 6) Rollback

Set `telegram_shadow_mode_enabled=false` and restart service:

```bash
systemctl --user restart defi-sentinel.service
```
