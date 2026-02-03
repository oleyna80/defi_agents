from __future__ import annotations

from dataclasses import dataclass
from time import time
from typing import Dict, Optional, Set

from .defi_client import DeFiClient
from .goplus_client import GoPlusClient
from .models import SecurityResult, SecurityStatus
from .whitelist import WhitelistProvider


@dataclass
class _CacheEntry:
    result: SecurityResult
    expires_at: float


class SecurityAuditor:
    def __init__(
        self,
        whitelist_provider: WhitelistProvider,
        goplus_client: GoPlusClient,
        defi_client: DeFiClient,
        *,
        tier1_addresses: Optional[Dict[str, Set[str]]] = None,
        cache_ttl_seconds: int = 3600,
    ) -> None:
        self.whitelist = whitelist_provider
        self.goplus = goplus_client
        self.defi = defi_client
        self._tier1 = {
            chain: {addr.lower() for addr in addrs}
            for chain, addrs in (tier1_addresses or {}).items()
        }
        self._cache: Dict[str, _CacheEntry] = {}
        self._cache_ttl = cache_ttl_seconds

    def _cache_key(self, address: str, chain_id: str) -> str:
        return f"{chain_id}:{address.lower()}"

    def _get_cached(self, address: str, chain_id: str) -> Optional[SecurityResult]:
        key = self._cache_key(address, chain_id)
        entry = self._cache.get(key)
        if not entry:
            return None
        if time() > entry.expires_at:
            self._cache.pop(key, None)
            return None
        return entry.result

    def _set_cached(self, address: str, chain_id: str, result: SecurityResult) -> None:
        key = self._cache_key(address, chain_id)
        ttl = result.ttl_seconds or self._cache_ttl
        self._cache[key] = _CacheEntry(result=result, expires_at=time() + ttl)

    def _is_tier1(self, address: str, chain_id: str) -> bool:
        addr = address.lower()
        if chain_id in self._tier1 and addr in self._tier1[chain_id]:
            return True
        return False

    async def evaluate(self, address: str, chain_id: str) -> SecurityResult:
        # Cache
        cached = self._get_cached(address, chain_id)
        if cached:
            return cached

        # Step 0.1: Check Local Whitelist (SSOT)
        trusted_result = self.whitelist.check(address, chain_id)
        if trusted_result:
            self._set_cached(address, chain_id, trusted_result)
            return trusted_result

        # Step 0.2: Check Tier-1 Constants (Hardcoded safe stables)
        if self._is_tier1(address, chain_id):
            result = SecurityResult.pass_as_tier1(
                reason="Tier 1 stable (hardcoded by chain)",
                data={"chain_id": chain_id, "address": address.lower()},
            )
            self._set_cached(address, chain_id, result)
            return result

        # Stage A: Dynamic Scan (GoPlus)
        tech_res = await self.goplus.scan(address, chain_id)
        if tech_res.status == SecurityStatus.BLOCK:
            self._set_cached(address, chain_id, tech_res)
            return tech_res

        # Stage B: De.Fi (Reputation)
        try:
            reputation = await self.defi.get_reputation(address)
        except Exception:  # noqa: BLE001
            # Fail open into reputation penalty path instead of crashing the whole cycle.
            from .models import SecurityReputation

            reputation = SecurityReputation.unidentified_penalty(None)
        tech_res.aggregate_reputation(reputation)

        # Fail-safe: if protocol unresolved and not Tier1, block
        if not self._is_tier1(address, chain_id) and reputation.protocol_slug is None and reputation.protocol_name is None:
            tech_res.status = SecurityStatus.BLOCK

        self._set_cached(address, chain_id, tech_res)
        return tech_res
