# `pana` — Lenovo Legion 7 16IAX10 control + monitoring tool

**Date:** 2026-06-17
**Status:** Approved design, pre-implementation
**Target hardware:** Lenovo Legion 7 16IAX10 (DMI product `83KY`, board `LNVNB161216`, BIOS `RXCN27WW`), Intel Core Ultra 9 275HX (Arrow Lake-HX) + NVIDIA dGPU, Ubuntu 24.04.4, kernel 6.17.0-35-generic.

---

## 1. Purpose & motivation

A personal control + monitoring tool for one specific laptop, tuned for **off-grid, hot-climate, solar-powered** use (no AC in Panama). Three concrete goals plus monitoring:

1. **Run cool & power-efficient** — cap CPU power to reduce heat and battery draw, with a one-flip switch to full performance for gaming.
2. **Protect battery longevity** — charge limiting suited to living on solar.
3. **Control the lights** — kill the keyboard/perimeter glow at night (scheduled + manual).
4. **Monitor usage** — live power draw, temps, and battery, so the effect of the cooling levers is visible.

This is **not** a clone of LenovoLegionLinux (LLL). LLL is already installed here but its fan stack is dead on this 2025 model (its DKMS `legion_laptop` loads but binds no device / creates no fan hwmon). `pana` deliberately targets only what this machine can actually do, above the EC, through interfaces that already exist — **no kernel module**.

## 2. Hardware reality (verified by recon + local probing)

What the machine exposes, and the constraints that shaped the design:

| Capability | Status | Mechanism |
|---|---|---|
| Power modes | ✅ | `platform_profile` (`low-power`/`balanced`/`balanced-performance`/`performance`/`custom`), provider `lenovo-wmi-gamezone` |
| CPU power limits (TDP) | ✅ | `firmware-attributes/lenovo-wmi-other-0/attributes/ppt_pl1_spl` (default 70, **50–110 W**), `ppt_pl2_sppt` (default 125, **60–168 W**). `ppt_pl3_fppt` has empty min/max here → **do not write**. |
| Battery charge limiting | ⚠️ fixed cap only | Binary conservation toggle via `ideapad_laptop`: `BAT0/charge_types` (`Standard`/`Long_Life`) or legacy `VPC2004:00/conservation_mode` (0/1). Firmware-fixed cap (~60–80%, exact value unknown until measured). **No** `charge_control_end_threshold` / `charge_behavior` anywhere → arbitrary sub-cap % is physically impossible. |
| Keyboard / perimeter / logo lighting | ✅ | Lenovo **Spectrum** HID protocol over `hidraw`, 960-byte feature reports (report id `0x07`, header `[0x07, op, 0xC0, 0x03]`). Devices `048d:c197` (primary, per the only working reference impl) and `048d:c193` (sibling) — **both expose the Spectrum signature; correct device chosen empirically at runtime.** |
| Power-button LED | ❌ arbitrary color impossible | Firmware-locked **status** LED: white=quiet, blue=balanced, red=performance. Changes only with `platform_profile`. Not addressable via the lighting controller. |
| Fan RPM / fan curves | ❌ not feasible now | No `fan*_input` hwmon on kernel 6.17 for this model. Needs unmerged upstream patches (lenovo-wmi-other HWMON series, or the `yogafan` driver targeting Linux 7.1). Out of scope. |
| Sensors for monitoring | ✅ | `coretemp` (CPU temps), `nvme` temps, `intel-rapl` `energy_uj` (CPU package power), `BAT0/power_now` + `capacity` + `status` + `cycle_count`, `ADP0/online`, cpufreq, optional `nvidia-smi`. |

### Two constraints surfaced to the user and accepted

- **Power-button color** can't be set arbitrarily, but it **follows the power mode** — so Eco→white, Balanced→blue, Game→red is obtained for free from mode switching. The bright stuff at night (keyboard + perimeter) *is* fully killable.
- **Battery** can't hold a target *below* the firmware cap. The cap (~60–80%) is hardware-enforced, survives crashes/reboots, and is the ideal longevity range for solar. A soft daemon adds the ability to hold a chosen target *at or above* the cap with hysteresis.

### Critical operational gotchas (must be honored by the implementation)

- **PPT requires `custom` mode first.** `ppt_pl*` writes only take effect when `platform_profile=custom`. In any other profile the BIOS owns the limits and writes silently no-op; switching to a non-custom profile afterward makes the BIOS clobber them. `current_value=0` today reflects a live WMI getter in non-custom mode, not a stored zero.
- **Custom-mode write hazard.** There is a (medium-confidence) community report of a hard shutdown when writing profiles via WMI in custom mode on this firmware family. Therefore the default cool path uses `low-power` (BIOS-managed, no custom mode); `custom` TDP is **opt-in**, clamps strictly to probed min/max, and warns/recommends AC.
- **Limits don't persist.** Reboot clears them; AC↔DC transitions trigger an ACPI-notifier TDP refresh; profile switches clobber. Persistence requires re-applying on boot, on `power_supply` change (udev), and on resume.
- **Spectrum device + zones vary by SKU.** The published zone keycode table is for the 83F5 sibling, not 83KY. Global brightness (the night-off path) needs no zone table; per-zone static color enumerates live via ops `0xC4`/`0xC5` and is best-effort. The correct hidraw device is identified at first run by a reversible probe (`0xCD` GetBrightness / `0xC4` KeyCount), not by hardcoded PID.

