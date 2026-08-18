import csv
import io

import requests


FPECR_URL = "https://raw.githubusercontent.com/dynastyprocess/data/master/files/db_fpecr_latest.csv"
PLAYERIDS_URL = "https://raw.githubusercontent.com/dynastyprocess/data/master/files/db_playerids.csv"

POSITIONS = ["QB", "RB", "WR", "TE", "K"]


def _download_csv(url):
    response = requests.get(url)

    response.raise_for_status()

    csv_text = response.text
    reader = csv.DictReader(io.StringIO(csv_text))

    return list(reader)


def get_fp_rankings_raw():
    return _download_csv(FPECR_URL)


def get_player_ids_raw():
    return _download_csv(PLAYERIDS_URL)


def _build_player_lookup(fp_rankings_raw, player_ids_raw, ranking_prefix):
    fp_id_to_sleeper_id = {}

    for row in player_ids_raw:
        sleeper_id = row.get("sleeper_id")
        fp_id = row.get("fantasypros_id")

        if sleeper_id and sleeper_id != "NA" and fp_id and fp_id != "NA":
            fp_id_to_sleeper_id[fp_id] = sleeper_id

    page_types = {f"{ranking_prefix}-{pos.lower()}" for pos in POSITIONS}

    lookup = {}

    for row in fp_rankings_raw:
        if row["page_type"] not in page_types:
            continue

        sleeper_id = fp_id_to_sleeper_id.get(row["id"])

        if not sleeper_id:
            continue

        try:
            rank_ecr = float(row["ecr"])
        except (ValueError, TypeError):
            continue

        lookup[sleeper_id] = {
            "rank_ecr": rank_ecr,
            "player_name": row["player"],
            "position": row["pos"],
        }

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

        try:
            rank_ecr = float(row["ecr"])
        except (ValueError, TypeError):
            continue

        lookup[team] = {
            "rank_ecr": rank_ecr,
            "player_name": row["player"],
            "position": row["pos"],
        }

    return lookup


def build_positional_lookup(fp_rankings_raw, player_ids_raw, ranking_type):
    lookup = _build_player_lookup(fp_rankings_raw, player_ids_raw, ranking_type)
    dst_lookup = _build_dst_lookup(fp_rankings_raw, ranking_type)

    lookup.update(dst_lookup)

    return lookup