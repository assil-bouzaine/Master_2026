"""Chronos-2 zero-shot baseline (forecast task, horizons 4 and 12 weeks).

    python -m src.models.chronos2            # resumable per well

Ansari et al. 2025, Chronos-2: From Univariate to Universal Forecasting,
arXiv:2510.15821. A pretrained time-series foundation model, used without
any training on our data ("zero-shot").

Rolling origin: for every issue week t0 in the validation and test splits,
the model sees the well's z-scored head up to t0 (last CONTEXT weeks, gaps as
NaN) with past covariates (rain, ETP, effective rain, drainage, local
pumping, canal volume) and the calendar (season) as a known future
covariate; it predicts the next 12 weeks. Future weather is treated as
unknown (operational setting). Weights: Hugging Face "amazon/chronos-2".
"""
import numpy as np
import pandas as pd
import torch

from src.models.evaluate import RESULTS, evaluate_run
from src.models.features import build_panel

RUN = "chronos2"
MODEL = "amazon/chronos-2"
CONTEXT = 260
HORIZONS = (4, 12)
PAST = ["rain", "ETP", "PE", "DRAINC", "pump_gw", "canal"]
FUTURE = ["season_sin", "season_cos"]


def main():
    from chronos import Chronos2Pipeline

    torch.set_num_threads(4)
    device = "cuda" if torch.cuda.is_available() else "cpu"  # GPU when present
    print(f"Chronos-2 on {device}", flush=True)
    pipe = Chronos2Pipeline.from_pretrained(MODEL, device_map=device)
    P = build_panel()
    P = P[P["mu"].notna()].sort_values(["code_bss", "week"])
    out = RESULTS / RUN / "wells"
    out.mkdir(parents=True, exist_ok=True)
    H = max(HORIZONS)
    for code, g in P.groupby("code_bss"):
        path = out / f"{code.replace('/', '_')}.parquet"
        if path.exists():
            continue
        g = g.reset_index(drop=True)
        z = g["z"].to_numpy(np.float32)
        issues = [i for i in g.index[g["split"].isin(["validation", "test"])] if i >= CONTEXT]
        if not issues:
            continue
        inputs = []
        for i in issues:
            sl = slice(i - CONTEXT + 1, i + 1)
            fut = slice(i + 1, i + 1 + H)
            ff = {c: g[c].to_numpy(np.float32)[fut] for c in FUTURE}
            if len(ff[FUTURE[0]]) < H:  # end of record: pad the calendar
                k = H - len(ff[FUTURE[0]])
                last = g["week"].iloc[-1]
                extra = pd.date_range(last + pd.Timedelta(days=7), periods=k, freq="7D")
                doy = extra.dayofyear / 365.25 * 2 * np.pi
                ff = {"season_sin": np.r_[ff["season_sin"], np.sin(doy)].astype(np.float32),
                      "season_cos": np.r_[ff["season_cos"], np.cos(doy)].astype(np.float32)}
            inputs.append({"target": z[sl],
                           "past_covariates": {c: g[c].to_numpy(np.float32)[sl]
                                               for c in PAST + FUTURE},
                           "future_covariates": ff})
        _, mean = pipe.predict_quantiles(inputs, prediction_length=H, batch_size=64)
        rows = []
        for i, m in zip(issues, mean):
            m = m.numpy().reshape(-1)
            for h in HORIZONS:
                j = i + h
                if j < len(g):
                    rows.append({"code_bss": code, "week": g.loc[j, "week"], "horizon": h,
                                 "pred": g.loc[j, "mu"] + g.loc[j, "sd"] * m[h - 1]})
        pd.DataFrame(rows).assign(task="forecast").to_parquet(path, index=False)
        print(f"  {code}: {len(issues)} issue weeks", flush=True)
    preds = pd.concat([pd.read_parquet(f) for f in sorted(out.glob("*.parquet"))])
    preds.to_parquet(RESULTS / RUN / "predictions.parquet", index=False)
    s = evaluate_run(RUN)
    c = s[(s["group"] == "all core") & (s["variant"] == "all")]
    print(c[["task", "horizon", "split", "n_wells", "NSE", "KGE", "RMSE"]].round(3)
          .to_string(index=False))


if __name__ == "__main__":
    main()
