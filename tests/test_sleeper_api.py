"""
Converted from scratch/test_conditional_matchups_ttl.py and
scratch/test_projections_cache_ttl.py. All network calls are mocked -
these never touch the real Sleeper API.
"""
import time
from unittest.mock import MagicMock, patch

import pytest

import src.sleeper_api as sleeper_api


def _fake_response(payload):
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status.return_value = None
    resp.json.return_value = payload
    return resp


# ---------------------------------------------------------------------------
# get_league_matchups: conditional TTL by week (798431d) - a past week
# (relative to current_week) is already final and immutable, so it gets a
# long TTL; the current/active week can still change live, so it keeps the
# original short TTL.
# ---------------------------------------------------------------------------

LEAGUE_ID = "test_league_123"


@pytest.fixture(autouse=True)
def clear_matchups_cache():
    sleeper_api._LEAGUE_MATCHUPS_CACHE.clear()
    yield
    sleeper_api._LEAGUE_MATCHUPS_CACHE.clear()


def test_past_week_does_not_refetch_after_the_old_short_ttl():
    current_week, past_week = 5, 4
    payload = [{"roster_id": 1, "points": 100.0}]

    with patch("src.sleeper_api.requests.get", return_value=_fake_response(payload)):
        first = sleeper_api.get_league_matchups(LEAGUE_ID, past_week, current_week=current_week)
    assert first == payload

    cache_key = (str(LEAGUE_ID), int(past_week))
    cached_at, cached_data = sleeper_api._LEAGUE_MATCHUPS_CACHE[cache_key]

    # Rewind past the OLD short 5-minute TTL, but still well within the new
    # long TTL - the exact scenario the fix targets.
    rewound_by = sleeper_api.LEAGUE_MATCHUPS_CACHE_TTL_SECONDS + 60
    sleeper_api._LEAGUE_MATCHUPS_CACHE[cache_key] = (cached_at - rewound_by, cached_data)

    with patch("src.sleeper_api.requests.get") as mock_get:
        second = sleeper_api.get_league_matchups(LEAGUE_ID, past_week, current_week=current_week)

    assert not mock_get.called, "a past week must not refetch just because the old 5-minute TTL elapsed"
    assert second == cached_data


def test_past_week_eventually_refetches_past_its_own_long_ttl():
    """Not a permanent cache with a different name - it still expires, just much later."""
    current_week, past_week = 5, 4
    payload = [{"roster_id": 1, "points": 100.0}]

    with patch("src.sleeper_api.requests.get", return_value=_fake_response(payload)):
        sleeper_api.get_league_matchups(LEAGUE_ID, past_week, current_week=current_week)

    cache_key = (str(LEAGUE_ID), int(past_week))
    cached_at, cached_data = sleeper_api._LEAGUE_MATCHUPS_CACHE[cache_key]
    sleeper_api._LEAGUE_MATCHUPS_CACHE[cache_key] = (
        cached_at - sleeper_api.LEAGUE_HISTORY_CACHE_TTL_SECONDS - 60, cached_data
    )

    with patch("src.sleeper_api.requests.get", return_value=_fake_response(payload)) as mock_get:
        sleeper_api.get_league_matchups(LEAGUE_ID, past_week, current_week=current_week)

    assert mock_get.called, "a past week must still refetch once its own (long) TTL has elapsed"


def test_current_week_still_refetches_after_the_short_ttl():
    current_week = 5
    payload = [{"roster_id": 1, "points": 50.0}]

    with patch("src.sleeper_api.requests.get", return_value=_fake_response(payload)):
        sleeper_api.get_league_matchups(LEAGUE_ID, current_week, current_week=current_week)

    cache_key = (str(LEAGUE_ID), int(current_week))
    cached_at, cached_data = sleeper_api._LEAGUE_MATCHUPS_CACHE[cache_key]

    # Still within the short TTL: must NOT refetch.
    sleeper_api._LEAGUE_MATCHUPS_CACHE[cache_key] = (
        cached_at - (sleeper_api.LEAGUE_MATCHUPS_CACHE_TTL_SECONDS - 30), cached_data
    )
    with patch("src.sleeper_api.requests.get") as mock_get:
        sleeper_api.get_league_matchups(LEAGUE_ID, current_week, current_week=current_week)
    assert not mock_get.called, "the current week must not refetch before its own short TTL elapses"

    # Past the short TTL: SHOULD refetch.
    sleeper_api._LEAGUE_MATCHUPS_CACHE[cache_key] = (
        cached_at - sleeper_api.LEAGUE_MATCHUPS_CACHE_TTL_SECONDS - 1, cached_data
    )
    with patch("src.sleeper_api.requests.get", return_value=_fake_response(payload)) as mock_get:
        sleeper_api.get_league_matchups(LEAGUE_ID, current_week, current_week=current_week)
    assert mock_get.called, "the current week must still refetch every ~5 minutes as before"


