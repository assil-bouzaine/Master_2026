"""The crop-demand index (LU-3): clipped areas, the FAO-56 Kc curve, the weekly demand.

    PFE_DATASET=v4 python -m tests.test_crop_demand

1. Synthetic: a 10 ha parcel with 4 ha inside the zone contributes 4 ha (CQ7
   acceptance); an unknown crop code stays in the table as "unmapped"; codes map to the
   harmonised classes; the Kc curve hits Kc_ini / Kc_mid / Kc_end on the FAO-56 stage
   days, on the same calendar dates in leap and common years; perennials keep Kc_ini off
   season, annual crops drop to 0, a winter crop sown in November is growing on
   1 January; years before the first RPG edition use the first one.
2. Foreign land, if built: a zone around Figueres (Spain) is entirely foreign, no well
   zone reaches Spain or Andorra at 3 km.
3. The built output, if present (data are not in git): no negative demand, no unmapped
   area, summer demand far above winter demand, every well on the same weeks, no zone
   outside the RPG extent (checked when the areas are built).
"""
import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

from src.config import CRS_L93, CRS_WGS84, DATASET, DATASET_DIR, INTERIM
from src.dataset.crop_demand import (AREA_OUT, FOREIGN, clipped_area, code_to_class,
                                     derangement, foreign_share, kc_on_dates, kc_weekly,
                                     load_classes, well_buffers, year_map)


def check_clipped_area(classes):
    zone = gpd.GeoDataFrame({"code_bss": ["W"]}, geometry=[box(0, 0, 1000, 1000)], crs=CRS_L93)
    # 400 m x 250 m = 10 ha, of which 400 m x 100 m = 4 ha inside the zone
    parcels = gpd.GeoDataFrame({"CODE_CULTU": ["VRC", "XXX"],
                                "CODE_GROUP": pd.array([21, 99], dtype="Int64")},
                               geometry=[box(900, 0, 1150, 400), box(0, 500, 100, 600)],
                               crs=CRS_L93)
    a = clipped_area(parcels, zone)
    a["crop_class"] = code_to_class(a["CODE_CULTU"].to_numpy(), a["CODE_GROUP"].to_numpy(), classes).to_numpy()
    ha = a.set_index("crop_class")["ha"]
    assert abs(ha["vine"] - 4.0) < 1e-9, ha
    assert abs(ha["unmapped"] - 1.0) < 1e-9, "unknown codes must stay in the denominator"


def check_code_mapping(classes):
    cls = code_to_class(["PVT", "AGR", "ART", "VRC", "JAC"], ["20", "20", "25", "21", "11"], classes)
    assert list(cls) == ["orchard_deciduous", "citrus", "artichoke", "vine", "no_crop"], list(cls)


def kc(classes, name, *dates):
    return kc_on_dates(pd.to_datetime(list(dates)), classes.loc[name])


def check_kc(classes):
    # vine: planted 1 April; 30 d initial, 60 d development, 40 d mid, 80 d late
    for year in (2003, 2004):  # common and leap year: same calendar dates
        d0 = pd.Timestamp(f"{year}-04-01")
        v = kc(classes, "vine", d0, d0 + pd.Timedelta(days=100), d0 + pd.Timedelta(days=209),
               d0 + pd.Timedelta(days=210), f"{year}-01-15")
        assert np.allclose(v, [0.30, 0.70, 0.45, 0.30, 0.30]), (year, v)
        # maize: 150-day season from 1 April, no crop before or after
        m = kc(classes, "maize", d0 - pd.Timedelta(days=1), d0, d0 + pd.Timedelta(days=149),
               d0 + pd.Timedelta(days=150))
        assert np.allclose(m, [0.0, 0.30, 0.35, 0.0]), (year, m)
    w = kc(classes, "winter_cereal", "2004-01-01", "2003-10-31")
    assert w[0] > 0.7 and w[1] == 0.0, w  # growing on 1 January, not yet sown on 31 October
    assert kc(classes, "no_crop", "2004-07-01").max() == 0.0
    k = kc_weekly(pd.to_datetime(["2001-07-15", "2001-01-14"]), classes)
    assert k.loc["2001-07-15", "maize"] > k.loc["2001-01-14", "maize"] == 0.0


def check_derangement():
    codes = [f"W{i}" for i in range(65)]
    d = derangement(codes)
    assert d == derangement(codes), "the placebo must be reproducible"
    assert sorted(d.values()) == sorted(codes) and all(k != v for k, v in d.items())


