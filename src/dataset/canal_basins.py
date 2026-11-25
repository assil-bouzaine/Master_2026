"""Split the plain's canal-intake volume by river basin (docs/v5_plan.md, step R1.2).

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m src.dataset.canal_basins

Why this module exists
----------------------
In dataset v4 every well with a canal edge receives the same plain-wide series
(src/dataset/pumping.py canal_series): the weekly sum of every surface-water intake
in the plain with usage "irrigation" or "canals" across the Tet, Agly, Tech and
coastal basins combined. At the alluvium well MILLAS C2-1 (Tet valley), the canal
contribution flips sign between model starts, partly because it receives canal water
diverted in other valleys. Splitting the intakes by river basin lets each well
receive its own river's canal series in dataset v5.

Important caveat on identifiability: BNPE publishes only annual volumes, and
src/dataset/build.py spreads every irrigation/canal intake over the weeks of
April-October using the local SAFRAN climatic deficit max(ETP - rain, 0). Within
a year, every basin's weekly series therefore still tracks the weather (r ~ 0.96
by construction). What the basin split changes is the between-year signal of each
valley (for example, the sharp 2023 drop on the Tet and Agly versus the much
smaller 2022->2023 change on the Tech).

Classification rules
--------------------
Each intake is assigned a basin in {Tet, Agly, Tech, Reart, other, unknown} using
two independent rules, both recorded in the output table:
  1. Name rule: word-boundary keyword match on accent-folded `nom_ouvrage`
     (TET/TÊT, AGLY, TECH, REART/RÉART).
  2. Spatial rule: nearest non-canal BD TOPO reach with a BD Carthage watercourse
     code within INTAKE_SNAP_M (500 m, reusing src/kg/rivers.py's snapshot and
     snapping distance). The first three characters of `code_du_cours_d_eau_bdcarthage`
     give the official Sandre hydrographic sub-sector (Y04 Tet, Y06 Agly, Y02 Tech,
     Y03 Reart; any other coded watercourse maps to "other"). Beyond INTAKE_SNAP_M
     the spatial rule returns "unknown".
  3. Decision: use the name rule when it names a basin, otherwise the spatial rule.
     Where both rules name a basin, disagreements are flagged explicitly and listed
     in the report rather than resolved silently.

Outputs
-------
  data/interim/canal_intakes_basin.parquet  per-intake basin table (both rules + distances)
  docs/canal_basins.md                      diagnostic report (counts, annual volumes,
                                            between-year and within-year correlations,
                                            and the arm-D canal-edge wells)
"""
from __future__ import annotations

import re
import unicodedata

import geopandas as gpd
import numpy as np
import pandas as pd

from src.analysis.piezo_profile import PLAIN_BBOX
from src.config import CRS_L93, CRS_WGS84, DATASET, DATASET_DIR, INTERIM, PROCESSED, RAW, ROOT
from src.dataset.pumping import canal_series
from src.kg.rivers import INTAKE_SNAP_M, snapshot

BASINS = ("Tet", "Agly", "Tech", "Reart", "other", "unknown")
MAIN_BASINS = ("Tet", "Agly", "Tech", "Reart")
CANAL_USAGES = ("irrigation", "canals")

# Word-boundary keywords matched against accent-folded uppercase `nom_ouvrage`.
NAME_KEYWORDS = {
    "Tet": ("TET",),
    "Agly": ("AGLY",),
    "Tech": ("TECH",),
    "Reart": ("REART",),
}

# Sandre / BD Carthage 3-character hydrographic sub-sector prefix -> river basin.
# Every tributary shares its main river's 3-character prefix in BD TOPO.
# Any other coded watercourse (Y01 Alberes coastal streams such as la Ribereta and
# la Massane, Y05 le Bourdigoul, Y07 Salses/Corbieres coastal, Y00 Segre, Y1* Aude,
# O1* Ariege/Hers) maps to "other".
BDCARTHAGE_PREFIX_BASIN = {
    "Y04": "Tet",
    "Y06": "Agly",
    "Y02": "Tech",
    "Y03": "Reart",
}

# Main stems of the four plain rivers (used to assign arm-D canal-edge wells).
MAIN_RIVER_CODES = {
    "Y04-0400": "Tet",
    "Y06-0400": "Agly",
    "Y02-0400": "Tech",
    "Y03-0400": "Reart",
}

OUT_PARQUET = INTERIM / "canal_intakes_basin.parquet"
OUT_REPORT = ROOT / "docs" / "canal_basins.md"
REPORT_YEARS = (2012, 2024)

OUTPUT_COLS = [
    "code_ouvrage",
    "nom_ouvrage",
    "longitude",
    "latitude",
    "cell_id",
    "basin",
    "rule_used",
    "name_basin",
    "spatial_basin",
    "disagreement",
    "snap_distance_m",
    "reach_code",
    "reach_name",
]


def fold_text(text: str | None) -> str:
    """Fold accents and uppercase a string for case- and accent-insensitive matching."""
    if not isinstance(text, str):
        return ""
    norm = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in norm if not unicodedata.combining(ch)).upper()


