from __future__ import annotations

from typing import List, Dict, Any
from .models import StrategyId, StrategyMetadata


def get_strategy_catalog() -> List[StrategyMetadata]:
    """Return v1 strategy catalog."""
    return [
        StrategyMetadata(
            id=StrategyId.LIQUID_STAKING_CORE,
            name="Liquid Staking Core",
            description="Stake native ETH (or other PoS) via liquid staking tokens (LSTs).",
            entry_rules=[
                "symbol contains stETH/rETH/sfrxETH/jitoSOL/mSOL",
                "project is known LST provider (Lido, Rocket Pool, Frax Ether, etc.)",
            ],
            exit_rules=["unstake via LST redemption"],
            required_data=["tvl_usd", "apy", "staking_rewards"],
            risk_limits={"max_slash_risk": 0.01},
            supported_chains=["Ethereum", "Solana", "Avalanche"],
            supported_pair_classes=["TOKEN_STABLE", "TOKEN_TOKEN"],
            tier="T1",
        ),
        StrategyMetadata(
            id=StrategyId.SINGLE_SIDED_LENDING,
            name="Single‑Sided Lending",
            description="Deposit single asset into lending protocol (Aave, Spark, Morpho).",
            entry_rules=[
                "project contains aave/spark/morpho",
                "pair class is TOKEN_STABLE or USD_STABLE_STABLE",
            ],
            exit_rules=["withdraw anytime"],
            required_data=["tvl_usd", "apy", "utilization", "supply_rate"],
            risk_limits={"max_utilization": 0.95},
            supported_chains=["Ethereum", "Base", "Arbitrum", "Polygon"],
            supported_pair_classes=["TOKEN_STABLE", "USD_STABLE_STABLE"],
            tier="T1",
        ),
        StrategyMetadata(
            id=StrategyId.YIELD_BEARING_STABLE_CORE,
            name="Yield‑Bearing Stable Core",
            description="Hold yield‑bearing stablecoins (sUSDe, sDAI, USDe).",
            entry_rules=[
                "symbol contains sUSDe/sDAI/USDe",
                "project indicates Ethena or Spark savings",
            ],
            exit_rules=["redeem for underlying stable"],
            required_data=["tvl_usd", "apy", "protocol_yield", "staking_rate"],
            risk_limits={"max_collateral_ratio_deviation": 0.1},
            supported_chains=["Ethereum", "Base"],
            supported_pair_classes=["USD_STABLE_STABLE"],
            tier="T2",
        ),
        StrategyMetadata(
            id=StrategyId.STABLE_STABLE_FEE_CAPTURE,
            name="Stable‑Stable Fee Capture",
            description="Provide liquidity to stable‑stable pairs (USDC‑USDT, EURC‑USDC).",
            entry_rules=[
                "pair class in USD_STABLE_STABLE, EUR_STABLE_STABLE, FX_STABLE",
                "project is DEX with fee tier",
            ],
            exit_rules=["withdraw liquidity"],
            required_data=["tvl_usd", "apy", "volume_24h_usd", "fees_24h_usd"],
            risk_limits={"max_impermanent_loss": 0.001},
            supported_chains=["Ethereum", "Arbitrum", "Base", "Polygon"],
            supported_pair_classes=["USD_STABLE_STABLE", "EUR_STABLE_STABLE", "FX_STABLE"],
            tier="T1",
        ),
        StrategyMetadata(
            id=StrategyId.CLMM_RANGE_HARVEST,
            name="CLMM Range Harvest",
            description="Concentrated liquidity with active range management (Uniswap V3, Aerodrome).",
            entry_rules=[
                "project indicates uniswap v3/aerodrome/slipstream/velodrome",
                "pool_type=CLMM explicit",
            ],
            exit_rules=["withdraw liquidity, harvest fees"],
            required_data=[
                "tvl_usd",
                "volume_24h_usd",
                "fees_24h_usd",
                "price_range",
                "volatility_proxy",
            ],
            risk_limits={"max_price_deviation": 0.2},
            supported_chains=["Ethereum", "Arbitrum", "Base", "Polygon"],
            supported_pair_classes=["TOKEN_STABLE", "TOKEN_TOKEN", "USD_STABLE_STABLE"],
            tier="T2",
        ),
    ]


def get_strategy_by_id(strategy_id: StrategyId) -> StrategyMetadata:
    """Return strategy metadata by ID."""
    for strat in get_strategy_catalog():
        if strat.id == strategy_id:
            return strat
    raise ValueError(f"Unknown strategy ID: {strategy_id}")


def get_strategy_ids() -> List[StrategyId]:
    """Return list of all strategy IDs."""
    return [strat.id for strat in get_strategy_catalog()]


def get_supported_pair_classes(strategy_id: StrategyId) -> List[str]:
    """Return pair classes supported by a strategy."""
    strat = get_strategy_by_id(strategy_id)
    return strat.supported_pair_classes


def get_required_data(strategy_id: StrategyId) -> List[str]:
    """Return required data fields for a strategy."""
    strat = get_strategy_by_id(strategy_id)
    return strat.required_data