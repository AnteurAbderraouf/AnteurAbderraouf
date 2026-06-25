"""Generate contrib.svg — a 53x7 contribution grid rendered as an isometric
stone field viewed from above-and-to-the-side. Each day is one irregular
stone whose height equals that day's contribution count. Drifting clouds sit
at a fixed altitude; tall stones poke up into / above them.

Modes:
  --mock        Use a deterministic synthetic dataset (no network).
  --user NAME   Fetch live data via GitHub GraphQL for NAME.
                Requires env GITHUB_TOKEN (a PAT with read:user / public).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import random
import sys
import urllib.request
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).parent

# Grid -------------------------------------------------------------------------
WEEKS = 53
DAYS = 7
TOTAL_CELLS = WEEKS * DAYS

# Isometric projection — classic 2:1 dimetric ('SimCity' angle) -----------------
# A cell is 1x1 in world units. In screen pixels the cell's top face is a
# parallelogram with width 2*HW and height 2*HH where HW:HH = 2:1.
HW = 13         # cell half-width  (screen px)
HH = 7          # cell half-height (screen px, foreshortened)
Z_UNIT = 3.6    # screen px per contribution count (stone height per unit)

# Canvas geometry computed from the grid bounds.
PAD_X = 40
PAD_TOP = 80         # space above max stone for clouds + sky
PAD_BOTTOM = 36      # space for caption
MAX_REASONABLE_H = 40  # most peak days under this many commits

# Derived: leftmost world point is (0, DAYS) projected; rightmost is (WEEKS, 0)
# In our projection: sx = (x - y) * HW.  sy = (x + y) * HH - z
WORLD_MIN_SX = (0 - (DAYS - 1)) * HW       # = -6 * HW
WORLD_MAX_SX = ((WEEKS - 1) - 0) * HW       # = 52 * HW
WORLD_MIN_SY = (0 + 0) * HH                 # 0
WORLD_MAX_SY = ((WEEKS - 1) + (DAYS - 1)) * HH  # 58 * HH

W = (WORLD_MAX_SX - WORLD_MIN_SX) + HW * 2 + PAD_X * 2
H = WORLD_MAX_SY + PAD_TOP + PAD_BOTTOM + int(MAX_REASONABLE_H * Z_UNIT)

# Translate world coords so the grid is positioned within the SVG with padding.
OFFSET_X = PAD_X - WORLD_MIN_SX
OFFSET_Y = PAD_TOP + int(MAX_REASONABLE_H * Z_UNIT)

# Palette ---------------------------------------------------------------------
BG_TOP = "#1a1a1a"
BG_HORIZON = "#2e2218"
ROCK_TOP_LOW = "#6b5244"
ROCK_TOP_HIGH = "#a89070"
ROCK_TOP_PEAK = "#e8e0d4"
ROCK_RIGHT = "#5a4538"
ROCK_RIGHT_PEAK = "#8c7355"
ROCK_LEFT = "#3d2d22"
ROCK_LEFT_PEAK = "#6b5244"
CLOUD = "#e8e0d4"
GROUND_TILE = "#2a1f15"

CLOUD_BAND_Y = PAD_TOP + 60   # screen y where cloud band sits
CLOUD_THRESHOLD_HEIGHT = 18    # stones taller than this contribution count poke clouds


# -----------------------------------------------------------------------------
# Data
# -----------------------------------------------------------------------------

def fetch_contributions(user: str, token: str) -> List[Tuple[str, int]]:
    """Last 53*7 = 371 days of (date, count) tuples, oldest first.
    Trims to the last full TOTAL_CELLS days."""
    query = """
    query($login:String!, $from:DateTime!, $to:DateTime!) {
      user(login:$login) {
        contributionsCollection(from:$from, to:$to) {
          contributionCalendar {
            weeks { contributionDays { date contributionCount } }
          }
        }
      }
    }
    """
    today = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    start = today - dt.timedelta(days=TOTAL_CELLS - 1)
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
            "User-Agent": "contrib-svg-builder/2.0",
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
    return days[-TOTAL_CELLS:]


def mock_contributions() -> List[Tuple[str, int]]:
    rng = random.Random(42)
    today = dt.date.today()
    out: List[Tuple[str, int]] = []
    for i in range(TOTAL_CELLS):
        d = today - dt.timedelta(days=TOTAL_CELLS - 1 - i)
        weekday = d.weekday()
        base = 0 if weekday >= 5 else 1
        roll = rng.random()
        if roll < 0.40:
            count = base + rng.randint(0, 2)
        elif roll < 0.82:
            count = base + rng.randint(2, 8)
        elif roll < 0.96:
            count = base + rng.randint(8, 18)
        else:
            count = rng.randint(22, 36)
        out.append((d.isoformat(), count))
    return out


# -----------------------------------------------------------------------------
# Geometry helpers
# -----------------------------------------------------------------------------

def project(wx: float, wy: float, wz: float) -> Tuple[float, float]:
    """World (wx, wy, wz) -> screen (sx, sy). World z grows upward."""
    sx = (wx - wy) * HW + OFFSET_X
    sy = (wx + wy) * HH - wz + OFFSET_Y
    return sx, sy


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def lerp_color(c1: str, c2: str, t: float) -> str:
    r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
    r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
    return f"#{int(lerp(r1, r2, t)):02x}{int(lerp(g1, g2, t)):02x}{int(lerp(b1, b2, t)):02x}"


def stone_top_polygon(wx: float, wy: float, wz: float, seed: int) -> str:
    """An irregular 8-vertex polygon for the top face of a stone — not a clean
    rectangle. Walks the perimeter of the 1x1 cell at height wz, inserting a
    jittered midpoint on each edge so the outline reads as 'boulder' not 'box'."""
    r = random.Random(seed)
    # 8 perimeter points around the unit square (corners + edge-midpoints)
    pts_world = []
    edges = [
        ((wx,     wy),     (wx + 1, wy)),     # back edge
        ((wx + 1, wy),     (wx + 1, wy + 1)), # right edge
        ((wx + 1, wy + 1), (wx,     wy + 1)), # front edge
        ((wx,     wy + 1), (wx,     wy)),     # left edge
    ]
    for (ax, ay), (bx, by) in edges:
        # Corner (slightly jittered inward)
        jx = (r.random() - 0.5) * 0.10
        jy = (r.random() - 0.5) * 0.10
        pts_world.append((ax + jx, ay + jy))
        # Midpoint of edge (jittered along edge normal)
        mx = (ax + bx) / 2 + (r.random() - 0.5) * 0.18
        my = (ay + by) / 2 + (r.random() - 0.5) * 0.18
        pts_world.append((mx, my))

    projected = [project(x, y, wz) for x, y in pts_world]
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in projected)


def stone_side_polygon(top_a_world, top_b_world, top_z: float) -> str:
    """A side face: from two adjacent corners of the top, down to the ground."""
    (ax, ay), (bx, by) = top_a_world, top_b_world
    pts = [
        project(ax, ay, top_z),
        project(bx, by, top_z),
        project(bx, by, 0),
        project(ax, ay, 0),
    ]
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)


def color_for_height(base_low: str, base_high: str, count: int) -> str:
    """Stones color-gradient with height. Above the cloud threshold they shift
    further toward the highlight tone — 'sunlight above the fog'."""
    t = min(1.0, count / MAX_REASONABLE_H)
    return lerp_color(base_low, base_high, t)


# -----------------------------------------------------------------------------
# SVG assembly
# -----------------------------------------------------------------------------

def build_svg(days: List[Tuple[str, int]]) -> str:
    total = sum(c for _, c in days)
    max_day = max((c for _, c in days), default=0)

    parts: list[str] = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Last year of contributions as an isometric stone field viewed from above; tall stones poke through drifting clouds.">')
    parts.append(f'''
  <defs>
    <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{BG_TOP}"/>
      <stop offset="65%" stop-color="{BG_HORIZON}"/>
      <stop offset="100%" stop-color="{ROCK_LEFT}"/>
    </linearGradient>
    <filter id="cloudBlur" x="-10%" y="-10%" width="120%" height="120%">
      <feGaussianBlur stdDeviation="7"/>
    </filter>
    <filter id="stoneShadow" x="-5%" y="-5%" width="110%" height="110%">
      <feGaussianBlur stdDeviation="0.4"/>
    </filter>
  </defs>
  <rect width="100%" height="100%" fill="url(#sky)"/>
''')

    # --- Ground plane: thin parallelogram suggesting the field the stones rest on
    g_pts = [
        project(-0.6, -0.6, 0),
        project(WEEKS + 0.6, -0.6, 0),
        project(WEEKS + 0.6, DAYS + 0.6, 0),
        project(-0.6, DAYS + 0.6, 0),
    ]
    g_str = " ".join(f"{x:.1f},{y:.1f}" for x, y in g_pts)
    parts.append(f'  <polygon points="{g_str}" fill="{GROUND_TILE}" opacity="0.65"/>\n')

    # --- Stones drawn back-to-front (smallest wx+wy first; ties broken by wx).
    # Inside same sort-key, low-height stones drawn before tall ones so a tall
    # stone in row N never gets clipped by a short stone in row N+1.
    cells = []
    for i, (date, count) in enumerate(days):
        gx = i // DAYS                # week index (column)
        gy = i % DAYS                 # day-of-week index (row)
        cells.append((gx, gy, count, date, i))

    # Sort: back rows first (lower gx+gy), then within row by gx
    cells.sort(key=lambda c: (c[0] + c[1], c[0]))

    # Tall stones drawn LAST so they overlap clouds in the screen-stacking order.
    # We separate into two passes: below-cloud-threshold and above-threshold.
    short = [c for c in cells if c[2] < CLOUD_THRESHOLD_HEIGHT]
    tall = [c for c in cells if c[2] >= CLOUD_THRESHOLD_HEIGHT]

    parts.append('  <g filter="url(#stoneShadow)">\n')
    for gx, gy, count, _, idx in short:
        parts.append(render_stone(gx, gy, count, idx))
    parts.append('  </g>\n')

    # --- Cloud band (between short and tall stones in the stacking order)
    parts.append('  <g filter="url(#cloudBlur)">\n')
    rng_c = random.Random(11)
    band1 = []
    for cx in range(-180, W + 360, 95):
        x = cx + rng_c.randint(-12, 12)
        y = CLOUD_BAND_Y + rng_c.randint(-10, 10)
        rx = rng_c.randint(60, 120)
        ry = rng_c.randint(12, 22)
        band1.append(f'<ellipse cx="{x}" cy="{y}" rx="{rx}" ry="{ry}" fill="{CLOUD}" opacity="0.50"/>')
    parts.append('    <g>')
    parts.append("".join(band1))
    parts.append('      <animateTransform attributeName="transform" type="translate" from="0 0" to="-200 0" dur="52s" repeatCount="indefinite"/>')
    parts.append('    </g>\n')

    rng_c2 = random.Random(29)
    band2 = []
    for cx in range(-180, W + 360, 75):
        x = cx + rng_c2.randint(-10, 10)
        y = CLOUD_BAND_Y - 26 + rng_c2.randint(-8, 8)
        rx = rng_c2.randint(36, 78)
        ry = rng_c2.randint(8, 14)
        band2.append(f'<ellipse cx="{x}" cy="{y}" rx="{rx}" ry="{ry}" fill="{CLOUD}" opacity="0.38"/>')
    parts.append('    <g>')
    parts.append("".join(band2))
    parts.append('      <animateTransform attributeName="transform" type="translate" from="0 0" to="-240 0" dur="36s" repeatCount="indefinite"/>')
    parts.append('    </g>\n')
    parts.append('  </g>\n')

    # --- Tall peaks above the clouds
    parts.append('  <g filter="url(#stoneShadow)">\n')
    for gx, gy, count, _, idx in tall:
        parts.append(render_stone(gx, gy, count, idx))
    parts.append('  </g>\n')

    # --- Caption
    start_date = days[0][0] if days else ""
    end_date = days[-1][0] if days else ""
    parts.append(f'''
  <g font-family="'EB Garamond','Times New Roman',Garamond,serif" fill="#b0a090" opacity="0.85">
    <text x="{PAD_X}" y="{H - 14}" font-size="13">⟡ {total:,} contributions  ·  {start_date} → {end_date}</text>
    <text x="{W - PAD_X}" y="{H - 14}" font-size="12" text-anchor="end">Peak day: {max_day}</text>
  </g>
''')
    parts.append("</svg>\n")
    return "".join(parts)


def render_stone(gx: int, gy: int, count: int, seed: int) -> str:
    """SVG fragment for one stone — left face, right face, top face — at grid
    cell (gx, gy) with height = count * Z_UNIT."""
    if count <= 0:
        # Tiny flat pebble — single quad on the ground plane, low contrast.
        top_pts = stone_top_polygon(gx, gy, 0, seed)
        return f'    <polygon points="{top_pts}" fill="{ROCK_TOP_LOW}" opacity="0.55"/>\n'

    h = count * Z_UNIT
    top_z = h

    # World corners (axis-aligned to grid).
    back_left  = (gx,     gy)
    back_right = (gx + 1, gy)
    front_right = (gx + 1, gy + 1)
    front_left  = (gx,     gy + 1)

    # In our isometric projection (sx = (x - y) * HW), the visible front faces
    # from a viewer above-and-to-the-upper-left are:
    #   - left face: from front_left to back_left (the wall facing down-left)
    #   - right face: from front_right to front_left? No — the wall facing the camera.
    # Actually with our chosen projection (camera looking from upper-right down to lower-left),
    # the visible side faces are the front-left edge (between front_left & front_right) and
    # the front-right edge (between front_right & back_right).
    left_face = stone_side_polygon(front_left, front_right, top_z)   # front face (closest)
    right_face = stone_side_polygon(front_right, back_right, top_z)  # right side
    top_face = stone_top_polygon(gx, gy, top_z, seed)

    top_color = color_for_height(ROCK_TOP_LOW, ROCK_TOP_PEAK, count)
    right_color = color_for_height(ROCK_RIGHT, ROCK_RIGHT_PEAK, count)
    left_color = color_for_height(ROCK_LEFT, ROCK_LEFT_PEAK, count)

    # Brighten top further on peaks ('caught by light')
    if count >= MAX_REASONABLE_H * 0.7:
        top_color = lerp_color(top_color, ROCK_TOP_PEAK, 0.35)

    return (
        f'    <polygon points="{left_face}" fill="{left_color}"/>\n'
        f'    <polygon points="{right_face}" fill="{right_color}"/>\n'
        f'    <polygon points="{top_face}" fill="{top_color}" stroke="{ROCK_LEFT}" stroke-width="0.3"/>\n'
    )


# -----------------------------------------------------------------------------
# Entry
# -----------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true", help="Synthetic data (no network)")
    parser.add_argument("--user", default="AnteurAbderraouf")
    parser.add_argument("--out", default=str(ROOT / "contrib.svg"))
    args = parser.parse_args()

    if args.mock:
        print("Using mock contribution data...")
        days = mock_contributions()
    else:
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if not token:
            print("ERROR: GITHUB_TOKEN env var required (or pass --mock).", file=sys.stderr)
            sys.exit(2)
        print(f"Fetching contributions for {args.user}...")
        days = fetch_contributions(args.user, token)

    print(f"  {len(days)} days, total {sum(c for _, c in days)} contributions, "
          f"peak {max(c for _, c in days)}")
    print(f"  canvas: {W}x{H}")
    svg = build_svg(days)
    out_path = Path(args.out)
    out_path.write_text(svg, encoding="utf-8")
    print(f"Wrote {out_path} ({out_path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
