from __future__ import annotations

import asyncio
import logging
import os
from typing import List

import httpx

from .scout.models import PriorityTier, ScoutResult


class TelegramNotifier:
    def __init__(self) -> None:
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID")

    async def send_alpha_report(self, results: List[ScoutResult]) -> None:
        message = self._format_report(results)
        await self._send(message)

    async def send_error(self, text: str) -> None:
        await self._send(f"⚠️ {text}")

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

    def _format_report(self, results: List[ScoutResult]) -> str:
        lines = [
            "*Scout Report — Decision View*",
            "Legend: 🟢 `SAFE` | 🟡 `WARN/REPUTATION`/`LINDY/WARN` | 🟠 `WARN/SECURITY`",
            "",
        ]
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
            lines.append(f"*{title}*")
            for r in section_results:
                badge = self._risk_badge(r.metadata.get("bucket", "N/A"))
                chain = r.candidate.chain
                sym = r.candidate.symbol
                project = r.candidate.project
                apy = f"{r.candidate.apy:.2f}%"
                tvl = self._format_tvl(r.candidate.tvl_usd)
                bucket = r.metadata.get("bucket", "N/A")
                sleeve = r.metadata.get("sleeve", "n/a")
                reason_codes = r.metadata.get("warn_reasons", "-") or "-"
                net_1k = r.metadata.get("net_profit_1k_usd", "n/a")
                lines.append(
                    f"- {badge} `{chain}` `{sym}` | `{project}` | APY {apy} | TVL {tvl} | "
                    f"Risk `{bucket}` | Sleeve `{sleeve}` | Reasons `{reason_codes}` | Net@1k ${net_1k}/mo"
                )
            lines.append("")
        return "\n".join(lines)

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
