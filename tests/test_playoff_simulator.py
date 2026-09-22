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

from src.playoff_simulator import run_monte_carlo_simulation

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
