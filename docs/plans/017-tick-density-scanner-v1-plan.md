# Technical Plan: Tick Density Scanner v1 (Band Depth Module)

Refers to Spec: `docs/specs/017-tick-density-scanner-v1.md`  
Related runbook: `docs/runbooks/Tick Density Scanner.md`  
Related strategy spec: `docs/specs/lp-decision-engine-v1.md`

## 1. Architecture Design

Target module layout:

```
src/defi_agents/lp/
├── __init__.py
├── models.py              # PoolState, TickData, BandDepthResult, PitInfo, SuggestedRange
├── tick_provider.py       # TickDataProvider + Uniswap/Aerodrome/Pancake/HyperSwap adapters
├── band_depth.py          # tick walking + band_depth windows (+1%/+2.5%/+5%)
├── pit_classifier.py      # pit detection + CONFIDENT/NOISE + whale-dependent flags
├── history.py             # band depth history + stability gates
└── visualization.py       # optional charts/heatmap (phase-gated)
```

Integration points:
- `src/defi_agents/scout/` (LP scorer/orchestrator reads `BandDepthResult`)
- `main.py` (shadow metrics + cycle counters + watchlist-only downgrade)
- `src/defi_agents/notifier.py` (optional phase: pit alerts/summary blocks)

Key boundary:
- Tick scanner is **data acquisition + feature extraction**, not trade execution.
- Any candidate with degraded data quality remains `WATCHLIST_ONLY`.

## 2. Delivery Phases

### Phase A — Core Provider + Tick Walking (P0)

Scope:
- Implement `TickDataProvider` protocol.
- Implement `UniswapV3TickProvider` with pagination and retry budget.
- Implement `calculate_band_depth()` using anchor-based tick walking.
- Implement RPC drift check (`validate_tick_freshness`).
- Emit minimal scoring hook payload (`REQ-020` contract).

Guardrails:
- Enforce `MAX_PAGES_PER_POOL` and `MAX_TICKS_PER_POOL`.
- On limit hit or timeout: return `DEGRADED` + reason code, no crash.

DoD:
- Unit tests for tick math and pagination limits pass.
- Integration check on Base ETH/USDC pool matches reference within tolerance.

### Phase B — Pit Detection + Range Suggestion (P0.5)

Scope:
- Add 1% binning and pit detection.
- Add `CONFIDENT_PIT` / `NOISE_PIT` classification.
- Add `WHALE_DEPENDENT` flag via positions overlap.
- Generate `SuggestedRange` aligned by `tickSpacing`.

DoD:
- Pits are deterministic on same snapshot.
- Suggested range fields are valid and aligned to fee-tier tick spacing.

### Phase C — Multi-DEX Adapters + Stability History (P1)

Scope:
- Add `AerodromeTickProvider`.
- Add `PancakeSwapV3TickProvider`.
- Add `HyperSwapTickProvider`.
- Add `BandDepthHistory` storage + 3-observation/6h stability gate.
- Add `scan_duration_p95_ms`, `pits_found_count`, `degraded_count`.

DoD:
- Multi-venue comparison for same pair is available.
- `UNSTABLE_DEPTH` gate is enforced before actionable use.

### Phase D — Shadow Rollout + Ops Gating (P1)

Scope:
- Enable module in shadow mode on VPS.
- Wire no-actionable behavior for `data_quality != OK`.
- Add operational checks in logs and runbook.

DoD:
- 24h shadow run without cycle errors.
- Required counters present in logs each cycle.
- No degraded candidate promoted to actionable.

### Phase E — Advanced Filters (P2+)

Scope:
- JIT capture detector.
- Event-driven Telegram pit alerts.
- Optional heatmap artifacts and deep-dive overlays.

DoD:
- JIT-trap signal is available and test-covered.
- Alerts deduplicated and rate-safe.

### Phase F — Krystal API Discovery (P1, non-blocking)

Scope:
- Evaluate Krystal Cloud API as **optional pool discovery aggregator** (REQ-022).
- This workstream runs **in parallel** with P0, does NOT block core implementation.
- Read-only investigation: no production code until stop/go gate passes.

Workstream tasks:
1. Obtain Krystal service-level API auth (contact team, partnership request).
2. If auth obtained: document endpoint list, JSON shapes, rate limits.
3. Validate tick-level data availability (does Krystal expose per-tick data or only pool-level?).
4. If pool-level only: Krystal = discovery provider, tick data stays Subgraph-sourced.

