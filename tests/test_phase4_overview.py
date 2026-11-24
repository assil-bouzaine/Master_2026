"""Check the Phase 4 score overview without running any fits.

    PFE_DATASET=v4 python -m tests.test_phase4_overview
"""
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from src.analysis import ladder_report, phase4_overview as overview
from src.config import RESULTS_DIR


def test_dry_run():
    plan = overview.phase4_plan()
    runs = overview.report_runs(plan)
    assert plan.summary()["fits"] == 378
    assert plan.summary()["assemblies"] == 51
    folders = {run.name for run in runs}
    assert len(runs) == len(folders) == 174
    assert folders == {task.run for task in plan.tasks if task.kind == "fit"}
    assert not any("_fold" in name for name in folders)
    assert Counter(run.block for run in runs) == {
        "B1": 30, "B1c": 10, "B2": 30, "B2conv": 6, "B3": 32, "B4": 30,
        "B5": 20, "B6": 8, "B7": 4, "B8": 4,
    }
    assert {run.name for run in runs if run.suffix == "_lwo"} == {
        task.run for task in plan.tasks if task.kind == "assembly"
    }
    by_name = {run.name: run for run in runs}
    assert by_name["p4_B1_A_r3_f25"] == overview.Run("p4_B1_A_r3_f25", "B1", "A", 3, "_f25")
    assert by_name["p4_B3_Edist2_r1_lwo"] == overview.Run(
        "p4_B3_Edist2_r1_lwo", "B3", "E_distance:2", 1, "_lwo"
    )
    print(f"  dry run: 378 fits, 51 assemblies, {len(runs)} result folders across 10 blocks")


def test_reference_scores():
    checked = 0
    for name in overview.REFERENCES:
        path = RESULTS_DIR / name / "metrics_per_well.csv"
        if not path.is_file():
            continue
        metrics = pd.read_csv(path)
        scores = overview.read_scores(path)
        expected = ladder_report.medians(metrics)
        np.testing.assert_equal({key: scores[key] for key in expected}, expected)
        kge = ladder_report.per_well(metrics, "test_drought", "KGE")
        np.testing.assert_equal(scores["KGE drought"], kge.median())
        assert scores["core wells"] == kge.index.nunique()
        checked += 1
    print(f"  references: {checked} available CSVs agree with direct ladder medians")


def test_render():
    runs = overview.report_runs(overview.phase4_plan())
    with TemporaryDirectory() as temp:
        results = Path(temp) / "results"
        for name, nse in (("p4_B1_A_r1", 0.2), ("p4_B1_B_r1", 0.4), ("p4_B1_A_r1_lwo", 0.9)):
            folder = results / name
            folder.mkdir(parents=True)
            pd.DataFrame([{
                "code_bss": "well-1", "task": "simulation", "split": "test_drought",
                "variant": "all", "core": True, "NSE": nse, "KGE": 0.6,
                "RMSE": 0.3, "skill": 0.1,
            }]).to_csv(folder / "metrics_per_well.csv", index=False)

        out = Path(temp) / "overview.md"
        out.write_text(overview.render(runs, results=results), encoding="utf-8")
        report = out.read_text(encoding="utf-8")

    assert report.count("| pending |") == len(runs) - 3 + len(overview.REFERENCES) + 9
    start = report.index("\n## B1\n")
    stop = report.index("\n## B1c\n")
    table_rows = [line for line in report[start:stop].splitlines() if line.startswith("| `p4_")]
    names = [line.split("`")[1] for line in table_rows]
    assert names == [run.name for suffix in (False, True) for run in runs
                     if run.block == "B1" and bool(run.suffix) == suffix]
    assert "| `p4_B1_A_r1_lwo` | A | 1 | _lwo | 1 | — | 0.900 | 0.100 | 0.300 | 0.600 | scored |" in report
    assert "| `p4_B1_A_r1_f25` | A | 1 | _f25 | — | — | — | — | — | — | pending |" in report
    best_section = report.split("## Best R1 drought NSE per block")[1]
    assert "| B1 | `p4_B1_B_r1` | 0.400 |" in best_section
    assert "| B1c | pending | — |" in best_section
    print("  render: temporary report has pending rows, dry-run order and the best R1 only")


if __name__ == "__main__":
    test_dry_run()
    test_reference_scores()
    test_render()
    print("test_phase4_overview: all checks passed")
