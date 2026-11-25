"""Count wrong signs in saved v4 response gains, without fitting a model.

Analysis plan section 10 (RQ2) and Gate 3 points 7–9 distinguish signs built
into the model from soft penalties and free gains. This descriptive check
complements the accuracy contrasts in docs/results_arms_v4.md. It reads every
saved start, including every LWO fold, and writes docs/rq2_signs_v4.md.

    PFE_DATASET=v4 python -m src.analysis.rq2_signs
"""
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import DATASET, ROOT

RESULTS = ROOT / "results" / "v4"
DS = ROOT / "data" / "processed" / "dataset_v4"
EXPORT = ROOT / "data" / "processed" / "kg" / "export_v4_main"
REPORT = ROOT / "docs" / "rq2_signs_v4.md"
SETTINGS = ("none", "soft1", "soft10", "soft100", "hard")
SLOTS = ("recharge", "pumping", "pumping_unattributed", "river_c", "river", "canal")
SIGNS = {"recharge": 1, "pumping": -1, "pumping_unattributed": -1,
         "river_c": 1, "river": 0, "canal": 0}


def read_table(path, verbose=True):
    """Show the schema and one row before using a saved table's fields."""
    path = Path(path)
    frame = pd.read_csv(path) if path.suffix == ".csv" else pd.read_parquet(path)
    if verbose:
        print(f"{path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}: "
              f"{len(frame)} rows\n  columns: {list(frame.columns)}\n"
              f"  sample: {frame.head(1).to_dict('records')}", flush=True)
    return frame


def frozen_inputs(verbose=True):
    """Bind the sign mask to arm D's frozen export, rather than today's KG."""
    if DATASET != "v4":
        raise ValueError("This saved-parameter analysis requires PFE_DATASET=v4")
    wells = read_table(DS / "wells.parquet", verbose)
    edges = read_table(EXPORT / "edges_D.parquet", verbose)
    splits = json.loads((DS / "splits.json").read_text())
    manifest = json.loads((EXPORT / "manifest.json").read_text())
    river = edges.loc[edges["relation"].eq("river")]
    if not river["constrained"].isin([True, False]).all():
        raise ValueError("Export has missing or invalid river constraint flags")
    constrained = river.groupby("dst")["constrained"].all()
    river_wells = set(constrained.index[constrained])
    core = set(wells.loc[wells["core"].eq(True), "code_bss"])
    folds = splits["leave_wells_out"]["fold_of_well"]
    if not core.issubset(folds):
        raise ValueError("Some core wells have no LWO fold")
    return core, river_wells, splits["leave_wells_out"], manifest["release"]


def saved_params(path, river_wells, verbose=True):
    """Validate merged river gains against the export before counting signs."""
    frame = read_table(path, verbose)
    required = {"code_bss", "river_constrained"} | {
        f"gain_{s}" for s in SLOTS if s != "river_c"}
    if not required.issubset(frame.columns):
        raise ValueError(f"{path}: missing columns {sorted(required - set(frame.columns))}")
    if frame["code_bss"].isna().any() or frame["code_bss"].duplicated().any():
        raise ValueError(f"{path}: missing or repeated well IDs")
    mask = frame["code_bss"].isin(river_wells)
    if not frame["river_constrained"].isin([True, False]).all() \
            or not np.array_equal(frame["river_constrained"].to_numpy(), mask.to_numpy()):
        raise ValueError(f"{path}: river_constrained differs from arm D's frozen export")
    gains = [f"gain_{s}" for s in SLOTS if s != "river_c"]
    if not np.isfinite(frame[gains].to_numpy(dtype=float)).all():
        raise ValueError(f"{path}: non-finite gain; refusing to shrink the denominator")
    return frame


def load_run(run, setting, core, river_wells, lwo, release, verbose=True):
    """Read all starts; an R2 well contributes only its held-out fold's gains."""
    is_lwo = run.name.endswith("_lwo")
    folders = [run]
    if is_lwo:
        folders = [run / f"fold_{k}" for k in range(lwo["n_folds"])]
        actual = {p.name for p in run.glob("fold_*") if p.is_dir()}
        if actual != {p.name for p in folders}:
            raise ValueError(f"{run}: missing or unexpected fold folders {sorted(actual)}")
    parts, starts = [], None
    for folder in folders:
        cfg = json.loads((folder / "config.json").read_text())
        want = sorted(cfg["seeds"])
        if not want or len(want) != len(set(want)) or (starts is not None and want != starts):
            raise ValueError(f"{folder}: empty, duplicate or inconsistent start list")
        starts = want
        fold = int(folder.name.split("_")[1]) if is_lwo else None
        expected_signs = "gate3" if setting == "hard" else "none"
        expected_soft = float(setting[4:]) if setting.startswith("soft") else None
        if (cfg["dataset"] != "v4" or cfg["arm"] != "D" or cfg["policy"] != "main"
                or cfg["export_release"] != release or cfg.get("fold") != fold
                or cfg["signs"] != expected_signs or cfg.get("soft") != expected_soft
                or cfg.get("sign_ref", "gate3" if setting == "hard" else None) != "gate3"
                or set(cfg["river_constrained_wells"]) != river_wells):
            raise ValueError(f"{folder}: config does not match the frozen RQ2 setting")
        paths = sorted(folder.glob("params_seed_*.csv"))
        got = sorted(int(p.stem.removeprefix("params_seed_")) for p in paths)
        if got != want:
            raise ValueError(f"{folder}: saved starts {got}, expected {want}")
        selected = {c for c in core if not is_lwo or lwo["fold_of_well"][c] == fold}
        for path in paths:
            frame = saved_params(path, river_wells, verbose)
            if not core.issubset(set(frame["code_bss"])):
                raise ValueError(f"{path}: missing core wells")
            frame = frame.loc[frame["code_bss"].isin(selected)].copy()
            frame["seed"] = int(path.stem.removeprefix("params_seed_"))
            parts.append(frame)
        if verbose:
            print(f"  {folder.name}: {len(paths)} starts, {len(selected)} selected core wells")
    combined = pd.concat(parts, ignore_index=True)
    if combined.duplicated(["code_bss", "seed"]).any() or len(combined) != len(core) * len(starts):
        raise ValueError(f"{run}: incomplete or repeated core well × start support")
    return combined, len(folders) * len(starts), len(starts)


