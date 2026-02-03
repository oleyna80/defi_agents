from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from time import time
from typing import Any


class CacheController:
    """Tiny file-backed TTL cache used by async pipeline modules."""

    def __init__(
        self,
        namespace: str,
        *,
        base_dir: str | Path = "docs/memory-bank/cache",
    ) -> None:
        self.namespace = namespace
        self.path = Path(base_dir) / f"{namespace}.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, dict[str, Any]] = {}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        if not self.path.exists():
            self._loaded = True
            return
        try:
            raw = json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            self._loaded = True
            return
        if isinstance(raw, dict):
            self._data = raw
        self._loaded = True

    def _save(self) -> None:
        temp_path = Path(f"{self.path}.tmp")
        try:
            with temp_path.open("w", encoding="utf-8") as handle:
                json.dump(self._data, handle, indent=2, sort_keys=True)
            os.replace(temp_path, self.path)
        except Exception:
            if temp_path.exists():
                temp_path.unlink()
            logging.error("Cache save failed for %s", self.path)
            raise

    def get(self, key: str) -> Any | None:
        self._load()
        item = self._data.get(key)
        if not item:
            return None
        expires_at = float(item.get("expires_at", 0))
        if expires_at and time() > expires_at:
            self._data.pop(key, None)
            self._save()
            return None
        return item.get("value")

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        self._load()
        self._data[key] = {
            "value": value,
            "expires_at": time() + max(0, ttl_seconds),
        }
        self._save()
