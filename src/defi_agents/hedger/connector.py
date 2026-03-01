from __future__ import annotations

from typing import Any, Awaitable, Callable

import httpx

from .models import HedgeConnectorHealth, HedgeIntent, HedgeSimulationResult

RequestFn = Callable[[str, str, dict[str, str], dict[str, Any] | None], Awaitable[tuple[int, Any]]]


class HummingbotConnectorError(RuntimeError):
    def __init__(self, reason_code: str, detail: str | None = None) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.detail = detail


class HummingbotShadowConnector:
    """Minimal connector wrapper for PoC health checks and shadow simulations."""

    supports_live_execution = False

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 8.0,
        api_key: str = "",
        exchange: str = "binance_perpetual",
        market_map: dict[str, str] | None = None,
        health_path: str = "/health",
        markets_path: str = "/api/v1/markets",
        ticker_path: str = "/api/v1/ticker",
        request_fn: RequestFn | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.api_key = (api_key or "").strip()
        self.exchange = (exchange or "").strip()
        self.market_map = {str(k).upper(): str(v) for k, v in (market_map or {}).items()}
        self.health_path = health_path
        self.markets_path = markets_path
        self.ticker_path = ticker_path
        self._request_fn = request_fn

    async def probe_health(self, symbol: str) -> HedgeConnectorHealth:
        reasons: list[str] = []
        market = self._resolve_market(symbol)

        auth_ok = False
        instrument_ok = False
        bbo_ok = False
        metadata: dict[str, Any] = {"exchange": self.exchange, "market": market}

        try:
            await self._check_auth()
            auth_ok = True
        except HummingbotConnectorError as exc:
            reasons.append(exc.reason_code)
            if exc.detail:
                metadata["auth_detail"] = exc.detail
            return HedgeConnectorHealth(
                ok=False,
                auth_ok=False,
                instrument_ok=False,
                bbo_ok=False,
                reason_codes=reasons,
                metadata=metadata,
            )

        try:
            markets_payload = await self._get_json(self.markets_path, {"exchange": self.exchange})
            if not self._market_supported(markets_payload, market):
                reasons.append("MARKET_UNSUPPORTED")
            else:
                instrument_ok = True
        except HummingbotConnectorError as exc:
            reasons.append(exc.reason_code)
            if exc.detail:
                metadata["markets_detail"] = exc.detail

        try:
            bid, ask = await self._fetch_bbo(market)
            metadata["best_bid"] = bid
            metadata["best_ask"] = ask
            bbo_ok = True
        except HummingbotConnectorError as exc:
            reasons.append(exc.reason_code)
            if exc.detail:
                metadata["bbo_detail"] = exc.detail

        reason_codes = self._dedupe(reasons)
        return HedgeConnectorHealth(
            ok=(auth_ok and instrument_ok and bbo_ok and not reason_codes),
            auth_ok=auth_ok,
            instrument_ok=instrument_ok,
            bbo_ok=bbo_ok,
            reason_codes=reason_codes,
            metadata=metadata,
        )

    async def simulate_order(self, intent: HedgeIntent, *, max_slippage_bps: int) -> HedgeSimulationResult:
        if intent.action != "HEDGE":
            return HedgeSimulationResult(ok=False, reason_codes=["INTENT_NOT_HEDGE"])
        if intent.side not in {"LONG", "SHORT"}:
            return HedgeSimulationResult(ok=False, reason_codes=["INVALID_HEDGE_SIDE"])
        if intent.target_notional_usd <= 0:
            return HedgeSimulationResult(ok=False, reason_codes=["TARGET_NOTIONAL_INVALID"])

        health = await self.probe_health(intent.symbol)
        if not health.ok:
            reasons = ["CONNECTOR_NOT_READY", *health.reason_codes]
            return HedgeSimulationResult(ok=False, reason_codes=self._dedupe(reasons), metadata=health.metadata)

        bid = self._to_float(health.metadata.get("best_bid"))
        ask = self._to_float(health.metadata.get("best_ask"))
        if bid is None or ask is None or bid <= 0 or ask <= 0 or ask < bid:
            return HedgeSimulationResult(ok=False, reason_codes=["BBO_UNAVAILABLE"], metadata=health.metadata)

        fill_price = ask if intent.side == "LONG" else bid
        mid_price = (bid + ask) / 2.0
        if mid_price <= 0:
            return HedgeSimulationResult(ok=False, reason_codes=["BBO_UNAVAILABLE"], metadata=health.metadata)
        slippage_bps = abs(fill_price - mid_price) / mid_price * 10_000.0
        if slippage_bps > float(max_slippage_bps):
            return HedgeSimulationResult(
                ok=False,
                reason_codes=["SLIPPAGE_LIMIT_EXCEEDED"],
                expected_fill_price=fill_price,
                mid_price=mid_price,
                expected_slippage_bps=slippage_bps,
                metadata=health.metadata,
            )

        quantity = intent.target_notional_usd / fill_price
        return HedgeSimulationResult(
            ok=True,
            reason_codes=[],
            expected_fill_price=fill_price,
            mid_price=mid_price,
            expected_slippage_bps=slippage_bps,
            estimated_quantity=quantity,
            metadata=health.metadata,
        )

    async def _check_auth(self) -> None:
        await self._get_json(self.health_path, {"exchange": self.exchange})

    async def _fetch_bbo(self, market: str) -> tuple[float, float]:
        payload = await self._get_json(
            self.ticker_path,
            {
                "exchange": self.exchange,
                "market": market,
            },
        )
        container = self._first_dict(payload, ["data", "result", "ticker", "orderbook"])
        bid = self._to_float(
            self._pick(container, ["bid", "best_bid", "bestBid"])
            if container is not None
            else self._pick(payload, ["bid", "best_bid", "bestBid"])
        )
        ask = self._to_float(
            self._pick(container, ["ask", "best_ask", "bestAsk"])
            if container is not None
            else self._pick(payload, ["ask", "best_ask", "bestAsk"])
        )
        if bid is None or ask is None or bid <= 0 or ask <= 0 or ask < bid:
            raise HummingbotConnectorError("BBO_UNAVAILABLE")
        return bid, ask

    def _resolve_market(self, symbol: str) -> str:
        key = str(symbol or "").strip().upper()
        return self.market_map.get(key, f"{key}-USDT")

    @classmethod
    def _market_supported(cls, payload: Any, market: str) -> bool:
        markets = cls._extract_markets(payload)
        return market.upper() in {m.upper() for m in markets}

    @classmethod
    def _extract_markets(cls, payload: Any) -> list[str]:
        candidates = payload
        if isinstance(payload, dict):
            candidates = (
                payload.get("markets")
                or payload.get("symbols")
                or payload.get("pairs")
                or payload.get("data")
                or payload.get("result")
                or []
            )
        if not isinstance(candidates, list):
            return []
        result: list[str] = []
        for item in candidates:
            if isinstance(item, str):
                result.append(item)
                continue
            if isinstance(item, dict):
                value = cls._pick(item, ["market", "symbol", "pair", "name"])
                if value is not None:
                    result.append(str(value))
        return result

    async def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            headers["X-API-KEY"] = self.api_key

        status_code: int
        body: Any
        if self._request_fn is not None:
            try:
                status_code, body = await self._request_fn("GET", path, headers, params)
            except HummingbotConnectorError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise HummingbotConnectorError("CONNECTOR_REQUEST_ERROR", detail=exc.__class__.__name__) from exc
        else:
            url = f"{self.base_url}{path}"
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    resp = await client.get(url, params=params, headers=headers)
                status_code = int(resp.status_code)
                try:
                    body = resp.json()
                except ValueError as exc:
                    raise HummingbotConnectorError("CONNECTOR_INVALID_JSON") from exc
            except httpx.TimeoutException as exc:
                raise HummingbotConnectorError("CONNECTOR_TIMEOUT") from exc
            except httpx.HTTPError as exc:
                raise HummingbotConnectorError("CONNECTOR_HTTP_ERROR", detail=exc.__class__.__name__) from exc

        if status_code in (401, 403):
            raise HummingbotConnectorError("AUTH_FAILED")
        if status_code == 404:
            raise HummingbotConnectorError("ENDPOINT_NOT_FOUND", detail=path)
        if status_code >= 500:
            raise HummingbotConnectorError("CONNECTOR_HTTP_5XX", detail=str(status_code))
        if status_code >= 400:
            raise HummingbotConnectorError(f"CONNECTOR_HTTP_{status_code}")
        if not isinstance(body, (dict, list)):
            raise HummingbotConnectorError("CONNECTOR_INVALID_RESPONSE")
        return body

    @staticmethod
    def _pick(payload: dict[str, Any], keys: list[str]) -> Any:
        for key in keys:
            if key in payload:
                return payload.get(key)
        return None

    @classmethod
    def _first_dict(cls, payload: Any, keys: list[str]) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None
        for key in keys:
            value = payload.get(key)
            if isinstance(value, dict):
                return value
        return None

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for value in values:
            if value and value not in seen:
                seen.add(value)
                ordered.append(value)
        return ordered

