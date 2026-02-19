# 🗺️ Project Roadmap: DeFi Sentinel & News Intelligence

**Версия:** Draft 1.0
**Статус ядра:** v3.6 (Stable, User-mode, Fail-fast)
**Цель:** Создание автономной системы для **создания и активного управления собственными пулами ликвидности**: выбор лучших сетей/проектов/токенов по доходности и риску (Scout) + анализ инфополя (News Hub).

---

## 🎯 Product Focus (актуализация)
- Мы **не** фокусируемся на поиске “чужих готовых пулов” как конечной цели.
- Основной режим: выбирать, **где и с какими активами создавать свои пулы** (сеть + протокол + пара), и управлять ими через мониторинг/ребаланс.
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
  - [x] Regression suite for P0 foundations (`tests/test_tick_density_scanner.py`) + full suite green (`157 passed`).
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
  - mandatory counters in logs: `pits_found_count`, `degraded_count`, `scan_duration_p95_ms`
  - degraded data -> watchlist only (no actionable)
- [x] **Phase F (Krystal API Discovery, non-blocking):**
  - `docs/research/krystal-api-discovery.md` зафиксировал текущий статус `NO-GO` (2026-02-19): server-side запросы блокируются Cloudflare challenge (`403 cf-mitigated`).
  - P0 execution path не блокирован и остаётся на `UniswapV3TickProvider`; Krystal остаётся optional discovery-track до service-level auth.

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

- [ ] **Autocompound:** Claim fees → swap → re-add liquidity (batch tx)
- [ ] **Auto-Rebalance:** Close old range → open new range (trigger-based)
- [ ] **Safe-Mode Guards:** Max gas per tx, max slippage, daily tx budget, kill-switch
- [ ] **MEV Protection:** Flashbots Protect / MEV Blocker integration
- [ ] **Multi-sig / Safe:** Smart Account SDK для execution с hardware signing

**Open-source reference:**
- `revert-finance/compoundor` (Solidity, audited) — autocompound smart contracts
- `revert-finance/compoundor-js` (JS/MIT) — compounder bot implementation
- `KrystalDeFi/v3utils` (fork of revert-finance/v3utils) — V3Utils + V3Automation: zap-in, compound, adjust, zap-out
- `code-423n4/2024-06-krystal-defi` — Code4rena audit of Krystal contracts

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

- [ ] **Funding Rate Monitor:** Отслеживание funding rates на CEX/perp DEX
- [ ] **Hedge Calculator:** Optimal hedge ratio based on LP delta exposure
- [ ] **Paper Trading Mode:** Симуляция hedging без реального исполнения
- [ ] **CEX Integration:** API connection (Binance/Hyperliquid) для hedge execution
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
