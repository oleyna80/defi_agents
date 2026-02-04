from __future__ import annotations

from typing import Protocol

from ...scout.models import ScoutResult
from ..types import FreshnessSnapshot


class FreshnessAdapter(Protocol):
    name: str

    def supports(self, result: ScoutResult) -> bool:
        ...

    async def fetch_snapshot(self, result: ScoutResult) -> FreshnessSnapshot | None:
        ...
