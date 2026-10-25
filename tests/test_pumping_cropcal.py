"""Pumping reconstruction (3): irrigation re-spread by a fixed crop calendar.

    PFE_DATASET=v4 python -m tests.test_pumping_cropcal

1. Synthetic: the climatology ignores weather after the training years, so the weights
   cannot depend on a test year's weather; weights sum to 1 over each calendar year; a
   cell without irrigable crops takes the département-wide mix and is flagged.
2. The built output, if present (data are not in git): the weights of reconstruction (1)
   (src.dataset.build.spread_weights, moved out of build_pumping_v3 on 2026-10-25)
   reproduce the dataset's weekly table, i.e. the annual volume recovered from each week
   is the same within a year; every annual irrigation volume of a complete year is kept
   (the unfinished year differs: each method gives the weeks so far its own share of the
   year); other uses are unchanged; within a year, irrigation follows the climatic deficit
   less than in (1).
"""
import numpy as np
import pandas as pd

from src.config import DATASET, DATASET_DIR
from src.dataset.crop_demand import load_classes
from src.dataset.pumping_cropcal import (OUT, annual_volumes, climatology, cropcal_weights,
                                         week_of_year)


def synthetic_forcing(seed=0):
    weeks = pd.date_range("2016-01-03", "2023-12-31", freq="W-SUN")
    rng = np.random.default_rng(seed)
    rows = []
    for cell in ("A", "B"):
        etp = 20 + 15 * np.sin(2 * np.pi * (week_of_year(weeks) - 13) / 52) + rng.normal(0, 2, len(weeks))
        rows.append(pd.DataFrame({"cell_id": cell, "week": weeks, "ETP": etp.clip(1),
                                  "rain": rng.gamma(1.0, 10.0, len(weeks))}))
    return pd.concat(rows, ignore_index=True)


def check_synthetic(classes):
    f = synthetic_forcing()
    g = f.copy()
    late = g["week"].dt.year > 2019
    g.loc[late, "rain"] = 0.0  # a different post-training weather ...
    assert climatology(f).equals(climatology(g))  # ... leaves the climatology unchanged
    mix = pd.DataFrame({2016: [100.0, 50.0], 2023: [80.0, 60.0]},
                       index=pd.MultiIndex.from_tuples([("A", "vine"), ("A", "orchard_deciduous")],
                                                       names=["cell_id", "crop_class"]))
    w = cropcal_weights(["A", "B"], [2017, 2021, 2022], mix, climatology(f), classes)
    s = w.groupby(["cell_id", "year"])["w_crop"].sum()
    assert np.allclose(s, 1.0), s
    assert w.loc[w["cell_id"] == "B", "cropcal_fallback"].all()
    assert not w.loc[w["cell_id"] == "A", "cropcal_fallback"].any()
    # the crop calendar: almost nothing in winter, most of the year's water in summer
    month = w.loc[w["cell_id"] == "A"].groupby(w["week"].dt.month)["w_crop"].sum() / w.loc[w["cell_id"] == "A", "year"].nunique()
    assert month.loc[[12, 1, 2]].sum() < 0.01 and month.loc[[6, 7, 8]].sum() > 0.5, month.round(3).to_dict()


def check_built():
    if not OUT.exists():
        print(f"  {OUT.name} absent: real-data checks skipped")
        return
    pw = pd.read_parquet(DATASET_DIR / "pumping_weekly.parquet")
    pts = pd.read_parquet(DATASET_DIR / "pumping_points.parquet")
    forcing = pd.read_parquet(DATASET_DIR / "forcing_weekly.parquet", columns=["cell_id", "week", "ETP", "rain"])
    _, spread = annual_volumes(pw, pts, forcing)
    assert spread < 1e-6, f"reconstruction (1) weights do not reproduce the table: spread {spread}"
    p3 = pd.read_parquet(OUT)
    assert len(p3) == len(pw) and (p3[["code_ouvrage", "usage", "week"]] == pw[["code_ouvrage", "usage", "week"]]).all().all()
    other = pw["usage"] != "irrigation"
    assert (p3.loc[other, "volume_m3"] == pw.loc[other, "volume_m3"]).all(), "other uses changed"
    last = pw["week"].max()
    full = pw["week"].dt.year < last.year
    irr = (pw["usage"] == "irrigation") & full
    k = [pw.loc[irr, "code_ouvrage"], pw.loc[irr, "week"].dt.year]
    v1 = pw.loc[irr, "volume_m3"].groupby(k).sum()
    v3 = p3.loc[irr, "volume_m3"].groupby(k).sum()
    assert np.allclose(v1, v3, rtol=1e-9, atol=1e-6), "annual irrigation volumes not kept"
    # within-year link with the climatic deficit (April-October, plain-wide)
    plain = pts.loc[pts["zone"] == "plain", "code_ouvrage"]
    f = forcing.assign(deficit=(forcing["ETP"] - forcing["rain"]).clip(lower=0)).groupby("week")["deficit"].mean()

    def mean_r(p):
        s = p[(p["usage"] == "irrigation") & p["code_ouvrage"].isin(plain)].groupby("week")["volume_m3"].sum()
        d = pd.DataFrame({"v": s, "def": f.reindex(s.index)})
        d = d[d.index.month.isin(range(4, 11)) & (d.index.year < last.year)]
        return d.groupby(d.index.year).apply(lambda t: t["v"].corr(t["def"])).mean()

    r1, r3 = mean_r(pw), mean_r(p3)
    assert r3 < r1, (r1, r3)
    print(f"  built: annual volumes kept; mean within-year r(irrigation, deficit), April-October: "
          f"reconstruction 1 = {r1:.2f}, reconstruction 3 = {r3:.2f}")


def main():
    classes = load_classes()
    check_synthetic(classes)
    print("synthetic checks passed")
    check_built()
    print("test_pumping_cropcal: OK")


if __name__ == "__main__":
    main()
