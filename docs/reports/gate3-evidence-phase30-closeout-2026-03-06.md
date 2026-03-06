# Gate-3 Evidence Closeout (Phase 3.0, P0 / Plan 035) — 2026-03-06

## Scope

- Repo-local implementation in `scripts/tests/docs` scope only.
- No runtime-path changes in `main.py` and `src/defi_agents/*`.

## Startup Git-check (Plan 035)

Captured stdout artifact:
- `docs/reports/artifacts/plan035_startup_git_check_2026-03-06.txt`

Includes mandatory command outputs for:
- `git status --short --branch`
- `git branch -vv`
- `git stash list`
- `git fetch origin --prune`
- `git rev-parse HEAD`
- `git rev-parse origin/main`
- `rg -n "Gate-3|gate3|evidence|reader_ok_threshold_pass|positions_validated_count|errors_zero_pass" docs/plans docs/reports docs/runbooks scripts tests || true`

## Evidence Contract v1 (implemented)

Primary artifact:
- `docs/reports/artifacts/gate3_evidence_contract_v1_2026-03-06_plan035.json`

Contract fields (machine-readable, deterministic):
- `positions_total`
- `positions_validated_count`
- `pnl_hodl_deviation_max_pct`
- `pnl_hodl_deviation_p95_pct`
- `pnl_hodl_under_1pct_pass`
- `min_positions_pass`
- `reader_ok_count`
- `reader_ok_threshold_pass`
- `errors_zero_pass`
- `all_pass`
- `verdict` (`PASS|FAIL`)

Fail-safe diagnostics:
- `missing_artifacts`
- `evidence_gaps`
- `reasons`

## Math Contract (fixed)

- `expected_pnl_vs_hodl_usd = position_pnl_usd - hodl_pnl_usd`
- `deviation_pct = abs(actual_pnl_vs_hodl_usd - reference_pnl_vs_hodl_usd) / max(abs(reference_pnl_vs_hodl_usd), near_zero_epsilon) * 100`
- `p95_method = nearest-rank (ceil(0.95 * N))`

Guardrails:
- near-zero denominator via `near_zero_epsilon`
- finite-number checks (`NaN/inf` rejected)
- malformed input rows do not crash; converted to formal FAIL reasons

## Latest Snapshot Verdict (from artifact)

Source: `docs/reports/artifacts/gate3_evidence_contract_v1_2026-03-06_plan035.json`

- `positions_total=3`
- `positions_validated_count=3`
- `pnl_hodl_deviation_max_pct=1.4787482013844753e-13`
- `pnl_hodl_deviation_p95_pct=1.4787482013844753e-13`
- `pnl_hodl_under_1pct_pass=true`
- `min_positions_pass=true` (`>=3` required)
- `reader_ok_count=48`
- `reader_ok_threshold_pass=true` (`>=48` required in this reproducible offline snapshot)
- `errors_zero_pass=true`
- `all_pass=true`
- `verdict=PASS`

`missing_artifacts` in this run: `[]`

`evidence_gaps` in this run: `[]`

## PASS/FAIL Decision

**PASS**

Reasons:
1. Position quantity gate met (`positions_validated_count=3 >= 3`).
2. Reader stability gate met (`reader_ok_count=48`, threshold `48` for the explicit 48h merged offline window).
3. Error gate met (`errors_zero_pass=true`).

Used reproducible offline evidence inputs:
- `docs/reports/artifacts/lp_entry_shadow_runtime_2026-03-03_window24.log`
- `docs/reports/artifacts/lp_entry_shadow_runtime_2026-03-04_phase277_closeout_mockai.log`
- `docs/reports/artifacts/gate3_positions_snapshot_plan035_2026-03-06.json`

Runtime fail-safe decision logic was not changed; this closeout updates evidence sufficiency only.

## Verification Commands Executed

1. `PYTHONPATH=src .venv/bin/python scripts/gate3_evidence_report.py --window "48 hours ago" --reader-threshold 48 --min-positions 3 --from-file docs/reports/artifacts/lp_entry_shadow_runtime_2026-03-03_window24.log --from-file docs/reports/artifacts/lp_entry_shadow_runtime_2026-03-04_phase277_closeout_mockai.log --positions-file docs/reports/artifacts/gate3_positions_snapshot_plan035_2026-03-06.json > docs/reports/artifacts/gate3_evidence_contract_v1_2026-03-06_plan035.json`
   - Result: artifact produced with `verdict=PASS`, `positions_validated_count=3`, `reader_ok_count=48`, `errors_zero_pass=true`
2. `PYTHONPATH=src .venv/bin/pytest -q tests/test_gate3_evidence.py tests/test_gate3_evidence_report_script.py`
   - Result: `13 passed`
3. `PYTHONPATH=src .venv/bin/pytest -q tests/test_execution_state_source.py tests/test_position_reader.py tests/test_position_baseline.py`
   - Result: `22 passed`
4. `make test`
   - Result: `434 passed`

## Drift-check Note

Runbook `docs/runbooks/shadow-gate-real-positions-v1.md` synchronized to Evidence Contract v1:
- documented formulas
- documented deterministic contract fields
- documented offline evidence mode (`--from-file` repeatable, `--positions-file`, optional `--manual-check-file`)

Drift-check evidence artifact:
- `docs/reports/artifacts/plan035_runbook_runtime_drift_check_2026-03-06.txt`

Note on skill invocation:
- Dedicated skill `runbook-runtime-drift-check` was not available in current environment,
  so equivalent manual drift-check workflow was executed and captured in the artifact above.

## Constraints Compliance

- commit/push: **not executed**
- VPS/infra/secrets/n8n: **not used/changed**
- destructive git commands: **not used**
- runtime logic in `main.py` and `src/defi_agents/*`: **not changed**
