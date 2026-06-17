from pana.tray import MODES, menu_model


def _status(**over):
    base = {
        "mode": "eco",
        "platform_profile": "low-power",
        "battery": {"capacity": 65, "status": "Charging", "conservation": True},
        "lights": {"available": True},
    }
    base.update(over)
    return base


def test_menu_has_header_and_modes():
    model = menu_model(_status())
    texts = [i.get("text", "") for i in model]
    assert any("pana — eco" in t for t in texts)
    assert any("battery 65%" in t for t in texts)
    for m in MODES:
        assert any(i.get("cmd") == "mode" and i["args"]["name"] == m for i in model)


def test_current_mode_is_checked():
    model = menu_model(_status(mode="game"))
    game = next(i for i in model if i.get("args", {}).get("name") == "game")
    eco = next(i for i in model if i.get("args", {}).get("name") == "eco")
    assert game["checked"] is True
    assert eco["checked"] is False


def test_battery_cap_reflects_conservation():
    on = next(i for i in menu_model(_status()) if i.get("text") == "Battery cap")
    assert on["checked"] is True
    off = next(
        i for i in menu_model(_status(battery={"capacity": 50, "conservation": False}))
        if i.get("text") == "Battery cap"
    )
    assert off["checked"] is False


def test_no_lighting_device_note():
    model = menu_model(_status(lights={"available": False}))
    assert any("no lighting device" in i.get("text", "") for i in model)


def test_quit_present():
    assert any(i.get("action") == "quit" for i in menu_model(_status()))
