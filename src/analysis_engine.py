from src.matching import match_players_by_sleeper_id
from src.team_strength import simulate_optimal_lineup


def is_rookie_or_taxi_eligible(player_obj):
    """
    Checks whether a player is a rookie / eligible for a fantasy taxi squad.
    """
    years = player_obj.get("years_exp")
    if years == 0:
        return True
    if player_obj.get("rookie") is True:
        return True
    return False


def is_protected_dynasty_drop(player_obj, ranking_data, is_dynasty=True, protect_injured=True):
    """
    Determines if a player on the bench is protected from being recommended as a waiver drop.
    
    1. Injured Star/Starter Protection (when protect_injured=True):
       Any player on an injury/reserve designation (IR, DNR, PUP, OUT, SUS) with NFL
       experience (years_exp >= 1 or market_value >= 200.0) is recognized as a temporarily 
       injured NFL contributor (e.g. Brandon Aiyuk) and protected from being cut for free agents.
    2. Elite Rank Floor:
       Top-tier consensus players (rank_ecr <= 80.0) are core assets protected from casual drops.
    """
    if not player_obj:
        return False
    if not protect_injured:
        return False

    val = (ranking_data or {}).get("market_value", 0.0)
    ecr = (ranking_data or {}).get("rank_ecr", 999.0)

    status = str(player_obj.get("status") or "").upper()
    inj_status = str(player_obj.get("injury_status") or "").upper()
    years_exp = player_obj.get("years_exp") or 0

    is_injured_or_inactive = (
        status in ("IR", "DNR", "PUP", "OUT", "SUS", "INJURED RESERVE", "NON FOOTBALL INJURY")
        or inj_status in ("OUT", "IR", "PUP", "DOUBTFUL")
        or bool(player_obj.get("injury_body_part"))
    )

    if is_injured_or_inactive and (years_exp >= 1 or val >= 200.0):
        return True

    if ecr <= 80.0:
        return True

    return False


