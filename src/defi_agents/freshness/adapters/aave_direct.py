from __future__ import annotations

from datetime import datetime, timezone
import logging
import os

import httpx

from ...scout.models import ScoutResult
from ..types import FreshnessSnapshot

logger = logging.getLogger(__name__)

_AAVE_MARKETS_QUERY = """
query Markets($chainIds:[ChainId!]!) {
  markets(request:{ chainIds: $chainIds }) {
    chain { chainId name }
    reserves {
      underlyingToken { symbol address }
      isFrozen
      isPaused
      size { usd }
      supplyInfo { apy { value } }
      borrowInfo { apy { value } availableLiquidity { usd } }
    }
  }
}
"""


class AaveDirectAdapter:
    name = "aave_direct"

    def __init__(
        self,
        *,
        enabled: bool = False,
        timeout_seconds: int = 8,
        endpoints: dict[str, str | list[str]] | None = None,
        chain_ids: dict[str, int] | None = None,
        reserve_symbols: dict[str, dict[str, str]] | None = None,
        api_key_env: str = "AAVE_DIRECT_API_KEY",
    ) -> None:
        self.enabled = bool(enabled)
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.endpoints = self._normalize_endpoints(endpoints or {})
        self.chain_ids = dict(chain_ids or {})
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

        endpoints = self._lookup_case_insensitive(self.endpoints, chain) or []
        if not endpoints:
            return False

        chain_id = self._chain_id_for_candidate(chain)
        if chain_id is None:
            return False

        reserve_underlying = self._reserve_underlying_for_candidate(chain, symbol)
        return bool(reserve_underlying)

    async def fetch_snapshot(self, result: ScoutResult) -> FreshnessSnapshot | None:
        result.metadata["aave_recheck_checked"] = "1"

        chain = (result.candidate.chain or "").strip()
        endpoints = self._lookup_case_insensitive(self.endpoints, chain) or []
        if not endpoints:
            result.metadata["aave_recheck_outcome"] = "error"
            logger.warning("Aave direct re-check skipped: unsupported chain=%s", chain or "unknown")
            return None

        chain_id = self._chain_id_for_candidate(chain)
        if chain_id is None:
            result.metadata["aave_recheck_outcome"] = "error"
            logger.warning("Aave direct re-check skipped: missing chain_id mapping for chain=%s", chain or "unknown")
            return None

        reserve_underlying = self._reserve_underlying_for_candidate(chain, result.candidate.symbol or "")
        if not reserve_underlying:
            result.metadata["aave_recheck_outcome"] = "error"
            logger.warning("Aave direct re-check skipped: unsupported reserve symbol for chain=%s", chain)
            return None
        if not _is_valid_address(reserve_underlying):
            result.metadata["aave_recheck_outcome"] = "error"
            logger.warning("Aave direct re-check skipped: invalid reserve mapping for chain=%s", chain)
            return None

        candidate_address = (result.candidate.address or "").strip().lower()
        if candidate_address and candidate_address != reserve_underlying.lower():
            result.metadata["aave_recheck_outcome"] = "addr_mismatch"
            logger.warning("Aave direct re-check skipped: candidate/reserve mismatch for chain=%s", chain)
            return None

        payload = {"query": _AAVE_MARKETS_QUERY, "variables": {"chainIds": [chain_id]}}
        headers: dict[str, str] = {"Content-Type": "application/json"}
        api_key = os.getenv(self.api_key_env, "").strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        reserve = None
        saw_timeout = False
        saw_schema_mismatch = False
        saw_addr_mismatch = False
        for endpoint in endpoints:
            try:
                async with httpx.AsyncClient(timeout=float(self.timeout_seconds)) as client:
                    resp = await client.post(endpoint, json=payload, headers=headers)
                if not resp.is_success:
                    logger.warning("Aave direct re-check request failed: status=%s", resp.status_code)
                    continue

                body = resp.json()
                errors = body.get("errors") if isinstance(body, dict) else None
                if isinstance(errors, list) and errors:
                    logger.warning("Aave direct re-check graphql error count=%s", len(errors))
                    continue

                reserve, missing_reason = _extract_reserve(body=body, reserve_underlying=reserve_underlying)
                if reserve is None:
                    if missing_reason == "schema_mismatch":
                        saw_schema_mismatch = True
                    elif missing_reason == "addr_mismatch":
                        saw_addr_mismatch = True
                    continue
                break
            except httpx.TimeoutException:
                saw_timeout = True
                logger.warning("Aave direct re-check request timeout")
                continue
            except Exception as exc:  # noqa: BLE001
                logger.warning("Aave direct re-check request error: %s", exc.__class__.__name__)
                continue

        if reserve is None:
            if saw_timeout:
                result.metadata["aave_recheck_outcome"] = "timeout"
            elif saw_addr_mismatch:
                result.metadata["aave_recheck_outcome"] = "addr_mismatch"
            elif saw_schema_mismatch:
                result.metadata["aave_recheck_outcome"] = "schema_mismatch"
            else:
                result.metadata["aave_recheck_outcome"] = "error"
            return None

        try:
            apy = _normalize_apy(
                _path_get(reserve, "supplyInfo", "apy", "value")
                or reserve.get("supplyAPY")
                or reserve.get("supplyApy")
            )
            tvl_usd = _to_float(
                _path_get(reserve, "size", "usd")
                or reserve.get("totalLiquidityUSD")
                or reserve.get("totalSupplyUSD")
                or reserve.get("tvlUsd")
                or reserve.get("tvl_usd")
            )
            is_paused = bool(reserve.get("isPaused"))
            is_frozen = bool(reserve.get("isFrozen"))
        except Exception as exc:  # noqa: BLE001
            result.metadata["aave_recheck_outcome"] = "schema_mismatch"
            logger.warning("Aave direct re-check parse error: %s", exc.__class__.__name__)
            return None

        if is_paused or is_frozen:
            result.metadata["aave_recheck_outcome"] = "error"
            logger.warning("Aave direct re-check skipped: paused_or_frozen chain=%s", chain)
            return None
        if apy is None and tvl_usd is None:
            result.metadata["aave_recheck_outcome"] = "schema_mismatch"
            logger.warning("Aave direct re-check schema mismatch: missing apy/tvl fields")
            return None

        result.metadata["aave_recheck_outcome"] = "ok"
        return FreshnessSnapshot(
            provider=self.name,
            source_timestamp=datetime.now(timezone.utc),
            apy=apy,
            tvl_usd=tvl_usd,
        )

    def _chain_id_for_candidate(self, chain: str) -> int | None:
        raw_value = self._lookup_case_insensitive(self.chain_ids, chain)
        if raw_value is None:
            return None
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            return None

    def _reserve_underlying_for_candidate(self, chain: str, symbol: str) -> str | None:
        mapping = self._lookup_case_insensitive(self.reserve_symbols, chain) or {}
        base_symbol = _base_symbol(symbol)
        if not base_symbol:
            return None
        mapped = self._lookup_case_insensitive(mapping, base_symbol)
        return mapped

    @staticmethod
    def _lookup_case_insensitive(mapping: dict[str, object], key: str) -> object | None:
        if key in mapping:
            return mapping[key]
        key_lower = key.lower()
        for candidate_key, value in mapping.items():
            if candidate_key.lower() == key_lower:
                return value
        return None

    @staticmethod
    def _normalize_endpoints(raw: dict[str, str | list[str]]) -> dict[str, list[str]]:
        normalized: dict[str, list[str]] = {}
        for chain, value in raw.items():
            if isinstance(value, str):
                items = [value]
            elif isinstance(value, list):
                items = [item for item in value if isinstance(item, str)]
            else:
                items = []
            endpoints = [item.strip() for item in items if item and item.strip()]
            if endpoints:
                normalized[chain] = endpoints
        return normalized


def _extract_reserve(body: object, reserve_underlying: str) -> tuple[dict | None, str]:
    if not isinstance(body, dict):
        return None, "schema_mismatch"
    data = body.get("data")
    if not isinstance(data, dict):
        return None, "schema_mismatch"
    markets = data.get("markets")
    if not isinstance(markets, list):
        return None, "schema_mismatch"

    wanted_address = reserve_underlying.lower()
    for market in markets:
        if not isinstance(market, dict):
            continue
        reserves = market.get("reserves")
        if not isinstance(reserves, list):
            continue
        for reserve in reserves:
            if not isinstance(reserve, dict):
                continue
            token = reserve.get("underlyingToken")
            address = ""
            if isinstance(token, dict):
                address = str(token.get("address") or "")
            address = address.lower()
            if not address:
                continue
            if address != wanted_address:
                continue
            return reserve, ""
    return None, "addr_mismatch"


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


def _path_get(obj: object, *path: str) -> object:
    current = obj
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


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
