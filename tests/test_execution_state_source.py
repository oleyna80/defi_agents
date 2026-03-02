import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import main as sentinel_main
from defi_agents.execution.models import PositionState
from defi_agents.scout.config import ScoutConfig


def _run(coro):
    return asyncio.run(coro)


def _real_state() -> PositionState:
    return PositionState(
        chain="Arbitrum",
        position_ref="uni-v3:1",
        current_tick=50,
        lower_tick=-100,
        upper_tick=100,
        data_freshness_at=1_700_000_000,
    )


def test_execution_state_source_no_wallet_does_not_fallback_to_mock(monkeypatch: pytest.MonkeyPatch):
    cfg = ScoutConfig()
    monkeypatch.delenv("WALLET_ADDRESS", raising=False)
    monkeypatch.setenv("RPC_URL_ARBITRUM", "https://arb.example-rpc.local")

    states = _run(sentinel_main._load_execution_states(cfg))

    assert states == []


def test_execution_state_source_reader_error_does_not_fallback_to_mock(monkeypatch: pytest.MonkeyPatch):
    cfg = ScoutConfig()
    monkeypatch.setenv("WALLET_ADDRESS", "0x1111111111111111111111111111111111111111")
    monkeypatch.setenv("RPC_URL_ARBITRUM", "https://arb.example-rpc.local")

    class _ReaderFail:
        def __init__(self, *, rpc_url: str):
            self.rpc_url = rpc_url

        async def load_active_position_states(self, _wallet_address: str):
            raise RuntimeError("reader_down")

    monkeypatch.setattr(sentinel_main, "ArbitrumUniswapV3PositionReader", _ReaderFail)

    states = _run(sentinel_main._load_execution_states(cfg))

    assert states == []


def test_execution_state_source_returns_real_reader_states(monkeypatch: pytest.MonkeyPatch):
    cfg = ScoutConfig()
    monkeypatch.setenv("WALLET_ADDRESS", "0x1111111111111111111111111111111111111111")
    monkeypatch.setenv("RPC_URL_ARBITRUM", "https://arb.example-rpc.local")

    expected = _real_state()

    class _ReaderOk:
        def __init__(self, *, rpc_url: str):
            self.rpc_url = rpc_url

        async def load_active_position_states(self, _wallet_address: str):
            return [expected]

    monkeypatch.setattr(sentinel_main, "ArbitrumUniswapV3PositionReader", _ReaderOk)

    states = _run(sentinel_main._load_execution_states(cfg))

    assert len(states) == 1
    assert states[0].position_ref == "uni-v3:1"
    assert states[0].stale is False
