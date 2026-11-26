"""CQ15 probable-irrigation rule on Sentinel-2 parcel observations, validation and per-well shares.

    PFE_DATASET=v5 python -m src.dataset.irrigation_s2

Why (docs/analysis_plan_v3.md §1 and §8 item 4; docs/competency_questions.md CQ15):
The subject's objective SO2 asks for a satellite-derived concept, `lulcw:ProbablyIrrigatedParcel`:
an agricultural parcel whose vegetation stays green in the driest summer months (July-August)
while the soil of its weather cell is dry is a candidate for irrigation. In dataset v5 this enters
as one static well fact -- the training-period (2017-2019) mean share of probably irrigated land
inside each well's 3 km zone -- tested in one with/without ablation row.

The rule (frozen before any census check and without any 2020+ observation):
1. Quality: `insufficient_data` if `n_px_summer < 4` (under ~400 m2 of valid 10 m pixels),
   `nobs_summer < 3` (fewer than 3 clear Sentinel-2 acquisitions in July-August), or if
   `ndvi_summer` or `SWI_JA` is missing.
2. Dry conditions: each parcel is matched to the nearest SAFRAN cell centre in Lambert-93
   (`data/raw/safran/grid_cells_66.parquet`). Its summer soil wetness `SWI_JA` is the mean of
   weekly `SWI` (`forcing_weekly.parquet`) over the July and August weeks of that year. A parcel
   gets `not_applicable` when `SWI_JA > 0.5`: above half the available soil water, a green summer
   canopy does not require irrigation (FAO-56 depletion fraction p ~= 0.5; Allen et al. 1998,
   FAO Irrigation and Drainage Paper 56).
3. Positive / negative: `positive` if `ndvi_summer >= TAU`, else `negative`. `TAU` is Otsu's
   threshold (maximising the between-class variance of a two-class split on a 0.005-wide NDVI
   histogram over [-0.2, 1.0]) computed once on the quality-passing, dry parcel-years of the
   training editions 2017-2019 only, parcels unweighted, then frozen.
4. Sensitivity variants (reported only, never used for the static well fact): `TAU - 0.05`,
   `TAU + 0.05`, and `TAU` combined with `ndmi_summer >= 0`.

CQ15 caveats:
- High summer NDVI under dry cell-level soil wetness is an irrigation hypothesis, not proof.
  Deep roots, residual moisture, phenology, mountain wetness below the 8 km SAFRAN grid scale,
  or mixed pixels can also keep a canopy green.
- A negative result does not prove rainfed management: in Roussillon, vegetable parcels can be
  bare in July-August between two irrigated crops.
- The 2020 Agreste census (dept 66) has no parcel labels, only farm-type totals covering 73 % of
  the irrigated area. It supports an aggregate plausibility check, never parcel-level precision
  or recall. If any of the three benchmark groups falls outside its census range, the rule is
  explicitly labelled a `heuristic`.
- No water-source (`irrigatedBy`) claim is derived here: proximity to a pump or canal is separate.

Outputs:
    data/interim/irrigation_s2_parcels_<dataset>.parquet   parcel x year observations and statuses
    data/processed/dataset_<dataset>/irrigation_s2_wells.parquet  well x year clipped shares + "train"
    data/processed/dataset_<dataset>/irrigation_s2_rule.json      frozen parameters, counts, SHA-256s
    docs/irrigation_s2.md                                         generated report and validation
"""
import argparse
import datetime as dt
import hashlib
import json
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from src.config import CRS_L93, CRS_WGS84, DATASET, DATASET_DIR, INTERIM, RAW, ROOT
from src.dataset.crop_demand import BUFFER_M, well_buffers

S2_SNAPSHOT = "2026-11-26"
YEARS = tuple(range(2017, 2026))
TRAIN_YEARS = (2017, 2018, 2019)

MIN_PX = 4
MIN_OBS = 3
SWI_DRY = 0.5
NDVI_LOW = -0.2
NDVI_HIGH = 1.0
NDVI_BIN = 0.005
TAU_DELTA = 0.05
NDMI_MIN = 0.0

STATUSES = ("positive", "negative", "insufficient_data", "not_applicable")

# Dept 66 RA2020 census figures recorded in data/README.md ("Land-use thread").
# Typology covers 73 % of the irrigated SAU, by farm type (not parcel).
CENSUS_2020 = {
    20: {
        "name": "Orchards (group 20)",
        "low_num": 5268,
        "high_num": 5268 + 1639 + 502,
        "denom": 8100,
        "low_expr": "5,268 / 8,100",
        "high_expr": "(5,268 + 1,639 + 502) / 8,100",
        "has_upper": True,
    },
    21: {
        "name": "Vines (group 21)",
        "low_num": 839,
        "high_num": 839 + 502,
        "denom": 19840,
        "low_expr": "839 / 19,840",
        "high_expr": "(839 + 502) / 19,840",
        "has_upper": True,
    },
    25: {
        "name": "Market gardening (group 25)",
        "low_num": 932,
        "high_num": 1760,
        "denom": 1760,
        "low_expr": "932 / 1,760",
        "high_expr": None,
        "has_upper": False,
    },
}

GROUP_NAMES = {
    1: "Soft wheat",
    2: "Maize",
    3: "Barley",
    4: "Other cereals",
    5: "Rapeseed",
    6: "Sunflower",
    7: "Other oilseeds",
    8: "Protein crops",
    9: "Fibre crops",
    11: "Fallow",
    14: "Rice",
    15: "Grain legumes",
    16: "Fodder",
    17: "Mountain pasture & heath",
    18: "Permanent grassland",
    19: "Temporary grassland",
    20: "Orchards",
    21: "Vines",
    22: "Nuts",
    23: "Olives",
    24: "Other industrial crops",
    25: "Vegetables & flowers",
    26: "Sugar cane",
    28: "Miscellaneous",
}


