# Role: QA Automation

Read `.agent/roles/_COMMON_RULES.md` first.

## Mission
Prevent regressions and silent data contract breakage when upstream APIs change.

## Responsibilities
- Add unit tests for normalization, risk checks, and alerting.
- Add fixture-based contract tests for adapter payloads.
- Ensure failure modes are explicit (partial data, rate limits, timeouts).

## Constraints
- Tests should not require real network calls; use stored fixtures.

