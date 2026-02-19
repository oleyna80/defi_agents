from __future__ import annotations

from datetime import datetime, timezone
import logging
import os

import httpx

from ...scout.models import ScoutResult
from ..types import FreshnessSnapshot

logger = logging.getLogger(__name__)

_MORPHO_MARKET_QUERY = """
query MarketByUniqueKey($uniqueKey: String!, $chainId: Int!) {
  marketByUniqueKey(uniqueKey: $uniqueKey, chainId: $chainId) {
    loanAsset { address symbol }
    state {
      supplyApy
      supplyAssetsUsd
      timestamp
    }
  }
}
"""


class MorphoDirectAdapter:
    name = "morpho_direct"

    def __init__(
        self,
        *,
        enabled: bool = False,
        timeout_seconds: int = 8,
        endpoints: dict[str, str | list[str]] | None = None,
        chain_ids: dict[str, int] | None = None,
        market_keys: dict[str, dict[str, str]] | None = None,
        api_key_env: str = "MORPHO_DIRECT_API_KEY",
    ) -> None:
        self.enabled = bool(enabled)
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.endpoints = self._normalize_endpoints(endpoints or {})
        self.chain_ids = dict(chain_ids or {})
        self.market_keys = dict(market_keys or {})
        self.api_key_env = api_key_env

    def supports(self, result: ScoutResult) -> bool:
        if not self.enabled:
            return False
        project = (result.candidate.project or "").lower()
        if "morpho" not in project:
            return False

        chain = (result.candidate.chain or "").strip()
        symbol = (result.candidate.symbol or "").strip()
        address = (result.candidate.address or "").strip()
        if not chain or not symbol:
            return False
        if address and not _is_valid_address(address):
            return False

        endpoints = self._lookup_case_insensitive(self.endpoints, chain) or []
        if not endpoints:
            return False

        chain_id = self._chain_id_for_candidate(chain)
        if chain_id is None:
            return False

        market_key = self._market_key_for_candidate(chain, symbol)
        return bool(market_key)

    async def fetch_snapshot(self, result: ScoutResult) -> FreshnessSnapshot | None:
        result.metadata["morpho_recheck_checked"] = "1"

        chain = (result.candidate.chain or "").strip()
        endpoints = self._lookup_case_insensitive(self.endpoints, chain) or []
        if not endpoints:
            result.metadata["morpho_recheck_outcome"] = "error"
            logger.warning("Morpho direct re-check skipped: unsupported chain=%s", chain or "unknown")
            return None

        chain_id = self._chain_id_for_candidate(chain)
        if chain_id is None:
            result.metadata["morpho_recheck_outcome"] = "error"
            logger.warning("Morpho direct re-check skipped: missing chain_id mapping for chain=%s", chain or "unknown")
            return None

        market_key = self._market_key_for_candidate(chain, result.candidate.symbol or "")
        if not market_key:
            result.metadata["morpho_recheck_outcome"] = "error"
            logger.warning("Morpho direct re-check skipped: unsupported market symbol for chain=%s", chain)
            return None

        payload = {"query": _MORPHO_MARKET_QUERY, "variables": {"uniqueKey": market_key, "chainId": chain_id}}
        headers: dict[str, str] = {"Content-Type": "application/json"}
        api_key = os.getenv(self.api_key_env, "").strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        market = None
        saw_timeout = False
        saw_schema_mismatch = False
        saw_addr_mismatch = False
        for endpoint in endpoints:
            try:
                async with httpx.AsyncClient(timeout=float(self.timeout_seconds)) as client:
                    resp = await client.post(endpoint, json=payload, headers=headers)
                if not resp.is_success:
                    logger.warning("Morpho direct re-check request failed: status=%s", resp.status_code)
                    continue

                body = resp.json()
                errors = body.get("errors") if isinstance(body, dict) else None
                if isinstance(errors, list) and errors:
                    logger.warning("Morpho direct re-check graphql error count=%s", len(errors))
                    continue

                market, missing_reason = _extract_market(body)
                if market is None:
                    if missing_reason == "schema_mismatch":
                        saw_schema_mismatch = True
                    continue

                if _has_addr_mismatch(result, market):
                    saw_addr_mismatch = True
                    market = None
                    continue
                break
            except httpx.TimeoutException:
                saw_timeout = True
                logger.warning("Morpho direct re-check request timeout")
                continue
            except Exception as exc:  # noqa: BLE001
                logger.warning("Morpho direct re-check request error: %s", exc.__class__.__name__)
                continue

        if market is None:
            if saw_timeout:
                result.metadata["morpho_recheck_outcome"] = "timeout"
            elif saw_addr_mismatch:
                result.metadata["morpho_recheck_outcome"] = "addr_mismatch"
            elif saw_schema_mismatch:
                result.metadata["morpho_recheck_outcome"] = "schema_mismatch"
            else:
                result.metadata["morpho_recheck_outcome"] = "error"
            return None

        state = market.get("state") if isinstance(market, dict) else None
        if not isinstance(state, dict):
            result.metadata["morpho_recheck_outcome"] = "schema_mismatch"
            logger.warning("Morpho direct re-check schema mismatch: missing state")
            return None

        apy = _normalize_apy(state.get("supplyApy"))
        tvl_usd = _to_float(state.get("supplyAssetsUsd"))
        source_ts = _parse_timestamp(state.get("timestamp"))
        if apy is None and tvl_usd is None:
            result.metadata["morpho_recheck_outcome"] = "schema_mismatch"
            logger.warning("Morpho direct re-check schema mismatch: missing apy/tvl fields")
            return None

        result.metadata["morpho_recheck_outcome"] = "ok"
        return FreshnessSnapshot(
            provider=self.name,
            source_timestamp=source_ts or datetime.now(timezone.utc),
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

    def _market_key_for_candidate(self, chain: str, symbol: str) -> str | None:
        mapping = self._lookup_case_insensitive(self.market_keys, chain) or {}
        base_symbol = _base_symbol(symbol)
        if not base_symbol:
            return None
        mapped = self._lookup_case_insensitive(mapping, base_symbol)
        if not isinstance(mapped, str):
            return None
        value = mapped.strip()
        return value or None

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


def _extract_market(body: object) -> tuple[dict | None, str]:
    if not isinstance(body, dict):
        return None, "schema_mismatch"
    data = body.get("data")
    if not isinstance(data, dict):
        return None, "schema_mismatch"
    market = data.get("marketByUniqueKey")
    if market is None:
        return None, "schema_mismatch"
    if not isinstance(market, dict):
        return None, "schema_mismatch"
    return market, ""


def _has_addr_mismatch(result: ScoutResult, market: dict) -> bool:
    candidate_address = (result.candidate.address or "").strip().lower()
    if not candidate_address or not _is_valid_address(candidate_address):
        return False
    loan_asset = market.get("loanAsset")
    if not isinstance(loan_asset, dict):
        return False
    market_address = str(loan_asset.get("address") or "").strip().lower()
    if not market_address or not _is_valid_address(market_address):
        return False
    if candidate_address != market_address:
        logger.warning("Morpho direct re-check skipped: candidate/loanAsset mismatch for chain=%s", result.candidate.chain)
        return True
    return False


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
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1e12:
            ts = ts / 1000.0
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.isdigit():
            return _parse_timestamp(int(raw))
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            return None
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
