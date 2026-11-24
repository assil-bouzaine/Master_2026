"""Input-space intervention faithfulness tests for the hybrid response model (Phase 5).

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python -m src.explain.faithfulness \\
        resp_pooled_l001 --target 2024-06-01:2024-09-30 --well 10964X0119/NYLS-1 10906X0039/C2-1

Why this module exists (docs/analysis_plan.md §12; docs/notes/step15_explanations.md)
------------------------------------------------------------------------------------
T46 (``src/explain/contributions.py``) states driver contributions in **output space**: each
stress's saved contribution minus its own training-period seasonal mean. Faithfulness asks
whether a plausible intervention in **input space** gives the same answer: replace the inputs
of a driver group over the full kernel memory ``[target_start - kernel_weeks + 1, target_end]``
with their training-period seasonal level (never zeroed inputs), run the saved model forward,
and measure how much the mean simulated head over the target window moves.

For this linear, time-invariant response model:
- **Superposition** is exact up to float precision (``<= 1e-6 m``): the sum of single-group
  removal effects equals the effect of replacing all input groups with their reference at once.
- **Stated vs intervened** agree closely but not identically, because output-space averaging
  averages lagged inputs over shifted windows ``[train_start - j, train_end - j]`` (picking up
  pre-training years 2000-2004, pre-2000 padding, 53-week ISO years, and trends across
  2000-2019), whereas input-space intervention feeds the training seasonal mean at every lag.
- **Fidelity+ and Fidelity-** adapt Azzolin et al. (arXiv:2406.15156) to regression with
  plausible interventions:
  - ``fidelity+`` = ``|Delta head when the largest-|stated| group is removed|`` (necessity);
  - ``fidelity-`` = ``|total anomaly - anomaly with only that group kept|``
    = ``|Delta head when every other group is set to its reference|`` (sufficiency).

Sign conventions
----------------
- ``intervene(..., mode="remove" | "keep_only")`` returns the **counterfactual head shift**
  ``mean(h_intervened) - mean(h_orig)`` over the target window (metres): e.g., restoring dry
  rainfall back to its seasonal reference raises the simulated head (positive shift).
- In ``fidelity()``, the **intervention effect** attributed to a group is ``-Delta_remove``
  = ``mean(h_orig) - mean(h_removed)`` (metres), which shares the exact sign convention of T46's
  stated contribution (e.g., drought lowers the head -> negative stated and negative effect).
- The seasonal ``residual`` has no inputs and is never intervened on.
"""
from __future__ import annotations

import argparse
from collections.abc import Iterable
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd
import torch

from src.config import DATASET
from src.explain.contributions import (
    GROUPS_PATH,
    _filter_wells,
    _iso_week_of_year,
    _parse_window,
    _run_dir,
    decompose,
    load_groups,
    training_window,
)
from src.models import response as R

SUPERPOSITION_TOL_M = 1e-6
_CKPT_RE = re.compile(r"^seed_(\d+)\.pt$")


def _logical_stress(model_stress: str) -> str:
    """Map internal model stress slots (e.g. ``river_c`` under gate3) to saved stress names."""
    return "river" if model_stress == "river_c" else model_stress


def _padded_weeks(weeks: pd.DatetimeIndex, kernel_weeks: int) -> pd.DatetimeIndex:
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

    # Precompute index masks for each ISO week present in training.
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


