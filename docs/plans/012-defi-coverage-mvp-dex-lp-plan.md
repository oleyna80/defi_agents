# Plan: DEX/LP Discovery v1 (DeFi Coverage MVP)

**Status:** Draft
**Spec:** `docs/specs/012-defi-coverage-mvp-dex-lp.md`
**Goal:** Deliver DEX/LP discovery baseline (DeFiLlama + Uniswap v3 new‑pool detection) with safe rollout and observability.

---

## Phase 0 — Prep & Config
- Confirm config keys for:
  - Uniswap adapter enable flag
  - `max_pools` / `min_tvl_usd`
  - freshness fields default (`UNVERIFIED`)
- Add config defaults to `docs/memory-bank/scout_config.json`.

**DoD:** config schema updated, defaults present, no runtime errors when disabled.

---

## Phase 1 — DeFiLlama LP Intake
- Ensure LP pools from DeFiLlama are tagged as `class="dex"` in metadata.
- Attach `pool_id` for deep links (already used in report).
- Normalize fields into unified contract (chain/symbol/project/TVL/APY).

**DoD:** DEX pools appear in Scout output with correct metadata, no regression in security gating.

---

## Phase 2 — Uniswap v3 New‑Pool Adapter
- Implement adapter to query Uniswap v3 subgraph for newest pools:
  - GraphQL query: latest pools ordered by `createdAtTimestamp`
  - Filter by `min_tvl_usd` and `max_pools`
- Attach `pool_age_minutes` and `source_timestamp` metadata.
- Fail‑safe: any errors mark pools as `UNVERIFIED` but do not crash cycle.

**DoD:** New pools appear within minutes when TVL exceeds threshold; adapter failures do not break cycle.

---

## Phase 3 — Observability & Metrics
- Add per‑cycle counters:
  - `dex_llama_count`
  - `dex_uniswap_new_count`
  - `dex_filtered_count`
- Log in cycle summary (same pattern as Funnel/Freshness/StrategySim).

**DoD:** logs show DEX intake and new‑pool detection counts each cycle.

---

## Phase 4 — Tests
- Unit tests:
  - Adapter enable/disable
  - Query limit and TVL filter behavior
  - Metadata mapping (class, pool_id, pool_age)
- Integration tests:
  - New pools appended without breaking existing Scout flow

**DoD:** tests pass; no regressions.

---

## Phase 5 — Rollout (Safe)
- Deploy with adapter disabled
- Enable on VPS, monitor 3+ cycles:
  - Ensure no error spikes
  - Verify new pools count
- Confirm Telegram report correctness

**DoD:** stable cycles, no noisy false positives, new pools visible when present.

---

## Risks / Mitigations
- **Graph rate limits:** cache per cycle, limit results, exponential backoff.
- **Pool spam:** require min TVL threshold.
- **Inconsistent symbols:** normalize token symbols where possible.

