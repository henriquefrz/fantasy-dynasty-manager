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
            "playerID": "9001", "mflid": "", "position": "TE", "playerName": "Elite TE",
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
    return [{"ktc_id": "9001", "sleeper_id": "te1", "name": "Elite TE"}]


# ---------------------------------------------------------------------------
# src/orchestration.py fixtures: a small synthetic 4-team, 1QB dynasty league
# with standard (baseline) scoring, engineered so team 1 is clearly the
# strongest roster and team 4 the weakest, for testing build_league_context /
# build_team_profiles end to end without any live Sleeper/KTC/FantasyPros
# data. roster_positions deliberately uses only FIXED_POSITIONS slots (no
# FLEX/SUPER_FLEX) so every player has exactly one possible starting slot,
# keeping lineup assignment unambiguous.
# ---------------------------------------------------------------------------

ORCH_ROSTER_POSITIONS = ["QB", "RB", "RB", "WR", "WR", "TE", "K", "DEF", "BN", "BN"]
ORCH_TEAM_IDS = (1, 2, 3, 4)
ORCH_POSITIONS_BY_SLOT = ["QB", "RB", "RB", "WR", "WR", "TE"]  # skill starters (K/DEF handled separately)


def _orch_player(pid, name, pos, team_abbr="AAA", age=25):
    return {"player_id": pid, "full_name": name, "position": pos, "team": team_abbr, "age": age, "years_exp": 3}


@pytest.fixture
def orchestration_players_db():
    """
    market_db["players"] equivalent (get_players()'s full Sleeper player DB),
    keyed by player_id. 4 teams x (6 skill starters + K + DEF + 2 bench).
    """
    players = {}
    for team_id in ORCH_TEAM_IDS:
        for slot_idx, pos in enumerate(ORCH_POSITIONS_BY_SLOT):
            pid = f"t{team_id}_{pos.lower()}{slot_idx}"
            players[pid] = _orch_player(pid, f"Team{team_id} {pos} Starter{slot_idx}", pos)
        players[f"t{team_id}_k"] = _orch_player(f"t{team_id}_k", f"Team{team_id} Kicker", "K")
        players[f"t{team_id}_def"] = _orch_player(f"t{team_id}_def", f"Team{team_id} Defense", "DEF")
        players[f"t{team_id}_bn1"] = _orch_player(f"t{team_id}_bn1", f"Team{team_id} Bench1", "WR")
        players[f"t{team_id}_bn2"] = _orch_player(f"t{team_id}_bn2", f"Team{team_id} Bench2", "RB")
    return players


@pytest.fixture
def orchestration_rosters(orchestration_players_db):
    """4 rosters, one per team, each owned by a distinct user_id."""
    rosters = []
    for team_id in ORCH_TEAM_IDS:
        player_ids = [pid for pid in orchestration_players_db if pid.startswith(f"t{team_id}_")]
        rosters.append({
            "roster_id": team_id,
            "owner_id": f"user_{team_id}",
            "players": player_ids,
            "starters": [pid for pid in player_ids if "_bn" not in pid],
            "reserve": [],
            "taxi": [],
            "settings": {"wins": 0, "losses": 0, "ties": 0, "fpts": 0, "fpts_decimal": 0},
        })
    return rosters


@pytest.fixture
def orchestration_users():
    return [
        {"user_id": f"user_{team_id}", "display_name": f"manager{team_id}", "metadata": {"team_name": f"Team {team_id}"}}
        for team_id in ORCH_TEAM_IDS
    ]


def _orch_skill_value(team_id, base):
    """Strictly decreasing value by team_id (team 1 strongest, team 4 weakest)."""
    return base - (team_id - 1) * (base * 0.2)


def _orch_lookup_entry(value, pos):
    return {
        "position": pos,
        "fc_val": value, "ktc_val": value, "dp_val": value,
        "market_value": value,
        "rank_ecr": 100.0 - value / 100.0,
        "rank_ecr_pos": 10.0, "rank_ecr_overall": 100.0 - value / 100.0,
        "fp_ecr_pos": 10.0, "fp_ecr_overall": 100.0 - value / 100.0,
    }


def _orch_kicker_def_entry(pos, rank_ecr):
    return {
        "position": pos,
        "rank_ecr": rank_ecr, "rank_ecr_pos": rank_ecr, "rank_ecr_overall": rank_ecr,
        "fp_ecr_pos": rank_ecr, "fp_ecr_overall": rank_ecr,
        "market_value": 0.0,  # recomputed from rank_ecr by compute_kicker_dst_value
    }


BASE_VALUE_BY_POS = {"QB": 6000.0, "RB": 5000.0, "WR": 4500.0, "TE": 3000.0}


