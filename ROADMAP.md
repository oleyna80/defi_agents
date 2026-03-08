# 🗺️ Project Roadmap: DeFi Sentinel & News Intelligence

**Версия:** Draft 1.0
**Статус ядра:** v3.6 (Stable, User-mode, Fail-fast)
**Цель:** Создание автономной системы для **создания и активного управления собственными пулами ликвидности**: выбор лучших сетей/проектов/токенов по доходности и риску (Scout) + анализ инфополя (News Hub).

---

## 🎯 Product Focus (актуализация)
- Мы **не** фокусируемся на поиске “чужих готовых пулов” как конечной цели.
- Основной режим: выбирать, **где и с какими активами создавать свои пулы** (сеть + протокол + пара), и управлять ими через мониторинг/ребаланс.
- Приоритетный операторский сценарий v1 (2026-03-08): для заданных `pair + range` (симметричный/асимметричный, включая `AUTO` по режиму рынка) выбирать `network + protocol` с минимальной in-range конкурирующей ликвидностью при приемлемом риске и издержках.
- На **первом этапе** работаем только с ограниченной вселенной активов:
  - топовые токены: `BTC`, `ETH` (и их ликвидные эквиваленты),
  - стейблкоины: топ‑ликвидные USD/fiat-pegged stable assets.
- Расширение в long-tail активы — только после стабильной валидации v1 на топовых токенах и стейблах.

---

## ✅ Success Metrics / DoD (по фазам)
*Чтобы каждый этап заканчивался измеримым результатом, а не “кажется стало лучше”.*

- **Phase 2 (Relaxation):**
  - Scout стабильно находит кандидатов: `>0` каждый день (YELLOW/Green-fast-lane суммарно).
  - Появляются “качественные” выдачи: минимум 1–3 сигнала в неделю в отчёте (пусть даже в статусе WARN).
  - Пайплайн перестаёт быть “чёрным ящиком”: в логах/артефактах есть счётчики по стадиям воронки и топ‑причины блоков.
- **Phase 3 (Traffic Light):**
  - Снижение затрат: уменьшение количества внешних вызовов (GoPlus/De.Fi/AI) за счёт pre-filter.
  - Безопасность не деградирует: критические tech-флаги никогда не обходятся “Green” статусом.
- **Phase 4 (News Hub):**
  - Утренний heartbeat: подтверждает, что Scout и News Hub живы.
  - Каналы алертов не шумят: меньше “noise”, больше actionable сигналов.

## 🟢 Phase 1: Core Stabilization (Завершено ✅)
*Фундамент системы. Обеспечивает автономную работу 24/7 без сбоев.*

- [x] **VPS Migration:** Перенос с GitHub Actions на VPS (Systemd).
- [x] **Zero-Overlap:** Исключение двойных запусков (отключение GitHub Cron).
- [x] **User-Mode Service:** Работа от имени пользователя (без root-прав).
- [x] **Fail-Fast Architecture:** Мгновенная остановка при ошибках конфига/API.
- [x] **Logging:** Чистые логи в `journalctl`.

---

## 🟡 Phase 2: Pipeline Relaxation (Приоритет: High, IN PROGRESS)
*Проблема: Бот работает стабильно, но находит 0 кандидатов (конфигураций сеть+проект+пара для собственных пулов) из-за слишком строгих фильтров.*

- **Исполнительный план:** `docs/plans/012-defi-coverage-mvp-plan.md`

- [x] **Policy v1 agreed (Lindy + output buckets):**
    - Lindy v1: `TVL >= $100M` и `age >= 180d` смягчают только audit/reputation сигналы (до `WARN`), но не обходят критические tech-флаги.
    - Выдача в 2 корзины: `SAFE` и `LINDY/WARN` (manual review).
- [x] **Policy Matrix SSOT:**
    - Зафиксировано в `docs/memory-bank/security/policy_matrix_v1.md` (единая таблица правил для SAFE/WARN/BLOCK/UNSUPPORTED).
- [x] **Funnel Observability (обязательно):**
    - Логировать/сохранять метрики воронки: `raw_pools → heuristics_pass → has_address+chain_id → security_pass/warn/block/unknown → l3_eligible → final_picks`.
    - Логировать топ‑причины `BLOCK/WARN` (по кодам причин), чтобы быстро понимать “почему 0”.
- [x] **Расширение Chain Mapping (EVM):**
    - Добавить маппинг для популярных EVM сетей (например: Polygon, BSC, Fantom, Linea и т.п.).
    - Цель: уменьшить долю кандидатов без `chain_id` и не терять хорошие EVM пулы.
- [x] **Audit Intake Expansion (Fast Win):**
    - Увеличен бюджет аудита кандидатов (`max_audit_candidates`: 15 -> 40).
    - Добавлена exploration-квота (`exploration_slots`) для high-APR stable-focused пулов вне top-TVL.
    - Цель: снизить missed-opportunity из-за ранжирования только по TVL.
