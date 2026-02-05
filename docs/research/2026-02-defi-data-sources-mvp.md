# DeFi Data Sources MVP (All Chains)

**Scope:** All chains (no restrictions)
**Goal:** Identify reliable data sources for lending, staking, perps funding, and DEX/LP pools to power Scout + Strategy Simulator.

---

## 0) Summary (MVP Picks)

- **Lending/Borrowing MVP:**
  - **DeFiLlama Yield API** (aggregated lending APY/TVL across many protocols; hourly refresh)
  - **Aave v3 GraphQL (The Graph)** (high‑fidelity, near‑realtime reserves/borrow/supply/LTV data)
  - **Compound v2/v3 API/Subgraph** (classic money markets, alternative model vs Aave)

- **Staking/LST MVP:**
  - **Lido API** (stETH APR, daily updated; canonical ETH staking reference)
  - **DeFiLlama Yield API (staking/vault categories)** (multi‑LST coverage + yield‑bearing stables)
  - **Yearn or Beefy API (optional)** for yield‑bearing stables/vaults

- **Perps Funding MVP:**
  - **dYdX Market Data API** (hourly funding; DeFi baseline)
  - **Binance Futures API** (CeFi baseline reference for BTC/ETH)
  - **GMX / Perpetual Protocol subgraph** (on‑chain perps funding on Arbitrum/Optimism)

- **DEX/LP MVP:**
  - **DeFiLlama Yield API (LP category)** (fast multi‑DEX coverage with APY/TVL)
  - **Uniswap v3 subgraph** (new pool discovery + fee‑APR computation)
  - **Curve API** (stable‑pool focus with base/reward APY breakdown)

---

## 1) Lending / Borrowing Markets

### 1.1 Source Table
| Protocol | API Type | Chains Supported | Fields Available | Freshness / Lag | Auth / Limits | Notes |
|---|---|---|---|---|---|---|
| Aave v3 | GraphQL (The Graph) | Ethereum, Polygon, Arbitrum, Optimism, Avalanche, etc. | supply/borrow APY, liquidity, TVL, LTV/liquidation thresholds, utilization, rewards | near‑realtime (subgraph delay minutes) | no API key; Graph limits possible | Best high‑fidelity protocol source |
| Compound v2/v3 | REST + Subgraph | Ethereum (v2), Polygon/Avalanche (v3) | supply/borrow APY, liquidity, collateral factors, rewards | near‑realtime | public endpoints | Good model diversity vs Aave |
| DeFiLlama Yield API | REST | multi‑protocol, multi‑chain | APY, TVL (aggregated) | hourly | open API; rate limits | Best breadth/coverage |
| DefiYields.dev | REST | multi‑protocol | APY, TVL (aggregated) | hourly | open | alternative aggregator |

### 1.2 Sample Queries
- **DeFiLlama (all pools):**
  - `GET https://yields.llama.fi/pools`
- **Aave v3 (GraphQL):**
  - `POST https://api.v3.aave.com/graphql` with `markets` query (reserves + rates)
- **Compound v2 (REST):**
  - `GET https://api.compound.finance/api/v2/ctoken`

### 1.3 Data Contract Mapping
- assets: `symbol` / `pool` / underlying token
- chain: network (Ethereum, Arbitrum, etc.)
- protocol: `aave_v3`, `compound_v2`, `defillama`
- apy / borrow_rate: supply APY + borrow APY fields where available
- tvl / liquidity: `tvlUsd` or protocol liquidity fields
- risk tags: protocol risk + chain risk + collateral parameters (LTV/liq threshold)
- freshness: timestamp from subgraph or API response time

### 1.4 Risks / Gaps
- Aggregators may lag 1h (acceptable for most lending decisions but not for rapid moves).
- Some protocols only expose full detail via subgraphs; availability varies by chain.

---

## 2) Staking / LST / Yield‑Bearing Stables

### 2.1 Source Table
| Protocol | API Type | Chains Supported | Fields Available | Freshness / Lag | Auth / Limits | Notes |
|---|---|---|---|---|---|---|
| Lido | REST | Ethereum (stETH), partial L2 | staking APR, net APR, timestamp | daily (rebases) | open, no key | Canonical ETH staking rate |
| Rocket Pool / StakeWise | Subgraph | Ethereum | rETH exchange rate, TVL, APR (derived) | near‑realtime | open subgraph | Alternative LSD sources |
| DeFiLlama Yield API | REST | multi‑chain | staking/vault APY, TVL | hourly | open API | Broad LSD + yield‑stable coverage |
| Yearn / Beefy | REST | Ethereum + multi‑chain | vault APY, TVL | hourly/daily | open | Yield‑bearing stables / vaults |
| Chainlink ETH Staking Rate | On‑chain / feed API | Ethereum | staking rate | feed update cadence | public | validation source for ETH staking |

### 2.2 Sample Queries
- **Lido APR:**
  - `GET https://eth-api.lido.fi/v1/protocol/steth/apr/last`
- **DeFiLlama (staking pools):**
  - `GET https://yields.llama.fi/pools` (filter `pool_type=staking` or `project`)
- **Yearn:**
  - `GET https://api.yearn.finance/v1/chains/1/vaults/all`

### 2.3 Data Contract Mapping
- assets: `stETH`, `rETH`, `sfrxETH`, `aUSDC`, etc.
- chain: Ethereum + other L1/L2s
- protocol: `lido`, `rocketpool`, `yearn`, `defillama`
- apy: staking/vault APR
- tvl: total staked or vault TVL
- lockup/unbonding/slashing: where protocol exposes (otherwise risk tag)
- freshness: timestamp or last update

