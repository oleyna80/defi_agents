import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.scout.config import ScoutConfig
from defi_agents.tracker.position_reader import (
    UNISWAP_V3_FACTORY_ARBITRUM,
    UNISWAP_V3_FACTORY_BASE,
    UNISWAP_V3_FACTORY_HYPEEVM,
    UNISWAP_V3_FACTORY_OPTIMISM,
    UNISWAP_V3_POSITION_MANAGER_ARBITRUM,
    UNISWAP_V3_POSITION_MANAGER_BASE,
    UNISWAP_V3_POSITION_MANAGER_HYPEEVM,
    UNISWAP_V3_POSITION_MANAGER_OPTIMISM,
)


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
    assert (
        cfg.execution.__class__.model_fields["mock_positions"].json_schema_extra
        == {"deprecated": True}
    )


def test_execution_mock_positions_retained_for_backward_compatibility():
    cfg = ScoutConfig(
        execution={
            "mock_positions": [
                {
                    "chain": "Arbitrum",
                    "position_ref": "legacy:1",
                    "current_tick": 0,
                    "lower_tick": -10,
                    "upper_tick": 10,
                }
            ]
        }
    )
    assert len(cfg.execution.mock_positions) == 1
    assert cfg.execution.mock_positions[0]["position_ref"] == "legacy:1"


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
    assert cfg.execution.mock_positions == []
    assert cfg.execution.krystal_timeout_seconds == 8.0


def test_sample_scout_config_execution_chains_have_no_placeholders():
    cfg = ScoutConfig.from_file(ROOT / "docs/memory-bank/scout_config.json")
    assert "Arbitrum" in cfg.execution.chains
    assert "Base" in cfg.execution.chains
    assert "Optimism" in cfg.execution.chains
    assert "HypeEVM" in cfg.execution.chains

    expected = {
        "Arbitrum": (
            UNISWAP_V3_FACTORY_ARBITRUM.lower(),
            UNISWAP_V3_POSITION_MANAGER_ARBITRUM.lower(),
        ),
        "Base": (
            UNISWAP_V3_FACTORY_BASE.lower(),
            UNISWAP_V3_POSITION_MANAGER_BASE.lower(),
        ),
        "Optimism": (
            UNISWAP_V3_FACTORY_OPTIMISM.lower(),
            UNISWAP_V3_POSITION_MANAGER_OPTIMISM.lower(),
        ),
        "HypeEVM": (
            UNISWAP_V3_FACTORY_HYPEEVM.lower(),
            UNISWAP_V3_POSITION_MANAGER_HYPEEVM.lower(),
        ),
    }

    for chain_name, chain_cfg in cfg.execution.chains.items():
        assert "example.invalid" not in chain_cfg.rpc_url.lower()
        exp_factory, exp_position_manager = expected[chain_name]
        assert chain_cfg.uniswap_v3.factory_proxy.lower() == exp_factory
        assert chain_cfg.uniswap_v3.position_manager_proxy.lower() == exp_position_manager


def test_execution_chains_incomplete_chain_excluded_from_active_set():
    cfg = ScoutConfig(
        execution={
            "chains": {
                "Arbitrum": {
                    "rpc_url": "https://arb.example.invalid",
                    "coingecko_platform_id": "arbitrum-one",
                    "uniswap_v3": {
                        "factory_proxy": "0x1111111111111111111111111111111111111111",
                        "position_manager_proxy": "",
                    },
                }
            }
        }
    )
    assert cfg.execution.chains == {}


def test_execution_chains_complete_chain_remains_active():
    cfg = ScoutConfig(
        execution={
            "chains": {
                "Base": {
                    "rpc_url": "https://base.example.invalid",
                    "coingecko_platform_id": "base",
                    "uniswap_v3": {
                        "factory_proxy": "0x3333333333333333333333333333333333333333",
                        "position_manager_proxy": "0x4444444444444444444444444444444444444444",
                    },
                }
            }
        }
    )
    assert "Base" in cfg.execution.chains
    assert cfg.execution.chains["Base"].rpc_url == "https://base.example.invalid"


def test_execution_chains_all_incomplete_results_in_empty_configured_chains():
    cfg = ScoutConfig(
        execution={
            "chains": {
                "Arbitrum": {
                    "rpc_url": "",
                    "coingecko_platform_id": "arbitrum-one",
                    "uniswap_v3": {
                        "factory_proxy": "0x1111111111111111111111111111111111111111",
                        "position_manager_proxy": "0x2222222222222222222222222222222222222222",
                    },
                },
                "Optimism": {
                    "rpc_url": "https://optimism.example.invalid",
                    "coingecko_platform_id": "",
                    "uniswap_v3": {
                        "factory_proxy": "0x5555555555555555555555555555555555555555",
                        "position_manager_proxy": "",
                    },
                },
            }
        }
    )
    assert cfg.execution.chains == {}
