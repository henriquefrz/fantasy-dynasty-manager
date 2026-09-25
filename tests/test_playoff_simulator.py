"""
Converted from scratch/test_real_finalist_pct.py.

Verifies the real finalist_pct/champ_pct counters in
run_monte_carlo_simulation: before this fix, the UI's "Finalist / Top 2"
stat was fabricated as playoff_prob * 0.68 with no relation to the actual
bracket simulation. Uses a small synthetic league instead of a real one -
run_monte_carlo_simulation falls back to a generated round-robin schedule
whenever `schedule` doesn't cover the requested weeks, so an empty dict is
enough to drive a full simulation deterministically.
"""
import concurrent.futures

import pytest

from src.playoff_simulator import run_monte_carlo_simulation, run_historical_simulation_snapshot

NUM_TEAMS = 8
NUM_SIMULATIONS = 300


def _make_roster(roster_id):
    return {
        "roster_id": roster_id,
        "owner_id": f"owner_{roster_id}",
        "settings": {"wins": 0, "losses": 0, "ties": 0, "fpts": 0, "fpts_decimal": 0},
    }


def _broadcast_weekly_expectations(flat_expectations, weeks=range(1, 19)):
    """Same constant expectation for every simulated week - synthetic tests here care about
    bracket/simulation mechanics, not week-to-week projection variance."""
    return {rid: {w: exp for w in weeks} for rid, exp in flat_expectations.items()}


@pytest.fixture
def synthetic_league():
    rosters = [_make_roster(rid) for rid in range(1, NUM_TEAMS + 1)]
    league = {
        "league_id": "synthetic_test_league",
        "settings": {"playoff_teams": 6, "playoff_week_start": 15},
    }
    # Spread out expected points so teams are meaningfully distinguishable.
    team_expectations = {
        rid: {"expected_pts": 80.0 + rid * 4.0, "std_dev": 15.0, "bench_depth_pts": 20.0}
        for rid in range(1, NUM_TEAMS + 1)
    }
    return league, rosters, team_expectations


def test_champion_finalist_and_playoff_percentages_respect_subset_relationship(synthetic_league):
    league, rosters, team_expectations = synthetic_league

    sim_results = run_monte_carlo_simulation(
        league=league,
        rosters=rosters,
        schedule={},
        team_week_expectations=_broadcast_weekly_expectations(team_expectations),
        current_week=1,
        playoff_week_start=15,
        num_simulations=NUM_SIMULATIONS,
    )

    assert len(sim_results) == NUM_TEAMS
    for rid, stats in sim_results.items():
        champ_pct = stats["champ_pct"]
        finalist_pct = stats["finalist_pct"]
        playoff_pct = stats["playoff_pct"]

        assert champ_pct <= finalist_pct, (
            f"roster {rid}: champ_pct ({champ_pct}) exceeds finalist_pct ({finalist_pct}) - "
            "every champion must have been a finalist"
        )
        assert finalist_pct <= playoff_pct, (
            f"roster {rid}: finalist_pct ({finalist_pct}) exceeds playoff_pct ({playoff_pct}) - "
            "every finalist must have made the playoffs"
        )


def _run_league(league_id, num_teams=NUM_TEAMS, num_simulations=200):
    rosters = [_make_roster(rid) for rid in range(1, num_teams + 1)]
    league = {"league_id": league_id, "settings": {"playoff_teams": 6, "playoff_week_start": 15}}
    team_expectations = {
        rid: {"expected_pts": 80.0 + rid * 4.0, "std_dev": 15.0, "bench_depth_pts": 20.0}
        for rid in range(1, num_teams + 1)
    }
    result = run_monte_carlo_simulation(
        league=league, rosters=rosters, schedule={}, team_week_expectations=_broadcast_weekly_expectations(team_expectations),
        current_week=1, playoff_week_start=15, num_simulations=num_simulations,
    )
    return {rid: result[rid]["playoff_pct"] for rid in range(1, num_teams + 1)}


def test_same_league_id_and_week_is_deterministic_when_run_sequentially():
    """
    The "Deterministic simulation seed derived from hash(league_id) + week"
    docstring's whole point is that the same league_id+week always simulates
    the same way (no UI rerun jitter) - pins that contract down directly.
    """
    first = _run_league("determinism_check_league")
    second = _run_league("determinism_check_league")
    assert first == second