### 2.4 Risks / Gaps
- Staking APR changes daily; real‑time not required but staleness must be tracked.
- Some yield‑bearing stables overlap with lending sources (avoid double counting).

---

## 3) Perps Funding Rates

### 3.1 Source Table
| Protocol | API Type | Chains Supported | Fields Available | Freshness / Lag | Auth / Limits | Notes |
|---|---|---|---|---|---|---|
| dYdX | REST | dYdX chain (perps) | fundingRate, next funding time | hourly | public API | Core DeFi perps reference |
| GMX | Subgraph | Arbitrum, Avalanche | funding/borrow fees (derived) | ~hourly | open subgraph | On‑chain perps model |
| Perpetual Protocol | Subgraph | Optimism | funding rate (8h) | 8h | open | DeFi perps coverage |
| Coinglass | REST (API key) | CEX + some DEX | funding rates (multi‑venue) | near‑realtime | key required | Aggregated reference |
| Binance Futures | REST/WebSocket | CEX | funding rate, next funding time | 8h | public | CeFi baseline |

### 3.2 Sample Queries
- **dYdX markets:**
  - `GET https://api.dydx.exchange/v3/markets`
- **Binance funding rate:**
  - `GET https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT`
- **Perp subgraph:**
  - GraphQL `market(id: "BTC") { fundingRate }`

### 3.3 Data Contract Mapping
- assets: underlying asset (BTC/ETH, etc.)
- chain: protocol chain (dYdX chain, Arbitrum, Optimism)
- protocol: `dydx`, `gmx`, `perp`
- funding_rate: current funding % (hourly/8h)
- oi / volume / liquidity: if available
- freshness: timestamp

### 3.4 Risks / Gaps
- Funding varies frequently; requires near‑realtime polling for accurate simulations.
- Some DeFi protocols don’t expose a simple REST endpoint; subgraph parsing required.

---

## 4) DEX / LP Pools

### 4.1 Source Table
| Protocol | API Type | Chains Supported | Fields Available | Freshness / Lag | Auth / Limits | Notes |
|---|---|---|---|---|---|---|
| Uniswap v2/v3 | GraphQL (The Graph) | Ethereum + multi‑chain | pool list, TVL, volume, fees, creation events | near‑realtime | public subgraph; query limits | Best source for new pools |
| Curve | REST API | Ethereum + others | pool list, TVL, base/reward APY | ~5–10 min | public | Stable‑pool focus |
| DeFiLlama Yield API | REST | multi‑DEX, multi‑chain | APY (base+reward), TVL | hourly | open API | Broadest APY coverage |
| Messari / Graph aggregators | GraphQL | multi‑DEX | unified schema | near‑realtime | often paid | advanced/optional |

### 4.2 Sample Queries
- **DeFiLlama pools:**
  - `GET https://yields.llama.fi/pools`
- **Uniswap v3 new pools (GraphQL):**
  - `pools(first: 5, orderBy: createdAtTimestamp, orderDirection: desc)`
- **Curve pools:**
  - `GET https://api.curve.fi/api/getPools/ethereum/main`

### 4.3 Data Contract Mapping
- assets: token0/token1 (LP pair)
- chain: pool chain
- protocol: `uniswap_v3`, `curve`, `defillama`
- apy: base + reward (if available)
- tvl / liquidity: pool TVL
- pool age: from `createdAtTimestamp`
- freshness: timestamp or subgraph block

### 4.4 Risks / Gaps
- APY often derived from 24h volume; can be noisy for low‑volume pools.
- Aggregators can lag new pool discovery by up to ~1 hour.

---

## 5) Cross‑Source Comparison & MVP Decision

- **Recommended MVP Sources (final):**
  - **Lending:** DeFiLlama + Aave v3 GraphQL (+ Compound API as second baseline)
  - **Staking/LST:** Lido API + DeFiLlama (staking/vaults) + optional Yearn/Beefy
  - **Perps Funding:** dYdX API + Binance Futures + GMX/Perp subgraph
  - **DEX/LP:** DeFiLlama (LP APY) + Uniswap v3 subgraph (new pools) + Curve API
- **Rationale:**
  - DeFiLlama provides broad coverage with low integration cost.
  - Protocol‑native APIs (Aave, Lido, Uniswap) provide high‑fidelity data.
  - CeFi baseline (Binance) is useful for funding rate sanity checks.

---

## 6) References
- Aave Market Data | Aave Protocol Docs — https://aave.com/docs/aave-v3/markets/data
- AaveKit API v3 | Aave Protocol Docs — https://aave.com/docs/aave-v3/getting-started/graphql
- DefiLlama Yields API — https://defillama.com/yields
- DefiYields — https://defiyields.dev/
- Lido API — https://docs.lido.fi/integrations/api/
- Chainlink Rates & Staking Feeds — https://docs.chain.link/data-feeds/rates-feeds
- dYdX Funding — https://docs.dydx.xyz/concepts/trading/funding
- Perpetual Protocol Data Source — https://docs.perp.com/docs/guides/data-source/
- CoinGlass Funding Rates — https://www.coinglass.com/FundingRate
- Binance Futures API — https://binance-docs.github.io/apidocs/futures/en/
- Curve API — https://api.curve.fi/api/getPools
- Uniswap Subgraph (The Graph) — https://thegraph.com/hosted-service/subgraph/uniswap/uniswap-v3
