#!/usr/bin/env bash
set -euo pipefail

UNIT="${UNIT:-defi-sentinel.service}"
WINDOW="${1:-24 hours ago}"

TMP_SUMMARY="$(mktemp)"
TMP_DIV="$(mktemp)"
trap 'rm -f "$TMP_SUMMARY" "$TMP_DIV"' EXIT

journalctl --user -u "$UNIT" --since "$WINDOW" --no-pager | rg "Freshness summary:" > "$TMP_SUMMARY" || true
journalctl --user -u "$UNIT" --since "$WINDOW" --no-pager | rg "Freshness divergence:" > "$TMP_DIV" || true

if [ ! -s "$TMP_SUMMARY" ]; then
  echo "window=$WINDOW freshness_summary_lines=0"
  exit 0
fi

echo "window=$WINDOW unit=$UNIT"

awk '
{
  if (match($0, /rechecked=([0-9]+)/, a)) rechecked += a[1];
  if (match($0, /fresh=([0-9]+)/, b)) fresh += b[1];
  if (match($0, /stale=([0-9]+)/, c)) stale += c[1];
  if (match($0, /unverified=([0-9]+)/, d)) unverified += d[1];
  if (match($0, /diverged=([0-9]+)/, e)) diverged += e[1];
  if (match($0, /morpho_checked=([0-9]+)/, f)) morpho_checked += f[1];
  if (match($0, /morpho_ok=([0-9]+)/, g)) morpho_ok += g[1];
  if (match($0, /morpho_timeout=([0-9]+)/, h)) morpho_timeout += h[1];
  if (match($0, /morpho_error=([0-9]+)/, i)) morpho_error += i[1];
  if (match($0, /morpho_schema_mismatch=([0-9]+)/, j)) morpho_schema_mismatch += j[1];
  if (match($0, /morpho_addr_mismatch=([0-9]+)/, k)) morpho_addr_mismatch += k[1];
  cycles += 1;
}
END {
  printf("cycles=%d rechecked=%d fresh=%d stale=%d unverified=%d diverged=%d\n", cycles, rechecked, fresh, stale, unverified, diverged);
  printf("morpho_checked=%d morpho_ok=%d morpho_timeout=%d morpho_error=%d morpho_schema_mismatch=%d morpho_addr_mismatch=%d\n",
    morpho_checked, morpho_ok, morpho_timeout, morpho_error, morpho_schema_mismatch, morpho_addr_mismatch);
  printf("rates: diverged_pct=%.1f morpho_ok_pct=%.1f\n",
    (rechecked ? (100.0 * diverged / rechecked) : 0.0),
    (morpho_checked ? (100.0 * morpho_ok / morpho_checked) : 0.0));
}' "$TMP_SUMMARY"

if [ -s "$TMP_DIV" ]; then
  awk '
  {
    provider = "";
    apy = "";
    tvl = "";
    if (match($0, /provider=([^ ]+)/, p)) provider = p[1];
    if (match($0, /apy_p90=([^ ]+)/, a)) apy = a[1];
    if (match($0, /tvl_p90=([^ ]+)/, t)) tvl = t[1];
    if (provider != "") {
      apy_last[provider] = apy;
      tvl_last[provider] = tvl;
      seen[provider] = 1;
    }
  }
  END {
    for (provider in seen) {
      printf("latest_p90: provider=%s apy_p90=%s tvl_p90=%s\n", provider, apy_last[provider], tvl_last[provider]);
    }
  }' "$TMP_DIV"
else
  echo "latest_p90: none"
fi

