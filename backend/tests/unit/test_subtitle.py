from pathlib import Path

import pytest

from pipeline.subtitle import (
    SubtitleBurnError,
    SubtitleStyle,
    _format_ass_time,
    _hex_to_ass_color,
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


# --- _hex_to_ass_color ---


@pytest.mark.parametrize(
    "hex_color,alpha,expected",
    [
        ("#FFFFFF", 0, "&H00FFFFFF"),
        ("#000000", 0, "&H00000000"),
        ("#FF0000", 0, "&H000000FF"),  # ASS BGR: red -> RR di posisi akhir
        ("#00FF00", 0, "&H0000FF00"),
        ("#0000FF", 0, "&H00FF0000"),
        ("#ffffff", 128, "&H80FFFFFF"),  # lowercase input diterima, alpha custom
    ],
)
def test_hex_to_ass_color(hex_color, alpha, expected):
    assert _hex_to_ass_color(hex_color, alpha) == expected


# --- generate_ass dengan style (Kustomisasi aktif) ---


def _style(**overrides):
    return SubtitleStyle(**overrides)


def test_generate_ass_without_style_unchanged_from_before():
    # style=None (default) harus identik dgn output sebelum fitur Kustomisasi ada.
    content = generate_ass(SAMPLE_WORDS, segment_start=10.0)
    golden = (FIXTURES / "expected_subtitle.ass").read_text()
    assert content == golden
    assert "\\pos(" not in content


def test_generate_ass_with_style_uses_style_colors():
    content = generate_ass(SAMPLE_WORDS, segment_start=10.0, style=_style(text_color="#112233"))
    assert "&H00332211" in content  # BGR dari #112233, alpha 0 (opacity 100 default)


def test_generate_ass_with_style_opacity_sets_alpha():
    content = generate_ass(SAMPLE_WORDS, segment_start=10.0, style=_style(opacity=50))
    # alpha = round((100-50)*255/100) = 128 = 0x80
    assert "&H80" in content


def test_generate_ass_with_style_background_box_uses_border_style_3():
    content = generate_ass(SAMPLE_WORDS, segment_start=10.0, style=_style(background_box=True))
    style_line = next(line for line in content.splitlines() if line.startswith("Style:"))
    fields = style_line.split(",")
    assert fields[15] == "3"  # BorderStyle


def test_generate_ass_with_style_no_background_box_uses_border_style_1():
    content = generate_ass(SAMPLE_WORDS, segment_start=10.0, style=_style(background_box=False))
    style_line = next(line for line in content.splitlines() if line.startswith("Style:"))
    assert style_line.split(",")[15] == "1"


def test_generate_ass_with_style_bold_flag():
    content = generate_ass(SAMPLE_WORDS, segment_start=10.0, style=_style(bold=False))
    style_line = next(line for line in content.splitlines() if line.startswith("Style:"))
    assert style_line.split(",")[7] == "0"


@pytest.mark.parametrize("align,expected", [("left", "4"), ("center", "5"), ("right", "6")])
def test_generate_ass_with_style_alignment(align, expected):
    content = generate_ass(SAMPLE_WORDS, segment_start=10.0, style=_style(align=align))
    style_line = next(line for line in content.splitlines() if line.startswith("Style:"))
    assert style_line.split(",")[18] == expected


def test_generate_ass_with_style_pos_override_matches_percentage():
    content = generate_ass(
        SAMPLE_WORDS,
        segment_start=10.0,
        output_width=1000,
        output_height=2000,
        style=_style(pos_x=25, pos_y=75),
    )
    assert "\\pos(250,1500)" in content


def test_generate_ass_with_style_pos_tag_only_on_first_word_per_line():
    content = generate_ass(SAMPLE_WORDS, segment_start=10.0, style=_style())
    assert content.count("\\pos(") == 2  # 7 kata / 4 per baris = 2 baris


def test_generate_ass_with_style_uses_custom_font():
    content = generate_ass(SAMPLE_WORDS, segment_start=10.0, style=_style(font="Impact"))
    assert "Style: Default,Impact," in content


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
