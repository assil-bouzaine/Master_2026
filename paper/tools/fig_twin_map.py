"""Draw the semi-synthetic twin's knowledge-value map for paper section 6.1.

Read the saved base grid and compare the graph and the oracle with the distance
arm, as in analysis plan section 14, item 19. The third column shows how often
the graph recovered pumping better than the distance arm in the same world.

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python paper/tools/fig_twin_map.py [--out DIR]
"""
import argparse
from pathlib import Path
import sys

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
from matplotlib.patches import Rectangle
from matplotlib.ticker import FormatStrFormatter, PercentFormatter

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.analysis.twin_report import PAYS, PLANNED_WORLDS, PROTOCOLS, load
from src.config import ROOT

OUT = ROOT / "paper" / "figures"
EPS = (0, 0.1, 0.25, 0.5)
U = (0, 0.3, 0.6)
SHAPE = (len(EPS), len(U))
ROW_LABELS = ("Early stopping", "Converged pooling")
D_OVER_C = "log_rmse_D_over_C"
T_OVER_C = "log_rmse_T_over_C"
PUMP_D, PUMP_C = "recovery_pumping_D", "recovery_pumping_C"
INK = "#263444"


def summarize_worlds(worlds):
    """Make one grid per statistic, in the same dial order as the axes."""
    dials = ["dial_eps", "dial_u"]
    grid = pd.MultiIndex.from_product((EPS, U), names=dials)
    results, pays_cells = {}, {}
    for setting in PROTOCOLS:
        rows = worlds.loc[worlds["setting"].eq(setting)]
        by_cell = rows.groupby(dials)
        counts = by_cell["world"].agg(["size", "nunique"])
        if set(counts.index) != set(grid) or not counts.eq(PLANNED_WORLDS).all().all():
            raise ValueError(f"{setting} must have {PLANNED_WORLDS} different worlds in each grid cell")
        if not np.isfinite(rows[[D_OVER_C, T_OVER_C, PUMP_D, PUMP_C]].to_numpy(dtype=float)).all():
            raise ValueError(f"{setting} has missing or non-finite scores")

        medians = by_cell[[D_OVER_C, T_OVER_C]].median().reindex(grid)
        upper_d = by_cell[D_OVER_C].quantile(0.975).reindex(grid)
        pays = medians[D_OVER_C].le(PAYS) & upper_d.lt(0)
        wins = rows[PUMP_D].lt(rows[PUMP_C]).groupby([rows[dial] for dial in dials]).mean()
        results[setting] = {
            D_OVER_C: medians[D_OVER_C].to_numpy().reshape(SHAPE),
            T_OVER_C: medians[T_OVER_C].to_numpy().reshape(SHAPE),
            "pumping_recovery_share": wins.reindex(grid).to_numpy().reshape(SHAPE),
            "pays_count": int(pays.sum()),
        }
        pays_cells[setting] = pays.to_numpy().reshape(SHAPE)
    return results, pays_cells


def draw_panel(ax, matrix, cmap, norm, fmt, show_y, pays=None):
    mesh = ax.pcolormesh(matrix, cmap=cmap, norm=norm, edgecolors="white", linewidth=0.65)
    for (row, col), value in np.ndenumerate(matrix):
        color = cmap(norm(value))
        luminance = np.dot(color[:3], (0.299, 0.587, 0.114))
        ax.text(col + 0.5, row + 0.5, format(value, fmt).replace("-", "−"),
                ha="center", va="center", color="white" if luminance < 0.5 else INK, fontsize=7.8)
    if pays is not None:
        for row, col in np.argwhere(pays):
            ax.add_patch(Rectangle((col + 0.035, row + 0.035), 0.93, 0.93, linewidth=1.65,
                                   edgecolor=INK, facecolor="none"))
    ax.set(ylim=(len(EPS), 0), xlim=(0, len(U)))
    ax.set_xticks(np.arange(len(U)) + 0.5, [f"{u:g}" for u in U])
    ax.set_yticks(np.arange(len(EPS)) + 0.5, [f"{e:g}" for e in EPS])
    ax.tick_params(length=0, pad=2.5, labelsize=7.5, labelcolor=INK, labelleft=show_y)
    for spine in ax.spines.values():
        spine.set_visible(False)
    return mesh


