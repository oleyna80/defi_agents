Systemd deployment (user mode, every 15 minutes):

1. Copy units:
   - `mkdir -p ~/.config/systemd/user`
   - `cp deploy/systemd/defi-sentinel.service ~/.config/systemd/user/`
   - `cp deploy/systemd/defi-sentinel.timer ~/.config/systemd/user/`
   - Optional hedger PoC:
     - `cp deploy/systemd/hummingbot-shadow-mock.service ~/.config/systemd/user/`
     - `cp deploy/systemd/defi-hedger.service ~/.config/systemd/user/`
     - `cp deploy/systemd/defi-hedger.timer ~/.config/systemd/user/`
2. Reload and enable timer:
   - `systemctl --user daemon-reload`
   - `systemctl --user enable --now defi-sentinel.timer`
   - Optional hedger PoC:
     - `systemctl --user enable --now hummingbot-shadow-mock.service`
     - `systemctl --user enable --now defi-hedger.timer`
3. Check status:
   - `systemctl --user status defi-sentinel.timer`
   - `journalctl --user -u defi-sentinel.service -n 200 --no-pager`
   - Optional hedger PoC:
     - `systemctl --user status hummingbot-shadow-mock.service`
     - `journalctl --user -u hummingbot-shadow-mock.service -n 200 --no-pager`
     - `systemctl --user status defi-hedger.timer`
     - `journalctl --user -u defi-hedger.service -n 200 --no-pager`
