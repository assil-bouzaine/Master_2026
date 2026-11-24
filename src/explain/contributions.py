"""Exact additive driver decomposition for the hybrid response model (Phase 5).

    PFE_DATASET=v4 python -m src.explain.contributions RUN --target 2024-06-01:2024-09-30
    PFE_DATASET=v4 python -m src.explain.contributions RUN --target 2024-06-01:2024-09-30 \\
        --reference 2023-06-01:2023-09-30 --well 10964X0119/NYLS-1 10906X0039/C2-1

Why this module exists (docs/analysis_plan.md §8 and §12; docs/competency_questions.md CQ10)
--------------------------------------------------------------------------------------------
The hybrid model (``src/models/response.py``) writes each start's simulated groundwater head as
the well's training-period mean ``mu`` plus an intercept ``d_m`` plus a sum of per-stress
convolution terms (and, when enabled, a fixed seasonal ``residual``). Because that sum is exact,
we can compute how much each stress, report group, and ontology driver group moved the simulated
head over any target window, relative to a stated reference condition, together with how stable
those numbers are across starts and which data-quality caveats apply.

An exact additive decomposition explains the **model's computation**, not the physical
contribution (analysis plan §12). Missing measurements, forcing assumptions, model structure,
and groundwater memory remain competing physical explanations.

Reference conditions (analysis plan §8 and §12; docs/notes/step15_explanations.md)
----------------------------------------------------------------------------------
- ``"average_forcing"`` (**default**, input space): set every model input column (all wells, all
  weeks, including the ``kernel_weeks - 1`` pre-record padding slots) to its training-period
  seasonal mean at each ISO week of the year (week 53 merged into week 52), replay each saved
  start once, evaluate ``net.contributions`` on those average-year inputs, and subtract the
  resulting reference contribution per stress. "Compared with an average year" therefore means
  "compared with what the model simulates under average-year forcing", so for this linear model
  the stated anomaly equals the input-space intervention by construction. The fixed seasonal
  ``residual`` has no input and keeps its own value under average-year forcing: its anomaly is
  the residual minus its own training-period ISO-week seasonal mean.
- ``"training_seasonal"`` (output-space sensitivity): for each seed, well, and stress, subtract
  the mean saved contribution over the run's training weeks at the same ISO week of the year
  (week 53 merged into week 52). Kept as a sensitivity because, for long-memory stresses, the
  2005–2019 output mean contains the model's response to the wetter 2000–2004 warm-up years.
- Explicit window ``("YYYY-MM-DD", "YYYY-MM-DD")``: mean contribution over the target window
  minus mean contribution over the reference window (used for event contrasts such as summer
  2024 vs summer 2023).

No sentence, no SPARQL query, and no plot lives here: later Phase 5 modules build on these
numbers.
"""
from __future__ import annotations

import argparse
from collections.abc import Iterable
import json
import os
from pathlib import Path
import re
from typing import NamedTuple

import numpy as np
import pandas as pd
import torch

from src.config import DATASET, INTERIM, PROCESSED, R3_STARTS, RESULTS_DIR, ROOT
from src.dataset.build import MODEL_START, TRAIN_END
from src.dataset.placeholders import load_mask
from src.dataset.pumping import seasonal_drinking_water
from src.models import response as R
from src.models.routing import RECONSTRUCTIONS, baseline_edges, load_arm, pumping_table

SD_FLOOR = R.SD_FLOOR
GROUPS_PATH = ROOT / "configs" / "explain_groups.csv"
RECONSTRUCT_TOL_M = 1e-4
SUM_TOL_M = 1e-9

_CONTRIB_RE = re.compile(r"^contrib_seed_(\d+)\.parquet$")
_PARAMS_RE = re.compile(r"^params_seed_(\d+)\.csv$")
_SEED_RE = re.compile(r"^seed_(\d+)\.parquet$")

# In-memory cache of replayed reference contributions for ``reference="average_forcing"``.
# Keyed by (resolved_run_dir, train_start, train_end, seed, cfg_mtime_ns, cfg_size, ckpt_mtime_ns, ckpt_size)
# -> (codes_tuple, weeks_index, {logical_stress: (N, T) float64 array}).
_REF_CONTRIB_CACHE: dict[tuple, tuple[tuple[str, ...], pd.DatetimeIndex, dict[str, np.ndarray]]] = {}


class RunData(NamedTuple):
    """Loaded configuration, long-format per-stress contributions, and per-well intercepts."""

    config: dict
    contrib: pd.DataFrame
    d_m: pd.DataFrame


def _run_dir(run: str | Path, dataset: str = DATASET) -> Path:
    """Resolve a run name or explicit directory path to the run folder."""
    path = Path(run)
    if isinstance(run, Path) or path.is_absolute() or (path / "config.json").is_file():
        return path
    if dataset == DATASET and os.environ.get("PFE_RESULTS"):
        return RESULTS_DIR / run
    return ROOT / "results" / dataset / run


def _dataset_dir(dataset: str = DATASET, dataset_dir: str | Path | None = None) -> Path:
    """Resolve the processed dataset directory."""
    return Path(dataset_dir) if dataset_dir is not None else PROCESSED / f"dataset_{dataset}"


