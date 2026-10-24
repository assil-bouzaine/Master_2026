"""Drought-class (SGI) scores and a compact hydrological error analysis of the simulation runs.

    PFE_DATASET=v4 python -m src.analysis.hydro_errors

The primary endpoints (median NSE and skill) stay those of docs/analysis_plan.md §1. This
adds what they do not show (third review, docs/review_codex_2026-10-24.md §7):

1. The predicted drought class. The subject is about drought risk, and a head RMSE is not a
   drought-class validation. A run's weekly heads become monthly means over the weeks that
   are also observed, then an SGI with the frozen *observed* reference of the well (every
   observed monthly mean up to 2019, as in src.dataset.build.sgi: Weibull plotting
   position, clipped half a step beyond the reference), then a BRGM IPS class (7 classes,
   bounds at the 10/20/40/60/80/90 % quantiles). Scored on the core wells, pooled over
   well-months: exact class, within one class, balanced accuracy (mean recall over the
   observed classes, so the 43 % of "très bas" months do not dominate), quadratic weighted
   kappa (classes are ordered) and, for "low levels" (SGI below the 20 % quantile: "bas"
   or "très bas"), the probability of detection, false-alarm ratio and critical success
   index. Climatology predicts about the average class everywhere, so its POD is near 0:
   the floor.
2. Hydrological errors per well, on the weeks observed in the period: the timing (weeks)
   and size (m) of each calendar year's minimum, the lag (weeks, |lag| <= 12) at which the
   simulated anomaly best correlates with the observed one (> 0: the simulation is late),
   and the trough of the whole period. Bias, sd ratio and correlation are already in
   metrics_per_well.csv (src.models.evaluate) and are read from there.
3. Representative hydrographs, chosen by a stated rule rather than by hand: per aquifer
   group, the core well whose drought NSE, averaged over every simulation run present, is
   the group median (the lower middle well for an even count).

From dataset v4 the weeks of suspect placeholder values (src.dataset.placeholders: CORNEILLA
PD5, Dec 2022 - Jan 2024) are left out, as in src.models.evaluate.

Head change is not water availability or sustainable yield: these are scores of a head
simulation, nothing more. Nothing is fitted here.

Outputs
    results/<version>/<run>/sgi_scores.csv, sgi_confusion.csv, hydro_errors_per_well.csv
    docs/results_hydro_<version>.md                       (generated; do not edit by hand)
    reports/figures/hydrographs_rule_<version>.png
"""
import json
from statistics import NormalDist

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.analysis.baseline_report import GRID, INK, INK2, SERIES, SIM, SURF
from src.config import DATASET, FIGURES, ROOT, TEST_PERIODS
from src.dataset.build import IPS_CLASSES, SGI_MIN_REF_YEARS, TRAIN_END
from src.dataset.placeholders import load_mask
from src.models.evaluate import DS, RESULTS

CLASSES = [label for _, label in IPS_CLASSES]
BOUNDS = np.array([b for b, _ in IPS_CLASSES[:-1]])
LOW = NormalDist().inv_cdf(0.2)          # "bas" or "très bas"
MAX_LAG = 12
MIN_YEAR_WEEKS = 26                      # weeks of a year in the period to score its minimum
PERIODS = ("test_drought", "test_recovery")
GROUPS = ("Pliocene multilayer", "recent alluvium", "ancient alluvium", "Corbières karst")
OUT_MD = ROOT / "docs" / f"results_hydro_{DATASET}.md"


def period_of(t):
    """Test sub-period of each timestamp (None outside), from src.config.TEST_PERIODS."""
    out = pd.Series(None, index=t.index, dtype=object)
    for name, (a, b) in TEST_PERIODS.items():
        m = t >= a
        if b is not None:
            m &= t <= b
        out[m] = name
    return out


def references(heads):
    """Per well and calendar month: the sorted observed monthly means up to the end of
    training (no lower bound), as src.dataset.build.sgi; None below SGI_MIN_REF_YEARS."""
    h = heads.dropna(subset=["head"])
    monthly = (h.set_index("week").groupby("code_bss")["head"].resample("MS").mean()
               .dropna().reset_index())
    ref = monthly[monthly["week"] <= TRAIN_END]
    out = {}
    for (code, m), g in ref.groupby([ref["code_bss"], ref["week"].dt.month]):
        if len(g) >= SGI_MIN_REF_YEARS:
            out[(code, m)] = np.sort(g["head"].to_numpy())
    return out


