"""Draw the observed groundwater index and evaluation periods for paper section 2.3.

Use the monthly SGI stored with the weekly heads and the core wells in dataset v4.
Find the drought trough and recovery boundary from the observations, as specified
in analysis plan section 2, and check the boundary against the configured split.

    PYTHONIOENCODING=utf-8 PFE_DATASET=v4 .venv/bin/python paper/tools/fig_periods.py [--out DIR]
"""
import argparse
import json
from pathlib import Path
import sys

import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.patheffects as effects
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.config import PROCESSED, ROOT, TEST_PERIODS

DATA = PROCESSED / "dataset_v4"
OUT = ROOT / "paper" / "figures"
THRESHOLD = -0.5
RECOVERY_MONTHS = 3
INK = "#253344"
MEDIAN_COLOR = "#21466b"
BAND_COLOR = "#87a8c7"
GROUP_STYLES = {
    "Pliocene multilayer": ("#ba4d0c", "-"),
    "Corbières karst": ("#0072b2", "--"),
    "recent alluvium": ("#008158", "-."),
}


def monthly_core_sgi(heads, core_wells, start):
    """Check repeated weekly values and return a month-by-core-well table."""
    by_month = heads.assign(month=heads["week"].dt.to_period("M")).groupby(["month", "code_bss"])["sgi"]
    inconsistent = by_month.nunique(dropna=False).gt(1)
    if inconsistent.any():
        month, code = inconsistent.index[inconsistent][0]
        raise ValueError(f"Weekly SGI values disagree in {month} for {code}")
    months = pd.period_range(start, heads["week"].max(), freq="M", name="month")
    return by_month.first().unstack("code_bss").reindex(index=months, columns=core_wells.index)


def observed_recovery(median, test_days):
    """Find the test trough and the first qualifying three-month run after it."""
    start, end = (pd.Period(day, freq="M") for day in test_days)
    test = median.loc[start:end]
    if test.dropna().empty:
        raise ValueError("The test period has no observed core-well median SGI")
    trough = test.idxmin()
    run_minimum = test.rolling(RECOVERY_MONTHS).min().shift(1 - RECOVERY_MONTHS)
    qualifies = run_minimum.loc[trough + 1:].ge(THRESHOLD)
    if not qualifies.any():
        raise ValueError(f"No three-month recovery at or above {THRESHOLD:g} after the trough in {trough}")
    return trough, qualifies.index[qualifies][0]


def period_spans(splits):
    """Convert inclusive split dates to plotting spans with an exclusive right edge."""
    day = pd.Timedelta(days=1)
    train_start, train_end = map(pd.Timestamp, splits["train"])
    val_start, val_end = map(pd.Timestamp, splits["validation"])
    test_start, test_end = map(pd.Timestamp, splits["test"])
    spans = [("Train", train_start, train_end + day, "#f1f4f6", "#556577"),
             ("Validation", val_start, val_end + day, "#e9e8f4", "#5f527c")]
    for key, label, fill, accent in (
        ("test_drought", "Test drought", "#fdf0e1", "#8a5021"),
        ("test_recovery", "Test recovery", "#e4f2eb", "#326752"),
    ):
        start, end = TEST_PERIODS[key]
        spans.append((label, max(pd.Timestamp(start), test_start),
                      min(pd.Timestamp(end) if end else test_end, test_end) + day, fill, accent))
    return spans


def draw_period_shading(axes, spans):
    for label, start, end, fill, accent in spans:
        for ax in axes:
            ax.axvspan(start, end, facecolor=fill, linewidth=0, zorder=0)
            ax.axvline(start, color=accent, alpha=0.25, linewidth=0.55, zorder=1)
        # The final span is short. Align its label with the right edge and
        # leave room by placing the drought label in the left half of its span.
        anchor = start + 0.5 * (end - start)
        align = "center"
        if label == "Test drought":
            anchor = start + 0.29 * (end - start)
        if label == "Test recovery":
            anchor, align = end, "right"
        axes[0].annotate(label, (anchor, 1), xycoords=("data", "axes fraction"), xytext=(0, 5),
                         textcoords="offset points", ha=align, va="bottom", fontsize=7.3, color=accent)
        axes[0].plot([start, end], [1, 1], transform=axes[0].get_xaxis_transform(),
                     color=accent, linewidth=0.85, alpha=0.70, clip_on=False, solid_capstyle="butt")


