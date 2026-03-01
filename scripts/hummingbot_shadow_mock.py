#!/usr/bin/env python3
"""Minimal local mock for Hummingbot HTTP API used by hedger SHADOW runs."""

from __future__ import annotations

import json
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


def _parse_markets(raw: str) -> list[str]:
    values = [item.strip() for item in raw.split(",")]
    return [item for item in values if item]


def _build_bbo(markets: list[str]) -> dict[str, tuple[float, float]]:
    defaults: dict[str, tuple[float, float]] = {
        "ETH-USDT": (2799.0, 2801.0),
        "BTC-USDT": (51990.0, 52010.0),
    }
    result: dict[str, tuple[float, float]] = {}
    for market in markets:
        result[market] = defaults.get(market, (99.5, 100.5))
    return result


HOST = os.getenv("HUMMINGBOT_SHADOW_MOCK_HOST", "127.0.0.1").strip() or "127.0.0.1"
PORT = int(os.getenv("HUMMINGBOT_SHADOW_MOCK_PORT", "15888"))
MARKETS = _parse_markets(os.getenv("HUMMINGBOT_SHADOW_MARKETS", "ETH-USDT,BTC-USDT"))
BBO_MAP = _build_bbo(MARKETS)
EXPECTED_API_KEY = os.getenv("HUMMINGBOT_API_KEY", "").strip()


def _is_authorized(headers) -> bool:
    if not EXPECTED_API_KEY:
        return True
    bearer = headers.get("Authorization", "")
    x_api = headers.get("X-API-KEY", "")
    if bearer == f"Bearer {EXPECTED_API_KEY}":
        return True
    if x_api == EXPECTED_API_KEY:
        return True
    return False


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if not _is_authorized(self.headers):
            self._send_json(401, {"error": "unauthorized"})
            return

        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        route = parsed.path

        if route == "/health":
            self._send_json(200, {"status": "ok", "service": "hummingbot-shadow-mock"})
            return

        if route == "/api/v1/markets":
            exchange = (query.get("exchange") or [""])[0]
            self._send_json(200, {"exchange": exchange, "markets": MARKETS})
            return

        if route == "/api/v1/ticker":
            market = (query.get("market") or [""])[0]
            if market not in BBO_MAP:
                self._send_json(404, {"error": "market_not_found", "market": market})
                return
            bid, ask = BBO_MAP[market]
            self._send_json(200, {"market": market, "bid": f"{bid:.6f}", "ask": f"{ask:.6f}"})
            return

        self._send_json(404, {"error": "not_found", "path": route})

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        logging.info("%s - %s", self.address_string(), format % args)

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - hummingbot-shadow-mock - %(message)s",
    )
    server = ThreadingHTTPServer((HOST, PORT), _Handler)
    logging.info("Starting mock on http://%s:%d markets=%s", HOST, PORT, ",".join(MARKETS))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        logging.info("Stopped")


if __name__ == "__main__":
    main()
