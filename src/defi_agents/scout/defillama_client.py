from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import List

import httpx

from .config import ScoutConfig
from .models import ScoutCandidate


class DeFiLlamaClient:
    BASE_URL = "https://yields.llama.fi/pools"

    def __init__(self, config: ScoutConfig, timeout_seconds: float = 15.0) -> None:
        self.config = config
        self._timeout = timeout_seconds

    async def get_pools(self) -> List[ScoutCandidate]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(self.BASE_URL)
            resp.raise_for_status()
            data = resp.json()

        pools = data.get("data", []) if isinstance(data, dict) else []
        results: List[ScoutCandidate] = []
        for item in pools:
            try:
                candidate = ScoutCandidate.model_validate(item)
            except Exception:
                continue

            candidate.chain_id = self._resolve_chain_id(item, candidate.chain)
            address, source = self._resolve_address(item, candidate)
            candidate.address = address
            candidate.address_source = source
            candidate.contract_age_days = self._resolve_contract_age_days(item)

            if candidate.tvl_usd < self.config.min_tvl_usd:
                continue

            if candidate.apy is not None and candidate.apy < self.config.min_apy:
                continue

            if self.config.target_chains and candidate.chain not in self.config.target_chains:
                continue

            results.append(candidate)

        return results

    def _resolve_chain_id(self, item: dict, chain: str) -> int | None:
        raw_chain_id = item.get("chainId")
        if isinstance(raw_chain_id, int):
            return raw_chain_id
        if isinstance(raw_chain_id, str) and raw_chain_id.isdigit():
            return int(raw_chain_id)
        if chain in self.config.chain_id_map:
            return self.config.chain_id_map[chain]
        for name, chain_id in self.config.chain_id_map.items():
            if name.lower() == chain.lower():
                return chain_id
        return None

    def _resolve_address(self, item: dict, candidate: ScoutCandidate) -> tuple[str | None, str | None]:
        direct = self._normalize_address(item.get("address"))
        if direct:
            return direct, "POOL"
        for token in candidate.underlying_tokens:
            normalized = self._normalize_address(token)
            if normalized:
                return normalized, "TOKEN"
        return None, None

    def _resolve_contract_age_days(self, item: dict) -> int | None:
        raw_ts = item.get("timestamp")
        if not isinstance(raw_ts, (int, float)):
            return None
        if raw_ts <= 0:
            return None
        now_ts = datetime.now(timezone.utc).timestamp()
        age_days = int(max(0.0, now_ts - float(raw_ts)) // 86400)
        return age_days

    @staticmethod
    def _normalize_address(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        addr = value.strip()
        if ":" in addr:
            addr = addr.split(":")[-1].strip()
        if re.fullmatch(r"0x[a-fA-F0-9]{40}", addr):
            return addr.lower()
        return None
