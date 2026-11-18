"""Read the planned Phase 4 contrasts (analysis plan §6, §10 and §14 items 18, 20).

    PFE_DATASET=v4 python -m src.analysis.arms_report [--config configs/phase4_contrasts_dev.json]

Compare the drought log RMSE ratio on core wells. Negative values favour arm a.
Apply Holm within each declared family and regime × reconstruction cell.
Detection requires p_holm < alpha, an interval excluding zero, and a median
outside both same-arm bands. A detected effect at or above the absolute
smallest effect is reported separately from a smaller detected effect. Otherwise
a whole interval strictly inside the smallest-effect bounds gives "no effect of
interest". All other results are undecided, with the compatible interval shown.

Use R1 validation to select each reconstruction's soft penalty. Carry that
setting into R2 as fixed-configuration transfer. Show the graph draws' range
and the same-arm band as separate sources of variation.
"""
import argparse
from collections import defaultdict
from functools import cached_property
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.analysis import ladder_report as ladder, stats
from src.config import DATASET, ROOT
from src.models.evaluate import DS, MIN_WEEKS, RESULTS, score

CONFIG = ROOT / "configs" / "phase4_contrasts.json"
DEV_CONFIG = CONFIG.with_name("phase4_contrasts_dev.json")
REGIME_NAMES = {"": "R1", "_lwo": "R2", "_f25": "R3 25%", "_f50": "R3 50%", "_refit": "Refit"}
METRICS = ("NSE", "skill", "KGE", "RMSE")
EFFECT = "median log(RMSE a / RMSE b)"
DETECTED = "detected, at least the smallest effect"
SMALL = "detected, below the smallest effect"
NO_EFFECT = "no effect of interest"
UNDECIDED = "undecided"
PLAN_STARTS = 10


