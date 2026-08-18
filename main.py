from src.sleeper_api import (
    get_user,
    get_user_leagues,
    get_league_rosters,
    get_user_roster,
    get_players,
    get_roster_players,
    get_free_agents,
    get_traded_picks,
)
from src.league_classifier import classify_league, get_starter_counts
from src.dynastyprocess_data import get_fp_rankings_raw, get_player_ids_raw, build_positional_lookup
from src.matching import match_players_by_sleeper_id
from src.analysis_engine import build_add_drop_suggestions, enrich_with_alt_ranking
from src.team_strength import (
    rank_teams_in_league,
    get_strength_tier,
    get_current_strength_tier,
    classify_dynasty_team,
    classify_redraft_team,
)


username = "henriquefrz"
season = "2026"

POSITIONS = ["QB", "RB", "WR", "TE", "K", "DEF"]

user = get_user(username)

user_id = user["user_id"]

leagues = get_user_leagues(user_id, season)

print(f"Usuário: {user['username']}")
print(f"User ID: {user_id}")
print(f"Ligas encontradas: {len(leagues)}")


players = get_players()

print(f"Jogadores disponíveis no banco do Sleeper: {len(players)}")


print()
print("Inspecionando traded_picks (Dinastia do Pão de Queijo):")

league_teste = next(l for l in leagues if l["name"] == "Dinastia do Pão de Queijo")
traded_picks = get_traded_picks(league_teste["league_id"])

print(f"Total de picks negociadas: {len(traded_picks)}")
print(f"Rodadas de draft da liga: {league_teste['settings']['draft_rounds']}")

if traded_picks:
    print("Exemplo de pick negociada:", traded_picks[0])


print()
print("Baixando rankings completos (DynastyProcess):")

fp_rankings = get_fp_rankings_raw()
player_ids = get_player_ids_raw()

dynasty_lookup = build_positional_lookup(fp_rankings, player_ids, "dynasty")
redraft_lookup = build_positional_lookup(fp_rankings, player_ids, "redraft")

print(f"Jogadores com ranking Dynasty disponível: {len(dynasty_lookup)}")
print(f"Jogadores com ranking Redraft disponível: {len(redraft_lookup)}")


print()
print("=" * 60)
print("SITUAÇÃO DO TIME E SUGESTÕES DE ADD/DROP POR LIGA")
print("=" * 60)

for league in leagues:
    league_rosters = get_league_rosters(league["league_id"])
    classification = classify_league(league, league_rosters)

    print()
    print(f"### {classification['name']} ({classification['type']}, {classification['stage']})")

    if classification["stage"] == "pre_draft_sem_roster":
        print("Pulada — sem roster atribuído ainda.")
        continue

    user_roster = get_user_roster(league_rosters, user_id)

    if not user_roster or not user_roster.get("players"):
        print("Seu roster não foi encontrado ou ainda não tem jogadores.")
        continue

    starter_counts = get_starter_counts(league)

    all_rosters_players = {
        r["roster_id"]: get_roster_players(r, players)
        for r in league_rosters
        if r.get("players")
    }

    redraft_ranked = rank_teams_in_league(all_rosters_players, redraft_lookup, starter_counts)
    redraft_tier, redraft_pos, redraft_total = get_strength_tier(user_roster["roster_id"], redraft_ranked)

    current_tier, games_played = get_current_strength_tier(
        user_roster, league_rosters, redraft_pos, redraft_total
    )

    if classification["type"] == "redraft":
        primary_lookup, primary_label = redraft_lookup, "Redraft"
        alt_lookup, alt_label = {}, None

        situacao = classify_redraft_team(current_tier)
        print(f"Situação: {situacao} (força Redraft: {redraft_pos}º de {redraft_total}, {games_played} jogos disputados)")
    else:
        primary_lookup, primary_label = dynasty_lookup, "Dynasty"
        alt_lookup, alt_label = redraft_lookup, "Redraft"

        dynasty_ranked = rank_teams_in_league(all_rosters_players, dynasty_lookup, starter_counts)
        dynasty_tier, dynasty_pos, dynasty_total = get_strength_tier(user_roster["roster_id"], dynasty_ranked)

        situacao = classify_dynasty_team(current_tier, dynasty_tier)
        print(
            f"Situação: {situacao} "
            f"(força Dynasty: {dynasty_pos}º de {dynasty_total} — força Redraft: {redraft_pos}º de {redraft_total}, {games_played} jogos disputados)"
        )

    roster_players = get_roster_players(user_roster, players)
    free_agents = get_free_agents(league_rosters, players)

    league_has_suggestion = False

    for position in POSITIONS:
        roster_pos_players = [p for p in roster_players if p.get("position") == position]
        fa_pos_players = [p for p in free_agents if p.get("position") == position]

        matched_roster, _ = match_players_by_sleeper_id(roster_pos_players, primary_lookup)
        matched_fa, _ = match_players_by_sleeper_id(fa_pos_players, primary_lookup)

        starter_count = starter_counts.get(position, 0)

        suggestions = build_add_drop_suggestions(matched_roster, matched_fa, starter_count)
        suggestions = enrich_with_alt_ranking(suggestions, alt_lookup)

        if not suggestions:
            continue

        league_has_suggestion = True

        print(f"  {position} (titulares: {starter_count}):")

        for suggestion in suggestions[:3]:
            tag = "⭐ TITULAR" if suggestion["priority"] == "titular" else "  banco"

            add_alt = f" / {alt_label} {suggestion['add_alt_rank']:.1f}" if suggestion["add_alt_rank"] is not None else ""
            drop_alt = f" / {alt_label} {suggestion['drop_alt_rank']:.1f}" if suggestion["drop_alt_rank"] is not None else ""

            print(
                f"    [{tag}] ADD {suggestion['add_name']} ({primary_label} {suggestion['add_rank']:.1f}{add_alt}) / "
                f"DROP {suggestion['drop_name']} ({primary_label} {suggestion['drop_rank']:.1f}{drop_alt}) — "
                f"ganho ({primary_label}): {suggestion['value_gained']:.1f} posições"
            )

    if not league_has_suggestion:
        print("  Nenhuma sugestão encontrada nessa liga.")