def resolve_group_stresses(
    group: str | Iterable[str],
    net_names: Iterable[str],
    groups_df: pd.DataFrame | None = None,
) -> tuple[str, ...]:
    """Resolve one or more report groups, driver groups, or stress names to active model stresses.

    Refuses ``"residual"`` because the fixed seasonal residual has no inputs and is never
    intervened on. Under ``--signs gate3``, ``"river"`` resolves to both ``"river_c"`` and
    ``"river"`` when present in ``net_names``.
    """
    if groups_df is None:
        groups_df = load_groups()
    active = tuple(net_names)
    items = [group] if isinstance(group, str) else list(group)
    if not items:
        raise ValueError("group must not be empty")

    # Map logical stress name -> list of active model stress slots (e.g. "river" -> ["river_c", "river"]).
    logical_to_active: dict[str, list[str]] = {}
    for s in active:
        logical_to_active.setdefault(_logical_stress(s), []).append(s)

    by_report = groups_df.groupby("report_group")["stress"].apply(list).to_dict()
    by_driver = (
        groups_df[groups_df["driver_group"].astype(str).str.len() > 0]
        .groupby("driver_group")["stress"]
        .apply(list)
        .to_dict()
    )
    known_stresses = set(groups_df["stress"])

    chosen: list[str] = []
    for name in items:
        if name == "residual":
            raise ValueError("residual has no inputs and cannot be intervened on")
        if name in by_report:
            logical = [s for s in by_report[name] if s != "residual"]
        elif name in by_driver:
            logical = [s for s in by_driver[name] if s != "residual"]
        elif name in known_stresses or name in logical_to_active:
            logical = [name]
        elif name in active:
            chosen.append(name)
            continue
        else:
            raise ValueError(
                f"Unknown group or stress {name!r}; expected a report_group, driver_group, "
                f"or active stress ({list(active)})"
            )
        for ls in logical:
            chosen.extend(logical_to_active.get(ls, []))

    # Preserve net_names ordering and deduplicate.
    chosen_set = set(chosen)
    return tuple(s for s in active if s in chosen_set)


def active_report_groups(
    net_names: Iterable[str],
    groups_df: pd.DataFrame | None = None,
) -> list[str]:
    """Return the intervenable report groups active in ``net_names`` in ``explain_groups.csv`` order."""
    if groups_df is None:
        groups_df = load_groups()
    active_logical = {_logical_stress(s) for s in net_names}
    stress_to_rg = dict(zip(groups_df["stress"], groups_df["report_group"]))
    unknown = sorted(active_logical - set(stress_to_rg))
    if unknown:
        raise ValueError(f"Active model stresses absent from explain_groups.csv: {unknown}")
    present = {stress_to_rg[s] for s in active_logical if s != "residual"}
    return [rg for rg in dict.fromkeys(groups_df["report_group"]) if rg in present and rg != "residual"]


def _inputs_for_stresses(stresses: Iterable[str], recharge: str) -> tuple[str, ...]:
    """Return the unique input-dict keys feeding ``stresses`` using ``src.models.response.stress_inputs``."""
    cols: list[str] = []
    for s in stresses:
        for col in R.stress_inputs(s, recharge=recharge):
            if col not in cols:
                cols.append(col)
    return tuple(cols)