def summarise(params):
    """Strictly wrong signs and strict majorities; zero and ties are not wrong.

    The saved gain_river is the selected slot at each well. Only the rows
    marked river_constrained belong to river_c. No-rule slots return missing
    rates, rather than zero, so they cannot imply a physical guarantee.
    """
    rows = []
    for slot in SLOTS:
        selected = params
        if slot in ("river_c", "river"):
            selected = params.loc[params["river_constrained"].eq(slot == "river_c")]
        gain = selected[f"gain_{'river' if slot == 'river_c' else slot}"].astype(float)
        sign = SIGNS[slot]
        wrong = gain * sign < 0 if sign else pd.Series(False, index=selected.index)
        n, wells = len(selected), selected["code_bss"].nunique()
        rate = float(wrong.mean()) if n and sign else np.nan
        majority = (wrong.groupby(selected["code_bss"]).mean() > 0.5).mean() \
            if n and sign else np.nan
        rows.append({"slot": slot, "sign": sign, "n_gains": n, "n_wells": wells,
                     "n_wrong": int(wrong.sum()), "share_wrong": rate,
                     "share_majority_wrong": float(majority),
                     "median_abs_wrong": float(gain[wrong].abs().median())
                     if wrong.any() else np.nan})
    return pd.DataFrame(rows).set_index("slot")


def collect(verbose=True):
    """List all requested runs, then compute summaries for those that exist."""
    core, river_wells, lwo, release = frozen_inputs(verbose)
    summaries, inventory = {}, []
    for regime, suffix in (("R1", ""), ("R2", "_lwo")):
        for setting in SETTINGS:
            for reconstruction in (1, 2, 3):
                name = f"p4_B4_D_{setting}_r{reconstruction}{suffix}"
                run = RESULTS / name
                key = (regime, setting, reconstruction)
                if verbose:
                    print(f"{name}: {'exists' if run.is_dir() else 'MISSING'}", flush=True)
                if not run.is_dir():
                    inventory.append((regime, setting, reconstruction, "missing", 0, 0))
                    continue
                params, files, starts = load_run(run, setting, core, river_wells, lwo, release, verbose)
                summaries[key] = summarise(params)
                inventory.append((regime, setting, reconstruction, "exists", files, starts))
    return summaries, inventory, core, river_wells, release


def cell(row):
    """Three quantities per slot; a missing median means there were no wrong gains."""
    if row["sign"] == 0:
        return "no rule"
    if row["n_gains"] == 0:
        return "no eligible wells"
    median = f"{row['median_abs_wrong']:.6g}" if row["n_wrong"] else "—"
    return f"{row['share_wrong']:.1%} / {row['share_majority_wrong']:.1%} / {median}"


