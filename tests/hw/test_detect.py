from pana.hw import detect as d
from pana.hw.transport import FakeSysfs


def _legion_tree() -> FakeSysfs:
    return FakeSysfs({
        d.PLATFORM_PROFILE: "performance",
        d.PLATFORM_PROFILE_CHOICES: "low-power balanced balanced-performance performance custom",
        f"{d.PPT_DIR}/ppt_pl1_spl/current_value": "0",
        f"{d.PPT_DIR}/ppt_pl2_sppt/current_value": "0",
        f"{d.PPT_DIR}/ppt_pl3_fppt/current_value": "0",
        d.CONSERVATION: "0",
    })


def test_detect_on_legion():
    caps = d.detect(_legion_tree())
    assert caps.power_modes is True
    assert "custom" in caps.profile_choices
    assert caps.ppt is True
    assert caps.ppt_attrs == ["ppt_pl1_spl", "ppt_pl2_sppt", "ppt_pl3_fppt"]
    assert caps.battery_conservation is True


def test_detect_on_empty_machine():
    caps = d.detect(FakeSysfs({}))
    assert caps.power_modes is False
    assert caps.profile_choices == []
    assert caps.ppt is False
    assert caps.ppt_attrs == []
    assert caps.battery_conservation is False


def test_battery_detected_via_charge_types_only():
    caps = d.detect(FakeSysfs({d.CHARGE_TYPES: "[Standard] Long_Life"}))
    assert caps.battery_conservation is True


def test_to_dict_is_json_safe():
    import json
    caps = d.detect(_legion_tree())
    json.dumps(caps.to_dict())  # must not raise
