# Unified Plan: DeFi Coverage MVP + Freshness & Ops

**Status:** Draft
**Goal:** Integrate MVP data sources across DEX/LP, Lending, Staking/LST, and Perps Funding, while completing Phase 2 freshness (C+/D), non‑EVM visibility, and silent‑mode ops.

---

## Scope (MVP)

**Data Sources (shortlist):**
- **DEX/LP:** DeFiLlama (LP category) + Uniswap v3 subgraph (new pools)
- **Lending:** DeFiLlama Yield API + Aave v3 GraphQL
- **Staking/LST:** Lido API + DeFiLlama (staking/vault categories)
- **Perps Funding:** dYdX Market Data API + Binance Futures API (baseline)

**Freshness (Phase 2 C+/D):**
- **Aave direct re‑check** (replace deprecated aave‑api‑v2)
- **Morpho API** + threshold calibration on VPS telemetry

**Ops & Coverage gaps:**
- **Non‑EVM strategy visibility** (explicit UNSUPPORTED reporting)
- **Silent mode fix** (daily heartbeat “no opportunities”)

**Non‑goals (MVP):**
- Full historical time‑series backfill
- Advanced PnL simulation (multi‑leg execution)
- Automated execution

---

## Workstreams & Order

### Workstream A — DEX/LP (Discovery baseline)
**Work:**
- Ingest DeFiLlama LP pools into Scout
- Add Uniswap v3 subgraph adapter for new‑pool detection
- Normalize to unified contract

**DoD:**
- DEX pools appear in Scout with correct chain/symbol/project/TVL/APY
- New pools detected via Uniswap subgraph within minutes
- Freshness metadata attached

---

### Workstream B — Lending (Aave + aggregator)
**Work:**
- Ingest DeFiLlama lending pools
- Add Aave v3 GraphQL adapter for high‑fidelity lending data
- Map LTV/liquidation fields into metadata

**DoD:**
- Lending candidates emitted with supply/borrow APY
- Aave adapter validates/overrides top markets
- Fields consistent with unified contract

---

### Workstream C — Staking/LST
**Work:**
- Add Lido API adapter for ETH staking APR
- Use DeFiLlama staking/vault categories for LSD coverage

**DoD:**
- Staking candidates emitted with APR + TVL
- Lido APR visible as canonical ETH staking reference

---

### Workstream D — Perps Funding
**Work:**
- Add dYdX market data adapter (funding rate)
- Add Binance Futures API adapter for baseline funding

**DoD:**
- Funding rates available for key perps markets
- Baseline comparisons possible (DeFi vs CeFi)

---

### Workstream E — Freshness C+/D (Decision‑grade)
**Work:**
- Implement Aave direct re‑check (modern endpoint strategy)
- Add Morpho API adapter
- Calibrate divergence thresholds on VPS telemetry

**DoD:**
- Actionable candidates are FRESH‑gated
- Divergence alerts triggered on outliers
- Telemetry shows stable freshness coverage

---

### Workstream F — Ops & Coverage Completeness
**Work:**
- Non‑EVM explicit reporting path (UNSUPPORTED tag/counters)
- Daily heartbeat when no opportunities found

**DoD:**
- No silent cycles: heartbeat confirms system health
- Missed non‑EVM opportunities are visible in logs/reporting

---

## Unified Data Contract (MVP)
Each candidate should expose:
- `class` (dex/lending/staking/perps)
- `protocol`, `chain`, `assets`
- `apy` (or `funding_rate` for perps)
- `tvl_usd` / `liquidity`
- `risk_tags`
- `freshness_status`, `source_timestamp`

---

## Ops & Safety
- Fail‑safe defaults: missing data ⇒ `UNVERIFIED` + WATCHLIST
- No scoring penalties in MVP (observability‑only)
- Rate‑limit protection and caching at adapters

---

## Risks / Mitigations
- **Aggregator lag:** use protocol sources for validation on top pools
- **Schema drift:** strict mapping + unit tests
- **Rate limits:** cache + throttling

---

## Success Metrics
- Each class yields >0 candidates daily
- No increase in false positives (security gates intact)
- Freshness tags present for all new sources
- Daily heartbeat confirms healthy “no‑signal” cycles

