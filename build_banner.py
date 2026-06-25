"""Build banner.svg with embedded Wanderer above the Sea of Fog + animated fog overlay.

Produces a single SVG with:
  - Base layer: cropped + optimized Friedrich painting (base64-embedded JPG)
  - Animated fog: SVG feTurbulence with animated baseFrequency/seed
  - Title overlay: 'Das Stein Adler' in EB Garamond style
  - Circular avatar baked in at the bottom edge (no GitHub-CSS hack needed)
"""

from __future__ import annotations

import base64
import io
import urllib.request
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).parent
PAINTING_URL = (
    "https://upload.wikimedia.org/wikipedia/commons/"
    "thumb/a/af/Caspar_David_Friedrich_-_Wanderer_above_the_Sea_of_Fog.jpeg/"
    "1280px-Caspar_David_Friedrich_-_Wanderer_above_the_Sea_of_Fog.jpeg"
)
AVATAR_URL = "https://avatars.githubusercontent.com/u/171722100?v=4"

# Banner geometry — GitHub READMEs render around 800-900px wide on desktop.
# 1600x420 gives high-DPI sharpness when scaled down.
W, H = 1600, 420
AVATAR_PX = 220  # rendered diameter in the SVG


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "banner-builder/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def crop_painting(raw: bytes) -> bytes:
    """Crop the painting into a banner. The original is portrait; we want a
    horizontal strip showing the wanderer + the sea of fog around him."""
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    src_w, src_h = img.size

    # Target a horizontal slice. Take the full width, crop a band that keeps
    # the wanderer (silhouette in the middle-upper area).
    target_ratio = W / H
    # We want a horizontal band — slice src_h to fit ratio against src_w.
    band_h = int(src_w / target_ratio)
    # Center the band vertically around the wanderer (roughly at 45% of height).
    center_y = int(src_h * 0.45)
    top = max(0, center_y - band_h // 2)
    bottom = min(src_h, top + band_h)
    top = bottom - band_h  # re-anchor if we clipped at bottom

    cropped = img.crop((0, top, src_w, bottom))
    resized = cropped.resize((W, H), Image.LANCZOS)

    # Slight warm tone shift to harmonize with the brown palette.
    out = io.BytesIO()
    resized.save(out, format="JPEG", quality=80, optimize=True, progressive=True)
    return out.getvalue()


def make_circular_avatar(raw: bytes, size: int) -> bytes:
    """Pre-crop avatar to a circular PNG with transparent background."""
    img = Image.open(io.BytesIO(raw)).convert("RGBA")
    img = img.resize((size, size), Image.LANCZOS)

    # Build circular alpha mask.
    mask = Image.new("L", (size, size), 0)
    from PIL import ImageDraw
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)

    out_img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out_img.paste(img, (0, 0), mask=mask)

    # Quantize the RGB channels to a palette while keeping the circular alpha,
    # which cuts PNG size dramatically without visible quality loss at this scale.
    rgb = out_img.convert("RGB").quantize(colors=128, method=Image.Quantize.MEDIANCUT)
    rgb = rgb.convert("RGBA")
    rgb.putalpha(out_img.split()[-1])

    out = io.BytesIO()
    rgb.save(out, format="PNG", optimize=True)
    return out.getvalue()


