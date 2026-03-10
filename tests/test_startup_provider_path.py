import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import main as sentinel_main
from defi_agents.scout.config import ScoutConfig


def test_build_l3_provider_uses_deepseek_when_ready(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture):
    class _DeepSeekReady:
        provider_name = "deepseek"

    monkeypatch.setattr(sentinel_main, "DeepSeekProvider", _DeepSeekReady)
    monkeypatch.setattr(sentinel_main, "should_allow_mock_fallback", lambda: False)

    cfg = ScoutConfig()
    with caplog.at_level("INFO"):
        provider = sentinel_main._build_l3_provider(cfg)

    assert getattr(provider, "provider_name", "") == "deepseek"
    assert "reason=PRIMARY_DEEPSEEK_READY" in caplog.text


def test_build_l3_provider_uses_env_mock_fallback(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture):
    class _DeepSeekMissing:
        def __init__(self) -> None:
            raise ValueError("DEEPSEEK_API_KEY is not set")

    class _MockProvider:
        provider_name = "mock"

    monkeypatch.setattr(sentinel_main, "DeepSeekProvider", _DeepSeekMissing)
    monkeypatch.setattr(sentinel_main, "MockAIService", _MockProvider)
    monkeypatch.setattr(sentinel_main, "should_allow_mock_fallback", lambda: True)

    cfg = ScoutConfig()
    with caplog.at_level("INFO"):
        provider = sentinel_main._build_l3_provider(cfg)

    assert getattr(provider, "provider_name", "") == "mock"
    assert "reason=MOCK_FALLBACK_ENV_ALLOW_MOCK_FALLBACK" in caplog.text


def test_build_l3_provider_uses_shadow_fallback_without_env_flag(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    class _DeepSeekMissing:
        def __init__(self) -> None:
            raise ValueError("DEEPSEEK_API_KEY is not set")

    class _MockProvider:
        provider_name = "mock"

    monkeypatch.setattr(sentinel_main, "DeepSeekProvider", _DeepSeekMissing)
    monkeypatch.setattr(sentinel_main, "MockAIService", _MockProvider)
    monkeypatch.setattr(sentinel_main, "should_allow_mock_fallback", lambda: False)

    cfg = ScoutConfig(
        execution={"mode": "SHADOW"},
        reporting={"telegram_shadow_mode_enabled": False},
    )
    with caplog.at_level("INFO"):
        provider = sentinel_main._build_l3_provider(cfg)

    assert getattr(provider, "provider_name", "") == "mock"
    assert "reason=MOCK_FALLBACK_SHADOW_DEEPSEEK_API_KEY_MISSING" in caplog.text


def test_build_l3_provider_reporting_shadow_flag_only_is_not_startup_shadow(
    monkeypatch: pytest.MonkeyPatch,
):
    class _DeepSeekMissing:
        def __init__(self) -> None:
            raise ValueError("DEEPSEEK_API_KEY is not set")

    monkeypatch.setattr(sentinel_main, "DeepSeekProvider", _DeepSeekMissing)
    monkeypatch.setattr(sentinel_main, "should_allow_mock_fallback", lambda: False)

    cfg = ScoutConfig(
        execution={"mode": "PAPER"},
        reporting={"telegram_shadow_mode_enabled": True},
    )
    with pytest.raises(RuntimeError, match="Production AI Init Failure"):
        sentinel_main._build_l3_provider(cfg)


def test_build_l3_provider_fails_closed_outside_shadow(monkeypatch: pytest.MonkeyPatch):
    class _DeepSeekBroken:
        def __init__(self) -> None:
            raise RuntimeError("network unavailable")

    monkeypatch.setattr(sentinel_main, "DeepSeekProvider", _DeepSeekBroken)
    monkeypatch.setattr(sentinel_main, "should_allow_mock_fallback", lambda: False)

    cfg = ScoutConfig(reporting={"telegram_shadow_mode_enabled": False})
    with pytest.raises(RuntimeError, match="Production AI Init Failure"):
        sentinel_main._build_l3_provider(cfg)
