"""Pastas baseline: transfer-function noise models, one per well (simulation task).

    python -m src.models.pastas_baseline              # both variants, resumable
    python -m src.models.pastas_baseline --variant pastas

Collenteur et al. 2019, Pastas, Groundwater 57(6), doi:10.1111/gwat.12925.

Each well's weekly head is explained as the sum of responses to stresses:
- recharge: daily rain and ETP of the well's SAFRAN cell, linear recharge
  (rain - f * ETP), Gamma response function
- pumping: weekly groundwater abstraction within 3 km of the well (BNPE,
  spread as in dataset_v1), Hantush response, gain forced negative
- variant "pastas_canal" adds the plain-wide surface-water irrigation and
  canal-intake volume as a stress with a positive gain: a direct test of the
  canal-return-recharge hypothesis (does it improve the fit, and where?)
- variants "*_seasonal" test the flat drinking-water assumption of dataset_v1:
  drinking-water volumes are re-spread as 50 % flat + 50 % following the
  weekly April-October climatic deficit (summer peak). The annual totals are
  unchanged; only the timing within the year moves. A first run showed the
  flat profile makes Pastas borrow evaporation (f at its bound) to fake the
  summer drawdown of the Pliocene.
- variant "pastas_regional" = seasonal + canal + the plain-wide groundwater
  abstraction as an extra stress: tests whether a well feels pumping beyond
  3 km (regional drawdown of the confined Pliocene). If it helps, local
  radius features are not enough, which is the argument for a graph.

Calibration on the training period (2012-2019) with an AR(1) noise model and
warm-up from 2005; the deterministic simulation (no noise model, no observed
heads) is then run to the end of the record. Pumping before 2012 (no BNPE)
is held at its 2012-2014 mean so the model does not see a fake step.

Outputs (results/<variant>/):
    wells/<code>.parquet       weekly simulation per well (resumable cache)
    params.csv                 fitted parameters and fit statistics per well
    predictions.parquet        all wells, evaluate format
"""
import argparse
import json
import warnings
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from src.config import RAW
from src.dataset.load import _pumping_near_wells
from src.models.evaluate import DS, RESULTS, evaluate_run

MIN_TRAIN_WEEKS = 52
VARIANTS = ("pastas", "pastas_canal", "pastas_seasonal", "pastas_seasonal_canal",
            "pastas_regional")
SEASONAL_SHARE = 0.5


def daily_forcing():
    files = sorted((RAW / "safran").glob("sim2_66_[0-9]*.parquet"))
    d = pd.concat([pd.read_parquet(f, columns=["LAMBX", "LAMBY", "date", "PRELIQ", "PRENEI", "ETP"])
                   for f in files], ignore_index=True)
    d["cell_id"] = d["LAMBX"].astype(str) + "_" + d["LAMBY"].astype(str)
    d["prec"] = (d["PRELIQ"] + d["PRENEI"]) / 1000.0   # mm/d -> m/d
    d["evap"] = d["ETP"] / 1000.0
    return d.set_index(["cell_id", "date"])[["prec", "evap"]].sort_index()


def weekly_to_daily(w, start, end):
    """Weekly volumes (m3/week, indexed by week end) -> daily m3/d over [start, end]."""
    days = pd.date_range(start, end, freq="D")
    daily = (w / 7.0).reindex(days, method="bfill")
    first = w.index.min()
    base = w[w.index < first + pd.Timedelta(days=3 * 365)].mean() / 7.0
    daily[daily.index < first - pd.Timedelta(days=6)] = base
    return daily.fillna(base)


