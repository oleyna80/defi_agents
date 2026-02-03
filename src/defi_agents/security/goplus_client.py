from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from .models import (
    SecurityReason,
    SecurityResult,
    SecuritySeverity,
    SecuritySource,
    SecuritySourceRecord,
    SecurityStatus,
)


def _to_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"1", "true", "yes"}:
            return True
        if v in {"0", "false", "no"}:
            return False
    return None


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass
class GoPlusFlag:
    code: str
    label: str
    severity: SecuritySeverity
    block: bool = False
    warn: bool = False


class GoPlusClient:
    BASE_URL = "https://api.gopluslabs.io/api/v1/token_security"

    def __init__(self, timeout_seconds: float = 10.0, semaphore=None) -> None:
        self._timeout = timeout_seconds
        self._sem = semaphore

    async def scan(self, address: str, chain_id: str) -> SecurityResult:
        try:
            raw = await self._fetch_api(address, chain_id)
            return self._parse_result(raw, address)
        except Exception as exc:  # noqa: BLE001
            return SecurityResult.unknown_from_error(
                reason=f"GoPlus API Error: {exc}",
                source=SecuritySource.GOPLUS,
            )

    async def _fetch_api(self, address: str, chain_id: str) -> Dict[str, Any]:
        url = f"{self.BASE_URL}/{chain_id}"
        params = {"contract_addresses": address}
        if self._sem:
            async with self._sem:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.get(url, params=params)
                    resp.raise_for_status()
                    return resp.json()

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()

    def _parse_result(self, data: Dict[str, Any], address: str) -> SecurityResult:
        addr = address.lower()
        result = data.get("result", {})
        payload = result.get(addr, {}) if isinstance(result, dict) else {}

        reasons: List[SecurityReason] = []
        status = SecurityStatus.PASS
        score = 80

        # Honeypot
        if _to_bool(payload.get("is_honeypot")):
            reasons.append(
                SecurityReason(
                    code="HONEYPOT_DETECTED",
                    label="Token is flagged as honeypot",
                    severity=SecuritySeverity.CRITICAL,
                    source=SecuritySource.GOPLUS,
                )
            )
            status = SecurityStatus.BLOCK

        # Taxes
        buy_tax = _to_float(payload.get("buy_tax"))
        sell_tax = _to_float(payload.get("sell_tax"))
        max_tax = max(buy_tax or 0.0, sell_tax or 0.0)
        if max_tax >= 0.1:
            reasons.append(
                SecurityReason(
                    code="HIGH_TAX",
                    label=f"High tax detected (buy={buy_tax}, sell={sell_tax})",
                    severity=SecuritySeverity.HIGH,
                    source=SecuritySource.GOPLUS,
                    data={"buy_tax": buy_tax, "sell_tax": sell_tax},
                )
            )
            status = SecurityStatus.BLOCK if max_tax >= 0.1 else status

        # Proxy / ownership risks
        if _to_bool(payload.get("is_proxy")):
            reasons.append(
                SecurityReason(
                    code="PROXY_CONTRACT",
                    label="Token is a proxy contract",
                    severity=SecuritySeverity.MEDIUM,
                    source=SecuritySource.GOPLUS,
                )
            )
            if status == SecurityStatus.PASS:
                status = SecurityStatus.WARN

        if _to_bool(payload.get("hidden_owner")):
            reasons.append(
                SecurityReason(
                    code="HIDDEN_OWNER",
                    label="Owner is hidden or unknown",
                    severity=SecuritySeverity.HIGH,
                    source=SecuritySource.GOPLUS,
                )
            )
            if status != SecurityStatus.BLOCK:
                status = SecurityStatus.WARN

        if reasons and status == SecurityStatus.PASS:
            status = SecurityStatus.WARN

        if status == SecurityStatus.BLOCK:
            score = 10
        elif status == SecurityStatus.WARN:
            score = 60

        sources = [
            SecuritySourceRecord(
                source=SecuritySource.GOPLUS,
                as_of=datetime.now(timezone.utc),
                summary={"address": addr},
            )
        ]

        return SecurityResult(
            status=status,
            score=score,
            reasons=reasons,
            sources=sources,
            is_trusted=False,
            ttl_seconds=3600,
        )
