"""Draw the frozen Phase 4 contrasts (analysis plan §6, §10 and §14 item 18).

    PFE_DATASET=v4 python -m src.analysis.phase4_figures [--recompute]

Cache arms_report.compute once: its bootstrap results are expensive and must
not be estimated again by the plotting code. JSON keeps the nested control
draws, same-arm unions and soft-penalty selection together without flattening
them. Per-well drought scores use the same saved-start reader as arms_report.
"""
import argparse
import json
from pathlib import Path
import time

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.ticker import MaxNLocator
import numpy as np
import pandas as pd

from src.analysis import arms_report as arms, ladder_report as ladder
from src.analysis.baseline_report import GRID, GROUPS, INK, INK2, SERIES, SURF
from src.config import DATASET, FIGURES

CACHE = arms.RESULTS / "arms_report_rows.json"
DPI = 150
SIZES = {"contrasts": (7, 9), "controls": (7, 4.8), "wells_dc": (7, 6.5)}
CAPTIONS = {
    "contrasts": "Drought contrasts: dots are median log RMSE ratios, lines are 95% cluster-bootstrap "
                 "intervals, and shading is the union of same-arm bands. Dashed lines mark ±0.05; "
                 "bold labels mark R1, reconstruction 1. RQ2 is declared only in R1 and R2.",
    "controls": "Graph controls in R1 and R2, reconstruction 1: small dots show each graph draw's "
                "median drought log RMSE ratio and lines show the draw range (not a confidence "
                "interval). Counts show scored / declared draws; dashed lines mark ±0.05.",
    "wells_dc": "Core-well drought RMSE of D against C in R1, reconstruction 1, in metres on log "
                "axes. Colours show aquifer groups; the diagonal marks equal error. Short codes "
                "label wells with |log(RMSE D / RMSE C)| > 0.3.",
}
EFFECT_LABEL = "Median drought log(RMSE a / RMSE b)\n← a better | b better →"
WELL_COLUMNS = ["code_bss", "C", "D", "group", "short_code", "log_ratio"]


