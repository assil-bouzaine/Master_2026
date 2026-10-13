"""BD LISA V3: station entities, vertical stacks, `overlies` edges, vertical well pairs.

    python -m src.analysis.bdlisa_profile

Needs src.ingest.bdlisa (extracted GeoPackage) and src.analysis.piezo_profile
(working set) to have run.

What it does
1. Decodes the attributes of the level-3 entities (milieu, theme, nature).
2. Joins the working-set stations to their BD LISA entity, and reads the
   vertical stack of entities *under each well* (point in elementary polygon
   -> TABLE_PILE_ENTITES_NIV3, ordered by OrdRelatif, 1 = top).
3. Builds the `overlies` edges of the plain: in every elementary polygon of
   the plain, each entity directly overlies the next one in the stack.
4. Finds vertical well pairs (<= 5 km, shallow entity above deep entity) and
   compares their heads week by week: how often is the shallow head above the
   deep head? That decides whether a head-ordering constraint is allowed
   (CLAUDE.md section 3).

Outputs (data/interim/)
    bdlisa_entities_plain.csv     entities present under the plain + attributes
    bdlisa_overlies_plain.csv     upper -> lower edges with polygon count and area
    bdlisa_station_stacks.csv     one row per working-set station
    bdlisa_vertical_pairs.csv     well pairs + head-ordering statistics
Figures (reports/figures/)
    bdlisa_plain_entities_pairs.png   map: outcropping entities, wells, pairs
    bdlisa_pair_head_difference.png   weekly shallow-minus-deep head per pair
"""
import itertools

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyogrio
from shapely.geometry import LineString, box

from src.analysis.piezo_profile import PLAIN_BBOX
from src.config import CRS_L93, CRS_WGS84, FIGURES, INTERIM, RAW
from src.ingest.hubeau_piezo import CHRON, safe_name

GPKG = RAW / "bdlisa" / "BDLISA_V3_OCC-gpkg" / "BDLISA_V3.gpkg"
PAIR_MAX_KM = 5.0
# Only wells this close measure a vertical gradient; farther pairs also carry
# the lateral slope of the water table (heads are in m NGF).
NESTED_MAX_KM = 0.1

# SANDRE nomenclatures, confirmed in Descriptif_donnees_BDLISA_V3.pdf
MILIEU = {"1": "porous", "2": "fissured", "3": "karstic", "11": "fractured"}
MILIEU.update({str(k): "mixed porosity" for k in range(4, 11)})
THEME = {"1": "alluvial", "2": "sedimentary", "3": "basement",
         "4": "intensely folded", "5": "volcanic"}
NATURE = {"5": "aquifer unit", "6": "semi-permeable unit", "7": "impermeable unit"}

# Plain-level grouping used for colours and for the shallow/deep reading.
# Prefix -> (short name, rank in the plain's sequence, top = 1)
GROUPS = {
    "718BP": ("recent alluvium", 1),
    "671AB": ("ancient alluvium", 2),
    "671AA": ("Pliocene multilayer", 3),
    "681AM": ("Corbières karst", 4),
}
# Categorical slots 1-4 of the validated default palette (dataviz skill),
# assigned in fixed order to the plain's sequence, top to bottom.
COLORS = {"recent alluvium": "#2a78d6", "ancient alluvium": "#eb6834",
          "Pliocene multilayer": "#1baf7a", "Corbières karst": "#eda100",
          "other": "#b8b7b1"}
SEASON = {12: "DJF", 1: "DJF", 2: "DJF", 3: "MAM", 4: "MAM", 5: "MAM",
          6: "JJA", 7: "JJA", 8: "JJA", 9: "SON", 10: "SON", 11: "SON"}


def group_of(code):
    for prefix, (name, _) in GROUPS.items():
        if isinstance(code, str) and code.startswith(prefix):
            return name
    return "other"


def plain_box_l93():
    return gpd.GeoSeries([box(*PLAIN_BBOX)], crs=CRS_WGS84).to_crs(CRS_L93)


