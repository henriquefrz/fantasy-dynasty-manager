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
from src.market_data import (
    apply_ktc_te_premium,
    apply_valuation_mode,
    compute_ktc_official_adjustment,
    compute_market_rank_divergence,
    _build_ktc_id_crosswalks,
    _extract_ktc_redraft_pillar,
    _extrapolate_deep_rounds,
    _resolve_ktc_sleeper_id,
)


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
# KTC ktc_id/mfl_id crosswalk matching (real bug: Jeremiyah Love, Drake Maye,
# Jayden Daniels, Caleb Williams, TreVeyon Henderson, Brian Thomas Jr. and
# ~10 other 2024-2025 draft-class players). KTC's "fantasy-rankings" (redraft)
# page uses a different internal playerID sequence than its dynasty-rankings
# page, and that redraft sequence had drifted out of sync with
# db_playerids.csv for this draft-class block - the crosswalk's ktc_id column
# pointed at a completely different real player for each of them. The old
# `ktc_id_to_sleeper.get(p_id) or mfl_id_to_sleeper.get(mfl_id)` trusted
# whichever side returned first as long as it was non-empty, so a
# wrong-but-real sleeper_id (or the literal string "NA", itself a non-empty
# and therefore truthy string) silently won over the otherwise-reliable
# mfl_id fallback - misattributing that rookie's KTC value to an unrelated
# player instead of leaving the rookie unmatched.
# ---------------------------------------------------------------------------

def test_resolve_ktc_sleeper_id_falls_through_to_mfl_id_when_ktc_id_points_at_a_different_player():
    """
    Reproduces the exact real-world shape: a rookie's live KTC playerID
    collides with a crosswalk row that actually belongs to someone else (a
    stale ktc_id), while the rookie's OWN crosswalk row - reachable via
    mfl_id, which stayed in sync - correctly identifies them.
    """
    live_player = {"playerID": "700", "mflid": "9700", "playerName": "Rookie QB"}
    player_ids_raw = [
        # A real crosswalk row for a DIFFERENT player that happens to still
        # carry ktc_id "700" (KTC has since reassigned that id to Rookie QB
        # on the redraft page; dynastyprocess hasn't caught up).
        {"ktc_id": "700", "mfl_id": "8888", "sleeper_id": "wrong_sid", "name": "Unrelated Veteran"},
        # Rookie QB's OWN real crosswalk row - stale ktc_id, correct mfl_id.
        {"ktc_id": "650", "mfl_id": "9700", "sleeper_id": "rookie_sid", "name": "Rookie QB"},
    ]
    ktc_id_to_row, mfl_id_to_row = _build_ktc_id_crosswalks(player_ids_raw)

    resolved = _resolve_ktc_sleeper_id(live_player, ktc_id_to_row, mfl_id_to_row)

    assert resolved == "rookie_sid", "must resolve to Rookie QB's own sleeper_id via the mfl_id fallback"
    assert resolved != "wrong_sid", "must never accept the unrelated veteran's sleeper_id just because ktc_id collided"


def test_resolve_ktc_sleeper_id_treats_the_string_NA_as_no_match():
    """
    "NA" is db_playerids.csv's own placeholder for "no ID available" - a
    non-empty string, and therefore truthy, so the old `or`-chain accepted
    it as if it were a real sleeper_id. It must now be treated as absent,
    with no fallback available in this case.
    """
    live_player = {"playerID": "700", "mflid": "9700", "playerName": "No Sleeper Player"}
    player_ids_raw = [
        {"ktc_id": "700", "mfl_id": "", "sleeper_id": "NA", "name": "No Sleeper Player"},
    ]
    ktc_id_to_row, mfl_id_to_row = _build_ktc_id_crosswalks(player_ids_raw)

    resolved = _resolve_ktc_sleeper_id(live_player, ktc_id_to_row, mfl_id_to_row)

    assert resolved is None, "the literal string 'NA' must never be returned as a sleeper_id"


def test_resolve_ktc_sleeper_id_excludes_a_player_missing_from_the_crosswalk_entirely():
    """A player with neither a matching ktc_id nor mfl_id row must be excluded gracefully, not raise."""
    live_player = {"playerID": "999", "mflid": "9999", "playerName": "Brand New Player"}
    player_ids_raw = [
        {"ktc_id": "700", "mfl_id": "9700", "sleeper_id": "rookie_sid", "name": "Rookie QB"},
    ]
    ktc_id_to_row, mfl_id_to_row = _build_ktc_id_crosswalks(player_ids_raw)

    resolved = _resolve_ktc_sleeper_id(live_player, ktc_id_to_row, mfl_id_to_row)

    assert resolved is None


def test_resolve_ktc_sleeper_id_still_matches_the_common_case_via_ktc_id():
    """No regression for the ordinary case: a correct, non-colliding ktc_id match still works."""
    live_player = {"playerID": "42", "mflid": "4242", "playerName": "Steady Veteran"}
    player_ids_raw = [
        {"ktc_id": "42", "mfl_id": "4242", "sleeper_id": "steady_sid", "name": "Steady Veteran"},
    ]
    ktc_id_to_row, mfl_id_to_row = _build_ktc_id_crosswalks(player_ids_raw)

    resolved = _resolve_ktc_sleeper_id(live_player, ktc_id_to_row, mfl_id_to_row)

    assert resolved == "steady_sid"


