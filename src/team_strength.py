from src.matching import match_players_by_sleeper_id


def calculate_team_strength(roster_players, lookup, starter_counts):
    position_averages = {}
    all_starter_ranks = []

    for position, starter_count in starter_counts.items():
        if starter_count <= 0:
            continue

        pos_players = [p for p in roster_players if p.get("position") == position]
        matched, _ = match_players_by_sleeper_id(pos_players, lookup)

        if not matched:
            continue

        matched_sorted = sorted(matched, key=lambda pr: pr[1]["rank_ecr"])
        top_players = matched_sorted[:starter_count]

        avg_rank = sum(ranking["rank_ecr"] for _, ranking in top_players) / len(top_players)
        position_averages[position] = avg_rank

        all_starter_ranks.extend(ranking["rank_ecr"] for _, ranking in top_players)

    overall_avg = sum(all_starter_ranks) / len(all_starter_ranks) if all_starter_ranks else None

    return position_averages, overall_avg


def rank_teams_in_league(all_rosters_players, lookup, starter_counts):
    team_strengths = []

    for roster_id, roster_players in all_rosters_players.items():
        _, overall_avg = calculate_team_strength(roster_players, lookup, starter_counts)

        if overall_avg is not None:
            team_strengths.append((roster_id, overall_avg))

    team_strengths.sort(key=lambda t: t[1])

    return team_strengths


def get_strength_tier(roster_id, ranked_teams):
    total = len(ranked_teams)

    if total == 0:
        return None, None, None

    for position, (rid, _) in enumerate(ranked_teams, start=1):
        if rid == roster_id:
            tier = score_to_tier(percentile_score(position, total))
            return tier, position, total

    return None, None, total


def percentile_score(position, total):
    if total <= 1:
        return 1.0

    return (total - position) / (total - 1)


def score_to_tier(score):
    if score >= 2 / 3:
        return "alta"
    elif score >= 1 / 3:
        return "média"
    else:
        return "baixa"


def total_games_played(roster):
    settings = roster.get("settings", {})

    return settings.get("wins", 0) + settings.get("losses", 0) + settings.get("ties", 0)


def rank_teams_by_record(rosters):
    def record_key(roster):
        settings = roster.get("settings", {})
        wins = settings.get("wins", 0)
        ties = settings.get("ties", 0)
        fpts = settings.get("fpts", 0) + settings.get("fpts_decimal", 0) / 100

        return (-(wins * 2 + ties), -fpts)

    return sorted(rosters, key=record_key)


def get_current_strength_tier(user_roster, rosters, redraft_position, redraft_total, season_length=14, max_record_weight=0.3):
    redraft_score = percentile_score(redraft_position, redraft_total)

    games_played = total_games_played(user_roster)

    record_score = None

    if games_played > 0:
        ranked = rank_teams_by_record(rosters)
        total = len(ranked)

        for position, roster in enumerate(ranked, start=1):
            if roster["roster_id"] == user_roster["roster_id"]:
                record_score = percentile_score(position, total)
                break

    if record_score is None:
        blended_score = redraft_score
    else:
        record_weight = min(games_played / season_length, 1.0) * max_record_weight
        blended_score = record_weight * record_score + (1 - record_weight) * redraft_score

    return score_to_tier(blended_score), games_played


def classify_dynasty_team(current_tier, dynasty_tier):
    if current_tier is None or dynasty_tier is None:
        return "Dados insuficientes"

    if current_tier == "alta" and dynasty_tier == "alta":
        return "🏆 Contender consolidado"

    if current_tier == "alta":
        return "⚡ Win-Now (elenco não tão forte no longo prazo — considere vender ativos de futuro por ganho imediato)"

    if dynasty_tier == "alta":
        return "🌱 Retooling (elenco forte no futuro, ainda não no auge agora)"

    if current_tier == "baixa" and dynasty_tier == "baixa":
        return "🔨 Rebuild"

    return "➖ Meio de tabela"


def classify_redraft_team(current_tier):
    if current_tier is None:
        return "Dados insuficientes"

    if current_tier == "alta":
        return "🏆 Competindo pelo título"

    if current_tier == "baixa":
        return "❌ Fora da disputa real"

    return "➖ Meio de tabela"