- [ ] **Freshness Re-check v1 (Decision-Grade):**
    - Two-step проверка перед Telegram для shortlist-кандидатов (re-check по ближайшему источнику).
    - Freshness/divergence теги: `FRESH/STALE/UNVERIFIED`, `STALE_DATA`, `DIVERGENCE_HIGH`.
    - Только `FRESH` кандидаты попадают в публичный actionable; остальные уходят в watchlist.
    - Цель: снизить риск принятия решений на устаревших данных.
    - Research baseline (см. `docs/research/2026-02-dex-lending-direct-api-research.md`):
      - MVP sources: `Uniswap Subgraph`, `Aave API v2`, `Morpho API`.
      - Expansion sources: `Aerodrome Subgraph`, `Curve API`.
      - Стартовые пороги (для калибровки): `max_age_minutes=90`, `max_apy_divergence_pct=25`, `max_tvl_divergence_pct=20`.
    - Progress:
      - [x] Phase A: schema + policy wiring (`freshness` config, metadata fields, downgrade policy, counters, report tags).
      - [x] Phase B: first re-check adapter MVP (`Uniswap Subgraph` for Ethereum, timeout budget, metadata/delta wiring; feature-flagged by default).
      - [x] Phase C: расширение на non-Ethereum DEX (multi-chain source registry via Graph subgraph IDs + `Aerodrome` adapter scaffold, feature-flagged).
      - [x] Phase C+: Aave direct re-check (миграция на AaveKit GraphQL + outcome counters `ok/timeout/error/schema_mismatch/addr_mismatch`).
      - [ ] Phase D: add Morpho API and calibrate thresholds on VPS telemetry.
- [x] **Non‑EVM стратегия (явно):**
    - Добавлена явная наблюдаемость unsupported/non‑EVM входов в funnel-метриках (`unsupported_non_evm`, `missing_chain_top`), чтобы такие кандидаты не исчезали “молча”.
    - Отдельные non‑EVM адаптеры (Solana/Sui/Aptos) вынесены в следующий этап расширения coverage.
- [x] **Смягчение Security Policy (v1 baseline):**
    - Внедрить правило "Lindy Effect" как *смягчение audit/reputation сигналов*, но НЕ как обход критических tech-флагов.
    - v1 пороги: `TVL >= $100M` и `age >= 180d` (при необходимости позже смягчить до `50M` по метрикам).
    - Эффект: отсутствие top-tier аудита переводить в `WARN`, но не в `PASS/TRUSTED`.
    - Разрешить `unknown` аудиты для “Blue Chip” протоколов (Aave, Uniswap, Curve) через реестр/whitelist, а не через хардкод.
- [x] **Fix "Silent Mode":**
    - Добавлен Telegram heartbeat "No opportunities found" с отдельным daily rate-limit (`reporting.telegram_no_opportunities_heartbeat_*`), чтобы подтверждать liveness при пустой выдаче.
- [x] **Scout: Staking Yield Discovery (v1):**
    - Discovery расширен beyond LP: single-asset рынки классифицируются как `staking` и попадают в отдельный directional Top-10 блок.
    - v1.1 backlog: добавить поля `lockup/unbonding/slashing` для chain-native/LST источников.

---

## 🟨 Phase 2.5: Investor Profiles & Allocation Engine (Новый приоритет: High)
*Цель: делать релевантный отбор для разных размеров капитала и стратегий (от DCA до tactical high-APY).*

- [x] **Investor Profile Schema:**
    - Добавить профиль инвестора: `initial_capital`, `monthly_contribution`, `risk_profile`, `horizon_days`, `benchmark_apy`.
    - Поддержать типовые профили: `micro`, `standard`, `whale`.
- [x] **Allocation Sleeves (Risk Budgets):**
    - `core_safe` (консервативные стейбл-пулы),
    - `yield_plus` (умеренный риск),
    - `tactical_high_apy` (высокорискованные APY 100%+, малой долей и коротким сроком).
- [x] **Capacity Guardrails (особенно для крупного капитала):**
    - Лимит позиции как `% TVL` (пример: 0.1–0.5%),
    - Лимиты по протоколу/цепочке (v1: per-position caps относительно deployable capital),
    - Базовый slippage/capacity sanity-check.
- [x] **DCA-aware Logic (для малых/растущих портфелей):**
    - Поддержка сценария `initial + monthly contribution` (например, 1000 + 500/мес),
    - Порог входа с учетом фиксированных издержек, чтобы газ не "съедал" доход.
- [x] **Benchmark Mode ("better than bank"):**
    - Оценка не только в `$ net/month`, но и в `net_apy` против `benchmark_apy + buffer`.
    - Отдельная маркировка "Above Benchmark" в Telegram-отчётах.

---

## 🟧 Phase 2.6: Scout My Pools Monitor (Новый приоритет: High)
*Цель: переключить Scout из "поиска чужих пулов" в "операционный мониторинг моих пулов" без потери risk-first и fail-safe поведения.*

- **Spec/Plan:** `docs/specs/016-scout-my-pools-monitor-v1.md`, `docs/plans/016-scout-my-pools-monitor-v1-plan.md`
- [x] **Watchlist Mode (pool-centric):**
    - Явный список пулов (`pool_id` и/или `chain+address`) в конфиге.
    - Отдельный pipeline мониторинга без смешивания с market Top-10.
- [x] **Pool Health Signals:**
    - Метрики: `TVL`, `Vol24h`, `Vol/TVL`, `APY`, `APY vs 30d mean`, freshness/confidence.
    - Теги статуса: `HEALTHY / WATCH_VOLUME / WATCH_APY_DRIFT / WATCH_TVL_DRAIN / DATA_UNVERIFIED`.
- [x] **Telegram Decision Blocks (operator view):**
    - `My Pools — Health`
    - `My Pools — Alerts`
    - (опционально) `My Pools — Market Gap`
- [x] **Fail-safe + compatibility:**
    - При выключенном monitor-режиме текущий отчет не меняется.
    - Неразрешенные/неполные данные не валят цикл, а деградируют в `DATA_UNVERIFIED`.
- [x] **DoD для фазы 2.6:**
    - 24h стабильной работы с включенным monitor-режимом (без падений цикла).
    - Все пулы из watchlist отражаются в отчете (resolved или explicit-unverified).
    - Полный тест-пакет green.

