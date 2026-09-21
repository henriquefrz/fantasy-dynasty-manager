"""
Converted from scratch/test_tep_contamination_fix.py and
scratch/test_fp_ros_failure_scenarios.py.
"""
import json
import os
import time
from unittest import mock

import pytest

import src.market_data as market_data
from src.market_data import apply_ktc_te_premium, apply_valuation_mode, compute_market_rank_divergence


# ---------------------------------------------------------------------------
# TEP contamination fix (bdb12b6): apply_valuation_mode / apply_ktc_te_premium
# used to mutate the lookup dict passed in and return the same object, so
# callers sharing one base lookup across many leagues (the portal loop, the
# league workspace, scripts/weekly_automation.py) could leak one league's TE
# Premium into another's values.
# ---------------------------------------------------------------------------

def test_shared_base_lookup_is_not_mutated_by_a_later_leagues_tep(te_premium_lookup, te_ktc_raw, te_player_ids_raw):
    """
    Mirrors the real-world manifestation of the bug: app.py computes a
    cross-league `primary_lookup` ONCE, before looping over leagues. If the
    shared functions mutated in place, any league processed later in the
    loop (with its own TEP) would silently corrupt that already-computed
    primary_lookup, since it was the same object.
    """
    base = te_premium_lookup
    original_value = base["te1"]["market_value"]

    # Computed once, before any league-specific TEP is applied - mirrors
    # app.py's cross-league primary_lookup.
    primary_lookup = apply_valuation_mode(base, mode="equal")
    primary_value_right_after_compute = primary_lookup["te1"]["market_value"]

    # A different league elsewhere in the loop, with its own TEP, reusing
    # the SAME base lookup object.
    league_lookup = apply_valuation_mode(base, mode="equal")
    league_lookup = apply_ktc_te_premium(league_lookup, 1.0, te_ktc_raw, te_player_ids_raw, is_superflex=True)

    assert league_lookup["te1"]["market_value"] != primary_value_right_after_compute, "sanity check: TEP should actually change this TE's value"
    assert primary_lookup["te1"]["market_value"] == primary_value_right_after_compute == original_value, (
        "primary_lookup must be left untouched by a later league's TEP"
    )
    assert base["te1"]["market_value"] == original_value, "the shared base lookup itself must never be mutated"


def test_apply_valuation_mode_returns_an_independent_copy(te_premium_lookup):
    result = apply_valuation_mode(te_premium_lookup, mode="equal")
    assert result is not te_premium_lookup
    assert result["te1"] is not te_premium_lookup["te1"]


def test_apply_ktc_te_premium_returns_an_independent_copy(te_premium_lookup, te_ktc_raw, te_player_ids_raw):
    result = apply_ktc_te_premium(te_premium_lookup, 1.0, te_ktc_raw, te_player_ids_raw, is_superflex=True)
    assert result is not te_premium_lookup
    assert result["te1"] is not te_premium_lookup["te1"]


# ---------------------------------------------------------------------------
# FantasyPros ROS scraper failure scenarios: what get_fp_ros_rankings_raw()
# actually does (not just what the code appears to do) on network failure,
# with and without a local cache to fall back to.
# ---------------------------------------------------------------------------

@pytest.fixture
def isolated_fp_ros_cache(tmp_path, monkeypatch):
    """Redirects CSV_CACHE_DIR to an empty temp dir for the duration of the test."""
    monkeypatch.setattr(market_data, "CSV_CACHE_DIR", str(tmp_path))
    return tmp_path


def _write_fp_ros_cache(cache_dir, rows, scraped_at="2026-01-01T00:00:00+00:00", age_seconds=0):
    cache_path = os.path.join(cache_dir, "fp_ros_ppr_latest.json")
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump({"scraped_at": scraped_at, "rows": rows}, f)
    if age_seconds:
        old_time = time.time() - age_seconds
        os.utime(cache_path, (old_time, old_time))
    return cache_path


