# System Patterns

## Architecture Decisions
- YYYY-MM-DD: <Decision> - <Rationale>
- 2026-02-01: Use aggregator APIs as universal adapters:
  - Discovery: DeFiLlama Yields API
  - Monitoring: Debank Cloud
  - Security: GoPlus Security (primary) + De.Fi (secondary enrichment)
  Rationale: avoid protocol-specific integrations; scale across chains/protocols.

- 2026-02-01: Security module strategy:
  - Stage A (dynamic): GoPlus checks for tokens/contracts + approvals monitoring
  - Stage B (reputation): De.Fi audit/REKT metadata to enrich candidate evaluation
  Rationale: API-first automation + granular flags (GoPlus), plus reputation context (De.Fi).

- 2026-02-01: Stablecoin tiering policy (Discovery/Security):
  - Tier 1 (OK by default): USDC, USDT, USDS
  - Tier 2 (Conditional): crvUSD (Curve/Convex), GHO (Aave), PYUSD (liquidity-conditional)
  - Tier 3 (Not OK by default / WARN): FRAX, USDe, LUSD
  Rationale: reduce false safety assumptions; drive deterministic recommendation rules.

- 2026-02-01: Discovery Step 1 (Scout) exclusion policy:
  - Exclude leveraged strategies, vault wrappers, bridged/synthetic stables by default.
  Rationale: keep daily top-10 conservative; defer exotic risk to explicit opt-in flows.

- 2026-02-01: Asset classification (echeloned, fail-safe):
  - Echelon 1 (DeFiLlama metadata): use `category` + `poolMeta` fingerprints.
  - Echelon 2 (regex, case-aware): detect bridged/synthetic/vault/leveraged patterns.
  - Echelon 3 (contract signature / proxy): confirm ERC-4626 (asset/totalAssets/convertToShares),
    detect risky proxies without timelock.
  - Policy: if classification is UNKNOWN and token is not Tier 1 stable (USDC/USDT/USDS) => BLOCK.
  - Manual override: maintain a local whitelist for explicitly approved UNKNOWN assets.

- 2026-02-01: Manual whitelist storage (SSOT):
  - Path: `docs/memory-bank/security/whitelist.json`
  - Purpose: explicit approvals for UNKNOWN assets/protocols to reduce opportunity cost while keeping fail-safe defaults.
  - Usage: Discovery and Security modules must consult this file before rejecting UNKNOWN non-Tier1 items.
  - Schema:
    - `manual_approvals.tokens.<address>` => `{ symbol, reason, added_at }`
    - `manual_approvals.protocols.<id_or_address>` => `{ name, reason, added_at? }`

- 2026-02-01: De.Fi enrichment identifiers + audit trust tiers:
  - Primary identifier: contract address.
  - Secondary: protocol slug from De.Fi response (used for audit history).
  - If no protocol mapping, apply reputation penalty (WARN).
  - Audit tiers:
    - Tier A: OpenZeppelin, Trail of Bits, Spearbit, Zellic
    - Tier B: Consensys Diligence, Sigma Prime, Nethermind, ChainSecurity
    - Excluded as sufficient alone: Quantstamp, Halborn
    - Low reputation (flag): CertiK
  - Audit tier definitions SSOT:
    - `docs/memory-bank/security/audit_tiers.json`

- 2026-02-01: Global Scout Mode:
  - `docs/memory-bank/scout_config.json` with `global_search: true` and empty `target_chains` means scan all chains.

- 2026-02-02: Scout -> Auditor strict identifier mapping:
  - Auditor input uses resolved `0x...` contract address + normalized `chain_id` (int -> string for adapter calls).
  - Address extraction heuristic:
    1) `address` field from DeFiLlama item (preferred, `POOL` target),
    2) fallback to first valid `underlyingTokens` address (`TOKEN` target).
  - Guardrail: unresolved address or unknown chain mapping => candidate skipped before security calls.
  - Rationale: avoid UUID/slug mismatch and reduce false `UNKNOWN`/mis-scans in Stage A/B.

