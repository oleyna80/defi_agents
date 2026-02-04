from __future__ import annotations

import asyncio
import logging
import os
from typing import List

import httpx

from .scout.models import ScoutResult


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
        lines = ["*Scout Report*", ""]
        actionable = [r for r in results if r.metadata.get("report_group") == "ACTIONABLE"]
        watchlist = [r for r in results if r.metadata.get("report_group") != "ACTIONABLE"]

        def _append_section(title: str, section_results: List[ScoutResult]) -> None:
            if not section_results:
                return
            lines.append(f"*{title}*")
            for r in section_results:
                sym = r.candidate.symbol
                chain = r.candidate.chain
                score = f"{r.score:.2f}"
                apy = f"{r.candidate.apy:.2f}%"
                profit = f"{r.net_profit_usd:.2f}"
                bucket = r.metadata.get("bucket", "N/A")
                sleeve = r.metadata.get("sleeve", "n/a")
                bench = "ABOVE_BENCH" if r.metadata.get("above_benchmark") == "true" else "BELOW_BENCH"
                bench_delta = r.metadata.get("benchmark_delta_apy", "0.00")
                l3_tag = getattr(r.candidate.l3_status, "value", r.candidate.l3_status) or "N/A"
                reason_codes = r.metadata.get("warn_reasons", "")
                reasons_tail = f" | Reasons `{reason_codes}`" if reason_codes else ""
                lines.append(
                    f"- `{chain}` `{sym}` | Bucket `{bucket}` | Sleeve `{sleeve}` | APY {apy} | Score {score} | "
                    f"Net ${profit}/mo | `{bench}` ({bench_delta}%) | {r.security.status.value.upper()} | "
                    f"L3 `{l3_tag}`{reasons_tail}"
                )
            lines.append("")

        _append_section("Actionable (Net >= Min Profit)", actionable)
        _append_section("Watchlist (Manual Review)", watchlist)
        return "\n".join(lines)
