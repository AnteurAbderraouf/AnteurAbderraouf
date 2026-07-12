"""Render stats.svg — a compact 'at a glance' stats card for the profile README.

Why not github-readme-stats.vercel.app: the shared Vercel deployment gets
paused when it exceeds free-tier limits, breaking the embedded image. This
script pulls the same numbers directly from GitHub's GraphQL API and renders
an SVG in the Das Stein Adler palette. No external service to depend on.

Streaks (current + longest) are computed from the full contribution calendar,
walking year-by-year from account creation to today because GraphQL caps a
single contributionsCollection query at a 1-year window.

Modes:
  --mock        Use static values (no network).
  --user NAME   Fetch live data for NAME (default AnteurAbderraouf).
                Requires env GITHUB_TOKEN (a PAT with read:user / public_repo).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent

# Palette (Das Stein Adler) ---------------------------------------------------
BG = "#1a1a1a"
BORDER = "#6b5244"
LABEL = "#a89070"
VALUE = "#e8e0d4"
DIVIDER = "#6b5244"
ACCENT = "#c8bdb0"

# Canvas ----------------------------------------------------------------------
W, H = 495, 250
PAD_X = 34
PAD_Y = 28

FONT_STACK = "'EB Garamond', Georgia, 'Times New Roman', serif"


# -----------------------------------------------------------------------------
# Data
# -----------------------------------------------------------------------------

META_QUERY = """
query($login: String!) {
  user(login: $login) {
    createdAt
    followers { totalCount }
    pullRequests { totalCount }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC) {
      totalCount
      nodes {
        stargazerCount
        languages(first: 5, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name } }
        }
      }
    }
  }
}
"""

CALENDAR_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""


def _graphql(token: str, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=payload,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "stats-svg-builder/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode())
    if "errors" in body:
        raise RuntimeError(f"GraphQL error: {body['errors']}")
    return body


def _fetch_meta(user: str, token: str) -> dict[str, Any]:
    body = _graphql(token, META_QUERY, {"login": user})
    u = body["data"]["user"]
    if u is None:
        raise RuntimeError(f"User {user!r} not found")

    lang_bytes: Counter[str] = Counter()
    total_stars = 0
    for repo in u["repositories"]["nodes"]:
        total_stars += repo["stargazerCount"]
        for edge in repo["languages"]["edges"]:
            lang_bytes[edge["node"]["name"]] += edge["size"]

    return {
        "created_at": u["createdAt"],
        "followers": u["followers"]["totalCount"],
        "prs": u["pullRequests"]["totalCount"],
        "repos": u["repositories"]["totalCount"],
        "stars": total_stars,
        "top_langs": [name for name, _ in lang_bytes.most_common(5)],
    }


def _fetch_all_days(user: str, token: str, created_at: str) -> list[tuple[str, int]]:
    """All contribution days from account creation to today, oldest first."""
    created = dt.datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    today = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)

    all_days: dict[str, int] = {}
    chunk_start = created
    one_year = dt.timedelta(days=365)
    while chunk_start < today:
        chunk_end = min(chunk_start + one_year, today)
        body = _graphql(token, CALENDAR_QUERY, {
            "login": user,
            "from": chunk_start.isoformat().replace("+00:00", "Z"),
            "to": chunk_end.isoformat().replace("+00:00", "Z"),
        })
        weeks = body["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
        for w in weeks:
            for d in w["contributionDays"]:
                # Dedup on date across window boundaries; last write wins.
                all_days[d["date"]] = int(d["contributionCount"])
        chunk_start = chunk_end + dt.timedelta(seconds=1)

    return sorted(all_days.items())


def _compute_streaks(days: list[tuple[str, int]]) -> tuple[int, int]:
    """(current_streak, longest_streak) in days.

    Current streak convention: if the last day (today) has 0 contributions,
    the streak isn't considered broken yet — the day isn't over. Runs ending
    yesterday are still 'alive'."""
    if not days:
        return 0, 0

    longest = 0
    run = 0
    for _, count in days:
        if count > 0:
            run += 1
            longest = max(longest, run)
        else:
            run = 0

    current = 0
    last_idx = len(days) - 1
    for i in range(last_idx, -1, -1):
        _, count = days[i]
        if count > 0:
            current += 1
        elif i == last_idx:
            continue
        else:
            break

    return current, longest


def fetch_stats(user: str, token: str) -> dict[str, Any]:
    meta = _fetch_meta(user, token)
    days = _fetch_all_days(user, token, meta["created_at"])
    current, longest = _compute_streaks(days)
    total_contributions = sum(count for _, count in days)

    return {
        "commits": total_contributions,
        "prs": meta["prs"],
        "repos": meta["repos"],
        "stars": meta["stars"],
        "followers": meta["followers"],
        "top_langs": meta["top_langs"],
        "current_streak": current,
        "longest_streak": longest,
    }


def mock_stats() -> dict[str, Any]:
    return {
        "commits": 3847,
        "prs": 68,
        "repos": 24,
        "stars": 31,
        "followers": 15,
        "top_langs": ["Python", "TypeScript", "PHP", "Dart", "Go"],
        "current_streak": 12,
        "longest_streak": 47,
    }


# -----------------------------------------------------------------------------
# SVG assembly
# -----------------------------------------------------------------------------

def build_svg(s: dict[str, Any]) -> str:
    rows: list[tuple[str, str]] = [
        ("Contributions",   f"{s['commits']:,}"),
        ("Pull requests",   f"{s['prs']:,}"),
        ("Repositories",    f"{s['repos']:,}"),
        ("Stars earned",    f"{s['stars']:,}"),
        ("Followers",       f"{s['followers']:,}"),
        ("Current streak",  f"{s['current_streak']} days"),
        ("Longest streak",  f"{s['longest_streak']} days"),
    ]

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'width="{W}" height="{H}" role="img" '
        f'aria-label="Stats: {s["commits"]:,} contributions, '
        f'{s["prs"]:,} pull requests, {s["repos"]:,} repositories, '
        f'{s["stars"]:,} stars, {s["followers"]:,} followers, '
        f'{s["current_streak"]} day current streak, '
        f'{s["longest_streak"]} day longest streak.">\n'
    )

    parts.append(
        f'  <rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="6" ry="6" '
        f'fill="{BG}" stroke="{BORDER}" stroke-width="1"/>\n'
    )

    title_y = PAD_Y + 12
    parts.append(
        f'  <text x="{PAD_X}" y="{title_y}" font-family="{FONT_STACK}" '
        f'font-size="15" fill="{VALUE}" letter-spacing="4">'
        f'⟡ &#160;&#160;AT A GLANCE</text>\n'
    )

    row_start_y = title_y + 30
    row_step = 20
    for i, (label, value) in enumerate(rows):
        y = row_start_y + i * row_step
        parts.append(
            f'  <text x="{PAD_X}" y="{y}" font-family="{FONT_STACK}" '
            f'font-size="11" fill="{LABEL}" letter-spacing="2.4">'
            f'{label.upper()}</text>\n'
        )
        parts.append(
            f'  <text x="{W - PAD_X}" y="{y}" font-family="{FONT_STACK}" '
            f'font-size="14" fill="{VALUE}" text-anchor="end">{value}</text>\n'
        )

    div_y = row_start_y + len(rows) * row_step + 4
    gap = 72
    parts.append(
        f'  <line x1="{PAD_X + 40}" y1="{div_y}" x2="{W/2 - gap/2}" y2="{div_y}" '
        f'stroke="{DIVIDER}" stroke-width="0.6"/>\n'
    )
    parts.append(
        f'  <text x="{W/2}" y="{div_y + 4}" font-family="{FONT_STACK}" '
        f'font-size="12" fill="{DIVIDER}" text-anchor="middle">⟡</text>\n'
    )
    parts.append(
        f'  <line x1="{W/2 + gap/2}" y1="{div_y}" x2="{W - PAD_X - 40}" y2="{div_y}" '
        f'stroke="{DIVIDER}" stroke-width="0.6"/>\n'
    )

    langs = s["top_langs"][:5]
    lang_text = "  ·  ".join(langs) if langs else ""
    lang_y = div_y + 22
    parts.append(
        f'  <text x="{W/2}" y="{lang_y}" font-family="{FONT_STACK}" '
        f'font-size="12" fill="{ACCENT}" text-anchor="middle" '
        f'font-style="italic">{lang_text}</text>\n'
    )

    parts.append("</svg>\n")
    return "".join(parts)


# -----------------------------------------------------------------------------
# Entry
# -----------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true", help="Static data (no network)")
    parser.add_argument("--user", default="AnteurAbderraouf")
    parser.add_argument("--out", default=str(ROOT / "stats.svg"))
    args = parser.parse_args()

    if args.mock:
        print("Using mock stats...")
        stats = mock_stats()
    else:
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if not token:
            print("ERROR: GITHUB_TOKEN env var required (or pass --mock).", file=sys.stderr)
            sys.exit(2)
        print(f"Fetching stats for {args.user}...")
        stats = fetch_stats(args.user, token)

    print(
        f"  commits={stats['commits']:,}  prs={stats['prs']:,}  "
        f"repos={stats['repos']:,}  stars={stats['stars']:,}  "
        f"followers={stats['followers']:,}"
    )
    print(f"  streaks: current={stats['current_streak']}d, longest={stats['longest_streak']}d")
    print(f"  top languages: {', '.join(stats['top_langs'][:5]) or '(none)'}")
    svg = build_svg(stats)
    out_path = Path(args.out)
    out_path.write_text(svg, encoding="utf-8")
    print(f"Wrote {out_path} ({out_path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