def _json_value(value):
    """Keep nested rows as ordinary JSON, including unavailable numeric values."""
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def load_rows(config, runs, cache=CACHE, recompute=False):
    """Read the cached report, or compute once and save before drawing anything."""
    cache = Path(cache)
    if cache.is_file() and not recompute:
        saved = json.loads(cache.read_text(encoding="utf-8"))
        if saved["schema"] != 1 or saved["config"] != config:
            raise ValueError(f"{cache}: configuration changed; use --recompute")
        print(f"Read cached rows: {cache}", flush=True)
        return saved["report"]
    print("Computing Phase 4 rows once; the bootstrap may take 25–40 minutes.", flush=True)
    started = time.perf_counter()
    report = arms.compute(config, runs)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(_json_value({"schema": 1, "config": config, "report": report}),
                                indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Cached rows: {cache} ({time.perf_counter() - started:.1f}s)", flush=True)
    return report


def _available(row):
    reason = row.get("pending")
    if not reason and (row.get(arms.EFFECT) is None or row.get("interval") is None):
        reason = "missing runs or scores"
    if not reason and not np.isfinite(np.asarray([row[arms.EFFECT], *row["interval"]], dtype=float)).all():
        reason = "non-finite effect or interval"
    if reason:
        print(f"Skipping pending row: {row['name']} / {arms.REGIME_NAMES[row['regime']]} / "
              f"reconstruction {row['reconstruction']}: {reason}")
        return False
    return True


def contrast_table(rows):
    """Copy plotted values directly from compute's family rows, without rounding."""
    plotted = []
    for row in rows:
        if row["family"] in ("RQ1", "RQ2") and _available(row):
            plotted.append(row | {"confirmatory": row["regime"] == "" and row["reconstruction"] == 1})
    return pd.DataFrame(plotted)


def well_table(report, runs):
    """Read paired core RMSE from the declared D/C runs and their ten-start means."""
    row = next((r for r in report["families"] if r["family"] == "RQ1" and r["name"] == "D vs C"
                and r["regime"] == "" and r["reconstruction"] == 1), None)
    if row is None or not _available(row):
        print("Skipping pending per-well D vs C: no complete R1, reconstruction 1 contrast")
        return pd.DataFrame(columns=WELL_COLUMNS)
    md, mc = (runs.metrics(row[arm], "") for arm in ("a", "b"))
    if md is None or mc is None:
        print("Skipping pending per-well D vs C: missing saved runs")
        return pd.DataFrame(columns=WELL_COLUMNS)
    table = pd.concat([ladder.per_well(mc, "test_drought", "RMSE").rename("C"),
                       ladder.per_well(md, "test_drought", "RMSE").rename("D")], axis=1)
    valid = np.isfinite(table[["C", "D"]]).all(axis=1) & table[["C", "D"]].gt(0).all(axis=1)
    if not valid.all():
        print(f"Skipping {int((~valid).sum())} wells with missing or non-positive paired RMSE")
    table = table.loc[valid].join(runs.wells.set_index("code_bss")[["group"]]).reset_index()
    table["short_code"] = table["code_bss"].str.split("/").str[-1]
    table["log_ratio"] = np.log(table["D"] / table["C"])
    return table[WELL_COLUMNS]


def _style(ax):
    ax.set_facecolor(SURF)
    ax.tick_params(labelsize=9, colors=INK2)
    ax.grid(axis="x", color=GRID, linewidth=0.5)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(axis="y", length=0)
    ax.set_axisbelow(True)


def _reference_lines(ax, smallest_effect):
    ax.xaxis.set_major_locator(MaxNLocator(nbins=5))
    ax.axvline(0, color=INK2, linewidth=0.8)
    for value in (-smallest_effect, smallest_effect):
        ax.axvline(value, color=INK2, linewidth=0.8, linestyle="--")
    ax.set_xlabel(EFFECT_LABEL, fontsize=9, color=INK2)


def _save(fig, output):
    # Fixed canvas dimensions keep the page size reproducible; do not crop to text.
    fig.savefig(output, dpi=DPI, facecolor=SURF)
    plt.close(fig)
    return output


def plot_contrasts(table, output, smallest_effect=0.05):
    fig, ax = plt.subplots(figsize=SIZES["contrasts"], facecolor=SURF)
    fig.subplots_adjust(left=0.31, right=0.76, bottom=0.09, top=0.98)
    _style(ax)
    _reference_lines(ax, smallest_effect)
    ticks, labels, bold = [], [], []
    y = 0
    for family, color in zip(("RQ1", "RQ2"), SERIES):
        rows = table.loc[table["family"].eq(family)] if len(table) else table
        if rows.empty:
            continue
        ax.text(-0.65, y, family, transform=ax.get_yaxis_transform(), fontsize=10,
                weight="bold", color=INK, va="center")
        y += 1.1
        for _, row in rows.iterrows():
            for lo, hi in row["union"] or ():
                ax.add_patch(Rectangle((lo, y - 0.36), hi - lo, 0.72, facecolor=GRID, zorder=1))
            ax.plot(row["interval"], [y, y], color=color, linewidth=1.3, zorder=2)
            ax.scatter(row[arms.EFFECT], y, color=color, s=17, zorder=3)
            classification = row["classification"]
            if classification in (arms.DETECTED, arms.SMALL):
                classification = "detected" if classification == arms.DETECTED else "detected (<0.05)"
            ax.text(1.025, y, classification, transform=ax.get_yaxis_transform(),
                    fontsize=9, color=INK2, va="center")
            ticks.append(y)
            labels.append(f"{row['name']} · {arms.REGIME_NAMES[row['regime']]} · {row['reconstruction']}")
            bold.append(row["confirmatory"])
            y += 1
        y += 0.5
    ax.set_yticks(ticks, labels, fontsize=9)
    for label, confirmatory in zip(ax.get_yticklabels(), bold):
        label.set_fontweight("bold" if confirmatory else "normal")
    ax.set_ylim(max(y - 0.4, 1), -0.6)
    ax.margins(x=0.06)
    if not ticks:
        ax.text(0.5, 0.5, "No complete contrasts", transform=ax.transAxes, ha="center", fontsize=10)
    return _save(fig, output)


def plot_controls(groups, output, smallest_effect=0.05):
    fig, ax = plt.subplots(figsize=SIZES["controls"], facecolor=SURF)
    fig.subplots_adjust(left=0.32, right=0.95, bottom=0.19, top=0.97)
    _style(ax)
    _reference_lines(ax, smallest_effect)
    ticks, labels = [], []
    for group in groups:
        if group["name"] not in ("D vs E_degree", "D vs E_distance", "D vs F_random", "D vs F_complete"):
            continue
        if group["regime"] not in ("", "_lwo") or group["reconstruction"] != 1:
            continue
        rows = [row for row in group["rows"] if _available(row)]
        if len(rows) != group["expected"]:
            print(f"Pending control draws: {group['name']} / {arms.REGIME_NAMES[group['regime']]}: "
                  f"{len(rows)} / {group['expected']} scored")
        if not rows:
            continue
        y = len(ticks)
        color = SERIES[0 if group["regime"] == "" else 1]
        if len(rows) == len(group["rows"]):
            ax.plot(group["range"], [y, y], color=color, linewidth=1.5, zorder=2)
        ax.scatter([r[arms.EFFECT] for r in rows], np.full(len(rows), y), s=23, color=color, zorder=3)
        ticks.append(y)
        labels.append(f"{group['name']} · {arms.REGIME_NAMES[group['regime']]} ({len(rows)}/{group['expected']})")
    ax.set_yticks(ticks, labels, fontsize=9)
    ax.set_ylim(max(len(ticks) - 0.4, 1), -0.6)
    ax.margins(x=0.08)
    if not ticks:
        ax.text(0.5, 0.5, "No complete controls", transform=ax.transAxes, ha="center", fontsize=10)
    return _save(fig, output)


def plot_wells(table, output):
    fig, ax = plt.subplots(figsize=SIZES["wells_dc"], facecolor=SURF)
    fig.subplots_adjust(left=0.13, right=0.97, bottom=0.19, top=0.97)
    _style(ax)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.tick_params(which="both", labelsize=9)
    for group, color in zip(GROUPS, SERIES):
        rows = table.loc[table["group"].fillna("other").eq(group)]
        if len(rows):
            ax.scatter(rows["C"], rows["D"], s=38, color=color, label=group, zorder=3)
    if len(table):
        lo, hi = table[["C", "D"]].to_numpy().min() / 1.25, table[["C", "D"]].to_numpy().max() * 1.25
        ax.plot([lo, hi], [lo, hi], color=INK2, linewidth=1)
        ax.set_xlim(lo, hi)
        ax.set_ylim(lo, hi)
        for _, row in table.loc[table["log_ratio"].abs().gt(0.3)].iterrows():
            ax.annotate(row["short_code"], (row["C"], row["D"]), xytext=(4, 5),
                        textcoords="offset points", fontsize=9, color=INK)
        handles, labels = ax.get_legend_handles_labels()
        fig.legend(handles, labels, loc="lower center", ncol=3, fontsize=9, frameon=False)
    else:
        ax.text(0.5, 0.5, "No paired core-well scores", transform=ax.transAxes, ha="center", fontsize=10)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("C drought RMSE (m; log scale)", fontsize=10, color=INK2)
    ax.set_ylabel("D drought RMSE (m; log scale)", fontsize=10, color=INK2)
    return _save(fig, output)


def render_figures(report, wells, output_dir=FIGURES, smallest_effect=0.05):
    """Render supplied results, so fixture tests never read or bootstrap real runs."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {name: output_dir / f"phase4_{name}_v4.png" for name in SIZES}
    with plt.rc_context({"font.size": 9, "text.color": INK, "axes.labelcolor": INK2}):
        plot_contrasts(contrast_table(report["families"]), paths["contrasts"], smallest_effect)
        plot_controls(report["controls"], paths["controls"], smallest_effect)
        plot_wells(wells, paths["wells_dc"])
    return paths


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--recompute", action="store_true", help="replace the cached bootstrap rows")
    args = parser.parse_args(argv)
    if DATASET != "v4":
        parser.error("these frozen figures require PFE_DATASET=v4")
    started = time.perf_counter()
    config = json.loads(arms.CONFIG.read_text(encoding="utf-8"))
    runs = arms.SavedRuns()
    report = load_rows(config, runs, recompute=args.recompute)
    paths = render_figures(report, well_table(report, runs), smallest_effect=config["smallest_effect"])
    for name, path in paths.items():
        print(f"-> {path}\nCaption: {CAPTIONS[name]}")
    print(f"Total runtime: {time.perf_counter() - started:.1f}s", flush=True)


if __name__ == "__main__":
    main()
