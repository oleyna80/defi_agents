import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from unittest.mock import Mock, patch
from src.defi_agents.strategy_sim.models import (
    StrategyId,
    SimStatus,
    SimulationResult,
    SimulationCounters,
)
from src.defi_agents.strategy_sim.catalog import get_strategy_catalog, get_strategy_by_id
from src.defi_agents.strategy_sim.engine import StrategySimEngine
from src.defi_agents.scout.models import ScoutCandidate, ScoutResult
from src.defi_agents.scout.config import ScoutConfig


def test_strategy_catalog_v1():
    catalog = get_strategy_catalog()
    assert len(catalog) == 5
    ids = {strat.id for strat in catalog}
    expected = {
        StrategyId.LIQUID_STAKING_CORE,
        StrategyId.SINGLE_SIDED_LENDING,
        StrategyId.YIELD_BEARING_STABLE_CORE,
        StrategyId.STABLE_STABLE_FEE_CAPTURE,
        StrategyId.CLMM_RANGE_HARVEST,
    }
    assert ids == expected
    # Check each has required fields
    for strat in catalog:
        assert strat.name
        assert isinstance(strat.supported_pair_classes, list)
        assert isinstance(strat.required_data, list)


def test_get_strategy_by_id():
    strat = get_strategy_by_id(StrategyId.STABLE_STABLE_FEE_CAPTURE)
    assert strat.id == StrategyId.STABLE_STABLE_FEE_CAPTURE
    assert "USD_STABLE_STABLE" in strat.supported_pair_classes
    with pytest.raises(ValueError):
        get_strategy_by_id("unknown")


def test_simulation_result_to_metadata():
    result = SimulationResult(
        status=SimStatus.PARTIAL,
        best_strategy=StrategyId.CLMM_RANGE_HARVEST,
        fit_score=75,
        exp_net_apy_min=12.5,
        exp_net_apy_max=18.2,
        risk_score=40,
        constraints_hit=["TVL_BELOW_1M"],
        required_data_missing=["volume_24h_usd", "fees_24h_usd"],
        candidates_compact="ETH/USDC:Base:15.2%",
    )
    meta = result.to_metadata_dict()
    assert meta["sim_status"] == "PARTIAL"
    assert meta["sim_best_strategy"] == "clmm_range_harvest"
    assert meta["sim_fit_score"] == "75"
    assert meta["sim_exp_net_apy_min"] == "12.50"
    assert meta["sim_exp_net_apy_max"] == "18.20"
    assert meta["sim_risk_score"] == "40"
    assert meta["sim_constraints_hit"] == "TVL_BELOW_1M"
    assert meta["sim_required_data_missing"] == "volume_24h_usd,fees_24h_usd"
    assert meta["sim_candidates_compact"] == "ETH/USDC:Base:15.2%"


def test_simulation_counters_log():
    counters = SimulationCounters(
        simulated_count=10,
        ok_count=5,
        partial_count=3,
        unsupported_count=2,
        watchlist_by_missing_data_count=1,
        downgraded_to_watchlist_count=2,
        best_strategy_distribution={"liquid_staking_core": 3, "stable_stable_fee_capture": 2},
    )
    line = counters.to_log_line()
    assert "simulated=10" in line
    assert "ok=5" in line
    assert "partial=3" in line
    assert "unsupported=2" in line
    assert "watchlist_missing=1" in line
    assert "downgraded=2" in line
    assert "best_strategy_dist=liquid_staking_core:3,stable_stable_fee_capture:2" in line


@pytest.fixture
def mock_config():
    config = Mock(spec=ScoutConfig)
    # Add strategy_sim sub-mock
    strategy_sim_mock = Mock()
    strategy_sim_mock.enabled = True
    strategy_sim_mock.max_candidates = 20
    strategy_sim_mock.supported_tiers = ["T1", "T2"]
    strategy_sim_mock.allow_unsupported_as_watchlist = True
    strategy_sim_mock.risk_thresholds_by_profile = {"micro": 30, "standard": 50, "whale": 70}
    strategy_sim_mock.min_data_completeness_pct = 80.0
    config.strategy_sim = strategy_sim_mock
    # Add other sub-mocks
    risk_policy_mock = Mock()
    risk_policy_mock.t3_min_apy_premium = 3.0
    config.risk_policy = risk_policy_mock
    investor_profile_mock = Mock()
    investor_profile_mock.risk_profile = "standard"
    config.investor_profile = investor_profile_mock
    config.chain_id_map = {"Ethereum": 1, "Base": 8453}
    return config


@pytest.fixture
def sample_candidate():
    return ScoutCandidate(
        pool="123",
        symbol="USDC-USDT",
        chain="Ethereum",
        project="Uniswap V3",
        apy=5.2,
        apy_base=5.0,
        apy_reward=0.2,
        tvlUsd=10_000_000,
        chain_id=1,
    )


@pytest.fixture
def sample_result(sample_candidate):
    return ScoutResult(
        candidate=sample_candidate,
        net_apy=5.2,
        net_profit_usd=120.0,
        score=25.0,
        priority="LOW_VOLATILITY",
        metadata={
            "pair_currency_class": "USD_STABLE_STABLE",
            "stable_tier": "T1",
            "fx_exposure": "false",
            "freshness_status": "FRESH",
        },
    )


