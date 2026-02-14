from __future__ import annotations

from typing import Any

from .defillama_models import (
    BridgeFact,
    BridgeSnapshotFact,
    MarketOverviewFact,
    MarketProtocolRow,
    MarketSummaryFact,
    PriceFact,
    StablecoinAssetFact,
    StablecoinSnapshotFact,
    YieldPoolFact,
    YieldPoolHistoryPoint,
)


def parse_data_list_payload(payload: Any) -> list[dict] | None:
    """Return data list when payload shape is valid, otherwise None."""
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if not isinstance(data, list):
        return None
    out: list[dict] = []
    for item in data:
        if isinstance(item, dict):
            out.append(item)
    return out


def parse_yield_pool_facts(rows: list[dict]) -> list[YieldPoolFact]:
    facts: list[YieldPoolFact] = []
    for row in rows:
        try:
            facts.append(YieldPoolFact.model_validate(row))
        except Exception:
            continue
    return facts


def parse_yield_pool_history(rows: list[dict]) -> list[YieldPoolHistoryPoint]:
    points: list[YieldPoolHistoryPoint] = []
    for row in rows:
        try:
            points.append(YieldPoolHistoryPoint.model_validate(row))
        except Exception:
            continue
    return points


def parse_market_overview(category: str, payload: Any) -> MarketOverviewFact | None:
    if not isinstance(payload, dict):
        return None
    raw_protocols = payload.get("protocols")
    if not isinstance(raw_protocols, list):
        return None
    protocols: list[MarketProtocolRow] = []
    for row in raw_protocols:
        if not isinstance(row, dict):
            continue
        try:
            protocols.append(MarketProtocolRow.model_validate(row))
        except Exception:
            continue
    raw_chains = payload.get("allChains")
    chains: list[str] = []
    if isinstance(raw_chains, list):
        chains = [str(chain) for chain in raw_chains if isinstance(chain, str)]
    data = dict(payload)
    data["category"] = category
    data["protocols"] = protocols
    data["all_chains"] = chains
    try:
        return MarketOverviewFact.model_validate(data)
    except Exception:
        return None


def parse_market_summary(category: str, protocol: str, payload: Any) -> MarketSummaryFact | None:
    if not isinstance(payload, dict):
        return None
    data = dict(payload)
    data["category"] = category
    data["protocol"] = protocol
    try:
        return MarketSummaryFact.model_validate(data)
    except Exception:
        return None


def parse_stablecoin_snapshot(payload: Any) -> StablecoinSnapshotFact | None:
    if not isinstance(payload, dict):
        return None
    raw_assets = payload.get("peggedAssets")
    if not isinstance(raw_assets, list):
        return None
    assets: list[StablecoinAssetFact] = []
    for row in raw_assets:
        if not isinstance(row, dict):
            continue
        try:
            assets.append(StablecoinAssetFact.model_validate(row))
        except Exception:
            continue
    raw_chains = payload.get("chains")
    chains: list[str] = []
    if isinstance(raw_chains, list):
        for row in raw_chains:
            if isinstance(row, str):
                chains.append(row)
            elif isinstance(row, dict):
                name = row.get("name")
                if isinstance(name, str):
                    chains.append(name)
    return StablecoinSnapshotFact(assets=assets, chains=chains)


def parse_bridge_snapshot(payload: Any) -> BridgeSnapshotFact | None:
    if not isinstance(payload, dict):
        return None
    raw_bridges = payload.get("bridges")
    if not isinstance(raw_bridges, list):
        return None
    bridges: list[BridgeFact] = []
    for row in raw_bridges:
        if not isinstance(row, dict):
            continue
        try:
            bridges.append(BridgeFact.model_validate(row))
        except Exception:
            continue
    raw_chains = payload.get("chains")
    chains: list[str] = []
    if isinstance(raw_chains, list):
        for row in raw_chains:
            if isinstance(row, str):
                chains.append(row)
            elif isinstance(row, dict):
                name = row.get("name")
                if isinstance(name, str):
                    chains.append(name)
    return BridgeSnapshotFact(bridges=bridges, chains=chains)


def parse_price_map(payload: Any) -> list[PriceFact]:
    if not isinstance(payload, dict):
        return []
    coins = payload.get("coins")
    if not isinstance(coins, dict):
        return []
    out: list[PriceFact] = []
    for key, row in coins.items():
        if not isinstance(key, str) or not isinstance(row, dict):
            continue
        try:
            out.append(
                PriceFact(
                    key=key,
                    symbol=row.get("symbol"),
                    price=row.get("price"),
                    timestamp=row.get("timestamp"),
                    confidence=row.get("confidence"),
                    raw=row,
                )
            )
        except Exception:
            continue
    return out
