"""
Converted from scratch/test_trade_engine.py (already close to pytest shape).

Unit tests for Model 3 (Stud Premium + package discounts) in
evaluate_trade_fairness / calculate_effective_trade_value.
"""
from src.trade_engine import evaluate_trade_fairness


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
