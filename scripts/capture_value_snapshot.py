#!/usr/bin/env python3
"""
Captures a dated snapshot of:
  1. Every player's/pick's raw per-source market-value components
     (FantasyCalc, KeepTradeCut, DynastyProcess) for both dynasty pool
     formats (Superflex and 1QB) - the foundation for the Market Rankings
     "value history" line chart.
  2. Every league's roster + draft-pick ownership (dynasty and redraft
     alike) - who owned what, on this date, in every league. Rosters
     change via trades/waivers, so this can only ever be captured
     going forward; it is captured now even though nothing consumes it
     yet, since a day not captured is a day of roster history lost for
     good (see the Etapa B - Total Net Worth - proposal).

Only the raw per-source components (fc/ktc/dp) are stored for values, not
the blended composite - any consensus mode (equal/dp-only/ktc-only/...)
can be reconstructed later from these three numbers via
src.market_data.apply_valuation_mode, so this file never needs
re-capturing just because the app's default blend changes.

Appends one line per run (one per calendar date - re-running the same
date replaces that date's line rather than duplicating it) to:
  data/value_history/dynasty_sf.jsonl
  data/value_history/dynasty_1qb.jsonl
  data/value_history/rosters.jsonl

A sanity floor on the dynasty lookups (MIN_EXPECTED_ENTRIES) makes this
script fail loudly - a non-zero exit code GitHub Actions will notify
about - instead of silently committing a near-empty snapshot if a source
API ever changes shape, same spirit as scrape_fantasypros_ros.py's
MIN_EXPECTED_PLAYERS. Per-league roster capture failures are logged and
skipped individually instead, since one league's transient API hiccup
shouldn't discard every other league's snapshot for the day.

Usage:
  .venv/bin/python scripts/capture_value_snapshot.py
  .venv/bin/python scripts/capture_value_snapshot.py --date 2026-09-18  (backfill/testing only)
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.market_data import (
    get_fp_rankings_raw,
    get_player_ids_raw,
    get_values_players_raw,
    get_values_picks_raw,
    get_ktc_data_raw,
    get_fantasycalc_data_raw,
    build_positional_lookup,
    enrich_lookup_with_consensus_values,
)
from src.sleeper_api import (
    get_user,
    get_user_leagues,
    get_league_rosters,
    get_league_users,
    get_traded_picks,
    get_nfl_state,
)
from src.draft_picks import build_picks_ownership, get_picks_for_roster

# Matches scripts/weekly_automation.py's own single-user convention - this
# is personal infrastructure for one Sleeper account, not a multi-tenant
# service (see app.py's ALLOWED_USERS for the separate, unrelated set of
# accounts the interactive app itself supports).
USERNAME = "henriquefrz"

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "value_history")
DYNASTY_SF_PATH = os.path.join(DATA_DIR, "dynasty_sf.jsonl")
DYNASTY_1QB_PATH = os.path.join(DATA_DIR, "dynasty_1qb.jsonl")
ROSTERS_PATH = os.path.join(DATA_DIR, "rosters.jsonl")

# The dynasty pool (players + picks combined) currently sits at ~578 (SF)
# / ~582 (1QB) entries; 400 leaves generous room for normal week-to-week
# churn while still catching a broken fetch (e.g. a source API renaming a
# field and silently emptying most of the lookup).
MIN_EXPECTED_ENTRIES = 400


def build_dynasty_value_snapshot(is_superflex, fp_rankings, player_ids, values_players, values_picks, ktc_raw, fc_raw):
    """
    Builds one date's { "<sleeper_id_or_pick_key>": {fc, ktc, dp, name, pos} }
    snapshot for one dynasty pool format - same lookup-building pipeline
    fetch_market_database (app.py) and weekly_automation.py already use,
    stopping short of computing the blended composite.
    """
    lookup = build_positional_lookup(fp_rankings, player_ids, "dynasty", is_superflex=is_superflex)
    enrich_lookup_with_consensus_values(
        lookup, values_players, player_ids, ktc_raw=ktc_raw, fc_raw=fc_raw,
        is_superflex=is_superflex, mode="equal", values_picks_raw=values_picks,
    )

    snapshot = {}
    for pid, p in lookup.items():
        snapshot[str(pid)] = {
            "fc": p.get("fc_val"),
            "ktc": p.get("ktc_val"),
            "dp": p.get("dp_val"),
            "name": p.get("player_name") or "",
            "pos": p.get("position") or "",
        }
    return snapshot


def capture_league_rosters(user_id, season):
    """
    Captures, for every league the user is in this season (dynasty and
    redraft alike), each roster's owner, current player_ids, and owned
    future draft picks (as "{season}-R{round}-orig{original_roster_id}"
    strings - a stable ownership key, independent of any projected
    tier/value a pick might carry - see src.draft_picks.get_picks_for_roster).
    """
    leagues = get_user_leagues(user_id, season)
    league_snapshots = {}

    for league in leagues:
        lid = str(league.get("league_id"))
        lname = league.get("name", lid)
        try:
            rosters = get_league_rosters(lid)
            league_users = get_league_users(lid)
            traded_picks = get_traded_picks(lid)

            username_by_owner_id = {u.get("user_id"): u.get("display_name", "Unknown") for u in league_users}
            ownership = build_picks_ownership(league, traded_picks)

            roster_snapshot = {}
            for r in rosters:
                rid = str(r.get("roster_id"))
                owned_picks = get_picks_for_roster(ownership, r.get("roster_id"))
                pick_ids = [f"{pk_season}-R{pk_round}-orig{orig_rid}" for (pk_season, pk_round, orig_rid) in owned_picks]

                roster_snapshot[rid] = {
                    "owner": username_by_owner_id.get(r.get("owner_id"), "Unknown"),
                    "player_ids": [p for p in (r.get("players") or []) if p],
                    "pick_ids": pick_ids,
                }

            league_snapshots[lid] = roster_snapshot
        except Exception as e:
            print(f"Warning: failed to capture rosters for league '{lname}' ({lid}): {e}")

    return league_snapshots


def upsert_jsonl_line(path, date_str, payload_key, payload_value):
    """
    Appends {"date": date_str, payload_key: payload_value} to path, one
    JSON object per line. If a line for date_str already exists, it is
    replaced (not duplicated) - re-running the capture for the same date
    (a manual workflow_dispatch retry, or local testing) must not leave
    two conflicting points for the same day in the history.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)

    existing_lines = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            existing_lines = [line for line in f if line.strip()]

    kept_lines = []
    for line in existing_lines:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("date") != date_str:
            kept_lines.append(line.rstrip("\n"))

    new_line = json.dumps({"date": date_str, payload_key: payload_value}, separators=(",", ":"))
    kept_lines.append(new_line)

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(kept_lines) + "\n")


