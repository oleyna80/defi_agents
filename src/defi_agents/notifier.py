from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any, List

import httpx

from .scout.models import (
    LendingSnapshot,
    MonitoredPoolSnapshot,
    MyPoolsMonitorReport,
    PoolHealthTag,
    PriorityTier,
    ScoutCandidate,
    ScoutResult,
    YieldDirectionSnapshot,
)
from .lp.models import EntryRecommendation, EntryActionability


class TelegramNotifier:
    _ALLOWED_STABLES = {
        "USDC",
        "USDT",
        "DAI",
        "USDS",
        "FRAX",
        "LUSD",
        "USDE",
        "GHO",
        "PYUSD",
        "CRVUSD",
        "EURS",
        "EURC",
        "AGEUR",
        "EURE",
        "FDUSD",
        "TUSD",
        "USDP",
        "USDD",
        "USD0",
        "USD1",
        "RLUSD",
        "USDG",
        "USDY",
        "SUSDS",
        "SDAI",
        "USDBC",
    }
    _ALLOWED_BTC = {
        "BTC",
        "WBTC",
        "WBTC.B",
        "CBBTC",
        "TBTC",
        "RENBTC",
        "SBTC",
        "BTCB",
        "LBTC",
    }
    _ALLOWED_ETH = {
        "ETH",
        "WETH",
        "STETH",
        "WSTETH",
        "RETH",
        "CBETH",
        "EETH",
        "WEETH",
        "METH",
        "SETH",
    }
    _ALLOWED_GOLD = {"XAUT", "PAXG", "PAXGOLD"}

    def __init__(
        self,
        include_tags: bool = False,
        top_n_per_section: int = 0,
        show_opportunity_sections: bool = True,
        show_source_confidence: bool = True,
        show_market_signals: bool = False,
        chat_id_env: str | None = None,
        message_prefix: str = "",
    ) -> None:
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        configured_chat = os.getenv(chat_id_env) if chat_id_env else None
        self.chat_id = (
            configured_chat or os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID")
        )
        self.include_tags = include_tags
        self.top_n_per_section = (
            int(top_n_per_section) if isinstance(top_n_per_section, int) else 0
        )
        self.show_opportunity_sections = bool(show_opportunity_sections)
        self.show_source_confidence = show_source_confidence
        self.show_market_signals = show_market_signals
        self.message_prefix = (message_prefix or "").strip()

    async def send_alpha_report(
        self,
        results: List[ScoutResult],
        lending_snapshot: LendingSnapshot | None = None,
        turnover_snapshot: List[ScoutCandidate] | None = None,
        directional_snapshot: YieldDirectionSnapshot | None = None,
        my_pools_report: MyPoolsMonitorReport | None = None,
        entry_recommendations: List[EntryRecommendation] | None = None,
    ) -> None:
        blocks = self._format_report_blocks(
            results,
            lending_snapshot=lending_snapshot,
            turnover_snapshot=turnover_snapshot,
            directional_snapshot=directional_snapshot,
            my_pools_report=my_pools_report,
            entry_recommendations=entry_recommendations,
        )
        for block in blocks:
            for chunk in self._chunk_message(block):
                await self._send(chunk)

    async def send_error(self, text: str) -> None:
        await self._send(f"⚠️ {text}")

    async def send_markdown_report(self, text: str) -> None:
        for chunk in self._chunk_message(text):
            await self._send(chunk)

    async def fetch_recheck_requests(
        self,
        *,
        offset: int | None = None,
        limit: int = 20,
        command: str = "/recheck",
    ) -> tuple[list[str], int | None]:
        """Poll Telegram updates and extract `/recheck <pool_id>` commands.

        Returns:
            (pool_ids, next_offset)
        """
        if not self.token:
            return [], offset
        url = f"https://api.telegram.org/bot{self.token}/getUpdates"
        params: dict[str, Any] = {
            "timeout": 0,
            "limit": max(1, min(int(limit), 100)),
            "allowed_updates": '["message"]',
        }
        if isinstance(offset, int):
            params["offset"] = offset
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, params=params)
            if not response.is_success:
                logging.warning(
                    "Telegram getUpdates failed: status=%s", response.status_code
                )
                return [], offset
            payload = response.json()
        except Exception as exc:  # noqa: BLE001
            logging.warning(
                "Telegram getUpdates request error: %s", exc.__class__.__name__
            )
            return [], offset

        updates = payload.get("result", []) if isinstance(payload, dict) else []
        if not isinstance(updates, list):
            return [], offset

        requests: list[str] = []
        seen: set[str] = set()
        max_update_id: int | None = None
        expected_chat = str(self.chat_id) if self.chat_id is not None else None

        for update in updates:
            if not isinstance(update, dict):
                continue
            update_id = update.get("update_id")
            if isinstance(update_id, int):
                max_update_id = (
                    update_id
                    if max_update_id is None
                    else max(max_update_id, update_id)
                )
            message = update.get("message")
            if not isinstance(message, dict):
                continue
            chat = message.get("chat")
            chat_id = (
                str(chat.get("id"))
                if isinstance(chat, dict) and chat.get("id") is not None
                else None
            )
            if expected_chat and chat_id and chat_id != expected_chat:
                continue
            text = message.get("text")
            pool_id = self._extract_recheck_pool_id(text, command=command)
            if pool_id and pool_id not in seen:
                seen.add(pool_id)
                requests.append(pool_id)

        next_offset = (max_update_id + 1) if max_update_id is not None else offset
        return requests, next_offset

    async def _send(self, text: str, retries: int = 3) -> bool:
        text_to_send = self._with_prefix(text)
        if not self.token or not self.chat_id:
            # No credentials configured; fallback to console output.
            print(text_to_send)
            return False
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text_to_send,
            "parse_mode": "Markdown",
        }
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

    def _with_prefix(self, text: str) -> str:
        if not self.message_prefix:
            return text
        if text.startswith(self.message_prefix):
            return text
        return f"{self.message_prefix}\n{text}"

    @staticmethod
    def _extract_recheck_pool_id(
        text: object, *, command: str = "/recheck"
    ) -> str | None:
        if not isinstance(text, str):
            return None
        raw = text.strip()
        if not raw:
            return None
        cmd = (command or "/recheck").strip()
        # Supports /recheck <id> and /recheck@BotName <id>.
        pattern = rf"^{re.escape(cmd)}(?:@\w+)?\s+([A-Za-z0-9\-:_]+)\s*$"
        match = re.match(pattern, raw)
        if not match:
            return None
        pool_id = match.group(1).strip()
        return pool_id or None

    def _format_report(
        self,
        results: List[ScoutResult],
        lending_snapshot: LendingSnapshot | None = None,
        turnover_snapshot: List[ScoutCandidate] | None = None,
        directional_snapshot: YieldDirectionSnapshot | None = None,
        my_pools_report: MyPoolsMonitorReport | None = None,
        entry_recommendations: List[EntryRecommendation] | None = None,
    ) -> str:
        lines = [
            "*Scout Report — Decision View*",
            "Legend: 🟢 `SAFE` | 🟡 `WARN/REPUTATION`/`LINDY/WARN` | 🟠 `WARN/SECURITY`",
            "",
        ]
        self._append_my_pools_sections(lines, my_pools_report)
        self._append_entry_recommendations(lines, entry_recommendations)
        self._append_directional_snapshot(lines, directional_snapshot)
        if not (directional_snapshot and directional_snapshot.has_any()):
            self._append_lending_snapshot(lines, lending_snapshot)
            self._append_turnover_snapshot(lines, turnover_snapshot)
        if self.show_opportunity_sections:
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
                    lines.append(self._format_opportunity_line(r))
                lines.append("")
        return "\n".join(lines)

    def _format_report_blocks(
        self,
        results: List[ScoutResult],
        lending_snapshot: LendingSnapshot | None = None,
        turnover_snapshot: List[ScoutCandidate] | None = None,
        directional_snapshot: YieldDirectionSnapshot | None = None,
        my_pools_report: MyPoolsMonitorReport | None = None,
        entry_recommendations: List[EntryRecommendation] | None = None,
        *,
        max_len: int = 3500,
    ) -> List[str]:
        """Format report as deterministic section blocks.

        This avoids arbitrary mid-section splitting when the report exceeds Telegram length limits.
        """
        header = [
            "*Scout Report — Decision View*",
            "Legend: 🟢 `SAFE` | 🟡 `WARN/REPUTATION`/`LINDY/WARN` | 🟠 `WARN/SECURITY`",
            "",
        ]
        continuation = ["*Scout Report — Decision View* (continued)", ""]

        sections: List[List[str]] = []

        my_pools_sections = self._format_my_pools_sections(my_pools_report)
        if my_pools_sections:
            sections.extend(my_pools_sections)

        lp_entry_sections = self._format_entry_recommendation_sections(
            entry_recommendations
        )
        if lp_entry_sections:
            sections.extend(lp_entry_sections)

        directional_sections = self._format_directional_sections(directional_snapshot)
        if directional_sections:
            sections.extend(directional_sections)
        else:
            lending_lines: List[str] = []
            self._append_lending_snapshot(lending_lines, lending_snapshot)
            if lending_lines:
                sections.append(lending_lines)

            turnover_lines: List[str] = []
            self._append_turnover_snapshot(turnover_lines, turnover_snapshot)
            if turnover_lines:
                sections.append(turnover_lines)

        if self.show_opportunity_sections:
            sections.extend(
                self._format_opportunity_section_lines(results, max_len=max_len)
            )

        if not sections:
            if not self.show_opportunity_sections:
                return []
            return ["\n".join(header).strip()]

        blocks: List[str] = []
        for idx, section in enumerate(sections):
            prefix = header if idx == 0 else continuation
            blocks.append("\n".join(prefix + section).strip())
        return blocks

    def _format_my_pools_sections(
        self,
        my_pools_report: MyPoolsMonitorReport | None,
    ) -> List[List[str]]:
        if my_pools_report is None or not my_pools_report.has_any():
            return []

        snapshots = [
            snap
            for snap in my_pools_report.snapshots
            if self._is_allowed_snapshot(snap)
        ]
        if not snapshots:
            return []

        top_n = int(getattr(my_pools_report, "top_n", 0) or 0)
        if top_n > 0:
            snapshots = snapshots[:top_n]

        sections: List[List[str]] = []
        if bool(getattr(my_pools_report, "show_health", True)):
            health_lines: List[str] = ["*My Pools — Health*"]
            health_lines.append(
                f"- Pools: {len(my_pools_report.snapshots)} | "
                f"Healthy {int(my_pools_report.healthy_count)} | "
                f"Watch {int(my_pools_report.watch_count)} | "
                f"Unverified {int(my_pools_report.unverified_count)}"
            )
            for snap in snapshots:
                health_lines.append(self._format_my_pool_health_line(snap))
            health_lines.append("")
            sections.append(health_lines)

        if bool(getattr(my_pools_report, "show_alerts", True)):
            alerts = [
                snap
                for snap in snapshots
                if PoolHealthTag.HEALTHY not in snap.health_tags
            ]
            if alerts:
                alert_lines: List[str] = ["*My Pools — Alerts*"]
                for snap in alerts:
                    alert_lines.append(self._format_my_pool_alert_line(snap))
                alert_lines.append("")
                sections.append(alert_lines)

        return sections

    def _format_entry_recommendation_sections(
        self,
        entry_recommendations: List[EntryRecommendation] | None,
    ) -> List[List[str]]:
        if not entry_recommendations:
            return []

        actionable = [
            r
            for r in entry_recommendations
            if r.actionability == EntryActionability.ACTIONABLE
        ]
        watchlist = [
            r
            for r in entry_recommendations
            if r.actionability == EntryActionability.WATCHLIST
        ]

        lines: List[str] = ["*LP Entry Recommendations*"]
        if actionable:
            lines.append("- Actionable:")
            for item in actionable:
                lines.append(self._format_entry_recommendation_line(item))
        if watchlist:
            lines.append("- Watchlist:")
            for item in watchlist:
                lines.append(self._format_entry_recommendation_line(item))
        lines.append("")

        selector_lines: List[str] = ["*LP Entry — Network/Protocol/Range Selector*", "- Top-N comparison:"]
        for item in actionable:
            selector_lines.append(self._format_entry_selector_line(item))
        if not actionable:
            selector_lines.append("  - no actionable selector matches (WATCHLIST-only cycle)")
        selector_lines.append("")

        return [lines, selector_lines]

    def _format_entry_recommendation_line(self, item: EntryRecommendation) -> str:
        range_part = "Range: n/a"
        if (
            item.suggested_range_lower_tick is not None
            and item.suggested_range_upper_tick is not None
        ):
            range_part = f"Range: [{item.suggested_range_lower_tick},{item.suggested_range_upper_tick}]"

        fee_part = f"fee {item.fee_tier}bps" if item.fee_tier is not None else "fee n/a"
        reason_part = (
            f" | reason `{item.watchlist_reason}`" if item.watchlist_reason else ""
        )
        return (
            f"  - `{item.chain}` `{item.pair}` | `{item.project}` | {fee_part} | "
            f"{range_part} | Conf `{item.confidence.value}` | Rank {item.rank_v1:.4f}{reason_part}"
        )

    def _format_entry_selector_line(self, item: EntryRecommendation) -> str:
        range_repr = "n/a"
        if (
            item.suggested_range_lower_tick is not None
            and item.suggested_range_upper_tick is not None
        ):
            range_repr = (
                f"[{item.suggested_range_lower_tick},{item.suggested_range_upper_tick}]"
            )
        fee_part = f"{item.fee_tier}bps" if item.fee_tier is not None else "n/a"
        return (
            f"  - `{item.chain}`/`{item.project}` | Pair `{item.pair}` | Range `{range_repr}` "
            f"({item.range_mode}/{item.market_regime}) | fee `{fee_part}` | "
            f"comp={item.in_range_liquidity_competition:.4f} vol_fee={item.volume_fee_proxy:.4f} "
            f"cost={item.cost_penalty:.4f} conf={item.confidence_score:.4f} | rank_v1={item.rank_v1:.4f}"
        )

    def _format_opportunity_section_lines(
        self, results: List[ScoutResult], *, max_len: int
    ) -> List[List[str]]:
        filtered = [item for item in results if self._is_allowed_candidate(item)]
        sections = [
            (PriorityTier.LOW_VOLATILITY, "1) Stable/Stable"),
            (PriorityTier.COIN_STABLE, "2) Token/Stable"),
            (PriorityTier.COIN_COIN, "3) Token/Token"),
        ]

        combined: List[str] = []
        per_category: List[List[str]] = []

        for priority, title in sections:
            section_results = [r for r in filtered if r.priority == priority]
            if not section_results:
                continue
            section_results = sorted(
                section_results,
                key=lambda r: (r.candidate.apy or 0.0, r.candidate.tvl_usd or 0.0),
                reverse=True,
            )
            if isinstance(self.top_n_per_section, int) and self.top_n_per_section > 0:
                section_results = section_results[: self.top_n_per_section]

            lines: List[str] = [f"*{title}*"]
            for r in section_results:
                lines.append(self._format_opportunity_line(r))
            lines.append("")

            per_category.append(lines)
            combined.extend(lines)

        if not combined:
            return []

        if len("\n".join(combined)) <= max_len:
            return [combined]
        return per_category

    def _format_directional_sections(
        self,
        directional_snapshot: YieldDirectionSnapshot | None,
    ) -> List[List[str]]:
        if directional_snapshot is None or not directional_snapshot.has_any():
            return []

        sections: List[List[str]] = []
        mapping = [
            ("*Top-10 LP (High Turnover)*", directional_snapshot.lp_top, "Vol/TVL"),
            (
                "*Top-10 Lending Supply*",
                directional_snapshot.lending_supply_top,
                "Supply APY",
            ),
            (
                "*Top-10 Lending Borrow (Cheapest)*",
                directional_snapshot.lending_borrow_top,
                "Borrow APR",
            ),
            ("*Top-10 Staking*", directional_snapshot.staking_top, "Staking APY"),
        ]
        for title, items, metric_label in mapping:
            lines: List[str] = [title]
            shown = 0
            for item in items:
                candidate = item.candidate
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
                if not self._is_allowed_candidate(fake):
                    continue
                vol_part = ""
                if metric_label == "Vol/TVL" and isinstance(
                    candidate.volume_24h_usd, (int, float)
                ):
                    vol_part = (
                        f" | Vol24h {self._format_tvl(float(candidate.volume_24h_usd))}"
                    )
                conf_part = ""
                if self.show_source_confidence:
                    conf_val = (
                        candidate.source_confidence.value
                        if hasattr(candidate.source_confidence, "value")
                        else str(candidate.source_confidence)
                    )
                    conf_part = (
                        f" | {self._confidence_badge(conf_val)} Conf `{conf_val}`"
                    )
                lines.append(
                    f"- `{candidate.chain}` `{candidate.symbol}` | `{candidate.project}` | "
                    f"{metric_label} {item.metric_value_pct:.2f}{'%' if metric_label != 'Vol/TVL' else ''} | "
                    f"TVL {self._format_tvl(float(candidate.tvl_usd))}{vol_part}{conf_part} | [Pool]({self._pool_link_from_candidate(candidate)})"
                )
                shown += 1
            if shown:
                lines.append("")
                sections.append(lines)
        return sections

    def _append_directional_snapshot(
        self,
        lines: List[str],
        directional_snapshot: YieldDirectionSnapshot | None,
    ) -> None:
        for section in self._format_directional_sections(directional_snapshot):
            lines.extend(section)

    def _append_my_pools_sections(
        self,
        lines: List[str],
        my_pools_report: MyPoolsMonitorReport | None,
    ) -> None:
        for section in self._format_my_pools_sections(my_pools_report):
            lines.extend(section)

    def _append_entry_recommendations(
        self,
        lines: List[str],
        entry_recommendations: List[EntryRecommendation] | None,
    ) -> None:
        for section in self._format_entry_recommendation_sections(
            entry_recommendations
        ):
            lines.extend(section)

    def _format_my_pool_health_line(self, snap: MonitoredPoolSnapshot) -> str:
        tags = (
            ",".join(tag.value for tag in snap.health_tags)
            if snap.health_tags
            else "HEALTHY"
        )
        label = snap.label or snap.symbol or snap.pool_ref
        conf_part = ""
        if self.show_source_confidence:
            conf_val = (
                snap.source_confidence.value
                if hasattr(snap.source_confidence, "value")
                else str(snap.source_confidence)
            )
            conf_part = f" | {self._confidence_badge(conf_val)} Conf `{conf_val}`"
        apy = f"{float(snap.apy):.2f}%" if isinstance(snap.apy, (int, float)) else "n/a"
        tvl = self._format_tvl(float(snap.tvl_usd or 0.0))
        vol = (
            self._format_tvl(float(snap.volume_24h_usd or 0.0))
            if isinstance(snap.volume_24h_usd, (int, float))
            else "n/a"
        )
        ratio = (
            f"{float(snap.vol_to_tvl_24h):.2f}"
            if isinstance(snap.vol_to_tvl_24h, (int, float))
            else "n/a"
        )
        return (
            f"- {self._pool_health_badge(snap)} `{snap.chain or 'n/a'}` `{label}` | "
            f"`{snap.project or 'n/a'}` | APY {apy} | TVL {tvl} | Vol24h {vol} | Vol/TVL {ratio} | "
            f"Fresh `{snap.freshness_status}`{conf_part} | Tags `{tags}` | [Pool]({snap.pool_url or 'https://defillama.com/yields'})"
        )

    def _format_my_pool_alert_line(self, snap: MonitoredPoolSnapshot) -> str:
        label = snap.label or snap.symbol or snap.pool_ref
        reasons = ",".join(snap.alert_reasons) if snap.alert_reasons else "NO_REASON"
        tags = (
            ",".join(tag.value for tag in snap.health_tags)
            if snap.health_tags
            else "DATA_UNVERIFIED"
        )
        return (
            f"- {self._pool_health_badge(snap)} `{snap.chain or 'n/a'}` `{label}` | "
            f"Alerts `{reasons}` | Tags `{tags}` | [Pool]({snap.pool_url or 'https://defillama.com/yields'})"
        )

    def _format_opportunity_line(self, r: ScoutResult) -> str:
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
            vol_str = (
                f" | Vol24h {self._format_tvl(float(vol_24h))} | Vol/TVL {ratio_str}"
            )
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
        conf_str = ""
        if self.show_source_confidence:
            confidence = r.metadata.get("source_confidence", "AGGREGATOR_ONLY")
            conf_str = f" | {self._confidence_badge(confidence)} Conf `{confidence}`"
        signal_str = ""
        if self.show_market_signals:
            signals: list[str] = []
            apy_vs_30d = r.metadata.get("apy_vs_mean_30d_pct", "")
            if apy_vs_30d not in {"", "-"}:
                try:
                    signals.append(f"APYvs30d:{float(apy_vs_30d):+.1f}%")
                except (TypeError, ValueError):
                    pass
            stability_factor = r.metadata.get("stability_factor", "")
            if stability_factor not in {"", "-"}:
                signals.append(f"StabF:{stability_factor}")
            raw_signals = r.metadata.get("stability_signals", "")
            if raw_signals:
                signals.append(f"Flags:{raw_signals}")
            if signals:
                signal_str = " | " + " ".join(signals)
        return (
            f"- {badge} `{chain}` `{sym}` | `{project}` | APY {apy} | TVL {tvl} | "
            f"Risk `{bucket}`"
            + (f" | Tags {tags_str}" if tags_str else "")
            + f" | Sleeve `{sleeve}` | Reasons `{reason_codes}` | "
            f"Fresh `{freshness}` ({age_m}m){conf_str} | ΔAPY {d_apy}% ΔTVL {d_tvl}% | "
            f"Net@1k ${net_1k}/mo"
            + vol_str
            + signal_str
            + (f" | {sim_str}" if sim_str else "")
            + f" | [Pool]({pool_link})"
        )

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
                for item in [
                    lending_snapshot.lowest_eurc_borrow,
                    lending_snapshot.lowest_usdc_borrow,
                ]
                if item is not None
            ]
            if borrow_candidates:
                best_borrow = min(
                    borrow_candidates, key=lambda item: item.metric_value_pct
                )
                spread = (
                    lending_snapshot.best_gho_supply.metric_value_pct
                    - best_borrow.metric_value_pct
                )
                coverage = (
                    (
                        lending_snapshot.best_gho_supply.metric_value_pct
                        / best_borrow.metric_value_pct
                    )
                    * 100.0
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

    def _confidence_badge(self, conf: str) -> str:
        return {
            "VERIFIED": "✅",
            "AGGREGATOR_ONLY": "⚪",
            "DIVERGED": "⚠️",
            "STALE": "🔴",
        }.get(conf, "⚪")

    def _pool_health_badge(self, snap: MonitoredPoolSnapshot) -> str:
        if PoolHealthTag.DATA_UNVERIFIED in snap.health_tags:
            return "⚪"
        if any(
            tag in snap.health_tags
            for tag in (
                PoolHealthTag.WATCH_VOLUME,
                PoolHealthTag.WATCH_APY_DRIFT,
                PoolHealthTag.WATCH_TVL_DRAIN,
            )
        ):
            return "🟡"
        return "🟢"

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

    def _is_allowed_snapshot(self, snapshot: MonitoredPoolSnapshot) -> bool:
        if not snapshot.symbol:
            return True
        tokens = self._extract_tokens(snapshot.symbol)
        if not tokens:
            return True
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
