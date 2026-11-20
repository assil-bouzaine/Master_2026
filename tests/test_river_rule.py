"""Checks of the river gap rule (src/models/features.py river_series; analysis plan §7b).

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m tests.test_river_rule   (< 1 min)

The rule declared in §7b interpolates internal gaps of at most 8 weeks between both ends and fills
every other missing week with the gauge's week-of-year median over the weeks observed in the
training window. Until 2026-11-20 the code (now rule "legacy") also interpolated the first 8 weeks of
a longer gap toward its far end (astra review point 2): the Têt at Perpignan misses 59 weeks from
2021-09-12, so 8 validation weeks leaned on a test-period observation.
1. "legacy" still reproduces the river columns of the cached panel of record exactly (the baselines
   of record and the twin keep it).
2. "declared": a far observation never moves the fill of a long gap (the review's check: change the
   observation of 2022-10-30 and the fill of 2021-09-12 stays), and that fill is the training-window
   median (1.011081 for the Têt, against 1.113916 under "legacy").
3. "declared" on a hand-made series: an internal 8-week gap is interpolated linearly, a 9-week gap
   and the ends of the record get the median of the observed training weeks only (warm-up weeks and
   interpolated values never enter it).
4. The routed inputs of the real-data arms use "declared" by default; the twin pins "legacy".
"""
import json

import numpy as np
import pandas as pd

from src.models import features as F
from src.models import twin as W
from src.models.evaluate import DS, RESULTS
from src.models.routing import routed_inputs

SPLITS = json.loads((DS / "splits.json").read_text())
TET = "Y047403001"


def panel_weeks():
    return pd.DatetimeIndex(sorted(pd.read_parquet(RESULTS / "_cache" / "panel.parquet", columns=["week"])["week"].unique()))


def woy_of(weeks):
    return pd.Series(weeks.isocalendar().week.clip(upper=52).to_numpy(), index=weeks)


def test_legacy_reproduces_the_panel():
    P = pd.read_parquet(RESULTS / "_cache" / "panel.parquet")
    weeks = panel_weeks()
    riv = F.river_series(weeks, SPLITS["train"][1], rule="legacy")
    one = P[P["code_bss"] == P["code_bss"].iloc[0]].set_index("week")
    for name, code in F.RIVERS.items():
        np.testing.assert_array_equal(one[name].reindex(weeks).to_numpy(), riv[code].to_numpy())
    print("  1. rule legacy = the river columns of the cached panel of record, exactly")


def test_far_observation_does_not_move_a_long_gap():
    weeks = panel_weeks()
    r = pd.read_parquet(DS / "rivers_weekly.parquet")
    s = np.log1p(r[r["code_station"] == TET].set_index("week")["q_m3s"]).reindex(weeks)
    gap, far = pd.Timestamp("2021-09-12"), pd.Timestamp("2022-10-30")
    assert np.isnan(s[gap]) and np.isfinite(s[far]) and s["2021-09-12":"2022-10-23"].isna().all()
    woy = woy_of(weeks)
    fills = {}
    for rule in ("legacy", "declared"):
        a = F.fill_river_gaps(s, woy, SPLITS["train"][1], rule, SPLITS["train"][0])
        moved = s.copy()
        moved[far] += 1.0
        b = F.fill_river_gaps(moved, woy, SPLITS["train"][1], rule, SPLITS["train"][0])
        fills[rule] = (a[gap], b[gap])
    assert fills["legacy"][0] != fills["legacy"][1], "legacy leaned on the far observation"
    assert fills["declared"][0] == fills["declared"][1], "declared must not"
    assert round(fills["declared"][0], 6) == 1.011081 and round(fills["legacy"][0], 6) == 1.113916, fills
    print(f"  2. Têt, 2021-09-12: declared {fills['declared'][0]:.6f} whatever the 2022-10-30 value; "
          f"legacy {fills['legacy'][0]:.6f} moved to {fills['legacy'][1]:.6f}")


def test_hand_made_series():
    weeks = pd.date_range("2003-01-05", "2021-12-26", freq="W-SUN")
    woy = woy_of(weeks)
    s = pd.Series(1.0 + 0.0 * np.arange(len(weeks)), index=weeks)
    s[weeks.year < 2005] = 50.0                         # warm-up: must not enter the median
    s[weeks >= "2020-01-01"] = 7.0                      # after training: must not enter the median
    s.iloc[:3] = np.nan                                 # an end of the record
    short = slice(400, 408)                             # 8 weeks between two observed weeks
    s.iloc[399], s.iloc[408] = 1.0, 10.0
    s.iloc[short] = np.nan
    s.iloc[600:609] = np.nan                            # 9 weeks: no interpolation
    f = F.fill_river_gaps(s, woy, "2019-12-31", "declared", "2005-01-01")
    np.testing.assert_allclose(f.iloc[short].to_numpy(), np.interp(range(400, 408), [399, 408], [1.0, 10.0]))
    in_window = (weeks >= "2005-01-01") & (weeks <= "2019-12-31") & s.notna()
    med = s[in_window].groupby(woy[in_window]).median()
    np.testing.assert_allclose(f.iloc[600:609].to_numpy(), woy.iloc[600:609].map(med).to_numpy())
    np.testing.assert_allclose(f.iloc[:3].to_numpy(), woy.iloc[:3].map(med).to_numpy())
    assert set(np.round(f.iloc[600:609], 9)) <= {1.0, 5.5}, "only observed training weeks enter the median"
    print("  3. hand-made series: an 8-week gap interpolated, a 9-week gap and the record's start filled "
          "with the median of the observed training weeks only")


def test_defaults():
    weeks = panel_weeks()
    e = pd.DataFrame({"relation": ["river"], "src_type": ["gauge"], "src": [TET], "dst": ["w"],
                      "weight": [1.0], "distance_m": [0.0]})
    gap = weeks.get_loc(pd.Timestamp("2021-09-12"))
    dec = routed_inputs(edges=e, codes=["w"], weeks=weeks)["river"][0, gap]
    leg = routed_inputs(edges=e, codes=["w"], weeks=weeks, river_rule="legacy")["river"][0, gap]
    assert round(dec, 6) == 1.011081 and round(leg, 6) == 1.113916, (dec, leg)
    assert W.RIVER_RULE == "legacy"
    print("  4. routed inputs: declared by default (real-data arms); the twin pins legacy")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("test_river_rule: all checks passed")
