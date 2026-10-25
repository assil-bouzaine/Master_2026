"""Separate land-use change from registration change in the RPG (LU-1 check).

    python -m src.analysis.rpg_coverage

Two editions are compared on the plain (PLAIN_BBOX), by geometry, never by parcel IDs
(there is no lineage across years, CQ7). For each harmonised crop class, the change in
declared area between editions y0 and y1 is split exactly into

    net = conversion + new - dropped

  conversion  change on land declared in both years (the stable footprint): what the
              declarations show as a crop change
  new         land declared in y1 only (newly declared, or newly drawn)
  dropped     land declared in y0 only (no longer declared)

A class that grows mainly on new land grows by registration, not by conversion. Edges
redrawn between editions put thin slivers into new and dropped; they cancel out in net.

Output: data/interim/rpg_coverage_plain.csv (ha by pair x class); printed summary
"""
import geopandas as gpd
import pandas as pd

from src.analysis.crop_demand_check import plain_polygon_l93
from src.config import CRS_L93, INTERIM
from src.dataset.crop_demand import code_to_class, load_classes, rpg_years

OUT = INTERIM / "rpg_coverage_plain.csv"


def plain_parcels(year, plain, classes):
    g = gpd.read_parquet(INTERIM / f"rpg_dept_{year}.parquet").set_crs(CRS_L93, allow_override=True)
    g = g[g.intersects(plain)].copy()
    g["geometry"] = g.geometry.make_valid().intersection(plain)
    g = g[~g.geometry.is_empty]
    g["crop_class"] = code_to_class(g["CODE_CULTU"].to_numpy(), g["CODE_GROUP"].to_numpy(), classes).to_numpy()
    return gpd.GeoDataFrame(g[["crop_class"]], geometry=g.geometry, crs=CRS_L93)


def split_change(g0, g1):
    """ha by class: area0, area1, net, conversion, new, dropped."""
    x = gpd.overlay(g0.rename(columns={"crop_class": "c0"}), g1.rename(columns={"crop_class": "c1"}),
                    how="intersection", keep_geom_type=True)
    x["ha"] = x.area / 1e4
    t = pd.DataFrame({
        "area0": g0.area.groupby(g0["crop_class"]).sum() / 1e4,
        "area1": g1.area.groupby(g1["crop_class"]).sum() / 1e4,
        "stable_out": x.groupby("c0")["ha"].sum(),  # class in y0, on land declared in y1
        "stable_in": x.groupby("c1")["ha"].sum(),   # class in y1, on land declared in y0
    }).fillna(0.0)
    t["net"] = t["area1"] - t["area0"]
    t["conversion"] = t["stable_in"] - t["stable_out"]
    t["new"] = t["area1"] - t["stable_in"]
    t["dropped"] = t["area0"] - t["stable_out"]
    return t[["area0", "area1", "net", "conversion", "new", "dropped"]]


def main():
    classes = load_classes()
    plain = plain_polygon_l93()
    years = rpg_years()
    pairs = list(zip(years[:-1], years[1:])) + ([(years[0], years[-1])] if len(years) > 2 else [])
    cache, rows = {}, []
    for y0, y1 in pairs:
        for y in (y0, y1):
            if y not in cache:
                cache[y] = plain_parcels(y, plain, classes)
        t = split_change(cache[y0], cache[y1]).assign(y0=y0, y1=y1)
        rows.append(t.rename_axis("crop_class").reset_index())
        tot = t[["area0", "area1", "net", "conversion", "new", "dropped"]].sum()
        print(f"{y0} -> {y1}: declared {tot['area0']:,.0f} -> {tot['area1']:,.0f} ha; "
              f"new land {tot['new']:,.0f} ha, dropped {tot['dropped']:,.0f} ha, "
              f"stable footprint {tot['area1'] - tot['new']:,.0f} ha")
    out = pd.concat(rows, ignore_index=True)
    out = out[["y0", "y1", "crop_class", "area0", "area1", "net", "conversion", "new", "dropped"]].round(1)
    out.to_csv(OUT, index=False)
    print(f"-> {OUT.name}")


if __name__ == "__main__":
    main()
