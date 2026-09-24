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
    """
    Arity-agnostic on purpose: _simulate_with_custom_idp_set (this file's
    reimplementation) still returns 2-tuples, while the real
    simulate_optimal_lineup now returns 3-tuples (player, ranking, slot).
    """
    return {tup[0].get("full_name") for tup in starters}


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


def _make_player(pid, name, pos, value):
    return {"player_id": pid, "full_name": name, "position": pos}, {
        pid: {"market_value": value, "rank_ecr": 10000.0 - value, "rank_ecr_overall": 10000.0 - value}
    }


def test_slot_labels_survive_a_fixed_slot_after_flex_in_roster_positions():
    """
    Regression test for a real production bug: a real league's
    roster_positions can list a fixed slot (K/DEF/IDP) AFTER a flex slot
    (e.g. Liga do Inguinho's ['QB','RB','RB','WR','WR','TE','FLEX','FLEX',
    'K']) - simulate_optimal_lineup fills every fixed slot first regardless
    of where it appears in roster_positions, then appends flex slots, so a
    caller reconstructing the slot by zipping starters[i] against
    roster_positions[i] mislabels two rows. Confirmed live: a Kicker
    (Cam Little) rendered as "FLEX" and a WR (Jaylen Waddle) rendered as
    "K" in the ROS/Dynasty roster breakdown tables. This pins the fix -
    simulate_optimal_lineup now attaches the real slot to each starter
    tuple instead of leaving it for the caller to reconstruct.
    """
    roster_positions = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX", "K", "BN", "BN"]

    roster_players = []
    lookup = {}
    # Values chosen so the two lowest-value flex-eligible WRs are the ones
    # left for FLEX after fixed slots are filled - deterministic selection.
    for pid, name, pos, value in [
        ("p_qb", "Test QB", "QB", 9000.0),
        ("p_rb1", "Test RB1", "RB", 8000.0),
        ("p_rb2", "Test RB2", "RB", 7000.0),
        ("p_wr1", "Test WR1", "WR", 6000.0),
        ("p_wr2", "Test WR2", "WR", 5000.0),
        ("p_te", "Test TE", "TE", 4000.0),
        ("p_k", "Test Kicker", "K", 3000.0),
        ("p_wr3", "Flex WR3", "WR", 2000.0),
        ("p_wr4", "Flex WR4", "WR", 1000.0),
    ]:
        player, entry = _make_player(pid, name, pos, value)
        roster_players.append(player)
        lookup.update(entry)

    starters, _bench = simulate_optimal_lineup(roster_players, lookup, roster_positions, is_dynasty=True)

    slot_by_name = {p.get("full_name"): slot for p, _r, slot in starters}

    assert slot_by_name["Test Kicker"] == "K", (
        f"the Kicker must be labeled 'K', not whatever roster_positions[i] happens to hold at his index - got {slot_by_name}"
    )
    assert slot_by_name["Flex WR3"] == "FLEX" and slot_by_name["Flex WR4"] == "FLEX", (
        f"the two lowest-value WRs must fill FLEX and be labeled 'FLEX', not 'K' - got {slot_by_name}"
    )
    # The exact bug this reproduces: zipping starters[i] <-> roster_positions[i]
    # by index would put the Kicker at index 6 (labeled "FLEX" there) and a
    # flex WR at index 8 (labeled "K" there) - assert that never happens.
    naive_zip_labels = {
        p.get("full_name"): (roster_positions[i] if i < len(roster_positions) else "FLEX")
        for i, (p, _r, _slot) in enumerate(starters)
    }
    assert naive_zip_labels["Test Kicker"] != slot_by_name["Test Kicker"], (
        "sanity check: this fixture must actually reproduce the index-mismatch scenario, or the assertions above prove nothing"
    )


def test_analyze_team_profile_starter_assets_carry_the_real_slot():
    """
    Same scenario one layer up: src.trade_engine.analyze_team_profile's
    starter_assets (what app.py's ROS/Dynasty roster breakdown tables
    actually render) must carry the same correct, explicit slot - not rely
    on app.py reconstructing it from roster_positions by index.
    """
    from src.trade_engine import analyze_team_profile

    roster_positions = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX", "K", "BN", "BN"]
    roster_players = []
    lookup = {}
    for pid, name, pos, value in [
        ("p_qb", "Test QB", "QB", 9000.0),
        ("p_rb1", "Test RB1", "RB", 8000.0),
        ("p_rb2", "Test RB2", "RB", 7000.0),
        ("p_wr1", "Test WR1", "WR", 6000.0),
        ("p_wr2", "Test WR2", "WR", 5000.0),
        ("p_te", "Test TE", "TE", 4000.0),
        ("p_k", "Test Kicker", "K", 3000.0),
        ("p_wr3", "Flex WR3", "WR", 2000.0),
        ("p_wr4", "Flex WR4", "WR", 1000.0),
    ]:
        player, entry = _make_player(pid, name, pos, value)
        roster_players.append(player)
        lookup.update(entry)

    profile = analyze_team_profile(
        roster={"roster_id": 1, "reserve": [], "taxi": []},
        roster_players=roster_players,
        owned_picks=[],
        primary_lookup=lookup,
        redraft_lookup=lookup,
        picks_lookup={},
        sim_rank_map={},
        roster_positions=roster_positions,
        is_dynasty=True,
        status="Active",
        category="neutral",
        manager_name="Test Manager",
        total_rosters=12,
    )

    slot_by_name = {a["name"]: a["slot"] for a in profile["starter_assets"]}
    assert slot_by_name["Test Kicker"] == "K"
    assert slot_by_name["Flex WR3"] == "FLEX" and slot_by_name["Flex WR4"] == "FLEX"


