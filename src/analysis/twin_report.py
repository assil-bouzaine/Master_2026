"""Report of the semi-synthetic twin (src/models/twin.py) -> docs/results_twin_<dataset>.md.

    PFE_DATASET=v4 python -m src.analysis.twin_report                    # every twin run found
    PFE_DATASET=v4 python -m src.analysis.twin_report twin_pilot twin_pilot_conv

Written on 2026-11-16, before any world was scored, so that the tables are fixed in advance
(analysis plan §14 item 19 and its amendment). For every run, cell of dials and learner setting:
the realised dials; score 1 (median over core wells of log(RMSE_a / RMSE_C) in the drought, a = D
and the oracle T, and D against T); the drought NSE of each arm; score 2 (recovery of each
stress's contribution, RMSE in units of the well's noise-free sd); score 3 (share of wells with the
right pumping contribution); the RQ2 sign-violation rate; score 4 (error of the recharge mean lag, weeks); score 5 (the -20 %
intervention: median relative error, share of wells with the right sign); the seed disagreement
of the pumping contribution (shortcut test 2); score 6 (share of worlds with "wrong reasons": the
pumping recovery error above 0.5 while the drought NSE is within 0.1 of the oracle's); and the run
time. Each value is the median over the worlds of a cell with its range (min to max under 10
worlds, else 2.5-97.5 %). With several (eps, u) cells, the knowledge-value map of score 1.

Synthetic heads only: it says how the models behave under these generators, not what is true in
the aquifer (analysis plan §10).
"""
import json
import sys

import numpy as np
import pandas as pd

from src.config import DATASET, ROOT
from src.models.evaluate import RESULTS

OUT = ROOT / "docs" / f"results_twin_{DATASET}.md"
ARMS = ("C", "D", "T")
STRESSES = ("recharge", "pumping", "river", "canal")
WRONG_RECOVERY, WRONG_NSE = 0.5, 0.1


def load(runs=None):
    rows = []
    for f in sorted(RESULTS.glob("*/*/world_*.json")):
        run = f.parent.parent.name
        if (run not in runs) if runs else run.startswith("_"):    # "_" runs: checks, only by name
            continue
        rec = json.loads(f.read_text())
        for setting, s in rec["fits"].items():
            row = {"run": run, "cell": f.parent.name, "world": rec["world"], "setting": setting,
                   **{f"dial_{k}": v for k, v in rec["dials"].items()},
                   **{f"real_{k}": v for k, v in rec["realised"].items()}}
            for k, v in s.items():
                if isinstance(v, list):                       # steps per start
                    row[k] = float(np.median(v))
                else:
                    row[k] = np.nan if v is None else v
            for a in ARMS:
                if f"nse_drought_{a}" in s and "nse_drought_T" in s and s.get(f"recovery_pumping_{a}") is not None:
                    row[f"wrong_reasons_{a}"] = float(s[f"recovery_pumping_{a}"] > WRONG_RECOVERY
                                                      and abs(s[f"nse_drought_{a}"] - s["nse_drought_T"]) <= WRONG_NSE)
            rows.append(row)
    return pd.DataFrame(rows)


def summary(x):
    x = pd.to_numeric(x, errors="coerce").dropna()
    if not len(x):
        return "—"
    lo, hi = (x.min(), x.max()) if len(x) < 10 else (x.quantile(0.025), x.quantile(0.975))
    return f"{x.median():.3f} [{lo:.3f}, {hi:.3f}]"


def table(df, cols, names):
    out = ["| run | cell | setting | worlds | " + " | ".join(names) + " |",
           "|---|---|---|---:|" + "---:|" * len(names)]
    for (run, cell, setting), g in df.groupby(["run", "cell", "setting"], sort=True):
        out.append(f"| {run} | {cell} | {setting} | {g['world'].nunique()} | "
                   + " | ".join(summary(g[c]) if c in g else "—" for c in cols) + " |")
    return "\n".join(out)


PAYS = -0.05          # the smallest effect of interest (item 18; Gate 3 point 3)
BRACKET = {(0.1, 0.3), (0.1, 0.6), (0.25, 0.3), (0.25, 0.6)}   # cells around the real graph
PROTOCOLS = ("free", "pooled_l0.1_fixed3000")                    # early stopping, converged pooling
ACCURACY_SLACK = 0.05  # "not worse in accuracy by more than 0.05" (drought NSE of arm D)


