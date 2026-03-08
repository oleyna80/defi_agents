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


def _chain_cfg(*, coingecko_platform_id: str) -> dict[str, object]:
    return {
        "rpc_url": "https://rpc.example.local",
        "coingecko_platform_id": coingecko_platform_id,
        "uniswap_v3": {
            "factory_proxy": "0x" + ("1" * 40),
            "position_manager_proxy": "0x" + ("2" * 40),
        },
    }


def _config_with_chains() -> ScoutConfig:
    return ScoutConfig(
        execution={
            "chains": {
                "Arbitrum": _chain_cfg(coingecko_platform_id="arbitrum-one"),
                "Base": _chain_cfg(coingecko_platform_id="base"),
                "Optimism": _chain_cfg(coingecko_platform_id="optimism"),
            }
        }
    )


def _real_state(
    *,
    chain: str = "Arbitrum",
    position_ref: str = "uni-v3:1",
    token_id: int = 1,
    metadata: dict | None = None,
) -> PositionState:
    merged_metadata = {"token_id": token_id}
    if metadata:
        merged_metadata.update(metadata)
    return PositionState(
        chain=chain,
        position_ref=position_ref,
        current_tick=50,
        lower_tick=-100,
        upper_tick=100,
        data_freshness_at=1_700_000_000,
        metadata=merged_metadata,
    )


def test_execution_state_source_no_wallet_does_not_fallback_to_mock(monkeypatch: pytest.MonkeyPatch):
    cfg = _config_with_chains()
    monkeypatch.delenv("WALLET_ADDRESS", raising=False)

    states = _run(sentinel_main._load_execution_states(cfg))

    assert states == []


def test_execution_state_source_all_chains_fail_raises_controlled_error(
    monkeypatch: pytest.MonkeyPatch,
):
    cfg = _config_with_chains()
    monkeypatch.setenv("WALLET_ADDRESS", "0x1111111111111111111111111111111111111111")

    class _ReaderFail:
        async def load_active_position_states(self, _wallet_address: str):
            raise RuntimeError("reader_down")

    def _build_reader(**_kwargs):
        return _ReaderFail()

    monkeypatch.setattr(sentinel_main, "_build_execution_position_reader", _build_reader)

    with pytest.raises(RuntimeError, match="POSITION_READER_ALL_CHAINS_FAILED"):
        _run(sentinel_main._load_execution_states(cfg))


def test_execution_state_source_aggregates_multichain_states_in_deterministic_order(
    monkeypatch: pytest.MonkeyPatch,
):
    cfg = _config_with_chains()
    monkeypatch.setenv("WALLET_ADDRESS", "0x1111111111111111111111111111111111111111")

    readers_by_chain = {
        "Arbitrum": [
            _real_state(chain="Arbitrum", position_ref="uni-v3:5", token_id=5),
            _real_state(chain="Arbitrum", position_ref="uni-v3:2", token_id=2),
        ],
        "Base": [
            _real_state(chain="Base", position_ref="uni-v3:11", token_id=11),
            _real_state(chain="Base", position_ref="uni-v3:3", token_id=3),
        ],
        "Optimism": [
            _real_state(chain="Optimism", position_ref="uni-v3:7", token_id=7),
        ],
    }
    build_order: list[str] = []

    class _ReaderOk:
        def __init__(self, chain_name: str):
            self._chain_name = chain_name

        async def load_active_position_states(self, _wallet_address: str):
            return readers_by_chain[self._chain_name]

    def _build_reader(*, chain_name: str, chain_cfg):
        del chain_cfg
        build_order.append(chain_name)
        return _ReaderOk(chain_name)

    monkeypatch.setattr(sentinel_main, "_build_execution_position_reader", _build_reader)

    states = _run(sentinel_main._load_execution_states(cfg))

    assert build_order == ["Arbitrum", "Base", "Optimism"]
    assert [(s.chain, s.position_ref) for s in states] == [
        ("Arbitrum", "uni-v3:2"),
        ("Arbitrum", "uni-v3:5"),
        ("Base", "uni-v3:3"),
        ("Base", "uni-v3:11"),
        ("Optimism", "uni-v3:7"),
    ]


