import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.scout.config import ScoutConfig
from defi_agents.scout.cache import ScoutDeduper
from defi_agents.scout.models import ScoutCandidate
from defi_agents.scout.scout import YieldScout
from defi_agents.security.models import (
    SecurityReason,
    SecurityResult,
    SecuritySeverity,
    SecuritySource,
    SecurityStatus,
)


class _MockClient:
    def __init__(self, pools):
        self._pools = pools

    async def get_pools(self):
        return self._pools


class _MockAuditor:
    def __init__(self, status_map):
        self._status_map = status_map

    async def evaluate(self, address, chain_id):
        return self._status_map[address]


def _candidate(pool, chain, symbol, apy, apy_mean_30d, tvl, age_days=None, volume_24h_usd=None):
    suffix = pool[-1] if pool and pool[-1].isdigit() else "1"
    candidate = ScoutCandidate.model_validate(
        {
            "pool": pool,
            "project": "dex",
            "chain": chain,
            "symbol": symbol,
            "address": "0x" + (suffix * 40),
            "chain_id": 8453,
            "tvlUsd": tvl,
            "volumeUsd1d": volume_24h_usd,
            "apy": apy,
            "apyBase": apy,
            "apyReward": 0.0,
            "apyMean30d": apy_mean_30d,
        }
    )
    candidate.contract_age_days = age_days
    return candidate


def _scout(cfg, pools, status_map):
    return YieldScout(cfg, _MockClient(pools), _MockAuditor(status_map), deduper=ScoutDeduper(ttl_seconds=0))


def test_aggregator_dedup():
    cfg = ScoutConfig(min_tvl_usd=100_000)
    pools = [
        _candidate("pool1", "Base", "USDC-USDT", 12, 10, 10_000_000),
        _candidate("pool2", "Base", "USDT-USDC", 10, 9, 12_000_000),
    ]
    status_map = {
        pools[0].address: SecurityResult.pass_as_tier1(),
        pools[1].address: SecurityResult.pass_as_tier1(),
    }
    scout = _scout(cfg, pools, status_map)
    results = _run(scout.analyze())
    assert len(results) == 1


def test_volatility_trap_filtered():
    cfg = ScoutConfig(min_tvl_usd=100_000, apy_anomaly_ratio=2.0)
    pools = [
        _candidate("pool1", "Base", "USDC-USDT", 100, 5, 10_000_000),
    ]
    status_map = {pools[0].address: SecurityResult.pass_as_tier1()}
    scout = _scout(cfg, pools, status_map)
    results = _run(scout.analyze())
    assert len(results) == 0


def test_security_block_excluded():
    cfg = ScoutConfig(min_tvl_usd=100_000)
    pools = [
        _candidate("pool1", "Base", "USDC-USDT", 20, 18, 10_000_000),
    ]
    status_map = {
        pools[0].address: SecurityResult(status=SecurityStatus.BLOCK, score=0, reasons=[], sources=[])
    }
    scout = _scout(cfg, pools, status_map)
    results = _run(scout.analyze())
    assert len(results) == 0


def test_lindy_softens_missing_audit_block():
    cfg = ScoutConfig(min_tvl_usd=100_000, lindy_min_tvl_usd=100_000_000, lindy_min_age_days=180)
    pool = _candidate("pool1", "Base", "USDC-USDT", 20, 18, 150_000_000, age_days=365)
    status_map = {
        pool.address: SecurityResult(
            status=SecurityStatus.BLOCK,
            score=10,
            reasons=[
                SecurityReason(
                    code="NO_TOP_TIER_AUDIT",
                    label="No top tier audit",
                    severity=SecuritySeverity.MEDIUM,
                    source=SecuritySource.DEFI_REPUTATION,
                )
            ],
            sources=[],
        )
    }
    scout = _scout(cfg, [pool], status_map)
    results = _run(scout.analyze())
    assert len(results) == 1
    assert results[0].security.status == SecurityStatus.WARN
    assert results[0].metadata.get("lindy_softened") == "true"


def test_lindy_does_not_override_hidden_owner_block():
    cfg = ScoutConfig(min_tvl_usd=100_000, lindy_min_tvl_usd=100_000_000, lindy_min_age_days=180)
    pool = _candidate("pool1", "Base", "USDC-USDT", 20, 18, 150_000_000, age_days=365)
    status_map = {
        pool.address: SecurityResult(
            status=SecurityStatus.BLOCK,
            score=10,
            reasons=[
                SecurityReason(
                    code="HIDDEN_OWNER",
                    label="Owner hidden",
                    severity=SecuritySeverity.HIGH,
                    source=SecuritySource.GOPLUS,
                )
            ],
            sources=[],
        )
    }
    scout = _scout(cfg, [pool], status_map)
    results = _run(scout.analyze())
    assert len(results) == 0


