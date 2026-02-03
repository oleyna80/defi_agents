---
name: asset-classifier
description: Implement the echeloned AssetClassifier (metadata -> regex -> optional contract signatures) and apply fail-safe policies for unknown assets.
---

# Asset Classifier

## Goal
Classify assets conservatively (bridged/synthetic/vault/leveraged/unknown) using "footprints", not only tags, to reduce false positives and opportunity cost.

## Workflow
1. Echelon 1 (metadata):
   - Use DeFiLlama `category` and `poolMeta` to detect leveraged/vault/LST patterns.
2. Echelon 2 (regex, case-aware):
   - Detect bridged/synthetic/vault/leveraged patterns from symbol/name.
   - Avoid false positives (check Tier 1 stable whitelist before regex).
3. Echelon 3 (optional signatures):
   - If still ambiguous and we have address + RPC, check ERC-4626 signatures:
     `asset()`, `totalAssets()`, `convertToShares()`.
   - Detect risky proxies (upgradeable without timelock) and mark high risk.
4. Fail-safe:
   - If UNKNOWN and not Tier 1 stable => BLOCK by default.
   - Allow manual override via local memory whitelist:
     `docs/memory-bank/security/whitelist.json`.

## Outputs
- `classify_asset(...) -> AssetType`
- Deterministic reasons for classification (for reports and debugging)
