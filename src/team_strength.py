from collections import Counter
from src.matching import match_players_by_sleeper_id


FIXED_POSITIONS = {"QB", "RB", "WR", "TE", "K", "DEF", "DL", "LB", "DB"}

FLEX_RULES = [
    # Slot name, eligible positions, order of filling (most specific first)
    ("WRRB_FLEX", {"RB", "WR"}),
    ("REC_FLEX", {"WR", "TE"}),
    ("FLEX", {"RB", "WR", "TE"}),
    ("SUPER_FLEX", {"QB", "RB", "WR", "TE"}),
    ("IDP_FLEX", {"DL", "LB", "DB"}),
]


def simulate_optimal_lineup(roster_players, lookup, roster_positions, is_dynasty=True):
    """
    Optimizes a fantasy starting lineup based on Sleeper league roster_positions.
    Fills fixed position slots first, then flex slots in order of specificity.
    All remaining roster players are designated as the bench.

    Returns (starters, bench) where each is a list of (player_obj, ranking_data).
    """
    if not roster_players:
        return [], []

    # If roster_positions is passed as a dict of counts, convert to list of slot strings
    if isinstance(roster_positions, dict):
        slots_list = []
        for pos, count in roster_positions.items():
            slots_list.extend([pos] * count)
        roster_positions = slots_list

    # Separate starting slots from bench/reserve slots
    starting_slots = [p for p in roster_positions if p not in {"BN", "IR", "TAXI"}]

    # Match roster players to lookup
    matched, _ = match_players_by_sleeper_id(roster_players, lookup)
    if not matched:
        return [], []

    # Sort players by priority:
    # In Dynasty: market_value descending (tie-break by rank_ecr ascending)
    # In Redraft: rank_ecr ascending (tie-break by market_value descending)
    if is_dynasty:
        sorted_players = sorted(
            matched,
            key=lambda item: (-item[1].get("market_value", 0.0), item[1].get("rank_ecr", 999.0))
        )
    else:
        sorted_players = sorted(
            matched,
            key=lambda item: (item[1].get("rank_ecr", 999.0), -item[1].get("market_value", 0.0))
        )

    assigned_player_ids = set()
    starters = []

    # 1. Fill fixed position slots (e.g. QB, RB, WR, TE, K, DEF)
    fixed_slots = [s for s in starting_slots if s in FIXED_POSITIONS]
    fixed_needed = Counter(fixed_slots)

    for pos, needed in fixed_needed.items():
        count = 0
        for p_obj, r_data in sorted_players:
            pid = p_obj.get("player_id")
            if pid not in assigned_player_ids and p_obj.get("position") == pos:
                starters.append((p_obj, r_data))
                assigned_player_ids.add(pid)
                count += 1
                if count >= needed:
                    break

    # 2. Fill flexible slots (e.g. WRRB_FLEX, FLEX, SUPER_FLEX) in order of specificity
    flex_dict = dict(FLEX_RULES)
    flex_order = [slot_name for slot_name, _ in FLEX_RULES]
    league_flex_slots = [s for s in starting_slots if s in flex_dict]
    league_flex_slots.sort(key=lambda s: flex_order.index(s) if s in flex_order else 99)

    for flex_slot in league_flex_slots:
        eligible_positions = flex_dict[flex_slot]
        for p_obj, r_data in sorted_players:
            pid = p_obj.get("player_id")
            if pid not in assigned_player_ids and p_obj.get("position") in eligible_positions:
                starters.append((p_obj, r_data))
                assigned_player_ids.add(pid)
                break

    # 3. All remaining matched players become the bench
    bench = [
        (p_obj, r_data)
        for p_obj, r_data in sorted_players
        if p_obj.get("player_id") not in assigned_player_ids
    ]

    return starters, bench


def calculate_team_strength(roster_players, lookup, roster_positions, starter_weight=0.70, bench_weight=0.30, is_dynasty=True):
    """
    Calculates team strength considering both:
    1. Starting Lineup (70% weight) - weekly scoring potential.
    2. Bench Depth (30% weight) - injury resilience and trade flexibility.

    Returns (position_averages, overall_avg_rank, blended_points, details_dict).
    """
    starters, bench = simulate_optimal_lineup(roster_players, lookup, roster_positions, is_dynasty=is_dynasty)

    position_ranks = {}
    all_starter_ranks = []
    starter_counts_by_pos = {}

    for p_obj, r_data in starters:
        pos = p_obj.get("position")
        rank = r_data.get("rank_ecr")
        if rank is not None:
            position_ranks.setdefault(pos, []).append(rank)
            all_starter_ranks.append(rank)
        starter_counts_by_pos[pos] = starter_counts_by_pos.get(pos, 0) + 1

    position_averages = {
        pos: sum(ranks) / len(ranks) for pos, ranks in position_ranks.items() if ranks
    }

    overall_avg = sum(all_starter_ranks) / len(all_starter_ranks) if all_starter_ranks else None
    starters_total = sum(r_data.get("market_value", 0.0) for _, r_data in starters)
    bench_total = sum(r_data.get("market_value", 0.0) for _, r_data in bench)
    blended_points = starter_weight * starters_total + bench_weight * bench_total

    details = {
        "starters_market_value": starters_total,
        "bench_market_value": bench_total,
        "total_market_value": starters_total + bench_total,
        "blended_points": blended_points,
        "starter_counts_by_pos": starter_counts_by_pos,
        "starters_count": len(starters),
        "bench_count": len(bench),
    }

    return position_averages, overall_avg, blended_points, details