def check_year_map():
    m = year_map([2005, 2015, 2016, 2019, 2026], [2015, 2016, 2023, 2025])
    assert m == {2005: 2015, 2015: 2015, 2016: 2016, 2019: 2016, 2026: 2025}, m


def check_foreign():
    if not FOREIGN.exists():
        print(f"  {FOREIGN.name} absent: foreign-land checks skipped")
        return
    fig = pd.DataFrame({"code_bss": ["FIGUERES"], "x": [2.96], "y": [42.27]})
    assert foreign_share(well_buffers(fig)).iloc[0] > 0.999
    wells = pd.read_parquet(DATASET_DIR / "wells.parquet")
    assert (foreign_share(well_buffers(wells)) == 0).all(), "a well zone reaches Spain or Andorra"


def check_built(classes):
    out = INTERIM / f"crop_demand_weekly_{DATASET}.parquet"
    if not out.exists():
        print(f"  {out.name} absent: real-data checks skipped")
        return
    d = pd.read_parquet(out)
    cols = [c for c in d.columns if c.startswith("demand_")]
    assert (d[cols] >= 0).all().all(), "negative demand"
    a = pd.read_parquet(AREA_OUT)
    cls = code_to_class(a["CODE_CULTU"].to_numpy(), a["CODE_GROUP"].to_numpy(), classes)
    assert a.loc[(cls == "unmapped").to_numpy(), "ha"].sum() == 0, "unmapped crop codes"
    m = d.assign(mo=d["week"].dt.month).groupby("mo")["demand_irrigable_m3"].mean()
    assert m.loc[[6, 7, 8]].mean() > 10 * m.loc[[12, 1, 2]].mean(), m
    assert d.groupby("code_bss")["week"].nunique().nunique() == 1, "wells with different weeks"
    # placebo: a well sharing its donor's SAFRAN cell gets exactly the donor's index
    cell = pd.read_parquet(DATASET_DIR / "wells.parquet").set_index("code_bss")["cell_id"]
    donors = d.groupby("code_bss")["placebo_donor"].first()
    same = [w for w, dn in donors.items() if cell[w] == cell[dn]]
    by = d.set_index(["code_bss", "week"])
    for w in same:
        assert np.allclose(by.loc[w, "demand_irrigable_placebo_m3"].to_numpy(),
                           by.loc[donors[w], "demand_irrigable_m3"].to_numpy())
    # placebo recomputed independently for three wells: own weather x donor's areas
    forcing = pd.read_parquet(DATASET_DIR / "forcing_weekly.parquet").set_index(["cell_id", "week"])
    a["crop_class"] = cls.to_numpy()
    irr = [c for c in classes.index if classes.loc[c, "irrigation_assumption"] in ("usually", "partly")]
    for w in list(donors.index[:3]):
        rows = by.loc[w]
        weeks = rows.index
        fc = forcing.loc[cell[w]].reindex(weeks)
        kc = kc_weekly(weeks, classes)[irr]
        need = kc.mul(fc["ETP"], axis=0).sub(fc["rain"], axis=0).clip(lower=0)
        ha = (a[(a["code_bss"] == donors[w]) & a["crop_class"].isin(irr)]
              .pivot_table(index="rpg_year", columns="crop_class", values="ha", aggfunc="sum")
              .reindex(columns=irr).fillna(0.0))
        ha = ha.reindex(sorted(a["rpg_year"].unique()), fill_value=0.0)
        a_t = ha.reindex(rows["rpg_year_used"].to_numpy()).set_axis(weeks)
        expect = (need * a_t * 10.0).sum(axis=1).to_numpy()
        assert np.allclose(rows["demand_irrigable_placebo_m3"].to_numpy(), expect), w
    print(f"  built: {d['code_bss'].nunique()} wells x {d['week'].nunique()} weeks; "
          f"summer/winter mean demand {m.loc[[6, 7, 8]].mean():.0f} / {m.loc[[12, 1, 2]].mean():.0f} m3/week")


def main():
    classes = load_classes()
    check_clipped_area(classes)
    check_code_mapping(classes)
    check_kc(classes)
    check_derangement()
    check_year_map()
    print("synthetic checks passed")
    check_foreign()
    check_built(classes)
    print("test_crop_demand: OK")


if __name__ == "__main__":
    main()
