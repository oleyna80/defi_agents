# SHADOW Gate: Real Positions — Checklist

Runbook для прохождения Gate-2 (48h SHADOW) на реальных позициях после внедрения `ArbitrumUniswapV3PositionReader`.

---

## Шаг 1: Добавить `WALLET_ADDRESS` в `.env`

```bash
cd ~/projects/defi_agents

# Добавить строку (замени адрес на свой)
echo 'WALLET_ADDRESS=0xYourWalletAddressHere' >> .env

# Проверить что записалось
grep WALLET_ADDRESS .env
```

Проверь что `RPC_URL_ARBITRUM` уже есть:

```bash
grep RPC_URL_ARBITRUM .env
```

---

## Шаг 2: Smoke-проверка reader'а (1 цикл локально)

Запустить изолированный тест reader'а без запуска полного sentinel:

```bash
cd ~/projects/defi_agents
source .venv/bin/activate

python - <<'PY'
import asyncio, os
from dotenv import load_dotenv
from defi_agents.tracker import ArbitrumUniswapV3PositionReader

load_dotenv()
wallet = os.environ["WALLET_ADDRESS"]
rpc_url = os.environ["RPC_URL_ARBITRUM"]

async def main():
    reader = ArbitrumUniswapV3PositionReader(rpc_url=rpc_url)
    states = await reader.load_active_position_states(wallet)
    print(f"Loaded {len(states)} active positions:")
    for s in states:
        print(
            f"  {s.position_ref}  tick={s.current_tick}  "
            f"range=[{s.lower_tick},{s.upper_tick}]  "
            f"in_range={not s.out_of_range}  "
            f"fees_usd={s.unclaimed_fees_usd:.4f}  "
            f"stale={s.stale}  stale_codes={s.stale_reason_codes}"
        )

asyncio.run(main())
PY
```

**Целевой результат:**

| Поле | Ожидание |
|---|---|
| `Loaded N positions` | ≥ 1 |
| `in_range` | True/False (проверь визуально в Uniswap UI) |
| `fees_usd` | Отклонение от Uniswap UI < 1% |
| `stale=False` | Нет STALE_POSITION_DATA |
| `stale_codes=[]` | Нет ошибок |

> **Верификация P&L:** Открой Uniswap UI → твои позиции → сравни `Unclaimed fees` с выводом `fees_usd`.
> Если цены не подтянулись (STALE_PRICE), сначала проверь доступность CoinGecko: `curl "https://api.coingecko.com/api/v3/ping"`.

---

## Шаг 3: Деплой на VPS и запуск SHADOW

### 3.1 Залить код на VPS

```bash
# Локально:
git add -A
git commit -m "feat: Real Position Reader Phase 0 + adapter rename"
git push
```

```bash
# На VPS:
cd ~/projects/defi_agents
git pull
source .venv/bin/activate
python -m pytest tests/ -q --tb=short
# Ожидание: 303 passed
```

### 3.2 Убедиться в конфиге

```bash
grep -A5 '"execution"' docs/memory-bank/scout_config.json | head -10
```

Должно быть:
- `"enabled": true`
- `"mode": "SHADOW"`
- `"primary_adapter": "uniswap_v3_simulate"`
- `"allow_live_mode": false`
- `"kill_switch": false`

### 3.3 Перезапустить sentinel

```bash
systemctl --user daemon-reload
systemctl --user restart defi-sentinel.service
sleep 5
journalctl --user -u defi-sentinel.service -n 50 --no-pager | \
  grep -E "Execution state|Execution summary|ERROR|Traceback"
```

**Ожидаемые строки в логах:**

```
Execution states loaded: source=position_reader chain=Arbitrum active_states=N
Execution summary: mode=SHADOW states=N tx_plans=... sim_ok=... exec_ok=0 ...
```

Если `WALLET_ADDRESS` не задан на VPS → появится:
```
Execution state source fallback: reason=WALLET_ADDRESS_MISSING source=mock_positions
```
Это нормально для mock-режима, но не пройдёт Gate.

---

## Шаг 4: 48h мониторинг

### Быстрая проверка каждые несколько часов:

```bash
journalctl --user -u defi-sentinel.service --since "3 hours ago" --no-pager | \
  grep -E "source=position_reader|STALE_POSITION_DATA|STALE_PRICE|Traceback|CRITICAL"
```

### Финальные счётчики перед Gate-3:

```bash
journalctl --user -u defi-sentinel.service --since "48 hours ago" --no-pager | \
  grep "Execution summary:" > /tmp/shadow_48h.log

awk '
{
  if (match($0, /sim_ok=([0-9]+)/, a)) sim_ok += a[1];
  if (match($0, /sim_fail=([0-9]+)/, b)) sim_fail += b[1];
  if (match($0, /blocked_by_policy=([0-9]+)/, c)) blocked += c[1];
  cycles += 1;
}
END {
  printf("cycles=%d sim_ok=%d sim_fail=%d blocked_by_policy=%d\n", cycles, sim_ok, sim_fail, blocked);
}
' /tmp/shadow_48h.log

echo "errors=$(journalctl --user -u defi-sentinel.service --since '48 hours ago' --no-pager | grep -c 'Traceback\|CRITICAL')"
echo "reader_ok=$(journalctl --user -u defi-sentinel.service --since '48 hours ago' --no-pager | grep -c 'source=position_reader')"
```

---

## Gate-2 DoD (условия прохождения)

- [ ] `errors=0` (нет Traceback/CRITICAL за 48h)
- [ ] `reader_ok >= 90` (reader читает реальные позиции в ≥ 90% циклов, не mock)
- [ ] `sim_fail=0` (симуляции без ошибок)
- [ ] `fees_usd` по reader'у расходится с Uniswap UI менее чем на 1%
- [ ] Telegram digest отображает execution summary без ошибок
- [ ] `kill_switch` вручную протестирован (поставил `true` → цикл завершился без tx → вернул `false`)

После прохождения → **Gate-3 (LIVE canary)**. Смотри `docs/runbooks/execution-loop-rollout-v1.md` раздел 6–7.
