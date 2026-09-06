"""
trade_finder.py

Interactive Targeted Trade Finder for Fantasy Dynasty Manager.
Allows users to target specific players or draft picks to buy (--trade-for)
or find optimal league trade partners to sell assets (--trade-away).

Implements:
- Asset resolution (fuzzy player matching and draft pick parsing).
- 3-package tailored proposal generation (1-for-1, 2-for-1 consolidation, draft capital).
- Model 3 consensus evaluation with +15% stud bonus & diminishing package weights.
- Deficit protection & competitive window alignment.
"""

import re
from typing import Dict, List, Tuple, Any, Optional
from src.trade_engine import (
    evaluate_trade_fairness,
    check_lineup_and_deficit_viability,
    get_pick_proximity_bonus,
    format_asset_str,
)


def resolve_asset_from_query(
    query: str,
    all_profiles: List[Dict[str, Any]],
    is_dynasty: bool = True,
) -> Dict[str, Any]:
    """
    Parses a user query into a player or draft pick asset, and identifies
    which team(s) own the asset.
    Returns:
      {
        "type": "player" | "pick",
        "asset": asset_dict,
        "owners": [ { "profile": prof, "asset": asset } ],
        "found": bool,
        "query": query,
      }
    """
    q = query.strip().lower()

    # 1. Check if query matches a draft pick (e.g., '2027 1st', '2028 round 2', '2027 late 1st')
    pick_match = re.search(r"(202\d)\s*(?:round\s*|r)?\s*([1-4])(?:st|nd|rd|th)?", q)
    if is_dynasty and pick_match:
        season = pick_match.group(1)
        rnd = int(pick_match.group(2))

        owners = []
        sample_asset = None
        for prof in all_profiles:
            for pk in prof.get("pick_assets", []):
                if str(pk.get("season")) == str(season) and pk.get("round") == rnd:
                    owners.append({"profile": prof, "asset": pk})
                    if sample_asset is None:
                        sample_asset = pk

        if owners:
            return {
                "type": "pick",
                "asset": sample_asset,
                "owners": owners,
                "found": True,
                "query": query,
            }

    # 2. Search across player assets in all team profiles
    matching_owners = []
    sample_asset = None

    for prof in all_profiles:
        all_players = prof.get("starter_assets", []) + prof.get("bench_assets", [])
        for p in all_players:
            p_name = p.get("name", "").lower()
            # Exact match or substring match
            if q == p_name or q in p_name:
                matching_owners.append({"profile": prof, "asset": p})
                if sample_asset is None or q == p_name:
                    sample_asset = p

    if matching_owners:
        return {
            "type": "player",
            "asset": sample_asset,
            "owners": matching_owners,
            "found": True,
            "query": query,
        }

    return {
        "type": "unknown",
        "asset": None,
        "owners": [],
        "found": False,
        "query": query,
    }


