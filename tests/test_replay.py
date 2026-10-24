"""Inference replay of the Pastas reference: params.csv reproduces the stored predictions.

    PFE_DATASET=v4 python -m tests.test_replay [run]      # default: pastas_seasonal_canal

Third review (docs/review_codex_2026-10-24.md §7): "a small cold rebuild and inference-replay
check is more valuable than a large set of superficial unit tests". A Pastas run keeps no
model file, but params.csv holds every fitted parameter: rebuilding each model with the code
of src.models.pastas_baseline (nothing is solved) and simulating with those parameters must
give the stored weekly predictions. This is what lets the frozen reference be extended to
weeks observed after the freeze (docs/analysis_plan.md §11). Checked on three core wells
chosen by rule (first, middle and last fitted core well by code), to 1e-6 m.
"""
import json
import sys

import numpy as np
import pandas as pd

from src.dataset.load import _pumping_near_wells
from src.dataset.pumping import canal_series, seasonal_drinking_water
from src.models.evaluate import DS, RESULTS
from src.models.pastas_baseline import build_model, daily_forcing, weekly_to_daily

TOL_M = 1e-6


def main(run="pastas_seasonal_canal"):
    variant = run.split("_trainobs")[0].split("_start")[0]
    assert variant in ("pastas_seasonal_canal", "pastas_canal", "pastas_seasonal", "pastas"), \
        f"replay covers the single-stress variants, not {variant}"
    params = pd.read_csv(RESULTS / run / "params.csv").set_index("code_bss")
    preds = pd.read_parquet(RESULTS / run / "predictions.parquet")
    splits = json.loads((DS / "splits.json").read_text())
    wells = pd.read_parquet(DS / "wells.parquet").set_index("code_bss")
    heads = pd.read_parquet(DS / "heads_weekly.parquet")
    end = str(heads["week"].max().date())
    fitted = sorted(c for c in params.index if wells.loc[c, "core"] and pd.isna(params.loc[c, "error"]))
    picks = [fitted[0], fitted[len(fitted) // 2], fitted[-1]]

    forcing = daily_forcing()
    pw = pd.read_parquet(DS / "pumping_weekly.parquet")
    pts = pd.read_parquet(DS / "pumping_points.parquet")
    seasonal = "seasonal" in variant
    pump_near = _pumping_near_wells(wells.reset_index(), seasonal_drinking_water(pw, pts)
                                    if seasonal else None).fillna(0.0)
    days = forcing.index.get_level_values("date")
    canal = weekly_to_daily(canal_series(pw, pts) / 1e6, days.min(), days.max())
    gcols = [c for c in pump_near.columns if c.startswith("pump_gr_")]
    for code in picks:
        obs = heads.loc[heads["code_bss"] == code].set_index("week")["head"]
        if "_trainobs" in run:
            obs = obs[:splits["train"][1]]
        f = forcing.loc[wells.loc[code, "cell_id"]]
        pump = (weekly_to_daily(pump_near.loc[code][gcols].sum(axis=1), f.index.min(), f.index.max())
                if code in pump_near.index.get_level_values(0) else None)
        ml = build_model(code, variant, obs, f["prec"], f["evap"], pump, canal,
                         bool(params.loc[code, "simple_rfuncs"]))
        p = np.array([params.loc[code, f"p_{n}"] for n in ml.parameters.index], dtype=float)
        assert not np.isnan(p).any(), f"{code}: a parameter of the rebuilt model is not stored"
        sim = ml.simulate(p=p, tmin=splits["model_start"], tmax=end)
        weekly = sim.resample(splits["week_rule"]).mean()
        stored = preds[preds["code_bss"] == code].set_index("week")["pred"]
        j = pd.concat([weekly.rename("replay"), stored.rename("stored")], axis=1, join="inner")
        gap = float((j["replay"] - j["stored"]).abs().max())
        assert len(j) == len(stored) and gap < TOL_M, f"{code}: replay differs by {gap:.2e} m"
        print(f"  {code}: {len(j)} weeks replayed from params.csv, max |difference| {gap:.1e} m")
    print(f"test_replay ({run}): all checks passed")


if __name__ == "__main__":
    main(*sys.argv[1:])
