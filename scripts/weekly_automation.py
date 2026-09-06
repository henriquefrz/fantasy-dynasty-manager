#!/usr/bin/env python3
"""
Weekly Automation Script for Fantasy Dynasty Manager.
Supports scheduled execution:
  - Tuesday Morning: Waiver Wire & Add/Drop Audit (IR slots, taxi swaps, starter displacement).
  - Thursday Afternoon: Matchup Start/Sit Audit & TNF Injury Pivot Check.
"""

import argparse
from datetime import datetime
import os
import sys

# Ensure parent directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.sleeper_api import (
    get_user,
    get_user_leagues,
    get_league_rosters,
    get_user_roster,
    get_players,
    get_roster_players,
    get_free_agents,
    get_nfl_state,
    get_weekly_projections,
)
from src.league_classifier import classify_league
from src.market_data import (
    get_fp_rankings_raw,
    get_player_ids_raw,
    build_positional_lookup,
    get_values_players_raw,
    get_values_picks_raw,
    get_ktc_data_raw,
    get_fantasycalc_data_raw,
    build_consensus_picks_lookup,
    enrich_lookup_with_consensus_values,
    enrich_lookup_with_redraft_values,
    apply_te_premium,
)
from src.matching import match_players_by_sleeper_id
from src.analysis_engine import (
    build_intelligent_waiver_suggestions,
    enrich_with_alt_ranking,
)
from src.start_sit import (
    audit_weekly_lineup,
    calculate_weekly_projected_points,
)

USERNAME = "henriquefrz"


