# Technical Plan: Scout My Pools Monitor v1

Refers to Spec: `docs/specs/016-scout-my-pools-monitor-v1.md`

## 1. Architecture Design

New pieces:
- `ScoutConfig` extension: `my_pools_monitor` block.
- New monitor module:
  - `src/defi_agents/scout/my_pools_monitor.py`
  - resolves watchlist pools via `DeFiLlamaDataProvider` / `DeFiLlamaClient`
  - computes health tags and alert reasons
- Notifier extension:
  - render `My Pools — Health` and `My Pools — Alerts` blocks.

Integration points:
- `main.py`: collect monitor snapshots each cycle and pass into notifier.
- `src/defi_agents/scout/scout.py`: optional helper hooks for pool lookup/reuse of candidate mapping.
- Existing freshness/confidence metadata reused (no parallel policy path).

## 2. Delivery Phases

### Phase A — Config + Model Contracts
- Add `my_pools_monitor` config schema and defaults in `docs/memory-bank/scout_config.json`.
- Add typed report models (`MonitoredPoolSnapshot`, `MyPoolsMonitorReport`).

DoD:
- Config validates with monitor OFF by default.
- No runtime behavior change with default config.

### Phase B — Pool Resolution Layer
- Implement resolver for watchlisted pools:
  - by `pool_id`,
  - fallback by `(chain,address)` when `pool_id` absent.
- Reuse provider cache and fail-safe semantics.

DoD:
- Resolved pools return normalized snapshot facts.
- Unresolved pools are tracked as `DATA_UNVERIFIED` (non-fatal).

### Phase C — Health/Alert Signal Engine
- Implement deterministic rule set:
  - low turnover (`Vol/TVL` below threshold),
  - APY drift vs 30d mean,
  - TVL drain (if previous snapshot present),
  - freshness/confidence downgrade passthrough.
- Add cycle counters (`configured/resolved/unresolved/watch/healthy`).

DoD:
- Health tags stable across runs for same inputs.
- No silent drops: every configured pool appears in output.

### Phase D — Telegram Sections + Digest Wiring
- Add dedicated report sections:
  - `My Pools — Health`
  - `My Pools — Alerts`
- Keep strict separation from market Top-10 directional sections.

DoD:
- Sections are deterministic and chunk-safe.
- Digest cadence remains unchanged (`6h`).

### Phase E — Validation + Rollout
- Add tests:
  - config parsing,
  - monitor snapshot/alerts,
  - notifier rendering.
- Run shadow rollout with monitor enabled and 3-5 real pools.

DoD:
- Full test suite green.
- 24h shadow logs: no cycle failures, stable monitor counters.

## 3. Config Changes

Add `scout_settings.my_pools_monitor`:
- `enabled: false`
- `pools: []`
- `min_tvl_usd`
- `min_vol_to_tvl_24h`
- `max_apy_drop_pct_24h`
- `show_health`, `show_alerts`, `show_market_gap`

Guardrails:
- Monitor mode must never widen security bypasses.
- Missing fields only downgrade confidence/status; no hard crash.

## 4. Testing Strategy

Unit tests:
- `tests/test_my_pools_monitor.py` (new)
- updates in `tests/test_notifier.py` and `tests/test_scout.py`

Verification commands:
- `.venv/bin/python -m json.tool docs/memory-bank/scout_config.json >/dev/null`
- `.venv/bin/pytest -q tests/test_my_pools_monitor.py tests/test_notifier.py tests/test_scout.py`
- `.venv/bin/pytest -q`

## 5. Rollout Strategy

1) Land with monitor OFF by default.
2) Enable on VPS with 3-5 pools and telemetry-only interpretation for 24h.
3) Calibrate thresholds for turnover/APY drift.
4) Expand watchlist and enable alert interpretation in operations routine.

## 6. Risks & Mitigations

- Pool identity mismatch (`pool_id` drift):
  - keep fallback by `(chain,address)`.
- False alerts on volatile pools:
  - use class-specific thresholds and confidence tags.
- Report bloat:
  - fixed Top-N + separate blocks + chunking.

## 7. Task Checklist

- [ ] Add config schema + defaults for `my_pools_monitor`
- [ ] Add monitor data models
- [ ] Implement pool resolver (`pool_id` + `chain/address`)
- [ ] Implement health/alert tags + counters
- [ ] Add notifier section rendering
- [ ] Add tests and run full suite
- [ ] Update runbook/memory docs after rollout