def draw_observed(ax, monthly, median, dates, trough, recovery):
    lower = monthly.quantile(0.25, axis=1)
    upper = monthly.quantile(0.75, axis=1)
    band = ax.fill_between(dates, lower, upper, color=BAND_COLOR, alpha=0.48,
                           linewidth=0, label="Interquartile band", zorder=2)
    threshold = ax.axhline(THRESHOLD, color="#555d66", linewidth=0.8, linestyle=(0, (4, 2.4)),
                          label="Threshold (−0.5)", zorder=3)
    line, = ax.plot(dates, median, color=MEDIAN_COLOR, linewidth=1.05, label="Core-well median", zorder=4)
    halo = [effects.withStroke(linewidth=2.15, foreground="white")]
    for label, month, offset in (
        ("Trough", trough, (-16, 11)),
        ("Recovery starts", recovery, (-10, 22)),
    ):
        xy = (month.start_time, median.loc[month])
        ax.scatter(*xy, color=MEDIAN_COLOR, edgecolor="white", linewidth=0.65, s=20, zorder=5)
        ax.annotate(f"{label}\n{month.start_time:%b %Y}", xy=xy, xytext=offset, textcoords="offset points",
                    ha="right", va="bottom", color=INK, fontsize=7.3, path_effects=halo, zorder=6,
                    arrowprops={"arrowstyle": "-", "color": INK, "lw": 0.6, "shrinkB": 3})
    ax.figure.legend(handles=(line, band, threshold), loc="upper left",
                     bbox_to_anchor=(ax.get_position().x0, 0.986), ncols=3, fontsize=7.15,
                     frameon=False, labelcolor=INK, handlelength=1.65, handletextpad=0.5,
                     columnspacing=1.25, borderaxespad=0)


def draw_groups(ax, monthly, core_wells, dates):
    for i, (group, wells) in enumerate(core_wells.groupby("group", sort=False)):
        if len(wells) >= 3:
            # Use the study-area hues for the main groups and distinct line styles.
            colour, style = GROUP_STYLES.get(group, (f"C{i}", ":"))
            ax.plot(dates, monthly[wells.index].median(axis=1), color=colour, linestyle=style,
                    linewidth=1.05, label=f"{group[:1].upper() + group[1:]} ({len(wells)})", zorder=3)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.20), ncols=3, fontsize=7.4,
              frameon=False, labelcolor=INK, handlelength=2.2, columnspacing=1.5)


def draw_periods(out=OUT):
    """Write a vector PDF and a 200 dpi PNG. Return the monthly median, dates and counts."""
    heads = pd.read_parquet(DATA / "heads_weekly.parquet", columns=["week", "code_bss", "sgi"])
    wells = pd.read_parquet(DATA / "wells.parquet", columns=["code_bss", "core", "group"])
    core_wells = wells.loc[wells["core"]].set_index("code_bss")
    splits = json.loads((DATA / "splits.json").read_text(encoding="utf-8"))
    monthly = monthly_core_sgi(heads, core_wells, splits["model_start"])
    median = monthly.median(axis=1).rename("sgi")
    counts = monthly.count(axis=1).rename("core_wells")
    trough, recovery = observed_recovery(median, splits["test"])
    configured = pd.Period(TEST_PERIODS["test_recovery"][0], freq="M")
    if recovery != configured:
        raise ValueError(f"Observed recovery starts in {recovery}. TEST_PERIODS starts in {configured}.")

    dates = monthly.index.to_timestamp()
    fig, axes = plt.subplots(2, 1, sharex=True, figsize=(190 / 25.4, 97 / 25.4), facecolor="white")
    fig.subplots_adjust(left=0.083, right=0.975, bottom=0.155, top=0.884, hspace=0.19)
    draw_period_shading(axes, period_spans(splits))
    draw_observed(axes[0], monthly, median, dates, trough, recovery)
    draw_groups(axes[1], monthly, core_wells, dates)
    for label, ax in zip(("(a)", "(b)"), axes):
        ax.text(-0.057, 1.02, label, transform=ax.transAxes, ha="left", va="top",
                fontsize=8, fontweight="bold", color=INK)
        ax.axhline(0, color="#58636c", linewidth=0.55, alpha=0.25, zorder=1)
        ax.tick_params(axis="both", length=2.5, width=0.6, labelsize=7.4, colors=INK, pad=2.5)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        for spine in ("bottom", "left"):
            ax.spines[spine].set(color="#596777", linewidth=0.65)
        ax.set_yticks([-2, -1, 0, 1, 2])
    axes[0].tick_params(axis="x", bottom=False)
    axes[1].set_xticks(pd.date_range(dates[0], dates[-1], freq="3YS"))
    axes[1].xaxis.set_major_formatter(DateFormatter("%Y"))
    axes[1].set_xlim(dates[0], heads["week"].max() + pd.Timedelta(days=1))
    fig.supylabel("Monthly SGI", x=0.012, fontsize=8, color=INK)

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    with matplotlib.rc_context({"pdf.fonttype": 42}):
        fig.savefig(out / "periods.pdf", metadata={"Title": "Observed groundwater and periods", "CreationDate": None})
        fig.savefig(out / "periods.png", dpi=200)
    plt.close(fig)
    return median, trough, recovery, counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT, help="directory for the PDF and PNG")
    args = parser.parse_args()
    median, trough, recovery, counts = draw_periods(args.out)
    print(f"Observed trough {trough} (SGI {median.loc[trough]:.6f})")
    print("Recovery months")
    print(pd.concat([median, counts], axis=1).loc[recovery:recovery + RECOVERY_MONTHS - 1].to_string())


if __name__ == "__main__":
    main()
