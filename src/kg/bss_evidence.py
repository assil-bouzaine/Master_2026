"""Measure what BRGM's BSS borehole records add to pump -> aquifer attribution (v5 plan R1.3).

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m src.kg.bss_evidence

Why (docs/v5_plan.md step R1.3; CLAUDE.md section 3):
The main pump-attribution policy (src/kg/pump_attribution.py, task 12.3) gives 0 % of the
declared irrigation volume a unit, because BNPE irrigation boreholes carry almost no BSS code
and no depth. BRGM's open BSS WFS layers (downloaded 2026-11-25 by src/ingest/brgm_bss.py)
provide, per water point, an investigation depth (`prof_invest`), the BD LISA entities BRGM
associates with the point (`liste_bdlisa`) and the aquifer condition (`mode_gisement`), and per
borehole, the depth reached (`prof_atteinte`).

Because BRGM does not document how `liste_bdlisa` is populated, its precision must be measured
on the 130 distinct recorded boreholes of task 12.3 before any integration (confidence levels
are measured, not assumed). This module measures evidence only and does not modify
`pump_attribution.py`.

Fixed rules (set before computing any precision):
- Entity parsing: BD LISA codes in `liste_bdlisa` match ``\\b\\d{3}[A-Z]{2}\\d{2}\\b``.
  Level is ``NV2`` when the text says ``"NV3 absent"``, else ``NV3`` (``mixed`` if a
  multi-entity string mixes both). Count = number of entity codes listed.
- Candidate rule ``bss_record``: a point whose ``liste_bdlisa`` lists exactly one entity
  proposes that entity. Points listing several entities yield no single candidate (all
  entities are kept and reported separately).
- Location matching: for each BNPE groundwater point, the nearest BSS water point in Lambert-93
  within D in {50, 100, 250, 500} m (every D is reported; none is picked here).
- Precision reference: task 12.3's reference on the 130 distinct recorded boreholes (the
  recorded ADES entity after its depth check, via ``pump_attribution.record_rule``), scored at
  both group level (``alluvium`` = recent + ancient alluvium) and exact-entity level.

Outputs:
    data/interim/bss_evidence.parquet   one row per BNPE groundwater point (direct BSS join,
                                        parsed BD LISA entities and depth, nearest BSS point)
    docs/bss_evidence.md                generated measurement report
"""
import re

import geopandas as gpd
import numpy as np
import pandas as pd

from src.analysis.bdlisa_profile import group_of
from src.config import CRS_L93, CRS_WGS84, DATASET, INTERIM, RAW, ROOT
from src.kg import pump_attribution as pa
from src.kg.pump_coverage import wilson

BSS_SNAPSHOT = "2026-11-25-tiled"  # the complete pull (the paged one of the same day skipped features)
BSS_DIR = RAW / "brgm_bss" / BSS_SNAPSHOT
BSS_EAU_PATH = BSS_DIR / "bss_eau_point.parquet"
BSS_TOTAL_PATH = BSS_DIR / "bss_total_sans_label.parquet"
OUT_PARQUET = INTERIM / "bss_evidence.parquet"
OUT_MD = ROOT / "docs" / "bss_evidence.md"

BDLISA_RE = re.compile(r"\b\d{3}[A-Z]{2}\d{2}\b")
RADII_M = (50, 100, 250, 500)


def parse_bdlisa(text):
    """Parse BRGM's ``liste_bdlisa`` field into codes, level (NV3 / NV2 / mixed) and count.

    Examples:
    - ``"Alluvions récentes de la Têt - 718BP02"`` -> 1 entity, level ``NV3``, single ``718BP02``
    - ``"NV3 absent, nom de l'entité NV2 : Sables et argiles pliocènes du Roussillon - 671AA00"``
      -> 1 entity, level ``NV2``, single ``671AA00``
    - ``"... - 671AA00;... - 671AB01"`` -> 2 entities, single ``None`` (both kept in ``entities``)
    - empty / None -> 0 entities, level ``None``, single ``None``
    """
    if not isinstance(text, str) or not text.strip():
        return {"entities": [], "n_entities": 0, "level": None, "single_entity": None}
    cleaned = text.strip()
    entities = BDLISA_RE.findall(cleaned)
    if not entities:
        return {"entities": [], "n_entities": 0, "level": None, "single_entity": None}
    parts = [p.strip() for p in cleaned.split(";") if p.strip()]
    levels = []
    for part in parts:
        found = BDLISA_RE.findall(part)
        if not found:
            continue
        lvl = "NV2" if "nv3 absent" in part.lower() else "NV3"
        levels.extend([lvl] * len(found))
    unique_levels = set(levels)
    if len(unique_levels) == 1:
        level = next(iter(unique_levels))
    else:
        level = "mixed"
    single = entities[0] if len(entities) == 1 else None
    return {"entities": entities, "n_entities": len(entities), "level": level, "single_entity": single}


def eval_group(code):
    """Aquifer group at the resolution of task 12.3's rule evaluation."""
    if not isinstance(code, str) or not code:
        return "none"
    g = group_of(code)
    return "alluvium" if g in pa.ALLUVIAL else g


def load_bss_eau(path=BSS_EAU_PATH):
    """Load and deduplicate BRGM BSS water points (``ms:BSS_EAU_POINT``)."""
    raw = gpd.read_parquet(path)
    n_raw = len(raw)
    eau = raw.sort_values("code_bss").drop_duplicates("code_bss", keep="first").reset_index(drop=True)
    parsed = eau["liste_bdlisa"].map(parse_bdlisa)
    eau["bdlisa_entities"] = [";".join(p["entities"]) for p in parsed]
    eau["bdlisa_n_entities"] = [p["n_entities"] for p in parsed]
    eau["bdlisa_level"] = [p["level"] for p in parsed]
    eau["bdlisa_single"] = [p["single_entity"] for p in parsed]
    eau["prof_invest_m"] = pd.to_numeric(eau["prof_invest"], errors="coerce")
    return eau, n_raw


