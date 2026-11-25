"""Audit dataset v5 without fitting a model (docs/v5_plan.md R1.5, Gate R1).

    PYTHONIOENCODING=utf-8 PFE_DATASET=v5 .venv/bin/python -m src.analysis.dataset_v5_audit --skip-rebuild
    PYTHONIOENCODING=utf-8 PFE_DATASET=v5 .venv/bin/python -m src.analysis.dataset_v5_audit

The first command compares v4 with v5 and checks the basin accounting. The second
also rebuilds v5 in a fresh Python process and compares every file's SHA-256.
It refuses to rebuild until T65's report exists, because that worker reads v5.
The builder overwrites its outputs from raw inputs; no model is trained here.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import time

import numpy as np
import pandas as pd

from src.config import PROCESSED, ROOT

REPORT = ROOT / "docs" / "dataset_v5_audit.md"
HASHES = ROOT / "results" / "logs" / "dataset_v5_hashes.json"
READY = ROOT / "results" / "_agents" / "reports" / "T65.md"
HEAD_KEY = ["code_bss", "week"]
FORCING_KEY = ["cell_id", "week"]


def hash_files(directory: Path) -> dict[str, str]:
    """Hash every file, including nested files, using relative names and stable order."""
    hashes = {}
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            hashes[path.relative_to(directory).as_posix()] = digest.hexdigest()
    return hashes


def compare_wells(old: pd.DataFrame, new: pd.DataFrame) -> dict:
    """Compare membership, core flags and actual fold labels, independent of row order."""
    left, right = old.set_index("code_bss"), new.set_index("code_bss")
    if not left.index.is_unique or not right.index.is_unique:
        raise ValueError("Duplicate well codes")
    common = left.index.intersection(right.index).sort_values()
    same_wells = set(left.index) == set(right.index)
    result = {"wells_identical": same_wells, "v4_wells": len(left), "v5_wells": len(right),
              "v4_core": int(old["core"].sum()), "v5_core": int(new["core"].sum()),
              "added": sorted(set(right.index) - set(left.index)),
              "removed": sorted(set(left.index) - set(right.index))}
    for column in ("core", "fold"):
        changed = common[left.loc[common, column].ne(right.loc[common, column])].tolist()
        result[column + "_identical"] = same_wells and not changed
        result[column + "_changed"] = changed
    return result


def compare_heads(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """Count shared well-weeks whose mean head moved by more than 0.001 m, by year."""
    joined = old[HEAD_KEY + ["head"]].merge(new[HEAD_KEY + ["head"]], on=HEAD_KEY,
                                           suffixes=("_v4", "_v5"), validate="one_to_one")
    finite = np.isfinite(joined["head_v4"]) & np.isfinite(joined["head_v5"])
    joined["year"] = joined["week"].dt.year.astype(int)
    joined["changed"] = finite & (joined["head_v5"] - joined["head_v4"]).abs().gt(0.001)
    joined["not_comparable"] = ~finite
    return joined.groupby("year").agg(common=("changed", "size"), changed=("changed", "sum"),
                                      not_comparable=("not_comparable", "sum")).reset_index()


def compare_forcing(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """Measure absolute differences for every shared numeric variable on shared cell-weeks."""
    variables = [c for c in old.columns if c not in FORCING_KEY and c in new.columns
                 and pd.api.types.is_numeric_dtype(old[c]) and pd.api.types.is_numeric_dtype(new[c])]
    joined = old[FORCING_KEY + variables].merge(new[FORCING_KEY + variables], on=FORCING_KEY,
                                               suffixes=("_v4", "_v5"), validate="one_to_one")
    rows = []
    for period, mask in (("before 2023", joined["week"] < "2023-01-01"),
                         ("2023 onward", joined["week"] >= "2023-01-01")):
        for variable in variables:
            left, right = joined.loc[mask, variable + "_v4"], joined.loc[mask, variable + "_v5"]
            finite = np.isfinite(left) & np.isfinite(right)
            delta = (right[finite] - left[finite]).abs()
            rows.append({"period": period, "variable": variable, "common": len(left),
                         "not_comparable": int((~finite).sum()), "changed": int(delta.gt(0).sum()),
                         "max_abs_delta": float(delta.max()), "mean_abs_delta": float(delta.mean())})
    return pd.DataFrame(rows)


def split_summary(heads: pd.DataFrame, wells: pd.DataFrame, splits: dict) -> pd.DataFrame:
    """Use each version's split bounds; give the mean unvalidated share of core well-weeks."""
    core = heads[heads["code_bss"].isin(wells.loc[wells["core"], "code_bss"])]
    rows = []
    for split in ("train", "validation", "test"):
        start, end = splits[split]
        block = core[core["week"].between(start, end)]
        rows.append({"split": split, "start": start, "end": end, "core_well_weeks": len(block),
                     "share_not_validated": float(block["share_not_validated"].mean())})
    return pd.DataFrame(rows)


