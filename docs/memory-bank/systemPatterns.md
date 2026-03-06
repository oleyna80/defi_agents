# System Patterns

## Architecture Decisions
- YYYY-MM-DD: <Decision> - <Rationale>
- 2026-03-04: LP Entry target scope is a config-driven pre-build filter over LP-eligible candidates with canonical pair matching and explicit empty-target marker:
  - runtime applies target scope before `build_entry_recommendations(...)` using `lp_entry_targeting` (`target_pair`, `allowed_chains`, `allowed_projects`, optional `top_n`),
  - pair matching uses normalization only for filtering (`ETH/USDT` ↔ `WETH-USDT`), while displayed symbols remain unchanged,
  - telemetry emits deterministic target counters (`entry_target_scope_enabled`, `entry_target_input_total`, `entry_target_matched_total`, `entry_target_excluded_total`) and machine-readable `entry_target_reason=TARGET_SCOPE_EMPTY` when no matches.
  Rationale: enable operator-targeted cross-network/cross-venue LP search without widening runtime blast radius or weakening existing fail-safe downgrade invariants.

- 2026-03-04: LP Entry target scope filtering and telemetry accounting are full-scope and pair-strict:
  - pair normalization/validation accepts only deterministic two-token symbols (e.g., `ETH/USDT`, `WETH-USDT`), rejecting ambiguous `3+` token symbols,
  - when target scope is enabled, runtime applies matching consistently to both LP-eligible and LP-ineligible recommendation paths, preventing non-target watchlist leakage into target reports,
  - target counters are computed over full recommendation input (`eligible + ineligible`) so `matched + excluded = input` per cycle.
  Rationale: avoid subtle recommendation/report drift and counter-math inconsistencies in target mode under partial/degraded market universes.

- 2026-03-04: LP Entry actionability must be seeded before StrategySim policy and evaluated from seed state (not mutable post-sim `report_group`):
  - runtime writes pre-sim seed fields (`lp_entry_seed_report_group`, `lp_entry_seed_watchlist_reason`) immediately before StrategySim policy,
  - LP entry builder consumes seed fields first, so generic sim policy downgrades do not structurally suppress LP-eligible/range-ready actionability,
  - fail-safe LP gates remain authoritative (`TICK_DATA_DEGRADED`, `SOURCE_CONFIDENCE_*`, `FRESHNESS_STALE`, range/stability gates).
  Rationale: keep StrategySim observability/guardrails intact while decoupling LP entry decision contract from generic sim limitations (`PARTIAL/UNSUPPORTED`).

- 2026-03-04: StrategySim policy downgrade reasons are machine-readable reason-codes only:
  - `strategy_sim.apply_policy(...)` writes deterministic reason codes for downgrade events (`SIM_STATUS_PARTIAL`, `SIM_STATUS_UNSUPPORTED`, `SIM_RISK_ABOVE_PROFILE`) into metadata (`watchlist_reason`, `sim_policy_reason`),
  - free-text downgrade reasons are not used on this path.
  Rationale: stable telemetry taxonomy for LP/actionable evidence, deterministic aggregation, and operator-safe runbook interpretation.

- 2026-03-03: LP Entry actionable contract must be LP-scoped before ranking, not applied to the whole report shortlist:
  - `EntryRecommendation` input should be explicitly filtered to LP-eligible candidates (`yield_type=lp_fees` + range/tick-capable venue path),
  - telemetry must expose coverage chain `input -> lp-eligible -> range-ready` to localize where actionable candidates are lost,
  - generic fallback reasons (`REPORT_GROUP_WATCHLIST`) are not sufficient for actionable-enablement diagnostics and must be replaced by deterministic reason taxonomy.
  Rationale: current evidence shows `actionable_ratio=0` is primarily a scope/coverage issue (many candidates never enter valid range path), not only ranking/calibration.

- 2026-03-03: LP Entry actionable-enablement telemetry is reason-coded and blocker-aware as a deterministic runtime/evidence contract:
  - runtime emits cycle-level `watchlist_reason_counts` for LP entry output (machine codes only; free-text reasons are normalized to deterministic fallback),
  - tick-density readiness emits explicit blocker counters (`GRAPH_API_KEY_MISSING`, provider/subgraph init/schema blockers) as separate telemetry line,
  - shadow-calibration snapshot aggregates both reason and blocker counters and evaluates explicit gate `actionable_ratio_positive_pass` (`actionable_ratio > 0`),
  - when actionable gate fails, report tooling must emit top-3 watchlist reasons for operator triage.
  Rationale: convert `all WATCHLIST` diagnosis from ad-hoc log reading into deterministic, machine-parseable evidence while preserving fail-safe downgrade behavior.

- 2026-03-03: Calibration phase can be closed with a `KEEP` decision when full evidence gate passes without retune:
  - phase closure criterion is deterministic gate pass on required window (`telemetry_min_cycles`, error-free parsing/runtime),
  - parameter changes are optional and only justified when evidence indicates improvement need,
  - `KEEP` is a valid outcome when current defaults already satisfy gate checks.
  Rationale: avoid unnecessary parameter drift and preserve stable fail-safe behavior.

- 2026-03-03: Calibration gate thresholds are validated as a hard contract before evaluation:
  - threshold bundle creation fails fast on invalid values (`telemetry_min_cycles < 1`, any ratio/churn threshold outside `[0,1]`, or `max_topn_churn_avg > max_topn_churn_p95`),
  - CLI returns structured JSON error for invalid threshold inputs instead of silently producing misleading gate results.
  Rationale: prevent operator/config mistakes from generating false pass/fail calibration evidence.

