from pana.core.presets import default_presets


def test_default_presets_shape():
    p = default_presets()
    assert p["eco"].platform_profile == "low-power"
    assert p["eco"].eco_cap is True        # eco applies the clock-ceiling cooling cap
    assert p["eco"].lights == "off"
    assert p["eco"].battery == "cap"
    assert p["performance"].platform_profile == "performance"
    assert p["performance"].eco_cap is False   # performance lifts the cap
    assert p["performance"].battery == "off"
    assert p["balanced"].platform_profile == "balanced"
    assert p["balanced"].eco_cap is False