def test_extract_ktc_redraft_pillar_no_longer_cross_contaminates_misattributed_players():
    """
    End-to-end reproduction through the real redraft pillar (the function
    named in the original bug report) with a synthetic pool shaped like the
    15 real cases: a rookie QB whose stale ktc_id collides with an unrelated
    veteran WR's crosswalk row. Before the fix, the rookie's value ended up
    filed under the WR's sleeper_id (or was lost to a dict-key collision)
    and the rookie's own sleeper_id had no entry at all.
    """
    ktc_fantasy_raw = [
        {
            "playerID": "700", "mflid": "9700", "position": "QB", "playerName": "Rookie QB",
            "oneQBValues": {"value": 5000.0},
        },
        {
            "playerID": "600", "mflid": "9600", "position": "WR", "playerName": "Unrelated Veteran",
            "oneQBValues": {"value": 3000.0},
        },
    ]
    player_ids_raw = [
        # Rookie QB's live playerID (700) collides with this stale crosswalk
        # row, which is actually the Veteran's row reachable another way.
        {"ktc_id": "700", "mfl_id": "8888", "sleeper_id": "veteran_sid", "name": "Unrelated Veteran"},
        # Rookie QB's OWN row - stale ktc_id, correct mfl_id.
        {"ktc_id": "650", "mfl_id": "9700", "sleeper_id": "rookie_sid", "name": "Rookie QB"},
        # The Veteran's OWN live-pool entry (playerID 600) needs its own
        # crosswalk row too, matched directly by ktc_id this time.
        {"ktc_id": "600", "mfl_id": "9600", "sleeper_id": "veteran_sid", "name": "Unrelated Veteran"},
    ]

    result = _extract_ktc_redraft_pillar(ktc_fantasy_raw, player_ids_raw=player_ids_raw, is_superflex=False)

    assert "rookie_sid" in result, "Rookie QB must get their own entry"
    assert result["rookie_sid"]["val"] == 5000.0, "Rookie QB's entry must carry Rookie QB's own value"
    assert "veteran_sid" in result, "Unrelated Veteran must keep their own entry"
    assert result["veteran_sid"]["val"] == 3000.0, "Unrelated Veteran's value must be their own, not the rookie's"


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


# ---------------------------------------------------------------------------
# compute_ktc_official_adjustment: ported from KeepTradeCut's own live
# adjustPackageNew()/processVNew()/reverseAdjustNew() (extracted from
# https://keeptradecut.com/js/site.min.js, ALGOTOUSE=2 - the algorithm KTC's
# own site actually runs, not the outdated 2022 third-party blog formula
# that no longer matches production). Each fixture's expected (side, value,
# display) was captured by calling KTC's real functions directly in a
# browser console against keeptradecut.com/trade-calculator (1QB dynasty
# values, Sep 2026) - this pins our port to their real, current output.
# ---------------------------------------------------------------------------

_KTC_TOP_OVERALL = 9998  # playersArray[0].value at the time these fixtures were captured

# fmt: off
_KTC_CHASE, _KTC_STBROWN, _KTC_OLAVE = 9635, 8435, 6763
_KTC_ALLEN, _KTC_JEFFERSON = 7686, 7631
_KTC_TAYLOR, _KTC_PICKENS, _KTC_FLOWERS, _KTC_SMITH = 7198, 6408, 6366, 6279
_KTC_WALKER, _KTC_BURROW, _KTC_HALL = 7240, 5858, 6162
_KTC_GIBBS, _KTC_WILSON = 9998, 6239
# fmt: on


@pytest.mark.parametrize(
    "side_a,side_b,expected_side,expected_value,expected_display",
    [
        pytest.param([_KTC_CHASE], [_KTC_STBROWN, _KTC_OLAVE], 1, 741, False, id="2-for-1 stud vs depth"),
        pytest.param([_KTC_ALLEN], [_KTC_JEFFERSON], 1, 403, False, id="1-for-1 close values"),
        pytest.param([_KTC_TAYLOR], [_KTC_PICKENS, _KTC_FLOWERS, _KTC_SMITH], 1, 3515, True, id="3-for-1 stud vs depth"),
        pytest.param([_KTC_WALKER, _KTC_BURROW], [_KTC_TAYLOR, _KTC_HALL], 2, 1060, True, id="2-for-2 mixed signal"),
        pytest.param([_KTC_TAYLOR, _KTC_HALL], [_KTC_WALKER, _KTC_BURROW], 1, 1060, True, id="2-for-2 mixed signal, sides swapped"),
        pytest.param([_KTC_GIBBS], [_KTC_FLOWERS, _KTC_SMITH, _KTC_WILSON], 1, 4363, True, id="1-for-3 elite vs three starters"),
        pytest.param([_KTC_STBROWN], [_KTC_OLAVE], 1, 3214, True, id="1-for-1 stud premium"),
    ],
)
def test_compute_ktc_official_adjustment_matches_live_ktc_site(side_a, side_b, expected_side, expected_value, expected_display):
    result = compute_ktc_official_adjustment(side_a, side_b, _KTC_TOP_OVERALL)

    assert result["adjust_side"] == expected_side
    assert result["adjust_value"] == expected_value
    assert result["display"] == expected_display


