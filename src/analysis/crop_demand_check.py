"""Order-of-magnitude check of the crop-demand index against declared irrigation (BNPE).

    PFE_DATASET=v4 python -m src.analysis.crop_demand_check

Plain = PLAIN_BBOX, the zone of the BNPE profile (src/analysis/bnpe_profile.py), without
margin. Parcels of each RPG edition are clipped to it; each piece takes the weekly ETP and
rain of its nearest SAFRAN cell; the potential demand of each crop class is summed over
the calendar year of the edition with the formula of src/dataset/crop_demand.py, and set
against the declared irrigation and canal-intake volumes of the plain (bnpe_annual.csv).

What it can show: whether the index has the right order of magnitude, and what share of
the irrigable demand the declared water could cover. What it cannot: declared volumes
are partly flat-rate (60 % of the groundwater irrigation volume), the surface irrigation
volume barely changes between years, gross volumes include conveyance and field losses,
and canal water also feeds return flow to the alluvium. Year-to-year agreement is not
expected, and agreement in size is a consistency check, not a validation.

Output: data/interim/crop_demand_plain_check.csv (Mm3 per year), printed
"""
import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Polygon

from src.analysis.piezo_profile import PLAIN_BBOX
from src.config import CRS_L93, CRS_WGS84, DATASET_DIR, INTERIM
from src.dataset.build import nearest_cell
from src.dataset.crop_demand import code_to_class, kc_weekly, load_classes, rpg_years

OUT = INTERIM / "crop_demand_plain_check.csv"


def plain_polygon_l93():
    lon0, lat0, lon1, lat1 = PLAIN_BBOX
    t = np.linspace(0, 1, 101)
    lon = np.concatenate([lon0 + (lon1 - lon0) * t, np.full(101, lon1), lon1 - (lon1 - lon0) * t, np.full(101, lon0)])
    lat = np.concatenate([np.full(101, lat0), lat0 + (lat1 - lat0) * t, np.full(101, lat1), lat1 - (lat1 - lat0) * t])
    pts = gpd.GeoSeries.from_xy(lon, lat, crs=CRS_WGS84).to_crs(CRS_L93)
    return Polygon(zip(pts.x, pts.y))


def plain_areas(year, plain, classes):
    """Clipped ha inside the plain by SAFRAN cell x crop class, for one RPG edition."""
    g = gpd.read_parquet(INTERIM / f"rpg_dept_{year}.parquet").set_crs(CRS_L93, allow_override=True)
    g = g[g.intersects(plain)].copy()
    g["geometry"] = g.geometry.make_valid().intersection(plain)
    g = g[~g.geometry.is_empty]
    g["crop_class"] = code_to_class(g["CODE_CULTU"].to_numpy(), g["CODE_GROUP"].to_numpy(), classes).to_numpy()
    g["ha"] = g.area / 1e4
    pts = gpd.GeoDataFrame(g[["crop_class", "ha"]], geometry=g.representative_point(), crs=CRS_L93)
    j = nearest_cell(pts)
    return j.groupby(["cell_id", "crop_class"])["ha"].sum()


def main():
    classes = load_classes()
    forcing = pd.read_parquet(DATASET_DIR / "forcing_weekly.parquet", columns=["cell_id", "week", "ETP", "rain"])
    weeks = pd.DatetimeIndex(sorted(forcing["week"].unique()))
    kc = kc_weekly(weeks, classes)
    plain = plain_polygon_l93()
    bnpe = pd.read_csv(INTERIM / "bnpe_annual.csv")
    bnpe = bnpe[bnpe["zone"] == "plain"].groupby(["annee", "usage"])["volume_m3"].sum().unstack()
    rows = []
    for year in rpg_years():
        area = plain_areas(year, plain, classes)
        wk = weeks[weeks.year == year]
        total = {}
        for cell, cell_area in area.groupby(level="cell_id"):
            fc = forcing[forcing["cell_id"] == cell].set_index("week").reindex(wk)
            need_mm = kc.loc[wk].mul(fc["ETP"], axis=0).sub(fc["rain"], axis=0).clip(lower=0).sum()
            for (_, c), ha in cell_area.items():
                total[c] = total.get(c, 0.0) + ha * need_mm.get(c, 0.0) * 10.0
        by_assumption = pd.Series(total).groupby(classes["irrigation_assumption"]).sum() / 1e6
        ha_by = area.groupby(classes["irrigation_assumption"].reindex(area.index.get_level_values("crop_class")).to_numpy()).sum()
        rows.append({
            "year": year, "weeks": len(wk),
            "irrigable_ha": round(ha_by.get("usually", 0) + ha_by.get("partly", 0)),
            "demand_usually_Mm3": round(by_assumption.get("usually", 0.0), 1),
            "demand_partly_Mm3": round(by_assumption.get("partly", 0.0), 1),
            "declared_irrigation_Mm3": round(bnpe.loc[year, "irrigation"] / 1e6, 1) if year in bnpe.index else np.nan,
            "declared_canals_Mm3": round(bnpe.loc[year, "canals"] / 1e6, 1) if year in bnpe.index else np.nan,
        })
    t = pd.DataFrame(rows).set_index("year")
    t["demand_irrigable_Mm3"] = t["demand_usually_Mm3"] + t["demand_partly_Mm3"]
    t.to_csv(OUT)
    print(t.to_string())
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
