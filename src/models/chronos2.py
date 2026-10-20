"""Chronos-2 baselines (forecast task, horizons 4 and 12 weeks).

    python -m src.models.chronos2                  # zero-shot, one well at a time -> chronos2
    python -m src.models.chronos2 --mode xl        # zero-shot, cross-learning   -> chronos2_xl
    python -m src.models.chronos2 --mode ft        # fine-tuned on train          -> chronos2_ft

Ansari et al. 2025, Chronos-2: From Univariate to Universal Forecasting,
arXiv:2510.15821. Weights: Hugging Face "amazon/chronos-2".

Rolling origin: for every issue week t0 in the validation and test splits, the model sees
the well's z-scored head up to t0 (last CONTEXT weeks, gaps as NaN) with past covariates
(rain, ETP, effective rain, drainage, local pumping, canal volume; rivers from dataset v3)
and the calendar (season) as a known future covariate; it predicts the next 12 weeks.
Future weather is treated as unknown (operational setting).

Modes
    zeroshot  no training on our data; the issue weeks of one well are batched together
              (independent predictions, cross_learning off)
    xl        zero-shot with cross-learning (group attention across the series of a batch):
              each batch holds ALL wells at the SAME issue week, so information is shared
              between wells but never across time (a batch mixing issue weeks of one well
              would let a later context leak into an earlier forecast)
    ft        full fine-tuning (library defaults: learning rate 1e-6, 1000 steps) on the
              training period only (2005-2019 series); the validation period serves the
              library's model selection; then predicted as zero-shot. No choice uses test.
"""
import argparse

import numpy as np
import pandas as pd
import torch

from src.models.evaluate import RESULTS, evaluate_run
from src.models.features import build_panel

MODEL = "amazon/chronos-2"
CONTEXT = 260
HORIZONS = (4, 12)
PAST = ["rain", "ETP", "PE", "DRAINC", "pump_gw", "canal"]
RIVER_PAST = ["river_tet", "river_agly", "river_tech", "river_near"]   # panels from v3
FUTURE = ["season_sin", "season_cos"]
RUNS = {"zeroshot": "chronos2", "xl": "chronos2_xl", "ft": "chronos2_ft"}


def past_cols(P):
    return PAST + [c for c in RIVER_PAST if c in P.columns]


def task_input(g, i, H, past):
    """Predict-format dict for issue row i of one well (g: that well's panel rows)."""
    sl = slice(i - CONTEXT + 1, i + 1)
    fut = slice(i + 1, i + 1 + H)
    ff = {c: g[c].to_numpy(np.float32)[fut] for c in FUTURE}
    if len(ff[FUTURE[0]]) < H:  # end of record: extend the calendar
        k = H - len(ff[FUTURE[0]])
        extra = pd.date_range(g["week"].iloc[-1] + pd.Timedelta(days=7), periods=k, freq="7D")
        doy = extra.dayofyear / 365.25 * 2 * np.pi
        ff = {"season_sin": np.r_[ff["season_sin"], np.sin(doy)].astype(np.float32),
              "season_cos": np.r_[ff["season_cos"], np.cos(doy)].astype(np.float32)}
    return {"target": g["z"].to_numpy(np.float32)[sl],
            "past_covariates": {c: g[c].to_numpy(np.float32)[sl] for c in past + FUTURE},
            "future_covariates": ff}


def rows_from(code, g, issues, means):
    rows = []
    for i, m in zip(issues, means):
        m = m.numpy().reshape(-1)
        for h in HORIZONS:
            j = i + h
            if j < len(g):
                rows.append({"code_bss": code, "week": g.loc[j, "week"], "horizon": h,
                             "pred": g.loc[j, "mu"] + g.loc[j, "sd"] * m[h - 1]})
    return rows


