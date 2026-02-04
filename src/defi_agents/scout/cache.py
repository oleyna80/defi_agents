from __future__ import annotations

from typing import Optional

from ..cache import CacheController


class ScoutDeduper:
    def __init__(self, ttl_seconds: int = 86400) -> None:
        self._ttl = ttl_seconds
        # Persist across oneshot systemd runs to avoid Telegram spam.
        self._cache = CacheController(namespace="scout_dedupe")

    def seen_recently(self, key: str, score: float) -> bool:
        previous = self._cache.get(key)
        if previous is None:
            return False
        try:
            previous_score = float(previous)
        except (TypeError, ValueError):
            return False
        # if score unchanged, treat as duplicate
        return abs(previous_score - float(score)) < 1e-6

    def update(self, key: str, score: float) -> None:
        self._cache.set(key, float(score), ttl_seconds=self._ttl)
