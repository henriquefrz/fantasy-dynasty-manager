"""
playoff_simulator.py

Monte Carlo Playoff Odds & Power Rankings Simulation Engine.
Simulates remaining regular season and postseason matchups across 1,000 iterations
using weekly starting lineup scoring projections, realistic scoring variance (Gaussian),
and real head-to-head league schedules from Sleeper.
"""

import random
import hashlib
from typing import Dict, List, Tuple, Any, Optional
from src.start_sit import calculate_weekly_projected_points, simulate_optimal_weekly_lineup


DEFAULT_WEEKLY_STD_DEV = 13.5  # Standard deviation in fantasy football weekly team scoring
DEFAULT_SIMULATIONS = 1000


def compute_team_lineup_expectation(
    roster: Dict[str, Any],
    roster_players: List[Dict[str, Any]],
    weekly_projections: Dict[str, Any],
    scoring_settings: Dict[str, Any],
    roster_positions: List[str],
) -> Dict[str, Any]:
    """
    Computes a team's baseline weekly expected score (mu) and bench depth score
    using the optimal lineup simulation.
    """
    proj_lookup = {}
    for p in roster_players:
        pid = p.get("player_id")
        raw = weekly_projections.get(pid)
        pts = calculate_weekly_projected_points(pid, raw, scoring_settings, p)
        proj_lookup[pid] = pts

    starters, bench = simulate_optimal_weekly_lineup(
        roster_players=roster_players,
        projections_lookup=proj_lookup,
        roster_positions=roster_positions,
    )

    optimal_pts = sum(pts for _, pts, _ in starters)

    # Fallback to reasonable average if projections are missing
    if optimal_pts <= 10.0:
        optimal_pts = 105.0

    # Calculate bench depth score (top 4 bench players' projected points)
    top_bench_pts = sum(pts for _, pts in bench[:4])

    return {
        "roster_id": roster["roster_id"],
        "expected_pts": round(optimal_pts, 1),
        "std_dev": DEFAULT_WEEKLY_STD_DEV,
        "bench_depth_pts": round(top_bench_pts, 1),
    }


def simulate_single_matchup(mu1: float, sigma1: float, mu2: float, sigma2: float) -> Tuple[float, float]:
    """
    Simulates a head-to-head weekly fantasy matchup between two teams
    using Gaussian scoring distributions. Scores are floored at 40.0 pts.
    """
    s1 = max(40.0, random.gauss(mu1, sigma1))
    s2 = max(40.0, random.gauss(mu2, sigma2))
    return round(s1, 2), round(s2, 2)


