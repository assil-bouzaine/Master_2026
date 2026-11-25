"""Measure the cost of LWO level offsets without changing frozen v4 results.

This post-hoc diagnostic follows docs/v5_plan.md section 1, C2. It is outside
analysis-plan-v2: centring changes the transfer protocol for every model family.
Only observed training weeks used by build_panel's mu enter the correction.
No model is fitted, and the frozen feature panel is read without rebuilding it.

    PFE_DATASET=v4 python -m src.analysis.lwo_centring
"""
import json
import numpy as np
import pandas as pd

from src.config import DATASET, ROOT
from src.models import evaluate, regimes
from src.models.features import CACHE, check_panel_cache
from src.models.response import SD_FLOOR

OUTPUT = ROOT / "results" / "v4_diag" / "lwo_centring"
REPORT = ROOT / "docs" / "lwo_centring_v4.md"
KEYS = ["code_bss", "week"]


def frozen_panel():
    """Read the existing panel; rebuilding it would write inside frozen v4."""
    if DATASET != "v4" or evaluate.RESULTS.resolve() != ROOT / "results" / "v4":
        raise ValueError("Run with PFE_DATASET=v4 and without a PFE_RESULTS override")
    if not CACHE.is_file():
        raise FileNotFoundError(f"Frozen panel is missing: {CACHE}; no cache was created")
    check_panel_cache(CACHE)
    return pd.read_parquet(CACHE, columns=KEYS + ["split", "head", "mu", "sd", "core"])


def fold_files(run, splits):
    """Require all planned seeds in every fold, just as assemble_lwo does."""
    response = run.name.startswith(("p4_", "resp_"))
    want = list(range(10)) if response else regimes.DEFAULT_SEEDS
    first_config = run / "fold_0" / "config.json"
    if first_config.is_file():
        want = sorted(json.loads(first_config.read_text())["seeds"])
    if not want or len(want) != len(set(want)):
        raise ValueError(f"{run.name}: empty or repeated planned seeds {want}")
    if splits["leave_wells_out"]["n_folds"] != regimes.N_FOLDS:
        raise ValueError("Dataset fold count differs from assemble_lwo")
    expected_folds = {f"fold_{k}" for k in range(regimes.N_FOLDS)}
    if {p.name for p in run.glob("fold_*") if p.is_dir()} != expected_folds:
        raise ValueError(f"{run.name}: expected folders {sorted(expected_folds)}")
    out = []
    for k in range(regimes.N_FOLDS):
        folder = run / f"fold_{k}"
        config = folder / "config.json"
        if config.is_file() and sorted(json.loads(config.read_text())["seeds"]) != want:
            raise ValueError(f"{folder}: planned seeds differ from fold_0")
        files = sorted(folder.glob("seed_*.parquet"))
        got = sorted(int(f.stem.split("_")[1]) for f in files)
        if got != want:
            raise FileNotFoundError(f"{folder}: has seeds {got}, expected {want}")
        out.append(files)
    return out, want


def rebuild_predictions(run, panel, splits):
    """Reproduce assemble_lwo's aggregation, scale and missing-prediction rule."""
    files, want = fold_files(run, splits)
    folds = splits["leave_wells_out"]["fold_of_well"]
    musd = panel.drop_duplicates("code_bss").set_index("code_bss")[["mu", "sd"]]
    parts = []
    for k, seeds in enumerate(files):
        frames = []
        for file in seeds:
            frame = pd.read_parquet(file)
            if not set(KEYS + ["z"]).issubset(frame.columns):
                raise ValueError(f"{file}: unsupported columns {list(frame.columns)}")
            frames.append(frame)
        z = pd.concat(frames)
        z = z[z["code_bss"].map(folds) == k]
        parts.append(z.groupby(KEYS)["z"].agg(["mean", "std"]).reset_index()
                     .assign(n_seeds=len(seeds)))
    z = pd.concat(parts).join(musd, on="code_bss")
    sd = z["sd"]
    if run.name.startswith(("resp_", "p4_")):
        sd = sd.clip(lower=SD_FLOOR)
    pred = pd.DataFrame({"code_bss": z["code_bss"], "week": z["week"],
                         "pred": z["mu"] + sd * z["mean"], "pred_seed_sd": sd * z["std"],
                         "task": "simulation", "horizon": 0}).dropna(subset=["pred"])
    return pred, want


