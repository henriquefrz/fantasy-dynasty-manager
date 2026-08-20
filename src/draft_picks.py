DRAFT_COMPLETED_STATUSES = {"in_season", "complete"}


def build_picks_ownership(league, traded_picks, future_years=2):
    rounds = league["settings"]["draft_rounds"]
    current_season = int(league["season"])
    total_rosters = league["total_rosters"]

    current_season_already_drafted = league.get("status") in DRAFT_COMPLETED_STATUSES
    start_offset = 1 if current_season_already_drafted else 0

    ownership = {}

    for year_offset in range(start_offset, future_years + 1):
        season = str(current_season + year_offset)

        for round_num in range(1, rounds + 1):
            for roster_id in range(1, total_rosters + 1):
                ownership[(season, round_num, roster_id)] = roster_id

    for pick in traded_picks:
        key = (pick["season"], pick["round"], pick["roster_id"])

        if key in ownership:
            ownership[key] = pick["owner_id"]

    return ownership


def get_picks_for_roster(ownership, roster_id):
    picks = [key for key, owner in ownership.items() if owner == roster_id]
    picks.sort(key=lambda k: (k[0], k[1]))

    return picks


def format_picks_summary(picks):
    by_season = {}

    for season, round_num, original_roster_id in picks:
        by_season.setdefault(season, []).append(round_num)

    parts = []

    for season in sorted(by_season):
        rounds = sorted(by_season[season])
        rounds_str = ", ".join(f"R{r}" for r in rounds)
        parts.append(f"{season}: {rounds_str}")

    return " | ".join(parts)


def get_picks_capital_score(picks, rounds_in_league):
    return sum((rounds_in_league - round_num + 1) for _, round_num, _ in picks)


def rank_teams_by_picks(ownership, total_rosters, rounds_in_league):
    scores = []

    for roster_id in range(1, total_rosters + 1):
        picks = get_picks_for_roster(ownership, roster_id)
        score = get_picks_capital_score(picks, rounds_in_league)
        scores.append((roster_id, score))

    scores.sort(key=lambda t: -t[1])

    return scores