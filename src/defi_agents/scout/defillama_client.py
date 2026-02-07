from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import List

import httpx

from .config import ScoutConfig
from .models import LendingSnapshot, LendingSnapshotItem, ScoutCandidate


class DeFiLlamaClient:
    BASE_URL = "https://yields.llama.fi/pools"

    def __init__(self, config: ScoutConfig, timeout_seconds: float = 15.0) -> None:
        self.config = config
        self._timeout = timeout_seconds

    async def get_pools(self) -> List[ScoutCandidate]:
        pools = await self._fetch_raw_pools()
        return self._build_candidates(pools, apply_min_apy=True)

    async def get_lending_snapshot(self) -> LendingSnapshot:
        pools = await self._fetch_raw_pools()
        candidates = self._build_candidates(pools, apply_min_apy=False)

        lending_candidates = [candidate for candidate in candidates if self._is_lending_candidate(candidate)]
        lending_candidates = [
            candidate
            for candidate in lending_candidates
            if self._is_single_asset_market(candidate.symbol)
        ]
        if not lending_candidates:
            return LendingSnapshot()

        eth_assets = {"ETH", "WETH", "STETH", "WSTETH", "RETH", "CBETH", "WEETH", "EZETH"}
        btc_assets = {"BTC", "WBTC", "TBTC", "RENBTC", "SBTC", "LBTC", "CBBTC", "WBTC.B"}
        stable_assets = self._stable_symbol_set()

        best_eth_supply = self._pick_best_supply(lending_candidates, eth_assets)
        best_btc_supply = self._pick_best_supply(lending_candidates, btc_assets)
        best_gho_supply = self._pick_best_supply(lending_candidates, {"GHO"})
        lowest_stable_borrow = self._pick_lowest_borrow(lending_candidates, stable_assets)
        lowest_eurc_borrow = self._pick_lowest_borrow(lending_candidates, {"EURC"})
        lowest_usdc_borrow = self._pick_lowest_borrow(lending_candidates, {"USDC"})

        return LendingSnapshot(
            best_eth_supply=best_eth_supply,
            best_btc_supply=best_btc_supply,
            best_gho_supply=best_gho_supply,
            lowest_stable_borrow=lowest_stable_borrow,
            lowest_eurc_borrow=lowest_eurc_borrow,
            lowest_usdc_borrow=lowest_usdc_borrow,
        )

    async def _fetch_raw_pools(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(self.BASE_URL)
            resp.raise_for_status()
            data = resp.json()
        pools = data.get("data", []) if isinstance(data, dict) else []
        return pools if isinstance(pools, list) else []

    def _build_candidates(self, pools: list[dict], apply_min_apy: bool) -> List[ScoutCandidate]:
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

            if apply_min_apy and candidate.apy is not None and candidate.apy < self.config.min_apy:
                continue

            if self.config.target_chains and candidate.chain not in self.config.target_chains:
                continue

            results.append(candidate)

        return results

    def _is_lending_candidate(self, candidate: ScoutCandidate) -> bool:
        if (
            candidate.apy_base_borrow is not None
            or candidate.apy_reward_borrow is not None
            or candidate.total_borrow_usd is not None
        ):
            return True

        project_tokens = self._project_tokens(candidate.project)
        return (
            "aave" in project_tokens
            or "compound" in project_tokens
            or "morpho" in project_tokens
            or "spark" in project_tokens
            or "euler" in project_tokens
            or "venus" in project_tokens
            or "moonwell" in project_tokens
        )

    @staticmethod
    def _project_tokens(project: str) -> set[str]:
        return {part for part in re.split(r"[^A-Za-z0-9]+", (project or "").lower()) if part}

    def _is_single_asset_market(self, symbol: str) -> bool:
        return len(self._extract_symbol_tokens(symbol)) == 1

    def _pick_best_supply(
        self,
        candidates: List[ScoutCandidate],
        tracked_symbols: set[str],
    ) -> LendingSnapshotItem | None:
        eligible: list[ScoutCandidate] = []
        for candidate in candidates:
            tokens = self._extract_symbol_tokens(candidate.symbol)
            if any(token in tracked_symbols for token in tokens):
                eligible.append(candidate)

        if not eligible:
            return None

        best = max(eligible, key=lambda candidate: candidate.apy)
        return LendingSnapshotItem(
            candidate=best,
            metric_name="supply_apy",
            metric_value_pct=float(best.apy),
        )

    def _pick_lowest_borrow(
        self,
        candidates: List[ScoutCandidate],
        stable_symbols: set[str],
    ) -> LendingSnapshotItem | None:
        scored: list[tuple[ScoutCandidate, float]] = []
        for candidate in candidates:
            tokens = self._extract_symbol_tokens(candidate.symbol)
            if not any(token in stable_symbols for token in tokens):
                continue
            borrow_apr = self._borrow_apr(candidate)
            if borrow_apr is None or borrow_apr < 0:
                continue
            scored.append((candidate, borrow_apr))

        if not scored:
            return None

        best, value = min(scored, key=lambda item: item[1])
        return LendingSnapshotItem(
            candidate=best,
            metric_name="borrow_apr",
            metric_value_pct=float(value),
        )

    def _borrow_apr(self, candidate: ScoutCandidate) -> float | None:
        base = candidate.apy_base_borrow
        reward = candidate.apy_reward_borrow
        if base is None and reward is None:
            return None
        return float(base or 0.0) + float(reward or 0.0)

    def _stable_symbol_set(self) -> set[str]:
        stable = {symbol.upper() for symbol in self.config.stable_symbols}
        stable.update(symbol.upper() for symbol in self.config.token_buckets.stablecoins_usd)
        stable.update(symbol.upper() for symbol in self.config.token_buckets.stablecoins_eur)
        stable.update(symbol.upper() for symbol in self.config.token_buckets.stablecoins_speculative)
        return stable

    @staticmethod
    def _extract_symbol_tokens(symbol: str) -> set[str]:
        parts = re.split(r"[^A-Za-z0-9.]+", symbol.upper())
        return {part for part in parts if part}

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
