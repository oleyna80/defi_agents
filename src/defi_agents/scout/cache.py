from __future__ import annotations

from dataclasses import dataclass
from time import time
from typing import Dict, Optional


@dataclass
class _Entry:
    ts: float
    score: float


class ScoutDeduper:
    def __init__(self, ttl_seconds: int = 86400) -> None:
        self._ttl = ttl_seconds
        self._cache: Dict[str, _Entry] = {}

    def seen_recently(self, key: str, score: float) -> bool:
        now = time()
        entry = self._cache.get(key)
        if not entry:
            return False
        if now - entry.ts > self._ttl:
            return False
        # if score unchanged, treat as duplicate
        return abs(entry.score - score) < 1e-6

    def update(self, key: str, score: float) -> None:
        self._cache[key] = _Entry(ts=time(), score=score)
