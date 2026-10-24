"""Baseline report: tables and figures comparing every baseline run.

    python -m src.analysis.baseline_report          # current dataset (PFE_DATASET)

Reads results/<version>/<run>/metrics_per_well.csv, metrics_summary.csv and the
seed files written by src.models.*, so it always reflects the latest runs.
Primary endpoint (docs/analysis_plan.md): simulation, median NSE over the 33 core
wells in the drought phase of the test period (src.config.TEST_PERIODS), with the
skill against the training climatology next to it.

Outputs
    docs/results_baselines.md                       tables, v1-v3 (do not edit by hand)
    docs/results_baselines_<version>.md             the same from v4 on
    reports/figures/baselines_nse_<version>.png       validation / drought / recovery NSE
    reports/figures/baselines_hydrographs_<version>.png
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.analysis.stats import SENS_KM, SENS_SHIFTS, cluster_sensitivity, holm, paired
from src.config import DATASET, FIGURES, ROOT
from src.models.evaluate import DS, RESULTS, score

SIM = [("naive_climatology", "Climatology (floor)"),
       ("pastas_seasonal_canal", "Pastas (seasonal + canal)"),
       ("pastas_wellmodel", "Pastas WellModel (distance-scaled pumping)"),
       ("lgbm_noclim_tuned", "LightGBM tuned (Optuna)"),
       # with each well's own training climatology as input (clim_z): sensitivity rows only,
       # the networks never get it (decision 2026-10-20, docs/notes/step12a_fixes.md 5c)
       ("lgbm_sim", "LightGBM + own-climatology input (sensitivity)"),
       ("lgbm_tuned", "LightGBM tuned + own-climatology input (sensitivity)"),
       ("lstm", "LSTM (5 seeds)"), ("lstm_tuned", "LSTM tuned (Optuna, 5 seeds)"),
       ("ealstm_tuned", "EA-LSTM tuned (Optuna, 5 seeds)"),
       ("stgnn_distance", "Distance-graph ST-GNN (5 seeds)"),
       ("stgnn_tuned", "Distance-graph ST-GNN tuned (5 seeds)"),
       ("taccari", "Taccari-graph ST-GNN (5 seeds)"),
       ("taccari_tuned", "Taccari-graph ST-GNN tuned (5 seeds)"),
       ("ensemble_sim", "Ensemble (members chosen on validation)")]
FC = [("naive_persistence", "Persistence"), ("naive_anomaly_persist", "Anomaly persistence (floor)"),
      ("lgbm_fc", "LightGBM"), ("chronos2", "Chronos-2 zero-shot"),
      ("chronos2_xl", "Chronos-2 zero-shot, cross-learning"),
      ("chronos2_ft", "Chronos-2 fine-tuned")]
# Hydrology reference of the significance table. From v4 (decided by Assil on 2026-10-24,
# third review §3.3, before any multistart result was seen): the Pastas fit built from the
# training heads only (--train-obs; the default fit sets its initial constant from the whole
# series, test years included), each well's start chosen by the frozen training-RMSE rule of
# src.analysis.pastas_stability, whatever its test score. The full-series fits stay as
# historical rows.
REFERENCE = "pastas_seasonal_canal_trainobs_beststart" if DATASET >= "v4" else "pastas_seasonal_canal"
if DATASET >= "v4":
    SIM.insert(1, (REFERENCE, "Pastas (seasonal + canal), training heads only, best start "
                              "[reference]"))
    SIM[2] = ("pastas_seasonal_canal", "Pastas (seasonal + canal), full series at construction "
                                       "(historical)")
    SIM[3] = ("pastas_wellmodel", "Pastas WellModel, full series at construction (historical)")
# RQ1 regimes (docs/analysis_plan.md section 4) of the tuned models: run-name suffixes
REGIME_MODELS = [("lgbm_noclim", "LightGBM"), ("lstm", "LSTM"),
                 ("ealstm", "EA-LSTM"),
                 ("stgnn", "Distance-graph ST-GNN"), ("taccari", "Taccari-graph ST-GNN")]
REGIMES = [("", "R1 all wells, full training"), ("_lwo", "R2 left-out monitored wells (5 folds)"),
           ("_f50", "R3 50 % of the training period"), ("_f25", "R3 25 % of the training period"),
           ("_refit", "refit on train + validation")]
# regimes deliberately not run on a dataset version, with the reason (shown under the table)
REGIME_NOTES = {("v3", "ealstm"): "EA-LSTM: R1 only on v3. Its other regimes were stopped on "
                "2026-10-23 and run on v4 only: the v3 leave-wells-out folds split twin wells "
                "20 m apart (`docs/notes/step12a_fixes.md`)."}
GROUPS = ["Pliocene multilayer", "recent alluvium", "ancient alluvium", "Corbières karst", "other"]
# validated categorical palette (dataviz skill), fixed order
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e5e4df", "#fcfcfb"


def summary(run, results=None):
    f = (results or RESULTS) / run / "metrics_summary.csv"
    return pd.read_csv(f) if f.exists() else None


def pick(s, task, h, split, col="NSE", variant="all", group="all core"):
    if s is None:
        return np.nan
    r = s[(s["task"] == task) & (s["horizon"] == h) & (s["split"] == split)
          & (s["variant"] == variant) & (s["group"] == group)]
    return float(r[col].iloc[0]) if len(r) and col in r else np.nan


def seed_spread(run, split="test_drought"):
    """Mean and sd over seeds of the single-seed core median NSE (None if no seed files)."""
    files = sorted((RESULTS / run).glob("seed_*.parquet"))
    if not files:
        return None
    P = pd.read_parquet(RESULTS / "_cache" / "panel.parquet", columns=["code_bss", "mu", "sd"])
    musd = P.drop_duplicates("code_bss").set_index("code_bss")
    vals = []
    for f in files:
        z = pd.read_parquet(f).dropna(subset=["z"])
        z = z.join(musd, on="code_bss")
        pred = z.assign(pred=z["mu"] + z["sd"] * z["z"], task="simulation", horizon=0)
        m = score(pred[["code_bss", "week", "pred", "task", "horizon"]])
        m = m[(m["split"] == split) & (m["variant"] == "all") & m["core"]]
        vals.append(m["NSE"].median())
    return float(np.mean(vals)), float(np.std(vals)), len(vals)


def main_table():
    rows = []
    for task, runs, hs in (("simulation", SIM, (0,)), ("forecast", FC, (4, 12))):
        for h in hs:
            for run, label in runs:
                s = summary(run)
                if s is None or np.isnan(pick(s, task, h, "validation")):
                    continue
                r = {"task": task, "h": h, "model": label,
                     "NSE val": pick(s, task, h, "validation"),
                     "NSE test": pick(s, task, h, "test"),
                     "NSE drought": pick(s, task, h, "test_drought"),
                     "NSE recovery": pick(s, task, h, "test_recovery"),
                     "skill drought": pick(s, task, h, "test_drought", "skill"),
                     "skill recovery": pick(s, task, h, "test_recovery", "skill"),
                     "KGE'' test": pick(s, task, h, "test", "KGE"),
                     "RMSE test (m)": pick(s, task, h, "test", "RMSE"),
                     "wells": pick(s, task, h, "test", "n_wells"),
                     "NSE drought, validated": pick(s, task, h, "test_drought", variant="validated")}
                sp = seed_spread(run) if task == "simulation" else None
                r["single seeds, NSE drought"] = (f"{sp[0]:.2f} ± {sp[1]:.2f} (n={sp[2]})"
                                                  if sp else "")
                rows.append(r)
    return pd.DataFrame(rows)


def group_table():
    rows = []
    for run, label in SIM:
        s = summary(run)
        if s is None:
            continue
        r = {"model": label}
        for g in GROUPS:
            r[g] = pick(s, "simulation", 0, "test_drought", group=g)
        r["plain core"] = pick(s, "simulation", 0, "test_drought", group="plain core")
        rows.append(r)
    t = pd.DataFrame(rows)
    n = summary(SIM[0][0])
    counts = {g: pick(n, "simulation", 0, "test_drought", "n_wells", group=g) for g in GROUPS}
    t.columns = [f"{c} ({counts[c]:.0f})" if c in counts and not np.isnan(counts[c]) else c
                 for c in t.columns]
    return t


def regimes_table():
    """Drought and recovery scores of every tuned model under each RQ1 regime."""
    rows = []
    for m, label in REGIME_MODELS:
        for suffix, regime in REGIMES:
            s = summary(f"{m}_tuned{suffix}")
            if s is None:
                continue
            rows.append({"model": label, "regime": regime,
                         "NSE drought": pick(s, "simulation", 0, "test_drought"),
                         "skill drought": pick(s, "simulation", 0, "test_drought", "skill"),
                         "NSE recovery": pick(s, "simulation", 0, "test_recovery"),
                         "skill recovery": pick(s, "simulation", 0, "test_recovery", "skill"),
                         "wells": pick(s, "simulation", 0, "test_drought", "n_wells")})
    return pd.DataFrame(rows)


def significance_table():
    """Each simulation model vs the hydrology reference, per-well paired, Holm across models."""
    ref = RESULTS / REFERENCE / "metrics_per_well.csv"
    if not ref.exists():
        return pd.DataFrame()
    wells = pd.read_parquet(DS / "wells.parquet")
    mb = pd.read_csv(ref)
    rows = []
    for run, label in SIM:
        f = RESULTS / run / "metrics_per_well.csv"
        if run == REFERENCE or not f.exists():
            continue
        ma = pd.read_csv(f)
        for split, metric in (("test_drought", "NSE"), ("test_drought", "skill"),
                              ("test_recovery", "NSE")):
            r = paired(ma, mb, wells, split=split, metric=metric)
            rows.append({"model": label, "period": split, "metric": metric} | r)
    t = pd.DataFrame(rows)
    for (split, metric), idx in t.groupby(["period", "metric"]).groups.items():
        t.loc[idx, "p_holm"] = holm(t.loc[idx, "p_cluster"].to_numpy())
    return t


def sensitivity_table():
    """Prespecified sensitivity of the cluster inference (analysis plan §6), drought NSE."""
    ref = RESULTS / REFERENCE / "metrics_per_well.csv"
    if not ref.exists():
        return pd.DataFrame()
    wells = pd.read_parquet(DS / "wells.parquet")
    mb = pd.read_csv(ref)
    rows = []
    for run, label in SIM:
        f = RESULTS / run / "metrics_per_well.csv"
        if run == REFERENCE or not f.exists():
            continue
        grids, loco = cluster_sensitivity(pd.read_csv(f), mb, wells)
        if not len(grids):
            continue
        prim = grids[grids["primary"]].iloc[0]
        rows.append({"model": label, "median_diff": prim["median_diff"],
                     "p_cluster (10 km)": prim["p_cluster"],
                     "p_cluster min": grids["p_cluster"].min(),
                     "p_cluster max": grids["p_cluster"].max(),
                     "clusters": f"{grids['n_clusters'].min()}–{grids['n_clusters'].max()}",
                     "median_diff LOCO min": loco["median_diff"].min(),
                     "median_diff LOCO max": loco["median_diff"].max()})
    return pd.DataFrame(rows)


def mask_table():
    """Primary endpoints with and without the placeholder mask (amendment of 2026-10-24)."""
    rows = []
    for run, label in SIM:
        s = summary(run)
        if s is None or np.isnan(pick(s, "simulation", 0, "test_drought", variant="all_unmasked")):
            continue
        rows.append({"model": label,
                     "NSE drought": pick(s, "simulation", 0, "test_drought"),
                     "NSE drought, unmasked": pick(s, "simulation", 0, "test_drought",
                                                   variant="all_unmasked"),
                     "skill drought": pick(s, "simulation", 0, "test_drought", "skill"),
                     "skill drought, unmasked": pick(s, "simulation", 0, "test_drought", "skill",
                                                     variant="all_unmasked")})
    return pd.DataFrame(rows)


def compare_versions():
    """Drought NSE and skill of every model across dataset versions (same core wells)."""
    versions = [v for v in ("v1", "v2", "v3", "v4") if (ROOT / "results" / v).exists()]
    rows = []
    for task, runs, hs in (("simulation", SIM, (0,)), ("forecast", FC, (4, 12))):
        for h in hs:
            for run, label in runs:
                r = {"task": task, "h": h, "model": label}
                for v in versions:
                    s = summary(run, ROOT / "results" / v)
                    r[f"NSE drought {v}"] = pick(s, task, h, "test_drought")
                    r[f"skill drought {v}"] = pick(s, task, h, "test_drought", "skill")
                if any(not np.isnan(r[f"NSE drought {v}"]) for v in versions):
                    rows.append(r)
    return pd.DataFrame(rows)


def fmt(t, signed=()):
    t = t.copy()
    for c in t.columns:
        if t[c].dtype.kind not in "fi":
            continue
        if c in ("wells", "n_wells", "n_clusters", "h"):
            f = "{:.0f}"
        elif c.startswith("p_"):
            f = "{:.3f}"
        else:
            f = "{:+.2f}" if c in signed else "{:.2f}"
        t[c] = t[c].map(lambda v, f=f: "—" if pd.isna(v) else f.format(v))
    return t


def plot_nse(t):
    panels = [("simulation", 0, "Simulation (weather + pumping only)"),
              ("forecast", 4, "Forecast, 4 weeks ahead"), ("forecast", 12, "Forecast, 12 weeks ahead")]
    cols = [("NSE val", "validation 2020 – Apr 2022", SERIES[0]),
            ("NSE drought", "test: drought, May 2022 – Nov 2025", SERIES[1]),
            ("NSE recovery", "test: recovery, Dec 2025 –", SERIES[2])]
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.2), facecolor=SURF)
    for ax, (task, h, title) in zip(axes, panels):
        d = t[(t["task"] == task) & (t["h"] == h)].reset_index(drop=True)
        y = np.arange(len(d))[::-1]
        for yi, (_, r) in zip(y, d.iterrows()):
            v = [r[c] for c, _, _ in cols if not pd.isna(r[c])]
            ax.plot([min(v), max(v)], [yi, yi], color=GRID, linewidth=2, zorder=1)
        for c, lab, colr in cols:
            ax.scatter(d[c], y, s=52, color=colr, edgecolor=SURF, linewidth=1.5, zorder=3, label=lab)
        ax.set_yticks(y, d["model"], fontsize=7.5, color=INK2)
        ax.axvline(0, color=INK2, linewidth=0.8)
        ax.set_xlim(left=max(-1.6, ax.get_xlim()[0]))
        ax.set_title(title, fontsize=9, loc="left", color=INK)
        ax.set_facecolor(SURF)
        ax.grid(axis="x", color=GRID, linewidth=0.5)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.set_xlabel("median NSE, 33 core wells (0 = mean of the period)", fontsize=7, color=INK2)
    hd, lb = axes[0].get_legend_handles_labels()
    fig.legend(hd, lb, loc="lower center", ncol=3, fontsize=8, frameon=False)
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    out = FIGURES / f"baselines_nse_{DATASET}.png"
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return out


def plot_hydrographs():
    heads = pd.read_parquet(DS / "heads_weekly.parquet")
    wells = pd.read_parquet(DS / "wells.parquet").set_index("code_bss")
    picks = ["10975X0032/SABIRO", "10906X0039/C2-1", "10912X0134/BARQUA"]
    cand = (REFERENCE, "lgbm_noclim_tuned", "lstm_tuned", "stgnn_distance", "ensemble_sim")
    runs = [r for r in cand if (RESULTS / r / "predictions.parquet").exists()][:5]
    labels = dict(SIM)
    preds = {r: pd.read_parquet(RESULTS / r / "predictions.parquet") for r in runs}
    fig, axes = plt.subplots(len(picks), 1, figsize=(10, 2.6 * len(picks)), facecolor=SURF,
                             sharex=True)
    for ax, code in zip(axes, picks):
        if code not in wells.index:
            continue
        o = heads[(heads["code_bss"] == code) & (heads["week"] >= "2020-01-01")]
        ax.plot(o["week"], o["head"], color=INK, linewidth=1.6, label="observed")
        for k, r in enumerate(runs):
            p = preds[r]
            p = p[(p["code_bss"] == code) & (p["task"] == "simulation") & (p["week"] >= "2020-01-01")]
            ax.plot(p["week"], p["pred"], color=SERIES[k], linewidth=1.1, label=labels.get(r, r))
        ax.axvspan(pd.Timestamp("2022-05-01"), pd.Timestamp("2025-11-30"), color="#e34948",
                   alpha=0.06, linewidth=0)
        ax.axvspan(pd.Timestamp("2025-12-01"), o["week"].max(), color="#1baf7a", alpha=0.06,
                   linewidth=0)
        w = wells.loc[code]
        ax.set_title(f"{w['libelle_pe']} — {w['group']}, {w['profondeur_investigation']:.0f} m deep",
                     fontsize=9, loc="left", color=INK)
        ax.set_ylabel("head (m NGF)", fontsize=8, color=INK2)
        ax.set_facecolor(SURF)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    hd, lb = axes[0].get_legend_handles_labels()
    fig.legend(hd, lb, loc="upper center", ncol=3, fontsize=8, frameon=False)
    axes[-1].text(0.99, -0.22, "red: test, drought phase · green: test, recovery",
                  transform=axes[-1].transAxes, ha="right", fontsize=7, color=INK2)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    out = FIGURES / f"baselines_hydrographs_{DATASET}.png"
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return out


def main():
    t = main_table()
    g = group_table()
    sig = significance_table()
    reg = regimes_table()
    cmp_ = compare_versions()
    mask_t = mask_table() if DATASET >= "v4" else pd.DataFrame()
    sens = sensitivity_table() if DATASET >= "v4" else pd.DataFrame()
    sig_cols = ["model", "period", "metric", "n_wells", "median_a", "median_b", "median_diff",
                "ci_lo", "ci_hi", "share_a_better", "n_clusters", "p_cluster", "p_holm",
                "p_wilcoxon"]
    # v3 keeps docs/results_baselines.md (the report of record of Step 12a)
    md = ROOT / "docs" / ("results_baselines.md" if DATASET < "v4" else f"results_baselines_{DATASET}.md")
    missing = [label for run, label in SIM + FC
               if not (RESULTS / run / "predictions.parquet").exists()]
    parts = [
        "# Baseline results\n",
        "Generated by `python -m src.analysis.baseline_report`; do not edit by hand. "
        f"Dataset **{DATASET}**. Medians over the 33 core wells. Test sub-periods "
        "(`src/config.py`, fixed from observed SGI): **drought** May 2022 – Nov 2025, "
        "**recovery** Dec 2025 – end. NSE: 1 = perfect, 0 = as good as the mean of the "
        "scored period. **Skill** = 1 − MSE/MSE(benchmark): the training climatology for "
        "simulation, anomaly persistence for forecasts (0 = no better than the benchmark). "
        "KGE'' = Tang et al. 2021 (datum-free). See `docs/analysis_plan.md`.\n",
        "## Main table\n", fmt(t).to_markdown(index=False), "",
        ("**Not run yet** (rows missing above): " + "; ".join(missing) + ".\n") if missing else "",
        "## Drought-phase NSE by aquifer group (number of core wells)\n",
        fmt(g).to_markdown(index=False), "",
        f"## Significance against the hydrology reference ({REFERENCE})\n",
        "Paired per well; a = model, b = reference; difference > 0 means the model is better. "
        "95 % interval = cluster bootstrap over 10 km cells. p_cluster = sign-flip permutation "
        "test over the same cells (signs flipped cluster by cluster), Holm-adjusted across the "
        "models of each period × metric (p_holm); the per-well Wilcoxon p, which treats the "
        "wells as independent, is shown for comparison only (analysis plan v2, §6).\n",
        (fmt(sig[sig_cols], signed=("median_diff", "ci_lo", "ci_hi")).to_markdown(index=False)
         if len(sig) else "(reference run missing)"), "",
        *([f"**Paired support:** in {int((sig['support_mismatch'] > 0).sum())} of these rows, some "
           "wells were scored on different numbers of weeks by the model and the reference "
           "(`support_mismatch`); compare those rows with care.\n"]
          if len(sig) and (sig["support_mismatch"] > 0).any() else []),
        *(["**Sensitivity of the cluster inference** (drought NSE; fixed on 2026-10-24, "
           f"analysis plan §6): grids of {', '.join(f'{k:g}' for k in SENS_KM)} km with the "
           f"origin shifted by {', '.join(f'{x:g}' for x in SENS_SHIFTS)} cell, and the "
           "median difference with each 10 km cluster left out (LOCO). The 10 km grid at "
           "origin 0 stays the test of record.\n",
           fmt(sens, signed=("median_diff", "median_diff LOCO min", "median_diff LOCO max"))
           .to_markdown(index=False), ""] if len(sens) else []),
        "## RQ1 regimes of the tuned models\n",
        "R2 scores held-out wells in the \"dynamics\" convention (each well's own training "
        "mean and sd convert z to metres); R3 shortens the training period, validation and "
        "test unchanged; refit = secondary rows (`docs/analysis_plan.md` sections 4–5).\n",
        (fmt(reg).to_markdown(index=False) if len(reg) else "(no regime runs yet)"), "",
        " ".join(note for (v, _), note in REGIME_NOTES.items() if v == DATASET), "",
        "## Across dataset versions (drought phase)\n",
        fmt(cmp_).to_markdown(index=False), "",
        *(["## Amendment of 2026-10-24: suspect placeholder values masked\n",
           "From v4 the weeks of a run of ≥ 28 days with a depth of exactly 0.00 m leave every "
           "scored variant (`src/dataset/placeholders.py`: CORNEILLA PD5, Dec 2022 – Jan 2024, "
           "60 weeks, qualified \"Correcte\" by its producer). The rule was written after the "
           "test period was seen, so the primary endpoints are shown both ways "
           "(`docs/analysis_plan.md` §13).\n",
           fmt(mask_t).to_markdown(index=False), ""] if len(mask_t) else [])]
    md.write_text("\n".join(parts), encoding="utf-8")
    print(fmt(t).to_string(index=False))
    print("->", md)
    print("->", plot_nse(t))
    print("->", plot_hydrographs())


if __name__ == "__main__":
    main()