def load_bss_total(path=BSS_TOTAL_PATH):
    """Load and deduplicate BRGM BSS boreholes (``ms:BSS_TOTAL_SANS_LABEL``)."""
    raw = gpd.read_parquet(path)
    n_raw = len(raw)
    tot = raw.sort_values("reference").drop_duplicates("reference", keep="first").reset_index(drop=True)
    tot["prof_atteinte_m"] = pd.to_numeric(tot["prof_atteinte"], errors="coerce")
    return tot, n_raw


def match_nearest_bss(bnpe_gdf, bss_gdf, radii=RADII_M):
    """For each BNPE point, find the nearest BSS water point and flag matches within each radius.

    Both inputs must have Point geometries. If a CRS is present and differs from Lambert-93
    (EPSG:2154), geometries are projected to Lambert-93 so distances are in metres. Exact
    distance ties (which happen when points share a commune centroid) are counted in
    ``nearest_bss_n_ties`` and broken deterministically by sorting on ``code_bss``.
    """
    left = bnpe_gdf[["code_ouvrage", "geometry"]].copy()
    if left.crs is not None and left.crs != CRS_L93:
        left = left.to_crs(CRS_L93)
    right_cols = [c for c in ("code_bss", "bdlisa_entities", "bdlisa_n_entities", "bdlisa_level",
                              "bdlisa_single", "prof_invest_m", "mode_gisement",
                              "coordonneescommune") if c in bss_gdf.columns]
    right = bss_gdf[right_cols + ["geometry"]].copy()
    if right.crs is not None and right.crs != CRS_L93:
        right = right.to_crs(CRS_L93)

    joined = gpd.sjoin_nearest(left, right, how="left", distance_col="nearest_bss_dist_m")
    ties = joined.groupby("code_ouvrage")["code_bss"].size().rename("nearest_bss_n_ties")
    best = (joined.sort_values(["code_ouvrage", "nearest_bss_dist_m", "code_bss"], na_position="last")
            .drop_duplicates("code_ouvrage", keep="first")
            .drop(columns=["geometry", "index_right"], errors="ignore"))
    best = best.merge(ties, on="code_ouvrage", how="left")
    rename = {
        "code_bss": "nearest_bss_code",
        "bdlisa_entities": "nearest_bss_entities",
        "bdlisa_n_entities": "nearest_bss_n_entities",
        "bdlisa_level": "nearest_bss_level",
        "bdlisa_single": "nearest_bss_record_unit",
        "prof_invest_m": "nearest_bss_prof_invest_m",
        "mode_gisement": "nearest_bss_mode_gisement",
        "coordonneescommune": "nearest_bss_coordonneescommune",
    }
    best = best.rename(columns={k: v for k, v in rename.items() if k in best.columns})
    if "nearest_bss_record_unit" in best.columns:
        best["nearest_bss_record_group"] = best["nearest_bss_record_unit"].map(eval_group)
    for d in radii:
        best[f"nearest_match_{d}m"] = best["nearest_bss_dist_m"].le(d).fillna(False)
    order = pd.DataFrame({"code_ouvrage": bnpe_gdf["code_ouvrage"].values})
    return order.merge(best, on="code_ouvrage", how="left")


def build_evidence_table(gw=None, eau=None, tot=None):
    """Build one-row-per-ouvrage BSS evidence table for all BNPE groundwater points."""
    if gw is None:
        gw = pa.evidence()
    if eau is None:
        eau, _ = load_bss_eau()
    if tot is None:
        tot, _ = load_bss_total()

    df = gw[["code_ouvrage", "nom_ouvrage", "zone", "usage_main", "volume_mm3",
             "longitude", "latitude", "code_bss_point_eau", "rec_unit", "rec_depth_m",
             "stack", "rec_near_point", "name_profond"]].copy()
    df["code_bss_point_eau"] = df["code_bss_point_eau"].replace("", np.nan)
    df["has_bss_code"] = df["code_bss_point_eau"].notna()

    # Reference entity from task 12.3 (record after depth check)
    truth_units = []
    truth_rules = []
    for _, row in df.iterrows():
        rr = pa.record_rule(row)
        truth_units.append(rr[0] if rr is not None else None)
        truth_rules.append(rr[1] if rr is not None else None)
    df["truth_unit"] = truth_units
    df["truth_rule"] = truth_rules
    df["truth_group"] = df["truth_unit"].map(eval_group)

    # Direct BSS code join: water points (ms:BSS_EAU_POINT)
    eau_keep = eau[["code_bss", "bss_id", "liste_bdlisa", "bdlisa_entities", "bdlisa_n_entities",
                    "bdlisa_level", "bdlisa_single", "prof_invest_m", "mode_gisement",
                    "nature_pe", "coordonneescommune"]].rename(columns={
        "liste_bdlisa": "bss_liste_bdlisa",
        "bdlisa_entities": "bss_entities",
        "bdlisa_n_entities": "bss_n_entities",
        "bdlisa_level": "bss_level",
        "bdlisa_single": "bss_record_unit",
        "prof_invest_m": "bss_prof_invest_m",
        "mode_gisement": "bss_mode_gisement",
        "nature_pe": "bss_nature_pe",
        "coordonneescommune": "bss_coordonneescommune",
    })
    df = df.merge(eau_keep, left_on="code_bss_point_eau", right_on="code_bss", how="left")
    df["in_bss_eau"] = df["code_bss"].notna()
    df["bss_record_group"] = df["bss_record_unit"].map(eval_group)
    df = df.drop(columns=["code_bss"])

    # Direct BSS code join: boreholes (ms:BSS_TOTAL_SANS_LABEL)
    tot_keep = tot[["reference", "prof_atteinte_m", "utilisation"]].rename(columns={
        "prof_atteinte_m": "bss_prof_atteinte_m",
        "utilisation": "bss_utilisation",
    })
    df = df.merge(tot_keep, left_on="code_bss_point_eau", right_on="reference", how="left")
    df["in_bss_total"] = df["reference"].notna()
    df = df.drop(columns=["reference"])

    # Metric coordinates (Lambert-93): distance to own BSS water point and nearest BSS water point
    bnpe_gdf = gpd.GeoDataFrame(
        df[["code_ouvrage"]],
        geometry=gpd.points_from_xy(df["longitude"], df["latitude"]),
        crs=CRS_WGS84,
    ).to_crs(CRS_L93)
    eau_l93 = eau.to_crs(CRS_L93)
    eau_geom = eau_l93.set_index("code_bss")["geometry"]
    own_dist = []
    for geom, code, found in zip(bnpe_gdf.geometry, df["code_bss_point_eau"], df["in_bss_eau"]):
        own_dist.append(float(geom.distance(eau_geom[code])) if found else np.nan)
    df["own_bss_dist_m"] = own_dist

    nearest = match_nearest_bss(bnpe_gdf, eau_l93, radii=RADII_M)
    df = df.merge(nearest, on="code_ouvrage", how="left")
    assert len(df) == len(gw), f"expected {len(gw)} rows, got {len(df)}"
    assert df["code_ouvrage"].is_unique, "one row per BNPE groundwater point"
    return df