class SavedRuns:
    """Read saved scores and reconstruct held-out predictions in memory when needed."""

    def __init__(self, results=RESULTS):
        self.results = results
        self._metrics = {}
        self._bands = {}
        self._scaling = {}

    @cached_property
    def wells(self):
        return pd.read_parquet(DS / "wells.parquet")

    @cached_property
    def splits(self):
        return json.loads((DS / "splits.json").read_text())

    @cached_property
    def observed(self):
        return ladder.drought_support()

    def scale(self, regime):
        window = regime.removeprefix("_") if regime in ("_f25", "_f50") else ""
        if window not in self._scaling:
            panel = self.results / "_cache" / (f"panel_{window}.parquet" if window else "panel.parquet")
            if panel.is_file():
                scale = pd.read_parquet(panel, columns=["code_bss", "mu", "sd"]).drop_duplicates("code_bss")
                scale = scale.set_index("code_bss")
            else:
                # Match the unscreened weekly heads and training window of features.build_panel.
                start, end = self.splits["train"]
                if window:
                    start = self.splits["r3_starts"][window]
                h = pd.read_parquet(DS / "heads_weekly.parquet", columns=["code_bss", "week", "head"])
                scale = (h.loc[h["week"].between(start, end)].groupby("code_bss")["head"]
                         .agg(mu="mean", sd="std"))
            self._scaling[window] = scale
        return self._scaling[window]

    def seed_frames(self, path, regime):
        files = sorted(path.glob("seed_*.parquet"))
        if not files:
            return {}
        if (regime not in ("_f25", "_f50") and self.results == ladder.RESULTS
                and (self.results / "_cache" / "panel.parquet").is_file()):
            return ladder.seed_frames(str(path.relative_to(self.results)))
        scale = self.scale(regime)
        frames = {}
        for file in files:
            z = pd.read_parquet(file).join(scale, on="code_bss")
            frames[int(file.stem.split("_")[1])] = (z.assign(pred=z["mu"] + z["sd"] * z["z"],
                                                              task="simulation", horizon=0)
                                                    [["code_bss", "week", "pred", "task", "horizon"]]
                                                    .dropna(subset=["pred"]))
        return frames

    def frames(self, run, regime):
        path = self.results / run
        if regime != "_lwo":
            return self.seed_frames(path, regime)
        split = self.splits["leave_wells_out"]
        fold_of = split["fold_of_well"]
        folds = [self.seed_frames(path / f"fold_{k}", regime) for k in range(split["n_folds"])]
        seeds = set(folds[0])
        if not seeds or any(set(fold) != seeds for fold in folds):
            return {}
        return {seed: pd.concat([fold[seed].loc[fold[seed]["code_bss"].map(fold_of).eq(k)]
                                 for k, fold in enumerate(folds)], ignore_index=True)
                for seed in sorted(seeds)}

    def metrics(self, run, regime):
        key = run, regime
        if key not in self._metrics:
            path = self.results / run
            saved, pred_file = path / "metrics_per_well.csv", path / "predictions.parquet"
            table = None
            if saved.is_file():
                table = pd.read_csv(saved)
            elif pred_file.is_file():
                table = score(pd.read_parquet(pred_file))
            elif regime == "_lwo":
                frames = self.frames(run, regime)
                if frames and (not run.startswith("p4_") or len(frames) == PLAN_STARTS):
                    pred = (pd.concat(frames.values()).groupby(["code_bss", "week", "task", "horizon"],
                                                              as_index=False)["pred"].mean())
                    table = score(pred)
            self._metrics[key] = table
        return self._metrics[key]

    def band(self, run, regime, metrics):
        key = run, regime
        if key not in self._bands:
            frames = self.frames(run, regime)
            bounds = None
            if len(frames) >= 4 and (not run.startswith("p4_") or len(frames) == PLAN_STARTS):
                codes = ladder.per_well(metrics, metric="RMSE").dropna().index
                obs = self.observed.loc[:, self.observed.columns.intersection(codes)]
                # Keep the same observed weeks in both halves, and avoid unscorable wells.
                for frame in frames.values():
                    available = frame.pivot(index="week", columns="code_bss", values="pred")
                    obs = obs.where(np.isfinite(available.reindex_like(obs)))
                obs = obs.loc[:, obs.notna().sum() >= MIN_WEEKS]
                if len(obs.columns):
                    lo, hi, _ = ladder.band(frames, obs, self.wells, np.random.default_rng(2026))
                    if np.isfinite([lo, hi]).all():
                        bounds = (lo, hi)
            self._bands[key] = bounds, len(frames)
        return self._bands[key]

    def coverage(self, run, regime):
        path = self.results / run
        if regime != "_lwo":
            return _coverage(path)
        folds = [_coverage(path / f"fold_{k}") for k in range(self.splits["leave_wells_out"]["n_folds"])]
        if not any(folds):
            return _coverage(path)
        if all(value == folds[0] for value in folds):
            return "all folds: " + folds[0]
        return "<br>".join(f"fold {k}: {value or 'unavailable'}" for k, value in enumerate(folds))


def _coverage(path):
    schema = path / "schema.json"
    relations = json.loads(schema.read_text()).get("wells_with_relation", {}) if schema.is_file() else {}
    counts = []
    for name, value in sorted(relations.items()):
        if isinstance(value, dict):
            core = f" ({value['core_wells']} core)" if "core_wells" in value else ""
            value = f"{value['wells']}{core}"
        counts.append(f"{name} {value}")
    return ", ".join(counts)


def union_band(a, b):
    if a is None or b is None:
        return None
    first, second = sorted((a, b))
    if first[1] >= second[0]:
        return ((first[0], max(first[1], second[1])),)
    return first, second


def classify(median, interval, union, p_holm, smallest_effect=0.05, alpha=0.05):
    lo, hi = interval
    excludes_zero = np.isfinite(interval).all() and lo <= hi and (lo > 0 or hi < 0)
    outside = union is not None and np.isfinite(median) and all(
        median < start or median > end for start, end in union)
    if p_holm is not None and p_holm < alpha and excludes_zero and outside:
        return DETECTED if abs(median) >= smallest_effect else SMALL
    if -smallest_effect < lo <= hi < smallest_effect:
        return NO_EFFECT
    return UNDECIDED


def aggregate_draws(rows):
    effects = [row[EFFECT] for row in rows if np.isfinite(row[EFFECT])]
    if not effects:
        return {"n": 0, "median": np.nan, "range": (np.nan, np.nan), "width": np.nan, "ratio": np.nan}
    lo, hi = min(effects), max(effects)
    band = rows[0]["band_a"]
    width = band[1] - band[0] if band is not None else np.nan
    return {"n": len(effects), "median": np.median(effects), "range": (lo, hi), "width": width,
            "ratio": (hi - lo) / width if width > 0 else np.nan}