def test_network_failure_falls_back_to_stale_local_cache(isolated_fp_ros_cache):
    # Aged past FP_ROS_CACHE_TTL_SECONDS so the fresh-cache shortcut doesn't
    # short-circuit before the (failing) network call is even attempted.
    _write_fp_ros_cache(
        isolated_fp_ros_cache,
        rows=[{"id": "1", "player": "Test Player"}],
        age_seconds=market_data.FP_ROS_CACHE_TTL_SECONDS + 3600,
    )

    with mock.patch("src.market_data.requests.get", side_effect=ConnectionError("simulated FantasyPros/GitHub outage")):
        rows = market_data.get_fp_ros_rankings_raw()

    assert rows == [{"id": "1", "player": "Test Player"}], "expected fallback to the stale-but-valid local cache, not an empty result"


def test_network_failure_with_no_cache_returns_empty_list_not_a_crash(isolated_fp_ros_cache):
    with mock.patch("src.market_data.requests.get", side_effect=ConnectionError("simulated total outage, no prior cache")):
        rows = market_data.get_fp_ros_rankings_raw()

    assert rows == [], "worst case (no network, no cache) must degrade to an empty list, never raise"


def test_market_data_freshness_monitors_the_fp_ros_source():
    """
    get_market_data_freshness must accept a parameter for the FantasyPros
    ROS source, so a scrape that silently stops updating for days can be
    flagged even though the fetch itself keeps returning HTTP 200.
    """
    import inspect
    params = list(inspect.signature(market_data.get_market_data_freshness).parameters)
    assert any("ros" in p.lower() for p in params), "get_market_data_freshness must monitor the FantasyPros ROS source for staleness"


# ---------------------------------------------------------------------------
# Market Differential (rank-based crowd-vs-expert divergence).
#
# Validated against real data this session: raw VALUE-based divergence
# explodes for low-value players (near-zero DynastyProcess denominators) and
# carries a strong positional bias (QB/TE medians of +76%/+88% vs RB/WR's
# +33%/+49%). Rank-based divergence - re-ranking each of the 3 sources within
# the INTERSECTION of players they all cover, then diffing DP's aligned rank
# against the market's - has neither problem and needs no minimum-value floor.
# ---------------------------------------------------------------------------

def _synthetic_rank_divergence_lookup():
    """
    10 valid candidates (p1-p10) plus 2 that must be excluded: p11 (a K,
    excluded regardless of having valid ranks) and p12 (a WR missing
    ktc_rank_native, so it's outside the fc/ktc/dp intersection).

    p1-p7 and p10 have fc_rank_native == ktc_rank_native (so
    rank_market_avg == that shared value) and a dp_rank_native that, once
    re-ranked among just these 10 players, lands close to the market
    average - a deliberately unremarkable middle of the pack.

    p8's dp_rank_native (999) is far worse than its market rank (8) - once
    aligned, the single biggest "Buy Low" case (DP undervalues it far more
    than anyone else). p9's dp_rank_native (0.1) is far better than its
    market rank (9) - the single biggest "Sell High" case (the market is
    far more excited about it than DP is).
    """
    lookup = {}
    for i in range(1, 8):
        lookup[f"p{i}"] = {"position": "WR", "fc_rank_native": i, "ktc_rank_native": i, "dp_rank_native": float(i)}
    lookup["p8"] = {"position": "RB", "fc_rank_native": 8, "ktc_rank_native": 8, "dp_rank_native": 999.0}
    lookup["p9"] = {"position": "TE", "fc_rank_native": 9, "ktc_rank_native": 9, "dp_rank_native": 0.1}
    lookup["p10"] = {"position": "QB", "fc_rank_native": 10, "ktc_rank_native": 10, "dp_rank_native": 10.0}
    lookup["p11"] = {"position": "K", "fc_rank_native": 1, "ktc_rank_native": 1, "dp_rank_native": 1.0}
    lookup["p12"] = {"position": "WR", "fc_rank_native": 5, "ktc_rank_native": None, "dp_rank_native": 5.0}
    return lookup


def test_rank_divergence_excludes_kickers_and_incomplete_players():
    lookup = _synthetic_rank_divergence_lookup()
    info = compute_market_rank_divergence(lookup)

    assert info["n"] == 10, "the K (p11) and the player missing ktc_rank_native (p12) must not enter the intersection"
    assert "rank_diff" not in lookup["p11"], "kickers must be excluded from the rank divergence entirely"
    assert "rank_diff" not in lookup["p12"], "a player missing a native rank from any of the 3 sources must be excluded"