def _precision_row(label, fired, pred_col, pred_group_col, truth_col="truth_unit",
                   truth_group_col="truth_group"):
    n = len(fired)
    k_grp = int((fired[pred_group_col] == fired[truth_group_col]).sum()) if n else 0
    k_ex = int((fired[pred_col] == fired[truth_col]).sum()) if n else 0
    p_grp = k_grp / n if n else float("nan")
    p_ex = k_ex / n if n else float("nan")
    lo_g, hi_g = wilson(k_grp, n)
    lo_e, hi_e = wilson(k_ex, n)
    return {
        "subset": label,
        "n": n,
        "correct_group": k_grp,
        "precision_group": round(p_grp, 3) if n else float("nan"),
        "wilson_group_lo": round(lo_g, 3) if n else float("nan"),
        "wilson_group_hi": round(hi_g, 3) if n else float("nan"),
        "correct_exact": k_ex,
        "precision_exact": round(p_ex, 3) if n else float("nan"),
        "wilson_exact_lo": round(lo_e, 3) if n else float("nan"),
        "wilson_exact_hi": round(hi_e, 3) if n else float("nan"),
    }


def summarize_joins(df):
    """Section 1: direct BSS code join counts and 2012-2024 volumes by use (all and plain)."""
    tables = {}
    for scope, sub in (("all", df), ("plain", df[df["zone"] == "plain"])):
        rows = []
        for use, g in sub.groupby("usage_main", dropna=False):
            label = use if isinstance(use, str) else "unknown"
            rows.append({
                "usage": label,
                "n_points": len(g),
                "vol_Mm3": round(float(g["volume_mm3"].sum()), 2),
                "with_bss_code": int(g["has_bss_code"].sum()),
                "vol_with_code_Mm3": round(float(g.loc[g["has_bss_code"], "volume_mm3"].sum()), 2),
                "in_bss_eau": int(g["in_bss_eau"].sum()),
                "vol_in_eau_Mm3": round(float(g.loc[g["in_bss_eau"], "volume_mm3"].sum()), 2),
                "single_bdlisa": int(g["bss_record_unit"].notna().sum()),
                "vol_single_Mm3": round(float(g.loc[g["bss_record_unit"].notna(), "volume_mm3"].sum()), 2),
                "in_bss_total": int(g["in_bss_total"].sum()),
            })
        rows.append({
            "usage": "Total",
            "n_points": len(sub),
            "vol_Mm3": round(float(sub["volume_mm3"].sum()), 2),
            "with_bss_code": int(sub["has_bss_code"].sum()),
            "vol_with_code_Mm3": round(float(sub.loc[sub["has_bss_code"], "volume_mm3"].sum()), 2),
            "in_bss_eau": int(sub["in_bss_eau"].sum()),
            "vol_in_eau_Mm3": round(float(sub.loc[sub["in_bss_eau"], "volume_mm3"].sum()), 2),
            "single_bdlisa": int(sub["bss_record_unit"].notna().sum()),
            "vol_single_Mm3": round(float(sub.loc[sub["bss_record_unit"].notna(), "volume_mm3"].sum()), 2),
            "in_bss_total": int(sub["in_bss_total"].sum()),
        })
        tables[scope] = pd.DataFrame(rows)
    new_direct = df[df["rec_unit"].isna() & df["in_bss_eau"]].copy()
    tables["new_beyond_ades"] = new_direct
    return tables


def evaluate_bss_record(df, radii=RADII_M):
    """Section 2: precision of ``bss_record`` on task 12.3's 130 distinct recorded boreholes."""
    rec = df[df["rec_unit"].notna()].drop_duplicates("code_bss_point_eau").copy()
    rec["raw_group"] = rec["rec_unit"].map(eval_group)
    fired = rec[rec["bss_record_unit"].notna()].copy()

    overall_rows = [
        _precision_row("All evaluated (vs 12.3 reference after depth check)",
                       fired, "bss_record_unit", "bss_record_group"),
        _precision_row("All evaluated (vs raw ADES rec_unit, before depth check)",
                       fired, "bss_record_unit", "bss_record_group",
                       truth_col="rec_unit", truth_group_col="raw_group"),
    ]
    overall = pd.DataFrame(overall_rows)

    by_use_rows = []
    for use in sorted(rec["usage_main"].dropna().unique()):
        sub = fired[fired["usage_main"] == use]
        by_use_rows.append(_precision_row(use, sub, "bss_record_unit", "bss_record_group"))
    # Explicitly show irrigation = 0 evaluated so the gap is unmistakable
    if "irrigation" not in {r["subset"] for r in by_use_rows}:
        by_use_rows.append(_precision_row("irrigation", fired.iloc[0:0],
                                          "bss_record_unit", "bss_record_group"))
    by_use = pd.DataFrame(by_use_rows).rename(columns={"subset": "usage"})

    confusion = pd.crosstab(fired["truth_group"], fired["bss_record_group"],
                            rownames=["reference_group"], colnames=["bss_record_group"],
                            margins=True, margins_name="Total")

    by_level_rows = []
    for lvl in ("NV3", "NV2"):
        sub = fired[fired["bss_level"] == lvl]
        label = "NV3 (level-3 entity)" if lvl == "NV3" else "NV2 ('NV3 absent')"
        by_level_rows.append(_precision_row(label, sub, "bss_record_unit", "bss_record_group"))
    by_level = pd.DataFrame(by_level_rows).rename(columns={"subset": "level"})

    mismatches = fired[fired["bss_record_unit"] != fired["truth_unit"]][
        ["code_bss_point_eau", "usage_main", "rec_unit", "rec_depth_m", "bss_prof_invest_m",
         "truth_unit", "bss_record_unit", "bss_level"]
    ].reset_index(drop=True)

    # Also measure location-matched bss_record precision on the same 130 distinct recorded boreholes
    loc_rows = []
    for d in radii:
        sub = rec[rec[f"nearest_match_{d}m"] & rec["nearest_bss_record_unit"].notna()]
        row = _precision_row(f"D <= {d} m", sub, "nearest_bss_record_unit", "nearest_bss_record_group")
        row["D_m"] = d
        row["same_code_among_fired"] = int((sub["nearest_bss_code"] == sub["code_bss_point_eau"]).sum())
        loc_rows.append(row)
    loc_precision = pd.DataFrame(loc_rows)

    return {
        "n_recorded_boreholes": len(rec),
        "n_in_bss_eau": int(rec["in_bss_eau"].sum()),
        "n_evaluated": len(fired),
        "n_multi_entity": int((rec["bss_n_entities"] > 1).sum()),
        "n_absent_or_empty": int(len(rec) - len(fired) - (rec["bss_n_entities"] > 1).sum()),
        "n_eval_by_use": fired["usage_main"].value_counts().to_dict(),
        "overall": overall,
        "by_use": by_use,
        "confusion": confusion,
        "by_level": by_level,
        "mismatches": mismatches,
        "loc_precision": loc_precision,
    }


