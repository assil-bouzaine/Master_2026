"""Checks of the canal-intake river-basin split (src/dataset/canal_basins.py).

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m tests.test_canal_basins

1. Fixture: 4 synthetic intakes (one named "PRISE CANAL SUR LA TET", one with no keyword
   near a Tech reach, one far from every reach, and one whose name says Agly while lying
   near a Tet reach) -> expected basins, rules, snap distances and the disagreement flag,
   plus accent-folding and word-boundary checks.
2. Real data (dataset v4): exact week-by-week conservation against `canal_series()`,
   every selected intake has a valid basin (unknown allowed), disagreement consistency,
   arm-D canal-edge wells, and the written parquet and generated report.
"""
from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString, Point

from src.config import CRS_L93, CRS_WGS84, DATASET, DATASET_DIR, PROCESSED
from src.dataset.canal_basins import (
    BASINS,
    MAIN_BASINS,
    OUT_PARQUET,
    OUT_REPORT,
    OUTPUT_COLS,
    assign_basins,
    canal_edge_well_basins,
    canal_series_by_basin,
    classify_name,
    load_river_reaches,
    select_intakes,
)
from src.dataset.pumping import canal_series
from src.kg.rivers import INTAKE_SNAP_M


def _l93_to_wgs84(points_l93: list[Point]) -> tuple[np.ndarray, np.ndarray]:
    gs = gpd.GeoSeries(points_l93, crs=CRS_L93).to_crs(CRS_WGS84)
    return gs.x.to_numpy(), gs.y.to_numpy()


def test_fixture() -> None:
    """Four fake intakes testing name rule, spatial rule, >snap unknown, and disagreement."""
    # Synthetic Lambert-93 reaches in the Roussillon area: one Tet reach and one Tech reach.
    reaches = gpd.GeoDataFrame(
        {
            "cleabs": ["R_TET", "R_TECH"],
            "nature": ["Ecoulement naturel", "Ecoulement naturel"],
            "code_du_cours_d_eau_bdcarthage": ["Y04-0400", "Y02-0400"],
            "cpx_toponyme_de_cours_d_eau": ["la Têt", "le Tech"],
        },
        geometry=[
            LineString([(680_000, 6_175_000), (682_000, 6_175_000)]),
            LineString([(680_000, 6_160_000), (682_000, 6_160_000)]),
        ],
        crs=CRS_L93,
    )

    # 1: named Tet (50 m from Tet reach)
    # 2: no keyword, 80 m from Tech reach
    # 3: no keyword, 3,000 m from every reach (> INTAKE_SNAP_M)
    # 4: named Agly, 60 m from Tet reach -> name wins, disagreement flagged
    pts_l93 = [
        Point(681_000, 6_175_050),
        Point(681_000, 6_160_080),
        Point(681_000, 6_168_000),
        Point(681_500, 6_175_060),
    ]
    lons, lats = _l93_to_wgs84(pts_l93)
    fake_intakes = pd.DataFrame(
        {
            "code_ouvrage": ["F1", "F2", "F3", "F4"],
            "nom_ouvrage": [
                "PRISE CANAL SUR LA TET",
                "PRISE SANS MOT CLE",
                "PRISE LOINTAINE",
                "PRISE DANS L'AGLY",
            ],
            "longitude": lons,
            "latitude": lats,
            "cell_id": ["C1", "C2", "C3", "C4"],
        }
    )

    out = assign_basins(fake_intakes, reaches, max_dist_m=INTAKE_SNAP_M).set_index("code_ouvrage")
    assert list(out.reset_index().columns) == OUTPUT_COLS

    # F1: name = Tet, spatial = Tet, agree
    assert out.loc["F1", "basin"] == "Tet"
    assert out.loc["F1", "rule_used"] == "name"
    assert out.loc["F1", "name_basin"] == "Tet"
    assert out.loc["F1", "spatial_basin"] == "Tet"
    assert not bool(out.loc["F1", "disagreement"])
    assert np.isclose(out.loc["F1", "snap_distance_m"], 50.0, atol=0.5)

    # F2: no keyword, spatial = Tech
    assert out.loc["F2", "basin"] == "Tech"
    assert out.loc["F2", "rule_used"] == "spatial"
    assert out.loc["F2", "name_basin"] is None
    assert out.loc["F2", "spatial_basin"] == "Tech"
    assert not bool(out.loc["F2", "disagreement"])
    assert np.isclose(out.loc["F2", "snap_distance_m"], 80.0, atol=0.5)

    # F3: far from every reach -> unknown
    assert out.loc["F3", "basin"] == "unknown"
    assert out.loc["F3", "rule_used"] == "none"
    assert out.loc["F3", "name_basin"] is None
    assert out.loc["F3", "spatial_basin"] == "unknown"
    assert not bool(out.loc["F3", "disagreement"])
    assert np.isnan(out.loc["F3", "snap_distance_m"])

    # F4: name = Agly, spatial = Tet -> Agly wins, disagreement flagged
    assert out.loc["F4", "basin"] == "Agly"
    assert out.loc["F4", "rule_used"] == "name"
    assert out.loc["F4", "name_basin"] == "Agly"
    assert out.loc["F4", "spatial_basin"] == "Tet"
    assert bool(out.loc["F4", "disagreement"])
    assert np.isclose(out.loc["F4", "snap_distance_m"], 60.0, atol=0.5)

    # Accent folding and word-boundary checks
    assert classify_name("PRISE SUR LA TÊT") == "Tet"
    assert classify_name("CANAL DU RÉART") == "Reart"
    assert classify_name("STATION TECHNIQUE") is None
    assert classify_name("PRISE DE LA TETIERE") is None

    print("  1. fixture (4 fake intakes + accent/word-boundary checks): basins, rules, distances and disagreement flag match")