def build_model(code, variant, obs, prec, evap, pump, canal, simple, regional=None):
    import pastas as ps

    ml = ps.Model(obs, name=code)
    ml.add_stressmodel(ps.RechargeModel(prec, evap, rfunc=ps.Exponential() if simple else ps.Gamma(),
                                        name="recharge", recharge=ps.rch.Linear()))
    if pump is not None and pump.sum() > 0:
        ml.add_stressmodel(ps.StressModel(pump, rfunc=ps.Exponential() if simple else ps.Hantush(),
                                          name="pumping", up=False, settings="well"))
    if variant.endswith("canal") or variant == "pastas_regional":
        ml.add_stressmodel(ps.StressModel(canal, rfunc=ps.Exponential(), name="canal", up=True,
                                          settings="well"))
    if regional is not None:
        ml.add_stressmodel(ps.StressModel(regional, rfunc=ps.Exponential() if simple else ps.Hantush(),
                                          name="regional", up=False, settings="well"))
    ml.add_noisemodel(ps.ArNoiseModel())
    return ml


def fit_well(args):
    """Fit one well; fall back to simpler response functions if the solver fails."""
    code, variant, obs, prec, evap, pump, canal, splits, end, regional = args
    import pastas as ps

    ps.set_log_level("ERROR")
    warnings.filterwarnings("ignore")
    tmin, tmax = splits["model_start"], splits["train"][1]
    errors = []
    for simple in (False, True):
        try:
            ml = build_model(code, variant, obs, prec, evap, pump, canal, simple, regional)
            ml.solve(tmin=tmin, tmax=tmax, report=False)
            break
        except Exception as e:  # noqa: BLE001 - record and try the simpler model
            errors.append(f"{'simple' if simple else 'full'}: {e}")
    else:
        return code, None, {"code_bss": code, "variant": variant, "error": " | ".join(errors)}
    sim = ml.simulate(tmin=tmin, tmax=end)
    weekly = sim.resample(splits["week_rule"]).mean()
    p = ml.parameters["optimal"].to_dict()
    stats = {"code_bss": code, "variant": variant, "simple_rfuncs": simple,
             "n_train_weeks": int(obs[tmin:tmax].notna().sum()),
             "fit_rsq": ml.stats.rsq(tmin=tmin, tmax=tmax),
             "has_pumping": "pumping" in ml.stressmodels, "error": " | ".join(errors)}
    stats.update({f"p_{k}": v for k, v in p.items()})
    return code, weekly, stats


def seasonal_drinking_water(pw, pts):
    """Re-spread drinking-water volumes: SEASONAL_SHARE follows the Apr-Oct deficit."""
    f = pd.read_parquet(DS / "forcing_weekly.parquet", columns=["cell_id", "week", "ETP", "rain"])
    f["year"] = f["week"].dt.year
    f["deficit"] = (f["ETP"] - f["rain"]).clip(lower=0)
    f.loc[~f["week"].dt.month.between(4, 10), "deficit"] = 0.0
    tot = f.groupby(["cell_id", "year"])["deficit"].transform("sum")
    f["w"] = f["deficit"] / tot
    d = pw.merge(pts[["code_ouvrage", "cell_id"]], on="code_ouvrage")
    dw = d["usage"] == "drinking water"
    d["year"] = d["week"].dt.year
    annual = d[dw].groupby(["code_ouvrage", "year"])["volume_m3"].transform("sum")
    d = d.merge(f[["cell_id", "week", "w"]], on=["cell_id", "week"], how="left")
    flat = d.loc[dw, "volume_m3"]
    d.loc[dw, "volume_m3"] = ((1 - SEASONAL_SHARE) * flat
                              + SEASONAL_SHARE * annual * d.loc[dw, "w"].fillna(0))
    return d[pw.columns]


