# pana wire protocol (v1)

The daemon (`panad`) and clients (`pana`, `pana-tray`) communicate over a Unix
domain socket using **newline-delimited JSON** — one JSON object per line. This
document is the contract: it is intentionally language-neutral so the daemon can
later be re-implemented in Rust without touching the clients (or vice versa).

- **Socket:** `/run/pana/pana.sock`, owned `root:<install-group>`, mode `0660`.
- **Framing:** one UTF-8 JSON object per line (`\n`-terminated). One request →
  one response. The connection may be reused or closed after each exchange.
- **Versioning:** every message carries an integer `version` (currently `1`).

## Request

```json
{"version": 1, "cmd": "<command>", "args": {<command-specific>}}
```

## Response

```json
{"version": 1, "ok": true,  "data": {<command-specific>}, "error": null}
{"version": 1, "ok": false, "data": {}, "error": "<message>"}
```

A malformed request line never drops the connection — it returns `ok:false`.

## Commands

| cmd | args | effect / data |
|-----|------|---------------|
| `ping` | — | `{"pong": true}` |
| `status` | — | full snapshot (see below) |
| `monitor` | — | `{"sample": <telemetry|null>}` (latest rolling sample) |
| `reapply` | — | re-applies persisted desired state; returns status |
| `mode` | `{"name": "eco"\|"balanced"\|"game"}` | apply a preset; returns status |
| `tdp` | `{"pl1"?: int, "pl2"?: int}` | enter custom profile, set clamped CPU limits |
| `battery` | `{"cap": true}` \| `{"target": int}` \| `{"off": true}` | conservation cap / soft target / charge-to-100 |
| `lights` | `{"on"?: bool, "brightness"?: 0-9, "color"?: [r,g,b]}` | control keyboard lighting |
| `night` | `{"enabled"?: bool, "clear"?: bool}` | toggle the night schedule / clear manual override |

### `status` data shape

```json
{
  "mode": "eco",
  "platform_profile": "low-power",
  "profile_choices": ["low-power", "balanced", "balanced-performance", "performance", "custom"],
  "ppt": {"ppt_pl1_spl": 0, "ppt_pl2_sppt": 0, "ppt_pl3_fppt": 0},
  "battery": {"conservation": false, "soft_target": null, "capacity": 65, "status": "Charging", "ac_online": true},
  "lights": {"available": true, "manual": null, "night_enabled": false},
  "monitor": {"cpu_power_w": 12.3, "cpu_temp_c": 63.0, "nvme_temps_c": [35.8], "battery": {...}, "ac_online": true, "cpu_freq_mhz": {"avg": 4110.4, "max": 5200.0}},
  "capabilities": {"power_modes": true, "ppt": true, "battery_conservation": true, ...}
}
```

## Porting to Rust

The seam is this protocol. To swap the daemon for a Rust binary:
1. Bind the same socket path, group, and mode.
2. Parse/emit the JSON shapes above (keep `version: 1`).
3. Re-implement the `hw/` controllers (sysfs writes + the Spectrum HID encoder
   in `hw/spectrum.py`) — these are the only OS-touching parts.
The Python `pana` / `pana-tray` clients are pure protocol consumers and continue
to work unchanged.
