import time
from datetime import date

import requests
import streamlit as st


BASE_URL = "https://api.sleeper.app/v1"

# How long an in-memory projections cache entry stays valid before a fresh
# request is made. Kept shorter than fetch_market_database's 24h
# @st.cache_data TTL in app.py so that every time that outer cache expires
# and re-calls into this module, it is guaranteed to see an expired (or
# already-expired-and-refreshed) entry here too - this cache never blocks
# the outer one from getting genuinely fresh data. Within that 24h window,
# this TTL still absorbs the redundant same-(season, week) calls that
# happen when multiple leagues/workspaces are opened back to back.
PROJECTIONS_CACHE_TTL_SECONDS = 6 * 60 * 60


def get_user(username):
    url = f"{BASE_URL}/user/{username}"

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Warning: Failed to fetch Sleeper user '{username}': {e}")
        return {}


def get_user_leagues(user_id, season):
    url = f"{BASE_URL}/user/{user_id}/leagues/nfl/{season}"

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Warning: Failed to fetch leagues for user {user_id} (season {season}): {e}")
        return []


def get_league_rosters(league_id):
    url = f"{BASE_URL}/league/{league_id}/rosters"

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Warning: Failed to fetch rosters for league {league_id}: {e}")
        return []


def get_user_roster(rosters, user_id):
    for roster in rosters:
        if roster["owner_id"] == user_id:
            return roster

    return None


def get_players():
    url = f"{BASE_URL}/players/nfl"

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Warning: Failed to fetch NFL players database: {e}")
        return {}


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


def get_free_agents(rosters, players, roster_positions=None):
    rostered_ids = set()

    for roster in rosters:
        if roster.get("players"):
            rostered_ids.update(roster["players"])

    # Determine positions used by this league
    if roster_positions:
        valid_positions = {"QB", "RB", "WR", "TE"}
        if any(pos in ("DEF", "DST") for pos in roster_positions):
            valid_positions.add("DEF")
        if any(pos == "K" for pos in roster_positions):
            valid_positions.add("K")
        if any(pos in ("DL", "DE", "DT") for pos in roster_positions):
            valid_positions.update({"DL", "DE", "DT"})
        if any(pos in ("LB",) for pos in roster_positions):
            valid_positions.add("LB")
        if any(pos in ("DB", "CB", "SS", "FS") for pos in roster_positions):
            valid_positions.update({"DB", "CB", "SS", "FS"})
        if any(pos in ("IDP_FLEX", "IDP") for pos in roster_positions):
            valid_positions.update({"DL", "DE", "DT", "LB", "DB", "CB", "SS", "FS"})
    else:
        valid_positions = RELEVANT_POSITIONS

    free_agents = []

    for player_id, player in players.items():
        if player_id in rostered_ids:
            continue

        pos = player.get("position")
        if pos not in valid_positions:
            continue

        if pos == "DEF":
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

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Warning: Failed to fetch traded picks for league {league_id}: {e}")
        return []


def get_league_users(league_id):
    url = f"{BASE_URL}/league/{league_id}/users"

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Warning: Failed to fetch users for league {league_id}: {e}")
        return []


def get_league_draft_type(league_id, expected_rounds=None):
    """
    Returns the league's rookie draft order convention ("linear" or "snake"),
    used to project a team's absolute draft slot from its standing. Prefers
    the draft object whose round count matches expected_rounds (the league's
    current settings.draft_rounds) over a stale startup draft with a
    different round count; falls back to "linear" (the standard dynasty
    rookie-draft convention) when no matching draft is found.
    """
    url = f"{BASE_URL}/league/{league_id}/drafts"

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        drafts = response.json() or []
    except Exception as e:
        print(f"Warning: Failed to fetch drafts for league {league_id}: {e}")
        return "linear"

    if expected_rounds is not None:
        matching = [d for d in drafts if (d.get("settings") or {}).get("rounds") == expected_rounds]
        if matching:
            return matching[0].get("type") or "linear"

    return (drafts[0].get("type") if drafts else None) or "linear"


def get_nfl_state():
    """
    Returns the current NFL state from Sleeper (season, week, season_type).
    """
    url = f"{BASE_URL}/state/nfl"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.json()


_WEEKLY_PROJECTIONS_CACHE = {}
_ROS_PROJECTIONS_CACHE = {}
_WEEKLY_STATS_CACHE = {}

# Real (already-played) stats move live during games, unlike the static
# pre-kickoff numbers in get_weekly_projections, so this cache is kept much
# shorter - long enough to absorb repeat calls across leagues in the same
# Streamlit rerun, short enough to reflect a live-scoring player's stat line
# changing play by play instead of sitting on a 20-minute-old snapshot.
LIVE_STATS_CACHE_TTL_SECONDS = 90


