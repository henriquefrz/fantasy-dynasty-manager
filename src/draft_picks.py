DRAFT_COMPLETED_STATUSES = {"in_season", "complete"}


def build_picks_ownership(league, traded_picks, future_years=3):
    """
    Builds a dictionary mapping draft picks to their current owner roster ID.

    Key: (season_str, round_int, original_roster_id_int)
    Value: current_owner_roster_id_int

    By default, future_years=3 tracks 3 future draft classes (e.g., 2027, 2028, 2029).
    """
    rounds = league["settings"]["draft_rounds"]
    current_season = int(league["season"])
    total_rosters = league["total_rosters"]

    current_season_already_drafted = league.get("status") in DRAFT_COMPLETED_STATUSES
    start_offset = 1 if current_season_already_drafted else 0

    ownership = {}

    # Initialize default ownership: every team starts owning their own original picks
    for year_offset in range(start_offset, future_years + 1):
        season = str(current_season + year_offset)

        for round_num in range(1, rounds + 1):
            for roster_id in range(1, total_rosters + 1):
                ownership[(season, round_num, roster_id)] = roster_id

    # Apply traded picks from the Sleeper API
    for pick in traded_picks:
        key = (pick["season"], pick["round"], pick["roster_id"])

        if key in ownership:
            ownership[key] = pick["owner_id"]

    return ownership


def get_picks_for_roster(ownership, roster_id):
    """
    Returns all picks currently owned by a specific roster.
    Sorted chronologically by season and round.
    """
    picks = [key for key, owner in ownership.items() if owner == roster_id]
    picks.sort(key=lambda k: (k[0], k[1]))

    return picks


def project_pick_tier(original_roster_id, team_tiers=None, season=None, target_season="2027"):
    """
    Projects whether an upcoming draft pick will be early, mid, or late
    based on the original owning team's tier/standing.

    - Year +1 (target_season, e.g. 2027): High correlation with current performance:
      - 'low' tier (Rebuilder) -> 'early' (projected top picks 1.01-1.04)
      - 'high' tier (Contender) -> 'late' (projected playoff picks 1.09-1.12)
      - 'medium' tier or unknown -> 'mid' (picks 1.05-1.08)
    - Year +2 / Year +3 (2028, 2029+): High long-term uncertainty; defaults to 'mid' (generic).
    """
    if season and target_season and season != target_season:
        return "mid"

    if not team_tiers or original_roster_id not in team_tiers:
        return "mid"

    tier = team_tiers[original_roster_id]
    if tier == "low":
        return "early"
    elif tier == "high":
        return "late"
    return "mid"


def format_picks_summary(picks, team_tiers=None, target_season="2027"):
    """
    Returns a clean, human-readable string summarizing owned picks.
    Only annotates picks from target_season (Year +1, e.g. 2027) for rounds 1-3.
    Example: '2027: R1 (Early), R2 (Early), R3 (Early) | 2028: R1, R2, R3 | 2029: R1, R2, R3'
    """
    by_season = {}

    for season, round_num, original_roster_id in picks:
        label = f"R{round_num}"
        if season == target_season and round_num <= 3 and team_tiers:
            tier = project_pick_tier(original_roster_id, team_tiers, season=season, target_season=target_season)
            if tier != "mid":
                label += f" ({tier.capitalize()})"

        by_season.setdefault(season, []).append(label)

    parts = []
    for season in sorted(by_season):
        rounds_str = ", ".join(by_season[season])
        parts.append(f"{season}: {rounds_str}")

    return " | ".join(parts)


def get_single_pick_value(
    season: str,
    round_num: int,
    tier: str,
    picks_lookup: dict,
    total_rosters: int = 12,
) -> float:
    """
    Returns the market value points for a draft pick, dynamically scaled by league size.
    Standard dynasty markets (KTC, FantasyCalc) calibrate picks for 12-team leagues.
    In an N-team league, overall pick numbers differ (e.g. pick 2.01 in an 8-team league
    is overall pick #9, equivalent to a 1.09 in a 12-team league).
    This function interpolates the value against the 12-team baseline curve when total_rosters != 12.
    """
    if total_rosters == 12:
        val = picks_lookup.get((season, round_num, tier))
        if val is None:
            val = picks_lookup.get((season, round_num), 0.0)
        return float(val)

    # Standard 12-team anchor points: (overall_pick_idx, (round_num, tier))
    anchors = [
        (1.0, (1, "early")),
        (2.4, (1, "early")),
        (6.0, (1, "mid")),
        (10.2, (1, "late")),
        (14.4, (2, "early")),
        (18.0, (2, "mid")),
        (22.2, (2, "late")),
        (26.4, (3, "early")),
        (30.0, (3, "mid")),
        (34.2, (3, "late")),
        (42.0, (4, "mid")),
        (54.0, (5, "mid")),
    ]

    pts = []
    for overall_idx, (r, t) in anchors:
        v = picks_lookup.get((season, r, t))
        if v is None:
            v = picks_lookup.get((season, r))
        if v is not None:
            pts.append((overall_idx, float(v)))

    if not pts:
        return float(picks_lookup.get((season, round_num, tier), 0.0))

    pts.sort(key=lambda p: p[0])

    tier_offsets = {"early": 0.2, "mid": 0.5, "late": 0.85}
    offset = tier_offsets.get(tier, 0.5) * total_rosters
    target_overall = (round_num - 1) * total_rosters + offset

    if target_overall <= pts[0][0]:
        return pts[0][1]
    if target_overall >= pts[-1][0]:
        return pts[-1][1]

    for i in range(len(pts) - 1):
        x1, y1 = pts[i]
        x2, y2 = pts[i + 1]
        if x1 <= target_overall <= x2:
            if x2 == x1:
                return y1
            slope = (y2 - y1) / (x2 - x1)
            return round(y1 + slope * (target_overall - x1), 1)

    return pts[-1][1]


def get_picks_capital_value(picks, picks_value_lookup, team_tiers=None, target_season="2027", total_rosters=12):
    """
    Calculates the total market value points for a list of owned picks,
    incorporating projected pick tier (early / mid / late) for the upcoming season (target_season)
    and scaling for league size (total_rosters).
    Each pick is a tuple: (season, round_num, original_roster_id).
    """
    total = 0.0
    for season, round_num, original_roster_id in picks:
        tier = project_pick_tier(original_roster_id, team_tiers, season=season, target_season=target_season)
        val = get_single_pick_value(season, round_num, tier, picks_value_lookup, total_rosters=total_rosters)
        total += val
    return total


def rank_teams_by_picks(ownership, total_rosters, picks_value_lookup, team_tiers=None, target_season="2027"):
    """
    Ranks all teams in the league by their total draft pick market value,
    accounting for projected pick tiers in the target_season and league size scaling.
    Returns a list of tuples: (roster_id, total_value_points) sorted descending.
    """
    scores = []

    for roster_id in range(1, total_rosters + 1):
        picks = get_picks_for_roster(ownership, roster_id)
        score = get_picks_capital_value(picks, picks_value_lookup, team_tiers, target_season=target_season, total_rosters=total_rosters)
        scores.append((roster_id, score))

    scores.sort(key=lambda t: -t[1])

    return scores