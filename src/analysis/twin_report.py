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

Fixes of 2026-11-20 (astra review points 1, 5, 6 and 10), written before any cell of the complete
grid was read: score 5 per well (the plan's definition; worlds of scores version 2) is reported
apart from the plain-wide cut (the only version of the first worlds, renamed); score 6 is a count of
worlds (k of n), not a median of 0/1 flags; the reading's verdicts wait for complete cells (20
worlds), the bracket verdict for all four bracket cells, the protocol comparison pairs the worlds and
counts ties, and recommends only on a strict majority; the worlds of one cell must share their
settings (src.models.twin.identity), or the report stops.

Slice F has its own reading (analysis plan §14 item 23). It records the pilot's choice of φ,
uses the grid's seed-disagreement threshold, and compares the main F worlds to the base cell
on the same seeds.
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


def _plain_wide(s):
    """Scores version 1 cut the union of the true facilities only: its score 5 is the plain-wide
    one."""
    return {(k.replace("intervention_", "intervention_plain_", 1)
             if k.startswith(("intervention_rel_error_", "intervention_sign_")) else k): v for k, v in s.items()}


def load(runs=None):
    from src.models.twin import identity_diff
    rows, seen = [], {}
    for f in sorted(RESULTS.glob("*/*/world_*.json")):
        run = f.parent.parent.name
        if (run not in runs) if runs else run.startswith("_"):    # "_" runs: checks, only by name
            continue
        rec = json.loads(f.read_text())
        config = rec.get("config", {})
        for other in seen.setdefault((run, f.parent.name), []):
            if identity_diff(other, config):
                raise SystemExit(f"{f}: its settings differ from the other worlds of {run}/{f.parent.name} "
                                 f"({', '.join(identity_diff(other, config))}; src.models.twin.identity); "
                                 "a cell must not mix experiments")
        if not any(c == config for c in seen[(run, f.parent.name)]):
            seen[(run, f.parent.name)].append(config)
        version = rec.get("scores_version", 1)
        for setting, s in rec["fits"].items():
            if version == 1:
                s = _plain_wide(s)
            row = {"run": run, "cell": f.parent.name, "world": rec["world"], "setting": setting,
                   "scores_version": version,
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


def summary(x, *, always_quantiles=False):
    x = pd.to_numeric(x, errors="coerce").dropna()
    if not len(x):
        return "—"
    lo, hi = (x.quantile(0.025), x.quantile(0.975)) if always_quantiles or len(x) >= 10 else (x.min(), x.max())
    return f"{x.median():.3f} [{lo:.3f}, {hi:.3f}]"


def count(x, *, share=True):
    """A 0/1 flag over worlds -> "k of n (share)", n = the worlds where the flag can be evaluated
    (astra review point 5: a median of 0/1 flags hides the share)."""
    x = pd.to_numeric(x, errors="coerce").dropna()
    if not len(x):
        return "—"
    return f"{int(x.sum())} of {len(x)}" + (f" ({x.mean():.0%})" if share else "")


def table(df, cols, names, fmt=summary, evaluable=None):
    """One row per run, cell and setting; `evaluable`: a column whose non-missing worlds are counted
    in an extra column (when a score exists in some worlds only)."""
    extra = ["worlds with it"] if evaluable else []
    out = ["| run | cell | setting | worlds | " + " | ".join(extra + names) + " |",
           "|---|---|---|---:|" + "---:|" * len(extra + names)]
    for (run, cell, setting), g in df.groupby(["run", "cell", "setting"], sort=True):
        ev = [str(int(g[evaluable].notna().sum()) if evaluable in g else 0)] if evaluable else []
        out.append(f"| {run} | {cell} | {setting} | {g['world'].nunique()} | "
                   + " | ".join(ev + [fmt(g[c]) if c in g else "—" for c in cols]) + " |")
    return "\n".join(out)


PAYS = -0.05          # the smallest effect of interest (item 18; Gate 3 point 3)
BRACKET = {(0.1, 0.3), (0.1, 0.6), (0.25, 0.3), (0.25, 0.6)}   # cells around the real graph
PLANNED_WORLDS = 20   # worlds per cell (item 19); a verdict waits for all of them
GRID_CELLS = 12       # eps in {0, 0.1, 0.25, 0.5} x u in {0, 0.3, 0.6}
PROTOCOLS = ("free", "pooled_l0.1_fixed3000")                    # early stopping, converged pooling
ACCURACY_SLACK = 0.05  # "not worse in accuracy by more than 0.05" (drought NSE of arm D)
SEED_FLAG_Q = 0.95     # shortcut test 2 flags a world above this quantile of the grid's (item 22)
GRID_RUN = "twin_map"  # the base grid: the reference of worlds without wrong reasons
MIN_POSITIVES = 5      # under this many worlds with wrong reasons, detection is "not estimable"
BASE_CELL = "e0.1_u0.3_p0.3_n0.25_rec_base"
SHORTCUT_PILOT = "twin_shortcut_pilot"
SHORTCUT_PILOT_SEEDS = (900, 901, 902)


def seed_thresholds(df, *, arms=("C", "D")):
    """Shortcut test 2's flag threshold τ per (arm, setting): the 95th percentile (numpy's default
    linear interpolation) of the seed disagreement over the base grid's worlds of that arm and
    setting (analysis plan §14 item 22, proposed before kernel version 13 was pulled). The grid's
    generator lies inside the learner's model class and no grid world has wrong reasons, so it is
    the reference of known negatives: a nominal 5 % false-alarm rate there by construction."""
    out = {}
    grid = df[df["run"] == GRID_RUN] if "run" in df else df.iloc[0:0]
    for setting, g in grid.groupby("setting"):
        for a in arms:
            col = f"seed_disagreement_pumping_{a}"
            x = pd.to_numeric(g[col], errors="coerce").dropna() if col in g else pd.Series(dtype=float)
            if len(x):
                out[(a, setting)] = (float(np.quantile(x.to_numpy(), SEED_FLAG_Q)), len(x))
    return out


def test2_rates(df, tau, *, arms=("C", "D")):
    """Detection and false-alarm rates of shortcut test 2 per run, cell and setting (item 22):
    flagged = seed disagreement above τ of its arm and setting; detection = flagged among the
    worlds with wrong reasons (score 6), false alarm = flagged among the others."""
    out = ["| run | cell | setting | arm | τ | worlds | wrong reasons | detection | false alarms |",
           "|---|---|---|---|---:|---:|---:|---:|---:|"]
    for (run, cell, setting), g in df.groupby(["run", "cell", "setting"], sort=True):
        for a in arms:
            w, sd = f"wrong_reasons_{a}", f"seed_disagreement_pumping_{a}"
            if (a, setting) not in tau or w not in g or sd not in g:
                continue
            t = tau[(a, setting)][0]
            x = g[[w, sd]].apply(pd.to_numeric, errors="coerce").dropna()
            if not len(x):                    # no world of this cell can be judged for the arm
                continue
            flag = x[sd] > t
            pos, neg = x[w] == 1, x[w] == 0
            k, n = int(flag[pos].sum()), int(pos.sum())
            det = ("no positive case" if n == 0 else
                   f"{k} of {n}" + (" (not estimable)" if n < MIN_POSITIVES else f" ({k / n:.0%})"))
            fa = f"{int(flag[neg].sum())} of {int(neg.sum())}" + (f" ({flag[neg].mean():.0%})" if neg.any() else "")
            out.append(f"| {run} | {cell} | {setting} | {a} | {t:.3f} | {len(x)} | {n} | {det} | {fa} |")
    return "\n".join(out)


def test2_section(df):
    """The report's text for test 2's flag (item 22): τ, then the rates per cell."""
    tau = seed_thresholds(df)
    if not tau:
        return ("\n\nTest 2's flag: no base-grid world with a seed disagreement in these runs, so τ "
                "(item 22) cannot be computed; add the run `twin_map`.")
    full = PLANNED_WORLDS * GRID_CELLS
    taus = "; ".join(f"{a}, {s}: τ = {t:.3f} ({n} grid worlds"
                     + ("" if n >= full else f", **interim: {n} of {full}**") + ")"
                     for (a, s), (t, n) in sorted(tau.items()))
    return (f"\n\nTest 2's flag (analysis plan §14 item 22, fixed before kernel version 13 was pulled): a "
            f"world is flagged when its seed disagreement is above τ, the {SEED_FLAG_Q:.0%} quantile of "
            f"the base grid's worlds of the same arm and setting ({taus}). Detection = flagged among the "
            "worlds with wrong reasons; false alarms = flagged among the others (nominally 5 % on the "
            f"grid itself, by construction); under {MIN_POSITIVES} worlds with wrong reasons the "
            "detection rate is not estimable.\n\n" + test2_rates(df, tau))


def _q(x, q):
    x = pd.to_numeric(x, errors="coerce").dropna()
    return float(x.quantile(q)) if len(x) else np.nan


def _median(x, fmt=".3f"):
    med = _q(x, 0.5)
    return format(med, fmt) if pd.notna(med) else "—"


def _shortcut_scores(cell):
    """One row per protocol and arm, using the per-well cut recorded in scores version 2."""
    lines = ["| protocol | worlds | arm | score 6 | pumping recovery error | drought NSE | "
             "score 5 head-change relative error | score 5 wells with right sign |",
             "|---|---:|---|---:|---:|---:|---:|---:|"]
    missing = pd.Series(dtype=float)
    for setting, g in cell.groupby("setting"):
        for a in ARMS:
            wrong = count(g.get(f"wrong_reasons_{a}", missing), share=False)
            recovery = summary(g.get(f"recovery_pumping_{a}", missing), always_quantiles=True)
            nse = _median(g.get(f"nse_drought_{a}", missing))
            rel_error = _median(g.get(f"intervention_well_rel_error_{a}", missing))
            sign = _median(g.get(f"intervention_well_sign_{a}", missing))
            lines.append(f"| {setting} | {g['world'].nunique()} | {a} | {wrong} | {recovery} | {nse} | "
                         f"{rel_error} | {sign} |")
    return "\n".join(lines)


def _shortcut_pilot(cell):
    """Count a pilot seed once if either protocol gives arm D wrong reasons."""
    flags = cell.pivot(index="world", columns="setting", values="wrong_reasons_D").reindex(
        index=SHORTCUT_PILOT_SEEDS, columns=PROTOCOLS)
    wrong = flags.eq(1)
    k = int(wrong.any(axis=1).sum())
    counts = ", ".join(f"{p}: {int(wrong[p].sum())}" for p in PROTOCOLS)
    if k:
        worlds = "world" if k == 1 else "worlds"
        return (f"The pilot has {k} {worlds} with wrong reasons for arm D (protocol {counts}): "
                "the 20 worlds use φ = 1.0.")
    if flags.isna().any().any():
        return "The pilot choice is pending until score 6 for arm D is available for all three seeds under both protocols."
    return (f"The pilot has no worlds with wrong reasons for arm D (protocol {counts}): "
            "by the rule, the 20 worlds use φ = 2.0.")


def _shortcut_comparison(cells, df):
    """Compare each main F cell to the grid's base cell on the same seeds and protocol."""
    line = "### Arm D against the base cell\n\nMedian change over matching seeds 0–19 (slice F minus base)."
    keys = ["setting", "world"]
    scores = ["recovery_pumping_D", "nse_drought_D"]
    base = df[(df["run"] == GRID_RUN) & (df["cell"] == BASE_CELL)].reindex(columns=keys + scores)
    lines = ["| cell | protocol | paired worlds | change in pumping recovery error | change in drought NSE |",
             "|---|---|---:|---:|---:|"]
    for (cell, setting), g in cells.groupby(["cell", "setting"]):
        g = g[g["world"].between(0, PLANNED_WORLDS - 1)].reindex(columns=keys + scores)
        paired = g.merge(base, on=keys, suffixes=("", "_base"), validate="one_to_one")
        rec, nse = (_median(paired[s] - paired[f"{s}_base"], "+.3f") for s in scores)
        lines.append(f"| {cell} | {setting} | {len(paired)} | {rec} | {nse} |")
    return line + "\n\n" + "\n".join(lines)


def shortcut_section(df):
    """Read each F cell alone, with the pilot rule and matched base comparison of item 23."""
    if "dial_variant" not in df:
        return ""
    f = df[df["dial_variant"].astype("string").str.startswith("F", na=False)]
    if f.empty:
        return ""
    out = ["## Slice F: the planted shortcut (analysis plan §14 item 23)",
           "Scores are medians over worlds, with the 2.5–97.5 % range for score 2. Score 5 cuts each "
           "well's own true facilities. Score 6 counts worlds with wrong reasons among evaluable worlds."]
    fields = ["real_far_explained_median_core", "real_far_facilities_median_core",
              "real_far_local_pumping_corr_median_core", "real_core_with_far"]
    labels = ["far-field variance share", "far-field facilities per core well",
              "correlation with local pumping", "core wells with far-field facilities"]
    for (run, cell, variant), g in f.groupby(["run", "cell", "dial_variant"], sort=False):
        out.append(f"### {run} / {cell} (φ = {variant[1:]})\n\n" + _shortcut_scores(g))
        if run == SHORTCUT_PILOT:
            out.append(_shortcut_pilot(g.reindex(columns=["world", "setting", "wrong_reasons_D"])))
        out.append("Realised generator fields (median over worlds):\n\n" + table(g, fields, labels, fmt=_median))
    tau = seed_thresholds(df, arms=ARMS)
    if tau:
        out.append("### Shortcut test 2\n\nThresholds (τ) come from the grid for each arm and protocol.\n\n"
                   + test2_rates(f, tau, arms=ARMS))
    else:
        out.append("Test 2 needs seed disagreement from `twin_map` to compute τ.")
    main = f[f["run"] == "twin_shortcut"]
    if not main.empty:
        out.append(_shortcut_comparison(main, df))
    return "\n\n".join(out)


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
            n = c["world"].nunique()
            complete = n >= PLANNED_WORLDS
            pays = bool(med <= PAYS and hi < 0) if complete else None
            reason = "—"
            if med < 0:
                rd, rc = c["recovery_pumping_D"].median(), c["recovery_pumping_C"].median()
                reason = "right reasons" if rd < rc else "D more accurate for other reasons"
            label = ("yes" if pays else "no") if complete else f"pending ({n} of {PLANNED_WORLDS} worlds)"
            cells.append({"eps": e, "u": u, "worlds": n, "median": med, "q97.5": hi,
                          "pays": pays, "label": label, "reason": reason})
        t = pd.DataFrame(cells)
        lines = ["| ε | u | worlds | D / C median | 97.5 % | pays (a) | reasons (c) |",
                 "|---:|---:|---:|---:|---:|---|---|"]
        lines += [f"| {r.eps:g} | {r.u:g} | {r.worlds} | {r.median:.3f} | {r._5:.3f} | "
                  f"{r.label} | {r.reason} |" for r in t.rename(columns={"q97.5": "_5"}).itertuples()]
        br = t[[(e, u) in BRACKET for e, u in zip(t["eps"], t["u"])]]
        done = br[br["pays"].notna()]
        if (done["pays"] == True).any():                              # noqa: E712 (object column)
            verdict = "at least one bracket cell pays: a real-data D vs C gain is possible"
        elif len(done) == len(BRACKET):
            verdict = ("no bracket cell pays: a real-data D vs C without a detected gain is the expected "
                       "outcome, not a failure of the graph")
        else:
            verdict = (f"pending: {len(done)} of {len(BRACKET)} bracket cells complete "
                       f"({PLANNED_WORLDS} worlds each), none pays so far")
        along = []
        for dial, other in (("eps", "u"), ("u", "eps")):
            s = t.groupby(dial)["median"].median()
            along.append(f"D / C along {dial} (median over {other}): "
                         + ", ".join(f"{k:g}: {v:.3f}" for k, v in s.items()))
        out.append(f"### Setting {setting}\n\n" + "\n".join(lines) + f"\n\n(d) {verdict} "
                   f"({len(br)} of {len(BRACKET)} bracket cells present).\n\n(b) " + "; ".join(along) + ".")
        gslice = df[(df["dial_variant"] == "G") & (df["setting"] == setting)]
        b0 = g[np.isclose(g["dial_eps"], 0.1) & np.isclose(g["dial_u"], 0.3)]
        if len(gslice) and len(b0):
            ng = gslice["world"].nunique()
            interim = "" if ng >= PLANNED_WORLDS else f" Interim: slice G has {ng} of {PLANNED_WORLDS} worlds."
            out.append(f"(b) Slice G against the base cell: D / C {gslice['log_rmse_D_over_C'].median():.3f} "
                       f"(G, {ng} worlds) against {b0['log_rmse_D_over_C'].median():.3f} "
                       "(base): the gain that stays in G is not credited to pumping knowledge." + interim)
    # (e) the two protocols, cell by cell on the grid, over the worlds both protocols have
    if all(p in set(grid["setting"]) for p in PROTOCOLS):
        rows, wins, ties, short = [], {p: 0 for p in PROTOCOLS}, 0, 0
        for (e, u), c in grid.groupby(["dial_eps", "dial_u"]):
            paired = set.intersection(*(set(c.loc[c["setting"] == p, "world"]) for p in PROTOCOLS))
            c = c[c["world"].isin(paired)]
            short += len(paired) < PLANNED_WORLDS
            rec = {p: c.loc[c["setting"] == p, "recovery_pumping_D"].median() for p in PROTOCOLS}
            nse = {p: c.loc[c["setting"] == p, "nse_drought_D"].median() for p in PROTOCOLS}
            if not paired or not all(np.isfinite(list(rec.values()))):
                continue
            if rec[PROTOCOLS[0]] == rec[PROTOCOLS[1]]:
                ties += 1
            else:
                wins[min(PROTOCOLS, key=lambda p: rec[p])] += 1
            rows.append(nse[PROTOCOLS[0]] - nse[PROTOCOLS[1]])
        n = len(rows)
        counts = (f"lower pumping recovery error of arm D: {PROTOCOLS[0]} in {wins[PROTOCOLS[0]]} cells, "
                  f"{PROTOCOLS[1]} in {wins[PROTOCOLS[1]]}, tied in {ties}, of {n} compared cells")
        if n < GRID_CELLS or short:
            out.append(f"### (e) The two protocols\n\nPending: {n} of {GRID_CELLS} cells compared, "
                       f"{short} with fewer than {PLANNED_WORLDS} paired worlds ({counts}). No "
                       "recommendation before the grid is complete.")
        else:
            better = max(PROTOCOLS, key=lambda p: wins[p])
            other = [p for p in PROTOCOLS if p != better][0]
            d_nse = float(np.median(rows)) * (1 if better == PROTOCOLS[0] else -1)   # better minus other
            if wins[better] * 2 <= n:
                out.append(f"### (e) The two protocols\n\nNo protocol has a strict majority of the cells "
                           f"({counts}): no recommendation by this rule; Gate 3 weighs recovery against "
                           "accuracy.")
            else:
                ok = d_nse >= -ACCURACY_SLACK
                out.append(f"### (e) The two protocols\n\nBetter pumping recovery: {better} ({counts}; its "
                           f"drought NSE minus {other}'s: median {d_nse:+.3f}). "
                           + (f"Recommendation for Gate 3 point 1: **{better}**."
                              if ok else f"It loses more than {ACCURACY_SLACK} NSE: no recommendation by "
                              "this rule; Gate 3 weighs recovery against accuracy."))
    # (f) RQ2 on the base cell and each slice: from twin_rq2 alone when it holds the three settings
    # on the same worlds (since 2026-11-20 it fits hard as well, with score 5 per well)
    settings = ("free", "free_none", "free_soft1")
    rq = df[np.isclose(df["dial_eps"], 0.1) & np.isclose(df["dial_u"], 0.3) & df["setting"].isin(settings)]
    if "twin_rq2" in set(rq["run"]) and set(rq.loc[rq["run"] == "twin_rq2", "setting"]) == set(settings):
        rq = rq[rq["run"] == "twin_rq2"]
    if rq["setting"].nunique() > 1:
        cut = "intervention_well_sign_D"
        lines = ["| run | cell | setting | worlds | sign violations D | worlds with score 5 per well | "
                 "right cut sign D (per well) | D / T |", "|---|---|---|---:|---:|---:|---:|---:|"]
        for (run, cell, setting), c in rq.groupby(["run", "cell", "setting"]):
            has = c[cut] if cut in c else pd.Series(dtype=float)
            lines.append(f"| {run} | {cell} | {setting} | {c['world'].nunique()} | "
                         f"{summary(c.get('violation_rate_D', pd.Series(dtype=float)))} | "
                         f"{int(has.notna().sum())} | {summary(has)} | {summary(c['log_rmse_D_over_T'])} |")
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
    parts.append("## Scores 3, 4 and seed disagreement\n\nScore 3: share of wells with true pumping whose "
                 "fitted pumping contribution correlates positively with the true one and has an sd "
                 "within a factor 2. Score 4: recharge lag error, weeks: |a·n fitted − a·n true|, the "
                 "means of the continuous Gamma laws (the model's kernels are weekly, truncated and "
                 "normalised, so these are not the implemented mean delays; astra review point 8). "
                 "Seed disagreement: RMSE between the two starts' pumping "
                 "contributions / noise-free sd. Sign violations (RQ2): share of core wells and "
                 "stresses whose fitted gain has the wrong sign (0 by construction under hard signs).\n\n" + table(
                     df, [f"pumping_right_{a}" for a in ARMS] + [f"lag_error_recharge_wk_{a}" for a in ARMS]
                     + [f"seed_disagreement_pumping_{a}" for a in ARMS] + [f"violation_rate_{a}" for a in ARMS],
                     [f"right pumping {a}" for a in ARMS] + [f"lag error {a}" for a in ARMS]
                     + [f"seed disagr. {a}" for a in ARMS] + [f"sign violations {a}" for a in ARMS]))
    parts.append("## Score 5: a −20 % cut of true-edge facilities in the drought\n\nMedian relative error of "
                 "the fitted head change against the true one, and share of wells with its sign. **Per "
                 "well** (the plan's definition, score of record; worlds of scores version 2): each "
                 "well's own true facilities, one well at a time. **Plain-wide** (descriptive; the only "
                 "version of the first worlds): every well's true facilities cut at once, so an arm's "
                 "links to facilities true for other wells move its prediction too.\n\n" + table(
                     df, [f"intervention_well_rel_error_{a}" for a in ARMS] + [f"intervention_well_sign_{a}" for a in ARMS],
                     [f"error {a}" for a in ARMS] + [f"sign {a}" for a in ARMS],
                     evaluable="intervention_well_rel_error_D")
                 + "\n\nPlain-wide:\n\n" + table(
                     df, [f"intervention_plain_rel_error_{a}" for a in ARMS] + [f"intervention_plain_sign_{a}" for a in ARMS],
                     [f"error {a}" for a in ARMS] + [f"sign {a}" for a in ARMS],
                     evaluable="intervention_plain_rel_error_D"))
    cond = df.copy()
    for a in ("C", "D"):
        w, sd = f"wrong_reasons_{a}", f"seed_disagreement_pumping_{a}"
        if w in cond and sd in cond:
            cond[f"sd_wrong_{a}"] = cond[sd].where(cond[w] == 1)
            cond[f"sd_right_{a}"] = cond[sd].where(cond[w] == 0)
    parts.append(f"## Score 6: worlds with wrong reasons\n\nWorlds where an arm's pumping recovery error "
                 f"exceeds {WRONG_RECOVERY} while its drought NSE is within {WRONG_NSE} of the oracle's: "
                 "k of n evaluable worlds (share).\n\n" + table(df, [f"wrong_reasons_{a}" for a in ("C", "D")],
                                                                ["C", "D"], fmt=count)
                 + "\n\nShortcut test 2 (seed disagreement of the pumping contribution) in the worlds with "
                 "and without wrong reasons.\n\n"
                 + table(cond, [c for a in ("C", "D") for c in (f"sd_wrong_{a}", f"sd_right_{a}")],
                         [f"{a}: {k}" for a in ("C", "D") for k in ("wrong reasons", "right reasons")])
                 + test2_section(df))
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
    shortcut = shortcut_section(df)
    if shortcut:
        parts.append(shortcut)
    OUT.write_text("\n\n".join(parts) + "\n")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