# ---------------------------------------------------------------------------
# In-memory projections cache TTL: within TTL, reuse the cache; past TTL,
# fetch fresh (so a mid-week projection change is eventually picked up);
# on fetch failure past TTL, fall back to stale cached data instead of an
# empty dict.
# ---------------------------------------------------------------------------

def test_projections_within_ttl_reuses_cache_with_no_extra_network_call():
    sleeper_api._WEEKLY_PROJECTIONS_CACHE.clear()
    call_count = {"n": 0}

    def fake_get(url, timeout=15):
        call_count["n"] += 1
        return _fake_response({"1234": {"pts_ppr": 10.0}})

    with patch("src.sleeper_api.requests.get", side_effect=fake_get):
        first = sleeper_api.get_weekly_projections("2026", 2)
        second = sleeper_api.get_weekly_projections("2026", 2)

    assert call_count["n"] == 1
    assert first == second == {"1234": {"pts_ppr": 10.0}}


def test_projections_ttl_expiry_triggers_a_fresh_fetch():
    sleeper_api._WEEKLY_PROJECTIONS_CACHE.clear()
    call_count = {"n": 0}

    def fake_get(url, timeout=15):
        call_count["n"] += 1
        # Simulate the player's projection actually changing between calls
        # (e.g. downgraded to Doubtful and the projection dropping to 0).
        pts = 10.0 if call_count["n"] == 1 else 0.0
        return _fake_response({"1234": {"pts_ppr": pts}})

    with patch("src.sleeper_api.requests.get", side_effect=fake_get):
        first = sleeper_api.get_weekly_projections("2026", 2)
        assert call_count["n"] == 1

        cache_key = ("2026", 2)
        cached_at, cached_data = sleeper_api._WEEKLY_PROJECTIONS_CACHE[cache_key]
        aged_at = cached_at - (sleeper_api.PROJECTIONS_CACHE_TTL_SECONDS + 1)
        sleeper_api._WEEKLY_PROJECTIONS_CACHE[cache_key] = (aged_at, cached_data)

        second = sleeper_api.get_weekly_projections("2026", 2)

    assert call_count["n"] == 2
    assert first["1234"]["pts_ppr"] == 10.0
    assert second["1234"]["pts_ppr"] == 0.0, "expected the fresh fetch to reflect the updated (downgraded) projection"


def test_projections_stale_fallback_on_fetch_failure_after_ttl_expiry():
    sleeper_api._WEEKLY_PROJECTIONS_CACHE.clear()

    with patch("src.sleeper_api.requests.get", side_effect=lambda url, timeout=15: _fake_response({"1234": {"pts_ppr": 12.0}})):
        first = sleeper_api.get_weekly_projections("2026", 3)
    assert first == {"1234": {"pts_ppr": 12.0}}

    cache_key = ("2026", 3)
    cached_at, cached_data = sleeper_api._WEEKLY_PROJECTIONS_CACHE[cache_key]
    aged_at = cached_at - (sleeper_api.PROJECTIONS_CACHE_TTL_SECONDS + 1)
    sleeper_api._WEEKLY_PROJECTIONS_CACHE[cache_key] = (aged_at, cached_data)

    with patch("src.sleeper_api.requests.get", side_effect=ConnectionError("simulated network failure")):
        second = sleeper_api.get_weekly_projections("2026", 3)

    assert second == {"1234": {"pts_ppr": 12.0}}, "expected fallback to stale cached data on fetch failure, not an empty dict"


