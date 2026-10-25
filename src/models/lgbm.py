"""LightGBM baseline: one global gradient-boosted tree model for all wells.

    python -m src.models.lgbm                 # select config on validation, then 5 seeds
    python -m src.models.lgbm --tune 24       # Optuna, same budget as the neural models
                                              # (docs/analysis_plan.md section 5) -> lgbm_tuned
    python -m src.models.lgbm --tune 24 --no-clim              # -> lgbm_noclim_tuned
    python -m src.models.lgbm --no-clim --regimes lwo f25 f50  # RQ1 regimes of that config

clim_z (each well's training climatology of z, its dominant feature) is computed from the
well's own observed heads. Fine for the temporal test of a monitored well, but the neural
models do not get it, and it leaks in the regimes: held-out wells' heads (lwo) and the
training years that f25/f50 remove. --no-clim gives LightGBM the networks' information set;
the regimes require it.

Configurations (chosen on the VALIDATION median NSE only, never on test):
    base     num_leaves 31, min_data_in_leaf 40
    reg      num_leaves 15, min_data_in_leaf 200, stronger L2, feature_fraction 0.5
    reg_nostatic  reg without x, y, altitude, artesian share (only group and
             investigation depth kept): limits memorising wells through identity-like
             statics (Heudorfer et al. 2024, doi:10.5194/hess-28-525-2024)
Targets (also chosen on validation):
- simulation: z (z-scored head) or anom (z minus the training climatology
  of that well and week of year); `linear` configs use LightGBM linear
  trees, whose leaves are linear models and can extrapolate below the
  training range (the 2022-2024 drought is below it; plain trees cannot).
- forecast: the correction to anomaly persistence,
  resid = z_t - [clim_z(t) + anom(t-h)], so the model starts from the
  strong naive forecast and only learns what it can improve.
Sample weights give every well the same total weight, divided by the
variance of its target: the squared-error objective then matches the
per-well NSE we report, instead of being dominated by the flashy karst wells.
Selection score = median validation NSE over the core wells (as evaluate.py).

Target: per-well z-scored head (training mean/sd), so one model serves all
wells; predictions are transformed back to m NGF. Early stopping on the
validation split (never on test). Seeds differ in row/feature subsampling;
the reported prediction is the mean of the 5 seeds (an ensemble), and the
spread between seeds is saved for the uncertainty discussion.

Simulation: inputs = weather windows, pumping, season, static attributes;
no observed head is used. Forecast h: inputs taken at the issue week t-h,
plus the head anomaly observed at t-h (src.models.features.lagged_panel).
"""
import argparse
import json

import lightgbm as lgb
import numpy as np
import pandas as pd

from src.config import R3_STARTS
from src.models.evaluate import DS, RESULTS, evaluate_run
from src.models.features import (R3_WINDOW_STATS, build_panel, input_columns, lagged_panel,
                                  land_use_identity)
from src.models.manifest import write_manifest

SEEDS = (0, 1, 2, 3, 4)
BASE = {"objective": "l2", "learning_rate": 0.03, "num_leaves": 31, "min_data_in_leaf": 40,
        "feature_fraction": 0.7, "bagging_fraction": 0.8, "bagging_freq": 1,
        "lambda_l2": 1.0, "verbose": -1, "num_threads": 4}
REG = dict(BASE, num_leaves=15, min_data_in_leaf=200, lambda_l2=10.0, feature_fraction=0.5)
IDENTITY_STATICS = ("x", "y", "altitude_station", "pct_days_artesian")
LIN = dict(REG, linear_tree=True, linear_lambda=1.0)
CONFIGS = {"base": (BASE, False), "reg": (REG, False), "reg_nostatic": (REG, True),
           "reg_linear": (LIN, False)}
SIM_TARGETS = ("z", "anom")
N_FOLDS = 5
FRACTIONS = R3_STARTS


def fit_predict(D, cols, seed, params, target, train_mask=True, es_mask=True):
    """train_mask / es_mask (boolean Series aligned with D) restrict the training rows and
    the early-stopping (validation) rows, for the RQ1 regimes."""
    ok = D[target].notna()
    tr = D[(D["split"] == "train") & ok & train_mask]
    va = D[(D["split"] == "validation") & ok & es_mask]
    params = dict(params, seed=seed, bagging_seed=seed, feature_fraction_seed=seed)
    booster = lgb.train(params, lgb.Dataset(tr[cols], tr[target], weight=well_weights(tr, target)),
                        num_boost_round=4000,
                        valid_sets=[lgb.Dataset(va[cols], va[target],
                                                weight=well_weights(va, target))],
                        callbacks=[lgb.early_stopping(200, verbose=False)])
    yhat = booster.predict(D[cols], num_iteration=booster.best_iteration)
    if target == "anom":
        yhat = yhat + D["clim_z"].to_numpy()
    elif target == "resid":
        yhat = yhat + D["clim_z"].to_numpy() + D["anom_issue"].to_numpy()
    return yhat, booster