def run_tuesday_waiver_audit(leagues, user_id, players, dynasty_sf, dynasty_1qb, redraft_lk, output_dir=None):
    """
    Tuesday Morning: Scans all leagues for intelligent waiver wire opportunities,
    IR eligibility fixes, taxi promotions, and high-upside handcuffs.
    """
    lines = []
    lines.append("=" * 70)
    lines.append(f"TUESDAY MORNING WAIVER & ADD/DROP AUDIT — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 70)

    for league in leagues:
        league_id = league["league_id"]
        league_name = league["name"]
        rosters = get_league_rosters(league_id)
        user_roster = get_user_roster(rosters, user_id)
        if not user_roster:
            continue

        ltype = classify_league(league, rosters)
        roster_pos = league.get("roster_positions", [])
        is_sf = "SUPER_FLEX" in roster_pos or roster_pos.count("QB") >= 2
        is_dyn = ltype["type"] != "redraft"
        scoring = league.get("scoring_settings", {})
        bonus_te = scoring.get("bonus_rec_te", 0.0) or scoring.get("te_bonus", 0.0)

        lookup = dynasty_sf if is_sf else dynasty_1qb
        if bonus_te > 0:
            lookup = apply_te_premium(dict(lookup), bonus_te)

        fmt_type = f"{'Dynasty' if is_dyn else 'Redraft'} {'Superflex' if is_sf else '1QB'}"
        lines.append(f"\n🏆 League: {league_name.upper()} ({fmt_type})")
        lines.append("-" * 60)

        roster_players = get_roster_players(user_roster, players)
        free_agents = get_free_agents(rosters, players)

        alt_lk = redraft_lk if is_dyn else None

        waivers = build_intelligent_waiver_suggestions(
            roster_players=roster_players,
            free_agents=free_agents,
            primary_lookup=lookup,
            roster_positions=roster_pos,
            user_roster=user_roster,
            category="win",
            is_dynasty=is_dyn,
            alt_lookup=alt_lk,
        )

        # 1. Starting Lineup Upgrades
        starter_upgrades = waivers.get("starter_upgrades", [])
        if starter_upgrades:
            lines.append("⚡ Starting Lineup Upgrades:")
            for s in starter_upgrades[:3]:
                add_p = s["add_player"].get("full_name") or s["add_player"].get("player_id")
                drop_p = s["drop_player"].get("full_name") or s["drop_player"].get("player_id")
                diff = s.get("market_value_gain", 0.0)
                lines.append(f"  • ADD {add_p} -> DROP {drop_p} (Net Gain: +{diff:,.0f} pts)")

        # 2. Cross-position bench moves
        cross_upgrades = waivers.get("cross_pos_upgrades", [])
        if cross_upgrades:
            lines.append("📈 High-Value Bench Upgrades:")
            for s in cross_upgrades[:3]:
                add_p = s["add_player"].get("full_name") or s["add_player"].get("player_id")
                drop_p = s["drop_player"].get("full_name") or s["drop_player"].get("player_id")
                diff = s.get("market_value_gain", 0.0)
                lines.append(f"  • ADD {add_p} -> DROP {drop_p} (Net Gain: +{diff:,.0f} pts)")

        # 3. IR / Taxi slot recommendations
        ir_rec = waivers.get("ir_suggestions", [])
        if ir_rec:
            lines.append("🚑 IR / Taxi Stash Opportunities:")
            for r in ir_rec[:3]:
                pname = r["player"].get("full_name") or r["player"].get("player_id")
                lines.append(f"  • {pname} ({r.get('reason', 'Eligible stash')})")

        if not starter_upgrades and not cross_upgrades and not ir_rec:
            lines.append("  ✅ Roster is fully optimized. No mandatory waiver wire moves required.")

    report = "\n".join(lines)
    print(report)

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        fname = os.path.join(output_dir, f"waiver_audit_{datetime.now().strftime('%Y%m%d')}.txt")
        with open(fname, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\n[+] Report written to {fname}")


def run_thursday_start_sit_audit(leagues, user_id, players, dynasty_sf, dynasty_1qb, weekly_proj, active_season, active_week, output_dir=None):
    """
    Thursday Afternoon: Checks upcoming matchups, starter health, bench pivots,
    and stud-protected streaming options ahead of Thursday Night Football.
    """
    lines = []
    lines.append("=" * 70)
    lines.append(f"THURSDAY START/SIT & INJURY CHECK (WEEK {active_week}) — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 70)

    for league in leagues:
        league_id = league["league_id"]
        league_name = league["name"]
        rosters = get_league_rosters(league_id)
        user_roster = get_user_roster(rosters, user_id)
        if not user_roster:
            continue

        ltype = classify_league(league, rosters)
        roster_pos = league.get("roster_positions", [])
        is_sf = "SUPER_FLEX" in roster_pos or roster_pos.count("QB") >= 2
        is_dyn = ltype["type"] != "redraft"
        scoring = league.get("scoring_settings", {})
        bonus_te = scoring.get("bonus_rec_te", 0.0) or scoring.get("te_bonus", 0.0)

        lookup = dynasty_sf if is_sf else dynasty_1qb
        if bonus_te > 0:
            lookup = apply_te_premium(dict(lookup), bonus_te)

        roster_players = get_roster_players(user_roster, players)
        proj_lookup = {}
        for p in roster_players:
            pid = p.get("player_id")
            raw = weekly_proj.get(pid)
            proj_lookup[pid] = calculate_weekly_projected_points(pid, raw, scoring, p)

        audit = audit_weekly_lineup(
            user_roster=user_roster,
            roster_players=roster_players,
            projections_lookup=proj_lookup,
            roster_positions=roster_pos,
            player_db=players,
        )

        fmt_type = f"{'Dynasty' if is_dyn else 'Redraft'} {'Superflex' if is_sf else '1QB'}"
        lines.append(f"\n🏆 League: {league_name.upper()} ({fmt_type})")
        lines.append(f"  • Projected Starters: {audit['active_points_total']:.1f} pts | Optimal Lineup: {audit['optimal_points_total']:.1f} pts (Gain: +{audit['points_differential']:.1f})")

        # Injury Alerts
        injuries = audit.get("injury_alerts", [])
        if injuries:
            lines.append("  ⚠️ Active Starter Injury Alerts & Pivots:")
            for inj in injuries:
                sname = inj["starter"].get("full_name") or inj["starter"].get("player_id")
                status = inj["status"]
                slot = inj["slot"]
                pivot = inj.get("pivot")
                if pivot:
                    pname = pivot[0].get("full_name")
                    pproj = pivot[1]
                    lines.append(f"    - [{status}] {sname} ({slot}) -> BENCH PIVOT: {pname} ({pproj:.1f} pts)")
                else:
                    lines.append(f"    - [{status}] {sname} ({slot}) -> NO HEALTHY BENCH PIVOT FOUND!")

        # Optimization
        swaps = audit.get("start_sit_swaps", [])
        if swaps:
            lines.append("  ⚡ Start/Sit Optimizations:")
            for r in swaps:
                lines.append(f"    - START {r['start_player'].get('full_name')} ({r['start_proj']:.1f} pts) over {r['sit_player'].get('full_name')} ({r['sit_proj']:.1f} pts) [+{r['gain']:.1f} pts]")

        # Streaming pivots
        streaming = audit.get("streaming_pivots", [])
        if streaming:
            lines.append("  🌊 Recommended FA Streamers:")
            for st in streaming[:2]:
                lines.append(f"    - STREAM {st['fa_player']['full_name']} (Proj: {st['fa_proj']:.1f}) -> Drop Safe Bench {st['safe_drop_player']['full_name']}")

        if not injuries and not recs and not streaming:
            lines.append("  ✅ Active lineup matches optimal projection. No changes needed.")

    report = "\n".join(lines)
    print(report)

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        fname = os.path.join(output_dir, f"start_sit_audit_{datetime.now().strftime('%Y%m%d')}.txt")
        with open(fname, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\n[+] Report written to {fname}")


def main():
    parser = argparse.ArgumentParser(description="Weekly Automation: Tuesday Waivers & Thursday Start/Sit")
    parser.add_argument("--routine", choices=["tuesday", "thursday", "all"], default="all", help="Which audit routine to execute")
    parser.add_argument("--league", type=str, default=None, help="Filter by specific league name")
    parser.add_argument("--output-dir", type=str, default="reports", help="Directory to save audit reports")
    args = parser.parse_args()

    print(f"Initializing weekly automation routine: {args.routine.upper()}...")
    user = get_user(USERNAME)
    user_id = user["user_id"]
    nfl_state = get_nfl_state()
    active_season = nfl_state.get("season", "2026")
    active_week = nfl_state.get("week", 1)

    leagues = get_user_leagues(user_id, active_season)
    if args.league:
        leagues = [l for l in leagues if args.league.lower() in l["name"].lower()]

    players = get_players()
    fp_rankings = get_fp_rankings_raw()
    player_ids = get_player_ids_raw()
    values_players = get_values_players_raw()

    ktc_sf = get_ktc_data_raw(is_superflex=True)
    ktc_1qb = get_ktc_data_raw(is_superflex=False)
    fc_sf = get_fantasycalc_data_raw(is_dynasty=True, is_superflex=True)
    fc_1qb = get_fantasycalc_data_raw(is_dynasty=True, is_superflex=False)
    fc_redraft = get_fantasycalc_data_raw(is_dynasty=False, is_superflex=False)

    dynasty_sf = build_positional_lookup(fp_rankings, player_ids, "dynasty")
    enrich_lookup_with_consensus_values(dynasty_sf, values_players, player_ids, ktc_raw=ktc_sf, fc_raw=fc_sf, is_superflex=True)

    dynasty_1qb = build_positional_lookup(fp_rankings, player_ids, "dynasty")
    enrich_lookup_with_consensus_values(dynasty_1qb, values_players, player_ids, ktc_raw=ktc_1qb, fc_raw=fc_1qb, is_superflex=False)

    redraft_lk = build_positional_lookup(fp_rankings, player_ids, "redraft")
    enrich_lookup_with_redraft_values(redraft_lk, fc_redraft_raw=fc_redraft)

    if args.routine in ["tuesday", "all"]:
        run_tuesday_waiver_audit(leagues, user_id, players, dynasty_sf, dynasty_1qb, redraft_lk, output_dir=args.output_dir)

    if args.routine in ["thursday", "all"]:
        weekly_proj = get_weekly_projections(active_season, active_week)
        run_thursday_start_sit_audit(leagues, user_id, players, dynasty_sf, dynasty_1qb, weekly_proj, active_season, active_week, output_dir=args.output_dir)


if __name__ == "__main__":
    main()
