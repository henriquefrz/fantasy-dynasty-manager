"""
Live sanity check that apply_ktc_te_premium (src/market_data.py) actually
raises TE market values when fed real KeepTradeCut data with a real TE
Premium bonus - the KTC-native TEP feature added this session (82009c5).

This is a thin smoke test, not a full port of any single scratch/ script:
it exists to fill out the tests/integration/ structure with one real,
end-to-end KTC check. scratch/test_ktc_native_tep_part1.py and
scratch/test_ktc_redraft_pillar_part2.py cover this area in more depth
across all of the user's real leagues and were intentionally left as-is
in this pass (not part of the requested Category C/D conversions).

Requires network access; run explicitly with `pytest -m integration`.
"""
import pytest

from src.market_data import (
    apply_ktc_te_premium,
    build_positional_lookup,
    enrich_lookup_with_consensus_values,
    get_fantasycalc_data_raw,
    get_fp_rankings_raw,
    get_ktc_data_raw,
    get_player_ids_raw,
    get_values_players_raw,
)

pytestmark = pytest.mark.integration


def test_ktc_native_tep_raises_te_market_values():
    fp_rankings = get_fp_rankings_raw()
    player_ids = get_player_ids_raw()
    values_players = get_values_players_raw()
    ktc_sf = get_ktc_data_raw(is_superflex=True)
    fc_sf = get_fantasycalc_data_raw(is_dynasty=True, is_superflex=True)

    dyn_lookup = build_positional_lookup(fp_rankings, player_ids, "dynasty", is_superflex=True)
    enrich_lookup_with_consensus_values(dyn_lookup, values_players, player_ids, ktc_raw=ktc_sf, fc_raw=fc_sf, is_superflex=True)

    te_entries_before = {pid: data["market_value"] for pid, data in dyn_lookup.items() if data.get("position") == "TE"}
    assert te_entries_before, "expected at least one TE in the real dynasty lookup"

    tepp_lookup = apply_ktc_te_premium(dyn_lookup, 1.0, ktc_sf, player_ids, is_superflex=True)

    raised_count = sum(
        1 for pid, before in te_entries_before.items()
        if tepp_lookup.get(pid, {}).get("market_value", before) > before
    )
    assert raised_count > 0, "expected at least one real TE's market_value to increase under a 1.0 (TE++) bonus"