def get_weekly_projections(season: str, week: int):
    """
    Returns live weekly player stats and fantasy projections from Sleeper.
    Cached in-memory by (season, week) for PROJECTIONS_CACHE_TTL_SECONDS, to
    avoid redundant requests across leagues while still picking up updated
    projections (e.g. a player downgraded to "Doubtful" mid-week) within the
    same game week instead of freezing until the process restarts.
    """
    cache_key = (str(season), int(week))
    cached = _WEEKLY_PROJECTIONS_CACHE.get(cache_key)
    if cached is not None:
        cached_at, cached_data = cached
        if time.time() - cached_at < PROJECTIONS_CACHE_TTL_SECONDS:
            return cached_data

    url = f"{BASE_URL}/projections/nfl/regular/{season}/{week}"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict):
            _WEEKLY_PROJECTIONS_CACHE[cache_key] = (time.time(), data)
            return data
        elif isinstance(data, list):
            # Map list to dict keyed by player_id
            mapped = {item.get("player_id", str(i)): item for i, item in enumerate(data)}
            _WEEKLY_PROJECTIONS_CACHE[cache_key] = (time.time(), mapped)
            return mapped
    except Exception as e:
        print(f"Warning: Failed to fetch weekly projections for {season} Week {week}: {e}")
        if cached is not None:
            print(f"Info: Falling back to stale cached weekly projections for {season} Week {week}")
            return cached[1]
        return {}


def get_weekly_stats(season: str, week: int):
    """
    Returns REAL (not projected) weekly player stats from Sleeper. A player_id
    only appears in this dict once their team's game for the week has
    actually kicked off - absent means their game hasn't started yet (or
    they're on a bye), which doubles as a reliable "has this player already
    played this week" signal without needing a separate schedule/scoreboard
    lookup or team-abbreviation cross-referencing (confirmed live: a player
    whose game just finished shows a real stat line here with gp=1, while a
    player whose game hasn't started has no entry at all).

    Cached in-memory by (season, week) for LIVE_STATS_CACHE_TTL_SECONDS -
    much shorter than get_weekly_projections' TTL, since these numbers
    change live during games instead of staying static pre-kickoff.
    """
    cache_key = (str(season), int(week))
    cached = _WEEKLY_STATS_CACHE.get(cache_key)
    if cached is not None:
        cached_at, cached_data = cached
        if time.time() - cached_at < LIVE_STATS_CACHE_TTL_SECONDS:
            return cached_data

    url = f"{BASE_URL}/stats/nfl/regular/{season}/{week}"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict):
            _WEEKLY_STATS_CACHE[cache_key] = (time.time(), data)
            return data
        elif isinstance(data, list):
            mapped = {item.get("player_id", str(i)): item for i, item in enumerate(data)}
            _WEEKLY_STATS_CACHE[cache_key] = (time.time(), mapped)
            return mapped
    except Exception as e:
        print(f"Warning: Failed to fetch weekly stats for {season} Week {week}: {e}")
        if cached is not None:
            print(f"Info: Falling back to stale cached weekly stats for {season} Week {week}")
            return cached[1]
        return {}


def get_ros_projections(season: str, start_week: int = 1, end_week: int = 17):
    """
    Returns aggregated Rest-of-Season (ROS) quantitative projections from Sleeper,
    spanning from start_week through end_week (standard fantasy championship Week 17).

    Each player's statistical projection (points, receptions, yards, touchdowns, etc.)
    is averaged across all remaining weeks N = (end_week - start_week + 1).
    This computes an authentic Effective ROS PPG that inherently accounts for:
    - Zero-point weeks during player injuries (e.g. multi-week IR stints)
    - Zero-point weeks during team NFL bye weeks
    - Expected return-to-play timelines modeled by Sleeper

    Cached in-memory by (season, start_week, end_week) for
    PROJECTIONS_CACHE_TTL_SECONDS - see get_weekly_projections.
    """
    from collections import defaultdict
    import concurrent.futures

    s_wk = max(1, int(start_week))
    e_wk = max(s_wk, int(end_week))
    cache_key = (str(season), s_wk, e_wk)
    cached = _ROS_PROJECTIONS_CACHE.get(cache_key)
    if cached is not None:
        cached_at, cached_data = cached
        if time.time() - cached_at < PROJECTIONS_CACHE_TTL_SECONDS:
            return cached_data

    weeks = list(range(s_wk, e_wk + 1))
    num_weeks = len(weeks)

    def _fetch(w):
        return w, get_weekly_projections(season, w)

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, num_weeks)) as executor:
        weekly_results = dict(executor.map(_fetch, weeks))

    player_sums = defaultdict(lambda: defaultdict(float))
    player_meta = {}

    for w in weeks:
        w_data = weekly_results.get(w) or {}
        for pid, proj in w_data.items():
            if not proj or not isinstance(proj, dict):
                continue
            if pid not in player_meta:
                player_meta[pid] = {
                    "player_id": pid,
                    "pos": proj.get("pos"),
                    "team": proj.get("team"),
                    "player_name": proj.get("player_name"),
                }
            for k, v in proj.items():
                if isinstance(v, (int, float)):
                    player_sums[pid][k] += float(v)

    ros_projections = {}
    for pid, sums in player_sums.items():
        ros_p = dict(player_meta.get(pid, {}))
        for k, total_val in sums.items():
            ros_p[k] = round(total_val / num_weeks, 3)
        ros_projections[pid] = ros_p

    _ROS_PROJECTIONS_CACHE[cache_key] = (time.time(), ros_projections)
    return ros_projections


