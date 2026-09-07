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
    if isinstance(players, list):
        p_dict = {p.get("player_id"): p for p in players if isinstance(p, dict)}
    elif isinstance(players, dict):
        p_dict = players
    else:
        p_dict = {}

    for player_id in (roster.get("players") or []):
        player = p_dict.get(player_id)
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

def get_traded_picks(league_id):
    url = f"{BASE_URL}/league/{league_id}/traded_picks"

    response = requests.get(url)

    response.raise_for_status()

    return response.json()


def get_league_users(league_id):
    url = f"{BASE_URL}/league/{league_id}/users"

    response = requests.get(url)

    response.raise_for_status()

    return response.json()


def get_nfl_state():
    """
    Returns the current NFL state from Sleeper (season, week, season_type).
    """
    url = f"{BASE_URL}/state/nfl"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.json()


_WEEKLY_PROJECTIONS_CACHE = {}


def get_weekly_projections(season: str, week: int):
    """
    Returns live weekly player stats and fantasy projections from Sleeper.
    Cached in-memory by (season, week) to avoid redundant requests across leagues.
    """
    cache_key = (str(season), int(week))
    if cache_key in _WEEKLY_PROJECTIONS_CACHE:
        return _WEEKLY_PROJECTIONS_CACHE[cache_key]

    url = f"{BASE_URL}/projections/nfl/regular/{season}/{week}"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict):
            _WEEKLY_PROJECTIONS_CACHE[cache_key] = data
            return data
        elif isinstance(data, list):
            # Map list to dict keyed by player_id
            mapped = {item.get("player_id", str(i)): item for i, item in enumerate(data)}
            _WEEKLY_PROJECTIONS_CACHE[cache_key] = mapped
            return mapped
    except Exception as e:
        print(f"Warning: Failed to fetch weekly projections for {season} Week {week}: {e}")
        return {}


_LEAGUE_MATCHUPS_CACHE = {}


def get_league_matchups(league_id: str, week: int):
    """
    Returns matchup pairings and scoring for a given league and week.
    Cached in-memory by (league_id, week).
    """
    cache_key = (str(league_id), int(week))
    if cache_key in _LEAGUE_MATCHUPS_CACHE:
        return _LEAGUE_MATCHUPS_CACHE[cache_key]

    url = f"{BASE_URL}/league/{league_id}/matchups/{week}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 404:
            return []
        response.raise_for_status()
        data = response.json()
        _LEAGUE_MATCHUPS_CACHE[cache_key] = data
        return data
    except Exception as e:
        return []


def get_league_schedule(league_id: str, start_week: int = 1, end_week: int = 14):
    """
    Returns the head-to-head regular season schedule map for the league.
    Format: dict mapping week -> list of (roster_id_1, roster_id_2) pairings.
    """
    schedule = {}
    for w in range(start_week, end_week + 1):
        matchups_data = get_league_matchups(league_id, w)
        if not matchups_data:
            continue
        by_matchup_id = {}
        for m in matchups_data:
            m_id = m.get("matchup_id")
            r_id = m.get("roster_id")
            if m_id is not None and r_id is not None:
                by_matchup_id.setdefault(m_id, []).append(r_id)

        pairings = []
        for m_id, r_ids in by_matchup_id.items():
            if len(r_ids) == 2:
                pairings.append((r_ids[0], r_ids[1]))
            elif len(r_ids) > 2:
                for i in range(0, len(r_ids), 2):
                    if i + 1 < len(r_ids):
                        pairings.append((r_ids[i], r_ids[i + 1]))
        schedule[w] = pairings
    return schedule


