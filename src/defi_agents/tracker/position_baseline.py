from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

ENTRY_BASELINE_MISSING = "ENTRY_BASELINE_MISSING"
ENTRY_BASELINE_MALFORMED = "ENTRY_BASELINE_MALFORMED"
ENTRY_BASELINE_INCOMPLETE = "ENTRY_BASELINE_INCOMPLETE"

DEFAULT_ENTRY_BASELINE_PATH = Path("docs/memory-bank/position_entry_baselines.json")


@dataclass(frozen=True)
class PositionEntryBaseline:
    position_ref: str
    entry_token0_amount: float
    entry_token1_amount: float
    entry_price_token0_usd: float
    entry_price_token1_usd: float

    @property
    def entry_value_usd(self) -> float:
        return (self.entry_token0_amount * self.entry_price_token0_usd) + (
            self.entry_token1_amount * self.entry_price_token1_usd
        )


@dataclass(frozen=True)
class BaselineLookupResult:
    baseline: PositionEntryBaseline | None = None
    reason_code: str | None = None


class PositionEntryBaselineProvider(Protocol):
    def lookup(self, position_ref: str) -> BaselineLookupResult: ...


class FileBackedPositionBaselineProvider:
    """Deterministic file-backed baseline provider keyed by position_ref (`uni-v3:<token_id>`)."""

    def __init__(self, path: str | Path = DEFAULT_ENTRY_BASELINE_PATH) -> None:
        self._path = Path(path)
        self._loaded = False
        self._global_error_reason: str | None = None
        self._baselines: dict[str, PositionEntryBaseline] = {}
        self._entry_errors: dict[str, str] = {}

    def lookup(self, position_ref: str) -> BaselineLookupResult:
        ref = self._normalize_position_ref(position_ref)
        if not ref:
            return BaselineLookupResult(reason_code=ENTRY_BASELINE_MISSING)

        self._ensure_loaded()

        if self._global_error_reason is not None:
            return BaselineLookupResult(reason_code=self._global_error_reason)

        baseline = self._baselines.get(ref)
        if baseline is not None:
            return BaselineLookupResult(baseline=baseline)

        entry_error = self._entry_errors.get(ref)
        if entry_error is not None:
            return BaselineLookupResult(reason_code=entry_error)

        return BaselineLookupResult(reason_code=ENTRY_BASELINE_MISSING)

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return

        self._loaded = True
        if not self._path.exists():
            return

        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            self._global_error_reason = ENTRY_BASELINE_MALFORMED
            return

        if not isinstance(payload, dict):
            self._global_error_reason = ENTRY_BASELINE_MALFORMED
            return

        positions_payload = payload.get("positions")
        if not isinstance(positions_payload, dict):
            self._global_error_reason = ENTRY_BASELINE_MALFORMED
            return

        for raw_ref, raw_entry in positions_payload.items():
            ref = self._normalize_position_ref(raw_ref)
            if not ref:
                continue
            baseline, reason_code = self._parse_entry(ref, raw_entry)
            if baseline is not None:
                self._baselines[ref] = baseline
            elif reason_code is not None:
                self._entry_errors[ref] = reason_code

    @classmethod
    def _parse_entry(
        cls,
        position_ref: str,
        raw_entry: Any,
    ) -> tuple[PositionEntryBaseline | None, str | None]:
        if not isinstance(raw_entry, dict):
            return None, ENTRY_BASELINE_MALFORMED

        try:
            amount0 = cls._parse_non_negative_float(raw_entry, "entry_token0_amount")
            amount1 = cls._parse_non_negative_float(raw_entry, "entry_token1_amount")
            price0 = cls._parse_non_negative_float(raw_entry, "entry_price_token0_usd")
            price1 = cls._parse_non_negative_float(raw_entry, "entry_price_token1_usd")
        except KeyError:
            return None, ENTRY_BASELINE_INCOMPLETE
        except (TypeError, ValueError):
            return None, ENTRY_BASELINE_MALFORMED

        return (
            PositionEntryBaseline(
                position_ref=position_ref,
                entry_token0_amount=amount0,
                entry_token1_amount=amount1,
                entry_price_token0_usd=price0,
                entry_price_token1_usd=price1,
            ),
            None,
        )

    @staticmethod
    def _parse_non_negative_float(payload: dict[str, Any], key: str) -> float:
        if key not in payload:
            raise KeyError(key)
        value = payload[key]
        if isinstance(value, bool):
            raise TypeError(key)
        parsed = float(value)
        if not math.isfinite(parsed) or parsed < 0.0:
            raise ValueError(key)
        return parsed

    @staticmethod
    def _normalize_position_ref(value: Any) -> str:
        text = str(value or "").strip().lower()
        return text

