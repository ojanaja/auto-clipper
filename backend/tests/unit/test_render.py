from pathlib import PurePosixPath, PureWindowsPath
from types import SimpleNamespace

import pytest

from pipeline.highlight import Segment
from pipeline.render import (
    RenderError,
    _escape_filter_path,
    _progress_percent,
    probe_dimensions,
    render_segment,
)
from pipeline.transcribe import TranscriptWord

SEGMENT = Segment(start=10.0, end=25.0, score=90, title="Klip", reason="bagus")

WORDS = [
    TranscriptWord(word="sebelum", start=5.0, end=5.5),  # di luar segmen
    TranscriptWord(word="halo", start=10.5, end=11.0),
    TranscriptWord(word="dunia", start=11.2, end=11.8),
    TranscriptWord(word="sesudah", start=30.0, end=30.5),  # di luar segmen
]


def _fake_run_factory(mocker, ffprobe_out="1920,1080"):
    """Mock subprocess.run: ffprobe kembalikan dimensi, ffmpeg sukses, filter ass tersedia."""
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[0] == "ffprobe":
            return SimpleNamespace(returncode=0, stdout=ffprobe_out, stderr="")
        if cmd[0] == "ffmpeg" and "-filters" in cmd:
            return SimpleNamespace(returncode=0, stdout=" ... ass \n", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    mocker.patch("pipeline.render.subprocess.run", side_effect=fake_run)
    return calls


def test_escape_filter_path_escapes_windows_drive_colon():
    # ':' pemisah option filter ffmpeg -> 'C:' drive letter mematahkan parser
    # ("Invalid argument" ke original_size dkk) kalau tak di-escape dua kali
    # (string -vf melewati dua tahap unescape ffmpeg, satu backslash abis di
    # tahap pertama -- diverifikasi manual pakai ffmpeg asli).
    result = _escape_filter_path(PureWindowsPath(r"C:\Users\Fauzan\Movies\sub_abc123.ass"))
    assert result == "C\\\\:/Users/Fauzan/Movies/sub_abc123.ass"
    assert result.count(":") == 1  # cuma colon drive letter yang tersisa (sudah di-escape)


def test_escape_filter_path_posix_unchanged():
    result = _escape_filter_path(PurePosixPath("/tmp/autoclip/sub_abc123.ass"))
    assert result == "/tmp/autoclip/sub_abc123.ass"


def test_probe_dimensions(mocker):
    _fake_run_factory(mocker)
    assert probe_dimensions("video.mp4") == (1920, 1080)


def test_probe_dimensions_failure_raises(mocker):
    def fail(cmd, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="not found")

    mocker.patch("pipeline.render.subprocess.run", side_effect=fail)
    with pytest.raises(RenderError):
        probe_dimensions("hilang.mp4")


def test_render_segment_builds_single_pass_command(mocker, tmp_path):
    calls = _fake_run_factory(mocker)
    output = tmp_path / "clip.mp4"

    render_segment("source.mp4", SEGMENT, WORDS, output, work_dir=tmp_path)

    ffmpeg_cmd = next(c for c in calls if c[0] == "ffmpeg" and "-ss" in c)
    joined = " ".join(ffmpeg_cmd)
    # Cut sesuai timestamp segmen.
    assert "-ss" in ffmpeg_cmd and "10.0" in ffmpeg_cmd
    assert "-to" in ffmpeg_cmd and "25.0" in ffmpeg_cmd
    # Satu -vf berisi crop 9:16 + scale + subtitle (single pass).
    vf = ffmpeg_cmd[ffmpeg_cmd.index("-vf") + 1]
    assert "crop=606:1080:657:0" in vf  # center crop dari 1920x1080
    assert "scale=1080:1920" in vf
    assert "ass=" in vf
    # Output path di akhir.
    assert ffmpeg_cmd[-1] == str(output)
    assert "-y" in joined


def test_render_segment_writes_ass_only_segment_words(mocker, tmp_path):
    _fake_run_factory(mocker)
    render_segment("source.mp4", SEGMENT, WORDS, tmp_path / "c.mp4", work_dir=tmp_path)

    ass_files = list(tmp_path.glob("*.ass"))
    assert len(ass_files) == 1
    content = ass_files[0].read_text()
    assert "halo" in content
    assert "dunia" in content
    assert "sebelum" not in content
    assert "sesudah" not in content
    # Waktu relatif segmen: kata pertama 10.5 - 10.0 = 0.5s.
    assert "0:00:00.50" in content


def test_render_segment_passes_subtitle_style_to_ass(mocker, tmp_path):
    from pipeline.subtitle import SubtitleStyle

    _fake_run_factory(mocker)
    render_segment(
        "source.mp4",
        SEGMENT,
        WORDS,
        tmp_path / "c.mp4",
        work_dir=tmp_path,
        subtitle_style=SubtitleStyle(text_color="#112233", background_box=True),
    )
    ass_files = list(tmp_path.glob("*.ass"))
    content = ass_files[0].read_text()
    assert "&H00332211" in content  # text_color BGR
    style_line = next(line for line in content.splitlines() if line.startswith("Style:"))
    assert style_line.split(",")[15] == "3"  # BorderStyle=3 (background_box)


def test_render_segment_inserts_color_grade_filters_before_subtitle(mocker, tmp_path):
    from pipeline.color_grade import ColorGradeStyle

    calls = _fake_run_factory(mocker)
    render_segment(
        "source.mp4",
        SEGMENT,
        WORDS,
        tmp_path / "c.mp4",
        work_dir=tmp_path,
        color_grade=ColorGradeStyle(contrast=1.3, vignette=0.5),
    )
    ffmpeg_cmd = next(c for c in calls if c[0] == "ffmpeg")
    vf = ffmpeg_cmd[ffmpeg_cmd.index("-vf") + 1]
    assert "eq=contrast=1.3" in vf
    assert "vignette=angle=" in vf
    # eq/vignette harus sebelum filter ass= (subtitle tak ikut ter-grade).
    assert vf.index("eq=contrast") < vf.index("ass=filename")


def test_render_segment_no_color_grade_filters_when_none(mocker, tmp_path):
    calls = _fake_run_factory(mocker)
    render_segment(
        "source.mp4", SEGMENT, WORDS, tmp_path / "c.mp4", work_dir=tmp_path, color_grade=None
    )
    ffmpeg_cmd = next(c for c in calls if c[0] == "ffmpeg")
    vf = ffmpeg_cmd[ffmpeg_cmd.index("-vf") + 1]
    assert "eq=" not in vf
    assert "vignette=" not in vf
    assert "colortemperature=" not in vf


def test_render_segment_ffmpeg_failure_raises(mocker, tmp_path):
    def fake_run(cmd, **kwargs):
        if cmd[0] == "ffprobe":
            return SimpleNamespace(returncode=0, stdout="1920,1080", stderr="")
        return SimpleNamespace(returncode=1, stdout="", stderr="encoder error")

    mocker.patch("pipeline.render.subprocess.run", side_effect=fake_run)
    with pytest.raises(RenderError):
        render_segment("source.mp4", SEGMENT, WORDS, tmp_path / "c.mp4", work_dir=tmp_path)


# --- progress per-detik ---


@pytest.mark.parametrize(
    "line,duration,expected",
    [
        ("out_time_us=0", 15.0, 0),
        ("out_time_us=7500000", 15.0, 50),  # 7.5s / 15s
        ("out_time_us=15000000", 15.0, 100),
        ("out_time_us=30000000", 15.0, 100),  # clamp
        ("out_time_us=N/A", 15.0, None),
        ("frame=12", 15.0, None),  # baris lain diabaikan
        ("out_time_us=7500000", 0.0, None),  # durasi tak diketahui
    ],
)
def test_progress_percent(line, duration, expected):
    assert _progress_percent(line, duration) == expected


def _fake_popen(mocker, lines, returncode=0):
    """Mock ffprobe via run + ffmpeg via Popen dengan stdout baris progress."""
    mocker.patch(
        "pipeline.render.subprocess.run",
        return_value=SimpleNamespace(returncode=0, stdout="1920,1080", stderr=""),
    )
    mocker.patch("pipeline.render._ass_filter_available", return_value=True)
    proc = mocker.MagicMock()
    proc.stdout = iter(lines)
    proc.stderr = iter([] if returncode == 0 else ["encoder error\n"])
    proc.wait.return_value = returncode
    proc.returncode = returncode
    return mocker.patch("pipeline.render.subprocess.Popen", return_value=proc)


def test_render_segment_reports_progress_per_second(mocker, tmp_path):
    popen = _fake_popen(
        mocker,
        [
            "out_time_us=0\n",
            "progress=continue\n",
            "out_time_us=7500000\n",  # 50% dari 15s
            "progress=continue\n",
            "out_time_us=15000000\n",
            "progress=end\n",
        ],
    )
    seen = []

    render_segment(
        "source.mp4",
        SEGMENT,
        WORDS,
        tmp_path / "c.mp4",
        work_dir=tmp_path,
        progress_cb=lambda pct, msg: seen.append(pct),
    )

    assert 50 in seen
    assert seen[-1] == 100
    # ffmpeg pakai -progress pipe:1 supaya progress streaming ke stdout.
    cmd = popen.call_args.args[0]
    assert "-progress" in cmd and "pipe:1" in cmd


def test_render_segment_progress_ffmpeg_failure_raises(mocker, tmp_path):
    _fake_popen(mocker, ["out_time_us=0\n", "progress=end\n"], returncode=1)
    with pytest.raises(RenderError):
        render_segment(
            "source.mp4",
            SEGMENT,
            WORDS,
            tmp_path / "c.mp4",
            work_dir=tmp_path,
            progress_cb=lambda pct, msg: None,
        )


def test_render_segment_1_1_ratio(mocker, tmp_path):
    calls = _fake_run_factory(mocker)
    render_segment(
        "source.mp4",
        SEGMENT,
        WORDS,
        tmp_path / "c.mp4",
        work_dir=tmp_path,
        target_ratio=1 / 1,
        output_width=1080,
        output_height=1080,
    )
    ffmpeg_cmd = next(c for c in calls if c[0] == "ffmpeg")
    vf = ffmpeg_cmd[ffmpeg_cmd.index("-vf") + 1]
    assert "scale=1080:1080" in vf
    assert "crop=1080:1080:420:0" in vf


def test_render_segment_watermark_and_sumber_share_one_ass_file(mocker, tmp_path):
    from pipeline.overlay import TextOverlayStyle

    _fake_run_factory(mocker)
    render_segment(
        "source.mp4",
        SEGMENT,
        WORDS,
        tmp_path / "c.mp4",
        work_dir=tmp_path,
        subtitle_enabled=False,
        watermark_style=TextOverlayStyle(
            text="AutoClip", font="Arial", size=40, color="#FFFFFF", opacity=25, pos_x=50, pos_y=50
        ),
        overlay_sumber_style=TextOverlayStyle(
            text="Sumber: @chan",
            font="Arial",
            size=32,
            color="#FFFFFF",
            opacity=90,
            pos_x=50,
            pos_y=95,
        ),
    )
    ass_files = list(tmp_path.glob("*.ass"))
    assert len(ass_files) == 1
    content = ass_files[0].read_text()
    assert "AutoClip" in content
    assert "Sumber: @chan" in content


def test_render_segment_no_overlay_text_no_ass_file(mocker, tmp_path):
    _fake_run_factory(mocker)
    render_segment(
        "source.mp4",
        SEGMENT,
        WORDS,
        tmp_path / "c.mp4",
        work_dir=tmp_path,
        subtitle_enabled=False,
        watermark_style=None,
        overlay_sumber_style=None,
    )
    assert len(list(tmp_path.glob("*.ass"))) == 0


def test_render_segment_image_overlay_uses_filter_complex(mocker, tmp_path):
    from pipeline.overlay import ImageOverlayStyle

    calls = _fake_run_factory(mocker)
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"fake-png")
    render_segment(
        "source.mp4",
        SEGMENT,
        WORDS,
        tmp_path / "c.mp4",
        work_dir=tmp_path,
        subtitle_enabled=False,
        image_overlay=ImageOverlayStyle(
            image_path=str(logo), size=20, opacity=100, rotate=0.0, pos_x=85, pos_y=12
        ),
    )
    ffmpeg_cmd = next(c for c in calls if c[0] == "ffmpeg" and "-ss" in c)
    assert "-vf" not in ffmpeg_cmd
    assert "-filter_complex" in ffmpeg_cmd
    assert "-loop" in ffmpeg_cmd and "1" in ffmpeg_cmd
    assert "-shortest" in ffmpeg_cmd  # gambar di-loop tanpa EOF, wajib dibatasi -shortest
    assert "-map" in ffmpeg_cmd
    assert "[merged]" in ffmpeg_cmd
    assert "0:a?" in ffmpeg_cmd
    filter_complex = ffmpeg_cmd[ffmpeg_cmd.index("-filter_complex") + 1]
    assert "[0:v]" in filter_complex and "[1:v]" in filter_complex
    assert "overlay=x=" in filter_complex


