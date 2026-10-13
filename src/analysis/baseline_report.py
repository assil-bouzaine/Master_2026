"""Baseline report: one table and two figures comparing every baseline run.

    python -m src.analysis.baseline_report

Reads results/<run>/metrics_per_well.csv and predictions.parquet (written by
src.models.*), so it always reflects the latest runs.

Outputs
    docs/results_baselines.md                  table (median over 33 core wells)
    reports/figures/baselines_nse.png           validation vs test NSE per model
    reports/figures/baselines_hydrographs.png   test-period hydrographs, 3 wells
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.config import FIGURES, ROOT
from src.models.evaluate import DS, RESULTS

SIM = [("naive_climatology", "Climatology (floor)"), ("pastas_seasonal_canal", "Pastas (best variant)"),
       ("lgbm_sim", "LightGBM"), ("lstm", "LSTM (5 seeds)"),
       ("stgnn_distance", "Distance-graph ST-GNN (5 seeds)")]
FC = [("naive_persistence", "Persistence"), ("naive_anomaly_persist", "Anomaly persistence (floor)"),
      ("lgbm_fc", "LightGBM"), ("chronos2", "Chronos-2 zero-shot")]
# validated categorical palette (dataviz skill), fixed order
C_VAL, C_TEST = "#2a78d6", "#eb6834"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e5e4df", "#fcfcfb"


def core_median(run, task, h, split, variant="all"):
    f = RESULTS / run / "metrics_per_well.csv"
    if not f.exists():
        return np.nan, np.nan, 0
    m = pd.read_csv(f)
    m = m[(m["task"] == task) & (m["horizon"] == h) & (m["split"] == split)
          & (m["variant"] == variant) & m["core"]]
    return m["NSE"].median(), m["RMSE"].median(), m["code_bss"].nunique()


def table():
    rows = []
    for task, runs, hs in (("simulation", SIM, (0,)), ("forecast", FC, (4, 12))):
        for h in hs:
            for run, label in runs:
                r = {"task": task, "horizon (weeks)": h, "model": label}
                for split in ("train", "validation", "test"):
                    nse, rmse, n = core_median(run, task, h, split)
                    r[f"NSE {split}"] = nse
                    if split == "test":
                        r["RMSE test (m)"] = rmse
                        r["wells"] = n
                r["NSE test, validated weeks"] = core_median(run, task, h, "test", "validated")[0]
                if not np.isnan(r["NSE validation"]):
                    rows.append(r)
    return pd.DataFrame(rows)


def plot_nse(t):
    panels = [("simulation", 0, "Simulation (weather + pumping only)"),
              ("forecast", 4, "Forecast, 4 weeks ahead"), ("forecast", 12, "Forecast, 12 weeks ahead")]
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.6), facecolor=SURF, sharex=True)
    for ax, (task, h, title) in zip(axes, panels):
        d = t[(t["task"] == task) & (t["horizon (weeks)"] == h)].reset_index(drop=True)
        y = np.arange(len(d))[::-1]
        for yi, (_, r) in zip(y, d.iterrows()):
            ax.plot([r["NSE validation"], r["NSE test"]], [yi, yi], color=GRID, linewidth=2, zorder=1)
        ax.scatter(d["NSE validation"], y, s=64, color=C_VAL, edgecolor=SURF, linewidth=2,
                   zorder=3, label="validation 2020–Apr 2022")
        ax.scatter(d["NSE test"], y, s=64, color=C_TEST, edgecolor=SURF, linewidth=2, zorder=3,
                   label="test May 2022–2026 (drought)")
        ax.set_yticks(y, d["model"], fontsize=8, color=INK2)
        ax.axvline(0, color=INK2, linewidth=0.8)
        ax.set_title(title, fontsize=9, loc="left", color=INK)
        ax.set_facecolor(SURF)
        ax.grid(axis="x", color=GRID, linewidth=0.5)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.set_xlabel("median NSE over 33 core wells (1 = perfect, 0 = mean level)",
                      fontsize=7, color=INK2)
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=2, fontsize=8, frameon=False)
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    out = FIGURES / "baselines_nse.png"
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return out


def plot_hydrographs():
    heads = pd.read_parquet(DS / "heads_weekly.parquet")
    wells = pd.read_parquet(DS / "wells.parquet").set_index("code_bss")
    picks = ["10975X0032/SABIRO", "10906X0039/C2-1", "10912X0134/BARQUA"]
    runs = [r for r in ("pastas_seasonal_canal", "lgbm_sim", "lstm", "stgnn_distance")
            if (RESULTS / r / "predictions.parquet").exists()]
    labels = dict(SIM)
    preds = {r: pd.read_parquet(RESULTS / r / "predictions.parquet") for r in runs}
    fig, axes = plt.subplots(len(picks), 1, figsize=(10, 2.6 * len(picks)), facecolor=SURF,
                             sharex=True)
    for ax, code in zip(axes, picks):
        o = heads[(heads["code_bss"] == code) & (heads["week"] >= "2020-01-01")]
        ax.plot(o["week"], o["head"], color=INK, linewidth=1.6, label="observed")
        for k, r in enumerate(runs):
            p = preds[r]
            p = p[(p["code_bss"] == code) & (p["task"] == "simulation") & (p["week"] >= "2020-01-01")]
            ax.plot(p["week"], p["pred"], color=SERIES[k], linewidth=1.2, label=labels[r])
        ax.axvspan(pd.Timestamp("2022-05-01"), o["week"].max(), color="#e34948", alpha=0.06,
                   linewidth=0)
        w = wells.loc[code]
        ax.set_title(f"{w['libelle_pe']} — {w['group']}, {w['profondeur_investigation']:.0f} m deep",
                     fontsize=9, loc="left", color=INK)
        ax.set_ylabel("head (m NGF)", fontsize=8, color=INK2)
        ax.set_facecolor(SURF)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper center", ncol=len(l), fontsize=8, frameon=False)
    axes[-1].text(0.99, -0.22, "shaded: test period (record drought, then recovery)",
                  transform=axes[-1].transAxes, ha="right", fontsize=7, color=INK2)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    out = FIGURES / "baselines_hydrographs.png"
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return out


def main():
    t = table()
    fmt = t.copy()
    for c in fmt.columns:
        if fmt[c].dtype.kind == "f":
            fmt[c] = fmt[c].map(lambda v: "—" if pd.isna(v) else f"{v:.2f}")
    md = ROOT / "docs" / "results_baselines.md"
    md.write_text("# Baseline results (dataset v1)\n\n"
                  "Median over the 33 core wells. NSE: 1 = perfect, 0 = as good as the mean "
                  "level, < 0 = worse. Generated by `python -m src.analysis.baseline_report`; "
                  "do not edit by hand.\n\n" + fmt.to_markdown(index=False) + "\n",
                  encoding="utf-8")
    print(fmt.to_string(index=False))
    print("->", md)
    print("->", plot_nse(t))
    print("->", plot_hydrographs())


if __name__ == "__main__":
    main()
