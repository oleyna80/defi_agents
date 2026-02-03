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
                    response.raise_for_status()
                    return True
                except httpx.HTTPError as exc:
                    wait_seconds = attempt * 2
                    logging.warning(
                        "Telegram send failed (%s/%s): %s. Retry in %ss.",
                        attempt,
                        retries,
                        exc,
                        wait_seconds,
                    )
                    if attempt < retries:
                        await asyncio.sleep(wait_seconds)
        logging.error("Telegram notification failed after retries.")
        return False

    def _format_report(self, results: List[ScoutResult]) -> str:
        lines = ["*Scout Report*", ""]
        for r in results:
            sym = r.candidate.symbol
            chain = r.candidate.chain
            score = f"{r.score:.2f}"
            apy = f"{r.candidate.apy:.2f}%"
            l3_tag = getattr(r.candidate.l3_status, "value", r.candidate.l3_status) or "N/A"
            lines.append(
                f"- `{chain}` {sym} | APY {apy} | Score {score} | "
                f"{r.security.status.value.upper()} | L3 {l3_tag}"
            )
        return "\n".join(lines)
