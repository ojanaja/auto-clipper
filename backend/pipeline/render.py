import subprocess
import uuid
from pathlib import Path

from pipeline.highlight import Segment
from pipeline.reframe import compute_crop_box
from pipeline.subtitle import generate_ass
from pipeline.transcribe import TranscriptWord


class RenderError(Exception):
    pass


def probe_dimensions(video_path: str | Path) -> tuple[int, int]:
    """Ambil lebar x tinggi video via ffprobe.

    Raises:
        RenderError: ffprobe gagal membaca file.
    """
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=p=0",
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RenderError(f"ffprobe gagal membaca {video_path}: {result.stderr[-300:]}")
    w, h = result.stdout.strip().split(",")[:2]
    return int(w), int(h)


def render_segment(
    source_path: str | Path,
    segment: Segment,
    words: list[TranscriptWord],
    output_path: Path,
    work_dir: Path,
) -> Path:
    """Render satu segmen: cut + crop 9:16 + scale + burn subtitle dalam satu pass ffmpeg.

    ponytail: crop pakai center-crop (compute_crop_box tanpa wajah); upgrade path:
    deteksi wajah per sample frame (opencv/mediapipe) lalu median bbox -> crop box.

    Raises:
        RenderError: ffprobe/ffmpeg gagal.
    """
    frame_w, frame_h = probe_dimensions(source_path)
    crop = compute_crop_box(frame_w, frame_h, faces=[])

    segment_words = [w for w in words if segment.start <= w.start and w.end <= segment.end]
    ass_path = Path(work_dir) / f"sub_{uuid.uuid4().hex[:8]}.ass"
    ass_path.write_text(generate_ass(segment_words, segment_start=segment.start))

    vf = (
        f"crop={crop.w}:{crop.h}:{crop.x}:{crop.y},"
        f"scale=1080:1920,"
        f"ass={ass_path}"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        str(segment.start),
        "-to",
        str(segment.end),
        "-i",
        str(source_path),
        "-vf",
        vf,
        "-c:a",
        "aac",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RenderError(f"ffmpeg gagal render segmen: {result.stderr[-500:]}")
    return output_path
