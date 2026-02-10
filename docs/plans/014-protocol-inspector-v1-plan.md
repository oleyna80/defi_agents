# Technical Plan: Protocol Inspector v1 (Risk-First, Onchain Verifiability)

Refers to Spec: `docs/specs/014-protocol-inspector-v1.md`

## 1. Architecture Design

Components (v1):
- Entry point: `inspector_main.py` (separate from `main.py`)
- Resolver: `contract_set_resolver` (bounded acquisition pipeline)
- Onchain checker: `onchain_checks` (EIP-1967/proxy/roles/pause best-effort)
- Storage: minimal last-known snapshot store (file-based JSON)
- Output: Telegram report + optional JSON artifact on disk

Recommended deployment:
- new `systemd --user` oneshot service + timer (daily or hourly)
- runs in same repo/venv, using the same `.env` EnvironmentFile

## 2. API / Interface Changes

### Inputs

Config blocks (proposed):
- `inspector.enabled` (default false)
- `inspector.targets[]`:
  - `name`
  - `defillama_protocol_slug` (optional)
  - `defillama_yield_pool_id` (optional)
  - `chain_id` (required if seed address is provided)
  - `rpc_url` (optional override; prefer env-based mapping)
  - `seed_addresses[]` (optional)
- `inspector.budgets`:
  - max http requests
  - max rpc calls
  - explorer scan budget
  - rpc log inference: disabled by default

### Output

`Dossier v0` JSON stored under a dedicated folder:
- `data/inspector/<target_id>/latest.json`
- `data/inspector/<target_id>/prev.json`

Diff alert payload:
- only high-impact fields
- includes old/new short hashes and explorer links

## 3. File Structure Impact

Planned (v1):
- [+] `src/defi_agents/inspector/` module (resolver + checks + storage)
- [+] `docs/runbooks/protocol_inspector_v1_ops.md` (safe rollout + debug)
- [M] `docs/memory-bank/scout_config.json` (add `inspector` block, default disabled)
- [M] `src/defi_agents/notifier.py` (add compact inspector report rendering)
- [+] `tests/test_inspector_*` (bounded unit tests)

Note: no changes to existing systemd scheduler in Phase 1; new unit added later after spec approval.

## 4. Verification Strategy

- Unit tests:
  - EIP-1967 slot parsing and proxy detection
  - verdict rules (PARTIAL => WATCHLIST)
  - URL/key sanitization helpers
- Integration tests:
  - resolver pipeline ordering (mock sources)
  - diff detection (prev vs latest)
- Manual checks (VPS):
  - enable in config, run oneshot manually
  - confirm no secret leakage in `journalctl`
  - verify Telegram report formatting and diff alerts

## 5. Implementation Checklist

- [ ] Draft config schema and safe defaults (feature flag off)
- [ ] Implement Contract Set Resolver v1 (bounded)
- [ ] Implement Onchain Checks v1 (proxy/admin/roles/pause best-effort)
- [ ] Implement Dossier storage + diff alerts
- [ ] Implement Telegram report output + chunking compatibility
- [ ] Add unit/integration tests and run full suite
- [ ] Write ops runbook and safe rollout checklist
- [ ] Update Memory Bank and roadmap entries

