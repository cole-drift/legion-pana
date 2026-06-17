from pana.hw.sensors import RAPL_ENERGY, Sensors
from pana.hw.transport import FakeSysfs


def test_cpu_package_temp():
    fs = FakeSysfs({
        "/sys/class/hwmon/hwmon6/name": "coretemp",
        "/sys/class/hwmon/hwmon6/temp1_label": "Package id 0",
        "/sys/class/hwmon/hwmon6/temp1_input": "52000",
        "/sys/class/hwmon/hwmon6/temp2_label": "Core 0",
        "/sys/class/hwmon/hwmon6/temp2_input": "50000",
    })
    assert Sensors(fs).cpu_package_temp_c() == 52.0


def test_nvme_temps():
    fs = FakeSysfs({
        "/sys/class/hwmon/hwmon2/name": "nvme",
        "/sys/class/hwmon/hwmon2/temp1_input": "41850",
        "/sys/class/hwmon/hwmon2/temp2_input": "39850",
    })
    assert Sensors(fs).nvme_temps_c() == [41.85, 39.85]


def test_rapl_power_math():
    # 1 joule over 1 second = 1 W
    assert Sensors.rapl_power_w(1_000_000, 2_000_000, 1.0) == 1.0
    # 5 joules over 0.5s = 10 W
    assert Sensors.rapl_power_w(0, 5_000_000, 0.5) == 10.0


def test_rapl_power_handles_counter_wrap():
    wrap = 10_000_000
    # e0 near top, e1 wrapped past zero: (1_000_000 - 9_500_000 + wrap) = 1_500_000 uj over 1s
    assert Sensors.rapl_power_w(9_500_000, 1_000_000, 1.0, wrap_uj=wrap) == 1.5


def test_rapl_energy_read():
    fs = FakeSysfs({RAPL_ENERGY: "123456789"})
    assert Sensors(fs).rapl_energy_uj() == 123456789


def test_battery_dict_and_cpu_freq():
    fs = FakeSysfs({
        "/sys/class/power_supply/BAT0/capacity": "38",
        "/sys/class/power_supply/BAT0/status": "Charging",
        "/sys/class/power_supply/BAT0/power_now": "15000000",
        "/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq": "2000000",
        "/sys/devices/system/cpu/cpu1/cpufreq/scaling_cur_freq": "4000000",
    })
    s = Sensors(fs)
    bat = s.battery()
    assert bat["capacity"] == 38
    assert bat["status"] == "Charging"
    assert bat["power_w"] == 15.0
    assert s.cpu_freq_mhz() == {"avg": 3000.0, "max": 4000.0}


def test_missing_sensors_return_none():
    s = Sensors(FakeSysfs({}))
    assert s.cpu_package_temp_c() is None
    assert s.nvme_temps_c() == []
    assert s.rapl_energy_uj() is None
    assert s.cpu_freq_mhz() == {"avg": None, "max": None}


class _PermDeniedSysfs(FakeSysfs):
    def __init__(self, files, deny):
        super().__init__(files)
        self._deny = set(deny)

    def read(self, path):
        if path in self._deny:
            raise PermissionError(path)
        return super().read(path)


def test_unreadable_rapl_does_not_blank_other_sensors():
    # RAPL energy_uj is root-only on modern kernels; a denied read must not crash.
    fs = _PermDeniedSysfs(
        {RAPL_ENERGY: "123", "/sys/class/power_supply/BAT0/capacity": "50"},
        deny={RAPL_ENERGY},
    )
    s = Sensors(fs)
    assert s.rapl_energy_uj() is None
    assert s.battery()["capacity"] == 50