def classify_name(nom_ouvrage: str | None) -> str | None:
    """Assign a basin from `nom_ouvrage` via word-boundary keywords, or None."""
    folded = fold_text(nom_ouvrage)
    hits = [
        basin
        for basin, keywords in NAME_KEYWORDS.items()
        if any(re.search(rf"\b{kw}\b", folded) for kw in keywords)
    ]
    if len(hits) > 1:
        raise ValueError(f"nom_ouvrage {nom_ouvrage!r} matched multiple basins: {hits}")
    return hits[0] if hits else None


def basin_from_bdcarthage(code: str | None) -> str:
    """Map a BD Carthage watercourse code to a basin; None/empty -> 'unknown'."""
    if not isinstance(code, str) or not code.strip():
        return "unknown"
    return BDCARTHAGE_PREFIX_BASIN.get(code.strip()[:3], "other")


def load_river_reaches() -> gpd.GeoDataFrame:
    """Non-canal BD TOPO reaches carrying a BD Carthage code (Lambert-93)."""
    path = snapshot("bdtopo_hydro") / "troncon_hydrographique.parquet"
    reaches = gpd.read_parquet(
        path,
        columns=[
            "cleabs",
            "nature",
            "code_du_cours_d_eau_bdcarthage",
            "cpx_toponyme_de_cours_d_eau",
            "geometry",
        ],
    )
    if reaches.crs != CRS_L93:
        reaches = reaches.to_crs(CRS_L93)
    mask = (reaches["nature"] != "Canal") & reaches["code_du_cours_d_eau_bdcarthage"].notna()
    return reaches.loc[mask].reset_index(drop=True)


def snap_points_to_reaches(
    points_l93: gpd.GeoSeries,
    reaches: gpd.GeoDataFrame,
    max_dist_m: float | None = INTAKE_SNAP_M,
) -> list[dict[str, object]]:
    """Snap Lambert-93 points to the nearest reach (reusing rivers.py's spatial-index rule).

    When `max_dist_m` is given, only reaches with exact Euclidean distance <= max_dist_m
    are considered (the search buffer is padded by 1 m so polygon approximation of the
    circle never misses a reach just inside `max_dist_m`). When `max_dist_m` is None,
    the globally nearest reach is returned.
    """
    if len(reaches) == 0:
        return [{"reach_code": None, "reach_name": None, "snap_distance_m": np.nan} for _ in points_l93]

    geoms = reaches.geometry.to_numpy()
    codes = reaches["code_du_cours_d_eau_bdcarthage"].to_numpy()
    names = reaches["cpx_toponyme_de_cours_d_eau"].to_numpy()
    sidx = reaches.sindex if max_dist_m is not None else None

    out: list[dict[str, object]] = []
    for pt in points_l93:
        if max_dist_m is not None:
            near = list(sidx.query(pt.buffer(max_dist_m + 1.0), predicate="intersects"))
            if not near:
                out.append({"reach_code": None, "reach_name": None, "snap_distance_m": np.nan})
                continue
            dists = [float(geoms[j].distance(pt)) for j in near]
            best_k = int(np.argmin(dists))
            best_d = dists[best_k]
            if best_d > max_dist_m:
                out.append({"reach_code": None, "reach_name": None, "snap_distance_m": np.nan})
                continue
            j = near[best_k]
        else:
            dists = reaches.geometry.distance(pt).to_numpy(dtype=float)
            j = int(np.argmin(dists))
            best_d = float(dists[j])

        name_val = names[j] if isinstance(names[j], str) else None
        out.append({"reach_code": str(codes[j]), "reach_name": name_val, "snap_distance_m": best_d})
    return out


