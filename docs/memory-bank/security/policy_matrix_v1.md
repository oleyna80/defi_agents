# Security Policy Matrix v1 (SSOT)

Date: 2026-02-04
Status: ACTIVE
Scope: Scout (Discovery) candidate screening + reporting buckets.

This document is the single source of truth for how we classify candidates into:
- `BLOCK` (drop)
- `WARN` (reportable, manual review)
- `SAFE` (reportable, conservative shortlist)
- `UNSUPPORTED` (not evaluable by current adapters; visible in metrics only)

## 1) Core Principles (Invariants)
1. **No silent drops:** if a candidate is excluded due to missing inputs (e.g., non-EVM), it must appear in funnel metrics as a counted rejection reason.
2. **Hard tech flags are non-bypassable:** no policy (including Lindy) can override critical technical scam indicators.
3. **Reputation availability != reputation verdict:** if Stage B reputation provider is unavailable, do not treat it as "no audits found".
4. **Two-bucket reporting:** user-facing output is split into `SAFE` and `WARN/LINDY` (manual review).

## 2) Definitions
- **Addressable (EVM):** candidate has `chain_id` and `address` suitable for L1/L2 scanning.
- **Hard tech flags:** any GoPlus reason with CRITICAL severity or explicit scam codes.
- **Lindy v1:** deterministic soften-only rule for missing audit/reputation signals:
  - `TVL >= $100M` and `age >= 180d`
  - effect: missing audit/reputation gates may be downgraded from `BLOCK` to `WARN`
  - never bypasses hard tech flags

## 3) Decision Order (Pipeline)
Order matters; apply rules top-to-bottom.

### Step 0: Addressability
- If `address` missing OR `chain_id` missing for required adapters:
  - Decision: `UNSUPPORTED`
  - Action: count + log reason (`missing_address` / `missing_chain_id`)
  - Output: not included in Telegram `SAFE/WARN`

### Step 1: Hard BLOCK (Tech Scam / Critical Risk)
BLOCK immediately if any of the following are present:
- GoPlus: `HONEYPOT_DETECTED`
- GoPlus: `HIDDEN_OWNER` (high risk)
- GoPlus: `HIGH_TAX` above block threshold (project threshold)
- Any reason with `SecuritySeverity.CRITICAL`
- De.Fi reputation: recent rekt/exploit without post-incident top-tier audit (if data available)

### Step 2: Soft Risks (WARN)
If not BLOCK and any of the following are present, classify as WARN:
- Proxy/upgradeability flags (e.g., `PROXY_CONTRACT`)
- Missing top-tier audit (`NO_TOP_TIER_AUDIT`)
- No audits found (`NO_AUDITS_FOUND`) (only when reputation data is available)
- Reputation provider unavailable (`REPUTATION_UNAVAILABLE`)
- Unidentified protocol (`UNIDENTIFIED_PROTOCOL`) (data available, but unresolved slug/name)

### Step 3: SAFE
SAFE is allowed only if:
- No hard tech flags
- Reputation signals are acceptable (top-tier audit or equivalent explicit allowlist)
- Candidate passes Scout heuristics (stable-first, non-anomalous by configured rules)

If SAFE conditions are not met but candidate is not BLOCK, it remains WARN.

## 4) Lindy v1 (Soften-Only) Matrix
If candidate is currently `BLOCK` due to missing-audit / missing-reputation signals only:
- AND `TVL >= $100M`
- AND `age >= 180d`
- AND no hard tech flags
Then:
- Decision becomes `WARN`
- Add reason `LINDY_SOFTENED`
- Output bucket: `WARN/LINDY` only

This rule must not change `BLOCK` when hard tech flags are present.

## 5) Reporting Buckets (Telegram)
- `SAFE` bucket:
  - Conservative shortlist (high confidence).
- `WARN/LINDY` bucket:
  - Explicitly risk-tagged shortlist; manual review required.
  - Must include reason codes (at least top 1-3) and net profit estimate.

## 6) Notes / Open Items
- Age source must be consistent and documented (pool age vs contract age proxy).
- Thresholds (`TVL`, `age`) may be tuned in v1.1 based on funnel metrics; changes must bump policy version.

