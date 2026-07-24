import re
import subprocess
import sys
import threading
import uuid
from pathlib import Path

from pipeline.color_grade import ColorGradeStyle, build_color_grade_filters
from pipeline.crop_expr import build_crop_x_expr, build_crop_y_expr
from pipeline.highlight import Segment
from pipeline.overlay import (
    ImageOverlayStyle,
    TextOverlayStyle,
    build_image_overlay_filter,
    build_text_overlay_event,
)
from pipeline.reframe import CropBox, compute_crop_box
from pipeline.subtitle import SubtitleStyle, _ass_header, _generate_karaoke_events
from pipeline.transcribe import TranscriptWord


class RenderError(Exception):
    pass


_ASS_FILTER_AVAILABLE: bool | None = None


def _ass_filter_available() -> bool:
    """Cek apakah ffmpeg build ini punya filter 'ass' (libass)."""
    global _ASS_FILTER_AVAILABLE
    if _ASS_FILTER_AVAILABLE is not None:
        return _ASS_FILTER_AVAILABLE
    try:
        result = subprocess.run(["ffmpeg", "-filters"], capture_output=True, text=True, timeout=10)
        _ASS_FILTER_AVAILABLE = bool(re.search(r"^\s*\S+\s+\bass\b", result.stdout, re.MULTILINE))
    except Exception:
        _ASS_FILTER_AVAILABLE = False
    return _ASS_FILTER_AVAILABLE


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


def _escape_filter_path(path: Path) -> str:
    """Escape path untuk value option filter ffmpeg (mis. ass=filename=...).

    Sintaks -vf pakai ':' sebagai pemisah option dan '\\' sebagai escape char.
    Path Windows ("C:\\Users\\...") mematahkan parser: 'C:' kebaca sebagai akhir
    option filename, sisanya salah-parse jadi option lain (mis. "Invalid
    argument" ke original_size). String -vf melewati DUA tahap unescape ffmpeg
    (parse nama+args filter, lalu parse tiap key:value) -- satu backslash abis
    di tahap pertama, jadi colon perlu di-escape dua kali (`\\\\:`) supaya
    lolos ke tahap kedua masih literal. Diverifikasi manual pakai ffmpeg asli.
    """
    return str(path).replace("\\", "/").replace(":", r"\\:")


def _resolve_encoder(encoder: str) -> str | None:
    if encoder == "auto":
        return None
    return encoder


