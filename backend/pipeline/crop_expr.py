"""Bangun ffmpeg expression untuk crop dinamis x(t)/y(t)."""

from pipeline.reframe import CropBox


def _format_time(t: float) -> str:
    return f"{t:.3f}".rstrip("0").rstrip(".")


def build_crop_x_expr(
    path: list[tuple[float, CropBox]], clip_start: float, frame_w: int, crop_w: int
) -> str:
    """Bangun expression x(t) piecewise-linear dari jalur crop."""
    if not path:
        center = (frame_w - crop_w) / 2
        return f"clip({center},0,{frame_w - crop_w})"

    if len(path) == 1:
        x = round(path[0][1].x)
        return f"clip({x},0,{frame_w - crop_w})"

    parts = []
    first_t, first_box = path[0]
    first_tr = _format_time(first_t - clip_start)
    parts.append(f"lt(t,{first_tr})*{round(first_box.x)}")

    for (t1, b1), (t2, b2) in zip(path, path[1:]):
        t1r = _format_time(t1 - clip_start)
        t2r = _format_time(t2 - clip_start)
        x1 = round(b1.x)
        x2 = round(b2.x)
        parts.append(
            f"between(t,{t1r},{t2r})*lerp({x1},{x2},(t-{t1r})/({_format_time(t2 - t1)}))"
        )

    last_t, last_box = path[-1]
    last_tr = _format_time(last_t - clip_start)
    parts.append(f"gte(t,{last_tr})*{round(last_box.x)}")

    return f"clip({'+'.join(parts)},0,{frame_w - crop_w})"


def build_crop_y_expr(
    path: list[tuple[float, CropBox]], clip_start: float, frame_h: int, crop_h: int
) -> str:
    """Bangun expression y(t) piecewise-linear dari jalur crop."""
    if not path:
        center = (frame_h - crop_h) / 2
        return f"clip({center},0,{frame_h - crop_h})"

    if len(path) == 1:
        y = round(path[0][1].y)
        return f"clip({y},0,{frame_h - crop_h})"

    parts = []
    first_t, first_box = path[0]
    first_tr = _format_time(first_t - clip_start)
    parts.append(f"lt(t,{first_tr})*{round(first_box.y)}")

    for (t1, b1), (t2, b2) in zip(path, path[1:]):
        t1r = _format_time(t1 - clip_start)
        t2r = _format_time(t2 - clip_start)
        y1 = round(b1.y)
        y2 = round(b2.y)
        parts.append(
            f"between(t,{t1r},{t2r})*lerp({y1},{y2},(t-{t1r})/({_format_time(t2 - t1)}))"
        )

    last_t, last_box = path[-1]
    last_tr = _format_time(last_t - clip_start)
    parts.append(f"gte(t,{last_tr})*{round(last_box.y)}")

    return f"clip({'+'.join(parts)},0,{frame_h - crop_h})"
