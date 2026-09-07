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


def get_player_avatar_url(player_id, position=None, team=None):
    """
    Returns Sleeper CDN thumbnail URL for an NFL player or team defense.
    """
    if not player_id:
        return ""

    pos_upper = str(position or "").upper()
    pid_str = str(player_id).strip()

    # Draft Picks (no CDN thumbnail)
    if pos_upper == "PICK" or pid_str.startswith("FP_") or pid_str.startswith("pick_") or "round" in pid_str.lower() or "pick" in pid_str.lower():
        return ""

    # Team Defense (DST / DEF)
    if pos_upper in ("DEF", "DST") or not pid_str.isdigit():
        team_code = (team or pid_str).lower()
        if team_code in ("fa", "—", "") or not team_code.isalpha():
            return ""
        if team_code == "jax":
            team_code = "jax"
        return f"https://sleepercdn.com/images/team_logos/nfl/{team_code}.png"

    # Standard NFL Player
    return f"https://sleepercdn.com/content/nfl/players/thumb/{pid_str}.jpg"


def get_team_logo_url(team_abbr):
    """
    Returns Sleeper CDN URL for an NFL team logo.
    """
    if not team_abbr:
        return ""
    code = str(team_abbr).strip().lower()
    return f"https://sleepercdn.com/images/team_logos/nfl/{code}.png"