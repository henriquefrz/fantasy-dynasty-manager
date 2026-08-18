from datetime import date

import requests


BASE_URL = "https://api.sleeper.app/v1"


def get_user(username):
    url = f"{BASE_URL}/user/{username}"

    response = requests.get(url)

    response.raise_for_status()

    return response.json()


def get_user_leagues(user_id, season):
    url = f"{BASE_URL}/user/{user_id}/leagues/nfl/{season}"

    response = requests.get(url)

    response.raise_for_status()

    return response.json()


def get_league_rosters(league_id):
    url = f"{BASE_URL}/league/{league_id}/rosters"

    response = requests.get(url)

    response.raise_for_status()

    return response.json()


def get_user_roster(rosters, user_id):
    for roster in rosters:
        if roster["owner_id"] == user_id:
            return roster

    return None


def get_players():
    url = f"{BASE_URL}/players/nfl"

    response = requests.get(url)

    response.raise_for_status()

    return response.json()


def get_roster_players(roster, players):
    roster_players = []

    for player_id in roster["players"]:
        player = players.get(player_id)

        if player:
            roster_players.append(player)

    return roster_players


RELEVANT_POSITIONS = {"QB", "RB", "WR", "TE", "K", "DEF"}
SEARCH_RANK_LIMIT = 500
AGE_MISMATCH_LIMIT = 2


def calculate_real_age(birth_date_str):
    if not birth_date_str:
        return None

    try:
        birth_date = date.fromisoformat(birth_date_str)
    except ValueError:
        return None

    today = date.today()

    age = today.year - birth_date.year

    if (today.month, today.day) < (birth_date.month, birth_date.day):
        age -= 1

    return age


def has_stale_record(player):
    reported_age = player.get("age")
    real_age = calculate_real_age(player.get("birth_date"))

    if reported_age is None or real_age is None:
        return False

    return abs(reported_age - real_age) >= AGE_MISMATCH_LIMIT


def get_free_agents(rosters, players):
    rostered_ids = set()

    for roster in rosters:
        if roster.get("players"):
            rostered_ids.update(roster["players"])

    free_agents = []

    for player_id, player in players.items():
        if player_id in rostered_ids:
            continue

        if player.get("position") not in RELEVANT_POSITIONS:
            continue

        if player.get("position") == "DEF":
            free_agents.append(player)
            continue

        search_rank = player.get("search_rank")

        if search_rank is None or search_rank > SEARCH_RANK_LIMIT:
            continue

        if has_stale_record(player):
            continue

        free_agents.append(player)

    return free_agents