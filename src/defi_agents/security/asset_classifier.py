from __future__ import annotations

import re
from enum import Enum
from typing import Optional


class AssetType(str, Enum):
    TIER1_STABLE = "tier1_stable"
    BRIDGED = "bridged"
    SYNTHETIC = "synthetic"
    VAULT = "vault"
    LEVERAGED = "leveraged"
    LIQUID_STAKING = "liquid_staking"
    UNKNOWN = "unknown"


class AssetClassifier:
    # Case-aware regex patterns (minimize false positives by checking Tier1 first).
    BLACKLIST_PATTERNS = {
        "bridged": r"\.(e|n|axl|ce|lz)$|^axl|^ce|^lz",
        "synthetic": r"^s[A-Z]|^u[A-Z]|^i[A-Z]",
        "vault": r"^yv|^v[A-Z]|^st[A-Z]|^a[A-Z]|^s[a-z]",
        "leveraged": r"\d+x$|^long|^short|^lb-",
    }

    TIER1 = {"USDC", "USDT", "USDS"}

    def classify(
        self,
        *,
        symbol: Optional[str],
        protocol_category: Optional[str],
        pool_meta: Optional[str],
    ) -> AssetType:
        # Echelon 0: explicit Tier1 stable
        if symbol and symbol.upper() in self.TIER1:
            return AssetType.TIER1_STABLE

        # Echelon 1: protocol metadata fingerprints
        if protocol_category:
            if "Leveraged" in protocol_category:
                return AssetType.LEVERAGED
            if "Liquid Staking" in protocol_category:
                return AssetType.LIQUID_STAKING
            if protocol_category in {"Yield", "Vaults"}:
                return AssetType.VAULT

        # poolMeta heuristics for leverage
        if pool_meta:
            if any(k in pool_meta for k in ("Leverage", "X2", "Multiplier")):
                return AssetType.LEVERAGED

        # Echelon 2: regex patterns on symbol
        if symbol:
            for asset_type, pattern in self.BLACKLIST_PATTERNS.items():
                if re.search(pattern, symbol):
                    return AssetType(asset_type)

        return AssetType.UNKNOWN

