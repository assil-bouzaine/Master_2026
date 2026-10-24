"""The weekly pumping keeps the annual volumes, layer by layer (third review §6).

    PFE_DATASET=v4 python -m tests.test_pumping_conservation

Layers (docs/review_codex_2026-10-24.md §6: "conservation of declared totals and
reconstructed annual totals ... at their respective layers, including December/January
weekly boundaries"):
    declared   BNPE rows as published (the KG keeps them as declared: tests/test_kg.py)
    annual     src.dataset.bnpe_v3.harmonise: completed, harmonised and imputed by rule
    weekly     the dataset's pumping_weekly.parquet: each annual volume spread over the
               weeks whose label (week ending on Sunday) falls in that calendar year
Checks, without fitting anything (about a minute):
1. Cold rebuild: the weekly table rebuilt from the raw BNPE snapshot and the stored
   forcings equals the stored file.
2. Declared -> annual: a reported row (imputation '') keeps its declared volume; rule 1
   relabels the usage of some rows, so the check is per ouvrage and year, over its uses.
3. Annual -> weekly, seasonal uses (irrigation, canals): the weeks of a complete year sum
   to its annual volume.
4. Annual -> weekly, flat uses (drinking water, industry, energy): every week gets
   7/365.25 of the annual volume, so a year keeps 52 x 7/365.25 = 0.9966 or
   53 x 7/365.25 = 1.0157 of it, by its number of week labels. Measured here, not fixed in
   v4: a year with 53 week labels (2006, 2012, 2017, 2023) carries 1.9 % more flat
   pumping than one with 52. Every model sees the same input, so comparisons are not
   biased; the annual accounting of CQ12 uses the declared layer, never these sums.
"""
import numpy as np
import pandas as pd

from src.analysis.bnpe_profile import load as load_bnpe
from src.config import DATASET_DIR
from src.dataset import build
from src.dataset.bnpe_v3 import harmonise, restricted_years

SEASONAL = ("irrigation", "canals")
FLAT = 7 / 365.25


def week_counts(weeks):
    w = pd.Series(pd.to_datetime(weeks).unique())
    return w.groupby(w.dt.year).size()


def main():
    assert build.CFG.get("bnpe_rules") == "v3", "checks the v3/v4 pumping rules"
    forcing = pd.read_parquet(DATASET_DIR / "forcing_weekly.parquet",
                              columns=["cell_id", "week", "ETP", "rain"])
    pts, out, _ = build.build_pumping(forcing)
    stored = pd.read_parquet(DATASET_DIR / "pumping_weekly.parquet")
    key = ["code_ouvrage", "usage", "week"]
    a = out.sort_values(key).reset_index(drop=True)
    b = stored.sort_values(key).reset_index(drop=True)
    assert len(a) == len(b) and (a[key] == b[key]).all().all(), "rebuilt rows differ"
    assert np.allclose(a["volume_m3"], b["volume_m3"], rtol=1e-12, atol=1e-9), "volumes differ"
    assert (a["imputation"].fillna("") == b["imputation"].fillna("")).all()
    print(f"  1. cold rebuild: {len(a):,} weekly rows equal the stored file")

    # the annual layer, exactly as build_pumping_v3 computes it
    d = load_bnpe(build.CFG["bnpe_snapshot"])
    end_year = int(forcing["week"].max().year)
    annual, _ = harmonise(d, restricted_years(), int(build.MODEL_START[:4]) - 2, end_year,
                          pts.set_index("code_ouvrage")["zone"])
    annual = annual[annual["code_ouvrage"].isin(pts["code_ouvrage"])]
    rep = annual[annual["imputation"] == ""]
    decl = (d[d["code_ouvrage"].isin(rep["code_ouvrage"])]
            .groupby(["code_ouvrage", "annee"])["volume"].sum())
    got = rep.groupby(["code_ouvrage", "annee"])["volume"].sum()
    j = pd.concat([got.rename("annual"), decl.rename("declared")], axis=1).dropna()
    assert len(j) == len(got), "reported rows without a declaration"
    rel = (j["annual"] - j["declared"]).abs() / j["declared"].abs().clip(lower=1.0)
    assert rel.max() < 1e-9, rel.sort_values().tail()
    print(f"  2. declared -> annual: {len(j):,} reported ouvrage-years keep their declared volume")

    s = stored.assign(annee=stored["week"].dt.year)
    wk = s.groupby(["code_ouvrage", "usage", "annee"])["volume_m3"].sum()
    an = annual.set_index(["code_ouvrage", "usage", "annee"])["volume"]
    an = an.groupby(level=[0, 1, 2]).sum()
    m = pd.concat([wk.rename("weekly"), an.rename("annual")], axis=1).dropna()
    m = m[m["annual"] > 0]
    last_week = s["week"].max()
    partial = last_week.year if last_week < pd.Timestamp(last_week.year, 12, 24) else None
    yrs = m.index.get_level_values("annee")
    seasonal = m.index.get_level_values("usage").isin(SEASONAL)
    ratio = m["weekly"] / m["annual"]
    full = yrs != partial
    err = (ratio[seasonal & full] - 1).abs()
    assert err.max() < 1e-9, err.sort_values().tail()
    print(f"  3. seasonal uses: {int((seasonal & full).sum()):,} ouvrage-years sum to their "
          f"annual volume (max relative error {err.max():.1e})")

    n_weeks = week_counts(s["week"])
    expect = pd.Series(yrs, index=m.index).map(n_weeks) * FLAT
    flat = ~seasonal & full
    dev = (ratio[flat] - expect[flat]).abs()
    assert dev.max() < 1e-9, dev.sort_values().tail()
    long_years = sorted(int(y) for y in n_weeks[n_weeks == 53].index if 2005 <= y <= end_year)
    print(f"  4. flat uses: {int(flat.sum()):,} ouvrage-years keep 52 x 7/365.25 = "
          f"{52 * FLAT:.4f} or 53 x 7/365.25 = {53 * FLAT:.4f} of their annual volume "
          f"(53-week years since 2005: {long_years})")
    print("test_pumping_conservation: all checks passed")


if __name__ == "__main__":
    main()
