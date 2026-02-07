from __future__ import annotations

from datetime import datetime, timezone
import logging
import os

import httpx

from ...scout.models import ScoutResult
from ..types import FreshnessSnapshot

logger = logging.getLogger(__name__)


class AaveDirectAdapter:
    name = "aave_direct"

    def __init__(
        self,
        *,
        enabled: bool = False,
        timeout_seconds: int = 8,
        endpoints: dict[str, str] | None = None,
        reserve_symbols: dict[str, dict[str, str]] | None = None,
        api_key_env: str = "AAVE_DIRECT_API_KEY",
    ) -> None:
        self.enabled = bool(enabled)
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.endpoints = dict(endpoints or {})
        self.reserve_symbols = dict(reserve_symbols or {})
        self.api_key_env = api_key_env

    def supports(self, result: ScoutResult) -> bool:
        if not self.enabled:
            return False
        project = (result.candidate.project or "").lower()
        if "aave" not in project and "spark" not in project:
            return False

        chain = (result.candidate.chain or "").strip()
        symbol = (result.candidate.symbol or "").strip()
        address = (result.candidate.address or "").strip()
        if not chain or not symbol or not _is_valid_address(address):
            return False

        endpoint = self._lookup_case_insensitive(self.endpoints, chain)
        if not endpoint:
            return False

        reserve_underlying = self._reserve_underlying_for_candidate(chain, symbol)
        return bool(reserve_underlying)

    async def fetch_snapshot(self, result: ScoutResult) -> FreshnessSnapshot | None:
        chain = (result.candidate.chain or "").strip()
        endpoint = self._lookup_case_insensitive(self.endpoints, chain)
        if not endpoint:
            logger.warning("Aave direct re-check skipped: unsupported chain=%s", chain or "unknown")
            return None

        reserve_underlying = self._reserve_underlying_for_candidate(chain, result.candidate.symbol or "")
        if not reserve_underlying:
            logger.warning("Aave direct re-check skipped: unsupported reserve symbol for chain=%s", chain)
            return None
        if not _is_valid_address(reserve_underlying):
            logger.warning("Aave direct re-check skipped: invalid reserve mapping for chain=%s", chain)
            return None

        candidate_address = (result.candidate.address or "").strip().lower()
        if candidate_address and candidate_address != reserve_underlying.lower():
            logger.warning("Aave direct re-check skipped: candidate/reserve mismatch for chain=%s", chain)
            return None

        payload = {
            "chain": chain,
            "reserve_address": reserve_underlying.lower(),
        }
        headers: dict[str, str] = {}
        api_key = os.getenv(self.api_key_env, "").strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            async with httpx.AsyncClient(timeout=float(self.timeout_seconds)) as client:
                resp = await client.get(endpoint, params=payload, headers=headers)
            if not resp.is_success:
                logger.warning("Aave direct re-check request failed: status=%s", resp.status_code)
                return None
            body = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Aave direct re-check request error: %s", exc.__class__.__name__)
            return None

        try:
            reserve = _extract_reserve(
                body=body,
                reserve_underlying=reserve_underlying,
            )
            if reserve is None:
                logger.warning("Aave direct re-check schema mismatch: reserve not found")
                return None

            source_ts = _parse_timestamp(
                reserve.get("lastUpdateTimestamp")
                or reserve.get("timestamp")
                or reserve.get("updatedAt")
                or reserve.get("updated_at")
            )
            apy = _normalize_apy(
                reserve.get("supplyAPY")
                or reserve.get("supplyApy")
                or reserve.get("liquidityRate")
                or reserve.get("apy")
            )
            tvl_usd = _to_float(
                reserve.get("totalLiquidityUSD")
                or reserve.get("totalSupplyUSD")
                or reserve.get("tvlUsd")
                or reserve.get("tvl_usd")
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Aave direct re-check parse error: %s", exc.__class__.__name__)
            return None

        return FreshnessSnapshot(
            provider=self.name,
            source_timestamp=source_ts,
            apy=apy,
            tvl_usd=tvl_usd,
        )

    def _reserve_underlying_for_candidate(self, chain: str, symbol: str) -> str | None:
        mapping = self._lookup_case_insensitive(self.reserve_symbols, chain) or {}
        base_symbol = _base_symbol(symbol)
        if not base_symbol:
            return None
        mapped = self._lookup_case_insensitive(mapping, base_symbol)
        return mapped

    @staticmethod
    def _lookup_case_insensitive(mapping: dict[str, str], key: str) -> str | None:
        if key in mapping:
            return mapping[key]
        key_lower = key.lower()
        for candidate_key, value in mapping.items():
            if candidate_key.lower() == key_lower:
                return value
        return None


def _extract_reserve(body: object, reserve_underlying: str) -> dict | None:
    if not isinstance(body, dict):
        return None
    reserves = body.get("reserves")
    if not isinstance(reserves, list):
        return None
    wanted_address = reserve_underlying.lower()
    for item in reserves:
        if not isinstance(item, dict):
            continue
        item_address = str(
            item.get("reserveAddress") or item.get("underlyingAsset") or item.get("address") or ""
        ).lower()
        if not item_address:
            continue
        if item_address != wanted_address:
            continue
        return item
    return None


def _to_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_apy(value: object) -> float | None:
    apy = _to_float(value)
    if apy is None:
        return None
    if -1.0 <= apy <= 1.0:
        return apy * 100.0
    return apy


def _parse_timestamp(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        ts = float(value)
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.isdigit():
            ts = float(raw)
        else:
            try:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except ValueError:
                return None
    else:
        return None

    if ts > 1_000_000_000_000:
        ts = ts / 1000.0
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _is_valid_address(address: str) -> bool:
    if len(address) != 42 or not address.startswith("0x"):
        return False
    return all(ch in "0123456789abcdefABCDEF" for ch in address[2:])


def _base_symbol(symbol: str) -> str | None:
    value = symbol.strip().upper()
    if not value:
        return None
    for sep in ("-", "/", " "):
        if sep in value:
            value = value.split(sep, 1)[0].strip()
            break
    return value or None
