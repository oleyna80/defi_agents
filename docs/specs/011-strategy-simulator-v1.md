# Specification: Strategy Simulator v1 (Simulation-Only, Risk-First)

Status: DRAFT

Owner: Tech Lead / Architect

Date: 2026-02-05

Related:
- docs/research/strategies_library.md
- docs/specs/010-freshness-recheck-v1.md

---

## 1. Context

Discovery pipeline currently finds and filters pools, but it does not model strategies on top of those candidates.

We need a simulation layer that:
- evaluates strategy suitability (fit)
- estimates expected net APY range (bounded heuristic)
- produces risk-first metadata suitable for human decision review
- does not execute on-chain actions

---

## 2. Goal

Add a Strategy Simulation stage after shortlist (post Scout + L3 + Freshness) so the report includes decision-grade strategy metadata.

---

## 3. Scope (v1)

In scope:
- Simulation-only (no execution)
- Tier 1–2 strategies from strategies library
- EVM-only simulation support; non-EVM chains are tagged as UNSUPPORTED
- Deterministic rules + bounded heuristics (no ML, no external calls)

Out of scope:
- Trade execution
- Perps funding / derivatives engine
- Tier 3–5 strategies as actionable

---

## 4. Strategy Catalog (v1)

Supported strategy IDs:
1) liquid_staking_core
2) single_sided_lending
3) yield_bearing_stable_core
4) stable_stable_fee_capture
5) clmm_range_harvest

For each strategy, define:
- entry_rules
- exit_rules
- required_data
- risk_limits
- supported_chains
- supported_pair_classes

---

## 5. Data Contract

### Inputs

- ScoutResult shortlist, including security + freshness metadata.

### Outputs

Attach strategy simulation outputs to the candidate metadata.

Implementation constraint:
- Current report object uses metadata as string map, so v1 stores outputs as flat keys.

Required keys (v1):
- sim_status: OK | PARTIAL | UNSUPPORTED
- sim_best_strategy: string strategy id
- sim_fit_score: 0..100 as string
- sim_exp_net_apy_min: float as string
- sim_exp_net_apy_max: float as string
- sim_risk_score: 0..100 as string
- sim_constraints_hit: compact csv string
- sim_required_data_missing: compact csv string
- sim_candidates_compact: compact summary of top candidates

---

## 6. Decision Policy

- If sim_required_data_missing is non-empty -> sim_status=PARTIAL and candidate is WATCHLIST-only.
- If sim_status=UNSUPPORTED -> WATCHLIST-only.

### 6.1 Missing-data policy (hard, v1)

Risk-first constraint for v1:
- If required data for the best-matching strategy is not complete, the candidate must be treated as PARTIAL.
- PARTIAL must be WATCHLIST-only.
- StrategySim must never upgrade a candidate to actionable when required data is missing.

CLMM strategy (clmm_range_harvest) required data (minimum):
- tvl_usd
- volume_24h_usd OR fees_24h_usd
- volatility proxy: apy_mean_30d OR price_vol_7d
- pool_type=CLMM must be explicit

Actionable is allowed only if:
- security bucket is allowed
- freshness policy passed (or already enforced)
- sim_status=OK
- sim_risk_score <= profile threshold

---

## 7. Investor Profile Mapping (v1)

Use existing profiles:
- micro: Tier 1 only, limited Tier 2
- standard: Tier 1–2
- whale: Tier 1–2 plus capacity guards

FX exposure:
- FX_STABLE pools always imply fx_exposure=true
- FX exposure never routes to core_safe (existing risk policy guardrail)

---

## 8. Integration Points

- New module: src/defi_agents/strategy_sim/
- Pipeline: scout -> security/l3 -> freshness -> strategy_sim -> notifier
- Config: strategy_sim block in docs/memory-bank/scout_config.json

---

## 9. Config (v1)

strategy_sim:
- enabled: false
- max_candidates: 20
- supported_tiers: [T1, T2]
- allow_unsupported_as_watchlist: true
- risk_thresholds_by_profile
- min_data_completeness_pct

---

## 10. Observability

Counters per cycle:
- simulated_count
- ok_count
- partial_count
- unsupported_count
- watchlist_by_missing_data_count
- best_strategy_distribution

---

## 11. Telegram / Report

Add per-row fields:
- BestStrategy
- SimStatus
- FitScore
- ExpNetAPY
- SimRisk
- MissingData (compact)

---

## 12. Verification

Automated:
- unit tests for strategy-fit and policy gates
- integration test: candidate -> strategy simulation metadata

Manual:
- 3+ VPS cycles with strategy_sim enabled, without runtime regression
- unsupported/partial never appear as actionable

---

## 13. DoD

- strategy_sim.enabled=true does not break pipeline
- strategy metadata is present in report/logs
- unsupported/partial are correctly watchlist-only
- all tests green

---

## 14. Risks / Open Questions

- Data completeness for CLMM and managed strategies
- Risk score calibration without backtest
- Chain coverage asymmetry (EVM vs non-EVM)
