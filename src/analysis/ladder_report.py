"""Report of the model ladder (analysis plan §14 item 18): scores and stability across starts.

    PFE_DATASET=v4 python -m src.analysis.ladder_report     # -> docs/results_ladder_<v>.md

For every response-superposition run present in results/<v>/ (src/models/response.py) and, beside
them, the Pastas multistart of the reference:
1. scores of the mean prediction over the starts, and of the single starts (core wells);
2. stability across starts, the measures fixed before the first run:
   - per core well, the range of the drought NSE over the starts (median over wells);
   - per parameter, (max - min) / |median| over the starts (median over wells);
   - per stress, the sd over the starts of the mean contribution in the drought phase, in units of
     the well's training sd (median over wells), with the size of that mean contribution;
3. contrasts with the primary effect measure of item 18, log(RMSE_a / RMSE_b) per well in the
   drought phase (negative: a better), against the hydrology reference and the tuned LSTM;
4. the same-arm band: the same statistic between random disjoint halves of one run's starts.
The pooled run is chosen on validation only. Exploratory (development benchmark), like every
baseline result (analysis plan §11).
"""
import json

import numpy as np
import pandas as pd

from src.analysis import stats
from src.config import DATASET, ROOT, TEST_PERIODS
from src.dataset.placeholders import load_mask
from src.models.evaluate import DS, MIN_WEEKS, RESULTS, score

RUNS = {"resp_free": "free (per-well parameters)",
        "resp_pooled_l001": "pooled, λ = 0.01", "resp_pooled_l01": "pooled, λ = 0.1",
        "resp_pooled_l1": "pooled, λ = 1", "resp_pooled_l10": "pooled, λ = 10",
        "resp_shared": "shared (one response per aquifer group)",
        "resp_free_a104": "free, time scale up to 104 weeks (sensitivity)",
        "resp_free_pe": "free, SIM2 effective rainfall as recharge (sensitivity)",
        "resp_free_split": "free, permanent + seasonal pumping (sensitivity)",
        "resp_pooled_split": "pooled λ = 0.01, permanent + seasonal pumping (sensitivity)",
        "resp_free_conv": "free, 3,000 steps without early stopping (diagnostic)",
        "resp_pooled_l01_conv": "pooled λ = 0.1, 3,000 steps without early stopping (diagnostic)",
        "resp_pooled_sd_l001": "pooled λ = 0.01, gains in units of the well's sd",
        "resp_pooled_sd_l01": "pooled λ = 0.1, gains in units of the well's sd",
        "resp_pooled_sd_l1": "pooled λ = 1, gains in units of the well's sd",
        "resp_shared_sd": "shared, gains in units of the well's sd"}
GRID = ("resp_pooled_l001", "resp_pooled_l01", "resp_pooled_l1", "resp_pooled_l10")   # the pooled choice
FIRST = ("resp_free", *GRID, "resp_shared", "resp_free_a104", "resp_free_pe")           # runs fixed in advance
# Caballero & Ladouche 2015 (doi:10.5194/hessd-12-10109-2015), Table 1: mean transit time of the
# recharge response (days) at two of our core wells; maximum response to seasonal pumping 75 days
# after pumping starts (analysis plan §14 item 18, comparator fixed before any result was read)
BRGM = {"10908X0263/FIGUER": ("Perpignan", 89), "10972X0137/PONT": ("Argelès", 220)}
BRGM_PUMP_DAYS = 75
REFERENCE = "pastas_seasonal_canal_trainobs_beststart"
PASTAS_STARTS = [f"pastas_seasonal_canal_trainobs_start{k}" for k in range(10)]
COMPARE = {REFERENCE: "Pastas reference", "lstm_tuned": "LSTM tuned (5 seeds)"}
N_BAND = 200


def per_well(m, split="test_drought", metric="NSE"):
    s = m[(m["task"] == "simulation") & (m["split"] == split) & (m["variant"] == "all") & m["core"]]
    return s.set_index("code_bss")[metric]


def medians(m):
    return {f"{metric} {name}": per_well(m, split, metric).median()
            for split, name in (("validation", "val"), ("test_drought", "drought"))
            for metric in ("NSE", "skill", "RMSE")}


def seed_frames(run):
    """{seed: prediction frame in metres} of a response run."""
    P = pd.read_parquet(RESULTS / "_cache" / "panel.parquet", columns=["code_bss", "week", "mu", "sd"])
    out = {}
    for f in sorted((RESULTS / run).glob("seed_*.parquet")):
        z = pd.read_parquet(f).merge(P, on=["code_bss", "week"])
        out[int(f.stem.split("_")[1])] = pd.DataFrame(
            {"code_bss": z["code_bss"], "week": z["week"], "pred": z["mu"] + z["sd"] * z["z"],
             "task": "simulation", "horizon": 0}).dropna(subset=["pred"])
    return out