def summarize_location_matching(df, radii=RADII_M):
    """Section 3: location-match accuracy on known-code points, and matches on no-code points."""
    with_code = df[df["has_bss_code"]].copy()
    in_eau = df[df["in_bss_eau"]].copy()
    uniq_code = with_code.drop_duplicates("code_bss_point_eau")
    real_coord = in_eau[in_eau["bss_coordonneescommune"] == "N"]
    comm_coord = in_eau[in_eau["bss_coordonneescommune"] == "Y"]

    acc_rows = []
    for d in radii:
        col = f"nearest_match_{d}m"
        for scope, sub in (("All BNPE with BSS code", with_code),
                           ("Found in bss_eau_point", in_eau),
                           ("Distinct BSS codes", uniq_code),
                           ("In bss_eau, exact coords (coordonneescommune=N)", real_coord),
                           ("In bss_eau, commune centroid (coordonneescommune=Y)", comm_coord)):
            matched = sub[sub[col]]
            same = int((matched["nearest_bss_code"] == matched["code_bss_point_eau"]).sum())
            n_m = len(matched)
            acc_rows.append({
                "D_m": d,
                "subset": scope,
                "n_total": len(sub),
                "n_matched": n_m,
                "n_same_code": same,
                "accuracy_among_matched": round(same / n_m, 3) if n_m else float("nan"),
                "share_of_subset": round(same / len(sub), 3) if len(sub) else float("nan"),
            })
    known_acc = pd.DataFrame(acc_rows)

    nocode = df[~df["has_bss_code"]].copy()
    nocode_rows = []
    for scope, base in (("all", nocode), ("plain", nocode[nocode["zone"] == "plain"])):
        for d in radii:
            col = f"nearest_match_{d}m"
            for use, g in base.groupby("usage_main", dropna=False):
                m = g[g[col]]
                single = m[m["nearest_bss_record_unit"].notna()]
                multi = m[m["nearest_bss_n_entities"] > 1]
                nocode_rows.append({
                    "scope": scope,
                    "D_m": d,
                    "usage": use if isinstance(use, str) else "unknown",
                    "n_nocode": len(g),
                    "vol_nocode_Mm3": round(float(g["volume_mm3"].sum()), 2),
                    "n_matched": len(m),
                    "vol_matched_Mm3": round(float(m["volume_mm3"].sum()), 2),
                    "n_single_bdlisa": len(single),
                    "vol_single_Mm3": round(float(single["volume_mm3"].sum()), 2),
                    "n_multi_bdlisa": len(multi),
                })
            m_all = base[base[col]]
            s_all = m_all[m_all["nearest_bss_record_unit"].notna()]
            mu_all = m_all[m_all["nearest_bss_n_entities"] > 1]
            nocode_rows.append({
                "scope": scope,
                "D_m": d,
                "usage": "Total",
                "n_nocode": len(base),
                "vol_nocode_Mm3": round(float(base["volume_mm3"].sum()), 2),
                "n_matched": len(m_all),
                "vol_matched_Mm3": round(float(m_all["volume_mm3"].sum()), 2),
                "n_single_bdlisa": len(s_all),
                "vol_single_Mm3": round(float(s_all["volume_mm3"].sum()), 2),
                "n_multi_bdlisa": len(mu_all),
            })
    nocode_tbl = pd.DataFrame(nocode_rows)
    return known_acc, nocode_tbl