def table_inventory(directory: Path) -> pd.DataFrame:
    """Read actual row counts and time coverage, including tables not listed in meta.json."""
    rows = []
    for path in sorted(directory.rglob("*.parquet")):
        frame = pd.read_parquet(path)
        first = last = "—"
        if len(frame) and "week" in frame:
            first, last = str(frame["week"].min().date()), str(frame["week"].max().date())
        elif len(frame) and {"first_week", "last_week"} <= set(frame.columns):
            first = str(frame["first_week"].min().date())
            last = str(frame["last_week"].max().date())
        rows.append({"table": path.relative_to(directory).as_posix(), "rows": len(frame),
                     "first_week": first, "last_week": last})
    return pd.DataFrame(rows)


def conservation(actual: pd.Series, expected: pd.Series) -> dict:
    """Missing weeks fail even when their expected volume happens to be zero."""
    if not actual.index.is_unique or not expected.index.is_unique:
        raise ValueError("Duplicate weeks in conservation check")
    common = actual.index.intersection(expected.index)
    delta = (actual.loc[common] - expected.loc[common]).abs()
    maximum = float(delta.max()) if len(delta) else None
    coverage = set(actual.index) == set(expected.index)
    finite = bool(np.isfinite(actual).all() and np.isfinite(expected).all())
    return {"passed": coverage and finite and maximum is not None and maximum <= 1e-6,
            "weeks": len(common), "same_weeks": coverage, "finite": finite,
            "max_abs_delta_m3": maximum,
            "missing_weeks": len(expected.index.difference(actual.index)),
            "extra_weeks": len(actual.index.difference(expected.index))}