def test_concurrent_leagues_do_not_contaminate_each_others_random_sequence():
    """
    run_monte_carlo_simulation used to seed Python's GLOBAL random module
    state (random.seed() + random.gauss()) instead of a private
    random.Random instance. That is a real, process-wide shared object: one
    thread's random.seed() call could land in the middle of another thread's
    sequence of random.gauss() draws whenever multiple leagues' simulations
    ran concurrently (e.g. the Portal grid's ThreadPoolExecutor, one call per
    league), silently breaking the "same league_id+week always simulates the
    same way" guarantee - confirmed empirically before the fix: running one
    target league alongside 30 others in a real ThreadPoolExecutor produced
    a result different from the isolated/sequential baseline in 20 of 20
    trials. Rerunning that same experiment here must now match every time.
    """
    target_league_id = "concurrency_check_target_league"
    baseline = _run_league(target_league_id)

    other_league_ids = [f"concurrency_check_other_{i}" for i in range(30)]
    mismatches = 0
    trials = 5
    for _ in range(trials):
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
            futures = {executor.submit(_run_league, lid): lid for lid in other_league_ids + [target_league_id]}
            results = {futures[f]: f.result() for f in concurrent.futures.as_completed(futures)}
        if results[target_league_id] != baseline:
            mismatches += 1

    assert mismatches == 0, f"target league's result diverged from its sequential baseline in {mismatches}/{trials} concurrent trials"


# ---------------------------------------------------------------------------
# "Phantom divisions": a roster's settings.division field can survive after
# a commissioner turns divisions OFF (league.settings.divisions set to 0 or
# removed) - Sleeper doesn't clear it. divisions_by_roster used to trust
# that residual field unconditionally, so a league with divisions off but
# 2+ distinct stale division numbers on its rosters still got divisional
# playoff seeding. Confirmed on 3 real leagues (Matt Ryan's League, Liga do
# Inguinho, Dinastia do Pão de Queijo) that this actually reordered seeds.
# Fixed to only build divisions_by_roster from the real field when
# league.settings.divisions > 0.
# ---------------------------------------------------------------------------

def test_phantom_residual_division_field_ignored_when_divisions_setting_is_off():
    """
    Same league_id (-> identical deterministic RNG seed), same schedule
    fallback, same per-team expectations - the ONLY difference between the
    two roster lists is a residual settings.division field. If it's
    correctly ignored (league.settings.divisions=0), both runs must
    simulate identically; before the fix, the residual 1/1/1/1/2/2/2/2
    split would have triggered divisional seeding and diverged the results.
    """
    league = {
        "league_id": "phantom_division_test_league",
        "settings": {"playoff_teams": 6, "playoff_week_start": 15, "divisions": 0},
    }
    team_expectations = {
        rid: {"expected_pts": 80.0 + rid * 4.0, "std_dev": 15.0, "bench_depth_pts": 20.0}
        for rid in range(1, NUM_TEAMS + 1)
    }
    flat_exp = _broadcast_weekly_expectations(team_expectations)

    rosters_with_stale_division = []
    for rid in range(1, NUM_TEAMS + 1):
        r = _make_roster(rid)
        r["settings"]["division"] = 1 if rid <= NUM_TEAMS // 2 else 2
        rosters_with_stale_division.append(r)

    rosters_without_division_field = [_make_roster(rid) for rid in range(1, NUM_TEAMS + 1)]

    with_residual = run_monte_carlo_simulation(
        league=league, rosters=rosters_with_stale_division, schedule={},
        team_week_expectations=flat_exp, current_week=1, playoff_week_start=15, num_simulations=NUM_SIMULATIONS,
    )
    without_field = run_monte_carlo_simulation(
        league=league, rosters=rosters_without_division_field, schedule={},
        team_week_expectations=flat_exp, current_week=1, playoff_week_start=15, num_simulations=NUM_SIMULATIONS,
    )

    for rid in range(1, NUM_TEAMS + 1):
        assert with_residual[rid]["playoff_pct"] == without_field[rid]["playoff_pct"], (
            f"roster {rid}: a stale settings.division field must not change simulated outcomes "
            f"when league.settings.divisions is off"
        )
        assert with_residual[rid]["champ_pct"] == without_field[rid]["champ_pct"]


