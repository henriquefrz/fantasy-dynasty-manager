def match_players_by_sleeper_id(sleeper_players, dynasty_lookup):
    matched = []
    unmatched = []

    for player in sleeper_players:
        player_id = player.get("player_id")
        ranking = dynasty_lookup.get(player_id)

        if ranking:
            matched.append((player, ranking))
        else:
            unmatched.append(player)

    return matched, unmatched