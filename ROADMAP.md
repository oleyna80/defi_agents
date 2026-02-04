# 🗺️ Project Roadmap: DeFi Sentinel & News Intelligence

**Версия:** Draft 1.0
**Статус ядра:** v3.6 (Stable, User-mode, Fail-fast)
**Цель:** Создание автономной системы поиска доходности (Scout) и анализа инфополя (News Hub).

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
*Проблема: Бот работает стабильно, но находит 0 кандидатов из-за слишком строгих фильтров.*

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
      - [ ] Phase C+: Aave direct re-check (обновить endpoint strategy: `aave-api-v2` deprecated, нужен актуальный source contract).
      - [ ] Phase D: add Morpho API and calibrate thresholds on VPS telemetry.
- [ ] **Non‑EVM стратегия (явно):**
    - Solana / Sui / Aptos: либо добавить отдельные адаптеры, либо пометить как `UNSUPPORTED` (но не “молча отбрасывать”).
    - Цель: понимать реальный missed-opportunity, а не терять его в нулевой статистике.
- [x] **Смягчение Security Policy (v1 baseline):**
    - Внедрить правило "Lindy Effect" как *смягчение audit/reputation сигналов*, но НЕ как обход критических tech-флагов.
    - v1 пороги: `TVL >= $100M` и `age >= 180d` (при необходимости позже смягчить до `50M` по метрикам).
    - Эффект: отсутствие top-tier аудита переводить в `WARN`, но не в `PASS/TRUSTED`.
    - Разрешить `unknown` аудиты для “Blue Chip” протоколов (Aave, Uniswap, Curve) через реестр/whitelist, а не через хардкод.
- [ ] **Fix "Silent Mode":**
    - Настроить отправку уведомления "No opportunities found" раз в сутки (Heartbeat), чтобы подтверждать работоспособность.

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
*Поиск высокорисковых возможностей (Degen Mode).*

- [ ] **Discovery Agent:**
    - Мониторинг *новых* пулов (возраст < 7 дней) с APY > 50%.
- [ ] **AI Analysis for New Projects:**
    - Анализ токеномики (Emission, Unlocks).
    - Проверка на Honeypot/Rugpull (через GoPlus).
    - Метрика `MCap / TVL` (оценка перегретости).
    - Вердикт: "Degen Play" (зайти-выйти) или "Long Term".

---

## ⚙️ Backlog & Tech Debt

- [ ] **Dashboard:** Простая веб-страница или сообщение с текущим статусом портфеля (вместо чтения логов).
- [ ] **Execution:** Автоматический вход в позицию (пока только алерты, execution — следующий большой шаг).
- [ ] **Retry Policy:** Добавить умные повторы (backoff) для внешних API (DeFiLlama), чтобы избегать ошибок 429.
- [ ] **Ops Invariants (SSOT):**
    - Явно зафиксировать правило “single scheduler”: VPS systemd *или* GitHub Actions, но не оба одновременно.
    - Короткий runbook/rollback для смены scheduler.
- [ ] **History/Artifacts Hygiene:**
    - Ротация/архивация `docs/memory-bank/history.csv` (или периодическая выгрузка), чтобы файл не рос бесконечно.