def build_intelligent_waiver_suggestions(
    roster_players,
    free_agents,
    primary_lookup,
    roster_positions,
    user_roster,
    alt_lookup=None,
    category="neutral",
    is_dynasty=True,
    protect_injured=True,
    min_point_gain=100.0,
    min_rank_gain=3.0,
):
    """
    Generates intelligent waiver recommendations considering:
    1. Hard IR Protection: Players on IR (reserve) are strictly immune from drops.
    2. Smart Taxi Protection: Players on Taxi are immune from regular bench drops,
       but eligible for Taxi-to-Taxi rookie swaps.
    3. Injured Star Protection: Players with active injury designations (IR/DNR/PUP/OUT like Brandon Aiyuk)
       are protected from waiver cuts when protect_injured is True.
    4. Starting Lineup Impact: Prioritizes additions that immediately crack the starting lineup
       (e.g. an RB2 is prioritized over a WR7).
    5. Cross-Positional Upgrades: Recommends dropping the lowest-value droppable active bench player
       regardless of position to add the best available free agent.
    6. Team Trajectory: Contenders prioritize immediate Redraft utility / starters;
       Rebuilders prioritize Dynasty market value and youth upside.
    """
    if not roster_players or not free_agents:
        return {
            "starter_upgrades": [],
            "cross_pos_upgrades": [],
            "taxi_swaps": [],
            "positional_options": {},
        }

    reserve_ids = set(user_roster.get("reserve") or [])
    taxi_ids = set(user_roster.get("taxi") or [])

    # 1. Simulate current optimal starting lineup
    current_starters, current_bench = simulate_optimal_lineup(
        roster_players, primary_lookup, roster_positions, is_dynasty=is_dynasty
    )
    starter_ids = {p.get("player_id") for p, _ in current_starters}

    # 2. Categorize roster players
    active_bench = []
    taxi_players = []

    for p_obj, r_data in current_bench:
        pid = p_obj.get("player_id")
        if pid in reserve_ids:
            # Hard IR protection: skip completely
            continue
        elif pid in taxi_ids:
            taxi_players.append((p_obj, r_data))
        else:
            active_bench.append((p_obj, r_data))

    # Sort active bench by market value ascending (lowest value first = prime cut candidates)
    active_bench_sorted = sorted(
        active_bench,
        key=lambda item: (item[1].get("market_value", 0.0), -item[1].get("rank_ecr", 999.0))
    )

    # Filter droppable active bench players (exclude K/DEF and protected players)
    droppable_skill_bench = [
        item for item in active_bench_sorted
        if item[0].get("position") not in ("K", "DEF") and not is_protected_dynasty_drop(item[0], item[1], is_dynasty=is_dynasty, protect_injured=protect_injured)
    ]

    # 3. Match free agents to lookup
    matched_fa, _ = match_players_by_sleeper_id(free_agents, primary_lookup)
    if not matched_fa:
        return {
            "starter_upgrades": [],
            "cross_pos_upgrades": [],
            "taxi_swaps": [],
            "positional_options": {},
        }

    # Filter FAs with meaningful rank or market value
    if is_dynasty:
        eligible_fa = [
            item for item in matched_fa
            if item[1].get("market_value", 0.0) >= 300.0
            or (item[0].get("position") in ("K", "DEF") and item[1].get("rank_ecr", 999.0) < 32.0)
        ]
    else:
        eligible_fa = [
            item for item in matched_fa
            if item[1].get("market_value", 0.0) >= 200.0
            or item[1].get("rank_ecr", 999.0) < 120.0
            or (item[0].get("position") in ("K", "DEF") and item[1].get("rank_ecr", 999.0) < 32.0)
        ]

    # Sort FAs based on team situation:
    # Contender -> sort primarily by Redraft ECR ascending
    # Rebuilder -> sort primarily by Dynasty Market Value descending
    if category == "win" or not is_dynasty:
        eligible_fa.sort(key=lambda item: (item[1].get("rank_ecr", 999.0), -item[1].get("market_value", 0.0)))
    else:
        eligible_fa.sort(key=lambda item: (-item[1].get("market_value", 0.0), item[1].get("rank_ecr", 999.0)))

    starter_upgrades = []
    cross_pos_upgrades = []
    taxi_swaps = []
    positional_options = {}

    seen_add_ids = set()

    # 4. Evaluate each free agent
    for fa_obj, fa_ranking in eligible_fa:
        fa_id = fa_obj.get("player_id")
        fa_pos = fa_obj.get("position")
        fa_val = fa_ranking.get("market_value", 0.0)
        fa_ecr = fa_ranking.get("rank_ecr", 999.0)

        # Test if FA cracks the starting lineup
        test_roster = roster_players + [fa_obj]
        new_starters, _ = simulate_optimal_lineup(
            test_roster, primary_lookup, roster_positions, is_dynasty=is_dynasty
        )
        new_starter_ids = {p.get("player_id") for p, _ in new_starters}

        is_starter = fa_id in new_starter_ids

        # A. Starter Upgrade
        if is_starter:
            # Find which starter was displaced
            displaced_id = (starter_ids - new_starter_ids).pop() if (starter_ids - new_starter_ids) else None
            displaced_p = next((p for p, _ in current_starters if p.get("player_id") == displaced_id), None) if displaced_id else None
            displaced_ranking = primary_lookup.get(displaced_id, {}) if displaced_id else {}

            if fa_pos in ("K", "DEF"):
                # K/DEF can only displace and drop another K/DEF
                if displaced_p and displaced_p.get("position") == fa_pos:
                    drop_candidate = (displaced_p, displaced_ranking)
                else:
                    same_pos = [item for item in active_bench_sorted if item[0].get("position") == fa_pos]
                    drop_candidate = same_pos[0] if same_pos else None
                if not drop_candidate:
                    continue
                disp_ecr = drop_candidate[1].get("rank_ecr", 999.0)
                if fa_ecr >= disp_ecr:
                    continue
                starter_gain = disp_ecr - fa_ecr
                drop_obj, drop_ranking = drop_candidate
                drop_val = drop_ranking.get("market_value", 0.0)
                starter_upgrades.append({
                    "add_player": fa_obj,
                    "add_ranking": fa_ranking,
                    "add_value": fa_val,
                    "drop_player": drop_obj,
                    "drop_ranking": drop_ranking,
                    "drop_value": drop_val,
                    "displaced_player": displaced_p,
                    "displaced_ranking": displaced_ranking,
                    "starter_gain": starter_gain,
                    "market_value_gain": fa_val - drop_val,
                    "priority_tag": "STARTER STREAM" if category == "win" else "STARTER",
                })
                seen_add_ids.add(fa_id)
            else:
                # Skill position starter upgrade (QB, RB, WR, TE)
                drop_candidate = droppable_skill_bench[0] if droppable_skill_bench else None
                if drop_candidate:
                    drop_obj, drop_ranking = drop_candidate
                    drop_val = drop_ranking.get("market_value", 0.0)
                    drop_ecr = drop_ranking.get("rank_ecr", 999.0)

                    disp_ecr = displaced_ranking.get("rank_ecr")
                    disp_val = displaced_ranking.get("market_value", 0.0)
                    starter_gain = (disp_ecr - fa_ecr) if (disp_ecr and fa_ecr) else (fa_val - disp_val)

                    # In dynasty, starter upgrade should not severely hurt dynasty capital
                    val_gain = fa_val - drop_val
                    if not (is_dynasty and category != "win" and val_gain < 0):
                        add_alt = alt_lookup.get(fa_id, {}) if alt_lookup else {}
                        drop_alt = alt_lookup.get(drop_obj.get("player_id"), {}) if alt_lookup else {}
                        viable_drops = [
                            {
                                "drop_player": cand_obj,
                                "drop_ranking": cand_ranking,
                                "drop_value": cand_ranking.get("market_value", 0.0),
                                "drop_ecr": cand_ranking.get("rank_ecr", 999.0),
                                "market_value_gain": fa_val - cand_ranking.get("market_value", 0.0),
                            }
                            for cand_obj, cand_ranking in droppable_skill_bench
                            if cand_ranking.get("market_value", 0.0) < fa_val
                        ]
                        starter_upgrades.append({
                            "add_player": fa_obj,
                            "add_ranking": fa_ranking,
                            "add_value": fa_val,
                            "drop_player": drop_obj,
                            "drop_ranking": drop_ranking,
                            "drop_value": drop_val,
                            "all_drop_candidates": viable_drops,
                            "displaced_player": displaced_p,
                            "displaced_ranking": displaced_ranking,
                            "starter_gain": starter_gain,
                            "market_value_gain": val_gain,
                            "is_high_value_drop": drop_val >= 500.0,
                            "add_alt_rank": add_alt.get("rank_ecr_overall") or add_alt.get("rank_ecr"),
                            "add_alt_pos_rank": add_alt.get("rank_ecr_pos") or add_alt.get("rank_ecr"),
                            "drop_alt_rank": drop_alt.get("rank_ecr_overall") or drop_alt.get("rank_ecr"),
                            "drop_alt_pos_rank": drop_alt.get("rank_ecr_pos") or drop_alt.get("rank_ecr"),
                            "add_alt_value": add_alt.get("market_value"),
                            "drop_alt_value": drop_alt.get("market_value"),
                            "priority_tag": "STARTER - WIN NOW" if category == "win" else "STARTER",
                        })
                        seen_add_ids.add(fa_id)

        # B. Cross-Positional Bench Upgrade (skill positions only)
        if fa_id not in seen_add_ids and fa_pos not in ("K", "DEF"):
            if droppable_skill_bench:
                drop_obj, drop_ranking = droppable_skill_bench[0]
                drop_val = drop_ranking.get("market_value", 0.0)
                drop_ecr = drop_ranking.get("rank_ecr", 999.0)

                val_gain = fa_val - drop_val
                ecr_gain = drop_ecr - fa_ecr

                # In Dynasty: bench upgrade must have positive dynasty market gain
                # In Redraft: can be based on market value or significant ECR gain without net loss
                is_valid_gain = (
                    (val_gain >= min_point_gain) if is_dynasty
                    else (val_gain >= min_point_gain or (ecr_gain >= min_rank_gain and fa_ecr < 100.0 and val_gain >= -50.0))
                )

                if is_valid_gain:
                    add_alt = alt_lookup.get(fa_id, {}) if alt_lookup else {}
                    drop_alt = alt_lookup.get(drop_obj.get("player_id"), {}) if alt_lookup else {}
                    viable_drops = [
                        {
                            "drop_player": cand_obj,
                            "drop_ranking": cand_ranking,
                            "drop_value": cand_ranking.get("market_value", 0.0),
                            "drop_ecr": cand_ranking.get("rank_ecr", 999.0),
                            "market_value_gain": fa_val - cand_ranking.get("market_value", 0.0),
                        }
                        for cand_obj, cand_ranking in droppable_skill_bench
                        if cand_ranking.get("market_value", 0.0) < fa_val
                    ]
                    cross_pos_upgrades.append({
                        "add_player": fa_obj,
                        "add_ranking": fa_ranking,
                        "add_value": fa_val,
                        "drop_player": drop_obj,
                        "drop_ranking": drop_ranking,
                        "drop_value": drop_val,
                        "all_drop_candidates": viable_drops,
                        "market_value_gain": val_gain,
                        "ecr_gain": ecr_gain,
                        "is_high_value_drop": drop_val >= 500.0,
                        "add_alt_rank": add_alt.get("rank_ecr_overall") or add_alt.get("rank_ecr"),
                        "add_alt_pos_rank": add_alt.get("rank_ecr_pos") or add_alt.get("rank_ecr"),
                        "drop_alt_rank": drop_alt.get("rank_ecr_overall") or drop_alt.get("rank_ecr"),
                        "drop_alt_pos_rank": drop_alt.get("rank_ecr_pos") or drop_alt.get("rank_ecr"),
                        "add_alt_value": add_alt.get("market_value"),
                        "drop_alt_value": drop_alt.get("market_value"),
                        "priority_tag": "WIN-NOW BENCH" if category == "win" else ("UPSIDE BENCH" if category == "rebuild" else "BENCH UPGRADE"),
                    })
                    seen_add_ids.add(fa_id)

        # C. Taxi Squad Rookie-for-Rookie Swap
        if taxi_players and is_rookie_or_taxi_eligible(fa_obj) and fa_pos not in ("K", "DEF"):
            # Find lowest-value taxi player
            worst_taxi_obj, worst_taxi_ranking = min(
                taxi_players, key=lambda item: item[1].get("market_value", 0.0)
            )
            worst_taxi_val = worst_taxi_ranking.get("market_value", 0.0)
            taxi_val_gain = fa_val - worst_taxi_val

            if taxi_val_gain >= min_point_gain:
                taxi_swaps.append({
                    "add_player": fa_obj,
                    "add_ranking": fa_ranking,
                    "add_value": fa_val,
                    "drop_player": worst_taxi_obj,
                    "drop_ranking": worst_taxi_ranking,
                    "drop_value": worst_taxi_val,
                    "market_value_gain": taxi_val_gain,
                    "priority_tag": "TAXI SWAP",
                })

        # D. Positional Options (Same Position Swap)
        pos_bench = [
            (p, r) for p, r in droppable_skill_bench
            if p.get("position") == fa_pos
        ]
        if pos_bench and fa_pos not in ("K", "DEF"):
            pos_drop_obj, pos_drop_ranking = pos_bench[0]
            pos_drop_val = pos_drop_ranking.get("market_value", 0.0)
            pos_drop_ecr = pos_drop_ranking.get("rank_ecr", 999.0)

            val_gain = fa_val - pos_drop_val
            ecr_gain = pos_drop_ecr - fa_ecr

            is_valid_pos_gain = (
                (val_gain >= 100.0) if is_dynasty
                else (val_gain >= 50.0 or (ecr_gain >= min_rank_gain and fa_ecr < 100.0 and val_gain >= 0.0))
            )

            if is_valid_pos_gain:
                positional_options.setdefault(fa_pos, []).append({
                    "add_player": fa_obj,
                    "add_ranking": fa_ranking,
                    "add_value": fa_val,
                    "drop_player": pos_drop_obj,
                    "drop_ranking": pos_drop_ranking,
                    "drop_value": pos_drop_val,
                    "market_value_gain": val_gain,
                    "ecr_gain": ecr_gain,
                    "priority_tag": "⭐ STARTER" if is_starter else "  bench",
                })

    # Sort results
    starter_upgrades.sort(key=lambda s: -s["market_value_gain"])
    cross_pos_upgrades.sort(key=lambda s: -s["market_value_gain"])
    taxi_swaps.sort(key=lambda s: -s["market_value_gain"])

    return {
        "starter_upgrades": starter_upgrades[:3],
        "cross_pos_upgrades": cross_pos_upgrades[:3],
        "taxi_swaps": taxi_swaps[:2],
        "positional_options": positional_options,
    }


