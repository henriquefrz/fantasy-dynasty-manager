LEAGUE_TYPE_MAP = {
    0: "redraft",
    1: "keeper",
    2: "dynasty",
}


def get_league_type(league):
    type_code = league.get("settings", {}).get("type")

    return LEAGUE_TYPE_MAP.get(type_code, "desconhecido")


def has_assigned_rosters(rosters):
    return any(roster.get("players") for roster in rosters)


def get_league_stage(league, rosters):
    status = league.get("status")
    assigned = has_assigned_rosters(rosters)

    if status == "pre_draft" and not assigned:
        return "pre_draft_sem_roster"

    if status == "pre_draft" and assigned:
        return "pre_draft_com_roster"

    if status == "drafting":
        return "em_draft"

    if status == "in_season":
        return "em_temporada"

    if status == "complete":
        return "temporada_encerrada"

    return "desconhecido"


def classify_league(league, rosters):
    return {
        "name": league["name"],
        "type": get_league_type(league),
        "stage": get_league_stage(league, rosters),
    }