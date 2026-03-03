from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

from .models import EntryActionability, EntryRecommendation


@dataclass(frozen=True)
class EntryStabilityTelemetry:
    entry_total: int
    entry_actionable: int
    entry_watchlist: int
    entry_watchlist_insufficient_history: int
    entry_topn_churn: float
    topn_pool_ids: list[str]


def compute_stability_observation_counts(
    pool_ids: Iterable[str],
    *,
    history_path: str | Path,
    lookback_hours: int,
    now_epoch: int | None = None,
) -> dict[str, int]:
    normalized_pool_ids = normalize_pool_ids(pool_ids)
    counts = {pool_id: 0 for pool_id in normalized_pool_ids}
    if not normalized_pool_ids:
        return counts

    window_hours = int(lookback_hours)
    if window_hours <= 0:
        return counts

    path = Path(history_path)
    if not path.exists():
        return counts

    now_ts = int(now_epoch) if now_epoch is not None else int(datetime.now(timezone.utc).timestamp())
    cutoff = now_ts - (window_hours * 3600)
    pool_id_set = set(normalized_pool_ids)

    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                pool_id = str(row.get("pool_id") or "").strip()
                if not pool_id or pool_id not in pool_id_set:
                    continue
                ts = _parse_timestamp(row.get("timestamp"))
                if ts is None or ts < cutoff:
                    continue
                counts[pool_id] = counts.get(pool_id, 0) + 1
    except OSError:
        return counts

    return counts


def summarize_entry_stability_telemetry(
    recommendations: Sequence[EntryRecommendation],
    *,
    top_n: int,
    previous_topn_pool_ids: Sequence[str] | None,
) -> EntryStabilityTelemetry:
    entry_total = len(recommendations)
    entry_actionable = sum(
        1
        for rec in recommendations
        if rec.actionability == EntryActionability.ACTIONABLE
    )
    entry_watchlist = entry_total - entry_actionable
    entry_watchlist_insufficient_history = sum(
        1
        for rec in recommendations
        if rec.actionability == EntryActionability.WATCHLIST
        and rec.watchlist_reason == "INSUFFICIENT_STABILITY_HISTORY"
    )

    actionable_pool_ids = [
        rec.source_pool_id
        for rec in recommendations
        if rec.actionability == EntryActionability.ACTIONABLE and rec.source_pool_id
    ]
    current_topn_pool_ids = normalize_pool_ids(actionable_pool_ids[: max(1, int(top_n or 1))])
    previous_pool_ids = normalize_pool_ids(previous_topn_pool_ids or [])
    entry_topn_churn = _compute_topn_churn(current_topn_pool_ids, previous_pool_ids)

    return EntryStabilityTelemetry(
        entry_total=entry_total,
        entry_actionable=entry_actionable,
        entry_watchlist=entry_watchlist,
        entry_watchlist_insufficient_history=entry_watchlist_insufficient_history,
        entry_topn_churn=entry_topn_churn,
        topn_pool_ids=current_topn_pool_ids,
    )


def normalize_pool_ids(pool_ids: Iterable[object]) -> list[str]:
    out: list[str] = []
    for item in pool_ids:
        value = str(item or "").strip()
        if not value or value in out:
            continue
        out.append(value)
    return out


def _compute_topn_churn(current: Sequence[str], previous: Sequence[str]) -> float:
    current_set = set(current)
    previous_set = set(previous)
    union = current_set | previous_set
    if not union:
        return 0.0
    return float(len(current_set.symmetric_difference(previous_set))) / float(len(union))


def _parse_timestamp(raw: object) -> int | None:
    if raw in (None, ""):
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        if text.isdigit() or (text.startswith("-") and text[1:].isdigit()):
            return int(text)
        return int(float(text))
    except (TypeError, ValueError):
        pass

    try:
        iso = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())