MANUAL_LEAGUE_HISTORY = {
    "Samonte Dynasty": {
        "inaugural_season": "2020",
        "total_seasons": 6,
        "user_titles": 0,
        "title_seasons": [],
        "is_migrated": True,
        "notes": "Migrated to Sleeper in 2026 (6 seasons on FleaFlickr)",
        "champions": [
            {"season": "2025", "champion": "Rise Up (Rafael)", "record": "—"},
            {"season": "2024", "champion": "SPFCSerieA's Team (Lucas)", "record": "—"},
            {"season": "2023", "champion": "Los Cardenales de Arizona (Hugo)", "record": "—"},
            {"season": "2022", "champion": "Liverpool Reds (Vinicius)", "record": "—"},
            {"season": "2021", "champion": "Liverpool Reds (Vinicius)", "record": "—"},
            {"season": "2020", "champion": "Los Cardenales de Arizona (Hugo)", "record": "—"},
        ],
    },
    "Samonte Bowl": {
        "inaugural_season": "2015",
        "total_seasons": 11,
        "user_titles": 1,
        "title_seasons": ["2024"],
        "is_migrated": True,
        "notes": "Migrated to Sleeper in 2026 (11 seasons on NFL.com)",
        "champions": [
            {"season": "2025", "champion": "Marco (Mengao)", "record": "13-1"},
            {"season": "2024", "champion": "Henrique (Pombos de BH) 🏆", "record": "8-6", "is_user": True},
            {"season": "2023", "champion": "Rafael (Falcons Cabuloso)", "record": "7-7"},
            {"season": "2022", "champion": "Ricardo (Samonte Codornas)", "record": "9-5"},
            {"season": "2021", "champion": "Vinícius LF (Liverpool Reds)", "record": "10-4"},
            {"season": "2020", "champion": "Lucas Frazão (Minas Xurupytha)", "record": "9-5"},
            {"season": "2019", "champion": "Gervásio (GervasioKing’s Steelers)", "record": "10-4"},
            {"season": "2018", "champion": "Rafael (Falcons Cabuloso)", "record": "9-4"},
            {"season": "2017", "champion": "Lucas Vacilo (Grim Bei Pequerz)", "record": "13-1"},
            {"season": "2016", "champion": "Ricardo (Samonte Codornas)", "record": "9-5"},
            {"season": "2015", "champion": "Vinícius LF (Samonte Fireworkers)", "record": "6-4"},
        ],
    },
}

_LEAGUE_HISTORY_CACHE = {}


def get_league_history(league_id: str, league_name: str = "", user_id: str = None):
    """
    Traverses Sleeper previous_league_id chain to compute:
    - Total seasons active
    - Inaugural season
    - List of past seasons and championship winners
    - Number of titles won by user and title years
    Supports manual overrides for leagues migrated from external platforms.
    """
    cache_key = (str(league_id), str(user_id or ""))
    if cache_key in _LEAGUE_HISTORY_CACHE:
        return _LEAGUE_HISTORY_CACHE[cache_key]

    # Check for manual overrides for migrated leagues
    for key, manual_data in MANUAL_LEAGUE_HISTORY.items():
        if key.lower() in league_name.lower():
            res = {
                "total_seasons": manual_data["total_seasons"],
                "inaugural_season": manual_data["inaugural_season"],
                "user_titles": manual_data["user_titles"],
                "title_seasons": manual_data["title_seasons"],
                "is_migrated": True,
                "notes": manual_data.get("notes", ""),
                "champions": manual_data.get("champions", []),
                "seasons": [],
            }
            _LEAGUE_HISTORY_CACHE[cache_key] = res
            return res

    seasons_history = []
    curr_id = league_id
    seen_ids = set()

    while curr_id and curr_id not in seen_ids:
        seen_ids.add(curr_id)
        try:
            resp = requests.get(f"{BASE_URL}/league/{curr_id}", timeout=10)
            if resp.status_code != 200:
                break
            lg_data = resp.json()
        except Exception:
            break

        season = str(lg_data.get("season", ""))
        status = lg_data.get("status")
        prev_id = lg_data.get("previous_league_id")

        champion_owner_id = None
        user_won = False

        if status == "complete":
            try:
                wb_resp = requests.get(f"{BASE_URL}/league/{curr_id}/winners_bracket", timeout=10)
                if wb_resp.status_code == 200:
                    bracket = wb_resp.json()
                    # Championship match in Sleeper bracket has p=1
                    champ_match = next((m for m in bracket if m.get("p") == 1), None)
                    if champ_match and champ_match.get("w"):
                        champ_roster_id = champ_match["w"]
                        r_resp = requests.get(f"{BASE_URL}/league/{curr_id}/rosters", timeout=10)
                        if r_resp.status_code == 200:
                            rosters_data = r_resp.json()
                            champ_r = next((r for r in rosters_data if r.get("roster_id") == champ_roster_id), None)
                            if champ_r:
                                champion_owner_id = str(champ_r.get("owner_id") or "")
                                if user_id and champion_owner_id == str(user_id):
                                    user_won = True
            except Exception:
                pass

        seasons_history.append({
            "season": season,
            "league_id": curr_id,
            "status": status,
            "champion_owner_id": champion_owner_id,
            "user_won": user_won,
        })

        curr_id = prev_id

    seasons_history.sort(key=lambda s: s.get("season", ""))

    total_seasons = len(seasons_history) if seasons_history else 1
    inaugural_season = seasons_history[0]["season"] if seasons_history else "Current"
    user_titles = sum(1 for s in seasons_history if s.get("user_won"))
    title_seasons = [s["season"] for s in seasons_history if s.get("user_won") and s.get("season")]

    result = {
        "total_seasons": total_seasons,
        "inaugural_season": inaugural_season,
        "user_titles": user_titles,
        "title_seasons": title_seasons,
        "is_migrated": False,
        "notes": "",
        "seasons": seasons_history,
    }
    _LEAGUE_HISTORY_CACHE[cache_key] = result
    return result