# Backwards compatibility alias
def build_add_drop_suggestions(matched_roster, matched_free_agents, starter_count, min_gain=1.0):
    """
    Legacy wrapper for same-position suggestions.
    """
    if not matched_roster:
        return []

    roster_sorted = sorted(matched_roster, key=lambda pr: pr[1]["rank_ecr"])
    worst_starter_rank = roster_sorted[min(starter_count, len(roster_sorted)) - 1][1]["rank_ecr"] if starter_count > 0 else None

    suggestions = []
    for fa_player, fa_ranking in matched_free_agents:
        for roster_player, roster_ranking in matched_roster:
            rank_diff = roster_ranking["rank_ecr"] - fa_ranking["rank_ecr"]
            if rank_diff < min_gain:
                continue

            priority = "starter" if worst_starter_rank and fa_ranking["rank_ecr"] < worst_starter_rank else "bench"
            suggestions.append({
                "add_player_id": fa_player.get("player_id"),
                "add_name": fa_player.get("full_name") or fa_player.get("player_id"),
                "add_rank": fa_ranking["rank_ecr"],
                "drop_player_id": roster_player.get("player_id"),
                "drop_name": roster_player.get("full_name") or roster_player.get("player_id"),
                "drop_rank": roster_ranking["rank_ecr"],
                "value_gained": rank_diff,
                "priority": priority,
            })

    suggestions.sort(key=lambda s: (s["priority"] != "starter", -s["value_gained"]))
    return suggestions


def enrich_with_alt_ranking(suggestions, alt_lookup):
    for suggestion in suggestions:
        add_alt = alt_lookup.get(suggestion.get("add_player_id")) if alt_lookup else None
        drop_alt = alt_lookup.get(suggestion.get("drop_player_id")) if alt_lookup else None

        suggestion["add_alt_rank"] = (add_alt.get("rank_ecr_overall") or add_alt.get("rank_ecr")) if add_alt else None
        suggestion["add_alt_pos_rank"] = (add_alt.get("rank_ecr_pos") or add_alt.get("rank_ecr")) if add_alt else None
        suggestion["drop_alt_rank"] = (drop_alt.get("rank_ecr_overall") or drop_alt.get("rank_ecr")) if drop_alt else None
        suggestion["drop_alt_pos_rank"] = (drop_alt.get("rank_ecr_pos") or drop_alt.get("rank_ecr")) if drop_alt else None

    return suggestions