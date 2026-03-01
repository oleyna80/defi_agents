#!/usr/bin/env bash
set -euo pipefail

UNIT="${UNIT:-defi-hedger.service}"
WINDOW="${1:-24 hours ago}"

TMP_SUMMARY="$(mktemp)"
TMP_REASONS="$(mktemp)"
trap 'rm -f "$TMP_SUMMARY" "$TMP_REASONS"' EXIT

journalctl --user -u "$UNIT" --since "$WINDOW" --no-pager | rg "Hedger summary:" > "$TMP_SUMMARY" || true
journalctl --user -u "$UNIT" --since "$WINDOW" --no-pager | rg "Hedger reasons:" > "$TMP_REASONS" || true

echo "window=$WINDOW unit=$UNIT"

if [ ! -s "$TMP_SUMMARY" ]; then
  echo "cycles=0 exposures=0 intents_hedge=0 intents_hold=0 intents_skip=0 sim_ok=0 sim_fail=0 connector_errors=0"
  echo "rates: sim_ok_pct=0.0 connector_error_pct=0.0"
  exit 0
fi

awk '
{
  if (match($0, /exposures=([0-9]+)/, a)) exposures += a[1];
  if (match($0, /intents_hedge=([0-9]+)/, b)) hedge += b[1];
  if (match($0, /intents_hold=([0-9]+)/, c)) hold += c[1];
  if (match($0, /intents_skip=([0-9]+)/, d)) skip += d[1];
  if (match($0, /sim_ok=([0-9]+)/, e)) sim_ok += e[1];
  if (match($0, /sim_fail=([0-9]+)/, f)) sim_fail += f[1];
  if (match($0, /connector_errors=([0-9]+)/, g)) connector_errors += g[1];
  cycles += 1;
}
END {
  printf("cycles=%d exposures=%d intents_hedge=%d intents_hold=%d intents_skip=%d sim_ok=%d sim_fail=%d connector_errors=%d\n",
    cycles, exposures, hedge, hold, skip, sim_ok, sim_fail, connector_errors);
  attempts = sim_ok + sim_fail;
  printf("rates: sim_ok_pct=%.1f connector_error_pct=%.1f\n",
    (attempts ? (100.0 * sim_ok / attempts) : 0.0),
    (attempts ? (100.0 * connector_errors / attempts) : 0.0));
}' "$TMP_SUMMARY"

if [ -s "$TMP_REASONS" ]; then
  echo "latest_reasons:"
  tail -n 1 "$TMP_REASONS" | sed 's/.*Hedger reasons: /  /'
fi