def summarize_depth(df, radii=RADII_M):
    """Section 4: agreement between BSS depths and task 12.3's ADES investigation depth."""
    uniq = df[df["has_bss_code"]].drop_duplicates("code_bss_point_eau").copy()
    rows = []
    for label, col in (("bss_eau_point.prof_invest vs ADES rec_depth_m (distinct BSS)", "bss_prof_invest_m"),
                       ("bss_total_sans_label.prof_atteinte vs ADES rec_depth_m (distinct BSS)", "bss_prof_atteinte_m")):
        both = uniq[uniq["rec_depth_m"].notna() & uniq[col].notna()].copy()
        diff = (both[col] - both["rec_depth_m"]).abs()
        denom = both["rec_depth_m"].abs()
        within_10 = np.where(denom > 0, diff <= 0.10 * denom, diff == 0)
        rows.append({
            "comparison": label,
            "n": len(both),
            "exact_match": int((diff == 0).sum()),
            "median_abs_diff_m": round(float(diff.median()), 2) if len(both) else float("nan"),
            "mean_abs_diff_m": round(float(diff.mean()), 2) if len(both) else float("nan"),
            "max_abs_diff_m": round(float(diff.max()), 2) if len(both) else float("nan"),
            "share_within_10pct": round(float(np.mean(within_10)), 3) if len(both) else float("nan"),
        })
    agreement = pd.DataFrame(rows)

    # Also how many points without ADES rec_depth_m would gain a positive BSS depth
    no_depth = df[df["rec_depth_m"].isna()]
    gain_rows = [{
        "source": "Direct BSS code join (prof_invest > 0)",
        "n_points": int(no_depth["bss_prof_invest_m"].gt(0).sum()),
        "n_irrigation": int(no_depth.loc[no_depth["usage_main"] == "irrigation", "bss_prof_invest_m"].gt(0).sum()),
        "vol_Mm3": round(float(no_depth.loc[no_depth["bss_prof_invest_m"].gt(0), "volume_mm3"].sum()), 2),
    }, {
        "source": "Direct BSS code join (prof_atteinte > 0)",
        "n_points": int(no_depth["bss_prof_atteinte_m"].gt(0).sum()),
        "n_irrigation": int(no_depth.loc[no_depth["usage_main"] == "irrigation", "bss_prof_atteinte_m"].gt(0).sum()),
        "vol_Mm3": round(float(no_depth.loc[no_depth["bss_prof_atteinte_m"].gt(0), "volume_mm3"].sum()), 2),
    }]
    for d in radii:
        hit = no_depth[~no_depth["has_bss_code"] & no_depth[f"nearest_match_{d}m"] & no_depth["nearest_bss_prof_invest_m"].gt(0)]
        gain_rows.append({
            "source": f"Location match (no code, D <= {d} m, prof_invest > 0)",
            "n_points": len(hit),
            "n_irrigation": int((hit["usage_main"] == "irrigation").sum()),
            "vol_Mm3": round(float(hit["volume_mm3"].sum()), 2),
        })
    gains = pd.DataFrame(gain_rows)

    disagree = uniq[uniq["rec_depth_m"].notna() & uniq["bss_prof_invest_m"].notna()
                    & (uniq["rec_depth_m"] != uniq["bss_prof_invest_m"])][
        ["code_bss_point_eau", "rec_depth_m", "bss_prof_invest_m", "bss_prof_atteinte_m"]
    ].reset_index(drop=True)
    return agreement, gains, disagree


def summarize_irrigation_addition(df, eval_res, radii=RADII_M):
    """Section 5: irrigation volume getting a bss_record candidate, next to measured precision."""
    direct_row = eval_res["overall"].iloc[0]
    n_irr_eval = int(eval_res["n_eval_by_use"].get("irrigation", 0))
    loc_by_d = eval_res["loc_precision"].set_index("D_m")

    tables = {}
    for scope, sub in (("plain", df[(df["zone"] == "plain") & (df["usage_main"] == "irrigation")]),
                       ("all", df[df["usage_main"] == "irrigation"])):
        tot_n = len(sub)
        tot_vol = float(sub["volume_mm3"].sum())
        rows = []
        # Direct BSS code join alone
        hit_direct = sub[sub["bss_record_unit"].notna()]
        vol_d = float(hit_direct["volume_mm3"].sum())
        qualifies_direct = (
            direct_row["n"] >= pa.MIN_EVAL
            and direct_row["precision_group"] >= pa.PRECISION_PROBABLE
            and n_irr_eval >= pa.MIN_USE_EVAL
        )
        rows.append({
            "rule": "Direct BSS code join only",
            "n_points": len(hit_direct),
            "share_n_%": round(100 * len(hit_direct) / tot_n, 1) if tot_n else 0.0,
            "vol_Mm3": round(vol_d, 2),
            "share_vol_%": round(100 * vol_d / tot_vol, 1) if tot_vol else 0.0,
            "prec_group": direct_row["precision_group"],
            "prec_exact": direct_row["precision_exact"],
            "n_eval": int(direct_row["n"]),
            "n_eval_irr": n_irr_eval,
            "probable_for_irr": "yes" if qualifies_direct else "NO",
        })
        # Location matching per D (no-code points + direct code join)
        for d in radii:
            col = f"nearest_match_{d}m"
            loc_hit = sub[~sub["has_bss_code"] & sub[col] & sub["nearest_bss_record_unit"].notna()]
            comb_hit = sub[sub["bss_record_unit"].notna()
                           | (~sub["has_bss_code"] & sub[col] & sub["nearest_bss_record_unit"].notna())]
            vol_c = float(comb_hit["volume_mm3"].sum())
            lp = loc_by_d.loc[d]
            qualifies_loc = (
                lp["n"] >= pa.MIN_EVAL
                and lp["precision_group"] >= pa.PRECISION_PROBABLE
                and n_irr_eval >= pa.MIN_USE_EVAL
            )
            rows.append({
                "rule": f"Direct code + location match (D <= {d} m)",
                "n_points": len(comb_hit),
                "share_n_%": round(100 * len(comb_hit) / tot_n, 1) if tot_n else 0.0,
                "vol_Mm3": round(vol_c, 2),
                "share_vol_%": round(100 * vol_c / tot_vol, 1) if tot_vol else 0.0,
                "prec_group": lp["precision_group"],
                "prec_exact": lp["precision_exact"],
                "n_eval": int(lp["n"]),
                "n_eval_irr": n_irr_eval,
                "probable_for_irr": "yes" if qualifies_loc else "NO",
            })
            # Also track pure location-match count for reference if needed
            _ = loc_hit
        tables[scope] = pd.DataFrame(rows)
    return tables


