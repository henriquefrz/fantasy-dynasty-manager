import csv
import io
import json
import re
import requests


FPECR_URL = "https://raw.githubusercontent.com/dynastyprocess/data/master/files/db_fpecr_latest.csv"
PLAYERIDS_URL = "https://raw.githubusercontent.com/dynastyprocess/data/master/files/db_playerids.csv"
VALUES_PLAYERS_URL = "https://raw.githubusercontent.com/dynastyprocess/data/master/files/values-players.csv"
VALUES_PICKS_URL = "https://raw.githubusercontent.com/dynastyprocess/data/master/files/values-picks.csv"

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


def _download_csv(url):
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    csv_text = response.text
    reader = csv.DictReader(io.StringIO(csv_text))
    return list(reader)


def get_fp_rankings_raw():
    return _download_csv(FPECR_URL)


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
        print(f"Warning: Failed to fetch FantasyCalc data: {e}")
        return []


def get_ktc_data_raw(is_superflex=True):
    """
    Fetches live market values from KeepTradeCut (KTC) crowdsourced rankings.
    """
    fmt = 2 if is_superflex else 1
    url = f"https://keeptradecut.com/dynasty-rankings?filters=QB|WR|RB|TE|RDP&format={fmt}"
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        matches = re.findall(r"var playersArray\s*=\s*(\[.*?\]);", response.text, re.DOTALL)
        if matches:
            return json.loads(matches[0])
        return []
    except Exception as e:
        print(f"Warning: Failed to fetch KeepTradeCut data: {e}")
        return []


def _build_player_lookup(fp_rankings_raw, player_ids_raw, ranking_prefix, is_superflex=False):
    fp_id_to_sleeper_id = {}

    for row in player_ids_raw:
        sleeper_id = row.get("sleeper_id")
        fp_id = row.get("fantasypros_id")

        if sleeper_id and sleeper_id != "NA" and fp_id and fp_id != "NA":
            fp_id_to_sleeper_id[fp_id] = sleeper_id

    pos_page_types = {f"{ranking_prefix}-{pos.lower()}" for pos in POSITIONS}
    overall_page_type = f"{ranking_prefix}-op" if is_superflex else f"{ranking_prefix}-overall"

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


