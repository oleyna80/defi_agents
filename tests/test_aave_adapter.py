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
    address: str = "0xA0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
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
    def __init__(self, responder) -> None:  # noqa: ANN001
        self._responder = responder

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def post(self, url: str, *args, **kwargs):  # noqa: ANN002, ANN003
        return self._responder(url, *args, **kwargs)


def _adapter(*, endpoints: dict[str, str | list[str]]) -> AaveDirectAdapter:
    return AaveDirectAdapter(
        enabled=True,
        timeout_seconds=5,
        endpoints=endpoints,
        chain_ids={"Ethereum": 1},
        reserve_symbols={"Ethereum": {"USDC": "0xA0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"}},
    )


def test_aave_adapter_supports_flag_and_shape_filters():
    endpoints = {"Ethereum": "https://api.v3.aave.com/graphql"}
    chain_ids = {"Ethereum": 1}
    symbols = {"Ethereum": {"USDC": "0xA0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"}}

    off_adapter = AaveDirectAdapter(
        enabled=False,
        endpoints=endpoints,
        chain_ids=chain_ids,
        reserve_symbols=symbols,
    )
    assert off_adapter.supports(_result()) is False

    adapter = AaveDirectAdapter(
        enabled=True,
        endpoints=endpoints,
        chain_ids=chain_ids,
        reserve_symbols=symbols,
    )
    assert adapter.supports(_result(project="aave-v3")) is True
    assert adapter.supports(_result(project="spark", symbol="USDC/DAI")) is True
    assert adapter.supports(_result(project="uniswap-v3")) is False
    assert adapter.supports(_result(chain="Arbitrum")) is False
    assert adapter.supports(_result(symbol="", project="aave-v3")) is False
    assert adapter.supports(_result(address="not-an-evm-address", project="aave-v3")) is False