def run(date_str):
    print(f"Capturing value/roster snapshot for {date_str}...")

    fp_rankings = get_fp_rankings_raw()
    player_ids = get_player_ids_raw()
    values_players = get_values_players_raw()
    values_picks = get_values_picks_raw()
    ktc_sf = get_ktc_data_raw(is_superflex=True)
    ktc_1qb = get_ktc_data_raw(is_superflex=False)
    fc_sf = get_fantasycalc_data_raw(is_dynasty=True, is_superflex=True)
    fc_1qb = get_fantasycalc_data_raw(is_dynasty=True, is_superflex=False)

    sf_snapshot = build_dynasty_value_snapshot(True, fp_rankings, player_ids, values_players, values_picks, ktc_sf, fc_sf)
    qb_snapshot = build_dynasty_value_snapshot(False, fp_rankings, player_ids, values_players, values_picks, ktc_1qb, fc_1qb)

    print(f"Built dynasty_sf snapshot: {len(sf_snapshot)} entries")
    print(f"Built dynasty_1qb snapshot: {len(qb_snapshot)} entries")

    if len(sf_snapshot) < MIN_EXPECTED_ENTRIES:
        raise RuntimeError(
            f"Only {len(sf_snapshot)} entries built for dynasty_sf, expected at least "
            f"{MIN_EXPECTED_ENTRIES}. A source API likely changed shape - refusing to "
            f"commit a near-empty snapshot. Check get_ktc_data_raw/get_fantasycalc_data_raw/"
            f"get_values_players_raw against their live sources."
        )
    if len(qb_snapshot) < MIN_EXPECTED_ENTRIES:
        raise RuntimeError(
            f"Only {len(qb_snapshot)} entries built for dynasty_1qb, expected at least "
            f"{MIN_EXPECTED_ENTRIES}. A source API likely changed shape - refusing to "
            f"commit a near-empty snapshot. Check get_ktc_data_raw/get_fantasycalc_data_raw/"
            f"get_values_players_raw against their live sources."
        )

    upsert_jsonl_line(DYNASTY_SF_PATH, date_str, "players", sf_snapshot)
    upsert_jsonl_line(DYNASTY_1QB_PATH, date_str, "players", qb_snapshot)
    print(f"Wrote {DYNASTY_SF_PATH}")
    print(f"Wrote {DYNASTY_1QB_PATH}")

    user = get_user(USERNAME)
    user_id = user.get("user_id")
    if not user_id:
        raise RuntimeError(f"Could not resolve Sleeper user_id for '{USERNAME}' - refusing to skip roster capture silently.")

    nfl_state = get_nfl_state() or {}
    season = nfl_state.get("season", str(datetime.now(timezone.utc).year))

    league_snapshots = capture_league_rosters(user_id, season)
    print(f"Captured rosters for {len(league_snapshots)} leagues")
    if not league_snapshots:
        print(f"Warning: 0 leagues captured for '{USERNAME}' (season {season}) - check get_user_leagues.")

    upsert_jsonl_line(ROSTERS_PATH, date_str, "leagues", league_snapshots)
    print(f"Wrote {ROSTERS_PATH}")

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Capture a dated dynasty value + roster snapshot.")
    parser.add_argument(
        "--date", type=str, default=None,
        help="Override the snapshot date (YYYY-MM-DD) - for backfilling or local testing only. Defaults to today (UTC).",
    )
    args = parser.parse_args()

    snapshot_date = args.date or datetime.now(timezone.utc).date().isoformat()
    sys.exit(run(snapshot_date))
