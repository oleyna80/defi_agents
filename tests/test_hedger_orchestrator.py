import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.hedger.calculator import HedgeCalculator
from defi_agents.hedger.models import HedgeExposure, HedgeSimulationResult
from defi_agents.hedger.orchestrator import HedgerOrchestrator
from defi_agents.scout.config import HedgerConfig


def _run(coro):
    return asyncio.run(coro)


def _calculator(**kwargs) -> HedgeCalculator:
    return HedgeCalculator(
        HedgerConfig(
            per_symbol_cooldown_seconds=0,
            **kwargs,
        )
    )


def _exposure(delta_usd: float = 1000.0, symbol: str = "ETH") -> HedgeExposure:
    return HedgeExposure(
        chain="Base",
        position_ref="pos-1",
        symbol=symbol,
        delta_usd=delta_usd,
        mark_price_usd=2800.0,
        freshness_age_seconds=10,
        snapshot_ts=1700000000,
    )


class _OkConnector:
    async def probe_health(self, symbol: str):  # pragma: no cover
        raise AssertionError("probe_health should not be called directly by orchestrator")

    async def simulate_order(self, intent, *, max_slippage_bps: int):
        return HedgeSimulationResult(ok=True, expected_fill_price=2800.0, estimated_quantity=0.5)


class _FailConnector:
    async def probe_health(self, symbol: str):  # pragma: no cover
        raise AssertionError("probe_health should not be called directly by orchestrator")

    async def simulate_order(self, intent, *, max_slippage_bps: int):
        return HedgeSimulationResult(ok=False, reason_codes=["CONNECTOR_NOT_READY", "AUTH_FAILED"])


class _RaiseConnector:
    async def probe_health(self, symbol: str):  # pragma: no cover
        raise AssertionError("probe_health should not be called directly by orchestrator")

    async def simulate_order(self, intent, *, max_slippage_bps: int):
        raise RuntimeError("boom")


def test_orchestrator_paper_mode_keeps_sim_zero():
    orchestrator = HedgerOrchestrator(
        mode="PAPER",
        calculator=_calculator(),
        connector=None,
    )
    report = _run(orchestrator.run_exposures([_exposure()], now_ts=1700000100))
    assert report.mode == "PAPER"
    assert report.counters.exposures_seen == 1
    assert report.counters.intents_hedge == 1
    assert report.sim_ok == 0
    assert report.sim_fail == 0
    assert report.counters.connector_errors == 0


def test_orchestrator_shadow_mode_without_connector_marks_failures():
    orchestrator = HedgerOrchestrator(
        mode="SHADOW",
        calculator=_calculator(),
        connector=None,
    )
    report = _run(orchestrator.run_exposures([_exposure()], now_ts=1700000100))
    assert report.counters.intents_hedge == 1
    assert report.sim_ok == 0
    assert report.sim_fail == 1
    assert report.counters.connector_errors == 1
    assert report.sim_fail_reason_counts.get("CONNECTOR_UNCONFIGURED") == 1


def test_orchestrator_shadow_mode_records_sim_ok():
    orchestrator = HedgerOrchestrator(
        mode="SHADOW",
        calculator=_calculator(),
        connector=_OkConnector(),
    )
    report = _run(orchestrator.run_exposures([_exposure()], now_ts=1700000100))
    assert report.counters.intents_hedge == 1
    assert report.sim_ok == 1
    assert report.sim_fail == 0
    assert report.counters.connector_errors == 0


def test_orchestrator_shadow_mode_records_connector_fail_reasons():
    orchestrator = HedgerOrchestrator(
        mode="SHADOW",
        calculator=_calculator(),
        connector=_FailConnector(),
    )
    report = _run(orchestrator.run_exposures([_exposure()], now_ts=1700000100))
    assert report.sim_ok == 0
    assert report.sim_fail == 1
    assert report.counters.connector_errors == 1
    assert report.sim_fail_reason_counts.get("CONNECTOR_NOT_READY") == 1
    assert report.connector_reason_counts.get("AUTH_FAILED") == 1


def test_orchestrator_shadow_mode_records_connector_exception():
    orchestrator = HedgerOrchestrator(
        mode="SHADOW",
        calculator=_calculator(),
        connector=_RaiseConnector(),
    )
    report = _run(orchestrator.run_exposures([_exposure()], now_ts=1700000100))
    assert report.sim_ok == 0
    assert report.sim_fail == 1
    assert report.counters.connector_errors == 1
    assert report.sim_fail_reason_counts.get("CONNECTOR_EXCEPTION") == 1
    assert report.connector_reason_counts.get("CONNECTOR_EXCEPTION") == 1

