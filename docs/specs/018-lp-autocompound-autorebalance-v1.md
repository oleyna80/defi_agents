# Specification: LP Autocompound + Autorebalance Platform v1

Status: APPROVED
Owner: Dmitrii / Codex (Tech Lead)
Related Memory: `docs/memory-bank/activeContext.md`
Related Specs:
- `docs/specs/lp-decision-engine-v1.md`
- `docs/specs/017-tick-density-scanner-v1.md`
Date: 2026-02-20

---

## 1. Context & Business Value

Проект переходит от стадии поиска пулов к стадии исполнения: нужен сервис, который автоматически управляет активными CLMM-позициями и повышает net yield после gas/slippage.

Цель v1:
- автокомпаунд комиссий;
- авторебаланс диапазона при выходе позиции или деградации edge;
- fail-safe исполнение с жёсткими risk-лимитами;
- запуск поэтапно: `PAPER -> SHADOW -> LIVE`.

Krystal stack может дать широкое покрытие сетей/DEX, но должен использоваться как optional adapter, без vendor lock-in.

---

## 2. User Stories

- US-1: Как оператор, я хочу автоматически реинвестировать накопленные fees, чтобы повышать APY без ручного клика.
- US-2: Как оператор, я хочу автоматически переносить позицию в новый диапазон при trigger-условиях, чтобы не оставаться out-of-range.
- US-3: Как риск-менеджер, я хочу kill-switch и policy-лимиты, чтобы остановить исполнение при небезопасном рынке/газе/проскальзывании.
- US-4: Как тех-лид, я хочу подключать Krystal/Revert на execution-слое без изменения core-логики через adapter contracts.

---

## 3. Functional Requirements

### 3.1 Execution Modes

- REQ-001: Система MUST поддерживать режимы:
  - `PAPER`: формирует план транзакций, не отправляет on-chain tx.
  - `SHADOW`: отправляет dry-run simulation + логирует expected outputs, без on-chain tx.
  - `LIVE`: отправляет on-chain tx только после policy gate.
- REQ-002: Переключение mode MUST происходить только через конфиг/операторский флаг; default = `PAPER`.

### 3.2 Position Monitoring & Triggers

- REQ-003: Система MUST читать позиционное состояние:
  - current tick, range lower/upper, liquidity, unclaimed fees, position value, last rebalance time.
- REQ-004: Система MUST вычислять триггеры:
  - `COMPOUND_DUE` (fees USD >= threshold);
  - `REBALANCE_DUE` (out-of-range, range utilization, edge decay);
  - `HOLD` (нет действия).
- REQ-005: Для каждого триггера MUST формироваться `ActionIntent`:
  - `COMPOUND`, `REBALANCE`, `SKIP`
  - с reason codes и expected net delta.

### 3.3 Policy Guard (Hard Safety Layer)

- REQ-006: Любая action MUST проходить `PolicyGuard` до симуляции/исполнения.
- REQ-007: `PolicyGuard` MUST проверять:
  - `max_gas_usd_per_tx`
  - `max_slippage_bps`
  - `max_daily_txs`
  - `max_daily_gas_usd`
  - `min_expected_net_usd`
  - `kill_switch`.
- REQ-008: При нарушении policy action MUST быть отменён с reason code; цикл продолжает работу (fail-safe).

### 3.4 Execution Adapter Pattern

- REQ-009: Система MUST использовать vendor-agnostic protocol:
  ```python
  class ExecutionAdapter(Protocol):
      async def build_compound_tx(intent: ActionIntent) -> TxPlan: ...
      async def build_rebalance_tx(intent: ActionIntent) -> TxPlan: ...
      async def simulate(tx: TxPlan) -> SimulationResult: ...
      async def execute(tx: TxPlan) -> ExecutionReceipt: ...
  ```
- REQ-010: Core orchestration MUST не зависеть от конкретного провайдера (Krystal/Revert/Native).
- REQ-011: Система SHOULD поддерживать минимум 2 adapters:
  - `NativeUniswapV3Adapter` (fallback baseline),
  - `KrystalExecutionAdapter` (optional, feature-flagged).

### 3.5 Krystal Integration Constraints

- REQ-012: Интеграция Krystal MUST использовать только server-to-server API path (`cloud-api.krystal.app`, `KC-APIKey`), без browser bypass.
- REQ-013: Krystal integration MUST быть optional:
  - при недоступности Krystal execution слой MUST деградировать на fallback adapter;
  - P0/P1 не блокируются vendor outage.
- REQ-014: Секреты (`KC-APIKey`, wallet keys) MUST быть только в env/secret store; запрещено логировать ключи/tx raw.

### 3.6 Observability & Ops

- REQ-015: Система MUST логировать по каждой попытке:
  - action type, mode, policy result, simulate result, execution result, gas/slippage/net.
- REQ-016: Система MUST считать counters:
  - `intent_count`, `blocked_by_policy`, `sim_ok`, `sim_fail`, `exec_ok`, `exec_fail`.
- REQ-017: Telegram/ops report SHOULD показывать только execution summary (без старых scout watchlist-секций).

---

## 4. Non-Functional Requirements

- Performance:
  - NFR-001: цикл оценки intents <= 30s на 20 позиций.
  - NFR-002: simulation timeout <= 10s per tx.
- Reliability:
  - NFR-003: fail-safe на уровне каждой позиции (ошибка в одной позиции не валит batch).
  - NFR-004: idempotency по `intent_id` (исключение дублей отправки).
- Security:
  - NFR-005: обязательный `kill_switch` check перед каждой отправкой tx.
  - NFR-006: execution в LIVE разрешён только при `mode=LIVE` и `kill_switch=false`.
- Compatibility:
  - NFR-007: поддержка multi-chain EVM через chain-specific RPC + adapter routing.

---

## 5. Constraints

- Tech stack: Python async orchestration + typed pydantic models.
- Existing logic:
  - Scout/tick-density остаются advisory layer;
  - execution слой независим от scout digest schedule.
- Governance:
  - PROD execution запрещён до `Status: APPROVED` и прохождения shadow gate.

---

## 6. Out of Scope (v1)

- Delta hedging (Phase 5).
- CEX perp execution.
- Non-EVM chains.
- Полностью автономная стратегия выбора пулов (это отдельный scouting layer).

---

## 7. Acceptance Criteria

- AC-01: `PAPER` mode генерирует intents и tx plans без on-chain отправок.
- AC-02: `SHADOW` mode стабильно проходит 24h без crash и с полными counters.
- AC-03: Любой policy breach корректно блокирует action с reason code.
- AC-04: При недоступности Krystal fallback adapter продолжает цикл без fatal error.
- AC-05: В `LIVE` режиме минимум 1 успешный compound и 1 rebalance на тестовом пуле с валидным receipt.
- AC-06: Kill-switch мгновенно останавливает новые tx.

---

## 8. Risks / Open Questions

- R-1: Rate limits/latency Krystal execution path под batch-нагрузкой.
- R-2: MEV/slippage spikes могут съедать edge при rebalance.
- R-3: Ошибки оценки expected net могут приводить к избыточным tx.
- OQ-1: Какие chain/DEX включать в LIVE wave 1 (Base only vs Base+Arbitrum)?
- OQ-2: Какие пороги compound/rebalance использовать по умолчанию для micro-capital?

---

## Approvals

- [x] User Approved
- [x] Architecture Approved
