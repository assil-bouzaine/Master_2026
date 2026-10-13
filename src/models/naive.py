"""Naive baselines: the floor every model must beat.

    python -m src.models.naive

Simulation task (no observed heads used at prediction time):
    climatology      mean head of the well for that week of the year, from the
                     training weeks only (circularly smoothed over 5 weeks)
Forecast task, horizons H weeks (observed heads known up to week - h):
    persistence      last observed head at or before week - h (within 26 weeks)
    anomaly_persist  climatology(week) + [obs - climatology] at week - h

Outputs: results/naive_<name>/predictions.parquet (+ metrics via evaluate).
"""
import json

import numpy as np
import pandas as pd

from src.models.evaluate import DS, RESULTS, evaluate_run

HORIZONS = (4, 12)


def climatology(heads, train_end):
    tr = heads[heads["week"] <= train_end].copy()
    tr["woy"] = tr["week"].dt.isocalendar().week.clip(upper=52).astype(int)
    c = tr.groupby(["code_bss", "woy"])["head"].mean().unstack()
    c = c.reindex(columns=range(1, 53))
    c = c.T.interpolate(limit_direction="both").T  # weeks never observed in training
    sm = pd.concat([c.iloc[:, -2:], c, c.iloc[:, :2]], axis=1).T.rolling(5, center=True).mean().T
    return sm.iloc[:, 2:-2].set_axis(range(1, 53), axis=1)


def main():
    splits = json.loads((DS / "splits.json").read_text())
    heads = pd.read_parquet(DS / "heads_weekly.parquet")
    heads = heads[heads["week"] >= splits["model_start"]]
    clim = climatology(heads, splits["train"][1])

    weeks = pd.date_range(splits["model_start"], heads["week"].max(), freq=splits["week_rule"])
    woy = pd.Series(weeks.isocalendar().week.clip(upper=52).astype(int).values, index=weeks)
    grid = heads.pivot(index="week", columns="code_bss", values="head").reindex(weeks)
    codes = [c for c in grid.columns if c in clim.index]
    clim_grid = pd.DataFrame({c: clim.loc[c, woy.values].values for c in codes}, index=weeks)

    def long(df, task, h):
        out = df.stack().rename("pred").reset_index()
        out.columns = ["week", "code_bss", "pred"]
        return out.assign(task=task, horizon=h)

    runs = {"naive_climatology": [long(clim_grid, "simulation", 0)]}
    runs["naive_persistence"], runs["naive_anomaly_persist"] = [], []
    last = grid[codes].ffill(limit=26)
    anom = (grid[codes] - clim_grid).ffill(limit=26)
    for h in HORIZONS:
        runs["naive_persistence"].append(long(last.shift(h), "forecast", h))
        runs["naive_anomaly_persist"].append(long(clim_grid + anom.shift(h), "forecast", h))

    for run_id, parts in runs.items():
        out = RESULTS / run_id
        out.mkdir(parents=True, exist_ok=True)
        pd.concat(parts, ignore_index=True).dropna().to_parquet(out / "predictions.parquet",
                                                                index=False)
        s = evaluate_run(run_id)
        core = s[(s["group"] == "all core") & (s["variant"] == "all")]
        print(f"== {run_id}")
        print(core[["task", "horizon", "split", "n_wells", "NSE", "KGE", "RMSE"]]
              .round(3).to_string(index=False))


if __name__ == "__main__":
    main()
