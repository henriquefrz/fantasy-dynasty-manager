"""
start_sit.py

In-Season Weekly Start/Sit Assistant for Fantasy Dynasty Manager.
Provides:
- Exact weekly projected points tailored to league-specific scoring settings (PPR, TEP, 4/6pt Pass TD).
- Optimal weekly starting lineup simulation maximizing weekly fantasy points.
- Active Sleeper lineup auditing: comparing current starters against optimal projections to detect sub-optimal starts.
- Injury risk alerts for active starters (Questionable, Doubtful, Out, IR).
- Free agent weekly streaming scanner with the "Josh Allen Bye Week" Stud Protection Guardrail.
"""

from typing import Dict, List, Tuple, Any, Optional, Set


STREAMING_POSITIONS = {"DEF", "K", "TE", "QB"}
PROTECTED_MARKET_VALUE_THRESHOLD = 1800.0
PROTECTED_REDRAFT_ECR_THRESHOLD = 60.0


def calculate_weekly_projected_points(
    player_id: str,
    raw_proj: Optional[Dict[str, Any]],
    scoring_settings: Dict[str, Any],
    player_obj: Optional[Dict[str, Any]] = None,
) -> float:
    """
    Calculates exact projected fantasy points for a player in a given week
    based on the league's scoring settings (PPR, pass TD weight, TEP bonus).
    """
    if not raw_proj:
        return 0.0

    pos = (player_obj.get("position") if player_obj else None) or ""

    # Check if raw_proj already has pre-computed points
    rec_val = float(scoring_settings.get("rec", 1.0))
    te_bonus = float(scoring_settings.get("bonus_rec_te", 0.0) or scoring_settings.get("te_bonus", 0.0))
    pass_td_val = float(scoring_settings.get("pass_td", 4.0))

    # Check if this player is an IDP player or has IDP stats
    is_idp = pos in ("DB", "LB", "DL", "IDP", "IDP_FLEX", "SS", "FS", "CB", "DE", "DT") or any(k.startswith("idp_") for k in raw_proj.keys())
    if is_idp:
        idp_pts = 0.0
        has_idp_stats = False
        for k, v in raw_proj.items():
            if k in scoring_settings:
                try:
                    mult = float(scoring_settings[k])
                    val = float(v)
                    idp_pts += val * mult
                    has_idp_stats = True
                except (ValueError, TypeError):
                    pass
        if has_idp_stats:
            return round(max(0.0, idp_pts), 2)
        pts_idp = raw_proj.get("pts_idp") or raw_proj.get("pts_std") or raw_proj.get("pts_ppr") or 0.0
        return round(float(pts_idp), 2)

    # Defensive or Kicker scoring
    if pos in ("DEF", "K") or player_id in ("MIN", "SF", "BAL", "DAL", "PHI", "BUF", "KC", "NYJ"):
        pts = raw_proj.get("pts_std") or raw_proj.get("pts_ppr") or 0.0
        return round(float(pts), 2)

    # Detailed offensive stat calculation when available
    stats = raw_proj
    has_stat_breakdown = any(k in stats for k in ("pass_yd", "rush_yd", "rec_yd", "pass_td"))

    if has_stat_breakdown:
        pass_yd = float(stats.get("pass_yd", 0.0))
        pass_td = float(stats.get("pass_td", 0.0))
        pass_int = float(stats.get("pass_int", 0.0))

        rush_yd = float(stats.get("rush_yd", 0.0))
        rush_td = float(stats.get("rush_td", 0.0))

        rec = float(stats.get("rec", 0.0))
        rec_yd = float(stats.get("rec_yd", 0.0))
        rec_td = float(stats.get("rec_td", 0.0))

        fum_lost = float(stats.get("fum_lost", 0.0))
        two_pt = float(stats.get("pass_2pt", 0.0) + stats.get("rush_2pt", 0.0) + stats.get("rec_2pt", 0.0))

        # League scoring multipliers
        p_yd_mult = float(scoring_settings.get("pass_yd", 0.04))
        r_yd_mult = float(scoring_settings.get("rush_yd", 0.1))
        rec_yd_mult = float(scoring_settings.get("rec_yd", 0.1))
        r_td_mult = float(scoring_settings.get("rush_td", 6.0))
        rec_td_mult = float(scoring_settings.get("rec_td", 6.0))
        pass_int_mult = float(scoring_settings.get("pass_int", -2.0))
        fum_mult = float(scoring_settings.get("fum_lost", -2.0))

        total_pts = (
            pass_yd * p_yd_mult
            + pass_td * pass_td_val
            + pass_int * pass_int_mult
            + rush_yd * r_yd_mult
            + rush_td * r_td_mult
            + rec * rec_val
            + rec_yd * rec_yd_mult
            + rec_td * rec_td_mult
            + fum_lost * fum_mult
            + two_pt * 2.0
        )

        if pos == "TE" and te_bonus > 0:
            total_pts += rec * te_bonus

        return round(max(0.0, total_pts), 2)

    # Fallback to precomputed points
    if rec_val >= 0.75:
        base = raw_proj.get("pts_ppr")
    elif rec_val >= 0.25:
        base = raw_proj.get("pts_half_ppr")
    else:
        base = raw_proj.get("pts_std")

    if base is None:
        base = raw_proj.get("pts_ppr") or raw_proj.get("pts_half_ppr") or raw_proj.get("pts_std") or 0.0

    total = float(base)
    if pos == "TE" and te_bonus > 0 and raw_proj.get("rec"):
        total += float(raw_proj["rec"]) * te_bonus

    return round(max(0.0, total), 2)


