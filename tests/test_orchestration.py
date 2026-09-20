"""
Tests for src/orchestration.py, written BEFORE migrating any of the 3 entry
points (app.py, main.py, scripts/weekly_automation.py) onto it - these are
the ground truth the migration is checked against, not a description of
call-site behavior. All synthetic, no live network calls (see the
`orchestration_*` fixtures in conftest.py: a 4-team, 1QB league engineered
so team 1 is the strongest roster and team 4 the weakest).
"""
from unittest import mock

from src.orchestration import build_league_context, build_team_profiles


# ---------------------------------------------------------------------------
# build_league_context
# ---------------------------------------------------------------------------

def test_dynasty_league_flags_and_lookup_selection(orchestration_dynasty_league, orchestration_rosters, orchestration_users, orchestration_market_db):
    context = build_league_context(orchestration_dynasty_league, orchestration_rosters, orchestration_users, orchestration_market_db, active_week=1)

    assert context["is_dynasty"] is True
    assert context["is_superflex"] is False
    assert context["tep_bonus"] == 0.0
    assert context["total_rosters"] == 4
    assert context["primary_lookup"] is not context["redraft_lookup"], "dynasty leagues must value primary assets off the dynasty lookup, not redraft"


def test_redraft_league_redirects_primary_lookup_to_redraft(orchestration_redraft_league, orchestration_rosters, orchestration_users, orchestration_market_db):
    context = build_league_context(orchestration_redraft_league, orchestration_rosters, orchestration_users, orchestration_market_db, active_week=1)

    assert context["is_dynasty"] is False
    assert context["primary_lookup"] is context["redraft_lookup"], "redraft leagues have no dynasty value to price against - primary must redirect to redraft"


def test_standard_scoring_falls_back_to_market_db_redraft_lookup(orchestration_dynasty_league, orchestration_rosters, orchestration_users, orchestration_market_db):
    context = build_league_context(orchestration_dynasty_league, orchestration_rosters, orchestration_users, orchestration_market_db, active_week=1)

    assert context["redraft_lookup"] is orchestration_market_db["redraft_lookup"], (
        "a league matching the standard 0.5 PPR / no-TEP baseline exactly should reuse the shared "
        "redraft_lookup, not recompute one"
    )


def test_nonstandard_scoring_recomputes_a_custom_redraft_lookup(orchestration_full_ppr_league, orchestration_rosters, orchestration_users, orchestration_market_db):
    """
    This is the intentional, approved behavior change this extraction makes
    for main.py/weekly_automation.py: every entry point now recomputes
    redraft_lookup per league's real scoring (PPR, TEP, pass TD, ...) instead
    of reusing one fixed global lookup - previously only app.py did this.
    """
    sentinel_lookup = {"sentinel": True}
    with mock.patch("src.orchestration.compute_custom_redraft_lookup", return_value=sentinel_lookup) as mock_compute:
        context = build_league_context(orchestration_full_ppr_league, orchestration_rosters, orchestration_users, orchestration_market_db, active_week=3)

    assert context["redraft_lookup"] is sentinel_lookup
    assert mock_compute.call_count == 1
    called_market_db, called_scoring_tuple, called_is_superflex, called_week = mock_compute.call_args[0]
    assert called_market_db is orchestration_market_db
    assert dict(called_scoring_tuple)["rec"] == 1.0, "the league's real (non-standard) scoring must reach compute_custom_redraft_lookup"
    assert called_is_superflex is False
    assert called_week == 3


def test_tep_bonus_is_applied_to_the_primary_lookup(orchestration_tep_league, orchestration_rosters, orchestration_users, orchestration_market_db, orchestration_dynasty_lookup):
    context = build_league_context(orchestration_tep_league, orchestration_rosters, orchestration_users, orchestration_market_db, active_week=1)

    assert context["tep_bonus"] == 1.0
    te_pid = "t1_te5"
    before = orchestration_dynasty_lookup[te_pid]["market_value"]
    after = context["primary_lookup"][te_pid]["market_value"]
    assert after > before, "a real TE Premium bonus must raise TE market values in the primary lookup"


def test_all_rosters_players_and_user_map(orchestration_dynasty_league, orchestration_rosters, orchestration_users, orchestration_market_db, orchestration_players_db):
    context = build_league_context(orchestration_dynasty_league, orchestration_rosters, orchestration_users, orchestration_market_db, active_week=1)

    assert set(context["all_rosters_players"].keys()) == {1, 2, 3, 4}
    for team_id in (1, 2, 3, 4):
        roster_players = context["all_rosters_players"][team_id]
        assert len(roster_players) == 10  # 6 skill starters + K + DEF + 2 bench
        assert all(p["player_id"].startswith(f"t{team_id}_") for p in roster_players)

    assert context["user_map"]["user_1"] == "@manager1 (Team 1)"
    assert context["user_map"]["user_4"] == "@manager4 (Team 4)"


