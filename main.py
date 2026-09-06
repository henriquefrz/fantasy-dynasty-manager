import argparse
import copy
import sys
from src.sleeper_api import (
    get_user,
    get_user_leagues,
    get_league_rosters,
    get_user_roster,
    get_players,
    get_roster_players,
    get_free_agents,
    get_traded_picks,
    get_league_users,
    get_nfl_state,
    get_weekly_projections,
    get_league_schedule,
)
from src.league_classifier import classify_league, get_starter_counts
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
    calculate_weekly_projected_points,
    simulate_optimal_weekly_lineup,
    audit_weekly_lineup,
    find_streaming_recommendations,
)
from src.trade_engine import (
    analyze_team_profile,
    generate_trade_suggestions,
    format_asset_str,
)
from src.team_strength import (
    calculate_team_strength,
    rank_teams_in_league,
    get_strength_tier,
    get_current_strength_tier,
    classify_dynasty_team,
    classify_redraft_team,
    get_picks_qualifier,
    percentile_score,
    score_to_tier,
)
from src.draft_picks import (
    build_picks_ownership,
    get_picks_for_roster,
    format_picks_summary,
    get_picks_capital_value,
    rank_teams_by_picks,
)
from src.playoff_simulator import (
    compute_team_lineup_expectation,
    run_monte_carlo_simulation,
    format_power_rankings_table,
    compute_dynasty_power_rankings,
    format_dynasty_power_rankings_table,
)
from src.trade_finder import (
    resolve_asset_from_query,
    find_targeted_buy_trades,
    find_targeted_sell_trades,
    print_targeted_trades_summary,
)


username = "henriquefrz"
season = "2026"

POSITIONS = ["QB", "RB", "WR", "TE", "K", "DEF"]


def format_waiver_player(p, r, alt_lk=None, show_sources=False):
    name = p.get("full_name") or p.get("player_id", "Unknown")
    pos = p.get("position") or ""
    team = p.get("team") or "FA"
    val = r.get("market_value", 0.0)

    parts = [f"{pos}, {team}", f"{val:,.0f} pts"]

    if show_sources and r.get("ktc_val") and r.get("dp_val"):
        parts.append(f"KTC: {r['ktc_val']:,.0f} | DP: {r['dp_val']:,.0f}")

    if alt_lk:
        alt = alt_lk.get(p.get("player_id"))
        if alt and alt.get("rank_ecr") and alt["rank_ecr"] < 999:
            parts.append(f"Redraft #{alt['rank_ecr']:.0f}")

    return f"{name} ({parts[0]} — {' | '.join(parts[1:])})"


parser = argparse.ArgumentParser(description="Fantasy Dynasty Manager CLI (Consensus Valuation, Start/Sit & Trade Finder)")
parser.add_argument("--league", "-l", type=str, default=None, help="Filter to a specific league name (fuzzy case-insensitive match)")
parser.add_argument("--trade-for", type=str, default=None, help="Target a specific player or pick to acquire across the league")
parser.add_argument("--trade-away", type=str, default=None, help="Find optimal league trade partners to sell a rostered asset")
parser.add_argument("--simulate", "-s", action="store_true", help="Run 1,000-iteration Monte Carlo playoff simulator & power rankings")
parser.add_argument("--all", "-a", action="store_true", help="Run full suite: Start/Sit, Waivers, General Trades, and Playoff Simulation")
args = parser.parse_args()

user = get_user(username)
user_id = user["user_id"]

leagues = get_user_leagues(user_id, season)

if args.league:
    matched = [l for l in leagues if args.league.lower() in l["name"].lower()]
    if matched:
        leagues = matched
        print(f"Filtered to league(s) matching '{args.league}': {[l['name'] for l in leagues]}")
    else:
        print(f"No leagues found matching '{args.league}'. Available leagues:")
        for l in leagues:
            print(f" - {l['name']}")
        sys.exit(0)

print(f"User: {user['username']}")
print(f"User ID: {user_id}")
print(f"Leagues found: {len(leagues)}")

players = get_players()
print(f"Players available in Sleeper database: {len(players)}")

print()
print("Downloading rankings & market values (FantasyCalc / KeepTradeCut / DynastyProcess):")

