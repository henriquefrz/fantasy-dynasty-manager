def build_add_drop_suggestions(matched_roster, matched_free_agents, starter_count, min_gain=1.0):
    if not matched_roster:
        return []

    roster_sorted = sorted(matched_roster, key=lambda pr: pr[1]["rank_ecr"])

    if starter_count > 0:
        index = min(starter_count, len(roster_sorted)) - 1
        worst_starter_rank = roster_sorted[index][1]["rank_ecr"]
    else:
        worst_starter_rank = None

    suggestions = []

    for fa_player, fa_ranking in matched_free_agents:
        for roster_player, roster_ranking in matched_roster:
            rank_diff = roster_ranking["rank_ecr"] - fa_ranking["rank_ecr"]

            if rank_diff < min_gain:
                continue

            if worst_starter_rank is not None and fa_ranking["rank_ecr"] < worst_starter_rank:
                priority = "titular"
            else:
                priority = "banco"

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

    suggestions.sort(key=lambda s: (s["priority"] != "titular", -s["value_gained"]))

    return suggestions


def enrich_with_alt_ranking(suggestions, alt_lookup):
    for suggestion in suggestions:
        add_alt = alt_lookup.get(suggestion["add_player_id"])
        drop_alt = alt_lookup.get(suggestion["drop_player_id"])

        suggestion["add_alt_rank"] = add_alt["rank_ecr"] if add_alt else None
        suggestion["drop_alt_rank"] = drop_alt["rank_ecr"] if drop_alt else None

    return suggestions