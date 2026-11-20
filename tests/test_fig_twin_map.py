"""Check the paper's twin map against the saved world JSON files.

    PFE_DATASET=v4 python -m tests.test_fig_twin_map
"""
from collections import defaultdict
import json
from math import exp
from pathlib import Path
import re
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter

import numpy as np
import pandas as pd

from paper.tools.fig_twin_map import compare_protocols, draw_twin_map
from src.config import ROOT

RUN = ROOT / "results" / "v4" / "twin_map"
SETTINGS = ("free", "pooled_l0.1_fixed3000")
EPS = (0, 0.1, 0.25, 0.5)
U = (0, 0.3, 0.6)


def read_worlds():
    """Read each world once and check that every cell is complete."""
    grid = defaultdict(list)
    for path in sorted(RUN.glob("*/world_*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        dials = record["dials"]
        grid[dials["eps"], dials["u"]].append(record)
    assert set(grid) == {(eps, u) for eps in EPS for u in U}
    for records in grid.values():
        assert len(records) == len({record["world"] for record in records}) == 20
    return grid


def values_from_world_json(grid=None):
    """Compute the matrices independently of the report loader."""
    if grid is None:
        grid = read_worlds()
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


def macros_from_world_json(grid, matrices):
    """Compute all the paper values from world records, without the report loader."""
    macros = {}
    for setting, suffix in zip(SETTINGS, ("Free", "Pooled")):
        cell_fits = [[record["fits"][setting] for record in records] for records in grid.values()]
        fits = [fit for cell in cell_fits for fit in cell]
        values = matrices[setting]
        dc = values["log_rmse_D_over_C"].ravel()
        tc = values["log_rmse_T_over_C"].ravel()
        quantile = min(np.quantile([fit["log_rmse_D_over_C"] for fit in cell], 0.975)
                       for cell in cell_fits)
        wins = [sum(fit["recovery_pumping_D"] < fit["recovery_pumping_C"] for fit in cell)
                for cell in cell_fits]
        numbers = {
            "DCMin": f"{min(dc):+.3f}", "DCMax": f"{max(dc):+.3f}", "DCQHighMin": f"{quantile:+.3f}",
            "TCMin": f"{min(tc):+.3f}", "TCMax": f"{max(tc):+.3f}",
            "TCGainMin": f"{100 * (1 - exp(max(tc))):.1f}", "TCGainMax": f"{100 * (1 - exp(min(tc))):.1f}",
            "RightMin": f"{100 * min(wins) / len(cell_fits[0]):.0f}",
            "RightMax": f"{100 * max(wins) / len(cell_fits[0]):.0f}",
            "RightMean": f"{100 * sum(wins) / len(fits):.0f}",
            "Pays": str(values["pays_count"]),
            "Worlds": str(len(fits)),
        }
        for arm in ("D", "C"):
            wrong = sum(fit[f"recovery_pumping_{arm}"] > 0.5
                        and abs(fit[f"nse_drought_{arm}"] - fit["nse_drought_T"]) <= 0.1 for fit in fits)
            numbers[f"Wrong{arm}"] = str(wrong)
        macros.update({f"twin{key}{suffix}": value for key, value in numbers.items()})

    better, differences = 0, []
    for records in grid.values():
        early, converged = ({record["world"]: record["fits"][setting]
                             for record in records if setting in record["fits"]} for setting in SETTINGS)
        paired = sorted(early.keys() & converged.keys())
        free_recovery = median(early[world]["recovery_pumping_D"] for world in paired)
        pooled_recovery = median(converged[world]["recovery_pumping_D"] for world in paired)
        better += free_recovery < pooled_recovery
        differences.append(median(early[world]["nse_drought_D"] for world in paired)
                           - median(converged[world]["nse_drought_D"] for world in paired))
    macros.update(twinFreeBetterCells=str(better), twinCellsCompared=str(len(differences)),
                  twinNSEDiff=f"{median(differences):+.3f}", twinCells=str(len(grid)),
                  twinWorldsPerCell=str(len(next(iter(grid.values())))))
    return macros


def read_macros(path):
    names = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("%"):
            continue
        match = re.fullmatch(r"\\newcommand\{\\(twin[A-Za-z]+)\}\{([+-]?\d+(?:\.\d+)?)\} % (.+)", line)
        assert match, line
        name, value, source = match.groups()
        assert name not in names and "/twin_map/" in source, line
        names[name] = value
    return names


def test_protocol_pairing():
    """Single-protocol worlds would change both results if they entered the comparison."""
    free, pooled = SETTINGS
    rows = pd.DataFrame([
        (0, 0, 0, free, 0.5, 0.8),
        (0, 0, 0, pooled, 0.4, 0.6),
        (0, 0, 1, free, 0.1, 0.0),
        (0, 0, 2, pooled, 0.9, 1.0),
    ], columns=["dial_eps", "dial_u", "world", "setting", "recovery_pumping_D", "nse_drought_D"])
    free_wins, compared, difference = compare_protocols(rows)
    assert (free_wins, compared) == (0, 1)
    np.testing.assert_allclose(difference, 0.2)


def test_twin_map():
    grid = read_worlds()
    expected = values_from_world_json(grid)
    expected_macros = macros_from_world_json(grid, expected)
    with TemporaryDirectory() as directory:
        out = Path(directory)
        first = draw_twin_map(out / "first", tables_out=out / "first")
        draw_twin_map(out / "second", tables_out=out / "second")
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
            assert original.read_bytes() == (ROOT / "paper" / "figures" / name).read_bytes(), name
        table = out / "first" / "twin_numbers.tex"
        assert table.read_bytes() == (out / "second" / "twin_numbers.tex").read_bytes()
        macros = read_macros(table)
        assert macros == expected_macros
        for name in ("kg_numbers.tex", "data_numbers.tex"):
            text = (ROOT / "paper" / "tables" / name).read_text(encoding="utf-8")
            other_macros = re.findall(r"\\newcommand\s*\{\\([A-Za-z]+)\}", text)
            assert other_macros and macros.keys().isdisjoint(other_macros), name
    print("240 worlds per protocol, with 20 per cell. Both outputs rebuild byte-identically.")
    print(f"All {len(macros)} macro values match the world JSON files. The macro names are unique.")


if __name__ == "__main__":
    start = perf_counter()
    test_protocol_pairing()
    test_twin_map()
    print(f"test_fig_twin_map: all checks passed ({perf_counter() - start:.2f}s)")
