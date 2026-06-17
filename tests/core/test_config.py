from pana.core.config import Config, State


def test_config_from_toml_section():
    cfg = Config.from_toml(
        """
        [pana]
        default_mode = "eco"
        battery_target = 80
        night_enabled = true
        night_start = "21:30"
        """
    )
    assert cfg.default_mode == "eco"
    assert cfg.battery_target == 80
    assert cfg.night_enabled is True
    assert cfg.night_start == "21:30"
    # untouched fields keep defaults
    assert cfg.night_end == "07:00"


def test_config_from_flat_toml():
    cfg = Config.from_toml('default_mode = "game"\n')
    assert cfg.default_mode == "game"


def test_config_corrupt_toml_falls_back_to_defaults():
    cfg = Config.from_toml("this is = = not toml [[[")
    assert cfg.default_mode == "balanced"


def test_config_ignores_unknown_keys():
    cfg = Config.from_toml('[pana]\nbogus_key = 5\ndefault_mode = "eco"\n')
    assert cfg.default_mode == "eco"
    assert not hasattr(cfg, "bogus_key")


def test_state_json_roundtrip():
    st = State(mode="eco", battery_target=80, lights_manual="off")
    back = State.from_json(st.to_json())
    assert back == st


def test_state_from_corrupt_json_defaults():
    assert State.from_json("{not json") == State()


def test_state_save_load_and_corrupt_backup(tmp_path):
    path = str(tmp_path / "state.json")
    State(mode="game", battery_target=85).save(path)
    assert State.load(path) == State(mode="game", battery_target=85)

    # corrupt it -> load returns defaults and backs up the bad file
    with open(path, "w") as f:
        f.write("{garbage")
    assert State.load(path) == State()
    import os
    assert os.path.exists(path + "-old")