def render_segment(
    source_path: str | Path,
    segment: Segment,
    words: list[TranscriptWord],
    output_path: Path,
    work_dir: Path,
    progress_cb=None,
    target_ratio: float = 9 / 16,
    output_width: int = 1080,
    output_height: int = 1920,
    subtitle_enabled: bool = True,
    subtitle_font_size: int = 80,
    subtitle_style: SubtitleStyle | None = None,
    color_grade: ColorGradeStyle | None = None,
    watermark_style: TextOverlayStyle | None = None,
    overlay_sumber_style: TextOverlayStyle | None = None,
    image_overlay: ImageOverlayStyle | None = None,
    encoder: str = "auto",
    crop_path: list[tuple[float, CropBox]] | None = None,
) -> Path:
    """Render satu segmen: cut + crop target ratio + scale + burn subtitle dalam satu pass ffmpeg.

    progress_cb(percent, message) dipanggil per-detik dari output `ffmpeg -progress`
    supaya bar render bergerak halus (bukan cuma per-klip).

    ponytail: crop pakai center-crop (compute_crop_box tanpa wajah); upgrade path:
    deteksi wajah per sample frame (opencv/mediapipe) lalu median bbox -> crop box.

    Raises:
        RenderError: ffprobe/ffmpeg gagal.
    """
    frame_w, frame_h = probe_dimensions(source_path)

    if crop_path:
        crop_w = round(crop_path[0][1].w)
        crop_h = round(crop_path[0][1].h)
        x_expr = build_crop_x_expr(crop_path, segment.start, frame_w, crop_w)
        y_expr = build_crop_y_expr(crop_path, segment.start, frame_h, crop_h)
        crop_filter = f"crop={crop_w}:{crop_h}:x='{x_expr}':y='{y_expr}'"
    else:
        crop = compute_crop_box(frame_w, frame_h, faces=[], target_ratio=target_ratio)
        crop_filter = f"crop={crop.w}:{crop.h}:{crop.x}:{crop.y}"

    vf_parts = [
        crop_filter,
        f"scale={output_width}:{output_height}",
    ]

    if color_grade is not None:
        # Sebelum subtitle: teks yang diburn tak boleh ikut ter-grade.
        vf_parts.extend(build_color_grade_filters(color_grade))

    # Subtitle karaoke, watermark, dan overlay sumber semua dirender lewat satu
    # file .ass yang sama (satu filter 'ass' saja) -- watermark/sumber cuma
    # teks statis sepanjang klip, jadi dipakai override tag per baris, bukan
    # style [V4+ Styles] terpisah (lihat pipeline/overlay.py).
    ass_filter_str = None
    ass_needed = subtitle_enabled or watermark_style is not None or overlay_sumber_style is not None
    if ass_needed:
        if _ass_filter_available():
            ass_path = Path(work_dir) / f"sub_{uuid.uuid4().hex[:8]}.ass"
            content = _ass_header(subtitle_font_size, output_width, output_height, subtitle_style)
            if subtitle_enabled:
                segment_words = [
                    w for w in words if segment.start <= w.start and w.end <= segment.end
                ]
                content += _generate_karaoke_events(
                    segment_words, segment.start, output_width, output_height, subtitle_style
                )
            duration = segment.end - segment.start
            if watermark_style is not None:
                content += build_text_overlay_event(
                    watermark_style, duration, output_width, output_height
                )
            if overlay_sumber_style is not None:
                content += build_text_overlay_event(
                    overlay_sumber_style, duration, output_width, output_height
                )
            ass_path.write_text(content)
            ass_filter_str = f"ass=filename={_escape_filter_path(ass_path)}"
        else:
            print(
                "WARNING: ffmpeg build ini tidak mendukung filter 'ass' (libass); "
                "subtitle/watermark/overlay sumber tidak diburn.",
                file=sys.stderr,
                flush=True,
            )

    image_path = (
        Path(image_overlay.image_path) if image_overlay and image_overlay.image_path else None
    )
    use_image_overlay = image_path is not None and image_path.exists()
    if image_overlay is not None and image_overlay.image_path and not use_image_overlay:
        print(
            f"WARNING: file overlay gambar tidak ditemukan: {image_overlay.image_path}",
            file=sys.stderr,
            flush=True,
        )

    video_codec = _resolve_encoder(encoder)

    cmd = ["ffmpeg", "-y"]
    if progress_cb is not None:
        # Streaming progress ke stdout; matikan stats agar tak mengotori parse.
        cmd += ["-progress", "pipe:1", "-nostats"]

    if use_image_overlay:
        # Dua input (video + gambar) -> filter_complex, beda dari jalur -vf
        # satu-input di bawah. Gambar di-loop (-loop 1) supaya persist sepanjang
        # durasi klip, bukan cuma 1 frame lalu overlay-nya hilang.
        logo_chain, overlay_expr = build_image_overlay_filter(
            image_overlay, output_width, output_height
        )
        base_chain = ",".join(vf_parts)
        filter_complex = (
            f"[0:v]{base_chain}[base];[1:v]{logo_chain}[logo];[base][logo]{overlay_expr}[merged]"
        )
        final_label = "[merged]"
        if ass_filter_str is not None:
            filter_complex += f";[merged]{ass_filter_str}[outv]"
            final_label = "[outv]"
        cmd += [
            "-ss",
            str(segment.start),
            "-to",
            str(segment.end),
            "-i",
            str(source_path),
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-filter_complex",
            filter_complex,
            "-map",
            final_label,
            "-map",
            "0:a?",
            # Gambar di-loop tanpa batas (tak pernah EOF) -- tanpa -shortest,
            # encode tak pernah berhenti karena durasi output ikut input
            # terpanjang. Ini yang membatasi ke durasi video utama.
            "-shortest",
        ]
    else:
        if ass_filter_str is not None:
            vf_parts.append(ass_filter_str)
        vf = ",".join(vf_parts)
        cmd += [
            "-ss",
            str(segment.start),
            "-to",
            str(segment.end),
            "-i",
            str(source_path),
            "-vf",
            vf,
        ]

    if video_codec is not None:
        cmd += ["-c:v", video_codec]
    cmd += ["-c:a", "aac", "-pix_fmt", "yuv420p", str(output_path)]

    if progress_cb is None:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            full_cmd = " ".join(str(c) for c in cmd)
            err = f"ffmpeg gagal render segmen.\nCMD: {full_cmd}\nSTDERR:\n{result.stderr}"
            print(err, file=sys.stderr, flush=True)
            raise RenderError(err)
        return output_path

    duration = segment.end - segment.start
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    # ffmpeg bisa nulis banyak ke stderr (warning libass/filter). Kalau cuma
    # stdout yang dibaca, buffer pipe stderr penuh -> ffmpeg blok nulis ->
    # seluruh proses freeze ("stuck" di 0%). Drain stderr di thread terpisah
    # biar gak deadlock.
    stderr_lines: list[str] = []
    stderr_thread = threading.Thread(target=lambda: stderr_lines.extend(proc.stderr), daemon=True)
    stderr_thread.start()

    for line in proc.stdout:
        if line.strip() == "progress=end":
            progress_cb(100, "Render 100%")
            continue
        pct = _progress_percent(line, duration)
        if pct is not None:
            progress_cb(pct, f"Render {pct}%")
    returncode = proc.wait()
    stderr_thread.join(timeout=5)
    if returncode != 0:
        err = f"ffmpeg gagal render segmen.\nSTDERR:\n{''.join(stderr_lines)}"
        print(err, file=sys.stderr, flush=True)
        raise RenderError(err)
    return output_path