def drought_support():
    """Observed heads of the core wells on the scored drought weeks: wide table (week x well)."""
    heads = pd.read_parquet(DS / "heads_weekly.parquet", columns=["code_bss", "week", "head"])
    wells = pd.read_parquet(DS / "wells.parquet")
    a, b = TEST_PERIODS["test_drought"]
    h = heads[(heads["week"] >= a) & (heads["week"] <= b) & heads["head"].notna()
              & heads["code_bss"].isin(wells.loc[wells["core"], "code_bss"])]
    mask = load_mask()
    if mask is not None:
        flagged = pd.MultiIndex.from_frame(h[["code_bss", "week"]]).isin(
            pd.MultiIndex.from_frame(mask[["code_bss", "week"]]))
        h = h[~flagged]
    obs = h.pivot(index="week", columns="code_bss", values="head")
    return obs.loc[:, obs.notna().sum() >= MIN_WEEKS]


def band(frames, obs, wells, rng):
    """Same-arm band: median over wells of log(RMSE_A / RMSE_B) between the mean predictions of two
    random disjoint halves of the starts; N_BAND draws. Returns (2.5 %, 97.5 %, max |.|)."""
    seeds = sorted(frames)
    if len(seeds) < 4:
        return (np.nan, np.nan, np.nan)
    wide = np.stack([frames[s].pivot(index="week", columns="code_bss", values="pred")
                     .reindex(index=obs.index, columns=obs.columns).to_numpy() for s in seeds])
    o, half, vals = obs.to_numpy(), len(seeds) // 2, []
    for _ in range(N_BAND):
        perm = rng.permutation(len(seeds))
        ra, rb = (np.sqrt(np.nanmean((wide[perm[i * half:(i + 1) * half]].mean(0) - o) ** 2, axis=0))
                  for i in (0, 1))
        vals.append(np.nanmedian(np.log(ra / rb)))
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return lo, hi, float(np.max(np.abs(vals)))


def spread(table):
    """(max - min) / |median| over the starts, per well (rows = wells, columns = starts)."""
    return (table.max(1) - table.min(1)) / table.median(1).abs().clip(lower=1e-12)


def response_stability(run, core, sd_train):
    out = {}
    params = {int(f.stem.split("_")[-1]): pd.read_csv(f).set_index("code_bss")
              for f in sorted((RESULTS / run).glob("params_seed_*.csv"))}
    if len(params) > 1:
        for col in next(iter(params.values())).columns:
            if col.startswith(("gain_", "a_", "n_")) or col == "f":
                t = pd.DataFrame({s: p[col] for s, p in params.items()}).loc[core]
                out[f"spread {col}"] = spread(t).median()
    a, b = TEST_PERIODS["test_drought"]
    means = {}
    for f in sorted((RESULTS / run).glob("contrib_seed_*.parquet")):
        c = pd.read_parquet(f)
        c = c[(c["week"] >= a) & (c["week"] <= b) & c["code_bss"].isin(core)]
        names = [k for k in c.columns if k not in ("code_bss", "week")]
        means[int(f.stem.split("_")[-1])] = c.groupby("code_bss")[names].mean()
    if len(means) > 1:
        for s in names:
            t = pd.DataFrame({k: v[s] for k, v in means.items()}).div(sd_train, axis=0)
            out[f"contribution {s}: size"] = t.mean(1).abs().median()
            out[f"contribution {s}: sd over starts"] = t.std(1).median()
            out[f"contribution {s}: wells with sd < half the size"] = float(
                (t.std(1) < 0.5 * t.mean(1).abs()).mean())
    return out


def comparator(run):
    """Per BRGM well: learned mean lag of the recharge response and lag of the largest weight of
    the (seasonal) pumping response, in days: median [min, max] over the starts."""
    rows = []
    params = [pd.read_csv(f).set_index("code_bss") for f in sorted((RESULTS / run).glob("params_seed_*.csv"))]
    pump = "pumping_seasonal" if "a_pumping_seasonal_wk" in params[0] else "pumping"
    q = lambda v: (float(np.median(v)), float(np.min(v)), float(np.max(v)))  # noqa: E731
    for code, (place, tm) in BRGM.items():
        if code not in params[0].index:
            continue
        lag = [7 * p.loc[code, "mean_lag_recharge_wk"] for p in params]
        peak = [7 * max((p.loc[code, f"n_{pump}"] - 1) * p.loc[code, f"a_{pump}_wk"], 0.0) for p in params]
        rows.append((f"{RUNS[run]}, {place}", {"recharge mean lag, days": q(lag), "BRGM mean transit, days": tm,
                                               "pumping peak lag, days": q(peak), "BRGM, days": BRGM_PUMP_DAYS}))
    return rows