def reconstruction_agreement(rows, reconstructions):
    classes, keys = {}, {}
    for row in rows:
        reconstruction, classification = row["reconstruction"], row["classification"]
        label, key = classification, classification
        if classification in (DETECTED, SMALL):
            favours = "a" if row[EFFECT] < 0 else "b"
            label += f" (favours {favours})"
            key = ("detected", favours)
        classes[reconstruction], keys[reconstruction] = label, key
    missing = [r for r in reconstructions if r not in classes]
    if missing:
        return "Incomplete. Missing " + ", ".join(map(str, missing))
    detail = ", ".join(f"({r}) {classes[r]}" for r in reconstructions)
    return ("Yes. " if len({keys[r] for r in reconstructions}) == 1 else "Depends on reconstruction. ") + detail


def adjust_families(rows):
    cells = defaultdict(list)
    for row in rows:
        cells[row["family"], row["regime"], row["reconstruction"]].append(row)
    for cell in cells.values():
        for row, adjusted in zip(cell, stats.holm([row["p_cluster"] for row in cell])):
            row["p_holm"] = adjusted


def _run_name(stem, regime, reconstruction):
    if reconstruction != 1:
        if not stem.endswith("_r1"):
            raise ValueError(f"missing reconstruction suffix in {stem}")
        stem = stem.removesuffix("_r1") + f"_r{reconstruction}"
    return stem + regime


def _cases(config, spec):
    for regime in spec.get("regimes", config["regimes"]):
        for reconstruction in spec.get("reconstructions", config["reconstructions"]):
            yield regime, reconstruction


def _compare(runs, spec, a, b, regime, reconstruction, missing, *, family=None, draw=None):
    ma, mb = runs.metrics(a, regime), runs.metrics(b, regime)
    unavailable = [name for name, m in ((a, ma), (b, mb)) if m is None]
    if unavailable:
        missing.update(unavailable)
        return None
    if family is not None:
        try:
            stats.paired(ma, mb, runs.wells, metric="RMSE", strict=True)
        except ValueError as error:
            raise ValueError(f"{a} vs {b}: {error}") from error
    values = ladder.contrast(ma, mb, runs.wells)
    band_a, starts_a = runs.band(a, regime, ma)
    band_b, starts_b = runs.band(b, regime, mb)
    return values | {"name": spec["name"], "family": family, "a": a, "b": b, "regime": regime,
                     "reconstruction": reconstruction, "draw": draw, "band_a": band_a, "band_b": band_b,
                     "starts_a": starts_a, "starts_b": starts_b, "union": union_band(band_a, band_b),
                     "p_holm": np.nan,
                     "scores_a": tuple(ladder.per_well(ma, metric=metric).median() for metric in METRICS),
                     "scores_b": tuple(ladder.per_well(mb, metric=metric).median() for metric in METRICS),
                     "coverage_requested": bool(spec.get("coverage")),
                     "coverage_a": runs.coverage(a, regime) if spec.get("coverage") else "",
                     "coverage_b": runs.coverage(b, regime) if spec.get("coverage") else ""}


def _select_soft(runs, stem, reconstruction, declared, missing):
    entries = []
    for setting in declared:
        run = _run_name(stem.format(best=setting), "", reconstruction)
        table = runs.metrics(run, "")
        val = ladder.per_well(table, split="validation").median() if table is not None else np.nan
        if not np.isfinite(val):
            missing.add(run + (" (no core validation NSE)" if table is not None else ""))
        entries.append((setting, run, val))
    if any(not np.isfinite(v) for _, _, v in entries):
        return None, entries
    return max(entries, key=lambda entry: entry[2])[0], entries