fp_rankings = get_fp_rankings_raw()
player_ids = get_player_ids_raw()
values_players = get_values_players_raw()
values_picks = get_values_picks_raw()

# Fetch live multi-source market values
ktc_sf = get_ktc_data_raw(is_superflex=True)
ktc_1qb = get_ktc_data_raw(is_superflex=False)
fc_sf = get_fantasycalc_data_raw(is_dynasty=True, is_superflex=True)
fc_1qb = get_fantasycalc_data_raw(is_dynasty=True, is_superflex=False)
fc_redraft = get_fantasycalc_data_raw(is_dynasty=False, is_superflex=False)

# Build baseline positional lookups enriched with 3-Pillar Consensus points (0-10,000 scale)
dynasty_lookup_sf = build_positional_lookup(fp_rankings, player_ids, "dynasty")
enrich_lookup_with_consensus_values(dynasty_lookup_sf, values_players, player_ids, ktc_raw=ktc_sf, fc_raw=fc_sf, is_superflex=True)

dynasty_lookup_1qb = build_positional_lookup(fp_rankings, player_ids, "dynasty")
enrich_lookup_with_consensus_values(dynasty_lookup_1qb, values_players, player_ids, ktc_raw=ktc_1qb, fc_raw=fc_1qb, is_superflex=False)

redraft_lookup = build_positional_lookup(fp_rankings, player_ids, "redraft")
enrich_lookup_with_redraft_values(redraft_lookup, fc_redraft_raw=fc_redraft)

print(f"Players with Dynasty consensus data loaded: {len(dynasty_lookup_sf)}")
print(f"Players with Redraft data loaded: {len(redraft_lookup)}")

# Build pick market value lookups supporting Early, Mid, and Late tiers via 3-Pillar Consensus
picks_lookup_sf = build_consensus_picks_lookup(values_picks, values_players, ktc_raw=ktc_sf, fc_raw=fc_sf, is_superflex=True)
picks_lookup_1qb = build_consensus_picks_lookup(values_picks, values_players, ktc_raw=ktc_1qb, fc_raw=fc_1qb, is_superflex=False)

print(f"Pick market value tiers loaded: {len(picks_lookup_sf)} entries")

# Fetch live NFL State & Weekly Projections for Phase 4 Start/Sit Assistant
nfl_state = get_nfl_state()
active_nfl_season = nfl_state.get("season", "2026")
active_nfl_week = nfl_state.get("week", 1)
weekly_projections = get_weekly_projections(active_nfl_season, active_nfl_week)
print(f"NFL State loaded: Season {active_nfl_season} | Week {active_nfl_week} ({len(weekly_projections)} player projections)")

print()
print("=" * 60)
print("TEAM STATUS & ADD/DROP SUGGESTIONS PER LEAGUE")
print("=" * 60)