def load_tables():
    tme = pyogrio.read_dataframe(GPKG, layer="TME", read_geometry=False)
    tme = tme[tme["niveaueh"] == 3].copy()
    for col in ("natureeh", "themeeh", "milieueh"):
        tme[col] = tme[col].astype(str).str.strip()
    tme["milieu"] = tme["milieueh"].map(MILIEU)
    tme["theme"] = tme["themeeh"].map(THEME)
    tme["nature"] = tme["natureeh"].map(NATURE)
    tme = tme.rename(columns={"codeeh": "CodeEH"}).set_index("CodeEH")
    pile = pyogrio.read_dataframe(GPKG, layer="TABLE_PILE_ENTITES_NIV3", read_geometry=False)
    poly = pyogrio.read_dataframe(GPKG, layer="POLYG_ELEMENTAIRES",
                                  bbox=tuple(plain_box_l93().total_bounds))
    poly = poly[poly.intersects(plain_box_l93().iloc[0])].copy()
    poly["area_km2"] = poly.area / 1e6
    return tme, pile, poly


def stacks_of(pile, codepolys):
    """codepoly -> list of CodeEH, top (OrdRelatif 1) to bottom."""
    sub = pile[pile["CodePoly"].isin(set(codepolys))].sort_values(["CodePoly", "OrdRelatif"])
    return sub.groupby("CodePoly")["CodeEH"].apply(list).to_dict()


def entities_and_edges(tme, pile, poly):
    stacks = stacks_of(pile, poly["codepoly"])
    area = poly.set_index("codepoly")["area_km2"]
    rows, edges = [], []
    for cp, stack in stacks.items():
        for pos, code in enumerate(stack, start=1):
            rows.append({"CodeEH": code, "codepoly": cp, "pos": pos, "area_km2": area[cp]})
        for upper, lower in zip(stack, stack[1:]):
            edges.append({"upper": upper, "lower": lower, "codepoly": cp, "area_km2": area[cp]})
    occ = pd.DataFrame(rows)
    ent = occ.groupby("CodeEH").agg(
        n_polygons=("codepoly", "nunique"),
        area_under_plain_km2=("area_km2", "sum"),
        outcrop_area_km2=("area_km2", lambda s: s[occ.loc[s.index, "pos"] == 1].sum()),
        median_pos=("pos", "median"),
    )
    ent = ent.join(tme[["libelleeh", "ordreabseh", "incluseh", "nature", "theme", "milieu"]])
    ent["group"] = [group_of(c) for c in ent.index]
    ent = ent.sort_values(["median_pos", "area_under_plain_km2"], ascending=[True, False])
    e = pd.DataFrame(edges).groupby(["upper", "lower"]).agg(
        n_polygons=("codepoly", "nunique"), area_km2=("area_km2", "sum")).reset_index()
    e = e.sort_values("area_km2", ascending=False)
    return ent, e, stacks


def station_stacks(pile):
    ws = pd.read_parquet(INTERIM / "piezo_working_set.parquet")
    ws = ws[ws["working_set"]].copy()
    pts = gpd.GeoDataFrame(ws, geometry=gpd.points_from_xy(ws["x"], ws["y"]),
                           crs=CRS_WGS84).to_crs(CRS_L93)
    allpoly = pyogrio.read_dataframe(GPKG, layer="POLYG_ELEMENTAIRES",
                                     bbox=tuple(pts.total_bounds + [-1, -1, 1, 1]))
    j = gpd.sjoin(pts, allpoly[["codepoly", "geometry"]], how="left", predicate="within")
    j = j[~j.index.duplicated()]  # a point on a shared edge: keep the first polygon
    stacks = stacks_of(pile, j["codepoly"].dropna())
    j["stack"] = j["codepoly"].map(lambda cp: stacks.get(cp, []))
    j["stack_str"] = j["stack"].map(" > ".join)
    j["entity_in_stack"] = [c in s for c, s in zip(j["code_bdlisa"], j["stack"])]
    j["pos_in_stack"] = [s.index(c) + 1 if c in s else np.nan
                         for c, s in zip(j["code_bdlisa"], j["stack"])]
    j["group"] = j["code_bdlisa"].map(group_of)
    return j


