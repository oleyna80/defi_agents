# Hedger Shadow Rollout v1 (Plan 020)

Runbook for 24h `PAPER/SHADOW` gate of isolated hedger worker (`defi-hedger.service`).

## 1) Pre-flight

```bash
cd ~/projects/defi_agents
.venv/bin/python -m json.tool docs/memory-bank/scout_config.json >/dev/null && echo "config: OK"
rg -n '"hedger"|\"enabled\"|\"mode\"|\"connector\"|\"kill_switch\"|\"mock_exposures\"' docs/memory-bank/scout_config.json
```

Required for SHADOW gate:
- `hedger.enabled=true`
- `hedger.mode="SHADOW"`
- `hedger.allow_live_mode=false`
- `hedger.connector="hummingbot"` (or `none` for explicit unconfigured-failure test)
- `hedger.mock_exposures` populated

## 2) Enable user timer

```bash
mkdir -p ~/.config/systemd/user
cp deploy/systemd/hummingbot-shadow-mock.service ~/.config/systemd/user/
cp deploy/systemd/defi-hedger.service ~/.config/systemd/user/
cp deploy/systemd/defi-hedger.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now hummingbot-shadow-mock.service
systemctl --user enable --now defi-hedger.timer
systemctl --user is-active hummingbot-shadow-mock.service
systemctl --user is-active defi-hedger.timer
```

If real Hummingbot API is available, skip mock service and point:
- `hedger.hummingbot_base_url` -> real endpoint
- `hedger.hummingbot_api_key_env` -> valid key env var

## 3) Smoke check

```bash
journalctl --user -u defi-hedger.service --since "30 minutes ago" --no-pager | \
rg -E "Hedger summary:|Hedger reasons:|FATAL|Traceback|CRITICAL"
```

Expected:
- `Hedger summary: mode=SHADOW ...`
- no `FATAL|Traceback|CRITICAL`

## 4) 24h Gate report

```bash
UNIT=defi-hedger.service ./scripts/hedger_shadow_gate_report.sh "24 hours ago"
```

Gate focus:
- `cycles >= 1`
- `sim_ok + sim_fail > 0` for hedge intents
- `connector_errors` explainable by reason taxonomy (no crash loops)
- no uncaught runtime failures

## 5) Rollback

```bash
systemctl --user disable --now defi-hedger.timer
```

Or keep timer and disable by config:
- set `hedger.enabled=false`
- restart service:

```bash
systemctl --user restart defi-hedger.service
```
