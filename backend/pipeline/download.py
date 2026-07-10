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


def _make_progress_hook(progress_cb):
    """Ubah dict progress yt-dlp jadi panggilan progress_cb(percent, message)."""

    def hook(d):
        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            pct = int(done / total * 100) if total else 0
            msg = f"Mengunduh {done / 1_048_576:.1f} MB"
            if total:
                msg += f" / {total / 1_048_576:.1f} MB"
            speed = d.get("speed")
            if speed:
                msg += f" • {speed / 1_048_576:.1f} MB/s"
            eta = d.get("eta")
            if eta:
                msg += f" • ETA {int(eta) // 60}:{int(eta) % 60:02d}"
            progress_cb(pct, msg)
        elif status == "finished":
            progress_cb(100, "Unduhan selesai, memproses")

    return hook


def download_video(url: str, dest_dir: Path, progress_cb=None) -> VideoMetadata:
    """Download video+audio kualitas terbaik ke dest_dir, kembalikan metadata.

    progress_cb(percent, message) dipanggil live selama unduhan berlangsung
    (dari yt-dlp progress hook) supaya UI tidak terlihat freeze di 0%.

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
    if progress_cb is not None:
        opts["progress_hooks"] = [_make_progress_hook(progress_cb)]
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
