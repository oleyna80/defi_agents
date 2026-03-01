import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.scout.config import ScoutConfig


def test_hedger_defaults_safe():
    cfg = ScoutConfig()
    assert cfg.hedger.enabled is False
    assert cfg.hedger.mode == "PAPER"
    assert cfg.hedger.allow_live_mode is False
    assert cfg.hedger.connector == "none"
    assert cfg.hedger.hummingbot_base_url == "http://127.0.0.1:15888"
    assert cfg.hedger.hummingbot_api_key_env == "HUMMINGBOT_API_KEY"
    assert cfg.hedger.hummingbot_exchange == "binance_perpetual"
    assert cfg.hedger.hummingbot_market_map == {}
    assert cfg.hedger.hummingbot_health_path == "/health"
    assert cfg.hedger.hummingbot_markets_path == "/api/v1/markets"
    assert cfg.hedger.hummingbot_ticker_path == "/api/v1/ticker"
    assert cfg.hedger.mock_exposures == []
    assert cfg.hedger.default_hedge_ratio == 1.0
    assert cfg.hedger.policy.kill_switch is False
    assert cfg.hedger.policy.max_notional_usd_per_order == 2_000.0


def test_hedger_live_mode_requires_explicit_allow():
    with pytest.raises(ValidationError):
        ScoutConfig(
            hedger={
                "enabled": True,
                "mode": "LIVE",
                "allow_live_mode": False,
            }
        )


def test_hedger_live_mode_allowed_with_flag():
    cfg = ScoutConfig(
        hedger={
            "enabled": True,
            "mode": "LIVE",
            "allow_live_mode": True,
            "connector": "hummingbot",
        }
    )
    assert cfg.hedger.mode == "LIVE"
    assert cfg.hedger.allow_live_mode is True
    assert cfg.hedger.connector == "hummingbot"


def test_sample_scout_config_includes_hedger_block():
    cfg = ScoutConfig.from_file(ROOT / "docs/memory-bank/scout_config.json")
    assert isinstance(cfg.hedger.enabled, bool)
    assert cfg.hedger.mode in {"PAPER", "SHADOW", "LIVE"}
    assert cfg.hedger.connector in {"none", "hummingbot"}
    assert cfg.hedger.policy.max_daily_notional_usd >= 0.0
    assert isinstance(cfg.hedger.mock_exposures, list)