def to_sgi(code, months, values, refs):
    """SGI of monthly values with the well's observed reference (NaN without one)."""
    z = np.full(len(values), np.nan)
    for k, (m, v) in enumerate(zip(months, values)):
        r = refs.get((code, m))
        if r is None or np.isnan(v):
            continue
        n = len(r)
        p = np.clip(np.searchsorted(r, v, side="right") / (n + 1), 0.5 / (n + 1), 1 - 0.5 / (n + 1))
        z[k] = NormalDist().inv_cdf(float(p))
    return z


def classify(z):
    """IPS class index 0 ("très bas") .. 6 ("très haut"); -1 for NaN."""
    c = np.searchsorted(BOUNDS, z, side="right")
    return np.where(np.isnan(z), -1, c)


def masked_heads(heads):
    """Heads without the suspect placeholder weeks (dataset v4 on), as the scorer sees them."""
    mask = load_mask() if DATASET >= "v4" else None
    if mask is None:
        return heads
    out = heads.merge(mask.assign(_flag=True), on=["code_bss", "week"], how="left")
    return out[out["_flag"].isna()].drop(columns="_flag")


def paired_weeks(pred, heads):
    p = pred[(pred["task"] == "simulation")][["code_bss", "week", "pred"]]
    d = heads[["code_bss", "week", "head"]].merge(p, on=["code_bss", "week"]).dropna()
    d["period"] = period_of(d["week"])
    return d[d["period"].notna()]


def monthly_classes(d, refs):
    """Observed and simulated monthly means over the same weeks -> SGI -> class."""
    g = (d.assign(month=d["week"].dt.to_period("M").dt.to_timestamp())
         .groupby(["code_bss", "month"]).agg(obs=("head", "mean"), sim=("pred", "mean"),
                                             period=("period", "first")).reset_index())
    parts = []
    for code, w in g.groupby("code_bss"):
        mm = w["month"].dt.month.to_numpy()
        parts.append(w.assign(z_obs=to_sgi(code, mm, w["obs"].to_numpy(), refs),
                              z_sim=to_sgi(code, mm, w["sim"].to_numpy(), refs)))
    g = pd.concat(parts, ignore_index=True).dropna(subset=["z_obs", "z_sim"])
    return g.assign(c_obs=classify(g["z_obs"].to_numpy()), c_sim=classify(g["z_sim"].to_numpy()))


def qwk(a, b, k=len(CLASSES)):
    """Quadratic weighted Cohen's kappa of two ordinal label vectors (0..k-1)."""
    o = np.zeros((k, k))
    np.add.at(o, (a, b), 1)
    w = (np.arange(k)[:, None] - np.arange(k)[None]) ** 2 / (k - 1) ** 2
    e = np.outer(o.sum(1), o.sum(0)) / o.sum()
    den = (w * e).sum()
    return float(1 - (w * o).sum() / den) if den > 0 else float("nan")


def class_scores(g):
    a, b = g["c_obs"].to_numpy(), g["c_sim"].to_numpy()
    lo_o, lo_s = g["z_obs"].to_numpy() < LOW, g["z_sim"].to_numpy() < LOW
    hits, miss, fa = int((lo_o & lo_s).sum()), int((lo_o & ~lo_s).sum()), int((~lo_o & lo_s).sum())
    recall = [float((b[a == c] == c).mean()) for c in np.unique(a)]
    return {"wells": g["code_bss"].nunique(), "well_months": len(g),
            "exact": float((a == b).mean()), "within_one": float((np.abs(a - b) <= 1).mean()),
            "balanced_acc": float(np.mean(recall)), "qwk": qwk(a, b),
            "pod_low": hits / (hits + miss) if hits + miss else np.nan,
            "far_low": fa / (hits + fa) if hits + fa else np.nan,
            "csi_low": hits / (hits + miss + fa) if hits + miss + fa else np.nan,
            "share_low_obs": float(lo_o.mean())}