def test_ros_projections_cache_also_respects_the_ttl():
    sleeper_api._WEEKLY_PROJECTIONS_CACHE.clear()
    sleeper_api._ROS_PROJECTIONS_CACHE.clear()
    call_count = {"n": 0}

    def fake_get(url, timeout=15):
        call_count["n"] += 1
        return _fake_response({"1234": {"pts_ppr": 5.0, "pos": "WR", "team": "XXX", "player_name": "Test Player"}})

    with patch("src.sleeper_api.requests.get", side_effect=fake_get):
        first = sleeper_api.get_ros_projections("2026", start_week=1, end_week=2)
        calls_after_first = call_count["n"]
        second = sleeper_api.get_ros_projections("2026", start_week=1, end_week=2)
    assert call_count["n"] == calls_after_first, "expected the second ROS call within TTL to reuse cache with no extra network calls"
    assert first == second

    cache_key = ("2026", 1, 2)
    cached_at, cached_data = sleeper_api._ROS_PROJECTIONS_CACHE[cache_key]
    aged_at = cached_at - (sleeper_api.PROJECTIONS_CACHE_TTL_SECONDS + 1)
    sleeper_api._ROS_PROJECTIONS_CACHE[cache_key] = (aged_at, cached_data)
    for wk in (1, 2):
        wk_key = ("2026", wk)
        wk_at, wk_data = sleeper_api._WEEKLY_PROJECTIONS_CACHE[wk_key]
        sleeper_api._WEEKLY_PROJECTIONS_CACHE[wk_key] = (wk_at - (sleeper_api.PROJECTIONS_CACHE_TTL_SECONDS + 1), wk_data)

    with patch("src.sleeper_api.requests.get", side_effect=fake_get):
        sleeper_api.get_ros_projections("2026", start_week=1, end_week=2)
    assert call_count["n"] > calls_after_first, "expected fresh network calls after aging the ROS cache entry past the TTL"


# ---------------------------------------------------------------------------
# get_league_draft_type: a rounds mismatch (the only draft Sleeper has on
# file is a stale startup draft with a different round count than the
# league's current settings.draft_rounds) used to silently copy that
# startup draft's type - real case: Diferenciados' only draft on file is a
# 22-round snake startup draft, but its actual yearly 4-round rookie draft
# is linear, so every pick's tier incorrectly alternated early/late by
# round instead of staying flat. Now defaults to "linear" on a mismatch
# instead of trusting the stale draft's type.
# ---------------------------------------------------------------------------

def test_rounds_mismatch_defaults_to_linear_instead_of_copying_the_stale_draft_type():
    """The real Diferenciados case: a 22-round snake startup draft on file, current draft_rounds=4."""
    stale_startup_draft = [{"type": "snake", "settings": {"rounds": 22}}]

    with patch("src.sleeper_api.requests.get", return_value=_fake_response(stale_startup_draft)):
        result = sleeper_api.get_league_draft_type(LEAGUE_ID, expected_rounds=4)

    assert result == "linear", "a rounds mismatch must default to linear, not copy the stale draft's snake type"


def test_rounds_match_still_trusts_the_real_draft_type():
    """When a draft's round count DOES match current settings, its real type must still be trusted."""
    matching_draft = [{"type": "snake", "settings": {"rounds": 4}}]

    with patch("src.sleeper_api.requests.get", return_value=_fake_response(matching_draft)):
        result = sleeper_api.get_league_draft_type(LEAGUE_ID, expected_rounds=4)

    assert result == "snake", "a genuinely matching draft's type must still be honored, not overridden to linear"


def test_no_expected_rounds_keeps_the_old_first_draft_fallback():
    """Callers that don't pass expected_rounds at all get the pre-existing behavior unchanged."""
    only_draft = [{"type": "snake", "settings": {"rounds": 22}}]

    with patch("src.sleeper_api.requests.get", return_value=_fake_response(only_draft)):
        result = sleeper_api.get_league_draft_type(LEAGUE_ID)

    assert result == "snake"


def test_no_drafts_on_file_defaults_to_linear():
    with patch("src.sleeper_api.requests.get", return_value=_fake_response([])):
        result = sleeper_api.get_league_draft_type(LEAGUE_ID, expected_rounds=4)

    assert result == "linear"


