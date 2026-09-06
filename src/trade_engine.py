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
                min_stud_val = 3200.0 if is_dynasty else 3500.0
                min_piece_val = 1100.0 if is_dynasty else 500.0
                max_piece_val = 3200.0 if is_dynasty else 5500.0

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
                        # For Championship Push: stud MUST be an established win-now point producer!
                        if stud.get("redraft_ecr", 999) > 40:
                            continue

                        for pk in user_picks:
                            for p in user_pieces:
                                # Contender must not trade for a player with worse redraft ranking than given player
                                if stud.get("redraft_ecr", 999) >= p.get("redraft_ecr", 999):
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

                                prox_bonus = get_pick_proximity_bonus(give) + get_pick_proximity_bonus(recv)
                                proposals.append({
                                    "archetype": "🏆 Championship Push (Star Upgrade)",
                                    "partner_name": manager_name,
                                    "partner_status": partner["status"],
                                    "partner_category": partner_cat,
                                    "give_assets": give,
                                    "receive_assets": recv,
                                    "eval_result": eval_result,
                                    "why": (
                                        f"You consolidate depth ({p['name']}) and draft capital ({pk['name']}) to acquire elite win-now starter {stud['name']} (Redraft #{stud.get('redraft_ecr', 999):.0f}); "
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

                            proposals.append({
                                "archetype": "⭐ 2-for-1 Star Consolidation",
                                "partner_name": manager_name,
                                "partner_status": partner["status"],
                                "partner_category": partner_cat,
                                "give_assets": give,
                                "receive_assets": recv,
                                "eval_result": eval_result,
                                "why": (
                                    f"You package two quality depth assets ({p1['name']} + {p2['name']}) for a top-tier difference-maker ({stud['name']}); "
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
                if a["market_value"] >= 1200.0
            ]
            partner_picks = [
                pk for pk in partner["pick_assets"]
                if pk["round"] <= 3 and pk["market_value"] >= 1100.0
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

                    prox_bonus = get_pick_proximity_bonus(give) + get_pick_proximity_bonus(recv)
                    proposals.append({
                        "archetype": "🌱 Capital Harvest (Depth for Draft Pick)",
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
        pos_min = 1200.0 if is_dynasty else 800.0
        pos_max = 3500.0 if is_dynasty else 6500.0
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

                    for my_p in my_pos_assets[:2]:
                        for their_p in their_pos_assets[:2]:
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

                            proposals.append({
                                "archetype": "🔄 Positional Rebalancing (1-for-1 Swap)",
                                "partner_name": manager_name,
                                "partner_status": partner["status"],
                                "partner_category": partner_cat,
                                "give_assets": give,
                                "receive_assets": recv,
                                "eval_result": eval_result,
                                "why": (
                                    f"You exchange surplus depth at {user_pos} ({my_p['name']}) to acquire {other_pos} starter {their_p['name']}; "
                                    f"{manager_name} rebalances their depth across positions."
                                ),
                                "synergy_score": 88 - abs(eval_result["net_diff"]) / 50.0,
                            })
                            break

    # Deduplicate and ensure diversity in trade proposals
    # (avoid recommending the exact same player in all 3 trades)
    used_player_names = set()
    used_partners = set()
    diverse_proposals = []

    sorted_proposals = sorted(proposals, key=lambda x: -x["synergy_score"])

    # 1. First pass: distinct partners and distinct players offered
    for p in sorted_proposals:
        partner_name = p["partner_name"]
        player_gives = {a["name"] for a in p["give_assets"] if a["type"] == "player"}

        if partner_name not in used_partners and not (player_gives & used_player_names):
            diverse_proposals.append(p)
            used_partners.add(partner_name)
            used_player_names.update(player_gives)

        if len(diverse_proposals) >= max_suggestions:
            break

    # 2. Second pass: fill remaining slots if any
    if len(diverse_proposals) < max_suggestions:
        for p in sorted_proposals:
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
