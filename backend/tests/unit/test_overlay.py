import math

from pipeline.overlay import (
    ImageOverlayStyle,
    TextOverlayStyle,
    build_image_overlay_filter,
    build_text_overlay_event,
)


def _text_style(**overrides):
    defaults = dict(
        text="Sumber: @channel",
        font="Arial",
        size=32,
        color="#FFFFFF",
        opacity=90,
        pos_x=50,
        pos_y=95,
        rotate=0.0,
    )
    defaults.update(overrides)
    return TextOverlayStyle(**defaults)


# --- build_text_overlay_event ---


def test_text_overlay_event_spans_full_duration():
    event = build_text_overlay_event(
        _text_style(), duration=12.5, output_width=1080, output_height=1920
    )
    assert event.startswith("Dialogue: 0,0:00:00.00,0:00:12.50,Default,,0,0,0,,")


def test_text_overlay_event_contains_escaped_text():
    event = build_text_overlay_event(
        _text_style(text="Halo"), duration=1.0, output_width=1080, output_height=1920
    )
    assert event.rstrip("\n").endswith("Halo")


def test_text_overlay_event_pos_matches_percentage():
    event = build_text_overlay_event(
        _text_style(pos_x=50, pos_y=95), duration=1.0, output_width=1000, output_height=2000
    )
    assert r"\pos(500,1900)" in event


def test_text_overlay_event_color_is_bgr_hex():
    event = build_text_overlay_event(
        _text_style(color="#112233"), duration=1.0, output_width=1080, output_height=1920
    )
    assert r"\1c&H332211&" in event


def test_text_overlay_event_opacity_sets_alpha():
    # ASS alpha terbalik: opacity 90% -> alpha rendah (dekat opaque).
    event = build_text_overlay_event(
        _text_style(opacity=90), duration=1.0, output_width=1080, output_height=1920
    )
    assert r"\1a&H1A&" in event


def test_text_overlay_event_no_rotate_tag_when_zero():
    event = build_text_overlay_event(
        _text_style(rotate=0.0), duration=1.0, output_width=1080, output_height=1920
    )
    assert "\\frz" not in event


def test_text_overlay_event_rotate_tag_when_nonzero():
    event = build_text_overlay_event(
        _text_style(rotate=-30.0), duration=1.0, output_width=1080, output_height=1920
    )
    assert r"\frz-30.00" in event


def test_text_overlay_event_no_outline_or_shadow():
    # Watermark/sumber "ghost" -- flat, tanpa border/shadow (beda dari subtitle karaoke).
    event = build_text_overlay_event(
        _text_style(), duration=1.0, output_width=1080, output_height=1920
    )
    assert r"\bord0\shad0" in event


def test_text_overlay_event_strips_braces_to_avoid_injecting_ass_tags():
    event = build_text_overlay_event(
        _text_style(text="{\\pos(0,0)}pwned"), duration=1.0, output_width=1080, output_height=1920
    )
    text_part = event.split("}", 1)[1]
    assert "{" not in text_part and "}" not in text_part


# --- build_image_overlay_filter ---


def _image_style(**overrides):
    defaults = dict(
        image_path="/tmp/logo.png", size=20, opacity=100, rotate=0.0, pos_x=85, pos_y=12
    )
    defaults.update(overrides)
    return ImageOverlayStyle(**defaults)


def test_image_overlay_scale_uses_percent_of_output_width():
    chain, _ = build_image_overlay_filter(
        _image_style(size=20), output_width=1080, output_height=1920
    )
    assert chain.startswith("scale=216:-1")


def test_image_overlay_full_opacity_skips_colorchannelmixer():
    chain, _ = build_image_overlay_filter(
        _image_style(opacity=100), output_width=1080, output_height=1920
    )
    assert "colorchannelmixer" not in chain
    assert "format=rgba" not in chain


def test_image_overlay_partial_opacity_adds_colorchannelmixer():
    chain, _ = build_image_overlay_filter(
        _image_style(opacity=50), output_width=1080, output_height=1920
    )
    assert "format=rgba" in chain
    assert "colorchannelmixer=aa=0.500" in chain


def test_image_overlay_no_rotate_skips_rotate_filter():
    chain, _ = build_image_overlay_filter(
        _image_style(rotate=0.0), output_width=1080, output_height=1920
    )
    assert "rotate=" not in chain


def test_image_overlay_rotate_adds_transparent_rotate_filter():
    chain, _ = build_image_overlay_filter(
        _image_style(rotate=90.0), output_width=1080, output_height=1920
    )
    assert "format=rgba" in chain
    angle = math.radians(90.0)
    assert f"rotate={angle:.6f}:c=black@0.0" in chain
    assert f"ow=rotw({angle:.6f})" in chain
    assert f"oh=roth({angle:.6f})" in chain


def test_image_overlay_position_expr_uses_percent_and_dynamic_size():
    _, expr = build_image_overlay_filter(
        _image_style(pos_x=85, pos_y=12), output_width=1080, output_height=1920
    )
    assert expr == "overlay=x=(1080*85/100)-(overlay_w/2):y=(1920*12/100)-(overlay_h/2)"


def test_image_overlay_size_rounds_to_at_least_one_pixel():
    chain, _ = build_image_overlay_filter(_image_style(size=1), output_width=10, output_height=10)
    assert chain.startswith("scale=1:-1")  # 10*1/100=0.1 -> round jadi 0, dipaksa minimal 1
