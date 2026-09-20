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
from src.market_data import apply_ktc_te_premium, apply_valuation_mode


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