---

## 🟧 Phase 2.7: Tick Density Scanner (Band Depth Module) (Новый приоритет: High, IN PROGRESS)
*Цель: добавить tick-level анализ ликвидности для CLMM, чтобы LP Decision Engine выбирал диапазоны с низкой конкуренцией и контролируемым риском.*

- **Spec/Plan:** `docs/specs/017-tick-density-scanner-v1.md`, `docs/plans/017-tick-density-scanner-v1-plan.md`
- [x] **Governance gate (2026-02-19):**
  - `docs/specs/017-tick-density-scanner-v1.md` переведена в `Status: APPROVED`.
  - Коллизии `REQ-022/REQ-023` устранены, plan/spec синхронизированы.
- [ ] **Phase 1 (P0, IN PROGRESS):**
  - [x] `TickDataProvider` + `UniswapV3TickProvider` (core provider contract + fail-safe adapter).
  - [x] Anchor-based tick walking (`pool.liquidity`), `band_depth_*` windows (+1%/+2.5%/+5%).
  - [x] RPC drift semantics + typed degradation reasons (`DegradationReason`).
  - [x] Pagination circuit breakers (`MAX_PAGES_PER_POOL`, `MAX_TICKS_PER_POOL`).
  - [x] Feature-flag config surface `tick_density.*` in `ScoutConfig` + sample `scout_config.json`.
  - [x] DeFiLlama prices → `tick_daily_vol` metadata in scan stage (token0/token1 ratio σ; fail-safe).
  - [x] Regression suite for P0 foundations (`tests/test_tick_density_scanner.py`) + full suite green (`157 passed`).
  - [x] Improved tick provider init diagnostics (reason+message) + fail-safe handling for temporary subgraph downtime.
  - [ ] Integration hook into scorer/runtime shadow counters and live reference checks (`AC-01..AC-07`, `AC-17`).
- [ ] **Phase 1.5 (P0.5):**
  - pit detection + `CONFIDENT_PIT/NOISE_PIT`
  - `SuggestedRange` (tickSpacing-aligned)
  - Aerodrome adapter
- [ ] **Phase 2 (P1):**
  - history/stability gate (>=3 obs / 6h)
  - multi-venue comparison
  - PancakeSwap/HyperSwap adapters
- [ ] **Ops gate (shadow):**
  - 24h VPS shadow-run with `errors=0`
  - [x] mandatory counters in logs: `pits_found_count`, `degraded_count`, `scan_duration_p95_ms`
  - degraded data -> watchlist only (no actionable)
- [x] **Phase F (Krystal API Discovery, non-blocking):**
  - `docs/research/krystal-integration-decision-report.md` зафиксировал текущий статус `CONDITIONAL GO` (2026-02-19): `cloud-api.krystal.app` доступен server-side через `KC-APIKey`, подтверждён pool-level schema fit для REQ-022.
  - Remaining gate перед production enablement: 48h schema stability check + rate-limit/load validation.
  - P0 execution path не блокирован и остаётся на `UniswapV3TickProvider`; Krystal остаётся optional discovery-track и включается только после закрытия remaining gate.

---

## 🟥 Phase 2.7.5: LP Entry Recommendation Engine (Новый приоритет: Critical, CLOSED)
*Цель: из текущего Scout/Tick-Density пайплайна получать детерминированную рекомендацию для входа в позицию: `сеть + протокол + пара + диапазон`.*

- **Spec baseline:** `docs/specs/lp-decision-engine-v1.md` (APPROVED)
- **Execution plans:** `docs/plans/024-lp-entry-recommendation-v1-plan.md`, `docs/plans/025-lp-entry-research-roo-task.md`, `docs/plans/026-lp-entry-implementation-roo-task.md`, `docs/plans/027-lp-entry-stability-calibration-roo-task.md`, `docs/plans/028-lp-entry-shadow-evidence-calibration-roo-task.md`
- [x] **Task definition locked (до кодинга):**
  - Вход: shortlist кандидатов + метаданные `band_depth_*`, `tick_data_quality`, `freshness`, `strategy_sim`.
  - Выход: `EntryRecommendation` (top-N), где для каждой рекомендации есть:
    - `chain`, `project`, `pair`, `fee_tier`,
    - `suggested_range_lower_tick`, `suggested_range_upper_tick` (+ price view),
    - `confidence`, `reason_codes`, `watchlist_reason` (если не actionable).
  - Fail-safe контракт: деградированные/неполные tick данные никогда не поднимаются в actionable.
- [x] **Research gate (обязательный, до разработки):**
  - Матрица покрытия по сетям/DEX для v1 (`Base/Arbitrum`, `Uniswap v3/Aerodrome`).
  - Сравнение подходов range selection: pit-based vs volatility-adjusted vs hybrid.
  - Калибровка порогов ранжирования (`competition_ratio`, `min_net_monthly_usd`, confidence cutoffs).
  - Формализация метрик качества (precision actionable, доля watchlist по degraded данным, стабильность top-N).
- [x] **Development gate (после research sign-off):**
  - Wiring pit detection + range suggestion в runtime output path.
  - Ранжирование `EntryRecommendation` и отдельный блок в отчёте оператора.
  - Регрессионные тесты + fail-safe тесты.
- [x] **DoD фазы 2.7.5:**
  - В отчёте есть отдельный блок `LP Entry Recommendations` с полями `network/pair/range`.
  - Для degraded tick/freshness данных рекомендации помечаются как WATCHLIST (без false-actionable).
  - Тесты на ранжирование/диапазон/fail-safe проходят стабильно.

