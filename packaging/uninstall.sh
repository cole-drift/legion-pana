#!/usr/bin/env bash
# pana uninstaller — run with: sudo ./packaging/uninstall.sh
# Leaves /etc/pana/config.toml and /var/lib/pana/state.json in place.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "must run as root: sudo $0" >&2
    exit 1
fi

systemctl disable --now panad.service 2>/dev/null || true
rm -f /etc/systemd/system/panad.service
rm -f /etc/systemd/user/pana-tray.service
rm -f /usr/lib/systemd/system-sleep/pana
systemctl daemon-reload

for b in pana panad pana-tray; do
    rm -f "/usr/local/bin/$b"
done
rm -rf /opt/pana

echo "==> removed pana (config at /etc/pana and state at /var/lib/pana kept)"
