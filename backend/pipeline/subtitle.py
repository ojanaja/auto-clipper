import subprocess
from pathlib import Path

from pipeline.transcribe import TranscriptWord


class SubtitleBurnError(Exception):
    pass


_WORDS_PER_LINE = 4

_ASS_HEADER = """\
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, \
BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, \
BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,80,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,\
-1,0,0,0,100,100,0,0,1,4,2,2,60,60,400,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _format_ass_time(seconds: float) -> str:
    """Format detik ke waktu ASS H:MM:SS.CC (centisecond)."""
    cs = round(seconds * 100)
    h, rem = divmod(cs, 360_000)
    m, rem = divmod(rem, 6_000)
    s, c = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{c:02d}"


def generate_ass(words: list[TranscriptWord], segment_start: float) -> str:
    """Generate isi file .ass dengan highlight karaoke kata-per-kata.

    Timestamp kata bersifat absolut terhadap video sumber; segment_start dipakai
    untuk menggeser semua waktu jadi relatif terhadap awal klip yang sudah dipotong.
    """
    lines = [_ASS_HEADER]
    for i in range(0, len(words), _WORDS_PER_LINE):
        group = words[i : i + _WORDS_PER_LINE]
        line_start = group[0].start - segment_start
        line_end = group[-1].end - segment_start

        parts = []
        for j, w in enumerate(group):
            # Durasi \k mencakup jeda ke kata berikutnya agar karaoke tidak drift.
            until = group[j + 1].start if j + 1 < len(group) else w.end
            duration_cs = round((until - w.start) * 100)
            parts.append(f"{{\\k{duration_cs}}}{w.word}")

        lines.append(
            f"Dialogue: 0,{_format_ass_time(line_start)},{_format_ass_time(line_end)},"
            f"Default,,0,0,0,,{' '.join(parts)}\n"
        )
    return "".join(lines)


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
        f"ass={ass_path}",
        "-c:a",
        "copy",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise SubtitleBurnError(f"ffmpeg gagal burn subtitle: {result.stderr[-500:]}")