def test_real_data() -> None:
    """Real dataset v4: conservation against canal_series(), validity, parquet and arm-D wells."""
    pw = pd.read_parquet(DATASET_DIR / "pumping_weekly.parquet")
    pts = pd.read_parquet(DATASET_DIR / "pumping_points.parquet")
    intakes, weekly_rows = select_intakes(pw=pw, pts=pts)
    reaches = load_river_reaches()
    assigned = assign_basins(intakes, reaches, max_dist_m=INTAKE_SNAP_M)

    # Every selected intake has a valid basin and rule_used
    assert len(assigned) == len(intakes) and len(assigned) > 0
    assert assigned["basin"].notna().all()
    assert set(assigned["basin"]).issubset(set(BASINS))
    assert set(assigned["rule_used"]).issubset({"name", "spatial", "none"})
    expected_disagree = (
        assigned["name_basin"].notna()
        & (assigned["spatial_basin"] != "unknown")
        & (assigned["name_basin"] != assigned["spatial_basin"])
    )
    assert (assigned["disagreement"] == expected_disagree).all()

    # Exact week-by-week conservation against canal_series()
    weekly_basin = canal_series_by_basin(assigned, weekly_rows=weekly_rows)
    expected = canal_series(pw, pts)
    assert weekly_basin.index.equals(expected.index)
    assert list(weekly_basin.columns) == list(BASINS)
    assert (weekly_basin.to_numpy() >= 0.0).all()
    max_diff = float((weekly_basin.sum(axis=1) - expected).abs().max())
    np.testing.assert_allclose(weekly_basin.sum(axis=1).to_numpy(), expected.to_numpy(), rtol=1e-12, atol=1e-6)

    # Arm-D canal-edge wells
    edges_d = pd.read_parquet(PROCESSED / "kg" / f"export_{DATASET}_main" / "edges_D.parquet")
    expected_wells = sorted(edges_d.loc[edges_d["relation"] == "canal", "dst"].unique())
    wb = canal_edge_well_basins(edges_d=edges_d, reaches=reaches)
    assert list(wb["code_bss"]) == expected_wells
    assert set(wb["basin"]).issubset(set(MAIN_BASINS))

    # Written parquet and generated report exist and match
    assert OUT_PARQUET.is_file(), f"missing {OUT_PARQUET}; run python -m src.dataset.canal_basins"
    disk = pd.read_parquet(OUT_PARQUET)
    assert list(disk.columns) == OUTPUT_COLS
    pd.testing.assert_frame_equal(disk, assigned)

    assert OUT_REPORT.is_file(), f"missing {OUT_REPORT}; run python -m src.dataset.canal_basins"
    first_line = OUT_REPORT.read_text(encoding="utf-8").splitlines()[0]
    assert "generated" in first_line.lower()

    print(
        f"  2. real data ({DATASET}): {len(assigned)} intakes across {len(weekly_basin)} weeks, "
        f"conservation max abs diff {max_diff:.2e} m3/week, "
        f"{len(wb)} arm-D canal wells ({wb['basin'].value_counts().to_dict()}), "
        f"parquet ({len(disk)} rows, {len(disk.columns)} cols) and report verified"
    )


if __name__ == "__main__":
    test_fixture()
    test_real_data()
    print("test_canal_basins: all checks passed")