def assert_frozen_predictions(pred, run):
    """Check scored predictions to 1e-12 m; record the separate seed-spread check.

    LightGBM's own assembler uses numpy mean and population sd, whereas
    assemble_lwo uses pandas mean and sample sd. Only the mean is scored.
    Keep assemble_lwo's spread here, and expose both differences in the summary.
    """
    frozen = pd.read_parquet(run / "predictions.parquet")
    keys = evaluate.PREDICTION_KEYS
    actual = pred.sort_values(keys).reset_index(drop=True)
    expected = frozen.sort_values(keys).reset_index(drop=True)
    pd.testing.assert_frame_equal(actual[keys], expected[keys], check_exact=True)
    np.testing.assert_allclose(actual["pred"], expected["pred"], rtol=0, atol=1e-12)
    return {"max_abs_rebuild_pred_difference_m": float((actual["pred"] - expected["pred"]).abs().max()),
            "max_abs_rebuild_seed_sd_difference_m": float((actual["pred_seed_sd"] - expected["pred_seed_sd"]).abs().max())}


def centre_predictions(pred, panel):
    """Translate each well to mu using its observed training weeks, preserving shape.

    build_panel aggregates head over split == train; pandas skips missing heads.
    There is no additional quality-share or placeholder mask in that calculation.
    All those weeks must have predictions, otherwise this would use a different W.
    """
    if pred.duplicated(KEYS).any() or panel.duplicated(KEYS).any():
        raise ValueError("Centring needs one row per well and week")
    codes = pred["code_bss"].unique()
    window = panel.loc[panel["code_bss"].isin(codes) & panel["split"].eq("train")
                       & panel["head"].notna(), KEYS + ["mu"]]
    training = window.merge(pred[KEYS + ["pred"]], on=KEYS, how="left", validate="one_to_one")
    if training["pred"].isna().any():
        raise ValueError("Some observed training weeks have no prediction; cannot use the exact W")
    offsets = training.groupby("code_bss").agg(
        mean_pred_W=("pred", "mean"), mu=("mu", "first"), n_weeks_W=("week", "size"))
    if set(offsets.index) != set(codes):
        raise ValueError("Some predicted wells have no observed training weeks")
    offsets["offset_m"] = offsets["mean_pred_W"] - offsets["mu"]
    if not np.isfinite(offsets[["mean_pred_W", "mu", "offset_m"]]).all().all():
        raise ValueError("Non-finite centring statistics")
    out = pred.copy()
    out["pred"] = out["pred"] - out["code_bss"].map(offsets["mean_pred_W"]) + out["code_bss"].map(offsets["mu"])
    offsets = offsets.join(panel.drop_duplicates("code_bss").set_index("code_bss")[["core"]])
    return out, offsets.reset_index()


def assert_same_support(before, after):
    """The correction must leave every scored well, variant and week unchanged."""
    keys = ["code_bss", "task", "horizon", "split", "variant"]
    columns = keys + ["n_weeks", "support"]
    pd.testing.assert_frame_equal(before[columns].sort_values(keys).reset_index(drop=True),
                                  after[columns].sort_values(keys).reset_index(drop=True))


