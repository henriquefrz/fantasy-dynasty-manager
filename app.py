"""
Fantasy Dynasty Manager — Interactive Web Application
Built with Streamlit for desktop (MacBook) and mobile (iPhone) use.
Provides:
  - Tab 0: 🏠 Franchise Hub (Executive Overview, Longevity & Roll of Honor, Starting Lineup)
  - Tab 1: ⚡ Matchups & Start/Sit (Active vs Optimal, Injury Alerts, FA Streaming)
  - Tab 2: 📊 Power Rankings & Playoff Odds (1,000-Run Monte Carlo + Dynasty 50/30/20)
  - Tab 3: 🌊 Add/Drops & Waivers (IR Slots, Taxi Swaps, Starter Displacements, Handcuffs)
  - Tab 4: 🤝 Trade Center & Targeted Finder (Targeted Buy/Sell + League Scanner)
  - Tab 5: 🌐 Multi-League Portfolio & Player Exposure (Cross-League Shares & Risk)
"""

import copy
from datetime import datetime
import pandas as pd
import streamlit as st

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
from src.matching import match_players_by_sleeper_id
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
st.set_page_config(
    page_title="Fantasy Dynasty Manager",
    page_icon="🏈",
    layout="wide",
    initial_sidebar_state="auto",
)

