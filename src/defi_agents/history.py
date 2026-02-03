from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from .scout.models import ScoutResult


def save_to_history(results: Iterable[ScoutResult], path: str | Path = "docs/memory-bank/history.csv") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    with path.open("a", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(
                [
                    "timestamp",
                    "chain",
                    "symbol",
                    "project",
                    "pool_id",
                    "apy",
                    "apy_base",
                    "apy_reward",
                    "tvl_usd",
                    "score",
                    "net_apy",
                    "net_profit_usd",
                    "security_status",
                    "l3_status",
                    "l3_confidence",
                    "l3_reason_codes",
                    "l3_cache_hit",
                    "l3_model",
                ]
            )
        for r in results:
            c = r.candidate
            l3 = c.l3_data
            metadata = getattr(l3, "metadata", None)
            writer.writerow(
                [
                    c.timestamp,
                    c.chain,
                    c.symbol,
                    c.project,
                    c.pool_id,
                    c.apy,
                    c.apy_base,
                    c.apy_reward,
                    c.tvl_usd,
                    r.score,
                    r.net_apy,
                    r.net_profit_usd,
                    getattr(r.security, "status", None),
                    getattr(c.l3_status, "value", c.l3_status),
                    getattr(l3, "confidence", None),
                    ",".join(code.value for code in (l3.reason_codes if l3 else [])),
                    getattr(metadata, "cache_hit_analysis", None),
                    getattr(metadata, "model", None),
                ]
            )
