"""
Scrapes FantasyPros' Rest-of-Season PPR overall rankings (a single page
covering every skill position, K, and DST in one cross-positional pool) and
writes the result to data/fp_ros_ppr_latest.json as
{"scraped_at": "<ISO UTC timestamp>", "rows": [...]} - the "rows" list is in
the same row shape build_positional_lookup/_build_player_lookup/
_build_dst_lookup already parse for "redraft-*" page_type rows, so no
downstream parsing logic changes; "scraped_at" lets the app detect a stale
file even when the fetch itself succeeds (see get_market_data_freshness).

This replaces db_fpecr_latest.csv's "redraft-*" rows (DynastyProcess) as the
source of REDRAFT/ROS FantasyPros ECR data only. Dynasty rankings are
untouched and keep coming from DynastyProcess.

FantasyPros does not publish a Superflex variant of this ROS page (confirmed
by inspecting the live page's position/scoring menus and testing the likely
URL patterns), so this is 1QB-flavored data only - a known, accepted
limitation, not a bug.

A sanity floor (MIN_EXPECTED_PLAYERS) makes this script fail loudly - a
non-zero exit code GitHub Actions will notify about - instead of silently
committing a near-empty file if FantasyPros ever renames a JSON field this
script depends on (player_id/rank_ecr rows would just get skipped one by
one otherwise, with no other error).

Usage: .venv/bin/python scripts/scrape_fantasypros_ros.py
"""
import json
import os
import re
import sys
from datetime import datetime, timezone

import requests

ROS_PPR_OVERALL_URL = "https://www.fantasypros.com/nfl/rankings/ros-ppr-overall.php"

# Honest, identifying User-Agent - this is a scheduled scraper for a hobby
# fantasy football project, not a browser impersonation.
HEADERS = {
    "User-Agent": "fantasy-dynasty-manager-scraper/1.0 (+https://github.com/henriquefrz/fantasy-dynasty-manager)",
}

OUTPUT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "fp_ros_ppr_latest.json")

# Positions build_positional_lookup's redraft path actually consumes today:
# QB/RB/WR/TE/K go through the generic per-position "redraft-{pos}" pool,
# DST goes through the separate team-keyed "redraft-dst" pool. Anything else
# on the page (there isn't anything else in practice) is skipped.
KNOWN_POSITIONS = {"QB", "RB", "WR", "TE", "K", "DST"}

# The live page currently has ~404 players; 300 leaves generous room for
# normal week-to-week roster churn while still catching a broken scrape
# (e.g. a renamed JSON field silently dropping most players one by one).
MIN_EXPECTED_PLAYERS = 300


def fetch_ros_ppr_ecr_data():
    """
    Fetches the live page and extracts the embedded `var ecrData = {...};`
    JSON blob - the same "JSON embedded in a <script> tag" shape already
    used for KTC's dynasty-rankings/fantasy-rankings pages, just from a
    plain HTML response instead of a DOM script tag.
    """
    response = requests.get(ROS_PPR_OVERALL_URL, headers=HEADERS, timeout=20)
    response.raise_for_status()
    html = response.text

    match = re.search(r"var ecrData\s*=\s*(\{.*?\});", html, re.DOTALL)
    if not match:
        raise RuntimeError("Could not find 'var ecrData = {...};' in the page - FantasyPros may have changed its markup.")

    return json.loads(match.group(1))


def build_redraft_rows(ecr_data):
    """
    Converts each player in ecr_data["players"] into two rows matching the
    existing "redraft-*" page_type schema: one tagged "redraft-overall"
    (the page's own cross-positional rank, used for rank_ecr_overall) and
    one tagged "redraft-{pos}" (used for the within-position rank) - the
    same duplication db_fpecr_latest.csv already had for these page types.
    """
    rows = []
    skipped_positions = set()

    for player in ecr_data.get("players", []):
        pos = (player.get("player_position_id") or "").upper()
        if pos not in KNOWN_POSITIONS:
            skipped_positions.add(pos)
            continue

        player_id = player.get("player_id")
        rank_ecr = player.get("rank_ecr")
        player_name = player.get("player_name") or ""
        team = player.get("player_team_id") or ""

        if player_id is None or rank_ecr is None:
            continue

        base_row = {
            "id": str(player_id),
            "ecr": str(rank_ecr),
            "player": player_name,
            "pos": pos,
            "team": team,
        }

        rows.append({**base_row, "page_type": "redraft-overall"})
        rows.append({**base_row, "page_type": f"redraft-{pos.lower()}"})

    if skipped_positions:
        print(f"Info: skipped positions not consumed by build_positional_lookup's redraft path: {sorted(skipped_positions)}")

    return rows


def run():
    print(f"Fetching {ROS_PPR_OVERALL_URL} ...")
    ecr_data = fetch_ros_ppr_ecr_data()

    total_players = len(ecr_data.get("players", []))
    print(f"Fetched {total_players} players (type={ecr_data.get('type')}, "
          f"scoring={ecr_data.get('scoring')}, total_experts={ecr_data.get('total_experts')}, "
          f"last_updated={ecr_data.get('last_updated')})")

    rows = build_redraft_rows(ecr_data)
    player_count = len(rows) // 2
    print(f"Built {len(rows)} redraft-* rows ({player_count} players x 2 page_type rows each)")

    if player_count < MIN_EXPECTED_PLAYERS:
        raise RuntimeError(
            f"Only {player_count} players parsed from {ROS_PPR_OVERALL_URL}, "
            f"expected at least {MIN_EXPECTED_PLAYERS}. FantasyPros likely changed "
            f"the page's field names or structure - refusing to overwrite "
            f"{OUTPUT_PATH} with a near-empty/broken dataset. Check "
            f"fetch_ros_ppr_ecr_data()/build_redraft_rows() against the live page."
        )

    scraped_at = datetime.now(timezone.utc).isoformat()
    output = {"scraped_at": scraped_at, "rows": rows}

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print(f"Wrote {OUTPUT_PATH}")
    print(f"Scraped at {scraped_at}")
    return 0


if __name__ == "__main__":
    sys.exit(run())