def finetune(pipe, P, past, out, steps=1000):
    """Fine-tune on each well's training series; validation series for model selection."""
    def series(end):
        items = []
        for _, g in P[P["week"] <= end].groupby("code_bss"):
            if g["z"].notna().sum() < 104:
                continue
            items.append({"target": g["z"].to_numpy(np.float32),
                          "past_covariates": {c: g[c].to_numpy(np.float32) for c in past + FUTURE},
                          "future_covariates": {c: None for c in FUTURE}})
        return items
    train_end = P.loc[P["split"] == "train", "week"].max()
    val_end = P.loc[P["split"] == "validation", "week"].max()
    return pipe.fit(series(train_end), prediction_length=max(HORIZONS),
                    validation_inputs=series(val_end), batch_size=64, num_steps=steps,
                    output_dir=str(out / "ckpt"))


def main():
    from chronos import Chronos2Pipeline

    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=list(RUNS), default="zeroshot")
    ap.add_argument("--wells", type=int, default=0, help="first N wells only (smoke tests)")
    ap.add_argument("--ft-steps", type=int, default=1000)
    args = ap.parse_args()
    run = RUNS[args.mode]
    torch.set_num_threads(4)
    device = "cuda" if torch.cuda.is_available() else "cpu"  # GPU when present
    print(f"Chronos-2 ({args.mode}) on {device}", flush=True)
    pipe = Chronos2Pipeline.from_pretrained(MODEL, device_map=device)
    P = build_panel()
    P = P[P["mu"].notna()].sort_values(["code_bss", "week"])
    if args.wells:
        P = P[P["code_bss"].isin(P["code_bss"].unique()[:args.wells])]
    past = past_cols(P)
    out = RESULTS / run / "wells"
    out.mkdir(parents=True, exist_ok=True)
    H = max(HORIZONS)
    if args.mode == "ft" and not any(out.glob("*.parquet")):
        pipe = finetune(pipe, P, past, RESULTS / run, args.ft_steps)
    groups = {code: g.reset_index(drop=True) for code, g in P.groupby("code_bss")}
    if args.mode == "xl":
        done = out / "all_wells.parquet"
        if not done.exists():
            rows = []
            ref = next(iter(groups.values()))
            issue_idx = [i for i in ref.index[ref["split"].isin(["validation", "test"])]
                         if i >= CONTEXT]
            for n, i in enumerate(issue_idx):
                codes = [c for c, g in groups.items() if i < len(g)]
                inputs = [task_input(groups[c], i, H, past) for c in codes]
                _, mean = pipe.predict_quantiles(inputs, prediction_length=H,
                                                 batch_size=len(inputs), cross_learning=True)
                for c, m in zip(codes, mean):
                    rows += rows_from(c, groups[c], [i], [m])
                if n % 50 == 0:
                    print(f"  issue week {n + 1}/{len(issue_idx)}", flush=True)
            pd.DataFrame(rows).assign(task="forecast").to_parquet(done, index=False)
    else:
        for code, g in groups.items():
            path = out / f"{code.replace('/', '_')}.parquet"
            if path.exists():
                continue
            issues = [i for i in g.index[g["split"].isin(["validation", "test"])] if i >= CONTEXT]
            if not issues:
                continue
            inputs = [task_input(g, i, H, past) for i in issues]
            _, mean = pipe.predict_quantiles(inputs, prediction_length=H, batch_size=64)
            pd.DataFrame(rows_from(code, g, issues, mean)).assign(task="forecast").to_parquet(
                path, index=False)
            print(f"  {code}: {len(issues)} issue weeks", flush=True)
    preds = pd.concat([pd.read_parquet(f) for f in sorted(out.glob("*.parquet"))])
    preds.to_parquet(RESULTS / run / "predictions.parquet", index=False)
    s = evaluate_run(run)
    c = s[(s["group"] == "all core") & (s["variant"] == "all")]
    print(c[["task", "horizon", "split", "n_wells", "NSE", "skill", "KGE", "RMSE"]].round(3)
          .to_string(index=False))


if __name__ == "__main__":
    main()