def find_targeted_buy_trades(
    target_asset: Dict[str, Any],
    owner_profile: Dict[str, Any],
    user_profile: Dict[str, Any],
    primary_lookup: Dict[str, Any],
    roster_positions: List[str],
    is_dynasty: bool,
    max_proposals: int = 3,
) -> List[Dict[str, Any]]:
    """
    Generates tailored trade offers from the user's roster/picks to acquire target_asset from owner_profile.
    Explores:
      1. 1-for-1 Fair Swap (positional need or strategic match).
      2. 2-for-1 Consolidation (Depth player + Pick or 2 depth players).
      3. Pure Draft Capital Package (Dynasty picks).
    """
    proposals = []
    user_cat = user_profile.get("category", "neutral")
    partner_cat = owner_profile.get("category", "neutral")
    partner_name = owner_profile.get("manager_name", f"Team {owner_profile['roster_id']}")

    user_players = user_profile.get("bench_assets", []) + user_profile.get("starter_assets", [])
    user_picks = sorted(
        user_profile.get("pick_assets", []),
        key=lambda pk: (int(pk["season"]) if str(pk["season"]).isdigit() else 9999, pk["round"]),
    )

    # -------------------------------------------------------------
    # Option 1: 1-for-1 Fair Swap
    # -------------------------------------------------------------
    for p in user_players:
        give = [p]
        recv = [target_asset]
        eval_res = evaluate_trade_fairness(give, recv)
        if not eval_res["is_balanced"]:
            continue

        is_viable, _ = check_lineup_and_deficit_viability(
            user_profile, give, recv, primary_lookup, roster_positions, is_dynasty
        )
        if not is_viable:
            continue

        # If user is contender, don't swap for a worse redraft producer
        if user_cat in ("win", "neutral") and target_asset.get("type") == "player" and p.get("type") == "player":
            if target_asset.get("redraft_ecr", 999) > p.get("redraft_ecr", 999) + 15:
                continue

        proposals.append({
            "archetype": "⚖️ Fair 1-for-1 Positional Swap",
            "partner_name": partner_name,
            "partner_status": owner_profile["status"],
            "partner_category": partner_cat,
            "give_assets": give,
            "receive_assets": recv,
            "eval_result": eval_res,
            "why": (
                f"Direct 1-for-1 swap exchanging {p['name']} for {target_asset['name']}. "
                f"Balances positional needs with Model 3 fairness ({eval_res['fairness_ratio']*100:.0f}% value match)."
            ),
            "score": 95 - abs(eval_res["net_diff"]) / 50.0,
        })
        break

    # -------------------------------------------------------------
    # Option 2: 2-for-1 Consolidation (Player + Pick OR 2 Players)
    # -------------------------------------------------------------
    # Try Player + Pick first (Dynasty)
    if is_dynasty and user_picks:
        for pk in user_picks:
            if pk.get("round", 9) > 3:
                continue
            for p in user_players:
                if p.get("market_value", 0) < 1000.0:
                    continue
                give = [pk, p]
                recv = [target_asset]
                eval_res = evaluate_trade_fairness(give, recv)
                if not eval_res["is_balanced"]:
                    continue

                is_viable, _ = check_lineup_and_deficit_viability(
                    user_profile, give, recv, primary_lookup, roster_positions, is_dynasty
                )
                if not is_viable:
                    continue

                prox_bonus = get_pick_proximity_bonus(give)
                proposals.append({
                    "archetype": "⭐ Player + Pick Consolidation",
                    "partner_name": partner_name,
                    "partner_status": owner_profile["status"],
                    "partner_category": partner_cat,
                    "give_assets": give,
                    "receive_assets": recv,
                    "eval_result": eval_res,
                    "why": (
                        f"Consolidates depth player {p['name']} with draft capital {pk['name']} to secure {target_asset['name']}. "
                        f"Provides {partner_name} with both immediate production and future rebuilding capital."
                    ),
                    "score": 92 + prox_bonus - abs(eval_res["net_diff"]) / 50.0,
                })
                break
            if len(proposals) >= 2:
                break

    # If still need proposals, try 2 Players for Target
    if len(proposals) < max_proposals:
        bench_candidates = [p for p in user_players if p.get("market_value", 0) >= 800.0]
        for i in range(len(bench_candidates)):
            for j in range(i + 1, len(bench_candidates)):
                p1, p2 = bench_candidates[i], bench_candidates[j]
                give = [p1, p2]
                recv = [target_asset]
                eval_res = evaluate_trade_fairness(give, recv)
                if not eval_res["is_balanced"]:
                    continue

                is_viable, _ = check_lineup_and_deficit_viability(
                    user_profile, give, recv, primary_lookup, roster_positions, is_dynasty
                )
                if not is_viable:
                    continue

                proposals.append({
                    "archetype": "📦 2-for-1 Depth Consolidation",
                    "partner_name": partner_name,
                    "partner_status": owner_profile["status"],
                    "partner_category": partner_cat,
                    "give_assets": give,
                    "receive_assets": recv,
                    "eval_result": eval_res,
                    "why": (
                        f"Packages two quality contributors ({p1['name']} + {p2['name']}) for {target_asset['name']}, "
                        f"helping {partner_name} fill multiple starting spots while upgrading your starting ceiling."
                    ),
                    "score": 88 - abs(eval_res["net_diff"]) / 50.0,
                })
                break
            if len(proposals) >= 2:
                break

    # -------------------------------------------------------------
    # Option 3: Pure Draft Capital Package (Dynasty)
    # -------------------------------------------------------------
    if is_dynasty and len(proposals) < max_proposals and user_picks:
        # Try 1 pick alone
        for pk in user_picks:
            give = [pk]
            recv = [target_asset]
            eval_res = evaluate_trade_fairness(give, recv)
            if eval_res["is_balanced"]:
                prox_bonus = get_pick_proximity_bonus(give)
                proposals.append({
                    "archetype": "🎟️ Draft Capital Acquisition",
                    "partner_name": partner_name,
                    "partner_status": owner_profile["status"],
                    "partner_category": partner_cat,
                    "give_assets": give,
                    "receive_assets": recv,
                    "eval_result": eval_res,
                    "why": (
                        f"Straightforward draft capital purchase giving {pk['name']} for {target_asset['name']}. "
                        f"Ideal for partners looking to accumulate future draft picks."
                    ),
                    "score": 90 + prox_bonus - abs(eval_res["net_diff"]) / 50.0,
                })
                break

        # Try 2 picks package
        if len(proposals) < max_proposals and len(user_picks) >= 2:
            for i in range(len(user_picks)):
                for j in range(i + 1, len(user_picks)):
                    pk1, pk2 = user_picks[i], user_picks[j]
                    give = [pk1, pk2]
                    recv = [target_asset]
                    eval_res = evaluate_trade_fairness(give, recv)
                    if not eval_res["is_balanced"]:
                        continue

                    prox_bonus = get_pick_proximity_bonus(give)
                    proposals.append({
                        "archetype": "🎟️ Multi-Pick Package",
                        "partner_name": partner_name,
                        "partner_status": owner_profile["status"],
                        "partner_category": partner_cat,
                        "give_assets": give,
                        "receive_assets": recv,
                        "eval_result": eval_res,
                        "why": (
                            f"Multi-pick draft capital package ({pk1['name']} + {pk2['name']}) to acquire {target_asset['name']} "
                            f"without surrendering any current rostered starters."
                        ),
                        "score": 89 + prox_bonus - abs(eval_res["net_diff"]) / 50.0,
                    })
                    break
                if len(proposals) >= max_proposals:
                    break

    proposals.sort(key=lambda p: p["score"], reverse=True)
    return proposals[:max_proposals]