def intervene_model(
    net: R.ResponseModel,
    data: dict,
    stresses_to_replace: Iterable[str],
    target: str | tuple[str, str],
    *,
    X_ref: dict[str, np.ndarray] | None = None,
    train_window: tuple[str | pd.Timestamp, str | pd.Timestamp] | None = None,
    wells: Iterable[str] | None = None,
    base_mean: np.ndarray | None = None,
) -> pd.Series:
    """Replace the inputs of ``stresses_to_replace`` by ``X_ref`` over the full kernel memory
    ``[target_start - kernel_weeks + 1, target_end]`` and return the per-well shift in mean
    simulated head over ``target`` (``mean(h_intervened) - mean(h_orig)``, metres).
    """
    weeks = pd.DatetimeIndex(data["weeks"])
    t_start, t_end = _parse_window(target)
    t_idx = np.where((weeks >= t_start) & (weeks <= t_end))[0]
    if len(t_idx) == 0:
        raise ValueError(f"No model weeks fall in target window {t_start.date()}..{t_end.date()}")

    t0, t1 = int(t_idx[0]), int(t_idx[-1])
    K = int(net.K)
    mem_slice = slice(t0, t1 + K)

    X = data["X"]
    if X_ref is None:
        if train_window is None:
            raise ValueError("Provide either X_ref or train_window")
        X_ref = reference_inputs(X, weeks, K, train_window)

    replace_cols = _inputs_for_stresses(stresses_to_replace, recharge=net.recharge)
    X_mod = dict(X)
    for col in replace_cols:
        arr = X[col].copy()
        arr[:, mem_slice] = X_ref[col][:, mem_slice]
        X_mod[col] = arr

    net.eval()
    with torch.no_grad():
        if base_mean is None:
            h_orig = net({k: torch.from_numpy(v) for k, v in X.items()}).numpy().astype(np.float64)
            base_mean = h_orig[:, t_idx].mean(axis=1)
        h_mod = net({k: torch.from_numpy(v) for k, v in X_mod.items()}).numpy().astype(np.float64)
        mod_mean = h_mod[:, t_idx].mean(axis=1)

    delta = pd.Series(mod_mean - base_mean, index=pd.Index(data["codes"], name="code_bss"), name="delta_head_m")
    if wells is not None:
        selected = _filter_wells(data["codes"], wells)
        delta = delta.loc[selected]
    return delta


def intervene(
    run: str | Path,
    seed: int,
    group: str | Iterable[str],
    target: str | tuple[str, str],
    mode: str = "remove",
    *,
    dataset: str = DATASET,
    dataset_dir: str | Path | None = None,
    wells: Iterable[str] | None = None,
    prep: dict | None = None,
    net_data: tuple[R.ResponseModel, dict] | None = None,
    X_ref: dict[str, np.ndarray] | None = None,
    groups_path: str | Path = GROUPS_PATH,
    train_window: tuple[str, str] | None = None,
    base_mean: np.ndarray | None = None,
) -> pd.Series:
    """Intervene on a saved response-model start in input space and return the per-well change
    in mean simulated head over ``target`` (``mean(h_intervened) - mean(h_orig)``, metres).

    - ``mode="remove"``: replace the inputs of ``group``'s stresses with their training seasonal
      reference over ``[target_start - kernel_weeks + 1, target_end]``.
    - ``mode="keep_only"``: replace the inputs of every **other** stress with their training
      seasonal reference instead, keeping ``group``'s inputs untouched.
    - The fixed seasonal ``residual`` has no inputs and is never intervened on.
    """
    if mode not in ("remove", "keep_only"):
        raise ValueError(f"mode must be 'remove' or 'keep_only', got {mode!r}")

    run_dir = _run_dir(run, dataset=dataset)
    if net_data is None:
        net, data = R.replay(run_dir, seed, prep=prep)
    else:
        net, data = net_data

    groups_df = load_groups(groups_path)
    group_stresses = resolve_group_stresses(group, net.names, groups_df=groups_df)
    if mode == "remove":
        stresses_to_replace = group_stresses
    else:
        keep_set = set(group_stresses)
        stresses_to_replace = tuple(s for s in net.names if s not in keep_set)

    if X_ref is None:
        if train_window is not None:
            tr_win = _parse_window(train_window)
        else:
            cfg = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
            tr_win = training_window(cfg, dataset=dataset, dataset_dir=dataset_dir)
        X_ref = reference_inputs(data["X"], data["weeks"], net.K, tr_win)

    return intervene_model(
        net,
        data,
        stresses_to_replace,
        target,
        X_ref=X_ref,
        wells=wells,
        base_mean=base_mean,
    )


def _available_ckpt_seeds(run_dir: Path) -> list[int]:
    seeds = []
    for path in run_dir.iterdir():
        if path.is_file():
            m = _CKPT_RE.match(path.name)
            if m:
                seeds.append(int(m.group(1)))
    return sorted(seeds)


