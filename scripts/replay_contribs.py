"""Rebuild missing response-model contributions for explanations (analysis plan §12).

Replay each saved start and check its predictions and parameters before writing any
contributions for the run. These checks tie the reconstructed contributions to the
model outputs that were saved during the experiment.
"""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd
import torch

from src.models.evaluate import RESULTS
from src.models.response import args_from_config, prepare, replay, seed_outputs

WELL_KEY = ["code_bss"]
WEEK_KEYS = [*WELL_KEY, "week"]
Z_TOL = 1e-5
PARAM_ATOL = 1e-6
PARAM_RTOL = 1e-5
CONTRIB_TOL_M = 1e-5


def compare_table(rebuilt, saved, keys, source, *, atol, rtol=0.0):
    """Check matching rows by key and return the largest absolute numeric difference."""
    if set(rebuilt.columns) != set(saved.columns):
        missing = sorted(set(rebuilt.columns) - set(saved.columns))
        extra = sorted(set(saved.columns) - set(rebuilt.columns))
        raise ValueError(f"{source}: saved columns differ (missing {missing}, extra {extra})")

    actual = rebuilt.set_index(keys, verify_integrity=True).sort_index()
    expected = saved.set_index(keys, verify_integrity=True).sort_index()
    if not actual.index.equals(expected.index):
        raise ValueError(f"{source}: saved keys {keys} differ from the replay")

    largest = 0.0
    for column in expected:
        reference = expected[column]
        if pd.api.types.is_bool_dtype(reference) or not pd.api.types.is_numeric_dtype(reference):
            if not actual[column].equals(reference):
                raise ValueError(f"{source}: values differ in {column}")
            continue

        want = reference.to_numpy(dtype=np.float64)
        got = actual[column].to_numpy(dtype=np.float64)
        if not (np.isfinite(want).all() and np.isfinite(got).all()):
            raise ValueError(f"{source}: non-finite values in {column}")
        delta = np.abs(got - want)
        allowed = np.maximum(atol, rtol * np.abs(want))
        if (delta > allowed).any():
            row = int(np.argmax(delta - allowed))
            raise ValueError(f"{source}: {column} at {expected.index[row]} differs by "
                             f"{delta[row]:.6g} (limit {allowed[row]:.6g})")
        largest = max(largest, float(delta.max(initial=0.0)))
    return largest


def check_start(folder, start, pz, contrib, params):
    prediction_file = folder / f"seed_{start}.parquet"
    predicted = contrib[WEEK_KEYS].assign(z=pz.reshape(-1))
    delta_z = compare_table(predicted, pd.read_parquet(prediction_file), WEEK_KEYS,
                            prediction_file.name, atol=Z_TOL)

    param_file = folder / f"params_seed_{start}.csv"
    saved_params = pd.read_csv(param_file)
    lag_cols = [col for col in params if col.startswith(("impl_mean_lag_", "impl_peak_lag_"))]
    if not set(lag_cols).intersection(saved_params.columns):
        # The ladder ran before the finite-kernel lag diagnostics were added.
        params = params.drop(columns=lag_cols)
    delta_param = compare_table(params, saved_params, WELL_KEY, param_file.name,
                                atol=PARAM_ATOL, rtol=PARAM_RTOL)
    return delta_z, delta_param


def publish(folder, missing, record):
    """Stage all outputs, then publish the tables without replacing existing files."""
    provenance = folder / "contrib_replayed.json"
    directory = os.open(folder, os.O_RDONLY | os.O_DIRECTORY)
    try:
        # Serialize provenance updates without leaving a lock file in the run.
        fcntl.flock(directory, fcntl.LOCK_EX)
        history = json.loads(provenance.read_text(encoding="utf-8")) if provenance.exists() else {"replays": []}
        history["replays"].append(record)
        with TemporaryDirectory(dir=folder) as staging_dir:
            staging = Path(staging_dir)
            for target, frame in missing.items():
                frame.to_parquet(staging / target.name, index=False)
            staged_record = staging / provenance.name
            staged_record.write_text(json.dumps(history, indent=2) + "\n", encoding="utf-8")
            published = []
            try:
                for target in missing:
                    os.link(staging / target.name, target)
                    published.append(target)
                staged_record.replace(provenance)
            except OSError:
                for target in published:
                    target.unlink()
                raise
    finally:
        os.close(directory)


def replay_run(folder, *, check_only):
    starts = sorted(int(path.stem.removeprefix("seed_")) for path in folder.glob("seed_*.pt")
                    if path.is_file() and re.fullmatch(r"seed_\d+\.pt", path.name))
    if not starts:
        raise ValueError("no seed_<k>.pt checkpoints found")

    cfg = json.loads((folder / "config.json").read_text(encoding="utf-8"))
    prep = prepare(args_from_config(cfg), verbose=False)
    missing = {}
    compared = 0
    max_z = max_param = max_contrib = 0.0
    for start in starts:
        net, data = replay(folder, start, prep=prep)
        pz, contrib, params = seed_outputs(net, data)
        delta_z, delta_param = check_start(folder, start, pz, contrib, params)
        max_z = max(max_z, delta_z)
        max_param = max(max_param, delta_param)
        target = folder / f"contrib_seed_{start}.parquet"
        if target.exists():
            delta = compare_table(contrib, pd.read_parquet(target), WEEK_KEYS, target.name,
                                  atol=CONTRIB_TOL_M)
            max_contrib = max(max_contrib, delta)
            compared += 1
        else:
            missing[target] = None if check_only else contrib

    # A mismatch in a later start must leave the earlier starts unwritten too.
    if missing and not check_only:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                         cwd=Path(__file__).resolve().parents[1], text=True).strip()
        publish(folder, missing, {"starts": [int(path.stem.rsplit("_", 1)[1]) for path in missing],
                                  "commit": commit, "utc_time": datetime.now(timezone.utc).isoformat(),
                                  "max_abs_delta_z": max_z, "max_abs_delta_param": max_param,
                                  "max_abs_delta_contrib_m": max_contrib if compared else None})

    action = f"written=0 would_write={len(missing)}" if check_only else f"written={len(missing)}"
    delta_note = f" max |Δcontrib|={max_contrib:.6g} m" if compared else ""
    print(f"{folder}: starts={len(starts)} max |Δz|={max_z:.6g} max |Δparam|={max_param:.6g} "
          f"{action} compared={compared}{delta_note}", flush=True)


def run_folders(folder, folds):
    if folder.is_dir() and folds and folder.name.endswith("_lwo"):
        children = sorted(path for path in folder.iterdir()
                          if path.is_dir() and re.fullmatch(r"fold_\d+", path.name))
        if children:
            return children
    return [folder]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", metavar="RUN", type=Path, nargs="+")
    parser.add_argument("--check-only", action="store_true", help="Check saved outputs without writing contributions")
    parser.add_argument("--folds", action="store_true", help="Replay the fold folders of assembled _lwo runs")
    args = parser.parse_args()
    torch.set_num_threads(int(os.environ.get("PFE_THREADS", 4)))

    status = 0
    for run in args.runs:
        folder = run if run.is_dir() else RESULTS / run
        for child in run_folders(folder, args.folds):
            try:
                replay_run(child, check_only=args.check_only)
            except (OSError, ValueError, KeyError, RuntimeError, subprocess.CalledProcessError) as error:
                print(f"{child}: replay failed: {error}", file=sys.stderr, flush=True)
                status = 1
    return status


if __name__ == "__main__":
    sys.exit(main())