st.markdown(
    """
    <style>
    /* Global Container & Typography */
    .block-container {
        padding-top: 1.25rem;
        padding-bottom: 2.5rem;
        padding-left: 1.25rem;
        padding-right: 1.25rem;
        max-width: 1400px;
    }

    /* Positional Badges */
    .badge-pos {
        display: inline-block;
        padding: 3px 9px;
        border-radius: 6px;
        font-weight: 700;
        font-size: 0.75rem;
        color: #fff;
        margin-right: 6px;
        letter-spacing: 0.03em;
    }
    .badge-qb { background-color: #ef4444; }
    .badge-rb { background-color: #06b6d4; }
    .badge-wr { background-color: #3b82f6; }
    .badge-te { background-color: #f59e0b; }
    .badge-k  { background-color: #8b5cf6; }
    .badge-def{ background-color: #64748b; }
    .badge-pick{ background-color: #10b981; }

    /* Modern Glassmorphic Cards */
    .card-container {
        border-radius: 12px;
        padding: 16px 18px;
        margin-bottom: 14px;
        border: 1px solid rgba(255, 255, 255, 0.08);
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.6) 0%, rgba(15, 23, 42, 0.75) 100%);
        backdrop-filter: blur(8px);
        box-shadow: 0 4px 16px -2px rgba(0, 0, 0, 0.4);
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    }
    .card-container:hover {
        border-color: rgba(255, 255, 255, 0.14);
    }
    .card-highlight {
        border-left: 4px solid #38bdf8;
        box-shadow: -3px 0 14px -2px rgba(56, 189, 248, 0.3);
    }
    .card-alert {
        border-left: 4px solid #f59e0b;
        background: linear-gradient(135deg, rgba(245, 158, 11, 0.12) 0%, rgba(15, 23, 42, 0.75) 100%);
        box-shadow: -3px 0 14px -2px rgba(245, 158, 11, 0.25);
    }
    .card-success {
        border-left: 4px solid #10b981;
        background: linear-gradient(135deg, rgba(16, 185, 129, 0.12) 0%, rgba(15, 23, 42, 0.75) 100%);
        box-shadow: -3px 0 14px -2px rgba(16, 185, 129, 0.25);
    }

    /* Polish Streamlit Native Metrics */
    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.55) 0%, rgba(15, 23, 42, 0.7) 100%);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 12px 16px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.45rem !important;
        font-weight: 800 !important;
        letter-spacing: -0.02em;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.8rem !important;
        font-weight: 600 !important;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        color: #94a3b8 !important;
    }

    /* Swipeable Horizontal Tabs for Mobile & Web */
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
        font-size: 0.9rem !important;
        font-weight: 600 !important;
        padding: 8px 16px !important;
        border-radius: 8px !important;
        min-height: 44px !important; /* Touch-friendly standard */
    }

    /* Interactive DataFrames & Tables */
    div[data-testid="stDataFrame"] {
        border-radius: 12px;
        overflow: hidden;
        border: 1px solid rgba(255, 255, 255, 0.08);
    }

    /* Mobile Responsive Optimizations */
    @media (max-width: 768px) {
        .block-container {
            padding-left: 0.6rem !important;
            padding-right: 0.6rem !important;
            padding-top: 0.75rem !important;
        }
        div[data-testid="column"] {
            min-width: 140px;
        }
        .card-container {
            padding: 12px 14px !important;
            margin-bottom: 10px !important;
        }
        div[data-testid="stMetricValue"] {
            font-size: 1.25rem !important;
        }
        div[data-baseweb="tab"] {
            font-size: 0.82rem !important;
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
def fetch_market_database(_cache_version="v4_kicker_dst_fix"):
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
        "dynasty_sf": base_dynasty_sf,
        "dynasty_1qb": base_dynasty_1qb,
        "redraft": base_redraft,
        "picks_bundle_sf": picks_bundle_sf,
        "picks_bundle_1qb": picks_bundle_1qb,
        "freshness": freshness_info,
    }


@st.cache_data(ttl=900, show_spinner=False)
def fetch_user_and_leagues(username):
    user = get_user(username)
    nfl_state = get_nfl_state()
    season = nfl_state.get("season", "2026")
    week = nfl_state.get("week", 1)
    leagues = get_user_leagues(user["user_id"], season)
    return user, season, week, leagues


@st.cache_data(ttl=600, show_spinner=False)
def fetch_league_bundle(league_id, season, week):
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

            league_summaries.append({
                "league_name": lname,
                "record": f"{w}-{l}" + (f"-{t}" if t > 0 else ""),
                "fpts": fpts,
                "fpts_against": fpts_against,
                "players_count": len(my_pids),
            })

            for pid in my_pids:
                p_obj = _players_db.get(pid, {})
                p_name = p_obj.get("full_name") or pid
                pos = p_obj.get("position") or "UTIL"
                nfl_team = p_obj.get("team") or "FA"
                val_data = _primary_lookup.get(pid, {})
                m_val = val_data.get("market_value", 0.0)

                if pid not in player_exposure:
                    player_exposure[pid] = {
                        "player_id": pid,
                        "name": p_name,
                        "position": pos,
                        "team": nfl_team,
                        "market_value": m_val,
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
        rows.append({
            "Player": d["name"],
            "Pos": d["position"],
            "NFL Team": d["team"],
            "Shares": f"{c} / {total_leagues}",
            "Share Count": c,
            "Exposure": f"{pct:.0f}%",
            "Exposure %": pct,
            "Consensus Value": d["market_value"],
            "Leagues Owned": ", ".join(d["leagues"]),
        })

    rows.sort(key=lambda x: (x["Share Count"], x["Consensus Value"]), reverse=True)
    return rows, total_leagues, league_summaries


# -----------------------------------------------------------------------------
# App Initialization & Sidebar
# -----------------------------------------------------------------------------
st.sidebar.markdown("### 🏈 Fantasy Dynasty Manager")
input_username = st.sidebar.text_input(
    "Sleeper Username",
    value="henriquefrz",
    help="Enter any Sleeper username to analyze their leagues, rankings, and roster portfolio."
).strip()
active_user_handle = input_username if input_username else "henriquefrz"

with st.spinner(f"Connecting to Sleeper (@{active_user_handle}) & Market Feeds..."):
    market_db = fetch_market_database(_cache_version="v4_kicker_dst_fix")
    try:
        user, active_season, active_week, leagues = fetch_user_and_leagues(active_user_handle)
    except Exception as e:
        st.sidebar.error(f"User @{active_user_handle} not found. Reverting to @henriquefrz.")
        user, active_season, active_week, leagues = fetch_user_and_leagues("henriquefrz")

st.sidebar.caption(f"Connected: **@{user['username']}** | Season: **{active_season}** (Wk {active_week})")


# Sidebar: League Selection
# Put leagues with rosters first, default to Dinastia do Povo if present
def get_league_sort_key(lg):
    name = lg.get("name", "")
    if "Dinastia do Povo" in name:
        return 0
    if "Samonte Dynasty" in name:
        return 1
    if "Diferenciados" in name:
        return 2
    if lg.get("settings", {}).get("type") == 0:  # Redraft pre-draft
        return 99
    return 10

sorted_leagues = sorted(leagues, key=get_league_sort_key)
league_names = [l["name"] for l in sorted_leagues]
selected_league_name = st.sidebar.selectbox("Select League", league_names, index=0)
selected_league = next(l for l in sorted_leagues if l["name"] == selected_league_name)

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

# Sidebar: Data Freshness Status
st.sidebar.markdown("---")
with st.sidebar.expander("🕒 Market Data Freshness", expanded=False):
    fresh = market_db["freshness"]
    st.markdown(f"**FantasyCalc:** `{fresh['fantasycalc']['status']}` ({fresh['fantasycalc']['date']})")
    st.markdown(f"**KeepTradeCut:** `{fresh['ktc']['status']}` ({fresh['ktc']['date']})")
    st.markdown(f"**DynastyProcess:** `{fresh['dynastyprocess']['status']}` (`{fresh['dynastyprocess']['date']}`)")
    st.markdown(f"**FantasyPros ECR:** `{fresh['fantasypros']['status']}` (`{fresh['fantasypros']['date']}`)")
    st.caption("KTC & FantasyCalc update real-time. DynastyProcess & FP update weekly.")

if st.sidebar.button("🔄 Refresh Live Data", use_container_width=True):
    st.cache_data.clear()
    st.rerun()


# -----------------------------------------------------------------------------
# League Data & Valuation Application
# -----------------------------------------------------------------------------
league_id = selected_league["league_id"]
league_data = fetch_league_bundle(league_id, active_season, active_week)
rosters = league_data["rosters"]
users = league_data["users"]
schedule = league_data["schedule"]
traded_picks = league_data["traded_picks"]
weekly_projections = league_data["projections"]
players = market_db["players"]

user_roster = get_user_roster(rosters, user["user_id"])
if not user_roster or not user_roster.get("players"):
    st.warning("⚠️ This league is currently in pre-draft status and has not drafted rosters yet. Please select an active drafted league from the sidebar.")
    st.stop()

# Classify league settings
ltype = classify_league(selected_league, rosters)
roster_pos = selected_league.get("roster_positions", [])
is_superflex = "SUPER_FLEX" in roster_pos or roster_pos.count("QB") >= 2
is_dynasty = ltype["type"] != "redraft"
scoring = selected_league.get("scoring_settings", {})
tep_bonus = scoring.get("bonus_rec_te", 0.0) or scoring.get("te_bonus", 0.0)

# Build active lookup for chosen valuation mode
redraft_lookup = market_db["redraft"]
if is_dynasty:
    base_lookup = market_db["dynasty_sf"] if is_superflex else market_db["dynasty_1qb"]
    primary_lookup = copy.deepcopy(base_lookup)
    apply_valuation_mode(primary_lookup, mode=selected_mode, bonus_rec_te=tep_bonus)
    alt_lookup = redraft_lookup
else:
    base_lookup = redraft_lookup
    primary_lookup = copy.deepcopy(base_lookup)
    alt_lookup = None

# Build pick lookups for chosen valuation mode
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

# Header Dashboard Banner
st.markdown(f"## {selected_league_name}")
format_badge = f"{'Dynasty' if is_dynasty else 'Redraft'} • {'Superflex' if is_superflex else '1QB'} • {len(rosters)} Teams"
if tep_bonus > 0:
    format_badge += f" • {tep_bonus} TEP"
st.caption(f"{format_badge} | Engine: **{VALUATION_MODES[selected_mode]}**")

# Top Metric Pills
col_m1, col_m2, col_m3, col_m4 = st.columns(4)
with col_m1:
    wins = user_roster.get("settings", {}).get("wins", 0)
    losses = user_roster.get("settings", {}).get("losses", 0)
    st.metric("Team Record", f"{wins} - {losses}", help="Current regular season record")
with col_m2:
    status_label = team_status.split("(")[0].strip() if team_status else "Active"
    st.metric("Competitive Status", status_label, help=team_status)
with col_m3:
    if is_dynasty and user_profile:
        dyn_rank_str = f"Rank #{dynasty_pos} of {dynasty_total}" if dynasty_pos else "Pre-Draft"
        st.metric("Dynasty Total Value", f"{user_profile['total_value']:,.0f} pts", dyn_rank_str)
    else:
        red_rank_str = f"#{redraft_pos} of {redraft_total}" if redraft_pos else "Pre-Draft"
        st.metric("Redraft Rank", red_rank_str)
with col_m4:
    if is_dynasty and user_profile:
        st.metric("Starting Lineup Value", f"{user_profile['starter_value']:,.0f} pts", f"Bench: {user_profile['bench_value']:,.0f} pts")
    else:
        fpts = user_roster.get("settings", {}).get("fpts", 0.0)
        st.metric("Points Scored", f"{fpts:,.1f} pts")

st.markdown("---")

# Main Multi-Tab Interface
tab_hub, tab_start_sit, tab_power, tab_waivers, tab_trades, tab_portfolio = st.tabs([
    "🏠 Franchise Hub",
    "⚡ Matchups & Start/Sit",
    "📊 Power Rankings & Playoff Odds",
    "🌊 Add/Drops & Waivers",
    "🤝 Trade Center & Targeted Finder",
    "🌐 Multi-League Portfolio",
])


# =============================================================================
# TAB 0: FRANCHISE HUB
# =============================================================================
with tab_hub:
    st.subheader(f"🏠 Franchise Executive Dashboard: {selected_league_name}")

    settings = user_roster.get("settings", {})
    wins = settings.get("wins", 0)
    losses = settings.get("losses", 0)
    ties = settings.get("ties", 0)
    total_games = wins + losses + ties
    win_pct = (wins / total_games * 100.0) if total_games > 0 else 0.0
    fpts = settings.get("fpts", 0) + (settings.get("fpts_decimal", 0) / 100.0)
    fpts_against = settings.get("fpts_against", 0) + (settings.get("fpts_against_decimal", 0) / 100.0)
    diff = fpts - fpts_against

    # 1. Top Executive Banner
    col_h1, col_h2, col_h3 = st.columns([1.2, 1, 1])
    with col_h1:
        cat_badge = "🏆 Championship Contender" if team_cat == "win" else ("🌱 Rebuilder (Draft Capital Mode)" if team_cat == "rebuild" else "⚖️ Frisky / Competitive Depth")
        st.markdown(
            f"<div class='card-container card-highlight'>"
            f"<h4>Franchise Trajectory</h4>"
            f"<b>Strategic Posture:</b> {cat_badge}<br/>"
            f"<b>Status Classification:</b> {team_status}<br/>"
            f"<b>League Format:</b> {'Dynasty' if is_dynasty else 'Redraft'} • {'Superflex' if is_superflex else '1QB'} ({len(rosters)} Teams)"
            f"</div>",
            unsafe_allow_html=True,
        )

    with col_h2:
        st.markdown(
            f"<div class='card-container'>"
            f"<h4>Standings & Record</h4>"
            f"<b>Record:</b> {wins}W - {losses}L{f' - {ties}T' if ties > 0 else ''} (<b>{win_pct:.1f}%</b>)<br/>"
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
                f"<h4>Asset Capital</h4>"
                f"<b>Dynasty Total:</b> {user_profile['total_value']:,.0f} pts (<b>{dyn_pos_txt}</b> of {dynasty_total})<br/>"
                f"<b>Starters:</b> {user_profile['starter_value']:,.0f} pts | <b>Bench:</b> {user_profile['bench_value']:,.0f} pts<br/>"
                f"<b>Future Picks:</b> {user_profile['picks_value']:,.0f} pts ({len(user_profile.get('picks', []))} picks)"
                f"</div>",
                unsafe_allow_html=True,
            )
        else:
            red_pos_txt = f"#{redraft_pos}" if redraft_pos else "Pre-Draft"
            st.markdown(
                f"<div class='card-container'>"
                f"<h4>Contender Strength</h4>"
                f"<b>Redraft Rank:</b> {red_pos_txt} of {redraft_total}<br/>"
                f"<b>Active Starters:</b> {len(user_roster.get('starters') or [])} players<br/>"
                f"<b>Bench Depth:</b> {len(user_roster.get('players') or []) - len(user_roster.get('starters') or [])} players"
                f"</div>",
                unsafe_allow_html=True,
            )

    # 2. League Longevity & Franchise Honors
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
            st.metric("Championship Rings", f"🏆 {titles_cnt} Titles", f"Won: {seasons_txt}")
        else:
            st.metric("Championship Rings", "0 Titles", "Chasing 1st Ring", delta_color="off")
    with col_lh3:
        if history["is_migrated"]:
            st.metric("League Heritage", "Migrated League", history.get("notes", ""))
        else:
            st.metric("Platform History", "Native Sleeper", f"{history['total_seasons']} yrs on Sleeper")

    if history["title_seasons"]:
        st.success(f"🥇 **Championship Legacy:** You were crowned league champion in: **{', '.join(str(s) for s in history['title_seasons'])}**!")

    if history.get("champions"):
        with st.expander("📜 View Complete League Roll of Honor & Past Champions", expanded=False):
            champ_rows = []
            for ch in history["champions"]:
                is_u = ch.get("is_user") or "Henrique" in ch.get("champion", "") or "Pombos" in ch.get("champion", "")
                champ_rows.append({
                    "Season": ch.get("season"),
                    "Champion": ch.get("champion"),
                    "Record": ch.get("record", "—"),
                    "Franchise Honor": "🏆 Your Title!" if is_u else "League Champion",
                })
            st.dataframe(pd.DataFrame(champ_rows), hide_index=True, use_container_width=True)

    # 3. Starting Lineup Snapshot Table
    st.markdown("---")
    st.markdown("### 📋 Current Starting Lineup Snapshot")
    roster_players = get_roster_players(user_roster, players)
    starter_pids = set(user_roster.get("starters") or [])

    starter_rows = []
    for p in roster_players:
        pid = p.get("player_id")
        if pid not in starter_pids:
            continue
        pname = p.get("full_name") or pid
        pos = p.get("position") or "UTIL"
        nfl_team = p.get("team") or "FA"
        val_data = primary_lookup.get(pid, {})
        m_val = val_data.get("market_value", 0.0)
        ecr = val_data.get("rank_ecr", 999.0)
        age = p.get("age", "—")
        starter_rows.append({
            "Starter Slot": pos,
            "Player": pname,
            "NFL Team": nfl_team,
            "Age": age,
            "ECR Rank": f"#{ecr:.0f}" if ecr < 900 else "—",
            "Consensus Market Val": f"{m_val:,.0f} pts",
        })

    if starter_rows:
        df_start = pd.DataFrame(starter_rows)
        st.dataframe(df_start, hide_index=True, use_container_width=True)
    else:
        st.info("No active starting lineup detected.")


# =============================================================================
# TAB 1: MATCHUPS & START/SIT
# =============================================================================
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

    # Opponent Lookup from live weekly matchups
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

    # Scorecard Banner
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
                        "Slot": slot_name,
                        "Player": p.get("full_name") or pid,
                        "NFL Team": p.get("team") or "FA",
                        "Projected": f"{p_proj:.1f} pts",
                    })
                else:
                    opp_lineup_rows.append({
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
            st.dataframe(pd.DataFrame(opp_lineup_rows), hide_index=True, use_container_width=True)

    # Start/Sit Recommendations
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

    # Free Agent Streaming with Josh Allen Drop Protection
    free_agents = get_free_agents(rosters, players)
    fa_projs = {}
    for fa in free_agents:
        fpid = fa.get("player_id")
        fa_projs[fpid] = calculate_weekly_projected_points(fpid, weekly_projections.get(fpid), scoring, fa)

    combined_projs = {**proj_lookup, **fa_projs}
    streams = find_streaming_recommendations(
        user_roster=user_roster,
        roster_players=roster_players,
        free_agents=free_agents,
        projections_lookup=combined_projs,
        roster_positions=roster_pos,
        primary_lookup=primary_lookup,
        top_n=2,
    )
    if streams:
        with st.expander("🌊 Weekly Free Agent Streaming Opportunities (Stud-Protected)", expanded=False):
            st.caption("Suggests high-upside waiver streamers while strictly protecting top foundation dynasty assets from being dropped.")
            for st_item in streams:
                sp = st_item["stream_player"]
                dp = st_item["drop_player"]
                st.markdown(
                    f"• **STREAM:** `{sp.get('full_name')}` ({sp.get('position')} — **{st_item['stream_proj']:.1f} pts**) "
                    f"➔ **DROP:** `{dp.get('full_name')}` (Bench | Market Val: {st_item['drop_market_val']:,.0f} pts) "
                    f"| *Outprojects starter `{st_item['current_starter'].get('full_name')}` by +{st_item['projected_gain']:.1f} pts*"
                )


# =============================================================================
# TAB 2: POWER RANKINGS & PLAYOFF ODDS
# =============================================================================
with tab_power:
    st.subheader("📊 League Power Rankings & Playoff Odds")

    ranking_type = st.radio(
        "Choose Power Ranking Model:",
        [
            "🏆 Season Contender Power Rankings (1,000-Run Monte Carlo Simulation)",
            "🏰 Dynasty Power Rankings (Long-Term Asset Value: 50% Starters / 30% Bench / 20% Picks)",
        ],
        horizontal=True,
    )

    if "Season Contender" in ranking_type:
        playoff_start = selected_league.get("settings", {}).get("playoff_week_start", 15)
        # Compute team lineup expectations
        team_expectations = {
            r["roster_id"]: compute_team_lineup_expectation(
                roster=r,
                roster_players=all_rosters_players[r["roster_id"]],
                weekly_projections=weekly_projections,
                scoring_settings=scoring,
                roster_positions=roster_pos,
            )
            for r in rosters
            if r["roster_id"] in all_rosters_players
        }

        with st.spinner("Running 1,000 Monte Carlo Season & Playoff Simulations..."):
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
        st.info(f"🏟️ **Playoff Bracket Format:** Top **{p_count} Teams** qualify for the postseason in this league.")

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
        st.info("💡 **Dynasty Formula:** `50% Starters Value + 30% Bench Depth + 20% Future Draft Pick Capital` (KeepTradeCut & Dynasty Daddy Industry Standard).")
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

        with st.expander("🔍 View Complete Team Roster & Pick Breakdowns"):
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


# =============================================================================
# TAB 3: ADD/DROPS & WAIVERS
# =============================================================================
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
                help="Dynasty horizon optimizes for long-term player trade capital (KTC/FC/DP). Rest of Season horizon optimizes for immediate starting points, weekly utility, and playoff wins."
            )
            eval_dynasty = "Dynasty" in waiver_perspective
        else:
            waiver_perspective = "🏆 Rest of Season (Redraft)"
            eval_dynasty = False

    with col_w2:
        protection_choice = st.selectbox(
            "Drop Protection Level:",
            ["🛡️ Injured Stars Protected", "⚠️ Unrestricted (Show All Drops)"],
            help="Protects injured NFL starters (IR/DNR/PUP like Brandon Aiyuk) from being recommended as drops."
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

    # 1. IR Slot Actions
    ir_suggestions = waivers.get("ir_suggestions", [])
    if ir_suggestions:
        st.markdown("### 🚑 IR Slot Optimization")
        for ir in ir_suggestions:
            pname = ir["player"].get("full_name")
            reason = ir.get("reason", "IR Eligible")
            st.info(f"• **Move to IR:** `{pname}` ({reason}) ➔ *Frees up an active bench roster spot for a free agent add.*")

    # 2. Starting Lineup Upgrades
    starter_upgrades = waivers.get("starter_upgrades", [])
    if starter_upgrades:
        st.markdown("### ⭐ Starting Lineup Upgrades (Immediate Impact)")
        for s in starter_upgrades[:3]:
            add_p = s["add_player"]
            drop_p = s["drop_player"]
            disp_p = s.get("displaced_player")
            disp_name = (disp_p.get("full_name") or disp_p.get("player_id")) if disp_p else "Starting Slot"
            diff = s.get("market_value_gain", 0.0)
            tag = s.get("priority_tag", "STARTER")
            add_val = s.get("add_value", s.get("add_ranking", {}).get("market_value", 0.0))
            drop_val = s.get("drop_value", s.get("drop_ranking", {}).get("market_value", 0.0))

            caution_html = ""
            if s.get("is_high_value_drop"):
                caution_html = f"<div style='color: #f59e0b; font-size: 0.85rem; margin-top: 4px;'>⚠️ <b>High Trade Value Notice</b>: <code>{drop_p.get('full_name')}</code> holds {drop_val:,.0f} pts market value. Consider shopping them in the Trade Center before cutting to waivers.</div>"

            alt_info = ""
            if eval_dynasty:
                a_ros = s.get("add_alt_rank")
                d_ros = s.get("drop_alt_rank")
                if a_ros and d_ros and a_ros < 900 and d_ros < 900:
                    alt_info = f"<div style='color: #94a3b8; font-size: 0.82rem; margin-top: 2px;'>↳ <i>Rest of Season (ROS) Rank: ADD #{a_ros:.0f} vs DROP #{d_ros:.0f} (Net: {d_ros - a_ros:+.0f} ranks)</i></div>"
            else:
                a_dyn = s.get("add_alt_value")
                d_dyn = s.get("drop_alt_value")
                if a_dyn is not None and d_dyn is not None:
                    alt_info = f"<div style='color: #94a3b8; font-size: 0.82rem; margin-top: 2px;'>↳ <i>Dynasty Capital Impact: ADD {a_dyn:,.0f} pts vs DROP {d_dyn:,.0f} pts (Net: {a_dyn - d_dyn:+,.0f} pts)</i></div>"

            st.markdown(
                f"<div class='card-container card-success'>"
                f"<b>{tag}</b>: "
                f"<b>ADD:</b> <code>{add_p.get('full_name')}</code> ({add_p.get('position')} — {add_p.get('team')}, Val: {add_val:,.0f} pts)<br/>"
                f"<b>DROP:</b> <code>{drop_p.get('full_name')}</code> (Bench | {drop_p.get('position')}, Val: {drop_val:,.0f} pts)<br/>"
                f"↳ <i>Displaces <b>{disp_name}</b> in starting lineup (Net Value Gain: <b>+{diff:,.0f} pts</b>)</i>"
                f"{alt_info}"
                f"{caution_html}"
                f"</div>",
                unsafe_allow_html=True,
            )

    # 3. High-Value Bench Upgrades
    cross_upgrades = waivers.get("cross_pos_upgrades", [])
    if cross_upgrades:
        st.markdown("### 📈 Top Bench Upgrades")
        for s in cross_upgrades[:3]:
            add_p = s["add_player"]
            drop_p = s["drop_player"]
            diff = s.get("market_value_gain", 0.0)
            add_val = s.get("add_value", s.get("add_ranking", {}).get("market_value", 0.0))
            drop_val = s.get("drop_value", s.get("drop_ranking", {}).get("market_value", 0.0))

            caution_str = ""
            if s.get("is_high_value_drop"):
                caution_str = f" <span style='color: #f59e0b;'>[⚠️ High Trade Value: {drop_val:,.0f} pts — consider trading first]</span>"

            alt_str = ""
            if eval_dynasty:
                a_ros = s.get("add_alt_rank")
                d_ros = s.get("drop_alt_rank")
                if a_ros and d_ros and a_ros < 900 and d_ros < 900:
                    alt_str = f" <i>(ROS: Add #{a_ros:.0f} vs Drop #{d_ros:.0f})</i>"
            else:
                a_dyn = s.get("add_alt_value")
                d_dyn = s.get("drop_alt_value")
                if a_dyn is not None and d_dyn is not None:
                    alt_str = f" <i>(Dynasty: {a_dyn - d_dyn:+,.0f} pts)</i>"

            st.markdown(
                f"- **ADD:** `{add_p.get('full_name')}` ({add_p.get('position')}, Val: {add_val:,.0f} pts) "
                f"➔ **DROP:** `{drop_p.get('full_name')}` ({drop_p.get('position')}, Val: {drop_val:,.0f} pts) "
                f"[Net: **+{diff:,.0f} pts**]{alt_str}{caution_str}",
                unsafe_allow_html=True,
            )

    if not starter_upgrades and not cross_upgrades:
        if protect_injured:
            st.info(
                "🛡️ **Roster Depth Notice**: All players on your active bench are established starters or protected injured assets. "
                "No cuts are recommended under current settings. To explore pure mathematical drops regardless of player status, "
                "switch Drop Protection to **Unrestricted**, or package surplus depth into 2-for-1 trades in the **Trade Center**."
            )
        else:
            st.info(
                "🛡️ **No Beneficial Upgrades Found**: No available free agents provide a net improvement over your current bench under this horizon."
            )

    # 4. Interactive Free Agent Market Explorer
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

        fa_rows.append({
            "Player": pname,
            "Pos": pos,
            "NFL Team": fa.get("team") or "FA",
            "Consensus Value": val,
            "ECR Rank": f"#{ecr:.0f}" if ecr < 999 else "—",
            "FantasyCalc": f"{fc_v:,.0f}" if fc_v is not None else "—",
            "KeepTradeCut": f"{ktc_v:,.0f}" if ktc_v is not None else "—",
            "DynastyProcess": f"{dp_v:,.0f}" if dp_v is not None else "—",
        })

    fa_rows.sort(key=lambda x: x["Consensus Value"], reverse=True)
    df_fa = pd.DataFrame(fa_rows[:50])
    st.dataframe(df_fa, hide_index=True, use_container_width=True)


# =============================================================================
# TAB 4: TRADE CENTER & TARGETED FINDER
# =============================================================================
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
            tol_val = 0.10 if "Strict" in tolerance_label else (0.20 if "Moderate" in tolerance_label else 0.30)

        if "Buy" in action_type:
            # Build list of assets across league opponents
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
            # Sell Mode
            user_assets = []
            for p in user_profile["starters"] + user_profile["bench"]:
                if p.get("market_value", 0) > 1000:
                    user_assets.append((f"{p['name']} ({p.get('position', '')}) — {p.get('market_value', 0):,.0f} pts", p["name"]))
            for pick in user_profile.get("picks", []):
                user_assets.append((f"{pick['name']} — {pick.get('market_value', 0):,.0f} pts", pick["name"]))

            user_assets.sort(key=lambda x: x[0])
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
        # League-Wide Scanner
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


# =============================================================================
# TAB 5: MULTI-LEAGUE PORTFOLIO & PLAYER EXPOSURE
# =============================================================================
with tab_portfolio:
    st.subheader("🌐 Multi-League Portfolio & Player Exposure")
    st.caption("Cross-analyzes all your Sleeper leagues to measure player shares, concentration risk, and your foundation franchise assets.")

    all_l_ids = [l["league_id"] for l in leagues]
    all_l_names = [l["name"] for l in leagues]

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
        df_exp["Exposure %"] = df_exp["Exposure %"].apply(lambda v: f"{v:.1f}%")
        st.dataframe(
            df_exp.drop(columns=["Share Count"]),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.info("No players matching the portfolio filter criteria.")
