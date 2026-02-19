"""Pit classifier — detect liquidity pits in tick data and suggest LP ranges.

Phase B (P0.5) of Tick Density Scanner spec 017.
Pure analysis: no I/O, deterministic, testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from math import floor

from .band_depth import align_tick_down, align_tick_up, tick_to_price
from .models import PitType, PoolState, TickData


@dataclass(frozen=True)
class PriceBin:
    """1% price bin with aggregated liquidity."""

    bin_index: int
    lower_price: float
    upper_price: float
    liquidity_usd: float


@dataclass(frozen=True)
class PitInfo:
    """Detected liquidity pit."""

    pit_type: PitType
    center_tick: int
    width_ticks: int
    distance_to_spot_pct: float
    depth_ratio: float  # pit liquidity / median neighbor liquidity
    whale_dependent: bool = False


@dataclass(frozen=True)
class SuggestedRange:
    """Optimal LP range aligned to tickSpacing."""

    lower_tick: int
    upper_tick: int
    lower_price: float
    upper_price: float
    width_pct: float
    rationale: str


def build_price_bins(
    pool_state: PoolState,
    ticks: list[TickData],
    bin_width_pct: float = 0.01,
) -> list[PriceBin]:
    """Aggregate tick liquidity into %-width price bins around current price.

    Steps:
      1. Compute current price from pool_state.tick
      2. Define bins from -20% to +20% around current price
      3. Walk ticks to reconstruct liquidity at each interval
      4. Accumulate USD proxy into bins
    """
    if not ticks:
        return []

    current_price = float(
        tick_to_price(
            pool_state.tick,
            token0_decimals=pool_state.token0_decimals,
            token1_decimals=pool_state.token1_decimals,
        )
    )
    if current_price <= 0:
        return []

    # Build bins from -20% to +20%
    num_bins_each_side = int(0.20 / bin_width_pct)
    bins_data: list[dict] = []
    for i in range(-num_bins_each_side, num_bins_each_side + 1):
        lower_pct = i * bin_width_pct
        upper_pct = (i + 1) * bin_width_pct
        bins_data.append({
            "bin_index": i,
            "lower_price": current_price * (1.0 + lower_pct),
            "upper_price": current_price * (1.0 + upper_pct),
            "liquidity_usd": 0.0,
        })

    # Reconstruct active liquidity via tick walking
    tick_map = {t.tick_index: t.liquidity_net for t in ticks}
    sorted_ticks = sorted(tick_map.keys())

    # Walk from pool_state to compute liquidity at each tick boundary
    active_liq = int(pool_state.liquidity)
    current_tick = int(pool_state.tick)

    # Build interval → liquidity map
    intervals: list[tuple[int, int, int]] = []  # (left_tick, right_tick, liquidity)

    # Expand sorted_ticks to include boundaries
    all_boundaries = sorted(set(sorted_ticks))
    if not all_boundaries:
        return []

    # Compute liquidity at the leftmost relevant tick
    liq = active_liq
    for t in reversed(sorted_ticks):
        if t <= current_tick:
            break
    # Re-walk from current tick outward
    # Left side: walk down from current_tick
    liq_left = active_liq
    left_intervals = []
    left_ticks = [t for t in reversed(sorted_ticks) if t <= current_tick]
    for idx, t in enumerate(left_ticks):
        next_t = left_ticks[idx + 1] if idx + 1 < len(left_ticks) else t - 1
        left_intervals.append((next_t, t, max(0, liq_left)))
        liq_left -= tick_map[t]

    # Right side: walk up from current_tick
    liq_right = active_liq
    right_ticks = [t for t in sorted_ticks if t > current_tick]
    prev = current_tick
    for t in right_ticks:
        liq_right += tick_map[t]
        intervals.append((prev, t, max(0, liq_right)))
        prev = t

    intervals.extend(left_intervals)

    # Distribute interval liquidity into bins
    for left_t, right_t, liq in intervals:
        if liq <= 0 or right_t <= left_t:
            continue
        try:
            left_price = float(
                tick_to_price(left_t, pool_state.token0_decimals, pool_state.token1_decimals)
            )
            right_price = float(
                tick_to_price(right_t, pool_state.token0_decimals, pool_state.token1_decimals)
            )
        except (OverflowError, ValueError):
            continue

        interval_usd = float(Decimal(liq) * abs(Decimal(str(right_price)) - Decimal(str(left_price))))

        for b in bins_data:
            overlap_lower = max(b["lower_price"], min(left_price, right_price))
            overlap_upper = min(b["upper_price"], max(left_price, right_price))
            if overlap_upper > overlap_lower:
                price_range = abs(right_price - left_price)
                if price_range > 0:
                    fraction = (overlap_upper - overlap_lower) / price_range
                    b["liquidity_usd"] += interval_usd * fraction

    return [
        PriceBin(
            bin_index=b["bin_index"],
            lower_price=b["lower_price"],
            upper_price=b["upper_price"],
            liquidity_usd=b["liquidity_usd"],
        )
        for b in bins_data
    ]


def find_liquidity_pits(
    bins: list[PriceBin],
    *,
    pit_threshold: float = 0.5,
    min_consecutive: int = 3,
    max_pits: int = 3,
) -> list[PitInfo]:
    """Detect liquidity pits in price bins.

    A pit = sequence of ≥min_consecutive bins where
    liquidity_usd < pit_threshold × median(all bins with nonzero liquidity).

    Returns top pits ranked by proximity to spot (bin_index=0).
    """
    if len(bins) < min_consecutive:
        return []

    # Compute median of nonzero bins
    nonzero = sorted(b.liquidity_usd for b in bins if b.liquidity_usd > 0)
    if not nonzero:
        return []
    median_liq = nonzero[len(nonzero) // 2]
    threshold = median_liq * pit_threshold

    # Find consecutive runs below threshold
    runs: list[list[PriceBin]] = []
    current_run: list[PriceBin] = []
    for b in sorted(bins, key=lambda x: x.bin_index):
        if b.liquidity_usd < threshold:
            current_run.append(b)
        else:
            if len(current_run) >= min_consecutive:
                runs.append(current_run)
            current_run = []
    if len(current_run) >= min_consecutive:
        runs.append(current_run)

    pits: list[PitInfo] = []
    for run in runs:
        center_idx = run[len(run) // 2].bin_index
        avg_liq = sum(b.liquidity_usd for b in run) / len(run) if run else 0
        depth_ratio = avg_liq / median_liq if median_liq > 0 else 0
        pits.append(
            PitInfo(
                pit_type=PitType.CONFIDENT_PIT if len(run) >= min_consecutive else PitType.NOISE_PIT,
                center_tick=center_idx,  # bin index, not tick index
                width_ticks=len(run),
                distance_to_spot_pct=abs(center_idx) * 1.0,  # each bin is ~1%
                depth_ratio=depth_ratio,
            )
        )

    # Sort by proximity to spot
    pits.sort(key=lambda p: p.distance_to_spot_pct)
    return pits[:max_pits]


def suggest_range(
    pit: PitInfo,
    pool_state: PoolState,
    bin_width_pct: float = 0.01,
) -> SuggestedRange:
    """Generate tickSpacing-aligned LP range around a pit.

    Expands the pit boundaries by 1 bin on each side, then aligns to tickSpacing.
    """
    current_price = float(
        tick_to_price(
            pool_state.tick,
            token0_decimals=pool_state.token0_decimals,
            token1_decimals=pool_state.token1_decimals,
        )
    )

    # Pit center and width in % terms
    lower_pct = (pit.center_tick - pit.width_ticks // 2 - 1) * bin_width_pct
    upper_pct = (pit.center_tick + pit.width_ticks // 2 + 1) * bin_width_pct

    lower_price = current_price * (1.0 + lower_pct)
    upper_price = current_price * (1.0 + upper_pct)

    if lower_price <= 0:
        lower_price = current_price * 0.80

    from .band_depth import price_to_tick

    lower_tick = align_tick_down(
        price_to_tick(lower_price, pool_state.token0_decimals, pool_state.token1_decimals),
        pool_state.tick_spacing,
    )
    upper_tick = align_tick_up(
        price_to_tick(upper_price, pool_state.token0_decimals, pool_state.token1_decimals),
        pool_state.tick_spacing,
    )

    width_pct = (upper_price - lower_price) / current_price * 100.0 if current_price > 0 else 0.0

    return SuggestedRange(
        lower_tick=lower_tick,
        upper_tick=upper_tick,
        lower_price=lower_price,
        upper_price=upper_price,
        width_pct=width_pct,
        rationale=f"Pit at {pit.distance_to_spot_pct:.1f}% from spot, depth_ratio={pit.depth_ratio:.2f}",
    )