def test_render_segment_image_overlay_missing_file_falls_back_to_vf(mocker, tmp_path, capsys):
    from pipeline.overlay import ImageOverlayStyle

    calls = _fake_run_factory(mocker)
    render_segment(
        "source.mp4",
        SEGMENT,
        WORDS,
        tmp_path / "c.mp4",
        work_dir=tmp_path,
        subtitle_enabled=False,
        image_overlay=ImageOverlayStyle(
            image_path=str(tmp_path / "tidak-ada.png"),
            size=20,
            opacity=100,
            rotate=0.0,
            pos_x=85,
            pos_y=12,
        ),
    )
    ffmpeg_cmd = next(c for c in calls if c[0] == "ffmpeg" and "-ss" in c)
    assert "-vf" in ffmpeg_cmd
    assert "-filter_complex" not in ffmpeg_cmd
    assert "tidak ditemukan" in capsys.readouterr().err


def test_render_segment_image_overlay_chains_ass_after_overlay(mocker, tmp_path):
    from pipeline.overlay import ImageOverlayStyle, TextOverlayStyle

    calls = _fake_run_factory(mocker)
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"fake-png")
    render_segment(
        "source.mp4",
        SEGMENT,
        WORDS,
        tmp_path / "c.mp4",
        work_dir=tmp_path,
        image_overlay=ImageOverlayStyle(
            image_path=str(logo), size=20, opacity=100, rotate=0.0, pos_x=85, pos_y=12
        ),
        watermark_style=TextOverlayStyle(
            text="AutoClip", font="Arial", size=40, color="#FFFFFF", opacity=25, pos_x=50, pos_y=50
        ),
    )
    ffmpeg_cmd = next(c for c in calls if c[0] == "ffmpeg" and "-ss" in c)
    filter_complex = ffmpeg_cmd[ffmpeg_cmd.index("-filter_complex") + 1]
    assert "[merged]ass=filename=" in filter_complex
    assert filter_complex.rstrip().endswith("[outv]")
    assert "[outv]" in ffmpeg_cmd  # final -map target


