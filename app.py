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

import base64
import concurrent.futures
import copy
import math
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

# Invalidate import caches so Streamlit daemon processes always load fresh src modules
importlib.invalidate_caches()
for _mod_name in [
    "src.sleeper_api",
    "src.market_data",
    "src.matching",
    "src.team_strength",
    "src.analysis_engine",
    "src.trade_engine",
    "src.playoff_simulator",
    "src.start_sit",
    "src.trade_finder",
    "src.draft_picks",
    "src.league_classifier",
    "src.orchestration",
]:
    if _mod_name in sys.modules:
        try:
            importlib.reload(sys.modules[_mod_name])
        except Exception:
            pass

try:
    from src.sleeper_api import (
        get_user,
        get_user_leagues,
        get_league_rosters,
        get_user_roster,
        get_players,
        get_roster_players,
        get_free_agents,
        get_traded_picks,
        get_league_draft_type,
        get_league_users,
        get_nfl_state,
        get_weekly_projections,
        get_weekly_projections_by_week,
        get_weekly_stats,
        get_ros_projections,
        get_league_schedule,
        get_league_matchups,
        get_league_history,
        compute_historical_standings,
        get_nfl_game_status_raw,
        build_team_game_status_map,
    )
except ImportError:
    # Fallback for Streamlit Cloud hot-reload when module cache holds stale objects
    import src.sleeper_api as _s_api
    importlib.reload(_s_api)
    get_user = getattr(_s_api, "get_user")
    get_user_leagues = getattr(_s_api, "get_user_leagues")
    get_league_rosters = getattr(_s_api, "get_league_rosters")
    get_user_roster = getattr(_s_api, "get_user_roster")
    get_players = getattr(_s_api, "get_players")
    get_roster_players = getattr(_s_api, "get_roster_players")
    get_free_agents = getattr(_s_api, "get_free_agents")
    get_traded_picks = getattr(_s_api, "get_traded_picks")
    get_league_draft_type = getattr(_s_api, "get_league_draft_type")
    get_league_users = getattr(_s_api, "get_league_users")
    get_nfl_state = getattr(_s_api, "get_nfl_state")
    get_weekly_projections = getattr(_s_api, "get_weekly_projections")
    get_weekly_projections_by_week = getattr(_s_api, "get_weekly_projections_by_week")
    get_weekly_stats = getattr(_s_api, "get_weekly_stats")
    get_ros_projections = getattr(_s_api, "get_ros_projections")
    get_league_schedule = getattr(_s_api, "get_league_schedule")
    get_league_matchups = getattr(_s_api, "get_league_matchups")
    get_league_history = getattr(_s_api, "get_league_history")
    compute_historical_standings = getattr(_s_api, "compute_historical_standings", lambda lid, r, w: {})
    get_nfl_game_status_raw = getattr(_s_api, "get_nfl_game_status_raw")
    build_team_game_status_map = getattr(_s_api, "build_team_game_status_map")
from src.league_classifier import classify_league, is_superflex_league
from src.market_data import (
    get_fp_rankings_raw,
    get_fp_ros_rankings_raw,
    get_fp_ros_rankings_scraped_at,
    get_player_ids_raw,
    build_positional_lookup,
    get_values_players_raw,
    get_values_picks_raw,
    get_ktc_data_raw,
    get_fantasycalc_data_raw,
    get_ktc_fantasy_rankings_raw,
    build_picks_sources_bundle,
    compute_picks_lookup_from_bundle,
    compute_custom_redraft_lookup,
    compute_market_rank_divergence,
    enrich_lookup_with_consensus_values,
    enrich_lookup_with_redraft_values,
    apply_valuation_mode,
    apply_ktc_te_premium,
    get_market_data_freshness,
    VALUATION_MODES,
)

# Robust import with hot-reload for Streamlit Cloud daemon processes
try:
    import src.market_data
    importlib.reload(src.market_data)
except Exception:
    pass

try:
    import src.matching
    importlib.reload(src.matching)
    from src.matching import match_players_by_sleeper_id, get_player_avatar_url, get_team_logo_url, is_draft_pick_asset
except Exception:
    try:
        from src.matching import match_players_by_sleeper_id, is_draft_pick_asset
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

        def is_draft_pick_asset(player_id, player_name=None, position=None):
            pid_str = str(player_id or "").strip()
            if pid_str in ("8137", "8160"):
                return False
            pos_upper = str(position or "").upper()
            if pos_upper in ("QB", "RB", "WR", "TE", "K", "DEF", "DST"):
                return False
            if pos_upper == "PICK" or pid_str.startswith("FP_") or pid_str.startswith("pick_"):
                return True
            pname_lower = str(player_name or "").lower()
            return any(k in pname_lower for k in [" 1st", " 2nd", " 3rd", " 4th", " round ", "draft pick"])

    def get_player_avatar_url(player_id, position=None, team=None):
        if not player_id:
            return ""
        pos_upper = str(position or "").upper()
        pid_str = str(player_id).strip()
        if is_draft_pick_asset(pid_str, position=pos_upper):
            return ""
        if pos_upper in ("DEF", "DST") or not pid_str.isdigit():
            team_code = (team or pid_str).lower()
            if team_code in ("fa", "—", "") or not team_code.isalpha():
                return ""
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
)
from src.start_sit import (
    calculate_weekly_projected_points,
    simulate_optimal_weekly_lineup,
    audit_weekly_lineup,
    find_streaming_recommendations,
    has_game_started,
    get_player_game_status_label,
    build_live_adjusted_points_lookup,
    build_actual_points_only_lookup,
    sum_points_for_starters,
)
try:
    from src.trade_engine import (
        analyze_team_profile,
        generate_trade_suggestions,
        build_positional_room_leaderboard,
        evaluate_trade_fairness,
        CATEGORY_ROS_WEIGHT,
    )
except ImportError:
    import src.trade_engine as _te
    importlib.reload(_te)
    analyze_team_profile = getattr(_te, "analyze_team_profile")
    generate_trade_suggestions = getattr(_te, "generate_trade_suggestions")
    build_positional_room_leaderboard = getattr(_te, "build_positional_room_leaderboard")
    evaluate_trade_fairness = getattr(_te, "evaluate_trade_fairness")
    CATEGORY_ROS_WEIGHT = getattr(_te, "CATEGORY_ROS_WEIGHT")

try:
    from src.team_strength import (
        rank_teams_in_league,
        get_strength_tier,
        get_current_strength_tier,
        classify_dynasty_team,
        classify_redraft_team,
        percentile_score,
        score_to_tier,
        get_rebuild_ceiling_meta,
        simulate_optimal_lineup,
    )
except ImportError:
    import src.team_strength as _ts
    importlib.reload(_ts)
    rank_teams_in_league = getattr(_ts, "rank_teams_in_league")
    get_strength_tier = getattr(_ts, "get_strength_tier")
    get_current_strength_tier = getattr(_ts, "get_current_strength_tier")
    classify_dynasty_team = getattr(_ts, "classify_dynasty_team")
    classify_redraft_team = getattr(_ts, "classify_redraft_team")
    percentile_score = getattr(_ts, "percentile_score")
    score_to_tier = getattr(_ts, "score_to_tier")
    get_rebuild_ceiling_meta = getattr(_ts, "get_rebuild_ceiling_meta")
    simulate_optimal_lineup = getattr(_ts, "simulate_optimal_lineup")

from src.draft_picks import (
    build_picks_ownership,
    get_picks_for_roster,
    get_picks_capital_value,
    format_picks_summary,
)
try:
    from src.playoff_simulator import (
        compute_team_weekly_expectations,
        run_monte_carlo_simulation,
        compute_ros_power_rankings,
        run_historical_simulation_snapshot,
        compute_weekly_evolution_history,
        compute_elimination_and_clinch_status,
    )
except ImportError:
    import src.playoff_simulator as _ps
    importlib.reload(_ps)
    compute_team_weekly_expectations = getattr(_ps, "compute_team_weekly_expectations")
    run_monte_carlo_simulation = getattr(_ps, "run_monte_carlo_simulation")
    compute_ros_power_rankings = getattr(_ps, "compute_ros_power_rankings")
    run_historical_simulation_snapshot = getattr(_ps, "run_historical_simulation_snapshot")
    compute_weekly_evolution_history = getattr(_ps, "compute_weekly_evolution_history")
    compute_elimination_and_clinch_status = getattr(_ps, "compute_elimination_and_clinch_status")
from src.trade_finder import (
    resolve_asset_from_query,
    find_targeted_buy_trades,
    find_targeted_sell_trades,
)
try:
    from src.orchestration import build_league_context, build_team_profiles
except ImportError:
    import src.orchestration as _orch
    importlib.reload(_orch)
    build_league_context = getattr(_orch, "build_league_context")
    build_team_profiles = getattr(_orch, "build_team_profiles")

DEFAULT_USERNAME = "henriquefrz"
ALLOWED_USERS = ["henriquefrz", "LucasFrazao", "GervasioAceiro"]

# -----------------------------------------------------------------------------
# Streamlit Page Setup & Custom Mobile-Responsive CSS
# -----------------------------------------------------------------------------
LOGO_PATH = "assets/logo.jpg"
LOGO_HORIZONTAL_PATH = "assets/logo_horizontal.png"
ICON_F_YARDS_PATH = "assets/icon_f_yards.png"
PAGE_ICON = ICON_F_YARDS_PATH if os.path.exists(ICON_F_YARDS_PATH) else (LOGO_PATH if os.path.exists(LOGO_PATH) else "🏈")

LOGO_HORIZONTAL_B64 = ""
if os.path.exists(LOGO_HORIZONTAL_PATH):
    try:
        with open(LOGO_HORIZONTAL_PATH, "rb") as _f:
            LOGO_HORIZONTAL_B64 = base64.b64encode(_f.read()).decode("utf-8")
    except Exception:
        LOGO_HORIZONTAL_B64 = ""