- [x] **Phase 2.7.6 (P1, CLOSED): Stability + Shadow Calibration**
  - [x] Ввести history/stability gate для actionable (`>=3 observations / 6h`).
  - [x] Добавить telemetry метрики churn/stability для Top-N.
  - [x] Выполнить controlled calibration `rank_v1`/confidence thresholds на SHADOW evidence.
    - 2026-03-03 window-24 evidence (`docs/reports/lp-entry-shadow-calibration-2026-03-03.md`): `all_pass=true` (`cycles_with_entry_telemetry=24`, `errors_zero_pass=true`), решение `KEEP` (без retune) как evidence-backed no-op.
  - [x] Закрыть через `docs/plans/028-lp-entry-shadow-evidence-calibration-roo-task.md` (evidence gate + controlled retune).

- [x] **Phase 2.7.7 (P1, CLOSED): Actionable Enablement**
  - [x] Добавлен детерминированный reason-level telemetry контракт для `WATCHLIST` (`watchlist_reason_counts`) в cycle-level LP entry telemetry.
  - [x] Формализованы и выведены в evidence data-readiness блокеры tick-density (`GRAPH_API_KEY_MISSING`, provider/subgraph init/schema blockers).
  - [x] Расширен calibration tooling: gate `actionable_ratio_positive_pass` + top-3 watchlist reasons при `actionable_ratio == 0`.
  - [x] Выпущен отчёт `docs/reports/lp-entry-actionable-enablement-2026-03-03.md` с before/after snapshot и blocker section.
  - [x] Реализован root-cause slice Plan 030 в runtime/tests: LP-only eligibility pre-filter перед `build_entry_recommendations(...)`, machine-code taxonomy для ineligible/range-path (`NON_LP_YIELD_TYPE`, `UNSUPPORTED_ENTRY_VENUE`, `MISSING_POOL_REFERENCE`, `RANGE_NOT_COMPUTED`, `INVALID_OR_MISSING_RANGE`), coverage counters `entry_input_total/entry_lp_eligible_total/entry_lp_ineligible_total/entry_range_ready_total/entry_range_missing_total`.
    - Реализация: `main.py`, `src/defi_agents/lp/entry_recommendation.py`, `src/defi_agents/lp/shadow_calibration.py`, тесты/репорт синхронизированы.
  - [x] Проведён post-Plan030 diagnostic SHADOW evidence (2026-03-04): при валидном runtime окне (`cycles_with_entry_telemetry=4`) зафиксировано `actionable_ratio=0.0` при `entry_lp_eligible_total_sum=26`, `entry_range_ready_total_sum=23` и доминации `REPORT_GROUP_WATCHLIST` в LP-eligible subset; зафиксирован следующий root-cause track через Plan 031.
  - [x] Реализован Plan 031 (StrategySim decoupling + deterministic sim policy reasons):
    - LP entry builder теперь использует seed-поля `lp_entry_seed_report_group`/`lp_entry_seed_watchlist_reason` (pre-StrategySim snapshot), поэтому generic StrategySim downgrade (`PARTIAL/UNSUPPORTED/risk`) больше не подавляет LP-eligible/range-ready actionable path структурно.
    - В `strategy_sim.apply_policy(...)` добавлены machine-readable причины downgrade без free-text: `SIM_STATUS_PARTIAL`, `SIM_STATUS_UNSUPPORTED`, `SIM_RISK_ABOVE_PROFILE` (в `watchlist_reason` + `sim_policy_reason`).
    - LP fail-safe контракт сохранён без ослабления (`degraded/stale/diverged/invalid-range/insufficient-history` -> `WATCHLIST`).
    - Post-fix SHADOW evidence: `docs/reports/artifacts/lp_entry_shadow_calibration_post_plan031_mockai_2026-03-04.json` => `actionable_ratio_positive_pass=true`, `errors_zero_pass=true`.
  - [x] Выполнить long-window closeout после Plan 031 через `docs/plans/032-lp-entry-phase277-shadow-closeout-roo-task.md`:
    - sustained SHADOW window (`>=24` cycles) + повторная проверка gate-метрик,
    - optional reversible tune только при необходимости (max 1-2 knobs),
    - финальное решение `KEEP/ADJUST/ROLLBACK` и формальное закрытие Phase 2.7.7.
    - 2026-03-04 closeout evidence (`docs/reports/artifacts/lp_entry_shadow_calibration_phase277_closeout_mockai_2026-03-04.json`): `cycles_with_entry_telemetry=24`, `errors_zero_pass=true`, `actionable_ratio_positive_pass=true`, churn gates pass (`topn_churn_avg=0.0605`, `topn_churn_p95=0.375`), decision `KEEP` (no tune required).
  - [x] Закрыть фазу после устойчивого SHADOW-окна с ненулевым `actionable_ratio` или после evidence-backed reversible tune итерации (макс 1-2 параметра за итерацию).
  - Трек ведётся через `docs/plans/029-lp-entry-actionable-enablement-roo-task.md`, `docs/plans/030-lp-entry-lp-scope-range-coverage-roo-task.md`, `docs/plans/031-lp-entry-strategysim-decoupling-roo-task.md`, `docs/plans/032-lp-entry-phase277-shadow-closeout-roo-task.md`.

