"""Check the black-box report with saved baseline scores and temporary outputs.

    PFE_DATASET=v4 python -m tests.test_blackbox_report
"""
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from src.analysis import blackbox_report as report, ladder_report as ladder
from src.models.evaluate import DS, RESULTS

A, B = "stgnn_tuned", "taccari_tuned"
RUNS = {run: report.RUNS[run] for run in (A, B)}
CONTRASTS = ((A, B, "pre-specified", "Test contrast with saved baselines"),)


def _row(markdown, *first_cells):
    prefix = "| " + " | ".join(f"`{cell}`" for cell in first_cells) + " |"
    line = next(line for line in markdown.splitlines() if line.startswith(prefix))
    return line.strip("|").strip().split(" | ")


def test_saved_runs():
    wells = pd.read_parquet(DS / "wells.parquet")
    ma, mb = [pd.read_csv(RESULTS / run / "metrics_per_well.csv") for run in RUNS]
    expected = ladder.contrast(ma, mb, wells)
    with TemporaryDirectory() as tmp:
        output = Path(tmp) / "blackbox.md"
        report.main(output, runs=RUNS, contrasts=CONTRASTS)
        markdown = output.read_text(encoding="utf-8")

    row = _row(markdown, A, B)
    assert row[4] == "scored"
    assert row[5:] == [ladder.fmt(value, nd=4) for value in expected.values()], row
    for run, table in zip(RUNS, (ma, mb)):
        medians = ladder.medians(table)
        assert _row(markdown, run)[2:] == ["scored", *(ladder.fmt(medians[key]) for key in (
            "NSE val", "NSE drought", "skill drought", "RMSE drought"))]
    assert f"Exact support for `{A}` vs `{B}` passed" in markdown
    print(f"  1. Saved baselines match the ladder helpers: {expected}")


def test_missing_runs():
    with TemporaryDirectory() as tmp:
        results = Path(tmp)
        (results / A).mkdir()  # A has a folder but no metrics. B has no folder.
        output = results / "blackbox.md"
        report.main(output, runs=RUNS, contrasts=CONTRASTS, results=results)
        markdown = output.read_text(encoding="utf-8")

    for run in RUNS:
        assert _row(markdown, run)[2:] == ["pending", "—", "—", "—", "—"]
    assert _row(markdown, A, B)[4:] == ["pending", "—", "—", "—", "—", "—"]
    assert f"Exact support for `{A}` vs `{B}` is pending" in markdown
    print("  2. A missing folder and a folder without metrics both give pending rows.")


def test_support_mismatch():
    ma, mb = [pd.read_csv(RESULTS / run / "metrics_per_well.csv") for run in RUNS]
    core = mb["core"] & mb["split"].eq("test_drought") & mb["variant"].eq("all")
    row = mb.loc[core].index[0]
    code, support = mb.loc[row, ["code_bss", "support"]]
    mb.loc[row, "support"] = mb.loc[core & mb["support"].ne(support), "support"].iloc[0]
    with TemporaryDirectory() as tmp:
        results = Path(tmp)
        for run, table in zip(RUNS, (ma, mb)):
            (results / run).mkdir()
            table.to_csv(results / run / "metrics_per_well.csv", index=False)
        output = results / "blackbox.md"
        report.main(output, runs=RUNS, contrasts=CONTRASTS, results=results)
        markdown = output.read_text(encoding="utf-8")

    assert _row(markdown, A, B)[4:] == ["support check failed", "—", "—", "—", "—", "—"]
    assert f"test_drought: scored on different well-weeks in the two runs: different weeks ['{code}']" in markdown
    print("  3. One different support digest with the same week count suppresses the pre-specified result.")


if __name__ == "__main__":
    test_saved_runs()
    test_missing_runs()
    test_support_mismatch()
    print("test_blackbox_report: all checks passed")
