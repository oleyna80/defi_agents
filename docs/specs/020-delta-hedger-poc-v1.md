# Specification: Delta Hedger PoC v1

Status: DRAFT
Owner: Dmitrii / Codex (Tech Lead)
Related Memory: `docs/memory-bank/activeContext.md`
Related Plan: `docs/plans/020-delta-hedger-hummingbot-poc-plan.md`
Date: 2026-02-27

## 1. Context & Business Value
После запуска автокомпаунда/авторебаланса нужен отдельный хедж-слой, который снижает направленный риск LP-позиций без повышения blast radius основного runtime.

PoC-v1 ограничен безопасной зоной `PAPER/SHADOW` и подтверждает, что контур хеджирования:
- работает как изолированный worker;
- дает детерминированные решения и reason-коды;
- не ломает текущий production loop.

## 2. User Stories
- Как оператор, я хочу видеть hedge-intent и симуляцию исполнения без LIVE-ордера, чтобы оценить готовность стратегии.
- Как риск-менеджер, я хочу строгий fail-safe (`NO_ACTION`) при деградации данных/коннектора, чтобы исключить скрытые риски.
- Как тех-лид, я хочу adapter boundary для коннектора, чтобы заменить mock на реальный venue без рефакторинга калькулятора/оркестратора.

## 3. Functional Requirements
- REQ-001: Система MUST поддерживать режимы `PAPER` и `SHADOW`; `LIVE` для PoC-v1 запрещен.
- REQ-002: Входом MUST быть нормализованный snapshot экспозиции (`HedgeExposure`) с проверкой свежести.
- REQ-003: Калькулятор MUST выдавать `HEDGE/HOLD/SKIP` с reason taxonomy (`EXPOSURE_STALE`, `MARK_PRICE_MISSING`, policy reasons).
- REQ-004: Оркестратор MUST симулировать только `HEDGE` intents и вести counters (`sim_ok`, `sim_fail`, `connector_errors`).
- REQ-005: Коннектор MUST иметь staged health checks (`auth`, `instrument`, `bbo`) и typed rejection reasons.
- REQ-006: При любой ошибке коннектора/runtime MUST быть fail-safe (`NO_ACTION` + reason), без uncaught exception.
- REQ-007: Runtime MUST логировать parseable строки `Hedger summary` и `Hedger reasons` для window-gate отчетов.

## 4. Non-Functional Requirements
- Reliability:
  - NFR-001: 24h SHADOW run без `FATAL`, `Traceback`, `CRITICAL`.
  - NFR-002: Ошибка по одной позиции не должна прерывать batch-cycle.
- Security:
  - NFR-003: `kill_switch` и лимиты нотационала обязательны даже в SHADOW.
  - NFR-004: Ключи коннектора только через env, без логирования секретов.
- Operability:
  - NFR-005: user-systemd units для worker/timer должны поддерживать enable/disable/rollback без прав root.

## 5. Constraints
- Tech stack: Python async + typed pydantic contracts.
- Runtime constraint: Hedger остается отдельным worker и не встраивается в `main.py` production cycle.
- Connector constraint: для PoC допускается локальный mock-сервис; для следующего этапа нужен sandbox/real venue readiness.

## 6. Out of Scope
- LIVE hedge execution.
- Funding/basis optimization.
- Liquidation engine.
- Multi-venue smart routing.

## 7. Acceptance Criteria
- AC-001: 24h SHADOW gate pass по метрикам стабильности и симуляции.
- AC-002: В логах присутствуют детерминированные reason counters.
- AC-003: При деградации коннектора worker не падает и возвращает `NO_ACTION`.
- AC-004: Есть documented path перехода mock -> real connector readiness.

## 8. Risks / Open Questions
- R-001: Расхождение поведения mock и real venue (market metadata, BBO shape).
- R-002: Недооценка slippage/funding в PoC может завысить perceived readiness.
- OQ-001: Какой первый production venue для sandbox validation (Binance futures vs Hyperliquid)?
- OQ-002: Какие минимальные hedge-notional и cooldown пороги зафиксировать для v1 default?

## Approvals
- [ ] User Approved
- [ ] Architecture Approved
