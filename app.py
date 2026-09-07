"""
Fantasy Analytics — Executive Multi-League Management & Intelligence Platform
Built with Streamlit for desktop (MacBook) and mobile (iPhone) use.
Provides:
  - Executive Front Page Portal (Multi-League Overview & Portfolio Capital)
  - Tab 0: 🏠 Franchise Hub (Executive Overview, Full Roster Breakdown, Asset Equity)
  - Tab 1: ⚡ Matchups & Start/Sit (Active vs Optimal, Injury Alerts, FA Streaming)
  - Tab 2: 🌊 Add/Drops & Waivers (IR Slots, Taxi Swaps, Starter Displacements, Handcuffs)
  - Tab 3: 📊 Power Rankings & Playoff Odds (1,000-Run Monte Carlo + Dynasty 50/30/20)
  - Tab 4: 🤝 Trade Center & Targeted Finder (Targeted Buy/Sell + League Scanner)
  - Tab 5: 🔍 Market Rankings & Database (Complete All-Player Valuation & Rankings)
  - Tab 6: 🌐 Multi-League Portfolio & Player Exposure (Cross-League Shares & Risk)
"""

import copy
import os
import sys
import importlib
from datetime import datetime
import pandas as pd
import streamlit as st

# Ensure project root is at the head of sys.path for Cloud environments
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.sleeper_api import (
    get_user,
    get_user_leagues,
    get_league_rosters,
    get_user_roster,
    get_players,
    get_roster_players,
    get_free_agents,
    get_traded_picks,
    get_league_users,
    get_nfl_state,
    get_weekly_projections,
    get_league_schedule,
    get_league_matchups,
    get_league_history,
)
from src.league_classifier import classify_league, get_starter_counts
from src.market_data import (
    get_fp_rankings_raw,
    get_player_ids_raw,
    build_positional_lookup,
    get_values_players_raw,
    get_values_picks_raw,
    get_ktc_data_raw,
    get_fantasycalc_data_raw,
    build_picks_sources_bundle,
    compute_picks_lookup_from_bundle,
    enrich_lookup_with_consensus_values,
    enrich_lookup_with_redraft_values,
    apply_valuation_mode,
    apply_te_premium,
    get_market_data_freshness,
    VALUATION_MODES,
)

# Robust import with hot-reload for Streamlit Cloud daemon processes
try:
    import src.matching
    importlib.reload(src.matching)
    from src.matching import match_players_by_sleeper_id, get_player_avatar_url, get_team_logo_url
except Exception:
    try:
        from src.matching import match_players_by_sleeper_id
    except Exception:
        def match_players_by_sleeper_id(sleeper_players, dynasty_lookup):
            matched, unmatched = [], []
            for player in sleeper_players:
                pid = player.get("player_id")
                ranking = dynasty_lookup.get(pid)
                if ranking:
                    matched.append((player, ranking))
                else:
                    unmatched.append(player)
            return matched, unmatched

    def get_player_avatar_url(player_id, position=None, team=None):
        if not player_id:
            return ""
        pos_upper = str(position or "").upper()
        pid_str = str(player_id).strip()
        if pos_upper in ("DEF", "DST") or not pid_str.isdigit():
            team_code = (team or pid_str).lower()
            return f"https://sleepercdn.com/images/team_logos/nfl/{team_code}.png"
        return f"https://sleepercdn.com/content/nfl/players/thumb/{pid_str}.jpg"

    def get_team_logo_url(team_abbr):
        if not team_abbr:
            return ""
        code = str(team_abbr).strip().lower()
        return f"https://sleepercdn.com/images/team_logos/nfl/{code}.png"

try:
    import src.team_strength
    importlib.reload(src.team_strength)
except Exception:
    pass
from src.analysis_engine import (
    build_intelligent_waiver_suggestions,
    enrich_with_alt_ranking,
)
from src.start_sit import (
    calculate_weekly_projected_points,
    simulate_optimal_weekly_lineup,
    audit_weekly_lineup,
    find_streaming_recommendations,
)
from src.trade_engine import (
    analyze_team_profile,
    generate_trade_suggestions,
)
from src.team_strength import (
    rank_teams_in_league,
    get_strength_tier,
    get_current_strength_tier,
    classify_dynasty_team,
    classify_redraft_team,
    percentile_score,
    score_to_tier,
)
from src.draft_picks import (
    build_picks_ownership,
    get_picks_for_roster,
    get_picks_capital_value,
    format_picks_summary,
)
from src.playoff_simulator import (
    compute_team_lineup_expectation,
    run_monte_carlo_simulation,
    compute_dynasty_power_rankings,
)
from src.trade_finder import (
    resolve_asset_from_query,
    find_targeted_buy_trades,
    find_targeted_sell_trades,
)

DEFAULT_USERNAME = "henriquefrz"
ALLOWED_USERS = ["henriquefrz", "LucasFrazao"]

# -----------------------------------------------------------------------------
# Streamlit Page Setup & Custom Mobile-Responsive CSS
# -----------------------------------------------------------------------------
LOGO_PATH = "assets/logo.jpg"
PAGE_ICON = LOGO_PATH if os.path.exists(LOGO_PATH) else "🏈"

