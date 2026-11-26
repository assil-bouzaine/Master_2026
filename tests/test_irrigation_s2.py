"""Unit and real-data tests for the CQ15 Sentinel-2 probable-irrigation rule (src/dataset/irrigation_s2.py).

    PFE_DATASET=v5 python -m tests.test_irrigation_s2

1. CQ15 synthetic acceptance cases: high NDVI + dry + valid quality -> positive; fewer than 4 pixels
   or fewer than 3 acquisitions (or missing values) -> insufficient_data; high NDVI + wet ->
   not_applicable; low NDVI + dry -> negative; boundary cases and sensitivity variants.
2. Otsu threshold on synthetic bimodal samples lands cleanly between the two modes.
3. No test leakage: altering every 2020+ row leaves the training-frozen TAU unchanged (checked both
   synthetically and on the real parcel table).
4. Per-well clipped share on a hand-made zone with two parcels (one half inside) equals the exact
   hand calculation; zones with only unclassified/missing parcels yield NaN share (never 0), and
   the "train" row equals the 2017-2019 mean (ignoring 2020+).
5. Real v5 outputs: every well of wells.parquet has 2017-2025 + "train" rows, share_positive and
   coverage lie in [0, 1] or NaN, "train" equals the 2017-2019 mean, rule.json matches recomputed
   TAU and is invariant to 2020+ perturbations, and SWI_JA matches forcing_weekly.parquet.
"""
import json

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

from src.config import CRS_L93, DATASET, DATASET_DIR, INTERIM, ROOT
from src.dataset.irrigation_s2 import (
    MIN_OBS,
    MIN_PX,
    STATUSES,
    SWI_DRY,
    TRAIN_YEARS,
    YEARS,
    add_train_summary_rows,
    classify_parcels,
    fit_otsu_tau,
    otsu_threshold,
    summer_swi,
    validate_census_2020,
    well_clipped_status_areas,
)


def test_cq15_acceptance():
    tau = 0.50
    df = pd.DataFrame({
        "year": [2020] * 11,
        "ID_PARCEL": [f"P{i}" for i in range(11)],
        "ndvi_summer": [0.72, 0.72, 0.72, np.nan, 0.72, 0.72, 0.25, 0.50, 0.499, 0.47, 0.52],
        "ndmi_summer": [0.15, 0.15, 0.15, 0.15, 0.15, 0.15, -0.10, -0.05, 0.10, 0.10, np.nan],
        "n_px_summer": [10, 2, 10, 10, 10, 10, 10, MIN_PX, 10, 10, 10],
        "nobs_summer": [8.0, 8.0, 2.0, 8.0, 8.0, 8.0, 8.0, float(MIN_OBS), 8.0, 8.0, 8.0],
        "SWI_JA": [0.25, 0.25, 0.25, 0.25, np.nan, 0.60, 0.25, SWI_DRY, 0.25, 0.25, 0.25],
    })
    out = classify_parcels(df, tau=tau)
    got = out["status"].tolist()
    expected = [
        "positive",           # P0: high NDVI + dry + enough pixels & obs
        "insufficient_data",  # P1: 2 pixels (< 4)
        "insufficient_data",  # P2: 2 acquisitions (< 3)
        "insufficient_data",  # P3: missing NDVI
        "insufficient_data",  # P4: missing SWI_JA
        "not_applicable",     # P5: high NDVI + wet (SWI_JA = 0.60 > 0.5)
        "negative",           # P6: low NDVI + dry
        "positive",           # P7: exact inclusive boundaries (px=4, obs=3, SWI=0.5, NDVI=TAU)
        "negative",           # P8: just below TAU
        "negative",           # P9: 0.47 < 0.50 (positive under TAU - 0.05 = 0.45)
        "positive",           # P10: 0.52 >= 0.50 (negative under TAU + 0.05 = 0.55; insufficient under NDMI)
    ]
    assert got == expected, f"status mismatch:\n  got:      {got}\n  expected: {expected}"

    # Sensitivity variants
    assert out.loc[9, "status_tau_minus"] == "positive"
    assert out.loc[10, "status_tau_plus"] == "negative"
    assert out.loc[0, "status_ndmi"] == "positive"
    assert out.loc[7, "status_ndmi"] == "negative"           # ndmi = -0.05 < 0
    assert out.loc[10, "status_ndmi"] == "insufficient_data"  # missing ndmi
    assert out.loc[5, "status_ndmi"] == "not_applicable"
    print("  1. CQ15 synthetic acceptance cases (quality, dry/wet, boundaries, variants): OK")


