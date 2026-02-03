Systemd deployment (user mode, every 15 minutes):

1. Copy units:
   - `mkdir -p ~/.config/systemd/user`
   - `cp deploy/systemd/defi-sentinel.service ~/.config/systemd/user/`
   - `cp deploy/systemd/defi-sentinel.timer ~/.config/systemd/user/`
2. Reload and enable timer:
   - `systemctl --user daemon-reload`
   - `systemctl --user enable --now defi-sentinel.timer`
3. Check status:
   - `systemctl --user status defi-sentinel.timer`
   - `journalctl --user -u defi-sentinel.service -n 200 --no-pager`