def weekly_heads(code_bss):
    df = pd.read_parquet(CHRON / f"{safe_name(code_bss)}.parquet",
                         columns=["date_mesure", "niveau_nappe_eau", "profondeur_nappe"])
    df["date_mesure"] = pd.to_datetime(df["date_mesure"])
    s = df.set_index("date_mesure").sort_index()
    return s["niveau_nappe_eau"].resample("W").mean().dropna(), s["profondeur_nappe"]


def vertical_pairs(st, edges):
    """Shallow/deep well pairs <= PAIR_MAX_KM in superposed entities.

    `superposed` = the shallow well's entity lies above the deep well's entity
    in at least one elementary polygon of the plain (any depth gap).
    `local` = it also does so in the stack under one of the two wells.
    """
    above = set()  # transitive "is above" from the stacks, not only direct edges
    for (u, l) in zip(edges["upper"], edges["lower"]):
        above.add((u, l))
    changed = True
    while changed:
        new = {(a, d) for (a, b) in above for (c, d) in above if b == c} - above
        above |= new
        changed = bool(new)
    rows = []
    for (_, a), (_, b) in itertools.combinations(st.iterrows(), 2):
        for sh, dp in ((a, b), (b, a)):
            if (sh["code_bdlisa"], dp["code_bdlisa"]) not in above:
                continue
            d_km = sh.geometry.distance(dp.geometry) / 1000
            if d_km > PAIR_MAX_KM:
                continue
            local = any(sh["code_bdlisa"] in s and dp["code_bdlisa"] in s
                        and s.index(sh["code_bdlisa"]) < s.index(dp["code_bdlisa"])
                        for s in (sh["stack"], dp["stack"]))
            rows.append({"shallow": sh["code_bss"], "deep": dp["code_bss"],
                         "shallow_entity": sh["code_bdlisa"], "deep_entity": dp["code_bdlisa"],
                         "shallow_depth_m": sh["profondeur_investigation"],
                         "deep_depth_m": dp["profondeur_investigation"],
                         "distance_km": round(d_km, 2), "local_superposition": local,
                         "nested": d_km <= NESTED_MAX_KM})
    return pd.DataFrame(rows)


def head_ordering(pairs):
    """Weekly shallow-minus-deep head: overall, per season, and since 2016."""
    cache, out, diffs = {}, [], {}
    for code in set(pairs["shallow"]) | set(pairs["deep"]):
        cache[code] = weekly_heads(code)[0]
    for _, p in pairs.iterrows():
        d = (cache[p["shallow"]] - cache[p["deep"]]).dropna()
        key = f"{p['shallow']} / {p['deep']}"
        diffs[key] = d
        row = {"n_weeks": len(d),
               "first_week": d.index.min().date() if len(d) else None,
               "last_week": d.index.max().date() if len(d) else None,
               "median_diff_m": round(d.median(), 2) if len(d) else np.nan,
               "pct_shallow_above": round(100 * (d > 0).mean(), 1) if len(d) else np.nan}
        recent = d[d.index >= "2016-01-01"]
        row["pct_shallow_above_2016on"] = round(100 * (recent > 0).mean(), 1) if len(recent) else np.nan
        for s in ("DJF", "MAM", "JJA", "SON"):
            ds = d[d.index.month.map(SEASON) == s]
            row[f"pct_above_{s}"] = round(100 * (ds > 0).mean(), 1) if len(ds) else np.nan
        out.append(row)
    return pd.concat([pairs.reset_index(drop=True), pd.DataFrame(out)], axis=1), diffs


