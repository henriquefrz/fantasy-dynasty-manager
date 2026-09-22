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
from src.team_strength import get_strength_tier

# Empty per-player projections for every simulated week (not one empty
# dict at the top level - that would leave every roster with zero weeks
# of data and skip every matchup entirely). Each week still exercises
# compute_team_weekly_expectations' own "no data -> 105.0 fallback" path,
# uniformly for every roster/week, same effective behavior the old
# single-week weekly_projections={} produced.
EMPTY_WEEKLY_PROJECTIONS_BY_WEEK = {w: {} for w in range(1, 19)}


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
        weekly_projections_by_week=EMPTY_WEEKLY_PROJECTIONS_BY_WEEK, schedule={}, num_simulations=100,
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
        weekly_projections_by_week=EMPTY_WEEKLY_PROJECTIONS_BY_WEEK, schedule={}, num_simulations=100,
    )

    ranked_roster_ids = [rid for rid, _, _ in result["redraft_ranked"]]
    assert ranked_roster_ids == [1, 2, 3, 4]


def test_portal_card_extraction_never_degrades_to_zeroed_fallback(orchestration_dynasty_league, orchestration_rosters, orchestration_users, orchestration_market_db):
    """
    Regression test for a real production incident: app.py's
    evaluate_league_quick_status (the Portal grid's per-league card) pulls
    dynasty_pos/dynasty_total/r_pos/status out of build_team_profiles'
    result using this exact extraction - get_strength_tier(my_rid,
    dynasty_score_pairs), sim_rank_map.get(my_rid, ...), profile["status"].
    A renamed dict key or field there doesn't raise where anyone would
    notice: it's a KeyError/AttributeError caught by
    evaluate_league_quick_status's bare except, which silently degrades
    EVERY Portal card to Record 0-0 / Points 0.0 / Dynasty #0/N / Season
    #0/N with no error surfaced anywhere (that except now logs a traceback
    - see app.py - but this test catches the underlying breakage in CI
    before it ever reaches that except in production). Pins the exact
    extraction shape so a rename fails loudly here instead.
    """
    context = _build_context(orchestration_dynasty_league, orchestration_rosters, orchestration_users, orchestration_market_db)
    profiles = build_team_profiles(
        context, orchestration_dynasty_league, orchestration_rosters, active_week=1,
        weekly_projections_by_week=EMPTY_WEEKLY_PROJECTIONS_BY_WEEK, schedule={}, num_simulations=100,
    )

    my_rid = 1
    my_profile = next(p for p in profiles["all_team_profiles"] if p["roster_id"] == my_rid)

    _, redraft_pos, redraft_total = get_strength_tier(my_rid, profiles["redraft_ranked"])
    r_pos = profiles["sim_rank_map"].get(my_rid, (redraft_pos, 0.0))[0]
    _, dynasty_pos, dynasty_total = get_strength_tier(my_rid, profiles["dynasty_score_pairs"])
    p_count = len(next(r for r in orchestration_rosters if r["roster_id"] == my_rid).get("players") or [])

    assert my_profile["status"] and my_profile["status"] != "Unknown", (
        "status must be overwritten with the real dynasty classification, never leak the internal placeholder"
    )
    assert p_count > 0, "roster player count must reflect the real roster, not an empty/degraded fallback"
    assert dynasty_pos not in (0, None) and dynasty_total not in (0, None), "dynasty rank must never silently degrade to #0/0"
    assert r_pos not in (0, None), "season power score rank must never silently degrade to #0"


def test_all_team_profiles_carry_tier_status_and_category_for_every_roster(orchestration_dynasty_league, orchestration_rosters, orchestration_users, orchestration_market_db):
    context = _build_context(orchestration_dynasty_league, orchestration_rosters, orchestration_users, orchestration_market_db)
    result = build_team_profiles(
        context, orchestration_dynasty_league, orchestration_rosters, active_week=1,
        weekly_projections_by_week=EMPTY_WEEKLY_PROJECTIONS_BY_WEEK, schedule={}, num_simulations=100,
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
        weekly_projections_by_week=EMPTY_WEEKLY_PROJECTIONS_BY_WEEK, schedule={}, num_simulations=100,
    )

    assert result["dynasty_score_pairs"] == []
    for prof in result["all_team_profiles"]:
        assert prof["dynasty_tier"] is None
        assert prof["pick_assets"] == []


def test_sim_results_and_rank_map_cover_every_roster(orchestration_dynasty_league, orchestration_rosters, orchestration_users, orchestration_market_db):
    context = _build_context(orchestration_dynasty_league, orchestration_rosters, orchestration_users, orchestration_market_db)
    result = build_team_profiles(
        context, orchestration_dynasty_league, orchestration_rosters, active_week=1,
        weekly_projections_by_week=EMPTY_WEEKLY_PROJECTIONS_BY_WEEK, schedule={}, num_simulations=100,
    )

    assert set(result["sim_results"].keys()) == {1, 2, 3, 4}
    assert set(result["sim_rank_map"].keys()) == {1, 2, 3, 4}
    ranks = [pos for pos, _ in result["sim_rank_map"].values()]
    assert sorted(ranks) == [1, 2, 3, 4], "every roster should get a distinct Season Power Score rank 1-4"


