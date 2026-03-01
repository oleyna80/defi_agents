from __future__ import annotations

import time
from datetime import datetime, timezone

from ..scout.config import HedgerConfig
from .models import HedgeCounters, HedgeExposure, HedgeIntent, HedgeSide


class HedgeCalculator:
    """Deterministic hedge intent calculator for PAPER/SHADOW modes."""

    def __init__(self, config: HedgerConfig) -> None:
        self.config = config
        self._day_utc = ""
        self._daily_notional_usd = 0.0
        self._last_hedge_by_symbol: dict[str, int] = {}

    def evaluate_exposure(self, exposure: HedgeExposure, now_ts: int | None = None) -> HedgeIntent:
        now = int(now_ts if now_ts is not None else time.time())
        self._rollover_if_needed(now)

        reasons: list[str] = []
        policy_reasons = self._policy_reasons(exposure)
        if policy_reasons:
            reasons.extend(policy_reasons)
            return self._intent(exposure, action="SKIP", side="NONE", target_notional_usd=0.0, now_ts=now, reason_codes=reasons)

        data_reasons = self._data_reasons(exposure)
        if data_reasons:
            reasons.extend(data_reasons)
            return self._intent(exposure, action="SKIP", side="NONE", target_notional_usd=0.0, now_ts=now, reason_codes=reasons)

        hedge_notional = abs(float(exposure.delta_usd)) * float(self.config.default_hedge_ratio)
        if hedge_notional < self.config.policy.min_rebalance_notional_usd:
            return self._intent(
                exposure,
                action="HOLD",
                side="NONE",
                target_notional_usd=0.0,
                now_ts=now,
                reason_codes=["DELTA_BELOW_MIN_NOTIONAL"],
            )

        if self._is_cooldown_active(exposure.symbol, now):
            return self._intent(
                exposure,
                action="HOLD",
                side="NONE",
                target_notional_usd=0.0,
                now_ts=now,
                reason_codes=["COOLDOWN_ACTIVE"],
            )

        if hedge_notional > self.config.policy.max_notional_usd_per_order:
            return self._intent(
                exposure,
                action="SKIP",
                side="NONE",
                target_notional_usd=0.0,
                now_ts=now,
                reason_codes=["MAX_NOTIONAL_PER_ORDER_EXCEEDED"],
            )

        projected_notional = self._daily_notional_usd + hedge_notional
        if projected_notional > self.config.policy.max_daily_notional_usd:
            return self._intent(
                exposure,
                action="SKIP",
                side="NONE",
                target_notional_usd=0.0,
                now_ts=now,
                reason_codes=["MAX_DAILY_NOTIONAL_REACHED"],
            )

        side: HedgeSide = "SHORT" if exposure.delta_usd > 0 else "LONG"
        self._daily_notional_usd = projected_notional
        self._last_hedge_by_symbol[exposure.symbol.upper()] = now
        return self._intent(
            exposure,
            action="HEDGE",
            side=side,
            target_notional_usd=hedge_notional,
            now_ts=now,
            reason_codes=["DELTA_HEDGE_REQUIRED"],
        )

    def evaluate_batch(self, exposures: list[HedgeExposure], now_ts: int | None = None) -> tuple[list[HedgeIntent], HedgeCounters]:
        intents: list[HedgeIntent] = []
        counters = HedgeCounters(exposures_seen=len(exposures))
        for exposure in exposures:
            intent = self.evaluate_exposure(exposure, now_ts=now_ts)
            intents.append(intent)
            if intent.action == "HEDGE":
                counters.intents_hedge += 1
            elif intent.action == "HOLD":
                counters.intents_hold += 1
            else:
                counters.intents_skip += 1
                if any(reason.startswith("MAX_") or reason == "KILL_SWITCH_ENABLED" for reason in intent.reason_codes):
                    counters.skipped_by_policy += 1
                else:
                    counters.skipped_by_data += 1
        return intents, counters

    def _policy_reasons(self, exposure: HedgeExposure) -> list[str]:
        reasons: list[str] = []
        if self.config.policy.kill_switch:
            reasons.append("KILL_SWITCH_ENABLED")
        if float(self.config.default_hedge_ratio) <= 0.0:
            reasons.append("HEDGE_RATIO_DISABLED")
        if float(exposure.delta_usd) == 0.0:
            reasons.append("ZERO_DELTA")
        return reasons

    def _data_reasons(self, exposure: HedgeExposure) -> list[str]:
        reasons: list[str] = []
        if exposure.freshness_age_seconds > self.config.exposure_max_age_seconds:
            reasons.append("EXPOSURE_STALE")
        if exposure.mark_price_usd <= 0.0:
            reasons.append("MARK_PRICE_MISSING")
        return reasons

    def _is_cooldown_active(self, symbol: str, now_ts: int) -> bool:
        last_ts = self._last_hedge_by_symbol.get(symbol.upper())
        if last_ts is None:
            return False
        return (now_ts - int(last_ts)) < self.config.per_symbol_cooldown_seconds

    def _rollover_if_needed(self, now_ts: int) -> None:
        day_utc = datetime.fromtimestamp(now_ts, tz=timezone.utc).strftime("%Y-%m-%d")
        if day_utc == self._day_utc:
            return
        self._day_utc = day_utc
        self._daily_notional_usd = 0.0

    @staticmethod
    def _intent(
        exposure: HedgeExposure,
        *,
        action: str,
        side: HedgeSide,
        target_notional_usd: float,
        now_ts: int,
        reason_codes: list[str],
    ) -> HedgeIntent:
        return HedgeIntent(
            intent_id=f"{exposure.chain}:{exposure.position_ref}:{action}:{now_ts}",
            action=action,  # type: ignore[arg-type]
            side=side,
            chain=exposure.chain,
            symbol=exposure.symbol,
            target_notional_usd=max(0.0, float(target_notional_usd)),
            reason_codes=list(reason_codes),
            metadata={
                "delta_usd": float(exposure.delta_usd),
                "mark_price_usd": float(exposure.mark_price_usd),
                "freshness_age_seconds": int(exposure.freshness_age_seconds),
            },
        )