def artesian_share(codes):
    """Share of daily records with the head above ground (profondeur_nappe < 0)."""
    res = {}
    for c in codes:
        depth = weekly_heads(c)[1].dropna()
        res[c] = round(100 * (depth < 0).mean(), 1) if len(depth) else np.nan
    return pd.Series(res, name="pct_days_artesian")


def plot_map(poly, pile, st, pairs):
    stacks = stacks_of(pile, poly["codepoly"])
    poly = poly.copy()
    poly["top"] = poly["codepoly"].map(lambda cp: stacks.get(cp, [None])[0])
    poly["group"] = poly["top"].map(group_of)
    fig, ax = plt.subplots(figsize=(8, 7), facecolor="#fcfcfb")
    ax.set_facecolor("#fcfcfb")
    for g, sub in poly.groupby("group"):
        sub.plot(ax=ax, color=COLORS[g], alpha=0.35, edgecolor="#fcfcfb", linewidth=0.5)
    plain = plain_box_l93()
    plain.boundary.plot(ax=ax, color="#52514e", linewidth=0.8, linestyle="--")
    lines = [LineString([st.set_index("code_bss").geometry[p["shallow"]],
                         st.set_index("code_bss").geometry[p["deep"]]]) for _, p in pairs.iterrows()]
    if lines:
        gpd.GeoSeries(lines, crs=CRS_L93).plot(ax=ax, color="#0b0b0b", linewidth=1.2)
    for g, sub in st.groupby("group"):
        sub.plot(ax=ax, color=COLORS[g], markersize=40, edgecolor="#fcfcfb", linewidth=1.5,
                 zorder=3)
    handles = [plt.Line2D([], [], marker="s", linestyle="", markersize=10, color=COLORS[g],
                          alpha=0.6, label=f"{g} (outcrop / well)") for g in COLORS]
    handles.append(plt.Line2D([], [], color="#0b0b0b", linewidth=1.2,
                              label=f"vertical well pair (≤ {PAIR_MAX_KM:g} km)"))
    ax.legend(handles=handles, loc="lower left", fontsize=8, frameon=False)
    ax.set_xlim(plain.total_bounds[[0, 2]]); ax.set_ylim(plain.total_bounds[[1, 3]])
    ax.set_axis_off()
    ax.set_title("Roussillon plain: outcropping BD LISA entity, working-set wells and "
                 "vertical pairs", fontsize=10, color="#0b0b0b", loc="left")
    out = FIGURES / "bdlisa_plain_entities_pairs.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_differences(diffs, pairs):
    keys = [k for k in diffs if len(diffs[k])]
    if not keys:
        return None
    fig, ax = plt.subplots(figsize=(8, 0.42 * len(keys) + 1.2), facecolor="#fcfcfb")
    ax.set_facecolor("#fcfcfb")
    order = sorted(keys, key=lambda k: diffs[k].median())
    for i, k in enumerate(order):
        d = diffs[k]
        ax.plot([d.quantile(0.05), d.quantile(0.95)], [i, i], color="#86b6ef", linewidth=2,
                solid_capstyle="round")
        ax.plot([d.quantile(0.25), d.quantile(0.75)], [i, i], color="#2a78d6", linewidth=5,
                solid_capstyle="round")
        ax.plot(d.median(), i, "o", color="#0b0b0b", markersize=4)
    ax.axvline(0, color="#52514e", linewidth=0.8)
    ax.set_yticks(range(len(order)), order, fontsize=7, color="#52514e")
    ax.set_xlabel("weekly head, shallow minus deep well (m)  —  > 0: shallow head above deep",
                  fontsize=8, color="#52514e")
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.grid(axis="x", color="#e5e4df", linewidth=0.5)
    ax.set_title("Head ordering in vertical well pairs (dot = median, bars = IQR and 5–95 %)",
                 fontsize=10, loc="left", color="#0b0b0b")
    out = FIGURES / "bdlisa_pair_head_difference.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return out