# ---------------------------------------------------------------------------
# Unmatched players (no entry in the lookup passed to simulate_optimal_lineup)
# used to be silently dropped by match_players_by_sleeper_id and discarded
# (`matched, _ = ...`), so a player FantasyPros' dynasty board doesn't cover
# at all (every real IDP position) or that its ROS board excludes (an
# injured player) vanished from starters AND bench - and therefore from
# every consumer built on top of them (Franchise Hub, Trade Center, Power
# Rankings, Room Value). Confirmed live: an entire IDP league's LB/DB/DL
# starters were unfillable, since dynasty_lookup has zero IDP entries.
# Fixed to fold unmatched players in as 0.0-value bench candidates instead.
# ---------------------------------------------------------------------------

def test_unmatched_player_appears_on_bench_with_zero_value_instead_of_vanishing():
    roster_positions = ["QB", "BN", "BN"]
    roster_players = []
    lookup = {}
    for pid, name, pos, value in [
        ("p_qb", "Test QB", "QB", 9000.0),
        ("p_bench", "Test Bench WR", "WR", 3000.0),
    ]:
        player, entry = _make_player(pid, name, pos, value)
        roster_players.append(player)
        lookup.update(entry)

    # No lookup entry at all for this one - e.g. an IDP position FantasyPros'
    # dynasty board doesn't rank, or a player its ROS board excludes.
    unmatched_player = {"player_id": "p_unranked", "full_name": "Test Unranked IDP", "position": "LB"}
    roster_players.append(unmatched_player)

    starters, bench = simulate_optimal_lineup(roster_players, lookup, roster_positions, is_dynasty=True)

    bench_ids = {p.get("player_id") for p, _r in bench}
    starter_ids = {p.get("player_id") for p, _r, _slot in starters}

    assert "p_unranked" in bench_ids, "an unmatched player must land on the bench, not be dropped entirely"
    assert "p_unranked" not in starter_ids, "an unmatched (0.0-value) player must never be a starter over real-value alternatives"

    unranked_ranking_data = next(r for p, r in bench if p.get("player_id") == "p_unranked")
    assert unranked_ranking_data.get("market_value", 0.0) == 0.0


def test_unmatched_player_never_displaces_a_real_value_player_at_the_same_position():
    """
    The actual bug this whole fix chain started from, in miniature: two real
    IDP starting slots (LB, DB) that a real-value candidate exists for, plus
    an unmatched (unranked) LB. The unmatched LB must land on the bench, not
    take the LB starting slot away from the real-value LB.
    """
    roster_positions = ["LB", "DB", "BN", "BN"]
    roster_players = []
    lookup = {}
    for pid, name, pos, value in [
        ("p_lb_real", "Real Value LB", "LB", 500.0),
        ("p_db_real", "Real Value DB", "DB", 400.0),
    ]:
        player, entry = _make_player(pid, name, pos, value)
        roster_players.append(player)
        lookup.update(entry)

    unmatched_lb = {"player_id": "p_lb_unranked", "full_name": "Unranked LB", "position": "LB"}
    roster_players.append(unmatched_lb)

    starters, bench = simulate_optimal_lineup(roster_players, lookup, roster_positions, is_dynasty=True)

    starter_names = {p.get("full_name") for p, _r, _slot in starters}
    bench_names = {p.get("full_name") for p, _r in bench}

    assert "Real Value LB" in starter_names
    assert "Unranked LB" in bench_names
    assert "Unranked LB" not in starter_names


def test_unmatched_player_fills_a_required_slot_when_no_real_value_candidate_exists():
    """
    The IDP-league case for real: if EVERY candidate for a required slot is
    unmatched (no dynasty_lookup coverage for any real IDP position), the
    slot must still be filled by one of them rather than left empty - an
    unmatched player only ever loses to a real-value one, it does not lose
    to an empty slot.
    """
    roster_positions = ["QB", "LB", "BN"]
    roster_players = []
    lookup = {}
    player, entry = _make_player("p_qb", "Test QB", "QB", 9000.0)
    roster_players.append(player)
    lookup.update(entry)

    # Both LB candidates are unmatched - neither has a lookup entry.
    roster_players.append({"player_id": "p_lb_a", "full_name": "Unranked LB A", "position": "LB"})
    roster_players.append({"player_id": "p_lb_b", "full_name": "Unranked LB B", "position": "LB"})

    starters, _bench = simulate_optimal_lineup(roster_players, lookup, roster_positions, is_dynasty=True)

    lb_starters = [p.get("full_name") for p, _r, slot in starters if slot == "LB"]
    assert len(lb_starters) == 1, f"the required LB slot must be filled by one of the unmatched candidates, not left empty - got {lb_starters}"
