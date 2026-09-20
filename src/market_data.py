import csv
import io
import json
import math
import os
import re
import time
import requests

from src.start_sit import calculate_weekly_projected_points


FPECR_URL = "https://raw.githubusercontent.com/dynastyprocess/data/master/files/db_fpecr_latest.csv"
PLAYERIDS_URL = "https://raw.githubusercontent.com/dynastyprocess/data/master/files/db_playerids.csv"
VALUES_PLAYERS_URL = "https://raw.githubusercontent.com/dynastyprocess/data/master/files/values-players.csv"
VALUES_PICKS_URL = "https://raw.githubusercontent.com/dynastyprocess/data/master/files/values-picks.csv"

# Our own scrape of FantasyPros' Rest-of-Season PPR overall rankings (see
# scripts/scrape_fantasypros_ros.py), published back to this same repo by a
# scheduled GitHub Action. Supplies "redraft-*" page_type rows only -
# "dynasty-*" rows still come exclusively from FPECR_URL/DynastyProcess.
FP_ROS_PPR_URL = "https://raw.githubusercontent.com/henriquefrz/fantasy-dynasty-manager/main/data/fp_ros_ppr_latest.json"

POSITIONS = ["QB", "RB", "WR", "TE", "K"]

TEAM_ABBR_ALIASES = {
    "JAC": "JAX",
}

# Consensus Model Weights
# Default: Equal Share (1/3 each)
WEIGHT_FC = 1.0 / 3.0   # FantasyCalc: Ground truth from actual completed Sleeper trades
WEIGHT_KTC = 1.0 / 3.0  # KeepTradeCut: Live crowdsourced market sentiment / hype
WEIGHT_DP = 1.0 / 3.0   # DynastyProcess: Expert consensus rankings (ECR) projection curve

# Empirical Consensus Weights
EMPIRICAL_WEIGHT_FC = 0.40
EMPIRICAL_WEIGHT_KTC = 0.35
EMPIRICAL_WEIGHT_DP = 0.25

VALUATION_MODES = {
    "equal": "Equal Share (33.3% FC / 33.3% KTC / 33.3% DP) [Default]",
    "empirical": "Empirical Market Consensus (40% FC / 35% KTC / 25% DP)",
    "ktc": "KeepTradeCut Only (100% KTC)",
    "fc": "FantasyCalc Only (100% FantasyCalc)",
    "dp": "DynastyProcess Only (100% DynastyProcess)",
}

CSV_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".cache_data", "market_csvs")

KTC_CACHE_TTL_SECONDS = 24 * 60 * 60

# KTC natively tiers TE market value by TE Premium bonus: "tep" matches a
# league-wide +0.5 PPR bonus for TEs, "tepp" matches a +1.0 PPR bonus. Any
# other bonus (including 0) has no matching KTC tier, so it is left unadjusted.
KTC_TEP_MIN_BASE_VALUE = 400.0
KTC_TEP_MAX_PCT = 0.80


def _ktc_tep_tier_key(bonus_rec_te):
    if bonus_rec_te == 0.5:
        return "tep"
    if bonus_rec_te == 1.0:
        return "tepp"
    return None


