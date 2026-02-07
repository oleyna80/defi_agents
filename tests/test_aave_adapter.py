import logging
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.freshness.adapters.aave_direct import AaveDirectAdapter
from defi_agents.scout.models import PriorityTier, ScoutCandidate, ScoutResult
from defi_agents.security.models import SecurityResult, SecurityStatus


def _result(
    *,
    project: str = "aave-v3",
    chain: str = "Ethereum",
    symbol: str = "USDC-WETH",
    address: str = "0x1111111111111111111111111111111111111111",
) -> ScoutResult:
    candidate = ScoutCandidate.model_validate(
        {
            "pool": "pool-aave-1",
            "project": project,
            "chain": chain,
            "symbol": symbol,
            "address": address,
            "chain_id": 1,
            "tvlUsd": 1_000_000,
            "apy": 6.0,
            "apyBase": 6.0,
            "apyReward": 0.0,
        }
    )
    return ScoutResult(
        candidate=candidate,
        security=SecurityResult(status=SecurityStatus.WARN, score=70),
        net_apy=6.0,
        score=5.0,
        net_profit_usd=10.0,
        priority=PriorityTier.COIN_STABLE,
        metadata={},
        flags=[],
    )


def test_aave_adapter_supports_flag_and_shape_filters():
    endpoints = {"Ethereum": "https://aave.example/v3/reserves"}
    symbols = {"Ethereum": {"USDC": "0xA0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"}}

    off_adapter = AaveDirectAdapter(enabled=False, endpoints=endpoints, reserve_symbols=symbols)
    assert off_adapter.supports(_result()) is False

    adapter = AaveDirectAdapter(enabled=True, endpoints=endpoints, reserve_symbols=symbols)
    assert adapter.supports(_result(project="aave-v3")) is True
    assert adapter.supports(_result(project="spark", symbol="USDC/DAI")) is True
    assert adapter.supports(_result(project="uniswap-v3")) is False
    assert adapter.supports(_result(chain="Arbitrum")) is False
    assert adapter.supports(_result(symbol="", project="aave-v3")) is False
    assert adapter.supports(_result(address="not-an-evm-address", project="aave-v3")) is False


class _FakeResponse:
    def __init__(self, *, status_code: int, body: object) -> None:
        self.status_code = status_code
        self._body = body

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self) -> object:
        return self._body


class _FakeClient:
    def __init__(self, *, response: _FakeResponse | None = None, exc: Exception | None = None) -> None:
        self._response = response
        self._exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, *args, **kwargs):
        if self._exc is not None:
            raise self._exc
        return self._response


@pytest.mark.asyncio
async def test_aave_adapter_fetch_snapshot_success(monkeypatch):
    endpoint = "https://aave.example/v3/reserves"
    underlying = "0xA0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
    adapter = AaveDirectAdapter(
        enabled=True,
        timeout_seconds=5,
        endpoints={"Ethereum": endpoint},
        reserve_symbols={"Ethereum": {"USDC": underlying}},
    )
    candidate = _result(address=underlying)

    body = {
        "reserves": [
            {
                "symbol": "USDC",
                "underlyingAsset": underlying,
                "lastUpdateTimestamp": 1_706_000_000,
                "supplyAPY": 0.031,
                "totalLiquidityUSD": "1234567.89",
            }
        ]
    }
    fake_response = _FakeResponse(status_code=200, body=body)
    monkeypatch.setattr(
        "defi_agents.freshness.adapters.aave_direct.httpx.AsyncClient",
        lambda timeout: _FakeClient(response=fake_response),
    )

    snapshot = await adapter.fetch_snapshot(candidate)
    assert snapshot is not None
    assert snapshot.provider == "aave_direct"
    assert snapshot.source_timestamp is not None
    assert snapshot.apy == pytest.approx(3.1, rel=1e-6)
    assert snapshot.tvl_usd == pytest.approx(1_234_567.89, rel=1e-6)


@pytest.mark.asyncio
async def test_aave_adapter_fail_safe_on_timeout(monkeypatch, caplog):
    adapter = AaveDirectAdapter(
        enabled=True,
        timeout_seconds=1,
        endpoints={"Ethereum": "https://aave.example/v3/reserves"},
        reserve_symbols={"Ethereum": {"USDC": "0xA0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"}},
    )
    candidate = _result(address="0xA0b86991c6218b36c1d19d4a2e9eb0ce3606eb48")

    monkeypatch.setattr(
        "defi_agents.freshness.adapters.aave_direct.httpx.AsyncClient",
        lambda timeout: _FakeClient(exc=httpx.TimeoutException("simulated timeout")),
    )
    caplog.set_level(logging.WARNING)

    snapshot = await adapter.fetch_snapshot(candidate)
    assert snapshot is None
    assert "Aave direct re-check request error" in caplog.text


@pytest.mark.asyncio
async def test_aave_adapter_logs_do_not_leak_secrets(monkeypatch, caplog):
    secret = "tok_secret_123"
    endpoint_with_query = "https://aave.example/v3/reserves?api_key=very-secret"
    monkeypatch.setenv("AAVE_DIRECT_API_KEY", secret)

    adapter = AaveDirectAdapter(
        enabled=True,
        timeout_seconds=1,
        endpoints={"Ethereum": endpoint_with_query},
        reserve_symbols={"Ethereum": {"USDC": "0xA0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"}},
        api_key_env="AAVE_DIRECT_API_KEY",
    )

    monkeypatch.setattr(
        "defi_agents.freshness.adapters.aave_direct.httpx.AsyncClient",
        lambda timeout: _FakeClient(response=_FakeResponse(status_code=500, body={})),
    )

    caplog.set_level(logging.WARNING)
    snapshot = await adapter.fetch_snapshot(_result(address="0xA0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"))

    assert snapshot is None
    logs = caplog.text
    assert secret not in logs
    assert "Authorization" not in logs
    assert "api_key=" not in logs
    assert endpoint_with_query not in logs


@pytest.mark.asyncio
async def test_aave_adapter_fail_safe_on_candidate_underlying_mismatch(monkeypatch, caplog):
    underlying = "0xA0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
    adapter = AaveDirectAdapter(
        enabled=True,
        timeout_seconds=1,
        endpoints={"Ethereum": "https://aave.example/v3/reserves"},
        reserve_symbols={"Ethereum": {"USDC": underlying}},
    )
    candidate = _result(address="0x1111111111111111111111111111111111111111")

    caplog.set_level(logging.WARNING)
    snapshot = await adapter.fetch_snapshot(candidate)

    assert snapshot is None
    assert "candidate/reserve mismatch" in caplog.text
