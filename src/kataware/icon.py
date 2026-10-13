"""Tray / menu bar icon rendering (pure Pillow, no system fonts needed)."""

from __future__ import annotations

from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

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


def render_icon(levels: list[LabeledLevel], style: str = "numbers", low: int = 20,
                connected: bool = True) -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    if not levels or not connected:
        d.rounded_rectangle((2, 2, SIZE - 3, SIZE - 3), radius=12, fill=DARK)
        _centered(d, "BT" if not levels else "×", (6, 6, SIZE - 6, SIZE - 6), GRAY, 40)
        return img

    shown = levels[:2]
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
                                    fill=level_color(lv.level, low))
        return img

    # numbers: one row per battery on a dark rounded background
    d.rounded_rectangle((0, 0, SIZE - 1, SIZE - 1), radius=12, fill=DARK)
    if len(shown) == 1:
        _centered(d, _num(shown[0].level), (3, 6, SIZE - 3, SIZE - 6), level_color(shown[0].level, low), 44)
        return img
    row_h = SIZE // 2
    for i, lv in enumerate(shown):
        y0 = i * row_h
        label_w = 16
        _centered(d, lv.short or "?", (2, y0 + 4, 2 + label_w, y0 + row_h - 4), WHITE, 22)
        _centered(d, _num(lv.level), (label_w + 2, y0 + 2, SIZE - 2, y0 + row_h - 2),
                  level_color(lv.level, low), 32)
    return img