def compute(config, runs):
    """Evaluate declared cases in order, recording every run still needed."""
    missing, families, exploratory, controls, selections = set(), [], [], [], {}
    groups = [(name, spec) for name, specs in config["families"].items() for spec in specs]
    groups += [(None, spec) for spec in config.get("exploratory", [])]
    for family, spec in groups:
        for regime, reconstruction in _cases(config, spec):
            stem = spec["a"]
            b = _run_name(spec["b"], regime, reconstruction)
            if "{best}" in stem:
                if reconstruction not in selections:
                    selections[reconstruction] = _select_soft(
                        runs, stem, reconstruction, config["soft_candidates"], missing)
                best, _ = selections[reconstruction]
                if best is None:
                    if runs.metrics(b, regime) is None:
                        missing.add(b)
                    for setting in config["soft_candidates"]:
                        candidate = _run_name(stem.format(best=setting), regime, reconstruction)
                        if runs.metrics(candidate, regime) is None:
                            missing.add(candidate)
                    continue
                stem = stem.format(best=best)
            a = _run_name(stem, regime, reconstruction)
            row = _compare(runs, spec, a, b, regime, reconstruction, missing, family=family)
            if row is not None:
                (families if family is not None else exploratory).append(row)

    for spec in config.get("controls", []):
        for regime, reconstruction in _cases(config, spec):
            b_stem = spec["b"]
            a = _run_name(spec["a"], regime, reconstruction)
            draws = spec.get("draws", [None])
            rows = []
            for draw in draws:
                b = _run_name(b_stem.format(d=draw), regime, reconstruction)
                row = _compare(runs, spec, a, b, regime, reconstruction, missing, draw=draw)
                if row is not None:
                    rows.append(row)
            controls.append({"name": spec["name"], "regime": regime, "reconstruction": reconstruction,
                             "expected": len(draws), "rows": rows, **aggregate_draws(rows)})

    adjust_families(families)
    for row in [*families, *exploratory, *(r for control in controls for r in control["rows"])]:
        row["classification"] = classify(row[EFFECT], row["interval"], row["union"], row["p_holm"],
                                         config["smallest_effect"], config["alpha"])
    return {"families": families, "exploratory": exploratory, "controls": controls,
            "missing": sorted(missing), "soft": selections}


def _number(value):
    return f"{value:.4g}" if value is not None and np.isfinite(value) else "—"


def _interval(bounds):
    return f"[{_number(bounds[0])}, {_number(bounds[1])}]" if bounds is not None else "—"


def _table(headers, rows):
    def line(values):
        return "| " + " | ".join(str(v).replace("|", "&#124;") for v in values) + " |"
    return "\n".join([line(headers), line("---" for _ in headers), *(line(row) for row in rows)])


def _contrast_table(rows, development):
    header = ["Contrast", "Regime", "Recon.", "Reading", "Runs a / b", "Median log RMSE ratio",
              "95% interval", "Share a better", "Cluster p", "Holm p", "Band a", "Band b", "Union",
              "Starts a / b", "Support mismatches", "NSE / skill / KGE″ / RMSE (a)",
              "NSE / skill / KGE″ / RMSE (b)", "Classification"]
    show_coverage = any(row["coverage_requested"] for row in rows)
    if show_coverage:
        header += ["Coverage a", "Coverage b"]
    display = []
    for row in rows:
        if development:
            reading = "development (exploratory)"
        elif row["family"] is None:
            reading = "exploratory"
        elif row["regime"] or row["reconstruction"] != 1:
            reading = "robustness"
        else:
            reading = "confirmatory"
        classification = row["classification"]
        if classification == UNDECIDED and np.isfinite(row["interval"]).all():
            lo, hi = map(_number, row["interval"])
            classification += f"<br>compatible with effects from {lo} to {hi}"
        name = row["name"] + (f" (draw {row['draw']})" if row["draw"] is not None else "")
        union = " ∪ ".join(map(_interval, row["union"])) if row["union"] is not None else "—"
        values = [name, REGIME_NAMES[row["regime"]], row["reconstruction"], reading,
                  f"{row['a']}<br>{row['b']}", _number(row[EFFECT]), _interval(row["interval"]),
                  _number(row["share of wells a better"]), _number(row["p_cluster"]),
                  _number(row["p_holm"]), _interval(row["band_a"]), _interval(row["band_b"]), union,
                  f"{row['starts_a']} / {row['starts_b']}", row["support mismatch"],
                  " / ".join(map(_number, row["scores_a"])), " / ".join(map(_number, row["scores_b"])),
                  classification]
        if show_coverage:
            values += [row["coverage_a"] or "—", row["coverage_b"] or "—"]
        display.append(values)
    return _table(header, display) if display else "No contrasts available."


