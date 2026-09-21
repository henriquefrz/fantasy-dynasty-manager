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


# Deepest draft round any league in this app currently runs - kept in sync
# with market_data.MAX_PROJECTED_DRAFT_ROUND (the source-data extrapolation
# limit); duplicated here rather than imported to avoid a market_data <->
# draft_picks import cycle (trade_engine imports from both).
MAX_PROJECTED_DRAFT_ROUND = 10

# Fractional draft slot each tier represents, as the midpoint of the third
# of the round it covers (early = first third, late = last third) - used
# both to label a pick's display tier and to place that tier's known value
# on the 12-team reference curve at a consistent x-position.
_TIER_SLOT_FRACTION = {"early": 1 / 6, "mid": 0.5, "late": 5 / 6}


def project_draft_position(sim_projected_rank, total_rosters, round_num, draft_type="linear"):
    """
    Projects the absolute draft slot (1..total_rosters) a team picks at
    within round_num, from its Monte Carlo Season Power Score standing
    (sim_projected_rank: 1 = best projected team, total_rosters = worst).
    Dynasty rookie drafts hand the worst team the round's first pick, and a
    "linear" (straight) draft keeps that same slot order in every round;
    "snake" reverses it on even rounds.
    """
    slot = total_rosters - sim_projected_rank + 1
    if draft_type == "snake" and round_num % 2 == 0:
        slot = total_rosters - slot + 1
    return slot


def project_absolute_pick_index(sim_projected_rank, total_rosters, round_num, draft_type="linear"):
    """
    The pick's literal overall number in ITS OWN league's draft (e.g. the
    9th player taken, for a round-2 pick in an 8-team league). Used as-is
    as the x-coordinate against the 12-team-calibrated value curve: draft
    capital at a given overall depth carries roughly the same market value
    regardless of how many teams produced that depth.
    """
    slot = project_draft_position(sim_projected_rank, total_rosters, round_num, draft_type)
    return (round_num - 1) * total_rosters + slot


def project_pick_tier(sim_projected_rank, total_rosters, round_num, season=None, target_season=None, draft_type="linear"):
    """
    Projects a pick's display tier (early / mid / late within its round)
    from the team's absolute draft slot, itself derived from its Monte
    Carlo Season Power Score standing (sim_projected_rank).

    - Year +1 (target_season): differentiates by standing - top-third
      draft slot -> 'early' (highest value), bottom-third -> 'late'
      (lowest value).
    - Year +2 / Year +3 and beyond: high long-term uncertainty; always
      'mid' (generic), regardless of standing.
    """
    if season and target_season and season != target_season:
        return "mid"
    if not sim_projected_rank or not total_rosters or total_rosters <= 1:
        return "mid"

    slot = project_draft_position(sim_projected_rank, total_rosters, round_num, draft_type)
    fraction = (slot - 1) / (total_rosters - 1)
    if fraction <= 1 / 3:
        return "early"
    elif fraction <= 2 / 3:
        return "mid"
    return "late"


def format_picks_summary(picks, sim_rank_map=None, total_rosters=12, target_season=None, draft_type="linear"):
    """
    Returns a clean, human-readable string summarizing owned picks.
    Only annotates picks from target_season (Year +1) for rounds 1-3.
    Example: '2027: R1 (Early), R2 (Early), R3 (Early) | 2028: R1, R2, R3 | 2029: R1, R2, R3'
    """
    by_season = {}

    for season, round_num, original_roster_id in picks:
        label = f"R{round_num}"
        if season == target_season and round_num <= 3 and sim_rank_map:
            sim_projected_rank = sim_rank_map.get(original_roster_id, (None, 0.0))[0]
            tier = project_pick_tier(
                sim_projected_rank, total_rosters, round_num, season=season, target_season=target_season, draft_type=draft_type
            )
            if tier != "mid":
                label += f" ({tier.capitalize()})"

        by_season.setdefault(season, []).append(label)

    parts = []
    for season in sorted(by_season):
        rounds_str = ", ".join(by_season[season])
        parts.append(f"{season}: {rounds_str}")

    return " | ".join(parts)