def test_genuinely_configured_divisions_still_apply():
    """
    The flip side: when league.settings.divisions is actually > 0, the
    residual field must still drive real divisional seeding - the fix must
    not have thrown out the working case along with the phantom one.
    """
    # Same league_id in both calls -> identical deterministic RNG seed, so
    # any difference in outcome is attributable ONLY to the divisions
    # setting, not to an incidentally different random sequence.
    shared_league_id = "genuine_division_test_league"
    league_no_divisions = {
        "league_id": shared_league_id,
        "settings": {"playoff_teams": 6, "playoff_week_start": 15, "divisions": 0},
    }
    league_with_divisions = {
        "league_id": shared_league_id,
        "settings": {"playoff_teams": 6, "playoff_week_start": 15, "divisions": 2},
    }
    team_expectations = {
        rid: {"expected_pts": 80.0 + rid * 4.0, "std_dev": 15.0, "bench_depth_pts": 20.0}
        for rid in range(1, NUM_TEAMS + 1)
    }
    flat_exp = _broadcast_weekly_expectations(team_expectations)

    rosters = []
    for rid in range(1, NUM_TEAMS + 1):
        r = _make_roster(rid)
        r["settings"]["division"] = 1 if rid <= NUM_TEAMS // 2 else 2
        rosters.append(r)

    off_result = run_monte_carlo_simulation(
        league=league_no_divisions, rosters=rosters, schedule={},
        team_week_expectations=flat_exp, current_week=1, playoff_week_start=15, num_simulations=NUM_SIMULATIONS,
    )
    on_result = run_monte_carlo_simulation(
        league=league_with_divisions, rosters=rosters, schedule={},
        team_week_expectations=flat_exp, current_week=1, playoff_week_start=15, num_simulations=NUM_SIMULATIONS,
    )

    # Divisional vs flat seeding usually still sends the same 6 teams to
    # the playoffs here (both division champs already rank in the top 6
    # either way) - what genuinely differs is WHO gets seeds 1-2 (and
    # therefore a first-round bye), since divisional seeding can promote a
    # division champion ahead of a higher-record non-champion.
    bye_pcts_differ = any(
        off_result[rid]["bye_pct"] != on_result[rid]["bye_pct"] for rid in range(1, NUM_TEAMS + 1)
    )
    assert bye_pcts_differ, (
        "a genuinely divisional league (divisions=2) must still seed differently than a "
        "non-divisional one given the same rosters/records - divisional logic must still work"
    )


def test_historical_snapshot_uses_real_per_week_data_not_one_flattened_week(synthetic_league):
    """
    Pins the real bug behind the "Week-by-Week Evolution & Trends" chart
    showing artificial jumps (e.g. @fbmartins in Liga do Inguinho: champ_pct
    9.7% -> 54.6% between week 2 and week 3, with no real change in
    underlying team strength). run_historical_simulation_snapshot used to
    take one flat single-week team_expectations snapshot and broadcast it
    across every simulated week - so a team with a genuine one-week
    projection data gap (a newly-elevated starter Sleeper hadn't published
    a projection for yet) had that gap's low score flattened onto its
    ENTIRE remaining season, not just the one week it was genuinely true
    for. It now takes team_week_expectations (the same real per-week curve
    compute_team_weekly_expectations produces for the live path) instead.

    Team A here is deliberately weak in exactly one week (mirroring a
    single-week projection gap) but strong every other week, same as
    control Team B which is strong every week. If the bug were still
    present, Team A's whole reconstructed season would use its weak week's
    score, crushing its win total far below Team B's; with the fix, only
    the one real bad week should count against it.
    """
    league, rosters, _ = synthetic_league
    league = dict(league)
    league["settings"] = {**league["settings"], "playoff_week_start": 15}

    STRONG = {"expected_pts": 150.0, "std_dev": 10.0, "bench_depth_pts": 20.0}
    WEAK = {"expected_pts": 50.0, "std_dev": 10.0, "bench_depth_pts": 20.0}

    team_a_rid, team_b_rid = 1, 2
    weeks = range(1, 15)
    team_week_expectations = {}
    for rid in range(1, NUM_TEAMS + 1):
        if rid == team_a_rid:
            team_week_expectations[rid] = {w: (WEAK if w == 3 else STRONG) for w in weeks}
        else:
            team_week_expectations[rid] = {w: STRONG for w in weeks}

    result = run_historical_simulation_snapshot(
        league=league,
        rosters=rosters,
        schedule={},
        team_week_expectations=team_week_expectations,
        snapshot_week=1,
        current_week=3,
        playoff_week_start=15,
        num_simulations=NUM_SIMULATIONS,
    )

    team_a_avg_wins = result[team_a_rid]["avg_wins"]
    team_b_avg_wins = result[team_b_rid]["avg_wins"]

    # Only 1 of ~13-14 simulated regular-season weeks is genuinely weak for
    # Team A, so its win total should stay close to Team B's (both strong
    # nearly every week) - not crushed toward zero the way flattening the
    # single weak week across the whole season would have done.
    assert team_a_avg_wins >= team_b_avg_wins - 2.0, (
        f"Team A avg_wins ({team_a_avg_wins}) is far below Team B's ({team_b_avg_wins}) despite "
        "being weak in only 1 of ~13 simulated weeks - the historical snapshot is still "
        "flattening one week's projection across the whole season."
    )


