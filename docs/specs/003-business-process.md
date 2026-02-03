# Specification: Business Process - Step 1 (Automated Scouting)

Status: DRAFT
Owner: User/Agent
Related Memory: `docs/specs/000-universal-defi-agent-concept.md`
Date: 2026-02-01

## 1. Goal
Each day the agent produces a short list of the best stablecoin opportunities (risk/return) using market-wide data, without protocol-specific searching.

## 2. Inputs (Config)
- `allowed_chains`: [Base, Arbitrum, Avalanche]
- `stablecoin_only`: true
- `min_tvl_usd`: 2_000_000
- `top_n`: 10
- `apy_mode`: best_available  # choose the best available APY field from the upstream data
- `stablecoin_tiers_enabled`: true
- `stablecoin_tier_policy`:
  - Tier 1: OK by default (safe)
  - Tier 2: Conditional OK (only in native protocol context)
  - Tier 3: Not OK by default (warn/risky)
- Optional (later): excluded protocols/pool types, min pool age, max deposit cap, bridge/liquidity constraints.

## 2.1 Stablecoin Tiers (2026)

### Tier 1 (OK by default)
- USDC
- USDT
- USDS (ex-DAI / Sky ecosystem)

### Tier 2 (Conditional OK)
Allowed only when the pool/protocol context matches the token's \"native\" ecosystem:
- crvUSD: OK on Curve / Convex
- GHO: OK in/around Aave
- PYUSD: trusted issuer, but low DeFi liquidity; treat as conditional

### Tier 3 (Not OK by default)
Always treated as WARN/risky (never \"safe\" by default):
- FRAX
- USDe
- LUSD

## 3. Data Source
- DeFiLlama Yields API

## 4. Filtering Rules (v0)
- Include only pools where `stablecoin=true`.
- Include only pools with `tvlUsd > 2_000_000`.
- Include only pools on the allowed chains (Base, Arbitrum, Avalanche).
- Include only pools whose underlying stablecoins are Tier 1 for the default top-10 output.
- Optionally (later): include Tier 2 pools into a separate \"Conditional\" list (not OK by default).
- Exclude Tier 3 from default scouting output (can be reported separately as \"risky/high-yield\" with WARN tag, but not recommended).
- Exclude obviously risky categories at Step 1:
  - leveraged strategies
  - vault wrappers
  - bridged stables / synthetic wrappers (unless explicitly whitelisted later)

## 4.1 AssetClassifier (echeloned detection, fail-safe)
To reduce false positives and opportunity cost, Step 1 uses an echeloned classifier:
1) Echelon 1: DeFiLlama metadata fingerprints (`category`, `poolMeta`).
2) Echelon 2: Case-aware regex patterns on token symbols and metadata.
3) Echelon 3: Contract signature check (when needed later) to confirm vault/proxy traits.

Fail-safe policy:
- If an asset is classified as UNKNOWN and is not Tier 1 (USDC/USDT/USDS), exclude from top-10 and require manual approval.

Manual approval storage (SSOT):
- `docs/memory-bank/security/whitelist.json`

## 5. Ranking / Scoring (to define)
We need an explicit scoring function for "best risk/return".
Initial proposal for a transparent score:
- Base score = normalized APY
- Penalties:
  - low TVL (closer to threshold)
  - unknown/low quality metadata
- Boosts:
  - higher TVL / deeper liquidity

Note: final scoring must be coordinated with Security (GoPlus/De.Fi) and exit constraints.

## 6. Output
- Primary output (Telegram): a ranked list of top-10 pools (Tier 1 only) with minimal fields:
  - chain
  - protocol
  - pool name / id
  - apy
  - tvlUsd
  - underlying tokens
  - rationale (why it ranked here)

- Secondary output (optional, JSON SSOT later): full candidate set + tier classification + excluded reasons.

## 7. Non-Goals (for Step 1)
- No security screening here (done in Step 2).
- No wallet-specific monitoring here (done in Monitoring).
- No execution/one-click actions.

## 8. Open Questions
- Which chains exactly (Base/Arbitrum/Avalanche only, or configurable)?
- Do we exclude volatile pairs and LST/LRT stables by default?
- Which APY field is canonical (base vs reward vs total)?
- Do we require pool age / historical stability?
- How exactly do we detect leveraged/vault/bridged categories from DeFiLlama metadata (tags/fields), and what is the fallback if tags are missing?
- Where do we store manual approvals (e.g., `config/whitelist.json`) and who can edit it?

## Approvals
- [ ] User Approved
- [ ] Architecture Approved
