# Execution Loop Rollout v1 (Spec 018)

Runbook for safe enablement and 24h SHADOW validation of the execution loop (`PAPER -> SHADOW -> LIVE`).

## 1) Pre-flight

```bash
cd ~/projects/defi_agents
git pull
.venv/bin/python -m json.tool docs/memory-bank/scout_config.json >/dev/null && echo "config: OK"
```

Confirm execution block:

```bash
rg -n '"execution"|\"mode\"|\"enabled\"|\"allow_live_mode\"|\"kill_switch\"' docs/memory-bank/scout_config.json
```

Required safe defaults before SHADOW:
- `execution.enabled=true`
- `execution.mode="SHADOW"`
- `execution.allow_live_mode=false`
- `execution.policy.kill_switch=false`
- optional deterministic dry inputs: `execution.mock_positions`

## 2) Reload and start scheduler

```bash
systemctl --user daemon-reload
systemctl --user enable --now defi-sentinel.timer
systemctl --user is-enabled defi-sentinel.timer
systemctl --user is-active defi-sentinel.timer
systemctl --user list-timers --all | rg 'defi-sentinel'
```

## 3) Smoke check (single cycle)

```bash
journalctl --user -u defi-sentinel.service --since "20 minutes ago" --no-pager | \
rg -E "Starting Global Scout Cycle|Tick density scan|Execution summary|Freshness summary|Traceback|ERROR|CRITICAL"
```

If you prefer `grep`, note the log line is capitalized (`Tick density ...`), so use `-i`:

```bash
journalctl --user -u defi-sentinel.service --since "24 hours ago" --no-pager | grep -i "tick density"
```

Expected:
- `Execution summary: mode=SHADOW ...`
- `exec_ok=0` (by design in SHADOW)
- reason maps present: `policy_blocks={...}`, `sim_fail_reasons={...}`, `exec_fail_reasons={...}`
- no `Traceback|CRITICAL`

## 3.1) v3utils SHADOW smoke (optional)

Local one-shot smoke to validate structured `v3utils_*_params` flow end-to-end (no on-chain send):

```bash
cd ~/projects/defi_agents
.venv/bin/python scripts/v3utils_shadow_smoke.py
```

Expected:
- `mode=SHADOW`
- `tx_plans >= 2`
- `sim_ok == tx_plans`
- `sim_fail == 0`

## 4) 24h Gate-2 validation

Quick counters:

```bash
echo "runs=$(journalctl --user -u defi-sentinel.service --since '24 hours ago' --no-pager | rg -c 'Starting Global Scout Cycle')"
echo "execution_summaries=$(journalctl --user -u defi-sentinel.service --since '24 hours ago' --no-pager | rg -c 'Execution summary:')"
echo "errors=$(journalctl --user -u defi-sentinel.service --since '24 hours ago' --no-pager | rg -c 'Traceback|CRITICAL')"
```

Aggregate execution counters:

```bash
journalctl --user -u defi-sentinel.service --since "24 hours ago" --no-pager | \
rg "Execution summary:" > /tmp/execution_summary.log

awk '
{
  if (match($0, /sim_ok=([0-9]+)/, a)) sim_ok += a[1];
  if (match($0, /sim_fail=([0-9]+)/, b)) sim_fail += b[1];
  if (match($0, /blocked_by_policy=([0-9]+)/, c)) blocked += c[1];
  if (match($0, /exec_fail=([0-9]+)/, d)) exec_fail += d[1];
  cycles += 1;
}
END {
  printf("execution_cycles=%d sim_ok=%d sim_fail=%d blocked_by_policy=%d exec_fail=%d\n", cycles, sim_ok, sim_fail, blocked, exec_fail);
}
' /tmp/execution_summary.log
```

Gate criteria:
- `errors=0`
- `execution_summaries >= 1` and aligns with `runs`
- `exec_fail=0` in SHADOW
- no crash loops; cycle duration stays within expected operational window

## 5) Rollback

Disable execution loop (recommended emergency rollback):

1. set `execution.enabled=false` in `docs/memory-bank/scout_config.json`
2. reload and restart:

```bash
systemctl --user daemon-reload
systemctl --user restart defi-sentinel.service
```

Optional full scheduler stop:

```bash
systemctl --user disable --now defi-sentinel.timer
```

## 6) LIVE preconditions (do not skip)

- explicit operator approval
- `allow_live_mode=true` only for canary window
- kill-switch drill done (`kill_switch=true` blocks all tx immediately)
- strict caps validated (`max_daily_txs`, `max_daily_gas_usd`, `max_slippage_bps`)
- post-canary revert to SHADOW or PAPER if anomaly observed

## 7) Phase H canary profile (recommended)

Before enabling `LIVE`, set a strict canary profile in `docs/memory-bank/scout_config.json`:

- `execution.mode="LIVE"`
- `execution.allow_live_mode=true`
- `execution.primary_adapter="native_uniswap_v3_live"`
- `execution.fallback_adapter="native_uniswap_v3"`
- `execution.policy.max_daily_txs=1`
- `execution.policy.max_daily_gas_usd=5.0`
- `execution.policy.max_gas_usd_per_tx=5.0`
- `execution.policy.max_slippage_bps=50`
- keep Krystal optional/discovery-only until official execution endpoints exist

Required env for native LIVE adapter:

- `BASE_RPC_URL` (and/or other chains from `execution.native_live_rpc_env_by_chain`)
- signed raw transaction payload in `TxPlan.metadata.signed_raw_tx` (or `raw_tx_hex`)

Validation commands before first canary cycle:

```bash
.venv/bin/python -m json.tool docs/memory-bank/scout_config.json >/dev/null && echo "config: OK"
python - <<'PY'
import os
for key in ("BASE_RPC_URL", "ARBITRUM_RPC_URL", "ETH_RPC_URL"):
    print(f"{key}={'set' if os.getenv(key) else 'missing'}")
PY
systemctl --user daemon-reload
systemctl --user restart defi-sentinel.service
sleep 10
journalctl --user -u defi-sentinel.service -n 120 --no-pager | \
rg -E "Execution summary|Policy|kill_switch|LIVE_EXECUTION_ADAPTER_UNAVAILABLE|TX_RECEIPT_TIMEOUT|Traceback|CRITICAL"
```

Expected in first canary:
- no `Traceback|CRITICAL`
- policy counters/logs are present
- if signing payload is missing, explicit safe failure reason is logged (`SIGNED_RAW_TX_MISSING`)
- if no live-capable adapter is configured/available, runtime fails fast with `LIVE_EXECUTION_ADAPTER_UNAVAILABLE` (fail-closed guard)

Krystal note (current):
- `cloud-api.krystal.app` supports pool/position data; `/v1/execution/*` currently returns `404`.
- Runtime maps this to `KRYSTAL_EXECUTION_API_UNAVAILABLE`; treat Krystal as discovery-only until official execution endpoints are available.

Quick probe command (machine-readable):

```bash
make krystal-probe
```

Exit codes:
- `0` = auth works and execution API routes are available
- `1` = auth/key/base-url issue
- `2` = auth works, but execution routes are unavailable (discovery-only mode)

## 8) Post-canary rollback

After canary window, return to SHADOW baseline:

```bash
# set in config:
# execution.mode="SHADOW"
# execution.allow_live_mode=false
systemctl --user daemon-reload
systemctl --user restart defi-sentinel.service
```