Stop/Go criteria:
- **GO** if ALL conditions met:
  - Service API key exists and returns 200 from server-side `curl`
  - JSON response schema is stable across 2+ calls over 48h
  - Response includes at minimum: `pool_address`, `token0`, `token1`, `volume_30d`, `fee_tier`
- **STOP** if ANY:
  - No auth path available within 2-week timebox
  - Krystal requires browser-only session (no server-side integration possible)
  - Response schema remains unstable/missing required pool-level fields for discovery contract

Timebox: 2 weeks from plan approval date.

DoD:
- Discovery report written to `docs/research/krystal-api-discovery.md`.
- Go/No-Go decision documented with evidence.
- If GO: implement adapter per existing REQ-022 contract (no spec rewrite required).

## 3. Config & Contracts

Proposed config block (feature-flagged, default OFF):
- `tick_density.enabled`
- `tick_density.max_pages_per_pool` (default 100)
- `tick_density.max_ticks_per_pool` (default 50000)
- `tick_density.scan_timeout_seconds` (default 5)
- `tick_density.retry_attempts` (default 3)
- `tick_density.min_expected_net_monthly_usd` (default 5.0)
- `tick_density.shadow_mode_enabled` (default true when enabled)

Contract requirements:
- Output object must contain at minimum:
  - `pool_address`
  - `band_depth_1pct_usd`, `band_depth_2_5pct_usd`, `band_depth_5pct_usd`
  - `pit_type`
  - `data_quality`
  - `scan_timestamp`

## 4. Testing Strategy

Unit tests:
- Tick math correctness (anchor walk vs known synthetic snapshots).
- Decimal conversion correctness (`USDC 6` vs `WETH 18`).
- Pagination/circuit-breaker behavior.
- Drift check behavior (`slot0` mismatch -> `DEGRADED`).
- Pit classification and range alignment.

Integration tests:
- Base ETH/USDC sanity check against external reference.
- Multi-adapter contract parity tests (same interface guarantees).
- Fail-safe tests for subgraph timeout/500.

Verification commands:
- `.venv/bin/python -m json.tool docs/memory-bank/scout_config.json >/dev/null`
- `.venv/bin/pytest -q tests/test_tick_density_*.py`
- `.venv/bin/pytest -q`

## 5. Rollout Strategy (VPS)

1) Merge with feature flag OFF.  
2) Enable shadow mode for 24h on 3-5 target pools.  
3) Validate:
- `errors=0`
- counters present: `pits_found_count`, `degraded_count`, `scan_duration_p95_ms`
- no actionable decisions from degraded data  
4) Calibrate thresholds (`min_expected_net_monthly_usd`, pit confidence thresholds).  
5) Promote to scoring pipeline for top candidates only.

## 6. Risks & Mitigations

- Subgraph schema drift:
  - adapter-level parser guards + explicit downgrade reason (`DegradationReason` enum, REQ-023).
- Broken pagination loops:
  - hard limits (`MAX_PAGES_PER_POOL`, `MAX_TICKS_PER_POOL`).
- False confidence in low-liquidity pits:
  - stability gate + small-cap profitability floor.
- Cost overhead on broad scans:
  - staged rollout: Uniswap -> Aerodrome -> Pancake/HyperSwap.
- Krystal API inaccessible (R-8):
  - P0 has zero dependency on Krystal. Discovery workstream (Phase F) is timeboxed and non-blocking.
  - If Krystal remains inaccessible: DeFiLlama continues as sole discovery source.

## 7. Task Checklist

- [x] Add `tick_density` config schema + safe defaults
- [x] Implement models and provider protocol (incl. `DegradationReason` enum)
- [x] Implement Uniswap provider + pagination guardrails
- [x] Implement anchor-based band depth calculation
- [x] Implement RPC drift validation
- [x] Add output-hook contract (`REQ-020`) to scorer integration point
- [x] Add small-cap watchlist guardrail (`REQ-021`)
- [x] Implement pit classification + suggested range
- [ ] Implement Aerodrome adapter
- [ ] Implement PancakeSwap and HyperSwap adapters
- [ ] Add history/stability gate
- [x] Add tests + full-suite validation (`168 passed`)
- [ ] Execute 24h VPS shadow rollout and record metrics
- [ ] (Phase F) Krystal API discovery — auth, schema validation, Go/No-Go report
