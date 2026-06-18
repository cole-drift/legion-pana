from pana.tray import MODES, TempTrend, _title, menu_model


def _status(**over):
    base = {
        "mode": "eco",
        "platform_profile": "low-power",
        "cpu_cap": {"available": True, "max_perf_pct": 50, "desired_pct": 50},
        "battery": {"capacity": 65, "status": "Charging", "conservation": True},
        "lights": {"available": True, "night_enabled": False, "on": False,
                   "brightness": 0, "color": None, "effect": None,
                   "night_start": "20:00", "night_end": "07:00"},
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
    assert any(i.get("cmd") == "night" for i in _flatten(model))  # night lives in a submenu
    assert any(i.get("action") == "quit" for i in model)
    assert any(i.get("action") == "refresh" for i in model)


def test_title_includes_cpu_cap():
    assert "CPU 50%" in menu_model(_status())[0]["text"]


def test_mode_labels_are_cpu_only():
    model = menu_model(_status())
    for m in MODES:
        lbl = _find(model, cmd="mode", args={"name": m})["text"]
        assert "battery" not in lbl.lower() and "lights" not in lbl.lower()


def test_night_submenu_has_enable_and_window_presets():
    model = menu_model(_status(lights={"available": True, "night_enabled": True,
                                       "night_start": "22:00", "night_end": "06:00"}))
    # enable/disable reflect state
    assert _find(model, cmd="night", args={"enabled": True})["checked"] is True
    # the current window preset is checked
    win = _find(model, cmd="night", args={"start": "22:00", "end": "06:00"})
    assert win["checked"] is True


# --- live telemetry: smoothing + peak (the tray's in-place label updates) ---

def test_temptrend_empty_is_none():
    tr = TempTrend()
    assert tr.smoothed() is None
    assert tr.peak() is None


def test_temptrend_smoothes_over_short_window_only():
    tr = TempTrend(smooth_s=2.0, peak_s=60.0)
    tr.add(0.0, 50.0)   # outside the 2s smooth window relative to latest (10.0)
    tr.add(9.0, 60.0)   # inside
    tr.add(10.0, 70.0)  # inside (latest)
    # smoothed averages only samples with ts >= 10.0 - 2.0 = 8.0  -> mean(60,70)=65
    assert tr.smoothed() == 65.0


def test_temptrend_peak_is_max_over_peak_window():
    tr = TempTrend(smooth_s=2.0, peak_s=60.0)
    tr.add(0.0, 80.0)    # peak within 60s window of latest? latest=70 -> cutoff 10 -> dropped
    tr.add(70.0, 55.0)
    tr.add(71.0, 58.0)
    # 80.0 sample (ts=0) is older than 71-60=11 -> evicted; peak over remaining = 58
    assert tr.peak() == 58.0


def test_temptrend_ignores_none_samples():
    tr = TempTrend()
    tr.add(1.0, None)
    tr.add(2.0, 50.0)
    assert tr.smoothed() == 50.0


def test_title_uses_temp_and_peak_overrides():
    st = {"mode": "eco", "cpu_cap": {"max_perf_pct": 50},
          "battery": {"capacity": 40}, "monitor": {"cpu_temp_c": 99.0}}
    title = _title(st, temp_c=51.3, peak_c=68.0)
    assert "51.3" in title          # uses the override, not the raw 99.0
    assert "99" not in title
    assert "68" in title            # peak shown


def test_title_without_overrides_uses_monitor_value():
    st = {"mode": "eco", "monitor": {"cpu_temp_c": 60.0}}
    assert "60" in _title(st)
