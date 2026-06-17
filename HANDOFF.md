# pana — team handoff

A control + monitoring tool for the **Lenovo Legion 7 16IAX10**. CPU power/thermal
modes, battery charge limiting, keyboard lighting, and live temps/power — one CLI,
one tray applet, one root daemon.

## Install (any systemd Linux)

```bash
git clone <repo-url> legion-pana
cd legion-pana
sudo ./packaging/install.sh
pana status        # no sudo needed — shows what's supported on your machine
```

The installer is distro-aware (apt / dnf / pacman / zypper) for the couple of system
packages the tray needs. It drops a root daemon (`panad`), a group-owned socket so the
CLI/tray need no `sudo`, a login-autostart tray, and a Super-key launcher ("pana").

**Prereqs:** Python 3.12+, systemd. Tray needs a desktop session with an
AppIndicator/SNI host (on GNOME: the AppIndicator extension, which the installer's
GIR package pulls in).

## What you get

- `pana mode eco|balanced|performance` — CPU clock-ceiling ladder (cooler ↔ full power)
- `pana power <pct>` — custom CPU cap
- `pana battery --cap | --limit N | --off` — conservation / soft target / full charge
- `pana lights off|on|--color RRGGBB|--effect ...|--zone ...` — keyboard RGB
- `pana night on|off --start HH:MM --end HH:MM` — auto lights-off schedule
- `pana monitor` / `pana status` — live W / °C / clocks / battery
- Tray applet for all of the above (autostarts; find it via the Super key)

## Portability notes

- **Same laptop (16IAX10):** everything works — these are standard kernel interfaces
  (`intel_pstate`, `ideapad`/`platform_profile`, `coretemp`/RAPL) plus the USB keyboard
  controller, identical across distros.
- **Other distros / kernels:** the tool is pure-Python stdlib + a JSON socket, so it runs
  anywhere with Python 3.12 + systemd. It **feature-detects and degrades gracefully** — a
  missing interface greys out that feature, it never crashes. Run `pana status` to see the
  capability map on each machine.
- **Known limitation (all units, any OS):** the power-button LED is firmware-locked to the
  power mode and cannot be turned off in software — not a pana gap (even Lenovo's own
  Windows tools can't change it).

## Uninstall

```bash
sudo ./packaging/uninstall.sh   # keeps /etc/pana/config.toml + /var/lib/pana
```

## Layout

- `src/pana/hw/` — hardware controllers (sysfs + USB-HID), each feature-detecting
- `src/pana/core/` — presets, config/state, scheduler, battery watcher, monitor, manager
- `src/pana/ipc/` — the versioned JSON socket protocol (see `docs/PROTOCOL.md`)
- `src/pana/{daemon,cli,tray}.py` — the daemon and the two thin clients
- `docs/superpowers/` — the design spec + implementation plan