def test_displayed_expected_pts_and_bench_depth_are_a_season_average_not_one_week(synthetic_league):
    """
    Pins the "Starters PPG"/"Bench PPG" fix: run_monte_carlo_simulation used
    to report team_results[rid]["expected_pts"]/["bench_depth_pts"] as
    whatever the CURRENT week's own team_week_expectations entry said,
    discarding every other week's real per-week projection even though the
    Monte Carlo simulation itself (avg_wins/playoff_pct/champ_pct) already
    correctly draws from the full current_week..17 curve. Since
    power_score is derived from these same two fields, that also meant a
    single unusually strong or weak week could swing power_score - and by
    extension a team's win/neutral/rebuild category - despite the season-
    long simulation being unaffected. The displayed figures must now be the
    mean of expected_pts/bench_depth_pts across every week from current_week
    through week 17, matching what "PPG" (points per game) actually claims.
    """
    league, rosters, _ = synthetic_league
    current_week = 3
    last_week = 17

    # Team 1's per-week curve varies a lot (a real week-3 data gap, like the
    # Sam Darnold/Puka Nacua case, followed by strong steady weeks) - its
    # current week alone (60.0) must NOT be what gets reported.
    per_week_pts = {w: (60.0 if w == current_week else 130.0) for w in range(current_week, last_week + 1)}
    per_week_bench = {w: (10.0 if w == current_week else 40.0) for w in range(current_week, last_week + 1)}
    expected_avg_pts = sum(per_week_pts.values()) / len(per_week_pts)
    expected_avg_bench = sum(per_week_bench.values()) / len(per_week_bench)

    team_week_expectations = {
        rid: {
            w: {"expected_pts": per_week_pts[w] if rid == 1 else 90.0, "std_dev": 15.0,
                "bench_depth_pts": per_week_bench[w] if rid == 1 else 20.0}
            for w in range(current_week, last_week + 1)
        }
        for rid in range(1, NUM_TEAMS + 1)
    }

    result = run_monte_carlo_simulation(
        league=league,
        rosters=rosters,
        schedule={},
        team_week_expectations=team_week_expectations,
        current_week=current_week,
        playoff_week_start=15,
        num_simulations=NUM_SIMULATIONS,
    )

    team1 = result[1]
    assert team1["expected_pts"] == round(expected_avg_pts, 1), (
        f"expected_pts ({team1['expected_pts']}) must be the {current_week}-17 average "
        f"({round(expected_avg_pts, 1)}), not the single current-week snapshot (60.0)"
    )
    assert team1["bench_depth_pts"] == round(expected_avg_bench, 1), (
        f"bench_depth_pts ({team1['bench_depth_pts']}) must be the {current_week}-17 average "
        f"({round(expected_avg_bench, 1)}), not the single current-week snapshot (10.0)"
    )

    # power_score must still be derived from these exact same displayed
    # fields - the table and the Power Score formula must never diverge.
    max_pts = max(t["expected_pts"] for t in result.values())
    max_wins = max(t["avg_wins"] for t in result.values())
    max_bench = max(t["bench_depth_pts"] for t in result.values())
    pts_norm = (team1["expected_pts"] / max_pts) * 100.0
    win_norm = (team1["avg_wins"] / max_wins) * 100.0 if max_wins > 0 else 50.0
    bench_norm = (team1["bench_depth_pts"] / max_bench) * 100.0
    playoff_norm = team1["playoff_pct"]
    recomputed_power_score = round(0.45 * pts_norm + 0.25 * win_norm + 0.15 * playoff_norm + 0.15 * bench_norm, 1)

    assert recomputed_power_score == team1["power_score"], (
        "power_score must be derived from the exact same expected_pts/bench_depth_pts "
        "shown in the table - recomputing it independently must match exactly."
    )