- 2026-03-03: LP Entry SHADOW calibration evidence is evaluated via deterministic telemetry snapshot gates, and controlled retune is blocked when evidence window is insufficient:
  - telemetry parser targets only explicit runtime signature `LP entry stability telemetry: ...` and computes fixed aggregates/gates,
  - gate contract includes explicit booleans (`errors_zero_pass`, `telemetry_min_cycles_pass`, churn/history ratio checks) with CLI-configurable safe defaults,
  - when baseline FAIL is caused by missing telemetry volume (e.g., `cycles_with_entry_telemetry=0`), decision stays `KEEP` (no config retune) to avoid parameter fitting on absent data.
  Rationale: preserve fail-safe, evidence-first calibration discipline and keep retune actions reversible and justified by sufficient SHADOW observations.

- 2026-03-03: Stability gate observation counting uses cycle observation time from history rows, not upstream source timestamps:
  - `save_to_history()` writes wall-clock cycle timestamp into history `timestamp`,
  - stability window checks (`>=N observations / H hours`) now reflect actual repeated cycle observations,
  - stale provider timestamps no longer force false `INSUFFICIENT_STABILITY_HISTORY` downgrades.
  Rationale: provider/source timestamps are freshness signals, not reliable evidence of repeated runtime observations in the gate window.

- 2026-03-03: LP Entry Recommendation P1 adds history-backed stability gating and deterministic Top-N churn telemetry as a separate layer on top of existing fail-safe contract:
  - actionable eligibility now requires minimum history observations in a rolling window (`stability_min_observations`, `stability_observation_window_hours`) sourced from `docs/memory-bank/history.csv`,
  - insufficient history explicitly downgrades to `WATCHLIST` with reason `INSUFFICIENT_STABILITY_HISTORY`,
  - runtime emits deterministic counters `entry_total`, `entry_actionable`, `entry_watchlist`, `entry_watchlist_insufficient_history`, `entry_topn_churn`,
  - previous Top-N snapshot is persisted via cache namespace (`lp_entry_topn_stability`) to compute churn between cycles.
  Rationale: improve recommendation stability and observability for shadow calibration without changing the existing fail-safe downgrade policy for degraded/stale/diverged/invalid-range states.

- 2026-03-03: LP Entry rank/confidence calibration remains config-driven and reversible, with no auto-optimization:
  - calibration knobs are centralized in `ScoutConfig.lp_entry_calibration`,
  - scoring knobs are limited to factor/threshold parameters (`source_confidence_factors`, confidence thresholds, rank powers, economics cap),
  - runtime only consumes configured values; it does not mutate thresholds based on runtime outcomes.
  Rationale: keep P1 calibration safe and operator-controlled while preserving fail-closed behavior and rollback simplicity.

- 2026-03-03: For critical P0 implementation tracks, Roo orchestration uses a paired-skill pattern:
  - one skill defines strict implementation scope/order (`implementation-contract`),
  - second skill defines mandatory verification matrix and fail-safe assertions (`test-gate-contract`).
  Rationale: reduces scope drift between plan and code and keeps handoff/review deterministic across multi-agent execution.

- 2026-03-03: Decision-grade LP allocation features follow a strict stage order `task-definition -> research-gate -> implementation` before any runtime wiring:
  - target output must be fixed upfront as explicit contract (`network + protocol + pair + range + confidence/reasons`),
  - research phase produces scoring/range policy and gap map as separate artifact,
  - development starts only after policy sign-off to avoid iterative drift between roadmap and code.
  Rationale: current code already has partial scanner primitives, but without contract-first gating it is easy to ship inconsistent output-hooks that do not close the product goal.

- 2026-03-03: LP entry recommendation in runtime follows a fail-closed two-lane contract (`ACTIONABLE` vs `WATCHLIST`) with deterministic Top-N ordering:
  - scanner metadata is SSOT for range fields (`pit_type`, `pits_found`, `suggested_range_lower_tick`, `suggested_range_upper_tick`),
  - recommendation rank is deterministic (`rank_v1`) with stable tie-breakers and explicit confidence bands,
  - any degraded tick quality, stale/diverged confidence, or invalid/missing range is force-downgraded to `WATCHLIST`,
  - notifier renders a dedicated `LP Entry Recommendations` block without replacing existing Decision View blocks.
  Rationale: keep P0 behavior transparent and auditable while preventing false-actionable suggestions under partial/invalid data.

- 2026-03-03: Gate-3 evidence collector is position-aware and emits both window-level and position-level pass signals in a single JSON snapshot:
  - log-window counters remain (`reader_ok`, `sim_fail`, `errors`),
  - reader samples are embedded as `position_samples` with computed `position_pnl_usd/hodl_pnl_usd/pnl_vs_hodl_usd`,
  - minimum valid positions are enforced via `position_samples_min_pass` (`--min-positions`, default `3`).
  Rationale: eliminate split evidence collection (manual reader dump + separate gate report) and keep Gate-3 decision artifacts deterministic.

- 2026-03-02: Gate-3 evidence intake for reader/SHADOW is script-driven instead of ad-hoc log parsing:
  - `scripts/gate3_evidence_report.py` is the canonical evidence snapshot command (`make gate3-evidence-report`),
  - parser logic is centralized in `src/defi_agents/execution/gate3_evidence.py`,
  - output includes both preflight blockers (`wallet_set`, `rpc_set`, baseline count) and runtime counters (`reader_ok`, `sim_fail`, `errors`) with explicit gate booleans.
  Rationale: avoid manual counting drift and keep Gate-3 PASS/FAIL decisions reproducible.

