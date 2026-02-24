import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import main as sentinel_main
from defi_agents.execution.adapters import (
    KrystalExecutionAdapter,
    NativeLiveExecutionAdapter,
    NativeUniswapV3Adapter,
    V3UtilsExecutionAdapter,
)
from defi_agents.scout.config import ScoutConfig


def test_live_mode_rejects_non_live_capable_native_adapter():
    cfg = ScoutConfig(
        execution={
            "enabled": True,
            "mode": "LIVE",
            "allow_live_mode": True,
            "primary_adapter": "native_uniswap_v3",
            "fallback_adapter": "native_uniswap_v3",
        }
    )
    with pytest.raises(RuntimeError, match="LIVE_EXECUTION_ADAPTER_UNAVAILABLE"):
        sentinel_main._build_execution_adapter(cfg)


def test_live_mode_selects_krystal_when_api_key_present(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("KRYSTAL_CLOUD_API_KEY", "test-key")
    cfg = ScoutConfig(
        execution={
            "enabled": True,
            "mode": "LIVE",
            "allow_live_mode": True,
            "primary_adapter": "krystal",
            "fallback_adapter": "native_uniswap_v3",
            "krystal_enabled": True,
            "krystal_api_key_env": "KRYSTAL_CLOUD_API_KEY",
        }
    )
    with pytest.raises(RuntimeError, match="LIVE_EXECUTION_ADAPTER_UNAVAILABLE"):
        sentinel_main._build_execution_adapter(cfg)


def test_live_mode_selects_native_live_adapter_when_rpc_present(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BASE_RPC_URL", "https://base.example-rpc.local")
    cfg = ScoutConfig(
        execution={
            "enabled": True,
            "mode": "LIVE",
            "allow_live_mode": True,
            "primary_adapter": "native_uniswap_v3_live",
            "fallback_adapter": "native_uniswap_v3",
            "native_live_rpc_env_by_chain": {"Base": "BASE_RPC_URL"},
        }
    )
    adapter = sentinel_main._build_execution_adapter(cfg)
    assert isinstance(adapter, NativeLiveExecutionAdapter)


def test_live_mode_native_live_fails_when_rpc_missing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("BASE_RPC_URL", raising=False)
    cfg = ScoutConfig(
        execution={
            "enabled": True,
            "mode": "LIVE",
            "allow_live_mode": True,
            "primary_adapter": "native_uniswap_v3_live",
            "fallback_adapter": "native_uniswap_v3",
            "native_live_rpc_env_by_chain": {"Base": "BASE_RPC_URL"},
        }
    )
    with pytest.raises(RuntimeError, match="LIVE_EXECUTION_ADAPTER_UNAVAILABLE"):
        sentinel_main._build_execution_adapter(cfg)


def test_live_mode_selects_v3utils_adapter_when_enabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BASE_RPC_URL", "https://base.example-rpc.local")
    cfg = ScoutConfig(
        execution={
            "enabled": True,
            "mode": "LIVE",
            "allow_live_mode": True,
            "primary_adapter": "v3utils",
            "fallback_adapter": "native_uniswap_v3",
            "v3utils_enabled": True,
            "v3utils_contracts_by_chain": {"Base": "0x1111111111111111111111111111111111111111"},
            "native_live_rpc_env_by_chain": {"Base": "BASE_RPC_URL"},
        }
    )
    adapter = sentinel_main._build_execution_adapter(cfg)
    assert isinstance(adapter, V3UtilsExecutionAdapter)


def test_live_mode_v3utils_fails_when_contracts_missing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BASE_RPC_URL", "https://base.example-rpc.local")
    cfg = ScoutConfig(
        execution={
            "enabled": True,
            "mode": "LIVE",
            "allow_live_mode": True,
            "primary_adapter": "v3utils",
            "fallback_adapter": "native_uniswap_v3",
            "v3utils_enabled": True,
            "v3utils_contracts_by_chain": {},
            "native_live_rpc_env_by_chain": {"Base": "BASE_RPC_URL"},
        }
    )
    with pytest.raises(RuntimeError, match="LIVE_EXECUTION_ADAPTER_UNAVAILABLE"):
        sentinel_main._build_execution_adapter(cfg)


def test_shadow_mode_accepts_krystal_primary_when_key_present(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("KRYSTAL_CLOUD_API_KEY", "test-key")
    cfg = ScoutConfig(
        execution={
            "enabled": True,
            "mode": "SHADOW",
            "primary_adapter": "krystal",
            "fallback_adapter": "native_uniswap_v3",
            "krystal_enabled": True,
            "krystal_api_key_env": "KRYSTAL_CLOUD_API_KEY",
        }
    )
    adapter = sentinel_main._build_execution_adapter(cfg)
    if hasattr(adapter, "primary"):
        assert isinstance(adapter.primary, KrystalExecutionAdapter)
    else:
        assert isinstance(adapter, KrystalExecutionAdapter)


def test_shadow_mode_falls_back_to_native_when_krystal_unavailable(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("KRYSTAL_CLOUD_API_KEY", raising=False)
    cfg = ScoutConfig(
        execution={
            "enabled": True,
            "mode": "SHADOW",
            "primary_adapter": "krystal",
            "fallback_adapter": "native_uniswap_v3",
            "krystal_enabled": True,
            "krystal_api_key_env": "KRYSTAL_CLOUD_API_KEY",
        }
    )
    adapter = sentinel_main._build_execution_adapter(cfg)
    assert isinstance(adapter, NativeUniswapV3Adapter)


def test_live_mode_fails_when_krystal_key_missing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("KRYSTAL_CLOUD_API_KEY", raising=False)
    cfg = ScoutConfig(
        execution={
            "enabled": True,
            "mode": "LIVE",
            "allow_live_mode": True,
            "primary_adapter": "krystal",
            "fallback_adapter": "native_uniswap_v3",
            "krystal_enabled": True,
            "krystal_api_key_env": "KRYSTAL_CLOUD_API_KEY",
        }
    )
    with pytest.raises(RuntimeError, match="LIVE_EXECUTION_ADAPTER_UNAVAILABLE"):
        sentinel_main._build_execution_adapter(cfg)
