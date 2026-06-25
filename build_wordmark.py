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
    title_size = 84 * SCALE   # "Das Stein Adler"
    sub_size = 18 * SCALE     # "Abderraouf Anteur · Software engineer · Algiers"
    pad_x = 40 * SCALE
    pad_y = 24 * SCALE
    gap = 14 * SCALE          # space between title and subtitle

    title_font = ImageFont.truetype(str(italic_path), title_size)
    sub_font = ImageFont.truetype(str(regular_path), sub_size)

    title = "Das Stein Adler"
    sub = "Abderraouf Anteur  ·  Software engineer  ·  Algiers"

    # Use font metrics (ascent / descent) instead of textbbox — italic fonts
    # have swash overhang the bbox underestimates, which caused the subtitle
    # to overlap the title in the first render.
    t_ascent, t_descent = title_font.getmetrics()
    s_ascent, s_descent = sub_font.getmetrics()
    t_line = t_ascent + t_descent
    s_line = s_ascent + s_descent

    # Measure widths only.
    tmp = Image.new("RGBA", (10, 10))
    tdraw = ImageDraw.Draw(tmp)
    t_w = int(tdraw.textlength(title, font=title_font))
    s_w = int(tdraw.textlength(sub, font=sub_font))

    # Italic overhang on the right: pad horizontally so right-edge swashes don't clip.
    italic_pad = title_size // 4

    W = max(t_w + italic_pad, s_w) + pad_x * 2
    H = t_line + gap + s_line + pad_y * 2

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    title_color = (232, 224, 212, 255)  # #e8e0d4
    sub_color = (176, 160, 144, 255)    # #b0a090

    # Pillow's draw.text places y at the top of the glyph box (ascent line).
    # Stack title above subtitle with explicit line heights so descenders /
    # swashes don't intrude into the row below.
    tx = (W - t_w) // 2
    ty = pad_y
    sx = (W - s_w) // 2
    sy = ty + t_line + gap

    draw.text((tx, ty), title, font=title_font, fill=title_color)
    draw.text((sx, sy), sub, font=sub_font, fill=sub_color)

    out = ROOT / "wordmark.png"
    img.save(out, format="PNG", optimize=True)
    print(f"Wrote {out} ({out.stat().st_size:,} bytes, {W // SCALE}x{H // SCALE} display)")


if __name__ == "__main__":
    main()
