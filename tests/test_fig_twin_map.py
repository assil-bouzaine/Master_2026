"""Check the paper's twin map against the saved world JSON files.

    PFE_DATASET=v4 python -m tests.test_fig_twin_map
"""
from collections import defaultdict
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import numpy as np

from paper.tools.fig_twin_map import draw_twin_map
from src.config import ROOT

RUN = ROOT / "results" / "v4" / "twin_map"
SETTINGS = ("free", "pooled_l0.1_fixed3000")
EPS = (0, 0.1, 0.25, 0.5)
U = (0, 0.3, 0.6)


def values_from_world_json():
    """Read each world once and compute the matrices independently of the report loader."""
    grid = defaultdict(list)
    for path in sorted(RUN.glob("*/world_*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        dials = record["dials"]
        grid[dials["eps"], dials["u"]].append(record)
    assert set(grid) == {(eps, u) for eps in EPS for u in U}
    for records in grid.values():
        assert len(records) == len({record["world"] for record in records}) == 20

    expected = {}
    for setting in SETTINGS:
        med_d = np.empty((len(EPS), len(U)))
        med_t = np.empty_like(med_d)
        recovery_share = np.empty_like(med_d)
        pays = 0
        for i, eps in enumerate(EPS):
            for j, u in enumerate(U):
                fits = [record["fits"][setting] for record in grid[eps, u]]
                graph = [fit["log_rmse_D_over_C"] for fit in fits]
                med_d[i, j] = np.median(graph)
                med_t[i, j] = np.median([fit["log_rmse_T_over_C"] for fit in fits])
                recovery_share[i, j] = sum(fit["recovery_pumping_D"] < fit["recovery_pumping_C"]
                                           for fit in fits) / len(fits)
                pays += int(med_d[i, j] <= -0.05 and np.quantile(graph, 0.975) < 0)
        expected[setting] = {"log_rmse_D_over_C": med_d, "log_rmse_T_over_C": med_t,
                             "pumping_recovery_share": recovery_share, "pays_count": pays}
    return expected


def test_twin_map():
    expected = values_from_world_json()
    with TemporaryDirectory() as directory:
        out = Path(directory)
        first = draw_twin_map(out / "first")
        draw_twin_map(out / "second")
        assert set(first) == set(expected)
        for setting, values in expected.items():
            assert set(first[setting]) == set(values)
            for metric, result in values.items():
                np.testing.assert_array_equal(first[setting][metric], result, err_msg=f"{setting}, {metric}")
            print(f"{setting}: all matrices match the world JSON files, {values['pays_count']} cells pay")
        for name in ("twin_map.pdf", "twin_map.png"):
            original = out / "first" / name
            rebuilt = out / "second" / name
            assert original.is_file() and rebuilt.is_file()
            assert original.stat().st_size > 0
            assert original.read_bytes() == rebuilt.read_bytes(), name
    print("240 worlds per protocol, with 20 per cell. Both outputs rebuild byte-identically.")


if __name__ == "__main__":
    start = perf_counter()
    test_twin_map()
    print(f"test_fig_twin_map: all checks passed ({perf_counter() - start:.2f}s)")
