"""
Projections Consensus Engine
Aggregates and synchronizes multi-source weekly and rest-of-season (ROS) statistical projections:
1. Sleeper API: Tailored to league custom scoring (PPR, TEP, 6pt Pass TD)
2. FantasyPros Consensus: Aggregated expert consensus projections
3. ESPN Fantasy: Mike Clay analytics and institutional machine learning projections

Yields an authentic Tri-Source Consensus Projected PPG:
    Consensus PPG = (Sleeper PPG + FantasyPros PPG + ESPN PPG) / 3
"""

import csv
import io
import json
import re
from typing import Any, Dict, List, Optional, Tuple
import requests

from src.start_sit import calculate_weekly_projected_points

FP_WEEKLY_URL = "https://raw.githubusercontent.com/dynastyprocess/data/master/files/fp_latest_weekly.csv"
ESPN_BASE_URL = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/segments/0/leaguedefaults/3?view=kona_player_info"

# In-memory session caches to avoid redundant HTTP network requests
_FP_PROJECTIONS_CACHE: Dict[str, Dict[str, Any]] = {}
_ESPN_PROJECTIONS_CACHE: Dict[Tuple[int, int], Dict[str, Any]] = {}
_TRI_CONSENSUS_CACHE: Dict[str, Dict[str, Dict[str, Any]]] = {}


def _normalize_name(name: str) -> str:
    """Removes special characters, suffixes (Jr, III), and lowercases for fuzzy match fallback."""
    if not name:
        return ""
    clean = re.sub(r"[^a-zA-Z0-9\s]", "", str(name)).lower()
    for suffix in (" jr", " sr", " ii", " iii", " iv", " v"):
        if clean.endswith(suffix):
            clean = clean[: -len(suffix)].strip()
    return clean.replace(" ", "")