def _parse_window(window: str | tuple[str, str] | list[str]) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Parse ``("YYYY-MM-DD", "YYYY-MM-DD")`` or ``"YYYY-MM-DD:YYYY-MM-DD"`` into timestamps."""
    if isinstance(window, str):
        parts = window.split(":")
        if len(parts) != 2:
            raise ValueError(f"Window string must have form 'YYYY-MM-DD:YYYY-MM-DD', got {window!r}")
        start_raw, end_raw = parts
    elif isinstance(window, (tuple, list)) and len(window) == 2:
        start_raw, end_raw = window
    else:
        raise ValueError(f"Window must be a (start, end) pair or 'start:end' string, got {window!r}")
    start, end = pd.Timestamp(start_raw), pd.Timestamp(end_raw)
    if pd.isna(start) or pd.isna(end):
        raise ValueError(f"Invalid dates in window: {window!r}")
    if start > end:
        raise ValueError(f"Window start {start.date()} is after end {end.date()}")
    return start, end


def _iso_week_of_year(weeks: pd.Series | pd.DatetimeIndex) -> np.ndarray:
    """ISO week number (1..52) with week 53 merged into week 52."""
    idx = pd.DatetimeIndex(weeks)
    return idx.isocalendar().week.clip(upper=52).to_numpy(dtype=np.int64)


def _padded_weeks(weeks: pd.DatetimeIndex | np.ndarray, kernel_weeks: int) -> pd.DatetimeIndex:
    """Extend a weekly DatetimeIndex backward by ``kernel_weeks - 1`` 7-day steps."""
    wks = pd.DatetimeIndex(weeks)
    if kernel_weeks <= 1:
        return wks
    pad = pd.date_range(end=wks[0] - pd.Timedelta(days=7), periods=kernel_weeks - 1, freq="7D")
    return pad.append(wks)


def reference_inputs(
    X: dict[str, np.ndarray],
    weeks: pd.DatetimeIndex | np.ndarray,
    kernel_weeks: int,
    train_window: tuple[str | pd.Timestamp, str | pd.Timestamp],
) -> dict[str, np.ndarray]:
    """Compute per-well, per-input seasonal reference arrays over the full padded timeline.

    For each well and input column, each ISO week of the year (1..52, with week 53 merged into
    week 52) gets the mean of the unpadded input over the run's training weeks at that ISO week.
    The ``kernel_weeks - 1`` pre-record padding slots receive the same seasonal values stepped
    backward by 7 days so every convolution lag sees average-year forcing.
    """
    wks = pd.DatetimeIndex(weeks)
    tr_start, tr_end = pd.Timestamp(train_window[0]), pd.Timestamp(train_window[1])
    train_mask = (wks >= tr_start) & (wks <= tr_end)
    if not train_mask.any():
        raise ValueError(f"No weeks fall inside training window {tr_start.date()}..{tr_end.date()}")

    padded = _padded_weeks(wks, kernel_weeks)
    woy_padded = _iso_week_of_year(padded)  # 1..52, length T + K - 1
    woy_unpadded = woy_padded[kernel_weeks - 1 :]  # length T
    woy_train = woy_unpadded[train_mask]

    needed_woys = set(int(w) for w in np.unique(woy_padded))
    present_woys = set(int(w) for w in np.unique(woy_train))
    missing_woys = sorted(needed_woys - present_woys)
    if missing_woys:
        raise ValueError(
            f"Training window {tr_start.date()}..{tr_end.date()} lacks ISO week(s) {missing_woys}"
        )

    woy_masks = {w: (woy_train == w) for w in present_woys}
    woy_idx = woy_padded - 1  # 0..51

    X_ref: dict[str, np.ndarray] = {}
    for col, arr in X.items():
        unpadded = np.asarray(arr[:, kernel_weeks - 1 :], dtype=np.float64)
        n_wells = unpadded.shape[0]
        means = np.zeros((n_wells, 52), dtype=np.float64)
        tr_vals = unpadded[:, train_mask]
        for w, mask in woy_masks.items():
            means[:, w - 1] = tr_vals[:, mask].mean(axis=1)
        X_ref[col] = means[:, woy_idx].astype(arr.dtype, copy=False)
    return X_ref


def clear_reference_cache() -> None:
    """Clear the in-memory cache of replayed average-forcing reference contributions."""
    _REF_CONTRIB_CACHE.clear()


def _ref_cache_key(
    run_dir: Path,
    tr_start: pd.Timestamp,
    tr_end: pd.Timestamp,
    seed: int,
) -> tuple:
    cfg_path = run_dir / "config.json"
    ckpt_path = run_dir / f"seed_{seed}.pt"
    if not ckpt_path.is_file():
        raise FileNotFoundError(
            f"Missing checkpoint {ckpt_path} required for reference='average_forcing'"
        )
    cfg_st = cfg_path.stat()
    ckpt_st = ckpt_path.stat()
    return (
        str(run_dir.resolve()),
        str(tr_start.date()),
        str(tr_end.date()),
        int(seed),
        cfg_st.st_mtime_ns,
        cfg_st.st_size,
        ckpt_st.st_mtime_ns,
        ckpt_st.st_size,
    )


def _replayed_reference_contributions(
    run_dir: Path,
    config: dict,
    seeds: list[int],
    tr_window: tuple[pd.Timestamp, pd.Timestamp],
    *,
    prep: dict | None = None,
) -> dict[int, tuple[tuple[str, ...], pd.DatetimeIndex, dict[str, np.ndarray]]]:
    """Replay each start on average-year forcing once and cache per-stress contributions in memory.

    Builds the reference inputs once per run (all wells, all weeks, all input columns) on cache
    miss, runs ``net.contributions(X_ref)`` for each uncached start, merges the ``gate3`` river
    slots (``river_c`` + ``river`` -> ``river``) to match ``contrib_seed_<k>.parquet``, and stores
    the full ``(N_wells, T_weeks)`` float64 arrays in ``_REF_CONTRIB_CACHE``.
    """
    tr_start, tr_end = tr_window
    keys = {seed: _ref_cache_key(run_dir, tr_start, tr_end, seed) for seed in seeds}
    missing_seeds = [seed for seed in seeds if keys[seed] not in _REF_CONTRIB_CACHE]

    if missing_seeds:
        if prep is None:
            prep = R.prepare(R.args_from_config(config), verbose=False)
        data_r = prep["data"]
        ref_codes = tuple(str(c) for c in data_r["codes"])
        ref_weeks = pd.DatetimeIndex(pd.to_datetime(data_r["weeks"]))
        kernel_weeks = int(prep["model_kwargs"]["kernel_weeks"])
        X_ref = reference_inputs(data_r["X"], ref_weeks, kernel_weeks, (tr_start, tr_end))
        X_ref_t = {k: torch.from_numpy(v) for k, v in X_ref.items()}

        for seed in missing_seeds:
            net, _ = R.replay(run_dir, seed, prep=prep)
            with torch.no_grad():
                c_ref = net.contributions(X_ref_t).numpy().astype(np.float64)  # (N, R, T)
            stress_arrays: dict[str, np.ndarray] = {}
            for r, name in enumerate(net.names):
                logical = "river" if name == "river_c" else name
                if logical in stress_arrays:
                    stress_arrays[logical] = stress_arrays[logical] + c_ref[:, r, :]
                else:
                    stress_arrays[logical] = c_ref[:, r, :].copy()
            _REF_CONTRIB_CACHE[keys[seed]] = (ref_codes, ref_weeks, stress_arrays)

    return {seed: _REF_CONTRIB_CACHE[keys[seed]] for seed in seeds}


def load_groups(path: str | Path = GROUPS_PATH) -> pd.DataFrame:
    """Load the stress -> report_group / driver_group mapping from ``configs/explain_groups.csv``."""
    df = pd.read_csv(path, keep_default_na=False)
    required = {"stress", "report_group", "driver_group"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"{path}: missing required columns {missing}")
    if df["stress"].duplicated().any():
        dups = df.loc[df["stress"].duplicated(), "stress"].tolist()
        raise ValueError(f"{path}: duplicated stress rows {dups}")
    return df


def training_window(
    config: dict,
    dataset: str = DATASET,
    dataset_dir: str | Path | None = None,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return ``(train_start, train_end)`` used by a run.

    Reads ``config["train_start"]`` when set (R3 ``f25``/``f50`` regimes, defined in
    ``src.config.R3_STARTS``), otherwise the dataset's training split start (``splits.json``
    ``"train"[0]``, i.e. ``2005-01-01`` in v4). The end is ``TRAIN_END`` from
    ``src.dataset.build`` (``2019-12-31``).
    """
    ds = _dataset_dir(dataset, dataset_dir)
    splits_path = ds / "splits.json"
    default_start = MODEL_START
    end = TRAIN_END
    if splits_path.is_file():
        splits = json.loads(splits_path.read_text(encoding="utf-8"))
        if "train" in splits and len(splits["train"]) == 2:
            default_start = splits["train"][0]
            end = splits["train"][1]
    start = config.get("train_start") or default_start
    return pd.Timestamp(start), pd.Timestamp(end)


def _seed_files(run_dir: Path, pattern: re.Pattern[str]) -> dict[int, Path]:
    found: dict[int, Path] = {}
    for path in run_dir.iterdir():
        if not path.is_file():
            continue
        match = pattern.match(path.name)
        if match:
            found[int(match.group(1))] = path
    return dict(sorted(found.items()))


