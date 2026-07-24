import subprocess
from dataclasses import dataclass
from pathlib import Path

from pipeline.transcribe import TranscriptWord


class SubtitleBurnError(Exception):
    pass


_WORDS_PER_LINE = 4

_ALIGN_TO_ASS = {"left": 4, "center": 5, "right": 6}


@dataclass
class SubtitleStyle:
    """Style render konkret untuk satu klip, diturunkan dari
    CustomizationConfig.subtitle (backend/customization.py) oleh orchestrator.
    Dipisah dari CustomizationConfig supaya modul pipeline ini tak perlu
    tahu-menahu soal persistence/API kustomisasi -- cuma nilai jadi yang dipakai
    render, sama seperti subtitle_font_size dkk yang sudah dioper sebagai
    parameter polos sebelumnya."""

    font: str = "Arial"
    text_color: str = "#FFFFFF"
    highlight_color: str = "#FFFF00"
    outline_color: str = "#000000"
    shadow_color: str = "#000000"
    outline_width: float = 4.0
    shadow_width: float = 2.0
    bold: bool = True
    background_box: bool = False
    opacity: int = 100
    align: str = "center"
    pos_x: int = 50
    pos_y: int = 70


def _hex_to_ass_color(hex_color: str, alpha: int = 0) -> str:
    """'#RRGGBB' -> ASS '&HAABBGGRR'. alpha ASS terbalik: 0=opaque, 255=transparan."""
    hex_color = hex_color.lstrip("#")
    r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6]
    return f"&H{alpha:02X}{b.upper()}{g.upper()}{r.upper()}"


def _ass_header(
    font_size: int = 80,
    output_width: int = 1080,
    output_height: int = 1920,
    style: SubtitleStyle | None = None,
) -> str:
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {output_width}\n"
        f"PlayResY: {output_height}\n"
        "WrapStyle: 0\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
    )
    if style is None:
        # Default sebelum ada fitur Kustomisasi (tab Kustomisasi nonaktif/section
        # Subtitle nonaktif) -- literal apa adanya, tak boleh berubah biar pipeline
        # existing tetap identik.
        return (
            header
            + f"Style: Default,Arial,{font_size},&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,"
            "-1,0,0,0,100,100,0,0,1,4,2,2,60,60,400,1\n"
            "\n[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        )

    alpha = round((100 - style.opacity) * 255 / 100)
    primary = _hex_to_ass_color(style.text_color, alpha)
    secondary = _hex_to_ass_color(style.highlight_color, alpha)
    outline = _hex_to_ass_color(style.outline_color, alpha)
    back = _hex_to_ass_color(style.shadow_color, alpha)
    bold = -1 if style.bold else 0
    border_style = 3 if style.background_box else 1
    alignment = _ALIGN_TO_ASS.get(style.align, 5)
    return (
        header + f"Style: Default,{style.font},{font_size},{primary},{secondary},{outline},{back},"
        f"{bold},0,0,0,100,100,0,0,{border_style},{style.outline_width},{style.shadow_width},"
        f"{alignment},0,0,0,1\n"
        "\n[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )


def _format_ass_time(seconds: float) -> str:
    """Format detik ke waktu ASS H:MM:SS.CC (centisecond)."""
    cs = round(seconds * 100)
    h, rem = divmod(cs, 360_000)
    m, rem = divmod(rem, 6_000)
    s, c = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{c:02d}"


def join_words(words: list[TranscriptWord]) -> str:
    """Gabung token kata whisper jadi teks biasa (buat preview transkrip).

    Sama seperti generate_ass: kata majemuk berhyphen ("video-on-demand")
    dipecah whisper jadi token terpisah tanpa spasi sebelum sambungannya.
    """
    parts = []
    for i, w in enumerate(words):
        if i > 0 and not w.word.startswith("-"):
            parts.append(" ")
        parts.append(w.word)
    return "".join(parts)


def _generate_karaoke_events(
    words: list[TranscriptWord],
    segment_start: float,
    output_width: int,
    output_height: int,
    style: SubtitleStyle | None,
) -> str:
    pos_tag = ""
    if style is not None:
        x_px = round(output_width * style.pos_x / 100)
        y_px = round(output_height * style.pos_y / 100)
        pos_tag = f"{{\\pos({x_px},{y_px})}}"
    lines = []
    for i in range(0, len(words), _WORDS_PER_LINE):
        group = words[i : i + _WORDS_PER_LINE]
        line_start = group[0].start - segment_start
        line_end = group[-1].end - segment_start

        parts = []
        for j, w in enumerate(group):
            # Durasi \k mencakup jeda ke kata berikutnya agar karaoke tidak drift.
            until = group[j + 1].start if j + 1 < len(group) else w.end
            duration_cs = round((until - w.start) * 100)
            # Whisper motong kata majemuk berhyphen ("video-on-demand") jadi token
            # terpisah ("video", "-on", "-demand") tanpa spasi sebelum sambungannya
            # -- jangan tambah spasi di situ, sisanya tetap dipisah spasi.
            sep = "" if j == 0 or w.word.startswith("-") else " "
            prefix = pos_tag if j == 0 else ""
            parts.append(f"{sep}{prefix}{{\\k{duration_cs}}}{w.word}")

        lines.append(
            f"Dialogue: 0,{_format_ass_time(line_start)},{_format_ass_time(line_end)},"
            f"Default,,0,0,0,,{''.join(parts)}\n"
        )
    return "".join(lines)


def generate_ass(
    words: list[TranscriptWord],
    segment_start: float,
    font_size: int = 80,
    output_width: int = 1080,
    output_height: int = 1920,
    style: SubtitleStyle | None = None,
) -> str:
    """Generate isi file .ass dengan highlight karaoke kata-per-kata.

    Timestamp kata bersifat absolut terhadap video sumber; segment_start dipakai
    untuk menggeser semua waktu jadi relatif terhadap awal klip yang sudah dipotong.

    style=None -> tampilan lama (dipakai saat tab Kustomisasi/section Subtitle
    nonaktif, lihat _ass_header). style diberikan -> posisi dikontrol lewat
    override \\pos() per baris (ikut style.pos_x/pos_y), bukan MarginV statis,
    supaya bisa digeser bebas nanti dari canvas kustomisasi.
    """
    header = _ass_header(font_size, output_width, output_height, style)
    events = _generate_karaoke_events(words, segment_start, output_width, output_height, style)
    return header + events


def burn_subtitle(video_path: Path, ass_path: Path, output_path: Path) -> None:
    """Burn subtitle .ass ke video via ffmpeg (video re-encode, audio copy).

    Raises:
        SubtitleBurnError: ffmpeg keluar dengan kode non-zero.
    """
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vf",
        f"ass=filename={ass_path}",
        "-c:a",
        "copy",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise SubtitleBurnError(f"ffmpeg gagal burn subtitle: {result.stderr[-500:]}")
