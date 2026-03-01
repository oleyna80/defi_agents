# Runbooks Index

Purpose: single entrypoint for operational and design runbooks in `docs/runbooks/`.

## 1) Operational Runbooks (active)

| File | Scope | Use when |
|---|---|---|
| `docs/runbooks/execution-loop-rollout-v1.md` | Spec 018 execution loop rollout (`PAPER -> SHADOW -> LIVE`) | You enable or validate execution loop on VPS |
| `docs/runbooks/hedger-shadow-rollout-v1.md` | Plan 020 isolated hedger worker 24h SHADOW gate | You run `defi-hedger` gate and inspect connector/sim counters |
| `docs/runbooks/lp-shadow-rollout-v1.md` | LP Decision Engine SHADOW mode rollout (Telegram shadow channel + smoke) | You enable LP shadow reporting and `/recheck` |
| `docs/runbooks/protocol_inspector_v1_ops.md` | Protocol Inspector v1 rollout/debug checklist | You activate inspector timer or triage inspector issues |
| `docs/runbooks/strategy_sim_v1_ops.md` | Strategy Simulator v1 safe activation and debugging | You enable simulator without report noise regressions |
| `docs/runbooks/shadow-gate-real-positions-v1.md` | Gate checklist for real on-chain positions in SHADOW | You switch from mock positions to wallet-backed position reads |

Notes:
- `protocol_inspector_v1_ops.md` is marked `Status: DRAFT` in the file.
- Treat these as action-oriented docs for VPS/runtime procedures.

## 2) Design / Research Artifacts (reference)

| File | Scope | Role |
|---|---|---|
| `docs/runbooks/Tick Density Scanner.md` | Early design + multi-review thread for tick-density concept | Historical context and rationale, not current rollout source |
| `docs/runbooks/low_competition_pool_finder_discussion.md` | Long-form design discussion for LP scoring/competition logic | Architecture debate and decision history |
| `docs/runbooks/low_competition_pool_finder_discussion_gemini_review.md` | Focused Gemini critical review | Companion critique referenced by discussion doc |

## 3) Product Program Docs (LP Operating System)

| File | Scope | Role |
|---|---|---|
| `docs/runbooks/LP_OS_Prompt_NewChat.md` | Project context prompt for new AI chat/session | Onboarding/context bootstrap |
| `docs/runbooks/LP_OS_Анализ_Ревью_v1.md` | Review analysis of LP_OS technical assignment | Gap analysis and blocker mapping |
| `docs/runbooks/LP_OS_ТехЗадание_v1.1.md` | LP Operating System technical assignment v1.1 | Current detailed product/architecture document |
| `docs/runbooks/LP_OS_ТехЗадание_v1.0.md` | LP Operating System technical assignment v1.0 | Legacy baseline version |

## 4) Export / Binary Artifacts

| File | Type | Notes |
|---|---|---|
| `docs/runbooks/LP_OS_ТехЗадание_v1.0.docx` | Binary DOCX | Editable office-format counterpart of v1.0 stream |
| `docs/runbooks/LP_OS_ТехЗадание_v1.1.docx` | Binary DOCX | Editable office-format counterpart of v1.1 stream |
| `docs/runbooks/output.html` | HTML export | Rendered export artifact (do not treat as canonical source) |
| `docs/runbooks/v1.0.html` | HTML export | Rendered export artifact (do not treat as canonical source) |

## 5) Source-of-Truth Rules

- For operational rollout decisions, prefer phase-linked runbooks in section 1.
- For LP Operating System architecture text, prefer `LP_OS_ТехЗадание_v1.1.md`.
- Do not edit `.docx`/`.html` export artifacts directly when `.md` source exists.