def test_engine_init(mock_config):
    engine = StrategySimEngine(mock_config)
    assert engine.config == mock_config
    assert len(engine.strategy_catalog) == 5


def test_simulate_one_evm_unsupported(mock_config, sample_result):
    engine = StrategySimEngine(mock_config)
    sample_result.candidate.chain = "Solana"
    sample_result.candidate.chain_id = None
    result = engine.simulate_one(sample_result)
    assert result.status == SimStatus.UNSUPPORTED
    assert "NON_EVM" in result.constraints_hit


def test_simulate_one_partial_missing_data(mock_config, sample_result):
    engine = StrategySimEngine(mock_config)
    # Mock _match_best_strategy to return CLMM_RANGE_HARVEST (requires volume/fees)
    with patch.object(engine, '_match_best_strategy', return_value=StrategyId.CLMM_RANGE_HARVEST):
        with patch.object(engine, '_check_missing_data', return_value=["volume_24h_usd"]):
            result = engine.simulate_one(sample_result)
            assert result.status == SimStatus.PARTIAL
            assert result.required_data_missing == ["volume_24h_usd"]
            assert result.best_strategy == StrategyId.CLMM_RANGE_HARVEST


def test_simulate_one_ok(mock_config, sample_result):
    engine = StrategySimEngine(mock_config)
    # Mock internal methods to produce OK result
    with patch.object(engine, '_match_best_strategy', return_value=StrategyId.STABLE_STABLE_FEE_CAPTURE):
        with patch.object(engine, '_check_missing_data', return_value=[]):
            with patch.object(engine, '_compute_fit_score', return_value=85):
                with patch.object(engine, '_compute_risk_score', return_value=30):
                    with patch.object(engine, '_compute_expected_net_apy_range', return_value=(4.5, 6.0)):
                        with patch.object(engine, '_detect_constraints_hit', return_value=[]):
                            result = engine.simulate_one(sample_result)
                            assert result.status == SimStatus.OK
                            assert result.fit_score == 85
                            assert result.risk_score == 30
                            assert result.exp_net_apy_min == 4.5
                            assert result.exp_net_apy_max == 6.0


def test_apply_policy_downgrade_partial(mock_config):
    engine = StrategySimEngine(mock_config)
    results = []
    for i in range(3):
        cand = Mock(spec=ScoutCandidate)
        res = ScoutResult(
            candidate=cand,
            net_apy=10.0,
            net_profit_usd=100.0,
            score=20.0,
            priority="LOW_VOLATILITY",
            metadata={
                "sim_status": SimStatus.PARTIAL.value if i == 0 else SimStatus.OK.value,
                "sim_risk_score": "25",
                "report_group": "ACTIONABLE",
            },
        )
        results.append(res)
    counters = SimulationCounters()
    updated = engine.apply_policy(results, counters)
    # First result should be downgraded to WATCHLIST
    assert results[0].metadata["report_group"] == "WATCHLIST"
    assert results[1].metadata["report_group"] == "ACTIONABLE"  # unchanged
    assert updated.downgraded_to_watchlist_count == 1
    assert updated.watchlist_by_missing_data_count == 1


def test_apply_policy_downgrade_risk_exceed(mock_config):
    engine = StrategySimEngine(mock_config)
    results = []
    for i in range(2):
        cand = Mock(spec=ScoutCandidate)
        res = ScoutResult(
            candidate=cand,
            net_apy=10.0,
            net_profit_usd=100.0,
            score=20.0,
            priority="LOW_VOLATILITY",
            metadata={
                "sim_status": SimStatus.OK.value,
                "sim_risk_score": "60",  # > threshold 50 for standard profile
                "report_group": "ACTIONABLE",
            },
        )
        results.append(res)
    counters = SimulationCounters()
    updated = engine.apply_policy(results, counters)
    # Both should be downgraded
    assert results[0].metadata["report_group"] == "WATCHLIST"
    assert results[1].metadata["report_group"] == "WATCHLIST"
    assert updated.downgraded_to_watchlist_count == 2


def test_apply_policy_no_downgrade(mock_config):
    engine = StrategySimEngine(mock_config)
    cand = Mock(spec=ScoutCandidate)
    res = ScoutResult(
        candidate=cand,
        net_apy=10.0,
        net_profit_usd=100.0,
        score=20.0,
        priority="LOW_VOLATILITY",
        metadata={
            "sim_status": SimStatus.OK.value,
            "sim_risk_score": "40",  # below threshold
            "report_group": "ACTIONABLE",
        },
    )
    counters = SimulationCounters()
    updated = engine.apply_policy([res], counters)
    assert res.metadata["report_group"] == "ACTIONABLE"
    assert updated.downgraded_to_watchlist_count == 0


def test_integration_wiring(mock_config, sample_result):
    # Ensure engine can be instantiated and simulate without crash
    engine = StrategySimEngine(mock_config)
    result = engine.simulate_one(sample_result)
    assert result is not None
    assert isinstance(result, SimulationResult)