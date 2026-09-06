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

USERNAME = "henriquefrz"

# -----------------------------------------------------------------------------
# Streamlit Page Setup & Custom Mobile-Responsive CSS
# -----------------------------------------------------------------------------
LOGO_PATH = "assets/logo.jpg"
PAGE_ICON = LOGO_PATH if os.path.exists(LOGO_PATH) else "🏈"

st.set_page_config(
    page_title="Fantasy Analytics",
    page_icon=PAGE_ICON,
    layout="wide",
    initial_sidebar_state="auto",
)

st.markdown(
    """
    <style>
    /* Fixed Streamlit Header Styling */
    header[data-testid="stHeader"] {
        background: rgba(11, 15, 23, 0.95) !important;
        backdrop-filter: blur(10px) !important;
        border-bottom: 1px solid rgba(255, 255, 255, 0.06) !important;
        z-index: 99 !important;
    }

    /* Global Container & Clean Layout */
    .block-container {
        padding-top: 5rem !important;
        padding-bottom: 3rem !important;
        padding-left: 1.25rem !important;
        padding-right: 1.25rem !important;
        max-width: 1400px;
    }

    /* Positional Micro-Badges */
    .badge-pos {
        display: inline-block;
        padding: 2px 7px;
        border-radius: 4px;
        font-weight: 700;
        font-size: 0.72rem;
        color: #fff;
        margin-right: 4px;
        letter-spacing: 0.04em;
    }
    .badge-qb { background-color: #ef4444; }
    .badge-rb { background-color: #06b6d4; }
    .badge-wr { background-color: #3b82f6; }
    .badge-te { background-color: #f59e0b; }
    .badge-k  { background-color: #8b5cf6; }
    .badge-def{ background-color: #64748b; }
    .badge-pick{ background-color: #10b981; }

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
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------------------------------------------------------------
# Cached Data Fetching
# -----------------------------------------------------------------------------
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_market_database(_cache_version="v5_fantasy_analytics_clean"):
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
    base_dynasty_sf = build_positional_lookup(fp_rankings, player_ids, "dynasty")
    enrich_lookup_with_consensus_values(base_dynasty_sf, values_players, player_ids, ktc_raw=ktc_sf, fc_raw=fc_sf, is_superflex=True, mode="equal")

    base_dynasty_1qb = build_positional_lookup(fp_rankings, player_ids, "dynasty")
    enrich_lookup_with_consensus_values(base_dynasty_1qb, values_players, player_ids, ktc_raw=ktc_1qb, fc_raw=fc_1qb, is_superflex=False, mode="equal")

    base_redraft = build_positional_lookup(fp_rankings, player_ids, "redraft")
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
                val_data = _primary_lookup.get(pid, {})
                m_val = val_data.get("market_value", 0.0)
                ecr = val_data.get("rank_ecr", 999.0)

                if pid not in player_exposure:
                    player_exposure[pid] = {
                        "player_id": pid,
                        "name": p_name,
                        "position": pos,
                        "team": nfl_team,
                        "market_value": m_val,
                        "rank_ecr": ecr,
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

        rows.append({
            "Avatar": get_player_avatar_url(pid, pos, d["team"]),
            "Player": d["name"],
            "Pos": pos,
            "NFL Team": d["team"],
            "Shares": f"{c} / {total_leagues}",
            "Share Count": c,
            "Exposure": f"{pct:.0f}%",
            "Exposure %": pct,
            "Pos ECR": pos_ecr_str,
            "Consensus Value": d["market_value"],
            "Leagues Owned": ", ".join(d["leagues"]),
        })

    rows.sort(key=lambda x: (x["Share Count"], x["Consensus Value"]), reverse=True)
    return rows, total_leagues, league_summaries


# -----------------------------------------------------------------------------
# App State & Navigation Router Initialization
# -----------------------------------------------------------------------------
if "selected_league_id" not in st.session_state:
    st.session_state["selected_league_id"] = None


# -----------------------------------------------------------------------------
# Sidebar: Branding, User Connection, and Navigation
# -----------------------------------------------------------------------------
if os.path.exists(LOGO_PATH):
    st.sidebar.image(LOGO_PATH, use_container_width=True)

st.sidebar.markdown("### Fantasy Analytics")
st.sidebar.caption("Intelligent Multi-League & Dynasty Portfolio Management")

input_username = st.sidebar.text_input(
    "Sleeper Username",
    value=USERNAME,
    help="Enter any Sleeper username to analyze their leagues, rankings, and roster portfolio."
).strip()
active_user_handle = input_username if input_username else USERNAME

with st.spinner(f"Connecting to Sleeper (@{active_user_handle}) & Market Feeds..."):
    market_db = fetch_market_database()
    try:
        user, active_season, active_week, leagues = fetch_user_and_leagues(active_user_handle)
    except Exception:
        st.sidebar.error(f"User @{active_user_handle} not found. Reverting to @{USERNAME}.")
        user, active_season, active_week, leagues = fetch_user_and_leagues(USERNAME)

st.sidebar.caption(f"Connected: **@{user['username']}** | Season: **{active_season}** (Wk {active_week})")

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

# Sidebar: League Switcher
PORTAL_LABEL = "🏠 Portal: All Leagues Overview"
league_options = [PORTAL_LABEL] + [l["name"] for l in sorted_leagues]

current_lid = st.session_state.get("selected_league_id")
default_idx = 0
if current_lid is not None:
    for idx, lg in enumerate(sorted_leagues, start=1):
        if lg.get("league_id") == current_lid:
            default_idx = idx
            break

selected_option = st.sidebar.selectbox("Active Workspace:", league_options, index=default_idx)

if selected_option == PORTAL_LABEL:
    if st.session_state.get("selected_league_id") is not None:
        st.session_state["selected_league_id"] = None
        st.rerun()
else:
    chosen_lg = next(l for l in sorted_leagues if l["name"] == selected_option)
    if st.session_state.get("selected_league_id") != chosen_lg["league_id"]:
        st.session_state["selected_league_id"] = chosen_lg["league_id"]
        st.rerun()

# Sidebar: Valuation Mode Switcher
st.sidebar.markdown("---")
st.sidebar.markdown("#### ⚖️ Valuation Consensus Model")
mode_keys = list(VALUATION_MODES.keys())
mode_labels = [VALUATION_MODES[k] for k in mode_keys]
selected_mode_label = st.sidebar.selectbox(
    "Active Valuation Engine:",
    mode_labels,
    index=0,
    help="Determines how players and draft picks are evaluated across all tabs."
)
selected_mode = mode_keys[mode_labels.index(selected_mode_label)]

# Sidebar: Market Freshness Status
st.sidebar.markdown("---")
with st.sidebar.expander("🕒 Market Data Freshness", expanded=False):
    fresh = market_db.get("freshness", {})
    ktc_stat = (fresh.get("ktc") or fresh.get("keeptradecut") or {}).get("status", "Live Current")
    fc_stat = (fresh.get("fantasycalc") or {}).get("status", "Live Current")
    dp_stat = (fresh.get("dynastyprocess") or {}).get("status", "Updated")
    fp_stat = (fresh.get("fantasypros") or {}).get("status", "Updated")
    st.markdown(f"**KeepTradeCut:** `{ktc_stat}`")
    st.markdown(f"**FantasyCalc:** `{fc_stat}`")
    st.markdown(f"**DynastyProcess:** `{dp_stat}`")
    st.markdown(f"**FantasyPros ECR:** `{fp_stat}`")


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
    total_portfolio_val = sum(s.get("roster_value", 0.0) for s in l_summaries)
    top_player = exp_rows[0]["Player"] if exp_rows else "—"
    top_shares = exp_rows[0]["Shares"] if exp_rows else "—"

    col_p1, col_p2, col_p3, col_p4 = st.columns(4)
    with col_p1:
        st.metric("Active Franchises", f"{total_user_leagues} Leagues", "Sleeper Connected")
    with col_p2:
        st.metric("Total Portfolio Asset Value", f"{total_portfolio_val:,.0f} pts", "Across All Rosters")
    with col_p3:
        st.metric("Unique Rostered Players", f"{len(exp_rows)} Assets", "Diversification")
    with col_p4:
        st.metric("Core Exposure Asset", f"{top_player}", f"{top_shares} Leagues")

    st.markdown("---")
    st.markdown("### 🏈 Your League Workspaces")
    st.caption("Select any franchise to enter its dedicated analytical suite (Franchise Hub, Matchups & Start/Sit, Waivers, Power Rankings, Trade Center).")

    # League Cards Grid (2-column responsive layout)
    grid_cols = st.columns(2)
    for idx, lg in enumerate(sorted_leagues):
        col = grid_cols[idx % 2]
        lid = lg["league_id"]
        lname = lg["name"]
        rosters = get_league_rosters(lid)
        my_r = next((r for r in rosters if r.get("owner_id") == user["user_id"] or user["user_id"] in (r.get("co_owners") or [])), None)

        settings = lg.get("settings", {})
        is_dyn = (settings.get("type") == 2)
        total_rosters = lg.get("total_rosters", len(rosters))
        roster_pos = lg.get("roster_positions", [])
        is_sf = any(pos in ("SUPER_FLEX", "QB") for pos in roster_pos if roster_pos.count("QB") > 1 or pos == "SUPER_FLEX")
        tep_b = settings.get("tep_bonus", 0.0)

        # Quick summary stats
        m_settings = (my_r.get("settings") or {}) if my_r else {}
        w = m_settings.get("wins", 0)
        l = m_settings.get("losses", 0)
        fpts = (m_settings.get("fpts", 0) + (m_settings.get("fpts_decimal", 0) / 100.0))
        p_count = len(my_r.get("players") or []) if my_r else 0

        # Trajectory badge
        if is_dyn:
            if w >= l:
                badge_html = "<span class='status-capsule status-contender'>CONTENDER</span>"
            else:
                badge_html = "<span class='status-capsule status-rebuild'>REBUILD</span>"
        else:
            badge_html = "<span class='status-capsule status-bubble'>REDRAFT</span>"

        format_str = f"{'Dynasty' if is_dyn else 'Redraft'} • {'Superflex' if is_sf else '1QB'} ({total_rosters} Teams)"
        if tep_b > 0:
            format_str += f" • {tep_b} TEP"

        with col:
            st.markdown(
                f"""
                <div class='card-container card-highlight'>
                    <div style='display: flex; justify-content: space-between; align-items: flex-start;'>
                        <h4 style='margin-bottom: 4px;'>{lname}</h4>
                        {badge_html}
                    </div>
                    <div style='color: #94a3b8; font-size: 0.85rem; margin-bottom: 12px;'>{format_str}</div>
                    <div style='display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; margin-bottom: 14px; font-size: 0.88rem;'>
                        <div><b>Record:</b> {w}-{l}</div>
                        <div><b>Points:</b> {fpts:,.1f}</div>
                        <div><b>Roster:</b> {p_count} players</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button(f"Open Workspace →", key=f"btn_enter_{lid}", use_container_width=True):
                st.session_state["selected_league_id"] = lid
                st.rerun()

    # Quick Top Exposure Table on Front Page
    st.markdown("---")
    st.markdown("### 🌐 Core Portfolio Exposure (Cross-League Foundations)")
    if exp_rows:
        df_quick = pd.DataFrame(exp_rows[:10])
        df_quick["Consensus Value"] = df_quick["Consensus Value"].apply(lambda v: f"{v:,.0f} pts")
        st.dataframe(
            df_quick[["Avatar", "Player", "Pos", "NFL Team", "Shares", "Exposure", "Pos ECR", "Consensus Value", "Leagues Owned"]],
            column_config={
                "Avatar": st.column_config.ImageColumn("", width="small"),
            },
            hide_index=True,
            use_container_width=True,
        )


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
        st.markdown(f"## 🏈 {selected_league_name}")
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
        st.warning("⚠️ This league is currently in pre-draft status and has not drafted rosters yet.")
        if st.button("← Return to All Leagues", key="btn_predraft_back"):
            st.session_state["selected_league_id"] = None
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
        format_badge += f" • {tep_bonus} TEP"
    st.caption(f"{format_badge} | Valuation Engine: **{VALUATION_MODES[selected_mode]}**")

    # Top Metric Summary Pills
    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    with col_m1:
        wins = user_roster.get("settings", {}).get("wins", 0)
        losses = user_roster.get("settings", {}).get("losses", 0)
        st.metric("Team Record", f"{wins} - {losses}", "Current Season")
    with col_m2:
        clean_status = team_status.split("(")[0].strip() if team_status else "Active"
        st.metric("Franchise Trajectory", clean_status, help=team_status)
    with col_m3:
        if is_dynasty and user_profile:
            dyn_rank_str = f"Rank #{dynasty_pos} of {dynasty_total}" if dynasty_pos else "Pre-Draft"
            st.metric("Dynasty Total Value", f"{user_profile['total_value']:,.0f} pts", dyn_rank_str)
        else:
            red_rank_str = f"#{redraft_pos} of {redraft_total}" if redraft_pos else "Pre-Draft"
            st.metric("Redraft Contender Rank", red_rank_str)
    with col_m4:
        if is_dynasty and user_profile:
            st.metric("Starting Lineup Value", f"{user_profile['starter_value']:,.0f} pts", f"Bench: {user_profile['bench_value']:,.0f} pts")
        else:
            fpts = user_roster.get("settings", {}).get("fpts", 0.0)
            st.metric("Points Scored", f"{fpts:,.1f} pts")

    st.markdown("---")

    # -------------------------------------------------------------------------
    # Reordered Multi-Tab Interface
    # -------------------------------------------------------------------------
    tab_hub, tab_start_sit, tab_waivers, tab_power, tab_trades, tab_market, tab_portfolio = st.tabs([
        "🏠 Franchise Hub",
        "⚡ Matchups & Start/Sit",
        "🌊 Add/Drops & Waivers",
        "📊 Power Rankings & Playoff Odds",
        "🤝 Trade Center & Targeted Finder",
        "🔍 Market Rankings & Database",
        "🌐 Multi-League Portfolio",
    ])

    # =========================================================================
    # TAB 1: FRANCHISE HUB (Enhanced with Full Roster Breakdown)
    # =========================================================================
    with tab_hub:
        st.subheader(f"Franchise Executive Dashboard: {selected_league_name}")

        settings = user_roster.get("settings", {})
        wins = settings.get("wins", 0)
        losses = settings.get("losses", 0)
        ties = settings.get("ties", 0)
        total_games = wins + losses + ties
        win_pct = (wins / total_games * 100.0) if total_games > 0 else 0.0
        fpts = settings.get("fpts", 0) + (settings.get("fpts_decimal", 0) / 100.0)
        fpts_against = settings.get("fpts_against", 0) + (settings.get("fpts_against_decimal", 0) / 100.0)
        diff = fpts - fpts_against

        col_h1, col_h2, col_h3 = st.columns([1.2, 1, 1])
        with col_h1:
            if team_cat == "win":
                traj_badge = "<span class='status-capsule status-contender'>CONTENDER</span>"
            elif team_cat == "rebuild":
                traj_badge = "<span class='status-capsule status-rebuild'>REBUILD</span>"
            else:
                traj_badge = "<span class='status-capsule status-bubble'>BUBBLE</span>"

            st.markdown(
                f"<div class='card-container card-highlight'>"
                f"<div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;'>"
                f"<b>Strategic Posture:</b> {traj_badge}"
                f"</div>"
                f"<b>Status:</b> {team_status}<br/>"
                f"<b>Format:</b> {'Dynasty' if is_dynasty else 'Redraft'} • {'Superflex' if is_superflex else '1QB'} ({len(rosters)} Teams)"
                f"</div>",
                unsafe_allow_html=True,
            )

        with col_h2:
            st.markdown(
                f"<div class='card-container'>"
                f"<b>Standings:</b> {wins}W - {losses}L{f' - {ties}T' if ties > 0 else ''} ({win_pct:.1f}%)<br/>"
                f"<b>Points For (PF):</b> {fpts:,.1f} pts<br/>"
                f"<b>Points Against (PA):</b> {fpts_against:,.1f} pts (<b>{'+' if diff >= 0 else ''}{diff:,.1f}</b>)"
                f"</div>",
                unsafe_allow_html=True,
            )

        with col_h3:
            if is_dynasty and user_profile:
                dyn_pos_txt = f"#{dynasty_pos}" if dynasty_pos else "Pre-Draft"
                st.markdown(
                    f"<div class='card-container'>"
                    f"<b>Dynasty Total:</b> {user_profile['total_value']:,.0f} pts ({dyn_pos_txt} of {dynasty_total})<br/>"
                    f"<b>Starters:</b> {user_profile['starter_value']:,.0f} pts | <b>Bench:</b> {user_profile['bench_value']:,.0f} pts<br/>"
                    f"<b>Draft Capital:</b> {user_profile['picks_value']:,.0f} pts ({len(user_profile.get('picks', []))} picks)"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            else:
                red_pos_txt = f"#{redraft_pos}" if redraft_pos else "Pre-Draft"
                st.markdown(
                    f"<div class='card-container'>"
                    f"<b>Redraft Rank:</b> {red_pos_txt} of {redraft_total}<br/>"
                    f"<b>Active Starters:</b> {len(user_roster.get('starters') or [])} players<br/>"
                    f"<b>Bench Depth:</b> {len(user_roster.get('players') or []) - len(user_roster.get('starters') or [])} players"
                    f"</div>",
                    unsafe_allow_html=True,
                )

        # Full Roster Breakdown & Equity Distribution
        st.markdown("---")
        st.markdown("### 📋 Complete Franchise Roster Breakdown & Asset Valuation")
        st.caption("Detailed view of all rostered players, market valuations, positional ECR, and franchise equity shares.")

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
            ecr = val_data.get("rank_ecr", 999.0)
            pos_ecr_str = f"{pos}{int(ecr)}" if (ecr and ecr < 900) else "—"
            equity_pct = (m_val / total_team_val * 100.0)

            return {
                "Avatar": get_player_avatar_url(pid, pos, team),
                "Slot": slot_label,
                "Player": pname,
                "Pos": pos,
                "NFL Team": team,
                "Age": age,
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

        roster_sub_starters, roster_sub_bench, roster_sub_taxi, roster_sub_all = st.tabs([
            f"⭐ Starters ({len(starters_data)})",
            f"🛡️ Bench ({len(bench_data)})",
            f"🚕 Taxi & IR ({len(taxi_data) + len(ir_data)})",
            f"🌐 All Rostered Players ({len(user_pids)})",
        ])

        with roster_sub_starters:
            if starters_data:
                df_st = pd.DataFrame(starters_data).drop(columns=["_val"])
                st.dataframe(
                    df_st,
                    column_config={"Avatar": st.column_config.ImageColumn("", width="small")},
                    hide_index=True,
                    use_container_width=True,
                )
            else:
                st.info("No active starters designated.")

        with roster_sub_bench:
            if bench_data:
                df_bn = pd.DataFrame(bench_data).drop(columns=["_val"])
                st.dataframe(
                    df_bn,
                    column_config={"Avatar": st.column_config.ImageColumn("", width="small")},
                    hide_index=True,
                    use_container_width=True,
                )
            else:
                st.info("No bench players detected.")

        with roster_sub_taxi:
            if taxi_data:
                st.markdown("#### Taxi Squad Assets")
                df_tx = pd.DataFrame(taxi_data).drop(columns=["_val"])
                st.dataframe(
                    df_tx,
                    column_config={"Avatar": st.column_config.ImageColumn("", width="small")},
                    hide_index=True,
                    use_container_width=True,
                )
            if ir_data:
                st.markdown("#### Injured Reserve (IR)")
                df_ir = pd.DataFrame(ir_data).drop(columns=["_val"])
                st.dataframe(
                    df_ir,
                    column_config={"Avatar": st.column_config.ImageColumn("", width="small")},
                    hide_index=True,
                    use_container_width=True,
                )
            if not taxi_data and not ir_data:
                st.info("No taxi squad or IR reserve players.")

        with roster_sub_all:
            all_roster_rows = starters_data + bench_data + taxi_data + ir_data
            all_roster_rows.sort(key=lambda x: x["_val"], reverse=True)
            df_all = pd.DataFrame(all_roster_rows).drop(columns=["_val"])
            st.dataframe(
                df_all,
                column_config={"Avatar": st.column_config.ImageColumn("", width="small")},
                hide_index=True,
                use_container_width=True,
            )

        # Draft Capital Table for Dynasty
        if is_dynasty and user_profile and user_profile.get("picks"):
            st.markdown("---")
            st.markdown("### 🎟️ Future Draft Capital Portfolio")
            pick_rows = []
            for pk in user_profile["picks"]:
                val = pk.get("market_value", 0.0)
                pick_rows.append({
                    "Draft Pick Asset": pk.get("name", "Draft Pick"),
                    "Season": pk.get("season", "—"),
                    "Round": f"Round {pk.get('round', '—')}",
                    "Consensus Market Value": f"{val:,.0f} pts",
                    "_val": val,
                })
            pick_rows.sort(key=lambda x: x["_val"], reverse=True)
            df_picks = pd.DataFrame(pick_rows).drop(columns=["_val"])
            st.dataframe(df_picks, hide_index=True, use_container_width=True)


    # =========================================================================
    # TAB 2: MATCHUPS & START/SIT
    # =========================================================================
    with tab_start_sit:
        st.subheader(f"⚡ Week {active_week} Matchup & Starting Lineup Audit")

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
            with st.expander(f"📋 View Opponent Starting Lineup ({opp_name})", expanded=False):
                st.dataframe(
                    pd.DataFrame(opp_lineup_rows),
                    column_config={"Avatar": st.column_config.ImageColumn("", width="small")},
                    hide_index=True,
                    use_container_width=True,
                )

        # Optimization alerts
        if audit["start_sit_swaps"]:
            st.warning(f"💡 **Lineup Optimization Available:** You can gain **+{audit['points_differential']:.1f} pts** by adjusting your starters:")
            for swap in audit["start_sit_swaps"]:
                st.markdown(
                    f"- 👉 **START:** `{swap['start_player'].get('full_name')}` ({swap['start_proj']:.1f} pts) "
                    f"over **SIT:** `{swap['sit_player'].get('full_name')}` ({swap['sit_proj']:.1f} pts) in **{swap['slot']}** "
                    f"(Net gain: **+{swap['gain']:.1f} pts**)"
                )
        else:
            st.success("✅ **Optimal Lineup Set:** Your active Sleeper lineup maximizes projected points for this week!")

        # Active Starter Injury Alerts
        if audit["injury_alerts"]:
            st.error("🚨 **Active Starter Injury Risk Detected:**")
            for inj in audit["injury_alerts"]:
                sname = inj["starter"].get("full_name")
                status = inj["status"]
                slot = inj["slot"]
                pivot = inj.get("pivot")
                if pivot:
                    pname = pivot[0].get("full_name")
                    pproj = pivot[1]
                    st.markdown(f"- ⚠️ **[{status.upper()}]** `{sname}` ({slot}, {inj['starter_proj']:.1f} pts) ➔ **Recommended Pivot:** `{pname}` ({pproj:.1f} pts)")
                else:
                    st.markdown(f"- ⚠️ **[{status.upper()}]** `{sname}` ({slot}, {inj['starter_proj']:.1f} pts) ➔ *No healthy bench substitute found!*")


    # =========================================================================
    # TAB 3: ADD/DROPS & WAIVERS (Moved Before Power Rankings)
    # =========================================================================
    with tab_waivers:
        st.subheader("🌊 Intelligent Waiver Wire & Add/Drop Assistant")

        roster_players = get_roster_players(user_roster, players)
        free_agents = get_free_agents(rosters, players)

        col_w1, col_w2 = st.columns([2, 1])
        with col_w1:
            if is_dynasty:
                waiver_perspective = st.radio(
                    "Evaluation Perspective / Horizon:",
                    [
                        "🌱 Dynasty (Long-Term Market Capital & Youth Upside)",
                        "🏆 Rest of Season (ROS / Win-Now Starting Points)",
                    ],
                    horizontal=True,
                    help="Dynasty horizon optimizes for long-term player trade capital. ROS horizon optimizes for immediate starting points."
                )
                eval_dynasty = "Dynasty" in waiver_perspective
            else:
                waiver_perspective = "🏆 Rest of Season (Redraft)"
                eval_dynasty = False

        with col_w2:
            protection_choice = st.selectbox(
                "Drop Protection Level:",
                ["🛡️ Injured Stars Protected", "⚠️ Unrestricted (Show All Drops)"],
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

        # IR Slot Actions
        ir_suggestions = waivers.get("ir_suggestions", [])
        if ir_suggestions:
            st.markdown("### 🚑 IR Slot Optimization")
            for ir in ir_suggestions:
                pname = ir["player"].get("full_name")
                reason = ir.get("reason", "IR Eligible")
                st.info(f"• **Move to IR:** `{pname}` ({reason}) ➔ *Frees up an active bench spot for a free agent add.*")

        # Starting Lineup Upgrades
        starter_upgrades = waivers.get("starter_upgrades", [])
        if starter_upgrades:
            st.markdown("### ⭐ Starting Lineup Upgrades")
            for s in starter_upgrades[:3]:
                add_p = s["add_player"]
                drop_p = s["drop_player"]
                disp_p = s.get("displaced_player")
                disp_name = (disp_p.get("full_name") or disp_p.get("player_id")) if disp_p else "Starting Slot"
                diff = s.get("market_value_gain", 0.0)
                tag = s.get("priority_tag", "STARTER")
                add_val = s.get("add_value", s.get("add_ranking", {}).get("market_value", 0.0))
                drop_val = s.get("drop_value", s.get("drop_ranking", {}).get("market_value", 0.0))

                st.markdown(
                    f"<div class='card-container card-success'>"
                    f"<b>{tag}</b>: "
                    f"<b>ADD:</b> <code>{add_p.get('full_name')}</code> ({add_p.get('position')} — {add_p.get('team')}, Val: {add_val:,.0f} pts)<br/>"
                    f"<b>DROP:</b> <code>{drop_p.get('full_name')}</code> (Bench | {drop_p.get('position')}, Val: {drop_val:,.0f} pts)<br/>"
                    f"↳ <i>Displaces <b>{disp_name}</b> in starting lineup (Net Value Gain: <b>+{diff:,.0f} pts</b>)</i>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

        # Bench Upgrades
        cross_upgrades = waivers.get("cross_pos_upgrades", [])
        if cross_upgrades:
            st.markdown("### 📈 Top Bench Upgrades")
            for s in cross_upgrades[:3]:
                add_p = s["add_player"]
                drop_p = s["drop_player"]
                diff = s.get("market_value_gain", 0.0)
                add_val = s.get("add_value", s.get("add_ranking", {}).get("market_value", 0.0))
                drop_val = s.get("drop_value", s.get("drop_ranking", {}).get("market_value", 0.0))

                st.markdown(
                    f"- **ADD:** `{add_p.get('full_name')}` ({add_p.get('position')}, Val: {add_val:,.0f} pts) "
                    f"➔ **DROP:** `{drop_p.get('full_name')}` ({drop_p.get('position')}, Val: {drop_val:,.0f} pts) "
                    f"[Net: **+{diff:,.0f} pts**]"
                )

        # Interactive Free Agent Market Explorer
        st.markdown("---")
        st.markdown("### 🔍 Free Agent Market Explorer")
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
            val = p_val_data.get("market_value", 0.0)
            ecr = p_val_data.get("rank_ecr", 999.0)
            fc_v = p_val_data.get("fc_val")
            ktc_v = p_val_data.get("ktc_val")
            dp_v = p_val_data.get("dp_val")
            pos_ecr_str = f"{pos}{int(ecr)}" if (ecr and ecr < 900) else "—"

            fa_rows.append({
                "Avatar": get_player_avatar_url(pid, pos, fa.get("team")),
                "Player": pname,
                "Pos": pos,
                "NFL Team": fa.get("team") or "FA",
                "Consensus Value": f"{val:,.0f} pts",
                "Pos ECR": pos_ecr_str,
                "FantasyCalc": f"{fc_v:,.0f}" if fc_v is not None else "—",
                "KeepTradeCut": f"{ktc_v:,.0f}" if ktc_v is not None else "—",
                "DynastyProcess": f"{dp_v:,.0f}" if dp_v is not None else "—",
                "_raw_val": val,
            })

        fa_rows.sort(key=lambda x: x["_raw_val"], reverse=True)
        df_fa = pd.DataFrame(fa_rows[:50]).drop(columns=["_raw_val"]) if fa_rows else pd.DataFrame()
        if not df_fa.empty:
            st.dataframe(
                df_fa,
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
        st.subheader("📊 League Power Rankings & Playoff Simulations")

        if not is_dynasty:
            # Monte Carlo Simulation
            st.caption("1,000-Run Monte Carlo Simulation incorporating dynamic season records, points scored, and rest-of-season schedule.")

            playoff_start = selected_league.get("settings", {}).get("playoff_week_start", 15)
            team_expectations = {}
            for r in rosters:
                rid = r["roster_id"]
                exp_pts, std_dev = compute_team_lineup_expectation(
                    roster=r,
                    roster_players=all_rosters_players.get(rid, []),
                    projections=weekly_projections,
                    scoring_settings=scoring,
                    roster_positions=roster_pos,
                    redraft_lookup=redraft_lookup,
                )
                team_expectations[rid] = (exp_pts, std_dev)

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
            st.info(f"🏟️ **Playoff Format:** Top **{p_count} Teams** qualify for the postseason.")

            ranked_sim = sorted(sim_results.values(), key=lambda t: t["power_score"], reverse=True)
            table_data = []
            for rank_idx, t in enumerate(ranked_sim, 1):
                rid = t["roster_id"]
                mgr = user_map.get(next((r["owner_id"] for r in rosters if r["roster_id"] == rid), ""), f"Team {rid}")
                is_me = (rid == user_roster["roster_id"])
                table_data.append({
                    "Rank": f"{'👉 ' if is_me else ''}#{rank_idx}",
                    "Manager / Team": mgr,
                    "Projected W-L": f"{t['avg_wins']:.1f} - {t['avg_losses']:.1f}",
                    "Median PPG": f"{t['expected_pts']:.1f}",
                    "Playoff Odds": f"{t['playoff_pct']:.1f}%",
                    "1st-Round Bye": f"{t['bye_pct']:.1f}%",
                    "Champ Odds": f"{t['champ_pct']:.1f}%",
                    "Season Power Score": f"{t['power_score']:.1f}",
                })

            df_sim = pd.DataFrame(table_data)
            st.dataframe(df_sim, hide_index=True, use_container_width=True)

        else:
            # Dynasty Power Rankings (50/30/20)
            st.caption("Dynasty Power Formula: `50% Starters Value + 30% Bench Depth + 20% Future Draft Capital` (Industry Standard).")
            dynasty_res = compute_dynasty_power_rankings(all_team_profiles)
            ranked_dyn = sorted(dynasty_res.values(), key=lambda x: x["dynasty_score"], reverse=True)

            dyn_data = []
            for rank_idx, t in enumerate(ranked_dyn, 1):
                rid = t["roster_id"]
                is_me = (rid == user_roster["roster_id"])
                dyn_data.append({
                    "Rank": f"{'👉 ' if is_me else ''}#{rank_idx}",
                    "Manager / Team": t["manager_name"],
                    "Dynasty Score": f"{t['dynasty_score']:.1f} / 100",
                    "Starters Val (50%)": f"{t['starters_val']:,.0f} pts",
                    "Bench Val (30%)": f"{t['bench_val']:,.0f} pts",
                    "Picks Capital (20%)": f"{t['picks_val']:,.0f} pts",
                    "Competitive Tier": t["status"].split("(")[0].strip() if t.get("status") else "Active",
                })

            df_dyn = pd.DataFrame(dyn_data)
            st.dataframe(df_dyn, hide_index=True, use_container_width=True)

            with st.expander("🔍 View Complete Team Roster & Pick Breakdown"):
                inspect_mgr = st.selectbox("Select Team to Inspect:", [t["manager_name"] for t in ranked_dyn])
                selected_prof = next(p for p in all_team_profiles if p["manager_name"] == inspect_mgr)

                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f"**Starting Assets ({selected_prof['starter_value']:,.0f} pts):**")
                    for p in selected_prof["starters"]:
                        st.markdown(f"- `{p['name']}` ({p.get('position', '')}) — **{p.get('market_value', 0):,.0f} pts**")
                with col_b:
                    st.markdown(f"**Top Bench Assets ({selected_prof['bench_value']:,.0f} pts):**")
                    for p in selected_prof["bench"][:8]:
                        st.markdown(f"- `{p['name']}` ({p.get('position', '')}) — **{p.get('market_value', 0):,.0f} pts**")
                    if is_dynasty and selected_prof["picks"]:
                        st.markdown(f"**Future Draft Capital ({selected_prof['picks_value']:,.0f} pts):**")
                        for pick in selected_prof["picks"][:6]:
                            st.markdown(f"- 🎟️ {pick['name']} — **{pick.get('market_value', 0):,.0f} pts**")


    # =========================================================================
    # TAB 5: TRADE CENTER & TARGETED FINDER
    # =========================================================================
    with tab_trades:
        st.subheader("🤝 Trade Center & Targeted Acquisition Engine")

        def render_trade_proposal_card(idx: int, prop: dict, show_chat_message: bool = True):
            arch = prop.get("archetype") or prop.get("structure") or "🤝 Balanced Trade Proposal"
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

            give_html = ", ".join(f"<code>{a.get('name', 'Asset')}</code> ({a.get('market_value', 0):,.0f} pts)" for a in gives)
            recv_html = ", ".join(f"<code>{a.get('name', 'Asset')}</code> ({a.get('market_value', 0):,.0f} pts)" for a in recvs)

            st.markdown(
                f"<div class='card-container card-highlight'>"
                f"<h4>Proposal #{idx}: {arch} with {partner}</h4>"
                f"<b>You Send:</b> {give_html} (Raw: {give_raw:,.0f} pts | Model 3 Stud Adj: {eff_give:,.0f} pts)<br/>"
                f"<b>You Receive:</b> {recv_html} (Raw: {recv_raw:,.0f} pts | Model 3: {eff_recv:,.0f} pts)<br/>"
                f"<b>Net Differential:</b> <b>{diff_sign}{net_diff:,.0f} pts</b> ({status_label})<br/>"
                f"<b>Rationale:</b> {why}"
                f"</div>",
                unsafe_allow_html=True,
            )
            if show_chat_message:
                send_names = " + ".join(a.get("name", "Asset") for a in gives)
                recv_names = " + ".join(a.get("name", "Asset") for a in recvs)
                chat_msg = f"Hey {partner}, would you consider {send_names} for {recv_names}? Evaluated as fair on consensus market values."
                st.code(chat_msg, language="markdown")

        trade_view = st.radio(
            "Trade Mode:",
            ["🎯 Targeted Asset Finder (Buy or Sell Specific Assets)", "🌐 League-Wide Trade Scanner"],
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
                                    st.success(f"Generated {len(proposals)} Model 3 trade proposals with **{owner_prof['manager_name']}**:")
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
            st.markdown("### 🌐 Automated League-Wide Win-Win Trade Scanner")
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
    # TAB 6: MARKET RANKINGS & DATABASE (NEW TAB)
    # =========================================================================
    with tab_market:
        st.subheader("🔍 Market Rankings & Player Database")
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
            ecr = p_data.get("rank_ecr", 999.0)
            ktc_v = p_data.get("ktc_val")
            fc_v = p_data.get("fc_val")
            dp_v = p_data.get("dp_val")

            if pos_mkt != "ALL" and pos != pos_mkt:
                continue
            if search_mkt and (search_mkt.lower() not in pname.lower() and search_mkt.lower() not in team.lower()):
                continue

            pos_ecr_str = f"{pos}{int(ecr)}" if (ecr and ecr < 900) else "—"

            market_rows.append({
                "Avatar": get_player_avatar_url(pid, pos, team),
                "Player": pname,
                "Pos": pos,
                "NFL Team": team,
                "Consensus Value": f"{val:,.0f} pts",
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

            df_market = pd.DataFrame(market_rows[:150]).drop(columns=["_val"])
            st.dataframe(
                df_market[["Rank", "Avatar", "Player", "Pos", "NFL Team", "Consensus Value", "Pos ECR", "KeepTradeCut", "FantasyCalc", "DynastyProcess"]],
                column_config={"Avatar": st.column_config.ImageColumn("", width="small")},
                hide_index=True,
                use_container_width=True,
            )
            st.caption(f"Showing top {min(len(market_rows), 150)} of {len(market_rows)} matching assets.")
        else:
            st.info("No players matched the filter criteria.")


    # =========================================================================
    # TAB 7: MULTI-LEAGUE PORTFOLIO & PLAYER EXPOSURE
    # =========================================================================
    with tab_portfolio:
        st.subheader("🌐 Multi-League Portfolio & Player Exposure")
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
                df_exp[["Avatar", "Player", "Pos", "NFL Team", "Shares", "Exposure", "Pos ECR", "Consensus Value", "Leagues Owned"]],
                column_config={"Avatar": st.column_config.ImageColumn("", width="small")},
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.info("No players matching the portfolio filter criteria.")