def test_net_profit_uses_position_size_and_amortized_gas():
    cfg = ScoutConfig(
        min_tvl_usd=100_000,
        gas_efficiency={
            "position_size_usd": 2500,
            "estimated_roundtrip_gas_usd": 8,
            "holding_period_days": 45,
        },
    )
    pool = _candidate("pool1", "Base", "USDC-USDT", 12, 10, 10_000_000)
    status_map = {pool.address: SecurityResult.pass_as_tier1()}
    scout = _scout(cfg, [pool], status_map)
    results = _run(scout.analyze())
    assert len(results) == 1
    # Gross: 2500 * 12% / 12 = 25.0, Gas amortized: 8 * (30/45) = 5.333...
    assert results[0].net_profit_usd == pytest.approx(19.6666, rel=1e-3)


def test_profile_capacity_micro_passes_while_whale_filtered():
    pool = _candidate("pool1", "Base", "USDC-USDT", 12, 10, 1_000_000)
    status_map = {pool.address: SecurityResult.pass_as_tier1()}

    micro_cfg = ScoutConfig(
        min_tvl_usd=100_000,
        gas_efficiency={
            "estimated_roundtrip_gas_usd": 1.0,
            "holding_period_days": 60,
        },
        investor_profile={
            "initial_capital_usd": 1_000,
            "risk_profile": "micro",
            "horizon_days": 30,
        },
    )
    whale_cfg = ScoutConfig(
        min_tvl_usd=100_000,
        gas_efficiency={
            "estimated_roundtrip_gas_usd": 1.0,
            "holding_period_days": 60,
        },
        investor_profile={
            "initial_capital_usd": 1_000_000,
            "risk_profile": "whale",
            "horizon_days": 30,
        },
    )

    micro_results = _run(_scout(micro_cfg, [pool], status_map).analyze())
    whale_results = _run(_scout(whale_cfg, [pool], status_map).analyze())

    assert len(micro_results) == 1
    assert len(whale_results) == 0


def test_benchmark_tag_is_added_to_metadata():
    cfg = ScoutConfig(
        min_tvl_usd=100_000,
        investor_profile={
            "benchmark_apy": 5.0,
            "benchmark_buffer_apy": 1.0,
        },
    )
    pool = _candidate("pool1", "Base", "USDC-USDT", 9, 8, 10_000_000)
    status_map = {pool.address: SecurityResult.pass_as_tier1()}
    results = _run(_scout(cfg, [pool], status_map).analyze())

    assert len(results) == 1
    assert results[0].metadata["above_benchmark"] == "true"
    assert float(results[0].metadata["benchmark_delta_apy"]) == pytest.approx(3.0, rel=1e-2)


def test_defillama_stability_fields_are_threaded_to_metadata():
    cfg = ScoutConfig(min_tvl_usd=100_000)
    pool = ScoutCandidate.model_validate(
        {
            "pool": "pool-stability",
            "project": "uniswap-v3",
            "chain": "Ethereum",
            "symbol": "USDC-USDT",
            "address": "0x" + ("1" * 40),
            "chain_id": 1,
            "tvlUsd": 5_000_000,
            "apy": 12.0,
            "apyBase": 11.0,
            "apyReward": 1.0,
            "apyMean30d": 9.0,
            "apyPct30D": 15.5,
            "apyPct7D": 4.2,
            "apyPct1D": 0.9,
            "apyBase7d": 10.7,
            "il7d": 0.3,
            "ilRisk": "no",
            "outlier": False,
            "mu": 11.5,
            "sigma": 2.1,
            "exposure": "multi",
        }
    )
    status_map = {pool.address: SecurityResult.pass_as_tier1()}
    results = _run(_scout(cfg, [pool], status_map).analyze())

    assert len(results) == 1
    meta = results[0].metadata
    assert meta["apy_mean_30d"] == "9.00"
    assert meta["apy_pct_30d"] == "15.50"
    assert meta["apy_pct_7d"] == "4.20"
    assert meta["apy_pct_1d"] == "0.90"
    assert meta["apy_base_7d"] == "10.70"
    assert meta["il_7d"] == "0.30"
    assert meta["il_risk"] == "no"
    assert meta["outlier"] == "false"
    assert meta["mu"] == "11.50"
    assert meta["sigma"] == "2.10"
    assert meta["exposure"] == "multi"
    assert float(meta["apy_vs_mean_30d_pct"]) == pytest.approx(33.33, rel=1e-2)


