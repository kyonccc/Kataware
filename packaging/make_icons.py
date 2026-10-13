"""Generate the application icons (app.ico / app.icns / app.png) from code.

Design: 二つ巴 (futatsu-domoe, two interlocking commas — a pair of "kataware")
on indigo, with a 七宝 (shippo) pattern woven into each tomoe and a gold ring
broken in two places (破れ, the beauty of imperfection). Green / orange echo
the two battery halves shown in the tray.
"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PIL import Image, ImageChops, ImageDraw  # noqa: E402

from kataware.icon import GREEN, ORANGE  # noqa: E402

S = 1024
AI = (28, 39, 72, 255)  # 藍色 indigo
GOLD = (214, 178, 74, 255)


def _mask() -> Image.Image:
    return Image.new("L", (S, S), 0)


def tomoe_mask(c: float, r: float, head: float = 0.47, sweep: float = 165, taper: float = 1.35) -> Image.Image:
    """One tomoe: a round head touching the rim at the top and a tail running
    anticlockwise along the rim, tapering to a point."""
    m = _mask()
    d = ImageDraw.Draw(m)
    hr = r * head
    d.ellipse((c - hr, c - r, c + hr, c - r + 2 * hr), fill=255)
    outer, inner = [], []
    steps = 240
    for i in range(steps + 1):
        t = i / steps
        a = math.radians(270 - sweep * t)
        w = 2 * hr * (1 - t) ** taper
        outer.append((c + r * math.cos(a), c + r * math.sin(a)))
        inner.append((c + (r - w) * math.cos(a), c + (r - w) * math.sin(a)))
    d.polygon(outer + inner[::-1], fill=255)
    return m


def shippo(radius: int, width: int, alpha: int) -> Image.Image:
    """七宝 pattern: a lattice of overlapping circles."""
    p = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(p)
    for gy in range(-2, S // radius + 3):
        for gx in range(-2, S // radius + 3):
            x, y = gx * radius + 40, gy * radius + 40
            d.ellipse((x - radius, y - radius, x + radius, y + radius), outline=(0, 0, 0, alpha), width=width)
    return p


def render() -> Image.Image:
    c = S // 2
    frame = _mask()
    ImageDraw.Draw(frame).rounded_rectangle((32, 32, S - 32, S - 32), radius=220, fill=255)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.paste(AI, (0, 0), frame)

    left = tomoe_mask(c, 300)
    right = left.rotate(180, center=(c, c))
    img.paste(GREEN, (0, 0), left)
    img.paste(ORANGE, (0, 0), right)

    pattern = shippo(95, 14, 60)
    woven = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    woven.paste(pattern, (0, 0), ImageChops.lighter(left, right))
    img.alpha_composite(woven)

    d = ImageDraw.Draw(img)
    box = (c - 360, c - 360, c + 360, c + 360)
    d.arc(box, -20, 150, fill=GOLD, width=30)
    d.arc(box, 165, 325, fill=GOLD, width=30)
    return img


if __name__ == "__main__":
    out = Path(__file__).resolve().parent / "build-icons"
    out.mkdir(exist_ok=True)
    img = render()
    img.save(out / "app.png")
    img.save(out / "app.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    img.save(out / "app.icns")
    print("icons written to", out)