def fidelity(
    run: str | Path,
    target: str | tuple[str, str],
    wells: Iterable[str] | None = None,
    seeds: Iterable[int] | str | None = "all",
    *,
    dataset: str = DATASET,
    dataset_dir: str | Path | None = None,
    groups_path: str | Path = GROUPS_PATH,
    train_window: tuple[str, str] | None = None,
) -> dict:
    """Compare T46 stated contributions against input-space interventions and compute fidelity+/−.

    Returns a dict with:
    - ``by_report_group``: per ``(code_bss, report_group)`` table with ``stated_m``,
      ``intervened_m`` (``h_orig - h_removed``), ``diff_m`` (``intervened_m - stated_m``),
      ``abs_diff_m``, ``rel_to_total`` (``diff_m / |total_stated_m|``), ``abs_rel_to_total``,
      ``stated_sd_m``, ``intervened_sd_m``, ``n_seeds``;
    - ``by_well``: per-well ``top_group`` (largest ``|stated_m|`` among intervenable report
      groups), ``top_stated_m``, ``top_intervened_m``, ``total_stated_m``,
      ``total_intervened_m``, ``total_diff_m``, ``fidelity_plus_m``, ``fidelity_minus_m``,
      and ``superposition_max_err_m``;
    - ``superposition``: ``{"max_abs_err_m", "tol_m", "passed"}``;
    - ``per_seed``: per-seed intervention and superposition tables;
    - run metadata (``run``, ``dataset``, ``target``, ``n_target_weeks``, ``reference``,
      ``seeds``, ``n_seeds``, ``groups``, ``metadata``).
    """
    run_dir = _run_dir(run, dataset=dataset)
    cfg = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    ckpt_seeds = _available_ckpt_seeds(run_dir)
    if not ckpt_seeds:
        raise FileNotFoundError(f"No seed_<k>.pt checkpoints found in {run_dir}")

    decomp = decompose(
        run_dir,
        target=target,
        reference="training_seasonal",
        wells=wells,
        dataset=dataset,
        dataset_dir=dataset_dir,
        groups_path=groups_path,
        train_window=train_window,
    )
    contrib_seeds = decomp["seeds"]
    common_seeds = sorted(set(ckpt_seeds) & set(contrib_seeds))
    if seeds is None or seeds == "all":
        if set(ckpt_seeds) != set(contrib_seeds):
            raise ValueError(
                f"{run_dir.name}: checkpoint seeds {ckpt_seeds} != contrib seeds {contrib_seeds}"
            )
        selected_seeds = common_seeds
    else:
        selected_seeds = [int(s) for s in seeds]
        missing = sorted(set(selected_seeds) - set(common_seeds))
        if missing:
            raise ValueError(f"{run_dir.name}: requested seed(s) missing checkpoints/contribs: {missing}")

    # Filter T46 per-seed tables to selected_seeds so stated and intervened average over the same starts.
    ps_rg = decomp["per_seed"]["by_report_group"]
    ps_rg = ps_rg[ps_rg["seed"].isin(selected_seeds)].copy()
    ps_tot = decomp["per_seed"]["total"]
    ps_tot = ps_tot[ps_tot["seed"].isin(selected_seeds)].copy()

    # Build inputs and seasonal reference once for the run.
    prep = R.prepare(R.args_from_config(cfg), verbose=False)
    data = prep["data"]
    selected_wells = _filter_wells(data["codes"], wells)
    groups_df = load_groups(groups_path)
    tr_win = _parse_window(train_window) if train_window is not None else training_window(
        cfg, dataset=dataset, dataset_dir=dataset_dir
    )
    X_ref = reference_inputs(data["X"], data["weeks"], prep["model_kwargs"]["kernel_weeks"], tr_win)

    weeks = pd.DatetimeIndex(data["weeks"])
    t_start, t_end = _parse_window(target)
    t_idx = np.where((weeks >= t_start) & (weeks <= t_end))[0]
    X_orig_t = {k: torch.from_numpy(v) for k, v in data["X"].items()}

    # Intervenable report groups in explain_groups.csv order (never includes residual).
    interv_groups = active_report_groups(prep["names"], groups_df=groups_df)
    all_report_groups = list(interv_groups)
    if "residual" in set(ps_rg["report_group"]):
        all_report_groups.append("residual")

    # Compute per-seed stated summaries first to identify each well's top report group.
    stated_stats = (
        ps_rg.groupby(["code_bss", "report_group"], sort=True)["value_m"]
        .agg(
            stated_m="mean",
            stated_sd_m=lambda s: float(np.std(s.to_numpy(dtype=np.float64), ddof=1)) if len(s) > 1 else float("nan"),
        )
        .reset_index()
    )
    tot_stated = (
        ps_tot.groupby("code_bss", sort=True)["value_m"]
        .mean()
        .reindex(selected_wells)
    )

    stated_interv = stated_stats[stated_stats["report_group"].isin(interv_groups)].copy()
    top_group_of: dict[str, str] = {}
    for code in selected_wells:
        sub = stated_interv[stated_interv["code_bss"] == code]
        idx_top = sub["stated_m"].abs().idxmax()
        top_group_of[code] = str(sub.loc[idx_top, "report_group"])

    per_seed_rows: list[dict] = []
    sup_rows: list[dict] = []
    keep_only_by_seed: dict[int, dict[str, pd.Series]] = {}

    for seed in selected_seeds:
        net, _ = R.replay(run_dir, seed, prep=prep)
        with torch.no_grad():
            h_orig = net(X_orig_t).numpy().astype(np.float64)
        base_mean = h_orig[:, t_idx].mean(axis=1)

        rem_deltas: dict[str, pd.Series] = {}
        keep_deltas: dict[str, pd.Series] = {}
        for rg in interv_groups:
            d_rem = intervene(
                run_dir,
                seed,
                rg,
                target,
                mode="remove",
                dataset=dataset,
                wells=selected_wells,
                net_data=(net, data),
                X_ref=X_ref,
                groups_path=groups_path,
                base_mean=base_mean,
            )
            rem_deltas[rg] = d_rem
            for code in selected_wells:
                per_seed_rows.append(
                    {
                        "seed": seed,
                        "code_bss": code,
                        "report_group": rg,
                        "delta_remove_m": float(d_rem.loc[code]),
                        "intervened_m": float(-d_rem.loc[code]),
                    }
                )

        # Keep-only is needed for each well's top group (avoid redundant calls if wells share top group).
        needed_top_groups = sorted(set(top_group_of.values()))
        for rg in needed_top_groups:
            keep_deltas[rg] = intervene(
                run_dir,
                seed,
                rg,
                target,
                mode="keep_only",
                dataset=dataset,
                wells=selected_wells,
                net_data=(net, data),
                X_ref=X_ref,
                groups_path=groups_path,
                base_mean=base_mean,
            )
        keep_only_by_seed[seed] = keep_deltas

        # Superposition: sum of single-group removal shifts vs removing all groups at once.
        d_all = intervene(
            run_dir,
            seed,
            interv_groups,
            target,
            mode="remove",
            dataset=dataset,
            wells=selected_wells,
            net_data=(net, data),
            X_ref=X_ref,
            groups_path=groups_path,
            base_mean=base_mean,
        )
        d_sum = sum(rem_deltas.values())
        for code in selected_wells:
            s_val = float(d_sum.loc[code])
            a_val = float(d_all.loc[code])
            sup_rows.append(
                {
                    "seed": seed,
                    "code_bss": code,
                    "sum_remove_m": s_val,
                    "all_remove_m": a_val,
                    "total_intervened_m": -a_val,
                    "abs_err_m": abs(s_val - a_val),
                }
            )

    ps_interv = pd.DataFrame(per_seed_rows)
    ps_sup = pd.DataFrame(sup_rows)

    interv_stats = (
        ps_interv.groupby(["code_bss", "report_group"], sort=True)["intervened_m"]
        .agg(
            intervened_m="mean",
            intervened_sd_m=lambda s: float(np.std(s.to_numpy(dtype=np.float64), ddof=1)) if len(s) > 1 else float("nan"),
        )
        .reset_index()
    )

    by_rg = stated_stats.merge(interv_stats, on=["code_bss", "report_group"], how="left")
    by_rg["diff_m"] = by_rg["intervened_m"] - by_rg["stated_m"]
    by_rg["abs_diff_m"] = by_rg["diff_m"].abs()
    tot_abs = by_rg["code_bss"].map(tot_stated.abs())
    by_rg["rel_to_total"] = np.where(tot_abs > 0.0, by_rg["diff_m"] / tot_abs, np.nan)
    by_rg["abs_rel_to_total"] = by_rg["rel_to_total"].abs()
    by_rg["n_seeds"] = len(selected_seeds)

    # Order cleanly by well and explain_groups.csv order.
    rg_order = {rg: i for i, rg in enumerate(all_report_groups)}
    by_rg["_rg_ord"] = by_rg["report_group"].map(lambda g: rg_order.get(g, 999))
    by_rg = (
        by_rg.sort_values(["code_bss", "_rg_ord"], kind="mergesort")
        .drop(columns="_rg_ord")
        .reset_index(drop=True)[
            [
                "code_bss",
                "report_group",
                "stated_m",
                "intervened_m",
                "diff_m",
                "abs_diff_m",
                "rel_to_total",
                "abs_rel_to_total",
                "stated_sd_m",
                "intervened_sd_m",
                "n_seeds",
            ]
        ]
    )

    # Per-well fidelity+ and fidelity- (Azzolin et al., arXiv:2406.15156, adapted to regression).
    by_rg_idx = by_rg.set_index(["code_bss", "report_group"])
    tot_interv_mean = ps_sup.groupby("code_bss")["total_intervened_m"].mean()
    sup_max_by_well = ps_sup.groupby("code_bss")["abs_err_m"].max()

    well_rows: list[dict] = []
    for code in selected_wells:
        tg = top_group_of[code]
        top_row = by_rg_idx.loc[(code, tg)]
        # Ensemble head shift when top_group is removed (fidelity+) or kept alone (fidelity-).
        rem_vals = ps_interv[(ps_interv["code_bss"] == code) & (ps_interv["report_group"] == tg)][
            "delta_remove_m"
        ].to_numpy(dtype=np.float64)
        keep_vals = np.array(
            [float(keep_only_by_seed[s][tg].loc[code]) for s in selected_seeds], dtype=np.float64
        )
        fid_plus = float(abs(rem_vals.mean()))
        fid_minus = float(abs(keep_vals.mean()))
        ts = float(tot_stated.loc[code])
        ti = float(tot_interv_mean.loc[code])
        well_rows.append(
            {
                "code_bss": code,
                "top_group": tg,
                "top_stated_m": float(top_row["stated_m"]),
                "top_intervened_m": float(top_row["intervened_m"]),
                "total_stated_m": ts,
                "total_intervened_m": ti,
                "total_diff_m": ti - ts,
                "fidelity_plus_m": fid_plus,
                "fidelity_minus_m": fid_minus,
                "superposition_max_err_m": float(sup_max_by_well.loc[code]),
                "n_seeds": len(selected_seeds),
            }
        )
    by_well = pd.DataFrame(well_rows)
    max_sup_err = float(ps_sup["abs_err_m"].max()) if not ps_sup.empty else 0.0

    return {
        "run": run_dir.name,
        "dataset": dataset,
        "target": decomp["target"],
        "n_target_weeks": decomp["n_target_weeks"],
        "reference": decomp["reference"],
        "seeds": selected_seeds,
        "n_seeds": len(selected_seeds),
        "groups": all_report_groups,
        "intervenable_groups": interv_groups,
        "by_report_group": by_rg,
        "by_well": by_well,
        "superposition": {
            "max_abs_err_m": max_sup_err,
            "tol_m": SUPERPOSITION_TOL_M,
            "passed": max_sup_err <= SUPERPOSITION_TOL_M,
        },
        "per_seed": {
            "by_report_group": ps_interv,
            "superposition": ps_sup,
        },
        "metadata": decomp["metadata"],
    }


