"""
Converted from scratch/test_trade_engine.py (already close to pytest shape).

Unit tests for Model 3 (Stud Premium + package discounts) in
evaluate_trade_fairness / calculate_effective_trade_value.
"""
from src.trade_engine import evaluate_trade_fairness, analyze_team_profile, make_pick_asset, CATEGORY_ROS_WEIGHT


def _make_profile_player(pid, name, pos, value):
    return {"player_id": pid, "full_name": name, "position": pos}, {
        pid: {"market_value": value, "rank_ecr": 10000.0 - value, "rank_ecr_overall": 10000.0 - value}
    }


def _build_test_profile(reserve_ids=None, taxi_ids=None):
    """
    A small synthetic roster with one starter, one plain bench player, one
    taxi player, and one reserve/IR player - roster_positions leaves 2 bench
    slots so both taxi and reserve candidates land in simulate_optimal_lineup's
    "bench" bucket, exactly like a real Sleeper roster.
    """
    roster_positions = ["QB", "BN", "BN", "BN"]
    roster_players = []
    lookup = {}
    for pid, name, pos, value in [
        ("p_starter", "Test Starter QB", "QB", 9000.0),
        ("p_bench", "Test Bench WR", "WR", 3000.0),
        ("p_taxi", "Test Taxi Rookie", "WR", 2000.0),
        ("p_reserve", "Test IR Stud", "RB", 5000.0),
    ]:
        player, entry = _make_profile_player(pid, name, pos, value)
        roster_players.append(player)
        lookup.update(entry)

    return analyze_team_profile(
        roster={"roster_id": 1, "reserve": reserve_ids or [], "taxi": taxi_ids or []},
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


def test_all_assets_length_matches_the_sum_of_the_four_source_lists():
    """
    Regression guard for the "all_assets" canonical roster list: its length
    must always equal the sum of starter/bench/taxi/reserve lengths. This
    would fail if a future change went back to reassembling only some of the
    four lists (e.g. "starter_assets + bench_assets + taxi_assets", forgetting
    reserve_assets - exactly the bug that made real IR'd players silently
    vanish from Room Value, Dynasty Power Rankings, and ROS Power Rankings).
    """
    profile = _build_test_profile(reserve_ids=["p_reserve"], taxi_ids=["p_taxi"])

    assert len(profile["all_assets"]) == (
        len(profile["starter_assets"])
        + len(profile["bench_assets"])
        + len(profile["taxi_assets"])
        + len(profile["reserve_assets"])
    )


def test_reserve_and_taxi_players_appear_exactly_once_in_all_assets():
    """
    Pins two things at once: (1) a player who is ONLY on IR must still show
    up in all_assets (the exact regression this whole investigation started
    from - IR'd players silently disappearing from every roster-total
    calculation); and (2) a taxi player must appear exactly ONCE, not twice -
    bench_assets used to only exclude reserve_ids, not taxi_ids, so a taxi
    player was counted in both bench_assets AND taxi_assets before this fix.
    """
    profile = _build_test_profile(reserve_ids=["p_reserve"], taxi_ids=["p_taxi"])
    all_ids = [a["player_id"] for a in profile["all_assets"]]

    assert all_ids.count("p_reserve") == 1, "an IR'd player must appear in all_assets exactly once"
    assert all_ids.count("p_taxi") == 1, "a taxi player must appear in all_assets exactly once, not double-counted via bench_assets + taxi_assets"
    assert all_ids.count("p_bench") == 1
    assert all_ids.count("p_starter") == 1

    # bench_assets itself must be the PURE bench: no taxi, no reserve.
    bench_ids = [a["player_id"] for a in profile["bench_assets"]]
    assert "p_taxi" not in bench_ids, "bench_assets must exclude taxi players (they belong to taxi_assets only)"
    assert "p_reserve" not in bench_ids, "bench_assets must exclude reserve/IR players (they belong to reserve_assets only)"


def test_package_discount_rejects_an_unbalanced_three_for_one():
    # Three 1,500 pt players (raw = 4,500) vs one 4,500 pt stud (raw = 4,500) -
    # raw values are equal, but Model 3's stud premium + package discount
    # should reveal this as unfair to the side receiving the stud.
    package = [
        {"name": "Player 1", "market_value": 1500.0, "type": "player"},
        {"name": "Player 2", "market_value": 1500.0, "type": "player"},
        {"name": "Player 3", "market_value": 1500.0, "type": "player"},
    ]
    stud = [{"name": "Elite Stud", "market_value": 4500.0, "type": "player"}]

    result = evaluate_trade_fairness(package, stud)

    # Eff Give = 1500*1.0 + 1500*0.85 + 1500*0.70 = 3825.0
    # Eff Receive = 4500*1.15 = 5175.0
    assert result["eff_give"] == 3825.0
    assert result["eff_receive"] == 5175.0
    assert result["fairness_ratio"] == 1.35
    assert result["is_balanced"] is False, "a 3-for-1 package of bench-level value must be rejected under Model 3"


def test_balanced_two_for_one_blockbuster_evaluates_within_tolerance():
    give = [
        {"name": "2027 Round 1 (Mid)", "market_value": 3666.0, "type": "pick"},
        {"name": "Quality Starter", "market_value": 3500.0, "type": "player"},
    ]
    receive = [{"name": "Superstar Stud", "market_value": 6500.0, "type": "player"}]

    result = evaluate_trade_fairness(give, receive)

    # Eff Give = 3666 + 3500*0.85 = 6641.0
    # Eff Receive = 6500*1.15 = 7475.0
    assert result["eff_give"] == 6641.0
    assert result["eff_receive"] == 7475.0
    assert result["net_diff"] == 834.0


# ---------------------------------------------------------------------------
# Pick assets carrying per-source ktc_val/fc_val/dp_val (Trade Center bug:
# picks showed "0 pts" in the "Raw Value Comparison by Source" table and
# silently hid the KTC Official Calculator card, because make_pick_asset
# only ever set market_value - never the individual source breakdown that
# player assets already carry).
# ---------------------------------------------------------------------------

def test_make_pick_asset_populates_per_source_values_when_lookups_given():
    picks_lookup = {("2027", 1, "mid"): 3000.0}
    ktc_picks_lookup = {("2027", 1, "mid"): 3500.0}
    fc_picks_lookup = {("2027", 1, "mid"): 2800.0}
    dp_picks_lookup = {("2027", 1, "mid"): 2600.0}

    asset = make_pick_asset(
        ("2027", 1, 1), picks_lookup, sim_rank_map={}, target_season="2028", total_rosters=12,
        ktc_picks_lookup=ktc_picks_lookup, fc_picks_lookup=fc_picks_lookup, dp_picks_lookup=dp_picks_lookup,
    )

    assert asset["market_value"] == 3000.0
    assert asset["ktc_val"] == 3500.0
    assert asset["fc_val"] == 2800.0
    assert asset["dp_val"] == 2600.0


def test_make_pick_asset_leaves_per_source_values_none_without_lookups():
    """A pick built without the new lookups (e.g. an older caller) must not
    crash and must leave ktc_val/fc_val/dp_val absent (None), not 0.0 - a
    real 0-value quote and "no data" must stay distinguishable."""
    picks_lookup = {("2027", 1, "mid"): 3000.0}

    asset = make_pick_asset(("2027", 1, 1), picks_lookup, sim_rank_map={}, target_season="2028", total_rosters=12)

    assert asset["market_value"] == 3000.0
    assert asset["ktc_val"] is None
    assert asset["fc_val"] is None
    assert asset["dp_val"] is None


def test_analyze_team_profile_threads_single_source_picks_lookups_to_pick_assets():
    """
    Reproduces the real Trade Center bug end to end: a roster with one owned
    pick, built through the same analyze_team_profile entry point
    src/orchestration.py uses. Before the fix, prof["pick_assets"][0] had no
    ktc_val/fc_val/dp_val at all, so the "Raw Value Comparison by Source"
    table's `if a.get("ktc_val")` filter silently dropped the pick (summing
    to 0 pts) and the KTC Official Calculator card's side list came back
    empty and the card just vanished.
    """
    player, lookup = _make_profile_player("p_starter", "Test Starter QB", "QB", 9000.0)

    prof = analyze_team_profile(
        roster={"roster_id": 1, "reserve": [], "taxi": []},
        roster_players=[player],
        owned_picks=[("2027", 1, 1)],
        primary_lookup=lookup,
        redraft_lookup=lookup,
        picks_lookup={("2027", 1, "mid"): 3000.0},
        sim_rank_map={},
        roster_positions=["QB", "BN"],
        is_dynasty=True,
        status="Active",
        category="neutral",
        manager_name="Test Manager",
        total_rosters=12,
        target_season="2028",
        ktc_picks_lookup={("2027", 1, "mid"): 3500.0},
        fc_picks_lookup={("2027", 1, "mid"): 2800.0},
        dp_picks_lookup={("2027", 1, "mid"): 2600.0},
    )

    assert len(prof["pick_assets"]) == 1
    pick = prof["pick_assets"][0]
    assert pick["ktc_val"] == 3500.0
    assert pick["fc_val"] == 2800.0
    assert pick["dp_val"] == 2600.0


# ---------------------------------------------------------------------------
# Dynasty+ROS fairness blend (CATEGORY_ROS_WEIGHT): converted from the
# flaky tests/integration/test_trade_refinements.py::
# test_taylor_for_jeanty_is_unfavorable_for_a_contender, which depended on
# two real players' live KTC/FantasyCalc/DynastyProcess market values -
# already drifted once since that test was written, turning a real
# "unfavorable" trade into "balanced" and breaking the test on live data
# alone, with the actual blend logic never having changed. Synthetic
# assets pin the same real bug this was meant to catch (a "win"/contender
# team getting a trade suggested as fair even though it trades a
# strong-ROS asset for a weak-ROS one) without ever depending on a live
# snapshot of two specific NFL players' values again.
# ---------------------------------------------------------------------------

def test_dynasty_ros_blend_flags_a_contender_unfavorable_trade_that_looks_balanced_on_pure_dynasty():
    """
    "Taylor-type": lower dynasty value, but far ahead in ROS production
    (the asset a win-now team actually wants). "Jeanty-type": higher
    dynasty value, but weak ROS production. On pure dynasty value alone
    (ros_weight=0.0, a rebuild team's lens) this reads as a fair,
    balanced trade. Blended with CATEGORY_ROS_WEIGHT["win"] (30% ROS /
    70% dynasty - what a contender's own evaluation actually uses), it
    must swing decisively into "unfavorable", since a contender is really
    trading away its best win-now asset for a worse one.
    """
    taylor_type = {"name": "Taylor-type RB", "type": "player", "market_value": 6000.0, "redraft_val": 7000.0}
    pick_2027_1st = {"name": "2027 Round 1 (Late)", "type": "pick", "market_value": 3000.0}
    jeanty_type = {"name": "Jeanty-type RB", "type": "player", "market_value": 7500.0, "redraft_val": 4000.0}

    give = [taylor_type, pick_2027_1st]
    receive = [jeanty_type]

    pure_dynasty = evaluate_trade_fairness(give, receive, ros_weight=0.0)
    assert pure_dynasty["is_balanced"] is True, (
        f"sanity check: this fixture must read as balanced on pure dynasty value, or the "
        f"blend assertion below proves nothing - got fairness_ratio={pure_dynasty['fairness_ratio']}"
    )

    win_ros_weight = CATEGORY_ROS_WEIGHT["win"]
    blended = evaluate_trade_fairness(give, receive, ros_weight=win_ros_weight)

    assert not blended["is_balanced"], (
        f"Taylor-type + {pick_2027_1st['name']} for Jeanty-type must be UNFAVORABLE for a contender "
        f"(win_ros_weight={win_ros_weight}), got fairness_ratio={blended['fairness_ratio']} "
        f"net_diff={blended['net_diff']}"
    )
    assert blended["fairness_ratio"] == 0.84
    assert blended["net_diff"] == -1432.5
    assert blended["ros_weight"] == win_ros_weight
