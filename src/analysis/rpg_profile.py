"""Profile RPG parcels around the working-set piezometers, 2016 vs 2023.

    python -m src.analysis.rpg_profile

A parcel is "within 3 km" when its centroid lies within 3 km of at least one
working-set piezometer (each parcel counted once, whole area).

Inputs : data/raw/rpg/<edition>/**/PARCELLES_GRAPHIQUES.shp
         data/raw/rpg/docs/REF_CULTURES_GROUPES_CULTURES_2023.csv
         data/interim/piezo_working_set.parquet
Outputs: data/interim/rpg_plain_<year>.parquet     parcels in the plain bbox (GeoParquet)
         data/interim/rpg_3km_<year>.parquet       parcels within 3 km
         data/interim/rpg_3km_groups.csv           area share by CODE_GROUP, both years
         reports/figures/rpg_3km_groups.png
"""
import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
import pyogrio

from src.analysis.piezo_profile import PLAIN_BBOX
from src.config import CRS_L93, CRS_WGS84, FIGURES, INTERIM, RAW

RPG = RAW / "rpg"
EDITIONS = {
    "2016": "RPG_2-0__SHP_LAMB93_R76-2016_2016-01-01",
    "2023": "RPG_2-2__SHP_LAMB93_R76_2023-01-01",
}
BUFFER_M = 3000


def group_labels():
    ref = pd.read_csv(RPG / "docs" / "REF_CULTURES_GROUPES_CULTURES_2023.csv",
                      sep=";", encoding="cp1252")
    # the IGN table labels a few group-25 rows inconsistently: take the majority label
    return (ref.groupby("CODE_GROUPE_CULTURE")["LIBELLE_GROUPE_CULTURE"]
               .agg(lambda s: s.value_counts().index[0]))


def plain_bbox_l93():
    lon0, lat0, lon1, lat1 = PLAIN_BBOX
    box = gpd.GeoSeries.from_xy([lon0, lon1], [lat0, lat1], crs=CRS_WGS84).to_crs(CRS_L93)
    # buffer the box so the 3 km zones of edge stations are complete
    x0, y0, x1, y1 = box.total_bounds
    return (x0 - BUFFER_M, y0 - BUFFER_M, x1 + BUFFER_M, y1 + BUFFER_M)


def load_plain(year):
    out = INTERIM / f"rpg_plain_{year}.parquet"
    if out.exists():
        return gpd.read_parquet(out)
    shp = next((RPG / EDITIONS[year]).rglob("PARCELLES_GRAPHIQUES.shp"))
    print(f"  reading {shp.name} ({year}) inside plain bbox ...")
    g = pyogrio.read_dataframe(shp, bbox=plain_bbox_l93())
    g = g.set_crs(CRS_L93, allow_override=True)  # .prj says IGNF:LAMB93 == EPSG:2154
    g["CODE_GROUP"] = pd.to_numeric(g["CODE_GROUP"], errors="coerce").astype("Int64")
    g.to_parquet(out, index=False)
    return g


def main():
    labels = group_labels()
    ws = pd.read_parquet(INTERIM / "piezo_working_set.parquet")
    pts = gpd.GeoSeries.from_xy(ws.x, ws.y, crs=CRS_WGS84).to_crs(CRS_L93)
    zone = pts.buffer(BUFFER_M).union_all()

    rows, shares, hectares = [], {}, {}
    for year in EDITIONS:
        g = load_plain(year)
        near = g[g.centroid.within(zone)].copy()
        near.to_parquet(INTERIM / f"rpg_3km_{year}.parquet", index=False)

        unknown = set(near["CODE_GROUP"].dropna()) - set(labels.index)
        if unknown:
            print(f"  WARNING {year}: CODE_GROUP without label: {sorted(unknown)}")
        rows.append({
            "year": year,
            "parcels_plain_bbox": len(g),
            "parcels_3km": len(near),
            "area_ha_3km": round(near["SURF_PARC"].sum()),
            "median_parcel_ha": round(near["SURF_PARC"].median(), 2),
            "geom_vs_declared_area": round(near.area.sum() / 1e4 / near["SURF_PARC"].sum(), 3),
        })
        ha = near.groupby("CODE_GROUP")["SURF_PARC"].sum()
        hectares[year] = ha
        shares[year] = ha / ha.sum() * 100

    summary = pd.DataFrame(rows).set_index("year")
    comp = pd.DataFrame(shares).fillna(0).round(1)
    comp.insert(0, "label", comp.index.map(labels))
    comp["change_pts"] = (comp["2023"] - comp["2016"]).round(1)
    # shares move when the total declared area moves: always read them with hectares
    ha = pd.DataFrame(hectares).fillna(0).round(0)
    comp["ha_2016"], comp["ha_2023"] = ha["2016"], ha["2023"]
    comp["change_ha"] = comp["ha_2023"] - comp["ha_2016"]
    comp = comp.sort_values("2023", ascending=False)
    comp.to_csv(INTERIM / "rpg_3km_groups.csv")

    print("\nparcels within 3 km of the working-set piezometers")
    print(summary.T.to_string())
    print("\narea share by CODE_GROUP (%)")
    print(comp.to_string())

    # --- Figure: groups above 1 % in either year ---------------------------
    top = comp[(comp["2016"] >= 1) | (comp["2023"] >= 1)].sort_values("ha_2023")
    fig, ax = plt.subplots(figsize=(8, 0.4 * len(top) + 1.5))
    y = range(len(top))
    ax.barh([i + 0.2 for i in y], top["ha_2016"], height=0.4, color="#9db4c0", label="2016")
    ax.barh([i - 0.2 for i in y], top["ha_2023"], height=0.4, color="#2f6690", label="2023")
    ax.set_yticks(list(y), top["label"])
    ax.set_xlabel(f"declared parcel area (ha); total {summary.loc['2016', 'area_ha_3km']:,} ha in 2016, "
                  f"{summary.loc['2023', 'area_ha_3km']:,} ha in 2023")
    ax.set_title(f"RPG land use within {BUFFER_M // 1000} km of the {len(ws)} working-set piezometers")
    ax.legend()
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIGURES / "rpg_3km_groups.png", dpi=150)
    print(f"\nfigure -> {FIGURES / 'rpg_3km_groups.png'}")


if __name__ == "__main__":
    main()