def find_targeted_sell_trades(
    target_asset: Dict[str, Any],
    user_profile: Dict[str, Any],
    other_profiles: List[Dict[str, Any]],
    primary_lookup: Dict[str, Any],
    roster_positions: List[str],
    is_dynasty: bool,
    max_partners: int = 3,
) -> List[Dict[str, Any]]:
    """
    Identifies the best league trade partners to sell target_asset to, and generates
    customized offers for each top partner.
    """
    proposals = []
    target_pos = target_asset.get("position", "")
    target_val = target_asset.get("market_value", 0.0)
    target_age = target_asset.get("age", 25)

    # Score partner suitability
    partner_scores = []
    for prof in other_profiles:
        if prof["roster_id"] == user_profile["roster_id"]:
            continue

        p_cat = prof.get("category", "neutral")
        p_deficits = prof.get("deficits", [])
        p_surpluses = prof.get("surpluses", [])

        suitability = 50.0

        # Positional need
        if target_pos in p_deficits:
            suitability += 30.0

        # Timeline fit
        if target_age >= 28:
            # Veteran asset -> best for contenders
            if p_cat == "win":
                suitability += 25.0
            elif p_cat == "rebuild":
                suitability -= 20.0
        elif target_age <= 24 or target_asset.get("type") == "pick":
            # Young asset or pick -> best for rebuilders
            if p_cat == "rebuild":
                suitability += 25.0

        partner_scores.append((suitability, prof))

    partner_scores.sort(key=lambda x: x[0], reverse=True)

    # For each top partner, construct a viable return package
    for score, partner in partner_scores:
        partner_name = partner.get("manager_name", f"Team {partner['roster_id']}")
        partner_cat = partner.get("category", "neutral")
        partner_picks = sorted(
            partner.get("pick_assets", []),
            key=lambda pk: (int(pk["season"]) if str(pk["season"]).isdigit() else 9999, pk["round"]),
        )
        partner_players = partner.get("starter_assets", []) + partner.get("bench_assets", [])

        # 1. Look for a pick return (if dynasty and partner has picks)
        offer_found = False
        if is_dynasty and partner_picks:
            for pk in partner_picks:
                give = [target_asset]
                recv = [pk]
                eval_res = evaluate_trade_fairness(give, recv)
                if eval_res["is_balanced"]:
                    is_viable, _ = check_lineup_and_deficit_viability(
                        user_profile, give, recv, primary_lookup, roster_positions, is_dynasty
                    )
                    if is_viable:
                        prox_bonus = get_pick_proximity_bonus(recv)
                        proposals.append({
                            "partner_name": partner_name,
                            "partner_status": partner["status"],
                            "partner_category": partner_cat,
                            "give_assets": give,
                            "receive_assets": recv,
                            "eval_result": eval_res,
                            "why": (
                                f"{partner_name} is an ideal buyer ({partner['status']}) who gains key starter {target_asset['name']}; "
                                f"you harvest future draft capital ({pk['name']}) to build long-term value."
                            ),
                            "score": score + prox_bonus,
                        })
                        offer_found = True
                        break

        # 2. Look for player return (or player + pick) if no pure pick trade found
        if not offer_found:
            for p in partner_players:
                give = [target_asset]
                recv = [p]
                eval_res = evaluate_trade_fairness(give, recv)
                if eval_res["is_balanced"]:
                    is_viable, _ = check_lineup_and_deficit_viability(
                        user_profile, give, recv, primary_lookup, roster_positions, is_dynasty
                    )
                    if is_viable:
                        proposals.append({
                            "partner_name": partner_name,
                            "partner_status": partner["status"],
                            "partner_category": partner_cat,
                            "give_assets": give,
                            "receive_assets": recv,
                            "eval_result": eval_res,
                            "why": (
                                f"Positional rebalancing with {partner_name}. You send {target_asset['name']} and receive "
                                f"{p['name']} ({p.get('position', '')} — {p.get('market_value', 0):,.0f} pts), addressing mutual roster needs."
                            ),
                            "score": score,
                        })
                        offer_found = True
                        break

        if len(proposals) >= max_partners:
            break

    proposals.sort(key=lambda p: p["score"], reverse=True)
    return proposals[:max_partners]