# ---------------------------------------------------------------------------
# build_weekly_roster_snapshots: reconstructs each week's real roster by
# undoing transactions backward from the current roster - regression test
# for the real Liga do Inguinho incident, where a week-3 trade
# (Judkins+Waddle -> Brian Thomas) was silently changing what the Week 1/2
# Power Rankings snapshots showed, since the app used to reuse today's
# (post-trade) roster for every historical week.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_transactions_cache():
    sleeper_api._LEAGUE_TRANSACTIONS_CACHE.clear()
    yield
    sleeper_api._LEAGUE_TRANSACTIONS_CACHE.clear()


def test_trade_does_not_change_weeks_before_it():
    """Mirrors the real Liga do Inguinho trade: roster 11 gives up players
    12512+7526 and receives 11631, completed in week 3."""
    current_rosters = [
        {"roster_id": 11, "players": ["11631", "9999"]},
        {"roster_id": 12, "players": ["12512", "7526", "8888"]},
    ]
    trade = {
        "status": "complete",
        "created": 1_000_000,
        "adds": {"11631": 11, "12512": 12, "7526": 12},
        "drops": {"11631": 12, "12512": 11, "7526": 11},
    }

    def fake_get(url, timeout=10):
        if url.endswith("/transactions/3"):
            return _fake_response([trade])
        return _fake_response([])

    with patch("src.sleeper_api.requests.get", side_effect=fake_get):
        snapshots = sleeper_api.build_weekly_roster_snapshots(LEAGUE_ID, current_rosters, current_week=3)

    assert sorted(snapshots.keys()) == [1, 2, 3]

    for week in (1, 2):
        r11 = next(r for r in snapshots[week] if r["roster_id"] == 11)
        r12 = next(r for r in snapshots[week] if r["roster_id"] == 12)
        assert "11631" not in r11["players"], f"week {week}: acquired player must not appear before the trade"
        assert set(r11["players"]) == {"12512", "7526", "9999"}, f"week {week}: roster 11 must still hold what it had before the trade"
        assert "12512" not in r12["players"] and "7526" not in r12["players"], f"week {week}: given-up players must still belong to roster 12"
        assert set(r12["players"]) == {"11631", "8888"}

    # Week 3 (the trade week itself) already reflects the post-trade state,
    # matching the current/live roster passed in.
    r11_w3 = next(r for r in snapshots[3] if r["roster_id"] == 11)
    r12_w3 = next(r for r in snapshots[3] if r["roster_id"] == 12)
    assert set(r11_w3["players"]) == {"11631", "9999"}
    assert set(r12_w3["players"]) == {"12512", "7526", "8888"}


def test_incomplete_transaction_is_never_undone():
    """A failed/pending waiver claim never actually changed the roster - it must be ignored entirely."""
    current_rosters = [{"roster_id": 1, "players": ["100"]}]
    failed_waiver = {
        "status": "failed",
        "created": 500,
        "adds": {"200": 1},
        "drops": {"100": 1},
    }

    with patch("src.sleeper_api.requests.get", return_value=_fake_response([failed_waiver])):
        snapshots = sleeper_api.build_weekly_roster_snapshots(LEAGUE_ID, current_rosters, current_week=2)

    r1_week1 = next(r for r in snapshots[1] if r["roster_id"] == 1)
    assert r1_week1["players"] == ["100"], "a failed transaction must not be undone - the roster never actually changed"


def test_no_transactions_keeps_the_same_roster_every_week():
    current_rosters = [{"roster_id": 1, "players": ["100", "200"]}]

    with patch("src.sleeper_api.requests.get", return_value=_fake_response([])):
        snapshots = sleeper_api.build_weekly_roster_snapshots(LEAGUE_ID, current_rosters, current_week=4)

    for week in range(1, 5):
        assert set(snapshots[week][0]["players"]) == {"100", "200"}


