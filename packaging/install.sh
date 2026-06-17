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
# System deps the tray needs: PyGObject (so the venv's --system-site-packages can import
# gi) + the AppIndicator GIR typelib (without it pystray falls back to a backend GNOME
# won't render). Package names vary by distro — best-effort across the major families.
install_tray_sysdeps() {
    if command -v apt-get >/dev/null; then
        DEBIAN_FRONTEND=noninteractive apt-get install -y python3-gi gir1.2-ayatanaappindicator3-0.1
    elif command -v dnf >/dev/null; then
        dnf install -y python3-gobject libayatana-appindicator-gtk3
    elif command -v pacman >/dev/null; then
        pacman -S --needed --noconfirm python-gobject libayatana-appindicator
    elif command -v zypper >/dev/null; then
        zypper --non-interactive install python3-gobject typelib-1_0-AyatanaAppIndicator3-0_1
    else
        echo "WARN: unknown package manager — install PyGObject + the AppIndicator GIR manually"
        return 0
    fi
}
install_tray_sysdeps >/dev/null 2>&1 || echo "WARN: tray system deps not installed (icon may not appear; daemon/CLI unaffected)"

for b in pana panad pana-tray; do
    ln -sf "$PREFIX/bin/$b" "/usr/local/bin/$b"
done

install -d -m755 /etc/pana /var/lib/pana
if [[ ! -f /etc/pana/config.toml ]]; then
    install -m644 "$SRC/packaging/config.example.toml" /etc/pana/config.toml
fi

sed "s/@GROUP@/$GROUP/" "$SRC/packaging/panad.service.in" > /etc/systemd/system/panad.service
install -m755 "$SRC/packaging/pana-sleep-hook.sh" /usr/lib/systemd/system-sleep/pana

systemctl daemon-reload
systemctl enable panad.service
# restart (not `enable --now`) so unit + code changes apply even on re-runs of an
# already-running daemon; restart also starts it if it was stopped.
systemctl restart panad.service

# Tray: a .desktop launcher (Super-key search) + autostart on login for every user.
# (A freedesktop autostart entry is more reliable than `systemctl --user enable` and
# avoids the per-session XDG_RUNTIME_DIR dance.)
install -d -m755 /usr/share/applications /etc/xdg/autostart
install -m644 "$SRC/packaging/pana.desktop" /usr/share/applications/pana.desktop
install -m644 "$SRC/packaging/pana.desktop" /etc/xdg/autostart/pana.desktop
update-desktop-database /usr/share/applications 2>/dev/null || true
# launch the tray now for the installing user (best-effort; it autostarts next login)
USER_UID="$(id -u "$USER_NAME")"
if [[ -d "/run/user/$USER_UID" ]]; then
    sudo -u "$USER_NAME" DISPLAY=:0 XDG_RUNTIME_DIR="/run/user/$USER_UID" \
        nohup /usr/local/bin/pana-tray >/dev/null 2>&1 &
fi

echo "==> done. 'pana status' (no sudo). Tray autostarts on login; or press Super and type 'pana'."
