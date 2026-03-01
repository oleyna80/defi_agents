import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.scout.config import ScoutConfig


def test_execution_defaults_safe():
    cfg = ScoutConfig()
    assert cfg.execution.enabled is False
    assert cfg.execution.mode == "PAPER"
    assert cfg.execution.allow_live_mode is False
    assert cfg.execution.compound_min_fees_usd == 5.0
    assert cfg.execution.rebalance_min_range_utilization == 0.15
    assert cfg.execution.rebalance_edge_decay_bps == 250
    assert cfg.execution.mock_positions == []
    assert cfg.execution.krystal_timeout_seconds == 8.0
    assert cfg.execution.v3utils_enabled is False
    assert cfg.execution.v3utils_contracts_by_chain == {}
    assert cfg.execution.v3utils_router_by_chain == {}
    assert cfg.execution.v3utils_slippage_bps_default == 50
    assert cfg.execution.native_live_timeout_seconds == 12.0
    assert cfg.execution.native_live_receipt_timeout_seconds == 45.0
    assert cfg.execution.native_live_receipt_poll_seconds == 1.5
    assert cfg.execution.native_live_rpc_env_by_chain["Base"] == "BASE_RPC_URL"
    assert cfg.execution.policy.kill_switch is False


def test_execution_live_mode_requires_explicit_allow():
    with pytest.raises(ValidationError):
        ScoutConfig(
            execution={
                "enabled": True,
                "mode": "LIVE",
            }
        )


def test_execution_live_mode_allowed_when_flag_enabled():
    cfg = ScoutConfig(
        execution={
            "enabled": True,
            "mode": "LIVE",
            "allow_live_mode": True,
        }
    )
    assert cfg.execution.mode == "LIVE"
    assert cfg.execution.allow_live_mode is True


def test_execution_krystal_primary_requires_krystal_enabled():
    with pytest.raises(ValidationError):
        ScoutConfig(
            execution={
                "enabled": True,
                "mode": "PAPER",
                "primary_adapter": "krystal",
                "krystal_enabled": False,
            }
        )


def test_execution_krystal_primary_with_feature_flag():
    cfg = ScoutConfig(
        execution={
            "enabled": True,
            "mode": "PAPER",
            "primary_adapter": "krystal",
            "krystal_enabled": True,
        }
    )
    assert cfg.execution.primary_adapter == "krystal"
    assert cfg.execution.krystal_enabled is True


def test_execution_v3utils_primary_requires_flag():
    with pytest.raises(ValidationError):
        ScoutConfig(
            execution={
                "enabled": True,
                "mode": "PAPER",
                "primary_adapter": "v3utils",
                "v3utils_enabled": False,
            }
        )


def test_execution_v3utils_primary_with_feature_flag():
    cfg = ScoutConfig(
        execution={
            "enabled": True,
            "mode": "PAPER",
            "primary_adapter": "v3utils",
            "v3utils_enabled": True,
            "v3utils_contracts_by_chain": {"Base": "0x1111111111111111111111111111111111111111"},
        }
    )
    assert cfg.execution.primary_adapter == "v3utils"
    assert cfg.execution.v3utils_enabled is True


def test_sample_scout_config_includes_execution_block():
    cfg = ScoutConfig.from_file(ROOT / "docs/memory-bank/scout_config.json")
    assert isinstance(cfg.execution.enabled, bool)
    assert cfg.execution.mode in {"PAPER", "SHADOW", "LIVE"}
    assert cfg.execution.primary_adapter == "uniswap_v3_simulate"
    assert cfg.execution.rebalance_edge_decay_bps == 250
    assert isinstance(cfg.execution.mock_positions, list)
    assert cfg.execution.krystal_timeout_seconds == 8.0
