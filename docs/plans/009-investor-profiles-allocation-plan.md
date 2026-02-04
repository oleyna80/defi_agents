# Technical Plan: Investor Profiles & Allocation Engine v1

Refers to Spec: `docs/specs/009-investor-profiles-allocation.md`

## 1. Architecture Design
- Components:
  - Profile config loader
  - Sleeve allocator
  - Capacity guard evaluator
  - Report enricher (sleeve + benchmark tags)
- Data flow:
  - Scout candidate -> security pass/warn -> profile-aware scoring -> sleeve assignment -> output filtering.

## 2. API / Interface Changes
### New or Updated Interfaces
```text
InvestorProfileConfig
SleeveConfig
AllocationDecision { sleeve, reason_codes, benchmark_delta, capacity_ok }
```

### Data Models
- `investor_profile`:
  - initial_capital_usd, monthly_contribution_usd, risk_profile, horizon_days, benchmark_apy
- `sleeves`:
  - core_safe_pct, yield_plus_pct, tactical_high_apy_pct
  - tactical_enabled

## 3. File Structure Impact
- [M] `src/defi_agents/scout/config.py` (profile + sleeves schema)
- [M] `src/defi_agents/scout/scout.py` (profile-aware scoring and capacity filters)
- [M] `src/defi_agents/notifier.py` (include sleeve/benchmark tags in messages)
- [M] `docs/memory-bank/scout_config.json` (new profile/sleeve config block)
- [+] optional `src/defi_agents/profile.py` (allocation helper)

## 4. Verification Strategy
- Unit tests:
  - profile-specific filtering (`micro` vs `whale`)
  - capacity guards (`max_position_pct_of_tvl`)
  - benchmark classification (`above_benchmark`)
- Integration:
  - one cycle run with synthetic profile configs ensuring sleeve split works
- Manual:
  - verify Telegram output includes sleeve + benchmark tag

## 5. Implementation Checklist
- [ ] Add profile/sleeve schema to config and defaults.
- [ ] Implement capacity guards in candidate evaluation.
- [ ] Add benchmark comparison and report tags.
- [ ] Implement tactical sleeve gating + limits.
- [ ] Add tests and update docs/memory-bank.