def rank_teams_in_league(all_rosters_players, lookup, roster_positions, is_dynasty=True):
    """
    Ranks all teams in the league.
    - In Dynasty: ranked descending by blended market value points (Starters 70% + Bench 30%).
    - In Redraft: ranked descending by blended market value points (Starters 80% + Bench 20%).
    """
    team_strengths = []

    for roster_id, roster_players in all_rosters_players.items():
        w_starter = 0.70 if is_dynasty else 0.80
        w_bench = 0.30 if is_dynasty else 0.20
        _, overall_avg, blended_points, details = calculate_team_strength(
            roster_players, lookup, roster_positions, starter_weight=w_starter, bench_weight=w_bench, is_dynasty=is_dynasty
        )

        score = blended_points if blended_points is not None else 0.0
        team_strengths.append((roster_id, score, details))

    team_strengths.sort(key=lambda t: -t[1])
    return team_strengths


def get_strength_tier(roster_id, ranked_teams):
    total = len(ranked_teams)

    if total == 0:
        return None, None, 0

    for position, item in enumerate(ranked_teams, start=1):
        rid = item[0]
        if rid == roster_id:
            tier = score_to_tier(percentile_score(position, total))
            return tier, position, total

    return None, None, total


def percentile_score(position, total):
    if position is None or total is None or total <= 1:
        return 0.5

    return (total - position) / (total - 1)


def score_to_tier(score):
    if score is None:
        return "medium"
    if score >= 0.60:
        return "high"
    elif score >= 0.35:
        return "medium"
    else:
        return "low"


def total_games_played(roster):
    settings = roster.get("settings", {})

    return settings.get("wins", 0) + settings.get("losses", 0) + settings.get("ties", 0)


def rank_teams_by_record(rosters):
    def record_key(roster):
        settings = roster.get("settings", {})
        wins = settings.get("wins", 0)
        ties = settings.get("ties", 0)
        fpts = settings.get("fpts", 0) + settings.get("fpts_decimal", 0) / 100

        return (-(wins * 2 + ties), -fpts)

    return sorted(rosters, key=record_key)


def calculate_dynamic_record_weight(games_played: int, season_length: int = 14) -> float:
    """
    Dynamically scales the weight of actual regular-season W-L record vs. paper roster value.
    - Pre-season (0 games): 0% record (100% paper roster)
    - Early season (Weeks 1-3): 15% - 25% record (small sample variance protection)
    - Mid season (Weeks 4-8): 35% - 65% record (balanced sample)
    - Late season (Weeks 9-14+): 75% - 90% record (standings reality dominates)
    """
    if games_played <= 0:
        return 0.0
    elif games_played == 1:
        return 0.15
    elif games_played == 2:
        return 0.20
    elif games_played == 3:
        return 0.25
    elif games_played == 4:
        return 0.35
    elif games_played == 5:
        return 0.45
    elif games_played == 6:
        return 0.55
    elif games_played == 7:
        return 0.65
    elif games_played == 8:
        return 0.72
    elif games_played == 9:
        return 0.80
    elif games_played == 10:
        return 0.85
    else:
        return 0.90


def get_current_strength_tier(
    user_roster,
    rosters,
    redraft_position,
    redraft_total,
    season_length=14,
    playoff_pct=None,
    is_eliminated=False,
):
    if not redraft_total or not redraft_position:
        return "medium", 0

    redraft_score = percentile_score(redraft_position, redraft_total)
    games_played = total_games_played(user_roster)
    record_score = None

    if games_played > 0 and rosters:
        ranked = rank_teams_by_record(rosters)
        total = len(ranked)

        for position, roster in enumerate(ranked, start=1):
            if roster["roster_id"] == user_roster["roster_id"]:
                record_score = percentile_score(position, total)
                break

    if record_score is None or games_played == 0:
        blended_score = redraft_score
    else:
        # Dynamic record scaling: small sample early, standings reality late
        record_weight = calculate_dynamic_record_weight(games_played, season_length)
        blended_score = record_weight * record_score + (1 - record_weight) * redraft_score

    tier = score_to_tier(blended_score)

    # Hard mathematical rebuild ceiling:
    # 1. Mathematically eliminated teams are locked into rebuild
    # 2. Teams with <= 5.0% playoff odds after at least 4 games played are locked into rebuild
    # 3. Fallback: Teams with <= 1 win after at least 7 games played
    wins = user_roster.get("settings", {}).get("wins", 0)
    if is_eliminated:
        tier = "low"
    elif playoff_pct is not None and playoff_pct <= 5.0 and games_played >= 4:
        tier = "low"
    elif games_played >= 7 and wins <= 1:
        tier = "low"

    return tier, games_played


