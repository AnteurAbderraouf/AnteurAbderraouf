"""Generate contrib.svg — a 365-day contribution graph rendered as a rocky
mountain range with drifting clouds. Peak days punch through the cloud layer.

Modes:
  --mock        Use a deterministic synthetic dataset (no network).
  --user NAME   Fetch live data via GitHub GraphQL for NAME.
                Requires env GITHUB_TOKEN (a PAT with read:user / public).

Output: ./contrib.svg
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import random
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).parent

# Canvas geometry --------------------------------------------------------------
W, H = 1200, 360
PAD_X = 20
GROUND_Y = H - 28          # rocks rest on this line
SKY_TOP = 0
CLOUD_BAND_Y = int(H * 0.42)  # rocks taller than this break the clouds
DAYS = 365
COL_W = (W - 2 * PAD_X) / DAYS  # ~3.2px per day

# Palette ---------------------------------------------------------------------
BG_TOP = "#1a1a1a"
BG_HORIZON = "#3a2a1d"
ROCK_DARK = "#4a3728"
ROCK_MID = "#6b5244"
ROCK_LIGHT = "#8c7355"
ROCK_PEAK = "#a89070"
CLOUD = "#e8e0d4"
GROUND_LINE = "#2a1f15"

# Rock-stack tuning ------------------------------------------------------------
ROCK_UNIT_H = 3.6  # vertical px per contribution unit
ROCK_UNIT_W = COL_W * 1.6  # rocks slightly wider than column for overlap
JITTER_X = 0.8
JITTER_H = 1.4


def fetch_contributions(user: str, token: str) -> List[Tuple[str, int]]:
    """Return [(YYYY-MM-DD, count), ...] for the last DAYS days."""
    query = """
    query($login:String!, $from:DateTime!, $to:DateTime!) {
      user(login:$login) {
        contributionsCollection(from:$from, to:$to) {
          contributionCalendar {
            weeks {
              contributionDays { date contributionCount }
            }
          }
        }
      }
    }
    """
    today = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    start = today - dt.timedelta(days=DAYS - 1)
    payload = json.dumps({
        "query": query,
        "variables": {
            "login": user,
            "from": start.isoformat().replace("+00:00", "Z"),
            "to": today.isoformat().replace("+00:00", "Z"),
        },
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=payload,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "contrib-svg-builder/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode())

    if "errors" in body:
        raise RuntimeError(f"GraphQL error: {body['errors']}")
    weeks = body["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    days = []
    for w in weeks:
        for d in w["contributionDays"]:
            days.append((d["date"], int(d["contributionCount"])))
    days.sort(key=lambda x: x[0])
    return days[-DAYS:]


def mock_contributions() -> List[Tuple[str, int]]:
    """Realistic-looking distribution: mostly quiet, regular activity bursts,
    and a few exceptional 'shipping day' peaks that should breach the clouds."""
    rng = random.Random(42)
    today = dt.date.today()
    out: List[Tuple[str, int]] = []
    for i in range(DAYS):
        d = today - dt.timedelta(days=DAYS - 1 - i)
        weekday = d.weekday()
        # Weekend baseline lower
        base = 0 if weekday >= 5 else 1
        # Random small daily activity
        roll = rng.random()
        if roll < 0.45:
            count = base + rng.randint(0, 2)
        elif roll < 0.85:
            count = base + rng.randint(2, 8)
        elif roll < 0.97:
            count = base + rng.randint(8, 18)
        else:
            # Rare peak day that should break through clouds
            count = rng.randint(22, 38)
        out.append((d.isoformat(), count))
    return out


def rock_color(layer_idx: int, total_layers: int) -> str:
    """Color shifts lighter as the stack goes up — like sunlight on peaks."""
    if total_layers <= 1:
        return ROCK_MID
    t = layer_idx / max(1, total_layers - 1)
    if t < 0.25:
        return ROCK_DARK
    if t < 0.55:
        return ROCK_MID
    if t < 0.85:
        return ROCK_LIGHT
    return ROCK_PEAK


def make_rock_polygon(cx: float, cy: float, w: float, h: float, seed: int) -> str:
    """Return an SVG polygon points string for an irregular rock chunk."""
    r = random.Random(seed)
    # 6-point rock outline with jittered corners
    half_w, half_h = w / 2, h / 2
    pts = [
        (cx - half_w * (0.85 + r.random() * 0.3), cy + half_h * (0.85 + r.random() * 0.2)),
        (cx - half_w * (0.95 + r.random() * 0.1), cy - half_h * (0.55 + r.random() * 0.2)),
        (cx - half_w * (0.40 + r.random() * 0.2), cy - half_h * (0.95 + r.random() * 0.1)),
        (cx + half_w * (0.30 + r.random() * 0.3), cy - half_h * (0.90 + r.random() * 0.15)),
        (cx + half_w * (0.95 + r.random() * 0.1), cy - half_h * (0.40 + r.random() * 0.2)),
        (cx + half_w * (0.80 + r.random() * 0.2), cy + half_h * (0.85 + r.random() * 0.2)),
    ]
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)


def build_svg(days: List[Tuple[str, int]]) -> str:
    total = sum(c for _, c in days)
    max_day = max((c for _, c in days), default=0)
    rng = random.Random(7)

    # Background + sky gradient + soft horizon glow
    parts: list[str] = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Last {DAYS} days of contributions, rendered as a rocky range with drifting clouds">')
    parts.append(f"""
  <defs>
    <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{BG_TOP}"/>
      <stop offset="80%" stop-color="{BG_HORIZON}"/>
      <stop offset="100%" stop-color="{ROCK_DARK}"/>
    </linearGradient>

    <linearGradient id="cloudGrad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{CLOUD}" stop-opacity="0"/>
      <stop offset="40%" stop-color="{CLOUD}" stop-opacity="0.45"/>
      <stop offset="60%" stop-color="{CLOUD}" stop-opacity="0.45"/>
      <stop offset="100%" stop-color="{CLOUD}" stop-opacity="0"/>
    </linearGradient>

    <filter id="cloudBlur" x="-10%" y="-10%" width="120%" height="120%">
      <feGaussianBlur stdDeviation="8"/>
    </filter>

    <filter id="rockShadow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="0.6"/>
    </filter>
  </defs>

  <rect width="100%" height="100%" fill="url(#sky)"/>
