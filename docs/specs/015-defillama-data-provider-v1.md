# Specification: DeFiLlama Data Provider v1

Status: DRAFT
Owner: Tech Lead / Architect
Related Memory: `docs/memory-bank/activeContext.md`
Date: 2026-02-12

## 1. Context & Business Value

Scout currently consumes DeFiLlama mostly via one surface (`yields/pools`) and parses fields inside scouting flows.
This limits controllability, reuse, and observability for:
- yield stability signals (e.g., `apyMean30d`, `outlier`, `mu/sigma`)
- protocol-level context (TVL/chains/category)
- market structure context (fees/DEX/options/perps overviews)
- stablecoin and bridge risk overlays

We need a dedicated provider layer that:
- normalizes DeFiLlama endpoints into typed internal facts
- centralizes retries/timeouts/cache/schema-guardrails
- feeds Scout scoring/risk/reporting with decision-grade inputs

## 2. Scope (v1)

In scope:
- New `DeFiLlamaDataProvider` module as SSOT for DeFiLlama ingestion.
- Normalized fetch + parse for:
  - Yields: `/yields/pools`, `/yields/poolsOld`, `/yields/chart/{pool_id}`
  - Protocol metadata: `/protocols`, `/protocol/{slug}`, `/chains`
  - Market overviews: `/overview/{fees|dexs|options|bridge-aggregators}` + `/summary/{category}/{protocol}`
  - Stablecoins: `stablecoins.llama.fi/*` key endpoints
  - Bridges: `bridges.llama.fi/*` key endpoints
  - Prices: `coins.llama.fi/prices/current|historical`
- Typed contracts for downstream modules (`Scout`, reporter, future inspector integrations).

Out of scope:
- Replacing Security Auditor, Freshness adapters, or Protocol Inspector logic.
- Non-DeFiLlama data source integrations.
- Economic model redesign beyond using additional normalized fields.

## 3. Functional Requirements

- REQ-001: Provide an explicit provider API:
  - `get_yield_pools()`
  - `get_yield_pool_history(pool_id)`
  - `get_protocols()`, `get_protocol(slug)`, `get_chains()`
  - `get_market_overview(category)`, `get_market_summary(category, protocol)`
  - `get_stablecoin_snapshot()`
  - `get_bridge_snapshot()`
  - `get_prices_current(keys)`, `get_prices_historical(ts, keys)`
- REQ-002: Provider must expose typed normalized models (no raw dict leakage to callers by default).
- REQ-003: On upstream/schema errors, provider must fail safe:
  - return bounded empty/partial result with structured warning metadata
  - never crash Scout cycle from provider parsing failures
- REQ-004: Add configurable HTTP controls:
  - request timeout, retries with backoff, max payload guard, per-endpoint TTL cache
- REQ-005: Preserve secret-safe logs:
  - no API keys/tokens/raw sensitive URLs in logs
- REQ-006: Backward compatibility:
  - current Scout behavior and report shape remain stable after provider wiring

## 4. Data Contract (v1, minimal)

Provider outputs normalized facts:
- `YieldPoolFact`
  - `pool_id`, `project`, `chain`, `symbol`, `tvl_usd`, `apy`, `apy_base`, `apy_reward`
  - `apy_mean_30d`, `apy_pct_30d`, `apy_pct_7d`, `apy_pct_1d`
  - `volume_usd_1d`, `volume_usd_7d`
  - `stablecoin`, `il_risk`, `outlier`, `underlying_tokens`, `reward_tokens`, `pool_meta`
- `YieldPoolHistoryFact`
  - timeseries points: `timestamp`, `tvl_usd`, `apy`, `apy_base`, `apy_reward`, `apy_base_7d`, `il7d`
- `ProtocolFact`
  - `slug`, `name`, `category`, `chain_tvls`, `current_chain_tvls`, `mcap`, `url`
- `MarketOverviewFact`
  - `category`, `total_24h`, `total_7d`, `change_1d`, `change_7d`, `protocol_rows[]`
- `StablecoinSnapshotFact`
  - per-asset circulating, chain distribution, price/peg metadata
- `BridgeSnapshotFact`
  - per-bridge 24h/7d/30d volumes, chain coverage
- `PriceFact`
  - `key`, `price`, `timestamp`, `confidence`

## 5. Non-Functional Requirements

- Performance:
  - provider requests are bounded and cache-backed; no unbounded fan-out per cycle
- Reliability:
  - schema drift must degrade gracefully with parse guards and counters
- Testability:
  - parser and adapter layers are unit-testable with fixture payloads
- Observability:
  - provider-level counters: success/timeout/error/parse_error/cache_hit per endpoint family

## 6. Integration Rules

- Scout domain logic does not call raw DeFiLlama endpoints directly after migration.
- `DeFiLlamaClient` can remain as compatibility orchestrator in v1, but all HTTP/parsing moves into provider.
- Directional sections and lending snapshot must consume normalized facts, not endpoint-specific keys.

## 7. Acceptance Criteria

- AC-001: Existing Scout tests stay green after provider integration.
- AC-002: New provider unit tests cover successful parsing + schema-missing fail-safe for each endpoint family.
- AC-003: Telegram digest output remains structurally unchanged for existing sections.
- AC-004: Scout gets access to `apyMean30d` and history endpoint via typed provider API.
- AC-005: Provider emits endpoint counters in logs without leaking secrets.

## 8. Risks / Open Questions

- Some DeFiLlama surfaces (`perps`, `revenue`) may intermittently return 5xx; v1 must treat them as optional.
- Payload sizes are large (`protocols`, `yields/pools`); cache + bounded refresh cadence are mandatory.
- Need explicit policy for freshness of provider cache vs cycle cadence (6h digest vs hourly run).
