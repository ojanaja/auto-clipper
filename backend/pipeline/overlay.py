import math
from dataclasses import dataclass

from pipeline.subtitle import _format_ass_time


@dataclass
class TextOverlayStyle:
    """Style render buat teks statis sepanjang klip (Watermark/Overlay Sumber),
    diturunkan dari CustomizationConfig.watermark / .overlay_sumber oleh
    orchestrator -- sama pola dengan SubtitleStyle/ColorGradeStyle."""

    text: str
    font: str
    size: int
    color: str
    opacity: int
    pos_x: int
    pos_y: int
    rotate: float = 0.0


@dataclass
class ImageOverlayStyle:
    """Style render buat overlay gambar (logo), diturunkan dari
    CustomizationConfig.overlay_gambar."""

    image_path: str
    size: int  # persen lebar output
    opacity: int
    rotate: float
    pos_x: int
    pos_y: int


def _hex_to_ass_rgb(hex_color: str) -> str:
    hex_color = hex_color.lstrip("#")
    r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6]
    return f"&H{b.upper()}{g.upper()}{r.upper()}&"


def _ass_alpha_tag(opacity: int) -> str:
    # ASS alpha terbalik: 0=opaque, 255=transparan (sama seperti pipeline/subtitle.py).
    alpha = round((100 - opacity) * 255 / 100)
    return f"&H{alpha:02X}&"


def _escape_ass_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("\n", "\\N").replace("{", "").replace("}", "")


def build_text_overlay_event(
    style: TextOverlayStyle, duration: float, output_width: int, output_height: int
) -> str:
    """Satu baris Dialogue ASS statis (nongol sepanjang durasi klip) buat
    watermark/overlay sumber. Style di-inline lewat override tag per baris
    (bukan named [V4+ Styles] baru) supaya independen dari style Default subtitle
    karaoke -- reuse filter 'ass' yang sama dipakai subtitle (lihat
    pipeline/render.py _ass_filter_available). drawtext TIDAK dipakai karena
    filter itu tak tersedia di build ffmpeg default (butuh libfreetype)."""
    x_px = round(output_width * style.pos_x / 100)
    y_px = round(output_height * style.pos_y / 100)
    color = _hex_to_ass_rgb(style.color)
    alpha = _ass_alpha_tag(style.opacity)
    text = _escape_ass_text(style.text)
    tags = (
        f"\\an5\\pos({x_px},{y_px})\\fn{style.font}\\fs{style.size}"
        f"\\bord0\\shad0\\1c{color}\\1a{alpha}"
    )
    if style.rotate:
        tags += f"\\frz{style.rotate:.2f}"
    return (
        f"Dialogue: 0,{_format_ass_time(0)},{_format_ass_time(duration)},"
        f"Default,,0,0,0,,{{{tags}}}{text}\n"
    )


def build_image_overlay_filter(
    style: ImageOverlayStyle, output_width: int, output_height: int
) -> tuple[str, str]:
    """Bangun fragment filter_complex buat overlay gambar (logo).

    Return (chain_untuk_input_kedua, xy_expr_filter_overlay). chain diterapkan
    ke label [1:v] (dipanggil pemanggil, biar nama label fleksibel); overlay_w/
    overlay_h dipakai runtime di ekspresi posisi karena ukuran akhir gambar
    berubah kalau dirotasi (bukan dihitung statis di Python).

    Filter dipakai (scale/format/colorchannelmixer/rotate/overlay) sudah
    diverifikasi ada di ffmpeg lokal via `ffmpeg -filters` + tes manual
    end-to-end sebelum dipakai di sini (beda dari ass/drawtext yang butuh
    libass/libfreetype dan tak selalu tersedia).
    """
    logo_w = max(1, round(output_width * style.size / 100))
    parts = [f"scale={logo_w}:-1"]

    needs_alpha = style.opacity < 100 or style.rotate != 0
    if needs_alpha:
        parts.append("format=rgba")
    if style.opacity < 100:
        parts.append(f"colorchannelmixer=aa={style.opacity / 100:.3f}")
    if style.rotate:
        angle = math.radians(style.rotate)
        parts.append(f"rotate={angle:.6f}:c=black@0.0:ow=rotw({angle:.6f}):oh=roth({angle:.6f})")
    chain = ",".join(parts)

    x_expr = f"({output_width}*{style.pos_x}/100)-(overlay_w/2)"
    y_expr = f"({output_height}*{style.pos_y}/100)-(overlay_h/2)"
    return chain, f"overlay=x={x_expr}:y={y_expr}"
