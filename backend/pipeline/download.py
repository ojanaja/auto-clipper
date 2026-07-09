import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com"}


class InvalidURLError(Exception):
    pass


class VideoUnavailableError(Exception):
    pass


class DownloadFailedError(Exception):
    pass


@dataclass
class VideoMetadata:
    video_id: str
    title: str
    duration: int
    width: int | None
    height: int | None
    filepath: str


def validate_youtube_url(url: str) -> str:
    """Validasi URL YouTube dan kembalikan video ID-nya.

    Raises:
        InvalidURLError: URL bukan link video YouTube yang dikenali.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise InvalidURLError(f"Bukan URL http(s): {url!r}")

    video_id = None
    if parsed.hostname == "youtu.be":
        video_id = parsed.path.lstrip("/")
    elif parsed.hostname in _YOUTUBE_HOSTS:
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [None])[0]
        else:
            m = re.match(r"^/(shorts|live)/([^/?]+)", parsed.path)
            if m:
                video_id = m.group(2)

    if not video_id or not _VIDEO_ID_RE.match(video_id):
        raise InvalidURLError(f"Bukan URL video YouTube yang valid: {url!r}")
    return video_id


# Pola pesan error yt-dlp yang berarti video memang tidak bisa diakses
# (bukan kegagalan teknis yang layak di-retry).
_UNAVAILABLE_PATTERNS = (
    "private video",
    "video unavailable",
    "has been removed",
    "not made this video available",
    "not available in your country",
)


def download_video(url: str, dest_dir: Path) -> VideoMetadata:
    """Download video+audio kualitas terbaik ke dest_dir, kembalikan metadata.

    Raises:
        InvalidURLError: URL bukan link YouTube valid.
        VideoUnavailableError: video privat/dihapus/region-locked.
        DownloadFailedError: kegagalan download lainnya (jaringan, dsb).
    """
    video_id = validate_youtube_url(url)

    opts = {
        "format": "bestvideo+bestaudio/best",
        "outtmpl": str(Path(dest_dir) / "%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
    }
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filepath = ydl.prepare_filename(info)
    except DownloadError as e:
        msg = str(e)
        if any(p in msg.lower() for p in _UNAVAILABLE_PATTERNS):
            raise VideoUnavailableError(
                f"Video {video_id} tidak dapat diakses (privat/dihapus/dibatasi wilayah)."
            ) from e
        raise DownloadFailedError(f"Download gagal untuk video {video_id}: {msg}") from e

    return VideoMetadata(
        video_id=info["id"],
        title=info.get("title", ""),
        duration=int(info.get("duration") or 0),
        width=info.get("width"),
        height=info.get("height"),
        filepath=filepath,
    )
