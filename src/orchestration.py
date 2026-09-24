"""
Shared per-league orchestration skeleton, extracted from the ~85%-identical
logic that app.py's League Workspace, main.py's per-league loop, and
scripts/weekly_automation.py's two audit functions each reimplemented
independently. See the session's duplication-mapping investigation for the
concrete bugs this drift already caused (main.py's dynasty_tier formula
falling out of sync with app.py's, Portal vs. Workspace current_tier
double-counting, 8 independent is_superflex_league() implementations, ...).

Two entry points:
- build_league_context: resolves the cheap, always-needed flags and lookups
  (is_dynasty, is_superflex, tep_bonus, primary/redraft/picks lookups,
  all_rosters_players, user_map, picks_ownership). This is all
  scripts/weekly_automation.py's two audit functions ever need.
- build_team_profiles: the more expensive dynasty_tier / current_tier /
  per-team profile machinery that only app.py's League Workspace and
  main.py's full per-league report need on top of build_league_context.

Signature note: the approved extraction plan sketched
build_league_context(league, rosters, market_db, active_week, mode="equal")
and build_team_profiles(context, rosters, active_week) during the read-only
investigation phase. Implementing them for real surfaced two genuine data
dependencies that sketch didn't account for:
  - user_map needs each league's real `users` list (per-league data, not
    global market data, so it can't live inside market_db) - added as an
    explicit `users` param.
  - the global Sleeper player DB (`players`, from get_players()) IS
    league-independent, fetched-once, reused-everywhere data exactly like
    the rest of market_db - so it now lives at market_db["players"]
    instead of becoming a second signature parameter.
  - picks_ownership (needed by both functions, for pick-asset valuation)
    depends on a league's `traded_picks`, which callers already fetch
    per-league - added as an optional `traded_picks` param on
    build_league_context, threaded through its returned context.
  - build_team_profiles' dynasty_tier and current_tier both depend on a
    real Monte Carlo simulation, which itself needs weekly_projections and
    the league's schedule - genuinely per-league, per-week fetched data
    that a pure, testable function cannot reach out and fetch itself -
    added as explicit `weekly_projections` and `schedule` params, plus
    `league` itself (needed for playoff settings and the simulation's
    deterministic seed).
These are additive, not behavior changes: every field the plan asked for is
still returned, unchanged in meaning.
"""
from src.draft_picks import build_picks_ownership, get_picks_for_roster
from src.league_classifier import classify_league, is_superflex_league
from src.market_data import (
    apply_ktc_te_premium,
    apply_valuation_mode,
    compute_custom_redraft_lookup,
    compute_picks_lookup_from_bundle,
)
from src.playoff_simulator import (
    compute_dynasty_power_rankings,
    compute_team_weekly_expectations,
    run_monte_carlo_simulation,
)
from src.sleeper_api import get_roster_players
from src.team_strength import (
    classify_dynasty_team,
    classify_redraft_team,
    get_current_strength_tier,
    get_strength_tier,
    rank_teams_in_league,
)
from src.trade_engine import analyze_team_profile


