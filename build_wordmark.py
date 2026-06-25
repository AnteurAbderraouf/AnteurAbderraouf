"""Render the 'Das Stein Adler' wordmark as a PNG.

Why a PNG and not markdown text: GitHub markdown renders system fonts,
not EB Garamond. To get a stable, identical wordmark across every visitor
regardless of their installed fonts, we bake the type into an image.

Fetches EB Garamond (italic) from Google Fonts mirror on first run; caches
locally in ./assets/.
"""

from __future__ import annotations

import io
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent
ASSETS = ROOT / "assets"
ASSETS.mkdir(exist_ok=True)

# EB Garamond Italic — SIL OFL 1.1 license. Google Fonts source-of-truth.
GARAMOND_ITALIC_URL = (
    "https://github.com/google/fonts/raw/main/ofl/ebgaramond/EBGaramond-Italic%5Bwght%5D.ttf"
)
GARAMOND_REGULAR_URL = (
    "https://github.com/google/fonts/raw/main/ofl/ebgaramond/EBGaramond%5Bwght%5D.ttf"
)


def fetch_font(url: str, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 50_000:
        return dest
    print(f"  downloading {url.rsplit('/', 1)[-1]} ...")
    req = urllib.request.Request(url, headers={"User-Agent": "wordmark-builder/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        dest.write_bytes(resp.read())
    return dest


def main() -> None:
    italic_path = fetch_font(GARAMOND_ITALIC_URL, ASSETS / "EBGaramond-Italic.ttf")
    regular_path = fetch_font(GARAMOND_REGULAR_URL, ASSETS / "EBGaramond-Regular.ttf")

    # 2x render so the wordmark stays crisp when GitHub scales it down.
    SCALE = 2
    title_size = 70 * SCALE   # smaller than italic version — small caps reads bigger
    sub_size = 16 * SCALE
    pad_x = 40 * SCALE
    pad_y = 28 * SCALE
    gap = 22 * SCALE          # extra breathing room under the monumental caps
    title_tracking = 16 * SCALE  # wide letter-spacing for the monument feel
    sub_tracking = 4 * SCALE

    # Regular (upright) weight for both — no italic. Small-caps appearance comes
    # from rendering in uppercase with wide tracking; reads architectural and
    # masculine instead of the flowing italic that read "girlish".
    title_font = ImageFont.truetype(str(regular_path), title_size)
    sub_font = ImageFont.truetype(str(regular_path), sub_size)

    title = "DAS STEIN ADLER"
    sub = "ABDERRAOUF ANTEUR  ·  SOFTWARE ENGINEER  ·  ALGIERS"

    t_ascent, t_descent = title_font.getmetrics()
    s_ascent, s_descent = sub_font.getmetrics()
    t_line = t_ascent + t_descent
    s_line = s_ascent + s_descent

    # Measure widths with manual tracking (Pillow doesn't support letter-spacing
    # directly — we draw each glyph individually with explicit spacing).
    def tracked_width(text: str, font: ImageFont.FreeTypeFont, tracking: int) -> int:
        tmp = Image.new("RGBA", (10, 10))
        d = ImageDraw.Draw(tmp)
        total = 0
        for i, ch in enumerate(text):
            total += int(d.textlength(ch, font=font))
            if i < len(text) - 1:
                total += tracking
        return total

    def draw_tracked(d: ImageDraw.ImageDraw, xy: tuple[int, int], text: str,
                     font: ImageFont.FreeTypeFont, tracking: int, fill) -> None:
        x, y = xy
        for ch in text:
            d.text((x, y), ch, font=font, fill=fill)
            x += int(d.textlength(ch, font=font)) + tracking

    t_w = tracked_width(title, title_font, title_tracking)
    s_w = tracked_width(sub, sub_font, sub_tracking)

    W = max(t_w, s_w) + pad_x * 2
    H = t_line + gap + s_line + pad_y * 2

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    title_color = (232, 224, 212, 255)  # #e8e0d4
    sub_color = (176, 160, 144, 255)    # #b0a090

    tx = (W - t_w) // 2
    ty = pad_y
    sx = (W - s_w) // 2
    sy = ty + t_line + gap

    draw_tracked(draw, (tx, ty), title, title_font, title_tracking, title_color)
    draw_tracked(draw, (sx, sy), sub, sub_font, sub_tracking, sub_color)

    out = ROOT / "wordmark.png"
    img.save(out, format="PNG", optimize=True)
    print(f"Wrote {out} ({out.stat().st_size:,} bytes, {W // SCALE}x{H // SCALE} display)")


if __name__ == "__main__":
    main()
