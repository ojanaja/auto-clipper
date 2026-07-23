from pathlib import Path

import pytest

from pipeline.subtitle import (
    SubtitleBurnError,
    _format_ass_time,
    burn_subtitle,
    generate_ass,
    join_words,
)
from pipeline.transcribe import TranscriptWord

FIXTURES = Path(__file__).parents[3] / "tests" / "fixtures"

# Transkrip contoh: segmen video sumber 10.0-13.6s, sudah dipotong jadi klip
# sehingga subtitle pakai waktu relatif terhadap awal segmen.
SAMPLE_WORDS = [
    TranscriptWord(word="Halo", start=10.0, end=10.4),
    TranscriptWord(word="semua", start=10.5, end=10.9),
    TranscriptWord(word="selamat", start=11.0, end=11.5),
    TranscriptWord(word="datang", start=11.6, end=12.0),
    TranscriptWord(word="di", start=12.1, end=12.2),
    TranscriptWord(word="channel", start=12.3, end=12.8),
    TranscriptWord(word="ini", start=12.9, end=13.6),
]


# --- format waktu ASS ---


@pytest.mark.parametrize(
    "seconds,expected",
    [
        (0.0, "0:00:00.00"),
        (1.5, "0:00:01.50"),
        (61.25, "0:01:01.25"),
        (3661.07, "1:01:01.07"),
    ],
)
def test_format_ass_time(seconds, expected):
    assert _format_ass_time(seconds) == expected


# --- join_words ---


def test_join_words_plain_sentence():
    assert join_words(SAMPLE_WORDS) == "Halo semua selamat datang di channel ini"


def test_join_words_hyphenated_compound_no_extra_space():
    words = [
        TranscriptWord(word="video", start=0.0, end=0.3),
        TranscriptWord(word="-on", start=0.3, end=0.5),
        TranscriptWord(word="-demand", start=0.5, end=0.9),
        TranscriptWord(word="secara", start=0.9, end=1.2),
    ]
    assert join_words(words) == "video-on-demand secara"


# --- generate_ass ---


def test_generate_ass_contains_required_sections():
    content = generate_ass(SAMPLE_WORDS, segment_start=10.0)
    assert "[Script Info]" in content
    assert "[V4+ Styles]" in content
    assert "[Events]" in content


def test_generate_ass_times_relative_to_segment_start():
    content = generate_ass(SAMPLE_WORDS, segment_start=10.0)
    # Kata pertama mulai 10.0 absolut -> 0.0 relatif.
    assert "0:00:00.00" in content
    # Tidak ada waktu absolut 10 detik.
    assert "0:00:10.00" not in content


def test_generate_ass_karaoke_tags_per_word():
    content = generate_ass(SAMPLE_WORDS, segment_start=10.0)
    # Tiap kata dapat tag \k (karaoke, durasi centisecond).
    assert content.count("\\k") == len(SAMPLE_WORDS)
    assert "Halo" in content
    assert "channel" in content


def test_generate_ass_empty_words():
    content = generate_ass([], segment_start=0.0)
    # Struktur file tetap valid, tanpa dialogue.
    assert "[Events]" in content
    assert "Dialogue:" not in content


def test_generate_ass_matches_golden_file():
    content = generate_ass(SAMPLE_WORDS, segment_start=10.0)
    golden = (FIXTURES / "expected_subtitle.ass").read_text()
    assert content == golden


def test_generate_ass_uses_custom_font_size():
    content = generate_ass(SAMPLE_WORDS, segment_start=10.0, font_size=120)
    assert "Style: Default,Arial,120," in content


def test_generate_ass_uses_custom_play_res():
    content = generate_ass(SAMPLE_WORDS, segment_start=10.0, output_width=720, output_height=1280)
    assert "PlayResX: 720" in content
    assert "PlayResY: 1280" in content


# --- burn_subtitle ---


@pytest.fixture
def fake_run(mocker):
    run = mocker.patch("pipeline.subtitle.subprocess.run")
    run.return_value.returncode = 0
    return run


def test_burn_subtitle_builds_correct_ffmpeg_command(fake_run, tmp_path):
    video = tmp_path / "clip.mp4"
    ass = tmp_path / "sub.ass"
    output = tmp_path / "final.mp4"

    burn_subtitle(video, ass, output)

    args = fake_run.call_args.args[0]
    assert args[0] == "ffmpeg"
    assert "-i" in args and str(video) in args
    vf_idx = args.index("-vf")
    assert f"ass=filename={ass}" == args[vf_idx + 1]
    assert str(output) == args[-1]
    # Audio tidak di-reencode.
    aidx = args.index("-c:a")
    assert args[aidx + 1] == "copy"


def test_burn_subtitle_overwrites_existing_output(fake_run, tmp_path):
    burn_subtitle(tmp_path / "a.mp4", tmp_path / "s.ass", tmp_path / "o.mp4")
    assert "-y" in fake_run.call_args.args[0]


def test_burn_subtitle_nonzero_exit_raises(fake_run, tmp_path):
    fake_run.return_value.returncode = 1
    fake_run.return_value.stderr = "Error opening filter"

    with pytest.raises(SubtitleBurnError):
        burn_subtitle(tmp_path / "a.mp4", tmp_path / "s.ass", tmp_path / "o.mp4")