ICON_F_YARDS_B64 = ""
if os.path.exists(ICON_F_YARDS_PATH):
    try:
        with open(ICON_F_YARDS_PATH, "rb") as _f:
            ICON_F_YARDS_B64 = base64.b64encode(_f.read()).decode("utf-8")
    except Exception:
        ICON_F_YARDS_B64 = ""

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
    .badge-pick{ background-color: #a855f7; }

    /* Top Bar Brand Logo - clickable as a single centered unit. The visible
       logo (image + wordmark) is static markup; clicking it is handled by a
       real st.button rendered as an invisible overlay on top of it, not an
       <a href> link (a raw link forces a full page reload, which drops
       st.session_state - active league, selected valuation mode, etc.).
       Selectors are scoped under .st-key-topbar_nav_container so they
       out-specificity the mobile ".st-key-topbar_nav_container button" rule
       further down. */
    .st-key-topbar_nav_container .st-key-brand_logo_wrap {
        position: relative !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        width: 100% !important;
    }
    .st-key-topbar_nav_container .st-key-brand_logo_wrap .brand-logo-visual {
        transition: filter 0.15s ease, transform 0.15s ease;
    }
    /* The pre-existing ".st-key-topbar_nav_container div[data-testid='stHtml']"
       rule makes every stHtml block a flex row with no justify-content, which
       left-aligns its content by default. Overridden here (scoped to this
       wrap, so it doesn't affect other topbar stHtml blocks) to actually
       center the logo, since .st-key-brand_logo_wrap's own justify-content
       only centers this stHtml block's own box - which already fills the
       full row width - not the fit-content logo markup inside it. */
    .st-key-topbar_nav_container .st-key-brand_logo_wrap [data-testid="stHtml"] {
        justify-content: center !important;
        width: 100% !important;
    }
    /* Streamlit gives every element-container its own `position: relative`,
       which would otherwise become the button's containing block instead of
       .st-key-brand_logo_wrap above, collapsing it to the button's own
       (tiny, content-sized) box instead of the full logo area. Overriding
       position here on the element-container itself (identified by the
       button's own key= class) fixes that, and takes this element out of
       the row flow so it overlaps the logo instead of sitting beside it. */
    .st-key-topbar_nav_container .st-key-brand_logo_wrap .st-key-brand_home_button {
        position: absolute !important;
        inset: 0 !important;
        width: 100% !important;
        height: 100% !important;
        z-index: 2 !important;
    }
    .st-key-topbar_nav_container .st-key-brand_logo_wrap .st-key-brand_home_button .stButton,
    .st-key-topbar_nav_container .st-key-brand_logo_wrap .st-key-brand_home_button button {
        width: 100% !important;
        height: 100% !important;
    }
    .st-key-topbar_nav_container .st-key-brand_logo_wrap .st-key-brand_home_button button {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        padding: 0 !important;
        margin: 0 !important;
        cursor: pointer !important;
    }
    .st-key-topbar_nav_container .st-key-brand_logo_wrap .st-key-brand_home_button button * {
        font-size: 0 !important;
        line-height: 0 !important;
    }
    .st-key-topbar_nav_container .st-key-brand_logo_wrap:has(.st-key-brand_home_button button:hover) .brand-logo-visual {
        filter: drop-shadow(0 0 10px rgba(56, 189, 248, 0.55));
        transform: scale(1.03);
    }
    .st-key-topbar_nav_container .st-key-brand_logo_wrap:has(.st-key-brand_home_button button:active) .brand-logo-visual {
        transform: scale(0.98);
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

    /* Heads Up Lineup Alerts Wrapper: replicates .card-container.card-alert on a
       real st.container so each league's row can sit directly beside its own
       real st.button (navigation needs a real widget, not <a href> - see
       set_active_workspace comments) instead of every button being clustered
       into one detached row below all the rows, which read as a bare,
       context-less link list disconnected from the detail above it. */
    .st-key-hub_lineup_alerts_wrap {
        border-radius: 10px !important;
        padding: 18px 20px 6px 20px !important;
        margin-bottom: 22px !important;
        border: 1px solid rgba(251, 191, 36, 0.25) !important;
        border-left: 3px solid #f59e0b !important;
        background: linear-gradient(135deg, rgba(245, 158, 11, 0.05) 0%, rgba(15, 23, 42, 0.85) 100%) !important;
        box-shadow: 0 4px 18px rgba(0, 0, 0, 0.35) !important;
    }
    .st-key-hub_lineup_alerts_wrap [data-testid="stHorizontalBlock"] {
        border-top: 1px solid rgba(255, 255, 255, 0.06);
        padding-top: 14px;
        margin-bottom: 8px;
        align-items: center !important;
    }

    /* Top Navigation Bar Container (Option 1: Linear & Vercel Glassmorphism) */
    .st-key-topbar_nav_container {
        background: rgba(15, 23, 42, 0.82) !important;
        backdrop-filter: blur(12px) !important;
        -webkit-backdrop-filter: blur(12px) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 14px !important;
        padding: 6px 18px !important;
        margin-bottom: 20px !important;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.35) !important;
    }
    .st-key-topbar_nav_container div[data-testid="stHorizontalBlock"] {
        align-items: center !important;
        min-height: 48px !important;
    }
    .st-key-topbar_nav_container div[data-testid="column"] {
        display: flex !important;
        flex-direction: column !important;
        justify-content: center !important;
        min-height: 48px !important;
    }
    .st-key-topbar_nav_container div[data-testid="column"] > div[data-testid="stVerticalBlock"] {
        display: flex !important;
        flex-direction: column !important;
        justify-content: center !important;
        gap: 0 !important;
    }
    .st-key-topbar_nav_container .element-container {
        margin: 0 !important;
        padding: 0 !important;
    }
    .st-key-topbar_nav_container div[data-testid="stHtml"] {
        display: flex !important;
        align-items: center !important;
        margin: auto 0 !important;
    }

    /* Streamlit Native Metric Cards */
    div[data-testid="stMetric"] {
        background: #111827;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 10px;
        padding: 12px 16px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
        min-height: 108px !important;
        display: flex !important;
        flex-direction: column !important;
        justify-content: space-between !important;
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

    /* Executive Dark Roster Table with Responsive Touch Scrolling */
    .table-responsive-wrapper {
        width: 100%;
        overflow-x: auto !important;
        -webkit-overflow-scrolling: touch;
        border-radius: 10px;
        border: 1px solid rgba(255, 255, 255, 0.08);
        background: #111827;
        margin-top: 6px;
        margin-bottom: 16px;
    }
    .roster-table {
        width: 100% !important;
        min-width: 680px;
        border-collapse: collapse;
        background: #111827;
        font-size: 0.88rem;
        margin: 0;
    }
    .roster-table-market { min-width: 980px !important; }
    .roster-table-portfolio { min-width: 860px !important; }
    .roster-table-power { min-width: 780px !important; }
    .roster-table-roster { min-width: 700px !important; }
    .roster-table-opponent { min-width: 360px !important; }
    .roster-table-opponent th, .roster-table-opponent td {
        padding: 10px 10px !important;
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
        white-space: nowrap !important;
    }
    .roster-table td {
        padding: 12px 14px;
        vertical-align: middle;
        border-bottom: 1px solid rgba(255, 255, 255, 0.04);
        color: #e2e8f0;
        white-space: nowrap !important;
    }
    .roster-table tr:last-child td {
        border-bottom: none;
    }
    .roster-table tr:hover td {
        background: rgba(255, 255, 255, 0.02);
    }
    .mobile-scroll-hint {
        display: none;
    }
    div[data-testid="stDataFrame"] {
        border-radius: 10px !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        background: #111827 !important;
        overflow: hidden !important;
    }

    /* Matchup Arena & Start/Sit Responsive Components */
    .matchup-arena-card {
        background: linear-gradient(135deg, rgba(15, 23, 42, 0.85) 0%, rgba(10, 15, 30, 0.95) 100%);
        border: 1px solid rgba(56, 189, 248, 0.25);
        border-radius: 12px;
        padding: 20px 24px;
        margin-bottom: 20px;
        box-shadow: 0 4px 18px rgba(0, 0, 0, 0.35);
    }
    .matchup-arena-grid {
        display: grid;
        grid-template-columns: 1fr auto 1fr;
        gap: 16px;
        align-items: center;
    }
    .arena-team-left {
        text-align: left;
    }
    .arena-team-right {
        text-align: right;
    }
    .arena-vs-col {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 8px;
        padding: 0 12px;
    }
    .arena-proj-score {
        font-size: 2.1rem;
        font-weight: 900;
        line-height: 1;
    }
    .start-sit-card {
        background: linear-gradient(135deg, rgba(15, 23, 42, 0.75) 0%, rgba(10, 15, 30, 0.9) 100%);
        border: 1px solid rgba(16, 185, 129, 0.35);
        border-radius: 10px;
        padding: 12px 16px;
        margin-bottom: 10px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
    }
    .start-sit-middle {
        text-align: center;
        flex-shrink: 0;
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
    .player-avatar-36 {
        width: 36px;
        height: 36px;
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
    .market-signal-sell, .market-signal-buy {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.72rem;
        font-weight: 700;
        white-space: nowrap;
    }
    .market-signal-sell {
        background: rgba(248, 113, 113, 0.15);
        color: #f87171;
    }
    .market-signal-buy {
        background: rgba(52, 211, 153, 0.15);
        color: #34d399;
    }
    .market-signal-neutral {
        color: #64748b;
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
        .mobile-scroll-hint {
            display: block !important;
            font-size: 0.70rem;
            color: #64748b;
            margin-bottom: 4px;
            text-align: right;
            font-weight: 600;
        }
        .roster-table th, .roster-table td {
            padding: 8px 10px !important;
            font-size: 0.80rem !important;
        }
        .player-avatar-44 {
            width: 36px !important;
            height: 36px !important;
        }

        /* Mobile Top Bar Glass Framing */
        .st-key-topbar_nav_container {
            padding: 10px 12px !important;
            margin-bottom: 14px !important;
            border-radius: 12px !important;
            border: 1px solid rgba(56, 189, 248, 0.22) !important;
            box-shadow: 0 2px 12px rgba(0, 0, 0, 0.4) !important;
        }

        /* Mobile Top Bar Layout: collapse the 4 stacked full-width blocks
           (brand, league selector, settings, user) into a compact 2x2 grid
           instead of 4 stacked rows - cuts the vertical space roughly in half. */
        .st-key-topbar_nav_container [data-testid="stHorizontalBlock"] {
            display: grid !important;
            grid-template-columns: 1fr 1fr !important;
            gap: 8px !important;
        }
        .st-key-topbar_nav_container [data-testid="column"] {
            width: 100% !important;
            min-width: 0 !important;
            flex: unset !important;
        }
        .st-key-topbar_nav_container [data-testid="stMarkdownContainer"] span {
            font-size: 0.95rem !important;
        }
        .st-key-topbar_nav_container button {
            padding: 6px 10px !important;
            font-size: 0.82rem !important;
        }
        .st-key-topbar_nav_container [data-baseweb="select"] {
            font-size: 0.82rem !important;
        }

        /* Mobile Brand Logo: the 2x2 grid leaves each top-bar cell only
           ~135-160px wide, but the full icon + "Fantasy Analytics" wordmark
           (unscaled) measures ~200px+ - wider than its own grid cell. Since
           .st-key-brand_logo_wrap centers its content, that overflow spills
           out equally on both sides: the icon gets clipped off the left
           edge and the wordmark bleeds into the neighboring column instead
           of wrapping or shrinking. Hiding the wordmark on mobile and
           keeping just the icon/monogram (a common responsive nav pattern)
           guarantees the logo fits its cell at any width without needing
           fragile font-size-vs-column-width tuning, and the click-to-home
           overlay button still covers the same wrap area either way.
           :last-child targets the wordmark span in both real markup shapes
           this renders as: icon image + single wordmark span, or the
           two-span "FA" + "Fantasy Analytics" text-only fallback - in each
           case the wordmark is the last span, so "FA" (or the icon) stays
           visible on its own. */
        .st-key-topbar_nav_container .st-key-brand_logo_wrap .brand-logo-visual span:last-child {
            display: none !important;
        }
        /* Defensive cap for the single-raster horizontal-logo variant (used
           only when the icon asset is missing but a combined logo+wordmark
           image is present) - that markup has no separate text span to hide,
           so it's capped by width instead to the same effect. */
        .st-key-topbar_nav_container .st-key-brand_logo_wrap .brand-logo-visual img {
            max-width: 110px !important;
        }

        /* Mobile Matchup Arena Scoreboard Card */
        .matchup-arena-card {
            padding: 12px !important;
            margin-bottom: 12px !important;
        }
        .matchup-arena-grid {
            display: flex !important;
            flex-direction: column !important;
            gap: 10px !important;
        }
        .arena-team-left, .arena-team-right {
            text-align: left !important;
            width: 100% !important;
            padding: 12px 14px !important;
            background: rgba(15, 23, 42, 0.6) !important;
            border-radius: 10px !important;
            border: 1px solid rgba(255, 255, 255, 0.06) !important;
        }
        .arena-team-left {
            order: 1 !important;
        }
        .arena-vs-col {
            order: 2 !important;
            width: 100% !important;
            flex-direction: column !important;
            align-items: center !important;
            justify-content: center !important;
            padding: 4px 0 !important;
            margin: 0 !important;
            border-top: none !important;
            gap: 6px !important;
        }
        .arena-vs-col div[style*="width: 140px"] {
            width: 100% !important;
            max-width: 220px !important;
            height: 6px !important;
        }
        .arena-team-right {
            order: 3 !important;
            text-align: left !important;
        }
        .arena-team-right .arena-opp-prob-row {
            justify-content: flex-start !important;
        }
        .arena-proj-score {
            font-size: 1.6rem !important;
            font-weight: 900 !important;
        }

        /* Mobile Side-by-Side Lineup Columns: two full lineup tables side by
           side would squeeze each into ~half the screen width, well under
           roster-table-opponent's own min-width, forcing constant horizontal
           scrolling to read either one. Stacking them (my lineup, then the
           opponent's, both still fully visible with no expander click)
           keeps every row legible - same pattern as the topbar's own mobile
           stacking above. */
        .st-key-lineup_vs_columns [data-testid="stHorizontalBlock"] {
            flex-direction: column !important;
        }
        .st-key-lineup_vs_columns [data-testid="column"] {
            width: 100% !important;
            min-width: 0 !important;
            flex: unset !important;
        }

        /* Mobile Start/Sit Card */
        .start-sit-card {
            flex-direction: column !important;
            align-items: stretch !important;
            gap: 10px !important;
            padding: 12px !important;
        }
        .start-sit-middle {
            display: flex !important;
            justify-content: space-between !important;
            align-items: center !important;
            padding-bottom: 8px !important;
            border-bottom: 1px solid rgba(255, 255, 255, 0.08) !important;
            order: 1 !important;
        }
        .start-sit-player-start {
            order: 2 !important;
        }
        .start-sit-player-sit {
            order: 3 !important;
            flex-direction: row !important;
            justify-content: flex-start !important;
        }
        .start-sit-player-sit .start-sit-sit-info {
            text-align: left !important;
        }

        /* Mobile Injury Alert Card */
        .injury-alert-card {
            flex-direction: column !important;
            align-items: flex-start !important;
            gap: 8px !important;
            padding: 10px 12px !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.components.v1.html(
    """
    <script>
    (function() {
        // st.html() strips <script> tags entirely, so this runs inside a
        // components.v1.html iframe instead (same-origin, so window.parent.document
        // is reachable) purely to get real script execution; the listener is
        // attached directly to the PARENT document, not this iframe's own one.
        //
        // Streamlit re-runs this whole block (and recreates this iframe) on every
        // real script rerun, which kills the previous iframe's closures - so a
        // "run once" guard stored on the parent document would leave a dead
        // listener behind with nothing to replace it. Instead, always remove the
        // previous (now-inert) listener and attach a fresh, working one each time.
        var doc = window.parent.document;
        if (doc.__tabScrollFixHandler) {
            doc.removeEventListener('click', doc.__tabScrollFixHandler, true);
        }

        function scrollActiveTabIntoView() {
            var selected = doc.querySelector('[role="tab"][aria-selected="true"]');
            if (selected && typeof selected.scrollIntoView === 'function') {
                selected.scrollIntoView({behavior: 'instant', inline: 'center', block: 'nearest'});
            }
        }

        // Event delegation on document: works for tabs that don't exist yet at
        // attach-time (e.g. after switching leagues), and for both the top-level
        // tab strip and any nested sub-tabs (Franchise Hub, Power Rankings, etc).
        doc.__tabScrollFixHandler = function(e) {
            var tab = e.target.closest && e.target.closest('[role="tab"]');
            if (tab) {
                setTimeout(scrollActiveTabIntoView, 50);
            }
        };
        doc.addEventListener('click', doc.__tabScrollFixHandler, true);
    })();
    </script>
    """,
    height=0,
    width=0,
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


def safe_age_display(age_raw):
    """
    Coerces a raw age value (int, float, numeric string, None, or the "—"
    sentinel) into a clean display string, or "—" when unavailable - some
    players (team defenses, incomplete Sleeper profiles) report no age at
    all, and this keeps a stray `None` from ever leaking into rendered HTML.
    """
    if age_raw is None or age_raw == "—":
        return "—"
    try:
        return str(int(float(age_raw)))
    except (TypeError, ValueError):
        return "—"


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
            <th style='width: 18%; text-align: center;'>Consensus Value</th>
            <th style='width: 60px; text-align: center;'>Age</th>
            <th style='width: 14%; text-align: center;'>Overall ECR</th>
            <th style='width: 14%; text-align: center;'>Pos ECR</th>
            <th style='width: 12%; text-align: center;'>Equity</th>
        """
    else:
        header_cols = """
            <th style='width: 95px; text-align: center;'>Slot</th>
            <th style='width: 38%; text-align: left;'>Player</th>
            <th style='width: 20%; text-align: center;'>Consensus Value</th>
            <th style='width: 65px; text-align: center;'>Age</th>
            <th style='width: 15%; text-align: center;'>Overall ECR</th>
            <th style='width: 15%; text-align: center;'>Pos ECR</th>
        """

    html = f"""
    <div class='mobile-scroll-hint'>↔ Swipe horizontally to view full stats</div>
    <div class='table-responsive-wrapper'>
    <table class='roster-table roster-table-roster'>
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
        age = safe_age_display(r.get("Age"))
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
                <td class='val-pill' style='text-align: center;'>{val}</td>
                <td style='color: #94a3b8; text-align: center;'>{age}</td>
                <td style='text-align: center;'><span class='rank-pill'>{overall_ecr}</span></td>
                <td style='text-align: center;'><span class='rank-pill rank-pill-highlight'>{pos_ecr}</span></td>
                {equity_td}
            </tr>
        """
    html += """
        </tbody>
    </table>
    </div>
    """
    return "\n".join(l.lstrip() for l in html.splitlines())


def render_market_table_html(market_rows, is_redraft: bool = False, show_trajectory: bool = False):
    """
    Renders an executive table for Free Agents or Market Database with 44px avatars,
    spacious rows (~56px), and consensus metrics (dynasty or single-season).

    Owner/Trajectory (the @username who owns this player in the current
    league, and that team's Franchise Trajectory) are secondary,
    at-a-glance columns appended after the core valuation metrics.
    show_trajectory reflects the LEAGUE's own format (is_dynasty), not
    which valuation scope the table is currently browsing (is_redraft): a
    redraft league has no Franchise Trajectory axis to show regardless of
    which value column the user picked.
    """
    if not market_rows:
        return "<p style='color: #94a3b8; font-style: italic; padding: 12px;'>No players to display.</p>"

    owner_th = "<th style='width: 9%; text-align: center;'>Owner</th>"
    trajectory_th = "<th style='width: 10%; text-align: center;' title=\"This team's Franchise Trajectory (current-season strength blended with dynasty asset value)\">Trajectory</th>" if show_trajectory else ""
    age_th = "<th style='width: 60px; text-align: center;'>Age</th>"

    if is_redraft:
        html = f"""
        <div class='mobile-scroll-hint'>↔ Swipe horizontally to view full stats</div>
        <div class='table-responsive-wrapper'>
        <table class='roster-table roster-table-market'>
            <thead>
                <tr>
                    <th style='width: 75px; text-align: center;'>Rank</th>
                    <th style='width: 21%; text-align: left;'>Player</th>
                    {age_th}
                    <th style='width: 13%; text-align: center;'>Single-Season Value</th>
                    <th style='width: 10%; text-align: center;'>Overall Rank</th>
                    <th style='width: 10%; text-align: center;'>Pos Rank</th>
                    <th style='width: 11%; text-align: center;'>Sleeper Proj PPG</th>
                    <th style='width: 11%; text-align: center;'>FantasyPros ECR</th>
                    <th style='width: 11%; text-align: center;'>KTC Redraft Value</th>
                    {owner_th}
                    {trajectory_th}
                </tr>
            </thead>
            <tbody>
        """
    else:
        html = f"""
        <div class='mobile-scroll-hint'>↔ Swipe horizontally to view full stats</div>
        <div class='table-responsive-wrapper'>
        <table class='roster-table roster-table-market'>
            <thead>
                <tr>
                    <th style='width: 75px; text-align: center;'>Rank</th>
                    <th style='width: 20%; text-align: left;'>Player</th>
                    {age_th}
                    <th style='width: 13%; text-align: center;'>Consensus Value</th>
                    <th style='width: 10%; text-align: center;'>Overall Rank</th>
                    <th style='width: 10%; text-align: center;'>Pos Rank</th>
                    <th style='width: 9%; text-align: center;'>KeepTradeCut</th>
                    <th style='width: 9%; text-align: center;'>FantasyCalc</th>
                    <th style='width: 8%; text-align: center;'>DynastyProcess</th>
                    {owner_th}
                    {trajectory_th}
                </tr>
            </thead>
            <tbody>
        """

    for idx, r in enumerate(market_rows, start=1):
        pos = r.get("Pos", "UTIL")
        pname = r.get("Player", "Unknown")
        team = r.get("NFL Team", "FA")
        pid = str(r.get("pid", ""))
        rank_str = r.get("Rank", f"#{idx}")
        overall_ecr = r.get("Overall ECR", "—")
        pos_ecr = r.get("Pos ECR", "—")
        val = r.get("Consensus Value", "0 pts")
        ktc = r.get("KeepTradeCut", "—")
        fc = r.get("FantasyCalc", "—")
        fp = r.get("FantasyPros ECR", "—")
        proj = r.get("Sleeper Proj PPG", "—")
        ktc_redraft = r.get("KTC Redraft Value", "—")
        dp = r.get("DynastyProcess", "—")
        age = safe_age_display(r.get("age"))
        age_cell = f"<td style='text-align: center; color: #94a3b8;'>{age}</td>"

        owner = r.get("Owner", "Free Agent")
        owner_cell = f"<td style='text-align: center; color: #94a3b8;'>{owner}</td>"
        trajectory_cell = ""
        if show_trajectory:
            trajectory = r.get("Trajectory", "—")
            trajectory_cls = {
                "win": "status-contender",
                "neutral": "status-bubble",
                "rebuild": "status-rebuild",
            }.get(r.get("_owner_category"), "")
            trajectory_badge = f"<span class='status-capsule {trajectory_cls}'>{trajectory}</span>" if trajectory_cls else f"<span style='color: #64748b;'>{trajectory}</span>"
            trajectory_cell = f"<td style='text-align: center;'>{trajectory_badge}</td>"

        is_pick = False if is_redraft else is_draft_pick_asset(pid, pname, pos)

        if is_pick:
            avatar_img = "<div class='player-avatar-44' style='background: linear-gradient(135deg, rgba(168, 85, 247, 0.25) 0%, rgba(126, 34, 206, 0.45) 100%); border: 1px solid rgba(168, 85, 247, 0.5); display: flex; flex-direction: column; align-items: center; justify-content: center; color: #d8b4fe; font-size: 0.68rem; font-weight: 800; text-transform: uppercase;'><span>PICK</span></div>"
            badge_cls = "badge-pick"
            pos = "PICK"
            team = "DRAFT"
        else:
            badge_cls = f"badge-{pos.lower()}" if f"badge-{pos.lower()}" in ("badge-qb", "badge-rb", "badge-wr", "badge-te", "badge-k", "badge-def", "badge-pick") else "badge-rb"
            avatar = r.get("Avatar", "")
            if avatar:
                avatar_img = f"<img src='{avatar}' class='player-avatar-44' onerror=\"this.src='https://sleepercdn.com/images/v2/icons/player_default.webp'\" />"
            else:
                avatar_img = "<div class='player-avatar-44' style='display: flex; align-items: center; justify-content: center; font-weight: bold; color: #94a3b8;'>—</div>"

        if is_redraft:
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
                    {age_cell}
                    <td class='val-pill' style='text-align: center; color: #38bdf8;'>{val}</td>
                    <td style='text-align: center;'><span class='rank-pill'>{overall_ecr}</span></td>
                    <td style='text-align: center;'><span class='rank-pill rank-pill-highlight'>{pos_ecr}</span></td>
                    <td style='text-align: center; color: #38bdf8; font-weight: 700;'>{proj}</td>
                    <td style='text-align: center; color: #fbbf24;'>{fp}</td>
                    <td style='text-align: center; color: #f87171; font-weight: 700;'>{ktc_redraft}</td>
                    {owner_cell}
                    {trajectory_cell}
                </tr>
            """
        else:
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
                    {age_cell}
                    <td class='val-pill' style='text-align: center; color: #38bdf8;'>{val}</td>
                    <td style='text-align: center;'><span class='rank-pill'>{overall_ecr}</span></td>
                    <td style='text-align: center;'><span class='rank-pill rank-pill-highlight'>{pos_ecr}</span></td>
                    <td style='text-align: center; color: #94a3b8;'>{ktc}</td>
                    <td style='text-align: center; color: #94a3b8;'>{fc}</td>
                    <td style='text-align: center; color: #94a3b8;'>{dp}</td>
                    {owner_cell}
                    {trajectory_cell}
                </tr>
            """
    html += """
        </tbody>
    </table>
    </div>
    """
    return "\n".join(l.lstrip() for l in html.splitlines())


def render_player_comparison_table_html(comparison_assets, is_redraft: bool = False):
    """
    Renders an executive side-by-side comparison table for 2 or 3 players/picks (dynasty or single-season).
    """
    if not comparison_assets or len(comparison_assets) < 2:
        return ""

    num_p = len(comparison_assets)
    col_w = "25%" if num_p == 3 else "32%"

    headers = "<th style='width: 25%; text-align: left;'>Comparison Metric</th>"
    for p in comparison_assets:
        headers += f"<th style='width: {col_w}; text-align: center; color: #f8fafc;'>{p['name']}</th>"
    headers += "<th style='width: 25%; text-align: center;'>Advantage / Leader</th>"

    # 1. Consensus Value Row
    val_cells = ""
    max_val = max(p.get("val", 0.0) for p in comparison_assets)
    val_leader = next(p for p in comparison_assets if p.get("val", 0.0) == max_val)
    val_runner_up = sorted(comparison_assets, key=lambda x: x.get("val", 0.0), reverse=True)[1]
    v_diff = max_val - val_runner_up.get("val", 0.0)
    v_pct = (v_diff / val_runner_up.get("val", 1.0) * 100) if val_runner_up.get("val", 0) > 0 else 0.0
    val_adv = f"<span style='color: #34d399; font-weight: 700;'>{val_leader['name']} (+{v_diff:,.0f} pts / +{v_pct:.1f}%)</span>" if v_diff > 0 else "<span style='color: #94a3b8;'>Tied</span>"

    for p in comparison_assets:
        v = p.get("val", 0.0)
        is_top = (v == max_val and v_diff > 0)
        color = "#34d399" if is_top else "#cbd5e1"
        weight = "800" if is_top else "600"
        val_cells += f"<td style='text-align: center; font-weight: {weight}; color: {color};'>{v:,.0f} pts</td>"

    # 2. Overall Rank Row
    ovr_cells = ""
    valid_ovrs = [(p, p.get("o_ecr", 999.0)) for p in comparison_assets if p.get("o_ecr") and p.get("o_ecr") < 900]
    if valid_ovrs:
        best_ovr_p, best_ovr_val = min(valid_ovrs, key=lambda x: x[1])
        ovr_adv = f"<span style='color: #38bdf8; font-weight: 700;'>{best_ovr_p['name']} (#{int(best_ovr_val)})</span>"
    else:
        best_ovr_val = None
        ovr_adv = "—"

    for p in comparison_assets:
        o = p.get("o_ecr")
        o_str = f"#{int(o)}" if (o and o < 900) else "—"
        is_best = (o == best_ovr_val and o is not None and o < 900)
        color = "#38bdf8" if is_best else "#94a3b8"
        ovr_cells += f"<td style='text-align: center; font-weight: 700; color: {color};'>{o_str}</td>"

    # 3. Positional Rank Row
    pos_cells = ""
    for p in comparison_assets:
        p_ecr = p.get("p_ecr")
        pos_str = f"{p['pos']}{int(p_ecr)}" if (p_ecr and p_ecr < 900) else "—"
        pos_cells += f"<td style='text-align: center; font-weight: 700; color: #cbd5e1;'>{pos_str}</td>"
    pos_adv = "<span style='color: #94a3b8;'>Per Position Tier</span>"

    # 4. FantasyCalc Row
    fc_cells = ""
    fc_vals = [(p, float(p.get("fc_val") or 0.0)) for p in comparison_assets if p.get("fc_val") is not None]
    if fc_vals and max(x[1] for x in fc_vals) > 0:
        fc_leader, fc_max = max(fc_vals, key=lambda x: x[1])
        fc_adv = f"<span style='color: #34d399; font-weight: 700;'>{fc_leader['name']} ({fc_max:,.0f})</span>"
    else:
        fc_max = None
        fc_adv = "—"

    for p in comparison_assets:
        fv = p.get("fc_val")
        fv_str = f"{float(fv):,.0f}" if fv is not None else "—"
        is_fc_lead = (fv is not None and float(fv) == fc_max and fc_max > 0)
        color = "#34d399" if is_fc_lead else "#94a3b8"
        fc_cells += f"<td style='text-align: center; font-weight: 700; color: {color};'>{fv_str}</td>"

    # 5. Age & Horizon Row
    age_cells = ""
    valid_ages = []
    for p in comparison_assets:
        try:
            a_num = float(p.get("age"))
            valid_ages.append((p, a_num))
        except (ValueError, TypeError):
            pass

    if len(valid_ages) >= 2:
        youngest_p, min_age = min(valid_ages, key=lambda x: x[1])
        oldest_p, max_age = max(valid_ages, key=lambda x: x[1])
        age_adv = f"<span style='color: #34d399; font-weight: 700;'>{youngest_p['name']} ({min_age:.1f} yrs • -{max_age - min_age:.1f}y)</span>" if max_age > min_age else "<span style='color: #94a3b8;'>Equal Age</span>"
    else:
        min_age = None
        age_adv = "—"

    for p in comparison_assets:
        age_disp = f"Age {p.get('age')}" if p.get("age") and str(p.get("age")) != "—" else "—"
        try:
            is_youngest = (float(p.get("age")) == min_age and min_age is not None and len(valid_ages) >= 2 and max_age > min_age)
        except (ValueError, TypeError):
            is_youngest = False
        color = "#34d399" if is_youngest else "#94a3b8"
        age_cells += f"<td style='text-align: center; font-weight: 600; color: {color};'>{age_disp}</td>"

    if is_redraft:
        # Sleeper Projections PPG Row
        proj_cells = ""
        valid_projs = [(p, float(p.get("proj_ppg") or 0.0)) for p in comparison_assets if p.get("proj_ppg") is not None]
        if valid_projs and max(x[1] for x in valid_projs) > 0:
            proj_lead, proj_max = max(valid_projs, key=lambda x: x[1])
            proj_adv = f"<span style='color: #38bdf8; font-weight: 700;'>{proj_lead['name']} ({proj_max:.1f} PPG)</span>"
        else:
            proj_max = None
            proj_adv = "—"
        for p in comparison_assets:
            pj_v = p.get("proj_ppg")
            pj_str = f"{float(pj_v):.1f} PPG" if pj_v is not None else "—"
            is_pj_lead = (pj_v is not None and float(pj_v) == proj_max and proj_max > 0)
            color = "#38bdf8" if is_pj_lead else "#94a3b8"
            proj_cells += f"<td style='text-align: center; font-weight: 700; color: {color};'>{pj_str}</td>"

        # FantasyPros ECR Row
        fp_cells = ""
        valid_fps = [(p, float(p.get("fp_ecr_overall") or 999.0)) for p in comparison_assets if p.get("fp_ecr_overall") and float(p.get("fp_ecr_overall")) < 500]
        if valid_fps:
            fp_lead, fp_min = min(valid_fps, key=lambda x: x[1])
            fp_adv = f"<span style='color: #fbbf24; font-weight: 700;'>{fp_lead['name']} (#{int(fp_min)})</span>"
        else:
            fp_min = None
            fp_adv = "—"
        for p in comparison_assets:
            fp_v = p.get("fp_ecr_overall")
            fp_str = f"#{int(fp_v)}" if (fp_v and float(fp_v) < 500) else "—"
            is_fp_lead = (fp_v and float(fp_v) == fp_min and fp_min is not None)
            color = "#fbbf24" if is_fp_lead else "#94a3b8"
            fp_cells += f"<td style='text-align: center; font-weight: 700; color: {color};'>{fp_str}</td>"

        # KTC Redraft Value Row
        ktc_redraft_cells = ""
        valid_ktc_redraft = [(p, float(p.get("ktc_redraft_val") or 0.0)) for p in comparison_assets if p.get("ktc_redraft_val") is not None]
        if valid_ktc_redraft and max(x[1] for x in valid_ktc_redraft) > 0:
            ktc_redraft_lead, ktc_redraft_max = max(valid_ktc_redraft, key=lambda x: x[1])
            ktc_redraft_adv = f"<span style='color: #f87171; font-weight: 700;'>{ktc_redraft_lead['name']} ({ktc_redraft_max:,.0f} pts)</span>"
        else:
            ktc_redraft_max = None
            ktc_redraft_adv = "—"
        for p in comparison_assets:
            kv = p.get("ktc_redraft_val")
            kv_str = f"{float(kv):,.0f} pts" if kv is not None else "—"
            is_ktc_redraft_lead = (kv is not None and float(kv) == ktc_redraft_max and ktc_redraft_max > 0)
            color = "#f87171" if is_ktc_redraft_lead else "#94a3b8"
            ktc_redraft_cells += f"<td style='text-align: center; font-weight: 700; color: {color};'>{kv_str}</td>"

        rows_html = f"""
            <tr>
                <td style='text-align: left; font-weight: 700; color: #f8fafc;'>Single-Season Consensus Value</td>
                {val_cells}
                <td style='text-align: center;'>{val_adv}</td>
            </tr>
            <tr>
                <td style='text-align: left; font-weight: 700; color: #f8fafc;'>Single-Season Overall Rank</td>
                {ovr_cells}
                <td style='text-align: center;'>{ovr_adv}</td>
            </tr>
            <tr>
                <td style='text-align: left; font-weight: 700; color: #f8fafc;'>Single-Season Pos Rank</td>
                {pos_cells}
                <td style='text-align: center;'>{pos_adv}</td>
            </tr>
            <tr>
                <td style='text-align: left; font-weight: 700; color: #f8fafc;'>Sleeper Projected PPG</td>
                {proj_cells}
                <td style='text-align: center;'>{proj_adv}</td>
            </tr>
            <tr>
                <td style='text-align: left; font-weight: 700; color: #f8fafc;'>FantasyPros Consensus ECR</td>
                {fp_cells}
                <td style='text-align: center;'>{fp_adv}</td>
            </tr>
            <tr>
                <td style='text-align: left; font-weight: 700; color: #f8fafc;'>KTC Redraft Value</td>
                {ktc_redraft_cells}
                <td style='text-align: center;'>{ktc_redraft_adv}</td>
            </tr>
            <tr>
                <td style='text-align: left; font-weight: 700; color: #f8fafc;'>Age & Horizon</td>
                {age_cells}
                <td style='text-align: center;'>{age_adv}</td>
            </tr>
        """
    else:
        # 4. KeepTradeCut Row
        ktc_cells = ""
        ktc_vals = [(p, float(p.get("ktc_val") or 0.0)) for p in comparison_assets if p.get("ktc_val") is not None]
        if ktc_vals and max(x[1] for x in ktc_vals) > 0:
            ktc_leader, ktc_max = max(ktc_vals, key=lambda x: x[1])
            ktc_adv = f"<span style='color: #38bdf8; font-weight: 700;'>{ktc_leader['name']} ({ktc_max:,.0f})</span>"
        else:
            ktc_max = None
            ktc_adv = "—"

        for p in comparison_assets:
            kv = p.get("ktc_val")
            kv_str = f"{float(kv):,.0f}" if kv is not None else "—"
            is_ktc_lead = (kv is not None and float(kv) == ktc_max and ktc_max > 0)
            color = "#38bdf8" if is_ktc_lead else "#94a3b8"
            ktc_cells += f"<td style='text-align: center; font-weight: 700; color: {color};'>{kv_str}</td>"

        # 6. DynastyProcess Row
        dp_cells = ""
        dp_vals = [(p, float(p.get("dp_val") or 0.0)) for p in comparison_assets if p.get("dp_val") is not None]
        if dp_vals and max(x[1] for x in dp_vals) > 0:
            dp_leader, dp_max = max(dp_vals, key=lambda x: x[1])
            dp_adv = f"<span style='color: #c084fc; font-weight: 700;'>{dp_leader['name']} ({dp_max:,.0f})</span>"
        else:
            dp_max = None
            dp_adv = "—"

        for p in comparison_assets:
            dv = p.get("dp_val")
            dv_str = f"{float(dv):,.0f}" if dv is not None else "—"
            is_dp_lead = (dv is not None and float(dv) == dp_max and dp_max > 0)
            color = "#c084fc" if is_dp_lead else "#94a3b8"
            dp_cells += f"<td style='text-align: center; font-weight: 700; color: {color};'>{dv_str}</td>"

        rows_html = f"""
            <tr>
                <td style='text-align: left; font-weight: 700; color: #f8fafc;'>Consensus Market Value</td>
                {val_cells}
                <td style='text-align: center;'>{val_adv}</td>
            </tr>
            <tr>
                <td style='text-align: left; font-weight: 700; color: #f8fafc;'>Consensus Overall Rank</td>
                {ovr_cells}
                <td style='text-align: center;'>{ovr_adv}</td>
            </tr>
            <tr>
                <td style='text-align: left; font-weight: 700; color: #f8fafc;'>Consensus Positional Rank</td>
                {pos_cells}
                <td style='text-align: center;'>{pos_adv}</td>
            </tr>
            <tr>
                <td style='text-align: left; font-weight: 700; color: #f8fafc;'>KeepTradeCut (KTC)</td>
                {ktc_cells}
                <td style='text-align: center;'>{ktc_adv}</td>
            </tr>
            <tr>
                <td style='text-align: left; font-weight: 700; color: #f8fafc;'>FantasyCalc (FC Trades)</td>
                {fc_cells}
                <td style='text-align: center;'>{fc_adv}</td>
            </tr>
            <tr>
                <td style='text-align: left; font-weight: 700; color: #f8fafc;'>DynastyProcess (DP Model)</td>
                {dp_cells}
                <td style='text-align: center;'>{dp_adv}</td>
            </tr>
            <tr>
                <td style='text-align: left; font-weight: 700; color: #f8fafc;'>Age & Horizon</td>
                {age_cells}
                <td style='text-align: center;'>{age_adv}</td>
            </tr>
        """

    html = f"""
    <div class='mobile-scroll-hint'>↔ Swipe horizontally to view full comparison</div>
    <div class='table-responsive-wrapper' style='margin-top: 16px;'>
    <table class='roster-table roster-table-market'>
        <thead>
            <tr>{headers}</tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>
    </div>
    """
    return "\n".join(l.lstrip() for l in html.splitlines())


def render_portfolio_table_html(portfolio_rows):
    """
    Renders Multi-League Portfolio table with 44px round avatars,
    spacious rows (~56px), exposure badge/progress, dual ECR badges, and leagues owned.
    """
    if not portfolio_rows:
        return "<p style='color: #94a3b8; font-style: italic; padding: 12px;'>No players in portfolio.</p>"

    html = """
    <div class='mobile-scroll-hint'>↔ Swipe horizontally to view full stats</div>
    <div class='table-responsive-wrapper'>
    <table class='roster-table roster-table-portfolio'>
        <thead>
            <tr>
                <th style='width: 24%; text-align: left;'>Player</th>
                <th style='width: 10%; text-align: center;'>Exposure</th>
                <th style='width: 9%; text-align: center;'>Dynasty Shares</th>
                <th style='width: 9%; text-align: center;'>Redraft Shares</th>
                <th style='width: 60px; text-align: center;'>Age</th>
                <th style='width: 10%; text-align: center;'>Overall Rank</th>
                <th style='width: 10%; text-align: center;'>Pos Rank</th>
                <th style='width: 13%; text-align: center;'>Consensus Value</th>
                <th style='width: 18%; text-align: left;'>Leagues Owned</th>
            </tr>
        </thead>
        <tbody>
    """
    for r in portfolio_rows:
        pos = r.get("Pos", "UTIL")
        badge_cls = f"badge-{pos.lower()}" if f"badge-{pos.lower()}" in ("badge-qb", "badge-rb", "badge-wr", "badge-te", "badge-k", "badge-def") else "badge-rb"
        avatar = r.get("Avatar", "")
        pname = r.get("Player", "Unknown")
        team = r.get("NFL Team", "FA")
        age = safe_age_display(r.get("Age"))
        shares = r.get("Shares", "—")
        redraft_shares = r.get("Redraft Shares", "—")
        exp = r.get("Exposure", "0%")
        overall_ecr = r.get("Overall ECR", "—")
        pos_ecr = r.get("Pos ECR", "—")
        val = r.get("Consensus Value", "0 pts")
        if isinstance(val, (int, float)):
            val = f"{val:,.0f} pts"
        leagues_str = r.get("Leagues Owned", "")

        avatar_img = f"<img src='{avatar}' class='player-avatar-44' onerror=\"this.src='https://sleepercdn.com/images/v2/icons/player_default.webp'\" />" if avatar else "<div class='player-avatar-44' style='display: flex; align-items: center; justify-content: center; font-weight: bold; color: #94a3b8;'>—</div>"

        html += f"""
            <tr>
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
                <td style='text-align: center;'><span class='rank-pill rank-pill-highlight'>{exp}</span></td>
                <td style='text-align: center; font-weight: 700; color: #f8fafc;'><span class='rank-pill'>{shares}</span></td>
                <td style='text-align: center; color: #94a3b8;'><span class='rank-pill'>{redraft_shares}</span></td>
                <td style='color: #94a3b8; text-align: center;'>{age}</td>
                <td style='text-align: center;'><span class='rank-pill'>{overall_ecr}</span></td>
                <td style='text-align: center;'><span class='rank-pill rank-pill-highlight'>{pos_ecr}</span></td>
                <td class='val-pill' style='text-align: center; color: #38bdf8;'>{val}</td>
                <td style='text-align: left; font-size: 0.78rem; color: #94a3b8; max-width: 250px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;' title='{leagues_str}'>{leagues_str}</td>
            </tr>
        """
    html += """
        </tbody>
    </table>
    </div>
    """
    return "\n".join(l.lstrip() for l in html.splitlines())


def render_picks_table_html(pick_rows, show_equity=False):
    """
    Renders Future Draft Capital Portfolio with purple Draft Pick Shield badges,
    spacious rows (~56px), and consensus market value, matching website theme.
    """
    if not pick_rows:
        return "<p style='color: #94a3b8; font-style: italic; padding: 12px;'>No future draft picks recorded.</p>"

    eq_th = "<th style='width: 15%; text-align: center;'>Equity</th>" if show_equity else ""

    html = f"""
    <div class='mobile-scroll-hint'>↔ Swipe horizontally to view full stats</div>
    <div class='table-responsive-wrapper'>
    <table class='roster-table roster-table-roster'>
        <thead>
            <tr>
                <th style='width: 45%; text-align: left;'>Draft Pick Asset</th>
                <th style='width: 25%; text-align: center;'>Consensus Market Value</th>
                <th style='width: 15%; text-align: center;'>Season</th>
                <th style='width: 15%; text-align: center;'>Round</th>
                {eq_th}
            </tr>
        </thead>
        <tbody>
    """
    for r in pick_rows:
        asset_name = r.get("Draft Pick Asset", "Draft Pick")
        season = r.get("Season", "—")
        round_str = r.get("Round", "—")
        val = r.get("Consensus Market Value", r.get("Consensus Value", "0 pts"))
        eq = r.get("Equity Share", "0.0%")

        avatar_img = "<div class='player-avatar-44' style='background: linear-gradient(135deg, rgba(168, 85, 247, 0.25) 0%, rgba(126, 34, 206, 0.45) 100%); border: 1px solid rgba(168, 85, 247, 0.5); display: flex; flex-direction: column; align-items: center; justify-content: center; color: #d8b4fe; font-size: 0.68rem; font-weight: 800; text-transform: uppercase;'><span>PICK</span></div>"

        eq_td = f"<td style='color: #38bdf8; font-weight: 600; text-align: center;'>{eq}</td>" if show_equity else ""

        html += f"""
            <tr>
                <td style='text-align: left;'>
                    <div class='player-cell'>
                        {avatar_img}
                        <div class='player-info'>
                            <span class='player-name'>{asset_name}</span>
                            <div class='player-meta'>
                                <span class='badge-pos badge-pick' style='font-size: 0.68rem; padding: 1px 5px;'>PICK</span>
                                <span>{season}</span>
                            </div>
                        </div>
                    </div>
                </td>
                <td class='val-pill' style='text-align: center; color: #38bdf8;'>{val}</td>
                <td style='text-align: center; color: #f8fafc; font-weight: 700;'><span class='rank-pill'>{season}</span></td>
                <td style='text-align: center; color: #cbd5e1;'><span class='rank-pill rank-pill-highlight'>{round_str}</span></td>
                {eq_td}
            </tr>
        """
    html += """
        </tbody>
    </table>
    </div>
    """
    return "\n".join(l.lstrip() for l in html.splitlines())


def render_power_simulation_table_html(sim_rows, user_roster_id):
    """
    Renders Season Standings & Playoff Simulation table with subtle cyan highlighting
    for the user's franchise row and real-time Playoff Status badges.
    """
    html = """
    <div class='mobile-scroll-hint'>↔ Swipe horizontally to view full stats</div>
    <div class='table-responsive-wrapper'>
    <table class='roster-table roster-table-power'>
        <thead>
            <tr>
                <th style='width: 60px; text-align: center;'>Rank</th>
                <th style='width: 20%; text-align: left;'>Manager / Team</th>
                <th style='width: 8%; text-align: center;'>Record</th>
                <th style='width: 14%; text-align: center;'>Playoff Status</th>
                <th style='width: 12%; text-align: center;'>Projected W-L</th>
                <th style='width: 10%; text-align: center;'>Starters PPG</th>
                <th style='width: 10%; text-align: center;'>Bench PPG</th>
                <th style='width: 10%; text-align: center;'>Playoff Odds</th>
                <th style='width: 10%; text-align: center;'>1st-Round Bye</th>
                <th style='width: 10%; text-align: center;'>Champ Odds</th>
                <th style='width: 10%; text-align: center;'>Power Score</th>
            </tr>
        </thead>
        <tbody>
    """
    for r in sim_rows:
        is_me = (r.get("roster_id") == user_roster_id)
        row_style = "background: rgba(14, 165, 233, 0.16); border-left: 4px solid #38bdf8;" if is_me else ""
        name_weight = "font-weight: 800; color: #38bdf8;" if is_me else "font-weight: 600; color: #f8fafc;"
        starters_val = r.get("Starters PPG") or r.get("Median PPG", "—")
        bench_val = r.get("Bench PPG", "—")

        # Format Playoff Status badge
        status_label = r.get("Status", "In The Hunt")
        badge_icon = r.get("badge_icon", "🎯")
        status_code = r.get("status_code", "HUNT")

        if status_code == "CLINCHED":
            badge_bg = "rgba(16, 185, 129, 0.15)"
            badge_border = "rgba(52, 211, 153, 0.35)"
            badge_text = "#34d399"
        elif status_code == "ELIMINATED":
            badge_bg = "rgba(244, 63, 94, 0.15)"
            badge_border = "rgba(251, 113, 133, 0.35)"
            badge_text = "#fb7185"
        elif status_code == "DANGER":
            badge_bg = "rgba(245, 158, 11, 0.15)"
            badge_border = "rgba(251, 191, 36, 0.35)"
            badge_text = "#fbbf24"
        elif status_code == "CONTENDER":
            badge_bg = "rgba(6, 182, 212, 0.15)"
            badge_border = "rgba(56, 189, 248, 0.35)"
            badge_text = "#38bdf8"
        else:
            badge_bg = "rgba(59, 130, 246, 0.15)"
            badge_border = "rgba(96, 165, 250, 0.35)"
            badge_text = "#60a5fa"

        status_pill = f"<span class='rank-pill' style='background: {badge_bg}; color: {badge_text}; border: 1px solid {badge_border}; font-weight: 700; white-space: nowrap;'>{badge_icon} {status_label}</span>"

        html += f"""
        <tr style='{row_style}'>
            <td style='text-align: center; color: #94a3b8; font-weight: 700;'>{r['Rank']}</td>
            <td style='text-align: left; {name_weight}'>{r['Manager / Team']}</td>
            <td style='text-align: center; color: #e2e8f0; font-weight: 700;'>{r.get('Record', '—')}</td>
            <td style='text-align: center;'>{status_pill}</td>
            <td style='text-align: center; font-weight: 600;'>{r['Projected W-L']}</td>
            <td style='text-align: center; color: #38bdf8; font-weight: 700;'>{starters_val}</td>
            <td style='text-align: center; color: #94a3b8;'>{bench_val}</td>
            <td style='text-align: center;'><span class='rank-pill rank-pill-highlight'>{r['Playoff Odds']}</span></td>
            <td style='text-align: center;'><span class='rank-pill'>{r['1st-Round Bye']}</span></td>
            <td style='text-align: center;'><span class='rank-pill' style='color: #c084fc;'>{r['Champ Odds']}</span></td>
            <td class='val-pill' style='text-align: center;'>{r['Season Power Score']}</td>
        </tr>
        """
    html += """
        </tbody>
    </table>
    </div>
    """
    return "\n".join(l.lstrip() for l in html.splitlines())


def render_dynasty_power_table_html(dyn_rows, user_roster_id):
    """
    Renders Dynasty Asset Power Rankings table with subtle cyan highlighting
    for the user's franchise row, eliminating text clutter.
    """
    html = """
    <div class='mobile-scroll-hint'>↔ Swipe horizontally to view full stats</div>
    <div class='table-responsive-wrapper'>
    <table class='roster-table roster-table-power'>
        <thead>
            <tr>
                <th style='width: 70px; text-align: center;'>Rank</th>
                <th style='width: 28%; text-align: left;'>Manager / Team</th>
                <th style='width: 14%; text-align: center;'>Dynasty Score</th>
                <th style='width: 14%; text-align: center;'>Starters (50%)</th>
                <th style='width: 14%; text-align: center;'>Bench (30%)</th>
                <th style='width: 14%; text-align: center;'>Picks (20%)</th>
                <th style='width: 16%; text-align: center;'>Tier</th>
            </tr>
        </thead>
        <tbody>
    """
    for r in dyn_rows:
        is_me = (r.get("roster_id") == user_roster_id)
        row_style = "background: rgba(14, 165, 233, 0.16); border-left: 4px solid #38bdf8;" if is_me else ""
        name_weight = "font-weight: 800; color: #38bdf8;" if is_me else "font-weight: 600; color: #f8fafc;"
        tier = r.get("Competitive Tier", "Active")
        # Color by the actual win/neutral/rebuild category (not a substring
        # match on the tier name), since most granular tier names - e.g.
        # "Dominant Empire", "Win-Now Favorite", "Productive Struggle" -
        # don't literally contain the words "Contender" or "Rebuild".
        cat = r.get("Category", "neutral")
        tier_cls = "status-contender" if cat == "win" else ("status-rebuild" if cat == "rebuild" else "status-bubble")
        html += f"""
        <tr style='{row_style}'>
            <td style='text-align: center; color: #94a3b8; font-weight: 700;'>{r['Rank']}</td>
            <td style='text-align: left; {name_weight}'>{r['Manager / Team']}</td>
            <td class='val-pill' style='text-align: center; color: #38bdf8;'>{r['Dynasty Score']}</td>
            <td style='text-align: center;'>{r['Starters Val (50%)']}</td>
            <td style='text-align: center; color: #94a3b8;'>{r['Bench Val (30%)']}</td>
            <td style='text-align: center; color: #c084fc;'>{r['Picks Capital (20%)']}</td>
            <td style='text-align: center;'><span class='status-capsule {tier_cls}'>{tier}</span></td>
        </tr>
        """
    html += """
        </tbody>
    </table>
    </div>
    """
    return "\n".join(l.lstrip() for l in html.splitlines())


def render_ros_power_table_html(ros_rows, user_roster_id):
    """
    Renders Rest-of-Season (ROS) Asset Power Rankings table with subtle cyan highlighting
    for the user's franchise row, displaying 85% Starters + 15% Bench consensus values.
    """
    html = """
    <div class='mobile-scroll-hint'>↔ Swipe horizontally to view full stats</div>
    <div class='table-responsive-wrapper'>
    <table class='roster-table roster-table-power'>
        <thead>
            <tr>
                <th style='width: 70px; text-align: center;'>Rank</th>
                <th style='width: 26%; text-align: left;'>Manager / Team</th>
                <th style='width: 15%; text-align: center;'>ROS Score</th>
                <th style='width: 15%; text-align: center;'>Starters (85%)</th>
                <th style='width: 15%; text-align: center;'>Bench (15%)</th>
                <th style='width: 15%; text-align: center;'>Total ROS Value</th>
                <th style='width: 14%; text-align: center;'>Tier</th>
            </tr>
        </thead>
        <tbody>
    """
    for r in ros_rows:
        is_me = (r.get("roster_id") == user_roster_id)
        row_style = "background: rgba(14, 165, 233, 0.16); border-left: 4px solid #38bdf8;" if is_me else ""
        name_weight = "font-weight: 800; color: #38bdf8;" if is_me else "font-weight: 600; color: #f8fafc;"
        tier = r.get("Competitive Tier", "Active")
        # Color by the actual win/neutral/rebuild category (not a substring
        # match on the tier name), since most granular tier names - e.g.
        # "Dominant Empire", "Win-Now Favorite", "Productive Struggle" -
        # don't literally contain the words "Contender" or "Rebuild".
        cat = r.get("Category", "neutral")
        tier_cls = "status-contender" if cat == "win" else ("status-rebuild" if cat == "rebuild" else "status-bubble")
        html += f"""
        <tr style='{row_style}'>
            <td style='text-align: center; color: #94a3b8; font-weight: 700;'>{r['Rank']}</td>
            <td style='text-align: left; {name_weight}'>{r['Manager / Team']}</td>
            <td class='val-pill' style='text-align: center; color: #38bdf8;'>{r['ROS Score']}</td>
            <td style='text-align: center;'>{r['Starters Val (85%)']}</td>
            <td style='text-align: center; color: #94a3b8;'>{r['Bench Val (15%)']}</td>
            <td style='text-align: center; color: #38bdf8; font-weight: 600;'>{r['Total ROS Value']}</td>
            <td style='text-align: center;'><span class='status-capsule {tier_cls}'>{tier}</span></td>
        </tr>
        """
    html += """
        </tbody>
    </table>
    </div>
    """
    return "\n".join(l.lstrip() for l in html.splitlines())


def render_positional_room_table_html(room_rows, user_roster_id, sort_col="total_val", show_picks: bool = True):
    """
    Renders the League-Wide Positional Room Leaderboard table.
    Highlights user's franchise row, and displays rank pills for each position room.
    When show_picks=False (e.g. Redraft leagues or ROS scope), excludes Draft Capital column.

    There is no single fixed "most important" column here - comparing QB/RB/WR/TE
    rooms side by side is the whole point of the table. Instead, whichever column
    matches the active sort_col is moved right after Manager/Team, so the metric
    the user is currently sorting by is always visible on mobile without swiping.
    """
    def rank_pill(rank_val, is_active_col=False):
        if rank_val <= 3:
            bg = "rgba(16, 185, 129, 0.15)"
            color = "#34d399"
            border = "rgba(16, 185, 129, 0.4)"
        elif rank_val <= 6:
            bg = "rgba(14, 165, 233, 0.15)"
            color = "#38bdf8"
            border = "rgba(14, 165, 233, 0.4)"
        else:
            bg = "rgba(148, 163, 184, 0.10)"
            color = "#94a3b8"
            border = "rgba(148, 163, 184, 0.25)"
        hl_style = "border: 1px solid #38bdf8; font-weight: 800;" if is_active_col else f"border: 1px solid {border};"
        return f"<span style='background: {bg}; color: {color}; {hl_style} border-radius: 4px; padding: 1px 6px; font-size: 0.70rem; font-weight: 700; margin-left: 4px;'>#{rank_val}</span>"

    total_label = "Total Franchise" if show_picks else "Total Roster"

    # Data-driven column definitions in their default order. The one matching
    # sort_col gets moved to the front (right after Manager/Team) below.
    columns = [
        ("qb_val", "QB Room", lambda r: f"<span style='color: #f8fafc; font-weight: 700;'>{r['qb_val']:,.0f}</span> {rank_pill(r['qb_rank'], sort_col == 'qb_val')}"),
        ("rb_val", "RB Room", lambda r: f"<span style='color: #f8fafc; font-weight: 700;'>{r['rb_val']:,.0f}</span> {rank_pill(r['rb_rank'], sort_col == 'rb_val')}"),
        ("wr_val", "WR Room", lambda r: f"<span style='color: #f8fafc; font-weight: 700;'>{r['wr_val']:,.0f}</span> {rank_pill(r['wr_rank'], sort_col == 'wr_val')}"),
        ("te_val", "TE Room", lambda r: f"<span style='color: #f8fafc; font-weight: 700;'>{r['te_val']:,.0f}</span> {rank_pill(r['te_rank'], sort_col == 'te_val')}"),
    ]
    if show_picks:
        columns.append(("picks_val", "Draft Capital", lambda r: f"<span style='color: #c084fc; font-weight: 700;'>{r['picks_val']:,.0f}</span> {rank_pill(r['picks_rank'], sort_col == 'picks_val')}"))
    columns.append(("total_val", total_label, lambda r: f"<span class='val-pill' style='color: #38bdf8; font-weight: 800;'>{r['total_val']:,.0f}</span> {rank_pill(r['total_rank'], sort_col == 'total_val')}"))

    active_idx = next((i for i, c in enumerate(columns) if c[0] == sort_col), None)
    if active_idx is not None and active_idx != 0:
        columns.insert(0, columns.pop(active_idx))

    col_width = "13%" if show_picks else "15%"
    name_col_width = "22%" if show_picks else "25%"
    header_cells = "".join(f"<th style='width: {col_width}; text-align: center;'>{label}</th>" for _, label, _ in columns)
    headers_html = f"""
                <th style='width: 65px; text-align: center;'>Rank</th>
                <th style='width: {name_col_width}; text-align: left;'>Manager / Team</th>
                {header_cells}
    """

    html = f"""
    <div class='mobile-scroll-hint'>↔ Swipe horizontally to view full room rankings</div>
    <div class='table-responsive-wrapper'>
    <table class='roster-table roster-table-power'>
        <thead>
            <tr>
                {headers_html}
            </tr>
        </thead>
        <tbody>
    """

    for r in room_rows:
        is_me = (r.get("roster_id") == user_roster_id)
        row_style = "background: rgba(14, 165, 233, 0.16); border-left: 4px solid #38bdf8;" if is_me else ""
        name_weight = "font-weight: 800; color: #38bdf8;" if is_me else "font-weight: 600; color: #f8fafc;"
        rank_disp = r.get("disp_rank", r.get("total_rank", 1))

        row_cells = "".join(f"<td style='text-align: center;'>{cell_fn(r)}</td>" for _, _, cell_fn in columns)

        html += f"""
        <tr style='{row_style}'>
            <td style='text-align: center; color: #94a3b8; font-weight: 700;'>#{rank_disp}</td>
            <td style='text-align: left; {name_weight}'>{r['manager_name']}</td>
            {row_cells}
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


LIVE_STATUS_BADGES = {
    "in_progress": "<span style='color: #fb7185; font-weight: 700;'>🔴 Live</span>",
    "final": "<span style='color: #34d399; font-weight: 700;'>✅ Final</span>",
    "not_started": "<span style='color: #94a3b8;'>⏳ Not Started</span>",
    "bye": "<span style='color: #64748b;'>— Bye</span>",
}


def render_live_status_badge_html(status_label):
    """Renders the live-score status badge for a player's game this week (see get_player_game_status_label)."""
    return LIVE_STATUS_BADGES.get(status_label, LIVE_STATUS_BADGES["bye"])


def render_opponent_lineup_html(opp_rows):
    """
    Renders a starting lineup table (opponent or the user's own) with 36px
    avatars, clean row spacing, and a live-status column when rows carry a
    "Status" key (see render_live_status_badge_html) - omitted otherwise.
    NFL team is folded into a subtitle line under the player name rather
    than its own column - keeps every field visible in a table narrow
    enough to sit two-up (side-by-side lineups) without horizontal scroll.
    """
    if not opp_rows:
        return "<p style='color: #94a3b8; padding: 8px;'>No lineup available.</p>"
    show_status = any("Status" in r for r in opp_rows)
    status_th = "<th>Status</th>" if show_status else ""
    html = f"""
    <div class='mobile-scroll-hint'>↔ Swipe horizontally to view full stats</div>
    <div class='table-responsive-wrapper'>
    <table class='roster-table roster-table-opponent'>
        <thead>
            <tr>
                <th style='width: 56px;'>Slot</th>
                <th>Player</th>
                <th>Proj.</th>
                {status_th}
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
        status_td = f"<td>{render_live_status_badge_html(r['Status'])}</td>" if show_status and "Status" in r else ("<td>—</td>" if show_status else "")
        avatar_img = f"<img src='{avatar}' class='player-avatar-36' onerror=\"this.src='https://sleepercdn.com/images/v2/icons/player_default.webp'\" />" if avatar else "<div class='player-avatar-36' style='display: flex; align-items: center; justify-content: center; font-weight: bold; color: #94a3b8;'>—</div>"
        html += f"""
            <tr>
                <td><span class='badge-pos badge-rb'>{slot}</span></td>
                <td>
                    <div class='player-cell'>
                        {avatar_img}
                        <div class='player-info'>
                            <span class='player-name'>{pname}</span>
                            <span class='player-meta'>{team}</span>
                        </div>
                    </div>
                </td>
                <td class='val-pill' style='color: #38bdf8;'>{proj}</td>
                {status_td}
            </tr>
        """
    html += """
        </tbody>
    </table>
    </div>
    """
    return "\n".join(l.lstrip() for l in html.splitlines())


def render_matchup_arena_html(user_name, user_actual, user_proj, user_ceiling, opp_name, opp_actual, opp_proj, active_week):
    """
    user_actual/opp_actual: real points scored so far by starters whose game
    has already started, zero for anyone who hasn't played yet (see
    build_actual_points_only_lookup) - a live scoreboard reading.
    user_proj/opp_proj: the live-adjusted best-guess final score (see
    build_live_adjusted_points_lookup) - real points for started players,
    static projection for the rest. Win chance and the point spread are
    still driven by user_proj/opp_proj, not the actual-only score, since
    they estimate the final result rather than report what's happened so far.
    """
    diff = user_proj - opp_proj
    if diff >= 0:
        spread_badge = f"<span style='background: rgba(16, 185, 129, 0.18); border: 1px solid rgba(16, 185, 129, 0.4); color: #34d399; padding: 4px 10px; border-radius: 6px; font-size: 0.74rem; font-weight: 800; letter-spacing: 0.04em;'>+{diff:.1f} PTS FAVORED</span>"
    else:
        spread_badge = f"<span style='background: rgba(245, 158, 11, 0.18); border: 1px solid rgba(245, 158, 11, 0.4); color: #fbbf24; padding: 4px 10px; border-radius: 6px; font-size: 0.74rem; font-weight: 800; letter-spacing: 0.04em;'>{diff:.1f} PTS UNDERDOG</span>"

    # Sleeper-calibrated matchup win probability (normal distribution CDF, sigma=20.0 pts)
    user_win_prob = 0.5 * (1.0 + math.erf(diff / (20.0 * math.sqrt(2)))) * 100.0
    user_win_prob = max(1.0, min(99.0, round(user_win_prob, 1)))
    opp_win_prob = round(100.0 - user_win_prob, 1)

    arena_html = f"""
    <div class='matchup-arena-card'>
        <div class='matchup-arena-grid'>
            <!-- User Franchise -->
            <div class='arena-team-left'>
                <div style='font-size: 0.7rem; font-weight: 800; color: #38bdf8; text-transform: uppercase; letter-spacing: 0.05em;'>YOUR FRANCHISE</div>
                <div style='font-size: 1.15rem; font-weight: 900; color: #f8fafc; margin: 3px 0 6px 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;'>{user_name}</div>
                <div class='arena-proj-score' style='color: #38bdf8;'>{user_actual:.1f} <span style='font-size: 0.8rem; font-weight: 600; color: #64748b;'>CURRENT</span></div>
                <div style='font-size: 0.78rem; color: #94a3b8; margin-top: 2px;'>Proj. Final: <strong style='color: #cbd5e1;'>{user_proj:.1f} pts</strong></div>
                <div style='display: flex; align-items: center; gap: 6px; margin-top: 5px;'>
                    <span style='background: rgba(56, 189, 248, 0.15); border: 1px solid rgba(56, 189, 248, 0.35); color: #38bdf8; font-size: 0.72rem; font-weight: 800; padding: 2px 8px; border-radius: 9999px;'>{user_win_prob:.0f}% WIN CHANCE</span>
                </div>
                <div style='font-size: 0.76rem; color: #94a3b8; margin-top: 6px;'>Optimal Ceiling: <strong style='color: #f8fafc;'>{user_ceiling:.1f} pts</strong></div>
            </div>

            <!-- VS, Spread & Win Prob Bar -->
            <div class='arena-vs-col' style='display: flex; flex-direction: column; align-items: center; gap: 8px;'>
                <div style='background: rgba(30, 41, 59, 0.9); border: 1px solid rgba(51, 65, 85, 0.8); border-radius: 9999px; padding: 4px 12px; font-weight: 900; font-size: 0.95rem; color: #94a3b8; letter-spacing: 0.05em;'>VS</div>
                {spread_badge}
                <div style='width: 140px; height: 6px; background: rgba(255,255,255,0.08); border-radius: 3px; overflow: hidden; display: flex; margin-top: 4px;' title='Win Probability: {user_win_prob:.0f}% vs {opp_win_prob:.0f}%'>
                    <div style='width: {user_win_prob}%; background: #38bdf8; height: 100%;'></div>
                    <div style='width: {opp_win_prob}%; background: #64748b; height: 100%;'></div>
                </div>
            </div>

            <!-- Opponent Franchise -->
            <div class='arena-team-right'>
                <div style='font-size: 0.7rem; font-weight: 800; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em;'>OPPONENT</div>
                <div style='font-size: 1.15rem; font-weight: 900; color: #f8fafc; margin: 3px 0 6px 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;'>{opp_name}</div>
                <div class='arena-proj-score' style='color: #f8fafc;'>{opp_actual:.1f} <span style='font-size: 0.8rem; font-weight: 600; color: #64748b;'>CURRENT</span></div>
                <div style='font-size: 0.78rem; color: #94a3b8; margin-top: 2px;'>Proj. Final: <strong style='color: #cbd5e1;'>{opp_proj:.1f} pts</strong></div>
                <div class='arena-opp-prob-row' style='display: flex; align-items: center; justify-content: flex-end; gap: 6px; margin-top: 5px;'>
                    <span style='background: rgba(148, 163, 184, 0.12); border: 1px solid rgba(148, 163, 184, 0.25); color: #cbd5e1; font-size: 0.72rem; font-weight: 800; padding: 2px 8px; border-radius: 9999px;'>{opp_win_prob:.0f}% WIN CHANCE</span>
                </div>
                <div style='font-size: 0.76rem; color: #64748b; margin-top: 6px;'>Week {active_week} Matchup</div>
            </div>
        </div>
    </div>
    """
    return "\n".join(l.lstrip() for l in arena_html.splitlines())


def render_start_sit_card_html(swap):
    st_p = swap["start_player"]
    sit_p = swap["sit_player"]
    gain = swap["gain"]
    slot = swap["slot"]

    st_avatar = get_player_avatar_url(st_p.get("player_id"), st_p.get("position"), st_p.get("team"))
    sit_avatar = get_player_avatar_url(sit_p.get("player_id"), sit_p.get("position"), sit_p.get("team"))

    card_html = f"""
    <div class='start-sit-card'>
        <!-- Net Gain & Slot Pill -->
        <div class='start-sit-middle'>
            <div style='background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.4); color: #34d399; padding: 3px 10px; border-radius: 6px; font-size: 0.78rem; font-weight: 800;'>+{gain:.1f} PTS GAIN</div>
            <div style='font-size: 0.7rem; color: #64748b; margin-top: 3px; font-weight: 600;'>Slot: {slot}</div>
        </div>

        <!-- START Player -->
        <div class='start-sit-player-start' style='display: flex; align-items: center; gap: 10px;'>
            <span style='background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.5); font-size: 0.68rem; font-weight: 900; padding: 3px 7px; border-radius: 4px;'>START</span>
            <img src='{st_avatar}' class='player-avatar-44' onerror=\"this.src='https://sleepercdn.com/images/v2/icons/player_default.webp'\" />
            <div>
                <div style='font-size: 0.92rem; font-weight: 800; color: #f8fafc;'>{st_p.get("full_name")}</div>
                <div style='font-size: 0.74rem; color: #94a3b8;'>{st_p.get("position")} • {st_p.get("team") or "FA"} • <strong style='color: #34d399;'>{swap["start_proj"]:.1f} pts</strong></div>
            </div>
        </div>

        <!-- SIT Player -->
        <div class='start-sit-player-sit' style='display: flex; align-items: center; gap: 10px;'>
            <span style='background: rgba(244, 63, 94, 0.15); color: #fb7185; border: 1px solid rgba(244, 63, 94, 0.35); font-size: 0.68rem; font-weight: 900; padding: 3px 7px; border-radius: 4px;'>SIT</span>
            <img src='{sit_avatar}' class='player-avatar-44' style='opacity: 0.75;' onerror=\"this.src='https://sleepercdn.com/images/v2/icons/player_default.webp'\" />
            <div class='start-sit-sit-info'>
                <div style='font-size: 0.92rem; font-weight: 800; color: #cbd5e1;'>{sit_p.get("full_name")}</div>
                <div style='font-size: 0.74rem; color: #64748b;'>{sit_p.get("position")} • {sit_p.get("team") or "FA"} • {swap["sit_proj"]:.1f} pts</div>
            </div>
        </div>
    </div>
    """
    return "\n".join(l.lstrip() for l in card_html.splitlines())


# -----------------------------------------------------------------------------
# Cached Data Fetching
# -----------------------------------------------------------------------------
@st.cache_data(ttl=86400, show_spinner=False)
def fetch_market_database(_cache_version="v28_market_rank_divergence"):
    """Fetches all foundational market datasets and raw API feeds once per 24 hours."""
    players = get_players()
    fp_rankings = get_fp_rankings_raw()
    fp_ros_rankings = get_fp_ros_rankings_raw()
    player_ids = get_player_ids_raw()
    values_players = get_values_players_raw()
    values_picks = get_values_picks_raw()

    nfl_state = get_nfl_state() or {}
    season = nfl_state.get("season", "2026")
    week = max(1, nfl_state.get("week", 1))

    ktc_sf = get_ktc_data_raw(is_superflex=True)
    ktc_1qb = get_ktc_data_raw(is_superflex=False)
    fc_sf = get_fantasycalc_data_raw(is_dynasty=True, is_superflex=True)
    fc_1qb = get_fantasycalc_data_raw(is_dynasty=True, is_superflex=False)
    ktc_redraft_sf = get_ktc_fantasy_rankings_raw(is_superflex=True)
    ktc_redraft_1qb = get_ktc_fantasy_rankings_raw(is_superflex=False)

    projections_raw = get_weekly_projections(season, week)
    ros_projections_raw = get_ros_projections(season, start_week=week, end_week=17)

    # Positional lookups with raw constituent values preserved
    base_dynasty_sf = build_positional_lookup(fp_rankings, player_ids, "dynasty", is_superflex=True)
    try:
        enrich_lookup_with_consensus_values(base_dynasty_sf, values_players, player_ids, ktc_raw=ktc_sf, fc_raw=fc_sf, is_superflex=True, mode="equal", values_picks_raw=values_picks)
    except TypeError:
        enrich_lookup_with_consensus_values(base_dynasty_sf, values_players, player_ids, ktc_raw=ktc_sf, fc_raw=fc_sf, is_superflex=True, mode="equal")
    market_signal_info_sf = compute_market_rank_divergence(base_dynasty_sf)

    base_dynasty_1qb = build_positional_lookup(fp_rankings, player_ids, "dynasty", is_superflex=False)
    try:
        enrich_lookup_with_consensus_values(base_dynasty_1qb, values_players, player_ids, ktc_raw=ktc_1qb, fc_raw=fc_1qb, is_superflex=False, mode="equal", values_picks_raw=values_picks)
    except TypeError:
        enrich_lookup_with_consensus_values(base_dynasty_1qb, values_players, player_ids, ktc_raw=ktc_1qb, fc_raw=fc_1qb, is_superflex=False, mode="equal")
    market_signal_info_1qb = compute_market_rank_divergence(base_dynasty_1qb)

    base_redraft = build_positional_lookup(fp_ros_rankings, player_ids, "redraft", is_superflex=False)
    enrich_lookup_with_redraft_values(
        base_redraft,
        ktc_fantasy_raw=ktc_redraft_1qb,
        projections_raw=ros_projections_raw,
        player_ids_raw=player_ids,
        start_week=week,
        end_week=17,
    )

    # Raw pick bundles for instant mode switching
    picks_bundle_sf = build_picks_sources_bundle(values_picks, values_players, ktc_raw=ktc_sf, fc_raw=fc_sf, is_superflex=True)
    picks_bundle_1qb = build_picks_sources_bundle(values_picks, values_players, ktc_raw=ktc_1qb, fc_raw=fc_1qb, is_superflex=False)

    freshness_info = get_market_data_freshness(
        fp_rankings, values_players,
        ktc_sf=ktc_sf, ktc_1qb=ktc_1qb, fc_sf=fc_sf, fc_1qb=fc_1qb,
        ktc_redraft_sf=ktc_redraft_sf, ktc_redraft_1qb=ktc_redraft_1qb,
        fp_ros_rows=fp_ros_rankings, fp_ros_scraped_at=get_fp_ros_rankings_scraped_at(),
    )

    return {
        "players": players,
        "player_ids": player_ids,
        "fp_rankings": fp_rankings,
        "fp_ros_rankings": fp_ros_rankings,
        "values_players": values_players,
        "values_picks": values_picks,
        "ktc_sf": ktc_sf,
        "ktc_1qb": ktc_1qb,
        "fc_sf": fc_sf,
        "fc_1qb": fc_1qb,
        "ktc_redraft_sf": ktc_redraft_sf,
        "ktc_redraft_1qb": ktc_redraft_1qb,
        "projections_raw": projections_raw,
        "ros_projections_raw": ros_projections_raw,
        "dynasty_sf_lookup": base_dynasty_sf,
        "dynasty_1qb_lookup": base_dynasty_1qb,
        "redraft_lookup": base_redraft,
        "picks_bundle_sf": picks_bundle_sf,
        "picks_bundle_1qb": picks_bundle_1qb,
        "freshness": freshness_info,
        "market_signal_info_sf": market_signal_info_sf,
        "market_signal_info_1qb": market_signal_info_1qb,
    }


@st.cache_data(ttl=900, show_spinner=False)
def get_league_custom_redraft_lookup(_market_db, scoring_tuple: tuple, is_superflex: bool, week: int = 1, _cache_version: str = "v27_fp_ros_scraper"):
    """
    Cached wrapper around src.market_data.compute_custom_redraft_lookup (the
    same league-exact-scoring redraft valuation now shared by main.py and
    scripts/weekly_automation.py via src/orchestration.py). This function's
    only job is the @st.cache_data(ttl=900) layer - the underlying logic is
    identical to before this extraction, byte-for-byte.
    """
    return compute_custom_redraft_lookup(_market_db, scoring_tuple, is_superflex, week)


def build_market_assets_list(active_lookup, players_db, is_redraft=False):
    """
    Builds an enriched, sorted list of market assets (players & draft picks)
    for use in market exploration, player head-to-head, and the trade calculator.
    """
    assets = []
    for pid, p_data in active_lookup.items():
        p_obj = players_db.get(str(pid), {})
        pname = p_obj.get("full_name") or p_data.get("player_name") or str(pid)
        raw_pos = p_obj.get("position") or p_data.get("position") or "UTIL"
        is_pick_asset = False if is_redraft else is_draft_pick_asset(pid, pname, raw_pos)

        pos = "PICK" if is_pick_asset else raw_pos
        team = "DRAFT" if is_pick_asset else (p_obj.get("team") or "FA")
        age = p_obj.get("age", "—")
        val = p_data.get("market_value", 0.0)
        ecr = p_data.get("rank_ecr_pos", p_data.get("rank_ecr", 999.0))
        o_ecr = p_data.get("rank_ecr_overall", 999.0)
        ktc_v = p_data.get("ktc_val")
        fc_v = p_data.get("fc_val")
        dp_v = p_data.get("dp_val")
        proj_ppg = p_data.get("proj_ppg")
        fp_o = p_data.get("fp_ecr_overall")
        fp_p = p_data.get("fp_ecr_pos")
        ktc_redraft_val = p_data.get("ktc_redraft_val")
        ktc_redraft_o = p_data.get("ktc_redraft_overall_rank")
        ktc_redraft_p = p_data.get("ktc_redraft_pos_rank")
        market_signal = p_data.get("market_signal")
        rank_diff = p_data.get("rank_diff")
        market_signal_str = {
            "sell_high": "🔥 Sell High",
            "buy_low": "💎 Buy Low",
        }.get(market_signal, "—")

        pos_ecr_str = f"{pos}{int(ecr)}" if (ecr and ecr < 900) else "—"
        overall_ecr_str = f"#{int(o_ecr)}" if (o_ecr and o_ecr < 900) else "—"

        try:
            raw_o_ecr = float(o_ecr) if (o_ecr is not None and float(o_ecr) < 900) else 9999.0
        except (ValueError, TypeError):
            raw_o_ecr = 9999.0

        try:
            raw_p_ecr = float(ecr) if (ecr is not None and float(ecr) < 900) else 9999.0
        except (ValueError, TypeError):
            raw_p_ecr = 9999.0

        assets.append({
            "pid": str(pid),
            "Avatar": "" if is_pick_asset else get_player_avatar_url(pid, pos, team),
            "avatar": "" if is_pick_asset else get_player_avatar_url(pid, pos, team),
            "Player": pname,
            "name": pname,
            "Pos": pos,
            "pos": pos,
            "NFL Team": team,
            "team": team,
            "age": age,
            "Consensus Value": f"{val:,.0f} pts",
            "Overall ECR": overall_ecr_str,
            "Pos ECR": pos_ecr_str,
            "val": val,
            "o_ecr": raw_o_ecr,
            "p_ecr": raw_p_ecr,
            "o_ecr_str": overall_ecr_str,
            "pos_ecr_str": pos_ecr_str,
            "KeepTradeCut": f"{ktc_v:,.0f}" if ktc_v is not None else "—",
            "FantasyCalc": f"{fc_v:,.0f}" if fc_v is not None else "—",
            "DynastyProcess": f"{dp_v:,.0f}" if dp_v is not None else "—",
            "FantasyPros ECR": (
                f"#{int(fp_o)}" if (fp_o is not None and float(fp_o) < 500)
                else (f"{pos}{int(fp_p)}" if (fp_p is not None and float(fp_p) < 200) else "—")
            ),
            "Sleeper Proj PPG": f"{proj_ppg:.1f} PPG" if proj_ppg is not None else "—",
            "KTC Redraft Value": f"{ktc_redraft_val:,.0f} pts" if ktc_redraft_val is not None else "—",
            "Market Signal": market_signal_str,
            "market_signal": market_signal,
            "rank_diff": rank_diff,
            "_rank_diff": float(rank_diff) if rank_diff is not None else 0.0,
            "proj_ppg": proj_ppg,
            "fp_ecr_overall": fp_o,
            "fp_ecr_pos": fp_p,
            "ktc_redraft_val": ktc_redraft_val,
            "ktc_redraft_overall_rank": ktc_redraft_o,
            "ktc_redraft_pos_rank": ktc_redraft_p,
            "_proj_ppg": float(proj_ppg or 0.0),
            "_ktc_redraft_val": float(ktc_redraft_val or 0.0),
            "_fp_ecr": (
                float(fp_o) if (fp_o is not None and float(fp_o) < 500)
                else (float(fp_p) + 500.0 if (fp_p is not None and float(fp_p) < 200) else 9999.0)
            ),
            "_ktc_redraft_o": float(ktc_redraft_o) if (ktc_redraft_o is not None and float(ktc_redraft_o) < 500) else 9999.0,
            "ktc_val": ktc_v,
            "fc_val": fc_v,
            "dp_val": dp_v,
            "is_pick": is_pick_asset,
            "_val": val,
            "_overall_ecr": raw_o_ecr,
            "_pos_ecr": raw_p_ecr,
            "_ktc": float(ktc_v) if (ktc_v is not None and str(ktc_v).replace(".", "", 1).isdigit()) else 0.0,
            "_fc": float(fc_v) if (fc_v is not None and str(fc_v).replace(".", "", 1).isdigit()) else 0.0,
            "_dp": float(dp_v) if (dp_v is not None and str(dp_v).replace(".", "", 1).isdigit()) else 0.0,
            "_name": pname.lower(),
            "label": f"{pname} ({pos} - {team}) • #{int(o_ecr) if (o_ecr and o_ecr < 900) else '—'} • {val:,.0f} pts",
        })
    assets.sort(key=lambda x: x["_val"], reverse=True)
    return assets


def build_player_owner_lookup(all_team_profiles, users):
    """
    Maps player_id -> the roster that owns them in this league (owner's raw
    Sleeper @username, and Franchise Trajectory status text/category) for
    the Market Rankings table's Owner/Trajectory columns. The username is
    the plain Sleeper display_name (not manager_name, which appends the
    fantasy team name in parens). bench_assets already includes taxi-squad
    players (analyze_team_profile only excludes reserve_ids there, not
    taxi_ids), so starter_assets + bench_assets alone already covers a
    team's full active + taxi roster - no separate taxi_assets pass needed.
    A player absent from this map is a free agent.
    """
    username_by_owner_id = {u.get("user_id"): f"@{u.get('display_name', 'Unknown')}" for u in users}

    owner_by_pid = {}
    for prof in all_team_profiles:
        username = username_by_owner_id.get(prof.get("owner_id"), "Unknown Owner")
        status = prof.get("status", "")
        trajectory = status.split("(")[0].strip() if status else "—"
        category = prof.get("category", "neutral")
        for asset in prof.get("starter_assets", []) + prof.get("bench_assets", []):
            pid = asset.get("player_id")
            if pid:
                owner_by_pid[str(pid)] = {
                    "username": username,
                    "trajectory": trajectory,
                    "category": category,
                }
    return owner_by_pid


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
    schedule = get_league_schedule(league_id, start_week=1, end_week=18, current_week=week)
    traded_picks = get_traded_picks(league_id)
    draft_type = get_league_draft_type(league_id)
    projections = get_weekly_projections(season, week)
    stats = get_weekly_stats(season, week)
    matchups = get_league_matchups(league_id, week, current_week=week)
    return {
        "rosters": rosters,
        "users": users,
        "schedule": schedule,
        "traded_picks": traded_picks,
        "draft_type": draft_type,
        "projections": projections,
        "stats": stats,
        "matchups": matchups,
    }


@st.cache_data(ttl=900, show_spinner=False)
def fetch_portfolio_exposure(user_id, league_ids, league_names, _players_db, _market_db, selected_mode, active_week, _leagues_data, _cache_version="v2_per_league_valuation_dynasty_redraft_split"):
    """
    Scans all user's leagues to aggregate portfolio player shares and exposure.

    Dynasty and redraft leagues are tracked separately: total_leagues/Share
    Count/Exposure% reflect dynasty leagues only, since this metric is about
    long-term portfolio concentration - a redraft roster is a one-season
    coincidence, not a dynasty asset, and shouldn't inflate it. Redraft
    overlap is still surfaced per player as an informational "Redraft
    Shares" count with no percentage attached. Players held only in redraft
    leagues (zero dynasty shares) are excluded from the table entirely.

    Each league's players are valued with that league's own correct lookup
    (dynasty Superflex/1QB with TE Premium applied, or that league's custom
    redraft lookup) - the same selection already used by the Portal card
    grid and League Workspace - instead of one fixed Superflex Dynasty table
    reused for every league regardless of its actual format.

    Roster fetches run concurrently across leagues (network-bound, like the
    Portal card grid's ThreadPoolExecutor) instead of one league at a time.
    """
    league_map = {str(lg.get("league_id")): lg for lg in _leagues_data}

    def fetch_one(lid, lname):
        lg = league_map.get(str(lid))
        if not lg:
            return None
        try:
            rosters = get_league_rosters(lid)
            my_roster = next((r for r in rosters if r.get("owner_id") == user_id or user_id in (r.get("co_owners") or [])), None)
            if not my_roster:
                return None

            my_pids = [p for p in (my_roster.get("players") or []) if p]
            if not my_pids:
                return None

            # Same is_dynasty/is_superflex/tep_bonus/primary_lookup resolution
            # as the League Workspace and main.py (src/orchestration.py) -
            # already redirects primary_lookup to the redraft lookup for
            # non-dynasty leagues internally, so no separate branch is needed
            # here.
            context = build_league_context(lg, rosters, [], _market_db, active_week, mode=selected_mode)
            is_dyn = context["is_dynasty"]
            lookup = context["primary_lookup"]

            settings = my_roster.get("settings", {})
            w = settings.get("wins", 0)
            l = settings.get("losses", 0)
            t = settings.get("ties", 0)
            fpts = settings.get("fpts", 0) + (settings.get("fpts_decimal", 0) / 100.0)
            fpts_against = settings.get("fpts_against", 0) + (settings.get("fpts_against_decimal", 0) / 100.0)
            roster_val = sum(lookup.get(pid, {}).get("market_value", 0.0) for pid in my_pids)

            return {
                "league_id": lid, "league_name": lname, "is_dynasty": is_dyn,
                "record": f"{w}-{l}" + (f"-{t}" if t > 0 else ""),
                "wins": w, "losses": l, "ties": t, "fpts": fpts, "fpts_against": fpts_against,
                "players_count": len(my_pids), "roster_value": roster_val,
                "player_ids": my_pids, "lookup": lookup,
            }
        except Exception:
            return None

    league_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(league_ids) or 1)) as executor:
        futures = [executor.submit(fetch_one, lid, lname) for lid, lname in zip(league_ids, league_names)]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                league_results.append(result)

    # Preserve original league order for deterministic downstream display
    order = {lid: idx for idx, lid in enumerate(league_ids)}
    league_results.sort(key=lambda r: order.get(r["league_id"], 999))

    total_dynasty_leagues = sum(1 for r in league_results if r["is_dynasty"])
    total_redraft_leagues = sum(1 for r in league_results if not r["is_dynasty"])

    player_exposure = {}
    league_summaries = []

    for r in league_results:
        league_summaries.append({
            "league_id": r["league_id"], "league_name": r["league_name"], "is_dynasty": r["is_dynasty"],
            "record": r["record"], "wins": r["wins"], "losses": r["losses"], "ties": r["ties"],
            "fpts": r["fpts"], "fpts_against": r["fpts_against"],
            "players_count": r["players_count"], "roster_value": r["roster_value"],
        })

        for pid in r["player_ids"]:
            p_obj = _players_db.get(pid, {})
            val_data = r["lookup"].get(pid, {})

            entry = player_exposure.setdefault(pid, {
                "player_id": pid,
                "name": p_obj.get("full_name") or pid,
                "position": p_obj.get("position") or "UTIL",
                "team": p_obj.get("team") or "FA",
                "age": p_obj.get("age", "—"),
                "dynasty_market_value": 0.0, "dynasty_rank_ecr": 999.0, "dynasty_rank_ecr_overall": 999.0,
                "redraft_market_value": 0.0,
                "dynasty_count": 0, "redraft_count": 0,
                "dynasty_leagues": [], "redraft_leagues": [],
            })

            if r["is_dynasty"]:
                if entry["dynasty_count"] == 0:
                    entry["dynasty_market_value"] = val_data.get("market_value", 0.0)
                    entry["dynasty_rank_ecr"] = val_data.get("rank_ecr", 999.0)
                    entry["dynasty_rank_ecr_overall"] = val_data.get("rank_ecr_overall", 999.0)
                entry["dynasty_count"] += 1
                entry["dynasty_leagues"].append(r["league_name"])
            else:
                if entry["redraft_count"] == 0:
                    entry["redraft_market_value"] = val_data.get("market_value", 0.0)
                entry["redraft_count"] += 1
                entry["redraft_leagues"].append(r["league_name"])

    rows = []
    for pid, d in player_exposure.items():
        dyn_c = d["dynasty_count"]
        if dyn_c == 0:
            continue  # redraft-only overlap isn't part of the long-term portfolio

        red_c = d["redraft_count"]
        pct = (dyn_c / total_dynasty_leagues * 100.0) if total_dynasty_leagues > 0 else 0.0
        pos = d["position"]
        ecr_val = d["dynasty_rank_ecr"]
        pos_ecr_str = f"{pos}{int(ecr_val)}" if (ecr_val and ecr_val < 900) else "—"
        o_val = d["dynasty_rank_ecr_overall"]
        overall_ecr_str = f"#{int(o_val)}" if (o_val and o_val < 900) else "—"

        rows.append({
            "Avatar": get_player_avatar_url(pid, pos, d["team"]),
            "Player": d["name"],
            "Pos": pos,
            "NFL Team": d["team"],
            "Age": d.get("age", "—"),
            "Shares": f"{dyn_c} / {total_dynasty_leagues}",
            "Share Count": dyn_c,
            "Exposure": f"{pct:.0f}%",
            "Exposure %": pct,
            "Redraft Shares": f"{red_c} / {total_redraft_leagues}" if total_redraft_leagues > 0 else "—",
            "Redraft Share Count": red_c,
            "Overall ECR": overall_ecr_str,
            "Pos ECR": pos_ecr_str,
            "Consensus Value": d["dynasty_market_value"],
            "Leagues Owned": ", ".join(d["dynasty_leagues"]),
        })

    rows.sort(key=lambda x: (x["Share Count"], x["Consensus Value"]), reverse=True)
    return rows, total_dynasty_leagues, league_summaries


@st.cache_data(ttl=600, show_spinner=False)
def fetch_portfolio_lineup_recommendations(user_id, league_ids, active_season, active_week, _players, _leagues_data, _cache_version="v3_game_started_filter"):
    """
    Aggregates actionable lineup suggestions across all leagues for the connected user.
    Reuses existing calculate_weekly_projected_points and audit_weekly_lineup engines.
    Returns sorted list of league alert dicts with structured move fields.
    """
    weekly_proj = get_weekly_projections(active_season, active_week)
    weekly_stats = get_weekly_stats(active_season, active_week)
    league_alerts = []

    league_map = {str(lg.get("league_id")): lg for lg in _leagues_data}

    for lid_raw in league_ids:
        lid = str(lid_raw)
        lg = league_map.get(lid)
        if not lg:
            continue
        lname = lg.get("name", f"League {lid}")
        rosters = get_league_rosters(lid)
        u_roster = get_user_roster(rosters, user_id)
        if not u_roster or not u_roster.get("players"):
            continue

        roster_pos = lg.get("roster_positions", [])
        scoring = lg.get("scoring_settings", {})
        r_players = get_roster_players(u_roster, _players)

        proj_lookup = {}
        for p in r_players:
            pid = p.get("player_id")
            raw = weekly_proj.get(pid)
            proj_lookup[pid] = calculate_weekly_projected_points(pid, raw, scoring, p)

        audit = audit_weekly_lineup(
            user_roster=u_roster,
            roster_players=r_players,
            projections_lookup=proj_lookup,
            roster_positions=roster_pos,
            player_db=_players,
            weekly_stats=weekly_stats,
        )

        swaps = audit.get("start_sit_swaps", [])
        raw_injuries = audit.get("injury_alerts", [])

        # Filter actionable injuries:
        # High urgency: Out / IR / PUP / Sus
        # Medium urgency: Doubtful / Questionable where a healthy bench pivot exists
        urgent_injuries = []
        for inj in raw_injuries:
            status = inj.get("status")
            if status in ("Out", "IR", "PUP", "Sus"):
                urgent_injuries.append({**inj, "urgency": "high"})
            elif status in ("Doubtful", "Questionable") and inj.get("pivot"):
                urgent_injuries.append({**inj, "urgency": "medium"})

        # Only alert if there is a concrete start/sit swap or a starter ruled OUT/IR
        if not swaps and not any(inj["urgency"] == "high" for inj in urgent_injuries):
            continue

        formatted_moves = []
        copy_lines = []

        # 1. Urgent injuries: active starter is Out / IR
        for inj in urgent_injuries:
            if inj["urgency"] == "high":
                starter_name = inj["starter"].get("full_name") or inj["starter"].get("player_id")
                slot = inj["slot"].replace("_", " ")
                pivot = inj.get("pivot")
                status = inj["status"].upper()
                if pivot:
                    pname = pivot[0].get("full_name")
                    ppts = pivot[1]
                    formatted_moves.append({
                        "type": "injury_out",
                        "slot": slot,
                        "starter_name": starter_name,
                        "pivot_name": pname,
                        "pivot_pts": ppts,
                        "status": status,
                        "text": f"{slot}: {starter_name} is {status} — start {pname} from bench ({ppts:.1f} pts)",
                        "impact": ppts,
                    })
                    copy_lines.append(f"{slot}: start {pname} over {starter_name} ({status})")
                else:
                    formatted_moves.append({
                        "type": "injury_out",
                        "slot": slot,
                        "starter_name": starter_name,
                        "pivot_name": "",
                        "pivot_pts": 0.0,
                        "status": status,
                        "text": f"{slot}: {starter_name} is {status} — No healthy bench pivot found!",
                        "impact": 5.0,
                    })
                    copy_lines.append(f"{slot}: {starter_name} is {status} (bench empty)")

        # 2. Start/Sit swaps (gain >= 0.5 pts)
        for s in swaps:
            st_p = s["start_player"].get("full_name") or s["start_player"].get("player_id")
            sit_p = s["sit_player"].get("full_name") or s["sit_player"].get("player_id")
            slot = s["slot"].replace("_", " ")
            gain = s["gain"]
            formatted_moves.append({
                "type": "swap",
                "slot": slot,
                "start_player": st_p,
                "start_proj": s["start_proj"],
                "sit_player": sit_p,
                "sit_proj": s["sit_proj"],
                "gain": gain,
                "text": f"{slot}: start {st_p} over {sit_p} (+{gain:.1f} pts)",
                "impact": gain,
            })
            copy_lines.append(f"{slot}: start {st_p} over {sit_p} (+{gain:.1f} pts)")

        # 3. Contextual Questionable warnings alongside swaps
        for inj in urgent_injuries:
            if inj["urgency"] == "medium":
                starter_name = inj["starter"].get("full_name") or inj["starter"].get("player_id")
                slot = inj["slot"].replace("_", " ")
                pivot = inj.get("pivot")
                pname = pivot[0].get("full_name")
                ppts = pivot[1]
                formatted_moves.append({
                    "type": "injury_q",
                    "slot": slot,
                    "starter_name": starter_name,
                    "pivot_name": pname,
                    "pivot_pts": ppts,
                    "status": "Q",
                    "text": f"{slot}: monitor {starter_name} (Q) — bench pivot ready: {pname} ({ppts:.1f} pts)",
                    "impact": 0.5,
                })
                copy_lines.append(f"{slot}: monitor {starter_name} (Q) -> pivot {pname}")

        total_impact = sum(m["impact"] for m in formatted_moves)
        has_out = any(m["type"] == "injury_out" for m in formatted_moves)

        league_alerts.append({
            "league_id": lid,
            "league_name": lname,
            "moves": formatted_moves,
            "copy_text": f"{lname}: " + "; ".join(copy_lines),
            "total_impact": total_impact,
            "has_out_injury": has_out,
            "points_diff": audit.get("points_differential", 0.0),
        })

    league_alerts.sort(key=lambda x: (x["has_out_injury"], x["total_impact"]), reverse=True)
    return league_alerts


def render_hub_lineup_empty_card_html(active_week):
    """
    Renders the "all lineups optimal" success card shown when no league needs
    a lineup look this week. Self-contained (own .card-container chrome) since
    there are no per-league rows or Open Workspace buttons in this state.
    """
    return f"""
    <div class="card-container card-success" style="margin-bottom: 22px; padding: 16px 20px; border-radius: 10px; background: linear-gradient(135deg, rgba(16, 185, 129, 0.08) 0%, #111827 100%); border: 1px solid rgba(16, 185, 129, 0.25); border-left: 3px solid #10b981;">
        <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px;">
            <div style="display: flex; align-items: center; gap: 10px;">
                <span style="font-size: 1.25rem;">⭐</span>
                <div>
                    <div style="color: #34d399; font-weight: 800; font-size: 0.98rem; letter-spacing: -0.01em;">
                        All Starting Lineups Optimal — Week {active_week}
                    </div>
                    <div style="color: #94a3b8; font-size: 0.82rem; margin-top: 2px;">
                        No suboptimal starters or unaddressed player injuries detected across your franchises.
                    </div>
                </div>
            </div>
            <span class="status-capsule status-rebuild" style="font-size: 0.72rem;">100% READY</span>
        </div>
    </div>
    """


def render_hub_lineup_header_html(num_leagues, total_actions, active_week):
    """
    Renders the title/intro of the Heads Up lineup-alerts panel. The outer
    card chrome (background/border) comes from the .st-key-hub_lineup_alerts_wrap
    CSS on the real st.container wrapping this call at the call site - each
    league's row is rendered separately (render_hub_lineup_row_html) so a
    real st.button can sit directly beside its own row, instead of every
    "Open Workspace" button being clustered into one detached row below all
    the rows, which read as a bare, context-less link list disconnected from
    the detail above it.
    """
    league_word = "Franchise" if num_leagues == 1 else "Franchises"
    return f"""
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; flex-wrap: wrap; gap: 8px;">
        <div style="display: flex; align-items: center; gap: 9px;">
            <span style="font-size: 1.15rem; color: #fbbf24;">⚡</span>
            <span style="font-size: 1.1rem; font-weight: 800; color: #f8fafc; letter-spacing: -0.01em;">
                Heads Up — {num_leagues} {league_word} Need a Lineup Look
            </span>
            <span style="background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.35); border-radius: 4px; padding: 2px 7px; font-size: 0.72rem; font-weight: 800; letter-spacing: 0.04em; text-transform: uppercase;">
                {total_actions} Actions
            </span>
        </div>
        <div style="color: #64748b; font-size: 0.75rem; font-weight: 600;">
            Week {active_week} Projection Engine
        </div>
    </div>
    <div style="color: #94a3b8; font-size: 0.84rem; margin-bottom: 4px;">
        Suboptimal starters, higher-projected bench depth, or active starter injuries detected across your franchises.
    </div>
    """


def render_hub_lineup_row_html(alert):
    """
    Renders one league's lineup-alert row (name, change count, move list,
    Copy Moves button). Rendered in the same st.columns row as a real
    st.button("Open Workspace") for that league - see the call site.
    """
    def _get_slot_badge_class(s_name):
        s = s_name.upper()
        if "QB" in s:
            return "badge-qb"
        elif "RB" in s:
            return "badge-rb"
        elif "WR" in s:
            return "badge-wr"
        elif "TE" in s:
            return "badge-te"
        elif "K" in s:
            return "badge-k"
        elif "DEF" in s or "DST" in s:
            return "badge-def"
        return "badge-wr"

    lname = alert["league_name"]
    moves = alert["moves"]
    copy_text = alert["copy_text"].replace("'", "\\'").replace('"', '&quot;')

    moves_rendered = []
    for m in moves:
        slot = m["slot"]
        mtype = m["type"]
        badge_cls = _get_slot_badge_class(slot)

        if mtype == "injury_out":
            starter_name = m.get("starter_name", "")
            pivot_name = m.get("pivot_name", "")
            pivot_pts = m.get("pivot_pts", 0.0)
            status = m.get("status", "OUT")
            if pivot_name:
                pivot_snippet = f"""
                <span style="color: #64748b; margin: 0 2px;">➔</span>
                <span style="background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.35); font-size: 0.68rem; font-weight: 800; padding: 2px 6px; border-radius: 4px;">START</span>
                <strong style="color: #38bdf8;">{pivot_name}</strong>
                <span style="color: #64748b; font-size: 0.8rem;">({pivot_pts:.1f} pts)</span>
                """
            else:
                pivot_snippet = "<span style='color: #fb7185; font-size: 0.8rem;'>(No healthy bench pivot found)</span>"

            moves_rendered.append(f"""
            <div style="display: flex; align-items: center; gap: 7px; margin-bottom: 7px; flex-wrap: wrap; font-size: 0.86rem; line-height: 1.4;">
                <span class="badge-pos {badge_cls}">{slot}</span>
                <span style="background: rgba(244, 63, 94, 0.18); color: #fb7185; border: 1px solid rgba(244, 63, 94, 0.4); font-size: 0.68rem; font-weight: 800; padding: 2px 6px; border-radius: 4px;">{status}</span>
                <strong style="color: #f87171;">{starter_name}</strong>
                {pivot_snippet}
            </div>
            """)
        elif mtype == "swap":
            st_p = m.get("start_player", "")
            sit_p = m.get("sit_player", "")
            st_pts = m.get("start_proj", 0.0)
            sit_pts = m.get("sit_proj", 0.0)
            gain = m.get("gain", 0.0)
            moves_rendered.append(f"""
            <div style="display: flex; align-items: center; gap: 7px; margin-bottom: 7px; flex-wrap: wrap; font-size: 0.86rem; line-height: 1.4;">
                <span class="badge-pos {badge_cls}">{slot}</span>
                <span style="background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.35); font-size: 0.68rem; font-weight: 800; padding: 2px 6px; border-radius: 4px;">START</span>
                <strong style="color: #f8fafc;">{st_p}</strong>
                <span style="color: #64748b; font-size: 0.8rem;">({st_pts:.1f} pts)</span>
                <span style="color: #64748b; font-weight: 600; margin: 0 2px;">over</span>
                <span style="background: rgba(244, 63, 94, 0.12); color: #fb7185; border: 1px solid rgba(244, 63, 94, 0.25); font-size: 0.68rem; font-weight: 800; padding: 2px 6px; border-radius: 4px;">SIT</span>
                <span style="color: #cbd5e1;">{sit_p}</span>
                <span style="color: #64748b; font-size: 0.8rem;">({sit_pts:.1f} pts)</span>
                <span style="background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); font-size: 0.72rem; font-weight: 800; padding: 2px 7px; border-radius: 4px; margin-left: 2px;">+{gain:.1f} PTS</span>
            </div>
            """)
        else:
            starter_name = m.get("starter_name", "")
            pivot_name = m.get("pivot_name", "")
            pivot_pts = m.get("pivot_pts", 0.0)
            moves_rendered.append(f"""
            <div style="display: flex; align-items: center; gap: 7px; margin-bottom: 7px; flex-wrap: wrap; font-size: 0.84rem; color: #94a3b8; line-height: 1.4;">
                <span class="badge-pos {badge_cls}" style="opacity: 0.85;">{slot}</span>
                <span style="background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.35); font-size: 0.68rem; font-weight: 800; padding: 2px 6px; border-radius: 4px;">QUESTIONABLE</span>
                <span style="color: #cbd5e1;">Monitor <strong>{starter_name}</strong></span>
                <span style="color: #64748b;">— pivot: <strong style="color: #38bdf8;">{pivot_name}</strong> ready ({pivot_pts:.1f} pts)</span>
            </div>
            """)

    moves_block = "".join(moves_rendered)

    return f"""
    <div style="display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap;">
        <div style="flex: 1; min-width: 260px;">
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
                <span style="font-weight: 800; font-size: 1.02rem; color: #f8fafc; letter-spacing: -0.01em;">
                    {lname}
                </span>
                <span style="color: #64748b; font-size: 0.78rem; font-weight: 600;">
                    ({len(moves)} {'change' if len(moves) == 1 else 'changes'})
                </span>
            </div>
            <div>
                {moves_block}
            </div>
        </div>
        <div style="display: flex; align-items: center; gap: 10px; flex-shrink: 0;">
            <button onclick="navigator.clipboard.writeText('{copy_text}'); this.innerText='Copied!'; this.style.borderColor='#34d399'; this.style.color='#34d399'; setTimeout(() => {{ this.innerText='Copy Moves'; this.style.borderColor='rgba(56, 189, 248, 0.25)'; this.style.color='#e2e8f0'; }}, 2000);"
                    style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(56, 189, 248, 0.25); color: #e2e8f0; border-radius: 6px; padding: 6px 13px; font-size: 0.78rem; font-weight: 700; cursor: pointer; transition: all 0.15s ease; white-space: nowrap;">
                Copy Moves
            </button>
        </div>
    </div>
    """


@st.cache_data(ttl=900, show_spinner=False)
def evaluate_league_quick_status(lid, user_id, _market_db, selected_mode, _weekly_proj_by_week, league_obj, current_week: int = 1, _cache_version: str = "v6_per_week_montecarlo"):
    """
    Accurately calculates franchise status, category, record, and
    synchronized rank across leagues - via the same shared
    build_league_context/build_team_profiles skeleton as the League
    Workspace and main.py (src/orchestration.py), instead of an
    independently-maintained reimplementation of the same dynasty prepass /
    Monte Carlo / redraft ranking logic.
    """
    try:
        rosters = get_league_rosters(lid)
        my_r = next((r for r in rosters if r.get("owner_id") == user_id or user_id in (r.get("co_owners") or [])), None)
        if not my_r or not my_r.get("players"):
            return "Pre-Draft", "neutral", 0, 0, 0.0, 0, "Pre-Draft", 0, 0

        traded_picks = get_traded_picks(lid)
        draft_type = get_league_draft_type(lid, expected_rounds=league_obj.get("settings", {}).get("draft_rounds"))
        context = build_league_context(
            league_obj, rosters, [], _market_db, current_week, mode=selected_mode,
            traded_picks=traded_picks, draft_type=draft_type,
        )

        playoff_start = league_obj.get("settings", {}).get("playoff_week_start", 15)
        schedule = get_league_schedule(lid, 1, max(1, playoff_start - 1), current_week=current_week)
        profiles = build_team_profiles(
            context, league_obj, rosters, current_week,
            weekly_projections_by_week=_weekly_proj_by_week, schedule=schedule, num_simulations=1000,
        )

        my_rid = my_r["roster_id"]
        my_profile = next((p for p in profiles["all_team_profiles"] if p["roster_id"] == my_rid), None)
        if my_profile is None:
            return "Pre-Draft", "neutral", 0, 0, 0.0, 0, "Pre-Draft", 0, 0

        m_settings = my_r.get("settings", {})
        w = m_settings.get("wins", 0)
        l = m_settings.get("losses", 0)
        fpts = m_settings.get("fpts", 0) + (m_settings.get("fpts_decimal", 0) / 100.0)
        p_count = len(my_r.get("players") or [])

        # r_pos is the Season Power Score rank (same signal as the "Season"
        # card badge) - shared by both branches below, matching what the
        # workspace's current_tier already reads off the same rank.
        _, redraft_pos, redraft_total = get_strength_tier(my_rid, profiles["redraft_ranked"])
        r_pos = profiles["sim_rank_map"].get(my_rid, (redraft_pos, 0.0))[0]

        if context["is_dynasty"]:
            _, dynasty_pos, dynasty_total = get_strength_tier(my_rid, profiles["dynasty_score_pairs"])
            return my_profile["status"], my_profile["category"], w, l, fpts, p_count, f"#{dynasty_pos}/{dynasty_total}", dynasty_pos, r_pos
        else:
            return my_profile["status"], my_profile["category"], w, l, fpts, p_count, f"#{r_pos}/{redraft_total}", r_pos, r_pos
    except Exception:
        # Never let one league's failure (transient API hiccup, bad data
        # assumption) take down the whole Portal grid - but a silent,
        # untraced except here means a real bug degrades every card to
        # zeros with zero diagnostic trail (see the Portal-wide
        # Record/Points/Dynasty-all-zeroed incident this traceback would
        # have caught immediately). Logged, not raised.
        import traceback
        print(f"Warning: evaluate_league_quick_status failed for league {lid}:")
        traceback.print_exc()
        return "Active", "neutral", 0, 0, 0.0, 0, "—", 0, 0


# -----------------------------------------------------------------------------
# App State & Navigation Router Initialization
# -----------------------------------------------------------------------------
if "selected_league_id" not in st.session_state:
    st.session_state["selected_league_id"] = None

qp_user = st.query_params.get("user")
if qp_user:
    matched_u = next((u for u in ALLOWED_USERS if u.lower() == qp_user.lower()), None)
    if matched_u:
        st.session_state["active_user_handle"] = matched_u
elif "active_user_handle" not in st.session_state:
    st.session_state["active_user_handle"] = DEFAULT_USERNAME

if "selected_mode" not in st.session_state:
    st.session_state["selected_mode"] = "equal"

active_user_handle = st.session_state["active_user_handle"]
if active_user_handle not in ALLOWED_USERS:
    active_user_handle = ALLOWED_USERS[0]
    st.session_state["active_user_handle"] = active_user_handle

st.query_params["user"] = active_user_handle

with st.spinner(f"Connecting to Sleeper (@{active_user_handle}) & Market Feeds..."):
    market_db = fetch_market_database()
    try:
        user, active_season, active_week, leagues = fetch_user_and_leagues(active_user_handle)
    except Exception:
        active_user_handle = DEFAULT_USERNAME
        st.session_state["active_user_handle"] = DEFAULT_USERNAME
        st.query_params["user"] = DEFAULT_USERNAME
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
        st.session_state["top_workspace_selector"] = match_lg["name"]
    else:
        st.session_state["selected_league_id"] = None
        st.session_state["top_workspace_selector"] = PORTAL_LABEL
else:
    st.session_state["selected_league_id"] = None
    st.session_state["top_workspace_selector"] = PORTAL_LABEL

def set_active_workspace(lid):
    st.session_state["selected_league_id"] = lid
    st.query_params["user"] = st.session_state.get("active_user_handle", DEFAULT_USERNAME)
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
# Top Navigation Bar (Option 1: Linear & Vercel Glassmorphism)
# -----------------------------------------------------------------------------
with st.container(key="topbar_nav_container"):
    top_col_brand, top_col_nav, top_col_cfg, top_col_user = st.columns(
        [2.8, 3.4, 1.6, 2.2], vertical_alignment="center"
    )

    with top_col_brand:
        with st.container(key="brand_logo_wrap"):
            # Brand mark is static markup (no <a href>): a raw link would force
            # a full page reload and drop st.session_state. Clicking the logo
            # returns to the portal via the real st.button below, rendered as
            # an invisible overlay on top of this markup by CSS.
            if ICON_F_YARDS_B64:
                st.html(
                    f"""
                    <span class="brand-logo-visual" style="display: inline-flex; align-items: center; gap: 10px; width: fit-content; max-width: fit-content; vertical-align: middle; line-height: 1;">
                        <img src="data:image/png;base64,{ICON_F_YARDS_B64}" style="height: 36px; width: auto; object-fit: contain; vertical-align: middle; display: block;" />
                        <span style="font-weight: 900; font-size: 1.25rem; color: #f8fafc; letter-spacing: -0.01em; white-space: nowrap; line-height: 1;">Fantasy Analytics</span>
                    </span>
                    """
                )
            elif LOGO_HORIZONTAL_B64:
                st.html(
                    f"""
                    <span class="brand-logo-visual" style="display: inline-flex; width: fit-content; max-width: fit-content; align-items: center;">
                        <img src="data:image/png;base64,{LOGO_HORIZONTAL_B64}" style="height: 38px; width: auto; max-width: 220px; object-fit: contain; vertical-align: middle;" />
                    </span>
                    """
                )
            else:
                st.html(
                    f"""
                    <span class="brand-logo-visual" style="display: inline-flex; width: fit-content; max-width: fit-content; align-items: center; gap: 8px;">
                        <span style="font-weight: 900; font-size: 1.22rem; color: #38bdf8; letter-spacing: -0.02em;">FA</span>
                        <span style="font-weight: 800; font-size: 1.05rem; color: #f8fafc; letter-spacing: -0.01em;">Fantasy Analytics</span>
                    </span>
                    """
                )
            st.button(
                "Fantasy Analytics",
                key="brand_home_button",
                on_click=set_active_workspace,
                args=(None,),
            )

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
            ktc_redraft_stat = (fresh.get("ktc_redraft") or {}).get("status", "Live Current")
            fp_ros_stat = (fresh.get("fp_ros") or {}).get("status", "Live Current")
            st.markdown(f"**KeepTradeCut:** `{ktc_stat}`")
            st.markdown(f"**FantasyCalc:** `{fc_stat}`")
            st.markdown(f"**DynastyProcess:** `{dp_stat}`")
            st.markdown(f"**FantasyPros ECR:** `{fp_stat}`")
            st.markdown(f"**KTC Fantasy Rankings:** `{ktc_redraft_stat}`")
            st.markdown(f"**FantasyPros ROS PPR:** `{fp_ros_stat}`")
            st.caption("KeepTradeCut & Sleeper projections update live every 30 mins from API.")
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
            st.query_params["user"] = selected_u
            st.session_state["selected_league_id"] = None
            if "league" in st.query_params:
                del st.query_params["league"]
            st.rerun()

st.markdown("<div style='margin-bottom: 18px;'></div>", unsafe_allow_html=True)

# Market Data Freshness Alert: surfaces source fetch failures that used to only
# be visible as a print() warning in the server console.
_freshness_info = market_db.get("freshness", {})
_failed_sources = [info.get("source", key) for key, info in _freshness_info.items() if not info.get("ok", True)]
if _failed_sources:
    st.warning(
        f"⚠️ Some market data sources failed to refresh this session: **{', '.join(_failed_sources)}**. "
        "Affected valuations may be based on stale or partial data. "
        "See Settings → Market Data Freshness for details."
    )

# A source can also fetch successfully (ok=True) while its own underlying
# scrape hasn't actually run in days - e.g. fp_ros_rankings served fine from
# GitHub, but the scheduled scraper behind it silently stopped updating.
# That's invisible to the check above, so it gets its own banner.
_stale_sources = [info.get("source", key) for key, info in _freshness_info.items() if info.get("stale")]
if _stale_sources:
    st.warning(
        f"🕓 Some market data sources are stale (fetched fine, but the underlying data hasn't "
        f"updated recently): **{', '.join(_stale_sources)}**. "
        "See Settings → Market Data Freshness for details."
    )

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
    st.markdown("<h1 style='margin-bottom: 4px; font-size: 2.1rem; font-weight: 900; letter-spacing: -0.02em; color: #f8fafc;'>Fantasy Analytics</h1>", unsafe_allow_html=True)
    st.markdown("<p style='color: #94a3b8; font-size: 1.05rem; margin-top: 0px; margin-bottom: 12px;'>Executive Multi-League Portfolio & Franchise Intelligence Platform</p>", unsafe_allow_html=True)

    st.caption(f"Connected Sleeper Account: **@{user['username']}** | Season: **{active_season}** (Wk {active_week}) | Active Model: **{VALUATION_MODES[selected_mode]}**")

    # Aggregate Portfolio Metrics
    exp_rows, total_user_leagues, l_summaries = fetch_portfolio_exposure(
        user["user_id"], all_l_ids, all_l_names, players, market_db, selected_mode, active_week, sorted_leagues
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

    # Consolidated Portfolio Lineup Recommendations Alert Card
    hub_lineup_alerts = fetch_portfolio_lineup_recommendations(
        user["user_id"], all_l_ids, active_season, active_week, players, sorted_leagues
    )
    if not hub_lineup_alerts:
        st.html(render_hub_lineup_empty_card_html(active_week))
    else:
        with st.container(key="hub_lineup_alerts_wrap"):
            total_actions = sum(len(a["moves"]) for a in hub_lineup_alerts)
            st.html(render_hub_lineup_header_html(len(hub_lineup_alerts), total_actions, active_week))
            for a in hub_lineup_alerts:
                row_col, btn_col = st.columns([5, 1.3], vertical_alignment="center")
                with row_col:
                    st.html(render_hub_lineup_row_html(a))
                with btn_col:
                    st.button(
                        "Open Workspace →",
                        key=f"open_workspace_hub_{a['league_id']}",
                        on_click=set_active_workspace,
                        args=(a["league_id"],),
                        use_container_width=True,
                        type="primary",
                    )

    st.markdown("### League Workspaces")
    st.caption("Select any franchise to enter its dedicated analytical suite (Franchise Hub, Matchups & Start/Sit, Waivers, Power Rankings, Trade Center).")

    # Real per-week projections (not one snapshot reused for the whole
    # simulated season) - each week is individually cached in
    # src.sleeper_api, so this is effectively free after the first league's
    # card computes it.
    weekly_proj_by_week_all = get_weekly_projections_by_week(active_season, range(active_week, 18))

    def _build_league_card_html(lg):
        """
        Computes and returns one league's card HTML for the League Workspaces
        grid below. Only reads from the closed-over market_db/players/
        weekly_proj_by_week_all/selected_mode/active_week/user - never mutates them
        (apply_valuation_mode/apply_ktc_te_premium already return new dicts
        instead of mutating their input, so concurrent calls for different
        leagues can't cross-contaminate each other's valuations the way a
        shared-mutation bug once did here) - so this is safe to run
        concurrently for every league via ThreadPoolExecutor below. Most of
        its cost is waiting on live Sleeper API calls (rosters, schedule,
        league history), not CPU, which is exactly what a thread pool helps
        with (the GIL releases during I/O waits) - same rationale as
        get_ros_projections's per-week parallel fetch in sleeper_api.py.
        """
        lid = lg["league_id"]
        lname = lg["name"]

        settings = lg.get("settings", {})
        is_dyn = (settings.get("type") == 2)
        total_rosters = lg.get("total_rosters", 12)
        roster_pos = lg.get("roster_positions", [])
        is_sf = is_superflex_league(roster_pos)
        scoring = lg.get("scoring_settings", {})
        tep_b = scoring.get("bonus_rec_te", 0.0) or scoring.get("te_bonus", 0.0) or settings.get("tep_bonus", 0.0)
        type_str = f"{'Dynasty' if is_dyn else 'Redraft'} • {'Superflex' if is_sf else '1QB'} ({total_rosters} Teams)"
        tep_badge = f"<span style='background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 4px; padding: 1px 5px; font-size: 0.68rem; font-weight: 700; margin-left: 6px;'>+{tep_b:g} TEP</span>" if tep_b > 0 else ""

        # Everything below derives from live Sleeper data (rosters, projections,
        # league history network calls, valuation lookups) and can fail for a
        # given league independently of the others - e.g. a transient Sleeper
        # API hiccup, or a league whose data doesn't fit an assumption made
        # elsewhere. A failure here must never drop this league's card entirely
        # (previously an uncaught exception here would halt the whole grid loop
        # mid-render); instead it degrades this one card's dynamic fields to
        # "N/A" and keeps rendering every other league normally.
        try:
            # Accurately compute quick status, category, record, and
            # synchronized ranks - build_league_context/build_team_profiles
            # (src/orchestration.py) resolve the league's own lookups
            # internally now, so there's no separate lookup-building block
            # here anymore (previously duplicated against
            # evaluate_league_quick_status's own copy of the same logic).
            t_status, t_cat, w, l, fpts, p_count, rank_str, d_pos, r_pos = evaluate_league_quick_status(
                lid, user["user_id"], market_db, selected_mode, weekly_proj_by_week_all, lg, current_week=active_week
            )

            # Trajectory badge - shows the real Franchise Trajectory tier name
            # (e.g. "Dominant Empire", "Fragile Bubble Team"), color-coded by its
            # win/neutral/rebuild macro category. Applies to both dynasty and
            # redraft leagues: evaluate_league_quick_status already routes
            # redraft through classify_redraft_team, so t_status/t_cat are
            # always populated for both league types.
            clean_t_status = t_status.split("(")[0].strip() if t_status else "Active"
            if t_cat == "win":
                badge_html = f"<span class='status-capsule status-contender'>{clean_t_status}</span>"
                border_accent = "border: 1px solid rgba(56, 189, 248, 0.35);"
            elif t_cat == "rebuild":
                badge_html = f"<span class='status-capsule status-rebuild'>{clean_t_status}</span>"
                border_accent = "border: 1px solid rgba(244, 63, 94, 0.35);"
            else:
                badge_html = f"<span class='status-capsule status-bubble'>{clean_t_status}</span>"
                border_accent = "border: 1px solid rgba(245, 158, 11, 0.35);"

            slots_str = format_starter_slots_summary(roster_pos)

            # Starter slots preview
            starter_badges = f"""
            <div style='background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(51, 65, 85, 0.6); border-radius: 6px; padding: 4px 8px; font-size: 0.72rem; color: #94a3b8; margin: 8px 0 12px 0; display: flex; align-items: center; gap: 6px; flex-wrap: wrap;'>
                <span style='color: #64748b; font-weight: 700;'>Starters:</span>
                <span style='color: #38bdf8; font-weight: 600;'>{slots_str}</span>
            </div>
            """ if slots_str else ""

            # 4-Cell Matrix
            dyn_cell = f"""
            <div style='background: rgba(14, 165, 233, 0.08); border: 1px solid rgba(56, 189, 248, 0.25); border-radius: 8px; padding: 8px 4px; text-align: center;'>
                <div style='font-size: 0.65rem; text-transform: uppercase; font-weight: 800; color: #38bdf8; letter-spacing: 0.04em;'>Dynasty</div>
                <div style='font-size: 0.95rem; font-weight: 900; color: #f8fafc; margin-top: 2px;'>#{d_pos} <span style='font-size: 0.68rem; font-weight: 500; color: #64748b;'>/ {total_rosters}</span></div>
                <div style='font-size: 0.65rem; color: #38bdf8; opacity: 0.85; margin-top: 2px;'>Capital</div>
            </div>
            """ if is_dyn else f"""
            <div style='background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(51, 65, 85, 0.5); border-radius: 8px; padding: 8px 4px; text-align: center;'>
                <div style='font-size: 0.65rem; text-transform: uppercase; font-weight: 800; color: #94a3b8; letter-spacing: 0.04em;'>Type</div>
                <div style='font-size: 0.85rem; font-weight: 800; color: #f8fafc; margin-top: 4px;'>Redraft</div>
                <div style='font-size: 0.65rem; color: #64748b; margin-top: 2px;'>Annual</div>
            </div>
            """

            # Static descriptor only (no classification text): this cell shows
            # the Season Power Score rank, a signal distinct from both Playoff
            # Status and Franchise Trajectory. Top-3 still gets a highlight
            # accent, matching the "Capital"/"Annual" descriptor pattern used
            # by the Dynasty/Type cell above.
            season_color = "#34d399" if r_pos <= 3 else ("#38bdf8" if r_pos <= 6 else "#94a3b8")
            season_bg = "rgba(16, 185, 129, 0.08)" if r_pos <= 3 else "rgba(15, 23, 42, 0.7)"
            season_border = "rgba(16, 185, 129, 0.25)" if r_pos <= 3 else "rgba(51, 65, 85, 0.5)"

            season_cell = f"""
            <div style='background: {season_bg}; border: 1px solid {season_border}; border-radius: 8px; padding: 8px 4px; text-align: center;'>
                <div style='font-size: 0.65rem; text-transform: uppercase; font-weight: 800; color: {season_color}; letter-spacing: 0.04em;'>Season</div>
                <div style='font-size: 0.95rem; font-weight: 900; color: #f8fafc; margin-top: 2px;'>#{r_pos} <span style='font-size: 0.68rem; font-weight: 500; color: #64748b;'>/ {total_rosters}</span></div>
                <div style='font-size: 0.65rem; color: {season_color}; font-weight: 600; margin-top: 2px;'>Power Score</div>
            </div>
            """

            history = get_league_history(lid, lname, user["user_id"])
            inaug_txt = f"Inaugural: {history.get('inaugural_season', '—')}"
            heritage_txt = "Migrated" if history.get("is_migrated") else "Native Sleeper"
            user_titles = history.get("user_titles", 0)
            title_badge = f"<span style='background: rgba(234, 179, 8, 0.18); color: #facc15; border: 1px solid rgba(234, 179, 8, 0.45); border-radius: 4px; padding: 1px 6px; font-size: 0.68rem; font-weight: 800;'>🏆 {user_titles} Title{'s' if user_titles > 1 else ''}</span>" if user_titles > 0 else ""
            heritage_badge = f"<span style='background: rgba(148, 163, 184, 0.12); color: #cbd5e1; border: 1px solid rgba(148, 163, 184, 0.25); border-radius: 4px; padding: 1px 6px; font-size: 0.68rem; font-weight: 600;'>{heritage_txt}</span>"
            w_txt = f"{w}-{l}"
            fpts_txt = f"{fpts:,.1f}"
        except Exception:
            na_badge_style = "background: rgba(148, 163, 184, 0.12); color: #94a3b8; border: 1px solid rgba(148, 163, 184, 0.25); border-radius: 4px; padding: 1px 6px; font-size: 0.68rem; font-weight: 700;"
            badge_html = f"<span style='{na_badge_style}'>DATA UNAVAILABLE</span>"
            border_accent = "border: 1px solid rgba(148, 163, 184, 0.2);"
            starter_badges = ""
            na_cell = """
            <div style='background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(51, 65, 85, 0.5); border-radius: 8px; padding: 8px 4px; text-align: center;'>
                <div style='font-size: 0.65rem; text-transform: uppercase; font-weight: 800; color: #94a3b8; letter-spacing: 0.04em;'>{label}</div>
                <div style='font-size: 0.95rem; font-weight: 900; color: #64748b; margin-top: 2px;'>N/A</div>
                <div style='font-size: 0.65rem; color: #64748b; margin-top: 2px;'>Unavailable</div>
            </div>
            """
            dyn_cell = na_cell.format(label="Dynasty" if is_dyn else "Type")
            season_cell = na_cell.format(label="Season")
            inaug_txt = "Inaugural: N/A"
            heritage_badge = ""
            title_badge = ""
            w_txt = "N/A"
            fpts_txt = "N/A"
            history = {"total_seasons": "N/A"}

        # No <a href> here: a raw link would force a full page reload and drop
        # st.session_state. Navigation is a real st.button below, via
        # set_active_workspace().
        card_html = f"""
        <div class='card-container' style='border-radius: 12px; padding: 16px 18px; margin-bottom: 8px; {border_accent} background: linear-gradient(135deg, rgba(15, 23, 42, 0.85) 0%, rgba(10, 15, 30, 0.95) 100%); box-shadow: 0 4px 14px rgba(0, 0, 0, 0.35);'>
            <div style='display: flex; justify-content: space-between; align-items: flex-start;'>
                <div>
                    <h4 style='margin: 0; color: #f8fafc; font-size: 1.02rem; font-weight: 800; letter-spacing: -0.01em;'>{lname}</h4>
                    <div style='display: flex; align-items: center; margin-top: 4px; flex-wrap: wrap; gap: 4px;'>
                        <span style='color: #94a3b8; font-size: 0.78rem; font-weight: 500;'>{type_str}</span>
                        {tep_badge}
                    </div>
                    <div style='display: flex; align-items: center; gap: 6px; margin-top: 4px; font-size: 0.73rem; color: #64748b; flex-wrap: wrap;'>
                        <span>{inaug_txt} • {history.get('total_seasons', 1)} Seasons</span>
                        {heritage_badge}
                        {title_badge}
                    </div>
                </div>
                {badge_html}
            </div>

            {starter_badges}

            <div style='display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px;'>
                <div style='background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(51, 65, 85, 0.5); border-radius: 8px; padding: 8px 4px; text-align: center;'>
                    <div style='font-size: 0.65rem; text-transform: uppercase; font-weight: 800; color: #94a3b8; letter-spacing: 0.04em;'>Record</div>
                    <div style='font-size: 0.95rem; font-weight: 900; color: #f8fafc; margin-top: 2px;'>{w_txt}</div>
                    <div style='font-size: 0.65rem; color: #64748b; margin-top: 2px;'>Wk {active_week}</div>
                </div>
                <div style='background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(51, 65, 85, 0.5); border-radius: 8px; padding: 8px 4px; text-align: center;'>
                    <div style='font-size: 0.65rem; text-transform: uppercase; font-weight: 800; color: #94a3b8; letter-spacing: 0.04em;'>Points</div>
                    <div style='font-size: 0.95rem; font-weight: 900; color: #f8fafc; margin-top: 2px;'>{fpts_txt}</div>
                    <div style='font-size: 0.65rem; color: #64748b; margin-top: 2px;'>PF Scored</div>
                </div>
                {dyn_cell}
                {season_cell}
            </div>
        </div>
        """

        return "\n".join(line.lstrip() for line in card_html.splitlines())

    # Compute every league's card concurrently: each call is dominated by
    # waiting on live Sleeper API requests (rosters, schedule, league
    # history), not CPU, so a thread pool cuts the grid's total load time
    # roughly from "sum of all 12 leagues" to "the slowest one". Only the
    # actual Streamlit rendering below stays on the main thread, in the
    # original league order - st.html/st.button aren't safe to call from
    # worker threads.
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(sorted_leagues))) as executor:
        future_to_league_id = {
            executor.submit(_build_league_card_html, lg): lg["league_id"] for lg in sorted_leagues
        }
        card_html_by_league_id = {}
        for future in concurrent.futures.as_completed(future_to_league_id):
            l_id = future_to_league_id[future]
            try:
                card_html_by_league_id[l_id] = future.result()
            except Exception:
                # _build_league_card_html already catches its own failures
                # and degrades to an "N/A" card - this only guards against
                # something failing outside that try/except entirely, so a
                # single league can never take down the whole grid render.
                card_html_by_league_id[l_id] = (
                    "<div class='card-container' style='border-radius: 12px; padding: 16px 18px; "
                    "margin-bottom: 8px; border: 1px solid rgba(148, 163, 184, 0.2);'>"
                    "<h4 style='margin: 0; color: #f8fafc;'>League unavailable</h4>"
                    "<p style='color: #94a3b8; font-size: 0.85rem;'>Could not load this league's card.</p>"
                    "</div>"
                )

    # League Cards Grid (2-column responsive layout)
    grid_cols = st.columns(2)
    for idx, lg in enumerate(sorted_leagues):
        col = grid_cols[idx % 2]
        lid = lg["league_id"]
        with col:
            st.html(card_html_by_league_id[lid])
            st.button(
                "Open Workspace →",
                key=f"open_workspace_card_{lid}",
                on_click=set_active_workspace,
                args=(lid,),
                use_container_width=True,
                type="primary",
            )


# =============================================================================
# VIEW 2: DEDICATED LEAGUE WORKSPACE (selected_league_id is active)
# =============================================================================
else:
    active_lid = st.session_state["selected_league_id"]
    selected_league = next((l for l in sorted_leagues if l["league_id"] == active_lid), sorted_leagues[0])
    selected_league_id = selected_league["league_id"]
    selected_league_name = selected_league["name"]

    # Top Breadcrumb Navigation & Return to Portal Button
    col_bcrumb, col_back = st.columns([4, 1.2])
    with col_bcrumb:
        st.markdown(f"## {selected_league_name}")
    with col_back:
        if st.button("← Return to All Leagues", use_container_width=True):
            st.session_state["selected_league_id"] = None
            if "league" in st.query_params:
                del st.query_params["league"]
            st.query_params["user"] = st.session_state.get("active_user_handle", DEFAULT_USERNAME)
            st.rerun()

    with st.spinner(f"Loading Workspace: {selected_league_name}..."):
        league_data = fetch_league_data(selected_league["league_id"], active_season, active_week)

    rosters = league_data["rosters"]
    users = league_data["users"]
    schedule = league_data["schedule"]
    traded_picks = league_data["traded_picks"]
    draft_type = league_data["draft_type"]
    weekly_projections = league_data["projections"]
    weekly_stats = league_data["stats"]
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

    # League Classification, Scoring Adjustments & Team Profiles - via the
    # shared src/orchestration.py skeleton (also used by main.py and
    # scripts/weekly_automation.py; see that module's docstring for the
    # duplication history this replaces).
    context = build_league_context(
        selected_league, rosters, users, market_db, active_week, mode=selected_mode,
        traded_picks=traded_picks, draft_type=draft_type,
    )
    is_dynasty = context["is_dynasty"]
    is_superflex = context["is_superflex"]
    tep_bonus = context["tep_bonus"]
    total_rosters = context["total_rosters"]
    primary_lookup = context["primary_lookup"]
    redraft_lookup = context["redraft_lookup"]
    picks_lookup = context["picks_lookup"]
    all_rosters_players = context["all_rosters_players"]
    user_map = context["user_map"]
    picks_ownership = context["picks_ownership"]

    # Real per-week projections (not one snapshot reused for the whole
    # simulated season) - see get_weekly_projections_by_week; each week is
    # individually cached, shared process-wide across every league/tab.
    weekly_projections_by_week = get_weekly_projections_by_week(active_season, range(active_week, 18))

    profiles = build_team_profiles(
        context, selected_league, rosters, active_week,
        weekly_projections_by_week=weekly_projections_by_week, schedule=schedule, num_simulations=1000,
    )
    live_sim_results = profiles["sim_results"]
    sim_rank_map = profiles["sim_rank_map"]
    dynasty_score_pairs = profiles["dynasty_score_pairs"]
    redraft_ranked = profiles["redraft_ranked"]
    all_team_profiles = profiles["all_team_profiles"]

    user_rid = user_roster["roster_id"]
    user_sim = live_sim_results.get(user_rid, {})
    user_playoff_pct = user_sim.get("playoff_pct")
    user_is_elim = user_sim.get("is_eliminated", False)

    user_profile = next((p for p in all_team_profiles if p["roster_id"] == user_rid), None)
    current_tier = user_profile["current_tier"] if user_profile else "medium"
    games_played = user_profile["games_played"] if user_profile else 0
    team_status = user_profile["status"] if user_profile else "Balanced Squad"
    team_cat = user_profile["category"] if user_profile else "neutral"

    if is_dynasty:
        dynasty_tier = user_profile["dynasty_tier"] if user_profile else None
        _, dynasty_pos, dynasty_total = get_strength_tier(user_rid, dynasty_score_pairs)
    else:
        dynasty_tier, dynasty_pos, dynasty_total = None, None, None
    redraft_tier, redraft_pos, redraft_total = get_strength_tier(user_rid, redraft_ranked)

    user_rebuild_meta = get_rebuild_ceiling_meta(
        user_roster,
        games_played=games_played,
        playoff_pct=user_playoff_pct,
        is_eliminated=user_is_elim,
    )

    # Enrichment fields the Workspace tabs read directly off each profile
    # (starter/bench/picks totals, live clinch status) - app.py-specific
    # presentation, not part of the shared skeleton.
    for prof in all_team_profiles:
        prof["starter_value"] = sum(a.get("market_value", 0.0) for a in prof.get("starter_assets", []))
        prof["bench_value"] = sum(a.get("market_value", 0.0) for a in prof.get("bench_assets", []))
        prof["picks_value"] = sum(pk.get("market_value", 0.0) for pk in prof.get("pick_assets", []))
        prof["total_value"] = prof["starter_value"] + prof["bench_value"] + prof["picks_value"]
        prof["starters"] = prof["starter_assets"]
        prof["bench"] = prof["bench_assets"]
        prof["picks"] = prof["pick_assets"]
        prof["clinch_status"] = live_sim_results.get(prof["roster_id"], {}).get("status_code", "HUNT")

    # Dedicated ROS single-season profiles (optimized for 3-source redraft
    # consensus starters + bench) - a second, app.py-only view layered on top
    # of the shared dynasty profiles; main.py/weekly_automation.py don't need
    # this angle at all.
    all_ros_team_profiles = []
    user_ros_profile = None
    for r in rosters:
        rid = r["roster_id"]
        base_prof = next((p for p in all_team_profiles if p["roster_id"] == rid), None)
        if base_prof is None:
            continue
        manager_label = base_prof["manager_name"]

        if is_dynasty:
            ros_prof = analyze_team_profile(
                roster=r,
                roster_players=all_rosters_players[rid],
                owned_picks=[],
                primary_lookup=redraft_lookup,
                redraft_lookup=redraft_lookup,
                picks_lookup={},
                sim_rank_map={},
                roster_positions=roster_pos,
                is_dynasty=False,
                status=base_prof["status"],
                category=base_prof["category"],
                manager_name=manager_label,
                total_rosters=total_rosters,
            )
            ros_prof["starter_value"] = sum(a.get("market_value", 0.0) for a in ros_prof.get("starter_assets", []))
            ros_prof["bench_value"] = sum(a.get("market_value", 0.0) for a in ros_prof.get("bench_assets", []))
            ros_prof["picks_value"] = 0.0
            ros_prof["total_value"] = ros_prof["starter_value"] + ros_prof["bench_value"]
            ros_prof["starters"] = ros_prof["starter_assets"]
            ros_prof["bench"] = ros_prof["bench_assets"]
            ros_prof["picks"] = []
            ros_prof["playoff_pct"] = base_prof.get("playoff_pct", 0.0)
            ros_prof["is_eliminated"] = base_prof.get("is_eliminated", False)
            ros_prof["clinch_status"] = base_prof.get("clinch_status", "HUNT")
            all_ros_team_profiles.append(ros_prof)
            if rid == user_rid:
                user_ros_profile = ros_prof
        else:
            all_ros_team_profiles.append(base_prof)
            if rid == user_rid:
                user_ros_profile = base_prof

    # dynasty_rank/dynasty_score are already set on every profile by
    # build_team_profiles (src/orchestration.py) - computed once, from the
    # same single pass dynasty_score_pairs comes from, so this view and the
    # Portal are guaranteed to agree instead of risking a second,
    # independently-computed dynasty ranking drifting from the first.
    for p in all_team_profiles:
        r_id = p["roster_id"]
        if r_id in sim_rank_map:
            p["in_season_rank"] = sim_rank_map[r_id][0]
            p["in_season_power_score"] = sim_rank_map[r_id][1]
        else:
            p["in_season_rank"] = redraft_pos
            p["in_season_power_score"] = 0.0

    user_in_season_pos = user_profile.get("in_season_rank") if user_profile else (sim_rank_map.get(user_roster["roster_id"], (redraft_pos, 0.0))[0])
    user_in_season_pos_to_use = user_in_season_pos or redraft_pos
    user_in_season_score = user_profile.get("in_season_power_score", 0.0) if user_profile else (sim_rank_map.get(user_roster["roster_id"], (redraft_pos, 0.0))[1])
    dyn_pos_to_use = user_profile.get("dynasty_rank") if user_profile else dynasty_pos

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
        trajectory_delta = (
            "Rebuild Phase" if any(w in clean_status for w in ["Rebuild", "Struggle", "Tank"])
            else ("Contender Phase" if "Contend" in clean_status else "Competitive Core")
        )
        st.metric("Franchise Trajectory", clean_status, trajectory_delta, delta_color="normal", help=team_status)
    with col_m3:
        if is_dynasty and user_profile:
            dyn_rank_str = f"#{dyn_pos_to_use} of {len(all_team_profiles)}" if dyn_pos_to_use else "Pre-Draft"
            st.metric("Dynasty Roster Rank", dyn_rank_str, f"{user_profile['total_value']:,.0f} pts")
        else:
            red_rank_str = f"#{user_in_season_pos_to_use} of {len(all_team_profiles)}" if user_in_season_pos_to_use else "Pre-Draft"
            score_delta = f"Power Score: {user_in_season_score:.1f}" if user_in_season_score > 0 else "Active Season"
            st.metric("In-Season Rank", red_rank_str, score_delta)
    with col_m4:
        if is_dynasty and user_profile:
            red_rank_str = f"#{user_in_season_pos_to_use} of {len(all_team_profiles)}" if user_in_season_pos_to_use else "Pre-Draft"
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
        "Trade Center & Calculator",
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

        # Projected finish and probabilities (Synced with 1,000-run Monte Carlo simulation)
        fpg = (fpts / total_games) if total_games > 0 else (user_profile.get("projected_weekly_score", 0.0) if user_profile else 0.0)
        playoff_prob = round(user_sim.get("playoff_pct", 50.0), 1)
        finalist_prob = round(user_sim.get("finalist_pct", 0.0), 1)
        # champ_pct is only absent when no simulation ever ran for this
        # roster (e.g. a pre-draft league) - show that honestly as "N/A"
        # instead of a fabricated number, rather than pretending it's a
        # real simulated probability like the rest of this card.
        champ_pct_raw = user_sim.get("champ_pct")
        champion_prob = round(champ_pct_raw, 1) if champ_pct_raw is not None else None
        champion_prob_display = f"{champion_prob:.0f}%" if champion_prob is not None else "N/A"
        champion_prob_bar_width = champion_prob if champion_prob is not None else 0

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

        if user_rebuild_meta.get("is_locked_rebuild"):
            st.info(
                f"🔒 **Mathematical Rebuild Ceiling Active:** {user_rebuild_meta.get('reason')}. "
                f"Franchise trajectory is locked to Rebuild (`{clean_status}`). "
                f"Trade Center is configured to monetize veterans for draft capital and high-upside youth."
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
                        <div class='dash-stat-sub'>Season PF • {'+' if diff >= 0 else ''}{diff:,.1f} net</div>
                    </div>
                    <div class='dash-stat-box'>
                        <div class='dash-stat-label'>SEASON RECORD</div>
                        <div class='dash-stat-value'>{wins}-{losses}{f'-{ties}' if ties > 0 else ''}</div>
                        <div class='dash-stat-sub'>{win_pct:.1f}% Win Rate</div>
                    </div>
                    <div class='dash-stat-box'>
                        <div class='dash-stat-label'>PROJ. FINISH</div>
                        <div class='dash-stat-value text-gold'>#{user_in_season_pos_to_use if user_in_season_pos_to_use else '—'}</div>
                        <div class='dash-stat-sub'>Sim Rank • {clean_status}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with col_dash_right:
            dyn_pos_txt = f"#{dyn_pos_to_use} of {len(all_team_profiles)}" if (is_dynasty and dyn_pos_to_use) else "—"
            red_pos_txt = f"#{user_in_season_pos_to_use} of {len(rosters)}" if user_in_season_pos_to_use else "—"
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
                        <div class='prob-labels'><span>Championship</span><span style='color: #c084fc; font-weight: 700;'>{champion_prob_display}</span></div>
                        <div class='prob-track'><div class='prob-fill' style='width: {champion_prob_bar_width}%; background: linear-gradient(90deg, #8b5cf6, #c084fc);'></div></div>
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

        # 3. League Longevity & Franchise Trophy Case
        st.markdown("---")
        st.markdown("### 🏆 League Longevity & Franchise Trophy Case")
        history = get_league_history(selected_league["league_id"], selected_league.get("name", ""), user["user_id"])

        col_lh1, col_lh2, col_lh3 = st.columns(3)
        with col_lh1:
            st.metric("League Era", f"{history['total_seasons']} Seasons Active", f"Inaugural: {history['inaugural_season']}")
        with col_lh2:
            titles_cnt = history["user_titles"]
            if titles_cnt > 0:
                seasons_txt = ", ".join(str(s) for s in history["title_seasons"])
                st.metric("Championship Rings", f"🏆 {titles_cnt} Title{'s' if titles_cnt > 1 else ''}", f"Won: {seasons_txt}")
            else:
                st.metric("Championship Rings", "0 Titles", "Chasing 1st Ring", delta_color="off")
        with col_lh3:
            if history["is_migrated"]:
                st.metric("Platform Heritage", "Migrated League", history.get("notes", ""))
            else:
                st.metric("Platform History", "Native Sleeper", f"{history['total_seasons']} yrs on Sleeper")

        if history.get("title_seasons"):
            st.success(f"🥇 **Championship Legacy:** You were crowned league champion in: **{', '.join(str(s) for s in history['title_seasons'])}**!")

        if history.get("champions"):
            with st.expander("📜 View Complete League Roll of Honor & Past Champions", expanded=False):
                champ_html = """
                <div class='mobile-scroll-hint'>↔ Swipe horizontally to view full stats</div>
                <div class='table-responsive-wrapper'>
                <table class='roster-table' style='width: 100%;'>
                    <thead>
                        <tr>
                            <th style='width: 20%; text-align: center;'>Season</th>
                            <th style='width: 45%; text-align: left;'>Champion</th>
                            <th style='width: 20%; text-align: center;'>Record</th>
                            <th style='width: 15%; text-align: center;'>Franchise</th>
                        </tr>
                    </thead>
                    <tbody>
                """
                for ch in history["champions"]:
                    is_u = ch.get("is_user") or "Henrique" in ch.get("champion", "") or "Pombos" in ch.get("champion", "")
                    champ_name = ch.get("champion", "—")
                    seas = ch.get("season", "—")
                    rec = ch.get("record", "—")
                    fr_badge = "<span style='background: rgba(234, 179, 8, 0.2); color: #facc15; border: 1px solid rgba(234, 179, 8, 0.4); padding: 2px 8px; border-radius: 4px; font-size: 0.72rem; font-weight: 800;'>YOU 🏆</span>" if is_u else "<span style='color: #64748b; font-size: 0.72rem;'>Rival</span>"
                    row_bg = "style='background: rgba(234, 179, 8, 0.08);'" if is_u else ""
                    champ_html += f"""
                        <tr {row_bg}>
                            <td style='text-align: center; font-weight: 700; color: #f8fafc;'><span class='rank-pill'>{seas}</span></td>
                            <td style='text-align: left; font-weight: 700; color: {'#facc15' if is_u else '#e2e8f0'};'>{champ_name}</td>
                            <td style='text-align: center; color: #94a3b8;'>{rec}</td>
                            <td style='text-align: center;'>{fr_badge}</td>
                        </tr>
                    """
                champ_html += "</tbody></table></div>"
                st.html(champ_html)

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
                st.html(render_picks_table_html(pick_rows))
            else:
                st.info("No future draft picks recorded.")


    # =========================================================================
    # TAB 2: MATCHUPS & START/SIT
    # =========================================================================
    with tab_start_sit:
        col_start_sit_title, col_start_sit_refresh = st.columns([5, 1], vertical_alignment="center")
        with col_start_sit_title:
            st.subheader(f"Week {active_week} Matchup & Starting Lineup Audit")
        with col_start_sit_refresh:
            if st.button("🔄 Refresh", key=f"refresh_live_scores_{selected_league_id}", use_container_width=True, help="Re-fetches live scores and game status now, instead of waiting for the normal cache window."):
                fetch_league_data.clear()
                st.rerun()

        roster_players = get_roster_players(user_roster, players)

        # Live game status per NFL team this week, used to badge each player
        # ("Live" / "Final" / "Not Started" / "Bye") independently of the
        # points hybrid below - get_weekly_stats alone can't tell a game
        # still in progress apart from one that already finished.
        game_status_raw = get_nfl_game_status_raw(active_season, active_week)
        team_status_map = build_team_game_status_map(game_status_raw)

        week_matchups = league_data.get("matchups") or []
        my_m_obj = next((m for m in week_matchups if m.get("roster_id") == user_roster["roster_id"]), None)
        my_matchup_id = my_m_obj.get("matchup_id") if my_m_obj else None
        my_live_points = (my_m_obj.get("players_points") or {}) if my_m_obj else {}

        # Live-adjusted points: a player whose game hasn't started yet still
        # uses the static pre-game projection (as before); once their game
        # has started - live or already finished - their real matchup points
        # take over instead of a stale projection.
        proj_lookup = build_live_adjusted_points_lookup(
            player_ids=[p.get("player_id") for p in roster_players],
            weekly_projections=weekly_projections,
            weekly_stats=weekly_stats,
            scoring_settings=scoring,
            player_db=players,
            live_points=my_live_points,
        )

        audit = audit_weekly_lineup(
            user_roster=user_roster,
            roster_players=roster_players,
            projections_lookup=proj_lookup,
            roster_positions=roster_pos,
            player_db=players,
            weekly_stats=weekly_stats,
        )

        # Actual-only points: 0.0 for anyone whose game hasn't started, never
        # a projection - this is a live scoreboard reading ("what has your
        # lineup really scored so far"), kept deliberately separate from the
        # hybrid proj_lookup above ("what is your lineup likely to finish
        # with"), so the two are never blended into one ambiguous number.
        actual_lookup = build_actual_points_only_lookup(
            player_ids=[p.get("player_id") for p in roster_players],
            weekly_stats=weekly_stats,
            live_points=my_live_points,
        )
        user_actual_total = sum_points_for_starters(
            starters=user_roster.get("starters"),
            roster_positions=roster_pos,
            points_lookup=actual_lookup,
        )

        my_lineup_rows = []
        for p_obj, pts, slot in audit["active_starters"]:
            pid = p_obj.get("player_id")
            status_label = get_player_game_status_label(p_obj.get("team"), team_status_map)
            my_lineup_rows.append({
                "Avatar": get_player_avatar_url(pid, p_obj.get("position"), p_obj.get("team")),
                "Slot": slot,
                "Player": p_obj.get("full_name") or pid,
                "NFL Team": p_obj.get("team") or "FA",
                "Projected": f"{pts:.1f} pts",
                "Status": status_label,
            })

        opp_roster = None
        opp_m_obj = None
        if my_matchup_id is not None:
            for m in week_matchups:
                if m.get("matchup_id") == my_matchup_id and m.get("roster_id") != user_roster["roster_id"]:
                    opp_m_obj = m
                    opp_roster = next((r for r in rosters if r.get("roster_id") == m.get("roster_id")), None)
                    break

        c1_empty = None
        user_name = user_map.get(user["user_id"], "You")
        opp_name = "No Opponent (Bye)"
        opp_proj = 0.0
        opp_actual_total = 0.0
        opp_lineup_rows = []

        if opp_roster:
            opp_name = user_map.get(opp_roster.get("owner_id"), f"Team {opp_roster['roster_id']}")
            opp_starter_pids = (
                opp_m_obj.get("starters")
                if opp_m_obj and opp_m_obj.get("starters")
                else (opp_roster.get("starters") or [])
            )
            opp_live_points = opp_m_obj.get("players_points") or {} if opp_m_obj else {}
            opp_points_lookup = build_live_adjusted_points_lookup(
                player_ids=[pid for pid in opp_starter_pids if pid and pid != "0"],
                weekly_projections=weekly_projections,
                weekly_stats=weekly_stats,
                scoring_settings=scoring,
                player_db=players,
                live_points=opp_live_points,
            )
            opp_actual_lookup = build_actual_points_only_lookup(
                player_ids=[pid for pid in opp_starter_pids if pid and pid != "0"],
                weekly_stats=weekly_stats,
                live_points=opp_live_points,
            )
            opp_actual_total = sum_points_for_starters(
                starters=opp_starter_pids,
                roster_positions=roster_pos,
                points_lookup=opp_actual_lookup,
            )
            for s_idx, pid in enumerate(opp_starter_pids):
                slot_name = roster_pos[s_idx] if s_idx < len(roster_pos) else "FLEX"
                if pid and pid != "0":
                    p = players.get(pid, {})
                    p_proj = opp_points_lookup.get(pid, 0.0)
                    opp_proj += p_proj
                    opp_lineup_rows.append({
                        "Avatar": get_player_avatar_url(pid, p.get("position"), p.get("team")),
                        "Slot": slot_name,
                        "Player": p.get("full_name") or pid,
                        "NFL Team": p.get("team") or "FA",
                        "Projected": f"{p_proj:.1f} pts",
                        "Status": get_player_game_status_label(p.get("team"), team_status_map),
                    })
                else:
                    opp_lineup_rows.append({
                        "Avatar": "",
                        "Slot": slot_name,
                        "Player": "— Empty Slot —",
                        "NFL Team": "—",
                        "Projected": "0.0 pts",
                        "Status": "bye",
                    })

        # Render Executive Head-to-Head Arena Card
        st.html(render_matchup_arena_html(
            user_name=user_name,
            user_actual=user_actual_total,
            user_proj=audit["active_points_total"],
            user_ceiling=audit["optimal_points_total"],
            opp_name=opp_name,
            opp_actual=opp_actual_total,
            opp_proj=opp_proj,
            active_week=active_week,
        ))

        # Optimization alerts
        if audit["start_sit_swaps"]:
            st.markdown(
                f"""
                <div style='background: rgba(14, 165, 233, 0.12); border: 1px solid rgba(56, 189, 248, 0.35); border-radius: 8px; padding: 10px 14px; margin-bottom: 14px; display: flex; align-items: center; justify-content: space-between;'>
                    <div>
                        <strong style='color: #38bdf8;'>⚡ Lineup Optimization Available:</strong>
                        <span style='color: #cbd5e1; font-size: 0.86rem; margin-left: 6px;'>You can gain <strong style='color: #34d399;'>+{audit['points_differential']:.1f} pts</strong> with optimal starter swaps.</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            for swap in audit["start_sit_swaps"]:
                st.html(render_start_sit_card_html(swap))
        else:
            st.markdown(
                f"""
                <div style='background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(16, 185, 129, 0.35); border-radius: 8px; padding: 10px 14px; margin-bottom: 14px;'>
                    <strong style='color: #34d399;'>⭐ Optimal Lineup Configured:</strong>
                    <span style='color: #cbd5e1; font-size: 0.86rem; margin-left: 6px;'>Your active starting lineup maximizes projected points for Week {active_week}.</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Active Starter Injury Alerts
        if audit["injury_alerts"]:
            st.markdown(
                """
                <div style='background: rgba(244, 63, 94, 0.12); border: 1px solid rgba(244, 63, 94, 0.35); border-radius: 8px; padding: 10px 14px; margin: 16px 0 10px 0;'>
                    <strong style='color: #fb7185;'>⚠️ Active Starter Injury Risk Detected:</strong>
                    <span style='color: #cbd5e1; font-size: 0.86rem; margin-left: 6px;'>The following players in your starting lineup carry official injury designations:</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            for inj in audit["injury_alerts"]:
                sname = inj["starter"].get("full_name")
                status = inj["status"]
                slot = inj["slot"]
                pivot = inj.get("pivot")
                s_avatar = get_player_avatar_url(inj["starter"].get("player_id"), inj["starter"].get("position"), inj["starter"].get("team"))
                if pivot:
                    pname = pivot[0].get("full_name")
                    pproj = pivot[1]
                    p_avatar = get_player_avatar_url(pivot[0].get("player_id"), pivot[0].get("position"), pivot[0].get("team"))
                    pivot_html = f"""
                    <div style='display: flex; align-items: center; gap: 8px;'>
                        <span style='color: #38bdf8; font-size: 0.8rem; font-weight: 700;'>➔ Recommended Pivot:</span>
                        <img src='{p_avatar}' class='player-avatar-44' style='width: 32px; height: 32px;' onerror=\"this.src='https://sleepercdn.com/images/v2/icons/player_default.webp'\" />
                        <span style='font-weight: 700; color: #f8fafc; font-size: 0.85rem;'>{pname}</span>
                        <span style='color: #34d399; font-weight: 700; font-size: 0.8rem;'>({pproj:.1f} pts)</span>
                    </div>
                    """
                else:
                    pivot_html = "<span style='color: #fb7185; font-size: 0.8rem; font-style: italic;'>No healthy bench substitute found</span>"

                st.markdown(
                    f"""
                    <div class='injury-alert-card' style='background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(244, 63, 94, 0.25); border-radius: 8px; padding: 10px 14px; margin-bottom: 8px; display: flex; align-items: center; justify-content: space-between; gap: 12px;'>
                        <div style='display: flex; align-items: center; gap: 10px;'>
                            <span style='background: rgba(244, 63, 94, 0.2); color: #fb7185; border: 1px solid rgba(244, 63, 94, 0.4); border-radius: 4px; padding: 2px 6px; font-size: 0.7rem; font-weight: 900;'>{status.upper()}</span>
                            <img src='{s_avatar}' class='player-avatar-44' style='width: 36px; height: 36px;' onerror=\"this.src='https://sleepercdn.com/images/v2/icons/player_default.webp'\" />
                            <div>
                                <span style='font-weight: 800; color: #f8fafc; font-size: 0.9rem;'>{sname}</span>
                                <span style='color: #94a3b8; font-size: 0.76rem; margin-left: 6px;'>({slot} • {inj['starter_proj']:.1f} pts)</span>
                            </div>
                        </div>
                        {pivot_html}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        # Always-visible side-by-side lineups (no expander click needed).
        # Wrapped in a keyed container so the mobile media query above can
        # target this specific stHorizontalBlock and stack the two columns
        # instead of squeezing two full lineup tables into half-width each.
        if my_lineup_rows or (opp_roster and opp_lineup_rows):
            with st.container(key="lineup_vs_columns"):
                col_my_lineup, col_opp_lineup = st.columns(2, gap="medium")
                with col_my_lineup:
                    if my_lineup_rows:
                        st.markdown(f"#### {user_name}")
                        st.html(render_opponent_lineup_html(my_lineup_rows))
                with col_opp_lineup:
                    if opp_roster and opp_lineup_rows:
                        st.markdown(f"#### {opp_name}")
                        st.html(render_opponent_lineup_html(opp_lineup_rows))


    # =========================================================================
    # TAB 3: ADD/DROPS & WAIVERS (Moved Before Power Rankings)
    # =========================================================================
    with tab_waivers:
        st.subheader("Intelligent Waiver Wire & Add/Drop Assistant")

        roster_players = get_roster_players(user_roster, players)
        free_agents = get_free_agents(rosters, players, roster_positions=roster_pos)

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
                    key=f"waiver_perspective_{selected_league_id}",
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
                key=f"waiver_protection_{selected_league_id}",
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

        def render_waiver_player_chip(p_obj, is_add=True, tag=None, displaced_name=None):
            pid = p_obj.get("player_id")
            name = p_obj.get("full_name") or pid
            pos = p_obj.get("position", "UTIL")
            team = p_obj.get("team", "FA")
            age = safe_age_display(p_obj.get("age"))
            age_suffix = f" • Age {age}" if age != "—" else ""
            avatar = get_player_avatar_url(pid, pos, team)
            pos_lower = pos.lower() if pos else "util"
            pos_cls = f"badge-{pos_lower}" if f"badge-{pos_lower}" in ("badge-qb", "badge-rb", "badge-wr", "badge-te", "badge-k", "badge-def") else "badge-rb"

            # Add player dynasty & redraft metrics
            dyn_data = primary_lookup.get(pid, {})
            ros_data = redraft_lookup.get(pid, {})

            dyn_val = dyn_data.get("market_value", 0.0)
            ros_val = ros_data.get("market_value", 0.0)

            dyn_o_ecr = dyn_data.get("rank_ecr_overall", 999.0)
            dyn_p_ecr = dyn_data.get("rank_ecr_pos", dyn_data.get("rank_ecr", 999.0))
            ros_o_rank = ros_data.get("rank_ecr_overall", 999.0)
            ros_p_rank = ros_data.get("rank_ecr_pos", ros_data.get("rank_ecr", 999.0))

            dyn_o_str = f"#{int(dyn_o_ecr)}" if (dyn_o_ecr and dyn_o_ecr < 900) else "—"
            dyn_p_str = f"{pos}{int(dyn_p_ecr)}" if (dyn_p_ecr and dyn_p_ecr < 900) else "—"
            ros_o_str = f"#{int(ros_o_rank)}" if (ros_o_rank and ros_o_rank < 900) else "—"
            ros_p_str = f"{pos}{int(ros_p_rank)}" if (ros_p_rank and ros_p_rank < 900) else "—"

            tag_html = ""
            if tag:
                bg_col = "rgba(16, 185, 129, 0.18)" if "STARTER" in tag.upper() else "rgba(56, 189, 248, 0.15)"
                text_col = "#34d399" if "STARTER" in tag.upper() else "#38bdf8"
                tag_html = f"<span style='background: {bg_col}; color: {text_col}; font-size: 0.68rem; font-weight: 700; padding: 2px 6px; border-radius: 4px; text-transform: uppercase;'>{tag}</span>"

            displaced_html = ""
            if displaced_name:
                displaced_html = f"<div style='margin-top: 4px; font-size: 0.78rem; color: #38bdf8;'>↳ Displaces <b>{displaced_name}</b> in starting lineup</div>"

            chip_html = f"""
            <div style='display: flex; gap: 12px; align-items: center; background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 10px 12px;'>
                <img src='{avatar}' class='player-avatar-44' onerror=\"this.src='https://sleepercdn.com/images/v2/icons/player_default.webp'\" />
                <div style='flex: 1; min-width: 0;'>
                    <div style='display: flex; align-items: center; gap: 6px; flex-wrap: wrap;'>
                        <span style='font-size: 1.02rem; font-weight: 700; color: #ffffff;'>{name}</span>
                        <span class='badge-pos {pos_cls}'>{pos}</span>
                        <span style='color: #94a3b8; font-size: 0.82rem;'>{team}{age_suffix}</span>
                        {tag_html}
                    </div>
                    <div style='display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; font-size: 0.76rem;'>
                        <span class='rank-pill'>Dynasty: {dyn_val:,.0f} pts ({dyn_o_str} Ovr • {dyn_p_str})</span>
                        <span class='rank-pill rank-pill-highlight'>ROS Value: {ros_val:,.0f} pts ({ros_o_str} Ovr • {ros_p_str})</span>
                    </div>
                    {displaced_html}
                </div>
            </div>
            """
            return chip_html

        starter_upgrades = waivers.get("starter_upgrades", [])
        cross_upgrades = waivers.get("cross_pos_upgrades", [])
        ir_suggestions = waivers.get("ir_suggestions", [])

        # Collect unique adds
        adds_list = []
        seen_add_ids = set()
        for s in starter_upgrades:
            ap = s.get("add_player")
            if not ap:
                continue
            pid = ap.get("player_id")
            if pid and pid not in seen_add_ids:
                seen_add_ids.add(pid)
                d_p = s.get("displaced_player")
                d_name = (d_p.get("full_name") or d_p.get("player_id")) if d_p else None
                adds_list.append({
                    "player": ap,
                    "is_starter": True,
                    "tag": "Starter Upgrade",
                    "displaced_name": d_name,
                    "val": float(active_lookup.get(pid, {}).get("market_value") or 0.0),
                })

        for s in cross_upgrades:
            ap = s.get("add_player")
            if not ap:
                continue
            pid = ap.get("player_id")
            if pid and pid not in seen_add_ids:
                seen_add_ids.add(pid)
                adds_list.append({
                    "player": ap,
                    "is_starter": False,
                    "tag": "Bench Upgrade",
                    "displaced_name": None,
                    "val": float(active_lookup.get(pid, {}).get("market_value") or 0.0),
                })

        # Sort adds: starter upgrades first, then by active valuation descending
        adds_list.sort(key=lambda x: (0 if x["is_starter"] else 1, -x["val"]))

        # Collect unique drops from recommended cuts
        drops_list = []
        seen_drop_ids = set()
        for s in starter_upgrades + cross_upgrades:
            dp = s.get("drop_player")
            if dp:
                pid = dp.get("player_id")
                if pid and pid not in seen_drop_ids:
                    seen_drop_ids.add(pid)
                    drops_list.append({
                        "player": dp,
                        "val": float(active_lookup.get(pid, {}).get("market_value") or 0.0),
                    })
            for cand in s.get("all_drop_candidates", []):
                cdp = cand.get("drop_player")
                if cdp:
                    cpid = cdp.get("player_id")
                    if cpid and cpid not in seen_drop_ids:
                        seen_drop_ids.add(cpid)
                        drops_list.append({
                            "player": cdp,
                            "val": float(active_lookup.get(cpid, {}).get("market_value") or 0.0),
                        })

        # Sort drops: lowest active valuation first (best cut candidates first)
        drops_list.sort(key=lambda x: x["val"])

        if adds_list:
            adds_html = [
                render_waiver_player_chip(
                    item["player"],
                    is_add=True,
                    tag=item["tag"],
                    displaced_name=item["displaced_name"],
                )
                for item in adds_list[:8]
            ]
            drops_html = [
                render_waiver_player_chip(
                    item["player"],
                    is_add=False,
                )
                for item in drops_list[:8]
            ]

            ir_banner_html = ""
            if ir_suggestions:
                ir_items = []
                for ir in ir_suggestions:
                    pname = ir["player"].get("full_name") or ir["player"].get("player_id")
                    reason = ir.get("reason", "IR Eligible")
                    ir_items.append(f"Move <b>{pname}</b> ({reason}) to IR")
                ir_text = " • ".join(ir_items)
                ir_banner_html = f"""
                <div style='background: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.25); border-radius: 8px; padding: 10px 14px; margin-bottom: 16px; display: flex; align-items: center; gap: 10px;'>
                    <span style='font-size: 1.1rem;'>💡</span>
                    <div style='font-size: 0.85rem; color: #fde68a;'>
                        <b>IR Slot Optimization:</b> {ir_text} ➔ <i>Frees up active bench space for a free agent addition.</i>
                    </div>
                </div>
                """

            horizon_tag = "DYNASTY HORIZON" if eval_dynasty else "REST OF SEASON (ROS)"

            card_html = f"""
            <div class='card-container' style='margin-bottom: 24px;'>
                <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid rgba(255, 255, 255, 0.08); flex-wrap: wrap; gap: 8px;'>
                    <div>
                        <h3 style='margin: 0; font-size: 1.15rem; font-weight: 700; color: #f8fafc;'>⚡ Waiver Wire & Add/Drop Recommendations</h3>
                        <span style='font-size: 0.82rem; color: #94a3b8;'>Consolidated recommendations based on your active roster and available free agents</span>
                    </div>
                    <div>
                        <span class='status-capsule status-contender' style='font-size: 0.75rem; font-weight: 700;'>
                            {horizon_tag}
                        </span>
                    </div>
                </div>

                {ir_banner_html}

                <div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 20px;'>
                    <!-- LEFT SIDE: PLAYERS TO ADD -->
                    <div style='background: rgba(16, 185, 129, 0.03); border: 1px solid rgba(16, 185, 129, 0.2); border-radius: 10px; padding: 14px;'>
                        <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid rgba(16, 185, 129, 0.15);'>
                            <span style='font-size: 0.82rem; font-weight: 800; color: #34d399; letter-spacing: 0.05em; text-transform: uppercase;'>
                                ➕ Target Adds (Free Agents)
                            </span>
                            <span style='background: rgba(16, 185, 129, 0.15); color: #34d399; font-size: 0.72rem; font-weight: 700; padding: 2px 8px; border-radius: 12px;'>
                                {len(adds_list)} Recommended
                            </span>
                        </div>
                        <div style='display: flex; flex-direction: column; gap: 10px;'>
                            {''.join(adds_html)}
                        </div>
                    </div>

                    <!-- RIGHT SIDE: PLAYERS TO DROP -->
                    <div style='background: rgba(239, 68, 68, 0.03); border: 1px solid rgba(239, 68, 68, 0.2); border-radius: 10px; padding: 14px;'>
                        <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid rgba(239, 68, 68, 0.15);'>
                            <span style='font-size: 0.82rem; font-weight: 800; color: #f87171; letter-spacing: 0.05em; text-transform: uppercase;'>
                                ➖ Droppable Players (Bench Cuts)
                            </span>
                            <span style='background: rgba(239, 68, 68, 0.15); color: #f87171; font-size: 0.72rem; font-weight: 700; padding: 2px 8px; border-radius: 12px;'>
                                {len(drops_list)} Candidates
                            </span>
                        </div>
                        <div style='display: flex; flex-direction: column; gap: 10px;'>
                            {''.join(drops_html) if drops_html else "<div style='color: #94a3b8; font-size: 0.85rem; padding: 12px;'>No drop required (open roster / IR spots available).</div>"}
                        </div>
                    </div>
                </div>
            </div>
            """
            st.html("\n".join(l.lstrip() for l in card_html.splitlines()))
        else:
            # Empty state notification if no waiver suggestions found
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
            avail_fa_pos = ["ALL", "QB", "RB", "WR", "TE"]
            if any(p == "K" for p in roster_pos):
                avail_fa_pos.append("K")
            if any(p in ("DEF", "DST") for p in roster_pos):
                avail_fa_pos.append("DEF")
            if any(p in ("IDP", "IDP_FLEX", "LB", "DB", "DL") for p in roster_pos):
                for idp_p in ["LB", "DB", "DL"]:
                    if idp_p not in avail_fa_pos:
                        avail_fa_pos.append(idp_p)
            pos_filter = st.selectbox("Filter Position:", avail_fa_pos, key=f"fa_pos_filter_{selected_league_id}")
        with c_f2:
            search_query = st.text_input("Search Player Name:", "")

        is_fa_redraft = not eval_dynasty
        fa_rows = []
        for fa in free_agents:
            pos = fa.get("position") or ""
            if pos_filter != "ALL" and pos != pos_filter:
                continue
            pname = fa.get("full_name") or fa.get("player_id", "")
            if search_query and search_query.lower() not in pname.lower():
                continue

            pid = fa.get("player_id")
            p_val_data = active_lookup.get(pid, {})
            val = float(p_val_data.get("market_value") or 0.0)
            ecr = p_val_data.get("rank_ecr_pos", p_val_data.get("rank_ecr", 999.0))
            o_ecr = p_val_data.get("rank_ecr_overall", 999.0)
            fc_v = p_val_data.get("fc_val")
            ktc_v = p_val_data.get("ktc_val")
            dp_v = p_val_data.get("dp_val")
            proj_ppg = p_val_data.get("proj_ppg")
            fp_o = p_val_data.get("fp_ecr_overall")
            fp_p = p_val_data.get("fp_ecr_pos")
            ktc_redraft_val = p_val_data.get("ktc_redraft_val")

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

            try:
                if fp_o is not None and float(fp_o) < 500:
                    fp_str = f"#{int(float(fp_o))}"
                elif fp_p is not None and float(fp_p) < 200:
                    fp_str = f"{pos}{int(float(fp_p))}"
                else:
                    fp_str = "—"
            except (ValueError, TypeError):
                fp_str = "—"

            try:
                proj_str = f"{float(proj_ppg):.1f} PPG" if proj_ppg is not None else "—"
            except (ValueError, TypeError):
                proj_str = "—"

            try:
                ktc_redraft_str = f"{float(ktc_redraft_val):,.0f} pts" if ktc_redraft_val is not None else "—"
            except (ValueError, TypeError):
                ktc_redraft_str = "—"

            try:
                raw_o_ecr = float(o_ecr) if (o_ecr is not None and float(o_ecr) < 900) else 9999.0
            except (ValueError, TypeError):
                raw_o_ecr = 9999.0

            try:
                raw_p_ecr = float(ecr) if (ecr is not None and float(ecr) < 900) else 9999.0
            except (ValueError, TypeError):
                raw_p_ecr = 9999.0

            fa_rows.append({
                "pid": str(pid),
                "Avatar": get_player_avatar_url(pid, pos, fa.get("team")),
                "Player": pname,
                "Pos": pos,
                "NFL Team": fa.get("team") or "FA",
                "age": fa.get("age"),
                "Consensus Value": f"{val:,.0f} pts",
                "Overall ECR": overall_ecr_str,
                "Pos ECR": pos_ecr_str,
                "FantasyCalc": fc_str,
                "KeepTradeCut": ktc_str,
                "DynastyProcess": dp_str,
                "FantasyPros ECR": fp_str,
                "Sleeper Proj PPG": proj_str,
                "KTC Redraft Value": ktc_redraft_str,
                "_raw_val": val,
                "_overall_ecr": raw_o_ecr,
                "_pos_ecr": raw_p_ecr,
                "_ktc": float(ktc_v) if (ktc_v is not None and str(ktc_v).replace(".", "", 1).isdigit()) else 0.0,
                "_fc": float(fc_v) if (fc_v is not None and str(fc_v).replace(".", "", 1).isdigit()) else 0.0,
                "_dp": float(dp_v) if (dp_v is not None and str(dp_v).replace(".", "", 1).isdigit()) else 0.0,
                "_fp_ecr": float(fp_o) if (fp_o is not None and float(fp_o) < 500) else 9999.0,
                "_proj_ppg": float(proj_ppg or 0.0),
                "_ktc_redraft_val": float(ktc_redraft_val or 0.0),
                "_name": pname.lower(),
            })

        fa_rows.sort(key=lambda x: x["_raw_val"], reverse=True)
        if fa_rows:
            c_fasort1, c_fasort2, c_fasort3 = st.columns([2, 1, 1], vertical_alignment="bottom")
            with c_fasort1:
                sort_options = (
                    ["Consensus Value", "Overall Rank", "Pos Rank", "Sleeper Projections PPG", "FantasyPros ECR", "KTC Redraft Value", "Player Name"]
                    if is_fa_redraft
                    else ["Consensus Value", "Overall Rank", "Pos Rank", "KeepTradeCut", "FantasyCalc", "DynastyProcess", "Player Name"]
                )
                sort_fa_col = st.selectbox(
                    "Sort Free Agents By:",
                    sort_options,
                    key=f"fa_sort_col_{'redraft' if is_fa_redraft else 'dynasty'}_{selected_league_id}"
                )
            with c_fasort2:
                sort_fa_order = st.selectbox(
                    "Order:",
                    ["Descending (High / Best)", "Ascending (Low)"],
                    key=f"fa_sort_order_{'redraft' if is_fa_redraft else 'dynasty'}_{selected_league_id}"
                )
            with c_fasort3:
                st.caption(f"Showing top {min(len(fa_rows), 50)} of {len(fa_rows)} matching free agents.")

            sorted_fa = list(fa_rows)
            is_desc = "Descending" in sort_fa_order
            if sort_fa_col == "Consensus Value":
                sorted_fa.sort(key=lambda x: x["_raw_val"], reverse=is_desc)
            elif sort_fa_col in ("Overall Rank", "Overall ECR"):
                sorted_fa.sort(key=lambda x: x["_overall_ecr"], reverse=not is_desc)
            elif sort_fa_col in ("Pos Rank", "Pos ECR"):
                sorted_fa.sort(key=lambda x: x["_pos_ecr"], reverse=not is_desc)
            elif sort_fa_col == "KeepTradeCut":
                sorted_fa.sort(key=lambda x: x["_ktc"], reverse=is_desc)
            elif sort_fa_col == "FantasyCalc":
                sorted_fa.sort(key=lambda x: x["_fc"], reverse=is_desc)
            elif sort_fa_col == "FantasyPros ECR":
                sorted_fa.sort(key=lambda x: x["_fp_ecr"], reverse=not is_desc)
            elif sort_fa_col == "Sleeper Projections PPG":
                sorted_fa.sort(key=lambda x: x["_proj_ppg"], reverse=is_desc)
            elif sort_fa_col == "KTC Redraft Value":
                sorted_fa.sort(key=lambda x: x["_ktc_redraft_val"], reverse=is_desc)
            elif sort_fa_col == "DynastyProcess":
                sorted_fa.sort(key=lambda x: x["_dp"], reverse=is_desc)
            elif sort_fa_col == "Player Name":
                sorted_fa.sort(key=lambda x: x["_name"], reverse=not is_desc)

            for idx, r in enumerate(sorted_fa, start=1):
                r["Rank"] = f"#{idx}"

            st.html(render_market_table_html(sorted_fa[:50], is_redraft=is_fa_redraft))
        else:
            st.info("No free agents match current filter criteria.")



    # =========================================================================
    # TAB 4: POWER RANKINGS & PLAYOFF ODDS
    # =========================================================================
    with tab_power:
        st.subheader("League Power Rankings & Playoff Simulations")

        def render_simulation_view():
            playoff_start = selected_league.get("settings", {}).get("playoff_week_start", 15)
            team_week_expectations = {
                r["roster_id"]: compute_team_weekly_expectations(
                    roster=r,
                    roster_players=all_rosters_players.get(r["roster_id"], []),
                    weekly_projections_by_week=weekly_projections_by_week,
                    scoring_settings=scoring,
                    roster_positions=roster_pos,
                )
                for r in rosters
            }

            max_sim_week = max(1, active_week)
            if max_sim_week == 1:
                snap_options = ["Week 1 (Kickoff)"]
                snap_values = [1]
            else:
                snap_options = [
                    (f"Week {w} (Current)" if w == max_sim_week else (f"Week {w} (Kickoff)" if w == 1 else f"Week {w}"))
                    for w in range(1, max_sim_week + 1)
                ]
                snap_values = list(range(1, max_sim_week + 1))

            col_snap, col_snap_info = st.columns([2.6, 4.4], vertical_alignment="center")
            with col_snap:
                chosen_snap = st.selectbox(
                    "Simulation Snapshot:",
                    snap_options,
                    index=len(snap_options) - 1,
                    key="sim_snapshot_week_selector",
                    help="View what the Monte Carlo projections and playoff odds were as of any prior week."
                )
            selected_snap_week = snap_values[snap_options.index(chosen_snap)]

            with col_snap_info:
                if selected_snap_week == 1:
                    st.caption("🏁 **Preseason Baseline:** Records start at 0-0; simulates entire season schedule based on roster strength.")
                elif selected_snap_week == max_sim_week:
                    st.caption(f"⚡ **Active Week {max_sim_week}:** Current live standings seeded; simulates remaining weeks to playoffs.")
                else:
                    st.caption(f"⏪ **Historical Snapshot (Week {selected_snap_week}):** Standings reconstructed through Week {selected_snap_week - 1}; simulated forward.")

            if selected_snap_week == max_sim_week:
                sim_results = live_sim_results
            else:
                with st.spinner(f"Simulating remaining season ({chosen_snap}, 1,000 iterations)..."):
                    sim_results = run_historical_simulation_snapshot(
                        league=selected_league,
                        rosters=rosters,
                        schedule=schedule,
                        team_week_expectations=team_week_expectations,
                        snapshot_week=selected_snap_week,
                        current_week=active_week,
                        playoff_week_start=playoff_start,
                        num_simulations=1000,
                    )

            sample_res = next(iter(sim_results.values())) if sim_results else {}
            p_count = sample_res.get("playoff_teams_count", 6)
            st.info(f"Playoff Format: Top {p_count} Teams qualify for the postseason. Simulation as of **{chosen_snap}**.")

            ranked_sim = sorted(sim_results.values(), key=lambda t: t["power_score"], reverse=True)
            table_data = []
            for rank_idx, t in enumerate(ranked_sim, 1):
                rid = t["roster_id"]
                roster_for_record = next((r for r in rosters if r["roster_id"] == rid), {})
                mgr = user_map.get(roster_for_record.get("owner_id", ""), f"Team {rid}")
                r_settings = roster_for_record.get("settings", {})
                r_wins = r_settings.get("wins", 0)
                r_losses = r_settings.get("losses", 0)
                r_ties = r_settings.get("ties", 0)
                record_str = f"{r_wins}-{r_losses}" + (f"-{r_ties}" if r_ties else "")
                table_data.append({
                    "roster_id": rid,
                    "Rank": f"#{rank_idx}",
                    "Manager / Team": mgr,
                    "Record": record_str,
                    "Status": t.get("status_label", "In The Hunt"),
                    "status_code": t.get("status_code", "HUNT"),
                    "badge_icon": t.get("badge_icon", "🎯"),
                    "badge_color": t.get("badge_color", "#3b82f6"),
                    "Projected W-L": f"{t['avg_wins']:.1f} - {t['avg_losses']:.1f}",
                    "Starters PPG": f"{t['expected_pts']:.1f}",
                    "Bench PPG": f"{t.get('bench_depth_pts', 0.0):.1f}",
                    "Playoff Odds": f"{t['playoff_pct']:.1f}%",
                    "1st-Round Bye": f"{t['bye_pct']:.1f}%",
                    "Champ Odds": f"{t['champ_pct']:.1f}%",
                    "Season Power Score": f"{t['power_score']:.1f}",
                })

            formula_caption = sample_res.get("power_formula", "Season Power Score Formula: 40% Starters PPG + 35% Projected Wins + 15% Playoff Odds + 10% Bench Depth PPG.")
            st.caption(f"📊 {formula_caption}")
            st.html(render_power_simulation_table_html(table_data, user_roster["roster_id"]))

            # Week-by-Week Evolution History View - always visible, no click needed.
            st.markdown("#### 📈 Week-by-Week Evolution & Trends")
            with st.container(border=True):
                st.caption("Compare how projected wins, playoff odds, championship probabilities, and the composite Power Score have shifted week-by-week. \"Power Score Δ\" tracks the blended Power Score itself; \"Playoff Odds Δ\" tracks the simulated playoff probability alone - they can move independently since Power Score also weighs Starters PPG, Projected Wins, and Bench Depth.")
                all_mgr_names = [user_map.get(r.get("owner_id"), f"Team {r['roster_id']}") for r in rosters]
                user_mgr_name = user_map.get(user.get("user_id"), all_mgr_names[0] if all_mgr_names else "Team")
                default_team_idx = all_mgr_names.index(user_mgr_name) if user_mgr_name in all_mgr_names else 0

                inspect_team_name = st.selectbox(
                    "Select Team to Inspect Evolution:",
                    all_mgr_names,
                    index=default_team_idx,
                    key="sim_evo_team_sel",
                )
                target_roster = next((r for r in rosters if user_map.get(r.get("owner_id")) == inspect_team_name), rosters[0] if rosters else None)
                if target_roster:
                    target_rid = target_roster["roster_id"]
                    with st.spinner("Calculating week-by-week progression..."):
                        evo_history = compute_weekly_evolution_history(
                            league=selected_league,
                            rosters=rosters,
                            schedule=schedule,
                            team_week_expectations=team_week_expectations,
                            current_week=active_week,
                            playoff_week_start=playoff_start,
                            num_simulations=1000,
                            current_sim_results=live_sim_results,
                        )

                    evo_rows = []
                    prev_playoff_pct = None
                    prev_power_score = None
                    for w in sorted(evo_history.keys()):
                        w_res = evo_history[w].get(target_rid, {})
                        p_pct = w_res.get("playoff_pct", 0.0)
                        p_score = w_res.get("power_score", 0.0)

                        if prev_playoff_pct is not None:
                            odds_diff = p_pct - prev_playoff_pct
                            if odds_diff > 0.5:
                                odds_trend_badge = f"<span style='color: #34d399; font-weight: 700;'>+{odds_diff:.1f}% ↑</span>"
                            elif odds_diff < -0.5:
                                odds_trend_badge = f"<span style='color: #fb7185; font-weight: 700;'>{odds_diff:.1f}% ↓</span>"
                            else:
                                # Inside the +/-0.5 neutral band: still show the real (small)
                                # diff instead of a hardcoded "0.0%", which previously masked
                                # any genuine sub-threshold movement (e.g. a true -0.5 or +0.1
                                # diff rendered as if it were exactly zero).
                                odds_trend_badge = f"<span style='color: #94a3b8;'>{odds_diff:+.1f}%</span>"
                        else:
                            odds_trend_badge = "<span style='color: #64748b;'>Baseline</span>"
                        prev_playoff_pct = p_pct

                        # Power Score is a blended 0-100 composite (Starters PPG + Projected
                        # Wins + Playoff Odds + Bench Depth, each normalized to 0-100), so it
                        # sits on the same nominal scale as playoff_pct but moves less sharply
                        # week to week since it dampens the raw simulation swing with three
                        # steadier inputs. The same 0.5-point neutral band is kept here since
                        # it empirically separates real movement from noise on this scale too.
                        if prev_power_score is not None:
                            score_diff = p_score - prev_power_score
                            if score_diff > 0.5:
                                score_trend_badge = f"<span style='color: #34d399; font-weight: 700;'>+{score_diff:.1f} ↑</span>"
                            elif score_diff < -0.5:
                                score_trend_badge = f"<span style='color: #fb7185; font-weight: 700;'>{score_diff:.1f} ↓</span>"
                            else:
                                # Same fix as odds_trend_badge above: show the real sub-threshold
                                # diff instead of a hardcoded "0.0".
                                score_trend_badge = f"<span style='color: #94a3b8;'>{score_diff:+.1f}</span>"
                        else:
                            score_trend_badge = "<span style='color: #64748b;'>Baseline</span>"
                        prev_power_score = p_score

                        init_w = w_res.get("initial_wins", 0)
                        init_l = w_res.get("initial_losses", 0)
                        w_rec = f"{init_w}-{init_l}" if w > 1 else "0-0"
                        w_label = f"Week {w} (Kickoff)" if w == 1 else (f"Week {w} (Current)" if w == max_sim_week else f"Week {w}")

                        evo_rows.append({
                            "Week": w_label,
                            "Record Entering Wk": w_rec,
                            "Projected W-L": f"{w_res.get('avg_wins', 0):.1f} - {w_res.get('avg_losses', 0):.1f}",
                            "Playoff Odds": f"{p_pct:.1f}%",
                            "Bye Odds": f"{w_res.get('bye_pct', 0):.1f}%",
                            "Champ Odds": f"{w_res.get('champ_pct', 0):.1f}%",
                            "Power Score": f"{p_score:.1f}",
                            "Power Score Trend": score_trend_badge,
                            "Odds Trend": odds_trend_badge,
                        })

                    evo_html = """
                    <div class='table-responsive-wrapper'>
                    <table class='roster-table'>
                        <thead>
                            <tr>
                                <th style='text-align: left;'>Snapshot Week</th>
                                <th style='text-align: center;'>Record Entering</th>
                                <th style='text-align: center;'>Projected W-L</th>
                                <th style='text-align: center;'>Playoff Odds</th>
                                <th style='text-align: center;'>1st-Round Bye</th>
                                <th style='text-align: center;'>Champ Odds</th>
                                <th style='text-align: center;'>Power Score</th>
                                <th style='text-align: center;'>Power Score Δ</th>
                                <th style='text-align: center;'>Playoff Odds Δ</th>
                            </tr>
                        </thead>
                        <tbody>
                    """
                    for er in evo_rows:
                        evo_html += f"""
                        <tr>
                            <td style='text-align: left; font-weight: 700; color: #f8fafc;'>{er['Week']}</td>
                            <td style='text-align: center; color: #94a3b8; font-weight: 600;'>{er['Record Entering Wk']}</td>
                            <td style='text-align: center; font-weight: 600;'>{er['Projected W-L']}</td>
                            <td style='text-align: center;'><span class='rank-pill rank-pill-highlight'>{er['Playoff Odds']}</span></td>
                            <td style='text-align: center;'><span class='rank-pill'>{er['Bye Odds']}</span></td>
                            <td style='text-align: center;'><span class='rank-pill' style='color: #c084fc;'>{er['Champ Odds']}</span></td>
                            <td class='val-pill' style='text-align: center;'>{er['Power Score']}</td>
                            <td style='text-align: center;'>{er['Power Score Trend']}</td>
                            <td style='text-align: center;'>{er['Odds Trend']}</td>
                        </tr>
                        """
                    evo_html += """
                        </tbody>
                    </table>
                    </div>
                    """
                    st.html(evo_html)

        def render_ros_power_view():
            st.caption("ROS Asset Power Formula: 85% Starters Value + 15% Bench Depth (Tri-Source Consensus: Sleeper Multi-Week Projections + FantasyPros ECR + KTC Redraft Value). Purely consultative.")
            ros_res = compute_ros_power_rankings(all_ros_team_profiles, weight_starters=0.85, weight_bench=0.15)
            ranked_ros = sorted(ros_res.values(), key=lambda x: x["ros_score"], reverse=True)

            ros_data = []
            for rank_idx, t in enumerate(ranked_ros, 1):
                rid = t["roster_id"]
                ros_data.append({
                    "roster_id": rid,
                    "Rank": f"#{rank_idx}",
                    "Manager / Team": t["manager_name"],
                    "ROS Score": f"{t['ros_score']:.1f} / 100",
                    "Starters Val (85%)": f"{t['starters_val']:,.0f} pts",
                    "Bench Val (15%)": f"{t['bench_val']:,.0f} pts",
                    "Total ROS Value": f"{t['total_val']:,.0f} pts",
                    "Competitive Tier": t["status"].split("(")[0].strip() if t.get("status") else "Active",
                    "Category": t.get("category", "neutral"),
                })

            st.html(render_ros_power_table_html(ros_data, user_roster["roster_id"]))

            st.markdown("#### Complete ROS Lineup & Bench Breakdown")
            with st.container(border=True):
                inspect_mgr = st.selectbox("Select Team to Inspect (ROS):", [t["manager_name"] for t in ranked_ros], key=f"inspect_ros_team_{selected_league_id}")
                selected_prof = next(p for p in all_ros_team_profiles if p["manager_name"] == inspect_mgr)
                tot_val = selected_prof.get("total_value", 0.0)

                insp_sub_starters, insp_sub_bench = st.tabs([
                    f"ROS Starters ({len(selected_prof['starters'])})",
                    f"ROS Bench ({len(selected_prof['bench'])})",
                ])

                with insp_sub_starters:
                    st.caption(f"ROS Starting Lineup Valuation: **{selected_prof.get('starter_value', 0):,.0f} pts**")
                    st_rows = []
                    for a in selected_prof["starters"]:
                        pid = a.get("player_id")
                        pos = a.get("position") or "UTIL"
                        team = a.get("team") or "FA"
                        m_val = float(a.get("market_value") or 0.0)
                        p_data = redraft_lookup.get(pid, {})
                        ecr = a.get("rank_ecr") or p_data.get("rank_ecr_pos", 999.0)
                        o_ecr = p_data.get("rank_ecr_overall", 999.0)
                        pos_ecr_str = f"{pos}{int(ecr)}" if (ecr and ecr < 900) else "—"
                        overall_ecr_str = f"#{int(o_ecr)}" if (o_ecr and o_ecr < 900) else "—"
                        eq_str = f"{(m_val / tot_val * 100):.1f}%" if tot_val > 0 else "0.0%"
                        st_rows.append({
                            "Slot": a.get("slot") or "FLEX",
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
                    st.caption(f"ROS Bench Depth Valuation: **{selected_prof.get('bench_value', 0):,.0f} pts**")
                    bn_rows = []
                    for a in selected_prof["bench"]:
                        pid = a.get("player_id")
                        pos = a.get("position") or "UTIL"
                        team = a.get("team") or "FA"
                        m_val = float(a.get("market_value") or 0.0)
                        p_data = redraft_lookup.get(pid, {})
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

        def render_dynasty_power_view():
            st.caption("Dynasty Power Formula: 50% Starters Value + 30% Bench Depth + 20% Future Draft Capital (Industry Standard).")
            # dynasty_score/dynasty_rank are already set on every profile by
            # build_team_profiles (src/orchestration.py) - reused here
            # instead of a third recomputation of the same ranking.
            ranked_dyn = sorted(all_team_profiles, key=lambda p: p.get("dynasty_score", 0.0), reverse=True)

            dyn_data = []
            for t in ranked_dyn:
                rid = t["roster_id"]
                dyn_data.append({
                    "roster_id": rid,
                    "Rank": f"#{t.get('dynasty_rank', 0)}",
                    "Manager / Team": t["manager_name"],
                    "Dynasty Score": f"{t.get('dynasty_score', 0.0):.1f} / 100",
                    "Starters Val (50%)": f"{t.get('starter_value', 0.0):,.0f} pts",
                    "Bench Val (30%)": f"{t.get('bench_value', 0.0):,.0f} pts",
                    "Picks Capital (20%)": f"{t.get('picks_value', 0.0):,.0f} pts",
                    "Competitive Tier": t["status"].split("(")[0].strip() if t.get("status") else "Active",
                    "Category": t.get("category", "neutral"),
                })

            st.html(render_dynasty_power_table_html(dyn_data, user_roster["roster_id"]))

            st.markdown("#### Complete Team Roster & Pick Breakdown")
            with st.container(border=True):
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
                    for a in selected_prof["starters"]:
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
                            "Slot": a.get("slot") or "FLEX",
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
                        st.html(render_picks_table_html(pk_rows, show_equity=True))
                    else:
                        st.info("No draft pick assets in this league format.")

        def render_positional_room_view():
            if is_dynasty:
                col_scope, col_sort = st.columns([1.6, 2.4], vertical_alignment="bottom")
                with col_scope:
                    room_scope = st.radio(
                        "Valuation Scope:",
                        ["🏆 Dynasty Long-Term", "📅 Single-Season (ROS)"],
                        horizontal=True,
                        key="room_lb_scope_sel",
                    )
                use_redraft = ("Single-Season" in room_scope)
            else:
                col_sort = st.container()
                use_redraft = True

            show_picks = (is_dynasty and not use_redraft)

            if show_picks:
                st.caption("League-wide Positional Room & Draft Capital Leaderboard (KeepTradeCut / Dynasty Daddy style).")
            else:
                st.caption("League-wide Positional Room Leaderboard (evaluated on 3-Pillar Single-Season / ROS values).")

            room_data = build_positional_room_leaderboard(all_team_profiles, use_redraft=use_redraft, roster_positions=roster_pos)

            with col_sort:
                if show_picks:
                    sort_options = {
                        "Total Franchise Value": "total_val",
                        "QB Room Value": "qb_val",
                        "RB Room Value": "rb_val",
                        "WR Room Value": "wr_val",
                        "TE Room Value": "te_val",
                        "Draft Capital Value": "picks_val",
                    }
                else:
                    sort_options = {
                        "Total Roster Value": "total_val",
                        "QB Room Value": "qb_val",
                        "RB Room Value": "rb_val",
                        "WR Room Value": "wr_val",
                        "TE Room Value": "te_val",
                    }
                chosen_sort = st.selectbox(
                    "Sort Leaderboard By:",
                    list(sort_options.keys()),
                    index=0,
                    key=f"room_lb_sort_sel_{'redraft' if use_redraft else 'dynasty'}"
                )
                sort_key = sort_options[chosen_sort]

            if sort_key == "total_val":
                if not use_redraft:
                    sorted_rooms = sorted(room_data, key=lambda x: (x.get("dynasty_score", 0.0), x.get("total_val", 0.0)), reverse=True)
                else:
                    sorted_rooms = sorted(room_data, key=lambda x: (x.get("in_season_power_score", 0.0), x.get("total_val", 0.0)), reverse=True)
            else:
                sorted_rooms = sorted(room_data, key=lambda x: x[sort_key], reverse=True)

            for idx, r in enumerate(sorted_rooms, 1):
                if sort_key == "total_val":
                    if not use_redraft and r.get("dynasty_rank"):
                        r["disp_rank"] = r["dynasty_rank"]
                    elif use_redraft and r.get("in_season_rank"):
                        r["disp_rank"] = r["in_season_rank"]
                    else:
                        r["disp_rank"] = idx
                else:
                    r["disp_rank"] = idx

            st.html(render_positional_room_table_html(sorted_rooms, user_roster["roster_id"], sort_col=sort_key, show_picks=show_picks))

            st.markdown("#### 🔍 Franchise Positional Room Depth")
            with st.container(border=True):
                inspect_room_mgr = st.selectbox(
                    "Select Team to Inspect:",
                    [t["manager_name"] for t in sorted_rooms],
                    key=f"inspect_room_mgr_sel_{'redraft' if use_redraft else 'dynasty'}"
                )
                sel_room_data = next((r for r in room_data if r["manager_name"] == inspect_room_mgr), sorted_rooms[0])

                st.markdown(f"#### {inspect_room_mgr} — Room Asset Breakdown")
                if show_picks:
                    col_q, col_r, col_w, col_t, col_pk = st.columns(5)
                else:
                    col_q, col_r, col_w, col_t = st.columns(4)

                with col_q:
                    st.metric("QB Room", f"{sel_room_data['qb_val']:,.0f} pts", f"Rank #{sel_room_data['qb_rank']}")
                    for name in sel_room_data['top_qbs']:
                        st.caption(f"• {name}")
                with col_r:
                    st.metric("RB Room", f"{sel_room_data['rb_val']:,.0f} pts", f"Rank #{sel_room_data['rb_rank']}")
                    for name in sel_room_data['top_rbs']:
                        st.caption(f"• {name}")
                with col_w:
                    st.metric("WR Room", f"{sel_room_data['wr_val']:,.0f} pts", f"Rank #{sel_room_data['wr_rank']}")
                    for name in sel_room_data['top_wrs']:
                        st.caption(f"• {name}")
                with col_t:
                    st.metric("TE Room", f"{sel_room_data['te_val']:,.0f} pts", f"Rank #{sel_room_data['te_rank']}")
                    for name in sel_room_data['top_tes']:
                        st.caption(f"• {name}")
                if show_picks:
                    with col_pk:
                        st.metric("Draft Capital", f"{sel_room_data['picks_val']:,.0f} pts", f"Rank #{sel_room_data['picks_rank']}")
                        for name in sel_room_data['top_picks']:
                            st.caption(f"• {name}")

        if is_dynasty:
            sub_mc, sub_ros, sub_dyn, sub_rooms = st.tabs([
                "Season Standings & Playoff Simulation (Monte Carlo)",
                "ROS Asset Power Rankings",
                "Dynasty Asset Power Rankings",
                "Positional Room & Draft Capital Leaderboard",
            ])
            with sub_mc:
                render_simulation_view()
            with sub_ros:
                render_ros_power_view()
            with sub_dyn:
                render_dynasty_power_view()
            with sub_rooms:
                render_positional_room_view()
        else:
            sub_mc, sub_ros, sub_rooms = st.tabs([
                "Season Standings & Playoff Simulation (Monte Carlo)",
                "ROS Asset Power Rankings",
                "Positional Room Leaderboard",
            ])
            with sub_mc:
                render_simulation_view()
            with sub_ros:
                render_ros_power_view()
            with sub_rooms:
                render_positional_room_view()


    # =========================================================================
    # TAB 5: TRADE CENTER & TARGETED FINDER
    # =========================================================================
    with tab_trades:
        st.subheader("Trade Center & Targeted Acquisition Engine")

        def get_trade_prop_tier(prop):
            t = prop.get("tier")
            if t in ("Blockbuster", "Starter Upgrade", "Depth & Capital"):
                return t
            gives = prop.get("give_assets") or prop.get("sending") or []
            recvs = prop.get("receive_assets") or prop.get("receiving") or []
            give_val = sum(float(a.get("market_value", 0.0) or 0.0) for a in gives)
            recv_val = sum(float(a.get("market_value", 0.0) or 0.0) for a in recvs)
            max_val = max(give_val, recv_val)
            if max_val >= 4500.0:
                return "Blockbuster"
            elif max_val >= 2500.0:
                return "Starter Upgrade"
            else:
                return "Depth & Capital"

        TRADE_CATEGORY_LABELS = {"win": "Contender", "neutral": "Neutral", "rebuild": "Rebuilder"}

        def render_ros_blend_notice(ros_weight, user_category):
            """
            Transparency banner shown whenever a Dynasty+ROS blend (ros_weight > 0)
            shaped a trade's fairness evaluation - see CATEGORY_ROS_WEIGHT in
            trade_engine.py. Returns "" (no banner) when ros_weight is 0, since that
            means the evaluation is identical to the pure-dynasty baseline.
            """
            if not ros_weight or ros_weight <= 0:
                return ""
            cat_label = TRADE_CATEGORY_LABELS.get(user_category, "your team")
            dyn_pct = (1 - ros_weight) * 100.0
            ros_pct = ros_weight * 100.0
            return (
                "<div style='background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.35); "
                "border-radius: 6px; padding: 8px 12px; margin-bottom: 10px; font-size: 0.8rem; color: #7dd3fc;'>"
                f"📊 <strong>Adjusted evaluation:</strong> {ros_pct:.0f}% ROS / {dyn_pct:.0f}% Dynasty — "
                f"based on your {cat_label} situation."
                "</div>"
            )

        def render_asset_chips(assets):
            if not assets:
                return "<div style='color: #64748b; font-size: 0.8rem; font-style: italic;'>No assets selected</div>"
            chips_html = ""
            for a in assets:
                name = a.get("name", "Asset")
                val = float(a.get("market_value") or 0.0)
                pos = a.get("position") or "PICK"
                team = a.get("team") or ""
                pid = a.get("player_id")

                age_html = ""
                if a.get("type") == "pick" or not pid or str(pid).startswith("pick_"):
                    icon_html = "<div style='width: 38px; height: 38px; border-radius: 50%; background: #1e1b4b; border: 1.5px solid #818cf8; display: flex; align-items: center; justify-content: center; font-size: 1rem; flex-shrink: 0;'>🎯</div>"
                    pos_badge = "<span class='badge-pos badge-pick' style='font-size: 0.65rem; padding: 1px 5px;'>PICK</span>"
                    dyn_ros_html = "<span style='color: #c084fc; font-weight: 600;'>Future Draft Capital</span>"
                else:
                    avatar_url = get_player_avatar_url(pid, pos, team)
                    icon_html = f"<img src='{avatar_url}' style='width: 38px; height: 38px; border-radius: 50%; object-fit: cover; border: 1.5px solid #475569; flex-shrink: 0;' onerror=\"this.src='https://sleepercdn.com/images/v2/icons/player_default.webp'\" />"
                    badge_cls = f"badge-{pos.lower()}" if f"badge-{pos.lower()}" in ("badge-qb", "badge-rb", "badge-wr", "badge-te", "badge-k", "badge-def") else "badge-rb"
                    pos_badge = f"<span class='badge-pos {badge_cls}' style='font-size: 0.65rem; padding: 1px 5px;'>{pos}</span>"

                    # "age" lives directly on asset dicts sourced from team
                    # profiles (analyze_team_profile), but the Trade
                    # Calculator's manually-built selections only carry the
                    # raw Sleeper player_obj - falling back to it covers both.
                    age_raw = a.get("age")
                    if age_raw is None:
                        age_raw = (a.get("player_obj") or {}).get("age")
                    age_disp = safe_age_display(age_raw)
                    age_html = f"<span>• {age_disp}y</span>" if age_disp != "—" else ""

                    p_data = primary_lookup.get(pid, {}) or primary_lookup.get(str(pid), {})
                    r_data = redraft_lookup.get(pid, {}) or redraft_lookup.get(str(pid), {})
                    d_o = p_data.get("rank_ecr_overall", 999.0)
                    d_p = p_data.get("rank_ecr_pos", p_data.get("rank_ecr", 999.0))
                    r_o = r_data.get("rank_ecr_overall", 999.0)
                    r_p = r_data.get("rank_ecr_pos", r_data.get("rank_ecr", 999.0))

                    d_str = f"Dyn: #{int(d_o)} ({pos}{int(d_p)})" if (d_p and d_p < 900) else "Dyn: —"
                    ros_str = f"ROS: #{int(r_o)} ({pos}{int(r_p)})" if (r_p and r_p < 900) else "ROS: —"
                    dyn_ros_html = f"<span style='color: #38bdf8; font-weight: 600;'>{d_str}</span> <span style='color: #64748b;'>•</span> <span style='color: #fbbf24; font-weight: 600;'>{ros_str}</span>"

                chips_html += f"""
                <div style='display: flex; align-items: center; justify-content: space-between; gap: 10px; background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 7px 10px; margin-bottom: 6px;'>
                    <div style='display: flex; align-items: center; gap: 10px; min-width: 0;'>
                        {icon_html}
                        <div style='min-width: 0;'>
                            <div style='font-weight: 700; color: #f8fafc; font-size: 0.88rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;'>{name}</div>
                            <div style='font-size: 0.72rem; color: #94a3b8; display: flex; gap: 6px; align-items: center;'>
                                {pos_badge}
                                <span>{team}</span>
                                {age_html}
                            </div>
                            <div style='font-size: 0.68rem; margin-top: 2px;'>
                                {dyn_ros_html}
                            </div>
                        </div>
                    </div>
                    <div style='font-weight: 800; font-size: 0.9rem; color: #38bdf8; text-align: right; white-space: nowrap;'>{val:,.0f} pts</div>
                </div>
                """
            return chips_html

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

            give_chips = render_asset_chips(gives)
            recv_chips = render_asset_chips(recvs)

            injury_warnings = eval_res.get("injury_warnings") or []
            injury_warning_html = ""
            if injury_warnings:
                warning_lines = "".join(f"<div style='margin-top: 2px;'>{w}</div>" for w in injury_warnings)
                injury_warning_html = f"""
                <div style='background: rgba(244, 63, 94, 0.1); border: 1px solid rgba(244, 63, 94, 0.35); border-radius: 6px; padding: 8px 12px; margin-bottom: 10px; font-size: 0.8rem; color: #fca5a5;'>
                    {warning_lines}
                </div>
                """

            ros_blend_html = render_ros_blend_notice(
                prop.get("ros_weight", eval_res.get("ros_weight", 0.0)), prop.get("user_category")
            )

            tier = get_trade_prop_tier(prop)
            if tier == "Blockbuster":
                tier_badge = "<span class='status-capsule' style='background: rgba(168, 85, 247, 0.15); color: #d8b4fe; border: 1px solid rgba(168, 85, 247, 0.4);'>⭐ BLOCKBUSTER</span>"
            elif tier == "Starter Upgrade":
                tier_badge = "<span class='status-capsule' style='background: rgba(14, 165, 233, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.4);'>🏆 STARTER UPGRADE</span>"
            else:
                tier_badge = "<span class='status-capsule' style='background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.4);'>🌱 DEPTH & CAPITAL</span>"

            card_html = f"""
            <div class='card-container card-highlight' style='padding: 16px; margin-bottom: 16px;'>
                <div style='display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255, 255, 255, 0.08); padding-bottom: 10px; margin-bottom: 14px; flex-wrap: wrap; gap: 8px;'>
                    <div>
                        <div style='display: flex; align-items: center; gap: 8px;'>
                            <span style='font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 700; color: #38bdf8;'>Proposal #{idx}</span>
                            {tier_badge}
                        </div>
                        <h4 style='margin: 4px 0 0 0; font-size: 1.05rem; font-weight: 800; color: #f8fafc;'>{arch}</h4>
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

                {injury_warning_html}
                {ros_blend_html}

                <p style='margin: 0; font-size: 0.82rem; color: #94a3b8; line-height: 1.4;'>
                    <strong style='color: #cbd5e1;'>Strategic Rationale:</strong> {why}
                </p>
            </div>
            """
            st.html(card_html)

        trade_view = st.radio(
            "Trade Center Mode:",
            [
                "🧮 Interactive Trade Calculator",
                "🎯 Targeted Asset Finder (Buy or Sell Specific Assets)",
                "📡 League-Wide Trade Scanner",
            ],
            horizontal=True,
            key=f"trade_center_mode_{selected_league_id}",
        )

        if "Interactive Trade Calculator" in trade_view:
            st.markdown(
                "<div style='margin: 4px 0 16px 0; color: #94a3b8; font-size: 0.9rem;'>"
                "Evaluate custom trades across any league teams or arbitrary market assets. "
                "Calculates Model 3 Stud Multipliers (+15%), package dilution weights, and starting lineup impacts."
                "</div>",
                unsafe_allow_html=True
            )

            # Redraft leagues have no dynasty valuation axis at all, so the
            # toggle is only meaningful - and only shown - for dynasty
            # leagues; a redraft league goes straight to Single-Season.
            if is_dynasty:
                c_calc_s1, c_calc_s2 = st.columns([1.8, 1.2], vertical_alignment="center")
                with c_calc_s1:
                    calc_scope = st.radio(
                        "Calculator Valuation Scope:",
                        ["🏆 Dynasty Consensus Values", "⚡ Single-Season (ROS) Projections"],
                        horizontal=True,
                        key=f"trade_calc_scope_{selected_league_id}",
                    )
                is_calc_redraft = ("Single-Season" in calc_scope)
            else:
                c_calc_s2 = st.container()
                is_calc_redraft = True
            active_calc_lookup = redraft_lookup if is_calc_redraft else primary_lookup
            calc_market_assets = build_market_assets_list(active_calc_lookup, players, is_redraft=is_calc_redraft)
            calc_asset_by_label = {a["label"]: a for a in calc_market_assets}

            with c_calc_s2:
                tep_bonus_val = (
                    scoring.get("bonus_rec_te", 0.0)
                    or scoring.get("te_bonus", 0.0)
                    or selected_league.get("settings", {}).get("tep_bonus", 0.0)
                )
                if not is_calc_redraft and tep_bonus_val > 0:
                    st.info(f"✨ Tight-End Premium Active (+{tep_bonus_val:.1f} TEP Boost included)")
                else:
                    st.caption("Model 3 Active: +15% Stud Premium & Package Diminishing Returns applied automatically.")

            # Team / Context dropdowns
            team_options = [f"⭐ {team_name} (My Roster)"]
            for p in all_team_profiles:
                if p["roster_id"] != user_roster["roster_id"]:
                    team_options.append(f"👤 {p['manager_name']}")
            team_options.append("🌐 Freeform / Custom (Universal Market)")

            c_ta, c_tb = st.columns(2)
            with c_ta:
                team_a_choice = st.selectbox(
                    "Side A (Team A / Send):",
                    team_options,
                    index=0,
                    key=f"calc_team_a_select_{selected_league_id}",
                )
            with c_tb:
                team_b_choice = st.selectbox(
                    "Side B (Team B / Receive):",
                    team_options,
                    index=1 if len(team_options) > 1 else 0,
                    key=f"calc_team_b_select_{selected_league_id}",
                )

            def get_profile_from_choice(choice_str):
                if choice_str.startswith("⭐"):
                    return user_profile
                for p in all_team_profiles:
                    if p["manager_name"] in choice_str:
                        return p
                return None

            prof_a = get_profile_from_choice(team_a_choice)
            prof_b = get_profile_from_choice(team_b_choice)

            # Asset Selection Side A
            selected_assets_a = []
            with c_ta:
                if prof_a:
                    owned_labels_a = []
                    owned_map_a = {}
                    for p in prof_a["starters"] + prof_a["bench"]:
                        pid = str(p.get("player_id"))
                        p_data = active_calc_lookup.get(pid, {})
                        val = p_data.get("market_value", p.get("market_value", 0.0))
                        pos = p.get("position", "UTIL")
                        team = p.get("team", "FA")
                        lbl = f"{p['name']} ({pos} - {team}) • {val:,.0f} pts"
                        owned_labels_a.append(lbl)
                        owned_map_a[lbl] = {
                            "player_id": pid,
                            "name": p["name"],
                            "position": pos,
                            "team": team,
                            "market_value": val,
                            "type": "player",
                            "player_obj": p.get("player_obj") or p,
                            "ktc_val": p_data.get("ktc_val"),
                            "fc_val": p_data.get("fc_val"),
                            "dp_val": p_data.get("dp_val"),
                            "proj_ppg": p_data.get("proj_ppg"),
                        }
                    if not is_calc_redraft and is_dynasty:
                        for pk in prof_a.get("picks", []):
                            pk_val = pk.get("market_value", 1000.0)
                            lbl = f"{pk['name']} • {pk_val:,.0f} pts"
                            owned_labels_a.append(lbl)
                            owned_map_a[lbl] = {
                                "player_id": pk.get("pick_id") or pk.get("name"),
                                "name": pk["name"],
                                "position": "PICK",
                                "team": "DRAFT",
                                "market_value": pk_val,
                                "type": "pick",
                                "season": pk.get("season", "2027"),
                                "round": pk.get("round", 1),
                                "original_owner": pk.get("original_owner", 1),
                            }

                    chosen_roster_a = st.multiselect(
                        f"Select Assets from {prof_a['manager_name']}'s Roster:",
                        options=owned_labels_a,
                        key=f"calc_roster_a_select_{selected_league_id}",
                        placeholder="Click or search to select players or picks from this roster...",
                    )
                    for lbl in chosen_roster_a:
                        if lbl in owned_map_a:
                            selected_assets_a.append(owned_map_a[lbl])

                    chosen_extra_a = st.multiselect(
                        "Add External / Custom Asset to Side A:",
                        options=[a["label"] for a in calc_market_assets],
                        key=f"calc_extra_a_select_{selected_league_id}",
                        placeholder="Search any player or pick in database...",
                        help="Add any player from another team, free agent, or rookie pick to Side A."
                    )
                    for lbl in chosen_extra_a:
                        m_asset = calc_asset_by_label.get(lbl)
                        if m_asset:
                            selected_assets_a.append({
                                "player_id": m_asset["pid"],
                                "name": m_asset["name"],
                                "position": m_asset["pos"],
                                "team": m_asset["team"],
                                "market_value": m_asset["val"],
                                "type": "pick" if m_asset["is_pick"] else "player",
                                "ktc_val": m_asset["ktc_val"],
                                "fc_val": m_asset["fc_val"],
                                "dp_val": m_asset["dp_val"],
                                "proj_ppg": m_asset["proj_ppg"],
                                "player_obj": players.get(str(m_asset["pid"])),
                            })
                else:
                    chosen_free_a = st.multiselect(
                        "Select Players or Picks for Side A:",
                        options=[a["label"] for a in calc_market_assets],
                        key=f"calc_free_a_select_{selected_league_id}",
                        placeholder="Search any player or pick in database...",
                    )
                    for lbl in chosen_free_a:
                        m_asset = calc_asset_by_label.get(lbl)
                        if m_asset:
                            selected_assets_a.append({
                                "player_id": m_asset["pid"],
                                "name": m_asset["name"],
                                "position": m_asset["pos"],
                                "team": m_asset["team"],
                                "market_value": m_asset["val"],
                                "type": "pick" if m_asset["is_pick"] else "player",
                                "ktc_val": m_asset["ktc_val"],
                                "fc_val": m_asset["fc_val"],
                                "dp_val": m_asset["dp_val"],
                                "proj_ppg": m_asset["proj_ppg"],
                                "player_obj": players.get(str(m_asset["pid"])),
                            })

            # Asset Selection Side B
            selected_assets_b = []
            with c_tb:
                if prof_b:
                    owned_labels_b = []
                    owned_map_b = {}
                    for p in prof_b["starters"] + prof_b["bench"]:
                        pid = str(p.get("player_id"))
                        p_data = active_calc_lookup.get(pid, {})
                        val = p_data.get("market_value", p.get("market_value", 0.0))
                        pos = p.get("position", "UTIL")
                        team = p.get("team", "FA")
                        lbl = f"{p['name']} ({pos} - {team}) • {val:,.0f} pts"
                        owned_labels_b.append(lbl)
                        owned_map_b[lbl] = {
                            "player_id": pid,
                            "name": p["name"],
                            "position": pos,
                            "team": team,
                            "market_value": val,
                            "type": "player",
                            "player_obj": p.get("player_obj") or p,
                            "ktc_val": p_data.get("ktc_val"),
                            "fc_val": p_data.get("fc_val"),
                            "dp_val": p_data.get("dp_val"),
                            "proj_ppg": p_data.get("proj_ppg"),
                        }
                    if not is_calc_redraft and is_dynasty:
                        for pk in prof_b.get("picks", []):
                            pk_val = pk.get("market_value", 1000.0)
                            lbl = f"{pk['name']} • {pk_val:,.0f} pts"
                            owned_labels_b.append(lbl)
                            owned_map_b[lbl] = {
                                "player_id": pk.get("pick_id") or pk.get("name"),
                                "name": pk["name"],
                                "position": "PICK",
                                "team": "DRAFT",
                                "market_value": pk_val,
                                "type": "pick",
                                "season": pk.get("season", "2027"),
                                "round": pk.get("round", 1),
                                "original_owner": pk.get("original_owner", 1),
                            }

                    chosen_roster_b = st.multiselect(
                        f"Select Assets from {prof_b['manager_name']}'s Roster:",
                        options=owned_labels_b,
                        key=f"calc_roster_b_select_{selected_league_id}",
                        placeholder="Click or search to select players or picks from this roster...",
                    )
                    for lbl in chosen_roster_b:
                        if lbl in owned_map_b:
                            selected_assets_b.append(owned_map_b[lbl])

                    chosen_extra_b = st.multiselect(
                        "Add External / Custom Asset to Side B:",
                        options=[a["label"] for a in calc_market_assets],
                        key=f"calc_extra_b_select_{selected_league_id}",
                        placeholder="Search any player or pick in database...",
                        help="Add any player from another team, free agent, or rookie pick to Side B."
                    )
                    for lbl in chosen_extra_b:
                        m_asset = calc_asset_by_label.get(lbl)
                        if m_asset:
                            selected_assets_b.append({
                                "player_id": m_asset["pid"],
                                "name": m_asset["name"],
                                "position": m_asset["pos"],
                                "team": m_asset["team"],
                                "market_value": m_asset["val"],
                                "type": "pick" if m_asset["is_pick"] else "player",
                                "ktc_val": m_asset["ktc_val"],
                                "fc_val": m_asset["fc_val"],
                                "dp_val": m_asset["dp_val"],
                                "proj_ppg": m_asset["proj_ppg"],
                                "player_obj": players.get(str(m_asset["pid"])),
                            })
                else:
                    chosen_free_b = st.multiselect(
                        "Select Players or Picks for Side B:",
                        options=[a["label"] for a in calc_market_assets],
                        key=f"calc_free_b_select_{selected_league_id}",
                        placeholder="Search any player or pick in database...",
                    )
                    for lbl in chosen_free_b:
                        m_asset = calc_asset_by_label.get(lbl)
                        if m_asset:
                            selected_assets_b.append({
                                "player_id": m_asset["pid"],
                                "name": m_asset["name"],
                                "position": m_asset["pos"],
                                "team": m_asset["team"],
                                "market_value": m_asset["val"],
                                "type": "pick" if m_asset["is_pick"] else "player",
                                "ktc_val": m_asset["ktc_val"],
                                "fc_val": m_asset["fc_val"],
                                "dp_val": m_asset["dp_val"],
                                "proj_ppg": m_asset["proj_ppg"],
                                "player_obj": players.get(str(m_asset["pid"])),
                            })

            # Attach ROS (redraft) value to every player asset so the Dynasty+ROS
            # blend below has both sides to work with, regardless of which scope
            # (Dynasty vs Single-Season) supplied market_value for this calculator.
            for asset in selected_assets_a + selected_assets_b:
                if asset.get("type") == "player" and "redraft_val" not in asset:
                    r_data = redraft_lookup.get(str(asset.get("player_id"))) or redraft_lookup.get(asset.get("player_id")) or {}
                    asset["redraft_val"] = r_data.get("market_value", asset.get("market_value", 0.0))

            # Blend only applies when Dynasty scope is active (Single-Season is
            # already 100% ROS) and the user's own roster is one of the two sides -
            # a comparison between two other teams keeps the pure-dynasty baseline,
            # since there's no single clear "is this good for me" perspective there.
            calc_user_is_side = team_a_choice.startswith("⭐") or team_b_choice.startswith("⭐")
            calc_ros_weight = (
                CATEGORY_ROS_WEIGHT.get(user_profile.get("category", "neutral"), 0.0)
                if (is_dynasty and not is_calc_redraft and calc_user_is_side)
                else 0.0
            )

            st.markdown("---")

            # Evaluation and Display
            if not selected_assets_a and not selected_assets_b:
                st.info("👈 Select players or draft picks above for Side A and Side B to calculate trade value and evaluate fairness.")
            elif not selected_assets_a or not selected_assets_b:
                has_side = "Side A" if selected_assets_a else "Side B"
                st.warning(f"👆 You have selected assets for **{has_side}**. Please add at least one asset to the other side to compute the trade comparison.")
            else:
                eval_res = evaluate_trade_fairness(selected_assets_a, selected_assets_b, ros_weight=calc_ros_weight)
                raw_give = eval_res["raw_give"]
                raw_receive = eval_res["raw_receive"]
                eff_give = eval_res["eff_give"]
                eff_receive = eval_res["eff_receive"]
                net_diff = eval_res["net_diff"]
                fairness_ratio = eval_res["fairness_ratio"]
                stud_asset = eval_res["stud_asset"]
                stud_side = eval_res["stud_side"]

                tot_eff = eff_give + eff_receive
                pct_a = (eff_give / tot_eff * 100.0) if tot_eff > 0 else 50.0
                pct_b = (eff_receive / tot_eff * 100.0) if tot_eff > 0 else 50.0

                if abs(net_diff) <= 400 or (0.95 <= fairness_ratio <= 1.05):
                    verdict_text = "⚖️ EVEN & BALANCED"
                    verdict_color = "#10b981"
                    verdict_bg = "rgba(16, 185, 129, 0.15)"
                    verdict_border = "rgba(16, 185, 129, 0.4)"
                    verdict_desc = f"Both sides exchange comparable effective trade value (Net difference: {net_diff:+,.0f} pts, ratio: {fairness_ratio:.2f})."
                elif net_diff > 400:
                    verdict_text = "🟢 FAVORS SIDE B"
                    verdict_color = "#34d399"
                    verdict_bg = "rgba(52, 211, 153, 0.15)"
                    verdict_border = "rgba(52, 211, 153, 0.4)"
                    verdict_desc = f"Side B gains a +{net_diff:,.0f} pt effective advantage (+{(pct_b - pct_a):.1f}% surplus)."
                else:
                    verdict_text = "🔵 FAVORS SIDE A"
                    verdict_color = "#38bdf8"
                    verdict_bg = "rgba(56, 189, 248, 0.15)"
                    verdict_border = "rgba(56, 189, 248, 0.4)"
                    verdict_desc = f"Side A gains a +{abs(net_diff):,.0f} pt effective advantage (+{(pct_a - pct_b):.1f}% surplus)."

                # Balance meter HTML
                stud_html = ""
                if stud_asset:
                    s_side_label = "Side A" if stud_side == "give" else "Side B"
                    stud_html = f"""
                    <div style='margin-top: 10px; padding: 8px 12px; background: rgba(30, 27, 75, 0.5); border: 1px solid rgba(129, 140, 248, 0.3); border-radius: 6px; font-size: 0.8rem; color: #cbd5e1; display: flex; align-items: center; gap: 8px;'>
                        <span style='font-size: 1rem;'>⭐</span>
                        <span><strong>The Stud:</strong> <span style='color: #f8fafc; font-weight: 700;'>{stud_asset['name']}</span> ({stud_asset.get('market_value', 0):,.0f} pts) earns a <strong>+15% Stud Multiplier</strong> on <strong>{s_side_label}</strong>.</span>
                    </div>
                    """

                meter_html = f"""
                <div style='background: rgba(15, 23, 42, 0.85); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 10px; padding: 16px; margin-bottom: 20px;'>
                    <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; flex-wrap: wrap; gap: 8px;'>
                        <div style='font-weight: 800; color: #38bdf8; font-size: 1.05rem;'>
                            Side A: {pct_a:.1f}% <span style='font-size: 0.82rem; font-weight: 500; color: #94a3b8;'>({eff_give:,.0f} effective pts)</span>
                        </div>
                        <div style='font-weight: 800; color: {verdict_color}; background: {verdict_bg}; border: 1px solid {verdict_border}; border-radius: 20px; padding: 4px 14px; font-size: 0.88rem; letter-spacing: 0.02em;'>
                            {verdict_text}
                        </div>
                        <div style='font-weight: 800; color: #34d399; font-size: 1.05rem;'>
                            Side B: {pct_b:.1f}% <span style='font-size: 0.82rem; font-weight: 500; color: #94a3b8;'>({eff_receive:,.0f} effective pts)</span>
                        </div>
                    </div>
                    <div style='width: 100%; height: 14px; background: #334155; border-radius: 7px; overflow: hidden; display: flex;'>
                        <div style='width: {pct_a}%; height: 100%; background: #38bdf8; transition: width 0.3s ease;'></div>
                        <div style='width: {pct_b}%; height: 100%; background: #34d399; transition: width 0.3s ease;'></div>
                    </div>
                    <div style='display: flex; justify-content: space-between; font-size: 0.76rem; color: #94a3b8; margin-top: 8px; flex-wrap: wrap; gap: 6px;'>
                        <span>Raw Total: <strong style='color: #f8fafc;'>{raw_give:,.0f} pts</strong></span>
                        <span style='color: #cbd5e1;'>{verdict_desc}</span>
                        <span>Raw Total: <strong style='color: #f8fafc;'>{raw_receive:,.0f} pts</strong></span>
                    </div>
                    {stud_html}
                </div>
                """
                st.html(meter_html)

                ros_blend_notice = render_ros_blend_notice(calc_ros_weight, user_profile.get("category"))
                if ros_blend_notice:
                    st.html(ros_blend_notice)

                injury_warnings = eval_res.get("injury_warnings") or []
                if injury_warnings:
                    warning_lines = "".join(f"<div style='margin-top: 2px;'>{w}</div>" for w in injury_warnings)
                    st.html(
                        f"<div style='background: rgba(244, 63, 94, 0.1); border: 1px solid rgba(244, 63, 94, 0.35); "
                        f"border-radius: 6px; padding: 8px 12px; margin-bottom: 16px; font-size: 0.82rem; color: #fca5a5;'>"
                        f"{warning_lines}</div>"
                    )

                # Two-column detailed cards
                c_card_a, c_card_b = st.columns(2)
                with c_card_a:
                    st.markdown(f"#### Side A Package ({len(selected_assets_a)} assets)")
                    chips_a_html = render_asset_chips(selected_assets_a)
                    st.html(f"<div style='background: rgba(17, 24, 39, 0.6); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 8px; padding: 12px; margin-bottom: 12px;'>{chips_a_html}</div>")

                with c_card_b:
                    st.markdown(f"#### Side B Package ({len(selected_assets_b)} assets)")
                    chips_b_html = render_asset_chips(selected_assets_b)
                    st.html(f"<div style='background: rgba(17, 24, 39, 0.6); border: 1px solid rgba(52, 211, 153, 0.3); border-radius: 8px; padding: 12px; margin-bottom: 12px;'>{chips_b_html}</div>")

                # Multi-Model Platform Breakdown
                st.markdown("#### Constituent Platform Trade Verdicts")
                st.caption("How each underlying source model scores this trade proposal side-by-side:")

                fc_a = sum(float(a.get("fc_val") or 0.0) for a in selected_assets_a if a.get("fc_val"))
                fc_b = sum(float(b.get("fc_val") or 0.0) for b in selected_assets_b if b.get("fc_val"))

                if not is_calc_redraft:
                    ktc_a = sum(float(a.get("ktc_val") or 0.0) for a in selected_assets_a if a.get("ktc_val"))
                    ktc_b = sum(float(b.get("ktc_val") or 0.0) for b in selected_assets_b if b.get("ktc_val"))
                    dp_a = sum(float(a.get("dp_val") or 0.0) for a in selected_assets_a if a.get("dp_val"))
                    dp_b = sum(float(b.get("dp_val") or 0.0) for b in selected_assets_b if b.get("dp_val"))

                    def model_verdict_str(va, vb):
                        if abs(vb - va) <= 300:
                            return "⚖️ Even"
                        elif vb > va:
                            return f"🟢 Favors Side B (+{vb - va:,.0f})"
                        else:
                            return f"🔵 Favors Side A (+{va - vb:,.0f})"

                    platform_data = [
                        {"Platform Model": "KeepTradeCut (Crowdsourced)", "Side A Total": f"{ktc_a:,.0f} pts", "Side B Total": f"{ktc_b:,.0f} pts", "Model Verdict": model_verdict_str(ktc_a, ktc_b)},
                        {"Platform Model": "FantasyCalc (Real Trades)", "Side A Total": f"{fc_a:,.0f} pts", "Side B Total": f"{fc_b:,.0f} pts", "Model Verdict": model_verdict_str(fc_a, fc_b)},
                        {"Platform Model": "DynastyProcess (Expert Model)", "Side A Total": f"{dp_a:,.0f} pts", "Side B Total": f"{dp_b:,.0f} pts", "Model Verdict": model_verdict_str(dp_a, dp_b)},
                    ]
                else:
                    ppg_a = sum(float(a.get("proj_ppg") or 0.0) for a in selected_assets_a if a.get("proj_ppg"))
                    ppg_b = sum(float(b.get("proj_ppg") or 0.0) for b in selected_assets_b if b.get("proj_ppg"))
                    ktc_redraft_a = sum(float(a.get("ktc_redraft_val") or 0.0) for a in selected_assets_a if a.get("ktc_redraft_val"))
                    ktc_redraft_b = sum(float(b.get("ktc_redraft_val") or 0.0) for b in selected_assets_b if b.get("ktc_redraft_val"))
                    def model_verdict_redraft(va, vb, unit="pts"):
                        if abs(vb - va) <= (0.5 if unit == "PPG" else 250):
                            return "⚖️ Even"
                        elif vb > va:
                            return f"🟢 Favors Side B (+{vb - va:.1f} {unit})"
                        else:
                            return f"🔵 Favors Side A (+{va - vb:.1f} {unit})"

                    platform_data = [
                        {"Platform Model": "Sleeper Projections", "Side A Total": f"{ppg_a:.1f} PPG", "Side B Total": f"{ppg_b:.1f} PPG", "Model Verdict": model_verdict_redraft(ppg_a, ppg_b, "PPG")},
                        {"Platform Model": "KTC Redraft Value", "Side A Total": f"{ktc_redraft_a:,.0f} pts", "Side B Total": f"{ktc_redraft_b:,.0f} pts", "Model Verdict": model_verdict_redraft(ktc_redraft_a, ktc_redraft_b, "pts")},
                    ]

                st.dataframe(pd.DataFrame(platform_data), hide_index=True, use_container_width=True)

                # Lineup Impact for League Rosters
                if (prof_a or prof_b) and roster_pos:
                    st.markdown("#### Starting Lineup Impact Analysis")
                    c_imp_a, c_imp_b = st.columns(2)
                    with c_imp_a:
                        if prof_a:
                            cur_p_objs = [a.get("player_obj") for a in prof_a["starters"] + prof_a["bench"] if a.get("player_obj")]
                            give_pids = {ga["player_id"] for ga in selected_assets_a if ga.get("type") == "player"}
                            recv_p_objs = [rb.get("player_obj") for rb in selected_assets_b if rb.get("type") == "player" and rb.get("player_obj")]
                            new_p_objs = [p for p in cur_p_objs if str(p.get("player_id")) not in give_pids] + recv_p_objs

                            old_st, _ = simulate_optimal_lineup(cur_p_objs, active_calc_lookup, roster_pos, is_dynasty=not is_calc_redraft)
                            new_st, _ = simulate_optimal_lineup(new_p_objs, active_calc_lookup, roster_pos, is_dynasty=not is_calc_redraft)

                            old_st_val = sum(r.get("market_value", 0.0) for _, r, _slot in old_st)
                            new_st_val = sum(r.get("market_value", 0.0) for _, r, _slot in new_st)
                            st_delta = new_st_val - old_st_val
                            st.metric(
                                f"{prof_a['manager_name']} Lineup Impact",
                                f"{new_st_val:,.0f} pts",
                                f"{st_delta:+,.0f} pts (was {old_st_val:,.0f} pts)"
                            )
                        else:
                            st.caption("Side A is Freeform / External; lineup simulation skipped.")

                    with c_imp_b:
                        if prof_b:
                            cur_p_objs_b = [b.get("player_obj") for b in prof_b["starters"] + prof_b["bench"] if b.get("player_obj")]
                            give_pids_b = {gb["player_id"] for gb in selected_assets_b if gb.get("type") == "player"}
                            recv_p_objs_a = [ra.get("player_obj") for ra in selected_assets_a if ra.get("type") == "player" and ra.get("player_obj")]
                            new_p_objs_b = [p for p in cur_p_objs_b if str(p.get("player_id")) not in give_pids_b] + recv_p_objs_a

                            old_st_b, _ = simulate_optimal_lineup(cur_p_objs_b, active_calc_lookup, roster_pos, is_dynasty=not is_calc_redraft)
                            new_st_b, _ = simulate_optimal_lineup(new_p_objs_b, active_calc_lookup, roster_pos, is_dynasty=not is_calc_redraft)

                            old_st_val_b = sum(r.get("market_value", 0.0) for _, r, _slot in old_st_b)
                            new_st_val_b = sum(r.get("market_value", 0.0) for _, r, _slot in new_st_b)
                            st_delta_b = new_st_val_b - old_st_val_b
                            st.metric(
                                f"{prof_b['manager_name']} Lineup Impact",
                                f"{new_st_val_b:,.0f} pts",
                                f"{st_delta_b:+,.0f} pts (was {old_st_val_b:,.0f} pts)"
                            )
                        else:
                            st.caption("Side B is Freeform / External; lineup simulation skipped.")

        elif "Targeted Asset Finder" in trade_view:
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
                for p in gen_trades:
                    p["tier"] = get_trade_prop_tier(p)

                c_tr1, c_tr2 = st.columns([1.5, 1])
                with c_tr1:
                    tier_filter = st.radio(
                        "Filter by Proposal Tier:",
                        ["All Tiers", "⭐ Blockbuster Trades", "🏆 Starter Upgrades", "🌱 Depth & Capital"],
                        horizontal=True,
                        key="trade_tier_filter",
                    )
                with c_tr2:
                    st.caption(f"Showing proposals curated across asset value tiers.")

                filtered_trades = gen_trades
                if "Blockbuster" in tier_filter:
                    filtered_trades = [p for p in gen_trades if get_trade_prop_tier(p) == "Blockbuster"]
                elif "Starter" in tier_filter:
                    filtered_trades = [p for p in gen_trades if get_trade_prop_tier(p) == "Starter Upgrade"]
                elif "Depth" in tier_filter:
                    filtered_trades = [p for p in gen_trades if get_trade_prop_tier(p) == "Depth & Capital"]

                if filtered_trades:
                    st.success(f"Displaying {len(filtered_trades)} trade opportunities ({tier_filter}):")
                    for idx, prop in enumerate(filtered_trades, 1):
                        render_trade_proposal_card(idx, prop, show_chat_message=False)
                else:
                    st.info(f"No trade proposals currently generated in {tier_filter} tier.")
            else:
                st.info("No general trades currently generated under default thresholds.")


    # =========================================================================
    # TAB 6: MARKET RANKINGS & DATABASE
    # =========================================================================
    with tab_market:
        st.subheader("Market Rankings & Player Database")

        # Redraft leagues have no dynasty valuation axis at all (see
        # build_league_context: primary_lookup falls back to redraft_lookup
        # there), so the toggle itself is only meaningful - and only shown -
        # for dynasty leagues. A redraft league goes straight to Single-
        # Season with no extra step.
        if is_dynasty:
            ranking_scope = st.radio(
                "Valuation Scope:",
                ["🏆 Dynasty Market Values", "📅 Single-Season (Redraft / ROS)"],
                horizontal=True,
                key="mkt_ranking_scope",
            )
            is_redraft = ("Single-Season" in ranking_scope)
        else:
            is_redraft = True
        if is_redraft:
            st.caption("Explore comprehensive single-season valuations and rankings comparing Sleeper Multi-Week Projections, FantasyPros ECR, and KTC Redraft Value.")
        else:
            st.caption("Explore comprehensive dynasty valuations and rankings comparing KeepTradeCut, FantasyCalc, DynastyProcess, and Positional ECR.")

        active_lookup = redraft_lookup if is_redraft else primary_lookup

        # Build unified market assets collection
        all_market_assets = build_market_assets_list(active_lookup, players, is_redraft=is_redraft)

        # Team/Trajectory: who owns this player in THIS league, and (dynasty
        # leagues only) that team's Franchise Trajectory - gated on the
        # league's own format (is_dynasty), not which valuation scope this
        # table happens to be browsing (is_redraft), since ownership and
        # trajectory are roster facts, not a pricing lens. A redraft league
        # has no Franchise Trajectory axis (see build_team_profiles /
        # classify_redraft_team - a different, single-axis "Contender
        # Status" concept), so that column/filter is left out there rather
        # than showing a misleading substitute.
        show_trajectory = is_dynasty
        owner_lookup = build_player_owner_lookup(all_team_profiles, users)
        for r in all_market_assets:
            owner = owner_lookup.get(r["pid"])
            if owner:
                r["Owner"] = owner["username"]
                r["Trajectory"] = owner["trajectory"]
                r["_owner_category"] = owner["category"]
            else:
                r["Owner"] = "Free Agent"
                r["Trajectory"] = "—"
                r["_owner_category"] = None

        market_tab_labels = ["📊 Market Player Database", "⚖️ Player Head-to-Head Comparison"]
        if is_dynasty:
            market_tab_labels.append("🔀 Buy Low / Sell High")
            tab_db, tab_h2h, tab_signal = st.tabs(market_tab_labels)
        else:
            tab_db, tab_h2h = st.tabs(market_tab_labels)

        with tab_db:
            trajectory_mkt = "ALL"

            # Filter columns are built dynamically (not hardcoded per
            # is_redraft/show_trajectory combination) since an optional
            # filter (Trajectory) on top of the base set (Position, Search,
            # Owner) would otherwise mean hand-coding every combination -
            # this scales to any subset being present.
            filter_key_scope = "redraft" if is_redraft else "dynasty"
            filter_specs = [("pos", 1), ("search", 1.3 if (show_trajectory or not is_redraft) else 2)]
            if show_trajectory:
                filter_specs.append(("trajectory", 1))
            filter_specs.append(("owner", 1))

            filter_cols = st.columns([w for _, w in filter_specs])
            col_by_key = {key: col for (key, _), col in zip(filter_specs, filter_cols)}

            with col_by_key["pos"]:
                pos_options = ["ALL", "QB", "RB", "WR", "TE", "K", "DEF"] if is_redraft else ["ALL", "QB", "RB", "WR", "TE", "PICK", "K", "DEF"]
                pos_mkt = st.selectbox("Position Filter:", pos_options, key=f"mkt_pos_filter_{filter_key_scope}")
            with col_by_key["search"]:
                search_label = "Search Player / Team:" if is_redraft else "Search Player / Team / Pick:"
                search_mkt = st.text_input(search_label, "", key=f"mkt_search_filter_{filter_key_scope}")
            if "trajectory" in col_by_key:
                trajectory_options = ["ALL"] + sorted({
                    r["Trajectory"] for r in all_market_assets
                    if r.get("Trajectory") and r["Trajectory"] != "—"
                })
                with col_by_key["trajectory"]:
                    trajectory_mkt = st.selectbox(
                        "Trajectory:",
                        trajectory_options,
                        key=f"mkt_trajectory_filter_{filter_key_scope}",
                        help="Filters by the owning team's Franchise Trajectory - free agents are excluded by any non-ALL selection.",
                    )
            owner_options = ["ALL"] + sorted({r["Owner"] for r in all_market_assets if r.get("Owner")})
            with col_by_key["owner"]:
                owner_mkt = st.selectbox(
                    "Owner:",
                    owner_options,
                    key=f"mkt_owner_filter_{filter_key_scope}",
                    help="Filters by which team in this league owns the player - includes Free Agent as its own option.",
                )

            filtered_rows = []
            for r in all_market_assets:
                if pos_mkt != "ALL" and r["pos"] != pos_mkt:
                    continue
                if search_mkt and (search_mkt.lower() not in r["name"].lower() and search_mkt.lower() not in r["team"].lower()):
                    continue
                if trajectory_mkt != "ALL" and r.get("Trajectory") != trajectory_mkt:
                    continue
                if owner_mkt != "ALL" and r.get("Owner") != owner_mkt:
                    continue
                filtered_rows.append(r)

            if filtered_rows:
                c_mksort1, c_mksort2, c_mksort3 = st.columns([2, 1.2, 1.2], vertical_alignment="bottom")
                with c_mksort1:
                    sort_options = (
                        ["Consensus Value", "Overall Rank", "Pos Rank", "Sleeper Projections PPG", "FantasyPros ECR", "KTC Redraft Value", "Player Name"]
                        if is_redraft
                        else ["Consensus Value", "Overall Rank", "Pos Rank", "KeepTradeCut", "FantasyCalc", "DynastyProcess", "Player Name"]
                    )
                    sort_mkt_col = st.selectbox(
                        "Sort Market Players By:",
                        sort_options,
                        key=f"mkt_sort_col_{'redraft' if is_redraft else 'dynasty'}"
                    )
                with c_mksort2:
                    sort_mkt_order = st.selectbox(
                        "Order:",
                        ["Descending (High / Best)", "Ascending (Low)"],
                        key=f"mkt_sort_order_{'redraft' if is_redraft else 'dynasty'}"
                    )
                with c_mksort3:
                    page_size_choice = st.selectbox(
                        "Items Per Page:",
                        [50, 100, 200, "All"],
                        index=1,
                        key=f"mkt_page_size_{'redraft' if is_redraft else 'dynasty'}"
                    )

                sorted_mkt = list(filtered_rows)
                is_desc = "Descending" in sort_mkt_order
                if sort_mkt_col == "Consensus Value":
                    sorted_mkt.sort(key=lambda x: x["_val"], reverse=is_desc)
                elif sort_mkt_col in ("Overall Rank", "Overall ECR"):
                    sorted_mkt.sort(key=lambda x: x["_overall_ecr"], reverse=not is_desc)
                elif sort_mkt_col in ("Pos Rank", "Pos ECR"):
                    sorted_mkt.sort(key=lambda x: x["_pos_ecr"], reverse=not is_desc)
                elif sort_mkt_col == "KeepTradeCut":
                    sorted_mkt.sort(key=lambda x: x["_ktc"], reverse=is_desc)
                elif sort_mkt_col == "FantasyCalc":
                    sorted_mkt.sort(key=lambda x: x["_fc"], reverse=is_desc)
                elif sort_mkt_col == "FantasyPros ECR":
                    sorted_mkt.sort(key=lambda x: x["_fp_ecr"], reverse=not is_desc)
                elif sort_mkt_col == "Sleeper Projections PPG":
                    sorted_mkt.sort(key=lambda x: x["_proj_ppg"], reverse=is_desc)
                elif sort_mkt_col == "KTC Redraft Value":
                    sorted_mkt.sort(key=lambda x: x["_ktc_redraft_val"], reverse=is_desc)
                elif sort_mkt_col == "DynastyProcess":
                    sorted_mkt.sort(key=lambda x: x["_dp"], reverse=is_desc)
                elif sort_mkt_col == "Player Name":
                    sorted_mkt.sort(key=lambda x: x["_name"], reverse=not is_desc)

                for idx, r in enumerate(sorted_mkt, start=1):
                    r["Rank"] = f"#{idx}"

                total_items = len(sorted_mkt)
                page_size = total_items if page_size_choice == "All" else int(page_size_choice)
                total_pages = max(1, math.ceil(total_items / page_size))

                # Validate current page state
                cur_page = st.session_state.get("mkt_page", 1)
                if cur_page > total_pages:
                    cur_page = 1
                    st.session_state["mkt_page"] = 1

                start_idx = (cur_page - 1) * page_size
                end_idx = min(start_idx + page_size, total_items)
                page_rows = sorted_mkt[start_idx:end_idx]

                # Pagination Controls Bar
                c_p1, c_p2, c_p3 = st.columns([1, 2, 1], vertical_alignment="center")
                with c_p1:
                    if st.button("← Previous", key=f"mkt_prev_btn_{'redraft' if is_redraft else 'dynasty'}", disabled=(cur_page <= 1), use_container_width=True):
                        st.session_state["mkt_page"] = max(1, cur_page - 1)
                        st.rerun()
                with c_p2:
                    st.markdown(
                        f"<div style='text-align: center; color: #94a3b8; font-size: 0.85rem; font-weight: 600;'>"
                        f"Page <strong style='color: #f8fafc;'>{cur_page}</strong> of <strong style='color: #f8fafc;'>{total_pages}</strong> "
                        f"<span style='color: #64748b;'>• Showing {start_idx + 1}–{end_idx} of {total_items} assets</span>"
                        f"</div>",
                        unsafe_allow_html=True
                    )
                with c_p3:
                    if st.button("Next →", key=f"mkt_next_btn_{'redraft' if is_redraft else 'dynasty'}", disabled=(cur_page >= total_pages), use_container_width=True):
                        st.session_state["mkt_page"] = min(total_pages, cur_page + 1)
                        st.rerun()

                st.html(render_market_table_html(page_rows, is_redraft=is_redraft, show_trajectory=show_trajectory))
            else:
                st.info("No players matched the filter criteria.")

        with tab_h2h:
            # =================================================================
            # SUBVIEW: PLAYER HEAD-TO-HEAD COMPARISON (2-3 PLAYERS)
            # =================================================================
            st.markdown(
                "<div style='margin: 8px 0 16px 0; color: #94a3b8; font-size: 0.88rem;'>"
                "Compare 2 or 3 players or rookie draft picks side-by-side across consensus market values, "
                "constituent platform models, and expert rankings."
                "</div>",
                unsafe_allow_html=True
            )

            # Preserve selected player IDs across Dynasty <-> Redraft scopes
            if "h2h_selected_pids" not in st.session_state:
                st.session_state["h2h_selected_pids"] = []

            scope_key = "redraft" if is_redraft else "dynasty"
            if st.session_state.get("h2h_last_scope") != scope_key:
                st.session_state["h2h_last_scope"] = scope_key
                # Evict multiselect state key so default is cleanly re-evaluated on scope switch
                if "h2h_players_multiselect" in st.session_state:
                    del st.session_state["h2h_players_multiselect"]

            pid_to_label = {a["pid"]: a["label"] for a in all_market_assets}
            label_to_pid = {a["label"]: a["pid"] for a in all_market_assets}

            # Map existing selected PIDs to the active scope's labels
            active_default_labels = [pid_to_label[p] for p in st.session_state["h2h_selected_pids"] if p in pid_to_label][:3]

            selected_cmp_labels = st.multiselect(
                "Select 2 or 3 Players or Picks to Compare:",
                options=[a["label"] for a in all_market_assets],
                default=active_default_labels,
                max_selections=3,
                key="h2h_players_multiselect",
                placeholder="Search and select 2 or 3 players or rookie draft picks...",
                help="Search by player name or draft pick. Select 2 or 3 assets to compare side-by-side."
            )

            # Update session state with currently selected PIDs
            st.session_state["h2h_selected_pids"] = [label_to_pid[l] for l in selected_cmp_labels if l in label_to_pid]

            if len(selected_cmp_labels) == 0:
                st.info("🔍 Search and select 2 or 3 players or rookie draft picks above to display the head-to-head comparison.")
            elif len(selected_cmp_labels) == 1:
                st.info("👆 Please select at least 1 more player or draft pick above to compare side-by-side.")
            else:
                selected_assets = [next(a for a in all_market_assets if a["label"] == lbl) for lbl in selected_cmp_labels]
                selected_assets.sort(key=lambda a: a.get("val", 0.0), reverse=True)

                p1 = selected_assets[0]
                p2 = selected_assets[1]
                p3 = selected_assets[2] if len(selected_assets) > 2 else None

                v_diff = p1["val"] - p2["val"]
                v_pct = (v_diff / p2["val"] * 100) if p2["val"] > 0 else 0.0

                # Age delta string
                age_delta_str = ""
                try:
                    a1 = float(p1["age"])
                    a2 = float(p2["age"])
                    if a1 < a2:
                        age_delta_str = f"• <b>{p1['name']}</b> is {a2 - a1:.1f} yrs younger"
                    elif a2 < a1:
                        age_delta_str = f"• <b>{p2['name']}</b> is {a1 - a2:.1f} yrs younger"
                except (ValueError, TypeError):
                    pass

                # Source sentiment bullets
                sentiment_bullets = []
                if not is_redraft:
                    if p1.get("ktc_val") and p2.get("ktc_val"):
                        k_diff = float(p1["ktc_val"]) - float(p2["ktc_val"])
                        if k_diff > 0:
                            sentiment_bullets.append(f"<span style='color: #38bdf8;'>KeepTradeCut</span> crowdsourced sentiment favors <b>{p1['name']}</b> (+{k_diff:,.0f} pts).")
                        elif k_diff < 0:
                            sentiment_bullets.append(f"<span style='color: #38bdf8;'>KeepTradeCut</span> crowdsourced sentiment favors <b>{p2['name']}</b> (+{abs(k_diff):,.0f} pts).")

                    if p1.get("fc_val") and p2.get("fc_val"):
                        f_diff = float(p1["fc_val"]) - float(p2["fc_val"])
                        if f_diff > 0:
                            sentiment_bullets.append(f"<span style='color: #34d399;'>FantasyCalc</span> real trade data favors <b>{p1['name']}</b> (+{f_diff:,.0f} pts).")
                        elif f_diff < 0:
                            sentiment_bullets.append(f"<span style='color: #34d399;'>FantasyCalc</span> real trade data favors <b>{p2['name']}</b> (+{abs(f_diff):,.0f} pts).")

                    if p1.get("dp_val") and p2.get("dp_val"):
                        d_diff = float(p1["dp_val"]) - float(p2["dp_val"])
                        if d_diff > 0:
                            sentiment_bullets.append(f"<span style='color: #c084fc;'>DynastyProcess</span> expert consensus favors <b>{p1['name']}</b> (+{d_diff:,.0f} pts).")
                        elif d_diff < 0:
                            sentiment_bullets.append(f"<span style='color: #c084fc;'>DynastyProcess</span> expert consensus favors <b>{p2['name']}</b> (+{abs(d_diff):,.0f} pts).")
                else:
                    if p1.get("proj_ppg") and p2.get("proj_ppg"):
                        p_diff = float(p1["proj_ppg"]) - float(p2["proj_ppg"])
                        if p_diff > 0:
                            sentiment_bullets.append(f"<span style='color: #38bdf8;'>Sleeper Projections</span> model projects <b>{p1['name']}</b> ({p1['proj_ppg']:.1f} PPG) to outscore <b>{p2['name']}</b> ({p2['proj_ppg']:.1f} PPG, +{p_diff:.1f} PPG).")
                        elif p_diff < 0:
                            sentiment_bullets.append(f"<span style='color: #38bdf8;'>Sleeper Projections</span> model projects <b>{p2['name']}</b> ({p2['proj_ppg']:.1f} PPG) to outscore <b>{p1['name']}</b> ({p1['proj_ppg']:.1f} PPG, +{abs(p_diff):.1f} PPG).")

                    if p1.get("fp_ecr_overall") and p2.get("fp_ecr_overall"):
                        try:
                            fp1 = float(p1["fp_ecr_overall"])
                            fp2 = float(p2["fp_ecr_overall"])
                            if fp1 < 500 and fp2 < 500:
                                if fp1 < fp2:
                                    sentiment_bullets.append(f"<span style='color: #fbbf24;'>FantasyPros ECR</span> consensus favors <b>{p1['name']}</b> (#{int(fp1)} vs #{int(fp2)}).")
                                elif fp2 < fp1:
                                    sentiment_bullets.append(f"<span style='color: #fbbf24;'>FantasyPros ECR</span> consensus favors <b>{p2['name']}</b> (#{int(fp2)} vs #{int(fp1)}).")
                        except (ValueError, TypeError):
                            pass

                    if p1.get("ktc_redraft_val") and p2.get("ktc_redraft_val"):
                        e_diff = float(p1["ktc_redraft_val"]) - float(p2["ktc_redraft_val"])
                        if e_diff > 0:
                            sentiment_bullets.append(f"<span style='color: #f87171;'>KTC Redraft Value</span> favors <b>{p1['name']}</b> ({p1['ktc_redraft_val']:,.0f} pts vs {p2['ktc_redraft_val']:,.0f} pts, +{e_diff:,.0f} pts).")
                        elif e_diff < 0:
                            sentiment_bullets.append(f"<span style='color: #f87171;'>KTC Redraft Value</span> favors <b>{p2['name']}</b> ({p2['ktc_redraft_val']:,.0f} pts vs {p1['ktc_redraft_val']:,.0f} pts, +{abs(e_diff):,.0f} pts).")

                # Executive Advantage Banner
                lead_title = "Single-Season Value Leader" if is_redraft else "Consensus Value Leader"
                verdict_html = f"""
                <div style='background: rgba(15, 23, 42, 0.85); border: 1px solid rgba(56, 189, 248, 0.25); border-radius: 10px; padding: 16px 20px; margin: 16px 0 20px 0;'>
                    <div style='display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; margin-bottom: 8px;'>
                        <span style='font-size: 0.76rem; font-weight: 800; color: #38bdf8; text-transform: uppercase; letter-spacing: 0.05em;'>{lead_title}</span>
                        <span style='background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.3); color: #34d399; font-size: 0.8rem; font-weight: 800; border-radius: 9999px; padding: 3px 10px;'>
                            +{v_diff:,.0f} PTS (+{v_pct:.1f}%) ADVANTAGE
                        </span>
                    </div>
                    <div style='font-size: 1.35rem; font-weight: 800; color: #ffffff;'>
                        {p1['name']} <span style='font-size: 0.92rem; font-weight: 600; color: #94a3b8;'>leads {p2['name']} {age_delta_str}</span>
                    </div>
                    {'<div style=\"margin-top: 10px; font-size: 0.84rem; color: #cbd5e1; line-height: 1.5; border-top: 1px solid rgba(255,255,255,0.06); padding-top: 8px;\">' + '<br/>'.join('• ' + s for s in sentiment_bullets) + '</div>' if sentiment_bullets else ''}
                </div>
                """
                st.html(verdict_html)

                # Side-by-Side Cards in Columns
                cmp_cols = st.columns(len(selected_assets))
                total_val_sum = sum(a.get("val", 0.0) for a in selected_assets) or 1.0

                rank_badges = [
                    ("#1 IN COMPARISON", "rgba(16, 185, 129, 0.15)", "#34d399", "rgba(16, 185, 129, 0.3)"),
                    ("#2 IN COMPARISON", "rgba(56, 189, 248, 0.15)", "#38bdf8", "rgba(56, 189, 248, 0.3)"),
                    ("#3 IN COMPARISON", "rgba(168, 85, 247, 0.15)", "#c084fc", "rgba(168, 85, 247, 0.3)"),
                ]

                for col, asset, b_info in zip(cmp_cols, selected_assets, rank_badges):
                    with col:
                        b_text, b_bg, b_color, border_c = b_info
                        a_share = (asset["val"] / total_val_sum * 100)
                        pos_cls = f"badge-{asset['pos'].lower()}" if f"badge-{asset['pos'].lower()}" in ("badge-qb", "badge-rb", "badge-wr", "badge-te", "badge-k", "badge-def") else "badge-rb"

                        if asset["is_pick"]:
                            avatar_html = "<span class='pick-badge' style='width: 46px; height: 46px; font-size: 0.8rem; display: flex; align-items: center; justify-content: center;'>PICK</span>"
                        else:
                            avatar_html = f"<img src='{asset['avatar']}' class='player-avatar-44' style='width: 46px; height: 46px;' onerror=\"this.src='https://sleepercdn.com/images/v2/icons/player_default.webp'\" />"

                        ktc_s = f"{float(asset['ktc_val']):,.0f} pts" if asset.get("ktc_val") is not None else "—"
                        fc_s = f"{float(asset['fc_val']):,.0f} pts" if asset.get("fc_val") is not None else "—"
                        dp_s = f"{float(asset['dp_val']):,.0f} pts" if asset.get("dp_val") is not None else "—"

                        val_card_title = "Single-Season Market Value" if is_redraft else "Consensus Market Value"

                        if is_redraft:
                            fp_o_val = asset.get("fp_ecr_overall")
                            fp_disp = f"#{int(fp_o_val)}" if (fp_o_val and float(fp_o_val) < 500) else "—"
                            pj_val = asset.get("proj_ppg")
                            pj_disp = f"{pj_val:.1f} PPG" if pj_val is not None else "—"
                            ktc_redraft_val_disp = asset.get("ktc_redraft_val")
                            ktc_redraft_disp = f"{ktc_redraft_val_disp:,.0f} pts" if ktc_redraft_val_disp is not None else "—"

                            constituent_grid = f"""
                            <div style='font-size: 0.7rem; font-weight: 700; color: #64748b; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 6px;'>Constituent Models (ROS)</div>
                            <div style='display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 6px;'>
                                <div style='background: rgba(56, 189, 248, 0.04); border: 1px solid rgba(56, 189, 248, 0.15); border-radius: 6px; padding: 6px 8px;'>
                                    <div style='font-size: 0.64rem; color: #38bdf8; font-weight: 700;'>Sleeper</div>
                                    <div style='font-size: 0.85rem; font-weight: 800; color: #ffffff;'>{pj_disp}</div>
                                </div>
                                <div style='background: rgba(245, 158, 11, 0.04); border: 1px solid rgba(245, 158, 11, 0.15); border-radius: 6px; padding: 6px 8px;'>
                                    <div style='font-size: 0.64rem; color: #fbbf24; font-weight: 700;'>FantasyPros</div>
                                    <div style='font-size: 0.85rem; font-weight: 800; color: #ffffff;'>{fp_disp}</div>
                                </div>
                                <div style='background: rgba(239, 68, 68, 0.04); border: 1px solid rgba(239, 68, 68, 0.15); border-radius: 6px; padding: 6px 8px;'>
                                    <div style='font-size: 0.64rem; color: #f87171; font-weight: 700;'>KTC Redraft</div>
                                    <div style='font-size: 0.85rem; font-weight: 800; color: #ffffff;'>{ktc_redraft_disp}</div>
                                </div>
                            </div>
                            """
                        else:
                            constituent_grid = f"""
                            <div style='font-size: 0.7rem; font-weight: 700; color: #64748b; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 6px;'>Constituent Models</div>
                            <div style='display: grid; grid-template-columns: 1fr 1fr; gap: 6px;'>
                                <div style='background: rgba(56, 189, 248, 0.04); border: 1px solid rgba(56, 189, 248, 0.15); border-radius: 6px; padding: 6px 8px;'>
                                    <div style='font-size: 0.66rem; color: #38bdf8; font-weight: 700;'>KeepTradeCut</div>
                                    <div style='font-size: 0.88rem; font-weight: 800; color: #ffffff;'>{ktc_s}</div>
                                </div>
                                <div style='background: rgba(16, 185, 129, 0.04); border: 1px solid rgba(16, 185, 129, 0.15); border-radius: 6px; padding: 6px 8px;'>
                                    <div style='font-size: 0.66rem; color: #34d399; font-weight: 700;'>FantasyCalc</div>
                                    <div style='font-size: 0.88rem; font-weight: 800; color: #ffffff;'>{fc_s}</div>
                                </div>
                                <div style='background: rgba(168, 85, 247, 0.04); border: 1px solid rgba(168, 85, 247, 0.15); border-radius: 6px; padding: 6px 8px;'>
                                    <div style='font-size: 0.66rem; color: #c084fc; font-weight: 700;'>DynastyProcess</div>
                                    <div style='font-size: 0.88rem; font-weight: 800; color: #ffffff;'>{dp_s}</div>
                                </div>
                                <div style='background: rgba(245, 158, 11, 0.04); border: 1px solid rgba(245, 158, 11, 0.15); border-radius: 6px; padding: 6px 8px;'>
                                    <div style='font-size: 0.66rem; color: #fbbf24; font-weight: 700;'>Consensus ECR</div>
                                    <div style='font-size: 0.88rem; font-weight: 800; color: #ffffff;'>{asset['pos_ecr_str']}</div>
                                </div>
                            </div>
                            """

                        card_html = f"""
                        <div class='card-container' style='height: 100%; border: 1px solid {border_c}; background: rgba(15, 23, 42, 0.75); border-radius: 10px; padding: 16px; margin-bottom: 12px;'>
                            <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;'>
                                <span class='status-capsule' style='background: {b_bg}; color: {b_color}; font-weight: 800; font-size: 0.74rem;'>{b_text}</span>
                                <span style='color: #94a3b8; font-size: 0.76rem; font-weight: 700;'>{a_share:.1f}% Share</span>
                            </div>

                            <div style='display: flex; align-items: center; gap: 12px; margin-bottom: 14px;'>
                                {avatar_html}
                                <div>
                                    <div style='font-size: 1.12rem; font-weight: 800; color: #ffffff; line-height: 1.2;'>{asset['name']}</div>
                                    <div style='display: flex; align-items: center; gap: 6px; margin-top: 4px; font-size: 0.78rem; color: #94a3b8;'>
                                        <span class='badge-pos {pos_cls}' style='font-size: 0.65rem; padding: 1px 5px;'>{asset['pos']}</span>
                                        <span>{asset['team']}</span>
                                        <span>• Age {asset['age']}</span>
                                    </div>
                                </div>
                            </div>

                            <div style='background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.07); border-radius: 8px; padding: 10px 12px; margin-bottom: 12px;'>
                                <div style='font-size: 0.7rem; font-weight: 700; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.04em;'>{val_card_title}</div>
                                <div style='display: flex; align-items: baseline; gap: 6px; margin-top: 2px;'>
                                    <span style='font-size: 1.55rem; font-weight: 800; color: #f8fafc;'>{asset['val']:,.0f}</span>
                                    <span style='color: #38bdf8; font-size: 0.8rem; font-weight: 700;'>PTS</span>
                                </div>
                                <div style='display: flex; gap: 6px; margin-top: 6px;'>
                                    <span class='rank-pill'>Overall {asset['o_ecr_str']}</span>
                                    <span class='rank-pill rank-pill-highlight'>{asset['pos_ecr_str']}</span>
                                </div>
                            </div>

                            {constituent_grid}
                        </div>
                        """
                        st.html(card_html)

                # Render Detailed Table
                st.html(render_player_comparison_table_html(selected_assets, is_redraft=is_redraft))

        if is_dynasty:
            with tab_signal:
                # =========================================================
                # SUBVIEW: BUY LOW / SELL HIGH
                # =========================================================
                # Always built from the dynasty lookup (primary_lookup),
                # independent of the "Valuation Scope" toggle above - Market
                # Signal is a dynasty-only concept (compute_market_rank_
                # divergence never runs on redraft_lookup), so this subview
                # must not go empty just because the user is browsing
                # Single-Season values in the Market Player Database tab.
                st.markdown(
                    "<div style='margin: 8px 0 16px 0; color: #94a3b8; font-size: 0.88rem;'>"
                    "Crowd consensus (KeepTradeCut / FantasyCalc) vs. expert consensus (DynastyProcess) rank "
                    "divergence - informational context on which players the market is most excited about "
                    "(Sell High) or most skeptical of (Buy Low) relative to expert rankings. This is not a "
                    "trade recommendation."
                    "</div>",
                    unsafe_allow_html=True
                )

                signal_assets = build_market_assets_list(primary_lookup, players, is_redraft=False)
                for r in signal_assets:
                    owner = owner_lookup.get(r["pid"])
                    if owner:
                        r["Owner"] = owner["username"]
                        r["Trajectory"] = owner["trajectory"]
                        r["_owner_category"] = owner["category"]
                    else:
                        r["Owner"] = "Free Agent"
                        r["Trajectory"] = "—"
                        r["_owner_category"] = None

                # Sell High = rank_diff most negative (market more excited
                # than DP); Buy Low = rank_diff most positive (DP undervalues
                # vs. the market) - most extreme divergence first on each side.
                sell_high_rows = sorted(
                    (r for r in signal_assets if r.get("market_signal") == "sell_high"),
                    key=lambda x: x["_rank_diff"],
                )
                buy_low_rows = sorted(
                    (r for r in signal_assets if r.get("market_signal") == "buy_low"),
                    key=lambda x: x["_rank_diff"],
                    reverse=True,
                )
                for idx, r in enumerate(sell_high_rows, start=1):
                    r["Rank"] = f"#{idx}"
                for idx, r in enumerate(buy_low_rows, start=1):
                    r["Rank"] = f"#{idx}"

                c_sell, c_buy = st.columns(2)
                with c_sell:
                    st.markdown(f"##### 🔥 Sell High ({len(sell_high_rows)})")
                    st.caption("Market values these players above expert consensus - most extreme divergence first.")
                    st.html(render_market_table_html(sell_high_rows, is_redraft=False, show_trajectory=True))
                with c_buy:
                    st.markdown(f"##### 💎 Buy Low ({len(buy_low_rows)})")
                    st.caption("Expert consensus values these players above the market - most extreme divergence first.")
                    st.html(render_market_table_html(buy_low_rows, is_redraft=False, show_trajectory=True))


    # =========================================================================
    # TAB 7: MULTI-LEAGUE PORTFOLIO & PLAYER EXPOSURE
    # =========================================================================
    with tab_portfolio:
        st.subheader("Multi-League Portfolio & Player Exposure")
        st.caption("Cross-analyzes all your Sleeper leagues to measure player shares, concentration risk, and your foundation franchise assets.")

        exp_rows, total_user_leagues, l_records = fetch_portfolio_exposure(
            user["user_id"], all_l_ids, all_l_names, players, market_db, selected_mode, active_week, sorted_leagues
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
            c_psort1, c_psort2, c_psort3 = st.columns([2, 1, 1], vertical_alignment="bottom")
            with c_psort1:
                sort_port_col = st.selectbox(
                    "Sort Portfolio Players By:",
                    ["Shares / Ownership", "Consensus Value", "Exposure %", "Overall Rank", "Pos Rank", "Age", "Player Name"],
                    key="port_sort_col"
                )
            with c_psort2:
                sort_port_order = st.selectbox(
                    "Order:",
                    ["Descending (High / Best)", "Ascending (Low)"],
                    key="port_sort_order"
                )
            with c_psort3:
                st.caption(f"Showing {len(filtered_exp)} portfolio players matching filters.")

            sorted_port = list(filtered_exp)
            is_desc = "Descending" in sort_port_order

            def safe_ecr(val_str):
                digits = "".join(c for c in str(val_str) if c.isdigit())
                return float(digits) if digits else 9999.0

            def safe_age(val):
                try:
                    return float(val)
                except (ValueError, TypeError):
                    return 0.0

            if sort_port_col == "Shares / Ownership":
                sorted_port.sort(key=lambda x: (x.get("Share Count", 0), x.get("Consensus Value", 0)), reverse=is_desc)
            elif sort_port_col == "Exposure %":
                sorted_port.sort(key=lambda x: x.get("Exposure %", 0.0), reverse=is_desc)
            elif sort_port_col == "Consensus Value":
                sorted_port.sort(key=lambda x: float(x.get("Consensus Value", 0) if isinstance(x.get("Consensus Value"), (int, float)) else 0), reverse=is_desc)
            elif sort_port_col in ("Overall Rank", "Overall ECR"):
                sorted_port.sort(key=lambda x: safe_ecr(x.get("Overall ECR")), reverse=not is_desc)
            elif sort_port_col in ("Pos Rank", "Pos ECR"):
                sorted_port.sort(key=lambda x: safe_ecr(x.get("Pos ECR")), reverse=not is_desc)
            elif sort_port_col == "Age":
                sorted_port.sort(key=lambda x: safe_age(x.get("Age")), reverse=is_desc)
            elif sort_port_col == "Player Name":
                sorted_port.sort(key=lambda x: str(x.get("Player", "")).lower(), reverse=not is_desc)

            st.html(render_portfolio_table_html(sorted_port[:100]))
        else:
            st.info("No players matching the portfolio filter criteria.")