- 2026-03-02: Test gate for async suites is fail-fast by plugin contract, not warning-based:
  - `pytest.ini` requires `pytest-asyncio` (`required_plugins=pytest-asyncio`),
  - asyncio execution uses strict mode (`--asyncio-mode=strict`),
  - environments without async plugin now fail explicitly instead of silently skipping async tests.
  Rationale: prevent false-green CI/local runs where async coverage is unintentionally dropped.

- 2026-03-01: Real-position P&L/HODL in reader path uses deterministic file-backed entry baseline provider with explicit reason-coded degradation:
  - baseline source is `docs/memory-bank/position_entry_baselines.json` with deterministic key `position_ref=uni-v3:<token_id>`,
  - reader emits `entry_value_usd`, `hodl_value_usd`, `net_pnl_usd`, `pnl_vs_hodl_usd` only when baseline and valuation inputs are valid,
  - baseline source/entry failures are explicit and non-throwing (`ENTRY_BASELINE_MISSING`, `ENTRY_BASELINE_INCOMPLETE`, `ENTRY_BASELINE_MALFORMED`), preserving fail-safe reader-only NO-ACTION semantics.
  Rationale: close Phase 3.0 integrity gap for real-position analytics without introducing hidden sync side effects, fake P&L values, or execution-path regressions.

- 2026-03-01: Real-position valuation is introduced as a staged integrity contract before full P&L/HODL:
  - `ArbitrumUniswapV3PositionReader` computes `position_value_usd` from on-chain liquidity + ticks (`LIQUIDITY_TICK_MODEL_V1`),
  - valuation quality is explicit in reason-codes (`TOKEN_DECIMALS_MISSING`, `STALE_PRICE`, `POSITION_MATH_INVALID`) instead of silent zeros,
  - unrealized `P&L/HODL` stays fail-transparent via explicit baseline-gap reason (`ENTRY_BASELINE_MISSING`) until entry snapshot/history ingestion is implemented.
  Rationale: closes the most critical state-integrity gap for execution decisions now, without faking `P&L/HODL` before reliable entry baselines exist.

- 2026-03-01: Deprecated config fields can be retained as explicit legacy-only schema contracts after runtime migration:
  - `execution.mock_positions` remains in `ExecutionConfig` for backward-compatible config shape,
  - field is explicitly marked deprecated in schema (`json_schema_extra.deprecated=true`) and documented as runtime-ignored,
  - sample runtime config must not seed deprecated operational payloads to avoid operator drift.
  Rationale: preserve non-breaking config loads while making the new runtime source of truth (reader-only execution states) unambiguous.

- 2026-03-01: Execution state source for LP execution loop is fail-closed and reader-only (no mock fallback in runtime):
  - `main.py::_load_execution_states()` now returns empty state-set when wallet/RPC/reader data is unavailable,
  - execution loop is skipped safely on empty state-set; it does not load `execution.mock_positions` fallback,
  - stale-state protection remains explicit via `STALE_POSITION_DATA` reason path (warning telemetry + LIVE policy block).
  Rationale: Gate-3/LIVE readiness requires removing hidden mock dependency while preserving fail-safe `NO_ACTION` behavior under degraded data conditions.

- 2026-02-26: SHADOW hedge gate can use local connector mock service to decouple runtime validation from external exchange uptime:
  - lightweight HTTP mock (`scripts/hummingbot_shadow_mock.py`) exposes `health/markets/ticker` contracts expected by `HummingbotShadowConnector`,
  - service is run as user unit (`hummingbot-shadow-mock.service`) and can be enabled/disabled independently from `defi-hedger.timer`,
  - real Hummingbot endpoint remains preferred for connector-readiness, but mock path is accepted for deterministic gate warm-up and regression on host.
  Rationale: enables reproducible SHADOW telemetry (`sim_ok`, reason taxonomy, no-crash checks) even when external connector infra is not yet provisioned.

- 2026-02-26: Hedger shadow/runtime telemetry uses parseable summary lines and windowed gate script:
  - worker entrypoint `hedger_main.py` emits deterministic counters in `Hedger summary:` logs,
  - gate script `scripts/hedger_shadow_gate_report.sh` aggregates 24h cycles/sim/connectivity metrics from `journalctl`,
  - no connector or connector exceptions are fail-safe counted (`CONNECTOR_UNCONFIGURED` / `CONNECTOR_EXCEPTION`) rather than treated as silent success.
  Rationale: Phase D gate requires objective, scriptable evidence for GO/NO-GO without coupling to scout runtime logs.

- 2026-02-26: Hedger orchestration separates intent generation from connector simulation:
  - `HedgeCalculator` generates deterministic intents/counters from exposure inputs,
  - `HedgerOrchestrator` applies mode semantics (`PAPER` no simulation, `SHADOW` simulation-only),
  - connector failures are reason-counted and never raise uncaught exceptions from per-intent processing.
  Rationale: preserves deterministic strategy logic while isolating unstable connector surfaces behind fail-safe boundaries.

- 2026-02-26: Hedger connector readiness is modeled as staged health probe + shadow simulation:
  - health probe runs explicit stages (`auth` -> `instrument` -> `bbo`) and returns typed status object,
  - shadow simulation consumes the same connector path and enforces slippage caps before reporting `ok`,
  - connector failures map to deterministic reason codes (`AUTH_FAILED`, `MARKET_UNSUPPORTED`, `BBO_UNAVAILABLE`, `CONNECTOR_HTTP_*`, etc.) instead of exceptions escaping to runtime.
  Rationale: supports safe rollout gates and auditable NO-ACTION outcomes while external connector contracts are unstable.

