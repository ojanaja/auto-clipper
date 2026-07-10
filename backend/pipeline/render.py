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


def _progress_percent(line: str, duration: float) -> int | None:
    """Parse satu baris output `ffmpeg -progress` jadi persen 0-100.

    Hanya baris out_time_us yang relevan; sisanya kembalikan None.
    """
    line = line.strip()
    if not line.startswith("out_time_us=") or duration <= 0:
        return None
    value = line.split("=", 1)[1]
    if not value.isdigit():  # "N/A" di awal encode
        return None
    return min(100, int(int(value) / 1_000_000 / duration * 100))


def render_segment(
    source_path: str | Path,
    segment: Segment,
    words: list[TranscriptWord],
    output_path: Path,
    work_dir: Path,
    progress_cb=None,
) -> Path:
    """Render satu segmen: cut + crop 9:16 + scale + burn subtitle dalam satu pass ffmpeg.

    progress_cb(percent, message) dipanggil per-detik dari output `ffmpeg -progress`
    supaya bar render bergerak halus (bukan cuma per-klip).

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
        f"ass=filename={ass_path}"
    )
    cmd = ["ffmpeg", "-y"]
    if progress_cb is not None:
        # Streaming progress ke stdout; matikan stats agar tak mengotori parse.
        cmd += ["-progress", "pipe:1", "-nostats"]
    cmd += [
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

    if progress_cb is None:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            full_cmd = " ".join(str(c) for c in cmd)
            raise RenderError(
                f"ffmpeg gagal render segmen.\nCMD: {full_cmd}\nSTDERR:\n{result.stderr}"
            )
        return output_path

    duration = segment.end - segment.start
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for line in proc.stdout:
        if line.strip() == "progress=end":
            progress_cb(100, "Render 100%")
            continue
        pct = _progress_percent(line, duration)
        if pct is not None:
            progress_cb(pct, f"Render {pct}%")
    returncode = proc.wait()
    if returncode != 0:
        raise RenderError(f"ffmpeg gagal render segmen.\nSTDERR:\n{proc.stderr.read()}")
    return output_path
