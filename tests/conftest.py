"""
Shared synthetic fixtures for the unit test suite - no live network calls.

Rosters, scoring settings, and market lookups here are hand-built to
reproduce the exact scenarios that exposed real bugs fixed this session
(see each fixture's docstring), instead of depending on live Sleeper/KTC/
FantasyPros data.
"""
import pytest


@pytest.fixture
def samonte_dynasty_roster_positions():
    """
    Real roster_positions shape from the Samonte Dynasty league: 9 fixed
    slots (QB/RB/RB/WR/WR/TE/K/LB/DB), 1 FLEX, 2 IDP_FLEX, 12 bench slots.
    """
    return [
        "QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "K", "LB", "DB",
        "IDP_FLEX", "IDP_FLEX",
        "BN", "BN", "BN", "BN", "BN", "BN", "BN", "BN", "BN", "BN", "BN", "BN",
    ]


@pytest.fixture
def idp_flex_roster_players():
    """
    Synthetic roster reproducing the scenario that exposed the IDP_FLEX
    eligibility bug: two elite pass rushers reporting Sleeper's specific
    `position` value "DE" (Myles Garrett, Maxx Crosby) - a real, common
    value team_strength.py's old IDP_FLEX set ({"DL", "LB", "DB"}) could
    never match, silently benching them from IDP_FLEX.

    One filler player per fixed slot (QB/RB/RB/WR/WR/TE/K/LB) plus a
    fixed-DB starter (Derwin James) so the fixed "DB" slot is spoken for
    before flex assignment runs - matching the real roster this was found
    on (Samonte Dynasty roster 6).
    """
    def player(pid, name, pos):
        return {"player_id": pid, "full_name": name, "position": pos}

    return [
        player("qb1", "Test QB", "QB"),
        player("rb1", "Test RB1", "RB"),
        player("rb2", "Test RB2", "RB"),
        player("rb3", "Test RB3 Flex Filler", "RB"),
        player("wr1", "Test WR1", "WR"),
        player("wr2", "Test WR2", "WR"),
        player("te1", "Test TE", "TE"),
        player("k1", "Test K", "K"),
        player("lb1", "Test LB", "LB"),
        player("3973", "Myles Garrett", "DE"),
        player("5991", "Maxx Crosby", "DE"),
        player("10898", "Tuli Tuipulotu", "DL"),
        player("4971", "Derwin James", "DB"),
        player("8286", "Dax Hill", "DB"),
    ]


@pytest.fixture
def idp_flex_lookup(idp_flex_roster_players):
    """
    market_value engineered so the two DE-position pass rushers clearly
    outrank the roster's only DL-position player and the DB-group players -
    the exact scenario that exposes the bug once they're actually eligible.
    Every other roster spot gets a low filler value.
    """
    overrides = {
        "3973": 9000.0,   # Myles Garrett (DE) - should win an IDP_FLEX slot once eligible
        "5991": 8800.0,   # Maxx Crosby (DE) - should win an IDP_FLEX slot once eligible
        "10898": 3000.0,  # Tuli Tuipulotu (DL) - the old narrow set's only eligible pass rusher
        "4971": 2500.0,   # Derwin James (DB) - fills the fixed "DB" slot first
        "8286": 2400.0,   # Dax Hill (DB)
    }
    lookup = {}
    for p in idp_flex_roster_players:
        pid = p["player_id"]
        val = overrides.get(pid, 500.0)
        lookup[pid] = {"market_value": val, "rank_ecr": 999.0 - val / 100.0}
    return lookup


@pytest.fixture
def te_premium_lookup():
    """Tiny synthetic dynasty-SF-style lookup with one elite TE and one RB."""
    return {
        "te1": {
            "player_name": "Elite TE", "position": "TE",
            "fc_val": 5000.0, "ktc_val": 5200.0, "dp_val": 4800.0,
            "market_value": 5000.0, "rank_ecr": 5.0, "rank_ecr_pos": 1.0,
            "rank_ecr_overall": 20.0, "fp_ecr_pos": 1.0, "fp_ecr_overall": 20.0,
        },
        "rb1": {
            "player_name": "Some RB", "position": "RB",
            "fc_val": 3000.0, "ktc_val": 3100.0, "dp_val": 2900.0,
            "market_value": 3000.0, "rank_ecr": 10.0, "rank_ecr_pos": 5.0,
            "rank_ecr_overall": 15.0, "fp_ecr_pos": 5.0, "fp_ecr_overall": 15.0,
        },
    }


@pytest.fixture
def te_ktc_raw():
    """
    Synthetic KTC "fantasy rankings" raw row for the TE in te_premium_lookup,
    with base/tep/tepp Superflex value tiers - the shape
    _extract_ktc_te_tiers/apply_ktc_te_premium expect.
    """
    return [
        {
            "playerID": "9001", "mflid": "", "position": "TE",
            "superflexValues": {
                "value": 5200.0,
                "tep": {"value": 6400.0},
                "tepp": {"value": 7000.0},
            },
        },
    ]


@pytest.fixture
def te_player_ids_raw():
    """Maps the synthetic KTC TE row's playerID to the lookup's Sleeper id."""
    return [{"ktc_id": "9001", "sleeper_id": "te1"}]