def test_execution_state_source_continues_when_one_chain_fails(
    monkeypatch: pytest.MonkeyPatch,
):
    cfg = _config_with_chains()
    monkeypatch.setenv("WALLET_ADDRESS", "0x1111111111111111111111111111111111111111")

    class _ReaderOk:
        async def load_active_position_states(self, _wallet_address: str):
            return [_real_state(chain="Base", position_ref="uni-v3:10", token_id=10)]

    class _ReaderFail:
        async def load_active_position_states(self, _wallet_address: str):
            raise RuntimeError("rpc_down")

    def _build_reader(*, chain_name: str, chain_cfg):
        del chain_cfg
        if chain_name == "Arbitrum":
            return _ReaderFail()
        return _ReaderOk()

    monkeypatch.setattr(sentinel_main, "_build_execution_position_reader", _build_reader)

    states = _run(sentinel_main._load_execution_states(cfg))

    assert len(states) == 2
    assert all(state.chain in {"Base", "Optimism"} for state in states)


def test_execution_state_source_keeps_entry_baseline_missing_reason_code(
    monkeypatch: pytest.MonkeyPatch,
):
    cfg = _config_with_chains()
    monkeypatch.setenv("WALLET_ADDRESS", "0x1111111111111111111111111111111111111111")

    class _ReaderOk:
        async def load_active_position_states(self, _wallet_address: str):
            return [
                _real_state(
                    chain="Arbitrum",
                    position_ref="uni-v3:1",
                    token_id=1,
                    metadata={
                        "pnl_reason_codes": ["ENTRY_BASELINE_MISSING"],
                        "hodl_reason_codes": ["ENTRY_BASELINE_MISSING"],
                    },
                )
            ]

    def _build_reader(**_kwargs):
        return _ReaderOk()

    monkeypatch.setattr(sentinel_main, "_build_execution_position_reader", _build_reader)

    states = _run(sentinel_main._load_execution_states(cfg))

    assert len(states) == 3
    assert all(
        state.metadata.get("pnl_reason_codes") == ["ENTRY_BASELINE_MISSING"]
        for state in states
    )
    assert all(
        state.metadata.get("hodl_reason_codes") == ["ENTRY_BASELINE_MISSING"]
        for state in states
    )


def test_execution_chain_rpc_env_key_normalizes_hypeevm() -> None:
    assert sentinel_main._execution_chain_rpc_env_key("HypeEVM") == "RPC_URL_HYPEEVM"


def test_build_execution_position_reader_uses_env_rpc_override(
    monkeypatch: pytest.MonkeyPatch,
):
    cfg = _config_with_chains()
    chain_cfg = cfg.execution.chains["Optimism"]
    monkeypatch.setenv("RPC_URL_OPTIMISM", "https://rpc.override.local")
    captured: dict[str, object] = {}

    class _CaptureReader:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(sentinel_main, "BaseUniswapV3PositionReader", _CaptureReader)

    sentinel_main._build_execution_position_reader(
        chain_name="Optimism",
        chain_cfg=chain_cfg,
    )

    assert captured["rpc_url"] == "https://rpc.override.local"


def test_build_execution_position_reader_falls_back_to_config_rpc(
    monkeypatch: pytest.MonkeyPatch,
):
    cfg = _config_with_chains()
    chain_cfg = cfg.execution.chains["Base"]
    monkeypatch.delenv("RPC_URL_BASE", raising=False)
    captured: dict[str, object] = {}

    class _CaptureReader:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(sentinel_main, "BaseUniswapV3PositionReader", _CaptureReader)

    sentinel_main._build_execution_position_reader(
        chain_name="Base",
        chain_cfg=chain_cfg,
    )

    assert captured["rpc_url"] == chain_cfg.rpc_url