def canal_summary(weekly: pd.DataFrame, intakes: pd.DataFrame,
                  pumping: pd.DataFrame, points: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Annual basin volumes and volume-weighted imputation, retaining zero-volume basins."""
    from src.dataset.pumping import canal_series

    selected = points.loc[(points["zone"] == "plain") & (points["source"] == "surface"),
                          ["code_ouvrage"]]
    rows = pumping[pumping["usage"].isin(["irrigation", "canals"])].merge(
        selected, on="code_ouvrage", validate="many_to_one")
    rows = rows.merge(intakes[["code_ouvrage", "basin"]], on="code_ouvrage", how="left",
                      validate="many_to_one")
    if rows["basin"].isna().any() or rows["imputed"].isna().any():
        raise ValueError("Canal rows lack a basin or an imputed flag")
    key = ["week", "basin"]
    stored = weekly.set_index(key)["volume_m3"]
    if not stored.index.is_unique:
        raise ValueError("Duplicate basin-weeks")
    reconstructed = rows.groupby(key)["volume_m3"].sum()
    if len(reconstructed.index.difference(stored.index)):
        raise ValueError("Stored basin series omit pumping basin-weeks")
    reconstructed = reconstructed.reindex(stored.index, fill_value=0.0)
    if not np.isfinite(stored).all() or not np.isfinite(reconstructed).all():
        raise ValueError("Non-finite canal volumes")
    allocation_delta = float((stored - reconstructed).abs().max())
    if allocation_delta > 1e-6:
        raise ValueError(f"Stored basin volumes disagree with intake accounting: {allocation_delta} m3")
    imputed = rows.loc[rows["imputed"]].groupby(key)["volume_m3"].sum()
    block = weekly.copy()
    block["imputed_m3"] = imputed.reindex(stored.index, fill_value=0.0).to_numpy()
    block["year"] = block["week"].dt.year
    annual = block[block["year"].between(2012, 2026)].groupby(["year", "basin"])[
        ["volume_m3", "imputed_m3"]].sum()
    annual = annual.reindex(pd.MultiIndex.from_product(
        [range(2012, 2027), sorted(weekly["basin"].unique())], names=["year", "basin"]), fill_value=0)
    annual["volume_Mm3"] = annual["volume_m3"] / 1e6
    annual["imputed_share"] = annual["imputed_m3"] / annual["volume_m3"].replace(0, np.nan)
    check = conservation(weekly.groupby("week")["volume_m3"].sum(), canal_series(pumping, points))
    check["max_basin_allocation_delta_m3"] = allocation_delta
    return annual.reset_index()[["year", "basin", "volume_Mm3", "imputed_share"]], check


def diagnose_change(name: str, before: bytes, after: bytes) -> str:
    """Explain changed bytes using the saved pre-build content, never guesses."""
    if name.endswith(".json"):
        left, right = json.loads(before), json.loads(after)
        keys = sorted(k for k in set(left) | set(right)
                      if k not in left or k not in right or left[k] != right[k])
        if not keys:
            return "JSON formatting/key order only; use a canonical JSON writer for byte stability."
        if keys == ["built"]:
            return (f"Only built changed: {left['built']} → {right['built']}; build.py would need a "
                    "fixed snapshot date or separate volatile metadata for cross-day byte stability.")
        return "JSON fields changed: " + ", ".join(keys) + "; inspect these builder inputs/fields."
    if name.endswith(".parquet"):
        left, right = pd.read_parquet(io.BytesIO(before)), pd.read_parquet(io.BytesIO(after))
        if left.equals(right):
            return "Table is identical; Parquet encoding/metadata changed. Pin writer settings/version."
        if list(left.columns) != list(right.columns):
            return "Column names/order changed; build.py would need a fixed output schema."
        if left.dtypes.astype(str).to_dict() != right.dtypes.astype(str).to_dict():
            return "Column dtypes changed; build.py would need fixed output dtypes."
        if len(left) != len(right):
            return f"Row count changed ({len(left)} → {len(right)}); freeze the builder's source inputs."
        # Current dataset tables contain scalar values, so sorting all columns can
        # distinguish row order from changed data without assuming a table-specific key.
        ordered_left = left.sort_values(list(left.columns), ignore_index=True)
        ordered_right = right.sort_values(list(right.columns), ignore_index=True)
        if ordered_left.equals(ordered_right):
            return "Row order only; build.py would need explicit stable sorting before writing."
        differences = []
        for column in left.columns:
            a, b = ordered_left[column], ordered_right[column]
            if not a.equals(b):
                if pd.api.types.is_numeric_dtype(a) and not pd.api.types.is_bool_dtype(a):
                    delta = (a - b).abs()
                    differences.append(f"{column} (sorted-row max |Δ| {delta.max():.9g})")
                else:
                    differences.append(column)
        return ("Table values changed in " + ", ".join(differences)
                + ". Sorted-row deltas are diagnostic, not key-aligned; freeze inputs and inspect "
                  "numeric reduction order before attributing this to float noise.")
    return "File bytes changed; no table/JSON diagnosis available. Inspect its producer."


def rebuild_audit(directory: Path) -> dict:
    """Only after T65, snapshot all files and run the builder in a new process."""
    if not READY.is_file():
        raise FileNotFoundError(f"Rebuild must wait for {READY.relative_to(ROOT)}")
    before = hash_files(directory)
    saved = {name: (directory / name).read_bytes() for name in before}
    command = [str(ROOT / ".venv" / "bin" / "python"), "-m", "src.dataset.build"]
    env = os.environ.copy()
    env.update(PFE_DATASET="v5", PYTHONIOENCODING="utf-8")
    started = time.perf_counter()
    result = subprocess.run(command, cwd=ROOT, env=env, check=False)
    elapsed = time.perf_counter() - started
    after = hash_files(directory)
    files = []
    for name in sorted(set(before) | set(after)):
        identical = name in before and name in after and before[name] == after[name]
        reason = "Identical bytes."
        if name not in before:
            reason = "Added by rebuild; absent from the initial dataset."
        elif name not in after:
            reason = "Missing after rebuild."
        elif not identical:
            reason = diagnose_change(name, saved[name], (directory / name).read_bytes())
        files.append({"file": name, "identical": identical, "diagnosis": reason})
    return {"status": "completed" if result.returncode == 0 else "build_failed",
            "dependency": str(READY.relative_to(ROOT)),
            "command": "PYTHONIOENCODING=utf-8 PFE_DATASET=v5 .venv/bin/python -m src.dataset.build",
            "returncode": result.returncode, "seconds": elapsed,
            "before": before, "after": after, "files": files}


def markdown_table(frame: pd.DataFrame) -> str:
    """Avoid optional Markdown dependencies and keep generated numbers reproducible."""
    def cell(value):
        if isinstance(value, (float, np.floating)):
            return "n/a" if pd.isna(value) else f"{value:.9g}"
        return str(value).replace("|", "\\|").replace("\n", " ")

    return "\n".join(["| " + " | ".join(map(str, frame.columns)) + " |",
                      "| " + " | ".join("---" for _ in frame.columns) + " |"]
                     + ["| " + " | ".join(cell(v) for v in row) + " |"
                        for row in frame.itertuples(index=False, name=None)])


def comparison_report(old_dir: Path, new_dir: Path) -> tuple[str, bool]:
    """Generate steps 2–3 before any rebuild, also usable while T65 is still reading."""
    wells = [pd.read_parquet(d / "wells.parquet") for d in (old_dir, new_dir)]
    heads = [pd.read_parquet(d / "heads_weekly.parquet") for d in (old_dir, new_dir)]
    forcing = [pd.read_parquet(d / "forcing_weekly.parquet") for d in (old_dir, new_dir)]
    splits = [json.loads((d / "splits.json").read_text()) for d in (old_dir, new_dir)]
    identity = compare_wells(*wells)
    sections = ["## v4 versus v5", markdown_table(pd.DataFrame([
        {"check": k, "value": json.dumps(v)} for k, v in identity.items()])),
        "Wells means the set of code_bss identifiers. Core flags and fold labels are compared by code."]
    fold_maps = [s["leave_wells_out"]["fold_of_well"] for s in splits]
    sections.append(f"Fold maps in splits.json identical: {fold_maps[0] == fold_maps[1]}. "
                    "Each map agrees with its wells table: " + str(all(
                        m == dict(zip(w["code_bss"], w["fold"])) for m, w in zip(fold_maps, wells))) + ".")
    inventories = [table_inventory(d).assign(version=v) for d, v in zip((old_dir, new_dir), ("v4", "v5"))]
    sections += ["### Table sizes and coverage", markdown_table(pd.concat(inventories, ignore_index=True)),
                 "Static tables have no week bounds. Gauge bounds describe their associated river records."]
    split_rows = [split_summary(h, w, s).assign(version=v)
                  for h, w, s, v in zip(heads, wells, splits, ("v4", "v5"))]
    sections += ["### Core well-weeks by split", markdown_table(pd.concat(split_rows, ignore_index=True)),
                 "Counts include available heads before the placeholder scoring mask. The unvalidated share "
                 "is the mean of share_not_validated over core well-weeks, not a count of wholly unvalidated "
                 "weeks or a daily-weighted percentage. Each version uses its own split end dates."]
    changes = compare_heads(*heads)
    common = int(changes["common"].sum())
    sections += ["### Shared weekly heads", markdown_table(changes),
                 f"Threshold: |Δhead| > 0.001 m (1 mm). Shared well-weeks: {common}; "
                 f"changed: {int(changes['changed'].sum())}. "
                 f"Only in v4: {len(heads[0]) - common}; only in v5: {len(heads[1]) - common}.",
                 "### Forcing on common cell-weeks", markdown_table(compare_forcing(*forcing)),
                 "Differences use the stored variable units: weekly sums for PRELIQ, PRENEI, ETP, EVAP, "
                 "PE, DRAINC, RUNC and rain; weekly means for T and SWI. Non-finite pairs are counted "
                 "separately and excluded from delta statistics."]
    masks = [pd.read_parquet(d / "placeholder_weeks.parquet") for d in (old_dir, new_dir)]
    mask_keys = [set(map(tuple, m[HEAD_KEY].itertuples(index=False, name=None))) for m in masks]
    sections += ["### Placeholder weeks",
                 f"v4: {len(masks[0])}; v5: {len(masks[1])}; identical pairs: {mask_keys[0] == mask_keys[1]}; "
                 f"added: {len(mask_keys[1] - mask_keys[0])}; removed: {len(mask_keys[0] - mask_keys[1])}."]
    for version, mask in zip(("v4", "v5"), masks):
        detail = mask.groupby("code_bss").agg(weeks=("week", "size"), first=("week", "min"),
                                               last=("week", "max")).reset_index()
        sections += [f"{version}:", markdown_table(detail)]
    annual, check = canal_summary(*[pd.read_parquet(new_dir / name) for name in (
        "canal_basins_weekly.parquet", "canal_intakes_basin.parquet", "pumping_weekly.parquet",
        "pumping_points.parquet")])
    sections += ["## Canal basins", markdown_table(pd.DataFrame([check])),
                 "Conservation compares every week with src.dataset.pumping.canal_series using the v5 "
                 "pumping and points tables (absolute tolerance 1e-6 m³/week). A separate check verifies "
                 "each stored basin against its intakes before assigning imputed volumes.",
                 markdown_table(annual),
                 "Volumes are Mm³, grouped by the Sunday week-label year. The imputed share is the "
                 "fraction of volume whose pumping_weekly rows have imputed=True, joined via intake "
                 "code and basin. n/a means zero volume. 2026 is partial: coverage ends at "
                 f"{pd.read_parquet(new_dir / 'canal_basins_weekly.parquet')['week'].max().date()}. "
                 "These are annual BNPE totals spread with the climatic deficit, not measured weekly flows."]
    return "\n\n".join(sections), check["passed"]


def write_outputs(comparison: str, hashes: dict) -> None:
    """Keep full digests in JSON and a readable file-by-file verdict in Markdown."""
    if hashes["status"] == "not_run":
        reproducibility = "Rebuild not run (--skip-rebuild). Gate R1 reproducibility is pending."
    else:
        reproducibility = (f"Build status: {hashes['status']}; return code: {hashes['returncode']}; "
                           f"elapsed: {hashes['seconds']:.2f} s. Fresh process, rebuilt from raw inputs.\n\n"
                           + markdown_table(pd.DataFrame(hashes["files"]))
                           + "\n\nFull before/after SHA-256 digests: results/logs/dataset_v5_hashes.json. "
                           "This checks the existing dataset against one fresh rebuild. meta.json's built "
                           "field is a calendar date, so a same-day pass does not establish cross-day byte "
                           "stability. build.py would need a fixed snapshot date or separate volatile metadata "
                           "to provide that guarantee.")
    REPORT.write_text("<!-- Generated by src.analysis.dataset_v5_audit; do not edit by hand. -->\n"
                      "# Dataset v5 audit (Gate R1)\n\n" + comparison
                      + "\n\n## Reproducibility\n\n" + reproducibility + "\n", encoding="utf-8")
    HASHES.parent.mkdir(parents=True, exist_ok=True)
    HASHES.write_text(json.dumps(hashes, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-rebuild", action="store_true", help="Only steps 2–3; safe while T65 runs")
    args = parser.parse_args()
    old_dir, new_dir = PROCESSED / "dataset_v4", PROCESSED / "dataset_v5"
    comparison, canal_passed = comparison_report(old_dir, new_dir)
    pending = {"status": "not_run", "before": {}, "after": {}, "files": []}
    # Write the comparisons first, as required by T68's work-order addendum.
    write_outputs(comparison, pending)
    hashes = pending if args.skip_rebuild else rebuild_audit(new_dir)
    if not args.skip_rebuild:
        comparison, canal_passed = comparison_report(old_dir, new_dir)
        write_outputs(comparison, hashes)
    print(f"-> {REPORT.relative_to(ROOT)}\n-> {HASHES.relative_to(ROOT)}", flush=True)
    if not canal_passed:
        raise SystemExit("FAIL: basin conservation")
    if hashes["status"] != "not_run" and (hashes["returncode"] or not hashes["files"]
                                           or not all(row["identical"] for row in hashes["files"])):
        raise SystemExit("FAIL: reproducibility (see generated report and hashes)")
    print("Dataset v5 audit checks passed" if not args.skip_rebuild else "Comparisons done; rebuild pending")


if __name__ == "__main__":
    main()
