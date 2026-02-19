from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, getcontext
from math import floor, log

from .models import BandDepthResult, DataQuality, DegradationReason, PoolState, TickData
from .tick_provider import TickDataProvider, TickProviderError

getcontext().prec = 48
_TICK_BASE = Decimal("1.0001")


@dataclass(frozen=True)
class TickFreshnessCheck:
    is_valid: bool
    reason: DegradationReason | None = None


def tick_to_price(tick_index: int, token0_decimals: int = 18, token1_decimals: int = 18) -> Decimal:
    decimals_delta = Decimal(10) ** Decimal(token0_decimals - token1_decimals)
    return (_TICK_BASE ** Decimal(int(tick_index))) * decimals_delta


def price_to_tick(price: float, token0_decimals: int = 18, token1_decimals: int = 18) -> int:
    if price <= 0:
        raise ValueError("price must be positive")
    raw_price = price / float(10 ** (token0_decimals - token1_decimals))
    if raw_price <= 0:
        raise ValueError("price produced non-positive raw_price after decimal normalization")
    return int(floor(log(raw_price) / log(1.0001)))


def align_tick_down(tick: int, tick_spacing: int) -> int:
    spacing = max(1, int(tick_spacing))
    return int(floor(tick / spacing) * spacing)


def align_tick_up(tick: int, tick_spacing: int) -> int:
    spacing = max(1, int(tick_spacing))
    down = align_tick_down(tick, spacing)
    return down if down == tick else down + spacing


def validate_tick_freshness(subgraph_tick: int, rpc_tick: int | None, tick_spacing: int) -> TickFreshnessCheck:
    if rpc_tick is None:
        return TickFreshnessCheck(is_valid=False, reason=DegradationReason.RPC_UNAVAILABLE)
    if abs(int(subgraph_tick) - int(rpc_tick)) > max(1, int(tick_spacing)):
        return TickFreshnessCheck(is_valid=False, reason=DegradationReason.RPC_DRIFT_EXCEEDED)
    return TickFreshnessCheck(is_valid=True)


def calculate_band_depth_windows(
    pool_state: PoolState,
    ticks: list[TickData],
    windows_pct: tuple[float, ...] = (0.01, 0.025, 0.05),
) -> dict[float, float]:
    current_price = float(
        tick_to_price(
            pool_state.tick,
            token0_decimals=pool_state.token0_decimals,
            token1_decimals=pool_state.token1_decimals,
        )
    )
    values: dict[float, float] = {}
    for window in windows_pct:
        lower_price = current_price * (1.0 - float(window))
        upper_price = current_price * (1.0 + float(window))
        lower_tick = align_tick_down(
            price_to_tick(lower_price, pool_state.token0_decimals, pool_state.token1_decimals),
            pool_state.tick_spacing,
        )
        upper_tick = align_tick_up(
            price_to_tick(upper_price, pool_state.token0_decimals, pool_state.token1_decimals),
            pool_state.tick_spacing,
        )
        values[float(window)] = _integrate_band_depth(pool_state, ticks, lower_tick, upper_tick)
    return values


