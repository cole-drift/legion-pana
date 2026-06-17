from pana.core.presets import custom_tdp_preset, default_presets


def test_default_presets_shape():
    p = default_presets()
    assert p["eco"].platform_profile == "low-power"
    assert p["eco"].lights == "off"
    assert p["eco"].battery == "cap"
    assert p["eco"].ppt == {}
    assert p["game"].platform_profile == "performance"
    assert p["game"].battery == "off"
    assert p["balanced"].platform_profile == "balanced"


def test_custom_tdp_preset_implies_custom_profile():
    p = custom_tdp_preset(pl1=50, pl2=60)
    assert p.platform_profile == "custom"
    assert p.ppt == {"ppt_pl1_spl": 50, "ppt_pl2_sppt": 60}


def test_custom_tdp_preset_partial():
    p = custom_tdp_preset(pl1=70)
    assert p.ppt == {"ppt_pl1_spl": 70}
