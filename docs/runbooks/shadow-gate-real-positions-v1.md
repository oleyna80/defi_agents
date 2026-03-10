# SHADOW Gate: Real Positions — Checklist

Runbook для прохождения Gate-2 (48h SHADOW) на реальных позициях после внедрения multi-chain execution state source (`execution.chains`).

---

## Шаг 1: Добавить `WALLET_ADDRESS` в `.env`

```bash
cd ~/projects/defi_agents

# Добавить строку (замени адрес на свой)
echo 'WALLET_ADDRESS=0xYourWalletAddressHere' >> .env

# Проверить что записалось
grep WALLET_ADDRESS .env
```

Проверь, что `docs/memory-bank/scout_config.json` содержит complete `execution.chains` (по каждой активной сети обязательны `rpc_url`, `coingecko_platform_id`, `uniswap_v3.factory_proxy`, `uniswap_v3.position_manager_proxy`):

```bash
python - <<'PY'
import json
from pathlib import Path

cfg = json.loads(Path("docs/memory-bank/scout_config.json").read_text())
chains = cfg.get("scout_settings", {}).get("execution", {}).get("chains", {})
required = (
    "rpc_url",
    "coingecko_platform_id",
    "uniswap_v3.factory_proxy",
    "uniswap_v3.position_manager_proxy",
)
print(f"chains_configured={len(chains)}")
for chain, item in sorted(chains.items()):
    uv3 = item.get("uniswap_v3", {}) if isinstance(item, dict) else {}
    present = {
        "rpc_url": bool(str(item.get("rpc_url", "")).strip()) if isinstance(item, dict) else False,
        "coingecko_platform_id": bool(str(item.get("coingecko_platform_id", "")).strip()) if isinstance(item, dict) else False,
        "uniswap_v3.factory_proxy": bool(str(uv3.get("factory_proxy", "")).strip()),
        "uniswap_v3.position_manager_proxy": bool(str(uv3.get("position_manager_proxy", "")).strip()),
    }
    missing = [name for name in required if not present[name]]
    print(f"{chain}: {'OK' if not missing else 'INCOMPLETE -> ' + ','.join(missing)}")
PY
```

---

## Шаг 2: Smoke-проверка reader'а (1 цикл локально)

Запустить изолированный multi-chain smoke reader'а без запуска полного sentinel:

```bash
cd ~/projects/defi_agents
source .venv/bin/activate

python - <<'PY'
import asyncio, os
import json
from pathlib import Path
from dotenv import load_dotenv
from defi_agents.tracker.position_reader import BaseUniswapV3PositionReader

load_dotenv()
wallet = os.environ["WALLET_ADDRESS"]
cfg = json.loads(Path("docs/memory-bank/scout_config.json").read_text())
chains = cfg.get("scout_settings", {}).get("execution", {}).get("chains", {})

async def main():
    total = 0
    total_stale = 0
    total_fees_usd = 0.0
    for chain_name, item in sorted(chains.items()):
        uv3 = item.get("uniswap_v3", {}) if isinstance(item, dict) else {}
        if not (
            isinstance(item, dict)
            and str(item.get("rpc_url", "")).strip()
            and str(item.get("coingecko_platform_id", "")).strip()
            and str(uv3.get("factory_proxy", "")).strip()
            and str(uv3.get("position_manager_proxy", "")).strip()
        ):
            print(f"[{chain_name}] skipped: incomplete execution.chains entry")
            continue
        reader = BaseUniswapV3PositionReader(
            chain_name=chain_name,
            rpc_url=item["rpc_url"],
            coingecko_platform_id=item["coingecko_platform_id"],
            factory_address=uv3["factory_proxy"],
            position_manager_address=uv3["position_manager_proxy"],
        )
        states = await reader.load_active_position_states(wallet)
        chain_stale = 0
        chain_fees_usd = 0.0
        for state in states:
            in_range = not state.out_of_range
            fees_usd = float(state.unclaimed_fees_usd)
            stale = bool(state.stale)
            stale_codes = sorted(
                set(
                    list(state.stale_reason_codes or [])
                    + list((state.metadata or {}).get("fee_reason_codes", []))
                )
            )
            if stale:
                chain_stale += 1
            chain_fees_usd += fees_usd
            print(
                f"[{chain_name}] position_ref={state.position_ref} "
                f"in_range={in_range} fees_usd={fees_usd:.6f} "
                f"stale={stale} stale_codes={stale_codes}"
            )
        total += len(states)
        total_stale += chain_stale
        total_fees_usd += chain_fees_usd
        print(
            f"[{chain_name}] active_positions={len(states)} "
            f"stale_positions={chain_stale} fees_usd_total={chain_fees_usd:.6f}"
        )
    print(f"Loaded total active positions across chains: {total}")
    print(f"Loaded total stale positions across chains: {total_stale}")
    print(f"Loaded total fees_usd across chains: {total_fees_usd:.6f}")

asyncio.run(main())
PY
```