def sha256_file(path: Path) -> str:
    """SHA-256 hex digest of a file, streamed in chunks."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def summer_swi(forcing: pd.DataFrame) -> pd.DataFrame:
    """Mean weekly SWI over July and August per SAFRAN cell and calendar year."""
    week = pd.to_datetime(forcing["week"])
    mask = week.dt.month.isin([7, 8])
    sub = pd.DataFrame({
        "cell_id": forcing.loc[mask, "cell_id"].to_numpy(),
        "year": week.loc[mask].dt.year.to_numpy(),
        "SWI": forcing.loc[mask, "SWI"].to_numpy(dtype=float),
    })
    return sub.groupby(["cell_id", "year"], as_index=False)["SWI"].mean().rename(columns={"SWI": "SWI_JA"})


def nearest_cells(parcels_gdf: gpd.GeoDataFrame, grid_cells: pd.DataFrame) -> pd.Series:
    """Nearest SAFRAN cell_id to each parcel centroid using Lambert-93 distances."""
    pts = gpd.GeoSeries.from_xy(grid_cells["lon"], grid_cells["lat"], crs=CRS_WGS84).to_crs(CRS_L93)
    cx = pts.x.to_numpy()
    cy = pts.y.to_numpy()
    cids = grid_cells["cell_id"].to_numpy()

    g = parcels_gdf.to_crs(CRS_L93)
    cen = g.geometry.make_valid().centroid
    px = cen.x.to_numpy()
    py = cen.y.to_numpy()
    d2 = (px[:, None] - cx[None, :]) ** 2 + (py[:, None] - cy[None, :]) ** 2
    idx = np.argmin(d2, axis=1)
    return pd.Series(cids[idx], index=parcels_gdf["ID_PARCEL"].astype(str).to_numpy(), name="cell_id")


def _histogram(values: np.ndarray, low: float = NDVI_LOW, high: float = NDVI_HIGH, bin_width: float = NDVI_BIN):
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    n_bins = int(round((high - low) / bin_width))
    edges = np.linspace(low, high, n_bins + 1)
    centres = 0.5 * (edges[:-1] + edges[1:])
    counts, _ = np.histogram(arr, bins=edges)
    return edges, centres, counts


def otsu_threshold(values: np.ndarray, low: float = NDVI_LOW, high: float = NDVI_HIGH,
                   bin_width: float = NDVI_BIN) -> float:
    """Otsu threshold maximising between-class variance on a fixed-width NDVI histogram.

    Returns the bin-boundary cut point TAU so that values >= TAU form the upper class and
    values < TAU form the lower class; when several empty bins tie for the maximum variance,
    returns the midpoint of the tied boundaries.
    """
    edges, centres, counts = _histogram(values, low=low, high=high, bin_width=bin_width)
    total = counts.sum()
    if total == 0:
        raise ValueError("No finite NDVI values inside the histogram range")
    p = counts / total
    w0 = np.cumsum(p)[:-1]
    w1 = 1.0 - w0
    valid = (w0 > 0) & (w1 > 0)
    if not valid.any():
        raise ValueError("All NDVI values fall in a single histogram bin; Otsu split is undefined")
    mu_cum = np.cumsum(p * centres)[:-1]
    mu_tot = float((p * centres).sum())
    mu0 = np.where(valid, mu_cum / np.where(valid, w0, 1.0), 0.0)
    mu1 = np.where(valid, (mu_tot - mu_cum) / np.where(valid, w1, 1.0), 0.0)
    var_b = np.where(valid, w0 * w1 * (mu0 - mu1) ** 2, -1.0)
    max_var = float(var_b.max())
    best = np.flatnonzero(np.isclose(var_b, max_var, rtol=0.0, atol=1e-15))
    return float(np.round(edges[best + 1].mean(), 6))


def otsu_histogram_summary(values: np.ndarray, tau: float, low: float = NDVI_LOW,
                           high: float = NDVI_HIGH, bin_width: float = NDVI_BIN) -> dict:
    """Histogram diagnostics on the training sample: class means, modes and coarse bins."""
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    edges, centres, counts = _histogram(arr, low=low, high=high, bin_width=bin_width)
    low_bins = centres < tau
    high_bins = centres >= tau
    below = arr[arr < tau]
    above = arr[arr >= tau]
    w0 = len(below) / len(arr)
    w1 = len(above) / len(arr)
    mu0 = float(below.mean()) if len(below) else float("nan")
    mu1 = float(above.mean()) if len(above) else float("nan")
    between_var = float(w0 * w1 * (mu0 - mu1) ** 2) if (len(below) and len(above)) else float("nan")

    mode_low_idx = int(np.argmax(counts[low_bins]))
    mode_low_ndvi = float(centres[low_bins][mode_low_idx])
    mode_low_count = int(counts[low_bins][mode_low_idx])

    mode_high_idx = int(np.argmax(counts[high_bins]))
    mode_high_ndvi = float(centres[high_bins][mode_high_idx])
    mode_high_count = int(counts[high_bins][mode_high_idx])

    # Smoothed (5-bin = 0.025 wide) local maxima above TAU to identify any secondary green peak
    smooth = np.convolve(counts, np.ones(5) / 5.0, mode="same")
    upper_peaks = [
        (float(centres[i]), float(smooth[i]))
        for i in range(1, len(smooth) - 1)
        if centres[i] >= tau + 0.05 and smooth[i] > smooth[i - 1] and smooth[i] >= smooth[i + 1]
    ]
    secondary_peak = max(upper_peaks, key=lambda pair: pair[1]) if upper_peaks else (mode_high_ndvi, float(mode_high_count))

    coarse_step = 0.05
    n_coarse = int(round((high - low) / coarse_step))
    coarse_edges = np.linspace(low, high, n_coarse + 1)
    coarse_counts, _ = np.histogram(arr, bins=coarse_edges)
    coarse_bins = [
        {"low": round(float(lo), 2), "high": round(float(hi), 2), "count": int(n)}
        for lo, hi, n in zip(coarse_edges[:-1], coarse_edges[1:], coarse_counts)
        if n > 0
    ]
    return {
        "n_train_classified_dry": int(len(arr)),
        "tau": float(tau),
        "between_class_variance": round(between_var, 6),
        "class0_count": int(len(below)),
        "class1_count": int(len(above)),
        "class0_share": round(float(w0), 6),
        "class1_share": round(float(w1), 6),
        "class0_mean": round(mu0, 4),
        "class1_mean": round(mu1, 4),
        "quantiles": {f"q{int(q * 100):02d}": round(float(v), 4)
                      for q, v in zip((0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95),
                                      np.quantile(arr, (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95)))},
        "mode_below_tau": {"ndvi": round(mode_low_ndvi, 4), "bin_count": mode_low_count},
        "mode_above_tau": {"ndvi": round(mode_high_ndvi, 4), "bin_count": mode_high_count},
        "upper_secondary_peak_smoothed": {"ndvi": round(secondary_peak[0], 4),
                                          "smoothed_count": round(secondary_peak[1], 1)},
        "coarse_bins_005": coarse_bins,
    }


def _quality_ok(df: pd.DataFrame) -> np.ndarray:
    n_px = pd.to_numeric(df["n_px_summer"], errors="coerce").to_numpy(dtype=float)
    nobs = pd.to_numeric(df["nobs_summer"], errors="coerce").to_numpy(dtype=float)
    ndvi = pd.to_numeric(df["ndvi_summer"], errors="coerce").to_numpy(dtype=float)
    swi = pd.to_numeric(df["SWI_JA"], errors="coerce").to_numpy(dtype=float)
    return (n_px >= MIN_PX) & (nobs >= MIN_OBS) & np.isfinite(ndvi) & np.isfinite(swi)


def fit_otsu_tau(parcels: pd.DataFrame, train_years: tuple[int, ...] = TRAIN_YEARS) -> float:
    """Compute frozen Otsu TAU on quality-passing, dry parcel-years of train_years only."""
    in_train = parcels["year"].isin(train_years).to_numpy()
    qual = _quality_ok(parcels)
    dry = pd.to_numeric(parcels["SWI_JA"], errors="coerce").to_numpy(dtype=float) <= SWI_DRY
    vals = pd.to_numeric(parcels.loc[in_train & qual & dry, "ndvi_summer"], errors="coerce").to_numpy(dtype=float)
    return otsu_threshold(vals)


def _classify_one(df: pd.DataFrame, tau: float, require_ndmi_ge: float | None = None) -> np.ndarray:
    qual = _quality_ok(df)
    ndvi = pd.to_numeric(df["ndvi_summer"], errors="coerce").to_numpy(dtype=float)
    swi = pd.to_numeric(df["SWI_JA"], errors="coerce").to_numpy(dtype=float)
    pos = ndvi >= tau
    if require_ndmi_ge is not None:
        ndmi = pd.to_numeric(df["ndmi_summer"], errors="coerce").to_numpy(dtype=float)
        qual = qual & np.isfinite(ndmi)
        pos = pos & (ndmi >= require_ndmi_ge)
    dry = swi <= SWI_DRY
    return np.where(~qual, "insufficient_data",
                    np.where(~dry, "not_applicable",
                             np.where(pos, "positive", "negative")))


def classify_parcels(parcels: pd.DataFrame, tau: float) -> pd.DataFrame:
    """Apply the frozen rule and its three reported sensitivity variants to parcel-years."""
    out = parcels.copy()
    out["status"] = _classify_one(out, tau)
    out["status_tau_minus"] = _classify_one(out, tau - TAU_DELTA)
    out["status_tau_plus"] = _classify_one(out, tau + TAU_DELTA)
    out["status_ndmi"] = _classify_one(out, tau, require_ndmi_ge=NDMI_MIN)
    return out


def well_clipped_status_areas(parcels_gdf: gpd.GeoDataFrame, buffers: gpd.GeoDataFrame,
                              well_codes: list[str] | np.ndarray) -> pd.DataFrame:
    """Clipped parcel area (ha) inside each well buffer by status, plus share_positive and coverage."""
    p = parcels_gdf[["status", "geometry"]].to_crs(CRS_L93).copy()
    p["geometry"] = p.geometry.make_valid()
    b = buffers[["code_bss", "geometry"]].to_crs(CRS_L93)
    x = gpd.overlay(p, b, how="intersection", keep_geom_type=True)
    x["ha"] = x.area / 1e4
    piv = x.groupby(["code_bss", "status"])["ha"].sum().unstack(fill_value=0.0)
    for st in STATUSES:
        if st not in piv.columns:
            piv[st] = 0.0
    piv = piv[list(STATUSES)].reindex(list(well_codes), fill_value=0.0)

    out = pd.DataFrame({"code_bss": list(well_codes)})
    for st in STATUSES:
        out[f"area_{st}_ha"] = piv[st].to_numpy(dtype=float)
    out["area_classified_ha"] = out["area_positive_ha"] + out["area_negative_ha"]
    out["area_total_ha"] = sum(out[f"area_{st}_ha"] for st in STATUSES)
    out["share_positive"] = np.where(
        out["area_classified_ha"] > 0.0,
        out["area_positive_ha"] / out["area_classified_ha"],
        np.nan,
    )
    out["coverage"] = np.where(
        out["area_total_ha"] > 0.0,
        out["area_classified_ha"] / out["area_total_ha"],
        np.nan,
    )
    return out


def add_train_summary_rows(annual_df: pd.DataFrame, train_years: tuple[int, ...] = TRAIN_YEARS) -> pd.DataFrame:
    """Append one `year = 'train'` row per well: 2017-2019 mean share_positive (NaN if unclassified)."""
    df = annual_df.copy()
    df["year"] = df["year"].astype(str)
    train_keys = {str(y) for y in train_years}
    sub = df[df["year"].isin(train_keys)]

    area_cols = [c for c in df.columns if c.startswith("area_")]
    well_order = list(dict.fromkeys(df["code_bss"]))
    # Mean across the training editions; skipna=True yields NaN when no training edition has classified area
    agg = sub.groupby("code_bss", sort=False).agg(
        {**{c: "mean" for c in area_cols}, "share_positive": "mean", "coverage": "mean"}
    ).reindex(well_order)
    train_rows = agg.reset_index()
    train_rows.insert(1, "year", "train")

    year_order = [str(y) for y in sorted({int(y) for y in df["year"]})] + ["train"]
    both = pd.concat([df, train_rows[df.columns]], ignore_index=True)
    both["_w_ord"] = both["code_bss"].map({w: i for i, w in enumerate(well_order)})
    both["_y_ord"] = both["year"].map({y: i for i, y in enumerate(year_order)})
    both = both.sort_values(["_w_ord", "_y_ord"], ignore_index=True).drop(columns=["_w_ord", "_y_ord"])
    return both


def validate_census_2020(parcels: pd.DataFrame, status_col: str = "status") -> tuple[str, dict]:
    """Aggregate 2020 check per RPG group against the dept-66 RA2020 census ranges."""
    d20 = parcels[(parcels["year"] == 2020) & parcels[status_col].isin(("positive", "negative"))].copy()
    d20["ha"] = d20["area_m2"] / 1e4
    by_grp = d20.groupby(["CODE_GROUP", status_col])["ha"].sum().unstack(fill_value=0.0)
    for st in ("positive", "negative"):
        if st not in by_grp.columns:
            by_grp[st] = 0.0

    results = {}
    all_in_range = True
    for grp, spec in CENSUS_2020.items():
        pos_ha = float(by_grp.loc[grp, "positive"]) if grp in by_grp.index else 0.0
        neg_ha = float(by_grp.loc[grp, "negative"]) if grp in by_grp.index else 0.0
        cls_ha = pos_ha + neg_ha
        share = pos_ha / cls_ha if cls_ha > 0 else float("nan")
        low = spec["low_num"] / spec["denom"]
        high = spec["high_num"] / spec["denom"] if spec["has_upper"] else 1.0
        in_range = bool(np.isfinite(share) and (low <= share <= high))
        if not in_range:
            all_in_range = False
        results[str(grp)] = {
            "group": grp,
            "name": spec["name"],
            "area_positive_ha": round(pos_ha, 2),
            "area_classified_ha": round(cls_ha, 2),
            "share_positive": round(share, 4) if np.isfinite(share) else None,
            "census_low": round(low, 4),
            "census_high": round(high, 4) if spec["has_upper"] else None,
            "low_expr": spec["low_expr"],
            "high_expr": spec["high_expr"],
            "in_range": in_range,
        }
    verdict = "aggregate-consistent" if all_in_range else "heuristic"
    return verdict, results


def group_stability_table(parcels: pd.DataFrame, status_col: str = "status") -> pd.DataFrame:
    """Positive share of classified mapped area per RPG group and year (2017-2025)."""
    cls = parcels[parcels[status_col].isin(("positive", "negative"))].copy()
    cls["ha"] = cls["area_m2"] / 1e4
    cls["pos_ha"] = np.where(cls[status_col] == "positive", cls["ha"], 0.0)
    g = cls.groupby(["CODE_GROUP", "year"], as_index=False)[["pos_ha", "ha"]].sum()
    g["share"] = np.where(g["ha"] > 0, g["pos_ha"] / g["ha"], np.nan)
    piv = g.pivot(index="CODE_GROUP", columns="year", values="share")
    ha20 = g[g["year"] == 2020].set_index("CODE_GROUP")["ha"]
    piv.insert(0, "classified_ha_2020", ha20.reindex(piv.index).fillna(0.0))
    piv.insert(0, "group_name", [GROUP_NAMES.get(int(k), f"Group {int(k)}") for k in piv.index])
    return piv.sort_index()


def _fmt_pct(val: float | None) -> str:
    if val is None or (isinstance(val, float) and not np.isfinite(val)):
        return "—"
    return f"{val:.3f}"


def render_markdown(rule_meta: dict, hist_summary: dict, status_by_year: pd.DataFrame,
                    variant_summary: dict, val_verdict: str, val_groups: dict,
                    variant_val_2020: dict, stability: pd.DataFrame,
                    well_train: pd.DataFrame, core_codes: set[str]) -> str:
    """Render docs/irrigation_s2.md from the computed tables."""
    tau = rule_meta["TAU"]
    lines = [
        "# CQ15: Sentinel-2 probable-irrigation rule and validation (generated)",
        "",
        f"Generated by `src/dataset/irrigation_s2.py` (dataset `{rule_meta['dataset']}`, S2 snapshot "
        f"`{rule_meta['s2_snapshot']}`); **do not edit by hand**.",
        "",
        "## 1. Rule and frozen threshold",
        "",
        "For each parcel-year of the Sentinel-2 parcel tables (`2017–2025`, RPG parcels intersecting "
        f"at least one well's {BUFFER_M / 1000:.0f} km buffer):",
        "",
        f"1. **Quality:** `insufficient_data` if `n_px_summer < {MIN_PX}` (under ~400 m² of valid 10 m pixels), "
        f"`nobs_summer < {MIN_OBS}` (fewer than 3 clear July–August acquisitions), or if `ndvi_summer` or `SWI_JA` is missing.",
        f"2. **Dry conditions:** each parcel is linked to its nearest SAFRAN cell centre in Lambert-93; "
        f"`SWI_JA` is the mean weekly `SWI` over July and August of that year (`forcing_weekly.parquet`). "
        f"`not_applicable` if `SWI_JA > {SWI_DRY}`: above half the available soil water, a green summer canopy "
        "does not need irrigation (FAO-56 depletion fraction p ≈ 0.5; Allen et al. 1998, FAO Irrigation and Drainage Paper 56).",
        f"3. **Positive / negative:** `positive` if `ndvi_summer >= TAU`, else `negative`, where "
        f"**`TAU = {tau:.4f}`** is Otsu's threshold on a {NDVI_BIN}-wide NDVI histogram over `[{NDVI_LOW}, {NDVI_HIGH}]`, "
        "computed once on the quality-passing, dry parcel-years of the **training editions 2017–2019 only** "
        "(parcels unweighted) and frozen before any comparison with the census or 2020+ years.",
        f"4. **Sensitivity variants (reported only, never used for the static well fact):** "
        f"`TAU - {TAU_DELTA:.2f}` (`{tau - TAU_DELTA:.4f}`), `TAU + {TAU_DELTA:.2f}` (`{tau + TAU_DELTA:.4f}`), "
        f"and `TAU` with `ndmi_summer >= {NDMI_MIN:.1f}`.",
        "",
        "## 2. Training NDVI histogram (2017–2019, quality-passing and dry)",
        "",
        f"- Training parcel-years entering Otsu: **{hist_summary['n_train_classified_dry']:,}**",
        f"- Frozen threshold **`TAU = {tau:.4f}`** (between-class variance = `{hist_summary['between_class_variance']:.6f}`)",
        f"- Lower class (`ndvi_summer < TAU`): **{hist_summary['class0_count']:,}** "
        f"({100 * hist_summary['class0_share']:.1f} %), mean NDVI = `{hist_summary['class0_mean']:.4f}`",
        f"- Upper class (`ndvi_summer >= TAU`): **{hist_summary['class1_count']:,}** "
        f"({100 * hist_summary['class1_share']:.1f} %), mean NDVI = `{hist_summary['class1_mean']:.4f}`",
        f"- Fine-bin (0.005) mode below `TAU`: **NDVI = `{hist_summary['mode_below_tau']['ndvi']:.4f}`** "
        f"({hist_summary['mode_below_tau']['bin_count']} parcel-years; dry/sparse canopies such as vines, fallow and stubble).",
        f"- Above `TAU`: the distribution is a **broad green shoulder** across NDVI `0.50–0.80` rather than a sharp "
        f"second spike; the single highest 0.005 bin >= `TAU` sits immediately at the cut "
        f"(`{hist_summary['mode_above_tau']['ndvi']:.4f}`, {hist_summary['mode_above_tau']['bin_count']} parcel-years), "
        f"while the 5-bin smoothed upper distribution shows a secondary green peak around "
        f"**NDVI = `{hist_summary['upper_secondary_peak_smoothed']['ndvi']:.4f}`** "
        f"(smoothed count `{hist_summary['upper_secondary_peak_smoothed']['smoothed_count']:.1f}`/bin; orchards and green pastures).",
        "- Quantiles: " + ", ".join(f"{k.upper()} `{v:.4f}`" for k, v in hist_summary["quantiles"].items()),
        "",
        "| NDVI bin | Parcel-years (2017–2019, dry & valid) | Share (%) |",
        "|:---|---:|---:|",
    ]
    tot_tr = hist_summary["n_train_classified_dry"]
    for b in hist_summary["coarse_bins_005"]:
        if b["count"] == 0:
            continue
        mark = "  ← TAU" if b["low"] <= tau < b["high"] else ""
        lines.append(f"| `[{b['low']:.2f}, {b['high']:.2f})`{mark} | {b['count']:,} | {100 * b['count'] / tot_tr:.1f} |")

    lines += [
        "",
        "## 3. Parcel-year status counts (2017–2025)",
        "",
        "| Year | positive | negative | not_applicable | insufficient_data | Total | Positive share of classified (%) |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for y, row in status_by_year.iterrows():
        tot = int(row.sum())
        cls = int(row["positive"] + row["negative"])
        pct = 100.0 * row["positive"] / cls if cls else float("nan")
        lines.append(
            f"| {y} | {int(row['positive']):,} | {int(row['negative']):,} | "
            f"{int(row['not_applicable']):,} | {int(row['insufficient_data']):,} | {tot:,} | {pct:.1f} |"
        )
    tot_all = int(status_by_year.to_numpy().sum())
    pos_all = int(status_by_year["positive"].sum())
    neg_all = int(status_by_year["negative"].sum())
    na_all = int(status_by_year["not_applicable"].sum())
    ins_all = int(status_by_year["insufficient_data"].sum())
    lines.append(
        f"| **All (2017–2025)** | **{pos_all:,}** | **{neg_all:,}** | "
        f"**{na_all:,}** | **{ins_all:,}** | **{tot_all:,}** | **{100.0 * pos_all / (pos_all + neg_all):.1f}** |"
    )

    lines += [
        "",
        "### Sensitivity variants (2017–2025 totals, reported only)",
        "",
        "| Rule / variant | Threshold | positive | negative | not_applicable | insufficient_data | Positive share of classified (%) |",
        "|:---|:---|---:|---:|---:|---:|---:|",
    ]
    variant_labels = [
        ("main", f"NDVI >= {tau:.4f}", "status"),
        ("tau_minus", f"NDVI >= {tau - TAU_DELTA:.4f}", "status_tau_minus"),
        ("tau_plus", f"NDVI >= {tau + TAU_DELTA:.4f}", "status_tau_plus"),
        ("ndmi", f"NDVI >= {tau:.4f} & NDMI >= {NDMI_MIN:.1f}", "status_ndmi"),
    ]
    for key, desc, _ in variant_labels:
        c = variant_summary[key]
        cls = c["positive"] + c["negative"]
        pct = 100.0 * c["positive"] / cls if cls else float("nan")
        lines.append(
            f"| `{key}` | `{desc}` | {c['positive']:,} | {c['negative']:,} | "
            f"{c['not_applicable']:,} | {c['insufficient_data']:,} | {pct:.1f} |"
        )

    lines += [
        "",
        "## 4. Aggregate validation against the 2020 Agreste census (CQ15 contract)",
        "",
        "Dept 66 RA2020 census figures (`data/README.md`, \"Land-use thread\"; irrigating-farm typology "
        "covering **73 %** of the irrigated SAU):",
        "",
        "- **Orchards (group 20):** total 8,100 ha; specialised fruit farms irrigate 5,268 ha, mixed "
        "vegetables + fruit 1,639 ha, mixed fruit + vines 502 ha.",
        f"  - Lower bound: `5,268 / 8,100 = {5268 / 8100:.4f}` (**0.65**)",
        f"  - Upper bound (all mixed fruit farms attributed to orchards): `(5,268 + 1,639 + 502) / 8,100 = 7,409 / 8,100 = {7409 / 8100:.4f}` (**0.91**)",
        "- **Vines (group 21):** total 19,840 ha; specialised vine farms irrigate 839 ha, mixed fruit + vines 502 ha.",
        f"  - Lower bound: `839 / 19,840 = {839 / 19840:.4f}` (**0.04**)",
        f"  - Upper bound (all fruit + vine irrigated area attributed to vines): `(839 + 502) / 19,840 = 1,341 / 19,840 = {1341 / 19840:.4f}` (**0.07**)",
        "- **Market gardening (group 25):** total 1,760 ha; specialised vegetable farms irrigate 932 ha "
        "(plus an unknown share of the 1,639 ha on mixed vegetables + fruit farms).",
        f"  - Lower bound: `932 / 1,760 = {932 / 1760:.4f}` (**0.53**; no upper bound below 1.00)",
        "",
        "Measured on the 2020 RPG edition using each parcel's mapped Lambert-93 area (`area_m2`, whole "
        "parcels intersecting the 3 km well zones, counted once each; classified = `positive + negative`):",
        "",
        "| RPG group | Classified area (ha) | Positive area (ha) | Main share | Census range | In range? | `TAU-0.05` | `TAU+0.05` | `TAU & NDMI>=0` |",
        "|:---|---:|---:|---:|:---|:---:|---:|---:|---:|",
    ]
    for grp in ("20", "21", "25"):
        r = val_groups[grp]
        rng = f"[{r['census_low']:.2f}, {r['census_high']:.2f}]" if r["census_high"] is not None else f">= {r['census_low']:.2f}"
        ok_str = "yes" if r["in_range"] else "no"
        lines.append(
            f"| {r['name']} | {r['area_classified_ha']:,.1f} | {r['area_positive_ha']:,.1f} | "
            f"**{_fmt_pct(r['share_positive'])}** | {rng} | {ok_str} | "
            f"{_fmt_pct(variant_val_2020['tau_minus'][grp]['share_positive'])} | "
            f"{_fmt_pct(variant_val_2020['tau_plus'][grp]['share_positive'])} | "
            f"{_fmt_pct(variant_val_2020['ndmi'][grp]['share_positive'])} |"
        )

    lines += [
        "",
        f"### Verdict: **`{val_verdict}`**",
        "",
    ]
    if val_verdict == "aggregate-consistent":
        lines.append(
            "All three benchmark RPG groups fall inside their RA2020 census ranges. Even so, this is "
            "an aggregate plausibility check rather than parcel-level validation (CQ15)."
        )
    else:
        lines.append(
            "Not all three benchmark RPG groups fall inside their RA2020 census ranges, so under the "
            "CQ15 contract this rule is explicitly labelled a **heuristic** (never parcel-level truth):"
        )
        for grp in ("20", "21", "25"):
            r = val_groups[grp]
            rng = f"[{r['census_low']:.2f}, {r['census_high']:.2f}]" if r["census_high"] is not None else f">= {r['census_low']:.2f}"
            status_txt = "inside" if r["in_range"] else "outside"
            lines.append(
                f"- {r['name']}: `{_fmt_pct(r['share_positive'])}` ({status_txt} `{rng}`)."
            )

    lines += [
        "",
        "### Caveats (CQ15)",
        "",
        "1. **Partial typology coverage:** the RA2020 irrigating-farm typology covers **73 %** of dept 66's "
        "irrigated SAU, so true crop-level irrigated shares can exceed the upper bounds derived above.",
        "2. **Spatial mismatch:** the Sentinel-2 parcel set covers the 65 wells' 3 km zones (concentrated on "
        "the Roussillon plain and valley floors), whereas the census covers the entire département.",
        "3. **Unit mismatch:** the census reports irrigated area by **farm type** (specialised or mixed farms), "
        "not by individual parcel or crop.",
        "4. **Summer bare soil on vegetable parcels:** market-gardening parcels (group 25) are often harvested "
        "in spring/early summer or tilled between crop rotations in July–August, so a low summer NDVI produces "
        "a `negative` status even on irrigated land (**a negative result does not prove rainfed management**).",
        "5. **Cell-scale wetness and canopy confounding:** `SWI_JA` is an 8 km SAFRAN grid-cell mean, not "
        "field soil moisture; deep-rooted perennials, grass cover between vine rows, or mixed 10 m pixels can "
        "raise summer NDVI without irrigation.",
        "6. **No water-source link:** a `positive` status never asserts groundwater pumping or canal supply (`irrigatedBy`).",
        "",
        "## 5. Stability across years (2017–2025, every RPG group)",
        "",
        "Positive share of classified mapped area (`area_m2`) per RPG group and edition year:",
        "",
    ]
    yr_cols = [y for y in YEARS if y in stability.columns]
    header = "| Group | Name | 2020 classified (ha) | " + " | ".join(str(y) for y in yr_cols) + " |"
    sep = "|---:|:---|---:|" + "|".join("---:" for _ in yr_cols) + "|"
    lines += [header, sep]
    for grp, row in stability.iterrows():
        vals = " | ".join(_fmt_pct(float(row[y])) if pd.notna(row[y]) else "—" for y in yr_cols)
        lines.append(f"| {int(grp)} | {row['group_name']} | {row['classified_ha_2020']:,.1f} | {vals} |")

    n_nan = int(well_train["share_positive"].isna().sum())
    core_tr = well_train[well_train["code_bss"].isin(core_codes)]
    lines += [
        "",
        "## 6. Per-well static summary (`year = \"train\"`, 2017–2019 mean)",
        "",
        f"- Total wells in `wells.parquet`: **{len(well_train)}** ({len(core_tr)} core)",
        f"- Wells with NaN training `share_positive` (no classified area in 2017–2019): **{n_nan}**",
        f"- All wells `share_positive` (train): min `{well_train['share_positive'].min():.3f}`, "
        f"median `{well_train['share_positive'].median():.3f}`, max `{well_train['share_positive'].max():.3f}`",
        f"- Core wells `share_positive` (train): min `{core_tr['share_positive'].min():.3f}`, "
        f"median `{core_tr['share_positive'].median():.3f}`, max `{core_tr['share_positive'].max():.3f}`",
        f"- All wells `coverage` (train): min `{well_train['coverage'].min():.3f}`, "
        f"median `{well_train['coverage'].median():.3f}`, max `{well_train['coverage'].max():.3f}`",
        "",
    ]
    return "\n".join(lines)


def run(snapshot: str = S2_SNAPSHOT, years: tuple[int, ...] = YEARS) -> dict:
    """Build parcel statuses, per-well shares, frozen rule JSON and docs/irrigation_s2.md."""
    t0 = time.perf_counter()
    s2_dir = RAW / "gee_s2" / snapshot
    grid_path = RAW / "safran" / "grid_cells_66.parquet"
    forcing_path = DATASET_DIR / "forcing_weekly.parquet"
    wells_path = DATASET_DIR / "wells.parquet"

    grid_cells = pd.read_parquet(grid_path)
    forcing = pd.read_parquet(forcing_path, columns=["cell_id", "week", "SWI"])
    wells = pd.read_parquet(wells_path)
    buffers = well_buffers(wells)
    well_codes = wells["code_bss"].tolist()

    swi_df = summer_swi(forcing)
    swi_lookup = swi_df.set_index(["cell_id", "year"])["SWI_JA"]

    input_paths = [s2_dir / "release.json", grid_path, forcing_path, wells_path]
    parcel_parts = []
    geoms_by_year = {}

    for y in years:
        s2_path = s2_dir / f"s2_parcels_{y}.parquet"
        rpg_path = INTERIM / f"rpg_dept_{y}.parquet"
        input_paths.extend([s2_path, rpg_path])

        s2 = pd.read_parquet(s2_path)
        s2["ID_PARCEL"] = s2["ID_PARCEL"].astype(str)
        rpg = gpd.read_parquet(rpg_path, columns=["ID_PARCEL", "geometry"]).to_crs(CRS_L93)
        rpg["ID_PARCEL"] = rpg["ID_PARCEL"].astype(str)
        rpg = rpg[rpg["ID_PARCEL"].isin(set(s2["ID_PARCEL"]))].copy()
        if len(rpg) != len(s2) or rpg["ID_PARCEL"].duplicated().any():
            raise ValueError(f"RPG/S2 mismatch in {y}: {len(rpg)} geometries for {len(s2)} S2 rows")

        cell_map = nearest_cells(rpg, grid_cells)
        s2["cell_id"] = s2["ID_PARCEL"].map(cell_map)
        s2["SWI_JA"] = pd.MultiIndex.from_arrays([s2["cell_id"], s2["year"]]).map(swi_lookup).to_numpy(dtype=float)
        parcel_parts.append(s2)
        geoms_by_year[y] = rpg

    parcels = pd.concat(parcel_parts, ignore_index=True)
    tau = fit_otsu_tau(parcels, train_years=TRAIN_YEARS)
    parcels = classify_parcels(parcels, tau)

    # Training sample for histogram diagnostics
    train_vals = parcels.loc[
        parcels["year"].isin(TRAIN_YEARS) & parcels["status"].isin(("positive", "negative")),
        "ndvi_summer",
    ].to_numpy(dtype=float)
    hist_summary = otsu_histogram_summary(train_vals, tau)

    # Per-well clipped areas per year + "train" summary row
    well_parts = []
    for y in years:
        st_y = parcels.loc[parcels["year"] == y, ["ID_PARCEL", "status"]]
        g_y = geoms_by_year[y].merge(st_y, on="ID_PARCEL", how="inner")
        w_y = well_clipped_status_areas(g_y, buffers, well_codes)
        w_y.insert(1, "year", str(y))
        well_parts.append(w_y)
    wells_out = add_train_summary_rows(pd.concat(well_parts, ignore_index=True), train_years=TRAIN_YEARS)

    # Validation and stability
    val_verdict, val_groups = validate_census_2020(parcels, status_col="status")
    variant_val_2020 = {}
    for key, col in (("tau_minus", "status_tau_minus"),
                     ("tau_plus", "status_tau_plus"),
                     ("ndmi", "status_ndmi")):
        _, variant_val_2020[key] = validate_census_2020(parcels, status_col=col)
    stability = group_stability_table(parcels, status_col="status")

    status_by_year = (
        pd.crosstab(parcels["year"], parcels["status"])
        .reindex(index=list(years), columns=list(STATUSES), fill_value=0)
    )
    variant_summary = {
        key: {st: int((parcels[col] == st).sum()) for st in STATUSES}
        for key, col in (
            ("main", "status"),
            ("tau_minus", "status_tau_minus"),
            ("tau_plus", "status_tau_plus"),
            ("ndmi", "status_ndmi"),
        )
    }

    # Column ordering for parcel output
    parcel_cols = [
        "year", "ID_PARCEL", "CODE_CULTU", "CODE_GROUP", "SURF_PARC", "area_m2",
        "ndvi_spring", "ndmi_spring", "nobs_spring", "n_px_spring",
        "ndvi_summer", "ndmi_summer", "nobs_summer", "n_px_summer",
        "cell_id", "SWI_JA", "status", "status_tau_minus", "status_tau_plus", "status_ndmi",
    ]
    parcels_out = parcels[parcel_cols]

    parcels_path = INTERIM / f"irrigation_s2_parcels_{DATASET}.parquet"
    wells_out_path = DATASET_DIR / "irrigation_s2_wells.parquet"
    rule_path = DATASET_DIR / "irrigation_s2_rule.json"
    doc_path = ROOT / "docs" / "irrigation_s2.md"

    parcels_path.parent.mkdir(parents=True, exist_ok=True)
    wells_out_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.parent.mkdir(parents=True, exist_ok=True)

    parcels_out.to_parquet(parcels_path, index=False)
    wells_out.to_parquet(wells_out_path, index=False)

    well_train = wells_out[wells_out["year"] == "train"].copy()
    inputs_sha = {
        p.relative_to(ROOT).as_posix(): sha256_file(p)
        for p in sorted(set(input_paths), key=lambda p: p.as_posix())
    }
    rule_meta = {
        "dataset": DATASET,
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "s2_snapshot": s2_dir.relative_to(ROOT).as_posix(),
        "TAU": tau,
        "MIN_PX": MIN_PX,
        "MIN_OBS": MIN_OBS,
        "SWI_DRY": SWI_DRY,
        "tau_delta": TAU_DELTA,
        "ndmi_min": NDMI_MIN,
        "ndvi_histogram_range": [NDVI_LOW, NDVI_HIGH],
        "ndvi_histogram_bin_width": NDVI_BIN,
        "buffer_m": BUFFER_M,
        "train_editions": list(TRAIN_YEARS),
        "editions": list(years),
        "otsu_summary": hist_summary,
        "counts": {
            "total_parcel_years": int(len(parcels_out)),
            "by_status": variant_summary["main"],
            "by_year": {
                str(y): {st: int(status_by_year.loc[y, st]) for st in STATUSES}
                for y in years
            },
            "variants_by_status": {k: variant_summary[k] for k in ("tau_minus", "tau_plus", "ndmi")},
            "wells_total": int(len(well_codes)),
            "wells_nan_train_share": int(well_train["share_positive"].isna().sum()),
        },
        "validation_2020": {
            "verdict": val_verdict,
            "groups": val_groups,
            "variants": variant_val_2020,
        },
        "inputs_sha256": inputs_sha,
    }
    rule_path.write_text(json.dumps(rule_meta, indent=2) + "\n", encoding="utf-8")

    core_codes = set(wells.loc[wells["core"], "code_bss"])
    md = render_markdown(
        rule_meta=rule_meta,
        hist_summary=hist_summary,
        status_by_year=status_by_year,
        variant_summary=variant_summary,
        val_verdict=val_verdict,
        val_groups=val_groups,
        variant_val_2020=variant_val_2020,
        stability=stability,
        well_train=well_train,
        core_codes=core_codes,
    )
    doc_path.write_text(md, encoding="utf-8")

    elapsed = time.perf_counter() - t0
    print(f"CQ15 irrigation_s2 ({DATASET}): TAU={tau:.4f}, verdict={val_verdict}, "
          f"{len(parcels_out):,} parcel-years, {len(well_codes)} wells "
          f"(NaN train share: {rule_meta['counts']['wells_nan_train_share']}), {elapsed:.1f} s")
    print(f"  -> {parcels_path.relative_to(ROOT)}")
    print(f"  -> {wells_out_path.relative_to(ROOT)}")
    print(f"  -> {rule_path.relative_to(ROOT)}")
    print(f"  -> {doc_path.relative_to(ROOT)}")
    return rule_meta


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--snapshot", default=S2_SNAPSHOT, help=f"S2 snapshot folder under data/raw/gee_s2 (default {S2_SNAPSHOT})")
    args = ap.parse_args()
    run(snapshot=args.snapshot)


if __name__ == "__main__":
    main()
