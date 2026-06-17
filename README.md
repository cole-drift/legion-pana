# legion-pana (`pana`)

A personal control + monitoring tool for the **Lenovo Legion 7 16IAX10**. Pure-Python, no kernel module.

- **Modes (CPU clock ladder)**: `pana mode eco` (50%) · `balanced` (80%) · `performance` (100%); `pana power 65` for a custom cap. Battery/lights are *not* bundled into modes.
- **Battery**: `pana battery --cap` (firmware cap) / `--limit 85` (soft target) / `--off`
- **Lights**: `pana lights off|on|--brightness 0-9|--color RRGGBB|--effect static|rainbow|breathe`
- **Night auto-off**: `pana night on|off|clear` · `pana night --start 21:30 --end 06:30`
- **Monitor**: `pana monitor` (live W / °C / battery), `pana status`

## Architecture

A root daemon (`panad`) owns all hardware writes (sysfs power limits + battery
conservation + USB-HID Spectrum lighting) and runs the monitor sampler, battery
watcher, and night scheduler. Thin clients (`pana` CLI, `pana-tray`) drive it
over a group-owned Unix socket — no `sudo` per command. The JSON socket protocol
([docs/PROTOCOL.md](docs/PROTOCOL.md)) is the language boundary for a future Rust port.

## Install

```bash
git clone https://github.com/cole-drift/legion-pana
cd legion-pana
sudo ./packaging/install.sh      # venv at /opt/pana, root daemon, group-owned socket
pana status                      # works without sudo — shows what's supported on your box
```

The installer is distro-aware (apt / dnf / pacman / zypper) for the tray's system deps,
and sets up a **login-autostart tray** plus a **Super-key launcher** (press Super, type
"pana"). Uninstall with `sudo ./packaging/uninstall.sh`.

## More

- **[HANDOFF.md](HANDOFF.md)** — team / multi-machine install + portability notes.
- `docs/superpowers/specs/` + `docs/superpowers/plans/` — design spec + implementation plan.
- `docs/PROTOCOL.md` — the JSON socket protocol (the language boundary for a future Rust port).
- Fans/RPM are out of scope (no kernel support on this model yet); the power-button LED is
  firmware-locked and can't be controlled in software (even Lenovo's Windows tools can't).

## License

MIT — see [LICENSE](LICENSE).
