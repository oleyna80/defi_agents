# Technical Plan: Pipeline Relaxation v1 (Scout Funnel + Lindy)

Refers to Spec: `docs/specs/007-pipeline-relaxation-v1.md`

## 1. Architecture Design
- Components:
  - Scout ingestion (DeFiLlama)
  - Heuristics + prioritization
  - Addressability filter (`address + chain_id`)
  - SecurityAuditor gate
  - L3 gating (unchanged)
  - Reporter (logs/CSV/Telegram) (minimal additions)
- Data flow:
  - Capture funnel counters at each stage and emit summary at end of cycle.

## 2. API / Interface Changes
### New or Updated Functions
```text
YieldScout.analyze() -> returns ScoutResult[] (unchanged)
New: FunnelMetrics (data class/pydantic) or dict emitted in logs and persisted
```

### Data Models (Schema)
- Funnel metrics schema (suggested):
  - cycle_timestamp
  - raw_pools_count
  - heuristics_pass_count
  - addressable_count
  - audited_count
  - security_status_counts (trusted/pass/warn/block/unknown)
  - l3_processed_count
  - final_safe_count
  - final_lindy_warn_count
  - top_block_reasons (code->count)
  - missing_address_count / missing_chain_id_count

## 3. File Structure Impact
- [M] `src/defi_agents/scout/scout.py` (prioritization, metrics capture)
- [M] `src/defi_agents/scout/config.py` (audit slice size, thresholds)
- [M] `src/defi_agents/security/auditor.py` and/or `src/defi_agents/security/models.py` (Lindy soften logic location decision)
- [M] `main.py` (bucketed reporting and/or logging)
- [M] `docs/memory-bank/scout_config.json` (new knobs, if needed)
- [+] optional: `src/defi_agents/metrics.py` (if metrics deserve a small module)

## 4. Verification Strategy
- Unit tests:
  - Funnel metrics counting (deterministic sample payloads)
  - Lindy soften-only behavior:
    - critical tech flag stays BLOCK regardless of Lindy
    - missing-audit/reputation becomes WARN only under thresholds
- Integration tests (light):
  - Run one cycle with mocked upstream payloads ensuring:
    - non-EVM candidates counted as unsupported
    - stable-first ranking increases addressable share
- Manual checks:
  - `deploy/vps/preflight.sh`
  - one `systemctl --user start defi-sentinel.service` and check logs contain funnel summary

## 5. Implementation Checklist
- [ ] Decide `age` source for Lindy v1 (pool timestamp vs contract age proxy) and document it.
- [x] Add funnel metrics capture + end-of-cycle summary.
- [x] Add stable-first + addressable-first prioritization before security calls.
- [x] Expand EVM `chain_id_map` and add "unsupported non-EVM" counters (v1 counters via missing-address/chain metrics).
- [x] Implement Lindy v1 soften-only rule and bucketed output (`SAFE` vs `LINDY/WARN`) (initial version).
- [x] Add/adjust tests and run full suite.