## 3. Architecture

A privileged daemon owns all hardware; thin clients drive it over a local socket.

```
  pana (CLI) ─┐                              ┌─ hw/platform_profile.py  power modes
              │                              │─ hw/ppt.py               TDP limits (clamped)
              ├─ Unix socket ── panad ───────┤─ hw/battery.py           conservation + capacity
  pana-tray ──┘  /run/pana/pana.sock         │─ hw/lights.py            Spectrum HID over hidraw
   (user session)  root:<group> 0660         │─ hw/sensors.py           temps / RAPL / battery (read-only)
                   newline-JSON              └─ hw/detect.py            runtime capability map
                                  panad also hosts:
                                    · core/monitor.py    sampler + rolling history (push to subscribers)
                                    · core/battery_watch.py  soft-target hysteresis loop
                                    · core/scheduler.py  night-lights schedule
                                    · core/state.py      re-apply on boot / resume / power-change
```

- **`panad`** runs as **root** (writes root-owned sysfs + hidraw), `systemd Type=notify`. Hardened unit: `ProtectSystem=strict` with `ReadWritePaths=` limited to the specific control nodes; `ProtectHome=yes`; `NoNewPrivileges=yes`; **`PrivateDevices` left unset** (hidraw is required). `RuntimeDirectory=pana` (mode 0750) creates `/run/pana`; the socket is `root:<cole's login group>` mode `0660`, so clients need no `sudo`.
- **`pana`** (CLI) and **`pana-tray`** are unprivileged, thin, and **language-agnostic** — they only speak the JSON protocol.

### Module layout (`pana/` Python package)

- `pana/hw/` — focused, feature-detecting hardware modules. Each reads/writes through a thin **sysfs-path** / **HID-transport** interface so it is fully fakeable in tests.
  - `platform_profile.py`, `ppt.py` (knows the custom-mode coupling + clamping), `battery.py`, `lights.py` (device discovery + Spectrum encode), `sensors.py` (read-only), `detect.py` (capability map).
- `pana/core/` — `presets.py`, `battery_watch.py`, `scheduler.py`, `monitor.py`, `config.py`, `state.py`.
- `pana/ipc/` — `protocol.py` (shared request/response model + JSON codec, **versioned**), `server.py` (asyncio socket server + subscriptions), `client.py`.
- `pana/daemon.py` — wires the asyncio loop: socket server + monitor sampler + battery watcher + scheduler + power/resume hooks + sd-notify readiness.
- `pana/cli.py`, `pana/tray.py`.
- `packaging/` — `panad.service`, optional user `pana-tray.service`, udev rules (hidraw `uaccess` for `048d:c193`/`c197`; `SUBSYSTEM=="power_supply"` change → re-apply), install `Makefile`.
- `docs/PROTOCOL.md` — the wire protocol (the language boundary; see §7).

## 4. Presets & behavior

### Presets (defaults; user-editable in `/etc/pana/config.toml`)

| Preset | platform_profile | TDP | Lights | Battery | Power-button (side effect) |
|---|---|---|---|---|---|
| **Eco/Cool** *(off-grid default)* | `low-power` | BIOS-managed (no custom-mode) | off-capable | cap on | white |
| **Balanced** | `balanced` | defaults | on | as-set | blue |
| **Game** | `performance` | optional `custom` pl1=110/pl2=168 | on | cap off (→100%) | red |
| **Custom TDP** *(advanced, opt-in)* | `custom` | user pl1 (50–110) / pl2 (60–168), clamped | — | — | — |

Optional auto-rule (off by default): on-battery → Eco, on-AC → Balanced.

### Behavior details

- **Battery:** conservation cap = robust hardware baseline. Soft target (≥ cap, e.g. 85%): watcher polls `capacity`/`status` every ~30 s; conservation **on** when `capacity ≥ target`, **off** at `target − hysteresis`; debounced (write only on state change); re-asserted on resume + `power_supply` change. `status` honestly reports that targets below the firmware cap are not possible and that the soft target reverts to charging if the daemon stops.
- **Lights / night:** brightness→0 (op `0xCE` level 0) kills keyboard + perimeter — a **global op needing no zone table**, so night-off works regardless of SKU. Static color is best-effort (enumerate live keycodes via `0xC4`/`0xC5`). Scheduler runs sunset→sunrise (configurable fixed times or lat/long); a manual toggle overrides until the next schedule boundary. First write to a newly-identified device is a low-risk brightness op.
- **Cool path avoids custom mode** by default. `custom` TDP is opt-in, clamps to min/max, fails closed on out-of-range, and recommends AC.
- **Monitoring:** the daemon samples sensors at a configurable interval into a rolling in-memory history and pushes samples to subscribed clients. Metrics: CPU package power (W, from RAPL `energy_uj` delta), battery/system draw (W), CPU package + per-core-max temp, NVMe temps, battery %/status/cycle-count/derived time-to-empty-or-full, AC online, current mode + live PL1/PL2 + conservation state, CPU freq, fan RPM (shown "unavailable (kernel)" until a driver lands — feature-detected), optional GPU temp/power via `nvidia-smi`. Optional opt-in **usage log** (CSV under `~/.local/share/pana/` or journald) for history.