def select_intakes(
    pw: pd.DataFrame | None = None,
    pts: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Select plain surface-water irrigation/canal intakes exactly as `canal_series` does.

    Returns (intakes_df, weekly_rows_df) where `intakes_df` has one row per distinct
    `code_ouvrage` that contributes to `canal_series`, and `weekly_rows_df` holds their
    matching weekly rows from `pumping_weekly`.
    """
    if pw is None:
        pw = pd.read_parquet(DATASET_DIR / "pumping_weekly.parquet")
    if pts is None:
        pts = pd.read_parquet(DATASET_DIR / "pumping_points.parquet")

    pts_sel = pts[pts["zone"] == "plain"] if "zone" in pts.columns else pts
    pts_sel = pts_sel[pts_sel["source"] == "surface"]
    weekly = pw.merge(pts_sel[["code_ouvrage", "source"]], on="code_ouvrage")
    weekly = weekly[weekly["usage"].isin(CANAL_USAGES)].copy()

    intakes = (
        pts_sel[pts_sel["code_ouvrage"].isin(weekly["code_ouvrage"].unique())]
        .drop_duplicates("code_ouvrage")
        .sort_values("code_ouvrage")
        .reset_index(drop=True)
    )
    return intakes, weekly


def assign_basins(
    intakes: pd.DataFrame,
    reaches: gpd.GeoDataFrame,
    max_dist_m: float = INTAKE_SNAP_M,
) -> pd.DataFrame:
    """Apply both name and spatial rules to each intake and combine them."""
    pts_l93 = gpd.GeoSeries(
        gpd.points_from_xy(intakes["longitude"], intakes["latitude"]),
        crs=CRS_WGS84,
    ).to_crs(CRS_L93)
    snapped = snap_points_to_reaches(pts_l93, reaches, max_dist_m=max_dist_m)

    rows = []
    for row, snap in zip(intakes.itertuples(index=False), snapped):
        nb = classify_name(row.nom_ouvrage)
        sb = basin_from_bdcarthage(snap["reach_code"])
        if nb is not None:
            basin, rule_used = nb, "name"
        elif sb != "unknown":
            basin, rule_used = sb, "spatial"
        else:
            basin, rule_used = "unknown", "none"
        disagree = (nb is not None) and (sb != "unknown") and (nb != sb)
        rows.append(
            {
                "code_ouvrage": row.code_ouvrage,
                "nom_ouvrage": row.nom_ouvrage,
                "longitude": float(row.longitude),
                "latitude": float(row.latitude),
                "cell_id": getattr(row, "cell_id", None),
                "basin": basin,
                "rule_used": rule_used,
                "name_basin": nb,
                "spatial_basin": sb,
                "disagreement": bool(disagree),
                "snap_distance_m": snap["snap_distance_m"],
                "reach_code": snap["reach_code"],
                "reach_name": snap["reach_name"],
            }
        )
    return pd.DataFrame(rows, columns=OUTPUT_COLS)


def canal_series_by_basin(
    intakes_basin: pd.DataFrame,
    weekly_rows: pd.DataFrame | None = None,
    pw: pd.DataFrame | None = None,
    pts: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Weekly canal volume (m3/week) per basin. Columns are BASINS; row sums equal canal_series."""
    if weekly_rows is None:
        _, weekly_rows = select_intakes(pw=pw, pts=pts)
    joined = weekly_rows.merge(intakes_basin[["code_ouvrage", "basin"]], on="code_ouvrage", how="left")
    if joined["basin"].isna().any():
        missing = sorted(joined.loc[joined["basin"].isna(), "code_ouvrage"].unique())
        raise ValueError(f"intakes missing from intakes_basin: {missing[:5]}")
    wide = (
        joined.groupby(["week", "basin"])["volume_m3"]
        .sum()
        .unstack("basin", fill_value=0.0)
        .reindex(columns=list(BASINS), fill_value=0.0)
    )
    return wide


def canal_edge_well_basins(
    edges_d: pd.DataFrame | None = None,
    wells: pd.DataFrame | None = None,
    reaches: gpd.GeoDataFrame | None = None,
) -> pd.DataFrame:
    """Assign each arm-D canal-edge well to the basin of its nearest main river."""
    if edges_d is None:
        edges_d = pd.read_parquet(PROCESSED / "kg" / f"export_{DATASET}_main" / "edges_D.parquet")
    if wells is None:
        wells = pd.read_parquet(DATASET_DIR / "wells.parquet")
    if reaches is None:
        reaches = load_river_reaches()

    canal_wells = sorted(edges_d.loc[edges_d["relation"] == "canal", "dst"].unique())
    sub = wells[wells["code_bss"].isin(canal_wells)].sort_values("code_bss").reset_index(drop=True)
    main_reaches = reaches[
        reaches["code_du_cours_d_eau_bdcarthage"].isin(MAIN_RIVER_CODES)
    ].reset_index(drop=True)

    w_l93 = gpd.GeoSeries(gpd.points_from_xy(sub["x"], sub["y"]), crs=CRS_WGS84).to_crs(CRS_L93)
    snapped = snap_points_to_reaches(w_l93, main_reaches, max_dist_m=None)

    rows = []
    for w, snap in zip(sub.itertuples(index=False), snapped):
        rows.append(
            {
                "code_bss": w.code_bss,
                "libelle_pe": w.libelle_pe if isinstance(w.libelle_pe, str) else "",
                "nom_commune": w.nom_commune if isinstance(w.nom_commune, str) else "",
                "group": w.group,
                "code_bdlisa": w.code_bdlisa,
                "core": bool(w.core),
                "basin": basin_from_bdcarthage(snap["reach_code"]),
                "river_code": snap["reach_code"],
                "river_name": snap["reach_name"],
                "distance_m": round(float(snap["snap_distance_m"]), 1),
            }
        )
    return pd.DataFrame(rows)


def plain_climatic_deficit(
    forcing: pd.DataFrame | None = None,
    cells: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """Weekly and annual (Apr-Sep) climatic deficit averaged over the plain's SAFRAN cells.

    Plain cells are the SAFRAN grid points inside `PLAIN_BBOX` (the same geographic box
    used throughout the project). Returns `(weekly_df, annual_df, n_cells)`.
    """
    if forcing is None:
        forcing = pd.read_parquet(
            DATASET_DIR / "forcing_weekly.parquet",
            columns=["cell_id", "week", "ETP", "rain"],
        )
    if cells is None:
        cells = pd.read_parquet(RAW / "safran" / "grid_cells_66.parquet")

    lon0, lat0, lon1, lat1 = PLAIN_BBOX
    plain_cells = sorted(
        cells.loc[cells["lon"].between(lon0, lon1) & cells["lat"].between(lat0, lat1), "cell_id"].unique()
    )
    f = forcing[forcing["cell_id"].isin(plain_cells)].copy()
    f["def_raw"] = f["ETP"] - f["rain"]
    f["def_pos"] = f["def_raw"].clip(lower=0.0)
    f["def_apr_oct"] = np.where(f["week"].dt.month.between(4, 10), f["def_pos"], 0.0)

    weekly = f.groupby("week")[["def_raw", "def_pos", "def_apr_oct"]].mean()

    apr_sep = f[f["week"].dt.month.between(4, 9)].copy()
    apr_sep["year"] = apr_sep["week"].dt.year
    annual = (
        apr_sep.groupby(["year", "cell_id"])[["def_raw", "def_pos"]]
        .sum()
        .groupby("year")
        .mean()
    )
    return weekly, annual, len(plain_cells)


def _md_table(headers: list[str], rows: list[list[str]], align_right: set[int] | None = None) -> str:
    align_right = align_right or set()
    sep = ["---:" if i in align_right else "---" for i in range(len(headers))]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(sep) + " |",
    ]
    for r in rows:
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines)


