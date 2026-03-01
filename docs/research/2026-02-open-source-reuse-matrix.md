# Open-Source Reuse Matrix for LP Execution and Hedging

**Date:** 2026-02-26  
**Owner:** Tech Lead  
**Scope:** Spec 018 (autocompound/autorebalance), Phase 5 pre-work (delta hedger)

## 1. Decision Rule (Mandatory)

- `ALLOW_DIRECT_REUSE`: only repositories with permissive license (`MIT`/`Apache-2.0`) and clear maintenance signals.
- `REFERENCE_ONLY`: copyleft or source-available licenses (`AGPL`, `GPL`, `BUSL`) can be used for architecture/patterns, but not copied into core runtime.
- `BLOCKED`: missing/unclear license metadata until legal clarification.

## 2. Reuse Matrix

| Project | Target module | License (as of 2026-02-26) | Reuse mode | Practical use in our stack | Notes / risks |
|---|---|---|---|---|---|
| `revert-finance/v3utils` | Autorebalance/autocompound tx mechanics | AGPL-3.0 | REFERENCE_ONLY | Keep only ABI/interface patterns behind `ExecutionAdapter` | Copyleft risk for direct code import |
| `revert-finance/compoundor` | Fee compounding flow | AGPL-3.0 | REFERENCE_ONLY | Reuse trigger/state-machine ideas in our own implementation | Direct contract reuse not recommended |
| `revert-finance/compoundor-js` | Keeper/bot orchestration ideas | License not visible in repo metadata | BLOCKED | No code import; only manual design comparison | Require explicit license confirmation |
| `Aperture-Finance/uniswap-v3-automan` | Rebalance automation patterns | BUSL-1.1 | REFERENCE_ONLY | Study keeper logic and safety guards | Source-available restrictions |
| `ArrakisFinance/v2-core` | Vault architecture and automation | AGPL-3.0 | REFERENCE_ONLY | Use vault/risk control concepts only | Copyleft obligations if copied |
| `GammaStrategies/hypervisor` | Active LP manager patterns | AGPL-3.0 | REFERENCE_ONLY | Reuse range-management ideas in spec/tests | Copyleft obligations if copied |
| `Uniswap/smart-order-router` | Swap pathing/slippage logic | GPL-3.0-or-later | REFERENCE_ONLY | Reuse routing heuristics at design level | GPL contamination risk if embedded |
| `hummingbot/hummingbot` | Hedge execution engine patterns | Apache-2.0 | ADAPT | Candidate base for isolated delta-hedger worker | Large framework, selective extraction only |
| `hummingbot/gateway` | Connector layer (DEX/CEX bridge) | Apache-2.0 | ADAPT | Candidate connector service for future hedger | Keep isolation boundary from core scout |
| `KrystalDeFi/v3utils` | Forked V3 utils and automation flows | License not visible in repo metadata | BLOCKED | Continue using our pinned adapter path only | Require explicit licensing + support confirmation |
| `code-423n4/2024-06-krystal-defi` | Security evidence (audit) | N/A (contest artifacts) | REFERENCE_ONLY | Input for threat model/checklist | Not an implementation dependency |

## 3. Immediate Integration Plan

1. Keep current execution implementation path: internal `ExecutionAdapter` contracts + local ABI pinning.
2. Continue Plan 019 with **pattern-level reuse** only from `v3utils`/`compoundor` (no direct AGPL/BUSL code import).
3. For delta hedger pre-phase, evaluate `hummingbot` as an **isolated service** candidate (adapter boundary, no coupling to scout runtime).
4. Treat `KrystalDeFi/v3utils` and `compoundor-js` as blocked until license status is explicitly confirmed.

## 4. Go/No-Go for Code Import

- `GO`: `hummingbot/*` (Apache-2.0), with minimal-scope extraction and adapter isolation.
- `CONDITIONAL`: any repo with declared permissive license but high integration complexity (requires PoC first).
- `NO-GO`: AGPL/GPL/BUSL repos for direct in-tree code import into core runtime.

## 5. Sources

- https://github.com/revert-finance/v3utils
- https://github.com/revert-finance/compoundor
- https://github.com/revert-finance/compoundor-js
- https://github.com/Aperture-Finance/uniswap-v3-automan
- https://github.com/ArrakisFinance/v2-core
- https://github.com/GammaStrategies/hypervisor
- https://github.com/Uniswap/smart-order-router
- https://github.com/hummingbot/hummingbot
- https://github.com/hummingbot/gateway
- https://github.com/KrystalDeFi/v3utils
- https://github.com/code-423n4/2024-06-krystal-defi