def well_weights(D, target):
    g = D.groupby("code_bss")[target]
    w = 1.0 / (g.transform("count") * g.transform("var").clip(lower=1e-3))
    return (w / w.mean()).to_numpy()


def val_nse(D, z):
    """Median per-well NSE on the validation split (heads in m), for model selection."""
    d = D[["code_bss", "split", "head", "mu", "sd"]].assign(pred=D["mu"] + D["sd"] * z)
    d = d[(d["split"] == "validation") & D["core"] & d["head"].notna() & d["pred"].notna()]
    r = []
    for _, g in d.groupby("code_bss"):
        if len(g) >= 26:
            o, s = g["head"].to_numpy(), g["pred"].to_numpy()
            r.append(1 - ((s - o) ** 2).sum() / ((o - o.mean()) ** 2).sum())
    return float(np.median(r))


def tune(D, cols, n_trials, out, targets=SIM_TARGETS):
    """Optuna TPE (seed 2026) over 4 hyperparameters + the target, scored by the median
    validation NSE over core wells; then the best configuration with 5 seeds."""
    import optuna

    out.mkdir(parents=True, exist_ok=True)
    study = optuna.create_study(direction="maximize", study_name="lgbm",
                                storage=f"sqlite:///{out / 'study.db'}", load_if_exists=True,
                                sampler=optuna.samplers.TPESampler(seed=2026))

    def score(p, seed):
        params = dict(BASE, **{k: v for k, v in p.items() if k != "target"})
        z, _ = fit_predict(D, cols, seed, params, p["target"])
        return val_nse(D, z)

    def objective(trial):
        return score({"num_leaves": trial.suggest_int("num_leaves", 7, 63, log=True),
                      "min_data_in_leaf": trial.suggest_int("min_data_in_leaf", 20, 400, log=True),
                      "feature_fraction": trial.suggest_float("feature_fraction", 0.3, 0.9),
                      "lambda_l2": trial.suggest_float("lambda_l2", 0.1, 30.0, log=True),
                      "target": trial.suggest_categorical("target", list(targets))}, 0)

    from src.models.tune import reselect

    done = len([t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE])
    study.optimize(objective, n_trials=max(0, n_trials - done))
    b, mean, number = reselect(study, score, out)
    print(f"    best single-seed trial {study.best_trial.number}: {study.best_value:.3f}; "
          f"selected trial {number} (3-seed mean {mean:.3f}): {b}", flush=True)
    (out / "best.json").write_text(json.dumps({"params": b, "trial": number,
                                               "validation_median_nse_3seed": mean,
                                               "single_seed_best": study.best_value,
                                               "n_trials": len(study.trials)}, indent=1))
    return final_seeds(D, cols, b, save_dir=out)


def final_seeds(D, cols, b, save_dir=None, extra=None):
    """The selected configuration b (best.json "params") trained with the 5 seeds. With
    `save_dir`, each booster is saved there (model_seed_<k>.txt) with a manifest.json;
    `extra` (e.g. the land-use identity record) is added to the manifest's configuration."""
    params = dict(BASE, **{k: v for k, v in b.items() if k != "target"})
    preds = []
    for s in SEEDS:
        z, booster = fit_predict(D, cols, s, params, b["target"])
        preds.append(z)
        if save_dir is not None:
            booster.save_model(str(save_dir / f"model_seed_{s}.txt"),
                               num_iteration=booster.best_iteration)
    if save_dir is not None:
        write_manifest(save_dir, {"params": params, "target": b["target"], "inputs": cols}
                       | (extra or {}), SEEDS)
    Z = np.vstack(preds)
    o = D[["code_bss", "week"]].copy()
    o["pred"] = D["mu"].values + D["sd"].values * Z.mean(axis=0)
    o["pred_seed_sd"] = D["sd"].values * Z.std(axis=0)
    o["task"], o["horizon"] = "simulation", 0
    return o.dropna(subset=["pred"])


