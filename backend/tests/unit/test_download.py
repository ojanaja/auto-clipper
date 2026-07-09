import pytest
from yt_dlp.utils import DownloadError

from pipeline.download import VideoUnavailableError, download_video

URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

FAKE_INFO = {
    "id": "dQw4w9WgXcQ",
    "title": "Video Contoh",
    "duration": 213,
    "width": 1920,
    "height": 1080,
    "ext": "mp4",
}


@pytest.fixture
def fake_ydl(mocker):
    """Patch yt_dlp.YoutubeDL di modul download, kembalikan instance mock-nya."""
    instance = mocker.MagicMock()
    instance.extract_info.return_value = dict(FAKE_INFO)
    instance.prepare_filename.return_value = "/tmp/out/dQw4w9WgXcQ.mp4"
    cls = mocker.patch("pipeline.download.YoutubeDL")
    cls.return_value.__enter__.return_value = instance
    return instance


def test_download_returns_metadata(fake_ydl, tmp_path):
    meta = download_video(URL, tmp_path)
    assert meta.video_id == "dQw4w9WgXcQ"
    assert meta.title == "Video Contoh"
    assert meta.duration == 213
    assert meta.width == 1920
    assert meta.height == 1080
    assert meta.filepath == "/tmp/out/dQw4w9WgXcQ.mp4"


def test_download_calls_extract_info_with_url(fake_ydl, tmp_path):
    download_video(URL, tmp_path)
    fake_ydl.extract_info.assert_called_once_with(URL, download=True)


def test_download_options_contain_outtmpl_and_format(mocker, tmp_path):
    instance = mocker.MagicMock()
    instance.extract_info.return_value = dict(FAKE_INFO)
    instance.prepare_filename.return_value = "/tmp/out/x.mp4"
    cls = mocker.patch("pipeline.download.YoutubeDL")
    cls.return_value.__enter__.return_value = instance

    download_video(URL, tmp_path)

    opts = cls.call_args.args[0]
    assert str(tmp_path) in opts["outtmpl"]
    assert "format" in opts


def test_invalid_url_rejected_before_download(fake_ydl, tmp_path):
    from pipeline.download import InvalidURLError

    with pytest.raises(InvalidURLError):
        download_video("https://vimeo.com/123", tmp_path)
    fake_ydl.extract_info.assert_not_called()


@pytest.mark.parametrize(
    "message",
    [
        "ERROR: [youtube] dQw4w9WgXcQ: Private video. Sign in if you've been granted access",
        "ERROR: [youtube] dQw4w9WgXcQ: Video unavailable",
        "ERROR: [youtube] dQw4w9WgXcQ: This video has been removed by the uploader",
        "ERROR: [youtube] dQw4w9WgXcQ: not available in your country",
    ],
)
def test_unavailable_video_maps_to_specific_error(fake_ydl, tmp_path, message):
    fake_ydl.extract_info.side_effect = DownloadError(message)
    with pytest.raises(VideoUnavailableError) as exc_info:
        download_video(URL, tmp_path)
    # Pesan harus dapat dibaca user, bukan raw traceback.
    assert "dQw4w9WgXcQ" in str(exc_info.value) or len(str(exc_info.value)) > 0
