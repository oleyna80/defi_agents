from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class FreshnessSnapshot:
    provider: str
    source_timestamp: datetime | None
    apy: float | None
    tvl_usd: float | None