def test_render_segment_no_subtitle(mocker, tmp_path):
    calls = _fake_run_factory(mocker)
    render_segment(
        "source.mp4",
        SEGMENT,
        WORDS,
        tmp_path / "c.mp4",
        work_dir=tmp_path,
        subtitle_enabled=False,
    )
    ffmpeg_cmd = next(c for c in calls if c[0] == "ffmpeg")
    vf = ffmpeg_cmd[ffmpeg_cmd.index("-vf") + 1]
    assert "ass=" not in vf
    assert len(list(tmp_path.glob("*.ass"))) == 0


def test_render_segment_uses_custom_encoder(mocker, tmp_path):
    calls = _fake_run_factory(mocker)
    render_segment(
        "source.mp4", SEGMENT, WORDS, tmp_path / "c.mp4", work_dir=tmp_path, encoder="libx264"
    )
    ffmpeg_cmd = next(c for c in calls if c[0] == "ffmpeg")
    assert "-c:v" in ffmpeg_cmd
    assert ffmpeg_cmd[ffmpeg_cmd.index("-c:v") + 1] == "libx264"


def test_render_segment_auto_encoder_omits_video_codec(mocker, tmp_path):
    calls = _fake_run_factory(mocker)
    render_segment("source.mp4", SEGMENT, WORDS, tmp_path / "c.mp4", work_dir=tmp_path)
    ffmpeg_cmd = next(c for c in calls if c[0] == "ffmpeg")
    assert "-c:v" not in ffmpeg_cmd


def test_render_segment_dynamic_crop_path(mocker, tmp_path):
    from pipeline.reframe import CropBox

    calls = _fake_run_factory(mocker)
    crop_path = [
        (10.0, CropBox(x=100, y=200, w=606, h=1080)),
        (11.0, CropBox(x=300, y=200, w=606, h=1080)),
    ]
    render_segment(
        "source.mp4", SEGMENT, WORDS, tmp_path / "c.mp4", work_dir=tmp_path, crop_path=crop_path
    )
    ffmpeg_cmd = next(c for c in calls if c[0] == "ffmpeg")
    vf = ffmpeg_cmd[ffmpeg_cmd.index("-vf") + 1]
    assert "crop=606:1080:x='" in vf
    assert "between(" in vf
    assert "lerp(" in vf
    assert "scale=1080:1920" in vf
