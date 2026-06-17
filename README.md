# legion-pana (`pana`)

A personal control + monitoring tool for the **Lenovo Legion 7 16IAX10**, tuned
for off-grid / hot-climate / solar use. Pure-Python, no kernel module.

- **Run cool**: `pana mode eco` (low CPU power → less heat & draw) ↔ `pana mode game`
- **Custom TDP**: `pana tdp --pl1 50 --pl2 60` (clamped; enters custom profile)
- **Battery**: `pana battery --cap` (firmware cap) / `--limit 85` (soft target) / `--off`
- **Lights**: `pana lights off|on|--brightness N|--color RRGGBB`; `pana night on|off|clear`
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