_LEAGUE_MATCHUPS_CACHE = {}

# Matchup points (players_points) move live during games, same as
# get_weekly_stats - a permanent cache would freeze a live score at whatever
# it was the first time this (league_id, week) pair was fetched for the rest
# of the running process. Kept slightly longer than LIVE_STATS_CACHE_TTL_SECONDS
# since matchup scoring is a coarser per-roster total, not a play-by-play feed.
LEAGUE_MATCHUPS_CACHE_TTL_SECONDS = 5 * 60


def get_league_matchups(league_id: str, week: int, current_week: int = None):
    """
    Returns matchup pairings and scoring for a given league and week.

    current_week (the league's actual active NFL week, when the caller knows
    it) decides the cache TTL: a week strictly before current_week is already
    final and immutable, so it's cached for LEAGUE_HISTORY_CACHE_TTL_SECONDS -
    the same long TTL get_league_history uses for the same reason. The
    current (or a future) week can still change live during games, so it
    keeps the short LEAGUE_MATCHUPS_CACHE_TTL_SECONDS. Callers that don't
    pass current_week (or pass None) get the safe short-TTL default, since
    an unknown week must be assumed to still be live.

    This split matters because get_league_schedule and
    compute_historical_standings call this once per week over a wide range
    (often 1-18) - without it, every already-completed week would keep
    re-fetching from Sleeper every LEAGUE_MATCHUPS_CACHE_TTL_SECONDS forever,
    even though its result can never change again.
    """
    cache_key = (str(league_id), int(week))
    is_historical = current_week is not None and week < current_week
    ttl = LEAGUE_HISTORY_CACHE_TTL_SECONDS if is_historical else LEAGUE_MATCHUPS_CACHE_TTL_SECONDS

    cached = _LEAGUE_MATCHUPS_CACHE.get(cache_key)
    if cached is not None:
        cached_at, cached_data = cached
        if time.time() - cached_at < ttl:
            return cached_data

    url = f"{BASE_URL}/league/{league_id}/matchups/{week}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 404:
            return []
        response.raise_for_status()
        data = response.json()
        _LEAGUE_MATCHUPS_CACHE[cache_key] = (time.time(), data)
        return data
    except Exception as e:
        print(f"Warning: Failed to fetch league matchups for league {league_id} Week {week}: {e}")
        if cached is not None:
            print(f"Info: Falling back to stale cached matchups for league {league_id} Week {week}")
            return cached[1]
        return []


NFL_SCORES_URL = "https://api.sleeper.app/scores/nfl/regular/{season}/{week}"

_NFL_GAME_STATUS_CACHE = {}

# Same live-data cadence as LEAGUE_MATCHUPS_CACHE_TTL_SECONDS - this is the
# only Sleeper feed that actually distinguishes a game currently in progress
# from one that has finished; get_weekly_stats' stat lines look identical
# either way, so this fills that gap for the live-status badge.
NFL_GAME_STATUS_CACHE_TTL_SECONDS = 90


def get_nfl_game_status_raw(season: str, week: int):
    """
    Fetches per-game live status ("pre_game" / "in_progress" / "complete")
    for every NFL game in a given week from Sleeper's public scoreboard feed
    (undocumented, but stable - same shape as the site's own live scoreboard).
    Cached in-memory by (season, week) for NFL_GAME_STATUS_CACHE_TTL_SECONDS.
    """
    cache_key = (str(season), int(week))
    cached = _NFL_GAME_STATUS_CACHE.get(cache_key)
    if cached is not None:
        cached_at, cached_data = cached
        if time.time() - cached_at < NFL_GAME_STATUS_CACHE_TTL_SECONDS:
            return cached_data

    url = NFL_SCORES_URL.format(season=season, week=week)
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        _NFL_GAME_STATUS_CACHE[cache_key] = (time.time(), data)
        return data
    except Exception as e:
        print(f"Warning: Failed to fetch NFL game status for {season} Week {week}: {e}")
        if cached is not None:
            print(f"Info: Falling back to stale cached NFL game status for {season} Week {week}")
            return cached[1]
        return []