def test_stability_scoring_applies_soft_penalty_without_hard_gate_changes():
    pool = ScoutCandidate.model_validate(
        {
            "pool": "pool-stability-penalty",
            "project": "uniswap-v3",
            "chain": "Base",
            "symbol": "USDC-USDT",
            "address": "0x" + ("2" * 40),
            "chain_id": 8453,
            "tvlUsd": 8_000_000,
            "apy": 10.0,
            "apyBase": 10.0,
            "apyReward": 0.0,
            "apyMean30d": 6.0,
            "outlier": True,
            "mu": 6.0,
            "sigma": 4.8,
            "ilRisk": "yes",
        }
    )
    status_map = {pool.address: SecurityResult.pass_as_tier1()}

    cfg_disabled = ScoutConfig(min_tvl_usd=100_000)
    cfg_enabled = ScoutConfig(
        min_tvl_usd=100_000,
        defillama_provider={
            "enable_stability_scoring": True,
            "stability_outlier_factor": 0.5,
            "stability_apy_mean_deviation_pct": 50.0,
            "stability_apy_deviation_factor": 0.8,
            "stability_sigma_to_mu_threshold": 0.6,
            "stability_sigma_factor": 0.8,
            "stability_il_risk_factor": 0.9,
        },
    )

    res_disabled = _run(_scout(cfg_disabled, [pool], status_map).analyze())
    res_enabled = _run(_scout(cfg_enabled, [pool], status_map).analyze())

    assert len(res_disabled) == 1
    assert len(res_enabled) == 1
    assert res_enabled[0].score < res_disabled[0].score
    assert res_enabled[0].metadata["stability_signals"] == "OUTLIER,APY_VS_30D_HIGH,SIGMA_TO_MU_HIGH,IL_RISK"
    assert float(res_enabled[0].metadata["stability_factor"]) == pytest.approx(0.288, rel=1e-3)


def test_tactical_sleeve_requires_explicit_enable():
    pool = _candidate("pool1", "Base", "USDC-USDT", 150, 100, 1_000_000)
    status_map = {pool.address: SecurityResult.pass_as_tier1()}

    disabled_cfg = ScoutConfig(min_tvl_usd=100_000)
    enabled_cfg = ScoutConfig(
        min_tvl_usd=100_000,
        sleeves={
            "tactical_enabled": True,
            "tactical_min_apy": 100.0,
            "tactical_high_apy_pct": 0.05,
        },
    )

    disabled_results = _run(_scout(disabled_cfg, [pool], status_map).analyze())
    enabled_results = _run(_scout(enabled_cfg, [pool], status_map).analyze())

    assert len(disabled_results) == 0
    assert len(enabled_results) == 1
    assert enabled_results[0].metadata["sleeve"] == "tactical_high_apy"


def test_exploration_quota_includes_high_apy_stable_outside_top_tvl():
    cfg = ScoutConfig(
        min_tvl_usd=100_000,
        max_audit_candidates=4,
        exploration_slots=1,
        exploration_min_apy=20.0,
        exploration_stable_only=True,
    )
    pools = [
        _candidate("pool1", "Base", "USDC-USDT", 10, 12, 20_000_000),
        _candidate("pool2", "Base", "DAI-USDC", 11, 13, 15_000_000),
        _candidate("pool3", "Base", "USDC-USDS", 12, 14, 12_000_000),
        _candidate("pool4", "Base", "FRAX-USDC", 9, 11, 8_000_000),
        _candidate("pool5", "Base", "EURC-USDC", 30, 35, 2_000_000),
    ]
    status_map = {pool.address: SecurityResult.pass_as_tier1() for pool in pools}
    results = _run(_scout(cfg, pools, status_map).analyze())

    assert len(results) == 4
    symbols = {res.candidate.symbol for res in results}
    assert "EURC-USDC" in symbols


def _run(coro):
    import asyncio

    return asyncio.run(coro)


# --- Stablecoin Risk Policy Tests ---


