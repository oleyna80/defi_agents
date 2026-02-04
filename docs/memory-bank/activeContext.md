# Active Context

## Current Session Focus
Current Spec: docs/specs/007-pipeline-relaxation-v1.md
Current Plan: docs/plans/007-pipeline-relaxation-v1-plan.md
Active Task: Phase 2 pipeline relaxation v1 (funnel observability + stable-first intake + Lindy WARN bucket)

## Recent Changes
- 2026-02-01: Initialized project template
- 2026-02-01: Filled product context for Universal DeFi Sentinel
- 2026-02-01: Drafted concept spec for Universal DeFi Agent (Multi-Protocol)
- 2026-02-01: Reframed spec 001 as Monitoring module (Observer) v1
- 2026-02-01: Approved spec 002 and drafted plan 002 (Security Auditor v1)
- 2026-02-01: Drafted business process spec 003 (Step 1: Automated Scouting)
- 2026-02-01: Drafted business process spec 004 (Step 2: Reliability Scoring / Auditor)
- 2026-02-01: Drafted business process spec 005 (Step 3: Universal Monitoring / Observer)
- 2026-02-01: Implemented security models (pydantic) with TRUSTED status
- 2026-02-01: Added AssetClassifier and whitelist loader
- 2026-02-01: Implemented WhitelistProvider + GoPlus client + SecurityAuditor wiring
- 2026-02-01: Defined De.Fi identifier strategy + audit trust tiers (Tier A/B)
- 2026-02-01: Implemented DeFiClient with name->slug lookup and protocol cache
- 2026-02-01: Wired De.Fi enrichment into SecurityAuditor with aggregation logic
- 2026-02-01: Added audit tiers SSOT + Tier B/Certik logic in aggregation
- 2026-02-01: Drafted Scout spec + plan
- 2026-02-01: Implemented Scout models + DeFiLlama client
- 2026-02-01: Implemented Scout heuristics + SecurityAuditor integration
- 2026-02-01: Implemented Scout dedupe + tests (Step 5-6)
- 2026-02-01: Added Global scout config + main orchestrator + Telegram notifier
- 2026-02-01: Added semaphore throttling + env fallback + history.csv logging
- 2026-02-01: Ran first global cycle successfully (no crash, no candidates passed)
- 2026-02-02: Fixed Scout -> Auditor mapping (resolved contract address + normalized chain_id)
- 2026-02-02: Added L3 data models (judgment/tag/reason/evidence/metadata) to Scout models
- 2026-02-02: Implemented `L3AnalysisManager` with deterministic policy matrix and budget guardrail
- 2026-02-02: Added file-backed TTL cache (`docs/memory-bank/cache/l3_audit.json`) for L3 results
- 2026-02-02: Integrated L3 pipeline into `main.py` before final candidate filtering
- 2026-02-02: Extended history logging with L3 fields (`status`, `confidence`, `reason_codes`, `cache_hit`, `model`)
- 2026-02-02: Added L3 unit tests and re-ran full suite (all green)
- 2026-02-02: Implemented `src/defi_agents/config.py` SSOT constants (`EXTRACTOR_VERSION`, `L3_POLICY_VERSION`)
- 2026-02-02: Added `src/defi_agents/ai/extractor.py` with redirect-aware SSRF checks (IPv4/IPv6/private/link-local)
- 2026-02-02: Added `src/defi_agents/ai/provider.py` with DeepSeek integration, schema retry, and structured metadata
- 2026-02-02: Reworked `L3AnalysisManager` with dual cache (content 24h + analysis 72h) and per-domain jitter throttling
- 2026-02-02: Added mandatory security tests in `tests/test_extractor_security.py` (private IP, metadata IP, redirect attack, rebinding guard)
- 2026-02-02: Updated L3 model typing (`decision_rationale`, reason enums, metadata) and added `project_url` SSOT field
- 2026-02-02: Full suite + dry run green (`20 passed`, `main.py` no crash)
- 2026-02-02: Added reproducible dependencies manifest (`requirements.txt`)
- 2026-02-02: Added live L3 smoke script (`debug_l3_live.py`) and verified DeepSeek + Jina end-to-end
- 2026-02-02: Live check result (Ethena docs): `WARN` / `SOLID_RISK`, confidence `0.70`, extraction source `jina`
- 2026-02-02: Added project `Makefile` (`setup`, `test`, `run`, `live-l3`, `lint`, `clean`)
- 2026-02-02: Added GitHub Actions schedule `.github/workflows/sentinel-cycle.yml` (every 4 hours + manual dispatch)
- 2026-02-02: Added Systemd deployment templates (`deploy/systemd/*.service|*.timer`)
- 2026-02-02: Verified new DevEx commands (`make test`, `make run`, `make live-l3`) all green
- 2026-02-03: Added strict startup policy: no implicit Mock fallback when `ALLOW_MOCK_FALLBACK=false`
- 2026-02-03: Added lazy env helper `should_allow_mock_fallback()` in config SSOT
- 2026-02-03: Hardened notifier `_send` with async retries, backoff, and HTTP status checks
- 2026-02-03: Switched cache persistence to atomic temp-file writes (`os.replace`) with fail-loud errors
- 2026-02-03: Added root `.gitignore` for secrets/runtime artifacts
- 2026-02-03: Updated systemd templates to user-mode `%h` paths and timer-driven oneshot cycle
- 2026-02-03: Added VPS subdomain deployment pack (`deploy/vps`) with env template, nginx reverse-proxy template, and preflight script
- 2026-02-03: Patched `main.py` fail-fast flow (`run_sentinel_cycle` now re-raises after alert; process exits non-zero on unhandled cycle crash)
- 2026-02-03: Hardened `deploy/vps/preflight.sh` policy check (POSIX regex, hard-fail on `ALLOW_MOCK_FALLBACK=true`)
- 2026-02-03: Updated GitHub Actions workflow to manual-only trigger (removed 4h cron) to prevent scheduler overlap with VPS
- 2026-02-03: Applied runtime hardening on host (`ALLOW_MOCK_FALLBACK=false`, `.env` permissions `600`, preflight pass, user timer enabled + smoke run success)
- 2026-02-03: Migration blocker discovered: system-level `defi-sentinel` timer/service still active because sudo-auth is required in non-interactive session
- 2026-02-04: Completed systemd cleanup: system-level `defi-sentinel` units removed; user-mode timer is the single scheduler
- 2026-02-04: Updated `ROADMAP.md` with measurable DoD/metrics, Phase 2 funnel observability, explicit non-EVM strategy, Traffic-Light “fast lane”, and ops/hygiene items
- 2026-02-04: Approved Phase 2 policy direction: Lindy v1 thresholds (`TVL >= $100M`, `age >= 180d`), soften-only (audit/reputation), and 2-bucket output (`SAFE` vs `LINDY/WARN`)
- 2026-02-04: Drafted and approved spec+plan for Pipeline Relaxation v1 (`docs/specs/007-*`, `docs/plans/007-*`)
- 2026-02-04: Implemented Phase 2 v1 groundwork: stable-first + addressable-first audit selection, funnel metrics logging, expanded EVM chain-id mapping, and file-backed dedupe cache
- 2026-02-04: Fixed "everything BLOCK" root cause: De.Fi reputation adapter failures are now treated as `WARN` (reputation unavailable) instead of hard-blocking discovery
- 2026-02-04: Added Policy Matrix SSOT (`docs/memory-bank/security/policy_matrix_v1.md`) and linked it from spec/roadmap
- 2026-02-04: Phase 2 execution update: Scout now emits top rejection reasons, warns are reportable in Telegram buckets, and dedupe persists across oneshot systemd runs
- 2026-02-04: Runtime validation after Phase 2 changes: funnel now yields addressable warn candidates (`results=15`, `deduped=13`) and no longer stuck at hard-zero
- 2026-02-04: Updated gas/profit model for portfolio-scale ops (10k portfolio / 2.5k position): switched from `% deposit` gas cost to amortized round-trip USD gas with holding period
- 2026-02-04: Added dual score floors (`min_final_score` for SAFE, `min_warn_score` for WARN) and validated report output with positive monthly net values on top WARN candidates
- 2026-02-04: Extended roadmap with new Phase 2.5 (Investor Profiles & Allocation Engine) to support micro/standard/whale strategies and DCA flows
- 2026-02-04: Drafted and approved Spec/Plan for profile-aware selection (`docs/specs/009-*`, `docs/plans/009-*`)

## Open Questions / Decisions
- Debank Cloud auth requirements and rate limits
- Security adapters chosen: GoPlus (primary), De.Fi (secondary enrichment)
- Data contracts: normalized position schema shared by all modules
- LP imbalance metric definition (based on available data)
- Step 1 scouting exclusion decided: exclude leveraged/vault/bridged/synthetic categories at Step 1
- AssetClassifier integration: whitelist SSOT decided:
  - `docs/memory-bank/security/whitelist.json` (tokens + protocols)

## Next Steps
1. Finalize Lindy `age` source (pool age vs contract-age proxy) and document the chosen source in spec/policy matrix
2. Implement explicit Non-EVM unsupported reporting path (per-chain counters/tags, not only missing-chain totals)
3. Start Phase 2.5 implementation: profile schema + sleeves + capacity guards (`spec 009`)
4. Add heartbeat (daily "no opportunities" message) for healthy-but-silent cycles