def _download_csv(url):
    filename = url.split("/")[-1]
    cache_path = os.path.join(CSV_CACHE_DIR, filename)
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        csv_text = response.text
        try:
            os.makedirs(CSV_CACHE_DIR, exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                f.write(csv_text)
        except Exception:
            pass
        reader = csv.DictReader(io.StringIO(csv_text))
        return list(reader)
    except Exception as e:
        print(f"Warning: Failed to download CSV from {url}: {e}")
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    print(f"Info: Successfully loaded cached backup for {filename}")
                    return list(csv.DictReader(f))
            except Exception as cache_err:
                print(f"Warning: Failed to read cached CSV {cache_path}: {cache_err}")
        return []


def get_fp_rankings_raw():
    return _download_csv(FPECR_URL)


# Scraped only 3x/week (see .github/workflows/scrape-fantasypros-ros.yml),
# so a full day of staleness is acceptable - same cadence as KTC_CACHE_TTL_SECONDS.
FP_ROS_CACHE_TTL_SECONDS = 24 * 60 * 60


def _fetch_fp_ros_payload():
    """
    Fetches our own scraped FantasyPros Rest-of-Season PPR rankings payload
    ({"scraped_at": "<ISO UTC timestamp>", "rows": [...]} - see
    scripts/scrape_fantasypros_ros.py and FP_ROS_PPR_URL) from this repo's
    own GitHub raw content, published by the scheduled scraper workflow.
    Reused from disk cache in .cache_data/market_csvs/ when younger than
    FP_ROS_CACHE_TTL_SECONDS; falls back to a stale cached copy on fetch
    failure, same resilience pattern as the other raw fetchers in this module.

    Internal - callers want either get_fp_ros_rankings_raw() (the "rows"
    list, for build_positional_lookup) or get_fp_ros_rankings_scraped_at()
    (the timestamp, for freshness checks) - both share this same fetch/cache
    so the payload is only ever downloaded once per TTL window.
    """
    cache_path = os.path.join(CSV_CACHE_DIR, "fp_ros_ppr_latest.json")

    if os.path.exists(cache_path):
        cache_age = time.time() - os.path.getmtime(cache_path)
        if cache_age < FP_ROS_CACHE_TTL_SECONDS:
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    print(f"Info: Using cached FantasyPros ROS rankings (age {cache_age / 3600:.1f}h)")
                    return json.load(f)
            except Exception as cache_err:
                print(f"Warning: Failed to read cached FantasyPros ROS rankings {cache_path}: {cache_err}")

    try:
        response = requests.get(FP_ROS_PPR_URL, timeout=15)
        response.raise_for_status()
        data = response.json()
        if data and data.get("rows"):
            try:
                os.makedirs(CSV_CACHE_DIR, exist_ok=True)
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(data, f)
            except Exception:
                pass
        return data
    except Exception as e:
        print(f"Warning: Failed to fetch FantasyPros ROS rankings: {e}")
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    print("Info: Loaded cached backup for FantasyPros ROS rankings")
                    return json.load(f)
            except Exception as cache_err:
                print(f"Warning: Failed to read cached FantasyPros ROS rankings {cache_path}: {cache_err}")
        return {"scraped_at": None, "rows": []}


def get_fp_ros_rankings_raw():
    """
    Returns the "redraft-*" page_type rows list (the part
    build_positional_lookup actually consumes) from the scraped FantasyPros
    ROS payload. See get_fp_ros_rankings_scraped_at() for the payload's
    timestamp, used by get_market_data_freshness to detect a stale file.
    """
    return _fetch_fp_ros_payload().get("rows") or []


def get_fp_ros_rankings_scraped_at():
    """
    Returns the ISO UTC timestamp string the scraped FantasyPros ROS payload
    was generated at, or None if unavailable (fetch failed with no cache,
    or an old-format cached file predates this field). Used by
    get_market_data_freshness to flag the source as stale even when the
    fetch itself succeeds but the underlying scrape hasn't run in days.
    """
    return _fetch_fp_ros_payload().get("scraped_at")


def get_player_ids_raw():
    return _download_csv(PLAYERIDS_URL)


def get_values_players_raw():
    return _download_csv(VALUES_PLAYERS_URL)


def get_values_picks_raw():
    return _download_csv(VALUES_PICKS_URL)


def get_fantasycalc_data_raw(is_dynasty=True, is_superflex=True):
    """
    Fetches current market values from FantasyCalc based on thousands of actual
    completed trades across Sleeper and MFL fantasy leagues.
    Supports both Dynasty and Redraft, in Superflex or 1QB.
    """
    num_qbs = 2 if is_superflex else 1
    dynasty_str = "true" if is_dynasty else "false"
    url = f"https://api.fantasycalc.com/values/current?isDynasty={dynasty_str}&numQbs={num_qbs}"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Warning: Failed to fetch FantasyCalc data: {e}")
        return []


def get_ktc_data_raw(is_superflex=True):
    """
    Fetches market values from KeepTradeCut (KTC) crowdsourced rankings.
    Reused from disk cache in .cache_data/market_csvs/ when younger than
    KTC_CACHE_TTL_SECONDS (24h); otherwise scrapes the live page, extracting
    structured JSON from <script type="application/json" id="ktc-players">,
    with backward-compatible fallback to inline playersArray.
    """
    fmt = 2 if is_superflex else 1
    cache_path = os.path.join(CSV_CACHE_DIR, f"ktc_data_raw_{'sf' if is_superflex else '1qb'}.json")

    if os.path.exists(cache_path):
        cache_age = time.time() - os.path.getmtime(cache_path)
        if cache_age < KTC_CACHE_TTL_SECONDS:
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    print(f"Info: Using cached KeepTradeCut data ({'SF' if is_superflex else '1QB'}, age {cache_age / 3600:.1f}h)")
                    return json.load(f)
            except Exception as cache_err:
                print(f"Warning: Failed to read cached KTC data {cache_path}: {cache_err}")

    url = f"https://keeptradecut.com/dynasty-rankings?filters=QB|WR|RB|TE|RDP&format={fmt}"
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        script_match = re.search(r'<script[^>]*id=["\']ktc-players["\'][^>]*>(.*?)</script>', response.text, re.DOTALL)
        if script_match:
            data = json.loads(script_match.group(1))
        else:
            matches = re.findall(r"var playersArray\s*=\s*(\[.*?\]);", response.text, re.DOTALL)
            data = json.loads(matches[0]) if matches else []
        if data:
            try:
                os.makedirs(CSV_CACHE_DIR, exist_ok=True)
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(data, f)
            except Exception:
                pass
        return data
    except Exception as e:
        print(f"Warning: Failed to fetch KeepTradeCut data: {e}")
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    print(f"Info: Loaded cached backup for KeepTradeCut data ({'SF' if is_superflex else '1QB'})")
                    return json.load(f)
            except Exception as cache_err:
                print(f"Warning: Failed to read cached KTC data {cache_path}: {cache_err}")
        return []


def get_ktc_fantasy_rankings_raw(is_superflex=True):
    """
    Fetches KeepTradeCut's redraft/seasonal "Fantasy Rankings" (distinct from
    dynasty-rankings, and capped at KTC's top ~300 redraft-relevant players).
    Acts as Pillar 3 in the Tri-Factor Redraft/ROS Consensus Engine.
    Same embedded <script id="ktc-players"> JSON shape (including tep/tepp
    TE Premium tiers) as get_ktc_data_raw, reused from disk cache in
    .cache_data/market_csvs/ when younger than KTC_CACHE_TTL_SECONDS (24h).
    """
    fmt = 2 if is_superflex else 1
    cache_path = os.path.join(CSV_CACHE_DIR, f"ktc_fantasy_rankings_raw_{'sf' if is_superflex else '1qb'}.json")

    if os.path.exists(cache_path):
        cache_age = time.time() - os.path.getmtime(cache_path)
        if cache_age < KTC_CACHE_TTL_SECONDS:
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    print(f"Info: Using cached KTC fantasy rankings ({'SF' if is_superflex else '1QB'}, age {cache_age / 3600:.1f}h)")
                    return json.load(f)
            except Exception as cache_err:
                print(f"Warning: Failed to read cached KTC fantasy rankings {cache_path}: {cache_err}")

    url = f"https://keeptradecut.com/fantasy-rankings?filters=QB|WR|RB|TE&format={fmt}"
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        script_match = re.search(r'<script[^>]*id=["\']ktc-players["\'][^>]*>(.*?)</script>', response.text, re.DOTALL)
        data = json.loads(script_match.group(1)) if script_match else []
        if data:
            try:
                os.makedirs(CSV_CACHE_DIR, exist_ok=True)
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(data, f)
            except Exception:
                pass
        return data
    except Exception as e:
        print(f"Warning: Failed to fetch KTC fantasy rankings: {e}")
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    print(f"Info: Loaded cached backup for KTC fantasy rankings ({'SF' if is_superflex else '1QB'})")
                    return json.load(f)
            except Exception as cache_err:
                print(f"Warning: Failed to read cached KTC fantasy rankings {cache_path}: {cache_err}")
        return []



def _build_player_lookup(fp_rankings_raw, player_ids_raw, ranking_prefix, is_superflex=False):
    fp_id_to_sleeper_id = {}

    for row in player_ids_raw:
        sleeper_id = row.get("sleeper_id")
        fp_id = row.get("fantasypros_id")

        if sleeper_id and sleeper_id != "NA" and fp_id and fp_id != "NA":
            fp_id_to_sleeper_id[fp_id] = sleeper_id

    pos_page_types = {f"{ranking_prefix}-{pos.lower()}" for pos in POSITIONS}
    op_page = f"{ranking_prefix}-op"
    std_page = f"{ranking_prefix}-overall"
    has_op = any(row.get("page_type") == op_page for row in fp_rankings_raw)
    overall_page_type = op_page if (is_superflex and has_op) else std_page

    lookup = {}

    # 1. Collect and sort overall rows strictly by ecr_val
    overall_rows = []
    seen_overall = set()
    for row in fp_rankings_raw:
        if row.get("page_type") == overall_page_type:
            sleeper_id = fp_id_to_sleeper_id.get(row.get("id"))
            if sleeper_id and sleeper_id not in seen_overall:
                try:
                    ecr_val = float(row["ecr"])
                    overall_rows.append((sleeper_id, ecr_val, row.get("player", ""), row.get("pos", "")))
                    seen_overall.add(sleeper_id)
                except (ValueError, TypeError):
                    continue
    overall_rows.sort(key=lambda x: x[1])
    overall_map = {sid: float(idx) for idx, (sid, _, _, _) in enumerate(overall_rows, start=1)}

    # 2. Collect and sort positional rows strictly by ecr_val within each position
    pos_rows_by_pos = {}
    seen_pos = set()
    for row in fp_rankings_raw:
        ptype = row.get("page_type")
        if ptype in pos_page_types:
            sleeper_id = fp_id_to_sleeper_id.get(row.get("id"))
            if sleeper_id and sleeper_id not in seen_pos:
                try:
                    ecr_val = float(row["ecr"])
                    pos_key = row.get("pos") or ptype.split("-")[-1].upper()
                    pos_rows_by_pos.setdefault(pos_key, []).append((sleeper_id, ecr_val, row.get("player", ""), pos_key))
                    seen_pos.add(sleeper_id)
                except (ValueError, TypeError):
                    continue

    for pos_key, p_list in pos_rows_by_pos.items():
        p_list.sort(key=lambda x: x[1])
        for idx, (sid, ecr_val, pname, pos) in enumerate(p_list, start=1):
            lookup[sid] = {
                "rank_ecr": float(idx),
                "rank_ecr_pos": float(idx),
                "raw_ecr": ecr_val,
                "player_name": pname,
                "position": pos,
            }

    # Attach overall ECR to each player in lookup
    for s_id, o_ecr in overall_map.items():
        if s_id in lookup:
            lookup[s_id]["rank_ecr_overall"] = o_ecr
        else:
            p_match = next((item for item in overall_rows if item[0] == s_id), None)
            lookup[s_id] = {
                "rank_ecr": 999.0,
                "rank_ecr_pos": 999.0,
                "rank_ecr_overall": o_ecr,
                "player_name": p_match[2] if p_match else "",
                "position": p_match[3] if p_match else "",
            }

    for item in lookup.values():
        if "rank_ecr_overall" not in item:
            item["rank_ecr_overall"] = 999.0
        if "rank_ecr_pos" not in item:
            item["rank_ecr_pos"] = item.get("rank_ecr", 999.0)

    return lookup


def _build_dst_lookup(fp_rankings_raw, ranking_prefix):
    dst_page_type = f"{ranking_prefix}-dst"

    lookup = {}

    for row in fp_rankings_raw:
        if row["page_type"] != dst_page_type:
            continue

        team = row.get("team")

        if not team:
            continue

        team = TEAM_ABBR_ALIASES.get(team, team)

        try:
            rank_ecr = float(row["ecr"])
        except (ValueError, TypeError):
            continue

        lookup[team] = {
            "rank_ecr": rank_ecr,
            "rank_ecr_pos": rank_ecr,
            "rank_ecr_overall": 999.0,
            "player_name": row["player"],
            "position": row["pos"],
        }

    return lookup


def build_positional_lookup(fp_rankings_raw, player_ids_raw, ranking_type, is_superflex=False):
    lookup = _build_player_lookup(fp_rankings_raw, player_ids_raw, ranking_type, is_superflex=is_superflex)
    dst_lookup = _build_dst_lookup(fp_rankings_raw, ranking_type)

    lookup.update(dst_lookup)

    return lookup


def _extract_fc_player_values(fc_raw):
    """
    Extracts Sleeper ID -> FantasyCalc market value.
    """
    fc_values = {}
    for item in fc_raw:
        player_info = item.get("player") or {}
        sleeper_id = str(player_info.get("sleeperId") or "")
        if sleeper_id and sleeper_id != "None":
            try:
                fc_values[sleeper_id] = float(item.get("value", 0.0))
            except (ValueError, TypeError):
                continue
    return fc_values


def _extract_fc_player_metadata(fc_raw):
    """
    Extracts Sleeper ID -> dict(name, position) from FantasyCalc feed.
    """
    meta = {}
    for item in (fc_raw or []):
        player_info = item.get("player") or {}
        sleeper_id = str(player_info.get("sleeperId") or "")
        if sleeper_id and sleeper_id != "None":
            name = player_info.get("name") or ""
            pos = player_info.get("position") or ""
            if sleeper_id.startswith("FP_"):
                pos = "PICK"
            meta[sleeper_id] = {"name": name, "position": pos}
    return meta


def parse_fp_pick_id(sid):
    """
    Parses a FantasyCalc pick ID (e.g. 'FP_2027_early_0' or 'FP_2027_1')
    into (season_str, round_int, tier_str).
    """
    parts = str(sid).split("_")
    if len(parts) == 4:
        year = parts[1]
        tier = parts[2].lower()
        try:
            r_num = int(parts[3]) + 1
        except ValueError:
            r_num = 1
        return (year, r_num, tier)
    elif len(parts) == 3:
        year = parts[1]
        try:
            r_num = int(parts[2])
        except ValueError:
            r_num = 1
        return (year, r_num, "mid")
    return None


def _extract_ktc_player_values(ktc_raw, player_ids_raw, is_superflex=True):
    """
    Extracts Sleeper ID -> KeepTradeCut market value.
    Maps using ktc_id and mfl_id from db_playerids.csv.
    """
    ktc_id_to_sleeper = {
        str(r["ktc_id"]): str(r["sleeper_id"])
        for r in player_ids_raw
        if r.get("ktc_id") and r.get("sleeper_id")
    }
    mfl_id_to_sleeper = {
        str(r["mfl_id"]): str(r["sleeper_id"])
        for r in player_ids_raw
        if r.get("mfl_id") and r.get("sleeper_id")
    }

    ktc_values = {}
    val_key = "superflexValues" if is_superflex else "oneQBValues"

    for p in ktc_raw:
        if p.get("position") == "RDP":
            continue

        p_id = str(p.get("playerID", ""))
        mfl_id = str(p.get("mflid", ""))

        s_id = ktc_id_to_sleeper.get(p_id) or mfl_id_to_sleeper.get(mfl_id)
        if not s_id:
            continue

        try:
            val = float(p.get(val_key, {}).get("value", 0.0))
            ktc_values[s_id] = val
        except (ValueError, TypeError):
            continue

    return ktc_values


def _extract_ktc_te_tiers(ktc_raw, player_ids_raw, is_superflex=True):
    """
    Extracts Sleeper ID -> KTC base/tep/tepp values for TE players only.
    Powers apply_ktc_te_premium's dynasty TE adjustment and the redraft
    KTC pillar's TE value selection - both need the same three tiers.
    """
    ktc_id_to_sleeper = {
        str(r["ktc_id"]): str(r["sleeper_id"])
        for r in player_ids_raw
        if r.get("ktc_id") and r.get("sleeper_id")
    }
    mfl_id_to_sleeper = {
        str(r["mfl_id"]): str(r["sleeper_id"])
        for r in player_ids_raw
        if r.get("mfl_id") and r.get("sleeper_id")
    }

    val_key = "superflexValues" if is_superflex else "oneQBValues"
    te_tiers = {}

    for p in ktc_raw:
        if p.get("position") != "TE":
            continue

        p_id = str(p.get("playerID", ""))
        mfl_id = str(p.get("mflid", ""))
        s_id = ktc_id_to_sleeper.get(p_id) or mfl_id_to_sleeper.get(mfl_id)
        if not s_id:
            continue

        vals = p.get(val_key, {}) or {}
        try:
            te_tiers[s_id] = {
                "base": float(vals.get("value", 0.0)),
                "tep": float((vals.get("tep") or {}).get("value", 0.0)),
                "tepp": float((vals.get("tepp") or {}).get("value", 0.0)),
            }
        except (ValueError, TypeError):
            continue

    return te_tiers


def _extract_dp_player_values(values_players_raw, player_ids_raw, is_superflex=True):
    """
    Extracts Sleeper ID -> DynastyProcess market value.
    """
    fp_id_to_sleeper = {
        str(r["fantasypros_id"]): str(r["sleeper_id"])
        for r in player_ids_raw
        if r.get("fantasypros_id") and r.get("sleeper_id")
    }

    val_col = "value_2qb" if is_superflex else "value_1qb"
    dp_values = {}

    for row in values_players_raw:
        fp_id = str(row.get("fp_id") or "")
        s_id = fp_id_to_sleeper.get(fp_id)
        if not s_id:
            continue

        try:
            dp_values[s_id] = float(row.get(val_col, 0.0))
        except (ValueError, TypeError):
            continue

    return dp_values


def compute_kicker_dst_value(rank_ecr):
    """
    Assigns a realistic market value (100 to 650 pts) to Kickers and Defenses
    based on their FantasyPros positional Expert Consensus Ranking (ECR).
    """
    if rank_ecr is not None and rank_ecr < 900:
        val = 650.0 - (rank_ecr - 1.0) * 18.0
        return max(50.0, min(650.0, round(val, 1)))
    return 50.0


def compute_composite_value(fc_val, ktc_val, dp_val, mode="equal", rank_ecr=None, is_pick=False, position=None):
    """
    Computes player or pick market value based on the chosen valuation mode:
    - 'equal': Equal Share (1/3 FC, 1/3 KTC, 1/3 DP) [Default]
    - 'empirical': Empirical Consensus (40% FC, 35% KTC, 25% DP)
    - 'ktc': KeepTradeCut Only (100% KTC)
    - 'fc': FantasyCalc Only (100% FantasyCalc)
    - 'dp': DynastyProcess Only (100% DynastyProcess)

    Special handling:
    - Kickers (K) and Defenses (DST/DEF) are calibrated via their FantasyPros ECR rank.
    - Skill players (QB/RB/WR/TE) with only KTC values and no FC/DP corroboration
      (e.g., Michael Trigg, Gabe Davis, David Bell) strictly receive 0.0.
    """
    pos = str(position or "").upper()
    if pos in ("K", "DST", "DEF"):
        return compute_kicker_dst_value(rank_ecr)

    has_fc = fc_val is not None and float(fc_val) > 0
    has_dp = dp_val is not None and float(dp_val) > 0
    has_ktc = ktc_val is not None and float(ktc_val) > 0

    # For NFL skill players (not rookie draft picks):
    # If only KTC has a quote without FC trades or DP expert valuation, it is
    # unconfirmed crowdsourced hype. We strictly set its value to 0.0.
    if not is_pick:
        if has_ktc and not has_fc and not has_dp:
            return 0.0
        if not has_fc and not has_dp and not has_ktc:
            return 0.0

    if mode == "ktc":
        return float(ktc_val) if ktc_val is not None else 0.0
    elif mode == "fc":
        return float(fc_val) if fc_val is not None else 0.0
    elif mode == "dp":
        return float(dp_val) if dp_val is not None else 0.0
    elif mode == "empirical":
        w_fc, w_ktc, w_dp = EMPIRICAL_WEIGHT_FC, EMPIRICAL_WEIGHT_KTC, EMPIRICAL_WEIGHT_DP
    else:  # "equal" default
        w_fc, w_ktc, w_dp = WEIGHT_FC, WEIGHT_KTC, WEIGHT_DP

    available_weights = []
    available_values = []
    if has_fc:
        available_weights.append(w_fc)
        available_values.append(float(fc_val))
    if has_ktc:
        available_weights.append(w_ktc)
        available_values.append(float(ktc_val))
    if has_dp:
        available_weights.append(w_dp)
        available_values.append(float(dp_val))

    if not available_weights:
        return 0.0

    total_w = sum(available_weights)
    composite = sum(w * v for w, v in zip(available_weights, available_values)) / total_w

    return round(composite, 1)


# fp_ros_rankings is only re-scraped 3x/week (see
# .github/workflows/scrape-fantasypros-ros.yml); this gives generous slack
# over that ~2-3 day cadence before flagging the file as stale, since a
# successful fetch of an old file looks identical to a fresh one otherwise.
FP_ROS_STALE_THRESHOLD_DAYS = 4


def get_market_data_freshness(
    fp_raw=None,
    dp_raw=None,
    ktc_sf=None,
    ktc_1qb=None,
    fc_sf=None,
    fc_1qb=None,
    ktc_redraft_sf=None,
    ktc_redraft_1qb=None,
    fp_ros_rows=None,
    fp_ros_scraped_at=None,
):
    """
    Returns timestamp / scrape date status for each connected data source,
    including whether the most recent fetch this session actually succeeded.

    Every raw fetcher in this module (get_ktc_data_raw, get_ktc_fantasy_rankings_raw,
    get_fantasycalc_data_raw, _download_csv-backed FP/DP feeds) returns an empty
    list on failure instead of raising, so an empty payload here is the signal a
    source failed to update - "ok" reflects that, and "status" surfaces it in
    plain text instead of always claiming "Live Current" regardless of what happened.

    fp_ros_rows/fp_ros_scraped_at (see get_fp_ros_rankings_raw/
    get_fp_ros_rankings_scraped_at) get a second, independent check: a
    successful fetch of that file only proves GitHub served *a* file, not
    that the scheduled scraper actually ran recently - so "ok" reflects the
    fetch outcome (same as every other source here) while "stale" separately
    flags a file whose own scraped_at timestamp is older than
    FP_ROS_STALE_THRESHOLD_DAYS, which a plain fetch-success check can't see.
    """
    from datetime import datetime, timezone
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    fp_date = None
    if fp_raw and len(fp_raw) > 0:
        fp_date = fp_raw[0].get("scrape_date")

    dp_date = None
    if dp_raw and len(dp_raw) > 0:
        dp_date = dp_raw[0].get("scrape_date")

    fp_ok = bool(fp_raw)
    dp_ok = bool(dp_raw)
    # Both Superflex and 1QB variants are fetched independently - only call the
    # source "ok" if neither variant silently came back empty.
    ktc_ok = bool(ktc_sf) and bool(ktc_1qb)
    fc_ok = bool(fc_sf) and bool(fc_1qb)
    ktc_redraft_ok = bool(ktc_redraft_sf) and bool(ktc_redraft_1qb)

    fp_ros_ok = bool(fp_ros_rows)
    fp_ros_stale = False
    fp_ros_age_days = None
    if fp_ros_scraped_at:
        try:
            scraped_dt = datetime.fromisoformat(fp_ros_scraped_at)
            fp_ros_age_days = (datetime.now(timezone.utc) - scraped_dt).total_seconds() / 86400.0
            fp_ros_stale = fp_ros_age_days > FP_ROS_STALE_THRESHOLD_DAYS
        except (ValueError, TypeError):
            pass

    if not fp_ros_ok:
        fp_ros_status = "Unavailable (fetch failed)"
    elif fp_ros_stale:
        fp_ros_status = f"Stale (last scraped {fp_ros_age_days:.1f} days ago)"
    elif fp_ros_scraped_at:
        fp_ros_status = f"Updated ({fp_ros_scraped_at[:10]})"
    else:
        fp_ros_status = "Live Current"

    return {
        "fantasycalc": {
            "source": "FantasyCalc API",
            "type": "Live real-time trade data",
            "date": now_str,
            "status": "Live Current" if fc_ok else "Unavailable (fetch failed)",
            "ok": fc_ok,
        },
        "ktc": {
            "source": "KeepTradeCut",
            "type": "Live crowdsourced rankings",
            "date": now_str,
            "status": "Live Current" if ktc_ok else "Unavailable (fetch failed)",
            "ok": ktc_ok,
        },
        "dynastyprocess": {
            "source": "DynastyProcess ECR Model",
            "type": "Curated expert rankings & values",
            "date": dp_date or "2026-09-04",
            "status": f"Updated ({dp_date or '2026-09-04'})" if dp_ok else "Unavailable (fetch failed)",
            "ok": dp_ok,
        },
        "fantasypros": {
            "source": "FantasyPros ECR",
            "type": "Consensus redraft & dynasty ECR",
            "date": fp_date or "2026-09-04",
            "status": f"Updated ({fp_date or '2026-09-04'})" if fp_ok else "Unavailable (fetch failed)",
            "ok": fp_ok,
        },
        "ktc_redraft": {
            "source": "KeepTradeCut Fantasy Rankings",
            "type": "Live crowdsourced redraft/seasonal rankings",
            "date": now_str,
            "status": "Live Current" if ktc_redraft_ok else "Unavailable (fetch failed)",
            "ok": ktc_redraft_ok,
        },
        "fp_ros": {
            "source": "FantasyPros ROS PPR",
            "type": "Rest-of-season redraft rankings (scraped 3x/week)",
            "date": fp_ros_scraped_at[:10] if fp_ros_scraped_at else now_str,
            "status": fp_ros_status,
            "ok": fp_ros_ok,
            "stale": fp_ros_stale,
        },
    }


def enrich_lookup_with_consensus_values(
    lookup,
    values_players_raw,
    player_ids_raw,
    ktc_raw=None,
    fc_raw=None,
    is_superflex=True,
    mode="equal",
    values_picks_raw=None,
    *args,
    **kwargs,
):
    """
    Enriches player lookup with market consensus:
    Attaches individual values (fc_val, ktc_val, dp_val) and composite market_value.
    Defaults to Equal Share (33.3% FC / 33.3% KTC / 33.3% DP).
    Accurately preserves draft pick names and resolves pick values from KTC and DP.
    """
    fc_values = _extract_fc_player_values(fc_raw) if fc_raw else {}
    fc_meta = _extract_fc_player_metadata(fc_raw) if fc_raw else {}
    ktc_values = _extract_ktc_player_values(ktc_raw, player_ids_raw, is_superflex) if ktc_raw else {}
    dp_values = _extract_dp_player_values(values_players_raw, player_ids_raw, is_superflex) if values_players_raw else {}

    try:
        ktc_picks_map = _parse_ktc_picks(ktc_raw, is_superflex) if ktc_raw else {}
    except Exception as e:
        print(f"Warning parsing KTC picks: {e}")
        ktc_picks_map = {}

    try:
        dp_picks_map = _parse_dp_picks(values_picks_raw, values_players_raw, is_superflex) if (values_picks_raw and values_players_raw) else {}
    except Exception as e:
        print(f"Warning parsing DP picks: {e}")
        dp_picks_map = {}

    # Extract DynastyProcess ECR overall and positional ranks as secondary fallback
    fp_id_to_sleeper = {
        str(r["fantasypros_id"]): str(r["sleeper_id"])
        for r in (player_ids_raw or [])
        if r.get("fantasypros_id") and r.get("sleeper_id")
    }
    val_ecr_col = "ecr_2qb" if is_superflex else "ecr_1qb"
    dp_ecr_overall = {}
    dp_ecr_pos = {}
    dp_player_names = {}
    dp_positions = {}
    if values_players_raw:
        for row in values_players_raw:
            fp_id = str(row.get("fp_id") or "")
            s_id = fp_id_to_sleeper.get(fp_id)
            if not s_id:
                continue
            try:
                dp_ecr_overall[s_id] = float(row.get(val_ecr_col, 999.0))
            except (ValueError, TypeError):
                pass
            try:
                dp_ecr_pos[s_id] = float(row.get("ecr_pos", 999.0))
            except (ValueError, TypeError):
                pass
            if row.get("player"):
                dp_player_names[s_id] = row.get("player")
            if row.get("pos"):
                dp_positions[s_id] = row.get("pos")

    all_player_ids = set(lookup.keys()) | set(fc_values.keys()) | set(ktc_values.keys()) | set(dp_values.keys())

    for pid in all_player_ids:
        fc_val = fc_values.get(pid)
        ktc_val = ktc_values.get(pid)
        dp_val = dp_values.get(pid)
        p_data = lookup.get(pid, {})

        is_fc_pick = str(pid).startswith("FP_")
        if is_fc_pick:
            pick_k = parse_fp_pick_id(pid)
            if pick_k:
                if ktc_val is None:
                    ktc_val = ktc_picks_map.get(pick_k)
                if dp_val is None:
                    dp_val = dp_picks_map.get(pick_k)
            fc_m = fc_meta.get(pid, {})
            p_name = fc_m.get("name") or str(pid)
            pos = "PICK"
            rank_ecr = p_data.get("rank_ecr", 999.0)
        else:
            fc_m = fc_meta.get(pid, {})
            p_name = dp_player_names.get(pid) or fc_m.get("name") or ""
            pos = p_data.get("position", "") or dp_positions.get(pid, "") or fc_m.get("position", "")
            rank_ecr = p_data.get("rank_ecr", dp_ecr_pos.get(pid, 999.0))

        composite = compute_composite_value(fc_val, ktc_val, dp_val, mode=mode, rank_ecr=rank_ecr, position=pos)

        if pid in lookup:
            lookup[pid]["market_value"] = composite
            lookup[pid]["fc_val"] = fc_val
            lookup[pid]["ktc_val"] = ktc_val
            lookup[pid]["dp_val"] = dp_val
            if lookup[pid].get("rank_ecr_overall", 999.0) >= 999.0 and pid in dp_ecr_overall:
                lookup[pid]["rank_ecr_overall"] = dp_ecr_overall[pid]
            if lookup[pid].get("rank_ecr_pos", 999.0) >= 999.0 and pid in dp_ecr_pos:
                lookup[pid]["rank_ecr_pos"] = dp_ecr_pos[pid]
            if not lookup[pid].get("player_name"):
                lookup[pid]["player_name"] = p_name
            if not lookup[pid].get("position"):
                lookup[pid]["position"] = pos
        else:
            lookup[pid] = {
                "rank_ecr": dp_ecr_pos.get(pid, 999.0) if not is_fc_pick else 999.0,
                "rank_ecr_pos": dp_ecr_pos.get(pid, 999.0) if not is_fc_pick else 999.0,
                "rank_ecr_overall": dp_ecr_overall.get(pid, 999.0) if not is_fc_pick else 999.0,
                "player_name": p_name,
                "position": pos,
                "market_value": composite,
                "fc_val": fc_val,
                "ktc_val": ktc_val,
                "dp_val": dp_val,
            }

    for p in lookup.values():
        if "market_value" not in p:
            p["market_value"] = 0.0
        if "rank_ecr_overall" not in p:
            p["rank_ecr_overall"] = 999.0
        if "rank_ecr_pos" not in p:
            p["rank_ecr_pos"] = p.get("rank_ecr", 999.0)

    recompute_consensus_ranks(lookup)
    return lookup


def recompute_consensus_ranks(lookup):
    """
    Assigns mathematically consistent consensus overall and positional ranks
    strictly based on each player's active 'market_value' (descending).
    Preserves original raw FantasyPros expert ranks as 'fp_ecr_overall' and 'fp_ecr_pos'.
    """
    for p in lookup.values():
        if "fp_ecr_overall" not in p:
            p["fp_ecr_overall"] = p.get("rank_ecr_overall", 999.0)
        if "fp_ecr_pos" not in p:
            p["fp_ecr_pos"] = p.get("rank_ecr_pos", p.get("rank_ecr", 999.0))

    def sort_key(item):
        val = float(item[1].get("market_value") or 0.0)
        fp_o = float(item[1].get("fp_ecr_overall") or 9999.0)
        return (-val, fp_o)

    sorted_players = sorted(lookup.items(), key=sort_key)

    by_pos = {}
    for overall_idx, (pid, p_data) in enumerate(sorted_players, start=1):
        p_data["rank_ecr_overall"] = float(overall_idx)
        pos = p_data.get("position") or "UTIL"
        by_pos.setdefault(pos, []).append((pid, p_data))

    for pos, p_list in by_pos.items():
        for pos_idx, (pid, p_data) in enumerate(p_list, start=1):
            p_data["rank_ecr_pos"] = float(pos_idx)
            p_data["rank_ecr"] = float(pos_idx)

    return lookup


def apply_valuation_mode(lookup, mode="equal"):
    """
    Returns a new lookup with 'market_value' recalculated for all players from
    their stored fc_val, ktc_val, and dp_val, without re-fetching from APIs.
    Recomputes consensus ranks.

    Does not mutate the input lookup - it builds and returns an independent
    copy. This matters because callers repeatedly pass the same shared base
    lookup (e.g. market_db["dynasty_sf_lookup"]) for many leagues in a row;
    mutating it in place would let one league's mode leak into every
    other league sharing that same object.
    """
    new_lookup = {pid: dict(p) for pid, p in lookup.items()}
    for pid, p in new_lookup.items():
        fc_val = p.get("fc_val")
        ktc_val = p.get("ktc_val")
        dp_val = p.get("dp_val")
        rank_ecr = p.get("fp_ecr_pos", p.get("rank_ecr", 999.0))
        pos = p.get("position", "")
        p["market_value"] = compute_composite_value(fc_val, ktc_val, dp_val, mode=mode, rank_ecr=rank_ecr, position=pos)

    recompute_consensus_ranks(new_lookup)
    return new_lookup


def _calculate_redraft_depth_value(blended_rank: float) -> float:
    """
    Computes smooth, continuous single-season (redraft/ROS) valuation for bench and depth players
    beyond rank 160. Uses a smooth exponential decay curve anchored at rank 160 = 160.0 pts that halves
    approximately every 40 ranks (k = ln(2)/40).
    Ensures viable NFL contributors (e.g. Troy Franklin, Keon Coleman, Samaje Perine, Deshaun Watson)
    maintain meaningful, proportional fantasy values rather than collapsing to near 0.
    """
    if blended_rank <= 160.0:
        return 160.0
    k = math.log(2) / 40.0
    val = 160.0 * math.exp(-k * (blended_rank - 160.0))
    if blended_rank > 450.0:
        val = max(0.0, val * max(0.0, (550.0 - blended_rank) / 100.0))
    return round(val, 1)


def _calculate_redraft_market_value(blended_rank: float) -> float:
    """
    Computes smooth, continuous single-season (redraft/ROS) valuation for all players
    based on the 3-Pillar Consensus Overall Rank (Sleeper + FantasyPros + KTC Redraft).
    - Top tier (ranks 1 to 160): smooth exponential decay from 10,500 down to 160 pts.
    - Depth tier (ranks > 160): continuous exponential decay ensuring deep bench/waiver targets
      maintain proportional capital (80 pts at rank 200, 40 pts at rank 240, 20 pts at rank 280).
    """
    if blended_rank <= 1.0:
        return 10500.0
    if blended_rank <= 160.0:
        k = math.log(10500.0 / 160.0) / 159.0
        return round(10500.0 * math.exp(-k * (blended_rank - 1.0)), 1)
    return _calculate_redraft_depth_value(blended_rank)


DEFAULT_REDRAFT_SCORING = {
    "rec": 0.5,
    "bonus_rec_te": 0.0,
    "pass_td": 4.0,
    "pass_yd": 0.04,
    "rush_yd": 0.1,
    "rec_yd": 0.1,
    "rush_td": 6.0,
    "rec_td": 6.0,
    "pass_int": -2.0,
    "fum_lost": -2.0,
}


def _extract_ktc_redraft_pillar(ktc_fantasy_raw, player_ids_raw=None, is_superflex=False, bonus_rec_te=0.0):
    """
    Ranks KeepTradeCut's Fantasy Rankings pool (QB/RB/WR/TE) by KTC's redraft
    value, both overall and within each position - the same "sort by value,
    position in the sort is the rank" ordinal-rank shape the other pillars
    produce via VORP, just without the VORP step, since KTC's value is
    already a single cross-positional consensus number.
    Acts as Pillar 3 in the Tri-Factor Redraft / ROS Consensus Engine.

    For TEs, selects the same KTC native TE Premium tier as
    apply_ktc_te_premium (bonus_rec_te == 0.5 -> "tep", == 1.0 -> "tepp",
    anything else -> base value, with a fallback to base value if the tier
    is missing for that player), so this pillar also reflects the league's
    real TE Premium instead of being blind to it like FantasyPros ECR is.
    """
    if not ktc_fantasy_raw:
        return {}

    ktc_id_to_sleeper = {
        str(r["ktc_id"]): str(r["sleeper_id"])
        for r in (player_ids_raw or [])
        if r.get("ktc_id") and r.get("sleeper_id")
    }
    mfl_id_to_sleeper = {
        str(r["mfl_id"]): str(r["sleeper_id"])
        for r in (player_ids_raw or [])
        if r.get("mfl_id") and r.get("sleeper_id")
    }

    val_key = "superflexValues" if is_superflex else "oneQBValues"
    tier = _ktc_tep_tier_key(bonus_rec_te)

    scored_players = []
    for p in ktc_fantasy_raw:
        pos = p.get("position")
        if pos not in ("QB", "RB", "WR", "TE"):
            continue

        p_id = str(p.get("playerID", ""))
        mfl_id = str(p.get("mflid", ""))
        s_id = ktc_id_to_sleeper.get(p_id) or mfl_id_to_sleeper.get(mfl_id)
        if not s_id:
            continue

        vals = p.get(val_key, {}) or {}
        try:
            base_val = float(vals.get("value", 0.0))
        except (ValueError, TypeError):
            continue

        val = base_val
        if pos == "TE" and tier:
            try:
                tier_val = float((vals.get(tier) or {}).get("value", 0.0))
            except (ValueError, TypeError):
                tier_val = 0.0
            if tier_val > 0:
                val = tier_val

        if val <= 0:
            continue

        scored_players.append({"pid": s_id, "pos": pos, "val": val})

    # Positional Ranks
    by_pos = {}
    for p in scored_players:
        by_pos.setdefault(p["pos"], []).append(p)

    for pos, p_list in by_pos.items():
        p_list.sort(key=lambda x: x["val"], reverse=True)
        for rank_idx, p in enumerate(p_list, start=1):
            p["pos_rank"] = rank_idx

    # Overall Rank (direct KTC value sort - no VORP step needed, unlike
    # the points-based pillars, since KTC's value is already cross-positional)
    scored_players.sort(key=lambda x: x["val"], reverse=True)
    for overall_idx, p in enumerate(scored_players, start=1):
        p["overall_rank"] = overall_idx

    return {
        p["pid"]: {
            "val": p["val"],
            "pos_rank": p["pos_rank"],
            "overall_rank": p["overall_rank"],
        }
        for p in scored_players
    }


def _extract_projections_pillar(projections_raw, lookup, scoring_settings=None, is_superflex=False):
    """
    Computes statistical projected weekly points (PPG), positional ranks,
    and VORP-based overall ranks for all players in projections_raw.
    Acts as Pillar 1 in the Tri-Factor Redraft / ROS Consensus Engine.
    """
    if not projections_raw:
        return {}

    active_scoring = dict(DEFAULT_REDRAFT_SCORING)
    if scoring_settings:
        active_scoring.update(scoring_settings)

    scored_players = []
    for pid, raw_proj in projections_raw.items():
        if not raw_proj:
            continue
        p_data = lookup.get(str(pid)) or {}
        pos = str(p_data.get("position") or raw_proj.get("pos") or "").upper()
        name = p_data.get("player_name") or raw_proj.get("player_name") or str(pid)

        if pos not in ("QB", "RB", "WR", "TE", "K", "DEF", "DST"):
            continue

        player_obj = {"position": pos, "full_name": name, "player_id": str(pid)}
        pts = calculate_weekly_projected_points(str(pid), raw_proj, active_scoring, player_obj)
        if pts > 0.0:
            scored_players.append({
                "pid": str(pid),
                "name": name,
                "pos": pos,
                "pts": pts,
            })

    # 1. Compute Positional Ranks (1 to N within each position)
    by_pos = {}
    for p in scored_players:
        by_pos.setdefault(p["pos"], []).append(p)

    for pos, p_list in by_pos.items():
        p_list.sort(key=lambda x: x["pts"], reverse=True)
        for rank_idx, p in enumerate(p_list, start=1):
            p["pos_rank"] = rank_idx

    # 2. Compute Overall Ranks via Value Over Replacement Player (VORP)
    qb_baseline_idx = 23 if is_superflex else 11

    def _get_baseline_pts(pos_key, idx, default_pts):
        p_list = by_pos.get(pos_key, [])
        if len(p_list) > idx:
            return p_list[idx]["pts"]
        return default_pts

    baselines = {
        "QB": _get_baseline_pts("QB", qb_baseline_idx, 14.0),
        "RB": _get_baseline_pts("RB", 23, 8.0),
        "WR": _get_baseline_pts("WR", 35, 8.0),
        "TE": _get_baseline_pts("TE", 11, 6.0),
        "K": _get_baseline_pts("K", 11, 6.0),
        "DEF": _get_baseline_pts("DEF", 11, _get_baseline_pts("DST", 11, 6.0)),
        "DST": _get_baseline_pts("DST", 11, 6.0),
    }

    for p in scored_players:
        b_pts = baselines.get(p["pos"], 6.0)
        if p["pos"] in ("K", "DEF", "DST"):
            p["vorp"] = (p["pts"] - b_pts) - 4.0
        else:
            p["vorp"] = p["pts"] - b_pts

    scored_players.sort(key=lambda x: x["vorp"], reverse=True)
    for overall_idx, p in enumerate(scored_players, start=1):
        p["overall_rank"] = overall_idx

    return {
        p["pid"]: {
            "ppg": round(p["pts"], 1),
            "pos_rank": p["pos_rank"],
            "overall_rank": p["overall_rank"],
        }
        for p in scored_players
    }


def enrich_lookup_with_redraft_values(
    lookup,
    ktc_fantasy_raw=None,
    projections_raw=None,
    player_ids_raw=None,
    scoring_settings=None,
    is_superflex=False,
    start_week=1,
    end_week=17,
    fc_redraft_raw=None,
):
    """
    Enriches redraft lookup with authentic 3-Pillar Consensus single-season market values:
    - Pillar 1 (Machine Projections): Sleeper Multi-Week Projections (Weekly PPG & VORP Ranks)
    - Pillar 2 (Expert Consensus): FantasyPros Redraft ECR & Positional Rankings
    - Pillar 3 (Market Consensus): KeepTradeCut Fantasy Rankings (Overall & Positional Rank)
    Assigns continuous, standardized market values (0-10,500 pts) based on the consensus curve.
    """
    # Extract Pillar 1: Sleeper Quant Projections Model
    proj_map = _extract_projections_pillar(
        projections_raw=projections_raw,
        lookup=lookup,
        scoring_settings=scoring_settings,
        is_superflex=is_superflex,
    )

    # Extract Pillar 3: KeepTradeCut Fantasy Rankings
    bonus_rec_te = float((scoring_settings or {}).get("bonus_rec_te", 0.0) or (scoring_settings or {}).get("te_bonus", 0.0))
    ktc_redraft_map = _extract_ktc_redraft_pillar(
        ktc_fantasy_raw=ktc_fantasy_raw,
        player_ids_raw=player_ids_raw,
        is_superflex=is_superflex,
        bonus_rec_te=bonus_rec_te,
    )

    for sleeper_id, p_data in lookup.items():
        pos = str(p_data.get("position", "")).upper()
        sid_str = str(sleeper_id)

        # Pillar 1: Sleeper Projections data for this player
        p_proj = proj_map.get(sid_str)
        proj_ppg = p_proj["ppg"] if p_proj else None
        proj_o = float(p_proj["overall_rank"]) if p_proj else None
        proj_p = float(p_proj["pos_rank"]) if p_proj else None

        p_data["proj_ppg"] = proj_ppg
        p_data["proj_overall_rank"] = proj_o
        p_data["proj_pos_rank"] = proj_p

        # Pillar 2: FantasyPros ECR
        fp_o = float(p_data.get("rank_ecr_overall") or 999.0)
        fp_p = float(p_data.get("rank_ecr_pos") or p_data.get("rank_ecr") or 999.0)
        p_data["fp_ecr_overall"] = fp_o
        p_data["fp_ecr_pos"] = fp_p

        # Pillar 3: KeepTradeCut Fantasy Rankings
        ktc_redraft_info = ktc_redraft_map.get(sid_str)
        ktc_redraft_val = ktc_redraft_info["val"] if ktc_redraft_info else None
        ktc_redraft_o = float(ktc_redraft_info["overall_rank"]) if ktc_redraft_info else None
        ktc_redraft_p = float(ktc_redraft_info["pos_rank"]) if ktc_redraft_info else None

        p_data["ktc_redraft_val"] = ktc_redraft_val
        p_data["ktc_redraft_overall_rank"] = ktc_redraft_o
        p_data["ktc_redraft_pos_rank"] = ktc_redraft_p

        # Kickers and DSTs
        if pos in ("K", "DST", "DEF"):
            valid_k_p = [p for p in (proj_p, fp_p, ktc_redraft_p) if p is not None and p < 200]
            r_ecr = (sum(valid_k_p) / len(valid_k_p)) if valid_k_p else (p_data.get("rank_ecr") or 1.0)
            if r_ecr < 900:
                kv = max(25.0, min(140.0, round(140.0 - (float(r_ecr) - 1.0) * 5.0, 1)))
            else:
                kv = 25.0
            p_data["market_value"] = kv
            p_data["rank_ecr_overall"] = 999.0
            p_data["rank_ecr_pos"] = round(r_ecr, 1)
            p_data["rank_ecr"] = round(r_ecr, 1)
            continue

        # Tri-Pillar Overall Consensus Rank (Sleeper + FP + KTC Redraft)
        valid_overall = []
        if proj_o is not None and proj_o < 500:
            valid_overall.append(proj_o)
        if fp_o < 500:
            valid_overall.append(fp_o)
        if ktc_redraft_o is not None and ktc_redraft_o < 500:
            valid_overall.append(ktc_redraft_o)

        if valid_overall:
            blended_o = round(sum(valid_overall) / len(valid_overall), 1)
        else:
            blended_o = 999.0

        # Tri-Pillar Positional Consensus Rank (Sleeper + FP + KTC Redraft)
        valid_pos = []
        if proj_p is not None and proj_p < 200:
            valid_pos.append(proj_p)
        if fp_p < 200:
            valid_pos.append(fp_p)
        if ktc_redraft_p is not None and ktc_redraft_p < 200:
            valid_pos.append(ktc_redraft_p)

        if valid_pos:
            blended_p = round(sum(valid_pos) / len(valid_pos), 1)
        else:
            blended_p = 999.0

        # Calculate Consensus Market Value via continuous curve
        p_data["market_value"] = _calculate_redraft_market_value(blended_o)

        p_data["rank_ecr_overall"] = blended_o
        p_data["rank_ecr_pos"] = blended_p
        p_data["rank_ecr"] = blended_p

    recompute_consensus_ranks(lookup)
    return lookup


# Backwards compatibility alias
enrich_lookup_with_market_values = enrich_lookup_with_consensus_values


def apply_ktc_te_premium(lookup, bonus_rec_te, ktc_raw, player_ids_raw, is_superflex=True, mode="equal"):
    """
    Returns a new lookup with Tight End market values rebuilt for the
    league's real TE Premium bonus, using KeepTradeCut's own native TE+
    ("tep") / TE++ ("tepp") value tiers instead of a synthetic multiplier.

    Only bonus_rec_te == 0.5 (KTC's "tep" tier) or == 1.0 ("tepp") are
    recognized - any other bonus (including 0) leaves TE values unadjusted,
    since KTC has no tier for it.

    The percentage lift of that tier over KTC's own base value for the same
    player (capped at KTC_TEP_MAX_PCT, and only derived when the base KTC
    value is at least KTC_TEP_MIN_BASE_VALUE, to avoid amplifying noise on
    low-value quotes) is then applied to fc_val and dp_val too, and the
    composite market_value is fully recomputed via compute_composite_value -
    not just scaled after the fact on top of an already-blended value.

    Does not mutate the input lookup - it builds and returns an independent
    copy, for the same reason apply_valuation_mode does (see its docstring).
    """
    new_lookup = {player_id: dict(data) for player_id, data in lookup.items()}

    tier = _ktc_tep_tier_key(bonus_rec_te)
    if not tier:
        return new_lookup

    te_tiers = _extract_ktc_te_tiers(ktc_raw, player_ids_raw, is_superflex) if ktc_raw else {}

    for player_id, data in new_lookup.items():
        if data.get("position") != "TE":
            continue

        tiers = te_tiers.get(str(player_id))
        if not tiers:
            continue

        base_val = tiers["base"]
        tier_val = tiers[tier]
        if base_val < KTC_TEP_MIN_BASE_VALUE or tier_val <= 0:
            continue

        pct = min(KTC_TEP_MAX_PCT, (tier_val / base_val) - 1.0)

        fc_val = data.get("fc_val")
        dp_val = data.get("dp_val")
        fc_val_adj = fc_val * (1.0 + pct) if fc_val is not None and fc_val > 0 else fc_val
        dp_val_adj = dp_val * (1.0 + pct) if dp_val is not None and dp_val > 0 else dp_val

        rank_ecr = data.get("fp_ecr_pos", data.get("rank_ecr", 999.0))
        data["fc_val"] = fc_val_adj
        data["ktc_val"] = tier_val
        data["dp_val"] = dp_val_adj
        data["market_value"] = compute_composite_value(
            fc_val_adj, tier_val, dp_val_adj, mode=mode, rank_ecr=rank_ecr, position="TE"
        )
        data["ktc_tep_pct_applied"] = round(pct, 4)

    return new_lookup


def _build_ecr_to_value_curve(values_players_raw, is_superflex=True):
    val_col = "value_2qb" if is_superflex else "value_1qb"
    ecr_col = "ecr_2qb" if is_superflex else "ecr_1qb"

    curve = []
    for row in values_players_raw:
        try:
            e = float(row.get(ecr_col, 0))
            v = float(row.get(val_col, 0))
            curve.append((e, v))
        except (ValueError, TypeError):
            continue

    curve.sort(key=lambda x: x[0])
    return curve


def _interpolate_value_from_ecr(curve, target_ecr):
    if not curve:
        return 0.0
    if target_ecr <= curve[0][0]:
        return curve[0][1]
    if target_ecr >= curve[-1][0]:
        return curve[-1][1]

    for i in range(len(curve) - 1):
        e1, v1 = curve[i]
        e2, v2 = curve[i + 1]
        if e1 <= target_ecr <= e2:
            if e2 == e1:
                return v1
            ratio = (target_ecr - e1) / (e2 - e1)
            return round(v1 + ratio * (v2 - v1), 1)

    return 0.0


def _parse_dp_picks(values_picks_raw, values_players_raw=None, is_superflex=True):
    try:
        ecr_col = "ecr_2qb" if is_superflex else "ecr_1qb"
        val_col = "value_2qb" if is_superflex else "value_1qb"

        curve = _build_ecr_to_value_curve(values_players_raw, is_superflex) if values_players_raw else []
        dp_picks = {}
        pattern = re.compile(r"^(\d{4})\s+(?:(Early|Mid|Late)\s+)?(\d+)(?:st|nd|rd|th)$", re.IGNORECASE)

        for row in (values_picks_raw or []):
            if not isinstance(row, dict):
                continue
            player_name = row.get("player", "").strip()
            match = pattern.match(player_name)
            if not match:
                continue

            season = match.group(1)
            tier = (match.group(2) or "mid").lower()
            round_num = int(match.group(3))

            raw_val = row.get(val_col)
            if raw_val and raw_val != "NA":
                try:
                    val = float(raw_val)
                except (ValueError, TypeError):
                    val = 0.0
            elif curve and row.get(ecr_col):
                try:
                    pick_ecr = float(row[ecr_col])
                    val = _interpolate_value_from_ecr(curve, pick_ecr)
                except (ValueError, TypeError):
                    val = 0.0
            else:
                val = 0.0

            dp_picks[(season, round_num, tier)] = val
            if tier == "mid":
                dp_picks[(season, round_num)] = val

        return dp_picks
    except Exception as e:
        print(f"Warning parsing DP picks: {e}")
        return {}


def _parse_ktc_picks(ktc_raw, is_superflex=True):
    try:
        ktc_picks = {}
        if not ktc_raw:
            return ktc_picks

        val_key = "superflexValues" if is_superflex else "oneQBValues"
        pattern = re.compile(r"^(\d{4})\s+(?:(Early|Mid|Late)\s+)?(\d+)(?:st|nd|rd|th)$", re.IGNORECASE)

        for p in (ktc_raw or []):
            if not isinstance(p, dict) or p.get("position") != "RDP":
                continue
            name = p.get("playerName", "").strip()
            match = pattern.match(name)
            if match:
                season = match.group(1)
                tier = (match.group(2) or "mid").lower()
                round_num = int(match.group(3))
                try:
                    val = float(p.get(val_key, {}).get("value", 0.0))
                    ktc_picks[(season, round_num, tier)] = val
                    if tier == "mid":
                        ktc_picks[(season, round_num)] = val
                except (ValueError, TypeError):
                    continue

        return ktc_picks
    except Exception as e:
        print(f"Warning parsing KTC picks: {e}")
        return {}


def _parse_fc_picks(fc_raw):
    fc_picks = {}
    if not fc_raw:
        return fc_picks

    pattern = re.compile(r"^(\d{4})\s+(\d+)(?:st|nd|rd|th)(?:\s+\((Early|Mid|Late)\))?", re.IGNORECASE)

    for item in fc_raw:
        name = item.get("player", {}).get("name", "").strip()
        match = pattern.match(name)
        if match:
            season = match.group(1)
            round_num = int(match.group(2))
            tier = (match.group(3) or "mid").lower()
            try:
                val = float(item.get("value", 0.0))
                fc_picks[(season, round_num, tier)] = val
                if tier == "mid":
                    fc_picks[(season, round_num)] = val
            except (ValueError, TypeError):
                continue

    return fc_picks


def _populate_missing_tiers(picks_dict):
    """
    Ensures that for any (season, round_num) with a mid/generic entry,
    'early' and 'late' are also populated within that source before combining.
    """
    two_tuple_items = [(k, v) for k, v in list(picks_dict.items()) if len(k) == 2]
    for (season, round_num), val in two_tuple_items:
        if isinstance(season, str) and isinstance(round_num, int):
            if (season, round_num, "early") not in picks_dict:
                picks_dict[(season, round_num, "early")] = round(val * 1.30, 1)
            if (season, round_num, "mid") not in picks_dict:
                picks_dict[(season, round_num, "mid")] = val
            if (season, round_num, "late") not in picks_dict:
                picks_dict[(season, round_num, "late")] = round(val * 0.75, 1)


def build_picks_sources_bundle(
    values_picks_raw,
    values_players_raw=None,
    ktc_raw=None,
    fc_raw=None,
    is_superflex=True,
):
    """
    Parses and returns raw individual pick valuation dictionaries:
    {'dp': dp_picks, 'ktc': ktc_picks, 'fc': fc_picks, 'all_keys': all_keys}
    """
    dp_picks = _parse_dp_picks(values_picks_raw, values_players_raw, is_superflex) if values_picks_raw else {}
    ktc_picks = _parse_ktc_picks(ktc_raw, is_superflex) if ktc_raw else {}
    fc_picks = _parse_fc_picks(fc_raw) if fc_raw else {}

    _populate_missing_tiers(dp_picks)
    _populate_missing_tiers(ktc_picks)
    _populate_missing_tiers(fc_picks)

    all_keys = set(dp_picks.keys()) | set(ktc_picks.keys()) | set(fc_picks.keys())
    return {
        "dp": dp_picks,
        "ktc": ktc_picks,
        "fc": fc_picks,
        "all_keys": all_keys,
    }


def compute_picks_lookup_from_bundle(bundle, mode="equal"):
    """
    Computes a picks lookup mapping (season, round_num, tier) -> float for any valuation mode.
    """
    dp_picks = bundle["dp"]
    ktc_picks = bundle["ktc"]
    fc_picks = bundle["fc"]
    all_keys = bundle["all_keys"]

    consensus_picks = {}
    for k in all_keys:
        fc_v = fc_picks.get(k)
        ktc_v = ktc_picks.get(k)
        dp_v = dp_picks.get(k)

        val = compute_composite_value(fc_v, ktc_v, dp_v, mode=mode, is_pick=True)
        if val > 0:
            consensus_picks[k] = val

    # Ensure all rounds have 'early', 'mid', 'late' populated
    two_tuple_items = [(k, v) for k, v in list(consensus_picks.items()) if len(k) == 2]
    for (season, round_num), val in two_tuple_items:
        if isinstance(season, str) and isinstance(round_num, int):
            if (season, round_num, "early") not in consensus_picks:
                consensus_picks[(season, round_num, "early")] = round(val * 1.35, 1)
            if (season, round_num, "mid") not in consensus_picks:
                consensus_picks[(season, round_num, "mid")] = val
            if (season, round_num, "late") not in consensus_picks:
                consensus_picks[(season, round_num, "late")] = round(val * 0.70, 1)

    # Automatically extend to future seasons (e.g., 2029) based on max known season
    known_seasons = [int(k[0]) for k in consensus_picks.keys() if len(k) == 2 and str(k[0]).isdigit()]
    if known_seasons:
        max_season = max(known_seasons)
        for future_year in range(max_season + 1, max_season + 4):
            for r in range(1, 6):
                for tier in ["early", "mid", "late"]:
                    key = (str(future_year), r, tier)
                    if key not in consensus_picks:
                        consensus_picks[key] = consensus_picks.get((str(max_season), r, tier), 0.0)
                default_key = (str(future_year), r)
                if default_key not in consensus_picks:
                    consensus_picks[default_key] = consensus_picks.get((str(max_season), r), 0.0)

    return consensus_picks


def build_consensus_picks_lookup(
    values_picks_raw,
    values_players_raw=None,
    ktc_raw=None,
    fc_raw=None,
    is_superflex=True,
    mode="equal",
):
    """
    Builds draft picks dictionary mapping (season, round_num, tier) -> market_value_points.
    Defaults to Equal Share (33.3% FC / 33.3% KTC / 33.3% DP).
    """
    bundle = build_picks_sources_bundle(
        values_picks_raw,
        values_players_raw=values_players_raw,
        ktc_raw=ktc_raw,
        fc_raw=fc_raw,
        is_superflex=is_superflex,
    )
    return compute_picks_lookup_from_bundle(bundle, mode=mode)


# Backwards compatibility alias
build_picks_value_lookup = build_consensus_picks_lookup