def print_targeted_trades_summary(
    mode: str,
    target_name: str,
    proposals: List[Dict[str, Any]],
    target_owner_name: Optional[str] = None,
):
    """
    Renders targeted trade suggestions cleanly to the CLI.
    """
    print()
    if mode == "buy":
        print(f"  🎯 Targeted Acquisition Search: '{target_name}'")
        if target_owner_name:
            print(f"     Owner: {target_owner_name}")
    else:
        print(f"  🏷️ Targeted Liquidation Search: '{target_name}'")

    if not proposals:
        print("     ⚠️ No mathematically fair and strategically viable trades identified for this asset.")
        return

    print("     " + "=" * 70)
    for i, prop in enumerate(proposals, 1):
        eval_res = prop["eval_result"]
        give_str = " + ".join(format_asset_str(a) for a in prop["give_assets"])
        recv_str = " + ".join(format_asset_str(a) for a in prop["receive_assets"])
        diff_str = f"+{eval_res['net_diff']:,.0f}" if eval_res["net_diff"] >= 0 else f"{eval_res['net_diff']:,.0f}"

        arch_label = prop.get("archetype", "🤝 Proposed Trade")
        print(f"     Option {i}: [{arch_label} with {prop['partner_name']}]")
        print(f"        YOU GIVE: {give_str}")
        print(f"        YOU GET:  {recv_str}")
        print(
            f"        ↳ Model 3 Value: You {eval_res['eff_give']:,.0f} pts vs Partner {eval_res['eff_receive']:,.0f} pts "
            f"(Fairness: {eval_res['fairness_ratio']*100:.0f}% | Net diff: {diff_str} pts)"
        )
        print(f"        ↳ Strategic Rationale: {prop['why']}")
        if i < len(proposals):
            print("     " + "-" * 70)
    print("     " + "=" * 70)
