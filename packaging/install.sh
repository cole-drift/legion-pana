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

# Recreate the venv with --system-site-packages so the tray can reach the system
# PyGObject (gi); pystray's GNOME (AppIndicator) backend needs it, and a venv-pip
# PyGObject build is fragile. Harmless for the daemon (it only imports stdlib + pana).
rm -rf "$PREFIX"
python3 -m venv --system-site-packages "$PREFIX"
"$PREFIX/bin/pip" install --quiet --upgrade pip

# Self-contained, NON-editable install: code is copied into /opt/pana so the daemon
# (ProtectHome=yes) never needs /home. Build from a throwaway copy of just the build
# inputs so we never write root-owned artifacts into the user's repo (an in-tree
# build/ from a prior sudo run breaks every later build).
rm -rf "$SRC/build" "$SRC/src/pana.egg-info"   # purge any root-owned leftovers
BUILD_SRC="$(mktemp -d)"
cp -a "$SRC/pyproject.toml" "$SRC/src" "$BUILD_SRC/"
"$PREFIX/bin/pip" install --quiet --force-reinstall --no-deps "$BUILD_SRC"
rm -rf "$BUILD_SRC"

# Tray dependencies (best-effort: a headless/offline box still gets the daemon).
"$PREFIX/bin/pip" install --quiet pystray Pillow || echo "WARN: tray deps (pystray/Pillow) not installed"
# AppIndicator GIR typelib — without it pystray falls back to a backend GNOME won't show.
if command -v apt-get >/dev/null; then
    DEBIAN_FRONTEND=noninteractive apt-get install -y gir1.2-ayatanaappindicator3-0.1 >/dev/null 2>&1 \
        || echo "WARN: could not install gir1.2-ayatanaappindicator3-0.1 (tray icon may not appear)"
fi

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

# Enable + (re)start the per-user tray service so it picks up the new code/venv.
USER_UID="$(id -u "$USER_NAME")"
RUNTIME_DIR="/run/user/$USER_UID"
if [[ -d "$RUNTIME_DIR" ]]; then
    sudo -u "$USER_NAME" XDG_RUNTIME_DIR="$RUNTIME_DIR" systemctl --user enable pana-tray.service 2>/dev/null || true
    sudo -u "$USER_NAME" XDG_RUNTIME_DIR="$RUNTIME_DIR" systemctl --user restart pana-tray.service 2>/dev/null || true
fi

echo "==> done. Try:  pana status   (no sudo needed)"
echo "    Tray icon (purple dot, top-right) manages everything. If it's missing, log out/in once."