- 2026-02-26: Hedger decision engine uses deterministic delta-to-intent pipeline with fail-safe skip taxonomy:
  - action order: policy/data guards -> threshold/cooldown -> hedge side selection,
  - positive LP delta maps to `SHORT` hedge, negative delta maps to `LONG`,
  - policy/data failures emit explicit `SKIP` reasons (`KILL_SWITCH_ENABLED`, `MAX_*`, `EXPOSURE_STALE`, `MARK_PRICE_MISSING`) and never attempt implicit hedge.
  Rationale: keep hedge behavior auditable and safe before connector/live execution stages.

- 2026-02-26: Hedger configuration is fail-closed by default and isolated from scout loop:
  - `ScoutConfig.hedger` defaults to `enabled=false`, `mode=PAPER`, `connector=none`,
  - `LIVE` mode is blocked unless explicit `hedger.allow_live_mode=true`,
  - policy limits (`max_notional_per_order`, `max_daily_notional`, `kill_switch`) are first-class config contract.
  Rationale: hedge execution path carries liquidation/funding risk and must require explicit operator opt-in with hard limits.

- 2026-02-26: Delta hedger exploration follows isolated-worker pattern:
  - hedge PoC runtime is a separate process/module boundary from scout/execution loop,
  - hedge path is limited to `PAPER/SHADOW` until dedicated spec gate,
  - connector/data degradation must default to `NO_ACTION` (fail-safe).
  Rationale: hedging introduces liquidation/basis/funding risk and must not increase blast radius of core production loop.

- 2026-02-26: Open-source reuse follows a license-first boundary policy:
  - direct in-tree code reuse is allowed only for permissive licenses (`MIT`, `Apache-2.0`),
  - copyleft/source-available stacks (`AGPL`, `GPL`, `BUSL`) are reference-only for core runtime,
  - repos with unclear license metadata are blocked until explicit legal clarification.
  Rationale: preserve delivery speed from ecosystem patterns without introducing licensing risk into the production codebase.

- 2026-02-23: Structured `v3utils` payloads are simulation-validated before live send:
  - for structured compound/rebalance payloads, adapter `simulate()` checks expected selector and target contract consistency,
  - mismatches are fail-safe rejected with explicit reason codes (`V3UTILS_SELECTOR_MISMATCH`, `V3UTILS_CONTRACT_MISMATCH`).
  Rationale: prevent accidental live sends with malformed or mismatched encoded calldata.

- 2026-02-23: v3utils compound calldata supports structured parameter encoding in adapter:
  - adapter accepts `v3utils_compound_params` (nfpm/token_id/instructions),
  - builds ABI calldata for `V3Utils.execute(...)` internally (selector `0xfd2d17d1`),
  - keeps fallback to pre-encoded `*_data_hex` for compatibility during migration.
  Rationale: move from manual hex payloads to typed intent metadata without breaking existing runs.

- 2026-02-23: External execution-module reuse is commit-pinned with local ABI bundle snapshots:
  - `v3utils` adapter references pinned upstream commit metadata (`33f487...`) in tx metadata,
  - local ABI/address snapshot bundle is stored under `src/defi_agents/execution/abi/`,
  - ABI asset presence/shape is covered by regression tests (`test_execution_v3utils_abi_assets.py`).
  Rationale: prevent silent drift of upstream contract interfaces/addresses during staged live rollout.

- 2026-02-23: `v3utils` integration is introduced as feature-flagged adapter scaffold, not a hard runtime dependency:
  - adapter key `v3utils` is available in execution routing,
  - activation requires explicit `execution.v3utils_enabled=true`,
  - missing contract mappings fail fast (`V3UTILS_CONTRACTS_MISSING` / `V3UTILS_CONTRACT_MISSING`),
  - execution transport reuses existing native live path (raw tx + receipt polling).
  Rationale: incremental integration of upstream automation modules with fail-closed defaults.

- 2026-02-23: Execution architecture explicitly separates data-plane and execution-plane dependencies:
  - liquidity/tick state source of truth is direct DEX data (`subgraph + RPC`),
  - external code reuse (`KrystalDeFi/v3utils`, `revert-finance`) is limited to execution mechanics behind `ExecutionAdapter`,
  - runtime policy/orchestration remains internal (`TriggerEngine`, `PolicyGuard`, `ExecutionOrchestrator`).
  Rationale: avoid vendor/API lock-in for analytics while accelerating execution delivery via audited/open-source modules.

- 2026-02-23: Execution adapter resolution is fail-closed in `LIVE` mode:
  - runtime selects only adapters declaring `supports_live_execution=True`,
  - non-live-capable adapters (e.g., native stub) are explicitly rejected in LIVE,
  - missing/invalid LIVE adapter path now raises `LIVE_EXECUTION_ADAPTER_UNAVAILABLE` instead of silently degrading to non-live fallback.
  Rationale: canary/live execution must never "appear enabled" while routing into a known non-executing adapter path.

- 2026-02-23: Native LIVE execution path uses external signing + raw tx submit semantics:
  - `NativeLiveExecutionAdapter` is the current LIVE-capable native path (`supports_live_execution=True`),
  - adapter sends pre-signed tx via `eth_sendRawTransaction` and polls `eth_getTransactionReceipt`,
  - chain RPC routing is config/env-driven (`execution.native_live_rpc_env_by_chain` -> `<CHAIN>_RPC_URL`),
  - missing signing payload or receipt timeout returns explicit fail-safe reason codes (`SIGNED_RAW_TX_MISSING`, `TX_RECEIPT_TIMEOUT`, `RPC_*`).
  Rationale: enable deterministic canary/live transport without coupling runtime to private-key handling inside the scout process.

