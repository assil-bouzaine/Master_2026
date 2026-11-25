"""Check Phase 4 figures (analysis plan §6 and §10) without real bootstraps.

    PFE_DATASET=v4 python -m tests.test_phase4_figures

Synthetic rows follow arms_report's row dictionaries. Check that plotting
preserves effects, pending cases are visible in the log, and the cache avoids
another expensive compute. No real run is read or fitted by these tests.
"""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time
from unittest.mock import patch

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from PIL import Image

from src.analysis import arms_report as arms, phase4_figures as figures


def row(name="D vs C", family="RQ1", regime="", reconstruction=1, effect=-0.08, draw=None):
    """Use the keys of _contrast_row and _compare, with explicit toy values."""
    return {"name": name, "family": family, "a": "fixture_D", "b": "fixture_C", "regime": regime,
            "reconstruction": reconstruction, "draw": draw, "p_cluster": 0.01, "p_holm": 0.02,
            "p_holm_interim": None, "classification": arms.DETECTED,
            "aggregate_seeds_a": tuple(range(10)), "aggregate_seeds_b": tuple(range(10)),
            "band_seeds_a": tuple(range(10)), "band_seeds_b": tuple(range(10)), "coverage_requested": False,
            arms.EFFECT: effect, "interval": (effect - 0.03, effect + 0.04),
            "share of wells a better": 0.7, "support mismatch": 0,
            "band_a": (-0.02, 0.02), "band_b": (-0.01, 0.03), "union": ((-0.02, 0.03),),
            "starts_a": 10, "starts_b": 10, "scores_a": (0.4, 0.5, 0.3, 0.6),
            "scores_b": (0.3, 0.4, 0.2, 0.7), "coverage_a": "", "coverage_b": ""}


def fixture():
    families = [row(effect=-0.08), row("B vs A", effect=0.004, regime="_f25", reconstruction=2),
                row("soft vs none", "RQ2", effect=0.02),
                row("hard vs none", "RQ2", regime="_lwo", reconstruction=3, effect=0.07)]
    families[1]["classification"] = arms.NO_EFFECT
    families[2]["classification"] = arms.UNDECIDED
    families[3]["classification"] = arms.SMALL
    # A disjoint union must stay disjoint, rather than shading its convex hull.
    families[0]["union"] = ((-0.04, -0.02), (0.01, 0.03))
    controls = []
    for name in ("D vs E_degree", "D vs E_distance", "D vs F_random", "D vs F_complete"):
        for regime in ("", "_lwo"):
            effects = [-0.08, -0.05, -0.02, 0.01, 0.04] if name != "D vs F_complete" else [0.03]
            rows = [row(name, None, regime, effect=e, draw=d) for d, e in enumerate(effects)]
            controls.append({"name": name, "regime": regime, "reconstruction": 1,
                             "expected": len(rows), "rows": rows, **arms.aggregate_draws(rows)})
    return {"families": families, "controls": controls, "exploratory": [], "missing": [],
            "pending": {}, "soft": {}}, pd.DataFrame({
                "code_bss": ["toy/W1", "toy/W2", "toy/W3"], "C": [0.5, 1.0, 2.0],
                "D": [0.2, 1.1, 3.0], "group": figures.GROUPS[:3],
                "short_code": ["W1", "W2", "W3"], "log_ratio": np.log([0.4, 1.1, 1.5])})


def test_pngs():
    report, wells = fixture()
    with TemporaryDirectory() as tmp, patch.object(arms, "compute", side_effect=AssertionError("real compute")):
        paths = figures.render_figures(report, wells, Path(tmp))
        assert len(paths) == 3
        dimensions = {"contrasts": (1050, 1350), "controls": (1050, 720), "wells_dc": (1050, 975)}
        for name, path in paths.items():
            assert path.name == f"phase4_{name}_v4.png" and path.is_file()
            with Image.open(path) as png:
                assert png.format == "PNG"
                assert png.size == dimensions[name]
                assert all(abs(dpi - figures.DPI) < 0.1 for dpi in png.info["dpi"])
                png.verify()
    assert not plt.get_fignums()
    print("  1. Three valid 150 dpi PNGs: 1050×1350, 1050×720 and 1050×975 pixels.")