@pytest.mark.asyncio
async def test_aave_adapter_fetch_snapshot_success(monkeypatch):
    endpoint = "https://api.v3.aave.com/graphql"
    adapter = _adapter(endpoints={"Ethereum": endpoint})
    candidate = _result()

    body = {
        "data": {
            "markets": [
                {
                    "reserves": [
                        {
                            "underlyingToken": {
                                "symbol": "USDC",
                                "address": "0xA0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
                            },
                            "isFrozen": False,
                            "isPaused": False,
                            "size": {"usd": "1234567.89"},
                            "supplyInfo": {"apy": {"value": "0.031"}},
                        }
                    ]
                }
            ]
        }
    }

    def responder(url, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        assert url == endpoint
        payload = kwargs["json"]
        assert payload["variables"]["chainIds"] == [1]
        assert "markets(" in payload["query"]
        return _FakeResponse(status_code=200, body=body)

    monkeypatch.setattr(
        "defi_agents.freshness.adapters.aave_direct.httpx.AsyncClient",
        lambda timeout: _FakeClient(responder),
    )

    snapshot = await adapter.fetch_snapshot(candidate)
    assert snapshot is not None
    assert snapshot.provider == "aave_direct"
    assert snapshot.source_timestamp is not None
    assert snapshot.apy == pytest.approx(3.1, rel=1e-6)
    assert snapshot.tvl_usd == pytest.approx(1_234_567.89, rel=1e-6)
    assert candidate.metadata["aave_recheck_checked"] == "1"
    assert candidate.metadata["aave_recheck_outcome"] == "ok"


@pytest.mark.asyncio
async def test_aave_adapter_fallback_endpoint_success(monkeypatch):
    primary = "https://primary.example/graphql"
    fallback = "https://fallback.example/graphql"
    adapter = _adapter(endpoints={"Ethereum": [primary, fallback]})
    candidate = _result()

    body = {
        "data": {
            "markets": [
                {
                    "reserves": [
                        {
                            "underlyingToken": {
                                "symbol": "USDC",
                                "address": "0xA0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
                            },
                            "isFrozen": False,
                            "isPaused": False,
                            "size": {"usd": "2000"},
                            "supplyInfo": {"apy": {"value": "0.020"}},
                        }
                    ]
                }
            ]
        }
    }
    calls = {"primary": 0, "fallback": 0}

    def responder(url, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        payload = kwargs["json"]
        assert payload["variables"]["chainIds"] == [1]
        if url == primary:
            calls["primary"] += 1
            return _FakeResponse(status_code=500, body={})
        calls["fallback"] += 1
        return _FakeResponse(status_code=200, body=body)

    monkeypatch.setattr(
        "defi_agents.freshness.adapters.aave_direct.httpx.AsyncClient",
        lambda timeout: _FakeClient(responder),
    )

    snapshot = await adapter.fetch_snapshot(candidate)
    assert snapshot is not None
    assert calls["primary"] == 1
    assert calls["fallback"] == 1
    assert candidate.metadata["aave_recheck_outcome"] == "ok"


@pytest.mark.asyncio
async def test_aave_adapter_fail_safe_on_timeout(monkeypatch, caplog):
    adapter = _adapter(endpoints={"Ethereum": "https://api.v3.aave.com/graphql"})
    candidate = _result()

    def responder(url, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        raise httpx.TimeoutException("simulated timeout")

    monkeypatch.setattr(
        "defi_agents.freshness.adapters.aave_direct.httpx.AsyncClient",
        lambda timeout: _FakeClient(responder),
    )
    caplog.set_level(logging.WARNING)

    snapshot = await adapter.fetch_snapshot(candidate)
    assert snapshot is None
    assert "request timeout" in caplog.text
    assert candidate.metadata["aave_recheck_checked"] == "1"
    assert candidate.metadata["aave_recheck_outcome"] == "timeout"


@pytest.mark.asyncio
async def test_aave_adapter_logs_do_not_leak_secrets(monkeypatch, caplog):
    secret = "tok_secret_123"
    endpoint_with_query = "https://api.v3.aave.com/graphql?api_key=very-secret"
    monkeypatch.setenv("AAVE_DIRECT_API_KEY", secret)

    adapter = AaveDirectAdapter(
        enabled=True,
        timeout_seconds=1,
        endpoints={"Ethereum": endpoint_with_query},
        chain_ids={"Ethereum": 1},
        reserve_symbols={"Ethereum": {"USDC": "0xA0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"}},
        api_key_env="AAVE_DIRECT_API_KEY",
    )

    def responder(url, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        return _FakeResponse(status_code=500, body={})

    monkeypatch.setattr(
        "defi_agents.freshness.adapters.aave_direct.httpx.AsyncClient",
        lambda timeout: _FakeClient(responder),
    )

    caplog.set_level(logging.WARNING)
    snapshot = await adapter.fetch_snapshot(_result())

    assert snapshot is None
    logs = caplog.text
    assert secret not in logs
    assert "Authorization" not in logs
    assert "api_key=" not in logs
    assert endpoint_with_query not in logs


@pytest.mark.asyncio
async def test_aave_adapter_addr_mismatch_is_fail_safe(caplog):
    adapter = _adapter(endpoints={"Ethereum": "https://api.v3.aave.com/graphql"})
    candidate = _result(address="0x1111111111111111111111111111111111111111")

    caplog.set_level(logging.WARNING)
    snapshot = await adapter.fetch_snapshot(candidate)

    assert snapshot is None
    assert "candidate/reserve mismatch" in caplog.text
    assert candidate.metadata["aave_recheck_checked"] == "1"
    assert candidate.metadata["aave_recheck_outcome"] == "addr_mismatch"


@pytest.mark.asyncio
async def test_aave_adapter_schema_mismatch_outcome(monkeypatch):
    adapter = _adapter(endpoints={"Ethereum": "https://api.v3.aave.com/graphql"})
    candidate = _result()

    def responder(url, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        return _FakeResponse(status_code=200, body={"data": {"foo": []}})

    monkeypatch.setattr(
        "defi_agents.freshness.adapters.aave_direct.httpx.AsyncClient",
        lambda timeout: _FakeClient(responder),
    )

    snapshot = await adapter.fetch_snapshot(candidate)
    assert snapshot is None
    assert candidate.metadata["aave_recheck_checked"] == "1"
    assert candidate.metadata["aave_recheck_outcome"] == "schema_mismatch"