def load_run(run: str | Path, dataset: str = DATASET) -> RunData:
    """Load ``config.json``, every ``contrib_seed_<k>.parquet``, and every ``params_seed_<k>.csv``.

    Returns ``RunData(config, contrib, d_m)`` where:
    - ``config`` is the parsed ``config.json`` dict;
    - ``contrib`` is a long DataFrame with columns ``seed, code_bss, week, stress, value_m``
      (``value_m`` as float64);
    - ``d_m`` is a DataFrame with columns ``seed, code_bss, d_m`` (``d_m`` as float64).

    Raises ``FileNotFoundError`` or ``ValueError`` if required files are missing or if seeds do
    not share the exact same wells, weeks, well-week grid, and stress columns.
    """
    run_dir = _run_dir(run, dataset=dataset)
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Run directory not found: {run_dir}")
    config_path = run_dir / "config.json"
    if not config_path.is_file():
        raise FileNotFoundError(f"Missing config.json in {run_dir}")
    config = json.loads(config_path.read_text(encoding="utf-8"))

    contrib_files = _seed_files(run_dir, _CONTRIB_RE)
    params_files = _seed_files(run_dir, _PARAMS_RE)
    if not contrib_files:
        raise FileNotFoundError(f"No contrib_seed_<k>.parquet files found in {run_dir}")
    if set(contrib_files) != set(params_files):
        raise ValueError(
            f"{run_dir}: seed mismatch between contrib_seed_*.parquet ({sorted(contrib_files)}) "
            f"and params_seed_*.csv ({sorted(params_files)})"
        )

    ref_stresses: tuple[str, ...] | None = None
    ref_wells: set[str] | None = None
    ref_weeks: np.ndarray | None = None
    ref_grid: pd.MultiIndex | None = None
    contrib_parts: list[pd.DataFrame] = []
    dm_parts: list[pd.DataFrame] = []

    for seed in sorted(contrib_files):
        cdf = pd.read_parquet(contrib_files[seed])
        for key in ("code_bss", "week"):
            if key not in cdf.columns:
                raise ValueError(f"{contrib_files[seed].name}: missing required column {key!r}")
        cdf["week"] = pd.to_datetime(cdf["week"])
        stress_cols = tuple(c for c in cdf.columns if c not in ("code_bss", "week"))
        if not stress_cols:
            raise ValueError(f"{contrib_files[seed].name}: no stress columns found")
        if cdf.duplicated(["code_bss", "week"]).any():
            raise ValueError(f"{contrib_files[seed].name}: duplicated (code_bss, week) rows")

        cdf = cdf.sort_values(["code_bss", "week"], kind="mergesort").reset_index(drop=True)
        wells = set(cdf["code_bss"])
        weeks = np.sort(cdf["week"].unique())
        grid = pd.MultiIndex.from_frame(cdf[["code_bss", "week"]])

        if ref_stresses is None:
            ref_stresses, ref_wells, ref_weeks, ref_grid = stress_cols, wells, weeks, grid
        else:
            if set(stress_cols) != set(ref_stresses):
                raise ValueError(
                    f"{run_dir.name}: seed {seed} stresses {sorted(stress_cols)} "
                    f"differ from seed {min(contrib_files)} stresses {sorted(ref_stresses)}"
                )
            if wells != ref_wells:
                raise ValueError(
                    f"{run_dir.name}: seed {seed} wells differ from seed {min(contrib_files)}"
                )
            if not np.array_equal(weeks, ref_weeks):
                raise ValueError(
                    f"{run_dir.name}: seed {seed} weeks differ from seed {min(contrib_files)}"
                )
            if not grid.equals(ref_grid):
                raise ValueError(
                    f"{run_dir.name}: seed {seed} (code_bss, week) grid differs from "
                    f"seed {min(contrib_files)}"
                )

        long_df = cdf.melt(
            id_vars=["code_bss", "week"],
            value_vars=list(ref_stresses),
            var_name="stress",
            value_name="value_m",
        )
        long_df["value_m"] = long_df["value_m"].astype(np.float64)
        long_df.insert(0, "seed", int(seed))
        contrib_parts.append(long_df)

        pdf = pd.read_csv(params_files[seed])
        for key in ("code_bss", "d_m"):
            if key not in pdf.columns:
                raise ValueError(f"{params_files[seed].name}: missing required column {key!r}")
        if pdf["code_bss"].duplicated().any():
            raise ValueError(f"{params_files[seed].name}: duplicated code_bss rows")
        if set(pdf["code_bss"]) != ref_wells:
            raise ValueError(
                f"{params_files[seed].name}: wells do not match {contrib_files[seed].name}"
            )
        dm = pdf[["code_bss", "d_m"]].copy()
        dm["d_m"] = dm["d_m"].astype(np.float64)
        dm.insert(0, "seed", int(seed))
        dm_parts.append(dm)

    contrib = pd.concat(contrib_parts, ignore_index=True)
    d_m = pd.concat(dm_parts, ignore_index=True)
    return RunData(config=config, contrib=contrib, d_m=d_m)


def _well_normalisation_stats(
    config: dict,
    dataset: str = DATASET,
    dataset_dir: str | Path | None = None,
    train_window: tuple[str, str] | None = None,
) -> pd.DataFrame:
    """Compute each well's training-period mean ``mu`` and ``sd`` from ``heads_weekly.parquet``.

    Matches ``src.models.features.build_panel(train_start=...)``: unscreened weekly heads inside
    ``[train_start, train_end]``, where ``train_start`` is ``config["train_start"]`` for R3 runs
    and the dataset's training split start (``2005-01-01`` in v4) for R1, R2, and Refit runs.
    """
    ds = _dataset_dir(dataset, dataset_dir)
    heads = pd.read_parquet(ds / "heads_weekly.parquet", columns=["code_bss", "week", "head"])
    heads["week"] = pd.to_datetime(heads["week"])
    if train_window is not None:
        start, end = _parse_window(train_window)
    else:
        start, end = training_window(config, dataset=dataset, dataset_dir=ds)
    sub = heads[heads["week"].between(start, end)]
    return sub.groupby("code_bss")["head"].agg(mu="mean", sd="std")


def _mean_reconstructed_anomaly(contrib: pd.DataFrame, d_m: pd.DataFrame) -> pd.DataFrame:
    """Per (code_bss, week), mean over seeds of ``d_m + sum_stress value_m`` (metres above mu)."""
    per_seed = (
        contrib.groupby(["seed", "code_bss", "week"], sort=False)["value_m"]
        .sum()
        .reset_index()
        .merge(d_m, on=["seed", "code_bss"], how="left", validate="many_to_one")
    )
    if per_seed["d_m"].isna().any():
        raise ValueError("Missing d_m intercept for some (seed, code_bss) pairs")
    per_seed["anom_m"] = per_seed["value_m"] + per_seed["d_m"]
    return per_seed.groupby(["code_bss", "week"], sort=False)["anom_m"].mean().reset_index()


def _filter_wells(
    available: Iterable[str],
    wells: Iterable[str] | None,
) -> list[str]:
    avail_set = set(available)
    if wells is None:
        return sorted(avail_set)
    selected = list(dict.fromkeys(wells))
    missing = sorted(set(selected) - avail_set)
    if missing:
        raise ValueError(f"Unknown wells not present in run: {missing}")
    return selected


