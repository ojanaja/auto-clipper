"""Konfigurasi aplikasi AutoClip Lokal — model, validasi, persistence.

Config disimpan sebagai JSON lokal per instalasi. API key disimpan plaintext
(single-user, localhost-only) — batasan MVP, didokumentasikan.
"""

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


class ConfigError(Exception):
    """Input konfigurasi tidak valid."""


ALLOWED_ASPECT_RATIOS = {"9:16", "1:1", "16:9", "4:5"}
ALLOWED_RESOLUTIONS = {480, 720, 1080}
ALLOWED_WHISPER_MODELS = {"tiny", "small", "medium"}
ALLOWED_LLM_PROVIDERS = {"gemini", "anthropic"}
ALLOWED_ENCODERS = {"auto", "libx264", "h264_videotoolbox", "h264_nvenc"}

_RATIO_MAP: dict[str, float] = {
    "9:16": 9 / 16,
    "1:1": 1.0,
    "16:9": 16 / 9,
    "4:5": 4 / 5,
}

_DEFAULT_OUTPUT_DIR = str(Path.home() / "Movies" / "AutoClip")


@dataclass
class AppConfig:
    aspect_ratio: str = "9:16"
    resolution: int = 1080
    duration_min: int = 20
    duration_max: int = 60
    subtitle_enabled: bool = True
    subtitle_font_size: int = 80
    whisper_model: str = "small"
    segment_count: int = 8
    llm_provider: str = "gemini"
    llm_model: str = ""
    gemini_api_key: str = ""
    anthropic_api_key: str = ""
    encoder: str = "auto"
    output_dir: str = ""
    face_tracking_enabled: bool = False
    face_sample_fps: int = 2
    speaker_min_dwell_s: float = 1.5

    def validate(self) -> None:
        """Validasi nilai config; raise ConfigError bila invalid."""
        if self.aspect_ratio not in ALLOWED_ASPECT_RATIOS:
            raise ConfigError(
                f"aspect_ratio harus salah satu dari {sorted(ALLOWED_ASPECT_RATIOS)}"
            )
        if self.resolution not in ALLOWED_RESOLUTIONS:
            raise ConfigError(
                f"resolution harus salah satu dari {sorted(ALLOWED_RESOLUTIONS)}"
            )
        if self.duration_min < 5 or self.duration_min > 180:
            raise ConfigError("duration_min harus antara 5 dan 180")
        if self.duration_max < 5 or self.duration_max > 180:
            raise ConfigError("duration_max harus antara 5 dan 180")
        if self.duration_min >= self.duration_max:
            raise ConfigError("duration_min harus lebih kecil dari duration_max")
        if self.whisper_model not in ALLOWED_WHISPER_MODELS:
            raise ConfigError(
                f"whisper_model harus salah satu dari {sorted(ALLOWED_WHISPER_MODELS)}"
            )
        if self.segment_count < 1 or self.segment_count > 20:
            raise ConfigError("segment_count harus antara 1 dan 20")
        if self.llm_provider not in ALLOWED_LLM_PROVIDERS:
            raise ConfigError(
                f"llm_provider harus salah satu dari {sorted(ALLOWED_LLM_PROVIDERS)}"
            )
        if self.encoder not in ALLOWED_ENCODERS:
            raise ConfigError(
                f"encoder harus salah satu dari {sorted(ALLOWED_ENCODERS)}"
            )
        if self.subtitle_font_size < 24 or self.subtitle_font_size > 160:
            raise ConfigError("subtitle_font_size harus antara 24 dan 160")
        if self.face_sample_fps < 1 or self.face_sample_fps > 5:
            raise ConfigError("face_sample_fps harus antara 1 dan 5")
        if self.speaker_min_dwell_s < 0.0 or self.speaker_min_dwell_s > 5.0:
            raise ConfigError("speaker_min_dwell_s harus antara 0.0 dan 5.0")

    def target_ratio(self) -> float:
        """Kembalikan rasio sebagai float (w/h)."""
        return _RATIO_MAP[self.aspect_ratio]

    def output_dimensions(self) -> tuple[int, int]:
        """Hitung dimensi output berdasarkan rasio dan resolusi (short edge).

        Width/height dibulatkan ke genap (syarat encoder).
        """
        ratio = self.target_ratio()
        if ratio <= 1:
            w = self.resolution
            h = round(self.resolution / ratio)
        else:
            h = self.resolution
            w = round(self.resolution * ratio)

        def even(n: int) -> int:
            return n // 2 * 2

        return even(w), even(h)

    def to_dict(self) -> dict:
        """Serialisasi lengkap (termasuk API key)."""
        return asdict(self)

    def to_public_dict(self) -> dict:
        """Serialisasi untuk dikirim ke frontend: key disamarkan."""
        data = asdict(self)
        data.pop("gemini_api_key", None)
        data.pop("anthropic_api_key", None)
        data["gemini_key_set"] = bool(self.gemini_api_key)
        data["anthropic_key_set"] = bool(self.anthropic_api_key)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "AppConfig":
        """Buat config dari dict; unknown key diabaikan, missing pakai default."""
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


def default_config_path() -> Path:
    """Path default file config; bisa dioverride via AUTOCLIP_CONFIG_DIR."""
    base = os.environ.get("AUTOCLIP_CONFIG_DIR", Path.home() / ".autoclip")
    return Path(base) / "config.json"


def load_config(path: Path | None = None) -> AppConfig:
    """Load config dari JSON; fallback ke default bila file tak ada/korup."""
    path = path or default_config_path()
    if not path.exists():
        return AppConfig()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return AppConfig()
    return AppConfig.from_dict(data)


def save_config(cfg: AppConfig, path: Path | None = None) -> None:
    """Simpan config ke JSON; buat parent directory bila belum ada."""
    path = path or default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg.to_dict(), f, indent=2, ensure_ascii=False)


def resolve_output_dir(cfg: AppConfig, fallback: Path | None = None) -> Path:
    """Resolve direktori output render dari konfigurasi atau fallback."""
    if cfg.output_dir:
        return Path(cfg.output_dir)
    return fallback or Path.home() / "Movies" / "AutoClip"