def test_classify_token_tier_t1():
    """T1 stables (USDC, USDT, DAI, USDS) are classified as T1."""
    cfg = ScoutConfig(min_tvl_usd=100_000, risk_policy={"enabled": True})
    pool = _candidate("pool1", "Base", "USDC-USDT", 12, 10, 10_000_000)
    status_map = {pool.address: SecurityResult.pass_as_tier1()}
    scout = _scout(cfg, [pool], status_map)
    
    from defi_agents.scout.models import StableTier
    assert scout._classify_token_tier("USDC") == StableTier.T1
    assert scout._classify_token_tier("USDT") == StableTier.T1
    assert scout._classify_token_tier("DAI") == StableTier.T1
    assert scout._classify_token_tier("USDS") == StableTier.T1


def test_classify_token_tier_t2():
    """T2 stables (crvUSD, GHO, PYUSD) are classified as T2."""
    cfg = ScoutConfig(min_tvl_usd=100_000, risk_policy={"enabled": True})
    pool = _candidate("pool1", "Base", "GHO-USDC", 12, 10, 10_000_000)
    status_map = {pool.address: SecurityResult.pass_as_tier1()}
    scout = _scout(cfg, [pool], status_map)
    
    from defi_agents.scout.models import StableTier
    assert scout._classify_token_tier("crvUSD") == StableTier.T2
    assert scout._classify_token_tier("GHO") == StableTier.T2
    assert scout._classify_token_tier("PYUSD") == StableTier.T2


def test_classify_token_tier_t3():
    """T3 speculative stables (USDe, TUSD, FDUSD) are classified as T3."""
    cfg = ScoutConfig(min_tvl_usd=100_000, risk_policy={"enabled": True})
    pool = _candidate("pool1", "Base", "USDe-USDC", 12, 10, 10_000_000)
    status_map = {pool.address: SecurityResult.pass_as_tier1()}
    scout = _scout(cfg, [pool], status_map)
    
    from defi_agents.scout.models import StableTier
    assert scout._classify_token_tier("USDe") == StableTier.T3
    assert scout._classify_token_tier("TUSD") == StableTier.T3
    assert scout._classify_token_tier("FDUSD") == StableTier.T3


def test_classify_pair_usd_stable_stable():
    """USD-only pair is classified as USD_STABLE_STABLE."""
    cfg = ScoutConfig(min_tvl_usd=100_000, risk_policy={"enabled": True})
    pool = _candidate("pool1", "Base", "USDC-USDT", 12, 10, 10_000_000)
    status_map = {pool.address: SecurityResult.pass_as_tier1()}
    scout = _scout(cfg, [pool], status_map)
    
    from defi_agents.scout.models import PairCurrencyClass
    pair_class, fx_exposure = scout._classify_pair(pool)
    assert pair_class == PairCurrencyClass.USD_STABLE_STABLE
    assert fx_exposure is False


def test_classify_pair_fx_stable():
    """USD/EUR mixed pair is classified as FX_STABLE with fx_exposure=True."""
    cfg = ScoutConfig(min_tvl_usd=100_000, risk_policy={"enabled": True})
    pool = _candidate("pool1", "Base", "EURC-USDC", 12, 10, 10_000_000)
    status_map = {pool.address: SecurityResult.pass_as_tier1()}
    scout = _scout(cfg, [pool], status_map)
    
    from defi_agents.scout.models import PairCurrencyClass
    pair_class, fx_exposure = scout._classify_pair(pool)
    assert pair_class == PairCurrencyClass.FX_STABLE
    assert fx_exposure is True


def test_blacklist_blocks_by_symbol():
    """Blacklisted symbol is rejected before security calls."""
    cfg = ScoutConfig(
        min_tvl_usd=100_000,
        risk_policy={"enabled": True},
        token_buckets={"exclude_symbols": ["BADTOKEN"]},
    )
    pool = _candidate("pool1", "Base", "BADTOKEN-USDC", 12, 10, 10_000_000)
    status_map = {pool.address: SecurityResult.pass_as_tier1()}
    scout = _scout(cfg, [pool], status_map)
    
    blocked, blacklist_by = scout._check_blacklist(pool)
    assert blocked is True
    assert blacklist_by == "symbol"


