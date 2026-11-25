"""Checks of BRGM BSS evidence parsing, location matching and report counts (src/kg/bss_evidence.py).

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m tests.test_bss_evidence

1. Parsing fixture: covers all ``liste_bdlisa`` shapes found in ``bss_eau_point.parquet`` —
   one NV3 entity, "NV3 absent, nom de l'entité NV2 : ... - 671AA00", several entities
   (NV3+NV3 and mixed NV2+NV3), and empty/missing values.
2. Location matching fixture: 3 BNPE points and 4 BSS water points at known Lambert-93
   distances -> checks the expected nearest BSS code, distance, tie count and match flags
   at every D in {50, 100, 250, 500} m.
3. Real data: runs on dataset v4 + BSS snapshot; checks that every BNPE groundwater point
   appears exactly once in ``data/interim/bss_evidence.parquet`` and that all precision,
   confusion, use-split and level-split counts add up consistently.
"""
import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point

from src.config import CRS_L93, DATASET_DIR
from src.kg import bss_evidence as be


def test_parse_bdlisa():
    # One NV3 entity
    r1 = be.parse_bdlisa("Alluvions récentes de la Têt - 718BP02")
    assert r1 == {"entities": ["718BP02"], "n_entities": 1, "level": "NV3", "single_entity": "718BP02"}, r1

    # One NV2 entity ("NV3 absent")
    r2 = be.parse_bdlisa(
        "NV3 absent, nom de l'entité NV2 : Sables et argiles pliocènes du Roussillon - 671AA00"
    )
    assert r2 == {"entities": ["671AA00"], "n_entities": 1, "level": "NV2", "single_entity": "671AA00"}, r2

    # Several entities (both NV3) -> no single candidate, both kept
    r3 = be.parse_bdlisa(
        "Calcaires et dolomies - 402AS07;Marnes gypsifères - 402AS08"
    )
    assert r3 == {"entities": ["402AS07", "402AS08"], "n_entities": 2, "level": "NV3",
                  "single_entity": None}, r3

    # Several entities (mixed NV2 and NV3) -> no single candidate, both kept
    r4 = be.parse_bdlisa(
        "NV3 absent, nom de l'entité NV2 : Sables et argiles pliocènes du Roussillon - 671AA00;"
        "Alluvions anciennes de l'Agly - 671AB01"
    )
    assert r4 == {"entities": ["671AA00", "671AB01"], "n_entities": 2, "level": "mixed",
                  "single_entity": None}, r4

    # Empty, whitespace, None, NaN
    for empty in ("", "   ", None, float("nan")):
        r = be.parse_bdlisa(empty)
        assert r == {"entities": [], "n_entities": 0, "level": None, "single_entity": None}, (empty, r)

    print("  1. parse_bdlisa: NV3 single, NV2 ('NV3 absent') single, multi-entity (NV3 & mixed) and empty pass")


def test_location_matching_fixture():
    # 3 BNPE points and 4 BSS water points in metric Lambert-93 coordinates
    #   BNPE P1 at (0, 0)       -> nearest BSS B1 at (30, 0), dist = 30 m  (matches 50, 100, 250, 500)
    #   BNPE P2 at (1000, 0)    -> nearest BSS B2 at (1180, 0), dist = 180 m (matches 250, 500 only)
    #   BNPE P3 at (5000, 0)    -> equidistant to B3 at (5400, 0) and B4 at (4600, 0), dist = 400 m
    #                              (matches 500 only; tie count = 2, deterministic code_bss order -> B3)
    bnpe = gpd.GeoDataFrame(
        {"code_ouvrage": ["P1", "P2", "P3"]},
        geometry=[Point(0, 0), Point(1000, 0), Point(5000, 0)],
        crs=CRS_L93,
    )
    bss = gpd.GeoDataFrame(
        {
            "code_bss": ["B1", "B2", "B4", "B3"],
            "bdlisa_entities": ["718BP02", "671AA00", "671AA00;671AB01", "671AB01"],
            "bdlisa_n_entities": [1, 1, 2, 1],
            "bdlisa_level": ["NV3", "NV2", "mixed", "NV3"],
            "bdlisa_single": ["718BP02", "671AA00", None, "671AB01"],
            "prof_invest_m": [20.0, 95.0, np.nan, 45.0],
            "mode_gisement": ["Libre", "Captif", "Inconnu", "Libre"],
            "coordonneescommune": ["N", "N", "N", "N"],
        },
        geometry=[Point(30, 0), Point(1180, 0), Point(4600, 0), Point(5400, 0)],
        crs=CRS_L93,
    )
    m = be.match_nearest_bss(bnpe, bss, radii=be.RADII_M).set_index("code_ouvrage")
    assert list(m.index) == ["P1", "P2", "P3"]
    assert m.loc["P1", "nearest_bss_code"] == "B1"
    assert np.isclose(m.loc["P1", "nearest_bss_dist_m"], 30.0)
    assert m.loc["P1", "nearest_bss_n_ties"] == 1
    assert [bool(m.loc["P1", f"nearest_match_{d}m"]) for d in be.RADII_M] == [True, True, True, True]

    assert m.loc["P2", "nearest_bss_code"] == "B2"
    assert np.isclose(m.loc["P2", "nearest_bss_dist_m"], 180.0)
    assert m.loc["P2", "nearest_bss_n_ties"] == 1
    assert [bool(m.loc["P2", f"nearest_match_{d}m"]) for d in be.RADII_M] == [False, False, True, True]

    assert m.loc["P3", "nearest_bss_code"] == "B3"
    assert np.isclose(m.loc["P3", "nearest_bss_dist_m"], 400.0)
    assert m.loc["P3", "nearest_bss_n_ties"] == 2
    assert [bool(m.loc["P3", f"nearest_match_{d}m"]) for d in be.RADII_M] == [False, False, False, True]

    print("  2. location matching fixture: 3 BNPE x 4 BSS points give expected nearest code, distance, ties and per-D flags")