def regimes(D, cols, run, which):
    """RQ1 regimes (docs/analysis_plan.md section 4) with the tuned configuration of `run`:
    lwo = 5 leave-wells-out folds (early stopping on the training wells only), f25 / f50 =
    shorter training period (from dataset v4 with the per-well statistics of that period only,
    src.models.features). One file per fold and seed (resumable); 5 seeds averaged."""
    b = json.loads((RESULTS / run / "best.json").read_text())["params"]
    params = dict(BASE, **{k: v for k, v in b.items() if k != "target"})
    fold_of = json.loads((DS / "splits.json").read_text())["leave_wells_out"]["fold_of_well"]
    full = D
    for name in which:
        D = full
        if name in FRACTIONS and R3_WINDOW_STATS:
            D = build_panel(train_start=FRACTIONS[name])
            D = D[D["mu"].notna()].reset_index(drop=True)
        fold = D["code_bss"].map(fold_of)
        keys = D[["code_bss", "week"]]
        out = RESULTS / f"{run}_{name}"
        jobs = ([(f"fold_{k}", fold != k, fold == k) for k in range(N_FOLDS)] if name == "lwo"
                else [("", D["week"] >= pd.Timestamp(FRACTIONS[name]), None)])
        preds = []
        for sub, train_mask, keep in jobs:
            d = out / sub
            d.mkdir(parents=True, exist_ok=True)
            zs = []
            for s in SEEDS:
                f = d / f"seed_{s}.parquet"
                if not f.exists():
                    z, booster = fit_predict(D, cols, s, params, b["target"], train_mask,
                                             train_mask if name == "lwo" else True)
                    booster.save_model(str(d / f"model_seed_{s}.txt"),
                                       num_iteration=booster.best_iteration)
                    keys.assign(z=z).to_parquet(f, index=False)
                    write_manifest(d, {"params": params, "target": b["target"], "inputs": cols,
                                       "regime": name, "fold": sub or None}, [s])
                    print(f"    {out.name} {sub} seed {s} done", flush=True)
                zs.append(keys.merge(pd.read_parquet(f), on=["code_bss", "week"], how="left")["z"]
                          .to_numpy())
            Z = np.vstack(zs)
            o = keys.copy()
            o["pred"] = D["mu"].values + D["sd"].values * Z.mean(axis=0)
            o["pred_seed_sd"] = D["sd"].values * Z.std(axis=0)
            preds.append(o if keep is None else o[keep.to_numpy()])
        p = pd.concat(preds).dropna(subset=["pred"]).assign(task="simulation", horizon=0)
        p.to_parquet(out / "predictions.parquet", index=False)
        s = evaluate_run(out.name)
        c = s[(s["group"] == "all core") & (s["variant"] == "all")]
        print(f"== {out.name}\n" + c[["split", "n_wells", "NSE", "skill", "KGE", "RMSE"]]
              .round(3).to_string(index=False), flush=True)