def build_team_game_status_map(scores_raw):
    """
    Maps each NFL team abbreviation to its game's live status this week
    ("pre_game" / "in_progress" / "complete"), from get_nfl_game_status_raw.
    A team absent from the returned map has a bye this week.
    """
    team_status = {}
    for game in (scores_raw or []):
        status = game.get("status")
        metadata = game.get("metadata") or {}
        home = metadata.get("home_team")
        away = metadata.get("away_team")
        if home:
            team_status[home] = status
        if away:
            team_status[away] = status
    return team_status


def get_league_schedule(league_id: str, start_week: int = 1, end_week: int = 18, current_week: int = None):
    """
    Returns the head-to-head regular season schedule map for the league.
    Format: dict mapping week -> list of (roster_id_1, roster_id_2) pairings.

    current_week (the league's actual active NFL week, when known) is
    forwarded to get_league_matchups so weeks already in the past get its
    long, "this can never change again" cache TTL instead of being
    re-fetched from Sleeper every few minutes like the still-live current
    week - see get_league_matchups for the full rationale.
    """
    schedule = {}
    for w in range(start_week, end_week + 1):
        matchups_data = get_league_matchups(league_id, w, current_week=current_week)
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


def compute_historical_standings(league_id: str, rosters: list, through_week: int) -> dict:
    """
    Computes cumulative wins, losses, ties, and points scored (PF)
    for each roster from completed matchup weeks 1 through through_week.
    If through_week <= 0, returns 0-0 records and 0.0 PF for all rosters.

    Every week iterated here (1..through_week) is by this function's own
    contract already completed, so get_league_matchups is always told
    current_week=through_week + 1 - guaranteeing each of those weeks gets
    the long "immutable" cache TTL rather than the short live one.
    """
    records = {
        r["roster_id"]: {"wins": 0, "losses": 0, "ties": 0, "pf": 0.0}
        for r in rosters
    }
    if through_week <= 0:
        return records

    for w in range(1, through_week + 1):
        matchups_data = get_league_matchups(league_id, w, current_week=through_week + 1)
        if not matchups_data:
            continue

        by_matchup_id = {}
        for m in matchups_data:
            m_id = m.get("matchup_id")
            if m_id is not None:
                by_matchup_id.setdefault(m_id, []).append(m)

        for m_id, pair in by_matchup_id.items():
            if len(pair) == 2:
                m1, m2 = pair[0], pair[1]
                r1, r2 = m1.get("roster_id"), m2.get("roster_id")
                pts1 = float(m1.get("points") or 0.0)
                pts2 = float(m2.get("points") or 0.0)

                if r1 in records and r2 in records:
                    records[r1]["pf"] = round(records[r1]["pf"] + pts1, 2)
                    records[r2]["pf"] = round(records[r2]["pf"] + pts2, 2)

                    if pts1 > 0 or pts2 > 0:
                        if pts1 > pts2:
                            records[r1]["wins"] += 1
                            records[r2]["losses"] += 1
                        elif pts2 > pts1:
                            records[r2]["wins"] += 1
                            records[r1]["losses"] += 1
                        else:
                            records[r1]["ties"] += 1
                            records[r2]["ties"] += 1

    return records


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

LEAGUE_HISTORY_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60


@st.cache_data(ttl=LEAGUE_HISTORY_CACHE_TTL_SECONDS, show_spinner=False)
def get_league_history(league_id: str, league_name: str = "", user_id: str = None):
    """
    Traverses Sleeper previous_league_id chain to compute:
    - Total seasons active
    - Inaugural season
    - List of past seasons and championship winners
    - Number of titles won by user and title years
    Supports manual overrides for leagues migrated from external platforms.

    Cached via st.cache_data (7 days) rather than a plain module-level dict:
    completed-season history is immutable, so a long TTL is safe, and unlike
    a bare dict this survives correctly across Streamlit's caching layer
    (a bare dict looked like a cache but measured no faster on repeat calls -
    see PROJECTIONS_CACHE_TTL_SECONDS above for the same lesson learned with
    get_weekly_projections). This also walks several sequential live Sleeper
    API requests per league (one per past season, plus a winners_bracket and
    rosters call for each completed one), so caching it matters a lot for
    the League Workspaces grid, which calls this once per league.
    """
    # Check for manual overrides for migrated leagues
    for key, manual_data in MANUAL_LEAGUE_HISTORY.items():
        if key.lower() in league_name.lower():
            return {
                "total_seasons": manual_data["total_seasons"],
                "inaugural_season": manual_data["inaugural_season"],
                "user_titles": manual_data["user_titles"],
                "title_seasons": manual_data["title_seasons"],
                "is_migrated": True,
                "notes": manual_data.get("notes", ""),
                "champions": manual_data.get("champions", []),
                "seasons": [],
            }

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
    return result