def lag_weeks(o, s):
    """Lag (weeks) of the best correlation of the anomalies; > 0: the simulation is late."""
    o, s = o - np.nanmean(o), s - np.nanmean(s)
    best, arg = -np.inf, np.nan
    for k in range(-MAX_LAG, MAX_LAG + 1):
        a, b = (o[:len(o) - k], s[k:]) if k >= 0 else (o[-k:], s[:len(s) + k])
        m = ~(np.isnan(a) | np.isnan(b))
        if m.sum() < 26 or a[m].std() == 0 or b[m].std() == 0:
            continue
        r = np.corrcoef(a[m], b[m])[0, 1]
        if r > best:
            best, arg = r, k
    return arg


def well_errors(d, period):
    rows = []
    for code, w in d[d["period"] == period].groupby("code_bss"):
        w = w.set_index("week").sort_index()
        full = w.reindex(pd.date_range(w.index.min(), w.index.max(), freq="W-SUN"))
        r = {"code_bss": code, "period": period,
             "lag_wk": lag_weeks(full["head"].to_numpy(), full["pred"].to_numpy())}
        yr = []
        for y, g in w.groupby(w.index.year):
            if len(g) >= MIN_YEAR_WEEKS:
                yr.append(((g["pred"].idxmin() - g["head"].idxmin()).days / 7,
                           g["pred"].min() - g["head"].min()))
        if yr:
            r["annual_min_timing_abs_wk"] = float(np.median([abs(t) for t, _ in yr]))
            r["annual_min_error_m"] = float(np.median([e for _, e in yr]))
            r["n_years"] = len(yr)
        r["trough_timing_wk"] = (w["pred"].idxmin() - w["head"].idxmin()).days / 7
        r["trough_error_m"] = w["pred"].min() - w["head"].min()
        rows.append(r)
    return pd.DataFrame(rows)


def score_run(run, heads, refs, core):
    pred = pd.read_parquet(RESULTS / run / "predictions.parquet")
    d = paired_weeks(pred, heads)
    d = d[d["code_bss"].isin(core)]
    g = monthly_classes(d, refs)
    scores, conf = [], []
    for period in PERIODS:
        gp = g[g["period"] == period]
        if len(gp):
            scores.append({"period": period} | class_scores(gp))
            ct = pd.crosstab(pd.Categorical(gp["c_obs"], range(len(CLASSES))),
                             pd.Categorical(gp["c_sim"], range(len(CLASSES))), dropna=False)
            conf.append(ct.rename_axis(index="observed", columns="simulated").stack()
                        .rename("n").reset_index().assign(period=period))
    errs = pd.concat([well_errors(d, p) for p in PERIODS], ignore_index=True)
    out = RESULTS / run
    pd.DataFrame(scores).to_csv(out / "sgi_scores.csv", index=False)
    pd.concat(conf, ignore_index=True).to_csv(out / "sgi_confusion.csv", index=False)
    errs.to_csv(out / "hydro_errors_per_well.csv", index=False)
    return pd.DataFrame(scores), errs, g


