from pana.tray import MODES, menu_model


def _status(**over):
    base = {
        "mode": "eco",
        "platform_profile": "low-power",
        "battery": {"capacity": 65, "status": "Charging", "conservation": True},
        "lights": {"available": True, "night_enabled": False, "on": False,
                   "brightness": 0, "color": None, "effect": None},
        "monitor": {"cpu_temp_c": 60.0, "cpu_power_w": 33.0},
    }
    base.update(over)
    return base


def _flatten(model):
    out = []
    for it in model:
        out.append(it)
        if it.get("type") == "submenu":
            out.extend(_flatten(it["items"]))
    return out


def _find(model, **match):
    for it in _flatten(model):
        if all(it.get(k) == v for k, v in match.items()):
            return it
    raise AssertionError(f"no item matching {match}")


def test_title_shows_mode_battery_temp():
    title = menu_model(_status())[0]["text"]
    assert "eco" in title and "65%" in title and "60" in title


def test_modes_are_performance_not_game_and_descriptive():
    model = menu_model(_status(mode="performance"))
    assert MODES == ["eco", "balanced", "performance"]
    perf = _find(model, cmd="mode", args={"name": "performance"})
    assert "full power" in perf["text"].lower()
    assert perf["checked"] is True and perf["radio"] is True
    # no 'game' anywhere
    assert not any(i.get("args", {}).get("name") == "game" for i in _flatten(model))


def test_mode_labels_describe_what_they_do():
    model = menu_model(_status())
    eco = _find(model, cmd="mode", args={"name": "eco"})
    assert "cool" in eco["text"].lower()


def test_lighting_submenu_has_brightness_color_effect():
    model = menu_model(_status())
    lighting = _find(model, text="Lighting")
    sub_texts = [i.get("text") for i in lighting["items"]]
    assert "Brightness" in sub_texts and "Color" in sub_texts and "Effect" in sub_texts
    # a concrete color option exists and carries a static effect
    purple = _find(model, text="Purple")
    assert purple["args"]["effect"] == "static" and purple["args"]["color"] == [150, 90, 220]
    # an effect option exists
    assert _find(model, cmd="lights", args={"effect": "rainbow"})["text"] == "Rainbow"


def test_lights_on_off_checked_reflects_state():
    off_model = menu_model(_status(lights={"available": True, "on": False, "night_enabled": False}))
    assert _find(off_model, cmd="lights", args={"on": False})["checked"] is True
    assert _find(off_model, cmd="lights", args={"on": True})["checked"] is False
    on_model = menu_model(_status(lights={"available": True, "on": True, "night_enabled": False}))
    assert _find(on_model, cmd="lights", args={"on": True})["checked"] is True


def test_brightness_and_color_checks_track_state():
    model = menu_model(_status(lights={"available": True, "on": True, "brightness": 5,
                                       "effect": "static", "color": [0, 0, 255], "night_enabled": False}))
    assert _find(model, cmd="lights", args={"brightness": 5})["checked"] is True
    assert _find(model, text="Blue")["checked"] is True
    assert _find(model, text="Red")["checked"] is False


def test_no_lighting_device_shows_note_not_submenu():
    model = menu_model(_status(lights={"available": False}))
    assert any("no device" in i.get("text", "") for i in model)
    assert not any(i.get("text") == "Lighting" for i in model)


def test_battery_and_controls_present():
    model = menu_model(_status(battery={"conservation": True}))
    assert _find(model, cmd="battery", args={"cap": True})["checked"] is True
    assert _find(model, cmd="battery", args={"off": True})["checked"] is False
    assert any(i.get("cmd") == "night" for i in model)
    assert any(i.get("action") == "quit" for i in model)
    assert any(i.get("action") == "refresh" for i in model)