def test_real_data():
    assert be.OUT_PARQUET.is_file(), f"missing {be.OUT_PARQUET}; run python -m src.kg.bss_evidence first"
    assert be.OUT_MD.is_file(), f"missing {be.OUT_MD}; run python -m src.kg.bss_evidence first"

    pts = pd.read_parquet(DATASET_DIR / "pumping_points.parquet")
    gw_codes = set(pts.loc[pts["source"] == "groundwater", "code_ouvrage"])

    df = pd.read_parquet(be.OUT_PARQUET)
    assert df["code_ouvrage"].is_unique, "duplicate code_ouvrage in bss_evidence.parquet"
    assert set(df["code_ouvrage"]) == gw_codes, "bss_evidence.parquet must match dataset groundwater points 1-to-1"
    assert len(df) == len(gw_codes)

    # Check join totals add up
    joins = be.summarize_joins(df)
    for scope in ("all", "plain"):
        tbl = joins[scope]
        body = tbl[tbl["usage"] != "Total"]
        tot = tbl[tbl["usage"] == "Total"].iloc[0]
        for col in ("n_points", "with_bss_code", "in_bss_eau", "single_bdlisa", "in_bss_total"):
            assert int(body[col].sum()) == int(tot[col]), (scope, col)

    # Check precision table counts add up across confusion matrix, use split and level split
    ev = be.evaluate_bss_record(df, radii=be.RADII_M)
    n_eval = ev["n_evaluated"]
    assert ev["n_recorded_boreholes"] == n_eval + ev["n_multi_entity"] + ev["n_absent_or_empty"]
    assert int(ev["overall"].iloc[0]["n"]) == n_eval
    assert int(ev["by_use"]["n"].sum()) == n_eval
    assert int(ev["by_use"]["correct_group"].sum()) == int(ev["overall"].iloc[0]["correct_group"])
    assert int(ev["by_use"]["correct_exact"].sum()) == int(ev["overall"].iloc[0]["correct_exact"])
    assert int(ev["by_level"]["n"].sum()) == n_eval
    assert int(ev["by_level"]["correct_group"].sum()) == int(ev["overall"].iloc[0]["correct_group"])
    assert int(ev["by_level"]["correct_exact"].sum()) == int(ev["overall"].iloc[0]["correct_exact"])

    conf = ev["confusion"]
    inner = conf.drop(index="Total", columns="Total")
    assert int(inner.to_numpy().sum()) == n_eval
    assert int(conf.loc["Total", "Total"]) == n_eval
    diag = sum(int(inner.loc[g, g]) for g in inner.index if g in inner.columns)
    assert diag == int(ev["overall"].iloc[0]["correct_group"])

    # Monotonicity across D for location matching
    known_acc, nocode_tbl = be.summarize_location_matching(df, radii=be.RADII_M)
    all_tot = nocode_tbl[(nocode_tbl["scope"] == "all") & (nocode_tbl["usage"] == "Total")].sort_values("D_m")
    assert list(all_tot["n_matched"]) == sorted(all_tot["n_matched"])
    assert list(all_tot["n_single_bdlisa"]) == sorted(all_tot["n_single_bdlisa"])

    print(f"  3. real data: {len(df)} BNPE groundwater points (1-to-1, unique); "
          f"precision tables add up ({n_eval}/{ev['n_recorded_boreholes']} recorded boreholes evaluated, "
          f"group={ev['overall'].iloc[0]['precision_group']:.3f}, exact={ev['overall'].iloc[0]['precision_exact']:.3f})")


if __name__ == "__main__":
    test_parse_bdlisa()
    test_location_matching_fixture()
    test_real_data()
    print("test_bss_evidence: all checks passed")
