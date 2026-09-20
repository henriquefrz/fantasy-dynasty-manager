"""
Converted from scratch/test_idp_flex_unification.py.

Verifies the IDP_FLEX eligibility fix: team_strength.py's FLEX_RULES used to
allow only {"DL", "LB", "DB"} for IDP_FLEX, while start_sit.py kept a
separate, still-incomplete {"DL", "LB", "DB", "DE", "DT", "CB", "S"} dict.
Sleeper's player.position field for IDP players is the specific real-world
position ("DE", "OLB", "FS", ...), not the broad fantasy group, so any
hardcoded set has to enumerate every specific position or it silently
benches real IDP starters (see 373091b in the git history).
"""
from collections import Counter

from src.matching import match_players_by_sleeper_id
from src.team_strength import (
    FIXED_POSITIONS,
    FLEX_RULES,
    IDP_FLEX_ELIGIBLE_POSITIONS,
    simulate_optimal_lineup,
)
from src.start_sit import FLEX_RULES as START_SIT_FLEX_RULES
from src.start_sit import simulate_optimal_weekly_lineup

# Reference reimplementations of the two pre-fix eligibility sets, kept only
# to reproduce the OLD (buggy) behavior for comparison - not the real code.
OLD_TEAM_STRENGTH_IDP_FLEX = {"DL", "LB", "DB"}
OLD_START_SIT_IDP_FLEX = {"DL", "LB", "DB", "DE", "DT", "CB", "S"}


def _simulate_with_custom_idp_set(roster_players, lookup, roster_positions, idp_eligible_positions):
    """
    Reimplements simulate_optimal_lineup's selection logic (fixed slots by
    exact position match, then flex slots most-specific-first) with an
    injectable IDP_FLEX eligibility set, to reproduce the two old,
    now-replaced behaviors for comparison against the real, unified function.
    """
    starting_slots = [p for p in roster_positions if p not in {"BN", "IR", "TAXI"}]
    matched, _ = match_players_by_sleeper_id(roster_players, lookup)
    if not matched:
        return [], []

    sorted_players = sorted(
        matched,
        key=lambda item: (-item[1].get("market_value", 0.0), item[1].get("rank_ecr_overall", item[1].get("rank_ecr", 999.0))),
    )

    assigned = set()
    starters = []

    fixed_slots = [s for s in starting_slots if s in FIXED_POSITIONS]
    for pos, needed in Counter(fixed_slots).items():
        count = 0
        for p_obj, r_data in sorted_players:
            pid = p_obj.get("player_id")
            if pid not in assigned and p_obj.get("position") == pos:
                starters.append((p_obj, r_data))
                assigned.add(pid)
                count += 1
                if count >= needed:
                    break

    flex_rules = [
        ("WRRB_FLEX", {"RB", "WR"}), ("REC_FLEX", {"WR", "TE"}), ("FLEX", {"RB", "WR", "TE"}),
        ("SUPER_FLEX", {"QB", "RB", "WR", "TE"}), ("IDP_FLEX", idp_eligible_positions),
    ]
    flex_dict = dict(flex_rules)
    flex_order = [n for n, _ in flex_rules]
    league_flex_slots = sorted(
        [s for s in starting_slots if s in flex_dict],
        key=lambda s: flex_order.index(s) if s in flex_order else 99,
    )
    for flex_slot in league_flex_slots:
        eligible = flex_dict[flex_slot]
        for p_obj, r_data in sorted_players:
            pid = p_obj.get("player_id")
            if pid not in assigned and p_obj.get("position") in eligible:
                starters.append((p_obj, r_data))
                assigned.add(pid)
                break

    return starters, [(p, r) for p, r in sorted_players if p.get("player_id") not in assigned]


def _starter_names(starters):
    return {p.get("full_name") for p, _ in starters}


def test_old_team_strength_idp_flex_set_benched_elite_pass_rushers(
    idp_flex_roster_players, idp_flex_lookup, samonte_dynasty_roster_positions
):
    old_starters, _ = _simulate_with_custom_idp_set(
        idp_flex_roster_players, idp_flex_lookup, samonte_dynasty_roster_positions, OLD_TEAM_STRENGTH_IDP_FLEX
    )
    names = _starter_names(old_starters)

    assert "Myles Garrett" not in names, "bug reproduction failed: old team_strength.py set should exclude position='DE' from IDP_FLEX"
    assert "Maxx Crosby" not in names, "bug reproduction failed: old team_strength.py set should exclude position='DE' from IDP_FLEX"
    assert "Tuli Tuipulotu" in names, "expected the roster's only DL-position player to fill IDP_FLEX under the old narrow set"


def test_old_start_sit_idp_flex_set_happened_to_include_de(
    idp_flex_roster_players, idp_flex_lookup, samonte_dynasty_roster_positions
):
    """
    start_sit.py's old, broader set included "DE" so it happened to start
    both pass rushers on THIS roster - but would still miss OLB/ILB/NT/FS/SS
    elsewhere, which is exactly why a single shared, fully-enumerated set is
    required instead of two independently-maintained partial ones.
    """
    old_starters, _ = _simulate_with_custom_idp_set(
        idp_flex_roster_players, idp_flex_lookup, samonte_dynasty_roster_positions, OLD_START_SIT_IDP_FLEX
    )
    names = _starter_names(old_starters)
    assert "Myles Garrett" in names and "Maxx Crosby" in names


def test_unified_simulate_optimal_lineup_starts_elite_pass_rushers(
    idp_flex_roster_players, idp_flex_lookup, samonte_dynasty_roster_positions
):
    """The real, current simulate_optimal_lineup (not a reimplementation)."""
    starters, _ = simulate_optimal_lineup(
        idp_flex_roster_players, idp_flex_lookup, samonte_dynasty_roster_positions, is_dynasty=True
    )
    names = _starter_names(starters)

    assert "Myles Garrett" in names, f"expected the fixed simulate_optimal_lineup to start Myles Garrett, got: {names}"
    assert "Maxx Crosby" in names, f"expected the fixed simulate_optimal_lineup to start Maxx Crosby, got: {names}"


def test_start_sit_lineup_agrees_with_team_strength_lineup(
    idp_flex_roster_players, idp_flex_lookup, samonte_dynasty_roster_positions
):
    """
    Same roster, same lookup, through simulate_optimal_weekly_lineup
    (start_sit.py) - proves both call sites now agree, since they share the
    same FLEX_RULES object.
    """
    weekly_projections_lookup = {pid: v["market_value"] for pid, v in idp_flex_lookup.items()}
    weekly_starters, _ = simulate_optimal_weekly_lineup(
        idp_flex_roster_players, weekly_projections_lookup, samonte_dynasty_roster_positions
    )
    names = {p.get("full_name") for p, _, _ in weekly_starters}
    assert "Myles Garrett" in names and "Maxx Crosby" in names


def test_flex_rules_is_a_single_shared_object():
    assert START_SIT_FLEX_RULES is FLEX_RULES, "start_sit.py should import the exact same FLEX_RULES object from team_strength.py, not a copy"
    idp_rule = dict(FLEX_RULES)["IDP_FLEX"]
    assert idp_rule is IDP_FLEX_ELIGIBLE_POSITIONS


def test_idp_flex_eligible_positions_covers_every_real_sleeper_idp_position():
    idp_rule = dict(FLEX_RULES)["IDP_FLEX"]
    for pos in ("DE", "DT", "NT", "OLB", "ILB", "MLB", "CB", "S", "SS", "FS", "DL", "LB", "DB"):
        assert pos in idp_rule, f"unified IDP_FLEX set is missing real Sleeper position value {pos!r}"