def nse_range(per_start):
    """per_start: {start: per-well drought NSE}. Median over wells of (max - min), and the
    mean and sd over starts of the median NSE."""
    t = pd.DataFrame(per_start)
    return {"per-well drought NSE range over starts (median)": (t.max(1) - t.min(1)).median(),
            "single start, drought NSE: mean": t.median(0).mean(),
            "single start, drought NSE: sd": t.median(0).std(), "starts": t.shape[1]}


def contrast(ma, mb, wells):
    """a against b, log RMSE ratio per well in the drought (negative: a better)."""
    f = lambda m: m.assign(neg_log_rmse=-np.log(m["RMSE"]))  # noqa: E731
    r = stats.paired(f(ma), f(mb), wells, split="test_drought", metric="neg_log_rmse")
    return {"median log(RMSE a / RMSE b)": -r["median_diff"], "interval": (-r["ci_hi"], -r["ci_lo"]),
            "share of wells a better": r["share_a_better"], "p_cluster": r["p_cluster"],
            "support mismatch": r["support_mismatch"]}


def fmt(v, nd=2):
    if isinstance(v, tuple) and len(v) == 3:
        return f"{fmt(v[0], nd)} [{fmt(v[1], nd)}, {fmt(v[2], nd)}]"
    if isinstance(v, tuple):
        return "[" + ", ".join(fmt(x, nd) for x in v) + "]"
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    return "—" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v:.{nd}f}"


def table(rows, cols, nd=2):
    head = "| run | " + " | ".join(cols) + " |\n|---|" + "---:|" * len(cols) + "\n"
    return head + "".join(f"| {name} | " + " | ".join(fmt(r.get(c, np.nan), nd) for c in cols) + " |\n"
                          for name, r in rows)


