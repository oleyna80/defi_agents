# Specification: Scout My Pools Monitor v1

Status: DRAFT
Owner: Tech Lead / Architect
Related Memory: `docs/memory-bank/activeContext.md`
Date: 2026-02-13

## 1. Context & Business Value

Scout currently optimizes for market-wide discovery (find best external pools).
For LP operators who create/manage their own pools, the main need is different:
- monitor operational health of a fixed pool set,
- detect when pool economics degrade,
- compare own pools against market baselines,
- receive actionable rebalance/add-remove-liquidity signals.

`My Pools Monitor` adds an operator mode to Scout so it can track decision-grade metrics for explicitly configured pools.

## 2. Scope (v1)

In scope:
- Watchlist-based monitoring of operator pools (`pool_id` and/or `(chain, address)`).
- Pull metrics from DeFiLlama provider surfaces (with optional project-source overlay later).
- Compute pool health signals:
  - `tvl_usd`
  - `volume_24h_usd`
  - `vol_to_tvl_24h` (`volume_24h_usd / tvl_usd`)
  - `apy`, `apy_base`, `apy_reward`
  - `apy_vs_mean_30d_pct` (when `apyMean30d` available)
  - `source_confidence` / freshness tags (existing pipeline)
- Dedicated Telegram section blocks:
  - `My Pools — Health`
  - `My Pools — Alerts`
  - `My Pools — Market Gap` (optional in v1, config-flagged)

Out of scope:
- Auto-rebalancing or auto-execution.
- Position management transactions.
- New risk engine replacing existing Security/Freshness/Inspector modules.

## 3. Functional Requirements

- REQ-001: Add config block `my_pools_monitor` with:
  - `enabled`
  - `pools[]` (ids/addresses + labels)
  - thresholds (`min_tvl_usd`, `min_vol_to_tvl_24h`, `apy_drop_pct_24h`, etc.)
  - section toggles (`show_health`, `show_alerts`, `show_market_gap`)
- REQ-002: Resolve each watchlisted pool to a normalized candidate/fact every cycle.
- REQ-003: For each pool, compute deterministic status tags:
  - `HEALTHY`
  - `WATCH_VOLUME`
  - `WATCH_APY_DRIFT`
  - `WATCH_TVL_DRAIN`
  - `DATA_UNVERIFIED`
- REQ-004: Alerts are non-fatal and fail-safe:
  - missing pool data must not crash cycle,
  - unresolved pools appear in report as `DATA_UNVERIFIED`.
- REQ-005: Telegram digest includes a dedicated block for monitored pools and never mixes it into market Top-10 lists.
- REQ-006: Existing market-wide Scout output remains backward-compatible when monitor mode is disabled.

## 4. Data Contract (v1)

`MonitoredPoolSnapshot`:
- `pool_ref` (id/address), `label`
- `chain`, `project`, `symbol`
- `tvl_usd`, `volume_24h_usd`, `vol_to_tvl_24h`
- `apy`, `apy_base`, `apy_reward`, `apy_mean_30d`, `apy_vs_mean_30d_pct`
- `freshness_status`, `source_confidence`
- `health_tags[]`, `alert_reasons[]`
- `pool_url`

`MyPoolsMonitorReport`:
- `generated_at`
- `healthy_count`, `watch_count`, `unverified_count`
- `snapshots[]`
- `market_gap[]` (optional)

## 5. Non-Functional Requirements

- Performance: monitor resolution must be O(number of configured pools), with provider cache reuse.
- Reliability: unresolved/missing pools degrade to warning tags only.
- Security: no secret leakage in logs; no raw credentialed URLs in messages.
- Observability: cycle logs expose monitor counters (`configured/resolved/unresolved/watch/healthy`).

## 6. Integration Rules

- Implemented as an extension inside Scout runtime (not a separate systemd service).
- Reuses existing data provider, freshness, confidence, and notifier surfaces.
- Protocol Inspector remains separate and can be referenced as an auxiliary verdict in later iterations.

## 7. Acceptance Criteria

- AC-001: With `my_pools_monitor.enabled=false`, no behavior change in existing digest blocks.
- AC-002: With monitor enabled and valid watchlist, digest includes `My Pools` sections with deterministic ordering.
- AC-003: Pool snapshots show `Vol/TVL`, APY fields, and confidence/freshness status when available.
- AC-004: Missing/unresolved pools do not crash cycle and appear as `DATA_UNVERIFIED`.
- AC-005: Unit tests cover config parsing, snapshot mapping, alert tag logic, and notifier rendering.

## 8. Risks / Open Questions

- Some pools may not have stable `pool_id` mapping across sources; need fallback `(chain,address)` resolution.
- APY drift thresholds should be calibrated against 1d/7d volatility by pool class.
- `Market Gap` baseline policy (compare to similar pools) needs deterministic peer-selection rules in v1.1.