""")

    # Far-distance mountain silhouette (decorative, smoothed contribution data)
    silhouette_pts = ["0," + str(GROUND_Y)]
    smoothed = []
    for i in range(DAYS):
        # 14-day window smoothing
        window = days[max(0, i - 7): min(DAYS, i + 7)]
        avg = sum(c for _, c in window) / max(1, len(window))
        smoothed.append(avg)
    max_smoothed = max(smoothed) if smoothed else 1
    for i, v in enumerate(smoothed):
        x = PAD_X + i * COL_W
        y = GROUND_Y - (v / max(1, max_smoothed)) * 100 - 30
        silhouette_pts.append(f"{x:.1f},{y:.1f}")
    silhouette_pts.append(f"{W},{GROUND_Y}")
    parts.append(f'  <polygon points="{" ".join(silhouette_pts)}" fill="{ROCK_DARK}" opacity="0.65"/>\n')

    # Cloud band — drifting horizontally, behind the peaks of tallest rocks.
    # Two overlapping bands at slightly different speeds gives parallax depth.
    cloud_h = 70
    parts.append('  <g filter="url(#cloudBlur)">\n')
    # Band 1 — slower, larger blobs
    band1 = []
    rng_c = random.Random(11)
    for x in range(-200, W + 400, 90):
        cx = x + rng_c.randint(-15, 15)
        cy = CLOUD_BAND_Y + rng_c.randint(-12, 12)
        rx = rng_c.randint(55, 110)
        ry = rng_c.randint(14, 26)
        band1.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="{CLOUD}" opacity="0.55"/>')
    parts.append('    <g>')
    parts.append("".join(band1))
    parts.append(f'      <animateTransform attributeName="transform" type="translate" from="0 0" to="-180 0" dur="48s" repeatCount="indefinite"/>')
    parts.append('    </g>\n')
    # Band 2 — faster, smaller wisps, slightly above the first
    band2 = []
    rng_c2 = random.Random(29)
    for x in range(-200, W + 400, 70):
        cx = x + rng_c2.randint(-10, 10)
        cy = CLOUD_BAND_Y - 22 + rng_c2.randint(-8, 8)
        rx = rng_c2.randint(35, 75)
        ry = rng_c2.randint(8, 16)
        band2.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="{CLOUD}" opacity="0.40"/>')
    parts.append('    <g>')
    parts.append("".join(band2))
    parts.append(f'      <animateTransform attributeName="transform" type="translate" from="0 0" to="-220 0" dur="32s" repeatCount="indefinite"/>')
    parts.append('    </g>\n')
    parts.append('  </g>\n')

    # Rocks layer — each day a vertical stack of rock polygons
    parts.append('  <g filter="url(#rockShadow)">\n')
    for i, (date, count) in enumerate(days):
        if count <= 0:
            # Draw a tiny pebble so the day still "exists"
            cx = PAD_X + i * COL_W + COL_W / 2
            cy = GROUND_Y - 1.5
            parts.append(
                f'    <ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{ROCK_UNIT_W*0.45:.1f}" ry="1.2" fill="{ROCK_DARK}" opacity="0.7"/>\n'
            )
            continue

        stack_h = count * ROCK_UNIT_H
        col_cx = PAD_X + i * COL_W + COL_W / 2
        # Layer count — each rock chunk is ~ROCK_UNIT_H * 1.4 tall to overlap nicely
        chunk_h = ROCK_UNIT_H * 1.4
        n_chunks = max(1, math.ceil(stack_h / ROCK_UNIT_H))
        cur_y = GROUND_Y
        for layer in range(n_chunks):
            seed = i * 97 + layer * 13
            r = random.Random(seed)
            jitter = (r.random() - 0.5) * 2 * JITTER_X
            chunk_actual_h = chunk_h + (r.random() - 0.5) * JITTER_H
            cx = col_cx + jitter
            cy = cur_y - chunk_actual_h / 2
            color = rock_color(layer, n_chunks)
            pts = make_rock_polygon(cx, cy, ROCK_UNIT_W, chunk_actual_h, seed)
            parts.append(f'    <polygon points="{pts}" fill="{color}"/>\n')
            cur_y -= ROCK_UNIT_H * 0.95  # slight overlap

        # Top highlight for peaks tall enough to break the clouds
        peak_y = GROUND_Y - stack_h
        if peak_y < CLOUD_BAND_Y - 10:
            parts.append(
                f'    <circle cx="{col_cx:.1f}" cy="{peak_y:.1f}" r="1.6" fill="{ROCK_PEAK}" opacity="0.95"/>\n'
            )
    parts.append('  </g>\n')

    # Subtle ground line
    parts.append(
        f'  <line x1="0" y1="{GROUND_Y}" x2="{W}" y2="{GROUND_Y}" stroke="{GROUND_LINE}" stroke-width="1" opacity="0.6"/>\n'
    )

    # Caption — total contributions in window + date range
    start_date = days[0][0] if days else ""
    end_date = days[-1][0] if days else ""
    parts.append(f"""
  <g font-family="'EB Garamond','Times New Roman',Garamond,serif" fill="#b0a090" opacity="0.85">
    <text x="{PAD_X}" y="{H - 8}" font-size="12" font-style="italic">⟡ {total:,} contributions · {start_date} → {end_date}</text>
    <text x="{W - PAD_X}" y="{H - 8}" font-size="11" text-anchor="end">Peak day: {max_day}</text>
  </g>
""")
    parts.append("</svg>\n")
    return "".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true", help="Use synthetic data (no network)")
    parser.add_argument("--user", default="AnteurAbderraouf", help="GitHub username")
    parser.add_argument("--out", default=str(ROOT / "contrib.svg"))
    args = parser.parse_args()

    if args.mock:
        print("Using mock contribution data...")
        days = mock_contributions()
    else:
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if not token:
            print("ERROR: GITHUB_TOKEN env var required (or pass --mock to preview).", file=sys.stderr)
            sys.exit(2)
        print(f"Fetching contributions for {args.user}...")
        days = fetch_contributions(args.user, token)

    print(f"  {len(days)} days, total {sum(c for _, c in days)} contributions")
    svg = build_svg(days)
    out_path = Path(args.out)
    out_path.write_text(svg, encoding="utf-8")
    print(f"Wrote {out_path} ({out_path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