def diagnostic_run(run, panel, splits, output=OUTPUT):
    """Write centred predictions, offsets and the shared scorer's tables elsewhere."""
    if output.resolve().is_relative_to(evaluate.RESULTS.resolve()):
        raise ValueError("Diagnostic output must be outside frozen results/v4")
    pred, seeds = rebuild_predictions(run, panel, splits)
    rebuild_check = assert_frozen_predictions(pred, run)
    centred, offsets = centre_predictions(pred, panel)
    before = pd.read_csv(run / "metrics_per_well.csv")
    after = evaluate.score(centred)
    assert_same_support(before, after)
    target = output / run.name
    target.mkdir(parents=True, exist_ok=True)
    centred.to_parquet(target / "predictions.parquet", index=False)
    offsets.to_csv(target / "offsets.csv", index=False)
    after.to_csv(target / "metrics_per_well.csv", index=False)
    evaluate.summarise(after).to_csv(target / "metrics_summary.csv", index=False)
    row = {"run": run.name, "family": "response" if run.name.startswith(("p4_", "resp_")) else "baseline",
           "n_seeds": len(seeds), "n_wells_offset": len(offsets),
           "median_abs_offset_m": offsets.loc[offsets["core"], "offset_m"].abs().median(),
           "median_abs_offset_all_wells_m": offsets["offset_m"].abs().median(), **rebuild_check}
    for label, metrics in (("before", before), ("after", after)):
        core = metrics.loc[metrics["core"] & metrics["variant"].eq("all")
                           & metrics["task"].eq("simulation") & metrics["horizon"].eq(0)]
        for split, endpoint in (("test_drought", "drought"), ("validation", "validation")):
            selected = core.loc[core["split"].eq(split)]
            row[f"{endpoint}_n_wells_{label}"] = selected["code_bss"].nunique()
            row[f"{endpoint}_NSE_{label}"] = selected["NSE"].median()
            if endpoint == "drought":
                row[f"drought_RMSE_{label}_m"] = selected["RMSE"].median()
    return row


def markdown_table(summary):
    """Render the requested endpoints without an optional tabulate dependency."""
    lines = ["| Run | Drought NSE before | after | Drought RMSE before (m) | after (m) | Validation NSE before | after | Median absolute offset (m) |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    columns = ["drought_NSE_before", "drought_NSE_after", "drought_RMSE_before_m",
               "drought_RMSE_after_m", "validation_NSE_before", "validation_NSE_after", "median_abs_offset_m"]
    for row in summary.to_dict("records"):
        lines.append("| `" + row["run"] + "` | " + " | ".join(f"{row[c]:.3f}" for c in columns) + " |")
    return "\n".join(lines)


