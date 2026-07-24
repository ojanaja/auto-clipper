import json

from customization import (
    CustomizationConfig,
    default_customization_path,
    load_customization,
    save_customization,
)


def test_default_customization_all_disabled_except_subtitle():
    cfg = CustomizationConfig()
    assert cfg.enabled is False
    assert cfg.subtitle.enabled is True
    assert cfg.overlay_sumber.enabled is False
    assert cfg.watermark.enabled is False
    assert cfg.overlay_gambar.enabled is False
    assert cfg.color_grade.enabled is False


def test_to_dict_nests_sections():
    data = CustomizationConfig().to_dict()
    assert data["subtitle"] == {"enabled": True}
    assert data["watermark"] == {"enabled": False}


def test_from_dict_roundtrip():
    original = CustomizationConfig(enabled=True)
    original.watermark.enabled = True
    restored = CustomizationConfig.from_dict(original.to_dict())
    assert restored == original


def test_from_dict_ignores_unknown_keys():
    cfg = CustomizationConfig.from_dict(
        {"enabled": True, "subtitle": {"enabled": False, "foo": "bar"}, "unknown_section": {}}
    )
    assert cfg.enabled is True
    assert cfg.subtitle.enabled is False


def test_from_dict_missing_section_uses_default():
    cfg = CustomizationConfig.from_dict({"enabled": True})
    assert cfg.subtitle.enabled is True
    assert cfg.watermark.enabled is False


def test_from_dict_corrupt_section_falls_back_to_default():
    cfg = CustomizationConfig.from_dict({"subtitle": "not-a-dict"})
    assert cfg.subtitle.enabled is True


def test_load_customization_missing_file_returns_default(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOCLIP_CONFIG_DIR", str(tmp_path))
    cfg = load_customization()
    assert cfg == CustomizationConfig()


def test_load_customization_corrupt_json_returns_default(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOCLIP_CONFIG_DIR", str(tmp_path))
    path = default_customization_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not valid json", encoding="utf-8")
    cfg = load_customization()
    assert cfg == CustomizationConfig()


def test_save_then_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOCLIP_CONFIG_DIR", str(tmp_path))
    cfg = CustomizationConfig(enabled=True)
    cfg.color_grade.enabled = True
    save_customization(cfg)

    saved_raw = json.loads((tmp_path / "customization.json").read_text())
    assert saved_raw["color_grade"] == {"enabled": True}

    loaded = load_customization()
    assert loaded == cfg
