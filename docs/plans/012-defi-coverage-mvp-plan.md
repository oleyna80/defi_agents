# Plan: DeFi Coverage MVP (Data Sources Integration)

**Status:** Draft
**Goal:** Integrate MVP data sources across DEX/LP, Lending, Staking/LST, and Perps Funding with a unified data contract and safe rollout.

---

## Scope (MVP)

**Data Sources (shortlist):**
- **DEX/LP:** DeFiLlama (LP category) + Uniswap v3 subgraph (new pools)
- **Lending:** DeFiLlama Yield API + Aave v3 GraphQL
- **Staking/LST:** Lido API + DeFiLlama (staking/vault categories)
- **Perps Funding:** dYdX Market Data API + Binance Futures API (baseline)

**Non‑goals (MVP):**
- Full historical time‑series backfill
- Advanced PnL simulation (multi‑leg execution)
- Automated execution

---

## Phased Execution

### Phase 1 — DEX/LP (Discovery baseline)
**Work:**
- Ingest DeFiLlama LP pools into Scout
- Add Uniswap v3 subgraph adapter for new‑pool detection
- Normalize to unified contract

**DoD:**
- DEX pools appear in Scout with correct chain/symbol/project/TVL/APY
- New pools detected via Uniswap subgraph within minutes
- Freshness metadata attached

---

### Phase 2 — Lending (Aave + aggregator)
**Work:**
- Ingest DeFiLlama lending pools
- Add Aave v3 GraphQL adapter for high‑fidelity lending data
- Map LTV/liquidation fields into metadata

**DoD:**
- Lending candidates emitted with supply/borrow APY
- Aave adapter validates/overrides top markets
- Fields consistent with unified contract

---

### Phase 3 — Staking/LST
**Work:**
- Add Lido API adapter for ETH staking APR
- Use DeFiLlama staking/vault categories for LSD coverage

**DoD:**
- Staking candidates emitted with APR + TVL
- Lido APR visible as canonical ETH staking reference

---

### Phase 4 — Perps Funding
**Work:**
- Add dYdX market data adapter (funding rate)
- Add Binance Futures API adapter for baseline funding

**DoD:**
- Funding rates available for key perps markets
- Baseline comparisons possible (DeFi vs CeFi)

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