def format_report(result: dict) -> str:
    """Format a ``fidelity()`` result as plain-text tables for the CLI."""
    ref = result["reference"]
    sup = result["superposition"]
    lines = [
        f"Run: {result['run']} (dataset={result['dataset']}, seeds={result['n_seeds']})",
        (
            f"Target: {result['target'][0]} .. {result['target'][1]} "
            f"({result['n_target_weeks']} weeks) | "
            f"Reference: {ref['kind']} ({ref['window'][0]} .. {ref['window'][1]})"
        ),
        (
            f"Superposition check: max |sum(single) - all| = {sup['max_abs_err_m']:.2e} m "
            f"(tol {sup['tol_m']:.1e} m -> {'PASS' if sup['passed'] else 'FAIL'})"
        ),
        "",
        "Stated (output space, T46) vs Intervened (input space) by report group (metres):",
    ]
    rg_view = result["by_report_group"][
        ["code_bss", "report_group", "stated_m", "intervened_m", "diff_m", "rel_to_total"]
    ].copy()
    for col in ("stated_m", "intervened_m", "diff_m"):
        rg_view[col] = rg_view[col].map(lambda x: f"{x:+.4f}" if pd.notna(x) else "n/a")
    rg_view["rel_to_total"] = rg_view["rel_to_total"].map(
        lambda x: f"{100.0 * x:+.1f}%" if pd.notna(x) else "n/a"
    )
    lines.append(rg_view.to_string(index=False))

    lines.append("")
    lines.append("Per-well fidelity summary (metres; Azzolin et al., arXiv:2406.15156):")
    w_view = result["by_well"][
        [
            "code_bss",
            "top_group",
            "total_stated_m",
            "total_intervened_m",
            "total_diff_m",
            "fidelity_plus_m",
            "fidelity_minus_m",
            "superposition_max_err_m",
        ]
    ].copy()
    for col in ("total_stated_m", "total_intervened_m", "total_diff_m"):
        w_view[col] = w_view[col].map(lambda x: f"{x:+.4f}")
    for col in ("fidelity_plus_m", "fidelity_minus_m"):
        w_view[col] = w_view[col].map(lambda x: f"{x:.4f}")
    w_view["superposition_max_err_m"] = w_view["superposition_max_err_m"].map(lambda x: f"{x:.2e}")
    lines.append(w_view.to_string(index=False))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Input-space intervention faithfulness checks for a saved response-model run."
    )
    parser.add_argument("run", help="Run name under results/<dataset>/ or path to a run folder.")
    parser.add_argument(
        "--target",
        required=True,
        help="Inclusive target window 'YYYY-MM-DD:YYYY-MM-DD'.",
    )
    parser.add_argument(
        "--well",
        nargs="+",
        action="extend",
        default=None,
        help="One or more well codes (code_bss) to evaluate.",
    )
    parser.add_argument(
        "--seeds",
        type=int,
        nargs="+",
        default=None,
        help="Optional subset of seed indices (default: all seeds in the run).",
    )
    parser.add_argument(
        "--dataset",
        default=DATASET,
        help=f"Dataset version (default: {DATASET}).",
    )
    args = parser.parse_args(argv)
    result = fidelity(
        args.run,
        target=args.target,
        wells=args.well,
        seeds="all" if args.seeds is None else args.seeds,
        dataset=args.dataset,
    )
    print(format_report(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
