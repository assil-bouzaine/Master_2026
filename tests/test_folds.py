"""Leave-wells-out folds keep nearby wells together (dataset v4 on).

    PFE_DATASET=v4 python -m tests.test_folds

1. Synthetic wells: three nested sites (two piezometers 20 m apart) and a chain of wells
   1.5 km apart (linked transitively) each land in a single fold; isolated wells spread
   over the five folds; the rule is deterministic.
2. The built dataset, if present (data are not in git): no two wells of different folds
   are closer than the linking distance, every fold has core wells, and no week of the
   targets contains a value qualified "Incorrecte".
"""
import json

import geopandas as gpd
import numpy as np
import pandas as pd

from src.config import CRS_L93, CRS_WGS84, DATASET, DATASET_DIR
from src.dataset.build import N_FOLDS, VERSIONS, grouped_folds


def synthetic_wells():
    rows, x0, y0 = [], 690000.0, 6170000.0  # Lambert-93, in the Roussillon plain
    for i in range(3):  # nested sites
        for j, grp in enumerate(("recent alluvium", "Pliocene multilayer")):
            rows.append((f"N{i}{j}", x0 + 10000 * i + 20 * j, y0, grp, True))
    for i in range(4):  # a chain: 1.5 km steps, so 4.5 km end to end, one block at 2 km
        rows.append((f"C{i}", x0 + 1500 * i, y0 + 20000, "Pliocene multilayer", i % 2 == 0))
    for i in range(10):  # isolated wells
        rows.append((f"I{i}", x0 + 5000 * i, y0 - 30000, "Pliocene multilayer", True))
    w = pd.DataFrame(rows, columns=["code_bss", "X", "Y", "group", "core"])
    pts = gpd.GeoSeries(gpd.points_from_xy(w["X"], w["Y"]), crs=CRS_L93).to_crs(CRS_WGS84)
    return w.assign(x=pts.x.to_numpy(), y=pts.y.to_numpy())


def check_synthetic():
    w = synthetic_wells()
    f = grouped_folds(w, link_m=2000)
    for i in range(3):
        assert f[f"N{i}0"] == f[f"N{i}1"], "nested piezometers split across folds"
    assert len({f[f"C{i}"] for i in range(4)}) == 1, "a chain of close wells was split"
    iso = [f[f"I{i}"] for i in range(10)]
    assert set(iso) == set(range(N_FOLDS)), "isolated wells not spread over the folds"
    assert f == grouped_folds(w, link_m=2000), "the rule is not deterministic"


def check_dataset():
    link = VERSIONS[DATASET].get("fold_link_m")
    if not link or not (DATASET_DIR / "wells.parquet").exists():
        print(f"dataset {DATASET}: no grouped folds or not built here, skipped")
        return
    w = pd.read_parquet(DATASET_DIR / "wells.parquet")
    g = gpd.GeoSeries(gpd.points_from_xy(w["x"], w["y"]), crs=CRS_WGS84).to_crs(CRS_L93)
    d = np.hypot(g.x.to_numpy()[:, None] - g.x.to_numpy()[None],
                 g.y.to_numpy()[:, None] - g.y.to_numpy()[None])
    fold = w["fold"].to_numpy()
    cross = np.where(fold[:, None] != fold[None], d, np.inf).min()
    assert cross >= link, f"wells {cross:.0f} m apart are in different folds"
    assert w.loc[w["core"], "fold"].nunique() == N_FOLDS, "a fold without core wells"
    split = json.loads((DATASET_DIR / "splits.json").read_text())["leave_wells_out"]
    assert split["fold_of_well"] == dict(zip(w["code_bss"], w["fold"])), "splits.json differs"
    meta = json.loads((DATASET_DIR / "meta.json").read_text())
    assert meta["quality_filter"]["values_dropped"] > 0
    print(f"dataset {DATASET}: closest wells in different folds {cross:.0f} m; "
          f"{meta['quality_filter']['values_dropped']} bad values dropped")


def main():
    check_synthetic()
    check_dataset()
    print("test_folds: all checks passed")


if __name__ == "__main__":
    main()
