# Specification: Pipeline Relaxation v1 (Scout Funnel + Lindy)

Status: APPROVED
Owner: Tech Lead / Architect
Related Memory: `docs/memory-bank/activeContext.md`
Date: 2026-02-04

## 1. Context & Business Value
Production is stable (v3.6), but Scout produces `0` candidates due to:
- limited audit slice + missing `chain_id`/`address` for many high-APY pools,
- overly strict security gating on missing audit/reputation signals,
- lack of funnel visibility ("why 0?").

We need to increase useful signal without degrading anti-scam guarantees.

## 2. User Stories
- As an operator, I want to see *why* candidates drop at each stage, so I can tune safely.
- As a user, I want the bot to surface high-TVL stable opportunities even if audits are not perfect, but with clear warnings.
- As a security-first system, I want hard-scam indicators to remain non-bypassable.

## 3. Functional Requirements

### REQ-001: Funnel Observability (Stage Metrics)
The system must emit per-cycle funnel metrics:
`raw_pools → heuristics_pass → addressable (address+chain_id) → audited → security_pass/warn/block/unknown → l3_processed → final_picks`.

The system must also emit top rejection reasons:
- `missing_chain_id` count
- `missing_address` count
- top `SecurityReason.code` for `BLOCK/WARN`

### REQ-002: Intake Expansion (Safe)
The system must increase the audit slice size (configurable) and prioritize candidates:
1) stable/stable and stable-leaning pools,
2) higher TVL,
3) then APY/yield-quality.

### REQ-003: Chain Mapping Expansion (EVM v1)
The system must expand `chain_id_map` to cover common EVM networks beyond current defaults.

Non-EVM chains must not fail silently: candidates must be counted and reported as unsupported for L1/L2 security until dedicated adapters exist.

### REQ-004: Lindy v1 (Audit/Reputation Soften-Only)
Introduce a deterministic "Lindy v1" rule that can *soften only missing-audit / missing-reputation signals*:
- thresholds: `TVL >= $100M` and `age >= 180 days`
- effect: downgrade "missing top-tier audit / no audits found / reputation unavailable" gating from `BLOCK` to `WARN`
- output: candidate appears only in `LINDY/WARN` bucket (manual review), not `SAFE`

Lindy must never bypass critical technical red flags (honeypot, hidden owner, extreme taxes, etc.).

### REQ-005: Output Buckets (No Operator Deception)
The system must produce two explicit output buckets:
- `SAFE` (strict)
- `LINDY/WARN` (explicitly risk-tagged; manual review)

### REQ-006: Policy Matrix SSOT
The decision rules above must be captured as a single source of truth document:
- `docs/memory-bank/security/policy_matrix_v1.md`

## 4. Non-Functional Requirements
- Reliability: no silent fallback in production; failures must surface via systemd non-zero exit (already enforced).
- Security: SSRF defenses and critical tech flags remain hard blocks; Lindy cannot override them.
- Operability: metrics must be readable from logs and/or persisted artifact.

## 5. Constraints
- Tech stack: Python async + external REST APIs.
- Maintain single-scheduler invariant (VPS systemd is primary; GitHub schedule disabled).
- Avoid breaking existing working pipeline.

## 6. Out of Scope
- Full non-EVM security adapters (Solana/Sui/Aptos scanners).
- Execution/tx building.
- Full reputation registry (Traffic Light) (planned in Phase 3).

## 7. Acceptance Criteria
- AC-001: Daily operations are no longer "silent": funnel metrics explain `0` outcomes.
- AC-002: The system yields `>0` candidates on a regular basis (at least `WARN` bucket) under normal market conditions.
- AC-003: No candidate with critical tech flags can enter `SAFE` or `LINDY/WARN`.
- AC-004: Non-EVM pools are visible in metrics as "unsupported", not silently dropped.

## 8. Risks / Open Questions
- What exact field is used for `age` (pool age vs contract age proxy) must be defined and consistent.
- Need to avoid noisy Telegram output; heartbeat and reporting format to be tuned separately if needed.

## Approvals
- [x] User Approved (explicit agreement in chat)
- [x] Architecture Approved