def representative_wells(runs, wells):
    """Per group: the core well with the median drought NSE averaged over the runs."""
    per = []
    for run in runs:
        m = pd.read_csv(RESULTS / run / "metrics_per_well.csv")
        m = m[(m["task"] == "simulation") & (m["split"] == "test_drought")
              & (m["variant"] == "all") & m["core"]]
        per.append(m.set_index("code_bss")["NSE"].rename(run))
    mean = pd.concat(per, axis=1).mean(axis=1)
    picks = {}
    for grp in GROUPS:
        codes = wells.loc[wells["core"] & (wells["group"] == grp), "code_bss"]
        s = mean.reindex(codes).dropna().sort_values()
        if len(s):
            picks[grp] = s.index[(len(s) - 1) // 2]
    return picks, mean


def plot(picks, runs, labels, heads, wells):
    fig, axes = plt.subplots(len(picks), 1, figsize=(10, 2.5 * len(picks)), facecolor=SURF,
                             sharex=True, squeeze=False)
    preds = {r: pd.read_parquet(RESULTS / r / "predictions.parquet") for r in runs}
    w = wells.set_index("code_bss")
    for ax, (grp, code) in zip(axes[:, 0], picks.items()):
        o = heads[(heads["code_bss"] == code) & (heads["week"] >= "2020-01-01")]
        o = o.set_index("week")["head"]          # missing weeks break the line
        o = o.reindex(pd.date_range(o.index.min(), o.index.max(), freq="W-SUN"))
        ax.plot(o.index, o.to_numpy(), color=INK, linewidth=1.6, label="observed")
        for k, r in enumerate(runs):
            p = preds[r]
            p = p[(p["code_bss"] == code) & (p["task"] == "simulation") & (p["week"] >= "2020-01-01")]
            ax.plot(p["week"], p["pred"], color=SERIES[k % len(SERIES)], linewidth=1.1,
                    label=labels.get(r, r))
        ax.axvspan(pd.Timestamp("2022-05-01"), pd.Timestamp("2025-11-30"), color="#e34948",
                   alpha=0.06, linewidth=0)
        name = w.loc[code, "libelle_pe"]
        ax.set_title(f"{grp}: {name} ({code})" if isinstance(name, str) else f"{grp}: {code}",
                     fontsize=9, loc="left", color=INK)
        ax.set_ylabel("head (m NGF)", fontsize=8, color=INK2)
        ax.set_facecolor(SURF)
        ax.grid(axis="y", color=GRID, linewidth=0.5)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    hd, lb = axes[0, 0].get_legend_handles_labels()
    fig.legend(hd, lb, loc="upper center", ncol=3, fontsize=8, frameon=False)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    out = FIGURES / f"hydrographs_rule_{DATASET}.png"
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return out


def fmt(t, digits=2):
    t = t.copy()
    for c in t.columns:
        if t[c].dtype.kind == "f":
            t[c] = t[c].map(lambda v: "—" if pd.isna(v) else f"{v:.{digits}f}")
    return t


def main():
    all_heads = pd.read_parquet(DS / "heads_weekly.parquet",
                                columns=["code_bss", "week", "head", "sgi"])
    heads = masked_heads(all_heads)
    wells = pd.read_parquet(DS / "wells.parquet")
    core = set(wells.loc[wells["core"], "code_bss"])
    refs = references(heads)
    labels = dict(SIM)
    runs = [r for r, _ in SIM if (RESULTS / r / "predictions.parquet").exists()]
    sgi_rows, err_rows, conf_of = [], [], {}
    for run in runs:
        s, e, g = score_run(run, heads, refs, core)
        sgi_rows.append(s.assign(model=labels[run]))
        e = e.groupby("period").agg(
            wells=("code_bss", "nunique"), lag_median_wk=("lag_wk", "median"),
            share_lag_le2=("lag_wk", lambda x: float((x.abs() <= 2).mean())),
            annual_min_timing_wk=("annual_min_timing_abs_wk", "median"),
            annual_min_error_m=("annual_min_error_m", "median"),
            trough_timing_abs_wk=("trough_timing_wk", lambda x: float(x.abs().median())),
            trough_error_m=("trough_error_m", "median")).reset_index()
        err_rows.append(e.assign(model=labels[run]))
        conf_of[run] = g
    # consistency: the observed classes equal the dataset's own SGI (src.dataset.build.sgi),
    # on the months that kept all their weeks (the dataset's SGI includes masked weeks)
    g0 = conf_of[runs[0]]
    month = lambda h: h.assign(month=h["week"].dt.to_period("M").dt.to_timestamp())  # noqa: E731
    ds = month(all_heads).dropna(subset=["sgi"]).groupby(["code_bss", "month"])["sgi"].first()
    dropped = month(all_heads.merge(heads[["code_bss", "week"]], how="left", indicator=True)
                    .query("_merge == 'left_only'"))[["code_bss", "month"]].drop_duplicates()
    chk = g0.set_index(["code_bss", "month"])["z_obs"].to_frame().join(ds, how="inner")
    chk = chk.drop(index=pd.MultiIndex.from_frame(dropped), errors="ignore")
    gap = float((chk["z_obs"] - chk["sgi"]).abs().max())
    assert gap < 1e-9, f"observed SGI differs from the dataset's: {gap}"

    sgi = pd.concat(sgi_rows, ignore_index=True)
    err = pd.concat(err_rows, ignore_index=True)
    cols = ["model", "wells", "well_months", "exact", "within_one", "balanced_acc", "qwk",
            "pod_low", "far_low", "csi_low", "share_low_obs"]
    ecols = ["model", "wells", "lag_median_wk", "share_lag_le2", "annual_min_timing_wk",
             "annual_min_error_m", "trough_timing_abs_wk", "trough_error_m"]

    # confusion matrices: the reference, and the run with the best *validation* median NSE
    def val(run):
        s = pd.read_csv(RESULTS / run / "metrics_summary.csv")
        s = s[(s["task"] == "simulation") & (s["split"] == "validation") & (s["variant"] == "all")
              & (s["group"] == "all core")]
        return float(s["NSE"].iloc[0]) if len(s) else -np.inf
    from src.analysis.baseline_report import REFERENCE
    shown = [r for r in dict.fromkeys([REFERENCE, max(runs, key=val)]) if r in conf_of]
    conf_md = []
    for r in shown:
        g = conf_of[r]
        g = g[g["period"] == "test_drought"]
        ct = pd.crosstab(pd.Categorical(g["c_obs"].map(dict(enumerate(CLASSES))), CLASSES),
                         pd.Categorical(g["c_sim"].map(dict(enumerate(CLASSES))), CLASSES),
                         dropna=False).rename_axis(index="observed \\ simulated")
        conf_md += [f"**{labels[r]}** (drought, core wells, well-months)\n",
                    ct.to_markdown(), ""]

    picks, _ = representative_wells(runs, wells)
    shown_runs = [r for r in dict.fromkeys([REFERENCE, "lgbm_noclim_tuned", "lstm_tuned",
                                            "taccari_tuned", "ensemble_sim"]) if r in runs][:5]
    fig = plot(picks, shown_runs, labels, heads, wells)

    md = [
        "# Drought classes and hydrological errors (generated)\n",
        f"Generated by `python -m src.analysis.hydro_errors` (dataset **{DATASET}**); do not "
        "edit by hand. Core wells. Secondary to the primary endpoints of "
        "`docs/analysis_plan.md` §1; exploratory, like every baseline result (§11).\n",
        "## Drought class (SGI → BRGM IPS class), drought phase\n",
        "Monthly means over the weeks that are both observed and simulated; the simulated "
        "SGI uses the well's observed reference (up to 2019). exact / within one class; "
        "balanced accuracy = mean recall over the observed classes; qwk = quadratic weighted "
        "kappa; low = SGI below the 20 % quantile (\"bas\" or \"très bas\"): POD = share of "
        "low months simulated low, FAR = share of simulated-low months that were not low, "
        "CSI = hits / (hits + misses + false alarms).\n",
        fmt(sgi[sgi["period"] == "test_drought"][cols]).to_markdown(index=False), "",
        "## Drought class, recovery phase (provisional: few validated weeks)\n",
        fmt(sgi[sgi["period"] == "test_recovery"][cols]).to_markdown(index=False), "",
        "## Confusion matrices\n",
        "Shown for the hydrology reference and for the run with the best median "
        "*validation* NSE (a choice that never looks at the test period).\n",
        *conf_md,
        "## Hydrological errors, drought phase (medians over core wells)\n",
        f"lag = shift (weeks, |lag| ≤ {MAX_LAG}) of the best correlation between simulated "
        "and observed anomalies (> 0: simulation late); share_lag_le2 = share of wells with "
        f"|lag| ≤ 2; annual minimum = each calendar year with ≥ {MIN_YEAR_WEEKS} weeks in "
        "the period: |timing error| (weeks) and size error (m, < 0: simulated too low), the "
        "well's median over its years; trough = the lowest week of the whole period. Bias, "
        "sd ratio and correlation per well are in the main report (KGE'' components).\n",
        fmt(err[err["period"] == "test_drought"][ecols]).to_markdown(index=False), "",
        "## Representative hydrographs (rule, not hand-picked)\n",
        "Per aquifer group, the core well whose drought NSE averaged over every simulation "
        "run above is the group median: "
        + "; ".join(f"{g}: {c}" for g, c in picks.items())
        + f". Figure: `{fig.relative_to(ROOT)}`.\n",
    ]
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")
    pd.set_option("display.width", 220, "display.max_columns", 20)
    print(fmt(sgi[sgi["period"] == "test_drought"][cols]).to_string(index=False))
    print(fmt(err[err["period"] == "test_drought"][ecols]).to_string(index=False))
    print(f"observed SGI = dataset SGI on {len(chk):,} well-months (max gap {gap:.1e})")
    print("->", OUT_MD)
    print("->", fig)


if __name__ == "__main__":
    main()