- [x] **Phase 2.7.8 (P1, CLOSED): ETH/USDT Targeted Cross-Network Selector (SHADOW)**
  - Цель: дать оператору целевой режим поиска `network + protocol + range` для пары `ETH/USDT` (с нормализацией `WETH-USDT`) в рамках поддерживаемых venue.
  - План исполнения: `docs/plans/033-lp-entry-eth-usdt-target-scope-roo-task.md`.
  - Scope:
    - Config-driven target scope (`pair/chains/projects/top_n`) без ломки текущего LP Entry report path.
    - Сравнение внутри target scope по нескольким сетям и поддерживаемым протоколам (`uniswap-v3`, `aerodrome-slipstream`).
    - Deterministic telemetry counters для target filtering и empty-target случаев.
  - 2026-03-04 (Plan 033): реализованы `lp_entry_targeting` schema/config validation, pair-normalization для target matching (`ETH/USDT` ↔ `WETH-USDT`) без изменения display symbols, pre-build target filtering перед `build_entry_recommendations(...)`, target-scope telemetry counters (`entry_target_scope_enabled`, `entry_target_input_total`, `entry_target_matched_total`, `entry_target_excluded_total`) и marker `entry_target_reason=TARGET_SCOPE_EMPTY`; regression coverage и обязательные проверки пройдены.
  - Инварианты:
    - Fail-safe contract сохраняется (`degraded/stale/diverged/invalid-range` не становятся actionable).
    - Нет LIVE/infra/secrets изменений, только WSL/repo scope.

- [ ] **Phase 2.7.9 (P0, NEXT): Cross-Protocol Range Competition Selector**
  - Цель: по входу оператора `pair + range` (симметричный/асимметричный) выбирать лучшую точку входа `network + protocol` на основе конкуренции ликвидности в целевом диапазоне и ожидаемого fee-potential.
  - План исполнения: `docs/plans/036-cross-protocol-range-competition-selector-v1-plan.md`.
  - Scope:
    - Входной контракт: `target_pair`, `range_mode=SYMMETRIC|ASYMMETRIC|AUTO`, `market_regime=SIDEWAYS|UPTREND|DOWNTREND`, optional manual `range_lower/range_upper`, allowlist `chains/projects`.
    - Cross-venue сравнение в рамках поддерживаемых CLMM по сети: `uniswap-v3`, `aerodrome-slipstream`, `sushiswap-v3` (и аналогичные venue в зависимости от сети).
    - Ранжирование `network x protocol x pair x range` по детерминированному score (`in_range_liquidity_competition`, volume/fee proxy, gas/cost sanity).
    - Явный вывод причин и confidence: почему выбран этот протокол/сеть, почему альтернативы ниже в рейтинге.
  - Инварианты:
    - Fail-safe не ослабляется: degraded/stale/diverged/invalid-range не переходят в actionable.
    - Нет auto-execution; только decision-grade recommendation layer.
  - DoD:
    - Для `ETH/USDT` в SHADOW выдаётся Top-N по нескольким сетям и протоколам с machine-readable метриками конкуренции.
    - В отчёте есть отдельный блок сравнения `network/protocol/range` с объяснимым ранжированием.
    - Тесты на математику score/ranking/tie-break и fail-safe деградацию проходят стабильно.

---

## 🛡️ Phase 2.8: Protocol Inspector (Новый приоритет: High, IN PROGRESS)
*Цель: автоматизировать due diligence протоколов (anti-scam / onchain verifiability) как отдельный service-bot, не ломая Scout pipeline.*

- **Spec/Plan/Ops:** `docs/specs/014-protocol-inspector-v1.md`, `docs/plans/014-protocol-inspector-v1-plan.md`, `docs/runbooks/protocol_inspector_v1_ops.md`
- [x] **Отдельный сервис-бот:**
    - Реализован отдельный entrypoint `inspector_main.py` и отдельный `systemd --user` oneshot/timer.
    - Изоляция от Scout: сбои/лимиты инспектора не влияют на цикл `defi-sentinel`.
- [x] **Risk-first dossier v1:**
    - Реализованы onchain core-checks (code/proxy/admin/owner/paused best-effort), хранение `latest/prev` и diff по high-impact полям.
    - Вердикты: `PASS / WATCHLIST / FAIL` без "silent PASS by missing data".
- [x] **Fail-safe и лог-гигиена:**
    - Ошибки RPC/API не валят пайплайн; статус деградирует в `PARTIAL/WATCHLIST`.
    - Санитизация потенциально чувствительных URL/ключей в логах.
- [x] **Governance fallback hardening:**
    - `owner()` fallback через `admin()/governor()/authority()`, чтобы убрать ложные `WATCHLIST` на нестандартных контрактах.
    - Low-only findings допускают `PASS` (информационные, не материальные).
- [ ] **Rollout-gate для расширения coverage:**
    - Добавить `Contract Set Builder` v1.1 (poolsOld/docs/campaign/explorer/RPC-inference) для автоматического расширения набора core-адресов.
    - Добавить чеки timelock/multisig и role-diff alerts в следующий инкремент.
- [ ] **DoD для фазы 2.8:**
    - 24h стабильной работы `defi-inspector.timer` без падений и без утечек секретов.
    - Минимум 1 целевой протокол с детерминированным досье и повторяемым verdict.
    - Diff-alert срабатывает при изменении `implementation/admin/owner/paused` (где детект возможно).

---

## 🔵 Phase 3: Reputation System (Traffic Light)
*Оптимизация расходов на AI и защита от скама на раннем этапе.*

- [ ] **Реестр Репутации (`reputation_registry.json`):**
    - 🔴 **RED:** Скам, эксплойты, черные списки (Drop immediately). Экономит API-вызовы.
    - 🟡 **YELLOW:** Новые/неизвестные проекты. Требуют Deep Audit + AI Analysis.
    - 🟢 **GREEN (Fast lane, не skip lane):** Проверенные гиганты (Uniswap, Lido).
      Минимальный обязательный чек остаётся (sanity + критические tech-флаги), а не “полный skip”.
