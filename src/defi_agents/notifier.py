from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import List

import httpx

from .scout.models import LendingSnapshot, PriorityTier, ScoutCandidate, ScoutResult


class TelegramNotifier:
    _ALLOWED_STABLES = {
        "USDC", "USDT", "DAI", "USDS", "FRAX", "LUSD", "USDE", "GHO", "PYUSD", "CRVUSD",
        "EURS", "EURC", "AGEUR", "EURE", "FDUSD", "TUSD", "USDP", "USDD", "USD0", "USD1",
        "RLUSD", "USDG", "USDY", "SUSDS", "SDAI", "USDBC",
    }
    _ALLOWED_BTC = {
        "BTC", "WBTC", "WBTC.B", "CBBTC", "TBTC", "RENBTC", "SBTC", "BTCB", "LBTC",
    }
    _ALLOWED_ETH = {
        "ETH", "WETH", "STETH", "WSTETH", "RETH", "CBETH", "EETH", "WEETH", "METH", "SETH",
    }
    _ALLOWED_GOLD = {"XAUT", "PAXG", "PAXGOLD"}

    def __init__(self, include_tags: bool = False, top_n_per_section: int = 0) -> None:
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID")
        self.include_tags = include_tags
        self.top_n_per_section = int(top_n_per_section) if isinstance(top_n_per_section, int) else 0

    async def send_alpha_report(
        self,
        results: List[ScoutResult],
        lending_snapshot: LendingSnapshot | None = None,
        turnover_snapshot: List[ScoutCandidate] | None = None,
    ) -> None:
        message = self._format_report(
            results,
            lending_snapshot=lending_snapshot,
            turnover_snapshot=turnover_snapshot,
        )
        for chunk in self._chunk_message(message):
            await self._send(chunk)

    async def send_error(self, text: str) -> None:
        await self._send(f"⚠️ {text}")

    async def send_markdown_report(self, text: str) -> None:
        for chunk in self._chunk_message(text):
            await self._send(chunk)

    async def _send(self, text: str, retries: int = 3) -> bool:
        if not self.token or not self.chat_id:
            # No credentials configured; fallback to console output.
            print(text)
            return False
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text, "parse_mode": "Markdown"}
        async with httpx.AsyncClient(timeout=10.0) as client:
            for attempt in range(1, retries + 1):
                try:
                    response = await client.post(url, json=payload)
                    if response.is_success:
                        return True
                    wait_seconds = attempt * 2
                    logging.warning(
                        "Telegram send failed (%s/%s): status=%s. Retry in %ss.",
                        attempt,
                        retries,
                        response.status_code,
                        wait_seconds,
                    )
                    if attempt < retries:
                        await asyncio.sleep(wait_seconds)
                except httpx.RequestError as exc:
                    wait_seconds = attempt * 2
                    logging.warning(
                        "Telegram send request error (%s/%s): %s. Retry in %ss.",
                        attempt,
                        retries,
                        exc.__class__.__name__,
                        wait_seconds,
                    )
                    if attempt < retries:
                        await asyncio.sleep(wait_seconds)
        logging.error("Telegram notification failed after retries.")
        return False

    def _format_report(
        self,
        results: List[ScoutResult],
        lending_snapshot: LendingSnapshot | None = None,
        turnover_snapshot: List[ScoutCandidate] | None = None,
    ) -> str:
        lines = [
            "*Scout Report — Decision View*",
            "Legend: 🟢 `SAFE` | 🟡 `WARN/REPUTATION`/`LINDY/WARN` | 🟠 `WARN/SECURITY`",
            "",
        ]
        self._append_lending_snapshot(lines, lending_snapshot)
        self._append_turnover_snapshot(lines, turnover_snapshot)
        results = [item for item in results if self._is_allowed_candidate(item)]
        sections = [
            (PriorityTier.LOW_VOLATILITY, "1) Stable/Stable"),
            (PriorityTier.COIN_STABLE, "2) Token/Stable"),
            (PriorityTier.COIN_COIN, "3) Token/Token"),
        ]
        for priority, title in sections:
            section_results = [r for r in results if r.priority == priority]
            if not section_results:
                continue
            section_results = sorted(
                section_results,
                key=lambda r: (r.candidate.apy or 0.0, r.candidate.tvl_usd or 0.0),
                reverse=True,
            )
            if isinstance(self.top_n_per_section, int) and self.top_n_per_section > 0:
                section_results = section_results[: self.top_n_per_section]
            lines.append(f"*{title}*")
            for r in section_results:
                badge = self._risk_badge(r.metadata.get("bucket", "N/A"))
                chain = r.candidate.chain
                sym = r.candidate.symbol
                project = r.candidate.project
                apy = f"{r.candidate.apy:.2f}%"
                tvl = self._format_tvl(r.candidate.tvl_usd)
                vol_24h = getattr(r.candidate, "volume_24h_usd", None)
                vol_str = ""
                if isinstance(vol_24h, (int, float)) and float(vol_24h) > 0:
                    tvl_value = float(r.candidate.tvl_usd)
                    ratio = (float(vol_24h) / tvl_value) if tvl_value > 0 else None
                    ratio_str = f"{ratio:.2f}" if ratio is not None else "n/a"
                    vol_str = f" | Vol24h {self._format_tvl(float(vol_24h))} | Vol/TVL {ratio_str}"
                bucket = r.metadata.get("bucket", "N/A")
                sleeve = r.metadata.get("sleeve", "n/a")
                reason_codes = r.metadata.get("warn_reasons", "-") or "-"
                net_1k = r.metadata.get("net_profit_1k_usd", "n/a")
                freshness = r.metadata.get("freshness_status", "UNVERIFIED")
                age_m = r.metadata.get("age_minutes", "-") or "-"
                d_apy = r.metadata.get("apy_divergence_pct", "-") or "-"
                d_tvl = r.metadata.get("tvl_divergence_pct", "-") or "-"
                pool_link = self._pool_link(r)
                tags = []
                if self.include_tags:
                    tier = r.metadata.get("stable_tier")
                    if tier:
                        tags.append(f"Tier:{tier}")
                    pair_class = r.metadata.get("pair_currency_class")
                    if pair_class:
                        tags.append(f"Class:{pair_class}")
                    fx = r.metadata.get("fx_exposure")
                    if fx == "true":
                        tags.append("FX_RISK")
                tags_str = " ".join(tags) if tags else ""
                # Strategy simulation fields
                sim_fields = []
                sim_status = r.metadata.get("sim_status")
                if sim_status == "OK":
                    best_strat = r.metadata.get("sim_best_strategy")
                    if best_strat:
                        sim_fields.append(f"BestStrategy:{best_strat}")
                    sim_fields.append("SimStatus:OK")
                    fit_score = r.metadata.get("sim_fit_score")
                    if fit_score:
                        sim_fields.append(f"FitScore:{fit_score}")
                    exp_apy = r.metadata.get("sim_exp_net_apy_min")
                    if exp_apy:
                        exp_max = r.metadata.get("sim_exp_net_apy_max", exp_apy)
                        sim_fields.append(f"ExpNetAPY:{exp_apy}-{exp_max}%")
                    risk_score = r.metadata.get("sim_risk_score")
                    if risk_score:
                        sim_fields.append(f"SimRisk:{risk_score}")
                sim_str = " ".join(sim_fields) if sim_fields else ""
                lines.append(
                    f"- {badge} `{chain}` `{sym}` | `{project}` | APY {apy} | TVL {tvl} | "
                    f"Risk `{bucket}`" + (f" | Tags {tags_str}" if tags_str else "") + f" | Sleeve `{sleeve}` | Reasons `{reason_codes}` | "
                    f"Fresh `{freshness}` ({age_m}m) | ΔAPY {d_apy}% ΔTVL {d_tvl}% | "
                    f"Net@1k ${net_1k}/mo" + vol_str + (f" | {sim_str}" if sim_str else "") + f" | [Pool]({pool_link})"
                )
            lines.append("")
        return "\n".join(lines)

    def _append_lending_snapshot(
        self,
        lines: List[str],
        lending_snapshot: LendingSnapshot | None,
    ) -> None:
        if lending_snapshot is None or not lending_snapshot.has_any():
            return

        lines.append("*Lending Snapshot*")
        if lending_snapshot.best_eth_supply:
            item = lending_snapshot.best_eth_supply
            lines.append(
                f"- Best ETH supply: `{item.candidate.chain}` `{item.candidate.symbol}` | "
                f"`{item.candidate.project}` | Supply APY {item.metric_value_pct:.2f}% | "
                f"TVL {self._format_tvl(item.candidate.tvl_usd)} | [Pool]({self._pool_link_from_candidate(item.candidate)})"
            )
        if lending_snapshot.best_btc_supply:
            item = lending_snapshot.best_btc_supply
            lines.append(
                f"- Best BTC supply: `{item.candidate.chain}` `{item.candidate.symbol}` | "
                f"`{item.candidate.project}` | Supply APY {item.metric_value_pct:.2f}% | "
                f"TVL {self._format_tvl(item.candidate.tvl_usd)} | [Pool]({self._pool_link_from_candidate(item.candidate)})"
            )
        if lending_snapshot.best_gho_supply:
            item = lending_snapshot.best_gho_supply
            lines.append(
                f"- Best GHO supply: `{item.candidate.chain}` `{item.candidate.symbol}` | "
                f"`{item.candidate.project}` | Supply APY {item.metric_value_pct:.2f}% | "
                f"TVL {self._format_tvl(item.candidate.tvl_usd)} | [Pool]({self._pool_link_from_candidate(item.candidate)})"
            )
        if lending_snapshot.lowest_stable_borrow:
            item = lending_snapshot.lowest_stable_borrow
            lines.append(
                f"- Cheapest stable borrow: `{item.candidate.chain}` `{item.candidate.symbol}` | "
                f"`{item.candidate.project}` | Borrow APR {item.metric_value_pct:.2f}% | "
                f"TVL {self._format_tvl(item.candidate.tvl_usd)} | [Pool]({self._pool_link_from_candidate(item.candidate)})"
            )
        if lending_snapshot.lowest_eurc_borrow:
            item = lending_snapshot.lowest_eurc_borrow
            lines.append(
                f"- Cheapest EURC borrow: `{item.candidate.chain}` `{item.candidate.symbol}` | "
                f"`{item.candidate.project}` | Borrow APR {item.metric_value_pct:.2f}% | "
                f"TVL {self._format_tvl(item.candidate.tvl_usd)} | [Pool]({self._pool_link_from_candidate(item.candidate)})"
            )
        if lending_snapshot.lowest_usdc_borrow:
            item = lending_snapshot.lowest_usdc_borrow
            lines.append(
                f"- Cheapest USDC borrow: `{item.candidate.chain}` `{item.candidate.symbol}` | "
                f"`{item.candidate.project}` | Borrow APR {item.metric_value_pct:.2f}% | "
                f"TVL {self._format_tvl(item.candidate.tvl_usd)} | [Pool]({self._pool_link_from_candidate(item.candidate)})"
            )
        extra_borrows = [
            (symbol, item)
            for symbol, item in sorted(
                lending_snapshot.lowest_borrow_by_symbol.items(),
                key=lambda pair: pair[1].metric_value_pct,
            )
            if symbol not in {"EURC", "USDC"}
        ]
        for symbol, item in extra_borrows:
            lines.append(
                f"- Cheapest {symbol} borrow: `{item.candidate.chain}` `{item.candidate.symbol}` | "
                f"`{item.candidate.project}` | Borrow APR {item.metric_value_pct:.2f}% | "
                f"TVL {self._format_tvl(item.candidate.tvl_usd)} | [Pool]({self._pool_link_from_candidate(item.candidate)})"
            )
        if lending_snapshot.best_gho_supply:
            borrow_candidates = [
                item
                for item in [lending_snapshot.lowest_eurc_borrow, lending_snapshot.lowest_usdc_borrow]
                if item is not None
            ]
            if borrow_candidates:
                best_borrow = min(borrow_candidates, key=lambda item: item.metric_value_pct)
                spread = lending_snapshot.best_gho_supply.metric_value_pct - best_borrow.metric_value_pct
                coverage = (
                    (lending_snapshot.best_gho_supply.metric_value_pct / best_borrow.metric_value_pct) * 100.0
                    if best_borrow.metric_value_pct > 0
                    else 0.0
                )
                lines.append(
                    f"- Carry pre-check: GHO supply {lending_snapshot.best_gho_supply.metric_value_pct:.2f}% "
                    f"vs {best_borrow.candidate.symbol} borrow {best_borrow.metric_value_pct:.2f}% | "
                    f"Spread {spread:+.2f}pp | Coverage {coverage:.0f}%"
                )
        lines.append("")

    def _append_turnover_snapshot(
        self,
        lines: List[str],
        turnover_snapshot: List[ScoutCandidate] | None,
    ) -> None:
        if not turnover_snapshot:
            return

        allowed: list[ScoutCandidate] = []
        for candidate in turnover_snapshot:
            fake = ScoutResult(
                candidate=candidate,
                security=None,
                net_apy=0.0,
                score=0.0,
                net_profit_usd=0.0,
                priority=PriorityTier.COIN_COIN,
                metadata={},
                flags=[],
            )
            if self._is_allowed_candidate(fake):
                allowed.append(candidate)

        if not allowed:
            return

        lines.append("*High Turnover (24h) — Market Snapshot*")
        for candidate in allowed:
            vol = getattr(candidate, "volume_24h_usd", None)
            if not isinstance(vol, (int, float)) or float(vol) <= 0:
                continue
            tvl_value = float(candidate.tvl_usd or 0.0)
            ratio = (float(vol) / tvl_value) if tvl_value > 0 else 0.0
            lines.append(
                f"- `{candidate.chain}` `{candidate.symbol}` | `{candidate.project}` | "
                f"TVL {self._format_tvl(float(candidate.tvl_usd))} | Vol24h {self._format_tvl(float(vol))} | "
                f"Vol/TVL {ratio:.2f} | APY {candidate.apy:.2f}% | [Pool]({self._pool_link_from_candidate(candidate)})"
            )
        lines.append("")

    def _chunk_message(self, text: str, max_len: int = 3500) -> List[str]:
        chunks: List[str] = []
        current = ""
        for line in text.splitlines():
            candidate = f"{current}\n{line}".strip() if current else line
            if len(candidate) <= max_len:
                current = candidate
                continue
            if current:
                chunks.append(current)
                current = line
            else:
                # Extremely long line fallback (unlikely for our format)
                chunks.append(line[:max_len])
                current = line[max_len:]
        if current:
            chunks.append(current)
        return chunks or [text]

    def _risk_badge(self, bucket: str) -> str:
        if bucket == "SAFE":
            return "🟢"
        if bucket in {"WARN/REPUTATION", "LINDY/WARN"}:
            return "🟡"
        return "🟠"

    def _format_tvl(self, value: float) -> str:
        if value >= 1_000_000_000:
            return f"${value / 1_000_000_000:.2f}B"
        if value >= 1_000_000:
            return f"${value / 1_000_000:.2f}M"
        if value >= 1_000:
            return f"${value / 1_000:.1f}K"
        return f"${value:.0f}"

    def _pool_link(self, result: ScoutResult) -> str:
        return self._pool_link_from_candidate(result.candidate)

    def _pool_link_from_candidate(self, candidate: ScoutCandidate) -> str:
        pool_id = getattr(candidate, "pool_id", "") or ""
        if not pool_id:
            return "https://defillama.com/yields"

        # If pool_id looks like an onchain contract address (DEX discovery), link to a chain explorer.
        if re.fullmatch(r"0x[a-fA-F0-9]{40}", pool_id):
            chain_id = getattr(candidate, "chain_id", None)
            explorer = {
                1: "https://etherscan.io/address/",
                10: "https://optimistic.etherscan.io/address/",
                56: "https://bscscan.com/address/",
                137: "https://polygonscan.com/address/",
                42161: "https://arbiscan.io/address/",
                43114: "https://snowtrace.io/address/",
                8453: "https://basescan.org/address/",
            }.get(chain_id)
            if explorer:
                return f"{explorer}{pool_id}"

        return f"https://defillama.com/yields/pool/{pool_id}"

    def _is_allowed_candidate(self, result: ScoutResult) -> bool:
        tokens = self._extract_tokens(result.candidate.symbol)
        if not tokens:
            return False
        return all(self._is_allowed_token(token) for token in tokens)

    def _extract_tokens(self, symbol: str) -> list[str]:
        parts = re.split(r"[-/\\s]+", symbol or "")
        return [self._normalize_token(part) for part in parts if part.strip()]

    def _normalize_token(self, token: str) -> str:
        normalized = token.upper().replace("₮", "T")
        normalized = re.sub(r"[^A-Z0-9.]", "", normalized)
        return normalized

    def _is_allowed_token(self, token: str) -> bool:
        return (
            token in self._ALLOWED_STABLES
            or token in self._ALLOWED_BTC
            or token in self._ALLOWED_ETH
            or token in self._ALLOWED_GOLD
        )