def build_report(
    assigned: pd.DataFrame,
    weekly_rows: pd.DataFrame,
    weekly_basin: pd.DataFrame,
    well_basins: pd.DataFrame,
    reaches: gpd.GeoDataFrame,
    weekly_def: pd.DataFrame,
    annual_def: pd.DataFrame,
    n_plain_cells: int,
    max_conservation_diff: float,
) -> str:
    """Build the markdown diagnostic report (`docs/canal_basins.md`)."""
    y0, y1 = REPORT_YEARS
    active_basins = [b for b in BASINS if (assigned["basin"] == b).any()]
    vol_cols = active_basins

    # Annual 2012-2024 volumes (Mm3) and imputed shares
    sw = weekly_rows.merge(assigned[["code_ouvrage", "basin"]], on="code_ouvrage")
    sw["year"] = sw["week"].dt.year
    sw12 = sw[sw["year"].between(y0, y1)]
    ann_mm3 = (
        sw12.groupby(["year", "basin"])["volume_m3"]
        .sum()
        .unstack("basin", fill_value=0.0)
        .reindex(index=range(y0, y1 + 1), columns=vol_cols, fill_value=0.0)
        / 1e6
    )
    ann_mm3["Total"] = ann_mm3.sum(axis=1)

    tot_12_24 = sw12.groupby("basin")["volume_m3"].sum().reindex(vol_cols, fill_value=0.0) / 1e6
    imp_12_24 = (
        sw12[sw12["imputed"]]
        .groupby("basin")["volume_m3"]
        .sum()
        .reindex(vol_cols, fill_value=0.0)
        / 1e6
    )
    sw23_24 = sw12[sw12["year"].isin((2023, 2024))]
    tot_23_24 = sw23_24.groupby("basin")["volume_m3"].sum().reindex(vol_cols, fill_value=0.0) / 1e6
    imp_23_24 = (
        sw23_24[sw23_24["imputed"]]
        .groupby("basin")["volume_m3"]
        .sum()
        .reindex(vol_cols, fill_value=0.0)
        / 1e6
    )
    grand_tot = float(tot_12_24.sum())
    grand_imp = float(imp_12_24.sum())

    # Rule counts and agreement
    both = assigned[assigned["name_basin"].notna() & (assigned["spatial_basin"] != "unknown")]
    n_both = len(both)
    n_agree = int((both["name_basin"] == both["spatial_basin"]).sum())
    disagreements = assigned[assigned["disagreement"]]

    # Table 1: intakes per basin and rule + 2012-2024 share + imputed share
    summary_rows = []
    for b in BASINS:
        sub = assigned[assigned["basin"] == b]
        n_tot = len(sub)
        n_name = int((sub["rule_used"] == "name").sum())
        n_spat = int((sub["rule_used"] == "spatial").sum())
        n_none = int((sub["rule_used"] == "none").sum())
        v = float(tot_12_24.get(b, 0.0))
        sh = 100.0 * v / grand_tot if grand_tot else 0.0
        imp_v = float(imp_12_24.get(b, 0.0))
        imp_sh = 100.0 * imp_v / v if v else 0.0
        v234 = float(tot_23_24.get(b, 0.0))
        i234 = float(imp_23_24.get(b, 0.0))
        imp_sh_234 = 100.0 * i234 / v234 if v234 else 0.0
        summary_rows.append(
            [
                b,
                str(n_tot),
                str(n_name),
                str(n_spat),
                str(n_none),
                f"{v:.2f}",
                f"{sh:.1f}%",
                f"{imp_sh:.1f}%",
                f"{imp_sh_234:.1f}%" if v234 else "—",
            ]
        )
    summary_rows.append(
        [
            "**Total**",
            f"**{len(assigned)}**",
            f"**{int((assigned['rule_used'] == 'name').sum())}**",
            f"**{int((assigned['rule_used'] == 'spatial').sum())}**",
            f"**{int((assigned['rule_used'] == 'none').sum())}**",
            f"**{grand_tot:.2f}**",
            "**100.0%**",
            f"**{100.0 * grand_imp / grand_tot:.1f}%**",
            f"**{100.0 * float(imp_23_24.sum()) / float(tot_23_24.sum()):.1f}%**",
        ]
    )
    t_summary = _md_table(
        [
            "Basin",
            "Intakes",
            "By name",
            "By spatial",
            "Unmatched",
            "2012–2024 (Mm³)",
            "Share",
            "Imputed 2012–2024",
            "Imputed 2023–2024",
        ],
        summary_rows,
        align_right={1, 2, 3, 4, 5, 6, 7, 8},
    )

    # Disagreements section
    if len(disagreements) == 0:
        disagree_md = (
            f"Both rules named a basin for **{n_both}** intakes; they agreed on **{n_agree}/{n_both} "
            f"(100.0%)** with **0 disagreements**."
        )
    else:
        dis_rows = [
            [
                r.code_ouvrage,
                r.nom_ouvrage,
                str(r.name_basin),
                str(r.spatial_basin),
                f"{r.reach_code} ({r.reach_name or 'unnamed'})",
                f"{r.snap_distance_m:.0f}",
            ]
            for r in disagreements.itertuples(index=False)
        ]
        disagree_md = (
            f"Both rules named a basin for **{n_both}** intakes; they agreed on **{n_agree}/{n_both} "
            f"({100.0 * n_agree / n_both:.1f}%)** and disagreed on **{len(disagreements)}** intakes:\n\n"
            + _md_table(
                ["Code", "Intake name", "Name rule", "Spatial rule", "Nearest reach", "Dist (m)"],
                dis_rows,
                align_right={5},
            )
        )

    # Unknowns table (also compute nearest coded reach beyond 500 m for diagnostic transparency)
    unk = assigned[assigned["basin"] == "unknown"].reset_index(drop=True)
    vol_by_o = sw12.groupby("code_ouvrage")["volume_m3"].sum() / 1e6
    if len(unk):
        unk_pts = gpd.GeoSeries(
            gpd.points_from_xy(unk["longitude"], unk["latitude"]), crs=CRS_WGS84
        ).to_crs(CRS_L93)
        unk_nearest = snap_points_to_reaches(unk_pts, reaches, max_dist_m=None)
        unk_rows = []
        for r, nr in zip(unk.itertuples(index=False), unk_nearest):
            nb_hint = basin_from_bdcarthage(nr["reach_code"])
            unk_rows.append(
                [
                    r.code_ouvrage,
                    r.nom_ouvrage,
                    f"{vol_by_o.get(r.code_ouvrage, 0.0):.2f}",
                    f"{nr['reach_code']} ({nr['reach_name'] or 'unnamed'}, {nb_hint})",
                    f"{nr['snap_distance_m']:.0f}",
                ]
            )
        unk_md = _md_table(
            ["Code", "Intake name", "2012–2024 (Mm³)", "Nearest coded reach (beyond 500 m)", "Dist (m)"],
            unk_rows,
            align_right={2, 4},
        )
    else:
        unk_md = "None."

    # 'other' basin intakes table
    oth = assigned[assigned["basin"] == "other"].reset_index(drop=True)
    if len(oth):
        oth_rows = [
            [
                r.code_ouvrage,
                r.nom_ouvrage,
                f"{vol_by_o.get(r.code_ouvrage, 0.0):.2f}",
                f"{r.reach_code} ({r.reach_name or 'unnamed'})",
                f"{r.snap_distance_m:.0f}",
            ]
            for r in oth.itertuples(index=False)
        ]
        oth_md = _md_table(
            ["Code", "Intake name", "2012–2024 (Mm³)", "Snapped reach", "Dist (m)"],
            oth_rows,
            align_right={2, 4},
        )
    else:
        oth_md = "None."

    # Table 2: Annual volumes 2012-2024 (Mm3)
    ann_headers = ["Year", *vol_cols, "Total"]
    ann_rows = []
    for yr in range(y0, y1 + 1):
        ann_rows.append([str(yr), *[f"{ann_mm3.loc[yr, c]:.2f}" for c in [*vol_cols, "Total"]]])
    ann_rows.append(
        [
            "**2012–2024 sum**",
            *[f"**{ann_mm3[c].sum():.2f}**" for c in [*vol_cols, "Total"]],
        ]
    )
    ann_rows.append(
        [
            "**Share of total**",
            *[f"**{100.0 * ann_mm3[c].sum() / ann_mm3['Total'].sum():.1f}%**" for c in [*vol_cols, "Total"]],
        ]
    )
    t_annual = _md_table(ann_headers, ann_rows, align_right=set(range(1, len(ann_headers))))

    # Table 3: Between-year correlations with Apr-Sep climatic deficit and 2022->2023 change
    ann_def_12 = annual_def.loc[y0:y1]
    by_rows = []
    for c in [*vol_cols, "Total"]:
        r_raw = float(ann_mm3[c].corr(ann_def_12["def_raw"]))
        r_pos = float(ann_mm3[c].corr(ann_def_12["def_pos"]))
        v22, v23 = float(ann_mm3.loc[2022, c]), float(ann_mm3.loc[2023, c])
        pct = 100.0 * (v23 - v22) / v22 if v22 else np.nan
        by_rows.append(
            [
                f"**{c}**" if c == "Total" else c,
                f"{r_raw:+.3f}",
                f"{r_pos:+.3f}",
                f"{v22:.2f}",
                f"{v23:.2f}",
                f"{pct:+.1f}%",
            ]
        )
    t_between = _md_table(
        [
            "Basin",
            "r vs Apr–Sep (ETP − rain)",
            "r vs Apr–Sep max(ETP − rain, 0)",
            "2022 (Mm³)",
            "2023 (Mm³)",
            "2022 → 2023",
        ],
        by_rows,
        align_right={1, 2, 3, 4, 5},
    )

    # Table 4: Between-basin annual correlation matrix (2012-2024)
    cmat = ann_mm3[vol_cols].corr()
    cmat_rows = [
        [b, *[f"{cmat.loc[b, c]:+.3f}" for c in vol_cols]]
        for b in vol_cols
    ]
    t_cmat = _md_table(["Basin", *vol_cols], cmat_rows, align_right=set(range(1, len(vol_cols) + 1)))

    # Table 5: Within-year weekly correlations (2012-2024 and full record)
    wk_12 = weekly_basin.loc[f"{y0}-01-01":f"{y1}-12-31"].copy()
    wk_12["Total"] = wk_12.sum(axis=1)
    wk_all = weekly_basin.copy()
    wk_all["Total"] = wk_all.sum(axis=1)
    def_12 = weekly_def.reindex(wk_12.index)
    def_all = weekly_def.reindex(wk_all.index)

    wy_rows = []
    for c in [*vol_cols, "Total"]:
        r_ao_12 = float(wk_12[c].corr(def_12["def_apr_oct"]))
        r_pos_12 = float(wk_12[c].corr(def_12["def_pos"]))
        r_raw_12 = float(wk_12[c].corr(def_12["def_raw"]))
        r_ao_all = float(wk_all[c].corr(def_all["def_apr_oct"]))
        wy_rows.append(
            [
                f"**{c}**" if c == "Total" else c,
                f"{r_ao_12:.3f}",
                f"{r_pos_12:.3f}",
                f"{r_raw_12:.3f}",
                f"{r_ao_all:.3f}",
            ]
        )
    t_within = _md_table(
        [
            "Basin",
            "r vs Apr–Oct deficit (2012–2024)",
            "r vs positive deficit (2012–2024)",
            "r vs raw ETP − rain (2012–2024)",
            "r vs Apr–Oct deficit (2003–2026)",
        ],
        wy_rows,
        align_right={1, 2, 3, 4, 5},
    )

    # Table 6: Arm-D canal-edge wells
    well_rows = [
        [
            r.code_bss,
            r.libelle_pe or "—",
            r.nom_commune or "—",
            r.group,
            "yes" if r.core else "no",
            f"{r.river_name} ({r.river_code})",
            f"{r.distance_m:.0f}",
            f"**{r.basin}**",
        ]
        for r in well_basins.itertuples(index=False)
    ]
    t_wells = _md_table(
        ["Well", "Name", "Commune", "Aquifer group", "Core", "Nearest main river", "Dist (m)", "Basin"],
        well_rows,
        align_right={6},
    )

    imp_tet_all = 100.0 * float(imp_12_24.get("Tet", 0.0)) / float(tot_12_24.get("Tet", 1.0))
    imp_tech_all = 100.0 * float(imp_12_24.get("Tech", 0.0)) / float(tot_12_24.get("Tech", 1.0))
    imp_agly_all = 100.0 * float(imp_12_24.get("Agly", 0.0)) / float(tot_12_24.get("Agly", 1.0))
    imp_oth_all = 100.0 * float(imp_12_24.get("other", 0.0)) / float(tot_12_24.get("other", 1.0))
    imp_agly_234 = 100.0 * float(imp_23_24.get("Agly", 0.0)) / float(tot_23_24.get("Agly", 1.0))
    imp_oth_234 = 100.0 * float(imp_23_24.get("other", 0.0)) / float(tot_23_24.get("other", 1.0))
    imp_tet_234 = 100.0 * float(imp_23_24.get("Tet", 0.0)) / float(tot_23_24.get("Tet", 1.0))
    imp_tech_234 = 100.0 * float(imp_23_24.get("Tech", 0.0)) / float(tot_23_24.get("Tech", 1.0))
    pct_22_23 = {
        c: 100.0 * (float(ann_mm3.loc[2023, c]) - float(ann_mm3.loc[2022, c])) / float(ann_mm3.loc[2022, c])
        for c in vol_cols
        if float(ann_mm3.loc[2022, c]) > 0
    }
    tech_21_22 = (
        100.0 * (float(ann_mm3.loc[2022, "Tech"]) - float(ann_mm3.loc[2021, "Tech"]))
        / float(ann_mm3.loc[2021, "Tech"])
    )
    r_unk_ao = float(wk_12["unknown"].corr(def_12["def_apr_oct"])) if "unknown" in wk_12 else np.nan
    top2_unk_vol = float(vol_by_o.get("OPR0000059760", 0.0) + vol_by_o.get("OPR0000059234", 0.0))
    unk_tot = float(tot_12_24.get("unknown", 0.0))
    top2_unk_share = 100.0 * top2_unk_vol / unk_tot if unk_tot else 0.0

    return f"""# Canal intakes split by river basin (generated)

Generated by `src/dataset/canal_basins.py` (dataset {DATASET}); do not edit by hand.

This report implements step R1.2 of `docs/v5_plan.md` (`gemini_neon_review.md`, fix 5):
splitting the Roussillon plain's surface-water irrigation and canal intakes
(`src/dataset/pumping.py` `canal_series`) by river basin so that in dataset v5 each
alluvium well can receive its own valley's canal series instead of the whole plain's sum.
Conservation check across all {len(weekly_basin)} weeks: maximum absolute difference
between the sum of all basin series and `canal_series()` is `{max_conservation_diff:.2e}` m³/week.

## 1. Intake selection and basin assignment

Selection follows `canal_series()` exactly: plain (`zone == "plain"`), surface-water
(`source == "surface"`) ouvrages in `pumping_points.parquet` that appear in
`pumping_weekly.parquet` with usage `irrigation` or `canals`. That gives
**{len(assigned)} intakes** with **{assigned['nom_ouvrage'].nunique()} distinct names**.

Two independent rules were applied to every intake:
- **Name rule:** word-boundary keyword match on accent-folded `nom_ouvrage`
  (`TET`, `AGLY`, `TECH`, `REART`).
- **Spatial rule:** nearest non-canal BD TOPO reach (`troncon_hydrographique.parquet`,
  pinned snapshot) carrying a BD Carthage watercourse code, within `INTAKE_SNAP_M` =
  {INTAKE_SNAP_M:.0f} m. The 3-character BD Carthage hydrographic sub-sector prefix maps
  each river and all its tributaries to a basin (`Y04` → Tet, `Y06` → Agly, `Y02` → Tech,
  `Y03` → Reart; any other coded watercourse → `other`). Beyond {INTAKE_SNAP_M:.0f} m → `unknown`.
- **Decision:** the name rule when it matches, otherwise the spatial rule.

{t_summary}

Note on `Reart`: **0** plain canal intakes belong to the Réart basin under either rule.
(Two intakes on the Villeneuve-de-la-Raho reservoir lie 1,275 m from a Réart tributary
and stay `unknown` below; hydrologically that reservoir is mainly filled by a Tech
diversion canal.)

### Agreement and disagreements between rules

{disagree_md}

### Unknown intakes ({len(unk)} ouvrages, {unk_tot:.2f} Mm³ in 2012–2024)

None of the {len(unk)} unknown intakes has a main-river keyword in its name, and all lie
more than {INTAKE_SNAP_M:.0f} m from the nearest coded non-canal reach:

{unk_md}

Two intakes account for {top2_unk_share:.0f}% of the unknown volume ({top2_unk_vol:.1f} of
{unk_tot:.1f} Mm³ in 2012–2024):
1. `OPR0000059760` (`PRISE DANS LA RETENUE VILLENEUVE DE LA RAHO`, {vol_by_o.get('OPR0000059760', 0.0):.2f} Mm³)
   draws from an artificial reservoir rather than a river reach.
2. `OPR0000059234` (`PRISE DANS LA BASSE PALAIS DE CONGRES`, {vol_by_o.get('OPR0000059234', 0.0):.2f} Mm³)
   carries coarse coordinates (~1 km from a coded reach) and stops declaring after 2016;
   four replacement ouvrages with the exact same name (`OPR0000140096`, `140097`, `595828`,
   `649838`) sit 7 m from `la Bassa` (`Y0470560`) and are classified as `Tet`. That explains
   why the `unknown` annual total halves after 2016.

### `other` coastal basins ({len(oth)} ouvrages, {float(tot_12_24.get('other', 0.0)):.2f} Mm³ in 2012–2024)

These intakes snap cleanly within {INTAKE_SNAP_M:.0f} m to small coastal streams outside the
four main rivers: Albères streams (`Y01`: `la Ribereta`, `la Massane`, `Agulla d'en Salleres`)
and `le Bourdigoul` (`Y05`):

{oth_md}

## 2. Annual volumes 2012–2024 (Mm³) and imputation

{t_annual}

All imputation inside 2012–2024 occurs in **2023 and 2024** (`gap_ratio` rule for intakes
with missing declarations). Over 2012–2024 as a whole, imputed volume is tiny for the **Tet**
({imp_tet_all:.1f}%) and **Tech** ({imp_tech_all:.1f}%), and higher for **Agly**
({imp_agly_all:.1f}%) and **other** ({imp_oth_all:.1f}%). In 2023–2024 specifically, **Agly**
is {imp_agly_234:.1f}% imputed ({float(imp_23_24.get('Agly', 0.0)):.2f} of
{float(tot_23_24.get('Agly', 0.0)):.2f} Mm³) and **other** is {imp_oth_234:.1f}% imputed,
whereas **Tet** ({imp_tet_234:.1f}%) and **Tech** ({imp_tech_234:.1f}%) remain overwhelmingly
observed.

## 3. Between-year behaviour (2012–2024)

Annual climatic deficit is computed as the April–September sum of `ETP − rain` averaged over
the **{n_plain_cells} SAFRAN cells inside `PLAIN_BBOX`** (`forcing_weekly.parquet` and
`grid_cells_66.parquet`). Both raw `ETP − rain` and clipped `max(ETP − rain, 0)` are shown.

{t_between}

Year-to-year canal volumes do **not** rise with the summer climatic deficit (correlations are
near zero or slightly negative): in the driest summers (2022–2023), low river flows and
prefectural drought restrictions force canal diversions down even though evaporative demand
peaks. Crucially, the valleys respond on different schedules: between 2022 and 2023,
**Agly** changed by **{pct_22_23.get('Agly', 0.0):+.1f}%** and **Tet** by
**{pct_22_23.get('Tet', 0.0):+.1f}%**, while **Tech** changed by only
**{pct_22_23.get('Tech', 0.0):+.1f}%** (having already moved {tech_21_22:+.1f}% from 2021 to 2022).

### Between-basin annual correlations (2012–2024)

{t_cmat}

## 4. Within-year behaviour (weekly series vs weekly climatic deficit)

{t_within}

**Why the within-year correlation stays around 0.93–0.98:** BNPE records only one annual total
per intake. In `src/dataset/build.py`, every irrigation and canal intake's annual total is
distributed across the weeks of April–October proportionally to its SAFRAN cell's positive
climatic deficit `max(ETP − rain, 0)` (zero in November–March). Splitting the intakes by river
basin therefore **does not break the within-year link to weather** — that link is built into
the weekly disaggregation. (`unknown` has a lower pooled correlation, {r_unk_ao:.3f}, only
because its annual level halves after 2016 when `OPR0000059234` stops declaring.) The benefit
of the basin split in v5 is purely the **between-year** separation between valleys (for
example, keeping the Tet's 2023 cut separate from the Tech's and Agly's different trajectories).

## 5. Arm-D wells with a canal edge

The {len(well_basins)} wells carrying a `canal` relation in `data/processed/kg/export_{DATASET}_main/edges_D.parquet`,
assigned to the basin of their nearest main river (`Y04-0400` la Têt, `Y06-0400` l'Agly,
`Y02-0400` le Tech, `Y03-0400` el Reart) from their `wells.parquet` coordinates:

{t_wells}

Four of the five canal-edge wells (including `MILLAS C2-1`, the case that motivated this
split) belong to the **Tet** basin; one (`BARQUA`, Le Barcarès) belongs to the **Agly** basin
(where 2023–2024 canal volumes are mostly imputed — a caveat to carry into v5).
"""