def draw_scale(fig, mesh, left, right, ticks, tick_format, label):
    cax = fig.add_axes([left, 0.085, right - left, 0.024])
    scale = fig.colorbar(mesh, cax=cax, orientation="horizontal", ticks=ticks, format=tick_format)
    # Matplotlib rasterizes long colour bars by default, even in a PDF.
    scale.solids.set_rasterized(False)
    scale.outline.set_visible(False)
    scale.ax.tick_params(length=2, width=0.5, labelsize=7, colors=INK, pad=2)
    scale.set_label(label, fontsize=7.4, color=INK, labelpad=2)


def draw_twin_map(out=OUT):
    """Write the PDF and 200 dpi PNG. Return the three grids and pays count per protocol."""
    results, pays_cells = summarize_worlds(load(["twin_map"]))
    limit = max(np.abs(result[key]).max() for result in results.values() for key in (D_OVER_C, T_OVER_C))
    diverging, sequential = matplotlib.colormaps["PuOr"], matplotlib.colormaps["cividis"]
    accuracy_norm, share_norm = Normalize(-limit, limit), Normalize(0, 1)

    fig, axes = plt.subplots(2, 3, figsize=(190 / 25.4, 116 / 25.4), facecolor="white")
    fig.subplots_adjust(left=0.145, right=0.97, bottom=0.226, top=0.924, hspace=0.30, wspace=0.16)
    heads = ("Accuracy of the graph (D / C)", "The oracle's ceiling (T / C)", "Right reasons")
    for ax, title in zip(axes[0], heads):
        ax.set_title(title, color=INK, fontsize=8, fontweight="bold", pad=6)
    for name, setting, row in zip(ROW_LABELS, PROTOCOLS, axes):
        result = results[setting]
        d_panel = draw_panel(row[0], result[D_OVER_C], diverging, accuracy_norm,
                             ".3f", show_y=True, pays=pays_cells[setting])
        draw_panel(row[1], result[T_OVER_C], diverging, accuracy_norm, ".3f", show_y=False)
        recovery_panel = draw_panel(row[2], result["pumping_recovery_share"], sequential, share_norm,
                                    ".0%", show_y=False)
        position = row[0].get_position()
        fig.text(0.084, (position.y0 + position.y1) / 2, name, rotation=90,
                 ha="center", va="center", color=INK, fontsize=8, fontweight="bold")
    fig.text(0.026, 0.575, "ε, share of the graph's pumping links that are false",
             rotation=90, ha="center", va="center", color=INK, fontsize=8)
    fig.text(0.564, 0.154, "u, share of the true pumping the graph misses",
             ha="center", va="center", color=INK, fontsize=8)
    left, middle, right = [ax.get_position() for ax in axes[-1]]
    draw_scale(fig, d_panel, left.x0, middle.x1, np.linspace(-limit, limit, 5),
               FormatStrFormatter("%.3f"), "Median log RMSE ratio")
    draw_scale(fig, recovery_panel, right.x0, right.x1, np.linspace(0, 1, 5),
               PercentFormatter(1, decimals=0), "Worlds with lower pumping error for D")

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    with matplotlib.rc_context({"pdf.fonttype": 42}):
        fig.savefig(out / "twin_map.pdf", metadata={"Title": "The twin's knowledge-value map", "CreationDate": None})
        fig.savefig(out / "twin_map.png", dpi=200)
    plt.close(fig)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT, help="directory for the PDF and PNG")
    args = parser.parse_args()
    for setting, result in draw_twin_map(args.out).items():
        print(f"{setting}: {result['pays_count']} of {len(EPS) * len(U)} cells pay")


if __name__ == "__main__":
    main()
