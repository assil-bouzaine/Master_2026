"""Build the paper's study-area map and check its counts against the local files.

    PFE_DATASET=v4 python -m tests.test_fig_study_area
"""
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import geopandas as gpd
import pandas as pd
import pyogrio
from PIL import Image
from shapely.geometry import box

from paper.tools.fig_study_area import RIVER_IMPORTANCE_MAX, RIVER_LENGTH_MIN_M, draw_study_area
from src.analysis.bdlisa_profile import GPKG
from src.config import CRS_L93, PROCESSED, RAW
from src.kg.build_kg import L, unit_class


def polygon_counts(extent):
    """Use the lowest relative stack order in each polygon to identify its outcrop."""
    countries = gpd.read_file(f"zip://{RAW / 'naturalearth/ne_10m_admin_0_countries.zip'}",
                              bbox=(0, 40, 5, 44), columns=[])
    land = countries.to_crs(CRS_L93).geometry.make_valid().union_all().intersection(extent)
    polygons = pyogrio.read_dataframe(GPKG, layer="POLYG_ELEMENTAIRES", bbox=extent.bounds)
    visible = polygons.geometry.make_valid().intersection(land).area > 0

    stack = pyogrio.read_dataframe(GPKG, layer="TABLE_PILE_ENTITES_NIV3", read_geometry=False)
    winning_rows = stack.groupby("CodePoly")["OrdRelatif"].idxmin()
    top_units = stack.loc[winning_rows].set_index("CodePoly")["CodeEH"]
    entities = pyogrio.read_dataframe(GPKG, layer="TME", read_geometry=False)
    entities = entities.loc[entities["niveaueh"].eq(3)].set_index("codeeh")
    for col in ("natureeh", "themeeh", "milieueh"):
        entities[col] = entities[col].astype(str).str.strip()
    classes = Counter()
    for code in top_units.loc[polygons.loc[visible, "codepoly"]]:
        tme_row = entities.loc[code] if code in entities.index else None
        classes[str(unit_class(code, tme_row)).removeprefix(str(L))] += 1
    return dict(classes)


def waterway_counts(extent):
    raw = RAW / "bdtopo_hydro" / "2026-11-06"
    watercourses = gpd.read_parquet(raw / "cours_d_eau.parquet")
    segments = gpd.read_parquet(raw / "troncon_hydrographique.parquet")
    candidate = watercourses.loc[pd.to_numeric(watercourses["importance"]).le(RIVER_IMPORTANCE_MAX)]
    visible_length = candidate.geometry.intersection(extent).length
    named = candidate["toponyme"].fillna("").str.strip()
    priority = named.str.fullmatch(r"la Têt|le Tech|l'Agly|el Reart", case=False)
    drawn = ((visible_length >= RIVER_LENGTH_MIN_M) | (priority & (visible_length > 0)))
    rivers = (drawn & ~named.str.match(r"canal ", case=False)).sum()
    canals = segments.loc[segments["nature"].eq("Canal")].geometry.intersection(extent).length.gt(0).sum()
    return int(rivers), int(canals)


def test_study_area():
    nodes = pd.read_parquet(PROCESSED / "kg" / "export_v4_main" / "nodes.parquet")
    wells = nodes.loc[nodes["type"].eq("well")]
    extent = box(wells["x93"].min() - 3000, wells["y93"].min() - 3000,
                 wells["x93"].max() + 3000, wells["y93"].max() + 3000)
    west, south, east, north = extent.bounds
    in_frame = nodes.loc[nodes["x93"].between(west, east) & nodes["y93"].between(south, north)]
    gauges = int(in_frame["type"].eq("gauge").sum())
    core = int(wells["core"].eq(True).sum())
    assert (len(wells), core, gauges) == (65, 33, 5)
    rivers, canals = waterway_counts(extent)
    expected = {"wells": len(wells), "core_wells": core, "gauges": gauges,
                "facilities": int(in_frame["type"].eq("facility").sum()),
                "polygons_per_class": polygon_counts(extent), "rivers_kept": rivers,
                "canal_pieces": canals, "wells_without_class": int(wells["unit"].isna().sum())}

    with TemporaryDirectory() as directory:
        out = Path(directory)
        assert draw_study_area(out) == expected
        for name in ("study_area.pdf", "study_area.png"):
            path = out / name
            assert path.is_file() and path.stat().st_size > 0, name
        with Image.open(out / "study_area.png") as preview:
            assert all(abs(dpi - 200) < 0.1 for dpi in preview.info["dpi"])
            assert abs(preview.width * 25.4 / 200 - 190) < 0.2
            assert preview.height * 25.4 / 200 <= 170
    print("Source counts match", expected)


if __name__ == "__main__":
    start = perf_counter()
    test_study_area()
    print(f"test_fig_study_area: all checks passed ({perf_counter() - start:.2f}s)")
