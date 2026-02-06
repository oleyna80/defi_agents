# Active Context

## Current Session Focus
Current Spec: docs/specs/012-defi-coverage-mvp-dex-lp.md
Current Plan: docs/plans/012-defi-coverage-mvp-dex-lp-plan.md
Active Task: DEX/LP discovery implementation plan (Workstream A)

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
- 2026-02-04: Implemented profile/sleeve/capacity schema in Scout config (`investor_profile`, `sleeves`, `capacity_guards`) and synced defaults in `docs/memory-bank/scout_config.json`
- 2026-02-04: Implemented profile-aware selection in Scout: tactical sleeve gating, position sizing by risk profile, capacity guard filtering, cost-dominated filtering, benchmark tagging/score factor
- 2026-02-04: Updated Telegram report formatting with sleeve + benchmark tags; added tests for micro-vs-whale capacity behavior, tactical gating, and benchmark metadata (`28 passed`)
- 2026-02-04: Applied logging hardening to prevent secret leakage in runtime logs: raised `httpx/httpcore` to WARNING and removed raw HTTP exception/URL logging in Telegram notifier
- 2026-02-04: Added report clarity tuning: split Telegram output into `ACTIONABLE` vs `WATCHLIST`, added explicit WARN reason codes, and tightened bucket labels (`WARN/REPUTATION`, `WARN/SECURITY`)
- 2026-02-04: Added notifier formatting tests (`tests/test_notifier.py`) and validated full suite (`30 passed`)
- 2026-02-04: Reworked Telegram report into universal "Decision View": focus on chain/pair/project/APY/TVL/risk, color badges, pair-type sorting (`stable/stable`, `token/stable`, `token/token`)
- 2026-02-04: Added standardized comparability metric `Net@1k` (instead of user-specific position size) in report metadata/output
- 2026-02-04: Implemented intake expansion for audit stage: increased `max_audit_candidates` to 40 and added configurable exploration quota (`exploration_slots`) for high-APR stable-focused discovery
- 2026-02-04: Added scout test coverage for exploration quota behavior; full suite green (`31 passed`)
- 2026-02-04: Fixed Telegram delivery reliability after report expansion: added safe message chunking for long Markdown reports to stay under Telegram size limits
- 2026-02-04: Revalidated full test suite after intake/report updates (`32 passed`) and smoke-run without runtime failures
- 2026-02-04: Added direct DefiLlama pool hyperlinks in Telegram report rows (`[Pool](https://defillama.com/yields/pool/<pool_id>)`) for faster decision workflow
- 2026-02-04: Drafted and approved Spec/Plan 010 for freshness re-check v1 (`docs/specs/010-*`, `docs/plans/010-*`)
- 2026-02-04: Updated roadmap/indexes to include Phase 2 freshness workstream (decision-grade actionable gating)
- 2026-02-04: Phase A (spec 010) implemented: added `freshness` config schema, freshness metadata wiring, downgrade policy scaffold, and cycle counters (`rechecked/fresh/stale/unverified/diverged/downgraded`)
- 2026-02-04: Telegram report now includes freshness/delta fields; added unit tests for freshness policy and report rendering (`35 passed`)
- 2026-02-04: Applied output-volume tuning preset: `exploration_slots=15`, `exploration_stable_only=false`, and configurable dedupe TTL (`dedupe_ttl_seconds=14400`) to reduce over-pruning
- 2026-02-04: Cleared persisted scout dedupe cache and validated broader report mix in dry run (`LOW_VOLATILITY`, `COIN_STABLE`, `COIN_COIN`)
- 2026-02-04: Ingested external research findings into roadmap for freshness Phase B/C/D: source shortlist (`Uniswap`, `Aave`, `Morpho`) and rollout sequence with explicit threshold baselines
- 2026-02-04: Added research artifact to repository: `docs/research/2026-02-dex-lending-direct-api-research.md`
- 2026-02-04: Completed Phase B (spec 010) MVP adapter: added `FreshnessManager` + `UniswapSubgraphAdapter` (chain-aware endpoints, timeout, safe fallback), wired into pre-alert stage
- 2026-02-04: Added adapter/manager tests (`tests/test_uniswap_adapter.py`, `tests/test_freshness_manager.py`); full suite green (`39 passed`)
- 2026-02-04: Expanded freshness source registry to non-Ethereum chains using Graph subgraph IDs (`Ethereum`, `Arbitrum`, `Base`, `BSC/Binance`, `Avalanche`) and optional `GRAPH_API_KEY` env wiring
- 2026-02-04: Added `AerodromeSubgraphAdapter` scaffold (project-keyword routing for `aerodrome/slipstream/velodrome`) with explicit safe fallback to `UNVERIFIED` when endpoint/key is missing
- 2026-02-04: Revalidated full suite after Phase C changes (`42 passed`)

