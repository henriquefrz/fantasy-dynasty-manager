from collections import Counter


LEAGUE_TYPE_MAP = {
    0: "redraft",
    1: "keeper",
    2: "dynasty",
}


def get_league_type(league):
    type_code = league.get("settings", {}).get("type")

    return LEAGUE_TYPE_MAP.get(type_code, "unknown")


def has_assigned_rosters(rosters):
    return any(roster.get("players") for roster in rosters)


def get_league_stage(league, rosters):
    status = league.get("status")
    assigned = has_assigned_rosters(rosters)

    if status == "pre_draft" and not assigned:
        return "pre_draft_no_roster"

    if status == "pre_draft" and assigned:
        return "pre_draft_with_roster"

    if status == "drafting":
        return "drafting"

    if status == "in_season":
        return "in_season"

    if status == "complete":
        return "complete"

    return "unknown"


def classify_league(league, rosters):
    return {
        "name": league["name"],
        "type": get_league_type(league),
        "stage": get_league_stage(league, rosters),
    }


def is_superflex_league(roster_positions):
    """
    Returns True if roster_positions indicates a Superflex format: an explicit
    "SUPER_FLEX" slot, or 2+ dedicated "QB" slots. Single shared implementation
    for every caller that needs this (previously reimplemented independently
    in 8 places across app.py, main.py, trade_engine.py, and
    weekly_automation.py, with no guarantee they'd stay in sync).
    """
    if not roster_positions:
        return False

    return "SUPER_FLEX" in roster_positions or roster_positions.count("QB") >= 2


def get_starter_counts(league):
    roster_positions = league.get("roster_positions", [])
    counts = Counter(roster_positions)

    return {
        "QB": counts.get("QB", 0),
        "RB": counts.get("RB", 0),
        "WR": counts.get("WR", 0),
        "TE": counts.get("TE", 0),
        "K": counts.get("K", 0),
        "DEF": counts.get("DEF", 0),
    }