**Целевой результат:**

| Поле | Ожидание |
|---|---|
| `position_ref` | Формат `uni-v3:<token_id>` для каждой позиции |
| `in_range` | `True/False` по каждой позиции (сверить визуально в Uniswap UI) |
| `fees_usd` | По каждой позиции: отклонение от Uniswap UI `< 1%` |
| `stale` | Для healthy-позиций `False` |
| `stale_codes` | Для healthy-позиций `[]`; не должно быть `STALE_POSITION_DATA`/`STALE_PRICE` |
| `[chain] active_positions` | По каждой сети `>= 0` |
| `[chain] fees_usd_total` | Сумма `fees_usd` по позициям сети |
| `[chain] stale_positions` | Кол-во stale-позиций в сети |
| `Loaded total active positions across chains` | ≥ 1 |
| `Loaded total fees_usd across chains` | Сумма `fees_usd` по всем сетям |
| `Loaded total stale positions across chains` | `0` для полностью healthy smoke |

> **Верификация fees vs UI:** Открой Uniswap UI → твои позиции → сверяй `Unclaimed fees` с `fees_usd` **по каждой** `position_ref`.
> Сравнение `< 1%` считается валидным при `stale=False` и `stale_codes=[]`.
> Если в `stale_codes` есть `STALE_PRICE`, сначала проверь доступность CoinGecko: `curl "https://api.coingecko.com/api/v3/ping"`.

---

## Шаг 3: Деплой на VPS и запуск SHADOW

### 3.1 Залить код на VPS

```bash
# На VPS:
cd ~/projects/defi_agents
git pull
source .venv/bin/activate
python -m pytest -q tests/test_execution_config.py tests/test_execution_state_source.py
```

### 3.2 Убедиться в конфиге

```bash
python - <<'PY'
import json
from pathlib import Path

cfg = json.loads(Path("docs/memory-bank/scout_config.json").read_text())
execution = cfg.get("scout_settings", {}).get("execution", {})
print("enabled=", execution.get("enabled"))
print("mode=", execution.get("mode"))
print("primary_adapter=", execution.get("primary_adapter"))
print("allow_live_mode=", execution.get("allow_live_mode"))
print("kill_switch=", execution.get("policy", {}).get("kill_switch"))
print("chains=", sorted((execution.get("chains") or {}).keys()))
PY
```