- [ ] **Pre-filter Logic:** Внедрение проверки по реестру *до* запросов к GoPlus/AI.
- [ ] **AI Cost Controls:**
    - Лимит AI-аудитов на цикл/день + агрессивный cache-first.
    - Триггеры для AI только для “аномалий” (новый/аномальный APY/подозрительные docs), а не для всего потока.

---

## 🟣 Phase 4: News Intelligence (n8n)
*AI-аналитик новостей и "глаза" системы.*

- [ ] **Infrastructure Setup:**
    - Google Sheets (список активов).
    - CryptoPanic API + DeepSeek API.
- [ ] **AI Routing Logic:**
    - Классификация новостей: "Portfolio Alert", "New Alpha", "Market Noise".
- [ ] **Multi-Channel Alerts:**
    - **DM (Личка):** Критические угрозы портфелю (взломы, депеги).
    - **Private Channel:** Alpha-находки, глубокий анализ.
    - **Public Channel:** Хайп, крупные новости рынка.
- [ ] **System Heartbeat:** Настроить в n8n утреннюю сводку: "Scout работает, News Hub активен".

---

## 🟠 Phase 5: Alpha Discovery (The "Hunter")
*Поиск высокорисковых возможностей для **создания собственных пулов** (Degen Mode).*

- [ ] **Deployment Hunter:**
    - Поиск сетей/проектов/токенов для запуска собственных пулов с целевой доходностью (в т.ч. high-risk сценарии).
    - Мониторинг high-yield сегментов как input, но решение формируется как “создать/перенести свой пул”, а не “зайти в чужой готовый пул”.
- [ ] **AI Analysis for New Projects:**
    - Анализ токеномики (Emission, Unlocks).
    - Проверка на Honeypot/Rugpull (через GoPlus).
    - Метрика `MCap / TVL` (оценка перегретости).
    - Вердикт: "Degen Play" (зайти-выйти) или "Long Term".

---

## 🔷 Phase 3: LP Execution Pipeline — Foundation (Priority: Medium)
*Переход от advisory ("вот хорошие пулы") к execution ("автоматически управляй позициями").*
*Требует новых approved спецификаций — текущая логика зафиксирована как `MANUAL_EXECUTION_ONLY`.*

### Phase 3.0 — Real Position Reader (LP_OS Critical Path, P0)
*Gate-3/LIVE блокер: execution не должен зависеть от `mock_positions`.*

- [x] **Replace mock state with real on-chain position reads (Arbitrum + Uniswap v3):**
    - убрать зависимость execution-контура от `execution.mock_positions`,
    - читать позиции через `NonfungiblePositionManager` + `slot0()` + fee fields.
- [ ] **Position state integrity:**
    - [x] корректный `in_range/out_of_range` статус в реальном времени,
    - [x] `position_value_usd` из on-chain liquidity+tick (`LIQUIDITY_TICK_MODEL_V1`) с quality reason-codes,
    - [ ] `P&L` и `HODL benchmark` для реальных позиций.
- [x] **Stale data safety gate:**
    - блокировать LIVE execution при `STALE_POSITION_DATA`,
    - добавить явные reason-codes в policy/report path.
- [ ] **DoD для Gate-3 readiness:**
    - минимум 3 реальные позиции с отклонением расчёта `P&L < 1%` от ручной проверки,
    - стабильная работа reader path в SHADOW без runtime failures.

- **Gate-3 evidence status (2026-03-07):** `FAIL` (insufficient evidence based on actual VPS 48h SHADOW run)
    - **Blocker 1**: `VALIDATED_POSITIONS_BELOW_MIN_THRESHOLD` - в текущем evidence pack найдена только 1 реальная позиция с заполненным `pnl_vs_hodl` (требуется >=3).
    - **Blocker 2**: `READER_OK_BELOW_THRESHOLD` - нет подтверждения `reader_ok_count >= 90` в 48h окне.
    - **Blocker 3**: Ошибки в логах: зафиксировано 3 ошибки `Traceback|CRITICAL` и 7 случаев `POSITION_READER_ALL_CHAINS_FAILED`.
    - Необходимые действия: устранить критические ошибки в ридере, обеспечить стабильную работу без ALL_CHAINS_FAILED на протяжении 48h, добавить как минимум 2 дополнительные позиции в baseline.

DoD: Gate-3 canary и любой `LIVE` execution остаются заблокированными до устранения blockers и закрытия Phase 3.0.

### Phase 3.1 — Strategy Calibration + Forward Simulation (P1)
*Калибровка параметров и stress-test на текущем state (не классический бэктест — ликвидность нестационарна).*

- [ ] **Range Width Calibration:** Оптимальная ширина диапазона vs rebalance frequency (разовая задача, structural insight)
- [ ] **Monte Carlo Forward Sim:** N случайных ценовых траекторий на текущем state → stress-test
- [ ] **Rebalance Cost Model:** gas_cost × rebalance_count → минимальный TVL для прибыльности
- [ ] **Regime Detector:** Бычий/медвежий/боковик → стратегия зависит от режима

DoD: Range width + rebalance frequency калиброваны на текущем state. Monte Carlo stress-test проходит без критических потерь.

### Phase 3.2 — Position Monitor v2 (P1)
*Расширение My Pools Monitor до полноценного Position State Tracker.*

