# Technical Plan: Security Module (Auditor) v1

Refers to Spec: `docs/specs/002-security-auditor.md`

## 1. Architecture Design

### Components
- `src/defi_agents/security/asset_classifier.py`
  - Echeloned asset classification (metadata -> regex -> optional signatures) used by Discovery/Monitoring gating.
- `docs/memory-bank/security/whitelist.json`
  - Local memory SSOT for manual approvals (tokens/protocols) consumed by Security/Discovery.
- `src/defi_agents/security/models.py`
  - Normalized models for security findings and adapter sources.
- `src/defi_agents/security/goplus_client.py`
  - GoPlus HTTP client (auth, retries, backoff, timeouts).
- `src/defi_agents/security/defi_client.py`
  - De.Fi HTTP client (optional enrichment; must fail open to "unknown").
- `src/defi_agents/security/auditor.py`
  - Orchestrates Stage A (GoPlus) + Stage B (De.Fi enrichment).
  - Applies deterministic decision rules -> normalized result.
- `src/defi_agents/security/cache.py`
  - TTL cache abstraction (in-memory for v1; optionally file-based).

### Data Flow
1) Input candidate: token/contract (chain_id + address) and optional pool metadata.
0) Pre-gate: AssetClassifier tags asset type (vault/bridged/synthetic/leveraged/unknown) and applies fail-safe policy.
0.1) Check Local Memory: if candidate is explicitly approved in `docs/memory-bank/security/whitelist.json` => PASS (Trusted).
2) Stage A: GoPlus scan -> granular flags.
3) Stage B: De.Fi enrichment (optional) -> audit/REKT metadata.
4) Normalize to `SecurityResult`:
   - `status`: pass|warn|block|unknown
   - `reasons`: list of typed flags
   - `sources`: raw-ish adapter summaries
5) Output to downstream modules (Discovery ranking / Monitoring alerts).

## 2. API / Interface Changes

### Public interface
- `audit_candidate(candidate: SecurityCandidate, cfg: SecurityConfig) -> SecurityResult`
- `scan_current_holdings(candidates: list[SecurityCandidate], cfg: SecurityConfig) -> list[SecurityResult]`

### Core data models (canonical)
- `SecurityCandidate`
  - `chain_id: str` (e.g., "1", "42161")
  - `address: str` (0x...)
  - optional: `symbol`, `name`, `protocol`, `pool_id`
- `SecurityResult`
  - `status: Literal["pass","warn","block","unknown"]`
  - `reasons: list[SecurityReason]`
  - `sources: list[SecuritySource]`
  - `as_of: datetime`
  - `ttl_seconds: int`
- `SecurityReason`
  - `code: str` (e.g., `HONEYPOT`, `HIGH_TAX`, `DANGEROUS_OWNERSHIP`, `NO_REPUTABLE_AUDIT`, `DATA_MISSING`)
  - `severity: Literal["info","warn","critical"]`
  - `message: str`
  - `data: dict` (optional small payload)

### Config
- `SecurityConfig`
  - `tax_warn_pct: float`
  - `tax_block_pct: float`
  - `cache_ttl_seconds: int`
  - `require_security_for_recommendation: bool` (default true)
  - `fail_safe_unknown_non_tier1: bool` (default true)

### De.Fi enrichment model (Stage B)
- `SecurityReputation` (embedded in `SecuritySourceRecord.summary` for De.Fi):
  - `protocol_score: int` (0-100)
  - `is_audited: bool`
  - `has_top_tier_audit: bool`
  - `rekt_history: bool`
  - `protocol_slug: str | None`
  - `protocol_name: str | None`

## 3. File Structure Impact
- [+] `src/defi_agents/security/asset_classifier.py`
- [+] `docs/memory-bank/security/whitelist.json`
- [+] `src/defi_agents/security/models.py`
- [+] `src/defi_agents/security/goplus_client.py`
- [+] `src/defi_agents/security/defi_client.py`
- [+] `docs/memory-bank/security/defi_protocols.json` (weekly refreshed)
- [+] `src/defi_agents/security/auditor.py`
- [+] `src/defi_agents/security/cache.py`
- [+] `tests/security/test_auditor_rules.py`
- [+] `tests/security/test_asset_classifier.py`
- [+] `tests/security/fixtures/goplus_token_security.sample.json`
- [+] `tests/security/fixtures/defi_enrichment.sample.json`
- [+] `.env.example`

## 4. Verification Strategy

### Unit tests
- Decision rules:
  - honeypot -> block
  - high tax -> warn/block based on cfg thresholds
  - not open source / dangerous ownership -> warn
  - missing data -> unknown
  - De.Fi no reputable audit -> warn for candidates

### Contract/fixture tests
- Normalization of GoPlus payload -> stable `SecuritySource` + derived reasons.
- Optional De.Fi enrichment:
  - success enriches result
  - failure yields `unknown` enrichment source but does not crash.

### Manual checks
- Run auditor on a known safe token and a known risky pattern (from fixtures) and confirm JSON output.

## 5. Implementation Checklist
- [x] Step 1: Define canonical security models (candidate/result/reason/source/config).
- [x] Step 1.1: Implement AssetClassifier (metadata + regex) and wire fail-safe gating for recommendations.
- [x] Step 2: Implement GoPlus client with retries/backoff/timeouts and basic caching.
- [x] Step 3: Implement decision rules mapping GoPlus flags -> reasons + status.
- [x] Step 4: Implement De.Fi enrichment client (contract address primary + protocol slug mapping) + mapping to reasons.
- [x] Step 5: Implement `auditor.py` orchestrator (Stage A + Stage B).
- [x] Step 6: Add fixtures + tests (rules + normalization).
- [ ] Step 7: Add `.env.example` entries and minimal docs for required env vars.