def build_league_context(league, rosters, users, market_db, active_week, mode="equal", traded_picks=None, draft_type="linear"):
    """
    Resolves the per-league flags and valuation lookups every entry point
    needs, regardless of how much further analysis it runs on top:
    is_dynasty, is_superflex, tep_bonus, primary_lookup, redraft_lookup,
    picks_lookup, all_rosters_players, user_map, picks_ownership,
    target_season, draft_type.

    market_db is the global, fetched-once-per-run bundle every league reuses
    (dynasty_sf_lookup, dynasty_1qb_lookup, ktc_sf, ktc_1qb, player_ids,
    fp_ros_rankings, ros_projections_raw, ktc_redraft_sf, ktc_redraft_1qb,
    redraft_lookup, picks_bundle_sf, picks_bundle_1qb, players - the shape
    app.py's fetch_market_database already builds).

    draft_type ("linear" or "snake") is the league's rookie-draft order
    convention - callers fetch it once per league (src.sleeper_api's
    get_league_draft_type) alongside traded_picks, since it's live Sleeper
    data this function can't reach out and fetch itself. Only matters for
    pick-asset valuation (build_team_profiles); defaults to "linear", the
    standard dynasty rookie-draft convention.
    """
    ltype = classify_league(league, rosters)
    is_dynasty = ltype.get("type") != "redraft"
    roster_pos = league.get("roster_positions", [])
    is_superflex = is_superflex_league(roster_pos)
    total_rosters = league.get("total_rosters", len(rosters))
    target_season = str(int(league["season"]) + 1)

    scoring = league.get("scoring_settings", {})
    tep_bonus = (
        scoring.get("bonus_rec_te", 0.0)
        or scoring.get("te_bonus", 0.0)
        or league.get("settings", {}).get("tep_bonus", 0.0)
    )

    raw_primary_lookup = market_db["dynasty_sf_lookup"] if is_superflex else market_db["dynasty_1qb_lookup"]
    primary_lookup = apply_valuation_mode(raw_primary_lookup, mode=mode)
    if tep_bonus > 0:
        primary_ktc_raw = market_db["ktc_sf"] if is_superflex else market_db["ktc_1qb"]
        primary_lookup = apply_ktc_te_premium(
            primary_lookup, tep_bonus, primary_ktc_raw, market_db["player_ids"], is_superflex=is_superflex, mode=mode
        )

    # Recompute the redraft/ROS lookup against THIS league's exact scoring
    # (PPR, TEP, pass TD, ...) instead of one fixed global redraft_lookup -
    # see compute_custom_redraft_lookup's docstring.
    scoring_tuple = tuple(sorted((k, float(v)) for k, v in scoring.items() if isinstance(v, (int, float))))
    redraft_lookup = compute_custom_redraft_lookup(market_db, scoring_tuple, is_superflex, active_week)

    picks_bundle = market_db["picks_bundle_sf"] if is_superflex else market_db["picks_bundle_1qb"]
    picks_lookup = compute_picks_lookup_from_bundle(picks_bundle, mode=mode)
    # Single-source picks lookups (same bundle, no new data fetched) - give
    # pick assets the same ktc_val/fc_val/dp_val breakdown player assets
    # already carry, instead of only the blended market_value. Needed for
    # the Trade Center's "Raw Value Comparison by Source" table and the KTC
    # Official Calculator card to see a pick at all (see make_pick_asset).
    ktc_picks_lookup = compute_picks_lookup_from_bundle(picks_bundle, mode="ktc")
    fc_picks_lookup = compute_picks_lookup_from_bundle(picks_bundle, mode="fc")
    dp_picks_lookup = compute_picks_lookup_from_bundle(picks_bundle, mode="dp")

    if not is_dynasty:
        primary_lookup = redraft_lookup

    players = market_db["players"]
    all_rosters_players = {
        r["roster_id"]: get_roster_players(r, players)
        for r in rosters
        if r.get("players")
    }

    user_map = {}
    for u in users:
        uid = u.get("user_id")
        dname = u.get("display_name", "Unknown")
        tname = (u.get("metadata") or {}).get("team_name")
        label = f"@{dname}" + (f" ({tname})" if tname else "")
        user_map[uid] = label

    picks_ownership = build_picks_ownership(league, traded_picks or []) if is_dynasty and traded_picks is not None else {}

    return {
        "is_dynasty": is_dynasty,
        "is_superflex": is_superflex,
        "tep_bonus": tep_bonus,
        "total_rosters": total_rosters,
        "roster_positions": roster_pos,
        "primary_lookup": primary_lookup,
        "redraft_lookup": redraft_lookup,
        "picks_lookup": picks_lookup,
        "ktc_picks_lookup": ktc_picks_lookup,
        "fc_picks_lookup": fc_picks_lookup,
        "dp_picks_lookup": dp_picks_lookup,
        "all_rosters_players": all_rosters_players,
        "user_map": user_map,
        "picks_ownership": picks_ownership,
        "target_season": target_season,
        "draft_type": draft_type,
    }


