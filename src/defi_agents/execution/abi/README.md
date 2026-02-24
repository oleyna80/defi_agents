# v3utils ABI Bundle (Pinned)

This directory contains pinned ABI/address snapshots for the `v3utils` execution adapter track.

Source of truth:
- Repo: `https://github.com/KrystalDeFi/v3utils`
- Commit: `33f487253051c3d6f439dc911b0e415b28b4cc9c`

Files:
- `v3utils_execute.abi.json` - ABI for `V3Utils.execute(...)` entrypoint.
- `v3automation_execute.abi.json` - ABI for `V3Automation.execute(...)` + cancel/read helpers.
- `v3utils_contracts.json` - upstream chain-to-contract mapping snapshot (`contracts.json` from pinned commit).
- `v3utils.lock.json` - lock metadata (upstream commit + local generation note).

Generation note:
- Full contract compilation was not used for ABI extraction in this environment.
- ABI was generated from interface-compatible signatures matching upstream public entrypoints.