def compute_elimination_and_clinch_status(
    rosters: List[Dict[str, Any]],
    schedule: Dict[int, List[Tuple[int, int]]],
    playoff_teams_count: int = 6,
    playoff_week_start: int = 15,
    current_week: int = 1,
    sim_results: Optional[Dict[int, Dict[str, Any]]] = None,
) -> Dict[int, Dict[str, Any]]:
    """
    Evaluates mathematical elimination and clinching status for every roster in the league.
    Combines direct standings & remaining schedule analysis with Monte Carlo simulation outcomes.

    Status codes:
    - CLINCHED: Guaranteed top-P finish or >= 99.5% simulated playoff probability (🏆)
    - CONTENDER: Playoff Odds >= 70% (⭐)
    - HUNT: 15% < Playoff Odds < 70% (🎯)
    - DANGER: 5% < Playoff Odds <= 15% (⚠️)
    - ELIMINATED: Mathematically eliminated or Playoff Odds <= 5% (❌)
    """
    roster_ids = [r["roster_id"] for r in rosters]
    end_regular_season = playoff_week_start - 1

    # Extract current records from rosters or simulation initial records
    records = {}
    for r in rosters:
        rid = r["roster_id"]
        settings = r.get("settings", {})
        w = settings.get("wins", 0)
        l = settings.get("losses", 0)
        t = settings.get("ties", 0)
        pf = settings.get("fpts", 0) + (settings.get("fpts_decimal", 0) / 100.0)

        # If sim_results has initial records for historical snapshots:
        if sim_results and rid in sim_results:
            w = sim_results[rid].get("initial_wins", w)
            l = sim_results[rid].get("initial_losses", l)
            t = sim_results[rid].get("initial_ties", t)
            pf = sim_results[rid].get("initial_pf", pf)

        records[rid] = {"wins": w, "losses": l, "ties": t, "pf": pf}

    # Count remaining regular season games for each team
    remaining_games = {rid: 0 for rid in roster_ids}
    if current_week <= end_regular_season:
        for w in range(current_week, playoff_week_start):
            matchups = schedule.get(w, [])
            if matchups:
                for r1, r2 in matchups:
                    if r1 in remaining_games:
                        remaining_games[r1] += 1
                    if r2 in remaining_games:
                        remaining_games[r2] += 1
            else:
                # Round-robin fallback: each team has 1 game per week
                for rid in roster_ids:
                    remaining_games[rid] += 1

    status_by_team = {}
    for rid in roster_ids:
        cur_w = records[rid]["wins"]
        cur_l = records[rid]["losses"]
        cur_pf = records[rid]["pf"]
        rem_g = remaining_games[rid]
        max_possible_wins = cur_w + rem_g
        min_possible_wins = cur_w

        # Check mathematical elimination:
        # Count how many other teams already have strictly more wins than team's max possible wins
        strictly_ahead_teams = sum(
            1 for other_rid, o_rec in records.items()
            if other_rid != rid and (
                o_rec["wins"] > max_possible_wins
                or (o_rec["wins"] == max_possible_wins and rem_g == 0 and o_rec["pf"] > cur_pf)
            )
        )
        is_math_eliminated = (strictly_ahead_teams >= playoff_teams_count)

        # Check mathematical clinch:
        # Count how many other teams can possibly reach or exceed team's min possible wins
        teams_that_can_catch = sum(
            1 for other_rid, o_rec in records.items()
            if other_rid != rid and (
                o_rec["wins"] + remaining_games[other_rid] > min_possible_wins
                or (o_rec["wins"] + remaining_games[other_rid] == min_possible_wins and o_rec["pf"] >= cur_pf)
            )
        )
        is_math_clinched = (teams_that_can_catch < playoff_teams_count) and (current_week > 1)

        # Monte Carlo probability cross-check
        sim_p_pct = sim_results.get(rid, {}).get("playoff_pct", None) if sim_results else None

        if is_math_eliminated or (sim_p_pct is not None and sim_p_pct == 0.0 and current_week >= 4):
            code = "ELIMINATED"
            label = "Eliminated"
            badge_icon = "❌"
            badge_color = "#f43f5e"
            is_elim = True
            is_clinch = False
        elif is_math_clinched or (sim_p_pct is not None and sim_p_pct >= 99.5 and current_week >= 8):
            code = "CLINCHED"
            label = "Clinched Playoff"
            badge_icon = "🏆"
            badge_color = "#10b981"
            is_elim = False
            is_clinch = True
        elif sim_p_pct is not None and sim_p_pct <= 5.0 and (cur_w + cur_l) >= 4:
            code = "ELIMINATED"
            label = "Rebuild Locked (<=5%)"
            badge_icon = "🔒"
            badge_color = "#fb7185"
            is_elim = True
            is_clinch = False
        elif sim_p_pct is not None and sim_p_pct <= 15.0:
            code = "DANGER"
            label = "Danger Zone"
            badge_icon = "⚠️"
            badge_color = "#f59e0b"
            is_elim = False
            is_clinch = False
        elif sim_p_pct is not None and sim_p_pct >= 70.0:
            code = "CONTENDER"
            label = "Playoff Track"
            badge_icon = "⭐"
            badge_color = "#06b6d4"
            is_elim = False
            is_clinch = False
        else:
            code = "HUNT"
            label = "In The Hunt"
            badge_icon = "🎯"
            badge_color = "#3b82f6"
            is_elim = False
            is_clinch = False

        status_by_team[rid] = {
            "roster_id": rid,
            "is_eliminated": is_elim,
            "is_math_eliminated": is_math_eliminated,
            "is_clinched": is_clinch,
            "is_math_clinched": is_math_clinched,
            "status_code": code,
            "status_label": label,
            "badge_icon": badge_icon,
            "badge_color": badge_color,
            "max_possible_wins": max_possible_wins,
            "min_possible_wins": min_possible_wins,
            "remaining_games": rem_g,
            "playoff_pct": sim_p_pct if sim_p_pct is not None else 0.0,
        }

    return status_by_team


