"""
trade_engine.py

Core trade suggestion and evaluation engine for Fantasy Dynasty Manager.
Implements:
- Model 3: Stud Premium (+15%) & Package Discounts (1.0, 0.85, 0.70, 0.50).
- Team trajectory profiling (Contender vs. Rebuilder, Positional Surplus vs. Deficit).
- Draft pick integration for future dynasty classes.
- Win-win trade generation (Contender win-now moves, Rebuilder pick-harvesting, Positional rebalancing).
"""

from typing import Dict, List, Tuple, Any, Optional
from src.team_strength import simulate_optimal_lineup
from src.draft_picks import project_pick_tier, get_single_pick_value


STUD_MULTIPLIER = 1.15
PACKAGE_WEIGHTS = (1.0, 0.85, 0.70, 0.50)
FAIRNESS_MIN_RATIO = 0.88
FAIRNESS_MAX_RATIO = 1.12
MAX_DIFF_TOLERANCE = 800.0


def calculate_effective_trade_value(
    assets: List[Dict[str, Any]],
    has_stud: bool,
    stud_multiplier: float = STUD_MULTIPLIER,
    package_weights: Tuple[float, ...] = PACKAGE_WEIGHTS,
) -> float:
    """
    Calculates the Model 3 effective trade value of an asset package.
    - Assets are sorted descending by market_value.
    - If this side holds the single highest-value asset in the trade (the Stud),
      that top asset receives the stud multiplier (+15%).
    - Multi-asset packages receive diminishing returns (1.0, 0.85, 0.70, 0.50).
    """
    if not assets:
        return 0.0

    sorted_assets = sorted(assets, key=lambda a: -a.get("market_value", 0.0))
    total_effective = 0.0

    for idx, asset in enumerate(sorted_assets):
        val = asset.get("market_value", 0.0)
        weight = package_weights[min(idx, len(package_weights) - 1)]

        if idx == 0 and has_stud:
            total_effective += val * stud_multiplier
        else:
            total_effective += val * weight

    return round(total_effective, 1)


def evaluate_trade_fairness(
    give_assets: List[Dict[str, Any]],
    receive_assets: List[Dict[str, Any]],
    stud_multiplier: float = STUD_MULTIPLIER,
) -> Dict[str, Any]:
    """
    Evaluates a proposed trade using Model 3.
    Identifies the Stud, computes effective values for both sides, and checks fairness.
    """
    if not give_assets or not receive_assets:
        return {
            "is_balanced": False,
            "raw_give": 0.0,
            "raw_receive": 0.0,
            "eff_give": 0.0,
            "eff_receive": 0.0,
            "fairness_ratio": 0.0,
            "net_diff": 0.0,
            "stud_asset": None,
            "stud_side": None,
        }

    raw_give = sum(a.get("market_value", 0.0) for a in give_assets)
    raw_receive = sum(a.get("market_value", 0.0) for a in receive_assets)

    # Find the trade stud (highest value asset across both sides)
    max_give = max(a.get("market_value", 0.0) for a in give_assets)
    max_receive = max(a.get("market_value", 0.0) for a in receive_assets)

    if max_give >= max_receive:
        stud_side = "give"
        stud_asset = max(give_assets, key=lambda a: a.get("market_value", 0.0))
    else:
        stud_side = "receive"
        stud_asset = max(receive_assets, key=lambda a: a.get("market_value", 0.0))

    eff_give = calculate_effective_trade_value(
        give_assets, has_stud=(stud_side == "give"), stud_multiplier=stud_multiplier
    )
    eff_receive = calculate_effective_trade_value(
        receive_assets, has_stud=(stud_side == "receive"), stud_multiplier=stud_multiplier
    )

    fairness_ratio = (eff_receive / eff_give) if eff_give > 0 else 0.0
    net_diff = eff_receive - eff_give

    # Balanced if ratio is in [FAIRNESS_MIN_RATIO, FAIRNESS_MAX_RATIO] and abs(diff) <= MAX_DIFF_TOLERANCE
    is_balanced = (
        (FAIRNESS_MIN_RATIO <= fairness_ratio <= FAIRNESS_MAX_RATIO)
        or abs(net_diff) <= MAX_DIFF_TOLERANCE
    )

    return {
        "is_balanced": is_balanced,
        "raw_give": round(raw_give, 1),
        "raw_receive": round(raw_receive, 1),
        "eff_give": eff_give,
        "eff_receive": eff_receive,
        "fairness_ratio": round(fairness_ratio, 2),
        "net_diff": round(net_diff, 1),
        "stud_asset": stud_asset,
        "stud_side": stud_side,
    }


