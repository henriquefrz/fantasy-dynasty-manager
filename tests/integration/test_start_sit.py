"""
Converted from scratch/test_start_sit.py.

audit_weekly_lineup() and find_streaming_recommendations() both gained a
required `weekly_stats` parameter since this scratch script was written (it
excludes players whose game has already started from start/sit swap and
streaming suggestions - see src/start_sit.py). Fixed here by passing
weekly_stats={}, which preserves this test's original intent: an empty dict
means no player is treated as already-started, i.e. a pure "optimal vs.
static projections" audit, exactly what this test checked before that
parameter existed.

Requires network access; run explicitly with `pytest -m integration`.
"""
import pytest

from src.market_data import (
    build_positional_lookup,
    enrich_lookup_with_consensus_values,
    get_fantasycalc_data_raw,
    get_fp_rankings_raw,
    get_ktc_data_raw,
    get_player_ids_raw,
    get_values_players_raw,
)
from src.sleeper_api import (
    get_free_agents,
    get_league_rosters,
    get_players,
    get_roster_players,
    get_user_roster,
    get_weekly_projections,
)
from src.start_sit import (
    audit_weekly_lineup,
    calculate_weekly_projected_points,
    find_streaming_recommendations,
)

pytestmark = pytest.mark.integration


def test_tep_scoring_calculation_matches_league_settings():
    scoring_tep = {"rec": 1.0, "bonus_rec_te": 0.5, "pass_td": 4.0, "pass_int": -2.0}
    scoring_std = {"rec": 0.0, "bonus_rec_te": 0.0, "pass_td": 4.0, "pass_int": -2.0}
    mock_te_stats = {"rec": 6.0, "rec_yd": 60.0, "rec_td": 0.0, "fum_lost": 0.0}
    te_obj = {"position": "TE", "full_name": "Test TE"}

    std_pts = calculate_weekly_projected_points("mock_te", mock_te_stats, scoring_std, te_obj)
    tep_pts = calculate_weekly_projected_points("mock_te", mock_te_stats, scoring_tep, te_obj)

    assert std_pts == 6.0
    assert tep_pts == 15.0


def test_lineup_audit_and_streaming_protect_bye_week_stud(real_user, real_nfl_state, real_user_leagues):
    season = real_nfl_state["season"]
    week = real_nfl_state.get("week", 1)

    dif = next(l for l in real_user_leagues if "Diferenciados" in l["name"])
    rosters = get_league_rosters(dif["league_id"])
    my_roster = get_user_roster(rosters, real_user["user_id"])
    all_players = get_players()
    my_roster_players = get_roster_players(my_roster, all_players)

    scoring_settings = dif.get("scoring_settings", {})
    roster_pos = dif["roster_positions"]
    raw_projs = get_weekly_projections(season, week)

    proj_lookup = {}
    for p in my_roster_players:
        pid = p.get("player_id")
        raw = raw_projs.get(pid)
        proj_lookup[pid] = calculate_weekly_projected_points(pid, raw, scoring_settings, p)

    audit = audit_weekly_lineup(
        user_roster=my_roster,
        roster_players=my_roster_players,
        projections_lookup=proj_lookup,
        roster_positions=roster_pos,
        player_db=all_players,
        weekly_stats={},
    )
    assert audit["optimal_points_total"] >= audit["active_points_total"], (
        "the optimal lineup can never score less than the active one, by definition"
    )

    fp_rankings = get_fp_rankings_raw()
    player_ids = get_player_ids_raw()
    values_players = get_values_players_raw()
    ktc_sf = get_ktc_data_raw(is_superflex=True)
    fc_sf = get_fantasycalc_data_raw(is_dynasty=True, is_superflex=True)
    dyn_lookup = build_positional_lookup(fp_rankings, player_ids, "dynasty")
    enrich_lookup_with_consensus_values(dyn_lookup, values_players, player_ids, ktc_raw=ktc_sf, fc_raw=fc_sf, is_superflex=True)

    free_agents = get_free_agents(rosters, all_players)
    fa_projs = {
        fa.get("player_id"): calculate_weekly_projected_points(fa.get("player_id"), raw_projs.get(fa.get("player_id")), scoring_settings, fa)
        for fa in free_agents
    }
    all_projs = {**proj_lookup, **fa_projs}

    # Simulate a bye week for a rostered stud: their weekly projection drops
    # to 0.0, which must NOT make find_streaming_recommendations suggest
    # dropping them for a free agent (the "Josh Allen Bye Week" guardrail).
    josh_jacobs = next((p for p in my_roster_players if p.get("full_name") == "Josh Jacobs"), None)
    if josh_jacobs:
        all_projs[josh_jacobs.get("player_id")] = 0.0

    streaming_opps = find_streaming_recommendations(
        user_roster=my_roster,
        roster_players=my_roster_players,
        free_agents=free_agents,
        projections_lookup=all_projs,
        roster_positions=roster_pos,
        primary_lookup=dyn_lookup,
        weekly_stats={},
        top_n=3,
    )
    for opp in streaming_opps:
        assert opp["drop_player"].get("full_name") != "Josh Jacobs", "Josh Jacobs must NOT be dropped despite a simulated 0.0-projection bye week"
