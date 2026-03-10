import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from unittest.mock import Mock, patch
from src.defi_agents.strategy_sim.models import (
    StrategyId,
    SimStatus,
    SimulationResult,
    SimulationCounters,
)
from src.defi_agents.strategy_sim.catalog import (
    get_strategy_catalog,
    get_strategy_by_id,
)
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
        best_strategy_distribution={
            "liquid_staking_core": 3,
            "stable_stable_fee_capture": 2,
        },
    )
    line = counters.to_log_line()
    assert "simulated=10" in line
    assert "ok=5" in line
    assert "partial=3" in line
    assert "unsupported=2" in line
    assert "watchlist_missing=1" in line
    assert "downgraded=2" in line
    assert (
        "best_strategy_dist=liquid_staking_core:3,stable_stable_fee_capture:2" in line
    )


@pytest.fixture
def mock_config():
    config = Mock(spec=ScoutConfig)
    # Add strategy_sim sub-mock
    strategy_sim_mock = Mock()
    strategy_sim_mock.enabled = True
    strategy_sim_mock.max_candidates = 20
    strategy_sim_mock.supported_tiers = ["T1", "T2"]
    strategy_sim_mock.allow_unsupported_as_watchlist = True
    strategy_sim_mock.risk_thresholds_by_profile = {
        "micro": 30,
        "standard": 50,
        "whale": 70,
    }
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
    with patch.object(
        engine, "_match_best_strategy", return_value=StrategyId.CLMM_RANGE_HARVEST
    ):
        with patch.object(
            engine, "_check_missing_data", return_value=["volume_24h_usd"]
        ):
            result = engine.simulate_one(sample_result)
            assert result.status == SimStatus.PARTIAL
            assert result.required_data_missing == ["volume_24h_usd"]
            assert result.best_strategy == StrategyId.CLMM_RANGE_HARVEST


def test_simulate_one_ok(mock_config, sample_result):
    engine = StrategySimEngine(mock_config)
    # Mock internal methods to produce OK result
    with patch.object(
        engine,
        "_match_best_strategy",
        return_value=StrategyId.STABLE_STABLE_FEE_CAPTURE,
    ):
        with patch.object(engine, "_check_missing_data", return_value=[]):
            with patch.object(engine, "_compute_fit_score", return_value=85):
                with patch.object(engine, "_compute_risk_score", return_value=30):
                    with patch.object(
                        engine,
                        "_compute_expected_net_apy_range",
                        return_value=(4.5, 6.0),
                    ):
                        with patch.object(
                            engine, "_detect_constraints_hit", return_value=[]
                        ):
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
    assert results[0].metadata["watchlist_reason"] == "SIM_STATUS_PARTIAL"
    assert results[0].metadata["sim_policy_reason"] == "SIM_STATUS_PARTIAL"
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
    assert results[0].metadata["watchlist_reason"] == "SIM_RISK_ABOVE_PROFILE"
    assert results[1].metadata["watchlist_reason"] == "SIM_RISK_ABOVE_PROFILE"
    assert results[0].metadata["sim_policy_reason"] == "SIM_RISK_ABOVE_PROFILE"
    assert results[1].metadata["sim_policy_reason"] == "SIM_RISK_ABOVE_PROFILE"
    assert updated.downgraded_to_watchlist_count == 2


def test_apply_policy_sets_machine_reason_for_unsupported_status(mock_config):
    engine = StrategySimEngine(mock_config)
    cand = Mock(spec=ScoutCandidate)
    res = ScoutResult(
        candidate=cand,
        net_apy=10.0,
        net_profit_usd=100.0,
        score=20.0,
        priority="LOW_VOLATILITY",
        metadata={
            "sim_status": SimStatus.UNSUPPORTED.value,
            "sim_risk_score": "0",
            "report_group": "ACTIONABLE",
        },
    )

    counters = SimulationCounters()
    updated = engine.apply_policy([res], counters)

    assert res.metadata["report_group"] == "WATCHLIST"
    assert res.metadata["watchlist_reason"] == "SIM_STATUS_UNSUPPORTED"
    assert res.metadata["sim_policy_reason"] == "SIM_STATUS_UNSUPPORTED"
    assert updated.downgraded_to_watchlist_count == 1
    assert updated.watchlist_by_missing_data_count == 0


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