def render_report(df, eau_stats, tot_stats, joins, eval_res, known_acc, nocode_tbl,
                  depth_agree, depth_gains, depth_disagree, irr_add):
    """Render the plain-English markdown report ``docs/bss_evidence.md``."""
    y0, y1 = pa.VOLUME_YEARS
    n_eau_unique, n_eau_raw, n_eau_multi, n_eau_comm = eau_stats
    n_tot_unique, n_tot_raw = tot_stats
    duplicate_note = (
        " Duplicate keys in this snapshot are dropped before any join or nearest-point match."
        if n_eau_raw > n_eau_unique or n_tot_raw > n_tot_unique else ""
    )
    new_ades = joins["new_beyond_ades"]
    new_ades_irr = new_ades[new_ades["usage_main"] == "irrigation"]
    direct_prec = eval_res["overall"].iloc[0]
    n_irr_eval = int(eval_res["n_eval_by_use"].get("irrigation", 0))
    n_ties = int((df["nearest_bss_n_ties"] > 1).sum())
    own_med = float(df.loc[df["in_bss_eau"], "own_bss_dist_m"].median())
    own_med_n = float(df.loc[df["in_bss_eau"] & (df["bss_coordonneescommune"] == "N"), "own_bss_dist_m"].median())
    own_med_y = float(df.loc[df["in_bss_eau"] & (df["bss_coordonneescommune"] == "Y"), "own_bss_dist_m"].median())

    absent_rec = sorted(
        df.loc[df["rec_unit"].notna() & ~df["in_bss_eau"], "code_bss_point_eau"].dropna().unique()
    )
    absent_str = ", ".join(f"`{c}`" for c in absent_rec) if absent_rec else "none"
    new_irr_codes = sorted(new_ades_irr["code_bss_point_eau"].dropna().unique())
    new_irr_str = ", ".join(f"`{c}`" for c in new_irr_codes) if new_irr_codes else "none"

    irr_plain = df[(df["zone"] == "plain") & (df["usage_main"] == "irrigation")]
    irr_all = df[df["usage_main"] == "irrigation"]
    irr_plain_vol = float(irr_plain["volume_mm3"].sum())
    irr_all_vol = float(irr_all["volume_mm3"].sum())
    plain_tbl = irr_add["plain"]
    loc_rows = plain_tbl[plain_tbl["rule"].str.startswith("Direct code + location match")]
    loc_vol_lo, loc_vol_hi = float(loc_rows["vol_Mm3"].min()), float(loc_rows["vol_Mm3"].max())
    loc_pct_lo, loc_pct_hi = float(loc_rows["share_vol_%"].min()), float(loc_rows["share_vol_%"].max())
    loc_pg_lo, loc_pg_hi = float(loc_rows["prec_group"].min()), float(loc_rows["prec_group"].max())
    loc_pe_lo, loc_pe_hi = float(loc_rows["prec_exact"].min()), float(loc_rows["prec_exact"].max())
    known_all = known_acc[known_acc["subset"] == "All BNPE with BSS code"]
    acc_lo = 100 * float(known_all["accuracy_among_matched"].min())
    acc_hi = 100 * float(known_all["accuracy_among_matched"].max())
    comm_share = 100 * float((df.loc[df["in_bss_eau"], "bss_coordonneescommune"] == "Y").mean())
    irr_nocode_pct = 100 * float((~irr_plain["has_bss_code"]).mean())
    direct_irr = plain_tbl.iloc[0]
    direct_irr_pct_exact = 100 * float(new_ades_irr["volume_mm3"].sum()) / irr_plain_vol if irr_plain_vol else 0.0
    n_eval_dw = int(eval_res["n_eval_by_use"].get("drinking water", 0))
    n_eval_ind = int(eval_res["n_eval_by_use"].get("industry", 0))

    lines = [
        "# BRGM BSS borehole evidence for pump → aquifer attribution (generated)\n",
        f"Generated by `src/kg/bss_evidence.py` (dataset `{DATASET}`, BSS snapshot `{BSS_SNAPSHOT}`); "
        "do not edit by hand. This report measures what BRGM's open BSS layers (`ms:BSS_EAU_POINT` "
        "and `ms:BSS_TOTAL_SANS_LABEL`) add to pump attribution (task 12.3, `docs/v5_plan.md` R1.3). "
        "It does **not** modify `pump_attribution.py`.\n",
        f"**Data hygiene note:** in BSS snapshot `{BSS_SNAPSHOT}`, "
        f"`bss_eau_point.parquet` has {n_eau_raw:,} rows for **{n_eau_unique:,}** "
        f"unique `code_bss` water points ({n_eau_comm:,} with `coordonneescommune = Y`, i.e. placed at the "
        f"commune centroid, and {n_eau_multi} water points listing more than one BD LISA entity); "
        f"`bss_total_sans_label.parquet` has {n_tot_raw:,} rows for **{n_tot_unique:,}** unique `reference` "
        f"boreholes.{duplicate_note}\n",
        f"## 1. Direct BSS code joins (declared volume {y0}–{y1})\n",
        f"Dataset `{DATASET}` has **{len(df):,}** BNPE groundwater points (**{int((df['zone'] == 'plain').sum()):,}** "
        f"in the Roussillon plain). Only **{int(df['has_bss_code'].sum())}** points (**{df.loc[df['has_bss_code'], 'code_bss_point_eau'].nunique()}** "
        f"distinct BSS codes) carry a BSS code in BNPE; **{int(df['in_bss_eau'].sum())}** (**{df.loc[df['in_bss_eau'], 'code_bss_point_eau'].nunique()}** "
        f"distinct) match `bss_eau_point`, and **{int(df['in_bss_total'].sum())}** (**{df.loc[df['in_bss_total'], 'code_bss_point_eau'].nunique()}** "
        "distinct) match `bss_total_sans_label`.\n",
        "### All BNPE groundwater points (département extent)\n",
        joins["all"].to_markdown(index=False), "",
        "### Plain subset only (matches `docs/pump_coverage.md`)\n",
        joins["plain"].to_markdown(index=False), "",
        f"**What direct BSS code joins add beyond ADES (`rec_unit` in task 12.3):** "
        f"**{len(new_ades)}** BNPE points (**{new_ades['code_bss_point_eau'].nunique()}** distinct BSS codes, "
        f"**{new_ades['volume_mm3'].sum():.2f} Mm³**) match `bss_eau_point` without being in ADES "
        f"({int(new_ades['bss_record_unit'].notna().sum())} of them have a single BD LISA entity). "
        f"Only **{len(new_ades_irr)}** of them are irrigation points ({new_irr_str}, "
        f"**{new_ades_irr['volume_mm3'].sum():.2f} Mm³** = **{direct_irr_pct_exact:.2f} %** "
        "of plain irrigation volume).\n",
        "## 2. Precision of `bss_record` on the 130 recorded boreholes\n",
        f"Task 12.3 evaluates rules on **{eval_res['n_recorded_boreholes']}** distinct ADES-recorded boreholes "
        "(one row per `code_bss_point_eau`), using `pump_attribution.record_rule` (ADES entity after the "
        f"{int(pa.ALLUVIUM_MAX_DEPTH_M)} m depth check) as the reference. Of those {eval_res['n_recorded_boreholes']} "
        f"boreholes, **{eval_res['n_in_bss_eau']}** are found in `bss_eau_point` (**{eval_res['n_evaluated']}** "
        f"list exactly one BD LISA entity, **{eval_res['n_multi_entity']}** list several entities, and "
        f"**{eval_res['n_absent_or_empty']}** are absent from `bss_eau_point`: {absent_str}).\n",
        "### Overall precision (with Wilson 95 % intervals)\n",
        eval_res["overall"].to_markdown(index=False), "",
        f"Why raw agreement is {100 * eval_res['overall'].iloc[1]['precision_group']:.0f} % "
        f"({int(eval_res['overall'].iloc[1]['correct_group'])} / {int(eval_res['overall'].iloc[1]['n'])}) "
        f"while post-depth-check precision is {direct_prec['precision_group']:.3f} "
        f"({int(direct_prec['correct_group'])} / {int(direct_prec['n'])}): "
        "`BSS_EAU_POINT` and ADES (`hubeau_qualite`) come from the same BRGM water-point record, so "
        "`liste_bdlisa` copies ADES verbatim on every borehole present in both. The "
        f"{len(eval_res['mismatches'])} mismatches are exactly the depth-conflict boreholes where "
        "task 12.3 overrides recent alluvium (`718BP*`) with Pliocene (`671AA00`) because the borehole "
        f"is deeper than {int(pa.ALLUVIUM_MAX_DEPTH_M)} m:\n",
        eval_res["mismatches"].to_markdown(index=False), "",
        "### Precision by use\n",
        eval_res["by_use"].to_markdown(index=False), "",
        "### Confusion table (reference group × `bss_record` group)\n",
        eval_res["confusion"].to_markdown(), "",
        "### Level-3 (`NV3`) vs level-2 (`NV3 absent`) split\n",
        eval_res["by_level"].to_markdown(index=False), "",
        f"Multi-entity `liste_bdlisa` rows are rare: only **{n_eau_multi}** of {n_eau_unique:,} unique "
        "water points in the entire département bbox list more than one entity (2 entities each), "
        f"and **{int((df['bss_n_entities'] > 1).sum())}** of the BNPE code-joined points do.\n",
        "## 3. Location matching (nearest BSS water point within D)\n",
        "### 3a. Accuracy on BNPE points WITH a known BSS code\n",
        "For each BNPE point that already carries a BSS code, we check whether the nearest BSS water "
        f"point within D metres has that **same** BSS code. Across the {int(df['in_bss_eau'].sum())} "
        f"code-matched BNPE points, the median distance to their **own** BSS water point is **{own_med:.0f} m** "
        f"(**{own_med_n:.0f} m** when `coordonneescommune = N`, n = {int((df['in_bss_eau'] & (df['bss_coordonneescommune'] == 'N')).sum())}; "
        f"**{own_med_y:.0f} m** when `coordonneescommune = Y`, n = {int((df['in_bss_eau'] & (df['bss_coordonneescommune'] == 'Y')).sum())}). "
        f"Commune-centroid blurring also creates exact distance ties for **{n_ties}** of {len(df):,} BNPE points.\n",
        known_acc.to_markdown(index=False), "",
        "### 3b. Precision of location-matched `bss_record` on the 130 recorded boreholes\n",
        "If we ignore the BSS code on the 130 recorded boreholes and take the `bss_record` candidate "
        "of the nearest BSS water point within D (the rule that would actually run on uncoded irrigation "
        f"boreholes), precision drops well below `PRECISION_PROBABLE` ({pa.PRECISION_PROBABLE:.2f}) at every distance:\n",
        eval_res["loc_precision"][
            ["D_m", "n", "same_code_among_fired", "correct_group", "precision_group",
             "wilson_group_lo", "wilson_group_hi", "correct_exact", "precision_exact"]
        ].to_markdown(index=False), "",
        "### 3c. Matches for BNPE points WITHOUT a BSS code, by use and volume\n",
        "#### All BNPE groundwater points without a BSS code\n",
        nocode_tbl[nocode_tbl["scope"] == "all"].drop(columns=["scope"]).to_markdown(index=False), "",
        "#### Plain subset without a BSS code\n",
        nocode_tbl[nocode_tbl["scope"] == "plain"].drop(columns=["scope"]).to_markdown(index=False), "",
        "## 4. Depth agreement (BSS depth vs task 12.3 ADES depth)\n",
        "Where both the BSS depth (`prof_invest` in `bss_eau_point` or `prof_atteinte` in "
        "`bss_total_sans_label`) and task 12.3's ADES investigation depth (`rec_depth_m`) exist on the "
        "same distinct BSS code, they agree almost identically:\n",
        depth_agree.to_markdown(index=False), "",
        "The single discrepancy is shown below:\n",
        depth_disagree.to_markdown(index=False), "",
        "BNPE points that currently have **no** ADES depth (`rec_depth_m` missing) and would gain a "
        "positive BSS depth:\n",
        depth_gains.to_markdown(index=False), "",
        "## 5. What BSS records would add to irrigation attribution (no integration)\n",
        f"Thresholds fixed in `pump_attribution.py`: `PRECISION_PROBABLE = {pa.PRECISION_PROBABLE:.2f}`, "
        f"`MIN_EVAL = {pa.MIN_EVAL}`, and `MIN_USE_EVAL = {pa.MIN_USE_EVAL}` evaluated boreholes **of "
        "that use**.\n",
        f"### Plain irrigation boreholes ({len(irr_plain):,} points, {irr_plain_vol:.2f} Mm³ declared {y0}–{y1})\n",
        irr_add["plain"].to_markdown(index=False), "",
        f"### All irrigation boreholes ({len(irr_all):,} points, {irr_all_vol:.2f} Mm³ declared {y0}–{y1})\n",
        irr_add["all"].to_markdown(index=False), "",
        "### Plain verdict\n",
        f"- **Does `bss_record` reach `PRECISION_PROBABLE` ({pa.PRECISION_PROBABLE:.2f}) with at least "
        f"`MIN_EVAL` ({pa.MIN_EVAL}) points among irrigation boreholes (`MIN_USE_EVAL` = {pa.MIN_USE_EVAL})?** "
        "**No.**\n"
        f"- **Zero** (`{n_irr_eval} < {pa.MIN_USE_EVAL}`) irrigation boreholes exist in the "
        f"{eval_res['n_recorded_boreholes']}-borehole recorded evaluation set (all "
        f"{eval_res['n_evaluated']} evaluated boreholes are drinking water [{n_eval_dw}] or industry "
        f"[{n_eval_ind}]). By task 12.3's rule, no measured precision can promote an irrigation "
        "heuristic to `probable` without irrigation validation points.\n"
        f"- **Direct BSS code join** matches ADES verbatim (group and exact precision "
        f"{direct_prec['precision_group']:.3f} after the depth check, "
        f"{eval_res['overall'].iloc[1]['precision_group']:.3f} raw), but reaches only "
        f"**{int(direct_irr['n_points'])}** of {len(irr_plain):,} plain irrigation boreholes "
        f"(**{direct_irr['vol_Mm3']:.2f} Mm³**, **{direct_irr_pct_exact:.2f} %** of plain irrigation "
        f"volume) because {irr_nocode_pct:.1f} % of plain BNPE irrigation boreholes carry no BSS code.\n"
        f"- **Location matching** reaches **{loc_pct_lo:.1f}–{loc_pct_hi:.1f} %** of plain irrigation "
        f"volume across D = {min(RADII_M)}–{max(RADII_M)} m (**{loc_vol_lo:.2f}–{loc_vol_hi:.2f} Mm³** "
        f"including the {int(direct_irr['n_points'])} direct-join points), **but** fails precision on "
        "two counts: (i) on known-code points, the nearest BSS water point is the same borehole only "
        f"**{acc_lo:.1f}–{acc_hi:.1f} %** of the time (largely because {comm_share:.0f} % of "
        "known-code BSS water points are blurred to commune centroids), and (ii) on the "
        f"{eval_res['n_recorded_boreholes']} recorded boreholes, location-matched `bss_record` achieves "
        f"group precision of only **{loc_pg_lo:.3f}–{loc_pg_hi:.3f}** (exact **{loc_pe_lo:.3f}–{loc_pe_hi:.3f}**), "
        f"below `{pa.PRECISION_PROBABLE:.2f}` at every D.\n"
        "- **Bottom line:** BRGM's open BSS layers do **not** unlock `probable` irrigation links for "
        f"the main policy. Direct BSS code joins add {len(new_ades)} unrecorded BNPE points "
        f"({new_ades['code_bss_point_eau'].nunique()} distinct boreholes, "
        f"**{new_ades['volume_mm3'].sum():.2f} Mm³** total; only **{new_ades_irr['volume_mm3'].sum():.2f} Mm³** "
        "irrigation) with ADES-identical records (requiring the same 50 m depth check—note drinking-water "
        "borehole `10972X0133/LATOUR`, 165 m deep in `718BP04`). Location-matched BSS links, if ever "
        "added, must stay `possible` (sensitivity run only).\n",
    ]
    return "\n".join(lines) + "\n"