# ---------------------------------------------------------------------------
# get_league_transactions: the current week must always be fetched live,
# never served from the 5-minute cache - regression test for the real
# incident this fixes. get_league_rosters has no cache at all (always
# live), while this function's current-week cache used to refresh on its
# own independent 5-minute clock - a transaction processed moments ago
# could already show up in a freshly-fetched roster while the stale
# transactions cache here still didn't know about it yet.
# build_weekly_roster_snapshots undoing a transaction it doesn't know
# exists is a no-op, so weeks 1/2/3 would transiently show a player who
# only arrived via that transaction TODAY - self-correcting a few minutes
# later once the stale cache naturally expired. That "changes on its own
# with no new transaction" symptom is exactly what reproducing the race
# below pins.
# ---------------------------------------------------------------------------

def test_current_week_always_refetches_live_even_with_a_fresh_cache_entry():
    """
    Pre-seeds a brand-new (age=0s, well within the old 5-minute TTL) cache
    entry for the current week, then confirms a call still goes live
    instead of trusting it - the fix removes the "is it still fresh"
    check entirely for week == current_week.
    """
    current_week = 4
    stale_payload = []  # what was cached before the real transaction existed
    live_payload = [{"status": "complete", "created": 123, "adds": {"NEW": 1}, "drops": {"OLD": 1}}]

    cache_key = (str(LEAGUE_ID), current_week)
    sleeper_api._LEAGUE_TRANSACTIONS_CACHE[cache_key] = (time.time(), stale_payload)

    with patch("src.sleeper_api.requests.get", return_value=_fake_response(live_payload)) as mock_get:
        result = sleeper_api.get_league_transactions(LEAGUE_ID, current_week, current_week=current_week)

    assert mock_get.called, "the current week must always hit the network, never short-circuit on a fresh cache entry"
    assert result == live_payload, "the live (real) payload must win over the stale cached one for the current week"


def test_past_week_still_uses_the_long_historical_cache_unchanged():
    """Regression guard: weeks strictly before current_week must keep their existing long-TTL cache behavior."""
    past_week, current_week = 2, 4
    payload = [{"status": "complete", "created": 1, "adds": {"A": 1}, "drops": {}}]

    with patch("src.sleeper_api.requests.get", return_value=_fake_response(payload)):
        first = sleeper_api.get_league_transactions(LEAGUE_ID, past_week, current_week=current_week)
    assert first == payload

    with patch("src.sleeper_api.requests.get") as mock_get:
        second = sleeper_api.get_league_transactions(LEAGUE_ID, past_week, current_week=current_week)

    assert not mock_get.called, "a past (already-settled) week must still be served from the long-TTL cache, not refetched"
    assert second == payload


def test_build_weekly_roster_snapshots_is_not_fooled_by_a_stale_current_week_cache_entry():
    """
    End-to-end reproduction of the real incident at the build_weekly_roster_snapshots
    level: a stale cache entry for the current week (pre-dating a real
    transaction) must no longer leak into the reconstructed past weeks.
    """
    current_rosters = [{"roster_id": 12, "players": ["NEW_PLAYER", "999"]}]
    real_transaction = {
        "status": "complete", "created": 1_000_000,
        "adds": {"NEW_PLAYER": 12}, "drops": {"OLD_PLAYER": 12},
    }

    # Pre-seed a stale (empty) cache entry for week 4 - as if it had been
    # populated moments before the real transaction happened.
    sleeper_api._LEAGUE_TRANSACTIONS_CACHE[(str(LEAGUE_ID), 4)] = (time.time(), [])

    def fake_get(url, timeout=10):
        week = int(url.rsplit("/", 1)[-1])
        return _fake_response([real_transaction] if week == 4 else [])

    with patch("src.sleeper_api.requests.get", side_effect=fake_get):
        snapshots = sleeper_api.build_weekly_roster_snapshots(LEAGUE_ID, current_rosters, current_week=4)

    for week in (1, 2, 3):
        r12 = next(r for r in snapshots[week] if r["roster_id"] == 12)
        assert "NEW_PLAYER" not in r12["players"], (
            f"week {week}: must not show the player added via TODAY's transaction, "
            "even though a stale cache entry for the current week existed"
        )
        assert "OLD_PLAYER" in r12["players"]

    r12_w4 = next(r for r in snapshots[4] if r["roster_id"] == 12)
    assert "NEW_PLAYER" in r12_w4["players"]
