from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import List

import httpx

from .config import ScoutConfig
from .models import LendingSnapshot, LendingSnapshotItem, ScoutCandidate, YieldDirectionSnapshot


class DeFiLlamaClient:
    BASE_URL = "https://yields.llama.fi/pools"

    def __init__(self, config: ScoutConfig, timeout_seconds: float = 15.0) -> None:
        self.config = config
        self._timeout = timeout_seconds
        self._raw_pools_cache: list[dict] | None = None

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
        tracked_stables = self._lending_report_stable_symbols()

        best_eth_supply = self._pick_best_supply(lending_candidates, eth_assets)
        best_btc_supply = self._pick_best_supply(lending_candidates, btc_assets)
        best_gho_supply = self._pick_best_supply(lending_candidates, {"GHO"})
        lowest_borrow_by_symbol = self._pick_lowest_borrow_by_symbol(lending_candidates, tracked_stables)
        lowest_stable_borrow = self._pick_lowest_borrow(lending_candidates, tracked_stables)
        lowest_eurc_borrow = lowest_borrow_by_symbol.get("EURC")
        lowest_usdc_borrow = lowest_borrow_by_symbol.get("USDC")

        return LendingSnapshot(
            best_eth_supply=best_eth_supply,
            best_btc_supply=best_btc_supply,
            best_gho_supply=best_gho_supply,
            lowest_stable_borrow=lowest_stable_borrow,
            lowest_eurc_borrow=lowest_eurc_borrow,
            lowest_usdc_borrow=lowest_usdc_borrow,
            lowest_borrow_by_symbol=lowest_borrow_by_symbol,
        )

    async def get_turnover_snapshot(self) -> List[ScoutCandidate]:
        """Return high-turnover DEX/LP candidates for market digest display.

        This is a read-only report helper and does not run security/L3.
        It is intentionally bounded by config thresholds.
        """
        pools = await self._fetch_raw_pools()
        # Build candidates without min_apy gating; turnover section is about activity.
        candidates = self._build_candidates(pools, apply_min_apy=False)

        reporting = getattr(self.config, "reporting", None)
        min_tvl = float(getattr(reporting, "telegram_turnover_min_tvl_usd", 0.0) or 0.0)
        min_vol = float(getattr(reporting, "telegram_turnover_min_volume_24h_usd", 0.0) or 0.0)
        min_ratio = float(getattr(reporting, "telegram_turnover_min_vol_to_tvl", 0.0) or 0.0)

        out: list[ScoutCandidate] = []
        for candidate in candidates:
            if float(candidate.tvl_usd or 0.0) < min_tvl:
                continue
            vol = candidate.volume_24h_usd
            if not isinstance(vol, (int, float)) or float(vol) <= 0:
                continue
            if min_vol > 0 and float(vol) < min_vol:
                continue
            ratio = float(vol) / float(candidate.tvl_usd or 1.0)
            if min_ratio > 0 and ratio < min_ratio:
                continue
            # Exclude lending single-asset markets; turnover snapshot is for DEX/LP style pools.
            if self._is_lending_candidate(candidate):
                continue
            out.append(candidate)

        out.sort(
            key=lambda c: (
                float(getattr(c, "volume_24h_usd", 0.0) or 0.0) / float(c.tvl_usd or 1.0),
                float(getattr(c, "volume_24h_usd", 0.0) or 0.0),
            ),
            reverse=True,
        )
        top_n = int(getattr(reporting, "telegram_turnover_top_n", 0) or 0)
        return out[:top_n] if top_n > 0 else out

    async def get_directional_snapshot(self) -> YieldDirectionSnapshot:
        pools = await self._fetch_raw_pools()
        reporting = getattr(self.config, "reporting", None)
        top_n = int(getattr(reporting, "telegram_directional_top_n", 0) or 0)
        if top_n <= 0:
            return YieldDirectionSnapshot()

        absolute_floor = float(getattr(self.config.liquidity_gates, "absolute_min_tvl_usd", 0.0) or 0.0)
        candidates = self._build_reporting_candidates(pools, min_tvl_floor=absolute_floor)
        if not candidates:
            return YieldDirectionSnapshot()

        lp_min_tvl = float(getattr(reporting, "telegram_directional_lp_min_tvl_usd", 0.0) or 0.0)
        lp_min_ratio = float(getattr(reporting, "telegram_directional_lp_min_vol_to_tvl", 0.0) or 0.0)
        lending_min_tvl = float(getattr(reporting, "telegram_directional_lending_min_tvl_usd", 0.0) or 0.0)
        staking_min_tvl = float(getattr(reporting, "telegram_directional_staking_min_tvl_usd", 0.0) or 0.0)
        staking_min_apy = float(getattr(reporting, "telegram_directional_staking_min_apy", 0.0) or 0.0)
        borrow_symbols = {
            str(symbol).upper()
            for symbol in (getattr(reporting, "telegram_directional_borrow_symbols", []) or [])
            if str(symbol).strip()
        }
        if not borrow_symbols:
            borrow_symbols = self._lending_report_stable_symbols()

        lp_scored: list[tuple[ScoutCandidate, float]] = []
        lending_supply: list[ScoutCandidate] = []
        lending_borrow_scored: list[tuple[ScoutCandidate, float]] = []
        staking_candidates: list[ScoutCandidate] = []

        for candidate in candidates:
            tvl = float(candidate.tvl_usd or 0.0)
            vol = candidate.volume_24h_usd
            is_lending = self._is_lending_candidate(candidate)

            if not is_lending:
                if isinstance(vol, (int, float)) and float(vol) > 0 and tvl >= lp_min_tvl:
                    ratio = float(vol) / tvl if tvl > 0 else 0.0
                    if ratio >= lp_min_ratio:
                        lp_scored.append((candidate, ratio))
                if self._is_single_asset_market(candidate.symbol) and tvl >= staking_min_tvl and float(candidate.apy or 0.0) >= staking_min_apy:
                    staking_candidates.append(candidate)
                continue

            if not self._is_single_asset_market(candidate.symbol):
                continue

            if tvl >= lending_min_tvl:
                lending_supply.append(candidate)

            token_set = self._extract_symbol_tokens(candidate.symbol)
            if len(token_set) == 1 and next(iter(token_set)) in borrow_symbols:
                borrow_apr = self._borrow_apr(candidate)
                if borrow_apr is not None and borrow_apr >= 0:
                    lending_borrow_scored.append((candidate, float(borrow_apr)))

        lp_scored.sort(
            key=lambda item: (
                item[1],
                float(item[0].volume_24h_usd or 0.0),
                float(item[0].tvl_usd or 0.0),
            ),
            reverse=True,
        )
        lending_supply.sort(
            key=lambda candidate: (float(candidate.apy or 0.0), float(candidate.tvl_usd or 0.0)),
            reverse=True,
        )
        lending_borrow_scored.sort(
            key=lambda item: (item[1], -float(item[0].tvl_usd or 0.0))
        )
        staking_candidates.sort(
            key=lambda candidate: (float(candidate.apy or 0.0), float(candidate.tvl_usd or 0.0)),
            reverse=True,
        )

        return YieldDirectionSnapshot(
            lp_top=[
                LendingSnapshotItem(candidate=candidate, metric_name="vol_to_tvl", metric_value_pct=ratio)
                for candidate, ratio in lp_scored[:top_n]
            ],
            lending_supply_top=[
                LendingSnapshotItem(candidate=candidate, metric_name="supply_apy", metric_value_pct=float(candidate.apy or 0.0))
                for candidate in lending_supply[:top_n]
            ],
            lending_borrow_top=[
                LendingSnapshotItem(candidate=candidate, metric_name="borrow_apr", metric_value_pct=borrow_apr)
                for candidate, borrow_apr in lending_borrow_scored[:top_n]
            ],
            staking_top=[
                LendingSnapshotItem(candidate=candidate, metric_name="staking_apy", metric_value_pct=float(candidate.apy or 0.0))
                for candidate in staking_candidates[:top_n]
            ],
        )

    async def _fetch_raw_pools(self) -> list[dict]:
        if isinstance(self._raw_pools_cache, list):
            return self._raw_pools_cache
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(self.BASE_URL)
            resp.raise_for_status()
            data = resp.json()
        pools = data.get("data", []) if isinstance(data, dict) else []
        out = pools if isinstance(pools, list) else []
        self._raw_pools_cache = out
        return out

    def _build_candidates(self, pools: list[dict], apply_min_apy: bool) -> List[ScoutCandidate]:
        results: List[ScoutCandidate] = []
        for item in pools:
            try:
                candidate = ScoutCandidate.model_validate(item)
            except Exception:
                continue

            # Best-effort normalize volume fields (DefiLlama uses volumeUsd1d/volumeUsd7d, but some pools may omit).
            if candidate.volume_24h_usd is None:
                raw_vol = item.get("volumeUsd24h") or item.get("volumeUSD1d") or item.get("volumeUsd1d")
                try:
                    candidate.volume_24h_usd = float(raw_vol) if raw_vol is not None else None
                except (TypeError, ValueError):
                    candidate.volume_24h_usd = None

            candidate.chain_id = self._resolve_chain_id(item, candidate.chain)
            address, source = self._resolve_address(item, candidate)
            candidate.address = address
            candidate.address_source = source
            candidate.contract_age_days = self._resolve_contract_age_days(item)

            # Liquidity gates: allow intake by either TVL or 24h volume (when configured).
            tvl_ok = float(candidate.tvl_usd) >= float(self.config.min_tvl_usd)
            min_vol = float(getattr(self.config.liquidity_gates, "min_volume_24h_usd", 0.0) or 0.0)
            max_ratio = float(getattr(self.config.liquidity_gates, "max_tvl_to_volume_24h_ratio", 0.0) or 0.0)
            vol = candidate.volume_24h_usd
            vol_ok = min_vol > 0 and isinstance(vol, (int, float)) and float(vol) >= min_vol
            if min_vol > 0:
                if not (tvl_ok or vol_ok):
                    continue
            else:
                if not tvl_ok:
                    continue

            # Optional ratio guard: drop low-activity pools when both TVL and volume are available.
            if max_ratio > 0 and isinstance(vol, (int, float)) and float(vol) > 0:
                ratio = float(candidate.tvl_usd) / float(vol)
                if ratio > max_ratio:
                    continue

            if apply_min_apy and candidate.apy is not None and candidate.apy < self.config.min_apy:
                continue

            if self.config.target_chains and candidate.chain not in self.config.target_chains:
                continue

            results.append(candidate)

        return results

    def _build_reporting_candidates(self, pools: list[dict], min_tvl_floor: float) -> List[ScoutCandidate]:
        results: List[ScoutCandidate] = []
        for item in pools:
            try:
                candidate = ScoutCandidate.model_validate(item)
            except Exception:
                continue

            if candidate.volume_24h_usd is None:
                raw_vol = item.get("volumeUsd24h") or item.get("volumeUSD1d") or item.get("volumeUsd1d")
                try:
                    candidate.volume_24h_usd = float(raw_vol) if raw_vol is not None else None
                except (TypeError, ValueError):
                    candidate.volume_24h_usd = None

            candidate.chain_id = self._resolve_chain_id(item, candidate.chain)
            address, source = self._resolve_address(item, candidate)
            candidate.address = address
            candidate.address_source = source
            candidate.contract_age_days = self._resolve_contract_age_days(item)

            if float(candidate.tvl_usd or 0.0) < float(min_tvl_floor):
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

    def _lending_report_stable_symbols(self) -> set[str]:
        stable = self._stable_symbol_set()
        stable.update({"USDC", "USDT", "DAI", "USDS", "EURC", "GHO"})
        return stable

    def _pick_lowest_borrow_by_symbol(
        self,
        candidates: List[ScoutCandidate],
        stable_symbols: set[str],
    ) -> dict[str, LendingSnapshotItem]:
        best_by_symbol: dict[str, tuple[ScoutCandidate, float]] = {}
        for candidate in candidates:
            tokens = self._extract_symbol_tokens(candidate.symbol)
            if len(tokens) != 1:
                continue
            token = next(iter(tokens))
            if token not in stable_symbols:
                continue
            borrow_apr = self._borrow_apr(candidate)
            if borrow_apr is None or borrow_apr < 0:
                continue
            current = best_by_symbol.get(token)
            if current is None or borrow_apr < current[1]:
                best_by_symbol[token] = (candidate, borrow_apr)

        return {
            symbol: LendingSnapshotItem(
                candidate=item[0],
                metric_name="borrow_apr",
                metric_value_pct=float(item[1]),
            )
            for symbol, item in best_by_symbol.items()
        }

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