- 2026-02-23: Krystal Cloud execution path is treated as discovery-only until server contract exists:
  - `cloud-api.krystal.app` execution endpoints (`/v1/execution/*`) return `404` in live probes,
  - adapter maps this condition to `KRYSTAL_EXECUTION_API_UNAVAILABLE`,
  - SHADOW mode can fallback via `FailoverExecutionAdapter`, but LIVE mode rejects Krystal as non-live-capable.
  Rationale: explicit endpoint-contract mismatch must degrade deterministically and never silently pass as execution-ready.

- 2026-02-21: Phase G shadow bootstrap uses deterministic `execution.mock_positions` as execution-state source:
  - profile includes representative scenarios (`COMPOUND`, `REBALANCE`, and policy-blocked intent),
  - this provides stable baseline counters (`sim_ok`, policy reason taxonomy) before connecting live position-state provider.
  Rationale: de-risks rollout by validating orchestrator/policy/adapter interactions with controlled input set.

- 2026-02-21: Execution shadow observability uses reason-taxonomy counters instead of aggregate-only metrics:
  - orchestrator report tracks per-reason maps for `policy blocks`, `simulation failures`, and `execution failures`,
  - runtime logs publish these maps in `Execution summary` line each cycle,
  - trigger metadata now passes tx-builder fields (`position_manager`, action-specific data hex, value) so SHADOW can validate both success and failure paths.
  Rationale: 24h shadow gate requires actionable failure taxonomy, not only total counter deltas.

- 2026-02-21: Execution adapter routing uses configurable primary/fallback with runtime failover:
  - adapter selection is driven by `execution.primary_adapter` / `execution.fallback_adapter`,
  - Krystal adapter requires `KC-APIKey` (from env var configured by `execution.krystal_api_key_env`) and timeout control (`execution.krystal_timeout_seconds`),
  - runtime wrapper `FailoverExecutionAdapter` automatically retries the same operation on fallback adapter when primary adapter raises an exception.
  Rationale: keeps vendor integration optional and prevents execution loop failure when external adapter path is unavailable.

- 2026-02-21: Execution runtime integration is isolated behind explicit config gates:
  - `main.py` runs execution loop only when `execution.enabled=true`,
  - initial PAPER bootstrap uses `execution.mock_positions` (typed `PositionState` payloads) for deterministic dry-run,
  - execution summary counters are logged per cycle and do not change Scout report delivery path.
  Rationale: incremental rollout without coupling transaction orchestration to existing Scout/freshness/reporting behavior.

- 2026-02-21: Native execution adapter baseline is intentionally "safe-non-live" for v1 rollout:
  - `NativeUniswapV3Adapter` builds deterministic tx plans from intent metadata,
  - `simulate()` validates tx-plan structure only (no chain side effects),
  - `execute()` returns explicit fail-safe receipt (`LIVE_EXECUTION_NOT_IMPLEMENTED`) instead of attempting on-chain send.
  Rationale: allows PAPER/SHADOW pipeline integration and contract testing before any private-key/on-chain execution path is enabled.

- 2026-02-21: Execution `PolicyGuard` follows a fail-safe "block-on-missing" policy input contract:
  - hard checks enforce `kill_switch`, expected net floor, gas/slippage per tx, and daily budgets,
  - missing `estimated_gas_usd`/`slippage_bps` is treated as policy failure (`*_MISSING`) rather than silent allow,
  - decisions are persisted to bounded in-memory journal entries (`PolicyJournalEntry`) with UTC-day usage snapshot for auditability.
  Rationale: execution safety requires deterministic rejection on incomplete risk inputs and post-mortem traceability for operator review.

- 2026-02-21: Execution trigger classification is deterministic and precedence-based:
  - trigger order is fixed as `REBALANCE > COMPOUND > HOLD`,
  - rebalance is fired on any of: `OUT_OF_RANGE`, low `range_utilization`, `edge_decay_bps` threshold breach,
  - per-position cooldown converts actionable triggers into `SKIP` with explicit reason `COOLDOWN_ACTIVE`.
  Rationale: avoid ambiguous dual-trigger behavior and keep execution intent generation auditable/testable before live orchestration.

- 2026-02-21: Execution layer uses an explicit contract-first adapter boundary with config-gated safety:
  - canonical typed contracts live in `src/defi_agents/execution/models.py` (`ActionIntent`, `TxPlan`, `SimulationResult`, `ExecutionReceipt`, `ExecutionCounters`, `PolicyDecision`, `ExecutionAdapter` protocol),
  - runtime config is centralized in `ScoutConfig.execution` (`ExecutionConfig` + nested `ExecutionPolicyConfig`),
  - `mode=LIVE` is invalid unless `allow_live_mode=true`, and `primary_adapter=krystal` is invalid unless `krystal_enabled=true`.
  Rationale: enforce SDD governance and fail-safe defaults before any transaction orchestration logic is introduced.

- 2026-02-19: Tick Density Scanner runtime integration follows a post-L3, pre-scoring scan stage:
  - scanner is invoked after `save_to_history()` and before `eligible` filtering,
  - per-chain `UniswapV3TickProvider` is lazily initialized and reused across candidates on the same chain,
  - optional RPC `slot0()` cross-check uses raw `eth_call` via `httpx` (no web3.py dependency),
  - all scan results are attached to `metadata` dict (not model fields) to avoid breaking `ScoutResult` schema,
  - WATCHLIST downgrade only fires when `tick_density.enabled=true` AND `shadow_mode_enabled=false` (safe rollout).
  Rationale: metadata-driven approach avoids model migration, shadow mode allows 24h observation before scoring impact.

