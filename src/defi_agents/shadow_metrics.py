from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from time import time
from typing import Any

from .cache import CacheController
from .scout.models import ScoutResult


@dataclass
class ShadowMetricsSummary:
    captured_count: int = 0
    evaluated_count: int = 0
    pending_count: int = 0
    median_ape_proxy: float = 0.0
    p75_ape_proxy: float = 0.0
    directional_accuracy_proxy: float = 0.0
    rmse_normalized_proxy: float = 0.0

    def to_log_line(self) -> str:
        return (
            "Shadow metrics: captured=%s evaluated=%s pending=%s "
            "median_ape_proxy=%.2f p75_ape_proxy=%.2f "
            "directional_accuracy_proxy=%.2f rmse_normalized_proxy=%.2f"
        ) % (
            self.captured_count,
            self.evaluated_count,
            self.pending_count,
            self.median_ape_proxy,
            self.p75_ape_proxy,
            self.directional_accuracy_proxy,
            self.rmse_normalized_proxy,
        )


class ShadowMetricsTracker:
    """Tracks shadow-mode prediction drift using cycle-to-cycle proxy outcomes.

    NOTE: These are proxy metrics (predicted-vs-later-estimated), not realized PnL.
    They are used for rollout calibration and model drift monitoring.
    """

    def __init__(
        self,
        *,
        cache: CacheController | None = None,
        horizon_seconds: int = 86_400,
        capture_interval_seconds: int = 21_600,
        retention_seconds: int = 1_209_600,
    ) -> None:
        self._cache = cache or CacheController(namespace="lp_shadow_metrics")
        self._horizon_seconds = max(60, int(horizon_seconds))
        self._capture_interval_seconds = max(60, int(capture_interval_seconds))
        self._retention_seconds = max(3_600, int(retention_seconds))

    def process(self, picks: list[ScoutResult]) -> ShadowMetricsSummary:
        now = int(time())
        state = self._cache.get("state")
        entries: list[dict[str, Any]] = list(state.get("entries", [])) if isinstance(state, dict) else []

        current_by_pool: dict[str, float] = {}
        for pick in picks:
            pool_id = str(getattr(pick.candidate, "pool_id", "") or "").strip()
            if not pool_id:
                continue
            current_by_pool[pool_id] = self._parse_net_profit_1k(pick)

        captured_count = 0
        evaluated_count = 0
        for entry in entries:
            pool_id = str(entry.get("pool_id", "")).strip()
            created_at = int(entry.get("created_at", 0) or 0)
            if not pool_id or created_at <= 0:
                continue
            if entry.get("evaluated_at"):
                continue
            if (now - created_at) < self._horizon_seconds:
                continue
            if pool_id not in current_by_pool:
                continue
            predicted = float(entry.get("predicted_net_profit_1k", 0.0) or 0.0)
            realized_proxy = float(current_by_pool[pool_id])
            entry["realized_proxy_net_profit_1k"] = realized_proxy
            entry["evaluated_at"] = now
            entry["ape_proxy"] = self._abs_pct_error(predicted, realized_proxy)
            entry["squared_error"] = (realized_proxy - predicted) ** 2
            entry["direction_hit"] = 1 if self._same_sign(predicted, realized_proxy) else 0
            evaluated_count += 1

        latest_by_pool: dict[str, int] = {}
        for entry in entries:
            pool_id = str(entry.get("pool_id", "")).strip()
            created_at = int(entry.get("created_at", 0) or 0)
            if not pool_id or created_at <= 0:
                continue
            prev = latest_by_pool.get(pool_id, 0)
            if created_at > prev:
                latest_by_pool[pool_id] = created_at

        for pick in picks:
            pool_id = str(getattr(pick.candidate, "pool_id", "") or "").strip()
            if not pool_id:
                continue
            last_created = latest_by_pool.get(pool_id, 0)
            if last_created and (now - last_created) < self._capture_interval_seconds:
                continue
            entries.append(
                {
                    "pool_id": pool_id,
                    "chain": getattr(pick.candidate, "chain", ""),
                    "symbol": getattr(pick.candidate, "symbol", ""),
                    "project": getattr(pick.candidate, "project", ""),
                    "created_at": now,
                    "predicted_net_profit_1k": self._parse_net_profit_1k(pick),
                    "predicted_net_apy": float(getattr(pick, "net_apy", 0.0) or 0.0),
                    "score": float(getattr(pick, "score", 0.0) or 0.0),
                }
            )
            latest_by_pool[pool_id] = now
            captured_count += 1

        min_ts = now - self._retention_seconds
        entries = [entry for entry in entries if int(entry.get("created_at", 0) or 0) >= min_ts]

        summary = self._summarize(entries, captured_count=captured_count, evaluated_count=evaluated_count)
        self._cache.set("state", {"entries": entries}, ttl_seconds=self._retention_seconds)
        return summary

    def latest_prediction(self, pool_id: str) -> dict[str, Any] | None:
        pool_key = str(pool_id or "").strip()
        if not pool_key:
            return None
        state = self._cache.get("state")
        entries: list[dict[str, Any]] = list(state.get("entries", [])) if isinstance(state, dict) else []
        latest: dict[str, Any] | None = None
        for entry in entries:
            if str(entry.get("pool_id", "")).strip() != pool_key:
                continue
            if latest is None or int(entry.get("created_at", 0) or 0) > int(latest.get("created_at", 0) or 0):
                latest = entry
        return latest

    def _summarize(
        self,
        entries: list[dict[str, Any]],
        *,
        captured_count: int,
        evaluated_count: int,
    ) -> ShadowMetricsSummary:
        evaluated = [entry for entry in entries if entry.get("evaluated_at")]
        pending_count = len(entries) - len(evaluated)
        if not evaluated:
            return ShadowMetricsSummary(
                captured_count=captured_count,
                evaluated_count=evaluated_count,
                pending_count=pending_count,
            )

        ape_values = [float(entry.get("ape_proxy", 0.0) or 0.0) for entry in evaluated]
        ape_sorted = sorted(ape_values)
        p75_index = int(0.75 * (len(ape_sorted) - 1))
        p75 = ape_sorted[p75_index] if ape_sorted else 0.0

        hits = sum(int(entry.get("direction_hit", 0) or 0) for entry in evaluated)
        directional_accuracy = hits / float(len(evaluated)) if evaluated else 0.0

        mse = sum(float(entry.get("squared_error", 0.0) or 0.0) for entry in evaluated) / float(len(evaluated))
        rmse = mse ** 0.5
        mean_abs_pred = sum(abs(float(entry.get("predicted_net_profit_1k", 0.0) or 0.0)) for entry in evaluated) / float(
            len(evaluated)
        )
        rmse_normalized = rmse / mean_abs_pred if mean_abs_pred > 0 else 0.0

        return ShadowMetricsSummary(
            captured_count=captured_count,
            evaluated_count=evaluated_count,
            pending_count=pending_count,
            median_ape_proxy=median(ape_values),
            p75_ape_proxy=p75,
            directional_accuracy_proxy=directional_accuracy,
            rmse_normalized_proxy=rmse_normalized,
        )

    @staticmethod
    def _parse_net_profit_1k(pick: ScoutResult) -> float:
        raw = pick.metadata.get("net_profit_1k_usd")
        if isinstance(raw, (int, float)):
            return float(raw)
        if isinstance(raw, str):
            try:
                return float(raw.strip())
            except ValueError:
                pass
        return float((1000.0 * (float(getattr(pick, "net_apy", 0.0) or 0.0) / 100.0)) / 12.0)

    @staticmethod
    def _abs_pct_error(predicted: float, realized: float) -> float:
        denom = abs(predicted)
        if denom <= 1e-9:
            return 0.0 if abs(realized) <= 1e-9 else 1.0
        return abs(realized - predicted) / denom

    @staticmethod
    def _same_sign(a: float, b: float) -> bool:
        if abs(a) <= 1e-9 or abs(b) <= 1e-9:
            return a == b
        return (a > 0 and b > 0) or (a < 0 and b < 0)
