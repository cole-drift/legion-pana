from pana.core.presets import default_presets


def test_default_presets_shape():
    p = default_presets()
    assert p["eco"].platform_profile == "low-power"
    assert p["eco"].rapl_cap is True       # eco applies the real RAPL cooling cap
    assert p["eco"].lights == "off"
    assert p["eco"].battery == "cap"
    assert p["game"].platform_profile == "performance"
    assert p["game"].rapl_cap is False     # game lifts the cap
    assert p["game"].battery == "off"
    assert p["balanced"].platform_profile == "balanced"
    assert p["balanced"].rapl_cap is False
