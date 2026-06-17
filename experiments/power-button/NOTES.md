# Power-button LED — research notes (experimental branch, NOT in releases)

Goal: turn off / dim the **power-button LED** above the keyboard on the Legion 7
16IAX10 (83KY). It tracks the power mode (color) and has no documented "off".

## Ruled out (definitively)
- **Spectrum keyboard controller** (USB 048d:c197): enumerated its full LED map via
  KeyCount/KeyPage (0xC4/0xC5) → exactly 130 LEDs = 101 keyboard + 28 perimeter + 1
  logo. The power button is **not** in the controller's address space.
- **sysfs LEDs**: only keyboard caps/num/scroll + `platform::fnlock`. No power node.
- **legion_laptop**: bound to nothing on 83KY; its two extra LEDs are the lid logo
  and the rear IO-port bar — neither is the power button.
- **BIOS / Lenovo Vantage / LenovoLegionToolkit**: none can change it (LLT maintainer:
  "as far as I know it is not possible"). It's an EC-firmware status indicator.

## The lead (UNVERIFIED — never tested whether it's actually the power button)
DSDT decompile found a vendor WMI method that writes two EC brightness fields:

- **WMI GUID** `603E9613-EF25-4338-A3D0-C46177516DB7`, method **`WMAA`**
  (ACPI path `\_SB.PC00.AWMI.WMAA`). Present in `/sys/bus/wmi/devices`.
  - `WMAA(0, 1, buf)`: MODF byte0=0 get / 1 set; LEDB dword@offset4. SET → `PCBV = LEDB; SPBL = 1`. Max (MODF=2) = `0x320` (800).
  - `WMAA(0, 2, buf)`: SET → if `LEDB < 3`: `PCBS = LEDB` (3 levels).
- **EC fields** are in MMIO region `ERAX` (`OperationRegion(ERAX, SystemMemory, 0xFE500400, 0xFF)`):
  - `PCBV` (16-bit) @ **0xFE500440**
  - `PCBS` (8-bit)  @ **0xFE500442**
  - `SPBL` latch = **bit7 of 0xFE50043F** (also `BLCF` = bit6)

`PCB*`/`SPBL`/`BLCF` smell like a power/indicator brightness control, but the names
don't prove it's the power button vs. a panel/other indicator. **Only a live write
test answers it.**

## Blocker
Secure Boot ON → kernel lockdown = `integrity`, which blocks **both**:
- `/dev/mem` (devmem returns EPERM even as root) → can't MMIO-poke PCBV/PCBS.
- loading **unsigned** modules → a hand-rolled helper won't load.
Also `acpi-call-dkms` does **not** build against kernel 6.17.

## Two paths forward
**A. Quick test — temporarily disable Secure Boot, then devmem.**
1. BIOS (F2) → Security → Secure Boot → Disabled → save. Confirm `cat /sys/kernel/security/lockdown` shows `[none]`.
2. `sudo bash pwrled.sh read` (baseline), then `sudo bash pwrled.sh pcbs 0|1|2` and
   `pwrled.sh pcbv 0|400` **while watching the power button** (and the screen — if the
   *screen* dims, PCBV is the panel backlight, not the button; abort that field).
3. Restore the baseline; re-enable Secure Boot.

**B. Permanent / keep Secure Boot on — MOK-signed helper module.**
Cole has a MOK enrolled (from LenovoLegionLinux). Write a tiny kernel module that calls
`WMAA` via `acpi_evaluate_object` (the vendor method — bounds-checked, handles the SPBL
latch), build against installed headers, sign with the MOK (DKMS auto-signs on Ubuntu),
load under Secure Boot. If the test in (A) confirms PCBV/PCBS is the button, wire a
`pana lights --power off/dim` command on top of this and the LED is controllable.

`pwrled.sh` here is the devmem-based test helper (needs Secure Boot off).