def test_compute_ktc_official_adjustment_returns_none_for_a_one_sided_trade():
    assert compute_ktc_official_adjustment([], [_KTC_CHASE], _KTC_TOP_OVERALL) is None
    assert compute_ktc_official_adjustment([_KTC_CHASE], [], _KTC_TOP_OVERALL) is None


# ---------------------------------------------------------------------------
# _extrapolate_deep_rounds: used to accumulate a shrinking-but-still-negative
# per-round DELTA onto the last known pick value with no floor, so a season
# whose last known round was already small (e.g. real 2027 data - KTC/
# FantasyCalc stop pricing at round 4, leaving only DynastyProcess's own
# near-zero round 5 quote) went negative by round 6 and stayed negative
# through round 10. Fixed to decay the VALUE itself multiplicatively
# (last_val *= decay_ratio), which - for any decay_ratio in (0, 1) - can
# only asymptotically approach zero, never cross it.
# ---------------------------------------------------------------------------

def test_extrapolate_deep_rounds_never_goes_negative():
    """
    Regression guard for the real Dinastia do Pão de Queijo bug: a season
    whose last known round is already tiny relative to the point drop from
    the round before it. Round 4 -> Round 5 here mirrors the real 2027
    data almost exactly (990.0 -> 4.7).
    """
    consensus_picks = {
        ("2027", 1): 3607.9,
        ("2027", 2): 1924.1,
        ("2027", 3): 1312.4,
        ("2027", 4): 990.0,
        ("2027", 5): 4.7,
    }

    _extrapolate_deep_rounds(consensus_picks, max_round=10)

    for r in range(6, 11):
        val = consensus_picks[("2027", r)]
        assert val > 0, f"round {r} synthesized a non-positive value: {val}"

    # Rounds 1-5 (native, not extrapolated) must be untouched.
    assert consensus_picks[("2027", 1)] == 3607.9
    assert consensus_picks[("2027", 5)] == 4.7

    # Smooth, monotonically decreasing curve - no jump back up.
    values = [consensus_picks[("2027", r)] for r in range(5, 11)]
    assert all(values[i] >= values[i + 1] for i in range(len(values) - 1)), (
        f"extrapolated values must decrease monotonically: {values}"
    )


def test_extrapolate_deep_rounds_never_goes_negative_with_a_steep_synthetic_decay():
    """
    Extreme synthetic case: a season that crashes to a fraction of a point
    by its last known round. Even the steepest clamped decay_ratio (0.5)
    applied multiplicatively can only ever shrink an already-positive
    value asymptotically toward zero - unlike the old additive-delta
    approach, it can never push it below zero. At this input's scale the
    result legitimately rounds to a displayed 0.0 pts (not negative) once
    it decays below the 1-decimal rounding threshold - that is a display
    footnote, not a regression, since 0.0 still satisfies "never below
    zero"; the assertion below is `>= 0` rather than `> 0` for exactly
    that reason.
    """
    consensus_picks = {
        ("2029", 1): 5000.0,
        ("2029", 2): 500.0,
        ("2029", 3): 5.0,
        ("2029", 4): 0.05,
    }

    _extrapolate_deep_rounds(consensus_picks, max_round=10)

    values = [consensus_picks[("2029", r)] for r in range(4, 11)]
    for r, val in zip(range(4, 11), values):
        assert val >= 0, f"round {r} synthesized a negative value: {val}"
    assert all(values[i] >= values[i + 1] for i in range(len(values) - 1)), (
        f"extrapolated values must never increase: {values}"
    )


def test_extrapolate_deep_rounds_uses_the_observed_decay_ratio_not_always_the_fallback():
    """
    Regression guard for the sign-filter bug: `ratios` was computed with
    `if deltas[i] > 0`, which is never true for a monotonically decreasing
    pick curve (deltas are always negative), so the adaptive decay_ratio
    branch was permanently dead code and every season silently used the
    flat 0.75 fallback regardless of its own actual shape. This pins a
    season whose observed ratio clamps to the 0.5 floor (a much steeper
    decay than 0.75) and confirms that steeper ratio is what actually gets
    applied.
    """
    # value ratio round2/round1 = 0.1, round3/round2 = 0.1 -> delta ratio
    # between consecutive deltas is also 0.1, i.e. computed decay_ratio
    # should clamp to the 0.5 floor, not fall back to 0.75.
    consensus_picks = {
        ("2030", 1): 1000.0,
        ("2030", 2): 100.0,
        ("2030", 3): 10.0,
    }

    _extrapolate_deep_rounds(consensus_picks, max_round=4)

    round4 = consensus_picks[("2030", 4)]
    # round3 * 0.75 (old fallback) would be 7.5 - assert the steeper,
    # clamped-to-0.5 ratio was actually used instead.
    assert round4 == pytest.approx(10.0 * 0.5, abs=0.01)