def test_effects():
    report, _ = fixture()
    table = figures.contrast_table(report["families"])
    np.testing.assert_array_equal(table[arms.EFFECT], [r[arms.EFFECT] for r in report["families"]])
    assert table["confirmatory"].tolist() == [True, False, True, False]
    assert table["classification"].tolist() == [r["classification"] for r in report["families"]]
    assert table.iloc[0]["union"] == ((-0.04, -0.02), (0.01, 0.03))
    assert table.iloc[0]["interval"] == report["families"][0]["interval"]
    print("  2. Plotted table preserves exact EFFECT values, intervals, union gaps and classifications.")


def test_pending():
    report, wells = fixture()
    pending = row("B vs A", effect=0.5) | {"pending": "pending: family incomplete, 1 of 2 tests"}
    missing = {key: value for key, value in row("B vs A").items()
               if key not in (arms.EFFECT, "interval", "union")}
    unavailable_interval = row("B vs A") | {"interval": [None, None]}
    report["families"].extend([pending, missing, unavailable_interval])
    report["controls"][0]["rows"][0]["pending"] = "missing draw"
    output = io.StringIO()
    with TemporaryDirectory() as tmp, redirect_stdout(output):
        table = figures.contrast_table(report["families"])
        assert len(table) == 4
        paths = figures.render_figures(report, wells, tmp)
        assert all(path.is_file() for path in paths.values())
        empty = {"families": [pending], "controls": []}
        figures.render_figures(empty, pd.DataFrame(columns=figures.WELL_COLUMNS), Path(tmp) / "empty")
    assert "Skipping pending row: B vs A" in output.getvalue()
    assert "missing runs or scores" in output.getvalue()
    assert "4 / 5 scored" in output.getvalue()
    print("  3. Pending, missing, partial-control and entirely pending fixtures render with printed notes.")


def test_cache():
    report, _ = fixture()
    config = {"smallest_effect": 0.05}
    with TemporaryDirectory() as tmp:
        cache = Path(tmp) / "rows.json"
        with patch.object(arms, "compute", return_value=report) as compute:
            figures.load_rows(config, object(), cache)
            compute.assert_called_once()
        with patch.object(arms, "compute", side_effect=AssertionError("cache missed")):
            cached = figures.load_rows(config, object(), cache)
        np.testing.assert_array_equal(figures.contrast_table(cached["families"])[arms.EFFECT],
                                      figures.contrast_table(report["families"])[arms.EFFECT])
        assert cached["controls"][0]["rows"][0]["interval"] == list(report["controls"][0]["rows"][0]["interval"])
        assert json.loads(cache.read_text())["schema"] == 1
        with patch.object(arms, "compute", return_value=report) as compute:
            figures.load_rows(config, object(), cache, recompute=True)
            compute.assert_called_once()
        with patch.object(arms, "compute", side_effect=AssertionError("stale cache recomputed")):
            try:
                figures.load_rows({"smallest_effect": 0.1}, object(), cache)
            except ValueError as error:
                assert "--recompute" in str(error)
            else:
                raise AssertionError("A different config silently reused the cache")
    print("  4. Cache reuses nested rows exactly; --recompute forces one call; changed config is rejected.")


def test_per_well():
    report, _ = fixture()
    metadata = pd.DataFrame({"code_bss": ["toy/W1", "toy/W2", "toy/noncore"],
                             "group": figures.GROUPS[:3]})
    base = metadata.assign(task="simulation", split="test_drought", variant="all", core=[True, True, False])
    c = base.assign(RMSE=[1.0, 2.0, 100.0])
    d = base.assign(RMSE=[0.5, 3.0, 200.0])
    runs = arms.SavedRuns()
    runs.wells = metadata
    with patch.object(runs, "metrics", side_effect=[d, c]) as metrics:
        table = figures.well_table(report, runs)
    assert metrics.call_args_list[0].args == ("fixture_D", "")
    assert metrics.call_args_list[1].args == ("fixture_C", "")
    assert table["code_bss"].tolist() == ["toy/W1", "toy/W2"]
    np.testing.assert_array_equal(table[["C", "D"]], [[1.0, 0.5], [2.0, 3.0]])
    np.testing.assert_allclose(table["log_ratio"], np.log([0.5, 1.5]))
    assert table["short_code"].tolist() == ["W1", "W2"]
    print("  5. Per-well table reads D/C R1 metrics, pairs core wells and retains metre-valued RMSE.")


def main():
    started = time.perf_counter()
    test_pngs()
    test_effects()
    test_pending()
    test_cache()
    test_per_well()
    print(f"test_phase4_figures: all checks passed ({time.perf_counter() - started:.1f}s)")


if __name__ == "__main__":
    main()