def run_monte_carlo_simulation(
    league: Dict[str, Any],
    rosters: List[Dict[str, Any]],
    schedule: Dict[int, List[Tuple[int, int]]],
    team_expectations: Dict[int, Dict[str, Any]],
    current_week: int = 1,
    playoff_week_start: int = 15,
    num_simulations: int = DEFAULT_SIMULATIONS,
    custom_initial_records: Optional[Dict[int, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Runs num_simulations iterations of the remaining regular season and playoff bracket.
    Tracks wins, losses, playoff appearances, first-round byes, and championships.
    Supports historical snapshots via custom_initial_records.
    """
    playoff_teams_count = league.get("settings", {}).get("playoff_teams", 6)
    roster_ids = [r["roster_id"] for r in rosters]

    # Deterministic simulation seed derived from hash(league_id) + week * 1000 to eliminate UI rerun jitter
    league_id_str = str(league.get("league_id", 0))
    league_hash = int(hashlib.md5(league_id_str.encode("utf-8")).hexdigest()[:8], 16)
    random.seed(league_hash + int(current_week) * 1000)

    # Initial records (if season has already started or custom historical records provided)
    initial_records = {}
    for r in rosters:
        rid = r["roster_id"]
        if custom_initial_records and rid in custom_initial_records:
            initial_records[rid] = {
                "wins": int(custom_initial_records[rid].get("wins", 0)),
                "losses": int(custom_initial_records[rid].get("losses", 0)),
                "ties": int(custom_initial_records[rid].get("ties", 0)),
                "pf": float(custom_initial_records[rid].get("pf", 0.0)),
            }
        else:
            settings = r.get("settings", {})
            wins = settings.get("wins", 0)
            losses = settings.get("losses", 0)
            ties = settings.get("ties", 0)
            fpts = settings.get("fpts", 0) + (settings.get("fpts_decimal", 0) / 100.0)
            initial_records[rid] = {
                "wins": wins,
                "losses": losses,
                "ties": ties,
                "pf": fpts,
            }

    # Tracking accumulators across all simulations
    sim_wins = {rid: 0 for rid in roster_ids}
    sim_losses = {rid: 0 for rid in roster_ids}
    sim_pf = {rid: 0.0 for rid in roster_ids}
    sim_playoffs = {rid: 0 for rid in roster_ids}
    sim_byes = {rid: 0 for rid in roster_ids}
    sim_champs = {rid: 0 for rid in roster_ids}

    # Determine remaining regular season weeks to simulate
    regular_season_weeks = [
        w for w in range(current_week, playoff_week_start)
        if w in schedule and len(schedule[w]) > 0
    ]

    # If schedule is not yet published in Sleeper, generate a balanced round-robin fallback
    if not regular_season_weeks and current_week < playoff_week_start:
        regular_season_weeks = list(range(current_week, playoff_week_start))
        pairs = []
        for i in range(0, len(roster_ids) - 1, 2):
            if i + 1 < len(roster_ids):
                pairs.append((roster_ids[i], roster_ids[i + 1]))
        fallback_schedule = {w: pairs for w in regular_season_weeks}
    else:
        fallback_schedule = schedule

    for _ in range(num_simulations):
        # Current run standings copy
        cur_records = {
            rid: {
                "wins": initial_records[rid]["wins"],
                "losses": initial_records[rid]["losses"],
                "ties": initial_records[rid]["ties"],
                "pf": initial_records[rid]["pf"],
            }
            for rid in roster_ids
        }

        # 1. Simulate remaining regular season weeks
        for w in regular_season_weeks:
            matchups = fallback_schedule.get(w, [])
            for r1, r2 in matchups:
                if r1 not in team_expectations or r2 not in team_expectations:
                    continue
                mu1 = team_expectations[r1]["expected_pts"]
                sig1 = team_expectations[r1]["std_dev"]
                mu2 = team_expectations[r2]["expected_pts"]
                sig2 = team_expectations[r2]["std_dev"]

                s1, s2 = simulate_single_matchup(mu1, sig1, mu2, sig2)
                cur_records[r1]["pf"] += s1
                cur_records[r2]["pf"] += s2

                if s1 > s2:
                    cur_records[r1]["wins"] += 1
                    cur_records[r2]["losses"] += 1
                elif s2 > s1:
                    cur_records[r2]["wins"] += 1
                    cur_records[r1]["losses"] += 1
                else:
                    cur_records[r1]["ties"] += 1
                    cur_records[r2]["ties"] += 1

        # Accumulate regular season stats
        for rid in roster_ids:
            sim_wins[rid] += cur_records[rid]["wins"]
            sim_losses[rid] += cur_records[rid]["losses"]
            sim_pf[rid] += cur_records[rid]["pf"]

        # 2. Seed Playoff Teams
        # Sleeper standard ranking: Wins desc, PF desc, Ties desc
        ranked_teams = sorted(
            roster_ids,
            key=lambda rid: (
                cur_records[rid]["wins"],
                cur_records[rid]["pf"],
                cur_records[rid]["ties"],
            ),
            reverse=True,
        )

        playoff_seeds = ranked_teams[:playoff_teams_count]
        for s in playoff_seeds:
            sim_playoffs[s] += 1

        # 3. Postseason Bracket Simulation
        champion_id = None
        if playoff_teams_count == 8 and len(playoff_seeds) >= 8:
            # Quarterfinals: 1 vs 8, 4 vs 5, 2 vs 7, 3 vs 6
            q1_w = _simulate_knockout(playoff_seeds[0], playoff_seeds[7], team_expectations)
            q2_w = _simulate_knockout(playoff_seeds[3], playoff_seeds[4], team_expectations)
            q3_w = _simulate_knockout(playoff_seeds[1], playoff_seeds[6], team_expectations)
            q4_w = _simulate_knockout(playoff_seeds[2], playoff_seeds[5], team_expectations)

            # Semifinals: Winner(1v8) vs Winner(4v5), Winner(2v7) vs Winner(3v6)
            semi1_w = _simulate_knockout(q1_w, q2_w, team_expectations)
            semi2_w = _simulate_knockout(q3_w, q4_w, team_expectations)

            # Championship
            champion_id = _simulate_knockout(semi1_w, semi2_w, team_expectations)

        elif playoff_teams_count == 6 and len(playoff_seeds) >= 6:
            # Seeds 1 & 2 get first-round byes
            sim_byes[playoff_seeds[0]] += 1
            sim_byes[playoff_seeds[1]] += 1

            # Quarterfinals: 3 vs 6, 4 vs 5
            q1_w = _simulate_knockout(playoff_seeds[2], playoff_seeds[5], team_expectations)
            q2_w = _simulate_knockout(playoff_seeds[3], playoff_seeds[4], team_expectations)

            # Semifinals: Seed 1 vs lower seed, Seed 2 vs higher seed
            remaining_after_q = sorted([q1_w, q2_w], key=lambda rid: playoff_seeds.index(rid), reverse=True)
            semi1_w = _simulate_knockout(playoff_seeds[0], remaining_after_q[0], team_expectations)
            semi2_w = _simulate_knockout(playoff_seeds[1], remaining_after_q[1], team_expectations)

            # Championship
            champion_id = _simulate_knockout(semi1_w, semi2_w, team_expectations)

        elif playoff_teams_count == 4 and len(playoff_seeds) >= 4:
            # Semifinals: 1 vs 4, 2 vs 3
            semi1_w = _simulate_knockout(playoff_seeds[0], playoff_seeds[3], team_expectations)
            semi2_w = _simulate_knockout(playoff_seeds[1], playoff_seeds[2], team_expectations)

            # Championship
            champion_id = _simulate_knockout(semi1_w, semi2_w, team_expectations)

        elif playoff_teams_count == 2 and len(playoff_seeds) >= 2:
            champion_id = _simulate_knockout(playoff_seeds[0], playoff_seeds[1], team_expectations)
        else:
            # Default to top seed if bracket configuration is non-standard
            champion_id = playoff_seeds[0] if playoff_seeds else ranked_teams[0]

        if champion_id is not None:
            sim_champs[champion_id] += 1

    # Aggregate results
    team_results = {}
    for rid in roster_ids:
        avg_wins = sim_wins[rid] / num_simulations
        avg_losses = sim_losses[rid] / num_simulations
        avg_pf = sim_pf[rid] / num_simulations
        playoff_pct = (sim_playoffs[rid] / num_simulations) * 100.0
        bye_pct = (sim_byes[rid] / num_simulations) * 100.0
        champ_pct = (sim_champs[rid] / num_simulations) * 100.0

        team_results[rid] = {
            "roster_id": rid,
            "avg_wins": round(avg_wins, 1),
            "avg_losses": round(avg_losses, 1),
            "avg_pf": round(avg_pf, 1),
            "playoff_pct": round(playoff_pct, 1),
            "bye_pct": round(bye_pct, 1),
            "champ_pct": round(champ_pct, 1),
            "expected_pts": team_expectations[rid].get("expected_pts", 105.0),
            "bench_depth_pts": team_expectations[rid].get("bench_depth_pts", 0.0),
            "playoff_teams_count": playoff_teams_count,
            "initial_wins": initial_records[rid]["wins"],
            "initial_losses": initial_records[rid]["losses"],
            "initial_ties": initial_records[rid]["ties"],
            "initial_pf": round(initial_records[rid]["pf"], 1),
            "sim_week": current_week,
        }

    # Dynamic Power Ranking Composite Weights based on Season Phase:
    # Early (Weeks 1-3): 45% Starting Expectation + 25% Projected Wins + 15% Playoff Odds + 15% Bench Depth
    # Mid (Weeks 4-8): 30% Starting Expectation + 35% Projected Wins + 25% Playoff Odds + 10% Bench Depth
    # Late (Weeks 9+): 15% Starting Expectation + 40% Projected Wins + 40% Playoff Odds + 5% Bench Depth
    if current_week <= 3:
        w_lineup = 0.45
        w_wins = 0.25
        w_odds = 0.15
        w_bench = 0.15
        phase_label = "Early Season"
    elif current_week <= 8:
        w_lineup = 0.30
        w_wins = 0.35
        w_odds = 0.25
        w_bench = 0.10
        phase_label = "Mid Season"
    else:
        w_lineup = 0.15
        w_wins = 0.40
        w_odds = 0.40
        w_bench = 0.05
        phase_label = "Late Season / Crunch Time"

    formula_str = (
        f"{phase_label} Formula (Week {current_week}): "
        f"{int(w_lineup*100)}% Starters PPG + {int(w_wins*100)}% Proj Wins + "
        f"{int(w_odds*100)}% Playoff Odds + {int(w_bench*100)}% Bench Depth"
    )

    max_pts = max(t["expected_pts"] for t in team_results.values()) if team_results else 100.0
    max_wins = max(t["avg_wins"] for t in team_results.values()) if team_results else 10.0
    max_bench = max(t["bench_depth_pts"] for t in team_results.values()) if team_results else 30.0

    for rid, stats in team_results.items():
        pts_norm = (stats["expected_pts"] / max_pts) * 100.0 if max_pts > 0 else 50.0
        win_norm = (stats["avg_wins"] / max_wins) * 100.0 if max_wins > 0 else 50.0
        bench_norm = (stats["bench_depth_pts"] / max_bench) * 100.0 if max_bench > 0 else 50.0
        playoff_norm = stats["playoff_pct"]

        power_score = (w_lineup * pts_norm) + (w_wins * win_norm) + (w_odds * playoff_norm) + (w_bench * bench_norm)
        stats["power_score"] = round(power_score, 1)
        stats["power_formula"] = formula_str

    # Compute elimination & clinch status metadata
    clinch_data = compute_elimination_and_clinch_status(
        rosters=rosters,
        schedule=fallback_schedule,
        playoff_teams_count=playoff_teams_count,
        playoff_week_start=playoff_week_start,
        current_week=current_week,
        sim_results=team_results,
    )
    for rid, stats in team_results.items():
        c_info = clinch_data.get(rid, {})
        stats["is_eliminated"] = c_info.get("is_eliminated", False)
        stats["is_math_eliminated"] = c_info.get("is_math_eliminated", False)
        stats["is_clinched"] = c_info.get("is_clinched", False)
        stats["is_math_clinched"] = c_info.get("is_math_clinched", False)
        stats["status_code"] = c_info.get("status_code", "HUNT")
        stats["status_label"] = c_info.get("status_label", "In The Hunt")
        stats["badge_icon"] = c_info.get("badge_icon", "🎯")
        stats["badge_color"] = c_info.get("badge_color", "#3b82f6")
        stats["remaining_games"] = c_info.get("remaining_games", 0)
        stats["max_possible_wins"] = c_info.get("max_possible_wins", stats["initial_wins"])

    return team_results


def _simulate_knockout(rid1: int, rid2: int, team_expectations: Dict[int, Dict[str, Any]]) -> int:
    """
    Simulates a single playoff knockout game between two teams.
    Returns the winning roster_id.
    """
    mu1 = team_expectations[rid1]["expected_pts"]
    sig1 = team_expectations[rid1]["std_dev"]
    mu2 = team_expectations[rid2]["expected_pts"]
    sig2 = team_expectations[rid2]["std_dev"]

    s1, s2 = simulate_single_matchup(mu1, sig1, mu2, sig2)
    if s1 == s2:
        return rid1 if mu1 >= mu2 else rid2
    return rid1 if s1 > s2 else rid2


def compute_dynasty_power_rankings(
    team_profiles: List[Dict[str, Any]],
    weight_starters: float = 0.50,
    weight_bench: float = 0.30,
    weight_picks: float = 0.20,
) -> Dict[int, Dict[str, Any]]:
    """
    Computes Dynasty Power Rankings following KeepTradeCut and Dynasty Daddy industry standards.
    Consensus market values (FantasyCalc, KTC, DynastyProcess) already price in player age,
    longevity, and future trajectory.

    Components:
    - Starters Value (50%): Premier difference-makers who win weekly matchups.
    - Bench Depth (30%): Roster depth, young upside stashes, and injury resilience.
    - Draft Capital (20%): Future draft pick equity normalized to league size.
    """
    dynasty_results = {}
    for prof in team_profiles:
        rid = prof["roster_id"]
        starters_val = sum(a.get("market_value", 0.0) for a in prof.get("starter_assets", []))
        bench_val = sum(a.get("market_value", 0.0) for a in prof.get("bench_assets", []))
        picks_val = sum(pk.get("market_value", 0.0) for pk in prof.get("pick_assets", []))
        total_val = starters_val + bench_val + picks_val

        dynasty_results[rid] = {
            "roster_id": rid,
            "manager_name": prof.get("manager_name", f"Team {rid}"),
            "status": prof.get("status", "Unknown"),
            "category": prof.get("category", "neutral"),
            "total_val": round(total_val, 1),
            "starters_val": round(starters_val, 1),
            "bench_val": round(bench_val, 1),
            "picks_val": round(picks_val, 1),
        }

    max_starters = max(t["starters_val"] for t in dynasty_results.values()) if dynasty_results else 1.0
    max_bench = max(t["bench_val"] for t in dynasty_results.values()) if dynasty_results else 1.0
    max_picks = max(t["picks_val"] for t in dynasty_results.values()) if dynasty_results else 1.0

    for rid, t in dynasty_results.items():
        norm_starters = (t["starters_val"] / max_starters) * 100.0 if max_starters > 0 else 50.0
        norm_bench = (t["bench_val"] / max_bench) * 100.0 if max_bench > 0 else 50.0
        norm_picks = (t["picks_val"] / max_picks) * 100.0 if max_picks > 0 else 50.0

        dynasty_score = (
            (weight_starters * norm_starters)
            + (weight_bench * norm_bench)
            + (weight_picks * norm_picks)
        )
        t["dynasty_score"] = round(dynasty_score, 1)

    return dynasty_results


def compute_ros_power_rankings(
    team_profiles: List[Dict[str, Any]],
    weight_starters: float = 0.70,
    weight_bench: float = 0.30,
) -> Dict[int, Dict[str, Any]]:
    """
    Computes Rest-of-Season (ROS) Asset Power Rankings based on 3-source consensus redraft valuations:
    - 70% Starters Value: Optimal starting lineup market value for single-season impact.
    - 30% Bench Depth: Active bench market value for injury resilience and bye-week protection.
    (Draft capital is 0% as future picks do not generate points in the current season).
    """
    ros_results = {}
    for prof in team_profiles:
        rid = prof["roster_id"]
        starters_val = sum(a.get("market_value", 0.0) for a in prof.get("starter_assets", []))
        bench_val = sum(a.get("market_value", 0.0) for a in prof.get("bench_assets", []))
        total_val = starters_val + bench_val

        ros_results[rid] = {
            "roster_id": rid,
            "manager_name": prof.get("manager_name", f"Team {rid}"),
            "status": prof.get("status", "Active"),
            "category": prof.get("category", "neutral"),
            "total_val": round(total_val, 1),
            "starters_val": round(starters_val, 1),
            "bench_val": round(bench_val, 1),
        }

    max_starters = max((t["starters_val"] for t in ros_results.values()), default=1.0) or 1.0
    max_bench = max((t["bench_val"] for t in ros_results.values()), default=1.0) or 1.0

    for rid, t in ros_results.items():
        norm_starters = (t["starters_val"] / max_starters) * 100.0 if max_starters > 0 else 50.0
        norm_bench = (t["bench_val"] / max_bench) * 100.0 if max_bench > 0 else 50.0

        ros_score = (
            (weight_starters * norm_starters)
            + (weight_bench * norm_bench)
        )
        t["ros_score"] = round(ros_score, 1)

    return ros_results


def format_power_rankings_table(
    sim_results: Dict[int, Dict[str, Any]],
    user_roster_id: int,
    user_map: Dict[str, str],
    rosters: List[Dict[str, Any]],
    team_profiles: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Generates an ASCII Season Power Rankings & Playoff Odds leaderboard.
    """
    owner_id_by_roster = {r["roster_id"]: r["owner_id"] for r in rosters}
    ranked = sorted(sim_results.values(), key=lambda t: t["power_score"], reverse=True)

    sample_item = next(iter(sim_results.values())) if sim_results else {}
    playoff_teams_count = sample_item.get("playoff_teams_count", 6)

    lines = []
    sample_formula = sample_item.get("power_formula", "")
    lines.append(f"  ⚡ 2026 Season Power Rankings & 1,000-Run Playoff Odds ({playoff_teams_count}-Team Playoff):")
    if sample_formula:
        lines.append(f"  📊 {sample_formula}")
    lines.append("  " + "-" * 102)
    header = f"  {'Rank':<5} {'Manager / Team':<26} {'Playoff Status':<16} {'Proj W-L':<11} {'Exp Pts/Wk':<12} {'Playoff %':<11} {'Champ %':<9} {'Season Score'}"
    lines.append(header)
    lines.append("  " + "-" * 102)

    for rank, t in enumerate(ranked, 1):
        rid = t["roster_id"]
        oid = owner_id_by_roster.get(rid, "")
        mgr_name = user_map.get(oid, f"Team {rid}")
        is_user = (rid == user_roster_id)

        if len(mgr_name) > 24:
            mgr_display = mgr_name[:21] + "..."
        else:
            mgr_display = mgr_name

        marker = "👉 " if is_user else "   "
        prefix = f"{marker}{rank:<2}"
        status_disp = f"{t.get('badge_icon', '')} {t.get('status_label', '')}"[:15]
        w_l_str = f"{t['avg_wins']:.1f} - {t['avg_losses']:.1f}"
        pts_str = f"{t['expected_pts']:.1f} pts"
        po_str = f"{t['playoff_pct']:.1f}%"
        champ_str = f"{t['champ_pct']:.1f}%"
        score_str = f"{t['power_score']:.1f}"

        row = f"  {prefix} {mgr_display:<26} {status_disp:<16} {w_l_str:<11} {pts_str:<12} {po_str:<11} {champ_str:<9} {score_str}"
        lines.append(row)

    lines.append("  " + "-" * 102)
    return "\n".join(lines)


def format_dynasty_power_rankings_table(
    dynasty_results: Dict[int, Dict[str, Any]],
    user_roster_id: int,
) -> str:
    """
    Generates an ASCII Dynasty Power Rankings leaderboard (Long-Term Franchise Strength).
    """
    ranked = sorted(dynasty_results.values(), key=lambda t: t["dynasty_score"], reverse=True)

    lines = []
    lines.append("  🏛️ Dynasty Power Rankings (Consensus Market Value: Starters 50% | Bench 30% | Picks 20%):")
    lines.append("  " + "-" * 98)
    header = f"  {'Rank':<5} {'Manager / Team':<28} {'Total Dynasty':<14} {'Starters (50%)':<16} {'Bench (30%)':<14} {'Picks (20%)':<14} {'Dynasty Score'}"
    lines.append(header)
    lines.append("  " + "-" * 98)

    for rank, t in enumerate(ranked, 1):
        rid = t["roster_id"]
        mgr_name = t["manager_name"]
        is_user = (rid == user_roster_id)

        if len(mgr_name) > 26:
            mgr_display = mgr_name[:23] + "..."
        else:
            mgr_display = mgr_name

        marker = "👉 " if is_user else "   "
        prefix = f"{marker}{rank:<2}"
        tot_str = f"{t['total_val']:,.0f}"
        st_str = f"{t['starters_val']:,.0f}"
        bn_str = f"{t['bench_val']:,.0f}"
        pk_str = f"{t['picks_val']:,.0f}"
        score_str = f"{t['dynasty_score']:.1f}"

        row = f"  {prefix} {mgr_display:<28} {tot_str:<14} {st_str:<16} {bn_str:<14} {pk_str:<14} {score_str}"
        lines.append(row)

    lines.append("  " + "-" * 98)
    return "\n".join(lines)


def run_historical_simulation_snapshot(
    league: Dict[str, Any],
    rosters: List[Dict[str, Any]],
    schedule: Dict[int, List[Tuple[int, int]]],
    team_expectations: Dict[int, Dict[str, Any]],
    snapshot_week: int = 1,
    current_week: int = 1,
    playoff_week_start: int = 15,
    num_simulations: int = DEFAULT_SIMULATIONS,
) -> Dict[str, Any]:
    """
    Simulates the season as it was projected at the start of `snapshot_week`.
    Reconstructs actual win/loss records through week `snapshot_week - 1`.
    """
    from src.sleeper_api import compute_historical_standings

    if snapshot_week <= 1:
        custom_records = {r["roster_id"]: {"wins": 0, "losses": 0, "ties": 0, "pf": 0.0} for r in rosters}
    elif snapshot_week >= current_week and current_week > 1:
        custom_records = None
    else:
        league_id = str(league.get("league_id", ""))
        custom_records = compute_historical_standings(league_id, rosters, through_week=snapshot_week - 1)

    return run_monte_carlo_simulation(
        league=league,
        rosters=rosters,
        schedule=schedule,
        team_expectations=team_expectations,
        current_week=snapshot_week,
        playoff_week_start=playoff_week_start,
        num_simulations=num_simulations,
        custom_initial_records=custom_records,
    )


def compute_weekly_evolution_history(
    league: Dict[str, Any],
    rosters: List[Dict[str, Any]],
    schedule: Dict[int, List[Tuple[int, int]]],
    team_expectations: Dict[int, Dict[str, Any]],
    current_week: int = 1,
    playoff_week_start: int = 15,
    num_simulations: int = 500,
) -> Dict[int, Dict[str, Any]]:
    """
    Computes simulation snapshots for all weeks from 1 to current_week.
    Returns dict mapping week_num -> simulation results dict.
    """
    evolution = {}
    for w in range(1, max(1, current_week) + 1):
        evolution[w] = run_historical_simulation_snapshot(
            league=league,
            rosters=rosters,
            schedule=schedule,
            team_expectations=team_expectations,
            snapshot_week=w,
            current_week=current_week,
            playoff_week_start=playoff_week_start,
            num_simulations=num_simulations,
        )
    return evolution