def _candidate_for_required_data(**overrides):
    payload = {
        "pool": "pool-required",
        "symbol": "ETH-USDC",
        "chain": "Ethereum",
        "project": "Uniswap V3",
        "apy": 6.0,
        "apyBase": 4.0,
        "apyReward": 2.0,
        "tvlUsd": 5_000_000,
        "chain_id": 1,
        "volumeUsd1d": 250_000,
        "totalSupplyUsd": 2_000_000,
        "totalBorrowUsd": 1_000_000,
        "apyBase7d": 3.5,
        "sigma": 0.25,
    }
    payload.update(overrides)
    return ScoutCandidate(**payload)


def test_has_fees_positive_cases(mock_config):
    engine = StrategySimEngine(mock_config)

    by_fees_metadata = _candidate_for_required_data(apyBase=0.0)
    assert engine._has_fees(by_fees_metadata, {"fees_24h_usd": "123.45"}) is True

    by_fee_apr = _candidate_for_required_data(apyBase=0.0)
    assert engine._has_fees(by_fee_apr, {"fee_apr": "0.15"}) is True

    by_candidate_proxy = _candidate_for_required_data(apyBase=2.1)
    assert engine._has_fees(by_candidate_proxy, {}) is True


@pytest.mark.parametrize(
    "metadata,apy_base",
    [
        ({}, 0.0),
        ({"fees_24h_usd": "abc"}, 0.0),
        ({"fees_24h_usd": "-10"}, 0.0),
        ({"fee_apr": "nan"}, 0.0),
    ],
)
def test_has_fees_negative_cases(mock_config, metadata, apy_base):
    engine = StrategySimEngine(mock_config)
    candidate = _candidate_for_required_data(apyBase=apy_base)
    assert engine._has_fees(candidate, metadata) is False


def test_has_utilization_positive_cases(mock_config):
    engine = StrategySimEngine(mock_config)

    assert (
        engine._has_utilization(_candidate_for_required_data(), {"utilization": "0.62"})
        is True
    )
    assert (
        engine._has_utilization(
            _candidate_for_required_data(
                totalSupplyUsd=500_000, totalBorrowUsd=250_000
            ),
            {},
        )
        is True
    )


@pytest.mark.parametrize(
    "candidate_kwargs,metadata",
    [
        ({}, {"utilization": "oops"}),
        ({}, {"utilization": "1.2"}),
        ({"totalSupplyUsd": 0, "totalBorrowUsd": 10}, {}),
        ({"totalSupplyUsd": 100, "totalBorrowUsd": -1}, {}),
        ({"totalSupplyUsd": 100, "totalBorrowUsd": 120}, {}),
    ],
)
def test_has_utilization_negative_cases(mock_config, candidate_kwargs, metadata):
    engine = StrategySimEngine(mock_config)
    candidate = _candidate_for_required_data(**candidate_kwargs)
    assert engine._has_utilization(candidate, metadata) is False


def test_has_supply_rate_positive_cases(mock_config):
    engine = StrategySimEngine(mock_config)
    assert (
        engine._has_supply_rate(
            _candidate_for_required_data(apyBase=0.0), {"supply_rate": "2.5"}
        )
        is True
    )
    assert (
        engine._has_supply_rate(_candidate_for_required_data(apyBase=1.7), {}) is True
    )


@pytest.mark.parametrize(
    "metadata,apy_base",
    [
        ({"supply_rate": "n/a"}, 0.0),
        ({"supply_rate": "-0.5"}, 0.0),
        ({}, 0.0),
    ],
)
def test_has_supply_rate_negative_cases(mock_config, metadata, apy_base):
    engine = StrategySimEngine(mock_config)
    assert (
        engine._has_supply_rate(
            _candidate_for_required_data(apyBase=apy_base), metadata
        )
        is False
    )


def test_has_protocol_yield_positive_cases(mock_config):
    engine = StrategySimEngine(mock_config)
    assert (
        engine._has_protocol_yield(
            _candidate_for_required_data(apyBase=0.0, apyBase7d=None),
            {"protocol_yield": "4.2"},
        )
        is True
    )
    assert (
        engine._has_protocol_yield(_candidate_for_required_data(apyBase=2.2), {})
        is True
    )


@pytest.mark.parametrize(
    "metadata,apy_base",
    [
        ({"protocol_yield": "bad"}, 0.0),
        ({"protocol_yield": "-1"}, 0.0),
        ({}, 0.0),
    ],
)
def test_has_protocol_yield_negative_cases(mock_config, metadata, apy_base):
    engine = StrategySimEngine(mock_config)
    assert (
        engine._has_protocol_yield(
            _candidate_for_required_data(apyBase=apy_base), metadata
        )
        is False
    )


