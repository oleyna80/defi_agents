from __future__ import annotations

from pydantic import BaseModel, Field

from .calculator import HedgeCalculator
from .models import HedgeConnector, HedgeCounters, HedgeExposure, HedgeIntent, HedgeMode


class HedgerRunReport(BaseModel):
    mode: HedgeMode
    counters: HedgeCounters = Field(default_factory=HedgeCounters)
    intents: list[HedgeIntent] = Field(default_factory=list)
    sim_ok: int = 0
    sim_fail: int = 0
    sim_fail_reason_counts: dict[str, int] = Field(default_factory=dict)
    connector_reason_counts: dict[str, int] = Field(default_factory=dict)


class HedgerOrchestrator:
    """Orchestrator for hedger PAPER/SHADOW runs."""

    def __init__(
        self,
        *,
        mode: HedgeMode,
        calculator: HedgeCalculator,
        connector: HedgeConnector | None = None,
    ) -> None:
        self.mode = mode
        self.calculator = calculator
        self.connector = connector

    async def run_exposures(self, exposures: list[HedgeExposure], *, now_ts: int | None = None) -> HedgerRunReport:
        intents, counters = self.calculator.evaluate_batch(exposures, now_ts=now_ts)
        report = HedgerRunReport(mode=self.mode, counters=counters, intents=intents)

        if self.mode == "PAPER":
            return report

        hedge_intents = [intent for intent in intents if intent.action == "HEDGE"]
        if self.connector is None:
            for _ in hedge_intents:
                report.sim_fail += 1
                report.counters.connector_errors += 1
                self._bump_reasons(report.sim_fail_reason_counts, ["CONNECTOR_UNCONFIGURED"])
                self._bump_reasons(report.connector_reason_counts, ["CONNECTOR_UNCONFIGURED"])
            return report

        for intent in hedge_intents:
            try:
                sim = await self.connector.simulate_order(
                    intent,
                    max_slippage_bps=self.calculator.config.policy.max_slippage_bps,
                )
            except Exception:  # noqa: BLE001
                report.sim_fail += 1
                report.counters.connector_errors += 1
                self._bump_reasons(report.sim_fail_reason_counts, ["CONNECTOR_EXCEPTION"])
                self._bump_reasons(report.connector_reason_counts, ["CONNECTOR_EXCEPTION"])
                continue

            if sim.ok:
                report.sim_ok += 1
                continue

            report.sim_fail += 1
            self._bump_reasons(report.sim_fail_reason_counts, sim.reason_codes)
            connector_reasons = [reason for reason in sim.reason_codes if self._is_connector_reason(reason)]
            if connector_reasons:
                report.counters.connector_errors += 1
                self._bump_reasons(report.connector_reason_counts, connector_reasons)

        return report

    @staticmethod
    def _is_connector_reason(reason: str) -> bool:
        value = str(reason or "").upper()
        if not value:
            return False
        prefixes = (
            "CONNECTOR_",
            "AUTH_",
            "ENDPOINT_",
            "BBO_",
            "MARKET_",
        )
        if value.startswith(prefixes):
            return True
        if value in {"CONNECTOR_NOT_READY", "BBO_UNAVAILABLE"}:
            return True
        return False

    @staticmethod
    def _bump_reasons(bucket: dict[str, int], reasons: list[str]) -> None:
        if not reasons:
            bucket["UNKNOWN"] = bucket.get("UNKNOWN", 0) + 1
            return
        for reason in reasons:
            key = str(reason or "UNKNOWN")
            bucket[key] = bucket.get(key, 0) + 1

