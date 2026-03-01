import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.hedger.connector import HummingbotShadowConnector
from defi_agents.hedger.models import HedgeIntent


def _run(coro):
    return asyncio.run(coro)


def _connector(*, request_fn, market_map=None, api_key=""):
    return HummingbotShadowConnector(
        base_url="http://127.0.0.1:15888",
        api_key=api_key,
        exchange="binance_perpetual",
        market_map=market_map or {"ETH": "ETH-USDT"},
        request_fn=request_fn,
    )


def _hedge_intent(*, side="SHORT", symbol="ETH", notional=1000.0):
    return HedgeIntent(
        intent_id="hedge-1",
        action="HEDGE",
        side=side,
        chain="Base",
        symbol=symbol,
        target_notional_usd=notional,
    )


def test_probe_health_success_and_shadow_simulation_success():
    async def fake_request(method, path, headers, params):
        assert method == "GET"
        if path == "/health":
            return 200, {"status": "ok"}
        if path == "/api/v1/markets":
            return 200, {"markets": ["ETH-USDT", "BTC-USDT"]}
        if path == "/api/v1/ticker":
            return 200, {"bid": "2799", "ask": "2801"}
        raise AssertionError(f"unexpected path: {path}")

    connector = _connector(request_fn=fake_request)
    health = _run(connector.probe_health("ETH"))
    assert health.ok is True
    assert health.auth_ok is True
    assert health.instrument_ok is True
    assert health.bbo_ok is True
    assert health.reason_codes == []

    sim = _run(connector.simulate_order(_hedge_intent(side="SHORT"), max_slippage_bps=10))
    assert sim.ok is True
    assert sim.expected_fill_price == pytest.approx(2799.0)
    assert sim.expected_slippage_bps is not None
    assert sim.expected_slippage_bps < 10
    assert sim.estimated_quantity is not None
    assert sim.estimated_quantity > 0


def test_probe_health_auth_failed():
    async def fake_request(method, path, headers, params):
        if path == "/health":
            return 401, {"error": "unauthorized"}
        raise AssertionError(f"unexpected path: {path}")

    connector = _connector(request_fn=fake_request)
    health = _run(connector.probe_health("ETH"))
    assert health.ok is False
    assert health.auth_ok is False
    assert "AUTH_FAILED" in health.reason_codes


def test_probe_health_market_unsupported():
    async def fake_request(method, path, headers, params):
        if path == "/health":
            return 200, {"status": "ok"}
        if path == "/api/v1/markets":
            return 200, {"markets": ["BTC-USDT"]}
        if path == "/api/v1/ticker":
            return 200, {"bid": "2799", "ask": "2801"}
        raise AssertionError(f"unexpected path: {path}")

    connector = _connector(request_fn=fake_request, market_map={"ETH": "ETH-USDT"})
    health = _run(connector.probe_health("ETH"))
    assert health.ok is False
    assert health.auth_ok is True
    assert "MARKET_UNSUPPORTED" in health.reason_codes


def test_probe_health_bbo_unavailable():
    async def fake_request(method, path, headers, params):
        if path == "/health":
            return 200, {"status": "ok"}
        if path == "/api/v1/markets":
            return 200, {"markets": ["ETH-USDT"]}
        if path == "/api/v1/ticker":
            return 200, {"bid": "2799"}
        raise AssertionError(f"unexpected path: {path}")

    connector = _connector(request_fn=fake_request)
    health = _run(connector.probe_health("ETH"))
    assert health.ok is False
    assert "BBO_UNAVAILABLE" in health.reason_codes


def test_simulate_order_rejects_non_hedge_intent():
    async def fake_request(method, path, headers, params):
        raise AssertionError("network should not be called")

    connector = _connector(request_fn=fake_request)
    intent = HedgeIntent(
        intent_id="hold-1",
        action="HOLD",
        side="NONE",
        chain="Base",
        symbol="ETH",
        target_notional_usd=0.0,
    )
    sim = _run(connector.simulate_order(intent, max_slippage_bps=100))
    assert sim.ok is False
    assert sim.reason_codes == ["INTENT_NOT_HEDGE"]


def test_simulate_order_rejects_when_slippage_too_high():
    async def fake_request(method, path, headers, params):
        if path == "/health":
            return 200, {"status": "ok"}
        if path == "/api/v1/markets":
            return 200, {"markets": ["ETH-USDT"]}
        if path == "/api/v1/ticker":
            return 200, {"bid": "100", "ask": "120"}
        raise AssertionError(f"unexpected path: {path}")

    connector = _connector(request_fn=fake_request)
    sim = _run(connector.simulate_order(_hedge_intent(side="LONG"), max_slippage_bps=100))
    assert sim.ok is False
    assert "SLIPPAGE_LIMIT_EXCEEDED" in sim.reason_codes


def test_probe_health_maps_request_exceptions_to_reason_code():
    async def fake_request(method, path, headers, params):
        raise RuntimeError("boom")

    connector = _connector(request_fn=fake_request)
    health = _run(connector.probe_health("ETH"))
    assert health.ok is False
    assert "CONNECTOR_REQUEST_ERROR" in health.reason_codes


def test_connector_injects_api_key_headers():
    seen_headers = {}

    async def fake_request(method, path, headers, params):
        seen_headers.update(headers)
        if path == "/health":
            return 200, {"status": "ok"}
        if path == "/api/v1/markets":
            return 200, {"markets": ["ETH-USDT"]}
        if path == "/api/v1/ticker":
            return 200, {"bid": "2799", "ask": "2801"}
        raise AssertionError(f"unexpected path: {path}")

    connector = _connector(request_fn=fake_request, api_key="test-key")
    _run(connector.probe_health("ETH"))
    assert seen_headers.get("Authorization") == "Bearer test-key"
    assert seen_headers.get("X-API-KEY") == "test-key"