def write_report(summaries, inventory, core, river_wells, release):
    """Write counts and the review comparison even if a hard sign is violated."""
    lines = ["# RQ2: wrong-signed response gains in v4", "",
             "**descriptive, on saved v4 parameters**", "",
             "Generated by `PFE_DATASET=v4 python -m src.analysis.rq2_signs`. "
             "No model is fitted. This checks the plausibility half of analysis-plan-v2 §10 RQ2; "
             "the separate accuracy contrasts are in [results_arms_v4.md](results_arms_v4.md).", "",
             f"The denominator is all {len(core)} core wells × every saved start, including wells "
             "without an active input edge. These are parameter signs; a wrong gain on a zero input "
             "does not imply a wrong contribution. R2 reads every fold but selects each well only "
             "in its held-out fold, as in the saved LWO predictions. It does not count the same "
             "well again in folds where it trained.", "",
             "Expected signs: recharge ≥ 0; attributed and unattributed pumping ≤ 0; "
             "river_c ≥ 0 only at wells where all river edges in arm D's export are constrained. "
             "Plain river and canal have **no rule**. The CSV merges river_c into `gain_river`; "
             "`river_constrained` selects its rows. Each file's mask is checked against the export "
             "and its saved config.", "",
             f"Frozen export release: `{release}`. Constrained river wells: "
             + ", ".join(f"`{c}`" for c in sorted(river_wells)) + ". Core subset: "
             + ", ".join(f"`{c}`" for c in sorted(core & river_wells)) + ".", "",
             "Each slot cell gives **share wrong over well × start / share of wells with a strict "
             "majority of starts wrong / median |wrong gain|**. Exactly zero is not wrong; "
             "a 50% tie is not a majority. The median is in metres per unit model stress, from "
             "`parameters_physical`; — means no wrong gains. Model stresses use rain/10 and ETP/10 "
             "for linear recharge, pump_gw/100, pump_un/100, river/1 and canal/10 "
             "(the saved config's scaling). Magnitudes across different slots are not directly comparable.", ""]
    for regime in ("R1", "R2"):
        lines += [f"## {regime}", "",
                  "| Setting | Reconstruction | " + " | ".join(SLOTS) + " |",
                  "| --- | --- | " + " | ".join("---" for _ in SLOTS) + " |"]
        for setting in SETTINGS:
            for reconstruction in (1, 2, 3):
                summary = summaries.get((regime, setting, reconstruction))
                cells = [cell(summary.loc[s]) if summary is not None else "missing run" for s in SLOTS]
                lines.append(f"| {setting} | {reconstruction} | " + " | ".join(cells) + " |")
        lines.append("")
    lines += ["## Comparison with the review", ""]
    rates = []
    for r in (1, 2, 3):
        summary = summaries.get(("R1", "none", r))
        rates.append(f"{summary.loc['pumping', 'share_wrong']:.1%}" if summary is not None else "missing")
    soft = summaries.get(("R1", "soft100", 1))
    soft_rate = f"{soft.loc['pumping', 'share_wrong']:.1%}" if soft is not None else "missing"
    hard = [frame.loc[frame["sign"].ne(0)] for (regime, setting, r), frame in summaries.items()
            if setting == "hard"]
    wrong = sum(int(frame["n_wrong"].sum()) for frame in hard)
    total = sum(int(frame["n_gains"].sum()) for frame in hard)
    lines += ["[gemini_neon_review.md §2.3 point 5](../gemini_neon_review.md) reports "
              "32.4% / 42.1% / 35.2% wrong attributed-pumping gains for none, reconstructions 1/2/3. "
              f"The R1 saved-parameter counts here are {' / '.join(rates)}. "
              f"For soft100 reconstruction 1, the review reports 20.6%; here it is {soft_rate}. "
              f"The review reports 0% under hard; here hard has {wrong}/{total} wrong constrained "
              "gains across the available R1 and R2 runs. These counts alone do not establish "
              "equal or better accuracy in every regime or reconstruction.", ""]
    for slot, review in (("recharge", "10.9%–15.2%"),
                         ("pumping_unattributed", "35.5%–43.3%"), ("river_c", "35%–40%")):
        values = [f"{summaries[('R1', 'none', r)].loc[slot, 'share_wrong']:.1%}"
                  if ("R1", "none", r) in summaries else "missing" for r in (1, 2, 3)]
        lines.append(f"The review's none range for {slot} is {review}; the R1 counts here "
                     f"are {' / '.join(values)} (reconstructions 1/2/3).")
    lines += ["", "The constrained-river counts cover only two core wells. With ten starts, "
              "one changed gain moves that rate by 5 percentage points, and one majority-wrong "
              "well moves the well share by 50 points. These are small descriptive counts."]
    lines += ["", "## Saved-run coverage", "",
              "| Regime | Setting | Reconstruction | Status | Parameter files read | Starts per well |",
              "| --- | --- | --- | --- | --- | --- |"]
    lines += ["| " + " | ".join(map(str, row)) + " |" for row in inventory]
    lines += ["", "## Denominators", "",
              "Counts are pooled over well × start, rather than averaged over fold percentages. "
              "The river_c denominator includes only constrained core wells. No-rule slots are "
              "excluded from violation counts, including the hard check.", "",
              "The following distinct support counts occur across the available settings and "
              "reconstructions. Exact wrong counts are the reported shares times these denominators, "
              "before percentage rounding.", "",
              "| Regime | Slot | Gains | Wells |",
              "| --- | --- | --- | --- |"]
    supports = set()
    for (regime, setting, r), summary in summaries.items():
        for slot, row in summary.iterrows():
            supports.add((regime, slot, int(row["n_gains"]), int(row["n_wells"])))
    for regime, slot, gains, wells in sorted(supports, key=lambda x: (x[0], SLOTS.index(x[1]), x[2:])):
        lines.append(f"| {regime} | {slot} | {gains} | {wells} |")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    started = time.perf_counter()
    result = collect()
    write_report(*result)
    print(f"Wrote {REPORT.relative_to(ROOT)}; {len(result[0])} runs, "
          f"{sum(row[4] for row in result[1])} parameter files; "
          f"{time.perf_counter() - started:.2f}s", flush=True)


if __name__ == "__main__":
    main()
