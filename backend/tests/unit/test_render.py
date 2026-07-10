from types import SimpleNamespace

import pytest

from pipeline.highlight import Segment
from pipeline.render import (
    RenderError,
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
    """Mock subprocess.run: ffprobe kembalikan dimensi, ffmpeg sukses."""
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[0] == "ffprobe":
            return SimpleNamespace(returncode=0, stdout=ffprobe_out, stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    mocker.patch("pipeline.render.subprocess.run", side_effect=fake_run)
    return calls


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

    ffmpeg_cmd = next(c for c in calls if c[0] == "ffmpeg")
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
    proc = mocker.MagicMock()
    proc.stdout = iter(lines)
    proc.stderr.read.return_value = "" if returncode == 0 else "encoder error"
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