def b64(data: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def build_svg(painting_b64: str, avatar_b64: str) -> str:
    avatar_cx = W // 2
    avatar_cy = H - AVATAR_PX // 2 - 10  # sits just above bottom edge
    title_y = int(H * 0.42)
    subtitle_y = title_y + 38

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" preserveAspectRatio="xMidYMid slice" role="img" aria-label="Das Stein Adler banner">
  <defs>
    <!-- Animated drifting fog: turbulence with shifting baseFrequency. -->
    <filter id="fog" x="0" y="0" width="100%" height="100%">
      <feTurbulence type="fractalNoise" baseFrequency="0.012 0.022" numOctaves="2" seed="3" result="noise">
        <animate attributeName="baseFrequency" dur="28s" values="0.012 0.022;0.018 0.028;0.012 0.022" repeatCount="indefinite" />
        <animate attributeName="seed" dur="24s" values="3;7;3" repeatCount="indefinite" />
      </feTurbulence>
      <feColorMatrix in="noise" type="matrix"
        values="0 0 0 0 0.92  0 0 0 0 0.88  0 0 0 0 0.82  0 0 0 0.55 0" result="tinted" />
      <feGaussianBlur in="tinted" stdDeviation="6" />
    </filter>

    <!-- Soft top vignette to make the title readable. -->
    <linearGradient id="topShade" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#1a1a1a" stop-opacity="0.55" />
      <stop offset="60%" stop-color="#1a1a1a" stop-opacity="0.10" />
      <stop offset="100%" stop-color="#1a1a1a" stop-opacity="0.00" />
    </linearGradient>

    <!-- Bottom shade to seat the avatar against the painting. -->
    <linearGradient id="botShade" x1="0" y1="1" x2="0" y2="0">
      <stop offset="0%" stop-color="#1a1a1a" stop-opacity="0.85" />
      <stop offset="100%" stop-color="#1a1a1a" stop-opacity="0.00" />
    </linearGradient>

    <!-- Warm gold→brown sweep to match the rest of the README palette. -->
    <linearGradient id="warmWash" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%"   stop-color="#4a3728" stop-opacity="0.18" />
      <stop offset="50%"  stop-color="#8c7355" stop-opacity="0.10" />
      <stop offset="100%" stop-color="#a89070" stop-opacity="0.16" />
    </linearGradient>

    <clipPath id="avatarClip">
      <circle cx="{avatar_cx}" cy="{avatar_cy}" r="{AVATAR_PX // 2}" />
    </clipPath>
  </defs>

  <!-- Base: painting -->
  <image href="{painting_b64}" x="0" y="0" width="{W}" height="{H}" preserveAspectRatio="xMidYMid slice" />

  <!-- Warm color wash to harmonize with palette -->
  <rect width="100%" height="100%" fill="url(#warmWash)" />

  <!-- Animated fog band: covers the lower 70% where the sea of fog already is -->
  <rect x="0" y="{int(H * 0.25)}" width="{W}" height="{int(H * 0.75)}" filter="url(#fog)" />

  <!-- Top vignette under the title -->
  <rect width="100%" height="60%" fill="url(#topShade)" />

  <!-- Title block -->
  <g font-family="'EB Garamond', 'Times New Roman', Garamond, serif" text-anchor="middle">
    <text x="50%" y="{title_y}" font-size="62" fill="#e8e0d4" letter-spacing="2" style="font-style: italic;">
      Das Stein Adler
      <animate attributeName="opacity" values="0;1" dur="1.6s" fill="freeze" />
    </text>
    <text x="50%" y="{subtitle_y}" font-size="18" fill="#b0a090" letter-spacing="4">
      AnteurAbderraouf  ·  CS student &amp; builder
      <animate attributeName="opacity" values="0;1" dur="2.2s" begin="0.4s" fill="freeze" />
    </text>
  </g>

  <!-- Bottom vignette to anchor the avatar -->
  <rect y="55%" width="100%" height="45%" fill="url(#botShade)" />

  <!-- Circular avatar baked in -->
  <g>
    <circle cx="{avatar_cx}" cy="{avatar_cy}" r="{AVATAR_PX // 2 + 4}" fill="none" stroke="#6b5244" stroke-width="3" />
    <image href="{avatar_b64}" x="{avatar_cx - AVATAR_PX // 2}" y="{avatar_cy - AVATAR_PX // 2}" width="{AVATAR_PX}" height="{AVATAR_PX}" clip-path="url(#avatarClip)" />
  </g>
</svg>
"""


def main() -> None:
    print("Fetching painting...")
    painting_raw = fetch(PAINTING_URL)
    print(f"  {len(painting_raw):,} bytes raw")

    print("Cropping + optimizing painting...")
    painting_jpg = crop_painting(painting_raw)
    print(f"  {len(painting_jpg):,} bytes cropped JPG ({W}x{H})")

    print("Fetching + circularizing avatar...")
    avatar_raw = fetch(AVATAR_URL)
    # Avatar renders at AVATAR_PX in the banner; source at 1.4x is plenty
    # crisp once the SVG is scaled by the browser.
    avatar_png = make_circular_avatar(avatar_raw, int(AVATAR_PX * 1.4))
    print(f"  {len(avatar_png):,} bytes circular PNG")

    print("Building SVG...")
    svg = build_svg(
        painting_b64=b64(painting_jpg, "image/jpeg"),
        avatar_b64=b64(avatar_png, "image/png"),
    )

    out_path = ROOT / "banner.svg"
    out_path.write_text(svg, encoding="utf-8")
    print(f"\nWrote {out_path} ({out_path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