def run(write_outputs: bool = True) -> dict[str, object]:
    """Run the full canal-basin split, conservation check, well mapping and report."""
    pw = pd.read_parquet(DATASET_DIR / "pumping_weekly.parquet")
    pts = pd.read_parquet(DATASET_DIR / "pumping_points.parquet")
    intakes, weekly_rows = select_intakes(pw=pw, pts=pts)
    reaches = load_river_reaches()
    assigned = assign_basins(intakes, reaches, max_dist_m=INTAKE_SNAP_M)
    weekly_basin = canal_series_by_basin(assigned, weekly_rows=weekly_rows)

    expected = canal_series(pw, pts)
    if not weekly_basin.index.equals(expected.index):
        raise AssertionError("weekly_basin index does not match canal_series() index")
    max_diff = float((weekly_basin.sum(axis=1) - expected).abs().max())
    if max_diff > 1e-6:
        raise AssertionError(f"conservation failed: max abs diff = {max_diff}")

    well_basins = canal_edge_well_basins(reaches=reaches)
    weekly_def, annual_def, n_plain_cells = plain_climatic_deficit()
    report = build_report(
        assigned=assigned,
        weekly_rows=weekly_rows,
        weekly_basin=weekly_basin,
        well_basins=well_basins,
        reaches=reaches,
        weekly_def=weekly_def,
        annual_def=annual_def,
        n_plain_cells=n_plain_cells,
        max_conservation_diff=max_diff,
    )

    if write_outputs:
        OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
        assigned.to_parquet(OUT_PARQUET, index=False)
        OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
        OUT_REPORT.write_text(report, encoding="utf-8")

    return {
        "assigned": assigned,
        "weekly_basin": weekly_basin,
        "well_basins": well_basins,
        "max_conservation_diff": max_diff,
    }


def main() -> None:
    res = run(write_outputs=True)
    assigned = res["assigned"]
    counts = assigned["basin"].value_counts().to_dict()
    rules = assigned["rule_used"].value_counts().to_dict()
    n_dis = int(assigned["disagreement"].sum())
    print(f"intakes: {len(assigned)} ({assigned['nom_ouvrage'].nunique()} distinct names)")
    print(f"by basin: {counts}")
    print(f"by rule_used: {rules}; disagreements: {n_dis}")
    print(f"conservation max abs diff: {res['max_conservation_diff']:.2e} m3/week")
    print(f"arm-D canal-edge wells: {len(res['well_basins'])} -> "
          f"{res['well_basins']['basin'].value_counts().to_dict()}")
    print(f"-> {OUT_PARQUET.relative_to(ROOT)}")
    print(f"-> {OUT_REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