def main():
    wells = pd.read_parquet(DS / "wells.parquet")
    core = list(wells.loc[wells["core"], "code_bss"])
    P = pd.read_parquet(RESULTS / "_cache" / "panel.parquet", columns=["code_bss", "sd"])
    sd_train = P.drop_duplicates("code_bss").set_index("code_bss")["sd"].reindex(core)
    obs = drought_support()
    rng = np.random.default_rng(2026)
    present = [r for r in RUNS if (RESULTS / r / "predictions.parquet").exists()]
    if not present:
        raise SystemExit(f"no response run in {RESULTS}: pull the Kaggle kernel first")
    scores, stab, contrasts, bands, mean_m, comp = [], [], [], [], {}, []
    for run in present:
        m = pd.read_csv(RESULTS / run / "metrics_per_well.csv")
        mean_m[run] = m
        frames = seed_frames(run)
        per_start = {s: per_well(score(f)) for s, f in frames.items()}
        cfg = json.loads((RESULTS / run / "config.json").read_text())
        steps = [json.loads(f.read_text())["best_epoch"] for f in sorted((RESULTS / run).glob("seed_*.json"))]
        scores.append((RUNS[run], medians(m) | nse_range(per_start)
                       | {"steps (median)": float(np.median(steps)), "λ": cfg.get("lam", np.nan)}))
        stab.append((RUNS[run], nse_range(per_start) | response_stability(run, core, sd_train)))
        lo, hi, mx = band(frames, obs, wells, rng)
        bands.append((RUNS[run], {"band 2.5 %": lo, "band 97.5 %": hi, "largest |value|": mx}))
        comp += comparator(run)
    pooled = [r for r in present if r in GRID]
    chosen = max(pooled, key=lambda r: per_well(mean_m[r], "validation").median()) if pooled else None
    ref_m = {r: pd.read_csv(RESULTS / r / "metrics_per_well.csv") for r in COMPARE
             if (RESULTS / r / "metrics_per_well.csv").exists()}
    for run in [r for r in ("resp_free", chosen, "resp_shared") if r in present]:
        for ref, label in COMPARE.items():
            if ref in ref_m:
                contrasts.append((f"{RUNS[run]} vs {label}", contrast(mean_m[run], ref_m[ref], wells)))
    if "resp_free" in present:
        for run in [r for r in present if r != "resp_free" and (r == chosen or r not in GRID + ("resp_shared",))]:
            contrasts.append((f"{RUNS[run]} vs {RUNS['resp_free']}",
                              contrast(mean_m[run], mean_m["resp_free"], wells)))
        for run in [r for r in present if r not in FIRST]:
            for ref, label in COMPARE.items():
                if ref in ref_m:
                    contrasts.append((f"{RUNS[run]} vs {label}", contrast(mean_m[run], ref_m[ref], wells)))
    # the Pastas multistart beside it
    pstarts = {k: per_well(pd.read_csv(RESULTS / r / "metrics_per_well.csv"))
               for k, r in enumerate(PASTAS_STARTS) if (RESULTS / r / "metrics_per_well.csv").exists()}
    pastas_rows = []
    if len(pstarts) > 1:
        row = nse_range(pstarts)
        pp = {k: pd.read_csv(RESULTS / r / "params.csv").set_index("code_bss")
              for k, r in enumerate(PASTAS_STARTS) if (RESULTS / r / "params.csv").exists()}
        for col, name in (("p_recharge_A", "spread gain_recharge"), ("p_recharge_a", "spread a_recharge_wk"),
                          ("p_pumping_A", "spread gain_pumping"), ("p_pumping_a", "spread a_pumping_wk"),
                          ("p_canal_A", "spread gain_canal"), ("p_canal_a", "spread a_canal_wk"),
                          ("p_recharge_f", "spread f")):
            t = pd.DataFrame({k: p[col] for k, p in pp.items() if col in p}).reindex(core).dropna()
            row[name] = spread(t).median()
        pastas_rows.append(("Pastas reference, 10 starts (one fit per well)", row))
        if REFERENCE in ref_m:
            scores.append(("Pastas reference (best start by the frozen rule)", medians(ref_m[REFERENCE])))
    if "lstm_tuned" in ref_m:
        scores.append(("LSTM tuned (5-seed mean)", medians(ref_m["lstm_tuned"])))

    L = [f"# Model ladder, rungs 1–2: scores and stability (generated)\n\n"
         f"Generated by `python -m src.analysis.ladder_report` (dataset **{DATASET}**); do not edit by "
         "hand. Response superposition for all wells together (`src/models/response.py`), protocol in "
         "`docs/analysis_plan.md` §14 item 18. Core wells. **Exploratory (development benchmark).** "
         "Every row of a response run is the mean prediction over its starts unless it says single "
         "start. The runs named sensitivity were fixed before any result; those named diagnostic, "
         "permanent + seasonal or \"in units of the well's sd\" are follow-ups defined after the first "
         "results were read (analysis plan §14 item 18).\n",
         "## Scores\n\nMedians over the core wells. RMSE in metres.\n",
         table(scores, ["NSE val", "NSE drought", "skill drought", "RMSE drought",
                        "single start, drought NSE: mean", "single start, drought NSE: sd", "starts",
                        "steps (median)"]),
         (f"\nPooled run chosen on validation: **{RUNS[chosen]}**.\n" if chosen else ""),
         "\n## Stability across starts\n\nRange = largest minus smallest drought NSE of a core well over "
         "the starts. Spread of a parameter = (max − min) / |median| over the starts, median over "
         "wells. A stable model has small values.\n",
         table(stab + pastas_rows,
               ["per-well drought NSE range over starts (median)"]
               + list(dict.fromkeys(k for _, r in stab + pastas_rows for k in r
                                    if k.startswith("spread ") and not k.startswith("spread n_")))),
         "\n### Contributions in the drought phase\n\nMean contribution of each stress over the drought "
         "weeks, in units of the well's training sd: its size (|mean over starts|) and its sd over the "
         "starts, medians over the core wells; and the share of wells whose sd is under half the size "
         "(a contribution that keeps its size whatever the start).\n",
         table(stab, list(dict.fromkeys(k for _, r in stab for k in r if k.startswith("contribution ")))),
         "\n## Learned response times beside BRGM's (two core wells)\n\nCaballero & Ladouche 2015 "
         "(doi:10.5194/hessd-12-10109-2015, Table 1) fitted a transfer model with measured monthly "
         "pumping (1998–2007) at these two wells: mean transit time of the recharge response, and the "
         "maximum response to seasonal pumping 75 days after pumping starts. Ours: median [min, max] "
         "over the starts. A comparison with a published model, not with a measurement.\n",
         table(comp, ["recharge mean lag, days", "BRGM mean transit, days", "pumping peak lag, days",
                      "BRGM, days"], nd=0),
         "\n## Contrasts (primary effect measure of item 18)\n\nPer core well, log(RMSE_a / RMSE_b) in "
         "the drought phase; negative = a better. Interval = cluster bootstrap, p = cluster sign-flip "
         "(14 cells of 10 km), not adjusted: these contrasts are exploratory.\n",
         table(contrasts, ["median log(RMSE a / RMSE b)", "interval", "share of wells a better",
                           "p_cluster", "support mismatch"], nd=3),
         f"\n## Same-arm band\n\nThe same statistic between the mean predictions of two random disjoint "
         f"halves of one run's starts ({N_BAND} draws): what training noise alone produces. A contrast "
         "inside this band is not distinguishable from it.\n",
         table(bands, ["band 2.5 %", "band 97.5 %", "largest |value|"], nd=3)]
    out = ROOT / "docs" / f"results_ladder_{DATASET}.md"
    out.write_text("\n".join(L))
    print(f"-> {out}")


if __name__ == "__main__":
    main()