def render(config, report, development=False):
    smallest, alpha = config["smallest_effect"], config["alpha"]
    lines = ["# Phase 4 arm contrasts", "", "Generated by `python -m src.analysis.arms_report`.", "",
             "The effect is the median drought log(RMSE a / RMSE b) over paired core wells. "
             "Negative values favour a. Intervals use the cluster bootstrap.", "",
             f"Detection requires Holm p < {alpha:g}, an interval excluding zero and a median "
             "strictly outside the union of the two same-arm bands. Detected magnitudes at or "
             f"above {smallest:g} meet the smallest effect. Smaller detections have their own class. "
             f"A whole interval strictly inside (−{smallest:g}, +{smallest:g}) gives no effect of "
             "interest when the detection rule fails. Other results are undecided.", "",
             "Holm uses the available tests in each family and regime × reconstruction cell. "
             "Missing runs can leave families incomplete. The Holm column is populated for family rows. "
             "A dash marks unavailable quantities. A Phase 4 same-arm band uses "
             "two disjoint halves of ten starts."]
    if development:
        lines += ["", "**Development only.** These are saved ladder runs and illustrative control draws."]
    if report["soft"]:
        values = []
        for reconstruction, (best, entries) in sorted(report["soft"].items()):
            values.append([reconstruction, "pending complete grid" if best is None else best,
                           "<br>".join(f"{name}: {_number(val)}" for _, name, val in entries)])
        lines += ["", "## Soft-penalty selection", "",
                  "Choose on the R1 median core validation NSE within each reconstruction. "
                  "R2 uses the selected R1 setting.", "",
                  _table(["Recon.", "Selected penalty", "R1 validation NSE by run"], values)]
    for family in config["families"]:
        rows = [row for row in report["families"] if row["family"] == family]
        lines += ["", f"## {family}", "", _contrast_table(rows, development)]

    if not development and len(config["reconstructions"]) > 1:
        stability = []
        for family, specs in config["families"].items():
            for spec in specs:
                rows = [row for row in report["families"] if row["family"] == family
                        and row["name"] == spec["name"] and row["regime"] == ""]
                stability.append([family, spec["name"], reconstruction_agreement(rows, config["reconstructions"])])
        lines += ["", "## Holds under all reconstructions in R1", "",
                  _table(["Family", "Contrast", "Agreement"], stability)]

    names = dict.fromkeys(group["name"] for group in report["controls"])
    if names:
        lines += ["", "## Graph controls (exploratory)", "",
                  "The draw range uses each draw's median effect. The ratio divides its span by "
                  "arm a's same-arm band width (arm D for the Phase 4 controls). "
                  "One scored graph has zero span. Scored and declared counts show the available draws."]
    for name in names:
        groups = [group for group in report["controls"] if group["name"] == name]
        summaries = [[REGIME_NAMES[g["regime"]], g["reconstruction"], f"{g['n']} / {g['expected']}",
                      _number(g["median"]), _interval(g["range"]), _number(g["width"]), _number(g["ratio"])]
                     for g in groups]
        lines += ["", f"### {name}", "", _contrast_table([row for g in groups for row in g["rows"]], development),
                  "", _table(["Regime", "Recon.", "Scored / declared", "Median over draws", "Draw range",
                             "Band width a", "Draw span / band width"], summaries)]
    if config.get("exploratory"):
        lines += ["", "## Exploratory contrasts", "", _contrast_table(report["exploratory"], development)]
    lines += ["", "## Missing runs or scores", ""]
    lines += [f"- `{name}`" for name in report["missing"]] or ["None."]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--config", type=Path, default=CONFIG)
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text())
    development = args.config.name == DEV_CONFIG.name
    output = RESULTS / "_arms_dev.md" if development else ROOT / "docs" / f"results_arms_{DATASET}.md"
    output.write_text(render(config, compute(config, SavedRuns()), development), encoding="utf-8")
    print(f"-> {output}")


if __name__ == "__main__":
    main()