def _build_pick_value_anchor_curve(picks_lookup, season, max_round=MAX_PROJECTED_DRAFT_ROUND, anchor_total_rosters=12):
    """
    Builds a sorted (12-team-equivalent overall_pick_index, value) curve
    from whatever (season, round, tier) entries picks_lookup has for this
    season, up to max_round. This is the 12-team reference calibration
    every league's absolute pick position gets interpolated against,
    regardless of that league's own size.
    """
    anchors = []
    for round_num in range(1, max_round + 1):
        for tier, slot_fraction in _TIER_SLOT_FRACTION.items():
            val = picks_lookup.get((season, round_num, tier))
            if val is None:
                continue
            overall_idx = (round_num - 1) * anchor_total_rosters + slot_fraction * (anchor_total_rosters - 1) + 1
            anchors.append((overall_idx, float(val)))
    anchors.sort(key=lambda p: p[0])
    return anchors


def get_single_pick_value(
    season: str,
    round_num: int,
    sim_projected_rank,
    picks_lookup: dict,
    total_rosters: int = 12,
    target_season: str = None,
    draft_type: str = "linear",
) -> float:
    """
    Returns the market value points for a future draft pick, interpolated
    by its absolute overall draft position (in ITS OWN league's draft,
    derived from sim_projected_rank via project_absolute_pick_index)
    against the 12-team-calibrated value curve. Works uniformly for any
    league size: e.g. a round-2 pick in an 8-team league starts at overall
    pick 9, which lands inside round 1's 'late' portion of the 12-team
    curve - no per-league-size special-casing needed.

    Only differentiates by standing for target_season; every other season
    (including no sim_projected_rank/total_rosters available) falls back
    to the season's generic 'mid' value.
    """
    def _generic_value():
        val = picks_lookup.get((season, round_num, "mid"))
        if val is None:
            val = picks_lookup.get((season, round_num), 0.0)
        return float(val or 0.0)

    if not season or not sim_projected_rank or not total_rosters or total_rosters <= 1:
        return _generic_value()
    if target_season and season != target_season:
        return _generic_value()

    anchors = _build_pick_value_anchor_curve(picks_lookup, season)
    if not anchors:
        return _generic_value()

    target_overall = project_absolute_pick_index(sim_projected_rank, total_rosters, round_num, draft_type)

    if target_overall <= anchors[0][0]:
        return anchors[0][1]
    if target_overall >= anchors[-1][0]:
        return anchors[-1][1]

    for i in range(len(anchors) - 1):
        x1, y1 = anchors[i]
        x2, y2 = anchors[i + 1]
        if x1 <= target_overall <= x2:
            if x2 == x1:
                return y1
            ratio = (target_overall - x1) / (x2 - x1)
            return round(y1 + ratio * (y2 - y1), 1)

    return anchors[-1][1]


def get_picks_capital_value(picks, picks_value_lookup, sim_rank_map=None, total_rosters=12, target_season=None, draft_type="linear"):
    """
    Calculates the total market value points for a list of owned picks,
    incorporating each pick's projected value (standing-based for
    target_season, generic otherwise) and league-size scaling.
    Each pick is a tuple: (season, round_num, original_roster_id).
    """
    total = 0.0
    for season, round_num, original_roster_id in picks:
        sim_projected_rank = (sim_rank_map or {}).get(original_roster_id, (None, 0.0))[0]
        val = get_single_pick_value(
            season, round_num, sim_projected_rank, picks_value_lookup,
            total_rosters=total_rosters, target_season=target_season, draft_type=draft_type,
        )
        total += val
    return total


def rank_teams_by_picks(ownership, total_rosters, picks_value_lookup, sim_rank_map=None, target_season=None, draft_type="linear"):
    """
    Ranks all teams in the league by their total draft pick market value,
    accounting for projected pick value in target_season and league size scaling.
    Returns a list of tuples: (roster_id, total_value_points) sorted descending.
    """
    scores = []

    for roster_id in range(1, total_rosters + 1):
        picks = get_picks_for_roster(ownership, roster_id)
        score = get_picks_capital_value(
            picks, picks_value_lookup, sim_rank_map=sim_rank_map,
            total_rosters=total_rosters, target_season=target_season, draft_type=draft_type,
        )
        scores.append((roster_id, score))

    scores.sort(key=lambda t: -t[1])

    return scores