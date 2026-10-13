"""Generate the application icons (app.ico / app.icns / app.png) from code."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PIL import Image, ImageDraw  # noqa: E402

from kataware.icon import DARK, GREEN, ORANGE, WHITE  # noqa: E402

out = Path(__file__).resolve().parent / "build-icons"
out.mkdir(exist_ok=True)

S = 1024
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((40, 40, S - 40, S - 40), radius=220, fill=DARK)
for i, (level, color) in enumerate(((0.8, GREEN), (0.45, ORANGE))):
    x0 = 230 + i * 330
    x1 = x0 + 230
    d.rounded_rectangle((x0 + 70, 170, x1 - 70, 230), radius=20, fill=WHITE)
    d.rounded_rectangle((x0, 220, x1, 860), radius=50, outline=WHITE, width=36)
    inner = 860 - 220 - 100
    h = int(inner * level)
    d.rounded_rectangle((x0 + 50, 810 - h, x1 - 50, 810), radius=24, fill=color)

img.save(out / "app.png")
img.save(out / "app.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
img.save(out / "app.icns")
print("icons written to", out)
