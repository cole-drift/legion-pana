from pana.tray import MODES, menu_model


def _status(**over):
    base = {
        "mode": "eco",
        "platform_profile": "low-power",
        "battery": {"capacity": 65, "status": "Charging", "conservation": True},
        "lights": {"available": True, "night_enabled": False},
        "monitor": {"cpu_temp_c": 60.0, "cpu_power_w": 33.0},
    }
    base.update(over)
    return base


def _item(model, **match):
    for it in model:
        if all(it.get(k) == v for k, v in match.items()):
            return it
    raise AssertionError(f"no item matching {match}")


def test_title_shows_mode_battery_temp():
    title = menu_model(_status())[0]["text"]
    assert "eco" in title and "65%" in title and "60" in title


def test_modes_present_and_radio_checked():
    model = menu_model(_status(mode="game"))
    for m in MODES:
        it = _item(model, cmd="mode", args={"name": m})
        assert it["radio"] is True
        assert it["checked"] is (m == "game")


def test_lights_items():
    model = menu_model(_status())
    assert _item(model, cmd="lights", args={"on": False})["text"] == "Lights off"
    assert _item(model, cmd="lights", args={"on": True})["text"] == "Lights on"


def test_night_toggle_inverts_and_reflects_state():
    on = _item(menu_model(_status(lights={"night_enabled": False})), cmd="night")
    assert on["args"] == {"enabled": True} and on["checked"] is False
    off = _item(menu_model(_status(lights={"night_enabled": True})), cmd="night")
    assert off["args"] == {"enabled": False} and off["checked"] is True


def test_battery_items_reflect_conservation():
    model = menu_model(_status(battery={"conservation": True}))
    assert _item(model, cmd="battery", args={"cap": True})["checked"] is True
    assert _item(model, cmd="battery", args={"off": True})["checked"] is False


def test_fixed_item_count_regardless_of_status():
    # the backend builds items once; the set must not change with status values
    a = menu_model(_status())
    b = menu_model(_status(mode="game", battery={"conservation": False}, lights={"night_enabled": True},
                           monitor={}))
    assert len(a) == len(b)


def test_quit_and_refresh_present():
    model = menu_model(_status())
    assert any(i.get("action") == "quit" for i in model)
    assert any(i.get("action") == "refresh" for i in model)
