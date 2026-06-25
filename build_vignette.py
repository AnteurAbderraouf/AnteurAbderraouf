"""Render the wanderer-figure vignette as a circular PNG.

Crops the central figure out of Friedrich's 'Wanderer above the Sea of Fog'
(1818, public domain), masks it to a circle, adds a thin warm border.
"""

from __future__ import annotations

import io
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).parent
ASSETS = ROOT / "assets"
ASSETS.mkdir(exist_ok=True)

PAINTING_URL = (
    "https://upload.wikimedia.org/wikipedia/commons/"
    "thumb/a/af/Caspar_David_Friedrich_-_Wanderer_above_the_Sea_of_Fog.jpeg/"
    "1280px-Caspar_David_Friedrich_-_Wanderer_above_the_Sea_of_Fog.jpeg"
)

OUT_PX = 240   # 2x of 120px display for retina sharpness
BORDER_PX = 4
BORDER_COLOR = (107, 82, 68)  # #6b5244


def fetch(url: str, cache: Path) -> bytes:
    if cache.exists() and cache.stat().st_size > 50_000:
        return cache.read_bytes()
    print(f"  downloading {cache.name} ...")
    req = urllib.request.Request(url, headers={"User-Agent": "vignette-builder/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    cache.write_bytes(data)
    return data


def main() -> None:
    raw = fetch(PAINTING_URL, ASSETS / "friedrich.jpg")
    src = Image.open(io.BytesIO(raw)).convert("RGB")
    sw, sh = src.size

    # The wanderer figure sits near horizontal center, vertically centered
    # roughly between 28% and 70% of the painting's height. We crop a tight
    # square around him so the silhouette dominates the vignette.
    fx = sw // 2
    fy = int(sh * 0.48)
    half = int(sh * 0.22)  # half the crop side length

    box = (fx - half, fy - half, fx + half, fy + half)
    figure = src.crop(box).resize((OUT_PX, OUT_PX), Image.LANCZOS)

    # Circle mask.
    mask = Image.new("L", (OUT_PX, OUT_PX), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, OUT_PX, OUT_PX), fill=255)

    # Composite figure into a transparent canvas.
    out_img = Image.new("RGBA", (OUT_PX, OUT_PX), (0, 0, 0, 0))
    out_img.paste(figure, (0, 0), mask=mask)

    # Thin warm border around the circle.
    rim = Image.new("RGBA", (OUT_PX, OUT_PX), (0, 0, 0, 0))
    ImageDraw.Draw(rim).ellipse(
        (BORDER_PX // 2, BORDER_PX // 2, OUT_PX - BORDER_PX // 2, OUT_PX - BORDER_PX // 2),
        outline=BORDER_COLOR + (255,),
        width=BORDER_PX,
    )
    out_img = Image.alpha_composite(out_img, rim)

    # Quantize for size — circular avatars don't need the full RGB range.
    rgb = out_img.convert("RGB").quantize(colors=128, method=Image.Quantize.MEDIANCUT)
    rgb = rgb.convert("RGBA")
    rgb.putalpha(out_img.split()[-1])

    out_path = ROOT / "vignette.png"
    rgb.save(out_path, format="PNG", optimize=True)
    print(f"Wrote {out_path} ({out_path.stat().st_size:,} bytes, {OUT_PX // 2}x{OUT_PX // 2} display)")


if __name__ == "__main__":
    main()
