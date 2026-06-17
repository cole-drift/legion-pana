# legion-pana (`pana`)

A personal control + monitoring tool for the **Lenovo Legion 7 16IAX10**, tuned
for off-grid / hot-climate / solar use. Pure-Python, no kernel module.

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
sudo ./packaging/install.sh      # venv at /opt/pana, enables the panad service
pana status                      # works without sudo
```

See `docs/superpowers/specs/` for the design and `docs/superpowers/plans/` for the
implementation plan. Fans/RPM are out of scope (no kernel support on this model yet).
