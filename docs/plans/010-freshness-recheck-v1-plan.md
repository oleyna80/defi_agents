# Technical Plan: Freshness Re-check v1 (Decision-Grade Alerts)

Refers to Spec: `docs/specs/010-freshness-recheck-v1.md`

## 1. Architecture Design
- Components:
  - `FreshnessConfig` (thresholds + budgets)
  - `FreshnessChecker` (re-check orchestrator for shortlist)
  - `SourceAdapter` interface (per DEX/protocol re-check backends)
  - Reporter enrichment (freshness/divergence tags in Telegram + history)
- Data flow:
  - Scout results -> security/L3 -> shortlist -> freshness re-check -> actionable/watchlist gating -> Telegram output.

## 2. API / Interface Changes

### New Interfaces
```text
FreshnessSnapshot {
  source_timestamp: datetime | None
  age_minutes: int | None
  apy: float | None
  tvl_usd: float | None
  provider: str
  status: FRESH | STALE | UNVERIFIED
}

FreshnessDecision {
  freshness_status: FRESH | STALE | UNVERIFIED
  staleness_score: int
  apy_divergence_pct: float | None
  tvl_divergence_pct: float | None
  downgrade_reason_codes: list[str]
}
```

### Updated Fields in `ScoutResult.metadata`
- `freshness_status`
- `staleness_score`
- `source_timestamp`
- `age_minutes`
- `apy_divergence_pct`
- `tvl_divergence_pct`
- `freshness_provider`

## 3. File Structure Impact
- [M] `src/defi_agents/scout/config.py` (freshness config block)
- [M] `main.py` (insert re-check stage before final report grouping)
- [M] `src/defi_agents/notifier.py` (freshness tags in report rows)
- [M] `src/defi_agents/history.py` (optional columns for freshness fields)
- [+] `src/defi_agents/freshness/manager.py` (orchestrator + decision policy)
- [+] `src/defi_agents/freshness/adapters/*.py` (source adapters)
- [M] `docs/memory-bank/scout_config.json` (default thresholds)

## 4. Delivery Phases (1 Week)

### Phase A (Days 1-2): Schema + Policy Wiring
- Add config knobs and metadata schema.
- Implement decision policy + downgrade rules (`FRESH` only for actionable).
- Add cycle counters for freshness pipeline.

### Phase B (Days 3-4): Re-check Adapter MVP
- Implement first adapter for high-impact pools/chains (coverage-first, not perfection).
- Enforce timeout/budget controls and explicit `UNVERIFIED` fallback tags.

### Phase C (Days 5-6): Reporter + History Integration
- Show freshness/divergence tags in Telegram.
- Persist freshness fields to history for calibration.
- Add operator-friendly log summary.

### Phase D (Day 7): Calibration + Hardening
- Tune threshold defaults against live VPS runs.
- Validate actionable/watchlist downgrade behavior.
- Finalize docs/memory updates.

## 5. Verification Strategy
- Unit tests:
  - Freshness decision matrix (`FRESH/STALE/UNVERIFIED`).
  - Divergence threshold behavior.
  - Actionable gating enforcement.
- Integration tests:
  - Re-check failure path produces `UNVERIFIED`, not false actionable.
  - End-to-end run includes freshness counters and tags.
- Manual VPS checks:
  - Compare 5-10 sample pairs against UI/API snapshots.
  - Confirm downgrade tags match observed divergence.

## 6. Implementation Checklist
- [ ] Add freshness config block + defaults.
- [ ] Implement freshness manager and decision policy.
- [ ] Insert pre-alert re-check stage into main cycle.
- [ ] Add report tags and history fields for freshness/divergence.
- [ ] Add freshness counters to cycle logs.
- [ ] Add tests (unit + integration smoke).
- [ ] Tune thresholds on VPS and update docs.
