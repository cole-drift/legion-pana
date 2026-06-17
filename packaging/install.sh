#!/usr/bin/env bash
# pana installer — run with: sudo ./packaging/install.sh
# Installs into a dedicated venv at /opt/pana (avoids Ubuntu 24.04 PEP-668),
# symlinks the binaries, installs+enables the root systemd daemon, and a
# resume hook. The socket is group-owned by the installing user's group so
# you drive it without sudo.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "must run as root: sudo $0" >&2
    exit 1
fi

USER_NAME="${SUDO_USER:-$USER}"
GROUP="$(id -gn "$USER_NAME")"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PREFIX=/opt/pana

echo "==> installing pana from $SRC for user $USER_NAME (group $GROUP)"

python3 -m venv "$PREFIX"
"$PREFIX/bin/pip" install --quiet --upgrade pip
# editable so re-running this (or `git pull`) updates the code in place — a plain
# `pip install "$SRC"` is a no-op when the version is unchanged, leaving stale code.
"$PREFIX/bin/pip" install --quiet -e "$SRC"

for b in pana panad pana-tray; do
    ln -sf "$PREFIX/bin/$b" "/usr/local/bin/$b"
done

install -d -m755 /etc/pana /var/lib/pana
if [[ ! -f /etc/pana/config.toml ]]; then
    install -m644 "$SRC/packaging/config.example.toml" /etc/pana/config.toml
fi

sed "s/@GROUP@/$GROUP/" "$SRC/packaging/panad.service.in" > /etc/systemd/system/panad.service
install -m755 "$SRC/packaging/pana-sleep-hook.sh" /usr/lib/systemd/system-sleep/pana
install -d -m755 /etc/systemd/user
install -m644 "$SRC/packaging/pana-tray.service" /etc/systemd/user/pana-tray.service

systemctl daemon-reload
systemctl enable panad.service
# restart (not `enable --now`) so unit + code changes apply even on re-runs of an
# already-running daemon; restart also starts it if it was stopped.
systemctl restart panad.service

echo "==> done. Try:  pana status   (no sudo needed)"
echo "    Optional tray:  sudo $PREFIX/bin/pip install pystray Pillow && systemctl --user enable --now pana-tray"