def _q(x, q):
    x = pd.to_numeric(x, errors="coerce").dropna()
    return float(x.quantile(q)) if len(x) else np.nan


def reading(df):
    """The reading of the map fixed in analysis plan §14 item 19, point 10 (written 2026-11-16
    while the grid ran, before any world could be read). Operational choices, written here on
    2026-11-18 before the grid was complete and tested on hand-made tables only:
    (a) a cell "pays" when the median over worlds of D / C is at most PAYS and the 97.5 % quantile
        of D / C over its worlds is below 0;
    (b) the non-pumping part of D's gain: D / C in slice G (the truth takes arm C's recharge, river
        and canal routes) against the base cell of the grid (eps 0.1, u 0.3), same setting; and the
        change of D / C along each dial of the grid (median over the other dial's cells);
    (c) in a cell where D's median D / C is below 0, "right reasons" if D's median pumping recovery
        error is below C's, else "D more accurate for other reasons";
    (d) the bracket cells (eps 0.1 or 0.25, u 0.3 or 0.6): whether any pays;
    (e) the two protocols, cell by cell: which has the lower median pumping recovery error of arm D,
        and the median over cells of the difference in arm D's median drought NSE; the protocol
        better in most cells is recommended unless its NSE is lower by more than ACCURACY_SLACK;
    (f) RQ2 on the base cell and each slice, one at a time: arm D's sign-violation rate, its share of
        wells with the right sign of the cut, and D / T, under hard (setting "free"), none and soft.
    Returns markdown."""
    out = ["## Reading of the map (analysis plan §14 item 19, point 10)",
           "Rules fixed on 2026-11-16 before any world was read; the operational choices are in "
           "`twin_report.reading`. Synthetic heads only."]
    base = df[df["dial_variant"].isna() & (df["dial_timing"] == "reconstructed")
              & np.isclose(df["dial_pi"], 0.3) & np.isclose(df["dial_nu"], 0.25)]
    grid = base[base["run"] == "twin_map"] if "twin_map" in set(base["run"]) else base
    for setting, g in grid.groupby("setting"):
        cells = []
        for (e, u), c in g.groupby(["dial_eps", "dial_u"]):
            med, hi = c["log_rmse_D_over_C"].median(), _q(c["log_rmse_D_over_C"], 0.975)
            pays = bool(med <= PAYS and hi < 0)
            reason = "—"
            if med < 0:
                rd, rc = c["recovery_pumping_D"].median(), c["recovery_pumping_C"].median()
                reason = "right reasons" if rd < rc else "D more accurate for other reasons"
            cells.append({"eps": e, "u": u, "worlds": c["world"].nunique(), "median": med, "q97.5": hi,
                          "pays": pays, "reason": reason})
        t = pd.DataFrame(cells)
        lines = ["| ε | u | worlds | D / C median | 97.5 % | pays (a) | reasons (c) |",
                 "|---:|---:|---:|---:|---:|---|---|"]
        lines += [f"| {r.eps:g} | {r.u:g} | {r.worlds} | {r.median:.3f} | {r._5:.3f} | "
                  f"{'yes' if r.pays else 'no'} | {r.reason} |" for r in t.rename(columns={"q97.5": "_5"}).itertuples()]
        br = t[[(e, u) in BRACKET for e, u in zip(t["eps"], t["u"])]]
        verdict = ("at least one bracket cell pays: a real-data D vs C gain is possible"
                   if br["pays"].any() else
                   "no bracket cell pays: a real-data D vs C without a detected gain is the expected "
                   "outcome, not a failure of the graph")
        along = []
        for dial, other in (("eps", "u"), ("u", "eps")):
            s = t.groupby(dial)["median"].median()
            along.append(f"D / C along {dial} (median over {other}): "
                         + ", ".join(f"{k:g}: {v:.3f}" for k, v in s.items()))
        out.append(f"### Setting {setting}\n\n" + "\n".join(lines) + f"\n\n(d) {verdict} "
                   f"({len(br)} bracket cells present).\n\n(b) " + "; ".join(along) + ".")
        gslice = df[(df["dial_variant"] == "G") & (df["setting"] == setting)]
        b0 = g[np.isclose(g["dial_eps"], 0.1) & np.isclose(g["dial_u"], 0.3)]
        if len(gslice) and len(b0):
            out.append(f"(b) Slice G against the base cell: D / C {gslice['log_rmse_D_over_C'].median():.3f} "
                       f"(G, {gslice['world'].nunique()} worlds) against {b0['log_rmse_D_over_C'].median():.3f} "
                       "(base): the gain that stays in G is not credited to pumping knowledge.")
    # (e) the two protocols, cell by cell on the grid
    if all(p in set(grid["setting"]) for p in PROTOCOLS):
        rows, wins = [], {p: 0 for p in PROTOCOLS}
        for (e, u), c in grid.groupby(["dial_eps", "dial_u"]):
            rec = {p: c.loc[c["setting"] == p, "recovery_pumping_D"].median() for p in PROTOCOLS}
            nse = {p: c.loc[c["setting"] == p, "nse_drought_D"].median() for p in PROTOCOLS}
            if not all(np.isfinite(list(rec.values()))):
                continue
            best = min(PROTOCOLS, key=lambda p: rec[p])
            wins[best] += 1
            rows.append(nse[PROTOCOLS[0]] - nse[PROTOCOLS[1]])
        if rows:
            better = max(PROTOCOLS, key=lambda p: wins[p])
            other = [p for p in PROTOCOLS if p != better][0]
            d_nse = float(np.median(rows)) * (1 if better == PROTOCOLS[0] else -1)   # better minus other
            rec_txt = (f"{better} (lower pumping recovery error in {wins[better]} of {sum(wins.values())} "
                       f"cells; its drought NSE minus {other}'s: median {d_nse:+.3f})")
            ok = d_nse >= -ACCURACY_SLACK
            out.append(f"### (e) The two protocols\n\nBetter pumping recovery: {rec_txt}. "
                       + (f"Recommendation for Gate 3 point 1: **{better}**."
                          if ok else f"It loses more than {ACCURACY_SLACK} NSE: no recommendation by "
                          "this rule; Gate 3 weighs recovery against accuracy."))
    # (f) RQ2 on the base cell and each slice
    rq = df[np.isclose(df["dial_eps"], 0.1) & np.isclose(df["dial_u"], 0.3)
            & df["setting"].isin(("free", "free_none", "free_soft1"))]
    if rq["setting"].nunique() > 1:
        lines = ["| cell | setting | worlds | sign violations D | right cut sign D | D / T |",
                 "|---|---|---:|---:|---:|---:|"]
        for (cell, setting), c in rq.groupby(["cell", "setting"]):
            lines.append(f"| {cell} | {setting} | {c['world'].nunique()} | "
                         f"{summary(c.get('violation_rate_D', pd.Series(dtype=float)))} | "
                         f"{summary(c.get('intervention_sign_D', pd.Series(dtype=float)))} | "
                         f"{summary(c['log_rmse_D_over_T'])} |")
        out.append("### (f) RQ2: hard (\"free\"), none and soft, base cell and slices one at a time\n\n"
                   + "\n".join(lines))
    return "\n\n".join(out)


