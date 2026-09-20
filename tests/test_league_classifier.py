"""
Converted from scratch/test_is_superflex_unification.py.

Verifies that src/league_classifier.py:is_superflex_league() produces the
same result as every one of the 8 independent inline implementations it
replaced across app.py, main.py, src/trade_engine.py, and
scripts/weekly_automation.py - each of which risked drifting out of sync
independently (see 64cf363 in the git history).
"""
import pytest

from src.league_classifier import is_superflex_league


# The 8 original call sites reduce to 5 distinct implementations once
# duplicates are collapsed; every one is compared against the unified
# function below.
def old_app_py(roster_pos):
    """app.py:3332 and app.py:3511 (identical, convoluted form)."""
    return any(pos in ("SUPER_FLEX", "QB") for pos in roster_pos if roster_pos.count("QB") > 1 or pos == "SUPER_FLEX")


def old_main_py(roster_pos):
    """main.py:223 (identical to scripts/weekly_automation.py:77 and :168)."""
    return "SUPER_FLEX" in roster_pos or roster_pos.count("QB") >= 2


def old_trade_engine_223(roster_positions):
    """src/trade_engine.py:223."""
    return "SUPER_FLEX" in roster_positions or roster_positions.count("QB") >= 2


def old_trade_engine_314(roster_positions):
    """src/trade_engine.py:314 - the only variant with a None-safety guard."""
    return bool(roster_positions and ("SUPER_FLEX" in roster_positions or roster_positions.count("QB") >= 2))


def old_trade_engine_837(roster_positions):
    """src/trade_engine.py:837."""
    return ("SUPER_FLEX" in roster_positions) or (roster_positions.count("QB") >= 2)


OLD_IMPLEMENTATIONS = {
    "app.py (x2)": old_app_py,
    "main.py / weekly_automation.py (x3)": old_main_py,
    "trade_engine.py:223": old_trade_engine_223,
    "trade_engine.py:314 (None-guarded)": old_trade_engine_314,
    "trade_engine.py:837": old_trade_engine_837,
}

EDGE_CASES = [
    ("0 QB, no SUPER_FLEX slot", ["RB", "WR", "TE", "FLEX", "BN", "BN"]),
    ("1 QB, no SUPER_FLEX slot (standard 1QB league)", ["QB", "RB", "WR", "TE", "FLEX", "BN"]),
    ("2 QB, no explicit SUPER_FLEX slot", ["QB", "QB", "RB", "WR", "FLEX", "BN"]),
    ("3+ QB, no explicit SUPER_FLEX slot", ["QB", "QB", "QB", "RB", "WR"]),
    ("1 QB + explicit SUPER_FLEX slot (standard Superflex league)", ["QB", "SUPER_FLEX", "RB", "WR", "TE"]),
    ("0 QB but an explicit SUPER_FLEX slot (unusual but possible)", ["SUPER_FLEX", "RB", "WR", "TE"]),
    ("Empty roster_positions", []),
    ("Only bench/IR slots, no starters at all", ["BN", "BN", "IR", "IR"]),
]


@pytest.mark.parametrize("label, roster_positions", EDGE_CASES, ids=[c[0] for c in EDGE_CASES])
@pytest.mark.parametrize("old_name, old_fn", OLD_IMPLEMENTATIONS.items(), ids=list(OLD_IMPLEMENTATIONS.keys()))
def test_matches_every_old_implementation(old_name, old_fn, label, roster_positions):
    assert is_superflex_league(roster_positions) == old_fn(roster_positions), (
        f"is_superflex_league() disagrees with old implementation {old_name!r} on case {label!r}"
    )


def test_none_is_handled_without_raising():
    """
    None crashes 5 of the 6 old implementations (every one except
    trade_engine.py:314's guarded form); the unified function must be
    strictly more robust and simply return False.
    """
    assert is_superflex_league(None) is False