for league in leagues:
    league_rosters = get_league_rosters(league["league_id"])
    classification = classify_league(league, league_rosters)

    print()
    print(f"### {classification['name']} ({classification['type']}, {classification['stage']})")

    if classification["stage"] == "pre_draft_no_roster":
        print("Skipped — no roster assigned yet.")
        continue

    user_roster = get_user_roster(league_rosters, user_id)

    if not user_roster or not user_roster.get("players"):
        print("Your roster was not found or has no players yet.")
        continue

    roster_pos = league.get("roster_positions", [])
    starter_counts = get_starter_counts(league)

    all_rosters_players = {
        r["roster_id"]: get_roster_players(r, players)
        for r in league_rosters
        if r.get("players")
    }

    # Detect Superflex
    is_superflex = "SUPER_FLEX" in roster_pos or roster_pos.count("QB") >= 2

    # Detect TE Premium
    scoring = league.get("scoring_settings", {})
    tep_bonus = scoring.get("bonus_rec_te", 0.0) or scoring.get("te_bonus", 0.0)

    if classification["type"] == "redraft":
        is_dynasty = False
        primary_lookup, primary_label = redraft_lookup, "Redraft"
        alt_lookup, alt_label = {}, None

        redraft_ranked = rank_teams_in_league(all_rosters_players, primary_lookup, roster_pos, is_dynasty=False)
        redraft_tier, redraft_pos, redraft_total = get_strength_tier(user_roster["roster_id"], redraft_ranked)

        current_tier, games_played = get_current_strength_tier(
            user_roster, league_rosters, redraft_pos, redraft_total
        )

        status = classify_redraft_team(current_tier)
        category = "win" if current_tier == "high" else ("rebuild" if current_tier == "low" else "neutral")
        print(f"Status: {status} (Redraft strength: #{redraft_pos} of {redraft_total}, {games_played} games played)")

        roster_players = get_roster_players(user_roster, players)
        _, _, _, my_details = calculate_team_strength(roster_players, primary_lookup, roster_pos, is_dynasty=False)
        print(
            f"Roster Value: {my_details['total_market_value']:,.0f} pts "
            f"(Starters: {my_details['starters_market_value']:,.0f} | Bench: {my_details['bench_market_value']:,.0f})"
        )
    else:
        is_dynasty = True
        # Clone dynasty lookup for this league to safely apply league-specific TE Premium
        base_lookup = dynasty_lookup_sf if is_superflex else dynasty_lookup_1qb
        primary_lookup = copy.deepcopy(base_lookup)
        if tep_bonus > 0:
            apply_te_premium(primary_lookup, tep_bonus)
            print(f"  ⚡ TE Premium active (+{tep_bonus} PPR bonus applied to TEs)")

        primary_label = "Dynasty"
        alt_lookup, alt_label = redraft_lookup, "Redraft"
        picks_lookup = picks_lookup_sf if is_superflex else picks_lookup_1qb

        # Rank teams in dynasty based on 70% Starters + 30% Bench Depth
        dynasty_ranked = rank_teams_in_league(all_rosters_players, primary_lookup, roster_pos, is_dynasty=True)
        dynasty_tier, dynasty_pos, dynasty_total = get_strength_tier(user_roster["roster_id"], dynasty_ranked)

        # Calculate Redraft strength for immediate scoring (THIS season's competitiveness)
        redraft_ranked = rank_teams_in_league(all_rosters_players, redraft_lookup, roster_pos, is_dynasty=False)
        redraft_tier, redraft_pos, redraft_total = get_strength_tier(user_roster["roster_id"], redraft_ranked)

        current_tier, games_played = get_current_strength_tier(
            user_roster, league_rosters, redraft_pos, redraft_total
        )

        # Build team tiers for pick projection based on REDRAFT strength
        # (a team's draft position depends on their record THIS season, not long-term dynasty value)
        team_tiers = {}
        for pos_idx, item in enumerate(redraft_ranked, start=1):
            rid = item[0]
            team_tiers[rid] = score_to_tier(percentile_score(pos_idx, len(redraft_ranked)))

        traded_picks = get_traded_picks(league["league_id"])
        picks_ownership = build_picks_ownership(league, traded_picks, future_years=3)
        my_picks = get_picks_for_roster(picks_ownership, user_roster["roster_id"])
        total_rosters = league.get("total_rosters", 12)
        my_picks_points = get_picks_capital_value(my_picks, picks_lookup, team_tiers, target_season="2027", total_rosters=total_rosters)

        picks_ranked = rank_teams_by_picks(picks_ownership, total_rosters, picks_lookup, team_tiers, target_season="2027")
        picks_tier, picks_pos, picks_total = get_strength_tier(user_roster["roster_id"], picks_ranked)

        status, category = classify_dynasty_team(current_tier, dynasty_tier)
        qualifier = get_picks_qualifier(category, picks_tier)

        roster_players = get_roster_players(user_roster, players)
        _, _, _, my_details = calculate_team_strength(roster_players, primary_lookup, roster_pos, is_dynasty=True)

        print(
            f"Status: {status}{qualifier} "
            f"(Dynasty: #{dynasty_pos} of {dynasty_total} — Redraft: #{redraft_pos} of {redraft_total}, {games_played} games played)"
        )
        print(
            f"Roster Value: {my_details['total_market_value']:,.0f} pts "
            f"(Starters: {my_details['starters_market_value']:,.0f} | Bench: {my_details['bench_market_value']:,.0f})"
        )
        print(
            f"Available Picks ({len(my_picks)}, Capital: #{picks_pos} of {picks_total}, {my_picks_points:,.0f} pts): "
            f"{format_picks_summary(my_picks, team_tiers, target_season='2027')}"
        )

    # -------------------------------------------------------------
    # Build Team Profiles for Trades & Simulation
    # -------------------------------------------------------------
    league_users = get_league_users(league["league_id"])
    user_map = {}
    for u in league_users:
        uid = u.get("user_id")
        dname = u.get("display_name", "Unknown")
        tname = (u.get("metadata") or {}).get("team_name")
        label = f"@{dname}" + (f" ({tname})" if tname else "")
        user_map[uid] = label

    all_team_profiles = []
    user_profile = None

    for r in league_rosters:
        rid = r["roster_id"]
        if rid not in all_rosters_players:
            continue
        owner_id = r.get("owner_id")
        manager_label = user_map.get(owner_id, f"Team {rid}")

        if is_dynasty:
            d_tier, _, _ = get_strength_tier(rid, dynasty_ranked)
            r_tier, r_pos, r_tot = get_strength_tier(rid, redraft_ranked)
            c_tier, _ = get_current_strength_tier(r, league_rosters, r_pos, r_tot)
            team_status, team_cat = classify_dynasty_team(c_tier, d_tier)
            owned_picks = get_picks_for_roster(picks_ownership, rid)
        else:
            r_tier, r_pos, r_tot = get_strength_tier(rid, redraft_ranked)
            c_tier, _ = get_current_strength_tier(r, league_rosters, r_pos, r_tot)
            team_status = classify_redraft_team(c_tier)
            team_cat = "win" if c_tier == "high" else ("rebuild" if c_tier == "low" else "neutral")
            owned_picks = []

        prof = analyze_team_profile(
            roster=r,
            roster_players=all_rosters_players[rid],
            owned_picks=owned_picks,
            primary_lookup=primary_lookup,
            redraft_lookup=redraft_lookup,
            picks_lookup=picks_lookup if is_dynasty else {},
            team_tiers=team_tiers if is_dynasty else {},
            roster_positions=roster_pos,
            is_dynasty=is_dynasty,
            status=team_status,
            category=team_cat,
            manager_name=manager_label,
            total_rosters=league.get("total_rosters", 12),
        )
        all_team_profiles.append(prof)
        if rid == user_roster["roster_id"]:
            user_profile = prof

    # -------------------------------------------------------------
    # Monte Carlo Playoff & Power Rankings Simulator (Phase 5)
    # -------------------------------------------------------------
    if args.simulate or args.all:
        playoff_start = league.get("settings", {}).get("playoff_week_start", 15)
        schedule = get_league_schedule(league["league_id"], start_week=active_nfl_week, end_week=playoff_start - 1)
        team_expectations = {
            r["roster_id"]: compute_team_lineup_expectation(
                roster=r,
                roster_players=all_rosters_players[r["roster_id"]],
                weekly_projections=weekly_projections,
                scoring_settings=scoring,
                roster_positions=roster_pos,
            )
            for r in league_rosters
            if r["roster_id"] in all_rosters_players
        }
        sim_results = run_monte_carlo_simulation(
            league=league,
            rosters=league_rosters,
            schedule=schedule,
            team_expectations=team_expectations,
            current_week=active_nfl_week,
            playoff_week_start=playoff_start,
            num_simulations=1000,
        )
        table = format_power_rankings_table(
            sim_results=sim_results,
            user_roster_id=user_roster["roster_id"],
            user_map=user_map,
            rosters=league_rosters,
            team_profiles=all_team_profiles,
        )
        print()
        print(table)

        if is_dynasty:
            dynasty_res = compute_dynasty_power_rankings(all_team_profiles)
            dynasty_table = format_dynasty_power_rankings_table(dynasty_res, user_roster["roster_id"])
            print()
            print(dynasty_table)

    # -------------------------------------------------------------
    # Targeted Trade Finder (Phase 5)
    # -------------------------------------------------------------
    if args.trade_for:
        if user_profile:
            resolved = resolve_asset_from_query(args.trade_for, all_team_profiles, is_dynasty=is_dynasty)
            if not resolved["found"]:
                print(f"\n  🎯 Targeted Acquisition: Could not locate '{args.trade_for}' on any team in this league.")
            else:
                target_asset = resolved["asset"]
                target_owners = resolved["owners"]
                other_owners = [o for o in target_owners if o["profile"]["roster_id"] != user_roster["roster_id"]]
                if not other_owners:
                    print(f"\n  🎯 Targeted Acquisition: You already own the only matching asset ('{target_asset['name']}') in this league!")
                else:
                    primary_owner = other_owners[0]["profile"]
                    targeted_props = find_targeted_buy_trades(
                        target_asset=target_asset,
                        owner_profile=primary_owner,
                        user_profile=user_profile,
                        primary_lookup=primary_lookup,
                        roster_positions=roster_pos,
                        is_dynasty=is_dynasty,
                        max_proposals=3,
                    )
                    print_targeted_trades_summary("buy", target_asset["name"], targeted_props, primary_owner["manager_name"])

    if args.trade_away:
        if user_profile:
            resolved = resolve_asset_from_query(args.trade_away, [user_profile], is_dynasty=is_dynasty)
            if not resolved["found"]:
                print(f"\n  🏷️ Targeted Liquidation: Could not locate '{args.trade_away}' on your roster in this league.")
            else:
                target_asset = resolved["asset"]
                targeted_sell_props = find_targeted_sell_trades(
                    target_asset=target_asset,
                    user_profile=user_profile,
                    other_profiles=all_team_profiles,
                    primary_lookup=primary_lookup,
                    roster_positions=roster_pos,
                    is_dynasty=is_dynasty,
                    max_partners=3,
                )
                print_targeted_trades_summary("sell", target_asset["name"], targeted_sell_props)

    # If user passed targeted trade flags, skip general waivers and generic trades to keep output focused
    if (args.trade_for or args.trade_away) and not args.all:
        continue

    # -------------------------------------------------------------
    # Weekly Start / Sit & Lineup Optimization (Phase 4)
    # -------------------------------------------------------------
    if user_roster.get("starters") and classification["stage"] not in ("pre_draft_no_roster", "pre_draft"):
        roster_players = get_roster_players(user_roster, players)
        scoring_settings = league.get("scoring_settings", {})
        proj_lookup = {}
        for p in roster_players:
            pid = p.get("player_id")
            raw = weekly_projections.get(pid)
            pts = calculate_weekly_projected_points(pid, raw, scoring_settings, p)
            proj_lookup[pid] = pts

        lineup_audit = audit_weekly_lineup(
            user_roster=user_roster,
            roster_players=roster_players,
            projections_lookup=proj_lookup,
            roster_positions=roster_pos,
            player_db=players,
        )

        print(f"  ⚡ Week {active_nfl_week} Lineup Outlook:")
        print(
            f"     Active Lineup Projection: {lineup_audit['active_points_total']:.1f} pts | "
            f"Optimal Lineup Projection: {lineup_audit['optimal_points_total']:.1f} pts"
        )

        if lineup_audit["start_sit_swaps"]:
            print(f"     💡 Start/Sit Recommendations (+{lineup_audit['points_differential']:.1f} pts potential):")
            for swap in lineup_audit["start_sit_swaps"]:
                st_p = swap["start_player"].get("full_name") or swap["start_player"].get("player_id")
                si_p = swap["sit_player"].get("full_name") or swap["sit_player"].get("player_id")
                print(f"        👉 START: {st_p} ({swap['start_proj']:.1f} pts)")
                print(f"           SIT:   {si_p} ({swap['sit_proj']:.1f} pts) in {swap['slot']} (Gain: +{swap['gain']:.1f} pts)")
        else:
            print("     ✅ Your Sleeper starting lineup is 100% optimal for this week!")

        if lineup_audit["injury_alerts"]:
            print("     🚨 Active Starter Injury Risks:")
            for inj in lineup_audit["injury_alerts"]:
                pname = inj["starter"].get("full_name") or inj["starter"].get("player_id")
                status = inj["status"]
                slot = inj["slot"]
                pivot_txt = f"↳ Pivot to: {inj['pivot'][0].get('full_name')} ({inj['pivot'][1]:.1f} pts)" if inj.get("pivot") else "↳ No healthy bench pivot available"
                print(f"        ⚠️ [{status}] {pname} starting in {slot} ({inj['starter_proj']:.1f} pts) | {pivot_txt}")

        # Streaming Recommendations
        if classification["stage"] not in ("drafting", "pre_draft_with_roster"):
            free_agents = get_free_agents(league_rosters, players)
            fa_projs = {}
            for fa in free_agents:
                fpid = fa.get("player_id")
                raw = weekly_projections.get(fpid)
                fa_projs[fpid] = calculate_weekly_projected_points(fpid, raw, scoring_settings, fa)

            combined_projs = {**proj_lookup, **fa_projs}
            streams = find_streaming_recommendations(
                user_roster=user_roster,
                roster_players=roster_players,
                free_agents=free_agents,
                projections_lookup=combined_projs,
                roster_positions=roster_pos,
                primary_lookup=primary_lookup,
                top_n=2,
            )
            if streams:
                print("     🌊 Weekly Streaming Opportunities (Stud Drop Protected):")
                for st in streams:
                    stream_p = st["stream_player"].get("full_name") or st["stream_player"].get("player_id")
                    cur_p = st["current_starter"].get("full_name") or st["current_starter"].get("player_id")
                    drop_p = st["drop_player"].get("full_name") or st["drop_player"].get("player_id")
                    print(f"        ADD {stream_p} ({st['position']} — {st['stream_proj']:.1f} pts) / DROP {drop_p} (Bench | Market: {st['drop_market_val']:,.0f} pts)")
                    print(f"        ↳ Outprojects starter {cur_p} by +{st['projected_gain']:.1f} pts this week")

    # If league is currently drafting or in pre-draft, waivers/free agents are locked
    if classification["stage"] in ("drafting", "pre_draft_with_roster", "pre_draft"):
        print("  🔒 Waivers locked during draft / pre-draft.")
    else:
        roster_players = get_roster_players(user_roster, players)
        free_agents = get_free_agents(league_rosters, players)

        waiver_recs = build_intelligent_waiver_suggestions(
            roster_players=roster_players,
            free_agents=free_agents,
            primary_lookup=primary_lookup,
            roster_positions=roster_pos,
            user_roster=user_roster,
            category=category,
            is_dynasty=is_dynasty,
            alt_lookup=alt_lookup,
        )

        has_any_recs = False
        already_shown_add_ids = set()

        # 1. Starting Lineup Upgrades (Immediate Impact)
        starter_upgrades = waiver_recs["starter_upgrades"]
        if starter_upgrades:
            has_any_recs = True
            print("  ⭐ Starting Lineup Upgrades (Immediate Impact):")
            for s in starter_upgrades:
                tag = s.get("priority_tag", "⭐ STARTER")
                add_txt = format_waiver_player(s["add_player"], s["add_ranking"], alt_lookup, show_sources=is_dynasty)
                drop_txt = format_waiver_player(s["drop_player"], s["drop_ranking"], None, show_sources=False)
                disp_p = s.get("displaced_player")
                disp_name = (disp_p.get("full_name") or disp_p.get("player_id")) if disp_p else "Starting Slot"
                disp_txt = f"{disp_name} ({disp_p.get('position')})" if disp_p else "Starting Slot"
                gain_pts = s.get("market_value_gain", 0.0)
                gain_str = f"+{gain_pts:,.0f} pts" if gain_pts >= 0 else f"{gain_pts:,.0f} pts"
                print(f"    [{tag}] ADD {add_txt}")
                print(f"            DROP {drop_txt}")
                print(f"            ↳ Displaces {disp_txt} in starting lineup (Net gain: {gain_str})")
                already_shown_add_ids.add(s["add_player"].get("player_id"))

        # 2. Top Cross-Positional Bench Moves (Value Upgrades)
        cross_pos = waiver_recs["cross_pos_upgrades"]
        if cross_pos:
            has_any_recs = True
            print("  🔄 Top Cross-Positional Bench Moves (Value Upgrades):")
            for s in cross_pos:
                tag = s.get("priority_tag", "bench upgrade")
                add_txt = format_waiver_player(s["add_player"], s["add_ranking"], alt_lookup, show_sources=is_dynasty)
                drop_txt = format_waiver_player(s["drop_player"], s["drop_ranking"], None, show_sources=False)
                gain_pts = s.get("market_value_gain", 0.0)
                gain_str = f"+{gain_pts:,.0f} pts" if gain_pts >= 0 else f"{gain_pts:,.0f} pts"
                print(f"    [{tag}] ADD {add_txt}")
                print(f"            DROP {drop_txt} (Net gain: {gain_str})")
                already_shown_add_ids.add(s["add_player"].get("player_id"))

        # 3. Taxi Squad Upgrades (Rookie-for-Rookie Stash)
        taxi_swaps = waiver_recs["taxi_swaps"]
        if taxi_swaps:
            has_any_recs = True
            print("  🚕 Taxi Squad Upgrades (Rookie-for-Rookie Stash):")
            for s in taxi_swaps:
                tag = s.get("priority_tag", "🚕 TAXI SWAP")
                add_txt = format_waiver_player(s["add_player"], s["add_ranking"], None, show_sources=False)
                drop_txt = format_waiver_player(s["drop_player"], s["drop_ranking"], None, show_sources=False)
                gain_pts = s.get("market_value_gain", 0.0)
                gain_str = f"+{gain_pts:,.0f} pts" if gain_pts >= 0 else f"{gain_pts:,.0f} pts"
                print(f"    [{tag}] ADD {add_txt}")
                print(f"            DROP {drop_txt} (Net gain: {gain_str})")
                already_shown_add_ids.add(s["add_player"].get("player_id"))

        # 4. Positional Options (Same-Position Swaps)
        pos_options = waiver_recs.get("positional_options", {})
        filtered_pos_options = {}
        for pos in POSITIONS:
            opts = pos_options.get(pos, [])
            unique_opts = [o for o in opts if o["add_player"].get("player_id") not in already_shown_add_ids]
            if unique_opts:
                filtered_pos_options[pos] = unique_opts[:2]

        if filtered_pos_options:
            has_any_recs = True
            print("  📌 Positional Options (Same-Position Swaps):")
            for pos, opts in filtered_pos_options.items():
                print(f"    {pos}:")
                for o in opts:
                    add_txt = format_waiver_player(o["add_player"], o["add_ranking"], None, show_sources=False)
                    drop_txt = format_waiver_player(o["drop_player"], o["drop_ranking"], None, show_sources=False)
                    gain_pts = o.get("market_value_gain", 0.0)
                    gain_str = f"+{gain_pts:,.0f} pts" if gain_pts >= 0 else f"{gain_pts:,.0f} pts"
                    print(f"      ADD {add_txt} / DROP {drop_txt} ({gain_str})")

        if not has_any_recs:
            print("  No high-conviction waiver suggestions found for this roster.")

    # -------------------------------------------------------------
    # General Trade Suggestions (Model 3 Consensus)
    # -------------------------------------------------------------
    if user_profile:
        trade_suggestions = generate_trade_suggestions(
            user_roster_id=user_roster["roster_id"],
            user_profile=user_profile,
            other_profiles=all_team_profiles,
            is_dynasty=is_dynasty,
            primary_lookup=primary_lookup,
            roster_positions=roster_pos,
            max_suggestions=3,
        )

        print()
        if trade_suggestions:
            print("  🤝 Recommended Trade Opportunities (Model 3 Consensus):")
            for i, t in enumerate(trade_suggestions, 1):
                eval_res = t["eval_result"]
                give_str = " + ".join(format_asset_str(a) for a in t["give_assets"])
                recv_str = " + ".join(format_asset_str(a) for a in t["receive_assets"])
                diff_str = f"+{eval_res['net_diff']:,.0f}" if eval_res['net_diff'] >= 0 else f"{eval_res['net_diff']:,.0f}"
                print(f"    {i}. [{t['archetype']} with {t['partner_name']}]")
                print(f"       YOU GIVE: {give_str}")
                print(f"       YOU GET:  {recv_str}")
                print(
                    f"       ↳ Model 3 Effective Value: You {eval_res['eff_give']:,.0f} pts vs Partner {eval_res['eff_receive']:,.0f} pts "
                    f"(Fairness: {eval_res['fairness_ratio']*100:.0f}% | Net diff: {diff_str} pts)"
                )
                print(f"       ↳ Strategic Rationale: {t['why']}")
        else:
            print("  🤝 Trade Opportunities: No high-conviction trades currently identified for this roster.")