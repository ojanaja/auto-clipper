import json
from pathlib import Path

import pytest

from config import (
    AppConfig,
    ConfigError,
    default_config_path,
    load_config,
    resolve_output_dir,
    save_config,
)


def test_default_config_matches_table():
    cfg = AppConfig()
    assert cfg.aspect_ratio == "9:16"
    assert cfg.resolution == 1080
    assert cfg.duration_min == 20
    assert cfg.duration_max == 60
    assert cfg.subtitle_enabled is True
    assert cfg.subtitle_font_size == 80
    assert cfg.whisper_model == "small"
    assert cfg.segment_count == 8
    assert cfg.llm_provider == "gemini"
    assert cfg.llm_model == ""
    assert cfg.gemini_api_key == ""
    assert cfg.anthropic_api_key == ""
    assert cfg.encoder == "auto"
    assert cfg.output_dir == ""


@pytest.mark.parametrize(
    "aspect_ratio,resolution,expected",
    [
        ("9:16", 1080, (1080, 1920)),
        ("1:1", 1080, (1080, 1080)),
        ("16:9", 720, (1280, 720)),
        ("4:5", 480, (480, 600)),
        ("9:16", 480, (480, 852)),  # 480/(9/16)=853.33 -> round -> 853 -> even 852
        ("16:9", 1080, (1920, 1080)),
    ],
)
def test_output_dimensions(aspect_ratio, resolution, expected):
    cfg = AppConfig(aspect_ratio=aspect_ratio, resolution=resolution)
    w, h = cfg.output_dimensions()
    assert (w, h) == expected
    assert w % 2 == 0 and h % 2 == 0


@pytest.mark.parametrize(
    "aspect_ratio",
    ["3:2", "21:9", ""],
)
def test_invalid_aspect_ratio_raises(aspect_ratio):
    with pytest.raises(ConfigError):
        AppConfig(aspect_ratio=aspect_ratio).validate()


@pytest.mark.parametrize("resolution", [360, 1440, 0])
def test_invalid_resolution_raises(resolution):
    with pytest.raises(ConfigError):
        AppConfig(resolution=resolution).validate()


@pytest.mark.parametrize("whisper_model", ["large", "base"])
def test_invalid_whisper_model_raises(whisper_model):
    with pytest.raises(ConfigError):
        AppConfig(whisper_model=whisper_model).validate()


@pytest.mark.parametrize("llm_provider", ["openai", "gemni"])
def test_invalid_llm_provider_raises(llm_provider):
    with pytest.raises(ConfigError):
        AppConfig(llm_provider=llm_provider).validate()


@pytest.mark.parametrize("encoder", ["hevc", "libx265"])
def test_invalid_encoder_raises(encoder):
    with pytest.raises(ConfigError):
        AppConfig(encoder=encoder).validate()


def test_duration_min_must_be_less_than_max():
    with pytest.raises(ConfigError):
        AppConfig(duration_min=60, duration_max=60).validate()
    with pytest.raises(ConfigError):
        AppConfig(duration_min=70, duration_max=60).validate()


@pytest.mark.parametrize("font_size", [10, 200])
def test_invalid_font_size_raises(font_size):
    with pytest.raises(ConfigError):
        AppConfig(subtitle_font_size=font_size).validate()


@pytest.mark.parametrize("count", [0, 25])
def test_invalid_segment_count_raises(count):
    with pytest.raises(ConfigError):
        AppConfig(segment_count=count).validate()


def test_target_ratio():
    assert AppConfig(aspect_ratio="9:16").target_ratio() == 9 / 16
    assert AppConfig(aspect_ratio="1:1").target_ratio() == 1.0
    assert AppConfig(aspect_ratio="16:9").target_ratio() == 16 / 9


def test_from_dict_ignores_unknown_and_fills_defaults():
    cfg = AppConfig.from_dict(
        {"aspect_ratio": "1:1", "resolution": 720, "unknown_field": "x"}
    )
    assert cfg.aspect_ratio == "1:1"
    assert cfg.resolution == 720
    assert cfg.whisper_model == "small"  # default


def test_to_dict_includes_keys():
    cfg = AppConfig(gemini_api_key="secret", anthropic_api_key="key2")
    data = cfg.to_dict()
    assert data["gemini_api_key"] == "secret"
    assert data["anthropic_api_key"] == "key2"


def test_to_public_dict_masks_keys():
    cfg = AppConfig(gemini_api_key="secret", anthropic_api_key="")
    data = cfg.to_public_dict()
    assert "gemini_api_key" not in data
    assert "anthropic_api_key" not in data
    assert data["gemini_key_set"] is True
    assert data["anthropic_key_set"] is False
    assert data["aspect_ratio"] == "9:16"


def test_default_config_path():
    assert default_config_path() == (Path.home() / ".autoclip" / "config.json")


def test_default_config_path_respects_env(monkeypatch):
    monkeypatch.setenv("AUTOCLIP_CONFIG_DIR", "/tmp/ac_cfg")
    assert default_config_path() == Path("/tmp/ac_cfg/config.json")


def test_load_config_missing_returns_default(tmp_path):
    cfg = load_config(tmp_path / "missing.json")
    assert cfg == AppConfig()


def test_load_config_corrupt_returns_default(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("not json")
    cfg = load_config(path)
    assert cfg == AppConfig()


def test_load_config_merge_default(tmp_path):
    path = tmp_path / "cfg.json"
    path.write_text(json.dumps({"aspect_ratio": "1:1"}))
    cfg = load_config(path)
    assert cfg.aspect_ratio == "1:1"
    assert cfg.resolution == 1080  # default


def test_save_config_creates_parent_and_round_trips(tmp_path):
    path = tmp_path / "nested" / "config.json"
    cfg = AppConfig(aspect_ratio="16:9", gemini_api_key="secret")
    save_config(cfg, path)
    assert path.exists()

    loaded = load_config(path)
    assert loaded.aspect_ratio == "16:9"
    assert loaded.gemini_api_key == "secret"


def test_save_config_is_valid_json(tmp_path):
    path = tmp_path / "cfg.json"
    save_config(AppConfig(), path)
    data = json.loads(path.read_text())
    assert data["aspect_ratio"] == "9:16"


def test_resolve_output_dir_uses_config_value():
    cfg = AppConfig(output_dir="/tmp/custom_out")
    assert resolve_output_dir(cfg) == Path("/tmp/custom_out")


def test_resolve_output_dir_uses_fallback_when_empty():
    cfg = AppConfig(output_dir="")
    fallback = Path("/tmp/fallback")
    assert resolve_output_dir(cfg, fallback=fallback) == fallback


def test_resolve_output_dir_default_fallback():
    cfg = AppConfig(output_dir="")
    assert resolve_output_dir(cfg) == Path.home() / "Movies" / "AutoClip"