def main():
    runs = sys.argv[1:] or None
    df = load(runs)
    if df.empty:
        sys.exit("no twin world found")
    parts = [f"# The semi-synthetic twin: scores (generated)\n\nGenerated by `python -m "
             f"src.analysis.twin_report` (dataset **{DATASET}**); do not edit by hand. Design: "
             "`docs/analysis_plan.md` §14 item 19 and its amendment of 2026-11-16. **Synthetic heads "
             "only**: these numbers describe how the models behave under the twin's generators, not "
             "what is true in the aquifer. Each value: median over the worlds of a cell [range: min–max "
             "under 10 worlds, else 2.5–97.5 %]; inside a world, medians over the core wells scored in "
             "the drought phase. Arms: C distance rules, D knowledge graph (the export's tables), T the "
             "truth's own routing (oracle). Cell tag: e = ε, u, p = π, n = ν, timing, variant."]
    parts.append("## Realised dials\n\nu: share of the true pumping volume from pairs the graph does "
                 "not attribute (core wells with a true attributed pair); ε: share of the graph's "
                 "attributed pairs that are not true; π explained: share of the noise-free head's "
                 "training variance that the pumping contribution has.\n\n" + table(
                     df, ["real_u_median_core", "real_eps", "real_pi_explained_median_core",
                          "real_core_with_true_pumping", "real_core_with_attributed_pumping"],
                     ["u", "ε", "π explained", "core wells with true pumping", "with an attributed pair"]))
    parts.append("## Score 1: accuracy against arm C (log RMSE ratio, drought; negative = better than C)\n\n"
                 + table(df, ["log_rmse_D_over_C", "log_rmse_T_over_C", "log_rmse_D_over_T"],
                         ["D / C", "T / C (ceiling)", "D / T"]))
    parts.append("## Drought NSE of each arm\n\n" + table(
        df, [f"nse_drought_{a}" for a in ARMS] + [f"val_{a}" for a in ARMS],
        [f"NSE drought {a}" for a in ARMS] + [f"val. NSE {a}" for a in ARMS]))
    parts.append("## Score 2: recovery of the contributions (RMSE / noise-free sd, drought; 0 = exact)\n\n"
                 + table(df, [f"recovery_{s}_{a}" for s in STRESSES for a in ARMS],
                         [f"{s} {a}" for s in STRESSES for a in ARMS]))
    parts.append("## Scores 3–5 and seed disagreement\n\nScore 3: share of wells with true pumping whose "
                 "fitted pumping contribution correlates positively with the true one and has an sd "
                 "within a factor 2. Score 4: recharge mean-lag error, weeks. Score 5: true-edge "
                 "facilities −20 % in the drought, median relative error of the head change, share of "
                 "wells with its sign. Seed disagreement: RMSE between the two starts' pumping "
                 "contributions / noise-free sd. Sign violations (RQ2): share of core wells and "
                 "stresses whose fitted gain has the wrong sign (0 by construction under hard signs).\n\n" + table(
                     df, [f"pumping_right_{a}" for a in ARMS] + [f"lag_error_recharge_wk_{a}" for a in ARMS]
                     + [f"intervention_rel_error_{a}" for a in ARMS] + [f"intervention_sign_{a}" for a in ARMS]
                     + [f"seed_disagreement_pumping_{a}" for a in ARMS] + [f"violation_rate_{a}" for a in ARMS],
                     [f"right pumping {a}" for a in ARMS] + [f"lag error {a}" for a in ARMS]
                     + [f"cut error {a}" for a in ARMS] + [f"cut sign {a}" for a in ARMS]
                     + [f"seed disagr. {a}" for a in ARMS] + [f"sign violations {a}" for a in ARMS]))
    parts.append(f"## Score 6: worlds with wrong reasons\n\nShare of worlds where an arm's pumping recovery "
                 f"error exceeds {WRONG_RECOVERY} while its drought NSE is within {WRONG_NSE} of the "
                 "oracle's.\n\n" + table(df, [f"wrong_reasons_{a}" for a in ("C", "D")],
                                         ["C", "D"]))
    parts.append("## Run time\n\nSeconds per fit (all starts) and steps per start, Kaggle CPU, one thread.\n\n"
                 + table(df, [f"seconds_{a}" for a in ARMS] + [f"steps_{a}" for a in ARMS],
                         [f"s {a}" for a in ARMS] + [f"steps {a}" for a in ARMS]))
    base = df[(df["dial_variant"].isna()) & (df["dial_timing"] == "reconstructed")]
    if base.groupby(["dial_eps", "dial_u"]).ngroups > 1:
        for (run, setting), g in base.groupby(["run", "setting"]):
            m = g.groupby(["dial_eps", "dial_u"])["log_rmse_D_over_C"].apply(summary).unstack("dial_u")
            t = g.groupby(["dial_eps", "dial_u"])["log_rmse_T_over_C"].median().unstack("dial_u")
            lines = ["| ε \\ u | " + " | ".join(f"{u:g}" for u in m.columns) + " |",
                     "|---|" + "---:|" * len(m.columns)]
            lines += [f"| {e:g} | " + " | ".join(f"{m.loc[e, u]} (T {t.loc[e, u]:.3f})" for u in m.columns) + " |"
                      for e in m.index]
            parts.append(f"## Knowledge-value map: {run}, {setting}\n\nScore 1, D / C (and the oracle's "
                         "T / C), by the share of false links ε and the share of missed pumping u.\n\n"
                         + "\n".join(lines))
    if base.groupby(["dial_eps", "dial_u"]).ngroups > 1:
        parts.append(reading(df))
    OUT.write_text("\n\n".join(parts) + "\n")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