- 2026-02-05: Added ops runbook for Strategy Simulator v1 safe activation and debug checklist (`docs/runbooks/strategy_sim_v1_ops.md`) — 2026-02-05
- 2026-02-05: Validated Strategy Simulator v1 on VPS with temporary loosened filters; StrategySim summary observed; PARTIAL/UNSUPPORTED downgraded to WATCHLIST; reverted to production thresholds and `strategy_sim.enabled=false` — 2026-02-05
- 2026-02-05: Adjusted Telegram report to hide StrategySim fields unless `SimStatus=OK` (v1.1 noise control) and added notifier tests — 2026-02-05
- 2026-02-05: Added DeFi Coverage Blueprint to roadmap as master plan (coverage + unified data contract + risk/freshness/strategy/ops/decision view) — 2026-02-05
- 2026-02-05: Ingested DeFi data sources MVP research into `docs/research/2026-02-defi-data-sources-mvp.md` — 2026-02-05
- 2026-02-05: Drafted MVP execution plan for data sources integration (`docs/plans/012-defi-coverage-mvp-plan.md`) — 2026-02-05
- 2026-02-05: Unified plan updated to include freshness C+/D and ops items (non‑EVM visibility, heartbeat) — 2026-02-05
- 2026-02-05: Drafted DEX/LP discovery spec for DeFi coverage MVP (`docs/specs/012-defi-coverage-mvp-dex-lp.md`) — 2026-02-05
- 2026-02-05: Drafted DEX/LP discovery implementation plan (`docs/plans/012-defi-coverage-mvp-dex-lp-plan.md`) — 2026-02-05
- 2026-02-05: Added RooCode agent skills (SSOT prompts) under `.roo/skills/` for memory sync, prod-safe review, spec writing, and VPS ops ask-first — 2026-02-05
- 2026-02-05: Expanded RooCode skills pack for project operations (funnel debug, freshness rollout, safe config edits, report quality, adapter engineering) — 2026-02-05

## Open Questions / Decisions
- Debank Cloud auth requirements and rate limits
- Security adapters chosen: GoPlus (primary), De.Fi (secondary enrichment)
- Data contracts: normalized position schema shared by all modules
- LP imbalance metric definition (based on available data)
- Step 1 scouting exclusion decided: exclude leveraged/vault/bridged/synthetic categories at Step 1
- AssetClassifier integration: whitelist SSOT decided:
  - `docs/memory-bank/security/whitelist.json` (tokens + protocols)

## Next Steps
1. Rotate Telegram bot token on VPS (old token appeared in historical logs before hardening) and restart user service
2. Populate VPS `.env` with `GRAPH_API_KEY` and configure `aerodrome_subgraph_{endpoints|ids}` for Base, then run freshness smoke checks
3. Implement lending Phase C+ adapter: replace deprecated `aave-api-v2` path with current Aave source contract (official API/subgraph)
4. Enable and calibrate strict freshness gating on VPS (`recheck_enabled=true`, then `enforce_freshness_for_actionable=true`) after telemetry baseline
5. Finalize Lindy `age` source (pool age vs contract-age proxy) and document the chosen source in spec/policy matrix
6. Implement explicit Non-EVM unsupported reporting path (per-chain counters/tags, not only missing-chain totals)
7. Add heartbeat (daily "no opportunities" message) for healthy-but-silent cycles