Должно быть:
- `"enabled": true`
- `"mode": "SHADOW"`
- `"primary_adapter": "uniswap_v3_simulate"`
- `"allow_live_mode": false`
- `"kill_switch": false`
- `"execution.chains"` не пустой и содержит только complete chain entries

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
Execution states loaded: source=position_reader chain=<ChainName> active_states=N
Execution summary: mode=SHADOW states=N tx_plans=... sim_ok=... exec_ok=0 ...
```

Для multi-chain деградации ожидаемые сигнатуры:

```
Execution state source degraded: chain=<ChainName> reason=POSITION_READER_ERROR ... source=position_reader
Execution state source failed: reason=POSITION_READER_ALL_CHAINS_FAILED failed_chains=<csv> source=position_reader
```

Если `WALLET_ADDRESS` не задан на VPS → появится:
```
Execution state source unavailable: reason=WALLET_ADDRESS_MISSING source=position_reader
```
Это fail-closed поведение: execution loop будет пропущен, fallback на `mock_positions` больше не используется.

Если деградировала только часть сетей, цикл продолжает работу по остальным active chains (partial degradation).

---

## Шаг 4: 48h мониторинг

### Быстрая проверка каждые несколько часов:

```bash
journalctl --user -u defi-sentinel.service --since "3 hours ago" --no-pager | \
  grep -E "source=position_reader|POSITION_READER_ERROR|POSITION_READER_ALL_CHAINS_FAILED|STALE_POSITION_DATA|STALE_PRICE|Traceback|CRITICAL"
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

Альтернатива (автоматизированный snapshot в JSON):

```bash
cd ~/projects/defi_agents
make gate3-evidence-report
```

Команда формирует **Evidence contract v1** и агрегирует в одном JSON:
- preflight (`wallet_set`, `rpc_set`, `baseline_positions_count`, `shadow_log_loaded`);
- counters (`execution_cycles`, `reader_ok`, `sim_ok`, `sim_fail`, `errors`);
- math contract:
  - `expected_pnl_vs_hodl_usd = position_pnl_usd - hodl_pnl_usd`
  - `deviation_pct = abs(actual - reference) / max(abs(reference), near_zero_epsilon) * 100`
  - `p95_method = nearest-rank (ceil(0.95 * N))`
- deterministic gate outputs:
  - `positions_total`
  - `positions_validated_count`
  - `pnl_hodl_deviation_max_pct`
  - `pnl_hodl_deviation_p95_pct`
  - `pnl_hodl_under_1pct_pass`
  - `min_positions_pass`
  - `reader_ok_count`
  - `reader_ok_threshold_pass`
  - `errors_zero_pass`
  - `all_pass`
- fail-safe diagnostics:
  - `missing_artifacts`
  - `evidence_gaps`
  - `reasons`

Для offline/handmade evidence (без journalctl/reader fetch) можно передать входные артефакты явно:

```bash
PYTHONPATH=src .venv/bin/python scripts/gate3_evidence_report.py \
  --from-file docs/reports/artifacts/<shadow-log>.log \
  --positions-file docs/reports/artifacts/<positions-snapshot>.json \
  --manual-check-file docs/reports/artifacts/<ui-manual-check>.json
```

Для объединения нескольких логов в одно 48h evidence-окно, флаг `--from-file` повторяется:

```bash
PYTHONPATH=src .venv/bin/python scripts/gate3_evidence_report.py \
  --from-file docs/reports/artifacts/<shadow-log-part1>.log \
  --from-file docs/reports/artifacts/<shadow-log-part2>.log \
  --positions-file docs/reports/artifacts/<positions-snapshot>.json
```

В contract v1 также выводится явный итоговый `verdict` (`PASS|FAIL`) вместе с `all_pass`,
а причины отказа остаются в `evidence_gaps` и `reasons`.

---

## Gate-2 DoD (условия прохождения)

- [ ] `errors=0` (нет Traceback/CRITICAL за 48h)
- [ ] `reader_ok >= 90` (reader читает реальные позиции в ≥ 90% циклов, не mock)
- [ ] `sim_fail=0` (симуляции без ошибок)
- [ ] нет `POSITION_READER_ALL_CHAINS_FAILED` за 48h
- [ ] `fees_usd` по reader'у расходится с Uniswap UI менее чем на 1%
- [ ] Telegram digest отображает execution summary без ошибок
- [ ] `kill_switch` вручную протестирован (поставил `true` → цикл завершился без tx → вернул `false`)

После прохождения → **Gate-3 (LIVE canary)**. Смотри `docs/runbooks/execution-loop-rollout-v1.md` раздел 6–7.