def simulate_optimal_weekly_lineup(
    roster_players: List[Dict[str, Any]],
    projections_lookup: Dict[str, float],
    roster_positions: List[str],
) -> Tuple[List[Tuple[Dict[str, Any], float, str]], List[Tuple[Dict[str, Any], float]]]:
    """
    Selects the starting lineup that maximizes total projected points for the current week
    subject to positional constraints (QB, RB, WR, TE, Flex, Superflex, K, DEF).
    """
    active_slots = [pos for pos in roster_positions if pos not in ("BN", "IR", "TAXI")]

    # Attach projected points to player objects
    available = []
    for p in roster_players:
        pid = p.get("player_id")
        raw_proj = projections_lookup.get(pid, 0.0)
        if isinstance(raw_proj, dict):
            proj_pts = float(raw_proj.get("consensus_ppg", 0.0) or 0.0)
        else:
            proj_pts = float(raw_proj or 0.0)
        available.append((p, proj_pts))

    # Sort descending by projected points
    available.sort(key=lambda t: -t[1])

    starters: List[Tuple[Dict[str, Any], float, str]] = []
    used_pids: Set[str] = set()

    # Pass 1: Fill primary dedicated slots (QB, RB, WR, TE, K, DEF)
    for slot in active_slots:
        if slot in ("FLEX", "SUPER_FLEX", "WRRB_FLEX", "REC_FLEX"):
            continue

        best_cand = None
        for p, pts in available:
            pid = p.get("player_id")
            if pid in used_pids:
                continue
            if p.get("position") == slot:
                best_cand = (p, pts, slot)
                break

        if best_cand:
            starters.append(best_cand)
            used_pids.add(best_cand[0].get("player_id"))

    # Pass 2: Fill flex slots
    flex_eligible = {
        "FLEX": {"RB", "WR", "TE"},
        "SUPER_FLEX": {"QB", "RB", "WR", "TE"},
        "WRRB_FLEX": {"RB", "WR"},
        "REC_FLEX": {"WR", "TE"},
    }

    for slot in active_slots:
        if slot not in flex_eligible:
            continue

        allowed_positions = flex_eligible[slot]
        best_cand = None
        for p, pts in available:
            pid = p.get("player_id")
            if pid in used_pids:
                continue
            if p.get("position") in allowed_positions:
                best_cand = (p, pts, slot)
                break

        if best_cand:
            starters.append(best_cand)
            used_pids.add(best_cand[0].get("player_id"))

    # Remaining players become the bench
    bench: List[Tuple[Dict[str, Any], float]] = [
        (p, pts) for p, pts in available if p.get("player_id") not in used_pids
    ]

    return starters, bench