- [ ] **Out-of-Range Detection:** Определение выхода позиции из диапазона + ETA (по волатильности)
- [ ] **Fee Tracker:** Accumulated fees (claimed vs unclaimed), fee APR вычисление
- [ ] **IL Tracker:** Impermanent loss в реальном времени vs entry price
- [ ] **Rebalance Trigger Engine:** Конфигурируемые правила "rebalance needed when X"
- [ ] **On-chain Position Reads:** Прямое чтение `positions()` из NonfungiblePositionManager

DoD: Оператор видит полную картину каждой позиции (fees + IL + range status) в Telegram digest.

### Phase 3.3 — Autocompound + Autorebalance Platform (P0.5 → **Spec Required**)
*Execution-контур: автоматическое управление позициями.*

> [!CAUTION]
> Требует отдельной approved спецификации с: ключами, лимитами, kill-switch, safe-mode, gas budget.

- **Spec/Plan (draft):**
  - `docs/specs/018-lp-autocompound-autorebalance-v1.md`
  - `docs/plans/018-lp-autocompound-autorebalance-v1-plan.md`
  - `docs/plans/019-v3utils-reuse-execution-plan.md` (execution module reuse track)
  - `docs/research/2026-02-open-source-reuse-matrix.md` (license-aware reuse matrix)
  - `docs/runbooks/execution-loop-rollout-v1.md`
  - `docs/runbooks/INDEX.md` (runbook entrypoint / navigation)

- **Execution track status (2026-02-23):**
  - Spec 018 approved; implementation phases A-F completed (contracts, triggers, policy, adapters, orchestrator).
  - Phase G SHADOW gate passed (24h, historical execution-track gate): `runs=85`, `execution_summaries=85`, `errors=0`, `sim_fail=0`, `exec_fail=0`.
  - Phase H prep: kill-switch drill passed in controlled LIVE profile (`KILL_SWITCH_ENABLED` hard-block confirmed), rollback to SHADOW verified.
  - LP_OS alignment: Gate-3/LIVE remains blocked by unresolved Phase 3.0 (`Real Position Reader`, no mock dependency).
  - Added LIVE-capable native path `native_uniswap_v3_live` (RPC `eth_sendRawTransaction` + receipt polling for pre-signed tx payloads).
  - Started module-reuse execution scaffold: feature-flagged `v3utils` adapter route added (Plan 019).
  - Pinned `v3utils` ABI/address bundle committed (`src/defi_agents/execution/abi/`, commit lock `33f487...`).
  - Started ABI-driven `compound` calldata builder (`v3utils_compound_params` -> `V3Utils.execute`).
  - Added ABI-driven `rebalance` structured path + selector/contract simulation checks.
  - Track moved to Phase H canary prep (LIVE remains guarded).
  - LIVE remains blocked (`allow_live_mode=false`) until canary + kill-switch drill.

- [ ] **Autocompound:** Claim fees → swap → re-add liquidity (batch tx)
- [ ] **Auto-Rebalance:** Close old range → open new range (trigger-based)
- [ ] **Safe-Mode Guards:** Max gas per tx, max slippage, daily tx budget, kill-switch
- [ ] **MEV Protection:** Flashbots Protect / MEV Blocker integration
- [ ] **Multi-sig / Safe:** Smart Account SDK для execution с hardware signing

**Open-source reference:**
- `revert-finance/compoundor` (Solidity, audited) — autocompound smart contracts
- `revert-finance/compoundor-js` (license to be confirmed) — compounder bot implementation
- `KrystalDeFi/v3utils` (fork of revert-finance/v3utils) — V3Utils + V3Automation: zap-in, compound, adjust, zap-out
- `code-423n4/2024-06-krystal-defi` — Code4rena audit of Krystal contracts
- Reuse policy: direct code import only for permissive licenses (`MIT`/`Apache-2.0`); AGPL/GPL/BUSL repos are reference-only in core runtime.

DoD: Paper mode → shadow mode → live mode escalation. Kill-switch в 1 click.

---

## 🔷 Phase 4: Risk Dashboard + Observability (Priority: Medium)
*Единая картина портфеля перед запуском hedger.*

- [ ] **Cross-chain Position Aggregation:** Все LP/lending/staking позиции в одном view
- [ ] **Real-time PnL:** Unrealized + Realized, по позициям и суммарно
- [ ] **Exposure Breakdown:** Asset / chain / protocol concentration matrix
- [ ] **Risk Metrics:** Max drawdown, VaR, correlation matrix
- [ ] **Alert Rules:** Configurable thresholds (IL > X%, TVL drop > Y%, fee APR < Z%)
- [ ] **Web UI (optional):** Простой dashboard вместо чтения логов

DoD: Оператор видит portfolio-level риск + может сказать hedger'у "что хеджировать".

---

## 🔷 Phase 5: Delta Hedger (Priority: Low, **Spec Required**)
*Фьючерсный хедж для нейтрализации направленного риска LP позиций.*

> [!CAUTION]
> Самый рискованный слой (ликвидации, funding, basis risk). Запускать поэтапно:
> advisory/paper mode → shadow → авто-исполнение.

- **PoC Plan (started):**
  - `docs/plans/020-delta-hedger-hummingbot-poc-plan.md`
  - `docs/runbooks/hedger-shadow-rollout-v1.md`
  - Текущий формат: isolated worker в `PAPER/SHADOW`, без LIVE-исполнения и без coupling к `main.py`.
  - Status (2026-02-27): 24h SHADOW gate passed (`cycles=88`, `sim_ok=176`, `sim_fail=0`, `connector_errors=0`, no `FATAL/Traceback/CRITICAL`). Next: formalize Spec 020 scope and move from mock connector to real venue sandbox readiness checks.