- 2026-02-19: Tick Density Scanner P0 uses an explicit fail-safe contract in typed models:
  - scanner output is `BandDepthResult` with mandatory `degradation_reason` whenever `data_quality != OK`,
  - provider-layer failures are mapped to deterministic reason codes (`PAGINATION_LIMIT_REACHED`, `SUBGRAPH_TIMEOUT`, `SUBGRAPH_ERROR`, `RPC_*`, `TICK_COUNT_ZERO`),
  - no silent empty-result fallbacks for degraded scanner outcomes.
  Rationale: preserve decision traceability and allow downstream scorer/notifier to apply deterministic watchlist-only downgrades.

- 2026-02-19: Optional discovery providers (Krystal Phase F) are explicitly decoupled from tick-level computation path.
  - P0 tick-level source of truth remains `UniswapV3TickProvider` (subgraph + RPC validation),
  - discovery-provider outages do not degrade `BandDepthResult` quality.
  Rationale: avoid vendor lock-in and keep LP scoring correctness independent from optional market-discovery integrations.

- 2026-02-13: Operator monitoring output is rendered as dedicated Telegram sections (`My Pools — Health` and `My Pools — Alerts`) and injected before directional market sections in section-block mode.
  Rationale: own-pool operational status must remain readable and independent from market discovery rankings; block-level rendering prevents mixed/partial sections under Telegram length limits.

- 2026-02-13: `My Pools Monitor` uses deterministic dual-key pool identity resolution:
  - Primary key: `pool_id`.
  - Fallback key: `(chain, address)` normalized to lowercase.
  - Unresolved targets become explicit snapshots (`DATA_UNVERIFIED`, `POOL_NOT_FOUND`) instead of silent drops.
  Rationale: operator watchlists must be complete and fail-safe; every configured pool must appear in report/state even when upstream mapping is partial.

- 2026-02-13: Monitor health signals are computed as additive, non-blocking tags on snapshots:
  - turnover (`WATCH_VOLUME`) from `Vol/TVL`,
  - APY drift (`WATCH_APY_DRIFT`) and TVL drain (`WATCH_TVL_DRAIN`) from last 24h history points,
  - default `HEALTHY` when no watch conditions trigger.
  Rationale: keep operator monitoring explainable and deterministic without introducing new hard gates into core Scout candidate filtering.

- 2026-02-13: Scout introduces an explicit operator-mode pattern (`My Pools Monitor`) alongside market-discovery mode:
  - Market mode keeps directional Top-10 discovery.
  - Operator mode tracks a configured watchlist of owned pools with health/alert tags (`Vol/TVL`, APY drift, TVL drain, confidence/freshness).
  - Reporting uses dedicated Telegram blocks (`My Pools — Health/Alerts`) and does not merge with market ranking sections.
  Rationale: users managing self-created pools need operational monitoring of a fixed set, not only external opportunity discovery.

- 2026-02-12: Scout uses explicit `yield_type` taxonomy as SSOT on candidates (`lp_fees`, `lending_supply`, `staking`, etc.) and directional digest routing consumes this field.
  Rationale: removes duplicated classification heuristics across snapshot/report paths and makes future ranking/risk logic composable.

- 2026-02-12: Scout ranking applies post-freshness confidence weighting via configurable `confidence_factors` (`VERIFIED/AGGREGATOR_ONLY/DIVERGED/STALE`) before report sorting.
  Rationale: keep raw economic/security scoring unchanged while systematically down-weighting lower-confidence data quality outcomes.

- 2026-02-12: DeFiLlama ingestion is being formalized behind a dedicated provider layer (`DeFiLlamaDataProvider`) with typed normalized facts and endpoint-specific cache/retry guards.
  Rationale: remove raw-endpoint coupling from Scout logic, improve schema-drift resilience, and make market/risk context reusable across modules.

- 2026-02-12: Optional DeFiLlama market-context surfaces (`overview/summary/stablecoins/bridges/prices`) are collected in shadow mode under an explicit feature flag and never block Scout intake.
  Rationale: upstream reliability differs by endpoint family; optional context must be additive and non-fatal until ranking/report policies are validated.

- 2026-02-12: Stability-aware ranking is implemented as a soft multiplier only (no hard-gate changes), controlled by `defillama_provider.enable_stability_scoring` and explicit factor thresholds.
  Rationale: improve ordering quality while preserving existing anti-scam and fail-safe gating semantics.

- 2026-02-12: Telegram market-context signals are opt-in (`telegram_show_market_signals`) and read from computed metadata (`stability_factor`, `stability_signals`, `apy_vs_mean_30d_pct`).
  Rationale: keep default report concise and production-safe while enabling richer operator diagnostics when needed.

- 2026-02-12: Scout digest market view is split into independent directional sections:
  - `Top-10 LP` ranked by `Vol/TVL` (activity-first, low APR allowed)
  - `Top-10 Lending Supply` ranked by supply APY
  - `Top-10 Lending Borrow` ranked by lowest borrow APR
  - `Top-10 Staking` ranked by APY for single-asset non-lending markets
  - Each section has separate config thresholds under `reporting.telegram_directional_*`.
  Rationale: avoid overfitting all opportunities to one metric and make digest decisions comparable across distinct yield mechanisms.

