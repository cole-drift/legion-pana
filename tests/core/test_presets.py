from pana.core.presets import MODE_ALIASES, default_presets


def test_default_presets_are_cpu_only():
    p = default_presets()
    # modes carry only a name + platform_profile (cosmetic); no battery/lights coupling
    assert p["eco"].platform_profile == "low-power"
    assert p["balanced"].platform_profile == "balanced"
    assert p["performance"].platform_profile == "performance"
    for preset in p.values():
        assert set(vars(preset)) == {"name", "platform_profile"}


def test_game_is_an_alias_for_performance():
    assert MODE_ALIASES["game"] == "performance"