def make_player_asset(player_obj: Dict[str, Any], ranking_data: Dict[str, Any], alt_lookup: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Wraps a Sleeper player and ranking data into a standardized trade asset."""
    pid = player_obj.get("player_id")
    alt_data = alt_lookup.get(pid, {}) if alt_lookup else {}

    return {
        "type": "player",
        "player_id": pid,
        "name": player_obj.get("full_name") or pid,
        "position": player_obj.get("position"),
        "team": player_obj.get("team") or "FA",
        "age": player_obj.get("age"),
        "years_exp": player_obj.get("years_exp", 0),
        "market_value": ranking_data.get("market_value", 0.0),
        "rank_ecr": ranking_data.get("rank_ecr", 999.0),
        "redraft_val": alt_data.get("market_value", ranking_data.get("market_value", 0.0)),
        "redraft_ecr": alt_data.get("rank_ecr", ranking_data.get("rank_ecr", 999.0)),
        "player_obj": player_obj,
        "ranking_data": ranking_data,
    }


def make_pick_asset(
    pick_tuple: Tuple[str, int, int],
    picks_lookup: Dict[str, float],
    team_tiers: Dict[int, str],
    target_season: str = "2027",
    total_rosters: int = 12,
) -> Dict[str, Any]:
    """Wraps a draft pick tuple into a standardized trade asset with league-size scaling."""
    season, round_num, orig_roster_id = pick_tuple
    tier = project_pick_tier(orig_roster_id, team_tiers=team_tiers, season=season, target_season=target_season)
    pt_val = get_single_pick_value(season, round_num, tier, picks_lookup, total_rosters=total_rosters)

    tier_label = f" ({tier.capitalize()})" if season == target_season and round_num <= 3 else ""
    league_size_label = f" [{total_rosters}T]" if total_rosters != 12 else ""
    name = f"{season} Round {round_num}{tier_label}{league_size_label}"

    return {
        "type": "pick",
        "season": season,
        "round": round_num,
        "original_roster_id": orig_roster_id,
        "projected_tier": tier,
        "name": name,
        "market_value": pt_val,
        "total_rosters": total_rosters,
    }


def analyze_team_profile(
    roster: Dict[str, Any],
    roster_players: List[Dict[str, Any]],
    owned_picks: List[Tuple[str, int, int]],
    primary_lookup: Dict[str, Any],
    redraft_lookup: Dict[str, Any],
    picks_lookup: Dict[str, float],
    team_tiers: Dict[int, str],
    roster_positions: List[str],
    is_dynasty: bool,
    status: str,
    category: str,
    manager_name: str,
    total_rosters: int = 12,
) -> Dict[str, Any]:
    """
    Profiles a team's starters, bench depth, positional strengths/deficits, and tradeable assets.
    Accurately identifies critical deficits and league-scaled draft picks.
    """
    starters_tuples, bench_tuples = simulate_optimal_lineup(
        roster_players, primary_lookup, roster_positions, is_dynasty=is_dynasty
    )

    reserve_ids = set(roster.get("reserve") or [])
    taxi_ids = set(roster.get("taxi") or [])

    starter_assets = [make_player_asset(p, r, redraft_lookup) for p, r in starters_tuples]
    bench_assets = [
        make_player_asset(p, r, redraft_lookup)
        for p, r in bench_tuples
        if p.get("player_id") not in reserve_ids
    ]
    taxi_assets = [
        make_player_asset(p, r, redraft_lookup)
        for p, r in bench_tuples
        if p.get("player_id") in taxi_ids
    ]
    pick_assets = [
        make_pick_asset(pk, picks_lookup, team_tiers, target_season="2027", total_rosters=total_rosters)
        for pk in owned_picks
    ]
    # Sort pick assets chronologically (nearest season first, round ascending)
    pick_assets.sort(
        key=lambda pk: (int(pk["season"]) if str(pk["season"]).isdigit() else 9999, pk["round"])
    )

    # Evaluate positional counts and strengths
    positions = ["QB", "RB", "WR", "TE"]
    pos_starters = {pos: [a for a in starter_assets if a["position"] == pos] for pos in positions}
    pos_bench = {pos: [a for a in bench_assets if a["position"] == pos] for pos in positions}

    req_counts = {pos: roster_positions.count(pos) for pos in positions}
    is_superflex = "SUPER_FLEX" in roster_positions or roster_positions.count("QB") >= 2

    surpluses = []
    deficits = []
    critical_deficits = []

    for pos in positions:
        st_count = len(pos_starters[pos])
        st_min_val = min((a["market_value"] for a in pos_starters[pos]), default=0.0)
        bn_val = sum(a["market_value"] for a in pos_bench[pos])

        # Viable starting bench players (active weekly producers or high-end starters on bench)
        if pos == "QB":
            viable_bench = [a for a in pos_bench[pos] if a.get("market_value", 0) >= 2500.0 or a.get("redraft_ecr", 999) <= 24]
        elif pos == "RB":
            # Real NFL starters/key committee backs (redraft top 50, not just backup handcuffs)
            viable_bench = [a for a in pos_bench[pos] if a.get("redraft_ecr", 999) <= 50 and a.get("market_value", 0) >= 1800.0]
        elif pos == "WR":
            viable_bench = [a for a in pos_bench[pos] if a.get("redraft_ecr", 999) <= 50 and a.get("market_value", 0) >= 1800.0]
        else:  # TE
            viable_bench = [a for a in pos_bench[pos] if a.get("market_value", 0) >= 2000.0 or a.get("redraft_ecr", 999) <= 16]

        min_needed = 2 if (pos == "QB" and is_superflex) else max(1, req_counts.get(pos, 1))

        # Critical Deficit: cannot even fill starters, or bench has ZERO viable starter replacements
        if st_count < min_needed or len(viable_bench) == 0:
            critical_deficits.append(pos)
            deficits.append(pos)
        elif st_min_val < 1500.0:
            deficits.append(pos)

        # Surplus: has required starters AND startable bench depth
        if pos == "QB":
            if is_superflex and len(viable_bench) >= 1 and st_count >= 2:
                surpluses.append(pos)
            elif not is_superflex and len(viable_bench) >= 1:
                surpluses.append(pos)
        elif pos in ("RB", "WR", "TE"):
            if len(viable_bench) >= 1 and pos not in critical_deficits and bn_val >= 2500.0:
                surpluses.append(pos)

    # Distinguish veterans (age >= 27 with high redraft scoring) vs young assets (age <= 24)
    veteran_assets = [
        a for a in starter_assets + bench_assets
        if (a.get("age") or 25) >= 27 and a.get("market_value", 0) >= 1200.0
    ]
    young_assets = [
        a for a in bench_assets + taxi_assets
        if (a.get("age") or 25) <= 24 and a.get("market_value", 0) >= 1000.0
    ]

    return {
        "roster_id": roster["roster_id"],
        "owner_id": roster.get("owner_id"),
        "manager_name": manager_name,
        "status": status,
        "category": category,
        "starter_assets": starter_assets,
        "bench_assets": bench_assets,
        "taxi_assets": taxi_assets,
        "pick_assets": pick_assets,
        "pos_starters": pos_starters,
        "pos_bench": pos_bench,
        "surpluses": surpluses,
        "deficits": deficits,
        "critical_deficits": critical_deficits,
        "veteran_assets": veteran_assets,
        "young_assets": young_assets,
    }


def check_lineup_and_deficit_viability(
    user_profile: Dict[str, Any],
    give_assets: List[Dict[str, Any]],
    receive_assets: List[Dict[str, Any]],
    primary_lookup: Optional[Dict[str, Any]] = None,
    roster_positions: Optional[List[str]] = None,
    is_dynasty: bool = True,
) -> Tuple[bool, str]:
    """
    Validates:
    1. Deficit Protection: Cannot give away a starter from a critical deficit position
       unless receiving an equal-or-better player at that same position.
    2. Lineup Improvement: For contenders/neutrals, incoming player must crack the starting lineup
       or the new starting lineup total value must not decline.
    """
    critical_deficits = set(user_profile.get("critical_deficits", []))
    starter_pids = {a["player_id"] for a in user_profile["starter_assets"]}

    user_cat = user_profile.get("category", "neutral")

    # 1. Deficit Protection Check
    # Strictly enforced for Contenders and Middle-of-the-pack teams!
    # Rebuilders ARE allowed to trade away older starters (e.g. Derrick Henry, Josh Jacobs) for draft capital & youth.
    if user_cat in ("win", "neutral"):
        for ga in give_assets:
            if ga.get("type") == "player":
                pid = ga["player_id"]
                pos = ga.get("position")
                if pid in starter_pids and pos in critical_deficits:
                    matching_recv = [
                        ra for ra in receive_assets
                        if ra.get("type") == "player" and ra.get("position") == pos
                        and ra.get("market_value", 0) >= ga.get("market_value", 0) * 0.90
                    ]
                    if not matching_recv:
                        return False, f"Cannot trade starter {ga['name']} from deficit position {pos} without receiving an equivalent starter at {pos}."

    # 2. Starting Lineup Impact Check
    if primary_lookup and roster_positions:
        current_players = [
            a["player_obj"] for a in user_profile["starter_assets"] + user_profile["bench_assets"]
            if a.get("player_obj")
        ]
        give_pids = {ga["player_id"] for ga in give_assets if ga.get("type") == "player"}
        recv_players = [
            ra["player_obj"] for ra in receive_assets
            if ra.get("type") == "player" and ra.get("player_obj")
        ]

        if recv_players or give_pids:
            new_players = [p for p in current_players if p.get("player_id") not in give_pids] + recv_players

            old_starters, _ = simulate_optimal_lineup(current_players, primary_lookup, roster_positions, is_dynasty=is_dynasty)
            new_starters, _ = simulate_optimal_lineup(new_players, primary_lookup, roster_positions, is_dynasty=is_dynasty)

            old_starter_val = sum(r.get("market_value", 0.0) for _, r in old_starters)
            new_starter_val = sum(r.get("market_value", 0.0) for _, r in new_starters)
            new_starter_pids = {p.get("player_id") for p, _ in new_starters}

            recv_makes_lineup = any(
                ra.get("player_id") in new_starter_pids
                for ra in receive_assets if ra.get("type") == "player"
            )

            giving_starter = any(ga.get("player_id") in starter_pids for ga in give_assets if ga.get("type") == "player")
            giving_top_pick = any(ga.get("type") == "pick" and ga.get("round", 99) <= 2 for ga in give_assets)

            if user_cat in ("win", "neutral"):
                if giving_starter and not recv_makes_lineup:
                    return False, "Giving up a starter, but no incoming player cracks the starting lineup."
                if giving_starter and new_starter_val < old_starter_val * 0.95:
                    return False, f"Trade degrades starting lineup strength (was {old_starter_val:,.0f}, becomes {new_starter_val:,.0f})."
                if giving_top_pick and not recv_makes_lineup:
                    return False, "Contender spending Round 1/2 pick on a player who sits on the bench."

    return True, ""


def get_pick_proximity_bonus(assets: List[Dict[str, Any]]) -> float:
    """Awards higher synergy to proposals using nearer draft picks (2027 > 2028 > 2029)."""
    bonus = 0.0
    for a in assets:
        if a.get("type") == "pick":
            season = str(a.get("season", "9999"))
            if season == "2027":
                bonus += 6.0
            elif season == "2028":
                bonus += 3.0
            elif season == "2029":
                bonus += 0.5
    return bonus


def generate_trade_suggestions(
    user_roster_id: int,
    user_profile: Dict[str, Any],
    other_profiles: List[Dict[str, Any]],
    is_dynasty: bool,
    primary_lookup: Optional[Dict[str, Any]] = None,
    roster_positions: Optional[List[str]] = None,
    max_suggestions: int = 3,
) -> List[Dict[str, Any]]:
    """
    Synthesizes high-conviction trade proposals for the user.
    Evaluates:
    1. Contender <-> Rebuilder win-now / pick accumulation trades.
    2. 2-for-1 consolidation trades for contenders.
    3. Surplus bench depth for future picks.
    4. Positional surplus <-> deficit swaps.
    """
    proposals = []
    user_cat = user_profile["category"]

    for partner in other_profiles:
        if partner["roster_id"] == user_roster_id:
            continue

        partner_cat = partner["category"]
        manager_name = partner["manager_name"]

        # -------------------------------------------------------------
        # Archetype 1: Star Acquisition (Consolidation Upgrade)
        # Contender or Neutral team with depth/picks buying a Stud
        # -------------------------------------------------------------
        if user_cat in ("win", "neutral"):
            # Target elite starters on Rebuilding or Neutral teams (or any team in Redraft)
            if not is_dynasty or partner_cat in ("rebuild", "neutral"):
                min_stud_val = 3200.0 if is_dynasty else 3000.0
                min_piece_val = 900.0 if is_dynasty else 500.0
                max_piece_val = 6500.0 if is_dynasty else 6500.0

                partner_studs = [
                    a for a in partner["starter_assets"]
                    if a["market_value"] >= min_stud_val
                ]
                user_picks = [pk for pk in user_profile["pick_assets"] if pk["round"] <= 2] if is_dynasty else []
                user_picks.sort(key=lambda pk: (int(pk["season"]) if str(pk["season"]).isdigit() else 9999, pk["round"]))

                user_pieces = [
                    a for a in user_profile["bench_assets"] + user_profile["starter_assets"]
                    if min_piece_val <= a["market_value"] <= max_piece_val
                ]

                for stud in partner_studs:
                    # Option A: Player + Pick for Stud (Dynasty only)
                    if is_dynasty and user_picks:
                        # In redraft, guard against low-value producers; in dynasty, high market value is key
                        if not is_dynasty and stud.get("redraft_ecr", 999) > 60:
                            continue

                        for pk in user_picks:
                            for p in user_pieces:
                                # Contender must not trade for a player with worse redraft ranking if giving a top producer
                                if not is_dynasty and stud.get("redraft_ecr", 999) >= p.get("redraft_ecr", 999):
                                    continue

                                give = [pk, p]
                                recv = [stud]

                                eval_result = evaluate_trade_fairness(give, recv)
                                if not eval_result["is_balanced"]:
                                    continue

                                is_viable, reason = check_lineup_and_deficit_viability(
                                    user_profile, give, recv, primary_lookup, roster_positions, is_dynasty
                                )
                                if not is_viable:
                                    continue

                                max_val = max(max(a.get("market_value", 0) for a in give), max(a.get("market_value", 0) for a in recv))
                                tier = "Blockbuster" if max_val >= 4500.0 else ("Starter Upgrade" if max_val >= 2500.0 else "Depth & Capital")

                                prox_bonus = get_pick_proximity_bonus(give) + get_pick_proximity_bonus(recv)
                                proposals.append({
                                    "archetype": "🏆 Championship Push (Star Upgrade)",
                                    "tier": tier,
                                    "partner_name": manager_name,
                                    "partner_status": partner["status"],
                                    "partner_category": partner_cat,
                                    "give_assets": give,
                                    "receive_assets": recv,
                                    "eval_result": eval_result,
                                    "why": (
                                        f"You consolidate depth ({p['name']}) and draft capital ({pk['name']}) to acquire elite win-now starter {stud['name']}; "
                                        f"{manager_name} accelerates their timeline with premium pick capital and a productive young asset."
                                    ),
                                    "synergy_score": 96 + prox_bonus - abs(eval_result["net_diff"]) / 50.0,
                                })
                                break

                    # Option B: 2-for-1 Depth Package for Stud (Dynasty & Redraft)
                    for i in range(len(user_pieces)):
                        for j in range(i + 1, len(user_pieces)):
                            p1, p2 = user_pieces[i], user_pieces[j]
                            give = [p1, p2]
                            recv = [stud]

                            eval_result = evaluate_trade_fairness(give, recv)
                            if not eval_result["is_balanced"]:
                                continue

                            is_viable, reason = check_lineup_and_deficit_viability(
                                user_profile, give, recv, primary_lookup, roster_positions, is_dynasty
                            )
                            if not is_viable:
                                continue

                            max_val = max(max(a.get("market_value", 0) for a in give), max(a.get("market_value", 0) for a in recv))
                            tier = "Blockbuster" if max_val >= 4500.0 else ("Starter Upgrade" if max_val >= 2500.0 else "Depth & Capital")

                            proposals.append({
                                "archetype": "⭐ 2-for-1 Star Consolidation",
                                "tier": tier,
                                "partner_name": manager_name,
                                "partner_status": partner["status"],
                                "partner_category": partner_cat,
                                "give_assets": give,
                                "receive_assets": recv,
                                "eval_result": eval_result,
                                "why": (
                                    f"You package two quality assets ({p1['name']} + {p2['name']}) for a top-tier difference-maker ({stud['name']}); "
                                    f"{manager_name} addresses multiple starting lineup holes across their roster."
                                ),
                                "synergy_score": 91 - abs(eval_result["net_diff"]) / 50.0,
                            })
                            break

        # -------------------------------------------------------------
        # Archetype 2: Surplus Bench Depth or Rebuilder Veterans for Future Picks
        # Selling quality depth or veterans to Contenders for draft capital
        # -------------------------------------------------------------
        if is_dynasty and partner_cat == "win":
            sellable_players = [
                a for a in user_profile["bench_assets"] + user_profile["veteran_assets"]
                if a["market_value"] >= 1000.0
            ]
            partner_picks = [
                pk for pk in partner["pick_assets"]
                if pk["round"] <= 3 and pk["market_value"] >= 900.0
            ]
            partner_picks.sort(key=lambda pk: (int(pk["season"]) if str(pk["season"]).isdigit() else 9999, pk["round"]))

            for p in sellable_players:
                for pk in partner_picks:
                    give = [p]
                    recv = [pk]
                    eval_result = evaluate_trade_fairness(give, recv)
                    if not eval_result["is_balanced"]:
                        continue

                    is_viable, reason = check_lineup_and_deficit_viability(
                        user_profile, give, recv, primary_lookup, roster_positions, is_dynasty
                    )
                    if not is_viable:
                        continue

                    max_val = max(max(a.get("market_value", 0) for a in give), max(a.get("market_value", 0) for a in recv))
                    tier = "Blockbuster" if max_val >= 4500.0 else ("Starter Upgrade" if max_val >= 2500.0 else "Depth & Capital")

                    prox_bonus = get_pick_proximity_bonus(give) + get_pick_proximity_bonus(recv)
                    proposals.append({
                        "archetype": "🌱 Capital Harvest (Depth for Draft Pick)",
                        "tier": tier,
                        "partner_name": manager_name,
                        "partner_status": partner["status"],
                        "partner_category": partner_cat,
                        "give_assets": give,
                        "receive_assets": recv,
                        "eval_result": eval_result,
                        "why": (
                            f"You monetize surplus depth ({p['name']}) to secure {pk['name']}; "
                            f"{manager_name} strengthens their active lineup/depth for a championship push."
                        ),
                        "synergy_score": 92 + prox_bonus - abs(eval_result["net_diff"]) / 50.0,
                    })
                    break

        # -------------------------------------------------------------
        # Archetype 3: Positional Rebalancing (1-for-1 Swap)
        # -------------------------------------------------------------
        pos_min = 1000.0 if is_dynasty else 800.0
        pos_max = 9500.0 if is_dynasty else 8500.0
        if user_profile["surpluses"]:
            for user_pos in user_profile["surpluses"]:
                my_pos_assets = [
                    a for a in user_profile["pos_bench"][user_pos] + user_profile["pos_starters"][user_pos]
                    if pos_min <= a["market_value"] <= pos_max
                ]
                # Look for partner's surplus in another position
                for other_pos in ["QB", "RB", "WR", "TE"]:
                    if other_pos == user_pos:
                        continue
                    their_pos_assets = [
                        a for a in partner["pos_bench"][other_pos] + partner["pos_starters"][other_pos]
                        if pos_min <= a["market_value"] <= pos_max
                    ]

                    for my_p in my_pos_assets[:3]:
                        for their_p in their_pos_assets[:3]:
                            give = [my_p]
                            recv = [their_p]
                            eval_result = evaluate_trade_fairness(give, recv)
                            if not eval_result["is_balanced"]:
                                continue

                            is_viable, reason = check_lineup_and_deficit_viability(
                                user_profile, give, recv, primary_lookup, roster_positions, is_dynasty
                            )
                            if not is_viable:
                                continue

                            max_val = max(max(a.get("market_value", 0) for a in give), max(a.get("market_value", 0) for a in recv))
                            tier = "Blockbuster" if max_val >= 4500.0 else ("Starter Upgrade" if max_val >= 2500.0 else "Depth & Capital")

                            proposals.append({
                                "archetype": "🔄 Positional Rebalancing (1-for-1 Swap)",
                                "tier": tier,
                                "partner_name": manager_name,
                                "partner_status": partner["status"],
                                "partner_category": partner_cat,
                                "give_assets": give,
                                "receive_assets": recv,
                                "eval_result": eval_result,
                                "why": (
                                    f"You exchange surplus at {user_pos} ({my_p['name']}) to acquire {other_pos} starter {their_p['name']}; "
                                    f"{manager_name} rebalances their depth across positions."
                                ),
                                "synergy_score": 88 - abs(eval_result["net_diff"]) / 50.0,
                            })
                            break

        # -------------------------------------------------------------
        # Archetype 4: Rebuilder Veteran Liquidation (Blockbuster for Premium Capital)
        # -------------------------------------------------------------
        if is_dynasty and user_cat == "rebuild" and partner_cat in ("win", "neutral"):
            valuable_vets = [
                a for a in user_profile.get("veteran_assets", [])
                if a.get("market_value", 0) >= 3000.0
            ]
            partner_firsts = [
                pk for pk in partner.get("pick_assets", [])
                if pk.get("round") == 1
            ]
            partner_young_assets = [
                a for a in partner.get("bench_assets", []) + partner.get("starter_assets", [])
                if (a.get("age") or 30) <= 25 and 1500.0 <= a.get("market_value", 0) <= 6500.0
            ]

            for vet in valuable_vets:
                # Option A: Vet for 1st Round Pick + Young Asset
                for pk in partner_firsts:
                    for ya in partner_young_assets:
                        give = [vet]
                        recv = [pk, ya]
                        eval_result = evaluate_trade_fairness(give, recv)
                        if not eval_result["is_balanced"]:
                            continue

                        prox_bonus = get_pick_proximity_bonus(recv)
                        proposals.append({
                            "archetype": "💎 Franchise Pivot (Veteran for 1st + Youth)",
                            "tier": "Blockbuster",
                            "partner_name": manager_name,
                            "partner_status": partner["status"],
                            "partner_category": partner_cat,
                            "give_assets": give,
                            "receive_assets": recv,
                            "eval_result": eval_result,
                            "why": (
                                f"You trade established star {vet['name']} ({vet['market_value']:,.0f} pts) at peak value; "
                                f"you receive foundation capital ({pk['name']}) plus rising talent {ya['name']} to accelerate your rebuild."
                            ),
                            "synergy_score": 97 + prox_bonus - abs(eval_result["net_diff"]) / 50.0,
                        })
                        break
                    if any(p["give_assets"] == [vet] for p in proposals if p.get("tier") == "Blockbuster"):
                        break

    # Deduplicate and ensure balanced diversity across tiers (Blockbuster, Starter Upgrade, Depth)
    used_player_names = set()
    used_partners = set()
    diverse_proposals = []

    # Partition candidate proposals by tier
    blockbusters = [p for p in proposals if p.get("tier") == "Blockbuster"]
    upgrades = [p for p in proposals if p.get("tier") == "Starter Upgrade"]
    depth_swaps = [p for p in proposals if p.get("tier") == "Depth & Capital"]

    for group in (blockbusters, upgrades, depth_swaps):
        group.sort(key=lambda x: -x["synergy_score"])

    # Collect balanced selections: up to 3 blockbusters, 3 upgrades, 3 depth swaps
    tier_targets = [
        (blockbusters, 3),
        (upgrades, 3),
        (depth_swaps, 2),
    ]

    for tier_pool, target_count in tier_targets:
        count = 0
        for p in tier_pool:
            partner_name = p["partner_name"]
            player_gives = {a["name"] for a in p["give_assets"] if a["type"] == "player"}
            if partner_name not in used_partners and not (player_gives & used_player_names):
                diverse_proposals.append(p)
                used_partners.add(partner_name)
                used_player_names.update(player_gives)
                count += 1
                if count >= target_count or len(diverse_proposals) >= max_suggestions:
                    break

    # Backfill if we haven't reached max_suggestions
    all_sorted = sorted(proposals, key=lambda x: -x["synergy_score"])
    if len(diverse_proposals) < max_suggestions:
        for p in all_sorted:
            if p not in diverse_proposals:
                diverse_proposals.append(p)
            if len(diverse_proposals) >= max_suggestions:
                break

    return diverse_proposals



def format_asset_str(asset: Dict[str, Any]) -> str:
    """Formats a single player or pick asset for the trade proposal printout."""
    val = asset.get("market_value", 0.0)
    if asset["type"] == "pick":
        return f"{asset['name']} ({val:,.0f} pts)"

    pos = asset.get("position", "")
    name = asset.get("name", "Unknown")
    redraft = asset.get("redraft_ecr")
    redraft_str = f" | Redraft #{redraft:.0f}" if redraft and redraft < 999 else ""

    return f"{name} ({pos} — {val:,.0f} pts{redraft_str})"


def build_positional_room_leaderboard(
    all_team_profiles: List[Dict[str, Any]], 
    use_redraft: bool = False,
    roster_positions: Optional[List[str]] = None,
    *args,
    **kwargs,
) -> List[Dict[str, Any]]:
    """
    Ranks all teams side-by-side across QB Room, RB Room, WR Room, TE Room, and Draft Capital.
    Computes room valuations using a Starter-Weighted Diminishing Utility Curve to reflect
    true lineup utility and eliminate roster bloat / hoarding distortions.

    Curve structure based on starting requirements S:
      - Tier 1: Starters (slots 1 to S) -> 100% weight (matchup scoring drivers)
      - Tier 2: Primary Backups (next 1-2 slots) -> 50% weight (bye week / injury flex)
      - Tier 3: Developmental Depth (next 1-2 slots) -> 20% weight (stashes & handcuffs)
      - Tier 4: Roster Bloat / Hoard (beyond depth) -> 5% weight (anti-hoarding discount)

    When use_redraft=True:
      - Uses 3-pillar Redraft / ROS consensus values for players
      - Excludes draft capital (future picks have 0 single-season ROS value)
    """
    # Determine starter requirements per position
    if roster_positions:
        is_sf = ("SUPER_FLEX" in roster_positions) or (roster_positions.count("QB") >= 2)
        s_qb = 2 if is_sf else max(1, roster_positions.count("QB"))
        s_rb = max(2, roster_positions.count("RB"))
        s_wr = max(3, roster_positions.count("WR"))
        s_te = max(1, roster_positions.count("TE"))
    else:
        max_qb_st = max((len(p.get("pos_starters", {}).get("QB", [])) for p in all_team_profiles), default=2)
        s_qb = max(1, max_qb_st)
        s_rb = max((len(p.get("pos_starters", {}).get("RB", [])) for p in all_team_profiles), default=2)
        s_wr = max((len(p.get("pos_starters", {}).get("WR", [])) for p in all_team_profiles), default=3)
        s_te = max((len(p.get("pos_starters", {}).get("TE", [])) for p in all_team_profiles), default=1)

    room_data = []
    for p in all_team_profiles:
        rid = p["roster_id"]
        mgr = p.get("manager_name", f"Team {rid}")
        all_players = p.get("starter_assets", []) + p.get("bench_assets", []) + p.get("taxi_assets", [])

        def _get_val(a):
            if use_redraft:
                return float(a.get("redraft_val") if a.get("redraft_val") is not None else a.get("market_value", 0.0))
            return float(a.get("market_value", 0.0))

        qb_players = sorted([a for a in all_players if a.get("position") == "QB"], key=_get_val, reverse=True)
        rb_players = sorted([a for a in all_players if a.get("position") == "RB"], key=_get_val, reverse=True)
        wr_players = sorted([a for a in all_players if a.get("position") == "WR"], key=_get_val, reverse=True)
        te_players = sorted([a for a in all_players if a.get("position") == "TE"], key=_get_val, reverse=True)
        picks = [] if use_redraft else p.get("pick_assets", [])

        def _compute_room(players_sorted, s_req, pos_type):
            tier2_count = 1 if pos_type in ("QB", "TE") else 2
            tier3_count = 1 if pos_type in ("QB", "TE") else 2
            t1_cutoff = s_req
            t2_cutoff = s_req + tier2_count
            t3_cutoff = t2_cutoff + tier3_count

            eff_val = 0.0
            raw_val = 0.0
            starter_val = 0.0
            bench_eff_val = 0.0

            for idx, player in enumerate(players_sorted):
                v = _get_val(player)
                raw_val += v
                if idx < t1_cutoff:
                    weight = 1.00
                    starter_val += v
                elif idx < t2_cutoff:
                    weight = 0.50
                elif idx < t3_cutoff:
                    weight = 0.20
                else:
                    weight = 0.05

                w_contrib = v * weight
                eff_val += w_contrib
                if idx >= t1_cutoff:
                    bench_eff_val += w_contrib

            return eff_val, raw_val, starter_val, bench_eff_val

        qb_val, qb_raw, qb_st, qb_bn = _compute_room(qb_players, s_qb, "QB")
        rb_val, rb_raw, rb_st, rb_bn = _compute_room(rb_players, s_rb, "RB")
        wr_val, wr_raw, wr_st, wr_bn = _compute_room(wr_players, s_wr, "WR")
        te_val, te_raw, te_st, te_bn = _compute_room(te_players, s_te, "TE")

        picks_val = sum(float(pk.get("market_value", 0.0)) for pk in picks) if not use_redraft else 0.0
        tot_val = qb_val + rb_val + wr_val + te_val + picks_val
        tot_raw_val = qb_raw + rb_raw + wr_raw + te_raw + picks_val

        room_data.append({
            "roster_id": rid,
            "manager_name": mgr,
            # Effective Starter-Weighted Values (used for room rankings)
            "qb_val": qb_val,
            "rb_val": rb_val,
            "wr_val": wr_val,
            "te_val": te_val,
            "picks_val": picks_val,
            "total_val": tot_val,
            # Raw and starter breakdown metrics for transparency
            "qb_raw_val": qb_raw,
            "rb_raw_val": rb_raw,
            "wr_raw_val": wr_raw,
            "te_raw_val": te_raw,
            "raw_total_val": tot_raw_val,
            "qb_starter_val": qb_st,
            "rb_starter_val": rb_st,
            "wr_starter_val": wr_st,
            "te_starter_val": te_st,
            "qb_bench_eff": qb_bn,
            "rb_bench_eff": rb_bn,
            "wr_bench_eff": wr_bn,
            "te_bench_eff": te_bn,
            "top_qbs": [a.get("name", "") for a in qb_players[:3]],
            "top_rbs": [a.get("name", "") for a in rb_players[:3]],
            "top_wrs": [a.get("name", "") for a in wr_players[:3]],
            "top_tes": [a.get("name", "") for a in te_players[:3]],
            "top_picks": [pk.get("name", "") for pk in picks[:3]] if not use_redraft else [],
        })

    def assign_ranks(key, rank_field):
        sorted_by_key = sorted(room_data, key=lambda x: x[key], reverse=True)
        for idx, item in enumerate(sorted_by_key, 1):
            item[rank_field] = idx

    assign_ranks("total_val", "total_rank")
    assign_ranks("qb_val", "qb_rank")
    assign_ranks("rb_val", "rb_rank")
    assign_ranks("wr_val", "wr_rank")
    assign_ranks("te_val", "te_rank")
    if not use_redraft:
        assign_ranks("picks_val", "picks_rank")
    else:
        for item in room_data:
            item["picks_rank"] = 0

    return room_data