- [ ] **Funding Rate Monitor:** Отслеживание funding rates на CEX/perp DEX
- [ ] **Hedge Calculator:** Optimal hedge ratio based on LP delta exposure
- [ ] **Paper Trading Mode:** Симуляция hedging без реального исполнения
- [ ] **Perp Venue Integration:** API connection (`Hyperliquid` primary, `GMX v2` fallback для Arbitrum) для hedge execution; для других сетей допускаются аналогичные perp venue по chain coverage/liquidity.
- [ ] **Basis Tracker:** Мониторинг basis risk (spot vs futures)
- [ ] **Liquidation Guard:** Pre-emptive de-leverage при приближении к ликвидации

DoD: Delta-neutral mode доступен для top pairs (ETH/USDC, BTC/USDC).

---

## ⚙️ Backlog & Tech Debt

- [ ] **Dashboard:** Простая веб-страница или сообщение с текущим статусом портфеля (вместо чтения логов).
- [ ] **Execution:** Автоматический вход в позицию (пока только алерты, execution — следующий большой шаг).
- [ ] **Strategy ROI Guardrail:**
    - Сложные стратегии должны превышать базовую доходность стейбл‑пулов.
    - Ввести baseline‑порог (например: `stable_lp_baseline_apy`) и отдавать “strategy‑only” сигналы, если `expected_net_apy > baseline`.
- [ ] **Retry Policy:** Добавить умные повторы (backoff) для внешних API (DeFiLlama), чтобы избегать ошибок 429.
- [ ] **Ops Invariants (SSOT):**
    - Явно зафиксировать правило “single scheduler”: VPS systemd *или* GitHub Actions, но не оба одновременно.
    - Короткий runbook/rollback для смены scheduler.
    - [x] Единая точка входа по runbooks: `docs/runbooks/INDEX.md`.
- [ ] **History/Artifacts Hygiene:**
    - Ротация/архивация `docs/memory-bank/history.csv` (или периодическая выгрузка), чтобы файл не рос бесконечно.

---

## 📌 DeFi Coverage Blueprint (Master Plan)
*Цель: закрыть весь спектр DeFi доходности и рисков в одном контуре.*

1) **Coverage (Источники доходности)**
   - DEX/LP, Lending/Borrowing, Staking/LST, Perps funding, Yield‑bearing stables.
   - DoD: для каждого класса есть адаптер + нормализованные поля.

2) **Unified Data Contract**
   - Единый формат кандидата: asset(s), chain, protocol, apy, tvl, liquidity, risk tags, freshness.
   - DoD: любой новый источник подключается без изменения downstream логики.

3) **Risk Policy**
   - Security audit + buckets SAFE/WARN/BLOCK.
   - Stablecoin policy (tiers + FX risk).
   - DoD: риск всегда важнее доходности.

4) **Freshness**
   - Re-check перед алертом, метки FRESH/UNVERIFIED/STALE.
   - DoD: actionable только после freshness‑подтверждения.

5) **Strategy Layer**
   - Multi‑leg стратегии: delta‑neutral, collateral‑loop, hedged LP.
   - DoD: стратегия > baseline доходности стейбл‑пулов.

6) **Ops & Observability**
   - systemd fail‑fast, heartbeat, метрики по воронке.
   - DoD: система объясняет, почему тишина/нет сигналов.

7) **Decision View**
   - Отчёт понятен конечному пользователю (что, где, почему, риск).
   - DoD: “хочу войти” → ясно куда и зачем.

---

## 🚀 Future Architectures & Moonshots (Gemini Architect Wishlist)
*Концептуальные идеи для долгосрочного развития (Post-v1).*

### 1. Delta-Neutral "Pure Yield" (Risk Hedging)
*Shift from "High Yield" to "Risk-Free Yield".*
- **Concept:** Одновременное открытие LP-позиции (Long) и шорта на ту же сумму (Perps/Aave).
- **Goal:** Забирать 50%+ APY комиссий, полностью игнорируя движение цены токена (Delta Neutral).
- **Tech:** Интеграция с Hyperliquid API или Aave V3.

### 2. "Time Machine" Backtesting
*Shift from "Forward Test" to "Historical Simulation".*
- **Concept:** Валидация стратегий не на живых деньгах, а на исторических данных.
- **Tech:** Fork-based simulation (Foundry/Anvil) с копией состояния блокчейна за прошлые периоды.
- **Goal:** Тюнинг параметров (ширина ренджа, порог входа) с нулевым риском.

### 3. Event-Driven Architecture
*Shift from "Polling" to "Push".*
- **Concept:** Замена cron/systemd polling (раз в 10 мин) на WebSocket подписку на события чейна.
- **Tech:** Alchemy/Infura WebSockets -> Async Event Loop.
- **Goal:** Реакция на появление "ямы ликвидности" за миллисекунды (опережение JIT-ботов).

### 4. Smart Execution Agent
*Shift from "Analysis" to "Action".*
- **Concept:** Бот не просто шлет алерт, а генерирует готовую транзакцию (или исполняет её сам в доверенном контуре).
- **Tech:** Safe Smart Account SDK или EOA signing service с жесткими лимитами.
- **Goal:** Auto-Close rules (stop-loss, profit-take, liquidity drain exit) без участия человека.

### 5. Cross-Chain Arbitrage Intelligence
*Shift from "Isolated" to "Comparative".*
- **Concept:** Сравнивать yield одного актива сразу во всех сетях (Base vs Arb vs Mainnet).
- **Goal:** "Не лезь на Base, перекинь USDC на Arbitrum, там yield на 40% выше с учетом моста".