- 2026-02-02: L3 AI-Analyst advisory layer (deterministic, not authoritative):
  - Stage order: Scout heuristics -> SecurityAuditor (L1/L2) -> L3AnalysisManager.
  - L3 gating:
    - Only `TRUSTED` / `PASS` from L1/L2 are eligible.
    - Only new/anomalous candidates are audited.
    - Budget cap: max 3 AI audits per cycle.
  - Decision matrix outputs final tags:
    - `ALPHA_STABLE`, `SOLID_RISK`, `AI_REJECT`, `AI_DOUBT`, `PENDING`, `AUDIT_LAG`.
  - Score adjustment uses `ai_security_factor` multiplier with hard reject on high-confidence `HIGH_RISK`.
  - Rationale: AI acts as risk advisory signal; it never overrides deterministic security blocks.

- 2026-02-02: File-backed TTL cache for L3:
  - Generic `CacheController` persists entries under `docs/memory-bank/cache/`.
  - L3 key format includes `chain_id`, `address`, doc-hash, prompt version, and model.
  - Default L3 TTL: 72h.
  - Rationale: reproducible outputs, lower latency/cost, and stable behavior across cycles.

- 2026-02-02: L3 production hardening (Plan 008 v3.1):
  - Added SSOT version constants:
    - `EXTRACTOR_VERSION` (content extraction behavior)
    - `L3_POLICY_VERSION` (decision matrix behavior)
  - Introduced dual-cache strategy:
    - L1 content cache (24h): `hash(url)`
    - L2 analysis cache (72h): `hash(chain:address:content_hash:provider:model:prompt_ver:extractor_ver:policy_ver)`
  - Rationale: deterministic cache invalidation when extraction/policy logic changes.

- 2026-02-02: Enterprise SSRF protections for documentation extraction:
  - Redirect-aware URL validation at each hop (max 5).
  - DNS/IP checks for IPv4/IPv6 private, loopback, link-local, carrier-grade ranges.
  - Scheme/port restrictions (`http/https`, ports 80/443), localhost blocked.
  - Response byte cap (4MB) and sanitized text output.
  - Rationale: prevent internal network access and rebinding/redirect SSRF bypasses.

- 2026-02-02: L3 provider error discipline:
  - DeepSeek provider (`https://api.deepseek.com/v1`) with one schema-validation retry.
  - `ERROR`/`INCONCLUSIVE` mapping is deterministic:
    - Technical failures (`SSRF_BLOCKED`, `JSON_PARSE_FAIL`, `RATE_LIMIT_HIT`) -> `AUDIT_LAG`, penalty `k=0.5`.
    - Data insufficiency (`NO_DATA`, `EXTRACTION_FAILED`) -> `PENDING`, penalty `k=0.5`.
  - Rationale: preserve fail-safe behavior and avoid AI hallucination-driven recommendations.

- 2026-02-02: Operational command contract via Makefile:
  - Canonical local commands:
    - `make setup` (venv + deps)
    - `make test` (full suite under `.venv`)
    - `make run` (single cycle)
    - `make live-l3` (isolated real provider smoke test)
  - Rationale: one-command reproducibility and reduced operator error.

- 2026-02-02: Dual deployment bootstrap prepared:
  - CI schedule: `.github/workflows/sentinel-cycle.yml` (manual + every 4h).
  - Host schedule: `deploy/systemd/defi-sentinel.{service,timer}`.
  - Rationale: support both GitHub-hosted automation and self-hosted VPS runtime with identical entrypoint (`main.py`).

- 2026-02-03: Strict provider initialization policy (no silent Mock in production):
  - Added lazy env gate `should_allow_mock_fallback()` for runtime decisioning after `.env` load.
  - `main.py` and `L3AnalysisManager` now fail fast when DeepSeek init fails and fallback is disabled.
  - Rationale: avoid false confidence where L3 appears active but is actually served by mock responses.

- 2026-02-03: Cache write durability pattern:
  - Replaced direct JSON writes with atomic temp-file swap (`os.replace`).
  - Save errors are logged and re-raised (fail-loud) to preserve operational visibility.
  - Rationale: prevent truncated/partial cache files and silent persistence failures.

- 2026-02-03: Notification reliability pattern:
  - Telegram sender now retries with async backoff and enforces HTTP status handling.
  - Rationale: transient network/API failures should not silently drop alerts.