async def scan_pool_band_depth(
    provider: TickDataProvider,
    pool_address: str,
    *,
    rpc_tick: int | None = None,
    enforce_rpc_check: bool = False,
) -> BandDepthResult:
    try:
        pool_state = await provider.get_pool_state(pool_address)
    except TickProviderError as exc:
        return _degraded_result(pool_address, exc.reason)

    max_window = 0.05
    current_price = float(
        tick_to_price(
            pool_state.tick,
            token0_decimals=pool_state.token0_decimals,
            token1_decimals=pool_state.token1_decimals,
        )
    )
    lower_tick = align_tick_down(
        price_to_tick(current_price * (1.0 - max_window), pool_state.token0_decimals, pool_state.token1_decimals),
        pool_state.tick_spacing,
    )
    upper_tick = align_tick_up(
        price_to_tick(current_price * (1.0 + max_window), pool_state.token0_decimals, pool_state.token1_decimals),
        pool_state.tick_spacing,
    )

    try:
        ticks = await provider.get_pool_ticks(pool_address, lower_tick, upper_tick)
    except TickProviderError as exc:
        return _degraded_result(pool_address, exc.reason)

    if not ticks:
        return _degraded_result(pool_address, DegradationReason.TICK_COUNT_ZERO)

    if enforce_rpc_check:
        freshness = validate_tick_freshness(pool_state.tick, rpc_tick, pool_state.tick_spacing)
        if not freshness.is_valid:
            return _degraded_result(pool_address, freshness.reason or DegradationReason.RPC_UNAVAILABLE)

    band_depth = calculate_band_depth_windows(pool_state, ticks)
    return BandDepthResult(
        pool_address=pool_state.pool_address,
        band_depth_1pct_usd=float(band_depth.get(0.01, 0.0)),
        band_depth_2_5pct_usd=float(band_depth.get(0.025, 0.0)),
        band_depth_5pct_usd=float(band_depth.get(0.05, 0.0)),
        data_quality=DataQuality.OK,
    )


def _degraded_result(pool_address: str, reason: DegradationReason) -> BandDepthResult:
    return BandDepthResult(
        pool_address=pool_address,
        data_quality=DataQuality.DEGRADED,
        degradation_reason=reason,
    )


def _integrate_band_depth(pool_state: PoolState, ticks: list[TickData], lower_tick: int, upper_tick: int) -> float:
    if upper_tick <= lower_tick:
        return 0.0
    tick_map = {item.tick_index: item.liquidity_net for item in ticks}
    tick_keys = sorted(tick_map.keys())

    active_liquidity = _liquidity_at_tick(pool_state, tick_keys, tick_map, lower_tick)
    boundaries = [lower_tick]
    boundaries.extend(t for t in tick_keys if lower_tick < t < upper_tick)
    boundaries.append(upper_tick)
    boundaries = sorted(set(boundaries))
    if len(boundaries) < 2:
        return 0.0

    depth_usd = 0.0
    for idx in range(len(boundaries) - 1):
        left_tick = boundaries[idx]
        right_tick = boundaries[idx + 1]
        if right_tick <= left_tick:
            continue
        depth_usd += _interval_liquidity_usd_proxy(
            liquidity=max(0, active_liquidity),
            left_tick=left_tick,
            right_tick=right_tick,
            token0_decimals=pool_state.token0_decimals,
            token1_decimals=pool_state.token1_decimals,
        )
        if right_tick in tick_map:
            active_liquidity += tick_map[right_tick]

    return max(0.0, depth_usd)


def _liquidity_at_tick(
    pool_state: PoolState,
    sorted_ticks: list[int],
    tick_map: dict[int, int],
    target_tick: int,
) -> int:
    current_tick = int(pool_state.tick)
    liquidity = int(pool_state.liquidity)
    if target_tick == current_tick:
        return liquidity
    if target_tick > current_tick:
        for tick in sorted_ticks:
            if current_tick < tick <= target_tick:
                liquidity += tick_map[tick]
        return liquidity
    for tick in reversed(sorted_ticks):
        if target_tick < tick <= current_tick:
            liquidity -= tick_map[tick]
    return liquidity


def _interval_liquidity_usd_proxy(
    *,
    liquidity: int,
    left_tick: int,
    right_tick: int,
    token0_decimals: int,
    token1_decimals: int,
) -> float:
    if liquidity <= 0:
        return 0.0
    try:
        left_price = tick_to_price(left_tick, token0_decimals, token1_decimals)
        right_price = tick_to_price(right_tick, token0_decimals, token1_decimals)
        width = abs(right_price - left_price)
        return float(Decimal(liquidity) * width)
    except (OverflowError, InvalidOperation):
        return 0.0