def build_team_profiles(context, league, rosters, active_week, weekly_projections_by_week, schedule, num_simulations=1000):
    """
    Builds the dynasty_tier / current_tier / per-team profile layer on top of
    a build_league_context() result: dynasty_score_pairs, redraft_ranked,
    sim_results/sim_rank_map, and all_team_profiles (each entry carrying
    current_tier, dynasty_tier, status, and category alongside the usual
    analyze_team_profile asset breakdown).

    weekly_projections_by_week is {week: {player_id: projection}} - see
    src.sleeper_api.get_weekly_projections_by_week - covering active_week
    through at least the league's playoff_week_start, so the Monte Carlo
    simulation can project each remaining week (and the playoffs) from
    that week's own real Sleeper data instead of reusing active_week's
    snapshot for the whole season (see run_monte_carlo_simulation's
    team_week_expectations docstring for why that flattening was wrong).

    Pick-asset valuation is driven entirely by sim_rank_map (each roster's
    Monte Carlo Season Power Score standing), which is available before any
    profile is built - unlike the old team_tiers/current_tier signal it
    replaced, it has zero dependency on dynasty_score_pairs or on
    all_team_profiles. That's what lets every roster's full profile
    (starters/bench/picks) be built in a SINGLE pass below: dynasty_tier
    still needs a full-league dynasty_score_pairs ranking (itself built from
    these same profiles) to classify status/category, but that no longer
    requires rebuilding the asset values themselves a second time with a
    different pick-tier input - the earlier two-pass shape (a "prepass"
    with team_tiers={} feeding dynasty_score_pairs, then a "final" pass with
    real team_tiers) was the root cause of the Portal-vs-Workspace dynasty
    rank divergence this consolidation fixes: two passes computing pick
    values two different ways could - and did - disagree.
    """
    is_dynasty = context["is_dynasty"]
    roster_pos = context["roster_positions"]
    all_rosters_players = context["all_rosters_players"]
    primary_lookup = context["primary_lookup"]
    redraft_lookup = context["redraft_lookup"]
    picks_lookup = context["picks_lookup"]
    ktc_picks_lookup = context.get("ktc_picks_lookup", {})
    fc_picks_lookup = context.get("fc_picks_lookup", {})
    dp_picks_lookup = context.get("dp_picks_lookup", {})
    picks_ownership = context["picks_ownership"]
    user_map = context["user_map"]
    total_rosters = context["total_rosters"]
    target_season = context.get("target_season") or str(int(league["season"]) + 1)
    draft_type = context.get("draft_type", "linear")

    playoff_start = league.get("settings", {}).get("playoff_week_start", 15)
    team_week_expectations = {
        r["roster_id"]: compute_team_weekly_expectations(
            roster=r,
            roster_players=all_rosters_players[r["roster_id"]],
            weekly_projections_by_week=weekly_projections_by_week,
            scoring_settings=league.get("scoring_settings", {}),
            roster_positions=roster_pos,
        )
        for r in rosters
        if r["roster_id"] in all_rosters_players
    }
    sim_results = run_monte_carlo_simulation(
        league=league,
        rosters=rosters,
        schedule=schedule,
        team_week_expectations=team_week_expectations,
        current_week=active_week,
        playoff_week_start=playoff_start,
        num_simulations=num_simulations,
    )
    ranked_by_power_score = sorted(sim_results, key=lambda rid: sim_results[rid].get("power_score", 0.0), reverse=True)
    sim_rank_map = {rid: (idx, sim_results[rid].get("power_score", 0.0)) for idx, rid in enumerate(ranked_by_power_score, 1)}

    redraft_ranked = rank_teams_in_league(all_rosters_players, redraft_lookup, roster_pos, is_dynasty=False)

    def _current_tier_for(r):
        rid = r["roster_id"]
        r_sim = sim_results.get(rid, {})
        _, r_pos, r_tot = get_strength_tier(rid, redraft_ranked)
        r_sps_pos = sim_rank_map.get(rid, (r_pos, 0.0))[0]
        return get_current_strength_tier(
            r, r_sps_pos, r_tot or len(rosters),
            playoff_pct=r_sim.get("playoff_pct"),
            is_eliminated=r_sim.get("is_eliminated", False),
        )

    # current_tier has zero dependency on dynasty_score_pairs/all_team_profiles
    # (only sim_results/redraft_ranked/roster settings), so it's safe and
    # cheap to resolve for every roster up front.
    current_tiers = {}
    games_played_map = {}
    for r in rosters:
        rid = r["roster_id"]
        if rid not in all_rosters_players:
            continue
        c_tier, games_played = _current_tier_for(r)
        current_tiers[rid] = c_tier
        games_played_map[rid] = games_played

    all_team_profiles = []
    for r in rosters:
        rid = r["roster_id"]
        if rid not in all_rosters_players:
            continue

        if is_dynasty:
            # status/category need dynasty_tier, which needs a full-league
            # dynasty_score_pairs ranking built from these same profiles -
            # placeholder here, overwritten in place once that ranking
            # exists below (asset values themselves don't need it).
            status, category = "Unknown", "neutral"
            owned_picks = get_picks_for_roster(picks_ownership, rid)
        else:
            c_tier = current_tiers[rid]
            status = classify_redraft_team(c_tier)
            category = "win" if c_tier == "high" else ("rebuild" if c_tier == "low" else "neutral")
            owned_picks = []

        prof = analyze_team_profile(
            roster=r,
            roster_players=all_rosters_players[rid],
            owned_picks=owned_picks,
            primary_lookup=primary_lookup,
            redraft_lookup=redraft_lookup,
            picks_lookup=picks_lookup if is_dynasty else {},
            sim_rank_map=sim_rank_map if is_dynasty else {},
            roster_positions=roster_pos,
            is_dynasty=is_dynasty,
            status=status,
            category=category,
            manager_name=user_map.get(r.get("owner_id"), f"Team {rid}"),
            total_rosters=total_rosters,
            target_season=target_season,
            draft_type=draft_type,
            ktc_picks_lookup=ktc_picks_lookup if is_dynasty else {},
            fc_picks_lookup=fc_picks_lookup if is_dynasty else {},
            dp_picks_lookup=dp_picks_lookup if is_dynasty else {},
        )
        prof["current_tier"] = current_tiers[rid]
        prof["dynasty_tier"] = None
        prof["games_played"] = games_played_map[rid]
        prof["playoff_pct"] = sim_results.get(rid, {}).get("playoff_pct")
        prof["is_eliminated"] = sim_results.get(rid, {}).get("is_eliminated", False)

        all_team_profiles.append(prof)

    dynasty_score_pairs = []
    if is_dynasty:
        dynasty_results = compute_dynasty_power_rankings(all_team_profiles)
        ranked_dynasty = sorted(dynasty_results.values(), key=lambda x: x["dynasty_score"], reverse=True)
        dynasty_score_pairs = [(d["roster_id"], d["dynasty_score"]) for d in ranked_dynasty]

        for prof in all_team_profiles:
            rid = prof["roster_id"]
            d_tier, d_pos, _ = get_strength_tier(rid, dynasty_score_pairs)
            status, category = classify_dynasty_team(current_tiers[rid], d_tier)
            prof["status"] = status
            prof["category"] = category
            prof["dynasty_tier"] = d_tier
            prof["dynasty_rank"] = d_pos
            prof["dynasty_score"] = dynasty_results.get(rid, {}).get("dynasty_score")

    return {
        "sim_results": sim_results,
        "sim_rank_map": sim_rank_map,
        "dynasty_score_pairs": dynasty_score_pairs,
        "redraft_ranked": redraft_ranked,
        "all_team_profiles": all_team_profiles,
    }
