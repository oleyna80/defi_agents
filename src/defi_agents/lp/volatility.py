"""Historical volatility calculator for LP range width optimization.

Pure math — no I/O. Feed it daily prices, get back σ and optimal range width.

Key formula:
    range_half_width = k × σ_daily × √holding_period_days
    where k = confidence multiplier (default 2.0 ≈ ~95% of price moves stay in range)
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class VolEstimate:
    """Volatility estimate with metadata."""

    daily_vol: float  # σ daily (log returns std dev)
    annual_vol: float  # σ × √365
    sample_days: int  # how many days of data were used
    range_half_width_pct: float  # recommended ±% for LP range


def compute_historical_vol(prices: list[float]) -> float | None:
    """Compute daily log-return volatility from a list of daily prices.

    Args:
        prices: Daily closing prices, oldest first. Minimum 3 data points.

    Returns:
        Daily volatility (σ) as a decimal (e.g. 0.02 = 2%), or None if insufficient data.
    """
    if len(prices) < 3:
        return None

    # Filter out zeros/negatives
    valid = [p for p in prices if p > 0]
    if len(valid) < 3:
        return None

    log_returns = [math.log(valid[i] / valid[i - 1]) for i in range(1, len(valid))]

    n = len(log_returns)
    if n < 2:
        return None

    mean = sum(log_returns) / n
    variance = sum((r - mean) ** 2 for r in log_returns) / (n - 1)  # sample variance

    return math.sqrt(variance)


def vol_adjusted_range_width(
    daily_vol: float,
    *,
    holding_days: float = 7.0,
    confidence_k: float = 2.0,
    min_width_pct: float = 0.005,  # 0.5% minimum
    max_width_pct: float = 0.50,  # 50% maximum
) -> float:
    """Calculate optimal LP range half-width based on volatility.

    Formula: half_width = k × σ_daily × √holding_days

    Args:
        daily_vol: Daily volatility (σ) as decimal.
        holding_days: Expected holding period in days.
        confidence_k: Multiplier for confidence interval (2.0 ≈ 95%).
        min_width_pct: Floor for range half-width.
        max_width_pct: Cap for range half-width.

    Returns:
        Range half-width as decimal (e.g. 0.05 = ±5%).
    """
    if daily_vol <= 0:
        return min_width_pct

    half_width = confidence_k * daily_vol * math.sqrt(holding_days)
    return max(min_width_pct, min(half_width, max_width_pct))


def estimate_vol(
    prices: list[float],
    *,
    holding_days: float = 7.0,
    confidence_k: float = 2.0,
) -> VolEstimate | None:
    """One-shot: prices → vol estimate + recommended range width.

    Args:
        prices: Daily prices (oldest first), minimum 3 points.
        holding_days: Expected LP position holding period.
        confidence_k: Confidence multiplier for range width.

    Returns:
        VolEstimate with all computed values, or None if data is insufficient.
    """
    daily_vol = compute_historical_vol(prices)
    if daily_vol is None:
        return None

    half_width = vol_adjusted_range_width(
        daily_vol,
        holding_days=holding_days,
        confidence_k=confidence_k,
    )

    return VolEstimate(
        daily_vol=daily_vol,
        annual_vol=daily_vol * math.sqrt(365),
        sample_days=len(prices) - 1,
        range_half_width_pct=half_width,
    )
