# Technical Plan: Scout Module (Discovery) v1.0

Refers to Spec: `docs/specs/006-scout-module.md`

## 1. Architecture Design

### Components
- `src/defi_agents/scout/config.py`
  - `ScoutConfig` (chains, TVL threshold, APY rules, gas thresholds)
- `src/defi_agents/scout/models.py`
  - `ScoutPool`, `ScoutResult` (pool data + `SecurityResult`)
- `src/defi_agents/scout/defillama_client.py`
  - async HTTP client for `https://yields.llama.fi/pools`
- `src/defi_agents/scout/scout.py`
  - main pipeline: fetch → filter → analyze → security gate → rank → dedupe
- `src/defi_agents/scout/cache.py`
  - anti-spam cache (pool last recommended timestamp)

### Data Flow
1) Fetch pools from DeFiLlama.
2) Apply static filters (TVL, pool priority tiers: stablecoin-only > coin+stable > coin+coin).
3) Compute analysis metrics:
   - yield_quality = apyBase / max(apyReward, eps)
   - apy_volatility_7d (if predictions or history available)
4) Security gate: call `SecurityAuditor.evaluate()` for each candidate.
5) Ranking: yield-to-risk score, remove `LOW_EFFICIENCY` if needed.
6) Dedupe: skip pools recommended < 24h ago unless parameters changed.

## 2. API / Interface Changes
- `Scout.find_candidates() -> list[ScoutResult]`
- `ScoutConfig`
  - `min_tvl_usd: float`
  - `pool_priority`: enum/order for [stablecoin, coin+stable, coin+coin]
  - `min_base_share: float` (base APY dominance)
  - `max_gas_pct: float` (2% default)
- `ScoutResult`
  - pool fields + `security: SecurityResult`
  - flags: `low_efficiency`, `rejected_reason`

## 3. File Structure Impact
- [+] `src/defi_agents/scout/config.py`
- [+] `src/defi_agents/scout/models.py`
- [+] `src/defi_agents/scout/defillama_client.py`
- [+] `src/defi_agents/scout/scout.py`
- [+] `src/defi_agents/scout/cache.py`
- [+] `tests/test_scout.py`

## 4. Verification Strategy
- Unit tests for filtering (TVL, pool priority tiers)
- Unit tests for yield quality metric and gas sanity check
- Integration test: mock DeFiLlama response + mock SecurityAuditor
- Dedupe test: same pool within 24h excluded

## 5. Implementation Checklist
- [x] Step 1: Define ScoutConfig + ScoutResult models.
- [x] Step 2: Implement DeFiLlama client (async) + response parsing.
- [x] Step 3: Implement filter + analysis layer.
- [x] Step 4: Integrate SecurityAuditor gate (PASS/TRUSTED only).
- [x] Step 5: Ranking + dedupe logic.
- [x] Step 6: Tests (filtering, scoring, dedupe).