def reconstruct(
    run: str | Path,
    dataset: str = DATASET,
    *,
    tol: float | None = RECONSTRUCT_TOL_M,
    wells: Iterable[str] | None = None,
    dataset_dir: str | Path | None = None,
    train_window: tuple[str, str] | None = None,
) -> float:
    """Verify that ``mu + mean_seed(d_m + sum_stress value_m)`` reproduces ``predictions.parquet``.

    In ``src/models/response.py``, each start encodes ``out = d + sum_r c_r (+ residual)`` as
    ``z = out / max(sd, SD_FLOOR)`` (float32), and ``predictions.parquet`` stores
    ``mu + max(sd, SD_FLOOR) * mean_seed(z)`` (since commit ``f2cd482``). Because
    ``max(sd, SD_FLOOR)`` is constant across seeds per well, it cancels algebraically, leaving
    ``pred == mu + mean_seed(d_m + sum_stress value_m)`` up to float32 storage precision.

    Returns the maximum absolute difference in metres across all checked well-weeks. Raises
    ``ValueError`` if ``tol`` is not None and the maximum difference exceeds ``tol``.
    """
    run_dir = _run_dir(run, dataset=dataset)
    data = load_run(run_dir, dataset=dataset)
    pred_path = run_dir / "predictions.parquet"
    if not pred_path.is_file():
        raise FileNotFoundError(f"Missing predictions.parquet in {run_dir}")

    pred = pd.read_parquet(pred_path)
    if "task" in pred.columns:
        pred = pred[pred["task"] == "simulation"]
    if "horizon" in pred.columns:
        pred = pred[pred["horizon"] == 0]
    pred = pred[["code_bss", "week", "pred"]].copy()
    pred["week"] = pd.to_datetime(pred["week"])
    if pred.duplicated(["code_bss", "week"]).any():
        raise ValueError(f"{pred_path}: duplicated (code_bss, week) rows")

    contrib, d_m = data.contrib, data.d_m
    selected = _filter_wells(d_m["code_bss"].unique(), wells)
    if wells is not None:
        contrib = contrib[contrib["code_bss"].isin(selected)]
        d_m = d_m[d_m["code_bss"].isin(selected)]
        pred = pred[pred["code_bss"].isin(selected)]

    stats = _well_normalisation_stats(
        data.config, dataset=dataset, dataset_dir=dataset_dir, train_window=train_window
    )
    mean_anom = _mean_reconstructed_anomaly(contrib, d_m)
    merged = pred.merge(mean_anom, on=["code_bss", "week"], how="outer", indicator=True)
    if (merged["_merge"] != "both").any():
        counts = merged["_merge"].value_counts().to_dict()
        raise ValueError(f"{run_dir.name}: well-week mismatch with predictions.parquet: {counts}")
    merged["mu"] = merged["code_bss"].map(stats["mu"])
    if merged["mu"].isna().any():
        bad = sorted(merged.loc[merged["mu"].isna(), "code_bss"].unique())
        raise ValueError(f"{run_dir.name}: missing training mean mu for wells {bad}")

    merged["recon_m"] = merged["mu"] + merged["anom_m"]
    merged["abs_diff_m"] = (merged["pred"].astype(np.float64) - merged["recon_m"]).abs()
    idx_max = merged["abs_diff_m"].idxmax()
    max_diff = float(merged.loc[idx_max, "abs_diff_m"])

    if tol is not None and max_diff > tol:
        worst = merged.loc[idx_max]
        offending = sorted(merged.loc[merged["abs_diff_m"] > tol, "code_bss"].unique())
        raise ValueError(
            f"{run_dir.name}: max reconstruction difference {max_diff:.3e} m exceeds "
            f"{tol:.1e} m (worst: {worst['code_bss']} on {worst['week'].date()}; "
            f"{len(offending)} well(s) above tolerance: {offending})"
        )
    return max_diff


def reconstruct_from_seeds(
    run: str | Path,
    dataset: str = DATASET,
    *,
    tol: float | None = RECONSTRUCT_TOL_M,
    wells: Iterable[str] | None = None,
    dataset_dir: str | Path | None = None,
    train_window: tuple[str, str] | None = None,
) -> float:
    """Check ``mu + mean_seed(d_m + sum_stress value_m)`` against ``SD_FLOOR``-decoded ``seed_<k>.parquet``.

    Useful for historical ladder runs saved before commit ``f2cd482`` (2026-11-20), whose
    ``predictions.parquet`` decoded the constant-head non-core well ``10984X0003/AIGUAN`` with
    unclipped ``sd`` while its ``seed_<k>.parquet`` files were encoded with ``max(sd, SD_FLOOR)``.
    """
    run_dir = _run_dir(run, dataset=dataset)
    data = load_run(run_dir, dataset=dataset)
    seed_files = _seed_files(run_dir, _SEED_RE)
    contrib_seeds = sorted(data.d_m["seed"].unique().tolist())
    if sorted(seed_files) != contrib_seeds:
        raise ValueError(
            f"{run_dir.name}: seed_<k>.parquet files {sorted(seed_files)} do not match "
            f"contrib seeds {contrib_seeds}"
        )

    contrib, d_m = data.contrib, data.d_m
    selected = _filter_wells(d_m["code_bss"].unique(), wells)
    if wells is not None:
        contrib = contrib[contrib["code_bss"].isin(selected)]
        d_m = d_m[d_m["code_bss"].isin(selected)]

    stats = _well_normalisation_stats(
        data.config, dataset=dataset, dataset_dir=dataset_dir, train_window=train_window
    )
    z_parts = []
    for seed, path in seed_files.items():
        sdf = pd.read_parquet(path, columns=["code_bss", "week", "z"])
        sdf["week"] = pd.to_datetime(sdf["week"])
        if wells is not None:
            sdf = sdf[sdf["code_bss"].isin(selected)]
        z_parts.append(sdf)
    mean_z = pd.concat(z_parts, ignore_index=True).groupby(["code_bss", "week"], sort=False)["z"].mean().reset_index()

    mean_anom = _mean_reconstructed_anomaly(contrib, d_m)
    merged = mean_z.merge(mean_anom, on=["code_bss", "week"], how="outer", indicator=True)
    if (merged["_merge"] != "both").any():
        raise ValueError(f"{run_dir.name}: well-week mismatch with seed_<k>.parquet")
    merged["mu"] = merged["code_bss"].map(stats["mu"])
    merged["sd_floored"] = merged["code_bss"].map(stats["sd"]).clip(lower=SD_FLOOR)
    merged["decoded_m"] = merged["mu"] + merged["sd_floored"] * merged["z"].astype(np.float64)
    merged["recon_m"] = merged["mu"] + merged["anom_m"]
    max_diff = float((merged["decoded_m"] - merged["recon_m"]).abs().max())

    if tol is not None and max_diff > tol:
        raise ValueError(
            f"{run_dir.name}: max seed-decoded reconstruction difference {max_diff:.3e} m "
            f"exceeds {tol:.1e} m"
        )
    return max_diff


def run_metadata(config: dict) -> dict:
    """Echo the run's regime, arm, export policy, pumping reconstruction, mode, and protocol."""
    fold = config.get("fold")
    train_start = config.get("train_start")
    refit_from = config.get("refit_from")
    r3_by_start = {start: name for name, start in R3_STARTS.items()}
    if refit_from is not None:
        regime = "refit"
    elif fold is not None:
        regime = f"R2_fold_{fold}"
    elif train_start is not None:
        regime = f"R3_{r3_by_start[train_start]}" if train_start in r3_by_start else f"R3_{train_start}"
    else:
        regime = "R1"

    arm = config.get("arm")
    policy = config.get("policy") if arm is not None else None
    reconstruction = int(config.get("pumping_reconstruction", 1))
    mode = config.get("mode")
    lam = config.get("lam")
    fixed_steps = config.get("fixed_steps")

    proto_parts = [str(mode or "unknown")]
    if mode == "pooled" and lam is not None:
        proto_parts.append(f"l{float(lam):g}")
    if fixed_steps is not None:
        proto_parts.append(f"fixed{int(fixed_steps)}")
    else:
        proto_parts.append("earlystop")
    if config.get("gain_units") == "sd":
        proto_parts.append("gain_sd")
    protocol = "_".join(proto_parts)

    return {
        "run": config.get("run"),
        "dataset": config.get("dataset"),
        "regime": regime,
        "arm": arm,
        "export_policy": policy,
        "pumping_reconstruction": reconstruction,
        "pumping_reconstruction_name": RECONSTRUCTIONS.get(reconstruction, str(reconstruction)),
        "mode": mode,
        "lam": lam,
        "fixed_steps": fixed_steps,
        "signs": config.get("signs", "structure"),
        "residual": config.get("residual", "none"),
        "protocol": protocol,
    }


def _sign_agreement(values: np.ndarray, mean_value: float) -> float:
    """Share of seeds whose sign matches ``np.sign(mean_value)`` (0 counts as its own sign)."""
    if len(values) == 0:
        return float("nan")
    target_sign = np.sign(mean_value)
    return float(np.mean(np.sign(values) == target_sign))