@pytest.fixture
def orchestration_dynasty_lookup(orchestration_players_db):
    """
    A dynasty-style lookup (raw fc_val/ktc_val/dp_val, pre apply_valuation_mode)
    with market value strictly decreasing from team 1 (strongest) to team 4
    (weakest) at every skill position, plus K/DEF valued via rank_ecr.
    """
    lookup = {}
    for pid, p in orchestration_players_db.items():
        team_id = int(pid.split("_")[0][1:])
        pos = p["position"]
        if pos in BASE_VALUE_BY_POS:
            value = _orch_skill_value(team_id, BASE_VALUE_BY_POS[pos])
            lookup[pid] = _orch_lookup_entry(value, pos)
        elif pos in ("K", "DEF"):
            # Lower rank_ecr = better; team 1 gets the best (lowest) rank.
            lookup[pid] = _orch_kicker_def_entry(pos, rank_ecr=float(team_id))
    return lookup


@pytest.fixture
def orchestration_redraft_lookup(orchestration_dynasty_lookup):
    """
    market_db["redraft_lookup"]: same ordering as the dynasty lookup (team 1
    strongest) but as a plain, already-resolved market_value lookup (no
    fc/ktc/dp recomputation), matching how a real redraft lookup is shaped
    after enrich_lookup_with_redraft_values has already run.
    """
    return {pid: dict(entry) for pid, entry in orchestration_dynasty_lookup.items()}


@pytest.fixture
def orchestration_ktc_te_raw_and_player_ids():
    """
    KTC "fantasy rankings" raw rows for each team's TE, with base/tep/tepp
    value tiers, plus the matching player_ids_raw rows - for testing
    build_league_context's TE Premium branch (tep_bonus > 0) without live data.
    """
    rows = []
    player_ids_raw = []
    for team_id in ORCH_TEAM_IDS:
        pid = f"t{team_id}_te5"
        ktc_player_id = f"ktc_{pid}"
        te_name = f"Team{team_id} TE Starter5"
        base = _orch_skill_value(team_id, BASE_VALUE_BY_POS["TE"])
        rows.append({
            "playerID": ktc_player_id, "mflid": "", "position": "TE", "playerName": te_name,
            "oneQBValues": {"value": base, "tep": {"value": base * 1.15}, "tepp": {"value": base * 1.30}},
            "superflexValues": {"value": base, "tep": {"value": base * 1.15}, "tepp": {"value": base * 1.30}},
        })
        player_ids_raw.append({"ktc_id": ktc_player_id, "sleeper_id": pid, "name": te_name})
    return rows, player_ids_raw


@pytest.fixture
def orchestration_market_db(orchestration_players_db, orchestration_dynasty_lookup, orchestration_redraft_lookup, orchestration_ktc_te_raw_and_player_ids):
    ktc_te_raw, player_ids_raw = orchestration_ktc_te_raw_and_player_ids
    return {
        "players": orchestration_players_db,
        "dynasty_sf_lookup": orchestration_dynasty_lookup,
        "dynasty_1qb_lookup": orchestration_dynasty_lookup,
        "redraft_lookup": orchestration_redraft_lookup,
        "ktc_sf": ktc_te_raw, "ktc_1qb": ktc_te_raw,
        "player_ids": player_ids_raw,
        "fp_ros_rankings": [], "ros_projections_raw": [],
        "ktc_redraft_sf": [], "ktc_redraft_1qb": [],
        "picks_bundle_sf": {"dp": {}, "ktc": {}, "fc": {}, "all_keys": []},
        "picks_bundle_1qb": {"dp": {}, "ktc": {}, "fc": {}, "all_keys": []},
    }


def _orch_league(league_type_code, roster_positions=None, scoring_overrides=None):
    scoring = {
        "rec": 0.5, "bonus_rec_te": 0.0, "pass_td": 4.0, "pass_yd": 0.04,
        "rush_yd": 0.1, "rec_yd": 0.1, "rush_td": 6.0, "rec_td": 6.0,
        "pass_int": -2.0, "fum_lost": -2.0,
    }
    scoring.update(scoring_overrides or {})
    return {
        "league_id": "orch_test_league",
        "name": "Orchestration Test League",
        "season": "2026",
        "total_rosters": len(ORCH_TEAM_IDS),
        "roster_positions": roster_positions or ORCH_ROSTER_POSITIONS,
        "scoring_settings": scoring,
        "settings": {"type": league_type_code, "playoff_week_start": 15, "draft_rounds": 4},
    }


@pytest.fixture
def orchestration_dynasty_league():
    """Dynasty, 1QB, standard (baseline) scoring - triggers compute_custom_redraft_lookup's fast-path fallback."""
    return _orch_league(league_type_code=2)


@pytest.fixture
def orchestration_redraft_league():
    """Redraft, 1QB, standard scoring."""
    return _orch_league(league_type_code=0)


@pytest.fixture
def orchestration_tep_league():
    """Dynasty, 1QB, TE Premium (bonus_rec_te=1.0) - exercises apply_ktc_te_premium."""
    return _orch_league(league_type_code=2, scoring_overrides={"bonus_rec_te": 1.0})


@pytest.fixture
def orchestration_full_ppr_league():
    """Dynasty, 1QB, non-standard (Full PPR) scoring - must NOT fall back to market_db['redraft_lookup']."""
    return _orch_league(league_type_code=2, scoring_overrides={"rec": 1.0})