- 2026-02-10: Protocol Inspector runs as a separate service-bot (standalone entrypoint `inspector_main.py`) rather than inside Scout cycle.
  Rationale: isolate onchain due-diligence runtime (RPC budgets, source failures, diff polling) from yield scouting path and keep blast radius minimal.

- 2026-02-10: Contract verification is implemented as a risk-first dossier pipeline:
  - Resolve Contract Set from bounded sources (seed/DeFiLlama)
  - Run onchain checks (`eth_getCode`, EIP-1967 proxy/admin, owner/paused best-effort)
  - Persist `latest/prev` dossier snapshots and alert on high-impact diffs (`implementation/admin/owner/paused`)
  - Missing data => `PARTIAL` + `WATCHLIST`; no pass-by-absence.
  Rationale: decision-grade transparency with explicit uncertainty handling.

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

- 2026-02-04: Portfolio-scale profitability model:
  - Replaced `% of deposit` gas model with:
    - per-candidate `position_size_usd`,
    - `estimated_roundtrip_gas_usd`,
    - amortization by `holding_period_days`.
  - Added relative monthly profit floor concept (`>= 0.5%` of position) as config-side guardrail.
  - Rationale: realistic screening for multi-position portfolios (e.g., 10k total capital) and less distorted net-profit math.

- 2026-02-04: Profile-aware allocation roadmap pattern (Phase 2.5):
  - Introduce investor profile schema (`initial_capital`, `monthly_contribution`, `risk_profile`, `benchmark_apy`, horizon).
  - Route candidates into configurable sleeves (`core_safe`, `yield_plus`, `tactical_high_apy`) with explicit risk budgets.
  - Add capacity guards (`position as % TVL`, per-chain/protocol caps) for large-capital scenarios.
  - Rationale: one pipeline should adapt to micro DCA users and whale portfolios without weakening anti-scam invariants.

- 2026-02-04: Profile-aware selection implementation pattern (Phase 2.5 v1):
  - Sleeve routing is deterministic:
    - `tactical_high_apy` only when `apy >= tactical_min_apy` and `tactical_enabled=true`;
    - otherwise `core_safe` for trusted/pass stable pairs, else `yield_plus`.
  - Position sizing is profile-driven (`micro`/`standard`/`whale`) and then clamped by sleeve budget.
  - Capacity guards are enforced before output (`position % TVL`, protocol/chain caps, sleeve budget cap).
  - Cost-dominated opportunities are filtered (`net_profit_usd <= 0`) to protect DCA/small-ticket users from gas drag.
  - Benchmark metadata is attached (`above_benchmark`, `benchmark_delta_apy`, threshold) and reflected in Telegram reports.
  - Rationale: make one shortlist engine adapt to different capital scales without relaxing scam-critical security blocks.

- 2026-02-04: Secret-safe operational logging pattern:
  - Runtime raises `httpx`/`httpcore` logger levels to `WARNING` to suppress verbose request URL logs.
  - Telegram notifier retry logs include only status code / exception class (no raw exception string with URL path).
  - Rationale: avoid leaking bot tokens and similar secrets via transport-layer logs.

- 2026-02-04: Report explainability and triage pattern:
  - Classify report rows into `ACTIONABLE` (net profit meets configured floor) and `WATCHLIST` (manual review).
  - Include compact WARN reason codes (`warn_reasons`) per candidate in report output.
  - Split WARN bucket semantics:
    - `WARN/REPUTATION` for reputation-provider unavailability-only cases,
    - `WARN/SECURITY` for genuine security-signal warnings,
    - `LINDY/WARN` when Lindy soften rule is applied.
  - Rationale: reduce operator ambiguity and speed up manual decision-making without weakening hard-block logic.

- 2026-02-04: Universal decision-report pattern:
  - Report prioritizes user-agnostic fields for decision intake: `chain`, `pair`, `project`, `APY`, `TVL`, `risk`.
  - Displayed profitability metric is normalized to a fixed notional: `Net@1k` per month.
  - Output is sorted by pair class for quick scanning:
    1) `stable/stable`
    2) `token/stable`
    3) `token/token`
  - Risk is color-coded with badges (`🟢 SAFE`, `🟡 reputation/lindy warnings`, `🟠 security warnings`).
  - Rationale: make reports comparable across users with different capital sizes and improve fast triage quality.

- 2026-02-04: Audit intake expansion + exploration quota pattern:
  - Increased audit-stage budget (`max_audit_candidates`) to widen addressable candidate coverage.
  - Reserve exploration slots (`exploration_slots`) for high-APR pools that may rank low by TVL in primary sorting.
  - Exploration lane can be stable-focused (`exploration_stable_only=true`) with configurable floor (`exploration_min_apy`).
  - Remaining unused exploration slots are backfilled by normal priority order.
  - Rationale: reduce false negatives for promising pools (e.g., lower TVL but strong APR) without removing core risk gates.

- 2026-02-04: Dedupe TTL tuning pattern:
  - Deduper TTL is now configurable (`dedupe_ttl_seconds`) instead of fixed 24h.
  - Default reduced to 4h to avoid over-suppressing legitimate updates in active markets.
  - Operational note: after major scoring/policy changes, clear persisted dedupe cache once to remove stale suppression state.
  - Rationale: keep anti-spam behavior while preserving signal throughput.

- 2026-02-04: Telegram report chunking pattern:
  - Report output is split into <= 3500-character chunks before sending via Telegram Bot API.
  - Chunking preserves line boundaries to keep Markdown formatting stable.
  - Rationale: prevent HTTP 400 failures on oversized messages when report volume increases.

