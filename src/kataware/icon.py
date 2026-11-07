"""Tray / menu bar icon rendering (pure Pillow, no system fonts needed)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from .models import LabeledLevel

SIZE = 64

GREEN = (46, 204, 113, 255)
ORANGE = (243, 156, 18, 255)
RED = (231, 76, 60, 255)
GRAY = (149, 165, 166, 255)
WHITE = (255, 255, 255, 255)
DARK = (40, 44, 52, 255)


def level_color(level: int | None, low: int = 20) -> tuple[int, int, int, int]:
    if level is None:
        return GRAY
    if level <= max(low, 10):
        return RED
    if level <= 50:
        return ORANGE
    return GREEN


@lru_cache(maxsize=64)
def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # very old Pillow
        return ImageFont.load_default()


def _fit_text(draw: ImageDraw.ImageDraw, text: str, max_w: int, max_h: int, start: int):
    size = start
    while size > 8:
        font = _font(size)
        l, t, r, b = draw.textbbox((0, 0), text, font=font)
        if r - l <= max_w and b - t <= max_h:
            return font, (l, t, r, b)
        size -= 1
    font = _font(8)
    return font, draw.textbbox((0, 0), text, font=font)


def _centered(draw, text, box, color, start):
    x0, y0, x1, y1 = box
    font, (l, t, r, b) = _fit_text(draw, text, x1 - x0, y1 - y0, start)
    x = x0 + (x1 - x0 - (r - l)) / 2 - l
    y = y0 + (y1 - y0 - (b - t)) / 2 - t
    draw.text((x, y), text, font=font, fill=color)


def _num(level: int | None) -> str:
    return "--" if level is None else str(level)


BOLT = (255, 214, 10, 255)


def _bolt(draw: ImageDraw.ImageDraw, cx: float, cy: float, s: float) -> None:
    """Charging mark: a yellow lightning bolt centred on (cx, cy), half-height s."""
    pts = [(cx + 0.30 * s, cy - s), (cx - 0.55 * s, cy + 0.12 * s), (cx - 0.05 * s, cy + 0.12 * s),
           (cx - 0.30 * s, cy + s), (cx + 0.55 * s, cy - 0.15 * s), (cx + 0.05 * s, cy - 0.15 * s)]
    draw.polygon(pts, fill=BOLT, outline=(40, 28, 0, 255))


# --- "ring" style: silver bezel, half rings for left / right ---------------

_FONT_FILE = Path(__file__).resolve().parent / "assets" / "InterDisplay-Bold.otf"
_R = SIZE * 4  # drawn at 4x and scaled down for smooth edges
_RC = _R // 2


@lru_cache(maxsize=16)
def _ring_font(px: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype(str(_FONT_FILE), px)
    except Exception:  # font missing: still draw something readable
        return _font(px)


def _vgrad(c1, c2) -> Image.Image:
    g = Image.new("RGBA", (_R, _R))
    d = ImageDraw.Draw(g)
    for y in range(_R):
        t = y / (_R - 1)
        d.line((0, y, _R, y), fill=tuple(int(c1[k] + (c2[k] - c1[k]) * t) for k in range(4)))
    return g


@lru_cache(maxsize=1)
def _ring_base() -> Image.Image:
    """Shadow, silver bezel and the recessed dark face (identical for every icon)."""
    def disc(r, dy=0):
        m = Image.new("L", (_R, _R), 0)
        ImageDraw.Draw(m).ellipse((_RC - r, _RC - r + dy, _RC + r, _RC + r + dy), fill=255)
        return m

    im = Image.new("RGBA", (_R, _R), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (_R, _R), (0, 0, 0, 0))
    shadow.putalpha(disc(118, 6).filter(ImageFilter.GaussianBlur(6)).point(lambda v: int(v * 0.55)))
    im.alpha_composite(shadow)
    im.paste(_vgrad((236, 240, 246, 255), (98, 106, 122, 255)), (0, 0), disc(122))
    im.paste(_vgrad((10, 12, 18, 255), (34, 40, 56, 255)), (0, 0), disc(110))
    inner = ImageChops.subtract(disc(110), disc(104, 5)).filter(ImageFilter.GaussianBlur(3))
    im.paste((0, 0, 0, 255), (0, 0), inner.point(lambda v: int(v * 0.8)))
    return im


@lru_cache(maxsize=1)
def _ring_gloss() -> Image.Image:
    face = Image.new("L", (_R, _R), 0)
    ImageDraw.Draw(face).ellipse((_RC - 108, _RC - 108, _RC + 108, _RC + 108), fill=255)
    hl = Image.new("L", (_R, _R), 0)
    ImageDraw.Draw(hl).ellipse((_RC - 92, _RC - 104, _RC + 92, _RC - 8), fill=60)
    hl = ImageChops.multiply(hl.filter(ImageFilter.GaussianBlur(10)), face)
    out = Image.new("RGBA", (_R, _R), (255, 255, 255, 0))
    out.putalpha(hl)
    return out


def _arc_mask(a0: float, a1: float, r_out: int, r_in: int) -> Image.Image:
    m = Image.new("L", (_R, _R), 0)
    d = ImageDraw.Draw(m)
    d.pieslice((_RC - r_out, _RC - r_out, _RC + r_out, _RC + r_out), a0, a1, fill=255)
    d.ellipse((_RC - r_in, _RC - r_in, _RC + r_in, _RC + r_in), fill=0)
    return m


def _lighten(c, f):
    return tuple(min(255, int(v + (255 - v) * f)) for v in c[:3]) + (255,)


def _darken(c, f):
    return tuple(int(v * (1 - f)) for v in c[:3]) + (255,)


def _render_ring(shown: list[LabeledLevel], color, connected: bool) -> Image.Image:
    im = _ring_base().copy()
    r_out, r_in = 100, 80
    # PIL angles: 0° = 3 o'clock, increasing clockwise (90° = 6 o'clock).
    # Two batteries: left half 98°→262° and right half 82°→-82°, both filling
    # from the bottom up. One battery: a ring with a gap at the bottom, filling
    # clockwise from the bottom-left.
    if len(shown) == 2:
        tracks = [(98, 262, True), (-82, 82, False)]  # (start, end, fills from start?)
    else:
        tracks = [(101, 439, True)]
    for (a0, a1, from_start), lv in zip(tracks, shown):
        im.paste((40, 46, 60, 255), (0, 0), _arc_mask(a0, a1, r_out, r_in))
        if not lv.level:
            continue
        c = color(lv.level)
        span = (a1 - a0) * lv.level / 100
        lit = _arc_mask(a0, a0 + span, r_out, r_in) if from_start else _arc_mask(a1 - span, a1, r_out, r_in)
        tube = Image.new("RGBA", (_R, _R), (0, 0, 0, 0))
        td = ImageDraw.Draw(tube)
        for r in range(r_in, r_out + 1):  # rounded, tube-like shading across the ring
            t = (r - r_in) / (r_out - r_in)
            shade = _lighten(c, 0.45 * (1 - abs(t - 0.35) / 0.65) ** 2) if t < 0.7 else _darken(c, (t - 0.7) * 0.9)
            td.ellipse((_RC - r, _RC - r, _RC + r, _RC + r), outline=shade, width=2)
        if connected:
            glow = Image.new("RGBA", (_R, _R), (0, 0, 0, 0))
            glow.paste(c[:3] + (255,), (0, 0), lit)
            im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(6)))
        im.paste(tube, (0, 0), lit)

    d = ImageDraw.Draw(im)
    fg = (250, 250, 250, 255) if connected else (170, 175, 185, 255)

    def text(y, s, px):
        f = _ring_font(px)
        l, t, r, b = d.textbbox((0, 0), s, font=f)
        x = _RC - (l + r) / 2
        d.text((x + 2, y - (t + b) / 2 + 3), s, font=f, fill=(0, 0, 0, 180))
        d.text((x, y - (t + b) / 2), s, font=f, fill=fg)

    if len(shown) == 2:
        for i, lv in enumerate(shown):
            y = 96 if i == 0 else 162
            text(y, _num(lv.level), 62 if (lv.level or 0) < 100 else 50)
            if lv.charging and connected:
                _bolt(d, _RC + 60, y, 17)
        d.line((_RC - 38, _RC + 1, _RC + 38, _RC + 1), fill=(222, 186, 84, 255), width=4)
    else:
        lv = shown[0]
        text(_RC, _num(lv.level), 92 if (lv.level or 0) < 100 else 74)
        if lv.charging and connected:
            _bolt(d, _RC, _RC + 62, 16)
    im.alpha_composite(_ring_gloss())
    return im.resize((SIZE, SIZE), Image.LANCZOS)


def render_icon(levels: list[LabeledLevel], style: str = "numbers", low: int = 20,
                connected: bool = True) -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    if not levels:
        d.rounded_rectangle((2, 2, SIZE - 3, SIZE - 3), radius=12, fill=DARK)
        _centered(d, "BT", (6, 6, SIZE - 6, SIZE - 6), GRAY, 40)
        return img

    # A disconnected (e.g. sleeping) device keeps its last values, in gray.
    def color(level):
        return level_color(level, low) if connected else GRAY

    shown = levels[:2]
    if style == "ring":
        return _render_ring(shown, color, connected)
    if style == "bars":
        n = len(shown)
        gap = 6
        # Same battery width whether one or two are shown, so a single
        # device does not get a fat battery stretched across the icon.
        bar_w = (SIZE - gap * 3) // 2
        start = (SIZE - (n * bar_w + (n - 1) * gap)) // 2
        for i, lv in enumerate(shown):
            x0 = start + i * (bar_w + gap)
            x1 = x0 + bar_w
            top, bottom = 10, SIZE - 3
            d.rounded_rectangle((x0 + bar_w // 3, 3, x1 - bar_w // 3, top), radius=2, fill=WHITE)
            d.rounded_rectangle((x0, top, x1, bottom), radius=6, fill=DARK, outline=WHITE, width=3)
            if lv.level is not None:
                inner_h = bottom - top - 8
                h = max(2, round(inner_h * lv.level / 100))
                d.rounded_rectangle((x0 + 4, bottom - 4 - h, x1 - 4, bottom - 4), radius=3,
                                    fill=color(lv.level))
            if lv.charging and connected:
                _bolt(d, (x0 + x1) / 2, (top + bottom) / 2, 11)
        return img

    # numbers: one row per battery on a dark rounded background
    d.rounded_rectangle((0, 0, SIZE - 1, SIZE - 1), radius=12, fill=DARK)
    if len(shown) == 1:
        _centered(d, _num(shown[0].level), (3, 6, SIZE - 3, SIZE - 6), color(shown[0].level), 44)
        if shown[0].charging and connected:
            _bolt(d, SIZE - 10, 12, 8)
        return img
    row_h = SIZE // 2
    for i, lv in enumerate(shown):
        y0 = i * row_h
        label_w = 16
        if lv.charging and connected:  # the L / R label becomes the charging mark
            _bolt(d, 2 + label_w / 2, y0 + row_h / 2, 11)
        else:
            _centered(d, lv.short or "?", (2, y0 + 4, 2 + label_w, y0 + row_h - 4), WHITE, 22)
        _centered(d, _num(lv.level), (label_w + 2, y0 + 2, SIZE - 2, y0 + row_h - 2),
                  color(lv.level), 32)
    return img