def get_market_data_freshness(fp_raw=None, dp_raw=None):
    """
    Returns timestamp / scrape date status for each connected database.
    """
    from datetime import datetime
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    fp_date = None
    if fp_raw and len(fp_raw) > 0:
        fp_date = fp_raw[0].get("scrape_date")

    dp_date = None
    if dp_raw and len(dp_raw) > 0:
        dp_date = dp_raw[0].get("scrape_date")

    return {
        "fantasycalc": {
            "source": "FantasyCalc API",
            "type": "Live real-time trade data",
            "date": now_str,
            "status": "Live Current",
        },
        "ktc": {
            "source": "KeepTradeCut",
            "type": "Live crowdsourced rankings",
            "date": now_str,
            "status": "Live Current",
        },
        "dynastyprocess": {
            "source": "DynastyProcess ECR Model",
            "type": "Curated expert rankings & values",
            "date": dp_date or "2026-09-04",
            "status": f"Updated ({dp_date or '2026-09-04'})",
        },
        "fantasypros": {
            "source": "FantasyPros ECR",
            "type": "Consensus redraft & dynasty ECR",
            "date": fp_date or "2026-09-04",
            "status": f"Updated ({fp_date or '2026-09-04'})",
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

    ktc_picks_map = _parse_ktc_picks(ktc_raw, is_superflex) if ktc_raw else {}
    dp_picks_map = _parse_dp_picks(values_picks_raw, values_players_raw, is_superflex) if (values_picks_raw and values_players_raw) else {}

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


def apply_valuation_mode(lookup, mode="equal", bonus_rec_te=0.0):
    """
    Dynamically recalculates 'market_value' for all players in an existing lookup
    using their stored fc_val, ktc_val, and dp_val without re-fetching from APIs.
    Optionally re-applies TE Premium. Recomputes consensus ranks.
    """
    for pid, p in lookup.items():
        fc_val = p.get("fc_val")
        ktc_val = p.get("ktc_val")
        dp_val = p.get("dp_val")
        rank_ecr = p.get("fp_ecr_pos", p.get("rank_ecr", 999.0))
        pos = p.get("position", "")
        p["market_value"] = compute_composite_value(fc_val, ktc_val, dp_val, mode=mode, rank_ecr=rank_ecr, position=pos)

    if bonus_rec_te and bonus_rec_te > 0:
        apply_te_premium(lookup, bonus_rec_te)

    recompute_consensus_ranks(lookup)
    return lookup


def enrich_lookup_with_redraft_values(lookup, fc_redraft_raw=None):
    """
    Enriches redraft lookup with authentic single-season market values
    from FantasyCalc (reflecting win-now impact without dynasty age penalties).
    Blends FantasyPros Redraft ECR and FantasyCalc rank data to assign mathematically
    consistent consensus overall and positional ranks.
    Interpolates for depth players using an overall-rank curve without inverted rank artifacts.
    """
    fc_player_map = {}
    fc_curve = []

    for item in (fc_redraft_raw or []):
        p_info = item.get("player") or {}
        sid = str(p_info.get("sleeperId") or "")
        v_raw = item.get("value")
        o_raw = item.get("overallRank")
        p_raw = item.get("positionRank")

        try:
            val = float(v_raw) if v_raw is not None else 0.0
        except (ValueError, TypeError):
            val = 0.0

        try:
            o_rank = float(o_raw) if (o_raw is not None and float(o_raw) > 0) else None
        except (ValueError, TypeError):
            o_rank = None

        try:
            p_rank = float(p_raw) if (p_raw is not None and float(p_raw) > 0) else None
        except (ValueError, TypeError):
            p_rank = None

        if o_rank is not None and val > 0:
            fc_curve.append((o_rank, val))

        if sid and sid != "None":
            fc_player_map[sid] = {
                "val": val,
                "overall_rank": o_rank,
                "pos_rank": p_rank,
            }

    fc_curve.sort(key=lambda x: x[0])

    for sleeper_id, p_data in lookup.items():
        pos = str(p_data.get("position", "")).upper()
        if pos in ("K", "DST", "DEF"):
            kv = compute_kicker_dst_value(p_data.get("rank_ecr"))
            p_data["market_value"] = kv
            p_data["fc_val"] = kv
            continue

        fp_o = float(p_data.get("rank_ecr_overall") or 999.0)
        fp_p = float(p_data.get("rank_ecr_pos") or p_data.get("rank_ecr") or 999.0)
        p_data["fp_ecr_overall"] = fp_o
        p_data["fp_ecr_pos"] = fp_p

        fc_info = fc_player_map.get(sleeper_id)
        if fc_info:
            fc_o = fc_info["overall_rank"]
            fc_p = fc_info["pos_rank"]
            raw_fc_v = fc_info["val"]
            p_data["fc_val"] = raw_fc_v

            # Consensus overall rank (50% FP ECR / 50% FC Rank when both exist)
            if fp_o < 500 and fc_o is not None and fc_o < 500:
                blended_o = round(fp_o * 0.5 + fc_o * 0.5, 1)
            elif fp_o < 500:
                blended_o = fp_o
            elif fc_o is not None:
                blended_o = fc_o
            else:
                blended_o = 999.0

            # Consensus positional rank
            if fp_p < 200 and fc_p is not None and fc_p < 200:
                blended_p = round(fp_p * 0.5 + fc_p * 0.5, 1)
            elif fp_p < 200:
                blended_p = fp_p
            elif fc_p is not None:
                blended_p = fc_p
            else:
                blended_p = 999.0

            curve_v = _interpolate_value_from_ecr(fc_curve, blended_o) if (fc_curve and blended_o <= 199) else 0.0
            # Smooth illiquid trade drop-offs so bench players are calibrated to their rank tier
            p_data["market_value"] = round(max(raw_fc_v, curve_v * 0.85 if curve_v > 40 else curve_v), 1)
        else:
            blended_o = fp_o
            blended_p = fp_p
            p_data["fc_val"] = None

            if blended_o <= 199 and fc_curve:
                p_data["market_value"] = round(_interpolate_value_from_ecr(fc_curve, blended_o), 1)
            elif blended_o < 250:
                p_data["market_value"] = max(0.0, round(2.0 - (blended_o - 199) * 0.04, 1))
            else:
                p_data["market_value"] = 0.0

        p_data["rank_ecr_overall"] = blended_o
        p_data["rank_ecr_pos"] = blended_p
        p_data["rank_ecr"] = blended_p

    return lookup


# Backwards compatibility alias
enrich_lookup_with_market_values = enrich_lookup_with_consensus_values


def apply_te_premium(lookup, bonus_rec_te):
    """
    Applies a realistic volume-tiered boost to tight ends based on TE Premium bonus.

    Tiers:
    - Elite TEs (>4,000 pts): +20% for 0.5 TEP | +35% for 1.0 TEP
    - Starting TEs (1,500-4,000 pts): +15% for 0.5 TEP | +25% for 1.0 TEP
    - Backup/Depth TEs (<1,500 pts): +8% for 0.5 TEP | +15% for 1.0 TEP
    """
    if not bonus_rec_te or bonus_rec_te <= 0:
        return lookup

    for player_id, data in lookup.items():
        if data.get("position") != "TE":
            continue

        curr_val = data.get("market_value", 0.0)
        if curr_val <= 0:
            continue

        if curr_val >= 4000:
            rate = 0.20 if bonus_rec_te <= 0.5 else 0.20 + (0.35 - 0.20) * ((bonus_rec_te - 0.5) / 0.5)
        elif curr_val >= 1500:
            rate = 0.15 if bonus_rec_te <= 0.5 else 0.15 + (0.25 - 0.15) * ((bonus_rec_te - 0.5) / 0.5)
        else:
            rate = 0.08 if bonus_rec_te <= 0.5 else 0.08 + (0.15 - 0.08) * ((bonus_rec_te - 0.5) / 0.5)

        data["market_value"] = round(curr_val * (1.0 + rate), 1)
        data["tep_boost_applied"] = rate

    return lookup


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
    ecr_col = "ecr_2qb" if is_superflex else "ecr_1qb"
    val_col = "value_2qb" if is_superflex else "value_1qb"

    curve = _build_ecr_to_value_curve(values_players_raw, is_superflex) if values_players_raw else []
    dp_picks = {}
    pattern = re.compile(r"^(\d{4})\s+(?:(Early|Mid|Late)\s+)?(\d+)(?:st|nd|rd|th)$", re.IGNORECASE)

    for row in values_picks_raw:
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


def _parse_ktc_picks(ktc_raw, is_superflex=True):
    ktc_picks = {}
    if not ktc_raw:
        return ktc_picks

    val_key = "superflexValues" if is_superflex else "oneQBValues"
    pattern = re.compile(r"^(\d{4})\s+(?:(Early|Mid|Late)\s+)?(\d+)(?:st|nd|rd|th)$", re.IGNORECASE)

    for p in ktc_raw:
        if p.get("position") != "RDP":
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