- 2026-02-06: Report deep-link pattern:
  - If `pool_id` is a DefiLlama yields id, link to pool page:
    - `https://defillama.com/yields/pool/<pool_id>`
  - If `pool_id` looks like an onchain contract address (`0x...`), link to chain explorer (by `chain_id`) for verification.
  - Rationale: reduce friction from alert -> manual verification -> decision, including DEX discovery rows not present in DefiLlama yet.

- 2026-02-06: Lending snapshot side-channel pattern:
  - Scout computes lending highlights from the same DeFiLlama universe as a separate snapshot (`best ETH supply`, `best BTC supply`, `lowest stable borrow`) and keeps core candidate ranking/filtering unchanged.
  - Snapshot uses borrow-specific fields (`apyBaseBorrow`, `apyRewardBorrow`) and can include low-APY markets even when global `min_apy` is higher.
  - Rationale: expose lending entry signals without weakening risk-first discovery gates for the main opportunity feed.

- 2026-02-06: Discovery error logging hygiene pattern:
  - DEX discovery adapters must never log raw Graph gateway endpoints with embedded API keys; logs must sanitize `/api/<key>/` to `/api/***/`.
  - Avoid logging raw HTTP response text for upstream API failures; log status/error class only.
  - Rationale: keep troubleshooting signal while preventing credential leakage to journal/log sinks.

- 2026-02-04: Freshness re-check gating pattern (spec 010):
  - Keep broad intake from DeFiLlama, then re-check shortlist candidates before Telegram publication.
  - Attach freshness metadata (`FRESH/STALE/UNVERIFIED`, age, staleness score, divergence deltas).
  - Enforce policy: only `FRESH` candidates are eligible for actionable output.
  - Downgrade stale/unverified/divergent rows into watchlist with explicit reason codes.
  - Rationale: preserve opportunity coverage while reducing decision risk from stale aggregator snapshots.

- 2026-02-04: Freshness Phase A wiring pattern:
  - Introduced `freshness` config schema in Scout settings (feature flags + thresholds + budget knobs).
  - Added metadata contract fields to report pipeline:
    - `freshness_status`, `freshness_provider`, `source_timestamp`, `age_minutes`,
      `staleness_score`, `apy_divergence_pct`, `tvl_divergence_pct`.
  - Added deterministic policy function (`freshness.policy`) to append freshness reason codes and optionally downgrade actionable rows when strict mode is enabled.
  - Added cycle-level freshness counters to logs for calibration.
  - Rationale: ship safe scaffolding first, then plug concrete adapters without breaking running operations.

- 2026-02-04: Freshness source-priority rollout pattern:
  - Phase B/C/D execution order is source-prioritized by impact and integration risk:
    1) `Uniswap Subgraph` (DEX baseline),
    2) `Aave API v2` (lending baseline),
    3) `Morpho API` (additional lending coverage),
    then `Aerodrome Subgraph` / `Curve API` expansion.
  - Rationale: maximize freshness gain early while limiting blast radius of adapter complexity.

- 2026-02-04: Freshness adapter MVP pattern (Phase B):
  - Introduced adapter interface (`supports` + `fetch_snapshot`) and manager orchestration with per-candidate timeout.
  - First implementation: `UniswapSubgraphAdapter` (chain-aware endpoint map, hourly/daily fallback query).
  - Snapshot fields mapped into report metadata (`freshness_provider`, `source_timestamp`, `age_minutes`, divergence deltas).
  - Failure behavior is explicit and safe: adapter errors/timeouts do not crash cycle; candidate remains `UNVERIFIED`.
  - Rationale: incremental source integration with bounded operational risk.

- 2026-02-04: Graph gateway migration + non-Ethereum freshness coverage pattern (Phase C):
  - Replaced deprecated hosted-service assumption (`api.thegraph.com/subgraphs/name/*`) with Graph gateway-ready source registry.
  - Added support for chain-to-subgraph-ID mapping and runtime API-key injection via env (`GRAPH_API_KEY`).
  - Kept optional explicit endpoint override for self-hosted/managed GraphQL backends.
  - Added protocol-scoped adapter routing (`AerodromeSubgraphAdapter`) reusing the same V3 snapshot logic.
  - Rationale: expand freshness coverage to reward-heavy non-Ethereum chains without weakening fail-safe `UNVERIFIED` behavior when credentials/endpoints are missing.

- 2026-02-05: DeFi Coverage Blueprint (Master Plan):
  - Coverage across DEX/LP, Lending/Borrowing, Staking/LST, Perps funding, Yield‑bearing stables.
  - Unified data contract for candidates (asset(s), chain, protocol, apy, tvl, liquidity, risk tags, freshness).
  - Risk‑first policy gates (SAFE/WARN/BLOCK) + stablecoin tiering + FX risk.
  - Freshness re-check gating before actionable output.
  - Strategy layer for multi‑leg strategies with ROI guardrail vs stable LP baseline.
  - Ops/observability + decision‑grade reporting as first‑class requirements.
  - Rationale: ensure full market coverage without degrading safety or actionability.

- 2026-02-05: RooCode skills as SSOT prompts:
  - Store reusable “agent skills” under `.roo/skills/*/SKILL.md` in the repository.
  - Skills encode mandatory process (Memory Bank sync), prod-safe review rubric, spec-writing flow, and VPS ops ask-first discipline.
  - Rationale: keep multiple agents aligned on process, safety, and output format.
  - Extended set covers funnel debugging, freshness rollout, safe config edits, report quality, and adapter engineering.

## Conventions
- Naming:
- Testing:
- Formatting:
- Error handling:

## Tech Stack
- ...
