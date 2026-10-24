"""What each RQ1 regime may use, checked against the data (analysis plan §4, third review §3.2).

    PFE_DATASET=v4 python -m tests.test_regime_boundaries

The rules (docs/analysis_plan.md §4, table "What each regime may use") restated here
independently of the code, and checked on the cached panels; nothing is trained:
1. R1: each well's mu and sd are the mean and sd of its observed heads in 2005-2019.
2. R3 (25 %, 50 %): mu, sd, the climatology of z and the artesian share come from the
   window [start, 2019-12-31] only; the input standardisation keeps the whole training
   period (R3 limits the head history, not the forcing history). A well without any head
   in the window has no statistics and leaves the regime (2016-2019: 4 non-core wells),
   so the forcing standardisation is compared on the wells both panels keep.
3. Masks: R3 trains on no week before the window; R2 trains on no week of the held-out fold
   and stops early on the other wells; the refit adds the validation weeks.
4. Coverage: every core well keeps at least MIN_WINDOW_WEEKS observed weeks in each window
   (printed per window: the wells with less than two years).
"""
import json

import numpy as np
import pandas as pd

from src.config import R3_STARTS
from src.models import lstm
from src.models.evaluate import DS
from src.models.features import build_panel

MIN_WINDOW_WEEKS = 52
TRAIN_END = pd.Timestamp("2019-12-31")


def head_stats(P, start):
    rows = P[(P["split"] == "train") & (P["week"] >= start) & P["head"].notna()]
    return rows.groupby("code_bss")["head"].agg(["mean", "std"])


def climatology(P, start):
    """Mean z per week of year over the window, interpolated and smoothed over 5 weeks."""
    rows = P[(P["split"] == "train") & (P["week"] >= start)]
    woy = rows["week"].dt.isocalendar().week.clip(upper=52).astype(int)
    c = rows.assign(woy=woy).groupby(["code_bss", "woy"])["z"].mean().unstack()
    c = c.reindex(columns=range(1, 53)).T.interpolate(limit_direction="both").T
    c = pd.concat([c.iloc[:, -2:], c, c.iloc[:, :2]], axis=1).T.rolling(5, center=True).mean().T
    return c.iloc[:, 2:-2].set_axis(range(1, 53), axis=1)


def main():
    splits = json.loads((DS / "splits.json").read_text())
    full = build_panel()
    st = head_stats(full, pd.Timestamp(splits["train"][0]))
    m = full.drop_duplicates("code_bss").set_index("code_bss")[["mu", "sd"]].join(st).dropna()
    assert np.allclose(m["mu"], m["mean"]) and np.allclose(m["sd"], m["std"]), "R1 statistics"
    print(f"  1. R1: mu and sd of {len(m)} wells are their 2005-2019 head statistics")

    wells = pd.read_parquet(DS / "wells.parquet").set_index("code_bss")
    for name, start in R3_STARTS.items():
        P = build_panel(train_start=start)
        st = head_stats(P, pd.Timestamp(start))
        m = P.drop_duplicates("code_bss").set_index("code_bss")[["mu", "sd"]].join(st).dropna()
        assert np.allclose(m["mu"], m["mean"]) and np.allclose(m["sd"], m["std"]), f"{name} mu/sd"
        clim = climatology(P, pd.Timestamp(start))
        woy = P["week"].dt.isocalendar().week.clip(upper=52).astype(int)
        got = P.assign(woy=woy).drop_duplicates(["code_bss", "woy"]).set_index(["code_bss", "woy"])["clim_z"]
        want = clim.stack().rename("want")
        j = pd.concat([got, want], axis=1, join="inner").dropna()
        assert np.allclose(j["clim_z"], j["want"]), f"{name}: climatology not from the window"
        art = P.drop_duplicates("code_bss").set_index("code_bss")["pct_days_artesian"]
        ref = wells[f"pct_days_artesian_{name}"].reindex(art.index)
        assert np.allclose(art.fillna(-1), ref.fillna(-1)), f"{name}: artesian share"
        kept = set(P.loc[P["mu"].notna(), "code_bss"])
        dropped = sorted(set(full.loc[full["mu"].notna(), "code_bss"]) - kept)
        assert not wells.loc[dropped, "core"].any(), f"{name}: a core well leaves the regime"
        both = full[full["mu"].notna() & full["code_bss"].isin(kept)]
        mean_w, _ = lstm.input_stats(P[P["mu"].notna()])
        mean_f, _ = lstm.input_stats(both)
        forcing_cols = [c for c in mean_f.index if c in lstm.DYNAMIC]
        assert np.allclose(mean_w[forcing_cols], mean_f[forcing_cols]), \
            f"{name}: the forcing standardisation should keep the whole training period"
        core = P[P["core"]]
        n = (core[(core["split"] == "train") & (core["week"] >= start)]
             .groupby("code_bss")["head"].count().reindex(core["code_bss"].unique()).fillna(0))
        assert (n >= MIN_WINDOW_WEEKS).all(), f"{name}: wells without enough history {n[n < 52]}"
        short = n[n < 104]
        print(f"  2. {name} (from {start}): mu, sd, climatology and artesian share from the window; "
              f"forcing standardisation from 2005; core wells {len(n)}, observed weeks min "
              f"{int(n.min())} median {int(n.median())}; under two years: "
              + (", ".join(f"{c} ({int(v)})" for c, v in short.items()) or "none")
              + f"; non-core wells without heads in the window: {', '.join(dropped) or 'none'}")

        codes, weeks, _, _, split, *_ = lstm.arrays(P[P["mu"].notna()])
        tm, keep = lstm.regime_masks(split, weeks, codes, train_start=start)
        assert not tm[:, weeks < np.datetime64(start)].any(), f"{name}: trains before the window"
    folds = splits["leave_wells_out"]["fold_of_well"]
    codes, weeks, _, _, split, *_ = lstm.arrays(full[full["mu"].notna()])
    for k in range(5):
        tm, keep = lstm.regime_masks(split, weeks, codes, fold=k)
        held = np.array([folds.get(c, -1) == k for c in codes])
        assert not tm[held].any() and not keep[held].any() and keep[~held].all(), f"fold {k}"
    tm, _ = lstm.regime_masks(split, weeks, codes, refit=True)
    assert tm[split == "validation"].all() and not tm[split == "test"].any()
    print("  3. masks: no week before an R3 window, no week or early stopping on a held-out "
          "fold, the refit adds validation and never test")
    print("test_regime_boundaries: all checks passed")


if __name__ == "__main__":
    main()