- 2026-02-03: VPS runtime standardization:
  - Systemd templates switched to user-mode (`%h` paths) with timer-triggered oneshot service.
  - Rationale: portable deploys across users/hosts without hardcoded account names.

- 2026-02-03: Subdomain migration pattern for VPS:
  - Added deployment pack `deploy/vps/` with:
    - environment template (`env.vps.example`),
    - reverse-proxy template for HTTPS subdomain (`nginx/*.conf.example`),
    - preflight verifier script (`preflight.sh`).
  - Runtime remains timer-driven bot by default; subdomain is optional until webhook/API endpoints are enabled.
  - Rationale: consistent cutover process with minimal downtime and fewer configuration mistakes.

- 2026-02-03: Fail-fast cycle propagation pattern:
  - `run_sentinel_cycle()` must re-raise on fatal cycle exceptions after best-effort Telegram error alert.
  - `__main__` must treat unhandled cycle exceptions as process-fatal and exit non-zero.
  - Rationale: prevent silent-success (`status=0`) in systemd when cycle logic fails.

- 2026-02-03: Production policy guardrail for mock fallback:
  - `deploy/vps/preflight.sh` enforces strict mode with a POSIX-safe regex check for
    `ALLOW_MOCK_FALLBACK=true` and hard-fails deployment.
  - Rationale: avoid accidental mock operation in production.

- 2026-02-03: Single-scheduler runtime policy:
  - When VPS timer is primary runtime, GitHub workflow trigger remains manual-only (`workflow_dispatch`);
    periodic `schedule` is disabled to avoid duplicate cycles.
  - Rationale: prevent overlapping executions, duplicate alerts, and external API rate-limit pressure.

- 2026-02-04: Pipeline relaxation v1 (Lindy soften-only + bucketed output):
  - Lindy v1 thresholds: `TVL >= $100M` and `age >= 180d`.
  - Lindy applies only to missing-audit / missing-reputation signals (downgrade to `WARN`), never to critical technical red flags.
  - Output is explicitly split into two buckets:
    - `SAFE` (strict shortlist)
    - `LINDY/WARN` (manual review shortlist; risk-tagged)
  - Rationale: increase actionable signal while keeping hard anti-scam invariants.

- 2026-02-04: Funnel observability pattern:
  - Each cycle emits stage counters and top rejection reasons to explain "why 0 candidates".
  - Rationale: tuning must be data-driven; reduces operator guesswork and prevents unsafe over-relaxation.

- 2026-02-04: Security policy matrix as SSOT:
  - Canonical rules for SAFE/WARN/BLOCK/UNSUPPORTED are documented in:
    - `docs/memory-bank/security/policy_matrix_v1.md`
  - Rationale: prevents policy drift between Scout/Security/L3 layers and keeps tuning auditable.

- 2026-02-04: Stage B reputation availability semantics:
  - If reputation enrichment fails due to upstream/API error, treat as `WARN` with reason `REPUTATION_UNAVAILABLE`.
  - Do not hard-block discovery purely because the reputation provider is down/unreachable.
  - Rationale: avoid "everything BLOCK" failure mode; keep hard-blocks reserved for technical scam flags.

- 2026-02-04: Persistent anti-spam dedupe for oneshot schedulers:
  - Deduper state is persisted under `docs/memory-bank/cache/` so timer-driven oneshot runs can suppress repeats across processes.
  - Rationale: prevent Telegram spam; in-memory dedupe is ineffective under oneshot systemd timers.

- 2026-02-04: Stable-first + addressable-first audit budget allocation:
  - Scout prioritization order for audit budget:
    1) stable tier (`LOW_VOLATILITY` -> `COIN_STABLE` -> `COIN_COIN`)
    2) addressable candidates (`address + chain_id`)
    3) higher TVL
    4) preliminary yield score
  - Rationale: maximize useful security checks under limited API budget.

- 2026-02-04: Dual-threshold reporting pattern:
  - `SAFE` shortlist remains strict (`min_final_score`).
  - `WARN` shortlist uses a lower floor (`min_warn_score`) and explicit bucket tagging.
  - Rationale: avoid "silent zero" while preserving conservative SAFE criteria.

## Conventions
- Naming:
- Testing:
- Formatting:
- Error handling:

## Tech Stack
- ...
