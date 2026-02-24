from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from ..scout.config import ExecutionPolicyConfig
from .models import ActionIntent, ExecutionCounters, PolicyDecision


class PolicyJournalEntry(BaseModel):
    ts: int
    day_utc: str
    intent_id: str
    action: str
    chain: str
    position_ref: str
    allowed: bool
    reason_codes: list[str] = Field(default_factory=list)
    expected_net_usd: float = 0.0
    estimated_gas_usd: float | None = None
    slippage_bps: int | None = None


class PolicyUsageSnapshot(BaseModel):
    day_utc: str
    daily_txs: int = 0
    daily_gas_usd: float = 0.0


class PolicyGuard:
    """Hard policy checks for execution intents."""

    def __init__(self, config: ExecutionPolicyConfig, max_journal_entries: int = 1_000) -> None:
        self.config = config
        self.max_journal_entries = max(10, int(max_journal_entries))
        self._day_utc = ""
        self._daily_txs = 0
        self._daily_gas_usd = 0.0
        self._journal: list[PolicyJournalEntry] = []

    def evaluate(
        self,
        intent: ActionIntent,
        *,
        estimated_gas_usd: float | None = None,
        slippage_bps: int | None = None,
        counters: ExecutionCounters | None = None,
        now_ts: int | None = None,
    ) -> PolicyDecision:
        now = int(now_ts if now_ts is not None else time.time())
        self._rollover_if_needed(now)
        gas = self._resolve_float(estimated_gas_usd, intent.metadata.get("estimated_gas_usd"))
        slippage = self._resolve_int(slippage_bps, intent.metadata.get("slippage_bps"))

        reasons: list[str] = []
        if intent.action == "SKIP":
            reasons = []
        else:
            if self.config.kill_switch:
                reasons.append("KILL_SWITCH_ENABLED")
            if intent.expected_net_usd < self.config.min_expected_net_usd:
                reasons.append("MIN_EXPECTED_NET_NOT_MET")
            if gas is None:
                reasons.append("GAS_ESTIMATE_MISSING")
            elif gas > self.config.max_gas_usd_per_tx:
                reasons.append("MAX_GAS_USD_PER_TX_EXCEEDED")
            if slippage is None:
                reasons.append("SLIPPAGE_BPS_MISSING")
            elif slippage > self.config.max_slippage_bps:
                reasons.append("MAX_SLIPPAGE_BPS_EXCEEDED")
            if self._daily_txs >= self.config.max_daily_txs:
                reasons.append("MAX_DAILY_TXS_REACHED")
            projected_daily_gas = self._daily_gas_usd + float(gas or 0.0)
            if projected_daily_gas > self.config.max_daily_gas_usd:
                reasons.append("MAX_DAILY_GAS_USD_REACHED")

        allowed = len(reasons) == 0
        if counters is not None and not allowed:
            counters.blocked_by_policy += 1

        self._append_journal(
            PolicyJournalEntry(
                ts=now,
                day_utc=self._day_utc,
                intent_id=intent.intent_id,
                action=intent.action,
                chain=intent.chain,
                position_ref=intent.position_ref,
                allowed=allowed,
                reason_codes=reasons,
                expected_net_usd=float(intent.expected_net_usd),
                estimated_gas_usd=gas,
                slippage_bps=slippage,
            )
        )
        return PolicyDecision(allowed=allowed, reason_codes=reasons)

    def record_executed_tx(self, gas_used_usd: float, *, now_ts: int | None = None) -> None:
        now = int(now_ts if now_ts is not None else time.time())
        self._rollover_if_needed(now)
        self._daily_txs += 1
        self._daily_gas_usd += max(0.0, float(gas_used_usd))

    def usage_snapshot(self, *, now_ts: int | None = None) -> PolicyUsageSnapshot:
        now = int(now_ts if now_ts is not None else time.time())
        self._rollover_if_needed(now)
        return PolicyUsageSnapshot(
            day_utc=self._day_utc,
            daily_txs=self._daily_txs,
            daily_gas_usd=self._daily_gas_usd,
        )

    def get_journal(self, *, limit: int | None = None) -> list[PolicyJournalEntry]:
        if limit is None or limit >= len(self._journal):
            return list(self._journal)
        return list(self._journal[-max(0, int(limit)):])

    def _rollover_if_needed(self, now_ts: int) -> None:
        day_utc = datetime.fromtimestamp(now_ts, tz=timezone.utc).strftime("%Y-%m-%d")
        if day_utc == self._day_utc:
            return
        self._day_utc = day_utc
        self._daily_txs = 0
        self._daily_gas_usd = 0.0

    def _append_journal(self, entry: PolicyJournalEntry) -> None:
        self._journal.append(entry)
        extra = len(self._journal) - self.max_journal_entries
        if extra > 0:
            del self._journal[0:extra]

    @staticmethod
    def _resolve_float(primary: float | None, fallback: Any) -> float | None:
        if primary is not None:
            return float(primary)
        if fallback is None:
            return None
        try:
            return float(fallback)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _resolve_int(primary: int | None, fallback: Any) -> int | None:
        if primary is not None:
            return int(primary)
        if fallback is None:
            return None
        try:
            return int(fallback)
        except (TypeError, ValueError):
            return None
