import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.hedger.calculator import HedgeCalculator
from defi_agents.hedger.models import HedgeExposure
from defi_agents.scout.config import HedgerConfig


def _calculator(**kwargs) -> HedgeCalculator:
    cfg = HedgerConfig(**kwargs)
    return HedgeCalculator(cfg)


def _exposure(
    *,
    delta_usd: float = 2_000.0,
    symbol: str = "ETH",
    freshness_age_seconds: int = 10,
    mark_price_usd: float = 2_800.0,
) -> HedgeExposure:
    return HedgeExposure(
        chain="Base",
        position_ref="pos-1",
        symbol=symbol,
        delta_usd=delta_usd,
        freshness_age_seconds=freshness_age_seconds,
        mark_price_usd=mark_price_usd,
        snapshot_ts=1_700_000_000,
    )


def test_calculator_emits_short_hedge_for_positive_delta():
    calc = _calculator(default_hedge_ratio=0.5)
    intent = calc.evaluate_exposure(_exposure(delta_usd=2_000.0), now_ts=1_700_000_100)
    assert intent.action == "HEDGE"
    assert intent.side == "SHORT"
    assert intent.target_notional_usd == pytest.approx(1_000.0)
    assert "DELTA_HEDGE_REQUIRED" in intent.reason_codes


def test_calculator_emits_long_hedge_for_negative_delta():
    calc = _calculator(default_hedge_ratio=0.5)
    intent = calc.evaluate_exposure(_exposure(delta_usd=-1_200.0), now_ts=1_700_000_100)
    assert intent.action == "HEDGE"
    assert intent.side == "LONG"
    assert intent.target_notional_usd == pytest.approx(600.0)


def test_calculator_holds_when_notional_below_threshold():
    calc = _calculator(default_hedge_ratio=0.2, policy={"min_rebalance_notional_usd": 500.0})
    intent = calc.evaluate_exposure(_exposure(delta_usd=2_000.0), now_ts=1_700_000_100)
    assert intent.action == "HOLD"
    assert intent.side == "NONE"
    assert intent.reason_codes == ["DELTA_BELOW_MIN_NOTIONAL"]


def test_calculator_holds_when_symbol_cooldown_active():
    calc = _calculator(per_symbol_cooldown_seconds=3600)
    first = calc.evaluate_exposure(_exposure(delta_usd=2_000.0, symbol="ETH"), now_ts=1_700_000_100)
    second = calc.evaluate_exposure(_exposure(delta_usd=2_000.0, symbol="ETH"), now_ts=1_700_000_200)
    assert first.action == "HEDGE"
    assert second.action == "HOLD"
    assert second.reason_codes == ["COOLDOWN_ACTIVE"]


def test_calculator_skips_on_stale_data():
    calc = _calculator(exposure_max_age_seconds=60)
    intent = calc.evaluate_exposure(_exposure(freshness_age_seconds=120), now_ts=1_700_000_100)
    assert intent.action == "SKIP"
    assert "EXPOSURE_STALE" in intent.reason_codes


def test_calculator_skips_on_missing_mark_price():
    calc = _calculator()
    intent = calc.evaluate_exposure(_exposure(mark_price_usd=0.0), now_ts=1_700_000_100)
    assert intent.action == "SKIP"
    assert "MARK_PRICE_MISSING" in intent.reason_codes


def test_calculator_skips_on_kill_switch():
    calc = _calculator(policy={"kill_switch": True})
    intent = calc.evaluate_exposure(_exposure(), now_ts=1_700_000_100)
    assert intent.action == "SKIP"
    assert "KILL_SWITCH_ENABLED" in intent.reason_codes


def test_calculator_skips_when_order_notional_exceeds_cap():
    calc = _calculator(policy={"max_notional_usd_per_order": 500.0})
    intent = calc.evaluate_exposure(_exposure(delta_usd=2_000.0), now_ts=1_700_000_100)
    assert intent.action == "SKIP"
    assert "MAX_NOTIONAL_PER_ORDER_EXCEEDED" in intent.reason_codes


def test_calculator_skips_when_daily_notional_cap_reached():
    calc = _calculator(
        default_hedge_ratio=1.0,
        per_symbol_cooldown_seconds=0,
        policy={"max_daily_notional_usd": 2_500.0},
    )
    first = calc.evaluate_exposure(_exposure(delta_usd=1_500.0, symbol="ETH"), now_ts=1_700_000_100)
    second = calc.evaluate_exposure(_exposure(delta_usd=1_500.0, symbol="BTC"), now_ts=1_700_000_120)
    assert first.action == "HEDGE"
    assert second.action == "SKIP"
    assert "MAX_DAILY_NOTIONAL_REACHED" in second.reason_codes


def test_calculator_daily_budget_resets_next_day():
    calc = _calculator(
        default_hedge_ratio=1.0,
        per_symbol_cooldown_seconds=0,
        policy={"max_daily_notional_usd": 2_000.0},
    )
    day1 = calc.evaluate_exposure(_exposure(delta_usd=1_800.0, symbol="ETH"), now_ts=1_700_000_000)
    blocked_same_day = calc.evaluate_exposure(_exposure(delta_usd=1_800.0, symbol="BTC"), now_ts=1_700_000_100)
    day2 = calc.evaluate_exposure(_exposure(delta_usd=1_800.0, symbol="BTC"), now_ts=1_700_086_500)
    assert day1.action == "HEDGE"
    assert blocked_same_day.action == "SKIP"
    assert day2.action == "HEDGE"


def test_calculator_batch_returns_reason_counters():
    calc = _calculator(
        per_symbol_cooldown_seconds=0,
        policy={"max_notional_usd_per_order": 900.0, "min_rebalance_notional_usd": 400.0},
    )
    exposures = [
        _exposure(delta_usd=300.0, symbol="ETH"),   # HOLD (below min)
        _exposure(delta_usd=1000.0, symbol="BTC"),  # SKIP policy (max per order)
        _exposure(delta_usd=600.0, symbol="ARB"),   # HEDGE
        _exposure(delta_usd=500.0, symbol="OP", freshness_age_seconds=99999),  # SKIP data
    ]
    intents, counters = calc.evaluate_batch(exposures, now_ts=1_700_000_100)
    assert len(intents) == 4
    assert counters.exposures_seen == 4
    assert counters.intents_hold == 1
    assert counters.intents_skip == 2
    assert counters.intents_hedge == 1
    assert counters.skipped_by_policy == 1
    assert counters.skipped_by_data == 1
