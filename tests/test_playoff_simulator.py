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
        team_expectations=team_expectations,
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
