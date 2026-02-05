# Strategy Simulator v1: Operational Runbook

**Status:** ACTIVE
**Version:** 1.0 (Safe Mode)
**Context:** Deployment of Strategy Simulator in "Observation Mode" (non-trading).

---

## 1. Rollout Plan (Safe Activation)

Цель: Включить симуляцию без спама в Telegram и падения сервиса.

### Step 0: Pre-Flight Check (Current State)
Проверить `docs/memory-bank/scout_config.json`:
- `risk_policy.enabled`: `true`
- `risk_policy.apply_scoring_penalties`: `false`
- `strategy_sim.enabled`: `false` (Базовое состояние)

### Step 1: Silent Activation
**Action:** Изменить в конфиге `strategy_sim.enabled: true`.
**Monitoring:**
- Прогнать 3-5 циклов (1-2 часа).
- Проверить логи на наличие `StrategySim summary`.
- Убедиться, что нет traceback/ошибок.
- **Критерий успеха:** `Reported` метрики не выросли взрывообразно (Actionable ≈ Baseline).

### Step 2: Noise Control
**Action:** Наблюдение за Telegram.
- Если сообщения выглядят "сломанными" (много `None` полей) -> Не закреплять в Public Channel.
- *Mitigation:* В v1.1 скрыть поля симуляции, если статус != OK.

### Step 3: Chain Gating (Strict)
**Action:** Мониторинг логов на предмет `Skipping chain`.
- Если видим валидную сеть (напр. `Polygon POS`), добавляем алиас в `config.chain_id_map`.
- **НЕ** отключаем проверку EVM.

---

## 2. Debug Checklist

Использовать при анализе логов (`journalctl --user -u defi-sentinel.service`).

### A. General Health
```bash
journalctl --user -u defi-sentinel.service --since "30 minutes ago" --no-pager | grep -E "StrategySim summary|Stablecoin risk policy|Freshness summary|Reported"

```

### B. Why is it PARTIAL? (Missing Data)

*Ожидаемое поведение для v1. Симулятор требует данных, которых нет в базовом фиде.*

```bash
journalctl --user -u defi-sentinel.service --since "30 minutes ago" --no-pager | grep -E "StrategySim|missing_data|PARTIAL"

```

*Look for keywords:* `volume_24h`, `fee_apr`, `utilization`, `price_range`.

### C. Why is it UNSUPPORTED? (Logic/Chain)

```bash
journalctl --user -u defi-sentinel.service --since "2 hours ago" --no-pager | grep -E "Skipping chain|unsupported chain|pair_class_counts"

```

*Fix:* Если сеть валидна — обновить маппинг в конфиге. Если класс актива не определен — проверить Metadata Pipeline.

---

## 3. Definition of Done (v1)

* [ ] 3+ цикла работы без критических ошибок.
* [ ] `StrategySim summary` присутствует в логах.
* [ ] Статус `PARTIAL` доминирует (Expected behavior).
* [ ] Количество `Actionable` алертов стабильно.
