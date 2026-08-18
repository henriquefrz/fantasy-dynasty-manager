from src.sleeper_api import (
    get_user,
    get_user_leagues,
    get_league_rosters,
    get_user_roster,
    get_players,
    get_roster_players,
    get_free_agents,
)
from src.league_classifier import classify_league
from src.dynastyprocess_data import get_fp_rankings_raw, get_player_ids_raw, build_positional_lookup
from src.matching import match_players_by_sleeper_id
from src.analysis_engine import build_add_drop_suggestions


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
print("Baixando rankings completos (DynastyProcess):")

fp_rankings = get_fp_rankings_raw()
player_ids = get_player_ids_raw()

dynasty_lookup = build_positional_lookup(fp_rankings, player_ids, "dynasty")
redraft_lookup = build_positional_lookup(fp_rankings, player_ids, "redraft")

print(f"Jogadores com ranking Dynasty disponível: {len(dynasty_lookup)}")
print(f"Jogadores com ranking Redraft disponível: {len(redraft_lookup)}")

print()
print("=" * 60)
print("SUGESTÕES DE ADD/DROP POR LIGA")
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

    if classification["type"] == "redraft":
        lookup = redraft_lookup
    else:
        lookup = dynasty_lookup

    roster_players = get_roster_players(user_roster, players)
    free_agents = get_free_agents(league_rosters, players)

    league_has_suggestion = False

    for position in POSITIONS:
        roster_pos_players = [p for p in roster_players if p.get("position") == position]
        fa_pos_players = [p for p in free_agents if p.get("position") == position]

        matched_roster, _ = match_players_by_sleeper_id(roster_pos_players, lookup)
        matched_fa, _ = match_players_by_sleeper_id(fa_pos_players, lookup)

        if position == "DEF":
            print(
                f"  [diagnóstico DEF] roster: {len(roster_pos_players)} ({len(matched_roster)} no ranking) — "
                f"free agents: {len(fa_pos_players)} ({len(matched_fa)} no ranking)"
            )

        suggestions = build_add_drop_suggestions(matched_roster, matched_fa)

        if not suggestions:
            continue

        league_has_suggestion = True

        print(f"  {position}:")

        for suggestion in suggestions[:3]:
            print(
                f"    ADD {suggestion['add_name']} (rank {suggestion['add_rank']:.1f}) / "
                f"DROP {suggestion['drop_name']} (rank {suggestion['drop_rank']:.1f}) — "
                f"ganho: {suggestion['value_gained']:.1f} posições"
            )

    if not league_has_suggestion:
        print("  Nenhuma sugestão encontrada nessa liga.")