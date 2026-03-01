# Plan 020 — Delta Hedger PoC (Hummingbot Worker)

Status: DRAFT  
Owner: Tech Lead  
Date: 2026-02-27  
Related: ROADMAP Phase 5, Spec 018 (execution safety baseline), `docs/research/2026-02-open-source-reuse-matrix.md`

## 0. Progress Snapshot (2026-02-27)

- [x] Phase A — contracts/config baseline
- [x] Phase B — deterministic calculator
- [x] Phase C — connector readiness + shadow simulation wrapper
- [x] Phase D — gate tooling (orchestrator, worker entrypoint, 24h report script, runbook)
- [x] Phase D live evidence collection (24h shadow window on VPS)
- [x] Final GO/NO-GO memo (`docs/research/2026-02-27-hedger-shadow-gate-note.md`)

## 1. Goal

Validate that delta-hedging can be implemented as an **isolated worker** (outside core scout runtime) using `hummingbot` components, without weakening current execution safety model.

## 2. Why this PoC now

- We need a low-risk path to Phase 5 (`Delta Hedger`) before any LIVE hedge execution.
- `hummingbot` has permissive license (`Apache-2.0`) and existing connector abstractions.
- Current scout/execution path must remain stable and independent while hedge layer is explored.

## 3. Scope (PoC only)

- Build a minimal hedge worker in `PAPER/SHADOW` modes:
  - input: normalized LP exposure snapshot (net delta per asset),
  - logic: target hedge ratio calculator,
  - output: simulated hedge intents/orders + risk metrics.
- Validate connector readiness for one venue pair:
  - CEX path: Binance Futures (testnet/sandbox if available),
  - DEX perp fallback candidate: Hyperliquid (read-only checks first).
- Produce deterministic logs/metrics for gate decision.

## 4. Out of Scope

- No automatic LIVE hedge execution.
- No cross-margin portfolio optimization.
- No liquidation bot in this phase.
- No coupling hedge worker into `main.py` production cycle.

## 5. Architecture Constraints (Mandatory)

- Hedge worker is a separate process/module boundary (no direct dependence in scout loop).
- Fail-safe defaults:
  - if exposure data is stale/unavailable => `NO_ACTION`,
  - if connector health is degraded => `NO_ACTION`,
  - if risk limits cannot be computed => `NO_ACTION`.
- Shared safety controls must mirror execution policy:
  - global kill-switch,
  - max notional per order,
  - max daily hedge notional,
  - max slippage / spread guard.

## 6. Implementation Phases

### Phase A — Contracts and Data Flow

1. Define PoC contracts (`HedgeExposure`, `HedgeIntent`, `HedgeDecision`, `HedgeCounters`).
2. Add adapter interface for exposure source (read-only from current position state pipeline).
3. Add config block for hedger policy caps (all defaults OFF / strict).

Acceptance:
- Unit tests for contract validation and fail-safe defaults.
- No runtime behavior change when hedger is disabled.

### Phase B — Calculator (Paper Logic)

1. Implement deterministic hedge ratio calculator:
   - `target_notional = exposure_delta_usd * hedge_ratio`.
2. Add threshold/cooldown logic:
   - min rebalance delta,
   - min interval between hedge actions.
3. Emit `PAPER` decisions with reasons (`HEDGE`, `HOLD`, `SKIP_POLICY`, `SKIP_DATA`).

Acceptance:
- Unit tests for calculation, thresholds, cooldown, and policy blocks.
- Structured summary logs with reason counters.

### Phase C — Connector Readiness (Shadow Transport)

1. Integrate minimal hummingbot connector wrapper for quote/simulated order path.
2. Add connector health probe:
   - auth check,
   - instrument metadata,
   - best bid/ask availability.
3. Shadow order simulation with explicit rejection taxonomy.

Acceptance:
- Shadow run does not break on connector failures.
- Failures are surfaced as typed reasons; no uncaught exceptions.

### Phase D — Gate and Decision

1. Run 24h PoC shadow session with fixed scenario inputs.
2. Collect gate metrics:
   - worker cycles,
   - skipped-by-policy,
   - connector errors,
   - simulated fill feasibility.
3. Produce GO/NO-GO note for Spec drafting.

Acceptance:
- `errors=0` (uncaught) for 24h shadow run.
- Decision memo with next-step recommendation (`Spec Required` for LIVE path).

## 7. Deliverables

- `docs/specs/020-delta-hedger-poc-v1.md` (draft spec skeleton after PoC gate).
- `src/defi_agents/hedger/` PoC module (isolated, feature-flagged OFF by default).
- Tests for contracts/calculator/policy behavior.
- Runbook for shadow launch and rollback.

## 8. Risks and Mitigations

- Connector/API instability:
  - Mitigation: health probes + strict fail-safe `NO_ACTION`.
- Over-hedging from noisy exposure input:
  - Mitigation: thresholds, cooldown, max notional caps.
- Runtime coupling risk:
  - Mitigation: separate process boundary, no hard dependency in scout loop.

## 9. Exit Criteria (PoC Complete)

- PoC worker operates in `PAPER/SHADOW` with deterministic outputs.
- Safety controls demonstrated (`kill-switch`, notional caps, connector degradation handling).
- Clear GO/NO-GO decision for full Phase 5 spec and implementation.
