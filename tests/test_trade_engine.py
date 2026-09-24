"""
Converted from scratch/test_trade_engine.py (already close to pytest shape).

Unit tests for Model 3 (Stud Premium + package discounts) in
evaluate_trade_fairness / calculate_effective_trade_value.
"""
from src.trade_engine import evaluate_trade_fairness, analyze_team_profile


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
