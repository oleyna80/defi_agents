# VPS Subdomain Deployment Pack

This folder contains production-ready templates to move Sentinel to a VPS under a subdomain.

## Important
- Sentinel currently runs as a scheduled bot (`main.py` + systemd timer).
- A subdomain is optional for polling mode, but required if you later add webhook/API endpoints.

## Contents
- `env.vps.example` - clean environment template for VPS
- `nginx/defi-sentinel.subdomain.conf.example` - reverse-proxy template for a subdomain
- `preflight.sh` - pre-deploy sanity checks (env, files, DNS)

## Recommended Cutover Steps
1. Provision VPS and install runtime deps (`python3.12`, `venv`, `nginx`, `certbot`).
2. Copy project to `%h/projects/defi_agents`.
3. Copy `env.vps.example` to `.env` and fill real values.
4. Run `./deploy/vps/preflight.sh`.
5. Enable bot timer:
   - `mkdir -p ~/.config/systemd/user`
   - `cp deploy/systemd/defi-sentinel.service ~/.config/systemd/user/`
   - `cp deploy/systemd/defi-sentinel.timer ~/.config/systemd/user/`
   - `systemctl --user daemon-reload`
   - `systemctl --user enable --now defi-sentinel.timer`
6. (Optional) Configure subdomain + TLS with nginx/certbot using template.
7. Validate logs and first cycle results.

## Smoke Checks
- `systemctl --user status defi-sentinel.timer`
- `journalctl --user -u defi-sentinel.service -n 200 --no-pager`
- `tail -n 50 docs/memory-bank/history.csv`