def audit_weekly_lineup(
    user_roster: Dict[str, Any],
    roster_players: List[Dict[str, Any]],
    projections_lookup: Dict[str, float],
    roster_positions: List[str],
    player_db: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Audits the manager's active Sleeper starting lineup against the optimal projected lineup.
    Detects sub-optimal starts, computes projected point differentials, and flags injury risks.
    """
    active_starter_pids = user_roster.get("starters") or []
    active_slots = [pos for pos in roster_positions if pos not in ("BN", "IR", "TAXI")]

    # Simulate optimal lineup
    optimal_starters, bench_players = simulate_optimal_weekly_lineup(
        roster_players, projections_lookup, roster_positions
    )

    optimal_starter_pids = {p.get("player_id") for p, _, _ in optimal_starters}

    # Map current active starters and their projections
    active_starter_objs = []
    active_points_total = 0.0

    for idx, pid in enumerate(active_starter_pids):
        if idx >= len(active_slots):
            break
        slot = active_slots[idx]
        p_obj = player_db.get(pid, {"player_id": pid, "full_name": pid, "position": slot})
        raw_val = projections_lookup.get(pid, 0.0)
        pts = float(raw_val.get("consensus_ppg", 0.0) if isinstance(raw_val, dict) else (raw_val or 0.0))
        active_starter_objs.append((p_obj, pts, slot))
        active_points_total += pts

    optimal_points_total = sum(pts for _, pts, _ in optimal_starters)
    points_differential = round(optimal_points_total - active_points_total, 2)

    # Detect Sub-optimal Start/Sit moves
    start_sit_swaps = []
    bench_pids = {p.get("player_id") for p, _ in bench_players}

    for opt_p, opt_pts, slot in optimal_starters:
        opt_pid = opt_p.get("player_id")
        # If this optimal starter is currently sitting on the manager's bench
        if opt_pid not in active_starter_pids:
            # Find which active starter in a compatible slot has fewer projected points
            worst_active = None
            min_pts = opt_pts

            for act_p, act_pts, act_slot in active_starter_objs:
                act_pid = act_p.get("player_id")
                if act_pid in optimal_starter_pids:
                    continue  # This starter is already part of the optimal lineup

                # Compatibility check
                pos = opt_p.get("position")
                is_compatible = False
                if act_slot == pos:
                    is_compatible = True
                elif act_slot == "FLEX" and pos in ("RB", "WR", "TE"):
                    is_compatible = True
                elif act_slot == "SUPER_FLEX" and pos in ("QB", "RB", "WR", "TE"):
                    is_compatible = True

                if is_compatible and act_pts < min_pts:
                    min_pts = act_pts
                    worst_active = (act_p, act_pts, act_slot)

            if worst_active:
                gain = round(opt_pts - worst_active[1], 2)
                if gain >= 0.5:
                    start_sit_swaps.append({
                        "start_player": opt_p,
                        "start_proj": opt_pts,
                        "sit_player": worst_active[0],
                        "sit_proj": worst_active[1],
                        "slot": slot,
                        "gain": gain,
                    })

    # Detect Injury Alerts among active starters
    injury_alerts = []
    for act_p, act_pts, slot in active_starter_objs:
        status = act_p.get("injury_status")
        if status in ("Questionable", "Doubtful", "Out", "IR", "PUP", "Sus"):
            # Find best healthy bench pivot
            pos = act_p.get("position")
            pivots = [
                (bp, bpts) for bp, bpts in bench_players
                if (bp.get("position") == pos or (slot in ("FLEX", "SUPER_FLEX") and bp.get("position") in ("RB", "WR", "TE")))
                and bp.get("injury_status") not in ("Questionable", "Doubtful", "Out", "IR")
            ]
            best_pivot = pivots[0] if pivots else None

            injury_alerts.append({
                "starter": act_p,
                "status": status,
                "starter_proj": act_pts,
                "slot": slot,
                "pivot": best_pivot,
            })

    return {
        "active_starters": active_starter_objs,
        "optimal_starters": optimal_starters,
        "active_points_total": round(active_points_total, 2),
        "optimal_points_total": round(optimal_points_total, 2),
        "points_differential": points_differential,
        "start_sit_swaps": start_sit_swaps,
        "injury_alerts": injury_alerts,
    }


def find_streaming_recommendations(
    user_roster: Dict[str, Any],
    roster_players: List[Dict[str, Any]],
    free_agents: List[Dict[str, Any]],
    projections_lookup: Dict[str, float],
    roster_positions: List[str],
    primary_lookup: Dict[str, Any],
    top_n: int = 3,
) -> List[Dict[str, Any]]:
    """
    Identifies high-upside Free Agent streaming additions for the upcoming week.
    Strictly enforces the 'Josh Allen Bye Week' Stud Protection Rule:
    - Never suggests dropping a player based on a single-week 0.0 projection.
    - Protected starters and core assets are immune from being cut.
    - Droppable candidates must be low season-long market value bench fliers or existing streamers.
    """
    active_starter_pids = set(user_roster.get("starters") or [])
    reserve_pids = set(user_roster.get("reserve") or [])
    taxi_pids = set(user_roster.get("taxi") or [])

    # Map current starters by position
    starters_by_pos = {}
    for p in roster_players:
        pid = p.get("player_id")
        if pid in active_starter_pids:
            starters_by_pos.setdefault(p.get("position"), []).append(p)

    # 1. Identify droppable bench candidates (The Stud Protection Guardrail)
    droppable_candidates = []
    for p in roster_players:
        pid = p.get("player_id")
        # Cannot drop active starters, IR, or Taxi
        if pid in active_starter_pids or pid in reserve_pids or pid in taxi_pids:
            continue

        pos = p.get("position")
        market_val = primary_lookup.get(pid, {}).get("market_value", 0.0)
        redraft_ecr = primary_lookup.get(pid, {}).get("rank_ecr", 999.0)

        # STUD PROTECTION: Core assets and high-value depth are IMMUNE from streaming drops
        if market_val >= PROTECTED_MARKET_VALUE_THRESHOLD or redraft_ecr <= PROTECTED_REDRAFT_ECR_THRESHOLD:
            continue

        droppable_candidates.append({
            "player": p,
            "market_val": market_val,
            "position": pos,
        })

    # Sort droppable candidates ascending by market value (drop the least valuable player)
    droppable_candidates.sort(key=lambda c: c["market_val"])

    if not droppable_candidates:
        return []

    streaming_opps = []

    # 2. Scan Free Agents across streaming positions
    for fa in free_agents:
        pos = fa.get("position")
        if pos not in STREAMING_POSITIONS:
            continue

        fa_pid = fa.get("player_id")
        fa_proj = projections_lookup.get(fa_pid, 0.0)

        if fa_proj <= 5.0:
            continue

        # Find current starter at this position
        current_starters = starters_by_pos.get(pos, [])
        if not current_starters:
            continue

        # Lowest projected starter at this position
        worst_starter = min(current_starters, key=lambda p: projections_lookup.get(p.get("player_id"), 0.0))
        starter_proj = projections_lookup.get(worst_starter.get("player_id"), 0.0)

        gain = round(fa_proj - starter_proj, 2)
        if gain >= 1.5:  # Conviction threshold: at least +1.5 projected points
            # Select appropriate drop candidate
            # If streaming K or DEF, prefer dropping the existing K or DEF
            drop_cand = None
            if pos in ("K", "DEF"):
                same_pos_drop = next((c for c in droppable_candidates if c["position"] == pos), None)
                if same_pos_drop:
                    drop_cand = same_pos_drop
                else:
                    # Also check if the worst starter at K/DEF is droppable
                    drop_cand = {"player": worst_starter, "market_val": 0.0, "position": pos}
            else:
                drop_cand = droppable_candidates[0]

            streaming_opps.append({
                "stream_player": fa,
                "stream_proj": fa_proj,
                "current_starter": worst_starter,
                "starter_proj": starter_proj,
                "drop_player": drop_cand["player"],
                "drop_market_val": drop_cand["market_val"],
                "position": pos,
                "projected_gain": gain,
            })

    # Sort descending by projected point gain
    streaming_opps.sort(key=lambda o: -o["projected_gain"])

    return streaming_opps[:top_n]