def test_blacklist_blocks_by_address():
    """Blacklisted address is rejected before symbol check."""
    bad_address = "0x" + ("b" * 40)
    cfg = ScoutConfig(
        min_tvl_usd=100_000,
        risk_policy={"enabled": True},
        token_buckets={"exclude_addresses": [bad_address]},
    )
    pool = ScoutCandidate.model_validate({
        "pool": "pool1",
        "project": "dex",
        "chain": "Base",
        "symbol": "USDC-USDT",
        "address": bad_address,
        "chain_id": 8453,
        "tvlUsd": 10_000_000,
        "apy": 12,
        "apyBase": 12,
        "apyMean30d": 10,
    })
    status_map = {pool.address: SecurityResult.pass_as_tier1()}
    scout = _scout(cfg, [pool], status_map)
    
    blocked, blacklist_by = scout._check_blacklist(pool)
    assert blocked is True
    assert blacklist_by == "address"


def test_metadata_contains_tier_and_class():
    """Result metadata contains stable_tier, pair_currency_class, and fx_exposure."""
    cfg = ScoutConfig(min_tvl_usd=100_000, risk_policy={"enabled": True})
    pool = _candidate("pool1", "Base", "USDC-USDT", 12, 10, 10_000_000)
    status_map = {pool.address: SecurityResult.pass_as_tier1()}
    results = _run(_scout(cfg, [pool], status_map).analyze())
    
    assert len(results) == 1
    meta = results[0].metadata
    assert meta.get("stable_tier") == "T1"
    assert meta.get("pair_currency_class") == "USD_STABLE_STABLE"
    assert meta.get("fx_exposure") == "false"


def test_fx_pair_has_fx_exposure_in_metadata():
    """FX pair has fx_exposure=true in metadata."""
    cfg = ScoutConfig(min_tvl_usd=100_000, risk_policy={"enabled": True})
    pool = _candidate("pool1", "Base", "EURC-USDC", 12, 10, 10_000_000)
    status_map = {pool.address: SecurityResult.pass_as_tier1()}
    results = _run(_scout(cfg, [pool], status_map).analyze())
    
    assert len(results) == 1
    meta = results[0].metadata
    assert meta.get("pair_currency_class") == "FX_STABLE"
    assert meta.get("fx_exposure") == "true"


def test_fx_stable_priority_not_low_volatility():
    """FX_STABLE pair must not be classified as LOW_VOLATILITY when risk policy enabled."""
    from defi_agents.scout.models import PairCurrencyClass, PriorityTier

    cfg = ScoutConfig(
        min_tvl_usd=100_000,
        risk_policy={"enabled": True, "fx_pairs_core_safe_allowed": False},
    )
    pool = _candidate("pool1", "Base", "EURC-USDC", 12, 10, 10_000_000)
    scout = _scout(cfg, [pool], {pool.address: SecurityResult.pass_as_tier1()})

    # Verify pair classification
    pair_class, fx_exposure = scout._classify_pair(pool)
    assert pair_class == PairCurrencyClass.FX_STABLE
    assert fx_exposure is True

    # Verify priority override
    priority = scout._classify_priority(pool)
    assert priority != PriorityTier.LOW_VOLATILITY
    assert priority == PriorityTier.COIN_STABLE  # as per our override


def test_fx_stable_sleeve_routing_when_core_safe_disallowed():
    """FX_STABLE pair must be routed to yield_plus when fx_pairs_core_safe_allowed=false."""
    from defi_agents.scout.models import PairCurrencyClass
    from defi_agents.security.models import SecurityStatus

    cfg = ScoutConfig(
        min_tvl_usd=100_000,
        risk_policy={"enabled": True, "fx_pairs_core_safe_allowed": False},
    )
    pool = _candidate("pool1", "Base", "EURC-USDC", 12, 10, 10_000_000)
    scout = _scout(cfg, [pool], {pool.address: SecurityResult.pass_as_tier1()})

    # Should be FX_STABLE
    pair_class, _ = scout._classify_pair(pool)
    assert pair_class == PairCurrencyClass.FX_STABLE

    # Sleeve assignment with TRUSTED security (would normally be core_safe)
    sleeve, reason = scout._assign_sleeve(pool, SecurityStatus.TRUSTED)
    assert sleeve == "yield_plus"
    assert reason is None


