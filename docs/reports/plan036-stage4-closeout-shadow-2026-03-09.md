# Plan 036 — Stage-4 Closeout (SHADOW evidence)

**Date (UTC):** 2026-03-09  
**Scope:** repo-local only, без infra/secrets/n8n изменений, без commit/push

## 1) Startup check (mandatory)

- Full stdout artifact:
  - `docs/reports/artifacts/plan036_stage4_startup_check_2026-03-09.txt`
- Key results:
  - branch/head sync: `HEAD == origin/feat/multi-chain-reader` (`f09d390bc486a6a070c0c412de35b1b9e95c89fc`)
  - stash list present (`stash@{0}`, `stash@{1}`)
  - required grep markers found for Plan 036 + selector telemetry contract.

## 2) Runtime SHADOW evidence collection

### 2.1 Strict startup (no fallback)
- Runtime artifact:
  - `docs/reports/artifacts/plan036_stage4_shadow_runtime_2026-03-09T16-10-16Z.log`
- Observation:
  - startup fails fast with `Production AI Init Failure` caused by missing `DEEPSEEK_API_KEY`.

### 2.2 Command-scoped local diagnostic fallback (no file/env mutation)
- Runtime artifacts:
  - `docs/reports/artifacts/plan036_stage4_shadow_runtime_mockfallback_2026-03-09T16-11-39Z.log`
  - `docs/reports/artifacts/plan036_stage4_shadow_runtime_mockfallback_multicycle_2026-03-09T16-27-16Z.log`
- Effective command mode:
  - command-level env override `ALLOW_MOCK_FALLBACK=true` for evidence collection only.

## 3) Selector evidence snapshot (Stage-4)

- Snapshot artifact:
  - `docs/reports/artifacts/plan036_stage4_shadow_evidence_2026-03-09.json`

### 3.1 Required selector counters
- `entry_selector_input_total_sum`: `42`
- `entry_selector_matched_total_sum`: `42`
- `entry_selector_actionable_total_sum`: `7`
- `entry_selector_watchlist_total_sum`: `35`
- `entry_selector_actionable_ratio`: `0.1667`

### 3.2 Watchlist reasons / blockers
- `watchlist_reason_counts`:
  - `NON_LP_YIELD_TYPE: 27`
  - `INSUFFICIENT_STABILITY_HISTORY: 5`
  - `UNSUPPORTED_ENTRY_VENUE: 3`
- `watchlist_blocker_reason_counts`:
  - `SUBGRAPH_SCHEMA_UNSUPPORTED: 30`
- `tick_density_readiness_blocker_counts`:
  - `SUBGRAPH_SCHEMA_UNSUPPORTED: 3`

### 3.3 Top-N stability/churn
- churn values by cycle: `[0.0, 1.0, 0.25]`
- `entry_topn_churn_avg`: `0.4167`
- `entry_topn_churn_p95`: `1.0000`
- actionable trajectory by cycle: `[0, 3, 4]`

## 4) Verdict

**Verdict: `ADJUST`**

### Reasons
1. Selector telemetry contract is present and active in current runtime (input/matched/actionable/watchlist all emitted with non-zero actionable trajectory).
2. Short-window stability is not yet sufficient for `KEEP` (`topn_churn_p95=1.0` over 3 cycles).
3. Dominant blockers are external readiness/data-plane (`SUBGRAPH_SCHEMA_UNSUPPORTED`), not decision-logic regression.
4. Strict startup path currently depends on unavailable local AI secret (`DEEPSEEK_API_KEY`), requiring command-scoped fallback for repo-local SHADOW collection.

## 5) Drift note (runbook/runtime)

- Detected runtime/environment drift:
  - strict local startup fails without `DEEPSEEK_API_KEY`, while repo-local SHADOW evidence required command-scoped fallback.
- This closeout does **not** change fail-safe contract and does **not** alter decision logic.
- Drift recorded in this report + memory-bank sync for explicit operator visibility.

## 6) Guardrails confirmation

- VPS/infra/secrets/n8n changes: **none**
- Decision logic changes: **none**
- Fail-safe contract weakening: **none**
- commit/push: **not performed**