def test_rank_diff_computed_correctly_after_aligning_within_the_intersection():
    lookup = _synthetic_rank_divergence_lookup()
    compute_market_rank_divergence(lookup)

    # p1-p7: fc/ktc/dp are already 1..7 in lockstep, so re-ranking within the
    # 10-player intersection just shifts dp's aligned rank by +1 relative to
    # the unchanged market average of i (p9's dp=0.1 slots in ahead of
    # everyone) - a small, consistent +1, nowhere near either tail.
    for i in range(1, 8):
        assert lookup[f"p{i}"]["rank_diff"] == pytest.approx(1.0)
        assert lookup[f"p{i}"]["market_signal"] is None

    # p8: market rank 8, but dp_rank_native (999) is the worst of all 10 -
    # aligned dp rank 10, vs. a market average of 8 -> rank_diff = +2, the
    # single largest positive value -> the "Buy Low" case (DP is far more
    # bearish than the market).
    assert lookup["p8"]["rank_diff"] == pytest.approx(2.0)
    assert lookup["p8"]["market_signal"] == "buy_low"

    # p9: market rank 9, but dp_rank_native (0.1) is the best of all 10 -
    # aligned dp rank 1, vs. a market average of 9 -> rank_diff = -8, the
    # single most negative value -> a "Sell High" case (DP is far more
    # bullish than the market).
    assert lookup["p9"]["rank_diff"] == pytest.approx(-8.0)
    assert lookup["p9"]["market_signal"] == "sell_high"

    # p10: market rank 10 (the worst market rank of the 10), but dp's aligned
    # rank is 9 (better than its own market rank, since p9's dp=0.1 and
    # p8's dp=999 both shuffle the dp ordering) -> rank_diff = -1.
    assert lookup["p10"]["rank_diff"] == pytest.approx(-1.0)
    assert lookup["p10"]["market_signal"] == "sell_high"  # ties AT the p10 threshold count as significant


def test_thresholds_are_the_actual_p10_p90_of_this_distribution_not_hardcoded():
    lookup = _synthetic_rank_divergence_lookup()
    info = compute_market_rank_divergence(lookup)

    # Sorted rank_diffs for the 10 candidates: [-8, -1, +1, +1, +1, +1, +1, +1, +1, +2]
    # p10 (10th percentile, nearest-rank on n=10) is index 1 -> -1.0
    # p90 (90th percentile, nearest-rank on n=10) is index 9 -> +2.0
    assert info["p10"] == pytest.approx(-1.0)
    assert info["p90"] == pytest.approx(2.0)

    # The thresholds must be genuinely derived from THIS call's distribution,
    # not a fixed constant. Rank-based diffs only depend on ORDER, not
    # magnitude - pushing dp_rank_native further apart without changing who's
    # ahead of whom leaves every aligned rank (and thus every rank_diff and
    # percentile) identical, which is itself a useful property to pin down.
    same_order = _synthetic_rank_divergence_lookup()
    same_order["p8"]["dp_rank_native"] = 5000.0
    same_order["p9"]["dp_rank_native"] = 0.001
    same_order_info = compute_market_rank_divergence(same_order)
    assert same_order_info["p10"] == info["p10"] and same_order_info["p90"] == info["p90"], (
        "rank_diff must be order-based, not magnitude-based - stretching values without reordering "
        "anyone should not move the thresholds at all"
    )

    # A genuinely different distribution (p1-p7's dp ranks reversed relative
    # to the market, instead of lining up 1:1) must move the thresholds.
    reordered = _synthetic_rank_divergence_lookup()
    for i in range(1, 8):
        reordered[f"p{i}"]["dp_rank_native"] = float(8 - i)  # was i, now 7..1 (reversed)
    reordered_info = compute_market_rank_divergence(reordered)
    assert reordered_info["p10"] != info["p10"] or reordered_info["p90"] != info["p90"], (
        "changing the actual ORDER of the underlying data must change the computed percentiles"
    )


def test_empty_intersection_returns_none_thresholds_without_crashing():
    lookup = {"p1": {"position": "WR", "fc_rank_native": None, "ktc_rank_native": None, "dp_rank_native": None}}
    info = compute_market_rank_divergence(lookup)
    assert info == {"n": 0, "p10": None, "p90": None}
