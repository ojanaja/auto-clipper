import json

import pytest

from customization import (
    ColorGradeConfig,
    CustomizationConfig,
    CustomizationError,
    OverlayGambarConfig,
    OverlaySumberConfig,
    SubtitleStyleConfig,
    WatermarkConfig,
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


def test_default_subtitle_style_matches_table():
    s = SubtitleStyleConfig()
    assert s.template == "karaoke_pop"
    assert s.font == "Arial"
    assert s.size == 80
    assert s.align == "center"
    assert s.opacity == 100
    assert s.text_color == "#FFFFFF"
    assert s.highlight_color == "#FFFF00"
    assert s.outline_color == "#000000"
    assert s.shadow_color == "#000000"
    assert s.outline_width == 4.0
    assert s.shadow_width == 2.0
    assert s.background_box is False
    assert s.pos_x == 50
    assert s.pos_y == 70


def test_to_dict_nests_sections():
    data = CustomizationConfig().to_dict()
    assert data["subtitle"]["template"] == "karaoke_pop"
    assert data["subtitle"]["enabled"] is True
    assert data["watermark"]["enabled"] is False
    assert data["watermark"]["text"] == "AutoClip"


@pytest.mark.parametrize(
    "overrides,message_contains",
    [
        ({"template": "not-a-template"}, "template"),
        ({"align": "diagonal"}, "align"),
        ({"size": 10}, "size"),
        ({"size": 999}, "size"),
        ({"opacity": -1}, "opacity"),
        ({"opacity": 101}, "opacity"),
        ({"outline_width": -1}, "outline_width"),
        ({"outline_width": 11}, "outline_width"),
        ({"shadow_width": 11}, "shadow_width"),
        ({"pos_x": -1}, "pos_x"),
        ({"pos_y": 101}, "pos_y"),
        ({"text_color": "white"}, "text_color"),
        ({"highlight_color": "#GGGGGG"}, "highlight_color"),
        ({"outline_color": "#FFF"}, "outline_color"),
        ({"shadow_color": "000000"}, "shadow_color"),
    ],
)
def test_subtitle_validate_rejects_invalid(overrides, message_contains):
    style = SubtitleStyleConfig(**overrides)
    with pytest.raises(CustomizationError, match=message_contains):
        style.validate()


def test_subtitle_validate_accepts_defaults():
    SubtitleStyleConfig().validate()  # tidak raise


def test_customization_validate_delegates_to_subtitle():
    cfg = CustomizationConfig()
    cfg.subtitle.template = "invalid"
    with pytest.raises(CustomizationError, match="template"):
        cfg.validate()


def test_default_color_grade_matches_table():
    g = ColorGradeConfig()
    assert g.preset == "none"
    assert g.contrast == 1.0
    assert g.brightness == 0.0
    assert g.saturation == 1.0
    assert g.gamma == 1.0
    assert g.temperature == 0
    assert g.vignette == 0.0


@pytest.mark.parametrize(
    "overrides,message_contains",
    [
        ({"preset": "not-a-preset"}, "preset"),
        ({"contrast": 0.4}, "contrast"),
        ({"contrast": 2.1}, "contrast"),
        ({"brightness": -0.6}, "brightness"),
        ({"brightness": 0.6}, "brightness"),
        ({"saturation": -0.1}, "saturation"),
        ({"saturation": 2.1}, "saturation"),
        ({"gamma": 0.4}, "gamma"),
        ({"gamma": 2.1}, "gamma"),
        ({"temperature": -101}, "temperature"),
        ({"temperature": 101}, "temperature"),
        ({"vignette": -0.1}, "vignette"),
        ({"vignette": 1.1}, "vignette"),
    ],
)
def test_color_grade_validate_rejects_invalid(overrides, message_contains):
    grade = ColorGradeConfig(**overrides)
    with pytest.raises(CustomizationError, match=message_contains):
        grade.validate()


def test_color_grade_validate_accepts_defaults():
    ColorGradeConfig().validate()  # tidak raise


def test_customization_validate_delegates_to_color_grade():
    cfg = CustomizationConfig()
    cfg.color_grade.preset = "invalid"
    with pytest.raises(CustomizationError, match="preset"):
        cfg.validate()


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


# --- Overlay Sumber / Watermark (TextOverlayConfig) ---


def test_default_overlay_sumber_matches_table():
    s = OverlaySumberConfig()
    assert s.enabled is False
    assert s.text == "Sumber: @channel"
    assert s.font == "Arial"
    assert s.size == 32
    assert s.color == "#FFFFFF"
    assert s.opacity == 90
    assert s.pos_x == 50
    assert s.pos_y == 95
    assert s.rotate == 0.0


def test_default_watermark_matches_table():
    w = WatermarkConfig()
    assert w.enabled is False
    assert w.text == "AutoClip"
    assert w.opacity == 25
    assert w.pos_x == 50
    assert w.pos_y == 50
    assert w.rotate == -30.0


@pytest.mark.parametrize(
    "overrides,message_contains",
    [
        ({"size": 11}, "size"),
        ({"size": 161}, "size"),
        ({"opacity": -1}, "opacity"),
        ({"opacity": 101}, "opacity"),
        ({"pos_x": -1}, "pos_x"),
        ({"pos_y": 101}, "pos_y"),
        ({"rotate": -181}, "rotate"),
        ({"rotate": 181}, "rotate"),
        ({"color": "white"}, "color"),
    ],
)
def test_overlay_sumber_validate_rejects_invalid(overrides, message_contains):
    cfg = OverlaySumberConfig(**overrides)
    with pytest.raises(CustomizationError, match=f"overlay_sumber.{message_contains}"):
        cfg.validate()


def test_watermark_validate_rejects_invalid_uses_own_label():
    cfg = WatermarkConfig(size=200)
    with pytest.raises(CustomizationError, match="watermark.size"):
        cfg.validate()


def test_overlay_sumber_validate_accepts_defaults():
    OverlaySumberConfig().validate()  # tidak raise


def test_watermark_validate_accepts_defaults():
    WatermarkConfig().validate()  # tidak raise


def test_customization_validate_delegates_to_watermark():
    cfg = CustomizationConfig()
    cfg.watermark.opacity = 500
    with pytest.raises(CustomizationError, match="watermark.opacity"):
        cfg.validate()


def test_customization_validate_delegates_to_overlay_sumber():
    cfg = CustomizationConfig()
    cfg.overlay_sumber.color = "notacolor"
    with pytest.raises(CustomizationError, match="overlay_sumber.color"):
        cfg.validate()


# --- Overlay Gambar ---


def test_default_overlay_gambar_matches_table():
    g = OverlayGambarConfig()
    assert g.enabled is False
    assert g.image_path == ""
    assert g.size == 20
    assert g.opacity == 100
    assert g.rotate == 0.0
    assert g.pos_x == 85
    assert g.pos_y == 12


@pytest.mark.parametrize(
    "overrides,message_contains",
    [
        ({"size": 4}, "size"),
        ({"size": 101}, "size"),
        ({"opacity": -1}, "opacity"),
        ({"opacity": 101}, "opacity"),
        ({"rotate": -181}, "rotate"),
        ({"rotate": 181}, "rotate"),
        ({"pos_x": -1}, "pos_x"),
        ({"pos_y": 101}, "pos_y"),
    ],
)
def test_overlay_gambar_validate_rejects_invalid(overrides, message_contains):
    cfg = OverlayGambarConfig(**overrides)
    with pytest.raises(CustomizationError, match=message_contains):
        cfg.validate()


def test_overlay_gambar_validate_accepts_defaults():
    OverlayGambarConfig().validate()  # tidak raise


def test_overlay_gambar_validate_ignores_missing_image_path():
    # image_path cuma dicek eksistensinya saat render (lihat pipeline/render.py),
    # bukan saat validate -- preset yang diimpor di mesin lain boleh menunjuk
    # file yang belum ada di mesin ini.
    OverlayGambarConfig(image_path="/tidak/ada/logo.png").validate()  # tidak raise


def test_customization_validate_delegates_to_overlay_gambar():
    cfg = CustomizationConfig()
    cfg.overlay_gambar.size = 1000
    with pytest.raises(CustomizationError, match="overlay_gambar.size"):
        cfg.validate()


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
    assert saved_raw["color_grade"]["enabled"] is True
    assert saved_raw["color_grade"]["preset"] == "none"

    loaded = load_customization()
    assert loaded == cfg
