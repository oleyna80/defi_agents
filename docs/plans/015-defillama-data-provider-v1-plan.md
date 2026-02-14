# Technical Plan: DeFiLlama Data Provider v1

Refers to Spec: `docs/specs/015-defillama-data-provider-v1.md`

## 1. Architecture Design

New components:
- `src/defi_agents/data/defillama_provider.py`
  - endpoint client methods + retry/timeout/cache
- `src/defi_agents/data/defillama_models.py`
  - normalized fact models (`YieldPoolFact`, `ProtocolFact`, etc.)
- `src/defi_agents/data/defillama_parsers.py`
  - pure parse/normalize functions (raw JSON -> typed facts)

Integration points:
- `src/defi_agents/scout/defillama_client.py`
  - migrate HTTP calls to provider
  - keep existing public methods for compatibility (`get_pools`, snapshots)
- `main.py`
  - keep orchestration unchanged; provider stays behind Scout APIs

## 2. Delivery Phases

### Phase A — Provider Foundation (safe, no behavior change)
- Add provider module and typed models.
- Implement `yields/pools` + `yields/poolsOld` + `yields/chart/{pool_id}`.
- Wire existing `DeFiLlamaClient` to provider for current flows only.
- Add endpoint counters/log line (provider_success/error/timeout/cache_hit).

DoD:
- Existing Scout behavior unchanged.
- Full test suite green.

### Phase B — Enriched Signals Exposure
- Expose and thread normalized extra fields to Scout candidate metadata:
  - `apy_mean_30d`, `apy_pct_30d`, `outlier`, `mu/sigma`, `il_risk`.
- Add helper methods for protocol/chains surfaces (without changing scoring yet).
- Add parser tests for missing/invalid fields.

DoD:
- New fields available in candidate/metadata with fail-safe defaults.
- No pipeline crashes on partial payloads.

### Phase C — Market Context Endpoints
- Add optional fetchers for:
  - overview/summary (`fees`, `dexs`, `options`, `bridge-aggregators`)
  - stablecoins and bridges snapshots
  - price current/historical
- Cache with endpoint-specific TTL (long TTL for heavy endpoints).
- Mark optional/unstable endpoints as non-blocking.

DoD:
- Provider returns typed facts or safe empty fallback.
- Counters include optional-endpoint failure stats.

### Phase D — Scout Usage for Ranking/Reporting (minimal impact)
- Add lightweight derived signals:
  - APY stability hint from `apy_mean_30d` and `apy_pct_30d`
  - outlier penalty flag
  - optional macro tags for report context
- Keep final gate semantics unchanged in v1 (no new hard blocks).

DoD:
- Ranking improves deterministically, with explicit metadata reasons.
- Telegram format stable, optional new tags behind config flag.

## 3. Config Changes

Add block in `ScoutConfig`:
- `defillama_provider.enabled` (default `true`)
- `defillama_provider.timeout_seconds` (default `8`)
- `defillama_provider.retry_attempts` (default `2`)
- `defillama_provider.cache_ttl_seconds` (family-specific map)
- `defillama_provider.enable_optional_market_surfaces` (default `false`)

Guardrails:
- Optional surfaces never block core Scout cycle.
- Large endpoints must be cache-backed.

## 4. Testing Strategy

Unit tests:
- parser tests per endpoint family (happy path + missing keys + type drift)
- retry/timeout/cache behavior tests for provider client
- counter/log formatting tests

Integration tests:
- `DeFiLlamaClient` parity tests against current behavior
- directional snapshot and lending snapshot regression
- end-to-end cycle smoke with provider enabled

Verification commands:
- `.venv/bin/pytest -q tests/test_lending_snapshot.py tests/test_notifier.py tests/test_scout.py`
- `.venv/bin/pytest -q`

## 5. Rollout Strategy

1) Land Phase A behind provider flag ON by default but behavior-parity guarded.
2) Observe 24h logs:
- no increase in cycle failures
- provider errors do not break cycle
3) Enable optional market surfaces in shadow mode (`enable_optional_market_surfaces=true`, no scoring impact).
4) Promote selected derived signals to ranking/reporting.

## 6. Risks & Mitigations

- Large payload latency:
  - mitigate with cache and bounded refresh.
- Upstream 5xx on certain categories:
  - mark optional and non-fatal.
- Schema drift:
  - pure parsers with default-safe coercion + regression fixtures.

## 7. Task Checklist

- [ ] Add provider models/parsers/client modules
- [ ] Wire `DeFiLlamaClient` to provider (Phase A)
- [ ] Add provider config block + defaults in `scout_config.json`
- [ ] Add tests (provider + parity)
- [ ] Implement enriched fields (Phase B)
- [ ] Add optional market surfaces (Phase C)
- [ ] Add ranking/report tags behind flags (Phase D)
- [ ] Update memory bank + roadmap pointers
