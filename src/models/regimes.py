"""Run the RQ1 regimes for a tuned neural model (docs/analysis_plan.md section 4).

    python -m src.models.regimes --model lstm                 # all regimes, resumable
    python -m src.models.regimes --model stgnn --only lwo f25

Uses the configuration chosen by src.models.tune (results/<v>/<model>_tuning/best.json):
    <model>_tuned_lwo     left-out monitored wells: 5 leave-wells-out folds x 5 seeds; each fold's
                          held-out wells are predicted by the models trained without them,
                          then the five folds are assembled into one prediction file
    <model>_tuned_f25     less data: training period 2016-04-01 .. 2019-12-31 (25 %)
    <model>_tuned_f50     less data: training period 2012-07-01 .. 2019-12-31 (50 %)
    <model>_tuned_refit   trained on train + validation, epochs fixed by <model>_tuned
"""
import argparse
import json
import subprocess
import sys

import pandas as pd

from src.config import R3_STARTS
from src.models.evaluate import DS, RESULTS, evaluate_run
from src.models.features import build_panel
from src.models.tune import MODULE

N_FOLDS = 5
FRACTIONS = R3_STARTS
DEFAULT_SEEDS = [0, 1, 2, 3, 4]   # the default --seeds of src.models.lstm and stgnn


EXTRA = []


def base_cmd(model, run):
    p = json.loads((RESULTS / f"{model}_tuning" / "best.json").read_text())["params"]
    cmd = [sys.executable, "-m", MODULE[model], "--run", run, "--lookback", str(p["lookback"]),
           "--hidden", str(p["hidden"]), "--dropout", str(p["dropout"]), "--lr", str(p["lr"])]
    return cmd + (["--arch", model] if model in ("lstm", "ealstm") else []) + EXTRA


def expected_seeds():
    """The seeds every fold must have: --seeds among the extra arguments, else the default."""
    if "--seeds" in EXTRA:
        i = EXTRA.index("--seeds") + 1
        out = []
        while i < len(EXTRA) and not EXTRA[i].startswith("--"):
            out.append(int(EXTRA[i]))
            i += 1
        return out
    return DEFAULT_SEEDS


def fold_seed_files(run, k, want):
    """The seed files of fold k, which must be exactly the seeds `want`."""
    files = sorted((RESULTS / run / f"fold_{k}").glob("seed_*.parquet"))
    got = sorted(int(f.stem.split("_")[1]) for f in files)
    if got != list(want):
        raise FileNotFoundError(f"{run}/fold_{k} has seeds {got}, expected {list(want)}")
    return files


def assemble_lwo(run, seeds=None):
    """Held-out predictions of every fold -> one predictions.parquet, then score it. Every
    fold must hold exactly the expected seeds: a partly finished fold is not an ensemble
    (third review, docs/review_codex_2026-10-24.md §7)."""
    folds = json.loads((DS / "splits.json").read_text())["leave_wells_out"]["fold_of_well"]
    P = build_panel()
    musd = P.drop_duplicates("code_bss").set_index("code_bss")[["mu", "sd"]]
    want = sorted(expected_seeds() if seeds is None else seeds)
    parts = []
    for k in range(N_FOLDS):
        seeds = fold_seed_files(run, k, want)
        z = pd.concat(pd.read_parquet(f) for f in seeds)
        z = z[z["code_bss"].map(folds) == k]
        parts.append(z.groupby(["code_bss", "week"])["z"].agg(["mean", "std"]).reset_index()
                     .assign(n_seeds=len(seeds)))
    z = pd.concat(parts).join(musd, on="code_bss")
    pred = pd.DataFrame({"code_bss": z["code_bss"], "week": z["week"],
                         "pred": z["mu"] + z["sd"] * z["mean"], "pred_seed_sd": z["sd"] * z["std"],
                         "task": "simulation", "horizon": 0}).dropna(subset=["pred"])
    pred.to_parquet(RESULTS / run / "predictions.parquet", index=False)
    return evaluate_run(run)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=list(MODULE), required=True)
    ap.add_argument("--only", nargs="*", default=["lwo", "f25", "f50", "refit"])
    ap.add_argument("--extra", nargs=argparse.REMAINDER, default=[],
                    help="arguments passed to every training command (e.g. --seeds 0 --epochs 2)")
    args = ap.parse_args()
    m = args.model
    EXTRA.extend(args.extra)
    if "lwo" in args.only:
        run = f"{m}_tuned_lwo"
        for k in range(N_FOLDS):
            subprocess.run(base_cmd(m, run) + ["--fold", str(k)], check=True)
        s = assemble_lwo(run)
        print(s[(s["group"] == "all core") & (s["variant"] == "all")].round(3).to_string(index=False))
    for name, start in FRACTIONS.items():
        if name in args.only:
            subprocess.run(base_cmd(m, f"{m}_tuned_{name}") + ["--train-start", start], check=True)
    if "refit" in args.only:
        subprocess.run(base_cmd(m, f"{m}_tuned_refit") + ["--refit-from", f"{m}_tuned"],
                       check=True)


if __name__ == "__main__":
    main()