def fetch_fantasypros_weekly_projections(
    player_ids_raw: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Downloads latest FantasyPros weekly projections (r2p_pts) and maps to Sleeper IDs.
    Returns:
        Dict mapping sleeper_id -> {
            "pts": float,
            "name": str,
            "pos": str,
            "team": str
        }
    """
    if "latest" in _FP_PROJECTIONS_CACHE:
        return _FP_PROJECTIONS_CACHE["latest"]

    # Build ID maps
    fp_to_sleeper = {}
    name_to_sleeper = {}
    if player_ids_raw:
        for r in player_ids_raw:
            s_id = str(r.get("sleeper_id") or "")
            fp_id = str(r.get("fantasypros_id") or "")
            p_name = r.get("name") or ""
            if s_id and s_id != "NA":
                if fp_id and fp_id != "NA":
                    fp_to_sleeper[fp_id] = s_id
                if p_name:
                    name_to_sleeper[_normalize_name(p_name)] = s_id

    result = {}
    try:
        resp = requests.get(FP_WEEKLY_URL, timeout=12)
        if resp.status_code == 200:
            reader = csv.DictReader(io.StringIO(resp.text))
            for row in reader:
                raw_pts = row.get("r2p_pts")
                if not raw_pts or raw_pts == "NA":
                    continue
                try:
                    pts = float(raw_pts)
                except (ValueError, TypeError):
                    continue

                fp_id = str(row.get("fantasypros_id") or "")
                p_name = row.get("player_name") or ""
                pos = row.get("pos") or row.get("page_pos") or ""
                team = row.get("team") or ""

                sleeper_id = fp_to_sleeper.get(fp_id)
                if not sleeper_id and p_name:
                    sleeper_id = name_to_sleeper.get(_normalize_name(p_name))

                if sleeper_id:
                    result[sleeper_id] = {
                        "pts": round(pts, 2),
                        "name": p_name,
                        "pos": pos,
                        "team": team,
                    }
    except Exception as e:
        print(f"Warning: Failed to fetch FantasyPros weekly projections: {e}")

    _FP_PROJECTIONS_CACHE["latest"] = result
    return result


def fetch_espn_weekly_projections(
    season: int = 2024,
    week: int = 1,
    player_ids_raw: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Fetches ESPN Fantasy (Mike Clay model) projections for a specific season and week.
    Maps ESPN player IDs to Sleeper IDs.
    Returns:
        Dict mapping sleeper_id -> {
            "pts": float,
            "season_avg": float,
            "name": str,
            "pos": str
        }
    """
    cache_key = (season, week)
    if cache_key in _ESPN_PROJECTIONS_CACHE:
        return _ESPN_PROJECTIONS_CACHE[cache_key]

    espn_to_sleeper = {}
    name_to_sleeper = {}
    if player_ids_raw:
        for r in player_ids_raw:
            s_id = str(r.get("sleeper_id") or "")
            e_id = str(r.get("espn_id") or "")
            p_name = r.get("name") or ""
            if s_id and s_id != "NA":
                if e_id and e_id != "NA":
                    espn_to_sleeper[e_id] = s_id
                if p_name:
                    name_to_sleeper[_normalize_name(p_name)] = s_id

    url = ESPN_BASE_URL.format(season=season)
    headers = {
        "x-fantasy-filter": json.dumps({
            "players": {
                "limit": 1200,
                "sortPercOwned": {"sortAsc": False, "sortPriority": 1},
            }
        })
    }

    result = {}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            for p_wrapper in data.get("players", []):
                p_info = p_wrapper.get("player") or {}
                e_id = str(p_info.get("id") or "")
                p_name = p_info.get("fullName") or ""

                sleeper_id = espn_to_sleeper.get(e_id)
                if not sleeper_id and p_name:
                    sleeper_id = name_to_sleeper.get(_normalize_name(p_name))

                if not sleeper_id:
                    continue

                stats_list = p_info.get("stats") or []
                week_pts: Optional[float] = None
                season_avg: Optional[float] = None

                for s in stats_list:
                    # statSourceId == 1 denotes projections in ESPN FFL
                    if s.get("statSourceId") == 1:
                        # Weekly projected points
                        if s.get("statSplitTypeId") == 1 and s.get("scoringPeriodId") == week:
                            try:
                                week_pts = float(s.get("appliedTotal", 0.0))
                            except (ValueError, TypeError):
                                pass
                        # Season-long average
                        elif s.get("statSplitTypeId") == 0:
                            try:
                                season_avg = float(s.get("appliedAverage", 0.0))
                            except (ValueError, TypeError):
                                pass

                # Fall back to season average if specific week is on bye / missing
                final_pts = week_pts if (week_pts is not None and week_pts > 0) else (season_avg or 0.0)
                if final_pts > 0:
                    result[sleeper_id] = {
                        "pts": round(final_pts, 2),
                        "season_avg": round(season_avg or final_pts, 2),
                        "name": p_name,
                    }
    except Exception as e:
        print(f"Warning: Failed to fetch ESPN weekly projections: {e}")

    _ESPN_PROJECTIONS_CACHE[cache_key] = result
    return result


def build_tri_source_projections(
    season: str,
    week: int,
    sleeper_projections: Dict[str, Any],
    scoring_settings: Dict[str, Any],
    player_lookup: Dict[str, Any],
    player_ids_raw: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Blends Sleeper, FantasyPros, and ESPN into a comprehensive Tri-Source Consensus Projected PPG lookup.
    Returns:
        Dict mapping sleeper_id -> {
            "consensus_ppg": float,
            "sleeper_ppg": Optional[float],
            "fp_ppg": Optional[float],
            "espn_ppg": Optional[float],
            "sources_count": int,
            "sources_used": List[str]
        }
    """
    try:
        season_int = int(season)
    except (ValueError, TypeError):
        season_int = 2024

    # Fetch secondary sources
    fp_data = fetch_fantasypros_weekly_projections(player_ids_raw=player_ids_raw)
    espn_data = fetch_espn_weekly_projections(season=season_int, week=week, player_ids_raw=player_ids_raw)

    # Collect all relevant player IDs
    all_pids = set(player_lookup.keys()) | set(sleeper_projections.keys()) | set(fp_data.keys()) | set(espn_data.keys())

    consensus_lookup = {}

    for pid in all_pids:
        pid_str = str(pid)
        p_obj = player_lookup.get(pid_str) or {}

        # 1. Sleeper Projection (Custom scoring tailored)
        raw_sleeper = sleeper_projections.get(pid_str)
        sleeper_pts: Optional[float] = None
        if raw_sleeper:
            try:
                calc_slp = calculate_weekly_projected_points(pid_str, raw_sleeper, scoring_settings, p_obj)
                if calc_slp > 0:
                    sleeper_pts = round(calc_slp, 2)
            except Exception:
                pass

        # 2. FantasyPros Projection
        fp_item = fp_data.get(pid_str)
        fp_pts: Optional[float] = round(fp_item["pts"], 2) if (fp_item and fp_item.get("pts", 0) > 0) else None

        # 3. ESPN Projection
        espn_item = espn_data.get(pid_str)
        espn_pts: Optional[float] = round(espn_item["pts"], 2) if (espn_item and espn_item.get("pts", 0) > 0) else None

        # Aggregate available sources
        available_sources = []
        source_names = []

        if sleeper_pts is not None and sleeper_pts > 0:
            available_sources.append(sleeper_pts)
            source_names.append("Sleeper")
        if fp_pts is not None and fp_pts > 0:
            available_sources.append(fp_pts)
            source_names.append("FantasyPros")
        if espn_pts is not None and espn_pts > 0:
            available_sources.append(espn_pts)
            source_names.append("ESPN")

        if available_sources:
            consensus_ppg = round(sum(available_sources) / len(available_sources), 2)
        else:
            consensus_ppg = 0.0

        consensus_lookup[pid_str] = {
            "consensus_ppg": consensus_ppg,
            "sleeper_ppg": sleeper_pts,
            "fp_ppg": fp_pts,
            "espn_ppg": espn_pts,
            "sources_count": len(available_sources),
            "sources_used": source_names,
        }

    return consensus_lookup