st.set_page_config(
    page_title="Fantasy Analytics",
    page_icon=PAGE_ICON,
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    /* Complete Sidebar Elimination */
    [data-testid="stSidebar"],
    [data-testid="collapsedControl"],
    section[data-testid="stSidebar"],
    button[data-testid="baseButton-headerNoPadding"] {
        display: none !important;
    }

    /* Fixed Streamlit Header Styling */
    header[data-testid="stHeader"] {
        background: rgba(11, 15, 23, 0.95) !important;
        backdrop-filter: blur(10px) !important;
        border-bottom: 1px solid rgba(255, 255, 255, 0.06) !important;
        z-index: 99 !important;
    }

    /* Global Container & Clean Layout */
    .block-container {
        padding-top: 5.5rem !important;
        padding-bottom: 3rem !important;
        padding-left: 1.25rem !important;
        padding-right: 1.25rem !important;
        max-width: 1400px;
    }
    @media (max-width: 768px) {
        .block-container {
            padding-top: 5.5rem !important;
        }
    }

    /* Positional Micro-Badges */
    .badge-pos {
        display: inline-block;
        padding: 3px 8px;
        border-radius: 4px;
        font-weight: 700;
        font-size: 0.75rem;
        color: #fff;
        margin-right: 4px;
        letter-spacing: 0.04em;
        white-space: nowrap !important;
    }
    .badge-qb { background-color: #ef4444; }
    .badge-rb { background-color: #06b6d4; }
    .badge-wr { background-color: #3b82f6; }
    .badge-te { background-color: #f59e0b; }
    .badge-k  { background-color: #8b5cf6; }
    .badge-def{ background-color: #64748b; }
    .badge-pick{ background-color: #10b981; }

    /* Top Bar Brand Home Button */
    .st-key-btn_brand_home button {
        background: linear-gradient(135deg, rgba(14, 165, 233, 0.15) 0%, rgba(15, 23, 42, 0.7) 100%) !important;
        border: 1px solid rgba(56, 189, 248, 0.35) !important;
        border-radius: 8px !important;
        color: #f8fafc !important;
        font-weight: 800 !important;
        font-size: 1.05rem !important;
        letter-spacing: -0.01em !important;
        padding: 6px 14px !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25) !important;
        transition: all 0.2s ease !important;
    }
    .st-key-btn_brand_home button:hover {
        background: rgba(56, 189, 248, 0.2) !important;
        border-color: rgba(56, 189, 248, 0.75) !important;
        box-shadow: 0 0 14px rgba(56, 189, 248, 0.3) !important;
        color: #ffffff !important;
    }

    /* Typographic Status Capsules (Option 2 - Clean & Professional) */
    .status-capsule {
        display: inline-block;
        padding: 3px 8px;
        border-radius: 4px;
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.05em;
        text-transform: uppercase;
    }
    .status-contender {
        background: rgba(14, 165, 233, 0.12);
        color: #38bdf8;
        border: 1px solid rgba(56, 189, 248, 0.35);
    }
    .status-bubble {
        background: rgba(245, 158, 11, 0.12);
        color: #fbbf24;
        border: 1px solid rgba(251, 191, 36, 0.35);
    }
    .status-rebuild {
        background: rgba(16, 185, 129, 0.12);
        color: #34d399;
        border: 1px solid rgba(52, 211, 153, 0.35);
    }

    /* Refined Linear Dark Cards */
    .card-container {
        border-radius: 10px;
        padding: 16px 18px;
        margin-bottom: 14px;
        border: 1px solid rgba(255, 255, 255, 0.08);
        background: #111827;
        box-shadow: 0 4px 14px -2px rgba(0, 0, 0, 0.35);
        transition: border-color 0.15s ease;
    }
    .card-container:hover {
        border-color: rgba(255, 255, 255, 0.16);
    }
    .card-highlight {
        border-left: 3px solid #38bdf8;
    }
    .card-alert {
        border-left: 3px solid #f59e0b;
        background: linear-gradient(135deg, rgba(245, 158, 11, 0.08) 0%, #111827 100%);
    }
    .card-success {
        border-left: 3px solid #10b981;
        background: linear-gradient(135deg, rgba(16, 185, 129, 0.08) 0%, #111827 100%);
    }

    /* Streamlit Native Metric Cards */
    div[data-testid="stMetric"] {
        background: #111827;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 10px;
        padding: 12px 16px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.45rem !important;
        font-weight: 700 !important;
        letter-spacing: -0.01em;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.78rem !important;
        font-weight: 600 !important;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        color: #94a3b8 !important;
    }

    /* Modern Tabs Bar */
    div[data-baseweb="tab-list"] {
        gap: 6px;
        overflow-x: auto;
        flex-wrap: nowrap !important;
        scrollbar-width: thin;
        -webkit-overflow-scrolling: touch;
        padding-bottom: 6px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    }
    div[data-baseweb="tab"] {
        white-space: nowrap !important;
        font-size: 0.88rem !important;
        font-weight: 600 !important;
        padding: 8px 16px !important;
        border-radius: 6px !important;
        min-height: 42px !important;
    }

    /* Tables & DataFrames */
    div[data-testid="stDataFrame"] {
        border-radius: 10px;
        overflow: hidden;
        border: 1px solid rgba(255, 255, 255, 0.08);
    }

    /* Executive Dark Roster Table with 44px Avatars */
    .roster-table {
        width: 100% !important;
        border-collapse: collapse;
        table-layout: fixed !important;
        background: #111827;
        border-radius: 10px;
        overflow: hidden;
        border: 1px solid rgba(255, 255, 255, 0.08);
        font-size: 0.88rem;
        margin-top: 8px;
        margin-bottom: 16px;
    }
    .roster-table th {
        background: #1a2234;
        color: #94a3b8;
        text-transform: uppercase;
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.05em;
        padding: 12px 14px;
        text-align: left;
        border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    }
    .roster-table td {
        padding: 12px 14px;
        vertical-align: middle;
        border-bottom: 1px solid rgba(255, 255, 255, 0.04);
        color: #e2e8f0;
    }
    .roster-table tr:last-child td {
        border-bottom: none;
    }
    .roster-table tr:hover td {
        background: rgba(255, 255, 255, 0.02);
    }
    .player-cell {
        display: flex;
        align-items: center;
        gap: 12px;
    }
    .player-avatar-44 {
        width: 44px;
        height: 44px;
        border-radius: 50%;
        object-fit: cover;
        background: #1f2937;
        border: 2px solid rgba(255, 255, 255, 0.12);
        flex-shrink: 0;
    }
    .player-info {
        display: flex;
        flex-direction: column;
    }
    .player-name {
        font-weight: 600;
        color: #ffffff;
        font-size: 0.92rem;
    }
    .player-meta {
        color: #94a3b8;
        font-size: 0.75rem;
        display: flex;
        align-items: center;
        gap: 6px;
    }
    .rank-pill {
        display: inline-block;
        padding: 2px 7px;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 600;
        background: rgba(255, 255, 255, 0.06);
        color: #cbd5e1;
    }
    .rank-pill-highlight {
        background: rgba(56, 189, 248, 0.15);
        color: #38bdf8;
    }
    .val-pill {
        font-weight: 700;
        color: #f1f5f9;
        font-variant-numeric: tabular-nums;
    }

    /* Glowing Posture Capsules */
    .status-glow-win, .status-glow-contender {
        background: rgba(14, 165, 233, 0.15) !important;
        color: #38bdf8 !important;
        border: 1px solid #38bdf8 !important;
        box-shadow: 0 0 14px rgba(56, 189, 248, 0.35) !important;
    }
    .status-glow-rebuild {
        background: rgba(16, 185, 129, 0.15) !important;
        color: #34d399 !important;
        border: 1px solid #34d399 !important;
        box-shadow: 0 0 14px rgba(52, 211, 153, 0.35) !important;
    }
    .status-glow-neutral, .status-glow-bubble {
        background: rgba(245, 158, 11, 0.15) !important;
        color: #fbbf24 !important;
        border: 1px solid #fbbf24 !important;
        box-shadow: 0 0 14px rgba(251, 191, 36, 0.35) !important;
    }

    /* Dashboard Key Stats & Playoff Probability Cards */
    .dash-stat-grid {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 10px;
        margin-bottom: 12px;
    }
    .dash-stat-box {
        background: #111827;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 10px;
        padding: 12px 14px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
    }
    .dash-stat-label {
        font-size: 0.72rem;
        font-weight: 700;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        margin-bottom: 4px;
    }
    .dash-stat-value {
        font-size: 1.35rem;
        font-weight: 800;
        color: #f8fafc;
        letter-spacing: -0.01em;
    }
    .dash-stat-sub {
        font-size: 0.74rem;
        color: #64748b;
        margin-top: 2px;
    }
    .prob-card-container {
        background: #111827;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 10px;
        padding: 14px 16px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
    }
    .prob-title {
        font-size: 0.76rem;
        font-weight: 700;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 10px;
    }
    .prob-item {
        margin-bottom: 8px;
    }
    .prob-labels {
        display: flex;
        justify-content: space-between;
        font-size: 0.8rem;
        font-weight: 600;
        color: #cbd5e1;
        margin-bottom: 3px;
    }
    .prob-track {
        width: 100%;
        height: 8px;
        background: rgba(255, 255, 255, 0.06);
        border-radius: 9999px;
        overflow: hidden;
    }
    .prob-fill {
        height: 100%;
        border-radius: 9999px;
        transition: width 0.3s ease;
    }

    /* Lineup Overview Card Grid */
    .lineup-grid-container {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
        gap: 12px;
        margin-top: 14px;
        margin-bottom: 20px;
    }
    .lineup-card {
        background: #111827;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 12px;
        display: flex;
        flex-direction: column;
        align-items: center;
        transition: transform 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.35);
    }
    .lineup-card:hover {
        transform: translateY(-2px);
        border-color: rgba(56, 189, 248, 0.4);
        box-shadow: 0 8px 20px rgba(56, 189, 248, 0.15);
    }
    .lineup-card-header {
        width: 100%;
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 8px;
    }
    .lineup-card-team {
        font-size: 0.72rem;
        font-weight: 700;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }
    .lineup-avatar-wrap {
        width: 56px;
        height: 56px;
        border-radius: 50%;
        padding: 2px;
        background: linear-gradient(135deg, rgba(56, 189, 248, 0.5) 0%, rgba(139, 92, 246, 0.3) 100%);
        display: flex;
        align-items: center;
        justify-content: center;
        margin-bottom: 8px;
    }
    .lineup-avatar {
        width: 52px;
        height: 52px;
        border-radius: 50%;
        object-fit: cover;
        background: #1e293b;
    }
    .lineup-card-body {
        width: 100%;
        text-align: center;
    }
    .lineup-name {
        font-size: 0.86rem;
        font-weight: 700;
        color: #f8fafc;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        margin-bottom: 8px;
    }
    .lineup-stats-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 4px;
        background: rgba(15, 23, 42, 0.6);
        border-radius: 8px;
        padding: 6px 8px;
        border: 1px solid rgba(255, 255, 255, 0.04);
    }
    .lineup-stat-box {
        display: flex;
        flex-direction: column;
        align-items: center;
    }
    .lineup-stat-label {
        font-size: 0.62rem;
        font-weight: 700;
        color: #64748b;
        letter-spacing: 0.05em;
        text-transform: uppercase;
    }
    .lineup-stat-val {
        font-size: 0.76rem;
        font-weight: 700;
        color: #e2e8f0;
    }
    .text-cyan {
        color: #38bdf8 !important;
    }
    .text-gold {
        color: #fbbf24 !important;
    }

    /* Mobile Responsive Optimizations */
    @media (max-width: 768px) {
        .block-container {
            padding-left: 0.65rem !important;
            padding-right: 0.65rem !important;
            padding-top: 4.5rem !important;
        }
        div[data-testid="column"] {
            min-width: 130px;
        }
        .card-container {
            padding: 12px 14px !important;
            margin-bottom: 10px !important;
        }
        div[data-testid="stMetricValue"] {
            font-size: 1.2rem !important;
        }
        div[data-baseweb="tab"] {
            font-size: 0.8rem !important;
            padding: 6px 12px !important;
        }
        .roster-table th, .roster-table td {
            padding: 9px 10px !important;
            font-size: 0.82rem !important;
        }
        .player-avatar-44 {
            width: 38px !important;
            height: 38px !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def format_starter_slots_summary(roster_positions):
    """Formats starting positions into a clean string (e.g. 1QB • 2RB • 2WR • 1TE • 2FLEX • 1SF)."""
    starters = [pos for pos in (roster_positions or []) if pos not in ("BN", "IR", "TAXI")]
    counts = {}
    ordered_keys = []
    for pos in starters:
        disp_pos = "SF" if pos == "SUPER_FLEX" else pos
        if disp_pos not in counts:
            counts[disp_pos] = 0
            ordered_keys.append(disp_pos)
        counts[disp_pos] += 1
    return " • ".join(f"{counts[k]}{k}" for k in ordered_keys)


def render_player_table_html(player_rows, show_equity=True):
    """
    Renders an executive dark table with 44px round avatars,
    spacious rows (~56-60px), non-wrapping slot tags, dual ECR badges,
    symmetrical column balance, and consensus market value.
    """
    if not player_rows:
        return "<p style='color: #94a3b8; font-style: italic; padding: 12px;'>No players to display.</p>"

    if show_equity:
        header_cols = """
            <th style='width: 95px; text-align: center;'>Slot</th>
            <th style='width: 32%; text-align: left;'>Player</th>
            <th style='width: 60px; text-align: center;'>Age</th>
            <th style='width: 14%; text-align: center;'>Overall ECR</th>
            <th style='width: 14%; text-align: center;'>Pos ECR</th>
            <th style='width: 18%; text-align: center;'>Consensus Value</th>
            <th style='width: 12%; text-align: center;'>Equity</th>
        """
    else:
        header_cols = """
            <th style='width: 95px; text-align: center;'>Slot</th>
            <th style='width: 38%; text-align: left;'>Player</th>
            <th style='width: 65px; text-align: center;'>Age</th>
            <th style='width: 15%; text-align: center;'>Overall ECR</th>
            <th style='width: 15%; text-align: center;'>Pos ECR</th>
            <th style='width: 20%; text-align: center;'>Consensus Value</th>
        """

    html = f"""
    <div style='overflow-x: auto; -webkit-overflow-scrolling: touch; margin-bottom: 1.25rem;'>
    <table class='roster-table'>
        <thead>
            <tr>
                {header_cols}
            </tr>
        </thead>
        <tbody>
    """
    for r in player_rows:
        slot = r.get("Slot", "BN")
        pos = r.get("Pos", "UTIL")
        badge_cls = f"badge-{pos.lower()}" if f"badge-{pos.lower()}" in ("badge-qb", "badge-rb", "badge-wr", "badge-te", "badge-k", "badge-def", "badge-pick") else "badge-rb"
        avatar = r.get("Avatar", "")
        pname = r.get("Player", "Unknown")
        team = r.get("NFL Team", "FA")
        age = r.get("Age", "—")
        overall_ecr = r.get("Overall ECR", "—")
        pos_ecr = r.get("Pos ECR", "—")
        val = r.get("Consensus Value", "0 pts")
        eq = r.get("Equity Share", "0.0%")

        avatar_img = f"<img src='{avatar}' class='player-avatar-44' onerror=\"this.src='https://sleepercdn.com/images/v2/icons/player_default.webp'\" />" if avatar else "<div class='player-avatar-44' style='display: flex; align-items: center; justify-content: center; font-weight: bold; color: #94a3b8;'>—</div>"

        equity_td = f"<td style='color: #38bdf8; font-weight: 600; text-align: center;'>{eq}</td>" if show_equity else ""

        html += f"""
            <tr>
                <td style='text-align: center;'><span class='badge-pos {badge_cls}' style='min-width: 65px; text-align: center; white-space: nowrap;'>{slot}</span></td>
                <td style='text-align: left;'>
                    <div class='player-cell'>
                        {avatar_img}
                        <div class='player-info'>
                            <span class='player-name'>{pname}</span>
                            <div class='player-meta'>
                                <span style='font-weight: 600; color: #cbd5e1;'>{pos}</span>
                                <span>•</span>
                                <span>{team}</span>
                            </div>
                        </div>
                    </div>
                </td>
                <td style='color: #94a3b8; text-align: center;'>{age}</td>
                <td style='text-align: center;'><span class='rank-pill'>{overall_ecr}</span></td>
                <td style='text-align: center;'><span class='rank-pill rank-pill-highlight'>{pos_ecr}</span></td>
                <td class='val-pill' style='text-align: center;'>{val}</td>
                {equity_td}
            </tr>
        """
    html += """
        </tbody>
    </table>
    </div>
    """
    return "\n".join(l.lstrip() for l in html.splitlines())


def render_market_table_html(market_rows):
    """
    Renders an executive table for Free Agents or Market Database with 44px avatars,
    spacious rows (~56px), and consensus metrics.
    """
    if not market_rows:
        return "<p style='color: #94a3b8; font-style: italic; padding: 12px;'>No players to display.</p>"

    html = """
    <div style='overflow-x: auto; -webkit-overflow-scrolling: touch; margin-bottom: 1.25rem;'>
    <table class='roster-table'>
        <thead>
            <tr>
                <th style='width: 75px; text-align: center;'>Rank</th>
                <th style='width: 28%; text-align: left;'>Player</th>
                <th style='width: 12%; text-align: center;'>Overall ECR</th>
                <th style='width: 12%; text-align: center;'>Pos ECR</th>
                <th style='width: 16%; text-align: center;'>Consensus Value</th>
                <th style='width: 11%; text-align: center;'>KeepTradeCut</th>
                <th style='width: 11%; text-align: center;'>FantasyCalc</th>
                <th style='width: 10%; text-align: center;'>DynastyProcess</th>
            </tr>
        </thead>
        <tbody>
    """
    for idx, r in enumerate(market_rows, start=1):
        pos = r.get("Pos", "UTIL")
        badge_cls = f"badge-{pos.lower()}" if f"badge-{pos.lower()}" in ("badge-qb", "badge-rb", "badge-wr", "badge-te", "badge-k", "badge-def", "badge-pick") else "badge-rb"
        avatar = r.get("Avatar", "")
        pname = r.get("Player", "Unknown")
        team = r.get("NFL Team", "FA")
        rank_str = r.get("Rank", f"#{idx}")
        overall_ecr = r.get("Overall ECR", "—")
        pos_ecr = r.get("Pos ECR", "—")
        val = r.get("Consensus Value", "0 pts")
        ktc = r.get("KeepTradeCut", "—")
        fc = r.get("FantasyCalc", "—")
        dp = r.get("DynastyProcess", "—")

        avatar_img = f"<img src='{avatar}' class='player-avatar-44' onerror=\"this.src='https://sleepercdn.com/images/v2/icons/player_default.webp'\" />" if avatar else "<div class='player-avatar-44' style='display: flex; align-items: center; justify-content: center; font-weight: bold; color: #94a3b8;'>—</div>"

        html += f"""
            <tr>
                <td style='text-align: center; color: #94a3b8; font-weight: 700;'>{rank_str}</td>
                <td style='text-align: left;'>
                    <div class='player-cell'>
                        {avatar_img}
                        <div class='player-info'>
                            <span class='player-name'>{pname}</span>
                            <div class='player-meta'>
                                <span class='badge-pos {badge_cls}' style='font-size: 0.68rem; padding: 1px 5px;'>{pos}</span>
                                <span>{team}</span>
                            </div>
                        </div>
                    </div>
                </td>
                <td style='text-align: center;'><span class='rank-pill'>{overall_ecr}</span></td>
                <td style='text-align: center;'><span class='rank-pill rank-pill-highlight'>{pos_ecr}</span></td>
                <td class='val-pill' style='text-align: center; color: #38bdf8;'>{val}</td>
                <td style='text-align: center; color: #94a3b8;'>{ktc}</td>
                <td style='text-align: center; color: #94a3b8;'>{fc}</td>
                <td style='text-align: center; color: #94a3b8;'>{dp}</td>
            </tr>
        """
    html += """
        </tbody>
    </table>
    </div>
    """
    return "\n".join(l.lstrip() for l in html.splitlines())


def render_starter_card_grid_html(starters_rows):
    """
    Renders modern dashboard starter cards inspired by cyberpunk sports UI.
    Each card shows slot badge, 52px circular player headshot, player name,
    positional ECR, overall ECR, and consensus value.
    """
    if not starters_rows:
        return "<p style='color: #94a3b8; font-style: italic; padding: 12px;'>No active starters designated.</p>"

    card_items = []
    for s in starters_rows:
        slot = s.get("Slot", "FLEX")
        player = s.get("Player", "")
        pos = s.get("Pos", "WR")
        team = s.get("NFL Team", "FA")
        avatar = s.get("Avatar") or "https://sleepercdn.com/images/v2/icons/player_default.webp"
        pos_ecr = s.get("Pos ECR", "—")
        overall_ecr = s.get("Overall ECR", "—")
        val = s.get("Consensus Value", "0 pts")
        eq = s.get("Equity Share", "0.0%")

        pos_class = f"badge-{pos.lower()}" if f"badge-{pos.lower()}" in ("badge-qb", "badge-rb", "badge-wr", "badge-te", "badge-k", "badge-def", "badge-pick") else "badge-rb"

        card_html = f"""
        <div class='lineup-card'>
            <div class='lineup-card-header'>
                <span class='badge-pos {pos_class}'>{slot}</span>
                <span class='lineup-card-team'>{team}</span>
            </div>
            <div class='lineup-avatar-wrap'>
                <img src='{avatar}' class='lineup-avatar' alt='{player}' onerror="this.onerror=null;this.src='https://sleepercdn.com/images/v2/icons/player_default.webp';" />
            </div>
            <div class='lineup-card-body'>
                <div class='lineup-name' title='{player}'>{player}</div>
                <div class='lineup-stats-grid'>
                    <div class='lineup-stat-box'>
                        <div class='lineup-stat-label'>POS ECR</div>
                        <div class='lineup-stat-val text-cyan'>{pos_ecr}</div>
                    </div>
                    <div class='lineup-stat-box'>
                        <div class='lineup-stat-label'>OVERALL</div>
                        <div class='lineup-stat-val'>{overall_ecr}</div>
                    </div>
                    <div class='lineup-stat-box' style='grid-column: span 2;'>
                        <div class='lineup-stat-label'>MARKET VALUE ({eq})</div>
                        <div class='lineup-stat-val text-gold'>{val}</div>
                    </div>
                </div>
            </div>
        </div>
        """
        card_items.append(card_html)

    full_html = f"""
    <div class='lineup-grid-container'>
        {''.join(card_items)}
    </div>
    """
    return "\n".join(l.lstrip() for l in full_html.splitlines())


def render_opponent_lineup_html(opp_rows):
    """Renders opponent starting lineup with 44px avatars and clean row spacing."""
    if not opp_rows:
        return "<p style='color: #94a3b8; padding: 8px;'>No opponent lineup available.</p>"
    html = """
    <div style='overflow-x: auto; -webkit-overflow-scrolling: touch; margin-bottom: 1rem;'>
    <table class='roster-table'>
        <thead>
            <tr>
                <th style='width: 70px;'>Slot</th>
                <th>Player</th>
                <th>NFL Team</th>
                <th>Projected</th>
            </tr>
        </thead>
        <tbody>
    """
    for r in opp_rows:
        slot = r.get("Slot", "FLEX")
        avatar = r.get("Avatar", "")
        pname = r.get("Player", "—")
        team = r.get("NFL Team", "—")
        proj = r.get("Projected", "0.0 pts")
        avatar_img = f"<img src='{avatar}' class='player-avatar-44' onerror=\"this.src='https://sleepercdn.com/images/v2/icons/player_default.webp'\" />" if avatar else "<div class='player-avatar-44' style='display: flex; align-items: center; justify-content: center; font-weight: bold; color: #94a3b8;'>—</div>"
        html += f"""
            <tr>
                <td><span class='badge-pos badge-rb'>{slot}</span></td>
                <td>
                    <div class='player-cell'>
                        {avatar_img}
                        <div class='player-info'>
                            <span class='player-name'>{pname}</span>
                        </div>
                    </div>
                </td>
                <td style='color: #94a3b8;'>{team}</td>
                <td class='val-pill' style='color: #38bdf8;'>{proj}</td>
            </tr>
        """
    html += """
        </tbody>
    </table>
    </div>
    """
    return "\n".join(l.lstrip() for l in html.splitlines())


# -----------------------------------------------------------------------------
# Cached Data Fetching
# -----------------------------------------------------------------------------
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_market_database(_cache_version="v6_fantasy_analytics_executive"):
    """Fetches all foundational market datasets and raw API feeds once per 30 minutes."""
    players = get_players()
    fp_rankings = get_fp_rankings_raw()
    player_ids = get_player_ids_raw()
    values_players = get_values_players_raw()
    values_picks = get_values_picks_raw()

    ktc_sf = get_ktc_data_raw(is_superflex=True)
    ktc_1qb = get_ktc_data_raw(is_superflex=False)
    fc_sf = get_fantasycalc_data_raw(is_dynasty=True, is_superflex=True)
    fc_1qb = get_fantasycalc_data_raw(is_dynasty=True, is_superflex=False)
    fc_redraft = get_fantasycalc_data_raw(is_dynasty=False, is_superflex=False)

    # Positional lookups with raw constituent values preserved
    base_dynasty_sf = build_positional_lookup(fp_rankings, player_ids, "dynasty", is_superflex=True)
    enrich_lookup_with_consensus_values(base_dynasty_sf, values_players, player_ids, ktc_raw=ktc_sf, fc_raw=fc_sf, is_superflex=True, mode="equal")

    base_dynasty_1qb = build_positional_lookup(fp_rankings, player_ids, "dynasty", is_superflex=False)
    enrich_lookup_with_consensus_values(base_dynasty_1qb, values_players, player_ids, ktc_raw=ktc_1qb, fc_raw=fc_1qb, is_superflex=False, mode="equal")

    base_redraft = build_positional_lookup(fp_rankings, player_ids, "redraft", is_superflex=False)
    enrich_lookup_with_redraft_values(base_redraft, fc_redraft_raw=fc_redraft)

    # Raw pick bundles for instant mode switching
    picks_bundle_sf = build_picks_sources_bundle(values_picks, values_players, ktc_raw=ktc_sf, fc_raw=fc_sf, is_superflex=True)
    picks_bundle_1qb = build_picks_sources_bundle(values_picks, values_players, ktc_raw=ktc_1qb, fc_raw=fc_1qb, is_superflex=False)

    freshness_info = get_market_data_freshness(fp_rankings, values_players)

    return {
        "players": players,
        "player_ids": player_ids,
        "fp_rankings": fp_rankings,
        "values_players": values_players,
        "values_picks": values_picks,
        "ktc_sf": ktc_sf,
        "ktc_1qb": ktc_1qb,
        "fc_sf": fc_sf,
        "fc_1qb": fc_1qb,
        "fc_redraft": fc_redraft,
        "dynasty_sf_lookup": base_dynasty_sf,
        "dynasty_1qb_lookup": base_dynasty_1qb,
        "redraft_lookup": base_redraft,
        "picks_bundle_sf": picks_bundle_sf,
        "picks_bundle_1qb": picks_bundle_1qb,
        "freshness": freshness_info,
    }


@st.cache_data(ttl=900, show_spinner=False)
def fetch_user_and_leagues(username):
    user = get_user(username)
    nfl_state = get_nfl_state()
    season = nfl_state.get("season", "2024")
    week = max(1, nfl_state.get("week", 1))
    leagues = get_user_leagues(user["user_id"], season)
    return user, season, week, leagues


@st.cache_data(ttl=600, show_spinner=False)
def fetch_league_data(league_id, season, week):
    rosters = get_league_rosters(league_id)
    users = get_league_users(league_id)
    schedule = get_league_schedule(league_id, week)
    traded_picks = get_traded_picks(league_id)
    projections = get_weekly_projections(season, week)
    matchups = get_league_matchups(league_id, week)
    return {
        "rosters": rosters,
        "users": users,
        "schedule": schedule,
        "traded_picks": traded_picks,
        "projections": projections,
        "matchups": matchups,
    }


@st.cache_data(ttl=900, show_spinner=False)
def fetch_portfolio_exposure(user_id, league_ids, league_names, _players_db, _primary_lookup):
    """
    Scans all user's leagues to aggregate portfolio player shares and exposure.
    """
    player_exposure = {}
    total_leagues = 0
    league_summaries = []

    for lid, lname in zip(league_ids, league_names):
        try:
            rosters = get_league_rosters(lid)
            my_roster = next((r for r in rosters if r.get("owner_id") == user_id or user_id in (r.get("co_owners") or [])), None)
            if not my_roster:
                continue

            my_pids = [p for p in (my_roster.get("players") or []) if p]
            if not my_pids:
                continue

            total_leagues += 1
            settings = my_roster.get("settings", {})
            w = settings.get("wins", 0)
            l = settings.get("losses", 0)
            t = settings.get("ties", 0)
            fpts = settings.get("fpts", 0) + (settings.get("fpts_decimal", 0) / 100.0)
            fpts_against = settings.get("fpts_against", 0) + (settings.get("fpts_against_decimal", 0) / 100.0)

            # Roster market capital
            roster_val = sum(_primary_lookup.get(pid, {}).get("market_value", 0.0) for pid in my_pids)

            league_summaries.append({
                "league_id": lid,
                "league_name": lname,
                "record": f"{w}-{l}" + (f"-{t}" if t > 0 else ""),
                "wins": w,
                "losses": l,
                "ties": t,
                "fpts": fpts,
                "fpts_against": fpts_against,
                "players_count": len(my_pids),
                "roster_value": roster_val,
            })

            for pid in my_pids:
                p_obj = _players_db.get(pid, {})
                p_name = p_obj.get("full_name") or pid
                pos = p_obj.get("position") or "UTIL"
                nfl_team = p_obj.get("team") or "FA"
                age = p_obj.get("age", "—")
                val_data = _primary_lookup.get(pid, {})
                m_val = val_data.get("market_value", 0.0)
                ecr = val_data.get("rank_ecr", 999.0)
                o_ecr = val_data.get("rank_ecr_overall", 999.0)

                if pid not in player_exposure:
                    player_exposure[pid] = {
                        "player_id": pid,
                        "name": p_name,
                        "position": pos,
                        "team": nfl_team,
                        "age": age,
                        "market_value": m_val,
                        "rank_ecr": ecr,
                        "rank_ecr_overall": o_ecr,
                        "count": 0,
                        "leagues": [],
                    }
                player_exposure[pid]["count"] += 1
                player_exposure[pid]["leagues"].append(lname)
        except Exception:
            continue

    rows = []
    for pid, d in player_exposure.items():
        c = d["count"]
        pct = (c / total_leagues * 100.0) if total_leagues > 0 else 0.0
        pos = d["position"]
        ecr_val = d["rank_ecr"]
        pos_ecr_str = f"{pos}{int(ecr_val)}" if (ecr_val and ecr_val < 900) else "—"
        o_val = d.get("rank_ecr_overall", 999.0)
        overall_ecr_str = f"#{int(o_val)}" if (o_val and o_val < 900) else "—"

        rows.append({
            "Avatar": get_player_avatar_url(pid, pos, d["team"]),
            "Player": d["name"],
            "Pos": pos,
            "NFL Team": d["team"],
            "Age": d.get("age", "—"),
            "Shares": f"{c} / {total_leagues}",
            "Share Count": c,
            "Exposure": f"{pct:.0f}%",
            "Exposure %": pct,
            "Overall ECR": overall_ecr_str,
            "Pos ECR": pos_ecr_str,
            "Consensus Value": d["market_value"],
            "Leagues Owned": ", ".join(d["leagues"]),
        })

    rows.sort(key=lambda x: (x["Share Count"], x["Consensus Value"]), reverse=True)
    return rows, total_leagues, league_summaries


@st.cache_data(ttl=900, show_spinner=False)
def evaluate_league_quick_status(lid, user_id, is_dyn, roster_pos, _lookup, _redraft_lookup, _players):
    """Accurately calculates franchise status, category, record, and rank across leagues."""
    try:
        rosters = get_league_rosters(lid)
        my_r = next((r for r in rosters if r.get("owner_id") == user_id or user_id in (r.get("co_owners") or [])), None)
        if not my_r or not my_r.get("players"):
            return "Pre-Draft", "neutral", 0, 0, 0.0, 0, "Pre-Draft", 0, 0

        m_settings = my_r.get("settings", {})
        w = m_settings.get("wins", 0)
        l = m_settings.get("losses", 0)
        fpts = m_settings.get("fpts", 0) + (m_settings.get("fpts_decimal", 0) / 100.0)
        p_count = len(my_r.get("players") or [])

        all_rosters_players = {
            r["roster_id"]: get_roster_players(r, _players)
            for r in rosters if r.get("players")
        }
        if is_dyn:
            dynasty_ranked = rank_teams_in_league(all_rosters_players, _lookup, roster_pos, is_dynasty=True)
            dynasty_tier, dynasty_pos, dynasty_total = get_strength_tier(my_r["roster_id"], dynasty_ranked)
            redraft_ranked = rank_teams_in_league(all_rosters_players, _redraft_lookup, roster_pos, is_dynasty=False)
            redraft_tier, redraft_pos, redraft_total = get_strength_tier(my_r["roster_id"], redraft_ranked)
            current_tier, _ = get_current_strength_tier(my_r, rosters, redraft_pos, redraft_total)
            status, cat = classify_dynasty_team(current_tier, dynasty_tier)
            return status, cat, w, l, fpts, p_count, f"#{dynasty_pos}/{dynasty_total}", dynasty_pos, redraft_pos
        else:
            redraft_ranked = rank_teams_in_league(all_rosters_players, _redraft_lookup, roster_pos, is_dynasty=False)
            redraft_tier, redraft_pos, redraft_total = get_strength_tier(my_r["roster_id"], redraft_ranked)
            current_tier, _ = get_current_strength_tier(my_r, rosters, redraft_pos, redraft_total)
            status = classify_redraft_team(current_tier)
            cat = "win" if current_tier == "high" else ("rebuild" if current_tier == "low" else "neutral")
            return status, cat, w, l, fpts, p_count, f"#{redraft_pos}/{redraft_total}", redraft_pos, redraft_pos
    except Exception:
        return "Active", "neutral", 0, 0, 0.0, 0, "—", 0, 0


# -----------------------------------------------------------------------------
# App State & Navigation Router Initialization
# -----------------------------------------------------------------------------
if "selected_league_id" not in st.session_state:
    st.session_state["selected_league_id"] = None
if "active_user_handle" not in st.session_state:
    st.session_state["active_user_handle"] = DEFAULT_USERNAME
if "selected_mode" not in st.session_state:
    st.session_state["selected_mode"] = "equal"

active_user_handle = st.session_state["active_user_handle"]
if active_user_handle not in ALLOWED_USERS:
    active_user_handle = ALLOWED_USERS[0]
    st.session_state["active_user_handle"] = active_user_handle

with st.spinner(f"Connecting to Sleeper (@{active_user_handle}) & Market Feeds..."):
    market_db = fetch_market_database()
    try:
        user, active_season, active_week, leagues = fetch_user_and_leagues(active_user_handle)
    except Exception:
        active_user_handle = DEFAULT_USERNAME
        st.session_state["active_user_handle"] = DEFAULT_USERNAME
        user, active_season, active_week, leagues = fetch_user_and_leagues(DEFAULT_USERNAME)

# League sorting
def get_league_sort_key(lg):
    name = lg.get("name", "")
    if "Dinastia do Povo" in name:
        return 0
    if "Samonte Dynasty" in name:
        return 1
    if "Diferenciados" in name:
        return 2
    if lg.get("settings", {}).get("type") == 0:
        return 99
    return 10

sorted_leagues = sorted(leagues, key=get_league_sort_key)
PORTAL_LABEL = "All Leagues"
league_options = [PORTAL_LABEL] + [l["name"] for l in sorted_leagues]

# Synchronize with URL query parameters
qp_lid = st.query_params.get("league")
if qp_lid:
    match_lg = next((l for l in leagues if str(l.get("league_id")) == str(qp_lid)), None)
    if match_lg:
        st.session_state["selected_league_id"] = match_lg["league_id"]

def set_active_workspace(lid):
    st.session_state["selected_league_id"] = lid
    if lid is None:
        if "league" in st.query_params:
            del st.query_params["league"]
        st.session_state["top_workspace_selector"] = PORTAL_LABEL
    else:
        st.query_params["league"] = str(lid)
        target = next((l["name"] for l in sorted_leagues if str(l["league_id"]) == str(lid)), None)
        if target:
            st.session_state["top_workspace_selector"] = target

mode_keys = list(VALUATION_MODES.keys())
mode_labels = [VALUATION_MODES[k] for k in mode_keys]
selected_mode = st.session_state.get("selected_mode", "equal")
if selected_mode not in mode_keys:
    selected_mode = "equal"

# -----------------------------------------------------------------------------
# Top Navigation Bar (Upper Bar)
# -----------------------------------------------------------------------------
top_col_brand, top_col_nav, top_col_cfg, top_col_user = st.columns(
    [2.6, 3.6, 1.6, 2.2], vertical_alignment="center"
)

with top_col_brand:
    if st.button("🏈  Fantasy Analytics", key="btn_brand_home", help="Click to return to All Leagues", use_container_width=True):
        set_active_workspace(None)
        st.rerun()

with top_col_nav:
    cur_lid = st.session_state.get("selected_league_id")
    target_label = PORTAL_LABEL
    if cur_lid is not None:
        target_lg = next((l for l in sorted_leagues if str(l.get("league_id")) == str(cur_lid)), None)
        if target_lg:
            target_label = target_lg["name"]

    cur_idx = league_options.index(target_label) if target_label in league_options else 0

    def on_top_workspace_changed():
        val = st.session_state.get("top_workspace_selector")
        if val == PORTAL_LABEL:
            set_active_workspace(None)
        else:
            chosen = next((l for l in sorted_leagues if l["name"] == val), None)
            if chosen:
                set_active_workspace(chosen["league_id"])

    st.selectbox(
        "Active Workspace",
        league_options,
        index=cur_idx,
        key="top_workspace_selector",
        on_change=on_top_workspace_changed,
        label_visibility="collapsed"
    )

with top_col_cfg:
    with st.popover("Settings", use_container_width=True):
        st.markdown("#### Valuation Consensus Model")
        cur_m_idx = mode_keys.index(selected_mode) if selected_mode in mode_keys else 0
        selected_mode_label = st.selectbox(
            "Consensus Engine:",
            mode_labels,
            index=cur_m_idx,
            help="Determines how players and draft picks are evaluated across all tabs."
        )
        new_mode = mode_keys[mode_labels.index(selected_mode_label)]
        if new_mode != st.session_state.get("selected_mode"):
            st.session_state["selected_mode"] = new_mode
            st.rerun()

        st.markdown("---")
        st.markdown("#### Market Data Freshness")
        fresh = market_db.get("freshness", {})
        ktc_stat = (fresh.get("ktc") or fresh.get("keeptradecut") or {}).get("status", "Live Current")
        fc_stat = (fresh.get("fantasycalc") or {}).get("status", "Live Current")
        dp_stat = (fresh.get("dynastyprocess") or {}).get("status", "Updated")
        fp_stat = (fresh.get("fantasypros") or {}).get("status", "Updated")
        st.markdown(f"**KeepTradeCut:** `{ktc_stat}`")
        st.markdown(f"**FantasyCalc:** `{fc_stat}`")
        st.markdown(f"**DynastyProcess:** `{dp_stat}`")
        st.markdown(f"**FantasyPros ECR:** `{fp_stat}`")
        st.markdown("---")
        if st.button("Reload Market Cache", key="btn_reload_market_cache", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

with top_col_user:
    user_idx = ALLOWED_USERS.index(active_user_handle) if active_user_handle in ALLOWED_USERS else 0
    selected_u = st.selectbox(
        "Sleeper Account",
        ALLOWED_USERS,
        index=user_idx,
        format_func=lambda u: f"@{u}",
        key="top_account_selector",
        label_visibility="collapsed"
    )
    if selected_u != st.session_state.get("active_user_handle"):
        st.session_state["active_user_handle"] = selected_u
        st.session_state["selected_league_id"] = None
        st.rerun()

st.markdown("<div style='margin-bottom: 18px;'></div>", unsafe_allow_html=True)

# Prepare Primary Lookup
players = market_db["players"]
all_l_ids = [l["league_id"] for l in sorted_leagues]
all_l_names = [l["name"] for l in sorted_leagues]

primary_lookup_base = market_db["dynasty_sf_lookup"]
primary_lookup = apply_valuation_mode(primary_lookup_base, mode=selected_mode)


# =============================================================================
# VIEW 1: EXECUTIVE FRONT PAGE PORTFOLIO PORTAL (selected_league_id is None)
# =============================================================================
if st.session_state.get("selected_league_id") is None:
    # Header Banner
    col_hero_logo, col_hero_txt = st.columns([1, 6])
    with col_hero_logo:
        if os.path.exists(LOGO_PATH):
            st.image(LOGO_PATH, use_container_width=True)
    with col_hero_txt:
        st.markdown("<h1 style='margin-bottom: 2px;'>Fantasy Analytics</h1>", unsafe_allow_html=True)
        st.markdown("<p style='color: #94a3b8; font-size: 1.05rem; margin-top: 0px;'>Executive Multi-League Portfolio & Franchise Intelligence Platform</p>", unsafe_allow_html=True)

    st.caption(f"Connected Sleeper Account: **@{user['username']}** | Season: **{active_season}** (Wk {active_week}) | Active Model: **{VALUATION_MODES[selected_mode]}**")

    # Aggregate Portfolio Metrics
    exp_rows, total_user_leagues, l_summaries = fetch_portfolio_exposure(
        user["user_id"], all_l_ids, all_l_names, players, primary_lookup
    )
    tot_wins = sum(s.get("wins", 0) for s in l_summaries)
    tot_losses = sum(s.get("losses", 0) for s in l_summaries)
    tot_ties = sum(s.get("ties", 0) for s in l_summaries)
    tot_games = tot_wins + tot_losses + tot_ties
    tot_win_pct = (tot_wins / tot_games * 100.0) if tot_games > 0 else 0.0
    tot_fpts = sum(s.get("fpts", 0.0) for s in l_summaries)
    top_player = exp_rows[0]["Player"] if exp_rows else "—"
    top_shares = exp_rows[0]["Shares"] if exp_rows else "—"

    col_p1, col_p2, col_p3, col_p4 = st.columns(4)
    with col_p1:
        st.metric("Active Franchises", f"{total_user_leagues} Leagues", "Sleeper Connected")
    with col_p2:
        st.metric("Cumulative Season Record", f"{tot_wins}-{tot_losses}" + (f"-{tot_ties}" if tot_ties > 0 else ""), f"{tot_win_pct:.1f}% Win Rate")
    with col_p3:
        st.metric("Total Points Scored", f"{tot_fpts:,.1f} PF", f"{len(exp_rows)} Unique Assets")
    with col_p4:
        st.metric("Core Exposure Asset", f"{top_player}", f"{top_shares} Leagues")

    st.markdown("---")
    st.markdown("### League Workspaces")
    st.caption("Select any franchise to enter its dedicated analytical suite (Franchise Hub, Matchups & Start/Sit, Waivers, Power Rankings, Trade Center).")

    # League Cards Grid (2-column responsive layout)
    grid_cols = st.columns(2)
    for idx, lg in enumerate(sorted_leagues):
        col = grid_cols[idx % 2]
        lid = lg["league_id"]
        lname = lg["name"]

        settings = lg.get("settings", {})
        is_dyn = (settings.get("type") == 2)
        total_rosters = lg.get("total_rosters", 12)
        roster_pos = lg.get("roster_positions", [])
        is_sf = any(pos in ("SUPER_FLEX", "QB") for pos in roster_pos if roster_pos.count("QB") > 1 or pos == "SUPER_FLEX")
        tep_b = settings.get("tep_bonus", 0.0)

        # Accurately compute quick status, category, record, and rank
        league_lookup = primary_lookup if is_dyn else market_db["redraft_lookup"]
        t_status, t_cat, w, l, fpts, p_count, rank_str, d_pos, r_pos = evaluate_league_quick_status(
            lid, user["user_id"], is_dyn, roster_pos, league_lookup, market_db["redraft_lookup"], players
        )

        # Trajectory badge
        if is_dyn:
            if t_cat == "win":
                badge_html = "<span class='status-capsule status-contender'>CONTENDER</span>"
            elif t_cat == "rebuild":
                badge_html = "<span class='status-capsule status-rebuild'>REBUILD</span>"
            else:
                badge_html = "<span class='status-capsule status-bubble'>BUBBLE</span>"
        else:
            badge_html = "<span class='status-capsule status-bubble'>REDRAFT</span>"

        slots_str = format_starter_slots_summary(roster_pos)
        tep_str = f" • +{tep_b:g} TEP" if tep_b > 0 else ""
        format_str = f"{'Dynasty' if is_dyn else 'Redraft'} • {'Superflex' if is_sf else '1QB'} ({total_rosters} Teams){tep_str}"
        if slots_str:
            format_str += f"<br/><span style='color: #64748b; font-size: 0.78rem;'>Starters: {slots_str}</span>"

        if is_dyn:
            d_str = f"#{d_pos}" if d_pos else "—"
            r_str = f"#{r_pos}" if r_pos else "—"
            rank_grid_html = f"""
                <div><span style='color: #94a3b8;'>Dynasty:</span> <b>{d_str}/{total_rosters}</b></div>
                <div><span style='color: #94a3b8;'>Season:</span> <b>{r_str}/{total_rosters}</b></div>
            """
        else:
            r_str = f"#{r_pos}" if r_pos else "—"
            rank_grid_html = f"""
                <div><span style='color: #94a3b8;'>Season:</span> <b>{r_str}/{total_rosters}</b></div>
            """

        card_html = f"""
        <div class='card-container card-highlight'>
            <div style='display: flex; justify-content: space-between; align-items: flex-start;'>
                <h4 style='margin-bottom: 4px;'>{lname}</h4>
                {badge_html}
            </div>
            <div style='color: #94a3b8; font-size: 0.85rem; margin-bottom: 12px;'>{format_str}</div>
            <div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 8px; margin-bottom: 14px; font-size: 0.88rem;'>
                <div><span style='color: #94a3b8;'>Record:</span> <b>{w}-{l}</b></div>
                <div><span style='color: #94a3b8;'>Points:</span> <b>{fpts:,.1f}</b></div>
                {rank_grid_html}
            </div>
        </div>
        """

        with col:
            st.html("\n".join(line.lstrip() for line in card_html.splitlines()))
            if st.button(f"Open Workspace →", key=f"btn_enter_{lid}", use_container_width=True):
                set_active_workspace(lid)
                st.rerun()

    # Quick Top Exposure Table on Front Page (Clean 44px Avatars)
    st.markdown("---")
    st.markdown("### Core Portfolio Exposure (Cross-League Foundations)")
    if exp_rows:
        front_exp = []
        for r in exp_rows[:10]:
            front_exp.append({
                "Slot": f"{r['Shares']}",
                "Player": r["Player"],
                "Pos": r["Pos"],
                "NFL Team": r["NFL Team"],
                "Avatar": r["Avatar"],
                "Age": r.get("Age", "—"),
                "Overall ECR": r.get("Overall ECR", "—"),
                "Pos ECR": r.get("Pos ECR", "—"),
                "Consensus Value": f"{r['Consensus Value']:,.0f} pts",
                "Equity Share": r.get("Exposure", "0%"),
            })
        st.html(render_player_table_html(front_exp, show_equity=True))


# =============================================================================
# VIEW 2: DEDICATED LEAGUE WORKSPACE (selected_league_id is active)
# =============================================================================
else:
    active_lid = st.session_state["selected_league_id"]
    selected_league = next((l for l in sorted_leagues if l["league_id"] == active_lid), sorted_leagues[0])
    selected_league_name = selected_league["name"]

    # Top Breadcrumb Navigation & Return to Portal Button
    col_bcrumb, col_back = st.columns([4, 1.2])
    with col_bcrumb:
        st.markdown(f"## {selected_league_name}")
    with col_back:
        if st.button("← Return to All Leagues", use_container_width=True):
            st.session_state["selected_league_id"] = None
            st.rerun()

    with st.spinner(f"Loading Workspace: {selected_league_name}..."):
        league_data = fetch_league_data(selected_league["league_id"], active_season, active_week)

    rosters = league_data["rosters"]
    users = league_data["users"]
    schedule = league_data["schedule"]
    traded_picks = league_data["traded_picks"]
    weekly_projections = league_data["projections"]
    scoring = selected_league.get("scoring_settings", {})
    roster_pos = selected_league.get("roster_positions", [])

    user_roster = get_user_roster(rosters, user["user_id"])
    if not user_roster:
        user_roster = rosters[0] if rosters else {}

    # Check for un-drafted / empty rosters
    if not user_roster or not user_roster.get("players"):
        st.warning("This league is currently in pre-draft status and has not drafted rosters yet.")
        if st.button("← Return to All Leagues", key="btn_predraft_back"):
            set_active_workspace(None)
            st.rerun()
        st.stop()

    # League Classification & Scoring Adjustments
    ltype = classify_league(selected_league, rosters)
    is_dynasty = (ltype.get("type") != "redraft")
    is_superflex = any(pos in ("SUPER_FLEX", "QB") for pos in roster_pos if roster_pos.count("QB") > 1 or pos == "SUPER_FLEX")
    total_rosters = selected_league.get("total_rosters", len(rosters))

    scoring = selected_league.get("scoring_settings", {})
    tep_bonus = scoring.get("bonus_rec_te", 0.0) or scoring.get("te_bonus", 0.0) or selected_league.get("settings", {}).get("tep_bonus", 0.0)

    # Primary valuation lookup selection
    raw_primary_lookup = market_db["dynasty_sf_lookup"] if is_superflex else market_db["dynasty_1qb_lookup"]
    primary_lookup = apply_valuation_mode(raw_primary_lookup, mode=selected_mode)
    if tep_bonus > 0:
        primary_lookup = apply_te_premium(primary_lookup, bonus_rec_te=tep_bonus)

    redraft_lookup = market_db["redraft_lookup"]
    picks_bundle = market_db["picks_bundle_sf"] if is_superflex else market_db["picks_bundle_1qb"]
    picks_lookup = compute_picks_lookup_from_bundle(picks_bundle, mode=selected_mode)

    all_rosters_players = {
        r["roster_id"]: get_roster_players(r, players)
        for r in rosters
        if r.get("players")
    }

    user_map = {}
    for u in users:
        uid = u.get("user_id")
        dname = u.get("display_name", "Unknown")
        tname = (u.get("metadata") or {}).get("team_name")
        label = f"@{dname}" + (f" ({tname})" if tname else "")
        user_map[uid] = label

    # Team Ranks & Profiles
    if is_dynasty:
        dynasty_ranked = rank_teams_in_league(all_rosters_players, primary_lookup, roster_pos, is_dynasty=True)
        dynasty_tier, dynasty_pos, dynasty_total = get_strength_tier(user_roster["roster_id"], dynasty_ranked)
        redraft_ranked = rank_teams_in_league(all_rosters_players, redraft_lookup, roster_pos, is_dynasty=False)
        redraft_tier, redraft_pos, redraft_total = get_strength_tier(user_roster["roster_id"], redraft_ranked)
        if redraft_total and redraft_pos:
            current_tier, games_played = get_current_strength_tier(user_roster, rosters, redraft_pos, redraft_total)
        else:
            current_tier, games_played = "medium", 0
        team_status, team_cat = classify_dynasty_team(current_tier, dynasty_tier)

        team_tiers = {}
        for pos_idx, item in enumerate(redraft_ranked, start=1):
            rid = item[0]
            team_tiers[rid] = score_to_tier(percentile_score(pos_idx, len(redraft_ranked)))

        picks_ownership = build_picks_ownership(selected_league, traded_picks)
    else:
        redraft_ranked = rank_teams_in_league(all_rosters_players, redraft_lookup, roster_pos, is_dynasty=False)
        redraft_tier, redraft_pos, redraft_total = get_strength_tier(user_roster["roster_id"], redraft_ranked)
        if redraft_total and redraft_pos:
            current_tier, games_played = get_current_strength_tier(user_roster, rosters, redraft_pos, redraft_total)
        else:
            current_tier, games_played = "medium", 0
        team_status = classify_redraft_team(current_tier)
        team_cat = "win" if current_tier == "high" else ("rebuild" if current_tier == "low" else "neutral")
        picks_ownership = {}
        team_tiers = {}

    all_team_profiles = []
    user_profile = None

    for r in rosters:
        rid = r["roster_id"]
        if rid not in all_rosters_players:
            continue
        owner_id = r.get("owner_id")
        manager_label = user_map.get(owner_id, f"Team {rid}")

        if is_dynasty:
            d_tier, _, _ = get_strength_tier(rid, dynasty_ranked)
            r_tier, r_pos, r_tot = get_strength_tier(rid, redraft_ranked)
            c_tier, _ = get_current_strength_tier(r, rosters, r_pos, r_tot)
            t_status, t_cat = classify_dynasty_team(c_tier, d_tier)
            owned_picks = get_picks_for_roster(picks_ownership, rid)
        else:
            r_tier, r_pos, r_tot = get_strength_tier(rid, redraft_ranked)
            c_tier, _ = get_current_strength_tier(r, rosters, r_pos, r_tot)
            t_status = classify_redraft_team(c_tier)
            t_cat = "win" if c_tier == "high" else ("rebuild" if c_tier == "low" else "neutral")
            owned_picks = []

        prof = analyze_team_profile(
            roster=r,
            roster_players=all_rosters_players[rid],
            owned_picks=owned_picks,
            primary_lookup=primary_lookup,
            redraft_lookup=redraft_lookup,
            picks_lookup=picks_lookup if is_dynasty else {},
            team_tiers=team_tiers if is_dynasty else {},
            roster_positions=roster_pos,
            is_dynasty=is_dynasty,
            status=t_status,
            category=t_cat,
            manager_name=manager_label,
            total_rosters=selected_league.get("total_rosters", len(rosters)),
        )
        prof["starter_value"] = sum(a.get("market_value", 0.0) for a in prof.get("starter_assets", []))
        prof["bench_value"] = sum(a.get("market_value", 0.0) for a in prof.get("bench_assets", []))
        prof["picks_value"] = sum(pk.get("market_value", 0.0) for pk in prof.get("pick_assets", []))
        prof["total_value"] = prof["starter_value"] + prof["bench_value"] + prof["picks_value"]
        prof["starters"] = prof["starter_assets"]
        prof["bench"] = prof["bench_assets"]
        prof["picks"] = prof["pick_assets"]

        all_team_profiles.append(prof)
        if rid == user_roster["roster_id"]:
            user_profile = prof

    format_badge = f"{'Dynasty' if is_dynasty else 'Redraft'} • {'Superflex' if is_superflex else '1QB'} • {len(rosters)} Teams"
    if tep_bonus > 0:
        format_badge += f" • +{tep_bonus:g} TEP"
    st.caption(f"{format_badge} | Valuation Engine: **{VALUATION_MODES[selected_mode]}**")

    # Top Metric Summary Pills (Prominently showing BOTH Dynasty Rank and In-Season Rank)
    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    with col_m1:
        wins = user_roster.get("settings", {}).get("wins", 0)
        losses = user_roster.get("settings", {}).get("losses", 0)
        ties = user_roster.get("settings", {}).get("ties", 0)
        st.metric("Team Record", f"{wins} - {losses}" + (f"-{ties}" if ties > 0 else ""), "Current Season")
    with col_m2:
        clean_status = team_status.split("(")[0].strip() if team_status else "Active"
        st.metric("Franchise Trajectory", clean_status, help=team_status)
    with col_m3:
        if is_dynasty and user_profile:
            dyn_rank_str = f"#{dynasty_pos} of {dynasty_total}" if dynasty_pos else "Pre-Draft"
            st.metric("Dynasty Roster Rank", dyn_rank_str, f"{user_profile['total_value']:,.0f} pts")
        else:
            red_rank_str = f"#{redraft_pos} of {redraft_total}" if redraft_pos else "Pre-Draft"
            st.metric("In-Season Rank", red_rank_str)
    with col_m4:
        if is_dynasty and user_profile:
            red_rank_str = f"#{redraft_pos} of {redraft_total}" if redraft_pos else "Pre-Draft"
            st.metric("In-Season Contender Rank", red_rank_str, f"Starters: {user_profile['starter_value']:,.0f} pts")
        else:
            fpts = user_roster.get("settings", {}).get("fpts", 0.0)
            st.metric("Points Scored", f"{fpts:,.1f} pts")

    st.markdown("---")

    # -------------------------------------------------------------------------
    # Multi-Tab Interface (Clean Typography - Emojis Purged)
    # -------------------------------------------------------------------------
    tab_hub, tab_start_sit, tab_waivers, tab_power, tab_trades, tab_market, tab_portfolio = st.tabs([
        "Franchise Hub",
        "Matchups & Start/Sit",
        "Add/Drops & Waivers",
        "Power Rankings & Playoff Odds",
        "Trade Center & Targeted Finder",
        "Market Rankings & Database",
        "Multi-League Portfolio",
    ])

    # =========================================================================
    # TAB 1: FRANCHISE HUB (Enhanced with 44px Avatars and Dual ECR)
    # =========================================================================
    with tab_hub:
        st.subheader(f"Franchise Executive Dashboard: {selected_league_name}")

        owner_user = next((u for u in users if u.get("user_id") == user["user_id"]), {})
        team_name = (owner_user.get("metadata") or {}).get("team_name") or owner_user.get("display_name") or f"Team {user_roster.get('roster_id')}"
        user_avatar_id = owner_user.get("avatar") or user.get("avatar")
        team_avatar = f"https://sleepercdn.com/avatars/thumbs/{user_avatar_id}" if user_avatar_id else "https://sleepercdn.com/images/v2/icons/player_default.webp"

        settings = user_roster.get("settings", {})
        wins = settings.get("wins", 0)
        losses = settings.get("losses", 0)
        ties = settings.get("ties", 0)
        total_games = wins + losses + ties
        win_pct = (wins / total_games * 100.0) if total_games > 0 else 0.0
        fpts = settings.get("fpts", 0) + (settings.get("fpts_decimal", 0) / 100.0)
        fpts_against = settings.get("fpts_against", 0) + (settings.get("fpts_against_decimal", 0) / 100.0)
        diff = fpts - fpts_against

        # Scoring rank calculation
        sorted_by_pf = sorted(rosters, key=lambda r: (r.get("settings", {}).get("fpts", 0) + r.get("settings", {}).get("fpts_decimal", 0)/100.0), reverse=True)
        scoring_rank = 1
        for s_i, s_r in enumerate(sorted_by_pf, start=1):
            if s_r.get("roster_id") == user_roster.get("roster_id"):
                scoring_rank = s_i
                break

        # Projected finish and probabilities
        fpg = (fpts / total_games) if total_games > 0 else (user_profile.get("projected_weekly_score", 0.0) if user_profile else 0.0)
        total_teams = max(len(rosters), 1)
        if redraft_pos:
            raw_playoff = max(5.0, min(98.0, (1.0 - (redraft_pos - 1) / total_teams) * 100.0))
            if total_games > 0:
                win_weight = min(0.85, 0.2 + 0.05 * total_games)
                playoff_prob = round(raw_playoff * (1.0 - win_weight) + win_pct * win_weight, 1)
            else:
                playoff_prob = round(raw_playoff, 1)
        else:
            playoff_prob = 50.0

        finalist_prob = round(max(2.0, min(95.0, playoff_prob * 0.68)), 1)
        champion_prob = round(max(1.0, min(85.0, finalist_prob * 0.45)), 1)

        clean_status = team_status.split("(")[0].strip() if team_status else "Active"
        glow_badge_class = f"status-glow-{team_cat}"
        format_badge = f"{'Dynasty' if is_dynasty else 'Redraft'} • {'Superflex' if is_superflex else '1QB'} • {len(rosters)} Teams"
        if tep_bonus > 0:
            format_badge += f" • +{tep_bonus:g} TEP"

        # 1. Team Identity Hero Banner
        st.markdown(
            f"""
            <div style='display: flex; align-items: center; justify-content: space-between; background: linear-gradient(135deg, rgba(15, 23, 42, 0.8) 0%, rgba(17, 24, 39, 0.95) 100%); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 12px; padding: 16px 22px; margin-bottom: 18px; box-shadow: 0 4px 14px rgba(0,0,0,0.35);'>
                <div style='display: flex; align-items: center; gap: 16px;'>
                    <img src='{team_avatar}' style='width: 50px; height: 50px; border-radius: 50%; border: 2px solid #38bdf8; object-fit: cover;' onerror=\"this.src='https://sleepercdn.com/images/v2/icons/player_default.webp'\" />
                    <div>
                        <div style='font-size: 1.35rem; font-weight: 800; color: #f8fafc; letter-spacing: -0.02em;'>{team_name}</div>
                        <div style='font-size: 0.82rem; color: #94a3b8; margin-top: 2px;'>{format_badge}</div>
                    </div>
                </div>
                <div>
                    <span class='status-capsule {glow_badge_class}' style='font-size: 0.85rem; padding: 6px 14px; border-radius: 9999px; font-weight: 800; letter-spacing: 0.08em;'>{clean_status}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # 2. Executive Dashboard Row (Key Stats & Playoff Probability)
        col_dash_left, col_dash_right = st.columns([1.2, 1.0])
        with col_dash_left:
            st.markdown(
                f"""
                <div class='dash-stat-grid'>
                    <div class='dash-stat-box'>
                        <div class='dash-stat-label'>AVG FP / GM</div>
                        <div class='dash-stat-value text-cyan'>{fpg:,.1f}</div>
                        <div class='dash-stat-sub'>PF: {fpts:,.1f} pts</div>
                    </div>
                    <div class='dash-stat-box'>
                        <div class='dash-stat-label'>SCORING RANK</div>
                        <div class='dash-stat-value'>#{scoring_rank} <span style='font-size: 0.8rem; font-weight: 500; color: #64748b;'>of {len(rosters)}</span></div>
                        <div class='dash-stat-sub'>Differential: {'+' if diff >= 0 else ''}{diff:,.1f}</div>
                    </div>
                    <div class='dash-stat-box'>
                        <div class='dash-stat-label'>SEASON RECORD</div>
                        <div class='dash-stat-value'>{wins}-{losses}{f'-{ties}' if ties > 0 else ''}</div>
                        <div class='dash-stat-sub'>{win_pct:.1f}% Win Rate</div>
                    </div>
                    <div class='dash-stat-box'>
                        <div class='dash-stat-label'>PROJ. FINISH</div>
                        <div class='dash-stat-value text-gold'>#{redraft_pos if redraft_pos else '—'}</div>
                        <div class='dash-stat-sub'>Tier: {team_status}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with col_dash_right:
            dyn_pos_txt = f"#{dynasty_pos} of {dynasty_total}" if (is_dynasty and dynasty_pos) else "—"
            red_pos_txt = f"#{redraft_pos} of {redraft_total}" if redraft_pos else "—"
            tot_val_txt = f"{user_profile['total_value']:,.0f} pts" if user_profile else "—"
            starter_val_txt = f"{user_profile['starter_value']:,.0f} pts" if user_profile else "—"
            bench_val_txt = f"{user_profile['bench_value']:,.0f} pts" if user_profile else "—"

            st.markdown(
                f"""
                <div class='prob-card-container'>
                    <div class='prob-title'>Playoff & Contender Probability</div>
                    <div class='prob-item'>
                        <div class='prob-labels'><span>Playoff Contender</span><span style='color: #38bdf8; font-weight: 700;'>{playoff_prob:.0f}%</span></div>
                        <div class='prob-track'><div class='prob-fill' style='width: {playoff_prob}%; background: linear-gradient(90deg, #06b6d4, #38bdf8);'></div></div>
                    </div>
                    <div class='prob-item'>
                        <div class='prob-labels'><span>Finalist / Top 2</span><span style='color: #22d3ee; font-weight: 700;'>{finalist_prob:.0f}%</span></div>
                        <div class='prob-track'><div class='prob-fill' style='width: {finalist_prob}%; background: linear-gradient(90deg, #0284c7, #06b6d4);'></div></div>
                    </div>
                    <div class='prob-item'>
                        <div class='prob-labels'><span>Championship</span><span style='color: #c084fc; font-weight: 700;'>{champion_prob:.0f}%</span></div>
                        <div class='prob-track'><div class='prob-fill' style='width: {champion_prob}%; background: linear-gradient(90deg, #8b5cf6, #c084fc);'></div></div>
                    </div>
                    <div style='margin-top: 10px; font-size: 0.74rem; color: #64748b; border-top: 1px solid rgba(255,255,255,0.06); padding-top: 6px; display: flex; justify-content: space-between;'>
                        <span><b>Dynasty:</b> {dyn_pos_txt}</span>
                        <span><b>Starters:</b> {starter_val_txt}</span>
                        <span><b>Bench:</b> {bench_val_txt}</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Full Roster Breakdown & Equity Distribution
        st.markdown("---")
        st.markdown("### Complete Franchise Roster Breakdown & Asset Valuation")
        st.caption("Spacious player roster view featuring 44px circular headshots, consensus valuations, positional and overall ECR, and franchise equity shares.")

        user_pids = user_roster.get("players") or []
        user_starter_pids = set(user_roster.get("starters") or [])
        user_taxi_pids = set(user_roster.get("taxi") or [])
        user_reserve_pids = set(user_roster.get("reserve") or [])

        # Total team market value for equity calculation
        total_team_val = sum(primary_lookup.get(pid, {}).get("market_value", 0.0) for pid in user_pids)
        if total_team_val <= 0:
            total_team_val = 1.0

        def build_player_row(pid, slot_label):
            p = players.get(pid, {})
            pname = p.get("full_name") or pid
            pos = p.get("position") or "UTIL"
            team = p.get("team") or "FA"
            age = p.get("age", "—")
            val_data = primary_lookup.get(pid, {})
            m_val = val_data.get("market_value", 0.0)
            ecr = val_data.get("rank_ecr_pos", val_data.get("rank_ecr", 999.0))
            o_ecr = val_data.get("rank_ecr_overall", 999.0)
            pos_ecr_str = f"{pos}{int(ecr)}" if (ecr and ecr < 900) else "—"
            overall_ecr_str = f"#{int(o_ecr)}" if (o_ecr and o_ecr < 900) else "—"
            equity_pct = (m_val / total_team_val * 100.0)

            return {
                "Avatar": get_player_avatar_url(pid, pos, team),
                "Slot": slot_label,
                "Player": pname,
                "Pos": pos,
                "NFL Team": team,
                "Age": age,
                "Overall ECR": overall_ecr_str,
                "Pos ECR": pos_ecr_str,
                "Consensus Value": f"{m_val:,.0f} pts",
                "Equity Share": f"{equity_pct:.1f}%",
                "_val": m_val,
            }

        # Segment players
        starters_data = []
        bench_data = []
        taxi_data = []
        ir_data = []

        # Order starters by roster_positions
        for s_idx, spid in enumerate(user_roster.get("starters") or []):
            if spid and spid != "0":
                slot_name = roster_pos[s_idx] if s_idx < len(roster_pos) else "FLEX"
                starters_data.append(build_player_row(spid, slot_name))

        for pid in user_pids:
            if pid in user_starter_pids:
                continue
            elif pid in user_taxi_pids:
                taxi_data.append(build_player_row(pid, "TAXI"))
            elif pid in user_reserve_pids:
                ir_data.append(build_player_row(pid, "IR"))
            else:
                bench_data.append(build_player_row(pid, "BENCH"))

        bench_data.sort(key=lambda x: x["_val"], reverse=True)
        taxi_data.sort(key=lambda x: x["_val"], reverse=True)
        ir_data.sort(key=lambda x: x["_val"], reverse=True)

        col_rst_title, col_rst_toggle = st.columns([3, 1.8], vertical_alignment="center")
        with col_rst_title:
            st.caption("Complete franchise asset valuation with consensus market values, ECR, and equity shares.")
        with col_rst_toggle:
            universal_roster_view = st.radio(
                "Roster View Mode",
                ["Card Grid (Dashboard)", "Detailed Table"],
                index=0,
                horizontal=True,
                key="universal_roster_view_mode",
                label_visibility="collapsed"
            )

        roster_sub_starters, roster_sub_bench, roster_sub_taxi, roster_sub_all = st.tabs([
            f"Starters ({len(starters_data)})",
            f"Bench ({len(bench_data)})",
            f"Taxi & IR ({len(taxi_data) + len(ir_data)})",
            f"All Rostered Players ({len(user_pids)})",
        ])

        with roster_sub_starters:
            if starters_data:
                if universal_roster_view == "Card Grid (Dashboard)":
                    st.html(render_starter_card_grid_html(starters_data))
                else:
                    st.html(render_player_table_html(starters_data, show_equity=True))
            else:
                st.info("No active starters designated.")

        with roster_sub_bench:
            if bench_data:
                if universal_roster_view == "Card Grid (Dashboard)":
                    st.html(render_starter_card_grid_html(bench_data))
                else:
                    st.html(render_player_table_html(bench_data, show_equity=True))
            else:
                st.info("No bench players detected.")

        with roster_sub_taxi:
            if taxi_data:
                st.markdown("#### Taxi Squad Assets")
                if universal_roster_view == "Card Grid (Dashboard)":
                    st.html(render_starter_card_grid_html(taxi_data))
                else:
                    st.html(render_player_table_html(taxi_data, show_equity=True))
            if ir_data:
                st.markdown("#### Injured Reserve (IR)")
                if universal_roster_view == "Card Grid (Dashboard)":
                    st.html(render_starter_card_grid_html(ir_data))
                else:
                    st.html(render_player_table_html(ir_data, show_equity=True))
            if not taxi_data and not ir_data:
                st.info("No taxi squad or IR reserve players.")

        with roster_sub_all:
            all_roster_rows = starters_data + bench_data + taxi_data + ir_data
            all_roster_rows.sort(key=lambda x: x["_val"], reverse=True)
            if all_roster_rows:
                if universal_roster_view == "Card Grid (Dashboard)":
                    st.html(render_starter_card_grid_html(all_roster_rows))
                else:
                    st.html(render_player_table_html(all_roster_rows, show_equity=True))

        # Draft Capital Table for Dynasty
        if is_dynasty and user_profile and user_profile.get("picks"):
            st.markdown("---")
            st.markdown("### Future Draft Capital Portfolio")
            pick_rows = []
            for pk in user_profile["picks"]:
                val = pk.get("market_value") or 0.0
                pick_rows.append({
                    "Draft Pick Asset": pk.get("name", "Draft Pick"),
                    "Season": pk.get("season", "—"),
                    "Round": f"Round {pk.get('round', '—')}",
                    "Consensus Market Value": f"{float(val):,.0f} pts",
                    "_val": float(val),
                })
            if pick_rows:
                pick_rows.sort(key=lambda x: x["_val"], reverse=True)
                df_picks = pd.DataFrame(pick_rows)
                if "_val" in df_picks.columns:
                    df_picks = df_picks.drop(columns=["_val"])
                st.dataframe(df_picks, hide_index=True, use_container_width=True)
            else:
                st.info("No future draft picks recorded.")


    # =========================================================================
    # TAB 2: MATCHUPS & START/SIT
    # =========================================================================
    with tab_start_sit:
        st.subheader(f"Week {active_week} Matchup & Starting Lineup Audit")

        roster_players = get_roster_players(user_roster, players)
        proj_lookup = {}
        for p in roster_players:
            pid = p.get("player_id")
            raw = weekly_projections.get(pid)
            proj_lookup[pid] = calculate_weekly_projected_points(pid, raw, scoring, p)

        audit = audit_weekly_lineup(
            user_roster=user_roster,
            roster_players=roster_players,
            projections_lookup=proj_lookup,
            roster_positions=roster_pos,
            player_db=players,
        )

        week_matchups = league_data.get("matchups") or []
        my_m_obj = next((m for m in week_matchups if m.get("roster_id") == user_roster["roster_id"]), None)
        my_matchup_id = my_m_obj.get("matchup_id") if my_m_obj else None

        opp_roster = None
        opp_m_obj = None
        if my_matchup_id is not None:
            for m in week_matchups:
                if m.get("matchup_id") == my_matchup_id and m.get("roster_id") != user_roster["roster_id"]:
                    opp_m_obj = m
                    opp_roster = next((r for r in rosters if r.get("roster_id") == m.get("roster_id")), None)
                    break

        c1, c2, c3 = st.columns([2, 1, 2])
        with c1:
            st.markdown(f"**Your Team** (`{user_map.get(user['user_id'], 'You')}`)")
            st.metric("Active Projected", f"{audit['active_points_total']:.1f} pts")
            st.caption(f"Optimal Lineup Ceiling: **{audit['optimal_points_total']:.1f} pts**")
        with c2:
            st.markdown("<div style='text-align: center; padding-top: 15px; font-weight: bold; font-size: 1.5rem;'>VS</div>", unsafe_allow_html=True)
        with c3:
            opp_lineup_rows = []
            if opp_roster:
                opp_name = user_map.get(opp_roster.get("owner_id"), f"Team {opp_roster['roster_id']}")
                opp_starter_pids = (
                    opp_m_obj.get("starters")
                    if opp_m_obj and opp_m_obj.get("starters")
                    else (opp_roster.get("starters") or [])
                )
                opp_proj = 0.0
                for s_idx, pid in enumerate(opp_starter_pids):
                    slot_name = roster_pos[s_idx] if s_idx < len(roster_pos) else "FLEX"
                    if pid and pid != "0":
                        p = players.get(pid, {})
                        p_proj = calculate_weekly_projected_points(pid, weekly_projections.get(pid), scoring, p)
                        opp_proj += p_proj
                        opp_lineup_rows.append({
                            "Avatar": get_player_avatar_url(pid, p.get("position"), p.get("team")),
                            "Slot": slot_name,
                            "Player": p.get("full_name") or pid,
                            "NFL Team": p.get("team") or "FA",
                            "Projected": f"{p_proj:.1f} pts",
                        })
                    else:
                        opp_lineup_rows.append({
                            "Avatar": "",
                            "Slot": slot_name,
                            "Player": "— Empty Slot —",
                            "NFL Team": "—",
                            "Projected": "0.0 pts",
                        })

                st.markdown(f"**Opponent** (`{opp_name}`)")
                st.metric("Opponent Projected", f"{opp_proj:.1f} pts")
                diff = audit['active_points_total'] - opp_proj
                delta_txt = f"{'+' if diff >= 0 else ''}{diff:.1f} pts"
                verdict = "Favored" if diff >= 0 else "Underdog"
                st.caption(f"Projected Spread: **{delta_txt}** ({verdict})")
            else:
                st.info("No head-to-head opponent scheduled for this week (or bye).")

        if opp_roster and opp_lineup_rows:
            with st.expander(f"View Opponent Starting Lineup ({opp_name})", expanded=False):
                st.html(render_opponent_lineup_html(opp_lineup_rows))

        # Optimization alerts
        if audit["start_sit_swaps"]:
            st.warning(f"**Lineup Optimization Available:** You can gain **+{audit['points_differential']:.1f} pts** by adjusting your starters:")
            for swap in audit["start_sit_swaps"]:
                st.markdown(
                    f"- **START:** `{swap['start_player'].get('full_name')}` ({swap['start_proj']:.1f} pts) "
                    f"over **SIT:** `{swap['sit_player'].get('full_name')}` ({swap['sit_proj']:.1f} pts) in **{swap['slot']}** "
                    f"(Net gain: **+{swap['gain']:.1f} pts**)"
                )
        else:
            st.success("**Optimal Lineup Set:** Your active Sleeper lineup maximizes projected points for this week!")

        # Active Starter Injury Alerts
        if audit["injury_alerts"]:
            st.error("**Active Starter Injury Risk Detected:**")
            for inj in audit["injury_alerts"]:
                sname = inj["starter"].get("full_name")
                status = inj["status"]
                slot = inj["slot"]
                pivot = inj.get("pivot")
                if pivot:
                    pname = pivot[0].get("full_name")
                    pproj = pivot[1]
                    st.markdown(f"- **[{status.upper()}]** `{sname}` ({slot}, {inj['starter_proj']:.1f} pts) ➔ **Recommended Pivot:** `{pname}` ({pproj:.1f} pts)")
                else:
                    st.markdown(f"- **[{status.upper()}]** `{sname}` ({slot}, {inj['starter_proj']:.1f} pts) ➔ *No healthy bench substitute found!*")


    # =========================================================================
    # TAB 3: ADD/DROPS & WAIVERS (Moved Before Power Rankings)
    # =========================================================================
    with tab_waivers:
        st.subheader("Intelligent Waiver Wire & Add/Drop Assistant")

        roster_players = get_roster_players(user_roster, players)
        free_agents = get_free_agents(rosters, players)

        col_w1, col_w2 = st.columns([2, 1])
        with col_w1:
            if is_dynasty:
                waiver_perspective = st.radio(
                    "Evaluation Perspective / Horizon:",
                    [
                        "Dynasty (Long-Term Market Capital & Youth Upside)",
                        "Rest of Season (ROS / Win-Now Starting Points)",
                    ],
                    horizontal=True,
                    help="Dynasty horizon optimizes for long-term player trade capital. ROS horizon optimizes for immediate starting points."
                )
                eval_dynasty = "Dynasty" in waiver_perspective
            else:
                waiver_perspective = "Rest of Season (Redraft)"
                eval_dynasty = False

        with col_w2:
            protection_choice = st.selectbox(
                "Drop Protection Level:",
                ["Injured Stars Protected", "Unrestricted (Show All Drops)"],
                help="Protects injured NFL starters (IR/DNR/PUP) from being recommended as cuts."
            )
            protect_injured = "Injured Stars" in protection_choice

        active_lookup = primary_lookup if eval_dynasty else redraft_lookup
        alt_eval_lookup = redraft_lookup if eval_dynasty else primary_lookup

        waivers = build_intelligent_waiver_suggestions(
            roster_players=roster_players,
            free_agents=free_agents,
            primary_lookup=active_lookup,
            roster_positions=roster_pos,
            user_roster=user_roster,
            category=team_cat,
            is_dynasty=eval_dynasty,
            protect_injured=protect_injured,
            alt_lookup=alt_eval_lookup,
        )

        def render_waiver_upgrade_card(s, is_starter=True):
            add_p = s["add_player"]
            drop_p = s["drop_player"]
            add_id = add_p.get("player_id")
            drop_id = drop_p.get("player_id")
            add_name = add_p.get("full_name") or add_id
            drop_name = drop_p.get("full_name") or drop_id
            pos = add_p.get("position", "UTIL")
            team = add_p.get("team", "FA")
            age = add_p.get("age", "—")
            avatar = get_player_avatar_url(add_id, pos, team)
            tag = s.get("priority_tag", "STARTER UPGRADE" if is_starter else "BENCH UPGRADE")

            dyn_val = s.get("add_value", 0.0) if eval_dynasty else (s.get("add_alt_value") or s.get("add_value", 0.0))
            ros_val = s.get("add_alt_value", 0.0) if eval_dynasty else s.get("add_value", 0.0)
            
            add_rank = s.get("add_ranking", {})
            dyn_o_ecr = add_rank.get("rank_ecr_overall", 999.0)
            dyn_p_ecr = add_rank.get("rank_ecr_pos", add_rank.get("rank_ecr", 999.0))
            ros_rank = s.get("add_alt_rank") or 999.0

            dyn_o_str = f"#{int(dyn_o_ecr)}" if (dyn_o_ecr and dyn_o_ecr < 900) else "—"
            dyn_p_str = f"{pos}{int(dyn_p_ecr)}" if (dyn_p_ecr and dyn_p_ecr < 900) else "—"
            ros_str = f"#{int(ros_rank)}" if (ros_rank and ros_rank < 900) else "—"

            # Drop player metrics & avatar
            drop_pos = drop_p.get("position", "UTIL")
            drop_team = drop_p.get("team", "FA")
            drop_age = drop_p.get("age", "—")
            drop_avatar = get_player_avatar_url(drop_id, drop_pos, drop_team)

            drop_rank = s.get("drop_ranking") or primary_lookup.get(drop_id, {})
            drop_dyn_val = s.get("drop_value", 0.0) if eval_dynasty else (s.get("drop_alt_value") or s.get("drop_value", 0.0))
            drop_ros_val = s.get("drop_alt_value", 0.0) if eval_dynasty else s.get("drop_value", 0.0)

            drop_dyn_o = drop_rank.get("rank_ecr_overall", 999.0)
            drop_dyn_p = drop_rank.get("rank_ecr_pos", drop_rank.get("rank_ecr", 999.0))
            drop_ros_rank = s.get("drop_alt_rank") or alt_eval_lookup.get(drop_id, {}).get("rank_ecr_pos", 999.0)

            drop_dyn_o_str = f"#{int(drop_dyn_o)}" if (drop_dyn_o and drop_dyn_o < 900) else "—"
            drop_dyn_p_str = f"{drop_pos}{int(drop_dyn_p)}" if (drop_dyn_p and drop_dyn_p < 900) else "—"
            drop_ros_str = f"#{int(drop_ros_rank)}" if (drop_ros_rank and drop_ros_rank < 900) else "—"

            gain = s.get("market_value_gain", 0.0)
            gain_sign = "+" if gain >= 0 else ""
            
            disp_p = s.get("displaced_player")
            disp_text = ""
            if is_starter and disp_p:
                d_name = disp_p.get("full_name") or disp_p.get("player_id")
                disp_text = f"<div style='margin-top: 8px; font-size: 0.82rem; color: #38bdf8;'>↳ Displaces <b>{d_name}</b> in starting lineup</div>"

            alt_drops_html = ""
            viable_drops = s.get("all_drop_candidates", [])
            if viable_drops and len(viable_drops) > 1:
                chips = []
                for cd in viable_drops[:4]:
                    c_obj = cd["drop_player"]
                    c_id = c_obj.get("player_id")
                    c_name = c_obj.get("full_name") or c_id
                    c_pos = c_obj.get("position", "UTIL")
                    c_team = c_obj.get("team", "FA")
                    c_val = cd.get("drop_value", 0.0)
                    c_gain = cd.get("market_value_gain", 0.0)
                    c_avatar = get_player_avatar_url(c_id, c_pos, c_team)
                    c_pos_cls = f"badge-{c_pos.lower()}" if f"badge-{c_pos.lower()}" in ("badge-qb", "badge-rb", "badge-wr", "badge-te", "badge-k", "badge-def") else "badge-rb"
                    chips.append(
                        f"<div style='display: flex; align-items: center; gap: 8px; background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); border-radius: 6px; padding: 4px 10px; font-size: 0.8rem;'>"
                        f"<img src='{c_avatar}' style='width: 24px; height: 24px; border-radius: 50%; object-fit: cover;' onerror=\"this.src='https://sleepercdn.com/images/v2/icons/player_default.webp'\" />"
                        f"<span style='color: #f8fafc; font-weight: 600;'>{c_name}</span>"
                        f"<span class='badge-pos {c_pos_cls}' style='font-size: 0.65rem; padding: 1px 4px;'>{c_pos}</span>"
                        f"<span style='color: #94a3b8;'>({c_val:,.0f} pts)</span>"
                        f"<span style='color: #34d399; font-weight: 700;'>+{c_gain:,.0f} pts</span>"
                        f"</div>"
                    )
                alt_drops_html = f"""
                <div style='margin-top: 12px; padding-top: 10px; border-top: 1px solid rgba(255, 255, 255, 0.06);'>
                    <div style='font-size: 0.76rem; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 6px;'>
                        Alternative Cut Options ({len(viable_drops)} bench players below FA value):
                    </div>
                    <div style='display: flex; flex-wrap: wrap; gap: 8px;'>
                        {''.join(chips)}
                    </div>
                </div>
                """

            card_html = f"""
            <div class='card-container card-success' style='margin-bottom: 16px;'>
                <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;'>
                    <span class='status-capsule status-contender'>{tag}</span>
                    <span class='status-capsule status-rebuild' style='font-size: 0.82rem; font-weight: 800;'>{gain_sign}{gain:,.0f} PTS NET GAIN</span>
                </div>
                
                <div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px;'>
                    <!-- TARGET ADD PLAYER -->
                    <div style='background: rgba(16, 185, 129, 0.05); border: 1px solid rgba(16, 185, 129, 0.25); border-radius: 8px; padding: 12px;'>
                        <div style='font-size: 0.72rem; font-weight: 800; color: #34d399; letter-spacing: 0.05em; margin-bottom: 6px; text-transform: uppercase;'>TARGET ADD</div>
                        <div style='display: flex; gap: 12px; align-items: center;'>
                            <img src='{avatar}' class='player-avatar-44' onerror=\"this.src='https://sleepercdn.com/images/v2/icons/player_default.webp'\" />
                            <div>
                                <div style='display: flex; align-items: center; gap: 6px;'>
                                    <span style='font-size: 1.02rem; font-weight: 700; color: #ffffff;'>{add_name}</span>
                                    <span class='badge-pos badge-{pos.lower()}'>{pos}</span>
                                    <span style='color: #94a3b8; font-size: 0.8rem;'>{team} • Age {age}</span>
                                </div>
                                <div style='display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; font-size: 0.76rem;'>
                                    <span class='rank-pill'>Dynasty: {dyn_val:,.0f} pts ({dyn_o_str} Ovr • {dyn_p_str})</span>
                                    <span class='rank-pill rank-pill-highlight'>ROS: {ros_val:,.0f} pts (Rank {ros_str})</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- RECOMMENDED CUT PLAYER -->
                    <div style='background: rgba(239, 68, 68, 0.05); border: 1px solid rgba(239, 68, 68, 0.25); border-radius: 8px; padding: 12px;'>
                        <div style='font-size: 0.72rem; font-weight: 800; color: #f87171; letter-spacing: 0.05em; margin-bottom: 6px; text-transform: uppercase;'>RECOMMENDED CUT</div>
                        <div style='display: flex; gap: 12px; align-items: center;'>
                            <img src='{drop_avatar}' class='player-avatar-44' onerror=\"this.src='https://sleepercdn.com/images/v2/icons/player_default.webp'\" />
                            <div>
                                <div style='display: flex; align-items: center; gap: 6px;'>
                                    <span style='font-size: 1.02rem; font-weight: 700; color: #ffffff;'>{drop_name}</span>
                                    <span class='badge-pos badge-{drop_pos.lower()}'>{drop_pos}</span>
                                    <span style='color: #94a3b8; font-size: 0.8rem;'>{drop_team} • Age {drop_age}</span>
                                </div>
                                <div style='display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; font-size: 0.76rem;'>
                                    <span class='rank-pill'>Dynasty: {drop_dyn_val:,.0f} pts ({drop_dyn_o_str} Ovr • {drop_dyn_p_str})</span>
                                    <span class='rank-pill rank-pill-highlight'>ROS: {drop_ros_val:,.0f} pts (Rank {drop_ros_str})</span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                {disp_text}
                {alt_drops_html}
            </div>
            """
            return "\n".join(l.lstrip() for l in card_html.splitlines())

        # IR Slot Actions
        ir_suggestions = waivers.get("ir_suggestions", [])
        if ir_suggestions:
            st.markdown("### IR Slot Optimization")
            for ir in ir_suggestions:
                pname = ir["player"].get("full_name")
                reason = ir.get("reason", "IR Eligible")
                st.info(f"• **Move to IR:** `{pname}` ({reason}) ➔ *Frees up an active bench spot for a free agent add.*")

        # Starting Lineup Upgrades
        starter_upgrades = waivers.get("starter_upgrades", [])
        if starter_upgrades:
            st.markdown("### Starting Lineup Upgrades")
            for s in starter_upgrades[:3]:
                st.html(render_waiver_upgrade_card(s, is_starter=True))

        # Bench Upgrades
        cross_upgrades = waivers.get("cross_pos_upgrades", [])
        if cross_upgrades:
            st.markdown("### Top Bench Upgrades")
            for s in cross_upgrades[:3]:
                st.html(render_waiver_upgrade_card(s, is_starter=False))

        # Empty state notification if no waiver suggestions found
        if not starter_upgrades and not cross_upgrades:
            st.markdown(
                """
                <div class='card-container'>
                    <h4 style='margin-bottom: 6px; color: #38bdf8;'>Roster Optimization Status: Optimal</h4>
                    <p style='color: #94a3b8; margin-bottom: 0;'>No immediate waiver wire adds recommended for this roster. Your active starting lineup and bench depth currently hold higher consensus valuation than all available free agents in this league.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Interactive Free Agent Market Explorer
        st.markdown("---")
        st.markdown("### Free Agent Market Explorer")
        c_f1, c_f2 = st.columns([1, 2])
        with c_f1:
            pos_filter = st.selectbox("Filter Position:", ["ALL", "QB", "RB", "WR", "TE", "K", "DEF"])
        with c_f2:
            search_query = st.text_input("Search Player Name:", "")

        fa_rows = []
        for fa in free_agents:
            pos = fa.get("position") or ""
            if pos_filter != "ALL" and pos != pos_filter:
                continue
            pname = fa.get("full_name") or fa.get("player_id", "")
            if search_query and search_query.lower() not in pname.lower():
                continue

            pid = fa.get("player_id")
            p_val_data = primary_lookup.get(pid, {})
            val = float(p_val_data.get("market_value") or 0.0)
            ecr = p_val_data.get("rank_ecr_pos", p_val_data.get("rank_ecr", 999.0))
            o_ecr = p_val_data.get("rank_ecr_overall", 999.0)
            fc_v = p_val_data.get("fc_val")
            ktc_v = p_val_data.get("ktc_val")
            dp_v = p_val_data.get("dp_val")

            try:
                pos_ecr_str = f"{pos}{int(float(ecr))}" if (ecr is not None and float(ecr) < 900) else "—"
            except (ValueError, TypeError):
                pos_ecr_str = "—"

            try:
                overall_ecr_str = f"#{int(float(o_ecr))}" if (o_ecr is not None and float(o_ecr) < 900) else "—"
            except (ValueError, TypeError):
                overall_ecr_str = "—"

            try:
                fc_str = f"{float(fc_v):,.0f}" if fc_v is not None else "—"
            except (ValueError, TypeError):
                fc_str = "—"

            try:
                ktc_str = f"{float(ktc_v):,.0f}" if ktc_v is not None else "—"
            except (ValueError, TypeError):
                ktc_str = "—"

            try:
                dp_str = f"{float(dp_v):,.0f}" if dp_v is not None else "—"
            except (ValueError, TypeError):
                dp_str = "—"

            fa_rows.append({
                "Avatar": get_player_avatar_url(pid, pos, fa.get("team")),
                "Player": pname,
                "Pos": pos,
                "NFL Team": fa.get("team") or "FA",
                "Consensus Value": f"{val:,.0f} pts",
                "Overall ECR": overall_ecr_str,
                "Pos ECR": pos_ecr_str,
                "FantasyCalc": fc_str,
                "KeepTradeCut": ktc_str,
                "DynastyProcess": dp_str,
                "_raw_val": val,
            })

        fa_rows.sort(key=lambda x: x["_raw_val"], reverse=True)
        if fa_rows:
            for idx, r in enumerate(fa_rows, start=1):
                r["Rank"] = f"#{idx}"

            c_faview1, c_faview2 = st.columns([1, 1])
            with c_faview1:
                fa_view = st.radio(
                    "Display Format:",
                    ["Standard Table (44px Avatars)", "Interactive Dataframe"],
                    horizontal=True,
                    key="fa_view_mode",
                )
            with c_faview2:
                st.caption(f"Showing top {min(len(fa_rows), 50)} of {len(fa_rows)} matching available free agents.")

            if fa_view == "Standard Table (44px Avatars)":
                st.html(render_market_table_html(fa_rows[:50]))
            else:
                df_fa = pd.DataFrame(fa_rows[:50]).drop(columns=["_raw_val"])
                st.dataframe(
                    df_fa[["Rank", "Avatar", "Player", "Pos", "NFL Team", "Consensus Value", "Overall ECR", "Pos ECR", "KeepTradeCut", "FantasyCalc", "DynastyProcess"]],
                    column_config={"Avatar": st.column_config.ImageColumn("", width="small")},
                    hide_index=True,
                    use_container_width=True,
                )
        else:
            st.info("No free agents match current filter criteria.")



    # =========================================================================
    # TAB 4: POWER RANKINGS & PLAYOFF ODDS
    # =========================================================================
    with tab_power:
        st.subheader("League Power Rankings & Playoff Simulations")

        def render_simulation_view():
            st.caption("1,000-Run Monte Carlo Simulation incorporating dynamic season records, points scored, and rest-of-season schedule.")

            playoff_start = selected_league.get("settings", {}).get("playoff_week_start", 15)
            team_expectations = {}
            for r in rosters:
                rid = r["roster_id"]
                team_expectations[rid] = compute_team_lineup_expectation(
                    roster=r,
                    roster_players=all_rosters_players.get(rid, []),
                    weekly_projections=weekly_projections,
                    scoring_settings=scoring,
                    roster_positions=roster_pos,
                )

            with st.spinner("Simulating remaining season (1,000 iterations)..."):
                sim_results = run_monte_carlo_simulation(
                    league=selected_league,
                    rosters=rosters,
                    schedule=schedule,
                    team_expectations=team_expectations,
                    current_week=active_week,
                    playoff_week_start=playoff_start,
                    num_simulations=1000,
                )

            sample_res = next(iter(sim_results.values())) if sim_results else {}
            p_count = sample_res.get("playoff_teams_count", 6)
            st.info(f"Playoff Format: Top {p_count} Teams qualify for the postseason.")

            ranked_sim = sorted(sim_results.values(), key=lambda t: t["power_score"], reverse=True)
            table_data = []
            for rank_idx, t in enumerate(ranked_sim, 1):
                rid = t["roster_id"]
                mgr = user_map.get(next((r["owner_id"] for r in rosters if r["roster_id"] == rid), ""), f"Team {rid}")
                is_me = (rid == user_roster["roster_id"])
                mgr_display = f"{mgr} ★ (Your Franchise)" if is_me else mgr
                table_data.append({
                    "Rank": f"#{rank_idx}",
                    "Manager / Team": mgr_display,
                    "Projected W-L": f"{t['avg_wins']:.1f} - {t['avg_losses']:.1f}",
                    "Median PPG": f"{t['expected_pts']:.1f}",
                    "Playoff Odds": f"{t['playoff_pct']:.1f}%",
                    "1st-Round Bye": f"{t['bye_pct']:.1f}%",
                    "Champ Odds": f"{t['champ_pct']:.1f}%",
                    "Season Power Score": f"{t['power_score']:.1f}",
                })

            df_sim = pd.DataFrame(table_data)
            st.dataframe(df_sim, hide_index=True, use_container_width=True)

        def render_dynasty_power_view():
            st.caption("Dynasty Power Formula: 50% Starters Value + 30% Bench Depth + 20% Future Draft Capital (Industry Standard).")
            dynasty_res = compute_dynasty_power_rankings(all_team_profiles)
            ranked_dyn = sorted(dynasty_res.values(), key=lambda x: x["dynasty_score"], reverse=True)

            dyn_data = []
            for rank_idx, t in enumerate(ranked_dyn, 1):
                rid = t["roster_id"]
                is_me = (rid == user_roster["roster_id"])
                mgr_display = f"{t['manager_name']} ★ (Your Franchise)" if is_me else t["manager_name"]
                dyn_data.append({
                    "Rank": f"#{rank_idx}",
                    "Manager / Team": mgr_display,
                    "Dynasty Score": f"{t['dynasty_score']:.1f} / 100",
                    "Starters Val (50%)": f"{t['starters_val']:,.0f} pts",
                    "Bench Val (30%)": f"{t['bench_val']:,.0f} pts",
                    "Picks Capital (20%)": f"{t['picks_val']:,.0f} pts",
                    "Competitive Tier": t["status"].split("(")[0].strip() if t.get("status") else "Active",
                })

            df_dyn = pd.DataFrame(dyn_data)
            st.dataframe(df_dyn, hide_index=True, use_container_width=True)

            with st.expander("View Complete Team Roster & Pick Breakdown", expanded=False):
                inspect_mgr = st.selectbox("Select Team to Inspect:", [t["manager_name"] for t in ranked_dyn])
                selected_prof = next(p for p in all_team_profiles if p["manager_name"] == inspect_mgr)
                tot_val = selected_prof.get("total_value", 0.0)

                insp_sub_starters, insp_sub_bench, insp_sub_picks = st.tabs([
                    f"Starters ({len(selected_prof['starters'])})",
                    f"Bench ({len(selected_prof['bench'])})",
                    f"Draft Capital ({len(selected_prof.get('picks', []))})",
                ])

                with insp_sub_starters:
                    st.caption(f"Starting Lineup Valuation: **{selected_prof.get('starter_value', 0):,.0f} pts**")
                    st_rows = []
                    for idx, a in enumerate(selected_prof["starters"]):
                        pid = a.get("player_id")
                        pos = a.get("position") or "UTIL"
                        team = a.get("team") or "FA"
                        m_val = float(a.get("market_value") or 0.0)
                        p_data = primary_lookup.get(pid, {})
                        ecr = a.get("rank_ecr") or p_data.get("rank_ecr_pos", 999.0)
                        o_ecr = p_data.get("rank_ecr_overall", 999.0)
                        pos_ecr_str = f"{pos}{int(ecr)}" if (ecr and ecr < 900) else "—"
                        overall_ecr_str = f"#{int(o_ecr)}" if (o_ecr and o_ecr < 900) else "—"
                        eq_str = f"{(m_val / tot_val * 100):.1f}%" if tot_val > 0 else "0.0%"
                        st_rows.append({
                            "Slot": roster_pos[idx] if idx < len(roster_pos) else "FLEX",
                            "Player": a.get("name", "Unknown"),
                            "Pos": pos,
                            "NFL Team": team,
                            "Age": a.get("age") or "—",
                            "Avatar": get_player_avatar_url(pid, pos, team),
                            "Overall ECR": overall_ecr_str,
                            "Pos ECR": pos_ecr_str,
                            "Consensus Value": f"{m_val:,.0f} pts",
                            "Equity Share": eq_str,
                        })
                    st.html(render_player_table_html(st_rows, show_equity=True))

                with insp_sub_bench:
                    st.caption(f"Full Bench Depth Valuation: **{selected_prof.get('bench_value', 0):,.0f} pts**")
                    bn_rows = []
                    for a in selected_prof["bench"]:
                        pid = a.get("player_id")
                        pos = a.get("position") or "UTIL"
                        team = a.get("team") or "FA"
                        m_val = float(a.get("market_value") or 0.0)
                        p_data = primary_lookup.get(pid, {})
                        ecr = a.get("rank_ecr") or p_data.get("rank_ecr_pos", 999.0)
                        o_ecr = p_data.get("rank_ecr_overall", 999.0)
                        pos_ecr_str = f"{pos}{int(ecr)}" if (ecr and ecr < 900) else "—"
                        overall_ecr_str = f"#{int(o_ecr)}" if (o_ecr and o_ecr < 900) else "—"
                        eq_str = f"{(m_val / tot_val * 100):.1f}%" if tot_val > 0 else "0.0%"
                        bn_rows.append({
                            "Slot": "BN",
                            "Player": a.get("name", "Unknown"),
                            "Pos": pos,
                            "NFL Team": team,
                            "Age": a.get("age") or "—",
                            "Avatar": get_player_avatar_url(pid, pos, team),
                            "Overall ECR": overall_ecr_str,
                            "Pos ECR": pos_ecr_str,
                            "Consensus Value": f"{m_val:,.0f} pts",
                            "Equity Share": eq_str,
                        })
                    st.html(render_player_table_html(bn_rows, show_equity=True))

                with insp_sub_picks:
                    if is_dynasty and selected_prof.get("picks"):
                        st.caption(f"Draft Capital Portfolio Valuation: **{selected_prof.get('picks_value', 0):,.0f} pts**")
                        pk_rows = []
                        for pk in selected_prof["picks"]:
                            pk_val = float(pk.get("market_value") or 0.0)
                            pk_eq = f"{(pk_val / tot_val * 100):.1f}%" if tot_val > 0 else "0.0%"
                            pk_rows.append({
                                "Draft Pick Asset": pk.get("name", "Draft Pick"),
                                "Season": str(pk.get("season", "—")),
                                "Round": f"Round {pk.get('round', '—')}",
                                "Consensus Value": f"{pk_val:,.0f} pts",
                                "Equity Share": pk_eq,
                            })
                        st.dataframe(pd.DataFrame(pk_rows), hide_index=True, use_container_width=True)
                    else:
                        st.info("No draft pick assets in this league format.")

        if is_dynasty:
            sub_mc, sub_dyn = st.tabs([
                "Season Standings & Playoff Simulation (Monte Carlo)",
                "Dynasty Asset Power Rankings (50/30/20)",
            ])
            with sub_mc:
                render_simulation_view()
            with sub_dyn:
                render_dynasty_power_view()
        else:
            render_simulation_view()


    # =========================================================================
    # TAB 5: TRADE CENTER & TARGETED FINDER
    # =========================================================================
    with tab_trades:
        st.subheader("Trade Center & Targeted Acquisition Engine")

        def render_trade_proposal_card(idx: int, prop: dict, show_chat_message: bool = True):
            arch = prop.get("archetype") or prop.get("structure") or "Balanced Trade Proposal"
            partner = prop.get("partner_name") or prop.get("partner_profile", {}).get("manager_name") or "Trade Partner"
            gives = prop.get("give_assets") or prop.get("sending") or []
            recvs = prop.get("receive_assets") or prop.get("receiving") or []
            eval_res = prop.get("eval_result", {})
            why = prop.get("why") or prop.get("rationale") or "Mutually beneficial trade proposal evaluated on consensus market values."

            give_raw = sum(a.get("market_value", 0.0) for a in gives)
            recv_raw = sum(a.get("market_value", 0.0) for a in recvs)
            eff_give = eval_res.get("eff_give", give_raw)
            eff_recv = eval_res.get("eff_receive", recv_raw)
            net_diff = eval_res.get("net_diff", recv_raw - give_raw)
            diff_sign = "+" if net_diff >= 0 else ""
            status_label = str(eval_res.get("status", "Balanced")).upper()
            diff_color = "#10b981" if net_diff >= 0 else "#f43f5e"

            def render_asset_chips(assets):
                chips_html = ""
                for a in assets:
                    name = a.get("name", "Asset")
                    val = float(a.get("market_value") or 0.0)
                    pos = a.get("position") or "PICK"
                    team = a.get("team") or ""
                    pid = a.get("player_id")

                    if a.get("type") == "pick" or not pid or str(pid).startswith("pick_"):
                        icon_html = "<div style='width: 38px; height: 38px; border-radius: 50%; background: #1e1b4b; border: 1.5px solid #818cf8; display: flex; align-items: center; justify-content: center; font-size: 1rem; flex-shrink: 0;'>🎯</div>"
                        pos_badge = "<span class='badge-pos badge-pick' style='font-size: 0.65rem; padding: 1px 5px;'>PICK</span>"
                    else:
                        avatar_url = get_player_avatar_url(pid, pos, team)
                        icon_html = f"<img src='{avatar_url}' style='width: 38px; height: 38px; border-radius: 50%; object-fit: cover; border: 1.5px solid #475569; flex-shrink: 0;' onerror=\"this.src='https://sleepercdn.com/images/v2/icons/player_default.webp'\" />"
                        badge_cls = f"badge-{pos.lower()}" if f"badge-{pos.lower()}" in ("badge-qb", "badge-rb", "badge-wr", "badge-te", "badge-k", "badge-def") else "badge-rb"
                        pos_badge = f"<span class='badge-pos {badge_cls}' style='font-size: 0.65rem; padding: 1px 5px;'>{pos}</span>"

                    chips_html += f"""
                    <div style='display: flex; align-items: center; justify-content: space-between; gap: 10px; background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 7px 10px; margin-bottom: 6px;'>
                        <div style='display: flex; align-items: center; gap: 10px; min-width: 0;'>
                            {icon_html}
                            <div style='min-width: 0;'>
                                <div style='font-weight: 700; color: #f8fafc; font-size: 0.88rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;'>{name}</div>
                                <div style='font-size: 0.72rem; color: #94a3b8; display: flex; gap: 6px; align-items: center;'>
                                    {pos_badge}
                                    <span>{team}</span>
                                </div>
                            </div>
                        </div>
                        <div style='font-weight: 800; font-size: 0.9rem; color: #38bdf8; text-align: right; white-space: nowrap;'>{val:,.0f} pts</div>
                    </div>
                    """
                return chips_html

            give_chips = render_asset_chips(gives)
            recv_chips = render_asset_chips(recvs)

            card_html = f"""
            <div class='card-container card-highlight' style='padding: 16px; margin-bottom: 16px;'>
                <div style='display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255, 255, 255, 0.08); padding-bottom: 10px; margin-bottom: 14px; flex-wrap: wrap; gap: 8px;'>
                    <div>
                        <span style='font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 700; color: #38bdf8;'>Proposal #{idx}</span>
                        <h4 style='margin: 0; font-size: 1.05rem; font-weight: 800; color: #f8fafc;'>{arch}</h4>
                    </div>
                    <div style='display: flex; align-items: center; gap: 10px;'>
                        <span style='font-size: 0.82rem; color: #94a3b8;'>Partner: <strong style='color: #e2e8f0;'>{partner}</strong></span>
                        <span class='status-capsule' style='background: rgba(16, 185, 129, 0.12); color: {diff_color}; border: 1px solid {diff_color}55;'>{status_label}</span>
                    </div>
                </div>

                <div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 14px; margin-bottom: 14px;'>
                    <div style='background: rgba(17, 24, 39, 0.6); border: 1px solid rgba(244, 63, 94, 0.2); border-radius: 8px; padding: 12px;'>
                        <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;'>
                            <span style='font-size: 0.75rem; font-weight: 800; text-transform: uppercase; color: #fb7185; letter-spacing: 0.04em;'>YOU SEND</span>
                            <span style='font-size: 0.78rem; font-weight: 700; color: #94a3b8;'>Total: <span style='color: #f8fafc;'>{give_raw:,.0f} pts</span></span>
                        </div>
                        {give_chips}
                    </div>

                    <div style='background: rgba(17, 24, 39, 0.6); border: 1px solid rgba(16, 185, 129, 0.2); border-radius: 8px; padding: 12px;'>
                        <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;'>
                            <span style='font-size: 0.75rem; font-weight: 800; text-transform: uppercase; color: #34d399; letter-spacing: 0.04em;'>YOU RECEIVE</span>
                            <span style='font-size: 0.78rem; font-weight: 700; color: #94a3b8;'>Total: <span style='color: #f8fafc;'>{recv_raw:,.0f} pts</span></span>
                        </div>
                        {recv_chips}
                    </div>
                </div>

                <div style='display: flex; justify-content: space-between; align-items: center; background: #0f172a; border-radius: 6px; padding: 8px 12px; margin-bottom: 10px; flex-wrap: wrap; gap: 8px;'>
                    <div style='font-size: 0.82rem; color: #cbd5e1;'>
                        <strong style='color: #94a3b8;'>Net Value Impact:</strong> <span style='font-weight: 800; color: {diff_color};'>{diff_sign}{net_diff:,.0f} pts</span>
                    </div>
                    <div style='font-size: 0.78rem; color: #94a3b8;'>
                        Stud Adj (Send: {eff_give:,.0f} pts | Recv: {eff_recv:,.0f} pts)
                    </div>
                </div>

                <p style='margin: 0; font-size: 0.82rem; color: #94a3b8; line-height: 1.4;'>
                    <strong style='color: #cbd5e1;'>Strategic Rationale:</strong> {why}
                </p>
            </div>
            """
            st.html(card_html)
            if show_chat_message:
                send_names = " + ".join(a.get("name", "Asset") for a in gives)
                recv_names = " + ".join(a.get("name", "Asset") for a in recvs)
                chat_msg = f"Hey {partner}, would you consider {send_names} for {recv_names}? Evaluated as fair on consensus market values."
                st.code(chat_msg, language="markdown")

        trade_view = st.radio(
            "Trade Mode:",
            ["Targeted Asset Finder (Buy or Sell Specific Assets)", "League-Wide Trade Scanner"],
            horizontal=True,
        )

        if "Targeted Asset Finder" in trade_view:
            col_t1, col_t2 = st.columns([1, 1])
            with col_t1:
                action_type = st.selectbox("Action:", ["Target Acquisition (Buy)", "Trade Away (Sell)"])
            with col_t2:
                tolerance_label = st.selectbox("Proposal Tolerance:", ["Strict Fair (0% to 10%)", "Moderate (10% to 20%)", "Aggressive (20% to 30%)"])

            if "Buy" in action_type:
                other_assets = []
                for prof in all_team_profiles:
                    if prof["roster_id"] == user_roster["roster_id"]:
                        continue
                    for p in prof["starters"] + prof["bench"]:
                        if p.get("market_value", 0) > 1000:
                            other_assets.append((f"{p['name']} ({p.get('position', '')} - {prof['manager_name']})", p['name']))
                    for pick in prof.get("picks", []):
                        other_assets.append((f"{pick['name']} ({prof['manager_name']})", pick["name"]))

                other_assets.sort(key=lambda x: x[0])
                if other_assets:
                    selected_asset_label = st.selectbox("Select Asset to Acquire:", [a[0] for a in other_assets])
                    target_query = next(a[1] for a in other_assets if a[0] == selected_asset_label)

                    if st.button("Generate Acquisition Proposals", type="primary"):
                        resolved = resolve_asset_from_query(target_query, all_team_profiles, is_dynasty=is_dynasty)
                        if resolved["found"]:
                            target_asset = resolved["asset"]
                            owners = [o for o in resolved["owners"] if o["profile"]["roster_id"] != user_roster["roster_id"]]
                            if owners:
                                owner_prof = owners[0]["profile"]
                                proposals = find_targeted_buy_trades(
                                    target_asset=target_asset,
                                    owner_profile=owner_prof,
                                    user_profile=user_profile,
                                    primary_lookup=primary_lookup,
                                    roster_positions=roster_pos,
                                    is_dynasty=is_dynasty,
                                    max_proposals=4,
                                )

                                if proposals:
                                    st.success(f"Generated {len(proposals)} trade proposals with **{owner_prof['manager_name']}**:")
                                    for idx, prop in enumerate(proposals, 1):
                                        render_trade_proposal_card(idx, prop)
                                else:
                                    st.info("No proposals matched current roster capital within specified tolerance.")
                        else:
                            st.error("Could not resolve asset.")
                else:
                    st.info("No assets available for acquisition.")

            else:
                user_assets = []
                for p in user_profile["starters"] + user_profile["bench"]:
                    if p.get("market_value", 0) > 1000:
                        user_assets.append((f"{p['name']} ({p.get('position', '')}) — {p.get('market_value', 0):,.0f} pts", p["name"]))
                for pick in user_profile.get("picks", []):
                    user_assets.append((f"{pick['name']} — {pick.get('market_value', 0):,.0f} pts", pick["name"]))

                user_assets.sort(key=lambda x: x[0])
                if user_assets:
                    selected_sell_label = st.selectbox("Select Roster Asset to Trade Away:", [a[0] for a in user_assets])
                    sell_query = next(a[1] for a in user_assets if a[0] == selected_sell_label)

                    if st.button("Find League Trade Partners", type="primary"):
                        resolved = resolve_asset_from_query(sell_query, [user_profile], is_dynasty=is_dynasty)
                        if resolved["found"]:
                            sell_asset = resolved["asset"]
                            other_profs = [p for p in all_team_profiles if p["roster_id"] != user_roster["roster_id"]]
                            sell_proposals = find_targeted_sell_trades(
                                target_asset=sell_asset,
                                user_profile=user_profile,
                                other_profiles=other_profs,
                                primary_lookup=primary_lookup,
                                roster_positions=roster_pos,
                                is_dynasty=is_dynasty,
                                max_partners=4,
                            )

                            if sell_proposals:
                                st.success(f"Found {len(sell_proposals)} trade proposals across the league:")
                                for idx, prop in enumerate(sell_proposals, 1):
                                    render_trade_proposal_card(idx, prop)
                            else:
                                st.info("No partner matches found matching the criteria.")
                        else:
                            st.error("Could not resolve asset.")
                else:
                    st.info("No assets available to trade.")

        else:
            st.markdown("### Automated League-Wide Win-Win Trade Scanner")
            st.caption("Evaluates team strengths, excess depth, and positional surpluses to craft balanced proposals using Model 3 (+15% Stud Premium).")

            other_profs = [p for p in all_team_profiles if p["roster_id"] != user_roster["roster_id"]]
            gen_trades = generate_trade_suggestions(
                user_roster_id=user_roster["roster_id"],
                user_profile=user_profile,
                other_profiles=other_profs,
                is_dynasty=is_dynasty,
                primary_lookup=primary_lookup,
                roster_positions=roster_pos,
                max_suggestions=8,
            )

            if gen_trades:
                st.success(f"Found {len(gen_trades)} viable league trade opportunities:")
                for idx, prop in enumerate(gen_trades[:8], 1):
                    render_trade_proposal_card(idx, prop, show_chat_message=False)
            else:
                st.info("No general trades currently generated under default thresholds.")


    # =========================================================================
    # TAB 6: MARKET RANKINGS & DATABASE
    # =========================================================================
    with tab_market:
        st.subheader("Market Rankings & Player Database")
        st.caption("Explore comprehensive valuations and rankings for all players comparing KeepTradeCut, FantasyCalc, DynastyProcess, and Positional ECR.")

        c_mkt1, c_mkt2 = st.columns([1, 2])
        with c_mkt1:
            pos_mkt = st.selectbox("Position Filter:", ["ALL", "QB", "RB", "WR", "TE", "K", "DEF"], key="mkt_pos_filter")
        with c_mkt2:
            search_mkt = st.text_input("Search Player / Team:", "", key="mkt_search_filter")

        market_rows = []
        for pid, p_data in primary_lookup.items():
            if str(pid).startswith("pick_") or str(pid).isdigit() is False and pos_mkt not in ("DEF", "ALL"):
                if str(pid).startswith("pick_"):
                    continue

            p_obj = players.get(str(pid), {})
            pname = p_obj.get("full_name") or p_data.get("player_name") or str(pid)
            pos = p_obj.get("position") or p_data.get("position") or "UTIL"
            team = p_obj.get("team") or "FA"
            val = p_data.get("market_value", 0.0)
            ecr = p_data.get("rank_ecr_pos", p_data.get("rank_ecr", 999.0))
            o_ecr = p_data.get("rank_ecr_overall", 999.0)
            ktc_v = p_data.get("ktc_val")
            fc_v = p_data.get("fc_val")
            dp_v = p_data.get("dp_val")

            if pos_mkt != "ALL" and pos != pos_mkt:
                continue
            if search_mkt and (search_mkt.lower() not in pname.lower() and search_mkt.lower() not in team.lower()):
                continue

            pos_ecr_str = f"{pos}{int(ecr)}" if (ecr and ecr < 900) else "—"
            overall_ecr_str = f"#{int(o_ecr)}" if (o_ecr and o_ecr < 900) else "—"

            market_rows.append({
                "Avatar": get_player_avatar_url(pid, pos, team),
                "Player": pname,
                "Pos": pos,
                "NFL Team": team,
                "Consensus Value": f"{val:,.0f} pts",
                "Overall ECR": overall_ecr_str,
                "Pos ECR": pos_ecr_str,
                "KeepTradeCut": f"{ktc_v:,.0f}" if ktc_v is not None else "—",
                "FantasyCalc": f"{fc_v:,.0f}" if fc_v is not None else "—",
                "DynastyProcess": f"{dp_v:,.0f}" if dp_v is not None else "—",
                "_val": val,
            })

        market_rows.sort(key=lambda x: x["_val"], reverse=True)

        if market_rows:
            # Add Rank number
            for idx, r in enumerate(market_rows, start=1):
                r["Rank"] = f"#{idx}"

            c_mkview1, c_mkview2 = st.columns([1, 1])
            with c_mkview1:
                mkt_view = st.radio(
                    "Display Format:",
                    ["Standard Table (44px Avatars)", "Interactive Dataframe"],
                    horizontal=True,
                    key="mkt_view_mode",
                )
            with c_mkview2:
                st.caption(f"Showing top {min(len(market_rows), 100)} of {len(market_rows)} matching assets.")

            if mkt_view == "Standard Table (44px Avatars)":
                st.html(render_market_table_html(market_rows[:100]))
            else:
                df_market = pd.DataFrame(market_rows[:150]).drop(columns=["_val"])
                st.dataframe(
                    df_market[["Rank", "Avatar", "Player", "Pos", "NFL Team", "Consensus Value", "Overall ECR", "Pos ECR", "KeepTradeCut", "FantasyCalc", "DynastyProcess"]],
                    column_config={"Avatar": st.column_config.ImageColumn("", width="small")},
                    hide_index=True,
                    use_container_width=True,
                )
        else:
            st.info("No players matched the filter criteria.")


    # =========================================================================
    # TAB 7: MULTI-LEAGUE PORTFOLIO & PLAYER EXPOSURE
    # =========================================================================
    with tab_portfolio:
        st.subheader("Multi-League Portfolio & Player Exposure")
        st.caption("Cross-analyzes all your Sleeper leagues to measure player shares, concentration risk, and your foundation franchise assets.")

        exp_rows, total_user_leagues, l_records = fetch_portfolio_exposure(
            user["user_id"], all_l_ids, all_l_names, players, primary_lookup
        )

        col_exp1, col_exp2, col_exp3 = st.columns(3)
        with col_exp1:
            st.metric("Total Active Leagues", f"{total_user_leagues} Leagues")
        with col_exp2:
            st.metric("Unique Rostered Assets", f"{len(exp_rows)} Players")
        with col_exp3:
            top_share = exp_rows[0]["Shares"] if exp_rows else "—"
            top_name = exp_rows[0]["Player"] if exp_rows else "—"
            st.metric("Highest Portfolio Share", f"{top_name}", f"{top_share} Leagues")

        c_pf1, c_pf2 = st.columns([1, 2])
        with c_pf1:
            pos_port_filter = st.selectbox("Filter Portfolio by Position:", ["ALL", "QB", "RB", "WR", "TE"], key="port_pos_filter")
        with c_pf2:
            search_port = st.text_input("Search Portfolio Player:", "", key="port_search_filter")

        filtered_exp = exp_rows
        if pos_port_filter != "ALL":
            filtered_exp = [r for r in filtered_exp if r["Pos"] == pos_port_filter]
        if search_port:
            filtered_exp = [r for r in filtered_exp if search_port.lower() in r["Player"].lower()]

        if filtered_exp:
            df_exp = pd.DataFrame(filtered_exp)
            df_exp["Consensus Value"] = df_exp["Consensus Value"].apply(lambda v: f"{v:,.0f} pts")
            st.dataframe(
                df_exp[["Avatar", "Player", "Pos", "NFL Team", "Age", "Shares", "Exposure", "Overall ECR", "Pos ECR", "Consensus Value", "Leagues Owned"]],
                column_config={"Avatar": st.column_config.ImageColumn("", width="small")},
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.info("No players matching the portfolio filter criteria.")