def test_fx_stable_sleeve_routing_when_core_safe_allowed():
    """FX_STABLE pair can be core_safe when fx_pairs_core_safe_allowed=true."""
    from defi_agents.scout.models import PairCurrencyClass
    from defi_agents.security.models import SecurityStatus

    cfg = ScoutConfig(
        min_tvl_usd=100_000,
        risk_policy={"enabled": True, "fx_pairs_core_safe_allowed": True},
    )
    pool = _candidate("pool1", "Base", "EURC-USDC", 12, 10, 10_000_000)
    scout = _scout(cfg, [pool], {pool.address: SecurityResult.pass_as_tier1()})

    pair_class, _ = scout._classify_pair(pool)
    assert pair_class == PairCurrencyClass.FX_STABLE

    # With TRUSTED security and low volatility tier (but priority overridden to COIN_STABLE)
    # However, tier will be COIN_STABLE, which is still eligible for core_safe.
    # Let's just verify that sleeve is core_safe (since security is TRUSTED and tier is COIN_STABLE)
    sleeve, reason = scout._assign_sleeve(pool, SecurityStatus.TRUSTED)
    assert sleeve == "core_safe"
    assert reason is None


def test_asset_universe_filter_defaults_to_all():
    cfg = ScoutConfig(min_tvl_usd=100_000)
    pools = [
        _candidate("pool1", "Base", "WETH-AERO", 12, 10, 10_000_000),
        _candidate("pool2", "Base", "USDC-USDT", 12, 10, 10_000_000),
    ]
    status_map = {pool.address: SecurityResult.pass_as_tier1() for pool in pools}
    results = _run(_scout(cfg, pools, status_map).analyze())
    assert {r.candidate.symbol for r in results} == {"WETH-AERO", "USDC-USDT"}


def test_asset_universe_filter_target_only_drops_non_target_tokens():
    cfg = ScoutConfig(min_tvl_usd=100_000, asset_universe={"intake_target_assets_only": True})
    pools = [
        _candidate("pool1", "Base", "WETH-USDC", 12, 10, 10_000_000),  # keep
        _candidate("pool2", "Base", "PAXG-USDC", 12, 10, 10_000_000),  # keep
        _candidate("pool3", "Base", "WETH-AERO", 12, 10, 10_000_000),  # drop
        _candidate("pool4", "Base", "USDC-USDT", 12, 10, 10_000_000),  # keep
    ]
    status_map = {pool.address: SecurityResult.pass_as_tier1() for pool in pools}
    results = _run(_scout(cfg, pools, status_map).analyze())
    symbols = {r.candidate.symbol for r in results}
    assert "WETH-AERO" not in symbols
    assert "WETH-USDC" in symbols
    assert "PAXG-USDC" in symbols
    assert "USDC-USDT" in symbols


def test_liquidity_gate_allows_high_volume_low_tvl_pool():
    cfg = ScoutConfig(
        min_tvl_usd=500_000,
        liquidity_gates={"min_volume_24h_usd": 1_000_000},
        investor_profile={"initial_capital_usd": 1_000, "risk_profile": "micro", "horizon_days": 30},
        gas_efficiency={"estimated_roundtrip_gas_usd": 0.0, "holding_period_days": 60},
    )
    pools = [
        _candidate("pool1", "Base", "USDC-USDT", 12, 10, 120_000, volume_24h_usd=2_000_000),
    ]
    status_map = {pools[0].address: SecurityResult.pass_as_tier1()}
    results = _run(_scout(cfg, pools, status_map).analyze())
    assert len(results) == 1


def test_liquidity_gate_rejects_below_absolute_min_tvl_even_with_volume():
    cfg = ScoutConfig(
        min_tvl_usd=500_000,
        liquidity_gates={"absolute_min_tvl_usd": 100_000, "min_volume_24h_usd": 1_000_000},
        investor_profile={"initial_capital_usd": 1_000, "risk_profile": "micro", "horizon_days": 30},
        gas_efficiency={"estimated_roundtrip_gas_usd": 0.0, "holding_period_days": 60},
    )
    pools = [
        _candidate("pool1", "Base", "USDC-USDT", 12, 10, 90_000, volume_24h_usd=2_000_000),
    ]
    status_map = {pools[0].address: SecurityResult.pass_as_tier1()}
    results = _run(_scout(cfg, pools, status_map).analyze())
    assert len(results) == 0


def test_non_evm_chain_hint_detection():
    cfg = ScoutConfig(min_tvl_usd=100_000)
    scout = _scout(cfg, [], {})
    assert scout._is_non_evm_chain_name("Solana") is True
    assert scout._is_non_evm_chain_name("Sui") is True
    assert scout._is_non_evm_chain_name("Ethereum") is False