def _summarise_across_seeds(per_seed_df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    """Aggregate per-seed values across seeds into mean, sample sd (ddof=1), and sign agreement."""
    rows = []
    for keys, grp in per_seed_df.groupby(group_cols, sort=True):
        if not isinstance(keys, tuple):
            keys = (keys,)
        vals = grp["value_m"].to_numpy(dtype=np.float64)
        mean_val = float(np.mean(vals))
        sd_val = float(np.std(vals, ddof=1)) if len(vals) > 1 else float("nan")
        rec = dict(zip(group_cols, keys))
        rec.update(
            {
                "mean_m": mean_val,
                "sd_m": sd_val,
                "sign_agreement": _sign_agreement(vals, mean_val),
                "n_seeds": int(len(vals)),
            }
        )
        rows.append(rec)
    cols = [*group_cols, "mean_m", "sd_m", "sign_agreement", "n_seeds"]
    return pd.DataFrame(rows, columns=cols)


def _pumping_edges_for_config(config: dict, dataset: str = DATASET) -> pd.DataFrame:
    """Return the well's ``pumping`` and ``pumping_unattributed`` edges for the run's arm."""
    arm = config.get("arm")
    policy = config.get("policy", "main")
    if arm is None or arm == "baseline":
        edges = baseline_edges()
    else:
        edges, _ = load_arm(arm, policy=policy, dataset=dataset)
    return edges[edges["relation"].isin(("pumping", "pumping_unattributed"))].copy()


def _load_pumping_for_flags(
    reconstruction: int,
    dataset: str = DATASET,
    dataset_dir: str | Path | None = None,
    *,
    facilities: set[str] | None = None,
    years: set[int] | None = None,
) -> pd.DataFrame:
    """Load the weekly pumping table matching ``reconstruction`` (1, 2, or 3) with ``imputed`` intact.

    Reconstructions 1, 2, and 3 share the exact same ``imputed`` flag on every
    ``(code_ouvrage, usage, week)`` row, but their weekly ``volume_m3`` profiles differ (seasonal
    vs flat drinking water; deficit vs crop-calendar irrigation), which shifts the volume-weighted
    imputed share in seasonal windows.
    """
    if dataset_dir is None and dataset == DATASET:
        pw = pumping_table(reconstruction)
        if facilities is not None:
            pw = pw[pw["code_ouvrage"].isin(facilities)]
        if years is not None:
            pw = pw[pd.to_datetime(pw["week"]).dt.year.isin(years)]
        if reconstruction == 2 or pw.empty:
            return pw
        pts = pd.read_parquet(_dataset_dir(dataset) / "pumping_points.parquet")
        return seasonal_drinking_water(pw, pts)

    ds = _dataset_dir(dataset, dataset_dir)
    if reconstruction == 3 and dataset_dir is None:
        path = INTERIM / f"pumping_weekly_cropcal_{dataset}.parquet"
        if not path.is_file():
            raise FileNotFoundError(f"{path} is missing; run python -m src.dataset.pumping_cropcal")
        pw = pd.read_parquet(path)
    else:
        pw = pd.read_parquet(ds / "pumping_weekly.parquet")
    if facilities is not None:
        pw = pw[pw["code_ouvrage"].isin(facilities)]
    if years is not None:
        pw = pw[pd.to_datetime(pw["week"]).dt.year.isin(years)]
    if reconstruction == 2 or pw.empty:
        return pw

    pts_path = ds / "pumping_points.parquet"
    forcing_path = ds / "forcing_weekly.parquet"
    if pts_path.is_file() and forcing_path.is_file():
        pts = pd.read_parquet(pts_path)
        forcing = pd.read_parquet(forcing_path, columns=["cell_id", "week", "ETP", "rain"])
        forcing["week"] = pd.to_datetime(forcing["week"])
        forcing["year"] = forcing["week"].dt.year
        forcing["deficit"] = (forcing["ETP"] - forcing["rain"]).clip(lower=0)
        forcing.loc[~forcing["week"].dt.month.between(4, 10), "deficit"] = 0.0
        tot = forcing.groupby(["cell_id", "year"])["deficit"].transform("sum")
        forcing["w"] = forcing["deficit"] / tot.replace(0.0, np.nan)
        d = pw.merge(pts[["code_ouvrage", "cell_id"]], on="code_ouvrage", how="left")
        dw = d["usage"] == "drinking water"
        d["week"] = pd.to_datetime(d["week"])
        d["year"] = d["week"].dt.year
        annual = d.loc[dw].groupby(["code_ouvrage", "year"])["volume_m3"].transform("sum")
        d = d.merge(forcing[["cell_id", "week", "w"]], on=["cell_id", "week"], how="left")
        flat = d.loc[dw, "volume_m3"]
        d.loc[dw, "volume_m3"] = 0.5 * flat + 0.5 * annual * d.loc[dw, "w"].fillna(0.0)
        return d[pw.columns]
    return pw


def data_quality_flags(
    config: dict,
    wells: Iterable[str],
    target_weeks: pd.DatetimeIndex,
    *,
    dataset: str = DATASET,
    dataset_dir: str | Path | None = None,
    edges: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Compute per-well data-quality flags over ``target_weeks`` (analysis plan §12).

    Returns one row per well with:
    - ``code_bss``, ``core`` (bool if ``wells.parquet`` has it), ``n_weeks``;
    - ``n_observed``, ``share_observed``: weeks in the window with a non-null observed head;
    - ``n_strict``, ``share_strict``: weeks with a strictly validated observed head
      (``share_not_validated == 0`` and not masked as a suspect placeholder, matching the
      ``"strict"`` variant of ``src/models/evaluate.py``);
    - ``n_placeholder``, ``share_placeholder``: weeks masked as suspect placeholders
      (``placeholder_weeks.parquet``, via ``src.dataset.placeholders.load_mask()``);
    - ``routed_pumping_m3``, ``imputed_pumping_m3``, ``share_pumping_imputed``: routed pumping
      volume (weighted sum across the well's ``pumping`` and ``pumping_unattributed`` edges using
      the run's pumping reconstruction) and the share coming from ``imputed == True`` rows
      (``NaN`` when routed pumping volume is zero).
    """
    well_list = list(dict.fromkeys(wells))
    weeks = pd.DatetimeIndex(sorted(pd.to_datetime(target_weeks).unique()))
    n_weeks = len(weeks)
    if n_weeks == 0:
        raise ValueError("target_weeks must be non-empty")

    ds = _dataset_dir(dataset, dataset_dir)
    wells_meta_path = ds / "wells.parquet"
    core_map: dict[str, bool] = {}
    if wells_meta_path.is_file():
        wm = pd.read_parquet(wells_meta_path, columns=["code_bss", "core"])
        core_map = dict(zip(wm["code_bss"], wm["core"].astype(bool)))

    heads = pd.read_parquet(
        ds / "heads_weekly.parquet",
        columns=["code_bss", "week", "head", "share_not_validated"],
    )
    heads["week"] = pd.to_datetime(heads["week"])
    heads = heads[heads["code_bss"].isin(well_list) & heads["week"].isin(weeks) & heads["head"].notna()]

    if dataset_dir is None and dataset == DATASET:
        mask_df = load_mask()
    else:
        mask_path = ds / "placeholder_weeks.parquet"
        mask_df = pd.read_parquet(mask_path) if mask_path.is_file() else None

    placeholder_pairs: set[tuple[str, pd.Timestamp]] = set()
    if mask_df is not None and not mask_df.empty:
        m_sub = mask_df.copy()
        m_sub["week"] = pd.to_datetime(m_sub["week"])
        m_sub = m_sub[m_sub["code_bss"].isin(well_list) & m_sub["week"].isin(weeks)]
        placeholder_pairs = set(zip(m_sub["code_bss"], m_sub["week"]))

    if not heads.empty:
        is_ph = [
            (code, wk) in placeholder_pairs
            for code, wk in zip(heads["code_bss"], heads["week"])
        ]
        heads = heads.assign(is_placeholder=is_ph)
        heads["is_strict"] = (heads["share_not_validated"] == 0.0) & (~heads["is_placeholder"])
        obs_counts = heads.groupby("code_bss")["week"].nunique().to_dict()
        strict_counts = heads[heads["is_strict"]].groupby("code_bss")["week"].nunique().to_dict()
    else:
        obs_counts, strict_counts = {}, {}

    ph_counts: dict[str, int] = {}
    for code, _ in placeholder_pairs:
        ph_counts[code] = ph_counts.get(code, 0) + 1

    if edges is None:
        pe = _pumping_edges_for_config(config, dataset=dataset)
    else:
        pe = edges[edges["relation"].isin(("pumping", "pumping_unattributed"))].copy()
    pe = pe[pe["dst"].isin(well_list)]

    reconstruction = int(config.get("pumping_reconstruction", 1))
    routed_tot: dict[str, float] = {}
    routed_imp: dict[str, float] = {}
    if not pe.empty:
        facs = set(pe["src"].unique())
        pw = _load_pumping_for_flags(
            reconstruction,
            dataset=dataset,
            dataset_dir=dataset_dir,
            facilities=facs,
            years=set(int(y) for y in weeks.year.unique()),
        )
        pw = pw.copy()
        pw["week"] = pd.to_datetime(pw["week"])
        pw_win = pw[pw["week"].isin(weeks) & pw["code_ouvrage"].isin(facs)]
        tot_by_fac = pw_win.groupby("code_ouvrage")["volume_m3"].sum()
        imp_by_fac = pw_win[pw_win["imputed"].astype(bool)].groupby("code_ouvrage")["volume_m3"].sum()
        pe["tot_m3"] = pe["weight"].astype(np.float64) * pe["src"].map(tot_by_fac).fillna(0.0)
        pe["imp_m3"] = pe["weight"].astype(np.float64) * pe["src"].map(imp_by_fac).fillna(0.0)
        by_well = pe.groupby("dst")[["tot_m3", "imp_m3"]].sum()
        routed_tot = by_well["tot_m3"].to_dict()
        routed_imp = by_well["imp_m3"].to_dict()

    rows = []
    for code in well_list:
        n_obs = int(obs_counts.get(code, 0))
        n_strict = int(strict_counts.get(code, 0))
        n_ph = int(ph_counts.get(code, 0))
        tot_m3 = float(routed_tot.get(code, 0.0))
        imp_m3 = float(routed_imp.get(code, 0.0))
        share_imp = imp_m3 / tot_m3 if tot_m3 > 0.0 else float("nan")
        rows.append(
            {
                "code_bss": code,
                "core": core_map.get(code, False),
                "n_weeks": n_weeks,
                "n_observed": n_obs,
                "share_observed": n_obs / n_weeks,
                "n_strict": n_strict,
                "share_strict": n_strict / n_weeks,
                "n_placeholder": n_ph,
                "share_placeholder": n_ph / n_weeks,
                "routed_pumping_m3": tot_m3,
                "imputed_pumping_m3": imp_m3,
                "share_pumping_imputed": share_imp,
            }
        )
    return pd.DataFrame(rows)


def _seasonal_output_reference(
    contrib: pd.DataFrame,
    target_weeks: pd.DatetimeIndex,
    tr_start: pd.Timestamp,
    tr_end: pd.Timestamp,
    run_name: str,
) -> pd.DataFrame:
    """For each (seed, code_bss, week, stress) in ``target_weeks``, attach the training-period
    ISO-week seasonal mean (week 53 merged into 52) as ``ref_m``."""
    train_df = contrib[contrib["week"].between(tr_start, tr_end)].copy()
    if train_df.empty:
        raise ValueError(
            f"{run_name}: no run weeks fall in training window {tr_start.date()}..{tr_end.date()}"
        )
    train_df["woy"] = _iso_week_of_year(train_df["week"])
    seasonal_ref = (
        train_df.groupby(["seed", "code_bss", "stress", "woy"], sort=False)["value_m"]
        .mean()
        .rename("ref_m")
        .reset_index()
    )
    tgt_df = contrib[contrib["week"].isin(target_weeks)].copy()
    tgt_df["woy"] = _iso_week_of_year(tgt_df["week"])
    tgt_df = tgt_df.merge(
        seasonal_ref, on=["seed", "code_bss", "stress", "woy"], how="left", validate="many_to_one"
    )
    if tgt_df["ref_m"].isna().any():
        missing_woys = sorted(tgt_df.loc[tgt_df["ref_m"].isna(), "woy"].unique().tolist())
        raise ValueError(
            f"{run_name}: training window {tr_start.date()}..{tr_end.date()} "
            f"has no weeks for target ISO week(s) {missing_woys}"
        )
    return tgt_df.drop(columns="woy")


def decompose(
    run: str | Path,
    target: str | tuple[str, str],
    reference: str | tuple[str, str] = "average_forcing",
    wells: Iterable[str] | None = None,
    *,
    dataset: str = DATASET,
    dataset_dir: str | Path | None = None,
    groups_path: str | Path = GROUPS_PATH,
    train_window: tuple[str, str] | None = None,
    edges: pd.DataFrame | None = None,
    prep: dict | None = None,
) -> dict:
    """Decompose simulated head anomalies or changes over ``target`` for every well and seed.

    Parameters
    ----------
    run : str or Path
        Run name under ``results/<dataset>/`` or path to a run directory.
    target : tuple[str, str] or str
        Inclusive target window ``("YYYY-MM-DD", "YYYY-MM-DD")`` or ``"YYYY-MM-DD:YYYY-MM-DD"``.
    reference : ``"average_forcing"`` | ``"training_seasonal"`` | tuple[str, str] | str
        Reference condition:
        - ``"average_forcing"`` (default, input space): replay each start on average-year
          forcing (every input column over all wells and all weeks set to its training-period
          ISO-week mean, week 53 merged into 52) and subtract each stress's replayed reference
          contribution. The fixed seasonal ``residual`` has no input and keeps its own value:
          its anomaly is the residual minus its own training-period ISO-week seasonal mean.
          Replayed reference contributions are cached in memory per run and start.
        - ``"training_seasonal"`` (output-space sensitivity): subtract each stress's mean
          saved contribution over the run's training weeks at the same ISO week of the year
          (week 53 merged into 52).
        - Explicit window ``(start, end)`` or ``"YYYY-MM-DD:YYYY-MM-DD"``: mean contribution
          over ``target`` minus mean contribution over the reference window.
    wells : iterable of str, optional
        Subset of ``code_bss`` to include (default: all wells in the run, core and other).
    dataset, dataset_dir, groups_path, train_window, edges, prep : optional
        Overrides primarily for sensitivity checks, reusing ``response.prepare()`` output, and
        isolated unit tests.

    Returns
    -------
    dict with keys ``run``, ``dataset``, ``target``, ``n_target_weeks``, ``reference``,
    ``n_seeds``, ``seeds``, ``stresses``, ``by_stress``, ``by_report_group``,
    ``by_driver_group``, ``total``, ``per_seed``, ``flags``, and ``metadata``.
    """
    run_dir = _run_dir(run, dataset=dataset)
    data = load_run(run_dir, dataset=dataset)
    groups = load_groups(groups_path)

    run_stresses = list(dict.fromkeys(data.contrib["stress"]))
    known_stresses = set(groups["stress"])
    unknown_stresses = sorted(set(run_stresses) - known_stresses)
    if unknown_stresses:
        raise ValueError(
            f"{run_dir.name}: run stresses absent from {Path(groups_path).name}: {unknown_stresses}"
        )
    group_map = groups.set_index("stress")

    selected_wells = _filter_wells(data.d_m["code_bss"].unique(), wells)
    contrib = data.contrib
    if wells is not None:
        contrib = contrib[contrib["code_bss"].isin(selected_wells)].copy()

    t_start, t_end = _parse_window(target)
    all_weeks = pd.DatetimeIndex(sorted(contrib["week"].unique()))
    target_weeks = all_weeks[(all_weeks >= t_start) & (all_weeks <= t_end)]
    if len(target_weeks) == 0:
        raise ValueError(
            f"{run_dir.name}: no run weeks fall in target window {t_start.date()}..{t_end.date()}"
        )

    seeds = sorted(int(s) for s in data.d_m["seed"].unique())

    if reference == "average_forcing":
        if train_window is not None:
            tr_start, tr_end = _parse_window(train_window)
        else:
            tr_start, tr_end = training_window(data.config, dataset=dataset, dataset_dir=dataset_dir)

        non_res_stresses = [s for s in run_stresses if s != "residual"]
        replayed = _replayed_reference_contributions(
            run_dir, data.config, seeds, (tr_start, tr_end), prep=prep
        )

        tgt_parts: list[pd.DataFrame] = []
        if non_res_stresses:
            tgt_non_res = contrib[
                contrib["week"].isin(target_weeks) & contrib["stress"].isin(non_res_stresses)
            ].copy()
            n_w = len(selected_wells)
            n_t = len(target_weeks)
            well_rep = np.repeat(selected_wells, n_t)
            week_tile = np.tile(target_weeks.to_numpy(), n_w)
            ref_frames: list[pd.DataFrame] = []
            for seed in seeds:
                ref_codes, ref_weeks, stress_arrays = replayed[seed]
                missing_stresses = sorted(set(non_res_stresses) - set(stress_arrays))
                if missing_stresses:
                    raise ValueError(
                        f"{run_dir.name}: replayed seed {seed} lacks stresses {missing_stresses}"
                    )
                code_to_idx = {c: i for i, c in enumerate(ref_codes)}
                missing_wells = sorted(set(selected_wells) - set(code_to_idx))
                if missing_wells:
                    raise ValueError(
                        f"{run_dir.name}: replayed seed {seed} lacks wells {missing_wells}"
                    )
                well_idx = np.array([code_to_idx[c] for c in selected_wells], dtype=np.int64)
                week_idx = ref_weeks.get_indexer(target_weeks)
                if (week_idx < 0).any():
                    bad_wks = [str(w.date()) for w in target_weeks[week_idx < 0]]
                    raise ValueError(
                        f"{run_dir.name}: replayed seed {seed} lacks target week(s) {bad_wks}"
                    )
                for s in non_res_stresses:
                    vals = stress_arrays[s][np.ix_(well_idx, week_idx)].ravel()
                    ref_frames.append(
                        pd.DataFrame(
                            {
                                "seed": seed,
                                "code_bss": well_rep,
                                "week": week_tile,
                                "stress": s,
                                "ref_m": vals,
                            }
                        )
                    )
            ref_df = pd.concat(ref_frames, ignore_index=True)
            merged_non_res = tgt_non_res.merge(
                ref_df,
                on=["seed", "code_bss", "week", "stress"],
                how="left",
                validate="one_to_one",
            )
            if merged_non_res["ref_m"].isna().any():
                raise ValueError(
                    f"{run_dir.name}: missing average_forcing reference values for some target rows"
                )
            tgt_parts.append(merged_non_res)

        if "residual" in run_stresses:
            # The fixed seasonal residual has no input: its anomaly is itself minus its own
            # training-period ISO-week seasonal mean.
            res_contrib = contrib[contrib["stress"] == "residual"]
            tgt_parts.append(
                _seasonal_output_reference(res_contrib, target_weeks, tr_start, tr_end, run_dir.name)
            )

        tgt_df = pd.concat(tgt_parts, ignore_index=True)
        tgt_df["anom_m"] = tgt_df["value_m"] - tgt_df["ref_m"]
        per_seed_stress = (
            tgt_df.groupby(["seed", "code_bss", "stress"], sort=True)["anom_m"]
            .mean()
            .rename("value_m")
            .reset_index()
        )
        ref_info = {
            "kind": "average_forcing",
            "space": "input",
            "window": (str(tr_start.date()), str(tr_end.date())),
            "woy_rule": "ISO week, 53 merged into 52",
        }
    elif reference == "training_seasonal":
        if train_window is not None:
            tr_start, tr_end = _parse_window(train_window)
        else:
            tr_start, tr_end = training_window(data.config, dataset=dataset, dataset_dir=dataset_dir)
        tgt_df = _seasonal_output_reference(contrib, target_weeks, tr_start, tr_end, run_dir.name)
        tgt_df["anom_m"] = tgt_df["value_m"] - tgt_df["ref_m"]
        per_seed_stress = (
            tgt_df.groupby(["seed", "code_bss", "stress"], sort=True)["anom_m"]
            .mean()
            .rename("value_m")
            .reset_index()
        )
        ref_info = {
            "kind": "training_seasonal",
            "space": "output",
            "window": (str(tr_start.date()), str(tr_end.date())),
            "woy_rule": "ISO week, 53 merged into 52",
        }
    else:
        r_start, r_end = _parse_window(reference)
        ref_weeks = all_weeks[(all_weeks >= r_start) & (all_weeks <= r_end)]
        if len(ref_weeks) == 0:
            raise ValueError(
                f"{run_dir.name}: no run weeks fall in reference window {r_start.date()}..{r_end.date()}"
            )
        tgt_mean = (
            contrib[contrib["week"].isin(target_weeks)]
            .groupby(["seed", "code_bss", "stress"], sort=True)["value_m"]
            .mean()
            .rename("tgt_m")
        )
        ref_mean = (
            contrib[contrib["week"].isin(ref_weeks)]
            .groupby(["seed", "code_bss", "stress"], sort=True)["value_m"]
            .mean()
            .rename("ref_m")
        )
        joined = pd.concat([tgt_mean, ref_mean], axis=1)
        per_seed_stress = (joined["tgt_m"] - joined["ref_m"]).rename("value_m").reset_index()
        ref_info = {
            "kind": "window",
            "window": (str(r_start.date()), str(r_end.date())),
            "n_reference_weeks": int(len(ref_weeks)),
        }

    per_seed_stress["report_group"] = per_seed_stress["stress"].map(group_map["report_group"])
    per_seed_stress["driver_group"] = per_seed_stress["stress"].map(group_map["driver_group"])

    per_seed_report = (
        per_seed_stress.groupby(["seed", "code_bss", "report_group"], sort=True)["value_m"]
        .sum()
        .reset_index()
    )
    has_driver = per_seed_stress["driver_group"].astype(str).str.len() > 0
    per_seed_driver = (
        per_seed_stress[has_driver]
        .groupby(["seed", "code_bss", "driver_group"], sort=True)["value_m"]
        .sum()
        .reset_index()
    )
    per_seed_total = (
        per_seed_stress.groupby(["seed", "code_bss"], sort=True)["value_m"]
        .sum()
        .reset_index()
    )

    # Exact additivity checks per seed and well (float64 tolerance 1e-9 m).
    sum_stress = per_seed_stress.groupby(["seed", "code_bss"], sort=True)["value_m"].sum()
    sum_report = per_seed_report.groupby(["seed", "code_bss"], sort=True)["value_m"].sum()
    tot_series = per_seed_total.set_index(["seed", "code_bss"])["value_m"]
    assert np.allclose(sum_stress.to_numpy(), tot_series.to_numpy(), rtol=0.0, atol=SUM_TOL_M), (
        "Per-seed stress contributions do not sum to total within 1e-9 m"
    )
    assert np.allclose(sum_report.to_numpy(), tot_series.to_numpy(), rtol=0.0, atol=SUM_TOL_M), (
        "Per-seed report-group contributions do not sum to total within 1e-9 m"
    )
    no_driver = (
        per_seed_stress[~has_driver]
        .groupby(["seed", "code_bss"], sort=True)["value_m"]
        .sum()
        .reindex(tot_series.index, fill_value=0.0)
    )
    sum_driver = (
        per_seed_driver.groupby(["seed", "code_bss"], sort=True)["value_m"]
        .sum()
        .reindex(tot_series.index, fill_value=0.0)
    )
    assert np.allclose(
        (sum_driver + no_driver).to_numpy(), tot_series.to_numpy(), rtol=0.0, atol=SUM_TOL_M
    ), "Per-seed driver-group contributions (+ ungrouped residual) do not sum to total within 1e-9 m"

    by_stress = _summarise_across_seeds(per_seed_stress, ["code_bss", "stress"])
    by_stress["report_group"] = by_stress["stress"].map(group_map["report_group"])
    by_stress["driver_group"] = by_stress["stress"].map(group_map["driver_group"])
    by_stress = by_stress[
        ["code_bss", "stress", "report_group", "driver_group", "mean_m", "sd_m", "sign_agreement", "n_seeds"]
    ]
    by_report_group = _summarise_across_seeds(per_seed_report, ["code_bss", "report_group"])
    by_driver_group = (
        _summarise_across_seeds(per_seed_driver, ["code_bss", "driver_group"])
        if not per_seed_driver.empty
        else pd.DataFrame(columns=["code_bss", "driver_group", "mean_m", "sd_m", "sign_agreement", "n_seeds"])
    )
    total = _summarise_across_seeds(per_seed_total, ["code_bss"])

    flags = data_quality_flags(
        data.config,
        selected_wells,
        target_weeks,
        dataset=dataset,
        dataset_dir=dataset_dir,
        edges=edges,
    )
    return {
        "run": run_dir.name,
        "dataset": dataset,
        "target": (str(t_start.date()), str(t_end.date())),
        "n_target_weeks": int(len(target_weeks)),
        "reference": ref_info,
        "n_seeds": len(seeds),
        "seeds": seeds,
        "stresses": run_stresses,
        "by_stress": by_stress,
        "by_report_group": by_report_group,
        "by_driver_group": by_driver_group,
        "total": total,
        "per_seed": {
            "by_stress": per_seed_stress[["seed", "code_bss", "stress", "value_m"]],
            "by_report_group": per_seed_report,
            "by_driver_group": per_seed_driver,
            "total": per_seed_total,
        },
        "flags": flags,
        "metadata": run_metadata(data.config),
    }


def _fmt_cell(mean_m: float, sd_m: float, sign_agr: float) -> str:
    sd_str = f"{sd_m:.3f}" if np.isfinite(sd_m) else "nan"
    return f"{mean_m:+.3f} ± {sd_str} ({sign_agr:.2f})"


def format_report(result: dict) -> str:
    """Format a ``decompose()`` result as plain-text tables for the CLI."""
    meta = result["metadata"]
    ref = result["reference"]
    ref_space = f", {ref['space']} space" if "space" in ref else ""
    lines = [
        f"Run: {result['run']} (dataset={result['dataset']}, seeds={result['n_seeds']})",
        (
            f"Metadata: regime={meta['regime']}, mode={meta['mode']}, protocol={meta['protocol']}, "
            f"arm={meta['arm'] or 'panel'}, policy={meta['export_policy'] or 'none'}, "
            f"pumping_recon={meta['pumping_reconstruction']} ({meta['pumping_reconstruction_name']}), "
            f"signs={meta['signs']}, residual={meta['residual']}"
        ),
        (
            f"Target: {result['target'][0]} .. {result['target'][1]} "
            f"({result['n_target_weeks']} weeks) | "
            f"Reference: {ref['kind']} ({ref['window'][0]} .. {ref['window'][1]}{ref_space})"
        ),
        "",
        "Report-group contributions (m; mean ± sd (sign agreement)):",
    ]

    groups_df = load_groups()
    present_groups = set(result["by_report_group"]["report_group"].unique())
    ordered_groups = [
        g for g in dict.fromkeys(groups_df["report_group"]) if g in present_groups
    ] + sorted(present_groups - set(groups_df["report_group"]))

    rep = result["by_report_group"].set_index(["code_bss", "report_group"])
    tot = result["total"].set_index("code_bss")
    flags = result["flags"].set_index("code_bss")

    table_rows = []
    for code in result["flags"]["code_bss"]:
        row = {"code_bss": code, "core": bool(flags.loc[code, "core"])}
        for grp in ordered_groups:
            if (code, grp) in rep.index:
                r = rep.loc[(code, grp)]
                row[grp] = _fmt_cell(r["mean_m"], r["sd_m"], r["sign_agreement"])
            else:
                row[grp] = "-"
        t = tot.loc[code]
        row["total"] = _fmt_cell(t["mean_m"], t["sd_m"], t["sign_agreement"])
        table_rows.append(row)
    lines.append(pd.DataFrame(table_rows).to_string(index=False))

    if not result["by_driver_group"].empty:
        lines.append("")
        lines.append("Driver-group contributions (m; mean ± sd (sign agreement)):")
        drv = result["by_driver_group"].set_index(["code_bss", "driver_group"])
        drv_groups = sorted(result["by_driver_group"]["driver_group"].unique())
        drv_rows = []
        for code in result["flags"]["code_bss"]:
            row = {"code_bss": code}
            for dg in drv_groups:
                if (code, dg) in drv.index:
                    r = drv.loc[(code, dg)]
                    row[dg] = _fmt_cell(r["mean_m"], r["sd_m"], r["sign_agreement"])
                else:
                    row[dg] = "-"
            drv_rows.append(row)
        lines.append(pd.DataFrame(drv_rows).to_string(index=False))

    lines.append("")
    lines.append("Data-quality flags:")
    flag_view = result["flags"][
        [
            "code_bss",
            "core",
            "n_weeks",
            "share_observed",
            "share_strict",
            "share_placeholder",
            "share_pumping_imputed",
            "routed_pumping_m3",
        ]
    ].copy()
    for col in ("share_observed", "share_strict", "share_placeholder", "share_pumping_imputed"):
        flag_view[col] = flag_view[col].map(lambda x: f"{x:.3f}" if pd.notna(x) else "n/a")
    flag_view["routed_pumping_m3"] = flag_view["routed_pumping_m3"].map(lambda x: f"{x:,.0f}")
    lines.append(flag_view.to_string(index=False))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Exact per-stress and driver-group decomposition of a response-model run."
    )
    parser.add_argument("run", help="Run name under results/<dataset>/ or path to a run folder.")
    parser.add_argument(
        "--target",
        required=True,
        help="Inclusive target window 'YYYY-MM-DD:YYYY-MM-DD'.",
    )
    parser.add_argument(
        "--reference",
        default="average_forcing",
        help=(
            "Reference condition: 'average_forcing' (default, input space), "
            "'training_seasonal' (output-space sensitivity), or 'YYYY-MM-DD:YYYY-MM-DD'."
        ),
    )
    parser.add_argument(
        "--well",
        nargs="+",
        action="extend",
        default=None,
        help="One or more well codes (code_bss) to show.",
    )
    parser.add_argument(
        "--dataset",
        default=DATASET,
        help=f"Dataset version (default: {DATASET}).",
    )
    args = parser.parse_args(argv)
    result = decompose(
        args.run,
        target=args.target,
        reference=args.reference,
        wells=args.well,
        dataset=args.dataset,
    )
    print(format_report(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