def write_document(summary, skipped, panel, splits):
    """Explain the changed protocol and reproduce the review's example honestly."""
    train_start, train_end = splits["train"]
    lines = ["Generated by `python -m src.analysis.lwo_centring`; do not edit by hand.", "",
             "This is a post-hoc diagnostic outside the pre-registered plan (`analysis-plan-v2`). "
             "It was chosen after seeing the v4 results. The frozen v4 numbers stand. "
             "Centring changes the transfer protocol and is applied to every model family with the supported LWO layout.", "",
             "# Centring the v4 leave-wells-out predictions", "",
             "Each ensemble is rebuilt exactly as `src.models.regimes.assemble_lwo`, including its seed check "
             "and the response model's sd floor, and checked against the frozen `predictions.parquet`. "
             "The before scores come from each frozen run's own `metrics_per_well.csv`.", "",
             "Rebuilt prediction keys must match exactly and prediction values must match within 1e-12 m "
             "absolute tolerance (floating-point aggregation order). Differences in prediction means and seed "
             "spread are recorded separately in `summary.csv`. LightGBM's own assembler (`src/models/lgbm.py`) "
             "uses numpy's population sd; `assemble_lwo` uses pandas' sample sd. This diagnostic keeps "
             "`assemble_lwo`'s spread. Seed spread does not enter any score or the centring correction.", "",
             f"For well i, W contains its non-missing observed heads in the training split ({train_start} to {train_end}). "
             "These are exactly the rows used by `build_panel` for mu and sd (pandas mean and sample sd). "
             "No extra quality-share or placeholder mask enters those statistics. "
             "Head availability selects W; no head magnitude beyond the permitted mu is used. "
             "Every W week must have a prediction, otherwise the run is skipped with a reason. "
             "The correction is `pred_c = pred - mean_W(pred) + mu`. It only translates each series: "
             "its temporal shape and seed spread stay the same.", "",
             "The after scores use `src.models.evaluate.score` and `summarise`, with the same splits, "
             "variants, placeholder masks, benchmarks and minimum 26-week support. Exact scored-week support "
             "is checked against the frozen metrics. Table endpoints use core wells, simulation, horizon 0, variant `all`. "
             "Median absolute offsets also use core wells; the CSV includes an all-well median. "
             "Offsets for every predicted well and their W sizes are saved in each diagnostic run's `offsets.csv`.", "",
             f"Found {len(summary) + len(skipped)} LWO runs; scored {len(summary)} and skipped {len(skipped)}. "
             f"The frozen panel contains {panel['code_bss'].nunique()} wells.", ""]
    for family, title in (("response", "Response-model runs"), ("baseline", "Baselines")):
        lines.extend([f"## {title}", "", markdown_table(summary.loc[summary["family"].eq(family)]), ""])
    lines.extend(["## Check of the review's example", ""])
    example = summary.loc[summary["run"].eq("p4_B2_D_r1_lwo")]
    if not example.empty:
        row = example.iloc[0]
        lines.append(f"For `p4_B2_D_r1_lwo`, validation median NSE is {row['validation_NSE_before']:.6f} → "
                     f"{row['validation_NSE_after']:.6f}; drought median RMSE is {row['drought_RMSE_before_m']:.6f} → "
                     f"{row['drought_RMSE_after_m']:.6f} m "
                     f"({100 * (1 - row['drought_RMSE_after_m'] / row['drought_RMSE_before_m']):.2f}% reduction). "
                     "The review (§2.3, bug 1) reports validation NSE −0.316 → +0.046 and RMSE 1.109 → 0.866 m. "
                     "Only the starting validation NSE agrees at the quoted precision. "
                     "The values above use the observed-training-week W specified here, and the before RMSE "
                     "is read directly from the frozen metrics. The review's exact calculation is not "
                     "available here, so the remaining discrepancy is unresolved.")
    else:
        lines.append("The example could not be scored; see the skip reason below.")
    lines.extend(["", "## Skipped layouts or incomplete runs", ""])
    lines.extend([f"- `{name}`: {reason}" for name, reason in skipped] or ["None."])
    lines.extend(["", "Outputs are under `results/v4_diag/lwo_centring/`; nothing is written inside `results/v4/`. "
                  "A lower error after centring measures the effect of an additive offset under this changed protocol. "
                  "It does not establish improved dynamics or a pre-registered gain.", ""])
    REPORT.write_text("\n".join(lines), encoding="utf-8")


def main():
    panel = frozen_panel()
    splits = json.loads((evaluate.DS / "splits.json").read_text())
    rows, skipped = [], []
    runs = sorted((p for p in evaluate.RESULTS.iterdir() if p.is_dir() and p.name.endswith("_lwo")),
                  key=lambda p: (not p.name.startswith(("p4_", "resp_")), p.name))
    for run in runs:
        try:
            files, seeds = fold_files(run, splits)
            sample = pd.read_parquet(files[0][0])
            print(f"{run.name}: {len(files)} folds, seeds {seeds}, columns {list(sample.columns)}; "
                  f"sample {sample.head(1).to_dict('records')}", flush=True)
            row = diagnostic_run(run, panel, splits)
        except (ValueError, FileNotFoundError, KeyError, AssertionError) as error:
            reason = str(error)
            skipped.append((run.name, reason))
            print(f"SKIP {run.name}: {reason}", flush=True)
            continue
        rows.append(row)
        print(f"  drought NSE {row['drought_NSE_before']:.3f} -> {row['drought_NSE_after']:.3f}; "
              f"median |offset| {row['median_abs_offset_m']:.3f} m", flush=True)
    if not rows:
        raise RuntimeError("No supported complete LWO run could be scored")
    summary = pd.DataFrame(rows)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    summary.to_csv(OUTPUT / "summary.csv", index=False)
    write_document(summary, skipped, panel, splits)
    print(markdown_table(summary), flush=True)


if __name__ == "__main__":
    main()