def test_otsu_bimodal():
    rng = np.random.default_rng(42)
    low_mode = rng.normal(0.25, 0.05, size=3000)
    high_mode = rng.normal(0.75, 0.05, size=3000)
    sample = np.concatenate([low_mode, high_mode])
    tau = otsu_threshold(sample)
    assert 0.45 <= tau <= 0.55, f"Otsu on bimodal (0.25, 0.75) landed at {tau}"

    # Exact two-point split: midpoint of the empty gap between 0.20 and 0.70
    two_pts = np.array([0.20] * 100 + [0.70] * 100)
    tau_gap = otsu_threshold(two_pts)
    assert 0.40 <= tau_gap <= 0.50, f"Otsu on two-point bimodal landed at {tau_gap}"
    print(f"  2. Otsu bimodal check: Gaussian modes (0.25, 0.75) -> TAU={tau:.4f}; "
          f"gap (0.20, 0.70) -> TAU={tau_gap:.4f}: OK")


def test_tau_no_test_leakage():
    rng = np.random.default_rng(7)
    rows = []
    for y in YEARS:
        n = 400
        ndvi = np.concatenate([rng.normal(0.28, 0.05, n // 2), rng.normal(0.70, 0.06, n // 2)])
        rows.append(pd.DataFrame({
            "year": y,
            "ndvi_summer": ndvi,
            "n_px_summer": 20,
            "nobs_summer": 10.0,
            "SWI_JA": 0.25,
        }))
    base = pd.concat(rows, ignore_index=True)
    tau_base = fit_otsu_tau(base)

    # Alter every 2020+ row radically (high NDVI, low NDVI, and dropped)
    hi = base.copy()
    hi.loc[hi["year"] >= 2020, ["ndvi_summer", "SWI_JA", "n_px_summer", "nobs_summer"]] = [0.98, 0.01, 500, 30.0]
    lo = base.copy()
    lo.loc[lo["year"] >= 2020, "ndvi_summer"] = -0.15
    tr_only = base[base["year"].isin(TRAIN_YEARS)].copy()

    assert fit_otsu_tau(hi) == tau_base
    assert fit_otsu_tau(lo) == tau_base
    assert fit_otsu_tau(tr_only) == tau_base
    print(f"  3. No 2020+ leakage into TAU (synthetic TAU={tau_base:.4f} invariant to 2020+ edits): OK")


def test_well_share_hand_calc():
    buffers = gpd.GeoDataFrame(
        {"code_bss": ["W_MAIN", "W_PARTIAL", "W_WET", "W_EMPTY"]},
        geometry=[
            box(0, 0, 1000, 1000),       # 100 ha zone
            box(2000, 0, 3000, 1000),    # 100 ha zone
            box(4000, 0, 5000, 1000),    # 100 ha zone
            box(6000, 0, 7000, 1000),    # empty zone
        ],
        crs=CRS_L93,
    )
    # W_MAIN: P1 (positive) 400x500 m = 20 ha fully inside;
    #         P2 (negative) 400x500 m = 20 ha, half inside (x in [800, 1000]) -> 10 ha inside.
    #         Expected share_positive = 20 / (20 + 10) = 2/3, coverage = 1.0.
    # W_PARTIAL: 10 ha positive + 10 ha insufficient_data -> share_positive = 1.0, coverage = 0.5.
    # W_WET: 10 ha not_applicable only -> share_positive = NaN, coverage = 0.0.
    # W_EMPTY: no parcels -> share_positive = NaN, coverage = NaN.
    parcels = gpd.GeoDataFrame(
        {"status": ["positive", "negative", "positive", "insufficient_data", "not_applicable"]},
        geometry=[
            box(0, 0, 400, 500),
            box(800, 0, 1200, 500),
            box(2000, 0, 2200, 500),
            box(2300, 0, 2500, 500),
            box(4000, 0, 4200, 500),
        ],
        crs=CRS_L93,
    )
    codes = buffers["code_bss"].tolist()
    res = well_clipped_status_areas(parcels, buffers, codes).set_index("code_bss")

    assert np.isclose(res.loc["W_MAIN", "area_positive_ha"], 20.0)
    assert np.isclose(res.loc["W_MAIN", "area_negative_ha"], 10.0)
    assert np.isclose(res.loc["W_MAIN", "area_classified_ha"], 30.0)
    assert np.isclose(res.loc["W_MAIN", "area_total_ha"], 30.0)
    assert np.isclose(res.loc["W_MAIN", "share_positive"], 2.0 / 3.0)
    assert np.isclose(res.loc["W_MAIN", "coverage"], 1.0)

    assert np.isclose(res.loc["W_PARTIAL", "share_positive"], 1.0)
    assert np.isclose(res.loc["W_PARTIAL", "coverage"], 0.5)

    assert np.isnan(res.loc["W_WET", "share_positive"])
    assert np.isclose(res.loc["W_WET", "coverage"], 0.0)
    assert np.isclose(res.loc["W_WET", "area_not_applicable_ha"], 10.0)

    assert np.isnan(res.loc["W_EMPTY", "share_positive"])
    assert np.isnan(res.loc["W_EMPTY", "coverage"])
    assert np.isclose(res.loc["W_EMPTY", "area_total_ha"], 0.0)

    # Check train summary row across 2017-2020 (2020 must not affect "train")
    y17 = res.reset_index().assign(year="2017")
    y18 = res.reset_index().assign(year="2018")
    y19 = res.reset_index().assign(year="2019")
    y18.loc[y18["code_bss"] == "W_MAIN", "share_positive"] = 0.5
    y19.loc[y19["code_bss"] == "W_MAIN", "share_positive"] = 0.25
    y20 = res.reset_index().assign(year="2020")
    y20.loc[y20["code_bss"] == "W_MAIN", "share_positive"] = 0.99
    full = add_train_summary_rows(pd.concat([y17, y18, y19, y20], ignore_index=True))
    tr = full[full["year"] == "train"].set_index("code_bss")
    expected_train_main = (2.0 / 3.0 + 0.5 + 0.25) / 3.0
    assert np.isclose(tr.loc["W_MAIN", "share_positive"], expected_train_main)
    assert np.isnan(tr.loc["W_WET", "share_positive"])
    assert np.isnan(tr.loc["W_EMPTY", "share_positive"])
    print("  4. Hand-made zone clipped share (20 ha pos + 10 ha neg half-inside -> 2/3; "
          "unclassified -> NaN; train mean excludes 2020): OK")


def test_real_data():
    parcels_path = INTERIM / f"irrigation_s2_parcels_{DATASET}.parquet"
    wells_out_path = DATASET_DIR / "irrigation_s2_wells.parquet"
    rule_path = DATASET_DIR / "irrigation_s2_rule.json"
    doc_path = ROOT / "docs" / "irrigation_s2.md"

    for path in (parcels_path, wells_out_path, rule_path, doc_path):
        assert path.exists(), f"missing output: {path} (run PFE_DATASET={DATASET} python -m src.dataset.irrigation_s2)"

    wells_ref = pd.read_parquet(DATASET_DIR / "wells.parquet")
    parcels = pd.read_parquet(parcels_path)
    well_tbl = pd.read_parquet(wells_out_path)
    rule = json.loads(rule_path.read_text(encoding="utf-8"))

    # Rule JSON and no-leakage check on real data
    assert rule["MIN_PX"] == MIN_PX and rule["MIN_OBS"] == MIN_OBS and rule["SWI_DRY"] == SWI_DRY
    assert tuple(rule["train_editions"]) == TRAIN_YEARS
    otsu = rule["otsu_summary"]
    assert sum(b["count"] for b in otsu["coarse_bins_005"]) == otsu["n_train_classified_dry"]
    tau = float(rule["TAU"])
    assert fit_otsu_tau(parcels) == tau
    mutated = parcels.copy()
    mutated.loc[mutated["year"] >= 2020, ["ndvi_summer", "SWI_JA", "n_px_summer", "nobs_summer"]] = [0.99, 0.01, 999, 50.0]
    assert fit_otsu_tau(mutated) == tau, "TAU changed when 2020+ rows were altered!"

    # Parcel table integrity
    assert not parcels.duplicated(["year", "ID_PARCEL"]).any()
    for col in ("status", "status_tau_minus", "status_tau_plus", "status_ndmi"):
        assert set(parcels[col].unique()).issubset(set(STATUSES)), (col, parcels[col].unique())
    assert set(parcels["year"].unique()) == set(YEARS)

    # Independent SWI_JA spot check against forcing_weekly.parquet
    forcing = pd.read_parquet(DATASET_DIR / "forcing_weekly.parquet", columns=["cell_id", "week", "SWI"])
    swi_ref = summer_swi(forcing).set_index(["cell_id", "year"])["SWI_JA"]
    sample = parcels.drop_duplicates(["cell_id", "year"]).head(10)
    for _, row in sample.iterrows():
        want = float(swi_ref.loc[(row["cell_id"], int(row["year"]))])
        assert np.isclose(float(row["SWI_JA"]), want, rtol=0, atol=1e-12)

    # Per-well table checks
    expected_wells = set(wells_ref["code_bss"])
    expected_years = {str(y) for y in YEARS} | {"train"}
    assert set(well_tbl["code_bss"]) == expected_wells
    assert len(well_tbl) == len(expected_wells) * len(expected_years)
    assert not well_tbl.duplicated(["code_bss", "year"]).any()
    for code, grp in well_tbl.groupby("code_bss"):
        assert set(grp["year"]) == expected_years, code

    sp = well_tbl["share_positive"].to_numpy(dtype=float)
    cov = well_tbl["coverage"].to_numpy(dtype=float)
    assert np.all(np.isnan(sp) | ((sp >= 0.0) & (sp <= 1.0))), "share_positive outside [0, 1]"
    assert np.all(np.isnan(cov) | ((cov >= 0.0) & (cov <= 1.0))), "coverage outside [0, 1]"

    annual = well_tbl[well_tbl["year"] != "train"]
    for st in STATUSES:
        assert (annual[f"area_{st}_ha"] >= 0.0).all()
    assert np.allclose(annual["area_classified_ha"], annual["area_positive_ha"] + annual["area_negative_ha"])
    assert np.allclose(
        annual["area_total_ha"],
        sum(annual[f"area_{st}_ha"] for st in STATUSES),
    )

    # "train" row equals mean of 2017-2019 for every well
    train_keys = {str(y) for y in TRAIN_YEARS}
    tr_means = well_tbl[well_tbl["year"].isin(train_keys)].groupby("code_bss")["share_positive"].mean()
    tr_rows = well_tbl[well_tbl["year"] == "train"].set_index("code_bss")["share_positive"]
    for code in expected_wells:
        a, b = float(tr_rows.loc[code]), float(tr_means.loc[code])
        if np.isnan(b):
            assert np.isnan(a), (code, a, b)
        else:
            assert np.isclose(a, b, rtol=1e-12, atol=1e-12), (code, a, b)

    # Validation verdict matches recomputation and doc contains it
    verdict, _ = validate_census_2020(parcels)
    assert verdict == rule["validation_2020"]["verdict"]
    doc_text = doc_path.read_text(encoding="utf-8")
    assert "do not edit by hand" in doc_text.lower()
    assert verdict in doc_text
    assert f"{tau:.4f}" in doc_text

    n_nan = int(tr_rows.isna().sum())
    print(f"  5. Real data ({DATASET}): {len(parcels):,} parcel-years, {len(expected_wells)} wells x 10 rows, "
          f"TAU={tau:.4f} (no 2020+ leakage), verdict={verdict}, NaN train shares={n_nan}: OK")


def main():
    test_cq15_acceptance()
    test_otsu_bimodal()
    test_tau_no_test_leakage()
    test_well_share_hand_calc()
    test_real_data()
    print("test_irrigation_s2: all checks passed")


if __name__ == "__main__":
    main()