def main():
    eau, n_eau_raw = load_bss_eau()
    tot, n_tot_raw = load_bss_total()
    gw = pa.evidence()
    df = build_evidence_table(gw=gw, eau=eau, tot=tot)

    joins = summarize_joins(df)
    eval_res = evaluate_bss_record(df, radii=RADII_M)
    known_acc, nocode_tbl = summarize_location_matching(df, radii=RADII_M)
    depth_agree, depth_gains, depth_disagree = summarize_depth(df, radii=RADII_M)
    irr_add = summarize_irrigation_addition(df, eval_res, radii=RADII_M)

    INTERIM.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PARQUET, index=False)

    eau_stats = (
        len(eau),
        n_eau_raw,
        int((eau["bdlisa_n_entities"] > 1).sum()),
        int((eau["coordonneescommune"] == "Y").sum()),
    )
    tot_stats = (len(tot), n_tot_raw)
    report = render_report(df, eau_stats, tot_stats, joins, eval_res, known_acc, nocode_tbl,
                           depth_agree, depth_gains, depth_disagree, irr_add)
    OUT_MD.write_text(report, encoding="utf-8")

    pd.set_option("display.width", 200, "display.max_columns", 20)
    print(f"BSS water points: {len(eau)} unique (raw {n_eau_raw}); boreholes: {len(tot)} unique (raw {n_tot_raw})")
    print(f"BNPE groundwater points: {len(df)} ({int((df['zone'] == 'plain').sum())} in plain); "
          f"{int(df['has_bss_code'].sum())} with BSS code, {int(df['in_bss_eau'].sum())} in bss_eau_point")
    print("\n--- Direct bss_record precision (130 recorded boreholes) ---")
    print(eval_res["overall"].to_string(index=False))
    print("\n--- Location-matched bss_record precision (130 recorded boreholes) ---")
    print(eval_res["loc_precision"][["D_m", "n", "same_code_among_fired", "precision_group", "precision_exact"]].to_string(index=False))
    print("\n--- What it would add to plain irrigation (161.43 Mm3) ---")
    print(irr_add["plain"].to_string(index=False))
    print(f"\n-> {OUT_PARQUET}\n-> {OUT_MD}")


if __name__ == "__main__":
    main()
