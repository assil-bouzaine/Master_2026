"""Measure how much fitted pumping contributions vary across starts on real heads.

Analysis plan §14 items 19 and 22–24 define shortcut test 2. This report uses
the saved contributions and shows their stability beside the twin's grid.

    PFE_DATASET=v4 python -m src.analysis.seed_disagreement
"""

import json
from itertools import combinations

import numpy as np
import pandas as pd

from src.analysis import twin_report
from src.config import DATASET, RESULTS_DIR, ROOT, TEST_PERIODS
from src.models.evaluate import MIN_WEEKS

OUT = ROOT / "docs" / f"results_seed_disagreement_{DATASET}.md"
STARTS = tuple(range(10))
RUNS = (
    "p4_B2_C_r1", "p4_B2_D_r1",
    *(f"p4_B2conv_{arm}_r{r}" for arm in ("C", "D") for r in (1, 2, 3)),
    *(f"p4_B4_D_{signs}_r1" for signs in ("hard", "none", "soft1", "soft10", "soft100")),
    "resp_free", "resp_pooled_l001", "resp_pooled_l01", "resp_pooled_l01_conv",
)


def panel_inputs(path):
    """Read the observed training scales and the weeks used by the twin's score."""
    panel = pd.read_parquet(path, columns=["code_bss", "week", "split", "core", "head", "sd"])
    train = panel["split"].eq("train")
    drought = panel["week"].between(*TEST_PERIODS["test_drought"])
    # As in the twin, require drought observations for eligibility. Once a well
    # is eligible, compare fitted contributions on every drought week.
    observed = drought & panel["core"] & np.isfinite(panel["head"])
    support = panel.loc[observed].groupby("code_bss").size()
    core = support.index[support >= MIN_WEEKS]
    sd = panel.drop_duplicates("code_bss").set_index("code_bss")["sd"].reindex(core)
    return sd, panel.loc[train, "week"].unique(), panel.loc[drought, "week"].unique()


def centred_pumping(path, wells, train_weeks, drought_weeks):
    """Sum pumping stresses in metres and remove this start's own training mean."""
    frame = pd.read_parquet(path)
    pumping = frame["pumping"].astype(float)
    if "pumping_unattributed" in frame:
        pumping = pumping + frame["pumping_unattributed"]
    wide = frame.assign(pumping=pumping).pivot(index="code_bss", columns="week", values="pumping")
    wide = wide.reindex(wells)
    train = wide.reindex(columns=train_weeks).to_numpy()
    drought = wide.reindex(columns=drought_weeks).to_numpy()
    return drought - train.mean(axis=1, keepdims=True)


def pair_disagreements(run, sd, train_weeks, drought_weeks, *, starts=STARTS):
    """Return scaled drought RMSEs per eligible well and pair of saved starts."""
    values = np.stack([centred_pumping(run / f"contrib_seed_{k}.parquet", sd.index, train_weeks, drought_weeks)
                       for k in starts])
    # Use the same wells for every pair so their medians measure the same cohort.
    scale = sd.to_numpy()
    valid = np.isfinite(scale) & (scale > 0) & np.isfinite(values).all(axis=(0, 2))
    if not valid.any():
        raise ValueError(f"{run}: no eligible core well with a positive training sd and complete contributions")
    scale = scale[valid]
    pairs = combinations(zip(starts, values[:, valid]), 2)
    return pd.DataFrame({(j, k): np.sqrt(np.mean((p - q) ** 2, axis=1)) / scale
                         for (j, p), (k, q) in pairs}, index=sd.index[valid])


def protocol(config):
    """Name the fitting protocol recorded with the contributions."""
    mode = config["mode"]
    if mode == "pooled":
        mode += f" λ = {config['lam']:g}"
    fixed = config.get("fixed_steps")
    stopping = f"{fixed:,} fixed steps" if fixed else "early stopping"
    return f"{mode}, {stopping}"


def real_rows(results):
    inputs = panel_inputs(results / "_cache" / "panel.parquet")
    for name in RUNS:
        run = results / name
        config = run / "config.json"
        if not config.is_file() or not all((run / f"contrib_seed_{k}.parquet").is_file() for k in STARTS):
            yield f"| `{name}` | — | pending | — | — |"
            continue
        pairs = pair_disagreements(run, *inputs)
        medians = pairs.median()
        fit = protocol(json.loads(config.read_text()))
        yield f"| `{name}` | {fit} | {medians[0, 1]:.3f} | {medians.mean():.3f} | {len(pairs)} |"


def twin_rows(grid):
    tau = twin_report.seed_thresholds(grid) if not grid.empty else {}
    for setting in twin_report.PROTOCOLS:
        for arm in ("C", "D"):
            if (arm, setting) not in tau:
                yield f"| {arm} | `{setting}` | pending | — | — |"
                continue
            threshold, count = tau[arm, setting]
            scores = grid.loc[grid["run"].eq(twin_report.GRID_RUN) & grid["setting"].eq(setting),
                              f"seed_disagreement_pumping_{arm}"]
            yield f"| {arm} | `{setting}` | {twin_report._median(scores)} | {threshold:.3f} | {count} |"


def write_report(path, results, grid):
    """Render the diagnostic from the saved real-data starts and twin grid."""
    start, end = TEST_PERIODS["test_drought"]
    lines = [
        f"# Pumping contribution disagreement across starts ({DATASET})",
        "",
        "Generated by `python -m src.analysis.seed_disagreement`. Do not edit by hand.",
        "",
        "Shortcut test 2 is an **uncalibrated** stability diagnostic. In slice F, it missed both "
        "arm D worlds with wrong reasons, leaving its detection power unproven. Low disagreement "
        "only establishes that the starts agree.",
        "",
        "Real-data values use the observed head's training standard deviation, while the twin uses "
        "the noise-free head's training standard deviation. The twin's τ is shown for context.",
        "",
        "## Real data",
        "",
        "Each start's pumping contribution sums attributed and unattributed pumping where both "
        "are available. Each series is centred on its own mean over the R1 training weeks "
        "(2005-01-01 to 2019-12-31). The cached panel's `sd` is the per-well sample standard "
        "deviation of observed heads in that same training period.",
        "",
        f"For each pair, take the RMSE over all drought weeks ({start} to {end}), divide by the well's "
        f"training SD, then take the median over core wells with at least {MIN_WEEKS} observed drought "
        "weeks and complete contributions for all starts. The sensitivity averages those medians "
        "over all 45 pairs.",
        "",
        "| Run | Protocol | Starts 0–1 | All-pairs mean | Core wells |",
        "|---|---|---:|---:|---:|",
        *real_rows(results),
        "",
        "## Twin grid",
        "",
        "Each row summarises the world-level disagreement over the base grid for its arm and "
        "protocol. The twin's early-stopping protocol used free fits. The Phase 4 early-stopping "
        "runs used pooling with λ = 0.01.",
        "",
        "| Arm | Protocol | Median | 95th percentile (τ) | Worlds |",
        "|---|---|---:|---:|---:|",
        *twin_rows(grid),
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    grid = twin_report.load({twin_report.GRID_RUN})
    write_report(OUT, RESULTS_DIR, grid)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