def get_rebuild_ceiling_meta(
    user_roster,
    games_played: int,
    playoff_pct=None,
    is_eliminated=False,
):
    """
    Returns diagnostic metadata about whether the Mathematical Rebuild Ceiling was enforced.
    """
    wins = user_roster.get("settings", {}).get("wins", 0)
    losses = user_roster.get("settings", {}).get("losses", 0)

    if is_eliminated:
        return {
            "is_locked_rebuild": True,
            "reason": f"Mathematically Eliminated from Playoffs ({wins}-{losses})",
            "clinch_status": "ELIMINATED",
        }
    if playoff_pct is not None and playoff_pct <= 5.0 and games_played >= 4:
        return {
            "is_locked_rebuild": True,
            "reason": f"Playoff Odds Dropped to {playoff_pct:.1f}% (Rebuild Ceiling Enforced)",
            "clinch_status": "ELIMINATED",
        }
    if games_played >= 7 and wins <= 1:
        return {
            "is_locked_rebuild": True,
            "reason": f"Standings Deficit: {wins}-{losses} after Week {games_played}",
            "clinch_status": "ELIMINATED",
        }

    return {
        "is_locked_rebuild": False,
        "reason": "",
        "clinch_status": "HUNT" if (playoff_pct is not None and playoff_pct >= 15.0) else "DANGER",
    }


def classify_dynasty_team(current_tier, dynasty_tier):
    if current_tier is None or dynasty_tier is None:
        return "Balanced Squad", "neutral"

    if current_tier == "high" and dynasty_tier == "high":
        return "Dominant Empire (Elite starting lineup & strong young core)", "win"
    if current_tier == "high" and dynasty_tier == "medium":
        return "Win-Now Favorite (High-scoring firepower with solid depth)", "win"
    if current_tier == "high" and dynasty_tier == "low":
        return "All-In Win-Now (Peak Scoring Window: Veteran studs — push for the title)", "win"

    if current_tier == "medium" and dynasty_tier == "high":
        return "Ascending Contender (Playoff Threat: Competitive starters backed by an elite young core)", "win"
    if current_tier == "medium" and dynasty_tier == "medium":
        return "Frisky Competitor (Playoff Bubble: Balanced roster capable of a postseason run)", "neutral"
    if current_tier == "medium" and dynasty_tier == "low":
        return "Fragile Bubble Team (Fringe Contender: Competitive starters but depleted depth/picks)", "neutral"

    if current_tier == "low" and dynasty_tier == "high":
        return "Productive Struggle (Elite young talent & draft capital; building powerhouse)", "rebuild"
    if current_tier == "low" and dynasty_tier == "medium":
        return "Retooling Roster (Developing youth & picks to return to contention)", "rebuild"
    if current_tier == "low" and dynasty_tier == "low":
        return "Ground-Up Rebuild (Depleted roster; prioritize picks & high-upside youth)", "rebuild"

    return "Frisky Competitor", "neutral"


def get_picks_qualifier(category_type, picks_tier):
    if picks_tier is None or category_type == "neutral":
        return ""

    if category_type == "win":
        if picks_tier == "high":
            return " — strong draft capital to acquire win-now studs via trade"
        elif picks_tier == "low":
            return " — scarce draft capital, limiting trade flexibility"

    if category_type == "rebuild":
        if picks_tier == "high":
            return " — well-positioned with abundant draft capital to accelerate the rebuild"
        elif picks_tier == "low":
            return " — poorly positioned with scarce draft capital to rebuild"

    return ""


def classify_redraft_team(current_tier):
    if current_tier is None:
        return "Playoff Contender"

    if current_tier == "high":
        return "Title Contender (Top-tier starting lineup & scoring ceiling — Championship favorite)"

    if current_tier == "low":
        return "Uphill Battle / Rebuilding (Struggling scoring pace — needs aggressive moves)"

    return "Playoff Contender (Firmly in the playoff hunt — stream matchups & optimize starting depth)"