### CLI surface (indicative)

```
pana status                         one-shot snapshot (reads sensors directly if daemon down)
pana monitor                        live refreshing view (subscribes to daemon)
pana mode <eco|balanced|game|...>   apply a preset
pana tdp --pl1 50 --pl2 60          custom TDP (implies custom mode; clamps + warns)
pana battery --cap | --limit 85 | --off
pana lights off|on|brightness <0-9>|color <RRGGBB>
pana night on|off|schedule <sunset-sunrise|HH:MM-HH:MM>
pana selftest                       reversible read-only hardware probes
```

The tray mirrors the common toggles (mode submenu, lights off, battery cap, live temp/power/battery readout).

## 5. Error handling

- Every hardware write is **clamped to probed min/max and fails closed** on out-of-range (guards the custom-mode shutdown hazard).
- **Feature detection** at startup builds a capability map; any missing node/device disables that feature gracefully, is reported by `status`, and never crashes the daemon.
- **Lights:** correct hidraw device identified empirically before any effect blob; if neither candidate responds, the lighting feature is disabled and reported.
- **Config** parse failure → back up to `config.toml-old` and write defaults (never crash root daemon).
- **Daemon death:** the firmware conservation cap persists (hardware); the soft target reverts to charging — documented, acceptable.

## 6. Testing strategy

- **TDD for all pure logic** against **fake sysfs trees + a fake HID transport**: presets, TDP clamping + custom-mode sequencing, battery hysteresis/debounce, scheduler boundaries, config load/migrate/recover, protocol (de)serialization + versioning, capability detection (incl. a "nothing supported" tree), RAPL-delta power math. Runs anywhere, no hardware.
- **IPC round-trip tests:** start `panad` with a fake HAL on a temp socket; exercise CLI→daemon and subscribe/stream paths.
- **Real-hardware verification (gated, manual):** `pana selftest` performs only reversible reads (profile, brightness via `0xCD`, capacity, sensors). A documented one-time manual checklist covers the few semi-irreversible writes (mode switch, conservation toggle, brightness set, and — separately, on AC with saved work — a `custom`-mode PPT write) to confirm real EC/HID effects, which cannot be unit-tested.

## 7. Migration path to Rust (designed-in)

The **JSON socket protocol is the language boundary**, documented and versioned in `docs/PROTOCOL.md`:

- Plain JSON objects only (no Python-specific framing), every message carries a `version` field, request/response and subscription/stream shapes are specified.
- Repo splits along the exact port seam: **`hw/` + `core/` + `ipc/server.py` = the daemon** (the unit a future Rust rewrite replaces); **`cli.py` + `tray.py` = pure protocol clients** that don't change when the daemon's language does.
- The `hw/` swappable sysfs/HID interface keeps the daemon's hardware surface small and well-bounded for porting.
- Plan: ship all-Python now → later replace `panad` with a Rust binary speaking the identical protocol (clients untouched), or port clients independently. No big-bang rewrite required.

## 8. Scope

**In:** power-mode presets; custom TDP (opt-in, clamped); battery hardware-cap + soft-target watcher; lights on/off + brightness + static color + night schedule; monitoring (sensors, live view, optional usage log); CLI; tray; persistence + re-apply on boot/resume/power-change; runtime feature detection; versioned socket protocol.

**Out (YAGNI / infeasible):** fan curves & RPM (kernel gap — auto-enabled later if a driver lands); a full per-key RGB effects engine (only on/off/brightness/static color); a GUI settings window (tray only); D-Bus/polkit/multi-user; distro packaging; arbitrary power-button color (impossible); sub-cap battery % (impossible).

## 9. Open items to validate empirically during implementation

These require live writes and are confirmed during the gated hardware-verification step, not assumed:

1. Exact firmware conservation cap % on this unit (set `Long_Life`, watch where `capacity` plateaus).
2. That `platform_profile=custom` + `ppt_pl*` writes actually change power behavior on BIOS `RXCN27WW` (write + measure RAPL package power under load).
3. Which device (`048d:c197` vs `c193`, or both) actually drives the keyboard vs perimeter/logo on the 83KY.
4. Whether the 83KY zone keycodes match the 83F5 table (only matters for per-zone static color; night-off is unaffected).
5. Whether the loaded DKMS `legion_laptop` runs any service that re-asserts a profile and would fight `panad` (check `systemctl`).
