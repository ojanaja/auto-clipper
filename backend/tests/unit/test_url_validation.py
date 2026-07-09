import pytest

from pipeline.download import InvalidURLError, validate_youtube_url


@pytest.mark.parametrize(
    "url,video_id",
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("http://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/live/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://m.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ],
)
def test_valid_urls_return_video_id(url, video_id):
    assert validate_youtube_url(url) == video_id


@pytest.mark.parametrize(
    "url",
    [
        "",
        "bukan url",
        "https://vimeo.com/12345",
        "https://www.youtube.com/",
        "https://www.youtube.com/watch",
        "https://www.youtube.com/watch?v=",
        "https://www.youtube.com/watch?v=terlalu-pendek-atau-karakter!aneh tapi panjang",
        "ftp://youtube.com/watch?v=dQw4w9WgXcQ",
        "https://notyoutube.com/watch?v=dQw4w9WgXcQ",
    ],
)
def test_invalid_urls_raise(url):
    with pytest.raises(InvalidURLError):
        validate_youtube_url(url)
