import math

import pytest

from pipeline.color_grade import (
    ColorGradeStyle,
    _kelvin_from_temperature,
    build_color_grade_filters,
)


def test_default_style_produces_no_filters():
    assert build_color_grade_filters(ColorGradeStyle()) == []


def test_contrast_only_produces_eq_with_contrast():
    filters = build_color_grade_filters(ColorGradeStyle(contrast=1.3))
    assert filters == ["eq=contrast=1.3"]


def test_multiple_eq_fields_combined_in_one_eq_filter():
    filters = build_color_grade_filters(
        ColorGradeStyle(contrast=1.2, brightness=0.1, saturation=0.8, gamma=1.1)
    )
    assert len(filters) == 1
    assert filters[0].startswith("eq=")
    assert "contrast=1.2" in filters[0]
    assert "brightness=0.1" in filters[0]
    assert "saturation=0.8" in filters[0]
    assert "gamma=1.1" in filters[0]


@pytest.mark.parametrize(
    "temperature,expected_kelvin",
    [
        (0, 6500),
        (40, 5300),  # hangat -> kelvin turun
        (-40, 7700),  # dingin -> kelvin naik
        (100, 3500),
        (-100, 9500),
        (1000, 1000),  # clamp bawah
        (-2000, 40000),  # clamp atas
    ],
)
def test_kelvin_from_temperature(temperature, expected_kelvin):
    assert _kelvin_from_temperature(temperature) == expected_kelvin


def test_temperature_nonzero_produces_colortemperature_filter():
    filters = build_color_grade_filters(ColorGradeStyle(temperature=40))
    assert filters == ["colortemperature=temperature=5300"]


def test_temperature_zero_produces_no_colortemperature_filter():
    filters = build_color_grade_filters(ColorGradeStyle(temperature=0))
    assert not any("colortemperature" in f for f in filters)


def test_vignette_zero_produces_no_vignette_filter():
    filters = build_color_grade_filters(ColorGradeStyle(vignette=0.0))
    assert not any("vignette" in f for f in filters)


def test_vignette_positive_produces_vignette_filter_with_angle():
    filters = build_color_grade_filters(ColorGradeStyle(vignette=1.0))
    vignette_filter = next(f for f in filters if f.startswith("vignette="))
    angle = float(vignette_filter.split("angle=")[1])
    assert angle == pytest.approx(math.pi / 8, abs=1e-3)


def test_vignette_stronger_value_yields_smaller_angle():
    weak = build_color_grade_filters(ColorGradeStyle(vignette=0.2))
    strong = build_color_grade_filters(ColorGradeStyle(vignette=0.8))
    weak_angle = float(weak[0].split("angle=")[1])
    strong_angle = float(strong[0].split("angle=")[1])
    assert strong_angle < weak_angle


def test_all_fields_combined_produces_three_filters():
    style = ColorGradeStyle(contrast=1.2, temperature=20, vignette=0.5)
    filters = build_color_grade_filters(style)
    assert len(filters) == 3
    assert filters[0].startswith("eq=")
    assert filters[1].startswith("colortemperature=")
    assert filters[2].startswith("vignette=")
