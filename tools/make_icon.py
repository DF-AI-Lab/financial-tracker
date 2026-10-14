"""Draws the app icon (the Lens: a £ in a magnifying glass) into static/.

Run: python tools/make_icon.py   (needs Pillow). Makes icon-192.png, icon-512.png and app.ico.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

TEAL, MINT, WHITE = "#0f6e5c", "#3fd0a4", "#ffffff"
FONTS = ["/usr/share/fonts/opentype/inter/InterDisplay-Bold.otf", "arialbd.ttf", "DejaVuSans-Bold.ttf"]


def draw(size=1024):
    k = size / 100  # drawn on a 100 x 100 grid, same as the mock-up
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=24 * k, fill=TEAL)
    d.ellipse([22 * k, 22 * k, 66 * k, 66 * k], outline=WHITE, width=round(7 * k))
    d.line([60 * k, 60 * k, 76 * k, 76 * k], fill=WHITE, width=round(9 * k))
    r = 4.5 * k  # round end of the handle
    d.ellipse([76 * k - r, 76 * k - r, 76 * k + r, 76 * k + r], fill=WHITE)
    for f in FONTS:
        try:
            font = ImageFont.truetype(f, round(28 * k))
            break
        except OSError:
            continue
    d.text((44 * k, 44 * k), "£", font=font, fill=MINT, anchor="mm")
    return im


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "static"
    big = draw()
    for s in (192, 512):
        big.resize((s, s), Image.LANCZOS).save(out / f"icon-{s}.png")
    big.save(out / "app.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("Icons written to", out)
