"""Tests for volatility module + vol-adjusted suggest_range."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from defi_agents.lp.volatility import (
    VolEstimate,
    compute_historical_vol,
    estimate_vol,
    vol_adjusted_range_width,
)
from defi_agents.lp.pit_classifier import PitInfo, suggest_range
from defi_agents.lp.models import PitType, PoolState


# ─── compute_historical_vol ────────────────────────────────────────


def test_vol_stable_prices_near_zero() -> None:
    """Identical prices → vol ≈ 0."""
    prices = [100.0] * 10
    vol = compute_historical_vol(prices)
    assert vol is not None
    assert vol < 1e-10


def test_vol_known_returns() -> None:
    """Manually computed: daily returns of +1% and -1% alternating."""
    # Prices: 100, 101, 100, 101, 100, 101
    prices = [100.0, 101.0, 100.0, 101.0, 100.0, 101.0]
    vol = compute_historical_vol(prices)
    assert vol is not None
    # Expected: std of log(1.01), log(100/101), log(1.01), ...
    # log(1.01) ≈ 0.00995, log(100/101) ≈ -0.00995
    assert 0.008 < vol < 0.012


def test_vol_insufficient_data() -> None:
    """Less than 3 prices → None."""
    assert compute_historical_vol([100.0, 101.0]) is None
    assert compute_historical_vol([]) is None


def test_vol_with_zero_prices_filtered() -> None:
    """Zero/negative prices are filtered before computation."""
    prices = [100.0, 0.0, 101.0, 102.0, 103.0]
    vol = compute_historical_vol(prices)
    assert vol is not None
    assert vol > 0


# ─── vol_adjusted_range_width ───────────────────────────────────────


def test_range_width_scales_with_vol() -> None:
    """Higher vol → wider range."""
    narrow = vol_adjusted_range_width(0.01, holding_days=7.0)
    wide = vol_adjusted_range_width(0.05, holding_days=7.0)
    assert wide > narrow


def test_range_width_scales_with_holding() -> None:
    """Longer holding → wider range (√t scaling)."""
    short = vol_adjusted_range_width(0.02, holding_days=1.0)
    long = vol_adjusted_range_width(0.02, holding_days=30.0)
    assert long > short
    # √30/√1 ≈ 5.48x
    assert 5.0 < long / short < 6.0


def test_range_width_respects_floor() -> None:
    """Very low vol should hit min_width_pct floor."""
    width = vol_adjusted_range_width(0.0001, holding_days=1.0, min_width_pct=0.005)
    assert width == 0.005


def test_range_width_respects_cap() -> None:
    """Extreme vol should hit max_width_pct cap."""
    width = vol_adjusted_range_width(1.0, holding_days=365.0, max_width_pct=0.50)
    assert width == 0.50


def test_range_width_zero_vol() -> None:
    """Zero vol → returns min_width_pct."""
    width = vol_adjusted_range_width(0.0, min_width_pct=0.005)
    assert width == 0.005


# ─── estimate_vol ───────────────────────────────────────────────────


def test_estimate_vol_full_pipeline() -> None:
    """End-to-end: prices → VolEstimate with all fields populated."""
    # ETH-like daily prices with ~3% daily vol
    prices = [2500.0, 2575.0, 2520.0, 2600.0, 2480.0, 2550.0, 2510.0, 2590.0]
    result = estimate_vol(prices, holding_days=7.0)

    assert result is not None
    assert isinstance(result, VolEstimate)
    assert result.daily_vol > 0
    assert result.annual_vol > result.daily_vol
    assert abs(result.annual_vol - result.daily_vol * math.sqrt(365)) < 1e-10
    assert result.sample_days == 7
    assert result.range_half_width_pct > 0


def test_estimate_vol_returns_none_for_short_data() -> None:
    """Less than 3 prices → None."""
    assert estimate_vol([100.0, 101.0]) is None


# ─── suggest_range with vol ─────────────────────────────────────────


def _make_pool_state(tick: int = 0) -> PoolState:
    return PoolState(
        pool_address="0x" + "a" * 40,
        tick=tick,
        liquidity=1_000_000,
        sqrt_price_x96=2**96,
        fee_tier=3000,
        tick_spacing=60,
        token0_decimals=18,
        token1_decimals=18,
    )


def _make_pit(center: int = 0, width: int = 5) -> PitInfo:
    return PitInfo(
        pit_type=PitType.CONFIDENT_PIT,
        center_tick=center,
        width_ticks=width,
        distance_to_spot_pct=abs(center) * 1.0,
        depth_ratio=0.3,
    )


def test_suggest_range_without_vol_uses_pit_width() -> None:
    """Without daily_vol, suggest_range uses pit boundaries."""
    pool = _make_pool_state()
    pit = _make_pit(center=0, width=5)
    result = suggest_range(pit, pool)
    assert "Pit at" in result.rationale
    assert result.width_pct > 0


def test_suggest_range_with_vol_uses_adjusted_width() -> None:
    """With daily_vol, suggest_range uses vol-adjusted width."""
    pool = _make_pool_state()
    pit = _make_pit(center=0, width=5)
    result = suggest_range(pit, pool, daily_vol=0.03, holding_days=7.0)
    assert "Vol-adjusted" in result.rationale
    assert "σ_daily=0.0300" in result.rationale
    assert result.width_pct > 0


def test_suggest_range_vol_wider_than_pit() -> None:
    """High vol should produce wider range than pit-based fallback."""
    pool = _make_pool_state()
    pit = _make_pit(center=0, width=3)  # narrow pit

    pit_range = suggest_range(pit, pool)
    vol_range = suggest_range(pit, pool, daily_vol=0.05, holding_days=14.0)

    # Vol-adjusted should generally be wider for high vol
    assert vol_range.width_pct > pit_range.width_pct


def test_suggest_range_stable_pair_narrow() -> None:
    """Stablecoin-like low vol → narrow range width."""
    pool = _make_pool_state()
    pit = _make_pit(center=0, width=5)
    result = suggest_range(pit, pool, daily_vol=0.001, holding_days=7.0)
    # For σ=0.1%, holding=7d: half_width = 2×0.001×√7 ≈ 0.53%
    assert result.width_pct < 5.0  # very narrow
