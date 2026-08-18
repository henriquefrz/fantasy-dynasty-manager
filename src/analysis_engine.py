def build_add_drop_suggestions(matched_roster, matched_free_agents):
    suggestions = []

    for fa_player, fa_ranking in matched_free_agents:
        for roster_player, roster_ranking in matched_roster:
            rank_diff = roster_ranking["rank_ecr"] - fa_ranking["rank_ecr"]

            if rank_diff > 0:
                suggestions.append({
                    "add_name": fa_player.get("full_name") or fa_player.get("player_id"),
                    "add_rank": fa_ranking["rank_ecr"],
                    "drop_name": roster_player.get("full_name") or roster_player.get("player_id"),
                    "drop_rank": roster_ranking["rank_ecr"],
                    "value_gained": rank_diff,
                })

    suggestions.sort(key=lambda s: s["value_gained"], reverse=True)

    return suggestions