def run(task, h, D, cols, run_id, seeds=SEEDS):
    targets = SIM_TARGETS if task == "simulation" else ("resid",)
    best = None
    for target in targets:
        for name, (params, drop) in CONFIGS.items():
            c = [x for x in cols if not (drop and x.split("_issue")[0] in IDENTITY_STATICS)]
            z, _ = fit_predict(D, c, 0, params, target)
            score = val_nse(D, z)
            print(f"    {task} h={h} target {target:<5} config {name:<13} "
                  f"validation median NSE {score:.3f}", flush=True)
            if best is None or score > best[0]:
                best = (score, name, params, c, target)
    _, name, params, cols, target = best
    print(f"    -> selected {name} / {target}", flush=True)
    preds, imps = [], []
    for s in seeds:
        z, booster = fit_predict(D, cols, s, params, target)
        preds.append(z)
        imps.append(pd.Series(booster.feature_importance("gain"), index=cols))
    Z = np.vstack(preds)
    out = D[["code_bss", "week"]].copy()
    out["pred"] = D["mu"].values + D["sd"].values * Z.mean(axis=0)
    out["pred_seed_sd"] = D["sd"].values * Z.std(axis=0)
    out["task"], out["horizon"] = task, h
    out = out.dropna(subset=["pred"])
    imp = pd.concat(imps, axis=1).mean(axis=1).sort_values(ascending=False)
    return out, imp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh-panel", action="store_true")
    ap.add_argument("--tune", type=int, default=0, help="Optuna trials (simulation task)")
    ap.add_argument("--no-clim", action="store_true",
                    help="without the well's own training climatology (clim_z): the inputs of "
                         "the neural models -> lgbm_noclim_tuned")
    ap.add_argument("--regimes", nargs="+", choices=["lwo", "f25", "f50"],
                    help="RQ1 regimes with the tuned --no-clim configuration")
    ap.add_argument("--final-only", action="store_true",
                    help="5 seeds of the configuration in <tuned>/best.json, no search "
                         "(dataset v4 re-runs reuse the v3 selection, scripts/v4_from_v3.py)")
    ap.add_argument("--land-use", choices=["on", "placebo", "wide", "frozen", "none"],
                    help="with --final-only --no-clim: add the crop-demand inputs, main, placebo, "
                         "wide or frozen (analysis plan §14 item 13) -> lgbm_noclim_tuned_lu_<variant>, with "
                         "the settings and seeds of lgbm_noclim_tuned, its run without them; none: "
                         "that run's inputs again, in the land-use job (a control for the machine)")
    args = ap.parse_args()
    if args.land_use and not (args.final_only and args.no_clim and not args.regimes):
        ap.error("--land-use is the pre-registered test: use it with --final-only --no-clim")
    with_lu = args.land_use if args.land_use != "none" else None
    P = build_panel(refresh=args.refresh_panel, land_use=with_lu)
    P = P[P["mu"].notna()].reset_index(drop=True)  # wells with training data
    P["resid"] = np.nan
    cols = [c for c in input_columns(P) if c != "resid" and not (args.no_clim and c == "clim_z")]
    tuned = "lgbm_noclim_tuned" if args.no_clim else "lgbm_tuned"
    if args.regimes:
        if not args.no_clim:
            ap.error("the regimes need --no-clim: clim_z is computed from the held-out wells' "
                     "heads (lwo) and from the training years that f25/f50 remove")
        regimes(P, cols, tuned, args.regimes)
        return
    if args.tune or args.final_only:
        out = RESULTS / tuned
        if args.final_only:
            best = json.loads((out / "best.json").read_text())["params"]
            extra = None
            if args.land_use:  # the tuned run's settings, a separate output folder
                out = RESULTS / f"{tuned}_lu_{args.land_use}"
                out.mkdir(parents=True, exist_ok=True)
                extra = {"land_use": land_use_identity(with_lu) if with_lu else
                         "none: the inputs of the run without land use, re-run in the land-use job"}
            pred = final_seeds(P, cols, best, save_dir=out, extra=extra)
        else:
            pred = tune(P, cols, args.tune, out, ("z",) if args.no_clim else SIM_TARGETS)
        pred.to_parquet(out / "predictions.parquet", index=False)
        s = evaluate_run(out.name)
        c = s[(s["group"] == "all core") & (s["variant"] == "all")]
        print(c[["split", "n_wells", "NSE", "skill", "KGE", "RMSE"]].round(3).to_string(index=False))
        return
    jobs = {"lgbm_sim": [("simulation", 0, P, [c for c in input_columns(P) if c != "resid"])]}
    jobs["lgbm_fc"] = []
    for h in (4, 12):
        L = lagged_panel(P, h)
        L["resid"] = L["z"] - (L["clim_z"] + L["anom_issue"])
        cols = [c for c in L.columns if c.endswith("_issue") or c.startswith("z_issue")
                or c.startswith("anom_issue") or c == "clim_z"
                or c.startswith("season_") or c in ("altitude_station", "profondeur_investigation",
                                                    "x", "y", "group_code", "pct_days_artesian")]
        jobs["lgbm_fc"].append(("forecast", h, L, cols))
    for run_id, items in jobs.items():
        out_dir = RESULTS / run_id
        out_dir.mkdir(parents=True, exist_ok=True)
        preds = []
        for task, h, D, cols in items:
            pr, imp = run(task, h, D, cols, run_id)
            preds.append(pr)
            imp.head(25).to_csv(out_dir / f"importance_{task}_{h}.csv")
            print(f"[{run_id}] {task} h={h}: top features {list(imp.index[:6])}", flush=True)
        pd.concat(preds).to_parquet(out_dir / "predictions.parquet", index=False)
        s = evaluate_run(run_id)
        core = s[(s["group"] == "all core") & (s["variant"] == "all")]
        print(core[["task", "horizon", "split", "n_wells", "NSE", "KGE", "RMSE"]].round(3)
              .to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