def test_picks_ownership_defaults_to_empty_without_traded_picks(orchestration_dynasty_league, orchestration_rosters, orchestration_users, orchestration_market_db):
    context = build_league_context(orchestration_dynasty_league, orchestration_rosters, orchestration_users, orchestration_market_db, active_week=1)
    assert context["picks_ownership"] == {}


# ---------------------------------------------------------------------------
# build_team_profiles
# ---------------------------------------------------------------------------

def _build_context(league, rosters, users, market_db):
    return build_league_context(league, rosters, users, market_db, active_week=1)


def test_dynasty_score_pairs_rank_teams_by_engineered_roster_strength(orchestration_dynasty_league, orchestration_rosters, orchestration_users, orchestration_market_db):
    context = _build_context(orchestration_dynasty_league, orchestration_rosters, orchestration_users, orchestration_market_db)
    result = build_team_profiles(
        context, orchestration_dynasty_league, orchestration_rosters, active_week=1,
        weekly_projections={}, schedule={}, num_simulations=100,
    )

    ranked_roster_ids = [rid for rid, _ in result["dynasty_score_pairs"]]
    assert ranked_roster_ids == [1, 2, 3, 4], (
        "team 1 was engineered to have the highest market_value at every position and team 4 the "
        f"lowest - expected dynasty_score_pairs ranked [1, 2, 3, 4], got {ranked_roster_ids}"
    )


def test_redraft_ranked_also_reflects_engineered_roster_strength(orchestration_dynasty_league, orchestration_rosters, orchestration_users, orchestration_market_db):
    context = _build_context(orchestration_dynasty_league, orchestration_rosters, orchestration_users, orchestration_market_db)
    result = build_team_profiles(
        context, orchestration_dynasty_league, orchestration_rosters, active_week=1,
        weekly_projections={}, schedule={}, num_simulations=100,
    )

    ranked_roster_ids = [rid for rid, _, _ in result["redraft_ranked"]]
    assert ranked_roster_ids == [1, 2, 3, 4]


def test_all_team_profiles_carry_tier_status_and_category_for_every_roster(orchestration_dynasty_league, orchestration_rosters, orchestration_users, orchestration_market_db):
    context = _build_context(orchestration_dynasty_league, orchestration_rosters, orchestration_users, orchestration_market_db)
    result = build_team_profiles(
        context, orchestration_dynasty_league, orchestration_rosters, active_week=1,
        weekly_projections={}, schedule={}, num_simulations=100,
    )

    assert len(result["all_team_profiles"]) == 4
    for prof in result["all_team_profiles"]:
        assert prof["current_tier"] in ("high", "medium", "low")
        assert prof["dynasty_tier"] in ("high", "medium", "low")
        assert prof["status"]
        assert prof["category"] in ("win", "neutral", "rebuild")
        assert "playoff_pct" in prof

    team1_profile = next(p for p in result["all_team_profiles"] if p["roster_id"] == 1)
    team4_profile = next(p for p in result["all_team_profiles"] if p["roster_id"] == 4)
    assert team1_profile["category"] != "rebuild", "the strongest engineered roster should not be classified as a rebuilder"
    assert team4_profile["category"] != "win", "the weakest engineered roster should not be classified as a win-now contender"


def test_redraft_league_skips_dynasty_scoring_and_picks(orchestration_redraft_league, orchestration_rosters, orchestration_users, orchestration_market_db):
    context = _build_context(orchestration_redraft_league, orchestration_rosters, orchestration_users, orchestration_market_db)
    result = build_team_profiles(
        context, orchestration_redraft_league, orchestration_rosters, active_week=1,
        weekly_projections={}, schedule={}, num_simulations=100,
    )

    assert result["dynasty_score_pairs"] == []
    assert result["team_tiers"] == {}
    for prof in result["all_team_profiles"]:
        assert prof["dynasty_tier"] is None
        assert prof["pick_assets"] == []


def test_sim_results_and_rank_map_cover_every_roster(orchestration_dynasty_league, orchestration_rosters, orchestration_users, orchestration_market_db):
    context = _build_context(orchestration_dynasty_league, orchestration_rosters, orchestration_users, orchestration_market_db)
    result = build_team_profiles(
        context, orchestration_dynasty_league, orchestration_rosters, active_week=1,
        weekly_projections={}, schedule={}, num_simulations=100,
    )

    assert set(result["sim_results"].keys()) == {1, 2, 3, 4}
    assert set(result["sim_rank_map"].keys()) == {1, 2, 3, 4}
    ranks = [pos for pos, _ in result["sim_rank_map"].values()]
    assert sorted(ranks) == [1, 2, 3, 4], "every roster should get a distinct Season Power Score rank 1-4"