def main():
    pd.set_option("display.width", 200, "display.max_columns", 30, "display.max_colwidth", 60)
    tme, pile, poly = load_tables()
    print(f"elementary polygons intersecting the plain bbox: {len(poly)} "
          f"({poly['area_km2'].sum():.0f} km²)")

    ent, edges, _ = entities_and_edges(tme, pile, poly)
    ent.to_csv(INTERIM / "bdlisa_entities_plain.csv")
    edges.to_csv(INTERIM / "bdlisa_overlies_plain.csv", index=False)
    print(f"\nentities under the plain: {len(ent)}  |  direct overlies edges: {len(edges)}")
    print(ent[["libelleeh", "group", "nature", "milieu", "median_pos",
               "outcrop_area_km2", "area_under_plain_km2"]].head(20).round(1))

    st = station_stacks(pile)
    found = st["code_bdlisa"].isin(tme.index)
    print(f"\nworking-set stations: {len(st)}; entity found in BD LISA extract: {found.sum()}")
    print("entities missing from the extract:", sorted(st.loc[~found, "code_bdlisa"].unique()))
    print(f"stations whose entity is in the stack under the well: {st['entity_in_stack'].sum()}")
    print(st.loc[~st["entity_in_stack"], ["code_bss", "code_bdlisa", "stack_str"]].to_string(index=False))
    st["pct_days_artesian"] = st["code_bss"].map(artesian_share(st["code_bss"]))
    keep = ["code_bss", "libelle_pe", "code_bdlisa", "group", "profondeur_investigation",
            "codepoly", "stack_str", "entity_in_stack", "pos_in_stack", "pct_days_artesian"]
    st[keep].to_csv(INTERIM / "bdlisa_station_stacks.csv", index=False)
    print("\nwells with the head ever above ground (artesian days > 0 %):")
    print(st.loc[st["pct_days_artesian"] > 0, ["code_bss", "code_bdlisa", "pct_days_artesian"]]
          .to_string(index=False))

    station_entities = set(st["code_bdlisa"])
    sub = edges[edges["upper"].isin(station_entities) | edges["lower"].isin(station_entities)]
    print("\noverlies edges touching station entities:")
    print(sub.round(1).to_string(index=False))

    pairs = vertical_pairs(st, edges)
    pairs, diffs = head_ordering(pairs)
    pairs.to_csv(INTERIM / "bdlisa_vertical_pairs.csv", index=False)
    print(f"\nvertical well pairs ≤ {PAIR_MAX_KM:g} km: {len(pairs)} "
          f"(local superposition: {int(pairs['local_superposition'].sum())})")
    cols = ["shallow", "deep", "shallow_entity", "deep_entity", "distance_km", "n_weeks",
            "median_diff_m", "pct_shallow_above", "pct_shallow_above_2016on",
            "pct_above_DJF", "pct_above_MAM", "pct_above_JJA", "pct_above_SON"]
    print(pairs[cols].to_string(index=False))
    w = pairs["n_weeks"]
    pooled = sum((diffs[f"{a} / {b}"] > 0).sum() for a, b in zip(pairs["shallow"], pairs["deep"]))
    print(f"\npooled: shallow head above deep head in {100 * pooled / w.sum():.1f}% "
          f"of {w.sum():,} pair-weeks")
    nested = pairs[pairs["nested"]]
    print(f"nested pairs (≤ {NESTED_MAX_KM * 1000:g} m, true vertical gradient): {len(nested)}")
    print(nested[["shallow", "deep", "distance_km", "median_diff_m", "pct_shallow_above",
                  "pct_above_DJF", "pct_above_MAM", "pct_above_JJA", "pct_above_SON"]]
          .to_string(index=False))
    consistent = (pairs["pct_shallow_above"] >= 95) | (pairs["pct_shallow_above"] <= 5)
    print(f"pairs with a consistent ordering (≥95% one way): {consistent.sum()} of {len(pairs)}")

    print("\nmap ->", plot_map(poly, pile, st, pairs))
    print("figure ->", plot_differences(diffs, pairs))


if __name__ == "__main__":
    main()
