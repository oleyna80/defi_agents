import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.hedger.models import (
    HedgeCounters,
    HedgeDecision,
    HedgeExposure,
    HedgeIntent,
)


def test_hedge_exposure_contract():
    exposure = HedgeExposure(
        chain="Base",
        position_ref="pos-1",
        symbol="ETH",
        delta_usd=1250.5,
        mark_price_usd=2800.0,
        snapshot_ts=1_747_032_000,
        freshness_age_seconds=45,
        metadata={"source": "position_state"},
    )
    assert exposure.chain == "Base"
    assert exposure.symbol == "ETH"
    assert exposure.delta_usd == 1250.5
    assert exposure.metadata["source"] == "position_state"


def test_hedge_exposure_rejects_blank_symbol():
    with pytest.raises(ValidationError):
        HedgeExposure(chain="Base", position_ref="pos-1", symbol=" ")


def test_hedge_intent_contract():
    intent = HedgeIntent(
        intent_id="hedge-1",
        action="HEDGE",
        side="SHORT",
        chain="Base",
        symbol="ETH",
        target_notional_usd=1000.0,
        reason_codes=["DELTA_ABOVE_THRESHOLD"],
    )
    assert intent.action == "HEDGE"
    assert intent.side == "SHORT"
    assert intent.target_notional_usd == 1000.0
    assert intent.reason_codes == ["DELTA_ABOVE_THRESHOLD"]


def test_hedge_intent_rejects_negative_notional():
    with pytest.raises(ValidationError):
        HedgeIntent(
            intent_id="hedge-2",
            action="HEDGE",
            side="SHORT",
            chain="Base",
            symbol="ETH",
            target_notional_usd=-1.0,
        )


def test_hedge_counters_and_decision_defaults():
    counters = HedgeCounters()
    assert counters.exposures_seen == 0
    assert counters.intents_hedge == 0
    assert counters.connector_errors == 0

    decision = HedgeDecision(allowed=False, reason_codes=["KILL_SWITCH_ENABLED"])
    assert decision.allowed is False
    assert decision.reason_codes == ["KILL_SWITCH_ENABLED"]