# ---------------------------------------------------------------------------
# Concurrency safety - written BEFORE migrating evaluate_league_quick_status /
# _build_league_card_html / fetch_portfolio_exposure onto build_league_context
# / build_team_profiles, since all 3 call sites run inside a
# ThreadPoolExecutor (one call per league, in parallel) and share the SAME
# market_db object across every thread. This is the same bug class as the
# apply_ktc_te_premium/apply_valuation_mode shared-mutation bug fixed earlier
# this session (see test_market_data.py) - hammer it with many threads and
# many distinct league configurations racing on one shared market_db, not a
# single sequential pass.
# ---------------------------------------------------------------------------

def test_concurrent_build_league_context_no_cross_contamination(
    orchestration_market_db, orchestration_rosters, orchestration_users,
    orchestration_dynasty_league, orchestration_tep_league, orchestration_full_ppr_league, orchestration_redraft_league,
):
    import concurrent.futures
    import copy

    market_db = orchestration_market_db
    market_db_snapshot = copy.deepcopy(market_db)

    # orchestration_dynasty_league and orchestration_redraft_league both use
    # standard baseline scoring, so compute_custom_redraft_lookup's fast path
    # returns market_db["redraft_lookup"] - the literal SAME object reference
    # - to both of them. That is exactly the scenario that would surface a
    # shared-mutation bug: two "leagues" on different threads holding the
    # identical dict object.
    leagues_by_label = {
        "dynasty_standard": orchestration_dynasty_league,
        "dynasty_tep": orchestration_tep_league,
        "dynasty_full_ppr": orchestration_full_ppr_league,
        "redraft_standard": orchestration_redraft_league,
    }

    def compute(label):
        league = leagues_by_label[label]
        context = build_league_context(league, orchestration_rosters, orchestration_users, market_db, active_week=1)
        return {
            "is_dynasty": context["is_dynasty"],
            "is_superflex": context["is_superflex"],
            "tep_bonus": context["tep_bonus"],
            "primary_values": {pid: p.get("market_value") for pid, p in context["primary_lookup"].items()},
            "redraft_values": {pid: p.get("market_value") for pid, p in context["redraft_lookup"].items()},
        }

    expected_by_label = {label: compute(label) for label in leagues_by_label}

    jobs = list(leagues_by_label.keys()) * 30  # 120 concurrent calls, 4 distinct configs racing on one market_db
    mismatches = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        future_to_label = {executor.submit(compute, label): label for label in jobs}
        for future in concurrent.futures.as_completed(future_to_label):
            label = future_to_label[future]
            result = future.result()
            if result != expected_by_label[label]:
                mismatches.append(label)

    assert not mismatches, f"cross-contamination detected across {len(mismatches)} concurrent build_league_context calls: {mismatches[:5]}"
    assert market_db == market_db_snapshot, "shared market_db was mutated by concurrent build_league_context calls"


def test_concurrent_build_team_profiles_no_cross_contamination(
    orchestration_market_db, orchestration_rosters, orchestration_users,
    orchestration_dynasty_league, orchestration_redraft_league,
):
    """
    Only checks the value-derived fields (dynasty_score_pairs, redraft_ranked)
    for exact cross-thread reproducibility - these depend solely on
    primary_lookup/redraft_lookup/picks_lookup market values, never on the
    Monte Carlo simulation. sim_results/current_tier/status are intentionally
    NOT compared for exact equality here: run_monte_carlo_simulation seeds
    and reads Python's global `random` module state (random.seed +
    random.gauss), which is a second, pre-existing, unrelated concurrency
    issue - concurrent leagues racing on that shared global RNG state produce
    non-deterministic (but not corrupted or crashing) simulation outputs
    regardless of build_team_profiles. That is a bug in
    run_monte_carlo_simulation itself (src/playoff_simulator.py), not a
    shared-mutation bug in the orchestration layer, and is out of scope for
    this migration - flagged separately.
    """
    import concurrent.futures
    import copy

    market_db = orchestration_market_db
    market_db_snapshot = copy.deepcopy(market_db)

    leagues_by_label = {
        "dynasty": orchestration_dynasty_league,
        "redraft": orchestration_redraft_league,
    }
    contexts_by_label = {
        label: build_league_context(league, orchestration_rosters, orchestration_users, market_db, active_week=1)
        for label, league in leagues_by_label.items()
    }

    def compute(label):
        league = leagues_by_label[label]
        context = contexts_by_label[label]
        result = build_team_profiles(
            context, league, orchestration_rosters, active_week=1,
            weekly_projections_by_week=EMPTY_WEEKLY_PROJECTIONS_BY_WEEK, schedule={}, num_simulations=50,
        )
        return {
            "dynasty_score_pairs": result["dynasty_score_pairs"],
            "redraft_ranked": result["redraft_ranked"],
        }

    expected_by_label = {label: compute(label) for label in leagues_by_label}

    jobs = list(leagues_by_label.keys()) * 25  # 50 concurrent calls
    mismatches = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        future_to_label = {executor.submit(compute, label): label for label in jobs}
        for future in concurrent.futures.as_completed(future_to_label):
            label = future_to_label[future]
            result = future.result()
            if result != expected_by_label[label]:
                mismatches.append(label)

    assert not mismatches, f"cross-contamination detected across {len(mismatches)} concurrent build_team_profiles calls: {mismatches[:5]}"
    assert market_db == market_db_snapshot, "shared market_db was mutated by concurrent build_team_profiles calls"