def run_variant(variant, wells, heads, forcing, pump_near, canal, splits, end, workers,
                regional=None):
    out = RESULTS / variant
    (out / "wells").mkdir(parents=True, exist_ok=True)
    jobs, cached_stats = [], []
    for _, w in wells.iterrows():
        code = w["code_bss"]
        cache = out / "wells" / f"{code.replace('/', '_')}.parquet"
        if cache.exists():
            continue
        obs = heads.loc[heads["code_bss"] == code].set_index("week")["head"]
        if obs[splits["model_start"]:splits["train"][1]].notna().sum() < MIN_TRAIN_WEEKS:
            continue
        f = forcing.loc[w["cell_id"]]
        pump = None
        if code in pump_near.index.get_level_values(0):
            gcols = [c for c in pump_near.columns if c.startswith("pump_gr_")]
            pw = pump_near.loc[code][gcols].sum(axis=1)
            pump = weekly_to_daily(pw, f.index.min(), f.index.max())
        jobs.append((code, variant, obs, f["prec"], f["evap"], pump, canal, splits, end,
                     regional if variant == "pastas_regional" else None))
    print(f"[{variant}] {len(jobs)} wells to fit ({len(wells)} in dataset)", flush=True)
    stats_path = out / "params_partial.jsonl"
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for code, weekly, stats in ex.map(fit_well, jobs):
            with open(stats_path, "a") as fh:
                fh.write(json.dumps(stats, default=float) + "\n")
            if weekly is None:
                print(f"  {code}: FAILED ({stats['error'][:120]})", flush=True)
                continue
            weekly.rename("pred").rename_axis("week").reset_index().assign(
                code_bss=code, task="simulation", horizon=0).to_parquet(
                out / "wells" / f"{code.replace('/', '_')}.parquet", index=False)
            print(f"  {code}: R² train {stats['fit_rsq']:.2f}", flush=True)
    preds = pd.concat([pd.read_parquet(f) for f in sorted((out / "wells").glob("*.parquet"))],
                      ignore_index=True)
    preds.to_parquet(out / "predictions.parquet", index=False)
    if stats_path.exists():
        params = pd.read_json(stats_path, lines=True).drop_duplicates("code_bss", keep="last")
        params.to_csv(out / "params.csv", index=False)
    return evaluate_run(variant)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=VARIANTS, nargs="*", default=list(VARIANTS))
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    splits = json.loads((DS / "splits.json").read_text())
    wells = pd.read_parquet(DS / "wells.parquet")
    heads = pd.read_parquet(DS / "heads_weekly.parquet")
    forcing = daily_forcing()
    end = str(heads["week"].max().date())
    pw = pd.read_parquet(DS / "pumping_weekly.parquet")
    pts = pd.read_parquet(DS / "pumping_points.parquet")
    pump_flat = _pumping_near_wells(wells).fillna(0.0)
    pump_seasonal = _pumping_near_wells(wells, seasonal_drinking_water(pw, pts)).fillna(0.0)
    surf = pw.merge(pts[["code_ouvrage", "source"]], on="code_ouvrage")
    surf = surf[(surf["source"] == "surface") & surf["usage"].isin(["irrigation", "canals"])]
    canal_w = surf.groupby("week")["volume_m3"].sum()
    canal = weekly_to_daily(canal_w / 1e6, forcing.index.get_level_values("date").min(),  # Mm3/d
                            forcing.index.get_level_values("date").max())

    sp = seasonal_drinking_water(pw, pts).merge(pts[["code_ouvrage", "source"]], on="code_ouvrage")
    gw_w = sp[sp["source"] == "groundwater"].groupby("week")["volume_m3"].sum()
    regional = weekly_to_daily(gw_w / 1e6, forcing.index.get_level_values("date").min(),  # Mm3/d
                               forcing.index.get_level_values("date").max())
    for v in args.variant:
        pump_near = pump_seasonal if ("seasonal" in v or v == "pastas_regional") else pump_flat
        s = run_variant(v, wells, heads, forcing, pump_near, canal, splits, end, args.workers,
                        regional)
        core = s[(s["group"] == "all core") & (s["variant"] == "all")]
        print(f"== {v}\n" + core[["split", "n_wells", "NSE", "KGE", "RMSE"]].round(3)
              .to_string(index=False))
        groups = s[(s["group"] != "all core") & (s["variant"] == "all") & (s["split"] == "test")]
        print(groups[["group", "n_wells", "NSE", "RMSE"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