def test_has_staking_rate_positive_cases(mock_config):
    engine = StrategySimEngine(mock_config)
    assert (
        engine._has_staking_rate(
            _candidate_for_required_data(apyReward=0.0), {"staking_rate": "1.1"}
        )
        is True
    )
    assert (
        engine._has_staking_rate(_candidate_for_required_data(apyReward=0.9), {})
        is True
    )


@pytest.mark.parametrize(
    "metadata,apy_reward",
    [
        ({"staking_rate": "oops"}, 0.0),
        ({"staking_rate": "-1.0"}, 0.0),
        ({}, 0.0),
    ],
)
def test_has_staking_rate_negative_cases(mock_config, metadata, apy_reward):
    engine = StrategySimEngine(mock_config)
    assert (
        engine._has_staking_rate(
            _candidate_for_required_data(apyReward=apy_reward), metadata
        )
        is False
    )


def test_has_price_range_positive_cases(mock_config):
    engine = StrategySimEngine(mock_config)
    assert (
        engine._has_price_range(
            {
                "suggested_range_lower_tick": "-100",
                "suggested_range_upper_tick": "100",
            }
        )
        is True
    )
    assert engine._has_price_range({"tick_range_half_width_pct": "0.03"}) is True


@pytest.mark.parametrize(
    "metadata",
    [
        {},
        {"suggested_range_lower_tick": "x", "suggested_range_upper_tick": "100"},
        {"suggested_range_lower_tick": "100", "suggested_range_upper_tick": "100"},
        {"suggested_range_lower_tick": "100", "suggested_range_upper_tick": "10"},
        {"range_width_pct": "-0.1"},
    ],
)
def test_has_price_range_negative_cases(mock_config, metadata):
    engine = StrategySimEngine(mock_config)
    assert engine._has_price_range(metadata) is False


def test_has_volatility_proxy_positive_cases(mock_config):
    engine = StrategySimEngine(mock_config)
    assert engine._has_volatility_proxy({"tick_daily_vol": "0.12"}) is True
    assert engine._has_volatility_proxy({"sigma": "0.4"}) is True


@pytest.mark.parametrize(
    "metadata",
    [
        {},
        {"volatility_proxy": ""},
        {"tick_daily_vol": "bad"},
        {"tick_daily_vol": "-0.2"},
        {"sigma": "0"},
    ],
)
def test_has_volatility_proxy_negative_cases(mock_config, metadata):
    engine = StrategySimEngine(mock_config)
    assert engine._has_volatility_proxy(metadata) is False


def test_required_data_missing_integration_clmm_ready_data_no_missing(mock_config):
    engine = StrategySimEngine(mock_config)
    result = ScoutResult(
        candidate=_candidate_for_required_data(
            symbol="ETH-USDC",
            project="Uniswap V3",
            volumeUsd1d=400_000,
            apyBase=3.0,
            sigma=0.2,
        ),
        net_apy=6.0,
        net_profit_usd=100.0,
        score=10.0,
        priority="COIN_STABLE",
        metadata={
            "pair_currency_class": "TOKEN_STABLE",
            "fees_24h_usd": "350.5",
            "suggested_range_lower_tick": "-120",
            "suggested_range_upper_tick": "80",
            "tick_daily_vol": "0.11",
        },
    )

    simulated = engine.simulate_one(result)
    assert simulated.best_strategy == StrategyId.CLMM_RANGE_HARVEST
    assert simulated.status == SimStatus.OK
    assert simulated.required_data_missing == []


def test_required_data_missing_integration_clmm_invalid_range_and_vol(mock_config):
    engine = StrategySimEngine(mock_config)
    result = ScoutResult(
        candidate=_candidate_for_required_data(
            symbol="ETH-USDC",
            project="Uniswap V3",
            volumeUsd1d=400_000,
            apyBase=3.0,
            sigma=None,
        ),
        net_apy=6.0,
        net_profit_usd=100.0,
        score=10.0,
        priority="COIN_STABLE",
        metadata={
            "pair_currency_class": "TOKEN_STABLE",
            "fees_24h_usd": "350.5",
            "suggested_range_lower_tick": "80",
            "suggested_range_upper_tick": "80",
            "tick_daily_vol": "bad",
        },
    )

    simulated = engine.simulate_one(result)
    assert simulated.best_strategy == StrategyId.CLMM_RANGE_HARVEST
    assert simulated.status == SimStatus.PARTIAL
    assert set(simulated.required_data_missing) == {"price_range", "volatility_proxy"}
